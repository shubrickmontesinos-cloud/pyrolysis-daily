#!/usr/bin/env python3
# -*- coding: utf-8 -*-
with open('index.html','r',encoding='utf-8') as f:
    html = f.read()
css_start = html.find('<style>')
css_end = html.find('</style>')
css = html[css_start:css_end+8]
opens = css.count('{')
closes = css.count('}')
print(f'CSS: {len(css)} chars, opens:{opens} closes:{closes}, balanced: {opens==closes}')
print(f'Total HTML: {len(html)} chars')
