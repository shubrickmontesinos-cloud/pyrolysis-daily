#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""删除 index.html 中的「催化热解」和「创新催化剂」分类"""

import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. 删除 CSS 变量（亮色+暗色各两套）
html = re.sub(r'\s*--cat-catalytic: #[0-9a-fA-F]+;', '', html)
html = re.sub(r'\s*--cat-catalyst: #[0-9a-fA-F]+;', '', html)

# 2. 删除 filter-btn 样式（催化热解 + 创新催化剂）
for cat in ['催化热解', '创新催化剂']:
    # 匹配 .filter-btn[data-cat="xxx"] { ... } 整个块
    pattern = rf'\s*\.filter-btn\[data-cat="{cat}"\][^\n]*\n(?:\s*[^\n]*\n)*?\s*\}}'
    html = re.sub(pattern, '', html)

# 3. 删除 news-card 样式
for cat in ['催化热解', '创新催化剂']:
    pattern = rf'\s*\.news-card\[data-cat="{cat}"\][^\n]*\n(?:\s*[^\n]*\n)*?\s*\}}'
    html = re.sub(pattern, '', html)
    # .news-card[data-cat="xxx"]::before { ... }
    pattern2 = rf'\s*\.news-card\[data-cat="{cat}"\]::before[^\n]*\n(?:\s*[^\n]*\n)*?\s*\}}'
    html = re.sub(pattern2, '', html)

# 4. 删除 cat-pill 样式
for cat in ['催化热解', '创新催化剂']:
    pattern = rf'\s*\[data-cat="{cat}"\]\s*\.cat-pill[^\n]*\n(?:\s*[^\n]*\n)*?\s*\}}'
    html = re.sub(pattern, '', html)

# 5. header small 文字
old_header = '热解周报 / 塑料热解 / 生物质 / 催化热解 / 创新催化剂 / 科研圈 / 科研技巧'
new_header = '热解周报 / 塑料热解 / 生物质热解 / 科研圈 / 科研技巧'
html = html.replace(old_header, new_header)

# 6. footer 分类文字
old_footer = '塑料热解 / 生物质热解 / 催化热解 / 创新催化剂 / 科研圈 / 科研技巧'
new_footer = '塑料热解 / 生物质热解 / 科研圈 / 科研技巧'
html = html.replace(old_footer, new_footer)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Done. File size: {len(html)} chars')

# 验证：检查是否还有残留
remaining = re.findall(r'催化热解|创新催化剂|catalytic|catalyst', html)
if remaining:
    print(f'Warning: still found {len(remaining)} matches:')
    for m in set(remaining):
        print(f'  - {m}')
else:
    print('OK: no traces of catalytic/catalyst categories found')
