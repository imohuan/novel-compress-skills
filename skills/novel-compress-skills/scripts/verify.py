#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py — 机械验收：压缩比 + 关键人物/设定是否保留。

用法:
    python verify.py --manifest input/chunks_manifest.json \
        --output output --min 0.3 --max 0.5 [--bible bible]
    python verify.py ... --entities-file entities.txt

退出码: 0=通过, 1=不通过
"""
import argparse
import json
import os
import re
import sys


def load_output(output_dir):
    text = ""
    chars = 0
    if not os.path.isdir(output_dir):
        return text, chars
    for fn in sorted(os.listdir(output_dir)):
        if fn.endswith(".txt") or fn.endswith(".md"):
            with open(os.path.join(output_dir, fn), encoding="utf-8") as f:
                t = f.read()
            text += t
            chars += len(t)
    return text, chars


def load_entities(bible_dir):
    names = []
    if not bible_dir or not os.path.isdir(bible_dir):
        return names
    for fn in os.listdir(bible_dir):
        if not fn.endswith(".md"):
            continue
        with open(os.path.join(bible_dir, fn), encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                m = re.match(r"^\s*[-*]\s*(?:\*{1,3})?(.+?)(?:\*{1,3})?\s*[：:（(]", line)
                if m:
                    name = m.group(1).strip()
                    if name:
                        names.append(name)
                    continue
                m = re.match(r"^\s*[-*]\s*(?:\*{1,3})?(.+?)(?:\*{1,3})?\s*$", line)
                if m:
                    name = m.group(1).strip()
                    if 2 <= len(name) <= 12 and not name.startswith("#") and name[0] not in "-*":
                        names.append(name)
                    continue
                m = re.match(r"^\s*([\u4e00-\u9fa5a-zA-Z]{2,12})\s*[：:（(]", line)
                if m:
                    names.append(m.group(1).strip())
                    continue
                m = re.match(r"^\s*\d+\.\s*(.+?)\s*$", line)
                if m:
                    name = m.group(1).strip()
                    if 2 <= len(name) <= 12:
                        names.append(name)
    seen = set()
    out = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def load_entities_from_file(filepath):
    """从纯文本文件加载实体名，一行一个，忽略#开头的注释和列表符号"""
    entities = []
    if not filepath or not os.path.isfile(filepath):
        return entities
    with open(filepath, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = re.sub(r"^[-*#\d\.\s]+", "", line).strip()
            if len(name) >= 2:
                entities.append(name)
    return entities


def main():
    ap = argparse.ArgumentParser(description="机械验收：压缩比 + 关键实体保留")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--min", type=float, default=0.3)
    ap.add_argument("--max", type=float, default=0.5)
    ap.add_argument("--bible", default=None, help="bible/ 目录")
    ap.add_argument("--entities-file", default=None, help="纯实体名列表文件（一行一个），比--bible更干净可靠")
    args = ap.parse_args()

    if not os.path.isfile(args.manifest):
        print(f"[verify] ERROR: manifest not found: {args.manifest}", file=sys.stderr)
        sys.exit(2)

    # 读 manifest（BOM 容错）
    try:
        with open(args.manifest, encoding="utf-8-sig") as f:
            man = json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError):
        with open(args.manifest, encoding="utf-8") as f:
            man = json.load(f)

    # 子集校验：output 中实际存在的文件对应各 chunk 的 chars 之和
    original = man.get("total_chars", 0)
    output_files = set(os.listdir(args.output)) if os.path.isdir(args.output) else set()
    actual_input = sum(c["chars"] for c in man.get("chunks", []) if c["file"] in output_files)
    if actual_input > 0:
        original = actual_input

    out_text, out_chars = load_output(args.output)
    ratio = (out_chars / original) if original else 0

    ok = True
    print(f"[verify] input_chars={original} output_chars={out_chars} ratio={ratio:.2%}")
    if not (args.min <= ratio <= args.max):
        print(f"[verify] FAIL: ratio {ratio:.2%} outside [{args.min:.0%}, {args.max:.0%}]")
        ok = False
    else:
        print("[verify] OK: ratio within band")

    # 实体校验：优先用 --entities-file
    entities = load_entities_from_file(args.entities_file)
    if not entities and args.bible:
        entities = load_entities(args.bible)

    if entities:
        missing = [e for e in entities if e not in out_text]
        if missing:
            print(f"[verify] FAIL: {len(missing)} key entities missing: {missing[:10]}")
            ok = False
        else:
            print(f"[verify] OK: all {len(entities)} key entities present")

    print("[verify] RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()