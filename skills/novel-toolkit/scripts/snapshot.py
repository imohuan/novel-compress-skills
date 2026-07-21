#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""snapshot.py — 从 bible/ 四个文件生成轻量 bible_snapshot.md。

用途：子代理并行压缩时，不能读完整 bible（token 爆炸），用此脚本生成精简索引。

用法:
    python scripts/snapshot.py examples/小说名/bible/
    python scripts/snapshot.py bible/ -o bible/bible_snapshot.md

输出: bible_snapshot.md（人物索引 + 设定摘要 + 时间线 + 当前钩子）
"""

import argparse, os, sys, re
from datetime import datetime


def parse_characters(text):
    """提取：名字 | 层级 | 一句话描述"""
    entries = []
    current_name = None
    current_level = ""
    current_desc = []

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # ### 角色名 开头
        m = re.match(r"^### (.+)", line)
        if m:
            if current_name:
                entries.append((current_name, current_level, "; ".join(current_desc)))
            current_name = m.group(1)
            current_level = ""
            current_desc = []
            continue

        # - 层级：xxx
        m = re.match(r"^- 层级[:：]\s*(.+)", line)
        if m and current_name:
            current_level = m.group(1)
            continue

        # 其他描述行
        if current_name and line.startswith("- "):
            desc = line[2:].strip()
            # 跳过 "来源:" 行，除非是第一条描述
            if not desc.startswith("来源:") and not desc.startswith("层级"):
                current_desc.append(desc)

    # 最后一个
    if current_name:
        entries.append((current_name, current_level, "; ".join(current_desc)))

    return entries


def parse_settings(text):
    """提取 ## 标题下的内容，压缩到 2-3 句"""
    sections = []
    current_title = None
    current_lines = []

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        m = re.match(r"^## (.+)", line)
        if m:
            if current_title and current_lines:
                sections.append((current_title, current_lines[:3]))  # 最多3句
            current_title = m.group(1)
            current_lines = []
            continue

        m = re.match(r"^### (.+)", line)
        if m:
            if current_title and current_lines:
                sections.append((current_title, current_lines[:3]))
            current_title = m.group(1)
            current_lines = []
            continue

        if current_title and line.startswith("- "):
            current_lines.append(line[2:].strip())

    if current_title and current_lines:
        sections.append((current_title, current_lines[:3]))

    return sections


def parse_hooks(text):
    """提取 '当前钩子' 之后的状态表"""
    in_hooks = False
    hooks = []
    for line in text.split("\n"):
        line = line.strip()
        if "当前钩子" in line:
            in_hooks = True
            continue
        if in_hooks and line.startswith("## "):
            break
        if in_hooks and line.startswith("| ch"):
            hooks.append(line)
    return hooks


def main():
    ap = argparse.ArgumentParser(description="从 bible 生成轻量 snapshot")
    ap.add_argument("bible_dir", help="bible/ 目录路径")
    ap.add_argument("-o", "--output", default=None, help="输出路径（默认 bible_dir/bible_snapshot.md）")
    args = ap.parse_args()

    bible_dir = args.bible_dir
    if not os.path.isdir(bible_dir):
        print(f"[snapshot] ERROR: directory not found: {bible_dir}", file=sys.stderr)
        sys.exit(2)

    required = ["characters.md", "settings.md", "timeline.md"]
    optional = ["throughline.md"]

    for fn in required:
        if not os.path.isfile(os.path.join(bible_dir, fn)):
            print(f"[snapshot] ERROR: {fn} not found in {bible_dir}", file=sys.stderr)
            sys.exit(2)

    for fn in optional:
        if not os.path.isfile(os.path.join(bible_dir, fn)):
            print(f"[snapshot] WARN: {fn} not found, skipping hooks extraction")

    # Read files
    with open(os.path.join(bible_dir, "characters.md"), encoding="utf-8") as f:
        char_text = f.read()
    with open(os.path.join(bible_dir, "settings.md"), encoding="utf-8") as f:
        sett_text = f.read()
    with open(os.path.join(bible_dir, "timeline.md"), encoding="utf-8") as f:
        time_text = f.read()

    hook_text = ""
    tl_path = os.path.join(bible_dir, "throughline.md")
    if os.path.isfile(tl_path):
        with open(tl_path, encoding="utf-8") as f:
            hook_text = f.read()

    # Parse
    chars = parse_characters(char_text)
    settings = parse_settings(sett_text)
    hooks = parse_hooks(hook_text) if hook_text else []

    # Build output
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    out = [f"# Bible Snapshot (生成: {now})", ""]

    out.append("## 人物索引")
    out.append("")
    out.append("| 名字 | 层级 | 描述 |")
    out.append("|------|------|------|")
    for name, level, desc in chars:
        if not name:
            continue
        desc_short = desc[:80] + "..." if len(desc) > 80 else desc
        out.append(f"| {name} | {level} | {desc_short} |")
    out.append("")

    out.append("## 设定摘要")
    out.append("")
    for title, lines in settings:
        out.append(f"### {title}")
        for l in lines:
            out.append(f"- {l}")
        out.append("")
    out.append("")

    out.append("## 时间线")
    out.append("")
    out.append(time_text.strip())
    out.append("")

    if hooks:
        out.append("## 当前钩子")
        out.append("")
        for h in hooks:
            out.append(h)
        out.append("")

    output_path = args.output or os.path.join(bible_dir, "bible_snapshot.md")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    print(f"[snapshot] {len(chars)} characters, {len(settings)} setting groups, "
          f"{len(hooks)} hooks -> {output_path}")
    print(f"[snapshot] size: {len('\n'.join(out))} chars")


if __name__ == "__main__":
    main()
