# 基于 Codex 目标导向模式的百万字小说压缩改编方法论与实战经验汇总

**日期**：2026-07-17
**执行模式**：完整

---

## 目录

- [引言](#引言)
- [1. 百万字小说的上下文瓶颈与 LLM 压缩可行性](#1-百万字小说的上下文瓶颈与-llm-压缩可行性)
- [2. 分块、剧情圣经与递归摘要](#2-分块剧情圣经与递归摘要)
- [3. Codex 目标导向模式的跨长时运行与 GOAL.md 设计](#3-codex-目标导向模式的跨长时运行与-goalmd-设计)
- [4. 提示词与规则文件：删留标准、禁用清单与压缩比控制](#4-提示词与规则文件删留标准禁用清单与压缩比控制)
- [5. 风险与对冲：摘要泛化失真、静默截断与合规边界](#5-风险与对冲摘要泛化失真静默截断与合规边界)
- [结论](#结论)
- [参考文献](#参考文献)

---

## 引言

百万字长篇小说正成为 AI 改编的新对象，但整本直喂 LLM 在技术上几乎不可行：以 GPT-5.4 标准上下文 272K token 计，仅容约 18–27 万字中文，百万字约等于 150–200 万 token（[OpenAI, Introducing GPT-5.4](https://openai.com/index/introducing-gpt-5-4/)）。即便塞入，长文本「中间迷失」会使核心章节信息召回率跌破闭卷基线（[Lost in the Middle, Liu et al.](https://doi.org/10.1162/TACL_A_00638)）。本报告面向将用 Codex 目标导向模式实操的读者，回答一个核心矛盾：在窗口、记忆与成本三重约束下，如何可靠地把百万字小说压缩为保留主线与独门设定的短篇？

报告由五章构成：第1章判定可行性，第2章搭建「分块—剧情圣经—递归摘要」流水线，第3章用 Codex /goal 与三文件信任架构承载长跑，第4章给出提示词四要素与分层规则文件，第5章收敛于三类风险的对冲。关键预告：①整本直喂不可行，工程化分治成本可控；②/goal 天然适配目标明确、可机械核验的任务，其可靠性来自 GOAL.md+VERIFY.md+LOG.md 外置契约与独立 verifier，而非模型本身（[OpenAI Cookbook: Long-horizon tasks](https://developers.openai.com/cookbook/examples/codex/long_horizon_tasks)）；③压缩是有损的，泛化失真与静默截断技术可控，但自动删除的合规边界须人工签收兜底。

---

## 1. 百万字小说的上下文瓶颈与 LLM 压缩可行性

### 论点
将一部约百万字的长篇小说直接整本丢给大语言模型（LLM）做压缩改编，在技术上不可行；可行的路径是"分块 + 外部记忆 + 递归摘要"的工程化分治流水线。这一结论源于三个硬约束：上下文窗口的 token 上限、长文本中的"中间迷失"（Lost in the Middle）现象，以及由此引发的长篇"失忆"。本章据此给出可行性判定与成本基线，为后续章节的展开奠基。

### 论据
**一、上下文窗口的硬限制：百万字远超单一窗口容量。** 以 Codex 当前主力模型 GPT-5.4 为例，其在 Codex 中的标准上下文窗口为 272K token，仅实验性支持 1M token 窗口（需手动配置，且超出 272K 的部分按 2 倍费率计费）（[Introducing GPT-5.4](https://openai.com/index/introducing-gpt-5-4/)）。Claude 一侧，Sonnet 5 在付费套餐对话中支持 1M token，Opus 4.6–4.8 与 Sonnet 4.6 为 500K，其余模型约 200K（[Claude Help Center](https://support.anthropic.com/en/articles/8606394-how-large-is-claude-pro-s-context-window)）。token 与中文字的换算通常为 1 个汉字 ≈ 1–2 个 token（[CSDN](https://blog.csdn.net/weixin_40806237/article/details/161549659)；[阿里云开发者](https://developer.aliyun.com/article/1736040)）。按 1.5–2 token/字估算，百万字 ≈ 150–200 万 token；即便取乐观的 1 token/字，也是 100 万 token。换言之，即便把最大的 1M 窗口用满，也仅能勉强容纳一部百万字小说"精简版"的文本，而原始全本仍超出窗口——标准 272K 窗口更仅相当于约 18–27 万字的中文容量，与百万字相差 4–5 倍。结论：一次直喂整本在物理上不可能。

**二、中间迷失：长上下文中段召回率断崖式下跌。** 斯坦福与 UC Berkeley 的 Liu 等人在 TACL 发表的实证研究（[Lost in the Middle](https://doi.org/10.1162/TACL_A_00638)；中文解读见 [clvsit](https://clvsit.github.io/%E8%AE%BA%E6%96%87%E9%98%85%E8%AF%BB%EF%BC%9ALost-in-the-Middle-How-Language-Models-Use-Long-Contexts)）显示，相关文档位于上下文开头或结尾时模型准确率最高，置于中段时显著下降。在 20 文档问答任务中，GPT-3.5-Turbo 在答案位于首位的准确率为 75.8%，移到中段（第 10 位）跌至 53.8%，甚至低于"不给任何文档"的闭卷基线 56.1%——即把答案放错位置反而比不给更糟。2025 年 Chroma 在 18 个前沿模型上复现了同一 U 形曲线（[memx](https://memx.app/blog/lost-in-the-middle-long-context-fails)）。RULER 基准进一步指出，宣称支持 128K–1M 上下文的模型，有效利用率在 64K 之后普遍下滑，1M 场景通常只有广告值的 40–60%（[稀土掘金](https://juejin.cn/post/7659715700890992666)）。对"整本直喂"策略的致命性在于：一部百万字小说的主体恰好落在上下文"中段"。

**三、长篇"失忆"：人设崩塌与伏笔失忆。** 即便窗口够大，"有效工作记忆"并未等比增长。社区与行业经验一致认为，AI 处理超长书籍时若缺乏外部记忆，会出现人物性格前后矛盾、设定冲突、伏笔被遗忘等问题（[Novarrium](https://novarrium.com/blog/ai-story-bible-structured-memory)；[Automateed](https://www.automateed.com/how-to-keep-an-ai-generated-book-consistent-reddit)）。这并非个别现象，而是"中间迷失"与窗口退化在叙事一致性上的具体表现：模型读到第 80 万字时，已难以稳健调用第 5 万字处埋下的设定。

**四、可行性判定与成本基准。** 数据显示，分治方案不仅可行且经济。Map-Reduce 摘要将长文切块、逐块独立摘要后再合并，使每块都获得模型的"完整注意力"，从根本上规避中间迷失（[Agentbus](https://agentbus.sh/posts/how-to-summarize-long-documents-with-llms)）。清华等机构提出的 LLM×MapReduce 框架（[PaperCodex](https://www.papercodex.com/llmxmapreduce-generate-coherent-long-form-articles-from-extremely-long-inputs-using-llms-efficiently/)）与 OpenAI 早年的递归任务分解研究均验证了这一路径：OpenAI 的方法"可用于摘要任意长度的书籍，不受所用 transformer 模型上下文长度限制"，先摘要小节、再逐层合并（[OpenAI, 2021](https://openai.com/index/summarizing-books/)）。成本上，Agentbus 的实测显示：5 万 token 文档用 gpt-4o 一次性处理输入约 $0.13，改用 gpt-4o-mini 的 Map-Reduce 总计约 $0.01——便宜约一个数量级，且质量更稳；同一流水线对 4.7 万 token 文档首轮即可压至约 2.8 千 token（约 94% 压缩率）。

### 分析
上述约束共同指向一个工程现实：上下文窗口是"更长的走廊"而非"更大的内存"——窗口变长，中段之门依旧最难打开（[memx](https://memx.app/blog/lost-in-the-middle-long-context-fails)）。因此，"压缩改编百万字小说"不能依赖单次超长上下文，而必须：(1) 将全本切分为可控块；(2) 用"剧情圣经 / 状态文件"作为跨块外部真相源，避免回灌原始章节；(3) 以递归/Map-Reduce 逐层抽取主线。这也正是后续章节展开的前提。

### 小结
百万字 ≈ 150–200 万 token，远超任何单一上下文窗口（即便 GPT-5.4 的 1M 实验窗口也只是"勉强够放精简版"）；长文本"中间迷失"使整本直喂的核心章节召回率跌破闭卷基线（中段约 54% vs 闭卷 56%）；缺乏外部记忆则导致人设崩塌与伏笔失忆。综合判断：整本直喂不可行，必须工程化分治。好在 Map-Reduce 方案已被多源实证可行，且成本可控（gpt-4o-mini 处理 5 万 token 约 $0.01，单文档压缩率 90%+），为后续落地提供可靠基础。

---

## 2. 分块、剧情圣经与递归摘要：LLM 小说压缩的核心流水线

### 论点
把百万字长篇小说压缩成保留主线的短篇，核心不是"一次把全文喂给模型让它写短"，而是搭建一条"分块 → 剧情圣经 → 递归/顺序摘要"的可复用流水线。主流综述指出，当文本超出上下文窗口时，Map-Reduce、Refine 与 Stuff 是三类经典策略，且各自在可预见的环节失效（[How to Summarize a Document...](https://dreaming.press/posts/how-to-summarize-a-document-too-long-for-the-context-window.html)）。对小说而言，这条流水线真正的目标，是在"上下文窗口有限"与"剧情连贯不能丢"两个约束之间找到可工程化的平衡。

### 论据
**分块——按语义单元切，而非固定字数。** 好的分块应满足连贯、尺寸适配、有重叠、落在自然边界四条标准（[Chunking Strategies Explained](https://notes.kodekloud.com/docs/Fundamentals-of-RAG/Document-Processing-and-Chunking/Chunking-Strategies-Explained/page)）。对小说，应以"章节结尾+空行+下一章标题"为天然断点，重点保护"角色首次登场段、伏笔句整段、跨章闪回起止"不被截断，并为每块保留约 1200 token 的重叠区，避免"他推开木门"与"门后是祭坛"被割裂成两个独立事件（[MiniMax M3 实战](https://m.php.cn/faq/2610430.html)）。数据显示，摘要类任务适宜块大小约 1k–4k token，书籍级任务常取 512–1k token 再配合检索（[Chunking Strategies Explained](https://notes.kodekloud.com/docs/Fundamentals-of-RAG/Document-Processing-and-Chunking/Chunking-Strategies-Explained/page)）。

**剧情圣经——把"事实"从"散文"里解耦出来。** 社区共识（r/WritingWithAI）认为，抗漂移的关键是颠倒主从关系：把故事圣经（人物、时间线、伏笔、世界规则）当作"真相源"，散文是输出而非相反；每生成一章后抽取变更（死亡、揭示、关系变化、时间线跳跃）回写圣经，而下一章只喂"大纲+压缩状态"，绝不回喂原始章节（[Keep an AI-Generated Book Consistent: What Reddit Says](https://www.automateed.com/how-to-keep-an-ai-generated-book-consistent-reddit)）。有社区观点认为，朴素方法约在 15–25 章开始漂移，而这一循环可撑过 28 章 / 10 万字不崩（[Automateed](https://www.automateed.com/how-to-keep-an-ai-generated-book-consistent-reddit)）。中文开源剧情引擎（如 Alex）也采用"结构化大纲 + 增量状态"的同类做法（[掘金 – 开源 AI 剧情引擎 Alex](https://juejin.cn/post/7660720162030632986)）。重复回喂原始章节之所以失败，是因为模型会抓住文风韵律却抓不住埋在散文里的事实（[Automateed](https://www.automateed.com/how-to-keep-an-ai-generated-book-consistent-reddit)）。

**递归 / Map-Reduce 摘要——并行快但丢跨块连接。** Map 阶段对各块独立并行摘要再归约；但当块数众多时，reduce 步骤本身可能再次超出上下文窗口，LangChain 因此需"递归折叠"——对摘要再摘要，而每一层折叠都是一次有损压缩（[LangChain – MapReduceDocumentsChain 迁移](https://langchain.cadn.net.cn/python/docs/versions/migrating_chains/map_reduce_chain/index.html)）。更隐蔽的失效是"摘要的摘要会丢失跨块连接"：若第 3 页的伏笔须结合第 40 页的定义才成立，Map-Reduce 从不让二者同框（[How to Summarize...](https://dreaming.press/posts/how-to-summarize-a-document-too-long-for-the-context-window.html)）。因此，当情节连贯、顺序敏感时，应改用顺序 Refine——逐块迭代更新运行中的摘要，以牺牲并行性换取连贯（[dreaming.press](https://dreaming.press/posts/how-to-summarize-a-document-too-long-for-the-context-window.html)）。OpenAI 早年的书籍摘要研究与 LLM×MapReduce 论文也都证明，分块聚合可在不丢主线前提下压缩长文（[OpenAI – Summarizing books](https://openai.com/index/summarizing-books/), [LLM×MapReduce](https://www.papercodex.com/llmxmapreduce-generate-coherent-long-form-articles-from-extremely-long-inputs-using-llms-efficiently/)）。

**增量回写与跨块一致性——纪律比工具更重要。** 开源项目 AINovelLab 的"脱水"流程给出可落地参数：将小说压缩至原长的 30%–50%，长内容按 20K 字符自动分块，并为每块附加"第 n/共 m 段"的位置上下文（[AINovelLab Novel Condensation](https://deepwiki.com/wb-hwang/AINovelLab/3.2-novel-condensation)）。一个真实案例显示，作者用 Claude + Obsidian 把 7.3 万字商业小说压成约 1.5 万字短篇，将 61 章浓缩为 5 部分，并让 AI 自建本地 git 版本库做变更追踪（[Claude 压缩 73k→15k 实战](https://talk.macpowerusers.com/t/using-claude-to-condense-a-73-000-word-business-novel-into-a-15k-novella-in-under-10-hours/44108)）。结构化事实库（如把"眼睛颜色=绿、疤在左前臂"存为不可变身份事实并标注来源句）能让事实被检索、注入与核验，从而防止人设崩塌（[Novarrium – Story Bible](https://novarrium.com/blog/ai-story-bible-structured-memory)）。

### 分析
对"百万字压缩改编"这一具体任务，四点需叠加考量：其一，分块须同时尊重语义边界（不切断剧情）与上下文预算（块大小适配窗口），重叠区是保连贯的廉价安全网。其二，剧情圣经是抗"人设崩塌/静默漂移"的支点——它把"事实"从"散文"中解耦，使下一章即使不读前文也能基于"大纲+状态"生成而不矛盾。其三，因为压缩是顺序敏感、叙事性的，纯并行 Map-Reduce 会丢失跨章情节连接，应改用顺序 Refine 或以"故事圣经状态"为共享上下文的生成式压缩；但 Refine 串行慢且早期错误会向后传播，故实践中常以"逐章回写的状态摘要"替代原始全文来充当那根共享线。其四，社区反复强调：回写纪律比工具选择更重要——跳过后章节更新的那一天，方法就会失效（[Automateed](https://www.automateed.com/how-to-keep-an-ai-generated-book-consistent-reddit)）。

### 小结
LLM 小说压缩的核心流水线可归纳为三件套：① 分块——以语义单元为断点、带重叠、尺寸适配窗口；② 剧情圣经——结构化"真相源"+ 每章增量回写；③ 递归/顺序摘要——是否顺序敏感决定选 Map-Reduce（快、丢连接）还是 Refine（连贯、慢）。落到 Codex 目标导向模式，GOAL.md 可定义为"逐章压缩 → 每章抽取事实 delta 回写圣经 → 下一章只喂大纲+压缩状态"，并以压缩比（如原长 30%–50%）作为验收闸门（[AINovelLab](https://deepwiki.com/wb-hwang/AINovelLab/3.2-novel-condensation)）。

---

## 3. Codex 目标导向模式的跨长时运行与 GOAL.md 设计

### 论点
Codex 的 `/goal` 目标导向模式，把"一次对话"升级为"一个可持续数十小时、自我驱动的自主执行体"。其可靠性的关键并不在于模型变得多聪明，而在于把目标、验收与审计外置成可检查的文件。对于"百万字小说压缩改编"这类目标明确、可机械核验（压缩比、保留章节数、剧情圣经一致性）的工程任务，`/goal` 是天然的承载形态——前提是写好 `GOAL.md`，并用三文件信任架构对冲"规格漂移、静默质量退化、验证作秀"三类失败模式。

### 论据
**一、`/goal` 机制与跨长时运行证据。** Codex 设定目标后进入"规划→行动→验证→复盘"的续作循环（continuation loop），每轮结束后自查是否满足可验证的终止条件，未达成则继续，无法推进则停止上报（[Codex Goal 模式使用指南](https://m.jinse.com.cn/blockchain/3734032.html)）。OpenAI 的官方压力测试显示，GPT-5.3-Codex 以 "Extra High" 推理连跑约 25 小时、消耗约 13M token、生成约 3 万行代码，核心转变是"time horizon（时间跨度）"而非一次性智能（[OpenAI Cookbook – Run long horizon tasks with Codex](https://developers.openai.com/cookbook/examples/codex/long_horizon_tasks)）。同一指南称已有用户让 Codex 为同一目标连续工作超过 120 小时（[Codex Goal 模式使用指南](https://m.jinse.com.cn/blockchain/3734032.html)）；社区实测中，xiaoming.io 一次运行持续 13 小时后因 token 窗口额度耗尽才停止（[xiaoming.io – Codex Goal 模式连续跑 13 小时](http://www.xiaoming.io/codex-goal-mode)）。从更宏观的基准看，METR 的长时域（time-horizon）数据显示，前沿模型可自主完成的任务时长大约每 7 个月翻一倍，50% 可靠性下的任务时长在 2025 年已达数小时级（[METR – Task-Completion Time Horizons](https://metr.org/time-horizons)）。

**二、GOAL.md 的设计要点。** 最关键的一条设计原则是：把"完成标准"写成可运行命令，而不是主观判断。有分析指出，"让代码更优雅"不可验证，而 "`npm run test:auth && npm run lint`" 则不是（[The /goal Command and the Verification Problem](https://codex.danielvaughan.com/2026/07/06/codex-cli-goal-mode-long-running-autonomous-agents-verification-trust-architecture)）。xiaoming.io 的实战结构建议 `GOAL.md` 包含八项：①目标；②状态记录与断点恢复（进度存入 `GOAL_STATUS.md`，重启先读状态）；③流程；④范围（仅改 Workspace 内文件）；⑤限制（不要做什么）；⑥验收标准；⑦异常处理（阻塞即停，需人工则记录后继续）；⑧Token 预算（如最多 100M token 即停）（[xiaoming.io](http://www.xiaoming.io/codex-goal-mode)）。在此之上，社区形成了三文件信任架构：`GOAL.md` 定义"完成"→`VERIFY.md` 把每条需求映射到真实检查命令（如 `npm run test:auth` 期望退出码 0）→`PROGRESS.md`（亦称 `LOG.md`）记录"做了什么、证据是什么"的执行日志，三者串联成可追溯链（[The /goal Command...](https://codex.danielvaughan.com/2026/07/06/codex-cli-goal-mode-long-running-autonomous-agents-verification-trust-architecture) [Nathan Onn – Three Files That Made Codex /goal Reliable](https://www.nathanonn.com/codex-goal-command-three-files)）。有观点认为，比起手写 goal 提示词，不如用另一个 AI 做"元提示（meta-prompt）"，把含糊目标盘问成可验证契约——因为人会低估自主体在不被监督时需要知道多少信息（[Aditya Bawankule – Codex /goal Meta Prompting Guide](https://adityabawankule.io/blog/codex-goal-meta-prompting)）。

**三、踩坑与规避。** 文献归纳出三种主导性失败模式：①规格漂移（specification drift）——欠定义的目标被逐轮"看似合理但偏离意图"地解释；②静默质量退化（silent quality degradation）——测试通过却引入技术债、不必要的抽象或与既有代码库不一致的架构；③验证作秀（verification theatre）——自己写测试证明自己正确，却绕开人类会查的边缘情况（[The /goal Command...](https://codex.danielvaughan.com/2026/07/06/codex-cli-goal-mode-long-running-autonomous-agents-verification-trust-architecture)）。数据显示，一次 12 小时的 Pro 任务可消耗周额度 70% 以上，因此必须设置 rollout token budget 实现"预算耗尽即软停止（暂停而非终止）"（[The /goal Command...](https://codex.danielvaughan.com/2026/07/06/codex-cli-goal-mode-long-running-autonomous-agents-verification-trust-architecture)）。规避手段有二：一是部署独立 verifier 子 Agent（只读沙箱、高推理强度），确保"出题人不能给自己阅卷"；二是把大任务拆成 2–4 小时的小 goal 分批执行，而非一个 goal 跑 18 小时（[The /goal Command...](https://codex.danielvaughan.com/2026/07/06/codex-cli-goal-mode-long-running-autonomous-agents-verification-trust-architecture) [toolin.ai – Codex /goal 自主任务调度完全指南](https://toolin.ai/blog/codex-goal-autonomous-task-scheduling)）。有观点进一步提醒，`/goal` 更适合"边界清晰、可机械核验"的任务，对需要主观审美判断或尚未定稿的架构决策表现不佳（[The /goal Command...](https://codex.danielvaughan.com/2026/07/06/codex-cli-goal-mode-long-running-autonomous-agents-verification-trust-architecture)）。

### 分析
把"小说压缩改编"映射为 Codex 的 goal，本质上是把第 1、2 章的流水线改写成一份可执行的工程契约：GOAL.md（目标）将"百万字→X 万字短篇、删除垃圾/恶心章节、保留主线"具象为可数指标——压缩到 N 万字、保留主线 M 条、删除章节清单符合既定标准；范围限定只读写 `novel/` 与 `bible/` 目录；验收写成交互命令（如脚本比对"摘要角色/地点集合"与"圣经条目"的差异）；异常写明"某章无法摘要则停止上报"；Token 预算设软停止阈值。闭环映射"逐章压缩→回写圣经→验收闸门"：每一章即一轮 plan（读章+读圣经）→act（摘要/删改并回写圣经）→verify（对照 `VERIFY.md` 跑 diff 与一致性检查）→复盘（写 `PROGRESS.md`）。把"验收闸门"落成可运行脚本，是让 Codex 不靠"我觉得到位了"而是靠"命令退出码 0"来判定章级完成。主观判断的留白：哪些章节算"垃圾/恶心"含审美判断，难以完全量化。有观点认为应采用"可机械核验的代理指标 + 人类最终签收"的混合模式，而非追求全自动——即在 GOAL.md 中保留一道人工签收节点，与 `/goal` "完成时即停"的自主哲学形成必要对冲（[xiaoming.io](http://www.xiaoming.io/codex-goal-mode) [The /goal Command...](https://codex.danielvaughan.com/2026/07/06/codex-cli-goal-mode-long-running-autonomous-agents-verification-trust-architecture)）。

### 小结
`/goal` 把长任务从"反复点继续"变成"下一条命令"，但其可靠性来自外置的目标与审计文件，而非模型本身。`GOAL.md` + `VERIFY.md` + `PROGRESS`/`LOG.md` 三件套，配合独立 verifier 与 token 预算，是把"百万字压缩"这类目标明确、可核验任务交给 Codex 长跑的工程底座；而对主观删留判断，应保留人工签收节点，避免验证作秀与规格漂移在长弧中悄悄累积。

---

## 4. 提示词与规则文件：删留标准、禁用清单与压缩比控制

### 论点
把百万字小说压缩成短篇，关键不在"让 AI 少写"，而在用一套可执行、可审计的提示词与规则文件，把四件事讲清：删什么、留什么、写成什么样、怎么算完。这样 Codex 才能在目标导向模式下跨长时执行而不跑偏。

### 论据
**一、提示词"四要素"：把压缩任务变成可校验的契约。**
**删什么。** 最核心的判定来自实操经验：有经验认为，一章删掉后对后续剧情几乎无影响，大概率就是"水章"，可整章剔除；冗余的环境渲染、次要支线、以及 AI 自身生成的套话也应删去。传统的缩写教学也强调"留主删次"，删掉次要情节与非关键细节、景物和外貌描写，只留主干（[忠于原文，精于原文——缩写小说的技巧](https://jiaoan1.7139.com/1417/23/251169.html)）。
**留什么。** 改编实践普遍要求锁定"主线 throughline、主角、关键钩子"三件套：ScreenWeaver 的 15 节拍表法要求明确"谁是电影主角、主线是什么"，并建议做一轮"特异性校验"——每个节拍至少要有一处只属于本书的细节、意象或名场面（[AI for Adaptation: 400-Page Novel → 15-Point Beat Sheet](https://screenweaver.ai/blog/ai-adaptation-400-page-novel-15-point-beat-sheet)）；短剧改编指南则要求把原小说的经典台词、名场面在指令中显式标注"必须保留"（[AI赋能内容创作：小说改编短剧全流程实操指南](https://2048ai.net/6996547654b52172bc5c670c.html)）。
**写成什么样（去 AI 味）。** 可落地的禁用清单已被多位作者汇总：禁用排比、对仗、递进式套话，禁用"突然/仿佛/骤然/与此同时/毋庸置疑"等高频模板词，禁止鸡汤式升华与过度顺滑的完美逻辑（[全套洗 AI 痕迹指令](https://www.toutiao.com/article/7654070264153768448/)）；通用禁词表还覆盖"综上所述/由此可见/值得一提的是"等连接词，以及"赋能/闭环/抓手"等黑话（[4 个零门槛技巧，彻底消除 AI 写作的人机味](https://www.toutiao.com/article/7647754572265472550/)）。参考坐标可以写得极简：文字冷静、信息密度高、短句为主、长句不超过 20 字（[AI 写小说万能公式，框架 Prompt 直接套用](https://www.toutiao.com/article/7625143840706298408/)）。
**怎么算完。** 用可量化指标收口：目标压缩比达成（见下）、关键钩子与独门设定无遗漏、且不新增剧情、不篡改人设。

**二、保留独门设定：把"专有名词 / 意象 / 口头禅"写进规则文件。** 压缩最容易丢的是作者独门的东西。有经验认为，专有名词、关键意象、人物口头禅必须进"真相源"（story bible / rules md）——Automateed 归纳的 Reddit 共识把故事圣经视为唯一真理，当正文与圣经冲突时以圣经为准，章节须据此重新生成（[Keep an AI-Generated Book Consistent: What Reddit Says](https://www.automateed.com/how-to-keep-an-ai-generated-book-consistent-reddit)）。工程化方案如 Alex 剧情引擎，用 YAML 配置覆写下挂 20+ 提示接点，并设"陈词滥调扫描"做规则+语义双重检测，从源头拦住套路表达（[我做了个开源 AI 剧情引擎](https://juejin.cn/post/7660720162030632986)）。

**三、压缩比与钩子：用区间而非绝对值控场。** 数据显示，开源项目 AINovelLab 的压缩提示词直接把目标写死为原文的 30%–50%，并要求"保留所有重要情节、对话和描写，不要遗漏关键情节和人物"（[Novel Condensation | AINovelLab](https://deepwiki.com/wb-hwang/AINovelLab/3.2-novel-condensation)）。这与逐段精修的实操经验一致：可要求"总字数压缩到原来的 60%"或"减少约 30%"等比例表达，比"精简一点"更可控（[简化段落的 ai 提示词怎么写](https://www.chooseai.net/news/1030)）。钩子方面，短剧改编要求"每 30 秒有小冲突、每集有大钩子"，改编指令须显式保留结尾钩子（[小说改编短剧全流程实操指南](https://2048ai.net/6996547654b52172bc5c670c.html)）。

**四、规则文件如何组织：交给 Codex 在本章落地。** 长提示词会引致截断与漂移。有测试显示，800 字原始 prompt 平均截断率达 38%，表现为人设重置与伏笔断裂；将设定符号化、改走"system 固化基础规则 + 章节级沙盒"的分层注入，可把截断率降到 0%（[DeepSeek 写小说时提示词过长导致截断](https://ask.csdn.net/questions/9309972)）。因此规则文件不宜塞进单条超长提示词，而应拆成 SKILL.md（基础规则、禁用词表、压缩比）与按章/按角色拆分的 md（剧情圣经、独门设定、当前章变量），由 Codex 在目标导向模式里按需读取——这部分的具体目录结构与 GOAL.md 承接交由第 3 章落地。

### 小结
把压缩交给 AI，本质是写一份"四要素契约"：删水章与套话、留主线与独门设定、文字冷静高密、以 30%–50% 压缩比且钩子无遗漏为完成标准；并用分层规则文件替代超长提示词，把真相源与禁用清单固化下来，让 Codex 可跨长时、可审计地执行。

---

## 5. 风险与对冲：摘要泛化失真、静默截断与合规边界

### 论点
用 AI（尤其是 Codex 目标导向模式）把约百万字小说压缩为保留主线的短篇，本质是一条"有损压缩 + 自动化决策"流水线。数据显示，它在三处最易系统性失真与失控：生成式摘要的泛化失真、输出上限引发的静默截断，以及自动删除"垃圾/恶心章节"所触及的合规边界——后者公开讨论最少却风险最高。本章认为，压缩改编能否可信落地，取决于是否建立"原文对照 + 关键事实清单 + 人工裁决 + 独立 verifier"的闭环对冲（呼应第 3 章 GOAL.md 设计）。

### 论据
**一、摘要泛化失真是生成式压缩的固有偏差。** 有研究指出，生成式（abstractive）摘要重写措辞、合成新句，在提升可读性的同时把"幻觉"一并带入——模型可能平滑掉关键数字或凭空加入原文没有的细节（[Text Summarization with LLMs](https://explainllm.ru/en/applications/summarization)）。2025 年发表于 Royal Society Open Science 的研究最具警示性：Peters 与 Chin-Yee（2025）比对 10 个主流 LLM 的 4,900 条摘要与原文，发现 DeepSeek、ChatGPT-4o、LLaMA 3.3 70B 在 26%–73% 案例中过度概括（省略限定结论的细节、得出更宽论断）；较新模型反而更差，且模型摘要产生宽泛概括的概率约为人类 5 倍（比值比 4.85）（[Generalization bias in LLM summarization](https://pmc.ncbi.nlm.nih.gov/articles/PMC12042776/)）。对小说而言这尤其致命。MemX（2026）归纳 AI 摘要最常遗漏的八类信息：数字与单位、告诫语/模糊限制词、否定词、少数派异议、不确定性与局限、归因、日期与条件、边缘案例；并直言"丢掉告诫语的摘要比丢掉一段更危险"，因为缺失的限定词不可见却会翻转语义（[What AI Summaries Leave Out](https://memx.app/blog/what-ai-summaries-leave-out)）。

**二、抽取式更稳，但压缩比受限。** 数据显示，抽取式（extractive）摘要直接复制原文句子、输出是源的子集，事实错误结构上几乎不可能，幻觉率接近零；生成式幻觉率依任务在 0.7%–14% 之间（[Extract and Summarise With AI](https://www.promptquorum.com/prompt-engineering/extract-and-summarise?lang=en)）；另有基准显示 Vectara 忠实度评测中摘要幻觉达 3%–27%，重大错误在多达 50% 案例出现（[Advanced Document Summarizer or Liability?](https://textwall.ai/advanced-document-summarizer)）。故"能否承受事实错误"应作删留分流开关：关键情节与设定用抽取式保底，过渡铺陈才交生成式重写。

**三、静默截断——作者看不见的内容丢失。** dev.to 的一线实测记录了一个 30 章、114,000 词 AI 长篇小说：约第 12 章起，要求 5,000 词/章频繁回落到 1,400 词，对话被压成"他们详细讨论了局势"之类的总结句，且无任何报错（[Why ChatGPT Keeps Cutting Off Your Writing](https://dev.to/totalvaluegroup/why-chatgpt-keeps-cutting-off-your-writing-the-hidden-ai-system-called-truncation-and-how-we-2f1n)）。根因是输出 token 上限：早期 GPT-4o 仅约 4,096 token（现版本更高，如 16,384 token），GPT-5 才达 128,000，Claude Opus 4.6 为 64,000、Gemini 2.5 Pro（API）65,536；一旦请求超出天花板即自动截断，而 Web 界面会隐藏 `finish_reason:"length"` 这类元数据，作者无从察觉（[同上](https://dev.to/totalvaluegroup/why-chatgpt-keeps-cutting-off-your-writing-the-hidden-ai-system-called-truncation-and-how-we-2f1n)）。小说递归摘要的每一层 reduce 都可能触发截断并被忽略。

**四、极致压缩稀释因果链与限定条件。** 即便无截断与幻觉，极致压缩本身也稀释因果。递归摘要（map-reduce）跨块合并会损失部分"跨块细微差别"，应在章节/段落自然边界切分而非句中切断（[Text Summarization with LLMs](https://explainllm.ru/en/applications/summarization)）。Royal Society 研究同样表明，省略限制条件会让摘要得出比原文更广的概括（[Generalization bias in LLM summarization](https://pmc.ncbi.nlm.nih.gov/articles/PMC12042776/)）。小说中"因 A 故 B"的条件链、人物动机的限定前提，正是被平均化优先牺牲的对象；一旦断裂，保留的"主线"会与原文产生隐性矛盾。

**五、自动删除敏感/恶心章节的伦理与合规边界。** 用户要求"删去垃圾/恶心章节"，把压缩变成一个内容审核（content moderation）动作。该议题在小说压缩场景公开讨论极少，但有研究指出普适原则：绝大多数内容审核决策现已由机器而非人类做出，自动化会放大训练数据与系统设计的偏见，故须在设计之初嵌入表达自由与人权考量，并让用户"有权知道内容为何被删、是人工还是自动决策"（[Content Moderation in a New Era for AI and Automation](https://www.oversightboard.com/news/content-moderation-in-a-new-era-for-ai-and-automation/)）。业界共识把 AI 定位为"分诊引擎"而非决策者，人类审阅微妙个案，human-in-the-loop（HITL）为黄金标准，且 DSA 与《欧盟 AI 法案》已对透明度与风险管理提出更高要求（[AI in Content Moderation](https://www.concentrix.com/insights/blog/ai-in-content-moderation-striking-the-right-balance-in-trust-and-safety-operations/)）；工程实践亦明确"AI 作第一层过滤、人类审阅更微妙案例"（[Types of AI Content Moderation](https://www.techtarget.com/searchcontentmanagement/tip/Types-of-AI-content-moderation-and-how-they-work)）。结论：删除判定不能由 Codex 自动签收，必须经过人工裁决并留下可审计记录。

### 分析
小说不是科研摘要，其"事实"是情节与人物关系的因果网。生成式改写一句对白可能翻转角色动机；静默截断砍掉一节可能让后文伏笔落空；自动删除若缺人工签收，既可能误删关键铺垫，也可能在合规上给作者造成不可见责任。三处风险叠加，使"压缩比"成为需要被控制的变量，而非越高越好。

### 对冲手段（呼应第 3 章）
1. **原文对照**：被压缩块保留源文本锚点，摘要段落可回溯原文，杜绝凭空改写（[What AI Summaries Leave Out](https://memx.app/blog/what-ai-summaries-leave-out)）。
2. **关键事实清单**：在 GOAL.md / 规则文件维护"不可丢失"的事实单元（人物、设定、因果前提），作为 verifier 的校验基准。
3. **人工裁决环节**：删除敏感/恶心章节一律升级人工签收，记录理由与原文定位，满足可审计与申诉（[AI in Content Moderation](https://www.concentrix.com/insights/blog/ai-in-content-moderation-striking-the-right-balance-in-trust-and-safety-operations/)）。
4. **独立 verifier**：验证代理与生成代理分离，输出拆为不可再分的事实单元、要求至少双源交叉验证，无法验证者明确标注转人工（[OpenClaw 自验证体系](https://bbs.huaweicloud.com/blogs/477073)）——与第 3 章 GOAL.md 的 verifier 闭环同构。研究显示 HITL 能补足 LLM-as-judge 的盲区（冗长偏好、漏判事实错误）（[Human-in-the-loop evals](https://www.braintrust.dev/articles/human-in-the-loop-evals-for-llm-apps)）。

### 小结
百万字小说压缩的可信度，不取决于单次摘要多漂亮，而取决于是否把"失真、截断、越界"三道风险都用机制兜住。摘要泛化失真与静默截断技术可控（抽取式保底、输出字数自检、自然边界切分）；而自动删除的合规边界必须由人工签收兜底——这是公开讨论最少、却最不能省略的一环。将原文对照、关键事实清单、人工裁决与独立 verifier 写入 GOAL.md 与规则文件，压缩改编才算从"能跑"走向"可用"。

---

## 结论

回到开篇的核心矛盾：百万字小说能否用 AI 可靠压缩改编？本报告给出的答案是——可以，但必须把它当作一项「工程」而非「一次对话」。上下文窗口只是更长的走廊而非更大的内存，整本直喂因中间迷失与长篇失忆而必然失败；可行路径是「分块+剧情圣经+递归摘要」的分治流水线，已被 OpenAI 书籍摘要与清华 LLM×MapReduce 实证可行（[OpenAI, 2021](https://openai.com/index/summarizing-books/)）。

综合五章，提炼四条关键发现：（1）可行性根因在分治：语义单元断点分块+重叠区+结构化真相源（剧情圣经）是抗漂移支点，回写纪律比工具选择更重要（[Novarrium](https://novarrium.com/blog/ai-story-bible-structured-memory)）。（2）Codex /goal 是天然承载形态：可靠性来自 GOAL.md+VERIFY.md+LOG.md 三文件信任架构与独立 verifier，而非模型本身；大任务须拆成 2–4 小时小 goal 并设 token 软停止（[Vaughan](https://codex.danielvaughan.com/2026/07/06/codex-cli-goal-mode-long-running-autonomous-agents-verification-trust-architecture)）。（3）提示词是契约：把「删什么/留什么/写成什么样/怎么算完」四要素写清，以 30%–50% 压缩比且钩子无遗漏为验收闸门，用分层规则文件替代超长提示词（[AINovelLab](https://deepwiki.com/wb-hwang/AINovelLab/3.2-novel-condensation)）。（4）风险必须兜底：生成式摘要过度概括在 26%–73% 案例中发生（[Royal Society / Peters & Chin-Yee, 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12042776/)），静默截断与自动删除合规边界更需原文对照、关键事实清单、人工裁决与独立 verifier 闭环。

未来方向有二：一是把主观删留判断固化为「可机械核验代理指标+人工最终签收」混合模式，写入 GOAL.md 保留签收节点；二是建立跨章事实单元 diff 的自动 verifier，降低人工审计成本。底线是：压缩比不是越高越好，守住失真、截断、越界三道风险，才算从「能跑」到「可用」。

---

## 参考文献

- Agentbus. (2024). How to summarize long documents with LLMs. Agentbus. [链接](https://agentbus.sh/posts/how-to-summarize-long-documents-with-llms)
- AINovelLab. (2025). Novel Condensation (Chapter 3.2). DeepWiki. [链接](https://deepwiki.com/wb-hwang/AINovelLab/3.2-novel-condensation)
- Anthropic. (2025). How large is Claude Pro's context window? Anthropic Help Center. [链接](https://support.anthropic.com/en/articles/8606394-how-large-is-claude-pro-s-context-window)
- Automateed. (2024). How to keep an AI-generated book consistent. Automateed. [链接](https://www.automateed.com/how-to-keep-an-ai-generated-book-consistent-reddit)
- Bawankule, A. (2025). Codex goal meta-prompting. [链接](https://adityabawankule.io/blog/codex-goal-meta-prompting)
- Braintrust. (2024). Human-in-the-loop evals for LLM apps. [链接](https://www.braintrust.dev/articles/human-in-the-loop-evals-for-llm-apps)
- ChooseAI. (2025). 逐段精修压缩比控制. ChooseAI. [链接](https://www.chooseai.net/news/1030)
- Chroma (MemX). (2025). Lost in the middle: Long context fails (18-model replication). MemX. [链接](https://memx.app/blog/lost-in-the-middle-long-context-fails)
- CLVSIT. (2024). 论文阅读：Lost in the Middle. [链接](https://clvsit.github.io/%E8%AE%BA%E6%96%87%E9%98%85%E8%AF%BB%EF%BC%9ALost-in-the-Middle-How-Language-Models-Use-Long-Contexts)
- Concentrix. (2025). AI in content moderation: Striking the right balance in trust and safety operations. [链接](https://www.concentrix.com/insights/blog/ai-in-content-moderation-striking-the-right-balance-in-trust-and-safety-operations/)
- CSDN. (2025). Token 与中文换算. CSDN. [链接](https://blog.csdn.net/weixin_40806237/article/details/161549659)
- CSDN 问答. (2025). 长提示词截断问答. CSDN. [链接](https://ask.csdn.net/questions/9309972)
- Dev.to (totalvaluegroup). (2024). Why ChatGPT keeps cutting off your writing: The hidden AI system called truncation. [链接](https://dev.to/totalvaluegroup/why-chatgpt-keeps-cutting-off-your-writing-the-hidden-ai-system-called-truncation-and-how-we-2f1n)
- Dreaming.press. (2024). How to summarize a document too long for the context window (Map-Reduce vs Refine). [链接](https://dreaming.press/posts/how-to-summarize-a-document-too-long-for-the-context-window.html)
- ExplainLLM. (2024). Summarization applications. [链接](https://explainllm.ru/en/applications/summarization)
- KodeCloud. (2024). Chunking strategies explained. KodeCloud Notes. [链接](https://notes.kodekloud.com/docs/Fundamentals-of-RAG/Document-Processing-and-Chunking/Chunking-Strategies-Explained/page)
- LangChain. (2024). Map-Reduce chain. LangChain Docs. [链接](https://langchain.cadn.net.cn/python/docs/versions/migrating_chains/map_reduce_chain/index.html)
- Liu, N. F., et al. (2024). Lost in the Middle: How language models use long contexts. Transactions of the ACL. [链接](https://doi.org/10.1162/TACL_A_00638)
- METR. (2025). Time-horizons benchmark. [链接](https://metr.org/time-horizons)
- MemX. (2025). What AI summaries leave out. [链接](https://memx.app/blog/what-ai-summaries-leave-out)
- Nathan Onn. (2025). Codex goal command: Three files. [链接](https://www.nathanonn.com/codex-goal-command-three-files)
- Novarrium. (2024). AI story bible: Structured memory. [链接](https://novarrium.com/blog/ai-story-bible-structured-memory)
- OpenAI. (2021). Summarizing books. [链接](https://openai.com/index/summarizing-books/)
- OpenAI. (2025a). Introducing GPT-5.4. [链接](https://openai.com/index/introducing-gpt-5-4/)
- OpenAI. (2025b). Long-horizon tasks with Codex (Cookbook). [链接](https://developers.openai.com/cookbook/examples/codex/long_horizon_tasks)
- OpenClaw (华为云). (2025). 独立 verifier 设计实践. 华为云论坛. [链接](https://bbs.huaweicloud.com/blogs/477073)
- Oversight Board. (2025). Content moderation in a new era for AI and automation. [链接](https://www.oversightboard.com/news/content-moderation-in-a-new-era-for-ai-and-automation/)
- PaperCodex. (2024). LLM×MapReduce: Generate coherent long-form articles from extremely long inputs. [链接](https://www.papercodex.com/llmxmapreduce-generate-coherent-long-form-articles-from-extremely-long-inputs-using-llms-efficiently/)
- Peters, H., & Chin-Yee, B. (2025). Overgeneralization in LLM-generated medical summaries. Royal Society Open Science. [链接](https://pmc.ncbi.nlm.nih.gov/articles/PMC12042776/)
- PromptQuorum. (2024). Extract and summarise: Prompt engineering. [链接](https://www.promptquorum.com/prompt-engineering/extract-and-summarise?lang=en)
- ScreenWeaver. (2025). AI adaptation of a 400-page novel: 15-point beat sheet. [链接](https://screenweaver.ai/blog/ai-adaptation-400-page-novel-15-point-beat-sheet)
- TechTarget. (2024). Types of AI content moderation and how they work. [链接](https://www.techtarget.com/searchcontentmanagement/tip/Types-of-AI-content-moderation-and-how-they-work)
- TextWall. (2024). Advanced document summarizer (Vectara hallucination benchmark). [链接](https://textwall.ai/advanced-document-summarizer)
- Toolin.ai. (2025). Codex goal autonomous task scheduling. [链接](https://toolin.ai/blog/codex-goal-autonomous-task-scheduling)
- Vaughan, D. (2026). Codex CLI goal mode: Long-running autonomous agents & verification trust architecture. [链接](https://codex.danielvaughan.com/2026/07/06/codex-cli-goal-mode-long-running-autonomous-agents-verification-trust-architecture)
- xiaoming.io. (2025). Codex goal mode 实战. [链接](http://www.xiaoming.io/codex-goal-mode)
- 7139 教案. (n.d.). 缩写教案（留主删次）. [链接](https://jiaoan1.7139.com/1417/23/251169.html)
- 2048AI. (2025). 短剧改编指南：经典台词与名场面保留. [链接](https://2048ai.net/6996547654b52172bc5c670c.html)
- 今日头条. (2025a). 洗 AI 痕迹指南. [链接](https://www.toutiao.com/article/7654070264153768448/)
- 今日头条. (2025b). 消除人机味：通用禁词表. [链接](https://www.toutiao.com/article/7647754572265472550/)
- 今日头条. (2025c). AI 写小说公式. [链接](https://www.toutiao.com/article/7625143840706298408/)
- 阿里云. (2024). 大模型 token 计算与中文换算. 阿里云开发者社区. [链接](https://developer.aliyun.com/article/1736040)
- 掘金 Alex. (2025). 中文开源剧情引擎 Alex：YAML 覆写与陈词滥调扫描. 稀土掘金. [链接](https://juejin.cn/post/7660720162030632986)
- 稀土掘金. (2025). RULER 长上下文基准评测. 稀土掘金. [链接](https://juejin.cn/post/7659715700890992666)
- 金色财经. (2025). Codex Goal 指南. [链接](https://m.jinse.com.cn/blockchain/3734032.html)
- PHP 中文网. (2025). MiniMax M3 实战：分块与重叠. [链接](https://m.php.cn/faq/2610430.html)

---

## 待完善事项

> 本节为报告透明度与勘误说明（按深度研究流程标准结构保留）。所列条目均已在成稿中处理完毕或已加注提示，**并非未交付的研究内容**；本报告 Phase 1–5 全流程已完结。请读者在重要场景下对下列标注处二次核验。

- 第 2、4 章原稿末尾存在"附：本章引用含…"面向审稿人的说明性备注段落，已在成稿中删除。
- 各章标题层级已统一为章 `##`、小节 `###`（含将原稿中以"一、二、三"序号呈现的分论点统一规范）。
- 术语统一：正文与小结中 `PROGRESS.md` 即 `LOG.md` 的别名，全文以 GOAL.md / VERIFY.md / LOG.md 三文件表述。
- 第 5 章 GPT-4o 输出上限：原稿写"约 4,096 token"，已据审稿意见加注——此为早期 GPT-4o 快照数值，现版本更高（如 16,384 token），论点（长文触发静默截断）仍成立；其余模型输出上限（GPT-5 128K、Claude Opus 4.6 64K、Gemini 2.5 Pro 65,536）引自 dev.to 实测，建议重要场景二次核验。
- 第 4 章"800 字 prompt 截断率 38%→0%"出自 CSDN 问答社区单帖非严谨测试，结论可作为经验参考，但勿作普适断言。

---

> 本报告由 AI 深度研究团队生成，重要决策请经专业人员核验。所有引用来源请用户在重要场景下二次核验时效性与真实性。
