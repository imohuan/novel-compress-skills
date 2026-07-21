# novel-compress-skills

面向 Codex 的长篇小说压缩与改编技能。它把“把百万字小说压缩成可读短篇”拆成可执行、可恢复、可核验的处理流程，而不是依赖一次性长上下文对话。

## 解决什么问题

适用于以下任务：

- 压缩长篇 TXT 小说，保留主线、关键冲突、人物弧和独有设定
- 从原文提炼人物、世界观、时间线、伏笔和故事弧，生成剧情圣经
- 按章节或故事弧批量处理百万字级文本
- 对压缩稿执行拼接、字数比例和输出完整性审计
- 根据压缩稿和人物档案生成多角色有声小说 TTS 音频

技能的核心原则是：

```text
原始小说
   │
   ▼
分块 → 剧情圣经 → 逐章压缩 → 增量回写 → 审计 → 合并 / TTS
```

压缩是有损处理。主观的删留判断、敏感内容处理和最终质量验收仍需要人工确认。

## 快速开始

### 1. 准备输入目录

建议为每部小说建立独立目录，并将原始 TXT 放在其中：

```text
examples/
└── <小说名>/
    └── novel.txt
```

### 2. 探测并切分小说

以下命令在 `skills/novel-compress-skills` 目录下执行：

```powershell
python scripts/chunk.py "examples/<小说名>/novel.txt" --probe
python scripts/chunk.py "examples/<小说名>/novel.txt" --pattern "^第" --out input
```

`--probe` 用于查看章节标题和文本规模；确认切分规则后，再执行实际切分。

### 3. 创建任务规则

将模板复制到小说目录，根据目标修改：

- `GOAL.md`：目标、范围、完成条件和断点恢复信息
- `RULES.md`：删留标准、文风、禁用表达和压缩比例
- `VERIFY.md`：压缩结果的验证方式
- `LOG.md`：执行过程、异常和人工决策记录
- `templates/bible/`：剧情圣经模板

建议先处理 2 至 3 章进行试点，确认压缩比例、叙事风格和人物一致性，再扩展到全书。

### 4. 合并和审计结果

```powershell
python scripts/merge.py output/ merged_novel.txt
python scripts/verify.py --manifest <manifest.json> --output output/ --min 0.30 --max 0.45
```

最终正文使用 Voice Design 对话体：

```text
角色名（自然语言音色描述）：对话内容
旁白：叙述内容
```

角色描述会直接作为 VoxCPM 的 Voice Design 指令使用。

## TTS 有声小说

TTS 流程需要可访问的 VoxCPM 服务地址，并分为两个步骤。

### 自动生成

先根据人物档案准备 `bible/voices_script.txt`，再运行：

```powershell
# 生成角色基线音色
python scripts/novel_tts.py "bible/voices_script.txt" `
  --target "examples/<小说名>" `
  --url "<VoxCPM2_URL>"

# 为章节生成音频
python scripts/novel_tts.py "output/ch001.txt" `
  --target "examples/<小说名>" `
  --url "<VoxCPM2_URL>"
```

### 手动调音

需要逐个试听和微调角色音色时，使用浏览器 UI：

```powershell
python scripts/voice_tuner.py `
  --target "examples/<小说名>" `
  --url "<VoxCPM2_URL>"
```

完整 TTS 说明见 [`tts-guide.md`](skills/novel-compress-skills/references/tts-guide.md)，音色脚本规范见 [`voices-script-guide.md`](skills/novel-compress-skills/references/voices-script-guide.md)。

## 目录结构

```text
skills/novel-compress-skills/
├── SKILL.md                       # Codex 技能入口和触发条件
├── templates/                     # GOAL、RULES、VERIFY、并行任务等模板
│   └── bible/                     # 剧情圣经模板
├── scripts/
│   ├── chunk.py                   # 探测和切分原文
│   ├── merge.py                   # 合并压缩稿
│   ├── verify.py                  # 输出审计
│   ├── snapshot.py                # 剧情圣经快照
│   ├── novel_tts.py               # 批量生成章节音频
│   └── voice_tuner.py             # 浏览器音色调校
├── references/                    # 写作、情绪标签和 TTS 参考资料
└── 基于Codex目标导向模式的百万字小说压缩改编方法论.md
                                    # 方法论与实践经验
```

## 推荐工作流

1. **定义目标**：明确压缩比例、保留内容、文风和输出格式。
2. **单章试点**：探测、切分、抽取初始剧情圣经，压缩 2 至 3 章。
3. **建立真相源**：维护人物、设定、时间线、主线和故事弧，按章增量更新。
4. **分批执行**：按章节或故事弧处理，避免整本小说一次性进入上下文。
5. **独立审计**：检查输出完整性、压缩比例、人物关系和关键伏笔。
6. **人工签收**：对删留结果、敏感内容和最终成稿进行人工复核。
7. **扩展产出**：将通过审计的压缩稿合并，或进入多角色 TTS 流程。

## 相关文档

- [`SKILL.md`](skills/novel-compress-skills/SKILL.md)：Codex 实际加载的技能说明
- [`methodology.md`](skills/novel-compress-skills/references/methodology.md)：方法论摘要
- [`emotion_tags.md`](skills/novel-compress-skills/references/emotion_tags.md)：对话情绪标签规则
- [`tts-guide.md`](skills/novel-compress-skills/references/tts-guide.md)：TTS 操作指南
- [`voices-script-guide.md`](skills/novel-compress-skills/references/voices-script-guide.md)：角色音色脚本规范
- [`百万字小说压缩改编方法论`](skills/novel-compress-skills/基于Codex目标导向模式的百万字小说压缩改编方法论.md)：完整研究与风险分析

## 注意事项

- 原始小说、生成稿和剧情圣经应分开保存，并保留可回溯的章节锚点。
- 不要跳过章节处理后的剧情圣经回写，否则人物和伏笔容易逐步漂移。
- 不要把“压缩比例达标”当成唯一质量指标；因果链、人物动机和关键限定条件同样需要审计。
- TTS 音频依赖外部 VoxCPM 服务，服务地址、模型能力和音色质量不由本项目保证。