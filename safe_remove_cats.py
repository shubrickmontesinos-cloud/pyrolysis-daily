#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全地移除「催化热解」和「创新催化剂」分类。
只用精确字符串替换，不动CSS结构。
"""

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

changes = 0

# ========== 1. CATEGORIES 数组 ==========
old = "['全部','塑料热解','生物质热解','催化热解','创新催化剂','科研圈','科研技巧']"
new = "['全部','塑料热解','生物质热解','科研圈','科研技巧']"
if old in html:
    html = html.replace(old, new)
    changes += 1
    print("OK: CATEGORIES array")

# ========== 2. CAT_ICONS (两处，用文件读入避免shell编码问题) ==========
try:
    with open('_old_icons.txt', 'r', encoding='utf-8') as f:
        old_i = f.read().strip()
    with open('_new_icons.txt', 'r', encoding='utf-8') as f:
        new_i = f.read().strip()
    if old_i in html:
        html = html.replace(old_i, new_i)
        changes += 1
        print("OK: CAT_ICONS")
except:
    print("SKIP: CAT_ICONS (file not found)")

# ========== 3. header small (两种格式) ==========
replacements_header = [
    ('热解周报 / 塑料热解 / 生物质 / 催化热解 / 创新催化剂 / 科研圈 / 科研技巧',
     '热解周报 / 塑料热解 / 生物质热解 / 科研圈 / 科研技巧'),
    ('PyroWeekly · 催化热解 / 塑料 / 生物质 / 科研圈 / 科研技巧',
     'PyroWeekly · 塑料热解 / 生物质热解 / 科研圈 / 科研技巧'),
]
for o, n in replacements_header:
    if o in html:
        html = html.replace(o, n)
        changes += 1
        print(f"OK: header small")

# ========== 4. footer (两种格式) ==========
replacements_footer = [
    ('塑料热解 / 生物质热解 / 催化热解 / 创新催化剂 / 科研圈 / 科研技巧',
     '塑料热解 / 生物质热解 / 科研圈 / 科研技巧'),
    ('覆盖领域：催化热解 · 塑料热解 · 生物质热解 · 创新催化剂 · 科研圈 / 科研技巧',
     '覆盖领域：塑料热解 · 生物质热解 / 科研圈 / 科研技巧'),
    ('覆盖领域：催化热解 · 塑料热解 · 生物质热解 · 创新催化剂 · 科研圈 · 科研技巧',
     '覆盖领域：塑料热解 · 生物质热解 · 科研圈 · 科研技巧'),
]
for o, n in replacements_footer:
    if o in html:
        html = html.replace(o, n)
        changes += 1
        print(f"OK: footer")

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\nTotal changes: {changes}")

# 验证：检查残留
import re
remaining = [m.group() for m in re.finditer(r'催化热解|创新催化剂', html)]
if remaining:
    print(f"\nWarning: {len(remaining)} remaining matches:")
    for m in set(remaining):
        print(f'  - {m}')
else:
    print("\nClean! No traces of removed categories.")
