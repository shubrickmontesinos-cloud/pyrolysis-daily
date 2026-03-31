#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_daily_data.py
将新一天的新闻数据注入 index.html 的 EMBEDDED_DATA 中。
由定时任务生成当日 JSON 后调用，或由定时任务直接调用。

用法:
  python inject_daily_data.py <YYYY-MM-DD.json>
  python inject_daily_data.py  # 自动查找今日 JSON
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR  = Path(__file__).parent
DATA_DIR    = SCRIPT_DIR / "data"
HTML_FILE   = SCRIPT_DIR / "index.html"
MAX_DAYS    = 30   # 往期最多保留天数

def load_today_json(date_str: str) -> dict:
    path = DATA_DIR / f"{date_str}.json"
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def scan_all_days() -> list[dict]:
    """读取 data/ 下所有 YYYY-MM-DD.json，返回按日期降序的列表"""
    days = []
    for f in sorted(DATA_DIR.glob("????-??-??.json"), reverse=True)[:MAX_DAYS]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            days.append({"date": data["date"], "news": data["news"]})
        except Exception as e:
            print(f"  [WARN] 跳过 {f.name}: {e}")
    return days

def inject_to_html(all_days: list[dict], current_date: str):
    html = HTML_FILE.read_text(encoding="utf-8")

    new_js = (
        f'const EMBEDDED_DATA = {{\n'
        f'  "currentDate": "{current_date}",\n'
        f'  "allDays": {json.dumps(all_days, ensure_ascii=False, separators=(",", ":"))}\n'
        f'}};'
    )

    # Replace between <script id="embedded-data"> ... </script>
    pattern = r'(<script id="embedded-data">)(.*?)(</script>)'
    replacement = r'\g<1>\n' + new_js + r'\n\g<3>'
    new_html, count = re.subn(pattern, replacement, html, flags=re.DOTALL)

    if count == 0:
        print("[ERROR] 未找到 embedded-data script 块，注入失败")
        return False

    HTML_FILE.write_text(new_html, encoding="utf-8")
    print(f"[✅] 已注入 {len(all_days)} 天数据到 index.html，当前显示: {current_date}")
    return True

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    date_str = today

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        # 支持传文件路径或日期字符串
        if arg.endswith(".json"):
            date_str = Path(arg).stem
        else:
            date_str = arg

    print(f"[INFO] 注入日期: {date_str}")

    try:
        load_today_json(date_str)   # 验证文件存在
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    all_days = scan_all_days()
    if not all_days:
        print("[ERROR] data/ 目录下无有效数据文件")
        sys.exit(1)

    success = inject_to_html(all_days, date_str)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
