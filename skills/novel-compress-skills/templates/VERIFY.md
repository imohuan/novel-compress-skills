# 独立 Verifier 验收清单

> 只读沙箱，不可修改文件。退出码 0=通过。

## 检查1：压缩比

```bash
python scripts/verify.py --manifest input/chunks_manifest.json --output output --min 0.30 --max 0.45
```

## 检查2：关键实体保留

```bash
python scripts/verify.py --manifest input/chunks_manifest.json --output output --entities-file work/_check_entities.txt
```

## 检查3：AI 味禁用词

```
python -c "
import os
banned = ['综上所述','由此可见','值得一提的是','毋庸置疑','不得不说','赋能','闭环','抓手','基石','保驾护航']
found = []
for fn in sorted(os.listdir('output')):
    if fn.endswith('.txt'):
        with open(os.path.join('output',fn), encoding='utf-8') as f:
            text = f.read()
        for w in banned:
            if w in text: found.append(f'{fn}: {w}')
if found:
    for f in found: print(f'BANNED: {f}')
    exit(1)
print('PASS')
"
```

## 检查4：对话格式正确性

```
python -c "
import os, re
errs = []
for fn in sorted(os.listdir('output')):
    if not fn.endswith('.txt'): continue
    with open(os.path.join('output',fn), encoding='utf-8-sig') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line: continue
            # 必须有中文冒号
            if '\uff1a' not in line:  # '：'
                errs.append(f'{fn}:{i} no colon')
            elif line.startswith('\u65c1\u767d\uff1a'):  # '旁白：'
                if '(' in line: errs.append(f'{fn}:{i} narrator has description')
            elif not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9]+\(.+\)\uff1a.+', line):
                if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9]+\uff1a.+', line):
                    errs.append(f'{fn}:{i} bad format: {line[:50]}')
if errs:
    for e in errs[:20]: print(e)
    exit(1)
print('PASS')
"
```

## 检查5：Bible 完整性

```
python -c "
import os
req = ['characters.md','settings.md','timeline.md','throughline.md','arcs.md','writing_techniques.md']
for fn in req:
    p = f'bible/{fn}'
    if not os.path.exists(p):
        print(f'MISSING: {fn}')
        exit(1)
    with open(p, encoding='utf-8') as f:
        if len(f.read().strip()) < 30:
            print(f'TOO SHORT: {fn}')
            exit(1)
print('PASS')
"
```

## 检查6：章节连续性

```
python -c "
import os, re
files = sorted([f for f in os.listdir('output') if re.match(r'ch\d+\.txt', f)])
nums = [int(re.search(r'\d+', f).group()) for f in files]
expected = set(range(1, nums[-1]+1)) - set(nums)
if expected: print(f'MISSING: {sorted(expected)}'); exit(1)
print(f'OK: 1-{nums[-1]}')
"
```

## 总结果

全部 6 项通过 → exit 0。
