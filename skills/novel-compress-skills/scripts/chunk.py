#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""chunk.py — 将单文件长篇小说切分为章节片段，供 Codex 逐章压缩。

设计哲学：不同小说的章节标记千差万别（第N章 / Chapter N / 卷 / 部 / 序号 /
【N】 / 纯空行 / 完全无标记），硬编码正则必然失灵或误判。本脚本不替 AI 做判断，
而是提供三类能力让 AI 在运行时按每本小说的实际结构决策：

  1. --probe        分析模式：列出候选标记的命中数/样本/切块大小分布，AI 据此选 pattern
  2. --pattern REGEX 选定模式：AI 写好正则后传入，脚本据此切分
  3. (默认)          无 pattern 时用三档兜底正则；仍无命中则退化为按字数切块（带重叠）

用法:
    python chunk.py <novel.txt> --probe                 # AI 先看分析
    python chunk.py <novel.txt> --pattern '^\s*第\d+章'  # AI 选定后切分
    python chunk.py <novel.txt> --out input              # 兜底自动切分
    python chunk.py <novel.txt> --target 20000 --overlap 1200  # 无标记时按字数

特性:
    - 纯标准库；自动探测编码（UTF-8/GBK/GB18030）
    - 输出 input/chNNN.txt + chunks_manifest.json（含前后文引用）
    - 切分后健康度自检：碎片率/大小悬殊/章节号漂移，异常即警告
