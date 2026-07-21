# 子代理调度规范

> 本规范定义小说压缩技能中何时、如何派发子代理（spawn_agent），以及文件冲突的规避策略。

---

## 何时用子代理

| 场景 | 方式 | 原因 |
|------|------|------|
| 弧内章节压缩（>10章） | 并行子代理 | 每 5-10 章一个子代理，独立压缩 |
| Verifier 验收 | 独立子代理 | 只读沙箱，不可修改任何文件 |
| 写作手法萃取（弧结束时） | 独立子代理 | 与本弧续跑和下弧压缩无依赖，可并行 |
| Bible 初始化（前 3 章） | 主流程 | 需建立人物分层基准，上下文敏感 |
| Bible 合并写入 | 主流程（单线程） | 只有主流程能写 bible |
| merge.py 拼接 | 主流程 | 流程全部结束后运行 |

---

## Bible 写入策略（核心）

**子代理绝不直接写 bible 文件。** 原因：5 个子代理同时写 `characters.md`，后写的覆盖先写的，数据丢失。

### Delta 机制

子代理完成压缩后，返回一个 `delta.json`：

```json
{
  "characters": [
    {
      "name": "郭虎禅",
      "level": "弧级(ch007-ch???)",
      "description": "陈氏囚犯，即将移交18号监狱",
      "source": "ch007:L5"
    }
  ],
  "settings": [
    {
      "key": "五大财团",
      "info": "李氏、陈氏、庆氏、神代、鹿岛",
      "source": "ch019"
    }
  ],
  "timeline": [
    {
      "time": "同日晚上",
      "event": "江雪反杀家暴夫",
      "source": "ch018"
    }
  ],
  "hooks": [
    {
      "chapter": "ch020",
      "hook": "母亲来电→庆尘无牵挂",
      "status": "悬而未决"
    }
  ]
}
```

主流程收到所有子代理的 delta 后：
1. 合并所有 `characters`：同名的取层级最高的（核心 > 弧级 > 路人）；不同名的直接追加
2. 合并 `settings`：按 key 去重，保留来源最新的
3. 合并 `timeline`：按时间排序去重
4. 合并 `hooks`：直接追加
5. 写入 bible 四个文件

---

## 弧内并行流程

```
主流程（我）
│
├── 0. 运行 python scripts/snapshot.py bible/ → 生成 bible_snapshot.md
│
├── 1. 派发子代理 × N
│   ├── 子代理A（ch001-010）
│   │     输入: ch001~010原文 + RULES.md全文 + bible_snapshot.md
│   │     输出: ch001~010 10个压缩稿 + delta_A.json
│   │
│   ├── 子代理B（ch011-020）
│   │     输入: ... + RULES.md + snapshot
│   │     输出: ... + delta_B.json
│   │
│   └── 子代理C（ch021-030）
│          ...
│
├── 2. wait_agent 等待全部完成
│
├── 3. 主流程单线程合并
│   │   拆压缩稿 → output/ch001.txt ... ch030.txt
│   │   合并 delta_A + delta_B + delta_C → 去重 → 写入 bible/
│   │   写 LOG.md
│
└── 4. 继续下一批 or 进入下一弧
```

---

## 传参模板

派发子代理时传入以下内容：

```
## 任务
压缩 chapters/ch001.txt ~ ch010.txt（共10章），输出对话格式。

## 压缩规则
[粘贴 RULES.md 全文]

## Bible 快照（当前已知的人物/设定/时间线/钩子）
[粘贴 bible_snapshot.md 全文]

## 原文
[ch001.txt 全文]
---
[ch002.txt 全文]
---
...
[ch010.txt 全文]

## 返回格式
1. 10个压缩稿，每个以 "## chNNN" 开头
2. delta.json 内容：
   - characters: 本章新出现的人物（名字+层级+一句话描述+来源章）
   - settings: 新出现的设定/地点（key+info+来源章）
   - timeline: 新时间线节点
   - hooks: 本章结尾钩子

注意：不要写 bible 文件！不要修改任何已有文件！只返回压缩稿和 delta。
```

---

## bible_snapshot.md 说明

**为什么需要**：子代理并行压缩时，不能读完整 bible（到500章可能几万字），token 爆炸。snapshot 只包含：

- **人物**：名字 + 层级 + 一句话（路人只保留名字）
- **设定**：每个 `##` 标题下压缩到 2-3 句
- **时间线**：完整保留（本来就简练）
- **钩子**：只保留"未揭"状态的行

生成命令：`python scripts/snapshot.py bible/`

---

## 冲突规避规则

| 规则 | 说明 |
|------|------|
| 子代理不写 bible | 返回 delta，主流程合并写入 |
| 子代理不写相同 output 文件 | 各代理范围不重叠（A=001-010, B=011-020） |
| Verifier 只读 | spawn 时明确"只读沙箱，不可修改任何文件" |
| 写作手法萃取在弧结束后 | 独立子代理，与本弧压缩不冲突 |
| merge.py 最后跑 | 所有 output 写完、验证通过后才拼接 |
| 同一个弧内的子代理可并行 | 它们都读同一份 snapshot，互不干扰 |
| 不同弧必须串行 | 弧 B 的 snapshot 依赖弧 A 合并后的 bible |
