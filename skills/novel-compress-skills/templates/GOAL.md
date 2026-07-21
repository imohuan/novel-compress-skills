# 小说压缩执行契约

> 从 templates/ 复制到工作目录，填参数后确认。

## 目标

逐章压缩 input/ 原文为 Voice Design 对话格式，写入 output/；增量回写 bible（人物三层分级+弧+写作手法）。

## 范围

- 只读：input/chNNN.txt、bible/、exclude.txt
- 只写：output/chNNN.txt、bible/、LOG.md
- 可选产出：output/chNNN_analysis.md（analysis 开关：____）

## 流程（弧内并行）

```
1. 故事弧规划 → bible/arcs.md
2. python scripts/snapshot.py bible/ → bible_snapshot.md
3. 派发子代理 N 个（每 5-10 章一个）
   - 输入：原文 + snapshot + RULES.md
   - 输出：压缩稿 + delta.json
   - 子代理不写 bible
4. 主流程合并 delta → 写入 bible
5. 独立 verifier 子代理验收
6. 弧结束时萃取写作手法 → writing_techniques.md
```

## 分批

- 每弧 50-200 章
- 弧内子批次 30-50 章 → verifier 验收

## Token 软停止

暂停后读 LOG.md → 从下一章续跑。

## 验收标准

- 压缩比 30%-45%（默认 35%，对话格式自然偏短）
- 全部核心+弧级人物出现在 output
- 全部关键钩子有体现
- 无禁用词
- Bible 6 文件齐全
- 独立 verifier 通过

## 参数

- 压缩比：____（默认 35%）
- analysis 开关：____（默认 off）
- 故事弧划分：____
- 黑名单：见 exclude.txt
