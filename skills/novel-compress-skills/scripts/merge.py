#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge.py — 将所有 output/ch*.txt 拼接为一个完整压缩稿。

用法:
    python scripts/merge.py examples/夜的命名术 v3/output/ merged_novel.txt

输出格式:
    旁白：叙述内容
    角色名<情绪>：对话内容

参数:
    第一个位置参数: output/ 目录路径
    第二个位置参数: 输出文件路径（可选，默认 merged_novel.txt）
"""

import os, sys, re

def merge_output(indir, outfile):
    if not os.path.isdir(indir):
        print(f"[merge] ERROR: directory not found: {indir}", file=sys.stderr)
        sys.exit(2)

    files = sorted(
        [f for f in os.listdir(indir) if re.match(r"^ch\d+\.txt$", f)],
        key=lambda f: int(re.search(r"\d+", f).group())
    )

    if not files:
        print(f"[merge] ERROR: no chNNN.txt files found in {indir}", file=sys.stderr)
        sys.exit(2)

    total_chars = 0
    with open(outfile, "w", encoding="utf-8") as out:
        for fname in files:
            with open(os.path.join(indir, fname), encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                out.write(content + "\n\n")
                total_chars += len(content)

    print(f"[merge] {len(files)} chapters -> {outfile} ({total_chars} chars)")
    return total_chars

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/merge.py <output_dir> [merged_file]", file=sys.stderr)
        sys.exit(1)
    indir = sys.argv[1]
    outfile = sys.argv[2] if len(sys.argv) > 2 else "merged_novel.txt"
    merge_output(indir, outfile)
