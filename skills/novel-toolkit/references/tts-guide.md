# TTS 有声小说生成指南

将压缩稿（`output/chNNN.txt`）+ 人物档案（`bible/characters.md`）合成为有声小说。后端使用 VoxCPM2 API。

---

## 两种姿势

| 方式 | 工具 | 适用场景 |
|------|------|----------|
| **无 UI（推荐）** | `novel_tts.py` 两步走 | 日常使用，快，不用浏览器 |
| **有 UI（精调）** | `voice_tuner.py` + `novel_tts.py` | 对音色要求极高，想逐个角色试听调整 |

---

## 方式一：无 UI（推荐，全自动）

不用打开浏览器，全程命令行：

```
bible/characters.md          ← 人物档案（年龄、性格、身份）
       │
       ▼  [AI 读取人物档案 + 推理生成]
bible/voices_script.txt      ← AI 生成的音色脚本
       │
       ▼  [python novel_tts.py Step 1]
tts_output/auto_refs/        ← 每个角色的基线音色 (wav)
       │
       ▼  [python novel_tts.py Step 2]
tts_output/<chapter>/output.mp3   ← 最终章节播客
```

### Step 0：AI 生成音色脚本

详见 [voices-script-guide.md](voices-script-guide.md)。

### Step 1：生成角色基线音色

```bash
python scripts/novel_tts.py "bible/voices_script.txt" \
  --target "examples/<小说名>" \
  --url <VoxCPM2_URL>
```

输出到 `{target}/tts_output/auto_refs/`，文件名格式为 `{角色名}_ref.wav`。

**修改 voices_script.txt 后重新生成基线（跳过已有参考）：**

```bash
python scripts/novel_tts.py "bible/voices_script.txt" \
  --target "examples/<小说名>" \
  --url <VoxCPM2_URL> \
  -f
```

### Step 2：生成章节对话音频

```bash
python scripts/novel_tts.py "output/ch001.txt" \
  --target "examples/<小说名>" \
  --url <VoxCPM2_URL>
```

脚本自动从 `{target}/tts_output/auto_refs/` 按角色名前缀匹配参考音频（`庆尘` 匹配 `庆尘_ref.wav`），无需手动映射。

合并输出为 `{target}/tts_output/ch001/output.mp3`。

---

## 方式二：有 UI（手动精调）

适合对音色有极致要求的场景：

```
bible/characters.md
       │
       ▼  [AI 生成]
bible/voices_script.txt
       │
       ▼  [voice_tuner.py — 浏览器 UI]
tts_output/auto_refs/
       │
       ▼  [novel_tts.py]
tts_output/<chapter>/output.mp3
```

### Step 1：浏览器 UI 调音色

```bash
python scripts/voice_tuner.py --target "examples/<小说名>" --url <VoxCPM2_URL>
```

自动打开浏览器。页面展示所有角色卡片，可播放已有音频、编辑音色描述、点击 Regenerate 重新生成。满意后点击 Done 关闭服务。

### Step 2：同方式一的 Step 2

基线音色生成后，后续步骤完全一样。

---

## novel_tts.py 参数

```
python scripts/novel_tts.py <script.txt> \
  --target <项目根目录>      # 自动发现 auto_refs/，输出到 tts_output/
  --url <VoxCPM2 完整 URL>   # 必填，如 http://localhost:8808
  -f, --force-rebuild        # 忽略已有参考音频，从头生成
  [--cfg 2.0]                # CFG 引导强度 1.0-3.0
  [--dit-steps 10]           # 推理步数 1-50
  [--denoise]                # 参考音频降噪
  [--normalize]              # 文本规范化
  [--use-ultimate-clone]     # 极致克隆模式
  [--gap 400]                # 台词间静音间隔 (ms)
  [-o 输出目录]              # 覆盖默认输出位置
  [--role-audio "角色=文件"]  # 手动指定参考音频（可选）
```

## 核心机制

| 机制 | 说明 |
|------|------|
| **参考音频自动匹配** | 角色名与 auto_refs/ 中文件名前缀匹配，忽略后缀（`庆尘` 匹配 `庆尘_ref.wav`） |
| **音色自引导** | 无参考的角色首次生成后自动保存为后续参考，保证音色一致 |
| **5 种生成模式** | 自动按优先级降级：极致克隆 > 可控克隆 > 纯音频克隆 > 声音设计 > 最简调用 |
| **旁白处理** | 非对话格式行自动归为旁白角色 |
| **不覆盖已有参考** | 除非加 `-f`，否则已有基线音色不会被覆盖 |

## 常见问题

**Q: 提示 "connect VoxCPM2" 失败？**
A: 检查 `--url` 是否可达，VoxCPM2 后台是否已启动（端口 8808）。

**Q: 音色不一致？**
A: 确保 Step 1 先生成了基线音色。如果某角色在 auto_refs/ 中没有对应文件，会降级为声音设计模式。

**Q: 怎么单独跑某一章？**
A: 直接传该章的压缩稿路径即可，参考音频复用 auto_refs/ 中的基线音色。

**Q: 基线音频太短，克隆效果不好？**
A: 用 `-f` 强制重建。确保 voices_script.txt 中每句台词 40~60 字，生成出的参考音频应≥5 秒。