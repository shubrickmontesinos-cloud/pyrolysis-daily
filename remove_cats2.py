#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二轮清理：header small, footer, JS CATEGORIES, CAT_ICONS"""

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

replacements = [
    # header small (另一种格式)
    ('PyroWeekly · 催化热解 / 塑料 / 生物质 / 科研圈 / 科研技巧',
     'PyroWeekly · 塑料热解 / 生物质热解 / 科研圈 / 科研技巧'),
    # footer
    ('覆盖领域：催化热解 · 塑料热解 · 生物质热解 · 创新催化剂 · 科研圈 / 科研技巧',
     '覆盖领域：塑料热解 · 生物质热解 / 科研圈 / 科研技巧'),
    # CATEGORIES array
    ("['全部','塑料热解','生物质热解','催化热解','创新催化剂','科研圈','科研技巧']",
     "['全部','塑料热解','生物质热解','科研圈','科研技巧']"),
]

for old, new in replacements:
    html = html.replace(old, new)

# CAT_ICONS dict - 用正则匹配避免emoji问题
import re
old_icons_pattern = r"\{'全部':'[^']+',?'塑料热解':'[^']+',?'生物质热解':'[^']+,?'催化热解':'[^']+,?'创新催化剂':'[^']+,?'科研圈':'[^']+,?'科研技巧':'[^']+'\}"
new_icons_str = "{'全部':'🌐','塑料热解':'♻️','生物质热解':'🌿','科研圈':'🎓','科研技巧':'💡'}"
html = re.sub(old_icons_pattern, new_icons_str, html)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

# 验证
remaining = [m.group() for m in re.finditer(r'催化热解|创新催化剂', html)]
if remaining:
    print(f'Still {len(remaining)} matches:')
    for m in set(remaining):
        print(f'  {m}')
else:
    print('All clean!')
