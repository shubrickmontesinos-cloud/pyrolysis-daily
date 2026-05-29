#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三轮清理"""

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. footer (middle dot version)
old_footer = '覆盖领域：催化热解 · 塑料热解 · 生物质热解 · 创新催化剂 · 科研圈 · 科研技巧'
new_footer = '覆盖领域：塑料热解 · 生物质热解 · 科研圈 · 科研技巧'
html = html.replace(old_footer, new_footer)

# 2. CAT_ICONS - read from file to avoid shell encoding issues
with open('cat_icons_old.txt', 'r', encoding='utf-8') as f:
    old_icons = f.read().strip()
with open('cat_icons_new.txt', 'r', encoding='utf-8') as f:
    new_icons = f.read().strip()
html = html.replace(old_icons, new_icons)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

import re
remaining = [m.group() for m in re.finditer(r'催化热解|创新催化剂', html)]
print(f'Remaining: {len(remaining)}' if remaining else 'All clean!')
if remaining:
    for m in remaining:
        print(f'  {m}')
