#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""删除CSS中催化热解和创新催化剂的样式规则（精确逐行删除）"""

with open('index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 要删除的行（包含这些关键字的完整CSS规则行）
skip_patterns = [
    'data-cat="催化热解"',
    'data-cat="创新催化剂"',
]

new_lines = []
skipped = 0
for line in lines:
    if any(p in line for p in skip_patterns):
        skipped += 1
        continue
    new_lines.append(line)

with open('index.html', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'Deleted {skipped} lines')

import re
html = ''.join(new_lines)
remaining = [m.group() for m in re.finditer(r'催化热解|创新催化剂', html)]
print(f'Remaining: {len(remaining)}' if remaining else 'All clean!')