"""
import argparse
import json
import os
import re
import statistics
import sys

# 候选章节标记（仅供 --probe 展示，让 AI 选择；不强制使用）
CANDIDATE_PATTERNS = [
    ('第N章(中文/阿拉伯)', r'^\s*第\s*[一二三四五六七八九十百千万零〇\d]+\s*章'),
    ('Chapter N', r'^\s*chapter\s+\d+'),
    ('第N卷/部', r'^\s*第\s*[一二三四五六七八九十百千万零〇\d]+\s*[卷部]'),
    ('N、/N./N: 标题', r'^\s*\d+\s*[、.．:：]\s*\S{1,40}'),
    ('【N】或[N]', r'^\s*[【\[]\s*\d+\s*[】\]]'),
    ('Chapter|序章|楔子|尾声', r'^\s*(chapter|序\s*章|楔\s*子|尾\s*声|终\s*章)'),
]

# 兜底三档（无 --pattern 时按优先级尝试；可靠档命中即忽略低档）
FALLBACK_TIERS = [
    [re.compile(r'^\s*第\s*[一二三四五六七八九十百千万零〇\d]+\s*章', re.M),
     re.compile(r'^\s*chapter\s+\d+', re.I | re.M)],
    [re.compile(r'^\s*第\s*[一二三四五六七八九十百千万零〇\d]+\s*[卷部]', re.M)],
    [re.compile(r'^\s*\d+\s*[:：、]\s*\S{1,30}$', re.M)],
]


def read_text(path):
    """自动探测编码：utf-8-sig / utf-8 / gb18030。"""
    last_err = None
    for enc in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            with open(path, encoding=enc) as f:
                return f.read(), enc
        except UnicodeDecodeError as e:
            last_err = e
    raise last_err


def find_positions(text, pattern_str=None):
    """返回章节边界位置列表。pattern_str 为 AI 提供的正则；为 None 则用兜底三档。"""
    if pattern_str:
        pat = re.compile(pattern_str, re.M)
        return sorted({m.start() for m in pat.finditer(text)})
    for tier in FALLBACK_TIERS:
        positions = sorted({m.start() for pat in tier for m in pat.finditer(text)})
        if positions:
            return positions
    return []


def split_by_boundaries(text, positions):
    if not positions:
        return None
    chunks, n = [], len(positions)
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < n else len(text)
        body = text[start:end].strip()
        if body:
            chunks.append(body)
    return chunks


def split_by_size(text, target, overlap):
    chunks, step = [], max(1, target - overlap)
    for i in range(0, len(text), step):
        seg = text[i:i + target].strip()
        if seg:
            chunks.append(seg)
    return chunks


def extract_title(chunk):
    lines = [l.strip() for l in chunk.splitlines() if l.strip()]
    return lines[0][:40] if lines else ''


def size_stats(chunks):
    chars = [len(c) for c in chunks]
    return {
        'count': len(chars),
        'min': min(chars) if chars else 0,
        'median': int(statistics.median(chars)) if chars else 0,
        'mean': int(statistics.mean(chars)) if chars else 0,
        'max': max(chars) if chars else 0,
        'tiny_lt200': sum(1 for c in chars if c < 200),
    }


def health_check(chunks, mode):
    """切分后健康度自检，返回告警列表。"""
    warnings = []
    if not chunks:
        return ['无切片产出']
    st = size_stats(chunks)
    if mode == 'chapter':
        tiny_ratio = st['tiny_lt200'] / st['count']
        if tiny_ratio > 0.02:
            warnings.append(f"碎片率 {tiny_ratio:.1%}（{st['tiny_lt200']}/{st['count']} 章不足200字），"
                             f"疑似正则误判正文行内列表项，建议改用 --probe 重选 pattern")
        if st['count'] > 5 and st['max'] / max(1, st['min']) > 30:
            warnings.append(f"大小悬殊 min={st['min']}/max={st['max']}，疑似正则切错边界")
        # 章节号漂移检测：从标题提数字看是否与序号一致
        nums = []
        for i, c in enumerate(chunks, 1):
            m = re.search(r'(\d+)', extract_title(c))
            if m:
                nums.append(int(m.group(1)))
        if len(nums) > st['count'] * 0.8:
            drift = sum(1 for i, n in enumerate(nums, 1) if n != i)
            if drift > st['count'] * 0.05:
                warnings.append(f"章节号与切片序号漂移 {drift}/{st['count']}，"
                                 f"疑似正则产生多余/缺失边界，建议 --probe 重选")
    return warnings


def probe(text):
    """分析模式：对每个候选正则打印命中数/样本/切块分布，供 AI 决策。"""
    print(f'[probe] 总字数 {len(text)}，候选标记分析（按命中数排序）：')
    print('=' * 70)
    rows = []
    for name, pat_str in CANDIDATE_PATTERNS:
        try:
            pat = re.compile(pat_str, re.M)
        except re.error:
            continue
        matches = list(pat.finditer(text))
        if not matches:
            continue
        samples = [m.group(0).strip()[:40] for m in matches[:3]]
        positions = sorted({m.start() for m in matches})
        chunks = split_by_boundaries(text, positions) or []
        st = size_stats(chunks)
        rows.append((len(matches), name, pat_str, samples, st))
    rows.sort(key=lambda r: -r[0])
    if not rows:
        print('[probe] 未发现任何候选章节标记 → 该小说可能无明确章节标记，')
        print('        建议改用按字数切块：--target 20000 --overlap 1200')
        return
    for cnt, name, pat_str, samples, st in rows:
        print(f'■ {name}  | 命中 {cnt} 次')
        print(f'  正则: {pat_str}')
        print(f'  样本: {samples}')
        print(f'  若用此切分: {st["count"]} 块 | 大小 min/中位/max = '
              f'{st["min"]}/{st["median"]}/{st["max"]} | <200字碎片 {st["tiny_lt200"]}')
        print('-' * 70)
    print('[probe] 建议：选「命中数合理、大小均匀、碎片为0」的那个正则，')
    print('        用 --pattern "<正则>" 切分；都不理想则用 --target 按字数切块。')


def main():
    ap = argparse.ArgumentParser(description='长篇小说切分工具（AI 自适应）')
    ap.add_argument('src', help='源 TXT 小说路径')
    ap.add_argument('--out', default='input', help='输出目录（默认 input）')
    ap.add_argument('--pattern', default=None,
                    help='AI 选定的章节标记正则（Python 语法，多行模式）；不传则用兜底三档')
    ap.add_argument('--probe', action='store_true', help='只分析不切分，打印候选标记统计')
    ap.add_argument('--overlap', type=int, default=800, help='按字数切块的重叠字符数')
    
    ap.add_argument('--limit', type=int, default=0, help='只切前N章（0=不限制）。试点/调参时强烈建议用')
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        print(f'[chunk] ERROR: 源文件不存在: {args.src}', file=sys.stderr)
        sys.exit(2)

    try:
        text, enc = read_text(args.src)
    except Exception as e:
        print(f'[chunk] ERROR: 读取失败: {e}', file=sys.stderr)
        sys.exit(2)
    print(f'[chunk] encoding={enc} chars={len(text)}')

    if args.probe:
        probe(text)
        return

    positions = find_positions(text, args.pattern)
    if positions:
        chunks = split_by_boundaries(text, positions)
        mode = 'chapter'
        mode_note = f'pattern={args.pattern!r}' if args.pattern else 'fallback-tier'
    else:
        chunks = split_by_size(text, args.target, args.overlap)
        mode = 'size'
        mode_note = f'target={args.target} overlap={args.overlap}'
        print('[chunk] 未发现/未提供章节标记，退化为按字数切块（带重叠区）。')

    os.makedirs(args.out, exist_ok=True)
    if args.limit > 0:
        chunks = chunks[:args.limit]
    manifest, total = [], 0
    for i, ch in enumerate(chunks, 1):
        fname = f'ch{i:03d}.txt'
        with open(os.path.join(args.out, fname), 'w', encoding='utf-8') as f:
            f.write(ch)
        c = len(ch)
        total += c
        manifest.append({
            'index': i, 'file': fname, 'title': extract_title(ch), 'chars': c,
            'prev': f'ch{i-1:03d}.txt' if i > 1 else None,
            'next': f'ch{i+1:03d}.txt' if i < len(chunks) else None,
        })
    with open(os.path.join(args.out, 'chunks_manifest.json'), 'w', encoding='utf-8') as f:
        json.dump({'mode': mode, 'mode_note': mode_note, 'count': len(chunks),
                   'total_chars': total, 'chunks': manifest}, f, ensure_ascii=False, indent=2)

    st = size_stats(chunks)
    print(f'[chunk] mode={mode} ({mode_note}) chapters={len(chunks)} total_chars={total}')
    print(f'[chunk] 大小 min/中位/max = {st["min"]}/{st["median"]}/{st["max"]} | <200字碎片 {st["tiny_lt200"]}')
    warnings = health_check(chunks, mode)
    if warnings:
        print('[chunk] [WARN] 健康度告警：')
        for w in warnings:
            print(f'  - {w}')
        print('[chunk] 建议改用 --probe 重新分析，或 --pattern 指定正确正则。')
    else:
        print('[chunk] 健康度自检通过。')
    print(f'[chunk] output dir: {args.out}/  (manifest: chunks_manifest.json)')


if __name__ == '__main__':
    main()
