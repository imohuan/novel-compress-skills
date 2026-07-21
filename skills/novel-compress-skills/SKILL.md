---
name: novel-toolkit
description: Use when the user provides a large TXT novel file and wants to compress/adapt it, extract key information, or build a story bible. Triggers: "压缩小说", "改编长篇", "小说精简", "故事线", "小说提炼", "剧情圣经", "生成有声小说", "TTS", "配音", "对话配音", "小说配音"
---

# 小说处理工具集

## Overview

把一个单文件 TXT 小说，用工程化流水线处理产出：

1. **压缩稿** — 对话格式正文
2. **剧情圣经** — `bible/` 目录：人物/设定/时间线/主线/弧摘要/写作手法
3. **拼接/审计** — `scripts/merge.py` + `scripts/verify.py`
4. **有声小说 TTS** — 从压缩稿 + 人物档案生成多角色配音音频

子代理并行、弧级分批，支持百万字级。

## Quick Start

```powershell
python scripts/chunk.py "examples/<小说名>/小说.txt" --probe         # 探测
python scripts/chunk.py "..." --pattern "^第" --out input --limit 20  # 切分
cp templates/{RULES,GOAL,VERIFY}.md examples/<小说名>/                # 模板
python scripts/merge.py output/ merged_novel.txt                      # 拼接
```

## 输出格式：Voice Design 对话体

```
角色名(自然语言描述)：对话内容
旁白：叙述内容
```

描述是自由形式的自然语言，直接作为 VoxCPM 的 Voice Design 指令。详细规则见 `references/emotion_tags.md`


## TTS 有声小说

从压缩稿 + 人物档案生成多角色配音音频。提供两种方式：

### 方式一：无 UI（推荐，全自动）

不用浏览器，`novel_tts.py` 两步走：

```
bible/characters.md
       │
       ▼  [AI 生成 voices_script.txt]
bible/voices_script.txt
       │
       ▼  [novel_tts.py — Step 1：生成基线音色]
tts_output/auto_refs/        ← 每个角色的基线音色 (wav)
       │
       ▼  [novel_tts.py — Step 2：生成章节音频]
tts_output/<chapter>/output.mp3
```

```bash
# Step 1：从音色脚本生成所有角色的基线音色
python scripts/novel_tts.py "bible/voices_script.txt" \
  --target "examples/<小说名>" \
  --url <VoxCPM2_URL>

# Step 2：用基线音色给某一章配音
python scripts/novel_tts.py "output/ch001.txt" \
  --target "examples/<小说名>" \
  --url <VoxCPM2_URL>
```

### 方式二：有 UI（手动精调）

适合对音色有极致要求的场景，用浏览器逐个角色试听和调整：

```
bible/characters.md
       │
       ▼  [AI 生成]
bible/voices_script.txt
       │
       ▼  [voice_tuner.py — 浏览器 UI 手动调音色]
tts_output/auto_refs/
       │
       ▼  [novel_tts.py — 章节对话生成]
tts_output/<chapter>/output.mp3
```

```bash
# Step 1：打开浏览器 UI 手动调整每个角色的音色
python scripts/voice_tuner.py --target "examples/<小说名>" --url <VoxCPM2_URL>

# Step 2：同方式一的 Step 2
```

完整操作指南见 `references/tts-guide.md`。

### Step 0：AI 生成音色脚本

从 `bible/characters.md` 读取人物档案，生成 `bible/voices_script.txt`。详见 `references/voices-script-guide.md`。

## 工作流

### 阶段一：单章试点

```
Step 0：询问压缩比（默认 35%）、是否要 analysis、黑名单章节
Step 1：探测 + 切分
Step 2：复制 RULES/GOAL/VERIFY 模板
Step 3：抽圣经（前 3 章）
Step 4：试点压缩 2-3 章 + 审计
```

### 阶段二：弧级分批

详见 `templates/PARALLEL.md`。

## Bible 结构

| 文件 | 内容 |
|------|------|
| characters.md | 人物三层：核心 / 弧级(chNNN) / 路人 |
| settings.md | 世界观 + 地点 + 科技 + 力量体系 |
| timeline.md | 时间线 |
| throughline.md | 主线钩子 + 伏笔 |
| arcs.md | 故事弧摘要 |
| writing_techniques.md | 写作手法知识库 |

## 章节分析

| 触发 | 产出 |
|------|------|
| 默认不生成 | 只出压缩稿 |
| 说"要 analysis" | 全章 |
| 说"补 chN-chM 的 analysis" | 指定章 |

## 快速命令

| 动作 | 命令 |
|---|---|
| 探测 | `python scripts/chunk.py novel.txt --probe` |
| 切分 | `python scripts/chunk.py ... --pattern '^第' --out input --limit N` |
| 拼接 | `python scripts/merge.py output/ merged_novel.txt` |
| 快照 | `python scripts/snapshot.py bible/` |
| 审计 | `python scripts/verify.py --manifest ... --output ... --min 0.30 --max 0.45` |
| TTS 音色调校 | `python scripts/voice_tuner.py --target "examples/<名>" --url <URL>` |
| TTS 章节配音 | `python scripts/novel_tts.py output/ch001.txt --target "examples/<名>" --url <URL>` |