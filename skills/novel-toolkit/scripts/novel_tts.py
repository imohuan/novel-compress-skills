#!/usr/bin/env python3
"""
小说角色对话 TTS 合成脚本
解析 TXT 格式的角色对话脚本，调用 VoxCPM2 逐条生成音频，合并为完整播客。

语音生成模式（按优先级）：
  1. 极致克隆   — ref_wav + prompt_text (--use-ultimate-clone)
  2. 可控克隆   — ref_wav + control_instruction
  3. 纯音频克隆 — ref_wav only
  4. 声音设计   — control_instruction only
  5. 最简调用   — text only

音色一致性：
  首次生成的音频会自动保存为该角色后续的参考音频 (Self-Bootstrapping)

两步工作流：
  Step 1: AI 从 bible/characters.md 生成 bible/voices_script.txt
  Step 2: python novel_tts.py voices_script.txt --target <dir> --url <url>  ← 生成基线音色
  Step 3: python novel_tts.py output/ch001.txt --target <dir> --url <url>  ← 生成对话音频

用法:
  # 推荐：使用 --target（自动发现参考音频、输出目录）
  python novel_tts.py script.txt --target "examples/夜的命名术 v4" --url http://host:8808

  # 兼容旧用法（散装参数）
  python novel_tts.py script.txt -o output_dir --role-audio "庆尘=荒泷一斗.mp3"

  # 生成角色配置模板（扫描脚本中的角色）
  python novel_tts.py script.txt --gen-role-config roles.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from gradio_client import Client, handle_file

# ============================================================
# 默认配置
# ============================================================
DEFAULT_HOST = "localhost:8808"
DEFAULT_URL = "http://localhost:8808"
DEFAULT_CFG = 2.0
DEFAULT_DIT_STEPS = 10
DEFAULT_GAP_MS = 400
DEFAULT_DENOISE = False
DEFAULT_DO_NORMALIZE = False
DEFAULT_USE_ULTIMATE_CLONE = False

# ============================================================
# 日志
# ============================================================

def _color(text: str, code: str) -> str:
    codes = {"green": 32, "red": 31, "yellow": 33, "cyan": 36, "bold": 1}
    return f"\033[{codes.get(code, 0)}m{text}\033[0m"


def log_info(msg):   print(f"  {msg}")
def log_step(msg):   print(_color(f"  \u2192 {msg}", "cyan"))
def log_ok(msg):     print(_color(f"  \u2713 {msg}", "green"))
def log_warn(msg):   print(_color(f"  \u26a0 {msg}", "yellow"))
def log_error(msg):  print(_color(f"  \u2717 {msg}", "red"))


# ============================================================
# FFmpeg 工具
# ============================================================

def ffprobe_duration(filepath: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", filepath,
    ]
    return float(subprocess.check_output(cmd, text=True).strip())


def ffmpeg_convert(src: str, dst: str, fmt: str = "mp3"):
    """转码: 任意格式 -> mp3/wav"""
    if fmt == "mp3":
        codec = ["-codec:a", "libmp3lame", "-q:a", "2"]
    else:
        codec = ["-acodec", "pcm_s16le", "-ar", "16000"]
    subprocess.run(["ffmpeg", "-y", "-i", src, *codec, dst],
                   check=True, capture_output=True)


def ffmpeg_generate_silence(output: str, duration_ms: int):
    """生成静音 MP3 文件"""
    dur = duration_ms / 1000.0
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", str(dur),
        "-codec:a", "libmp3lame", "-q:a", "2",
        output,
    ], check=True, capture_output=True)


def ffmpeg_concat(file_list: list[str], output: str, gap_ms: int = 0):
    """拼接 MP3 文件。有间隔时插入静音。"""
    if not file_list:
        log_error("empty file list")
        return

    if gap_ms <= 0:
        list_file = Path(output).parent / "_concat.txt"
        list_file.write_text("\n".join(f"file '{f}'" for f in file_list), encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-codec", "copy", output,
        ], check=True, capture_output=True)
        list_file.unlink(missing_ok=True)
    else:
        silence_file = str(Path(output).parent / "_silence.mp3")
        ffmpeg_generate_silence(silence_file, gap_ms)
        expanded = []
        for i, f in enumerate(file_list):
            expanded.append(f)
            if i < len(file_list) - 1:
                expanded.append(silence_file)
        list_file = Path(output).parent / "_concat.txt"
        list_file.write_text("\n".join(f"file '{f}'" for f in expanded), encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-codec", "copy", output,
        ], check=True, capture_output=True)
        list_file.unlink(missing_ok=True)
        Path(silence_file).unlink(missing_ok=True)

    log_ok(f"\u5408\u5e76\u5b8c\u6210 \u2192 {output}")


# ============================================================
# TXT 解析
# ============================================================

LINE_PATTERN = re.compile(
    r"^(.+?)\s*[(（]\s*(.*?)\s*[)）]\s*[：:]\s*(.+)$"
)
SIMPLE_PATTERN = re.compile(
    r"^(.+?)\s*[：:]\s*(.+)$"
)


def parse_script(filepath: str) -> list[dict]:
    """解析 TXT -> [{角色, 音色, 台词}]，无法匹配的归为旁白"""
    with open(filepath, "r", encoding="utf-8-sig") as f:
        raw = f.read()

    lines = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        m = LINE_PATTERN.match(line)
        if m:
            lines.append({
                "角色": m.group(1).strip(),
                "音色": m.group(2).strip(),
                "台词": m.group(3).strip(),
            })
            continue

        m = SIMPLE_PATTERN.match(line)
        if m:
            lines.append({
                "角色": m.group(1).strip(),
                "音色": None,
                "台词": m.group(2).strip(),
            })
            continue

        lines.append({"角色": "旁白", "音色": None, "台词": line})

    return lines


# ============================================================
# VoxCPM2 客户端
# ============================================================

class VoxCPM2Client:
    def __init__(self, url: str):
        self.url = url
        self._client = None

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = Client(self.url)
        return self._client

    def generate(
        self, text, control_instruction="", ref_wav=None,
        use_prompt_text=False, prompt_text_value="",
        cfg_value=DEFAULT_CFG, do_normalize=DEFAULT_DO_NORMALIZE,
        denoise=DEFAULT_DENOISE, dit_steps=DEFAULT_DIT_STEPS,
    ) -> str:
        result = self.client.predict(
            text=text,
            control_instruction=control_instruction,
            ref_wav=handle_file(ref_wav) if ref_wav else None,
            use_prompt_text=use_prompt_text,
            prompt_text_value=prompt_text_value,
            cfg_value=cfg_value,
            do_normalize=do_normalize,
            denoise=denoise,
            dit_steps=dit_steps,
            api_name="/generate",
        )
        if isinstance(result, tuple) and len(result) >= 2:
            return str(result[1])
        if isinstance(result, str):
            return result
        if isinstance(result, list) and result:
            return str(result[0])
        raise RuntimeError(f"unexpected result: {type(result)}")


# ============================================================
# 音色管理器
# ============================================================

AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}


class VoiceManager:
    """
    管理角色 -> 参考音频映射。
    查找优先级：
      1. 用户显式指定的映射 (role_map)
      2. auto_refs 字典（运行时自引导）
      3. ref_dirs 中按角色名前缀匹配文件
    """

    def __init__(self, ref_dirs: list[Path], role_map: dict[str, str] | None = None, force_rebuild: bool = False):
        self.ref_dirs = ref_dirs
        self.role_map = role_map or {}
        self.auto_refs: dict[str, str] = {}
        self.force_rebuild = force_rebuild

    def _find_in_dirs(self, role: str) -> str | None:
        """在 ref_dirs 中按角色名前缀匹配音频文件"""
        for d in self.ref_dirs:
            if not d.exists():
                continue
            for f in sorted(d.iterdir()):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in AUDIO_EXTS:
                    continue
                stem = f.stem  # 不含后缀的文件名
                # 精确匹配 或 前缀+分隔符匹配（如 庆尘_ref, 庆尘-v1）
                if stem == role:
                    return str(f.resolve())
                if stem.startswith(role) and len(stem) > len(role) and stem[len(role)] in ("_", "-", "."):
                    return str(f.resolve())
        return None

    def get_ref(self, role: str) -> str | None:
        # 0. force rebuild: ignore all existing refs
        if self.force_rebuild:
            return None
        # 1. 用户指定映射
        if role in self.role_map:
            fname = self.role_map[role]
            for d in self.ref_dirs:
                path = d / fname
                if path.exists():
                    return str(path.resolve())
            log_warn(f"specified ref {fname} not found for [{role}]")

        # 2. 运行时自引导
        if role in self.auto_refs:
            return self.auto_refs[role]

        # 3. 目录前缀匹配
        return self._find_in_dirs(role)

    def register_auto_ref(self, role: str, path: str):
        self.auto_refs[role] = path
        log_info(f"[{role}] -> auto ref: {os.path.basename(path)}")


# ============================================================
# 角色配置模板
# ============================================================

def generate_role_config(script_path: str, output_path: str):
    segments = parse_script(script_path)
    roles = {}
    for s in segments:
        r = s["角色"]
        if r not in roles:
            roles[r] = ""
    config = {
        "_comment": "fill audio filename for each role (empty = auto-generate ref)",
        "_ref_audio_dir": str(Path(output_path).parent.resolve()),
        "roles": roles,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    log_ok(f"config template -> {output_path}")


# ============================================================
# 主流程
# ============================================================

def run(args: argparse.Namespace):
    start_time = time.time()

    if args.gen_role_config:
        generate_role_config(args.script, args.gen_role_config)
        return

    # ---- 0. 解析 --target ----
    target = Path(args.target) if args.target else None

    # 从脚本文件名提取章节号 (e.g. ch001.txt -> ch001)
    script_stem = Path(args.script).stem
    chap_match = re.match(r"(ch\d+)", script_stem, re.IGNORECASE)
    chapter_id = chap_match.group(1) if chap_match else script_stem

    # 输出目录: {target}/tts_output/{chapter}/
    out_dir = Path(args.output)
    if target and args.output == "./tts_output":  # 默认值未被覆盖
        out_dir = target / "tts_output"
    out_dir = out_dir / chapter_id

    # 参考音频搜索目录
    ref_dirs: list[Path] = []
    if args.ref_audio_dir:
        ref_dirs.append(Path(args.ref_audio_dir))
    if target:
        auto_dir = target / "tts_output" / "auto_refs"
        if auto_dir.exists() and auto_dir not in ref_dirs:
            ref_dirs.insert(0, auto_dir)  # 优先搜索 auto_refs

    # ---- 1. 解析 ----
    log_step("parse script...")
    segments = parse_script(args.script)
    log_ok(f"{len(segments)} lines")
    for i, s in enumerate(segments):
        d = f"[{s['角色']}]"
        if s["音色"]:
            d += f" ({s['音色']})"
        t = s["台词"][:60] + ("..." if len(s["台词"]) > 60 else "")
        log_info(f"  {i+1:04d} {d}: {t}")

    # ---- 2. 角色映射 ----
    role_map: dict[str, str] = {}
    for m in args.role_audio or []:
        if "=" in m:
            r, f = m.split("=", 1)
            role_map[r.strip()] = f.strip()
    if args.role_config:
        with open(args.role_config, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        src = cfg.get("roles", cfg)
        for r, fn in src.items():
            if fn and not str(r).startswith("_"):
                role_map[r] = fn
    if role_map:
        log_info(f"role map: {json.dumps(role_map, ensure_ascii=False)}")
    if ref_dirs:
        log_info(f"ref dirs: {[str(d) for d in ref_dirs]}")

    # ---- 3. 初始化 ----
    log_step(f"connect VoxCPM2 ({args.url})...")
    tts = VoxCPM2Client(args.url)

    out_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir = out_dir / "chunks"
    # auto_refs 共享：放在 tts_output/auto_refs/（不在章节子目录下）
    if target:
        auto_ref_dir = target / "tts_output" / "auto_refs"
    else:
        auto_ref_dir = out_dir.parent / "auto_refs"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    auto_ref_dir.mkdir(parents=True, exist_ok=True)

    vm = VoiceManager(ref_dirs, role_map, force_rebuild=args.force_rebuild)

    meta = {
        "script": str(Path(args.script).resolve()),
        "output_dir": str(out_dir.resolve()),
        "url": args.url,
        "target": str(target.resolve()) if target else None,
        "ref_dirs": [str(d.resolve()) for d in ref_dirs],
        "force_rebuild": args.force_rebuild,
        "defaults": {
            "cfg": args.cfg, "dit_steps": args.dit_steps,
            "denoise": args.denoise, "do_normalize": args.normalize,
            "use_ultimate_clone": args.use_ultimate_clone, "gap_ms": args.gap,
        },
        "segments": [],
        "started_at": datetime.now().isoformat(),
    }

    # ---- 4. 逐条生成 ----
    total = len(segments)
    ok = fail = 0

    for i, seg in enumerate(segments):
        idx = i + 1
        role = seg["角色"]
        desc = seg["音色"] or ""
        text = seg["台词"]

        chunk_name = f"{idx:04d}_{role}.mp3"
        chunk_path = chunk_dir / chunk_name
        ref = vm.get_ref(role)

        sm = {
            "index": idx, "角色": role, "音色": desc, "台词": text,
            "chunk_file": str(chunk_path.resolve()),
            "mode": None, "ref_wav": ref, "ref_source": None,
        }

        # 记录参考音频来源
        if ref:
            if role in role_map:
                sm["ref_source"] = "user_map"
            elif role in vm.auto_refs:
                sm["ref_source"] = "auto_refs"
            else:
                sm["ref_source"] = "dir_match"

        # 决定模式
        if args.use_ultimate_clone and ref:
            mode = "ultimate"
            up, pt, ci = True, text, ""
        elif ref:
            mode = "clone" if desc else "clone-only"
            up, pt, ci = False, "", desc
        elif desc:
            mode = "design"
            up, pt, ci = False, "", desc
        else:
            mode = "bare"
            up, pt, ci = False, "", ""

        sm["mode"] = mode
        sm["control_instruction"] = ci
        sm["cfg"] = args.cfg
        sm["dit_steps"] = args.dit_steps

        print()
        log_step(f"[{idx}/{total}] {mode} | [{role}]: {text[:30]}...")

        try:
            t0 = time.time()
            raw = tts.generate(
                text=text, control_instruction=ci, ref_wav=ref,
                use_prompt_text=up, prompt_text_value=pt,
                cfg_value=args.cfg, do_normalize=args.normalize,
                denoise=args.denoise, dit_steps=args.dit_steps,
            )
            elapsed = time.time() - t0

            ffmpeg_convert(raw, str(chunk_path), "mp3")
            dur = ffprobe_duration(str(chunk_path))
            sm["duration_sec"] = round(dur, 2)
            sm["elapsed_sec"] = round(elapsed, 1)
            sm["file_size"] = chunk_path.stat().st_size

            if ref is None:
                ref_wav = auto_ref_dir / f"{role}_ref.wav"
                ffmpeg_convert(raw, str(ref_wav), "wav")
                vm.register_auto_ref(role, str(ref_wav.resolve()))
                sm["auto_ref_saved"] = str(ref_wav.resolve())

            ok += 1
            log_ok(f"done ({elapsed:.1f}s, {dur:.1f}s)")

        except Exception as e:
            fail += 1
            sm["error"] = str(e)
            sm["traceback"] = traceback.format_exc()
            log_error(f"fail: {e}")

        meta["segments"].append(sm)

    # ---- 5. 元数据 ----
    meta["total"] = total
    meta["success"] = ok
    meta["failed"] = fail
    meta["elapsed_total_sec"] = round(time.time() - start_time, 1)

    mp = out_dir / "metadata.json"
    mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log_ok(f"metadata -> {mp}")

    # ---- 6. 合并 ----
    print()
    log_step(f"merge {ok} chunks...")
    chunks = sorted(str(p.resolve()) for p in chunk_dir.glob("*.mp3"))
    ffmpeg_concat(chunks, str(out_dir / "output.mp3"), gap_ms=args.gap)

    # ---- 7. 汇总 ----
    print()
    print(_color("=" * 50, "bold"))
    s_ok  = _color(str(ok), "green")
    s_fail = _color(str(fail), "red") if fail else _color("0", "green")
    print(f"  total: {total}  ok: {s_ok}  fail: {s_fail}  time: {meta['elapsed_total_sec']:.0f}s")
    print(_color("=" * 50, "bold"))

    if fail:
        sys.exit(1)


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="novel dialogue TTS (VoxCPM2)")
    parser.add_argument("script", help="input TXT")

    # 路径参数
    parser.add_argument("--target", help="project root dir (auto-discovers bible/, auto_refs/, output)")
    parser.add_argument("-o", "--output", default="./tts_output", help="output dir (default ./tts_output or {target}/tts_output)")
    parser.add_argument("--ref-audio-dir", help="extra reference audio dir (also auto-discovers from --target)")

    # 服务地址
    parser.add_argument("--url", default=DEFAULT_URL, help="full URL like http://host:8808")
    parser.add_argument("--host", default=DEFAULT_HOST, help="host:port shortcut (overridden by --url)")

    # 角色映射（可选，--target 模式下通常不需要）
    parser.add_argument("--role-audio", action="append", help='"role=file.mp3"')
    parser.add_argument("--role-config", help="role mapping JSON")
    parser.add_argument("--gen-role-config", metavar="OUT.json", help="generate role config template")

    # TTS 参数
    parser.add_argument("--cfg", type=float, default=DEFAULT_CFG)
    parser.add_argument("--dit-steps", type=int, default=DEFAULT_DIT_STEPS)
    parser.add_argument("--denoise", action="store_true", default=DEFAULT_DENOISE)
    parser.add_argument("--normalize", action="store_true", default=DEFAULT_DO_NORMALIZE)
    parser.add_argument("-f", "--force-rebuild", action="store_true", help="ignore existing refs, regenerate all from scratch")
    parser.add_argument("--use-ultimate-clone", action="store_true", default=DEFAULT_USE_ULTIMATE_CLONE)
    parser.add_argument("--gap", type=int, default=DEFAULT_GAP_MS, help="gap silence (ms)")

    args = parser.parse_args()

    # --url overrides --host
    if args.url == DEFAULT_URL and args.host != DEFAULT_HOST:
        args.url = f"http://{args.host}"

    if not args.gen_role_config:
        print(_color("=" * 50, "bold"))
        print(_color("  novel dialogue TTS", "bold"))
        print(f"  script: {args.script}")
        print(f"  target: {args.target or '(none)'}")
        print(f"  output: {args.output}")
        print(f"  url:    {args.url}")
        print(_color("=" * 50, "bold"))
        print()

    run(args)


if __name__ == "__main__":
    main()

