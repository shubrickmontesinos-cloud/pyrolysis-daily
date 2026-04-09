#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_daily_data.py (Fixed v3.1)
优化了正则注入安全性与 JS 字符串安全
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# 配置路径
SCRIPT_DIR = Path(__file__).parent
DATA_DIR   = SCRIPT_DIR / "data"
HTML_FILE  = SCRIPT_DIR / "index.html"
MAX_DAYS   = 30  # 往期最多保留天数

def load_today_json(date_str: str) -> dict:
    path = DATA_DIR / f"{date_str}.json"
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def scan_all_days() -> List[Dict]:
    """读取 data/ 下所有 YYYY-MM-DD.json，返回按日期降序的列表"""
    days = []
    # 获取并排序所有符合格式的json
    json_files = sorted(DATA_DIR.glob("????-??-??.json"), reverse=True)
    for f in json_files[:MAX_DAYS]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            days.append({"date": data["date"], "news": data["news"]})
        except Exception as e:
            print(f"  [WARN] 跳过损坏文件 {f.name}: {e}")
    return days

def sanitize_news(all_days: List[Dict]) -> List[Dict]:
    """清理控制字符，防止注入 JS 时产生语法错误"""
    clean_days = []
    for day in all_days:
        new_news = []
        for item in day.get("news", []):
            new_item = item.copy()
            for field in ("title", "summary", "source", "url"):
                if field in new_item and isinstance(new_item[field], str):
                    # 清理换行符、制表符及多余空格
                    new_item[field] = " ".join(new_item[field].split())
            new_news.append(new_item)
        clean_days.append({"date": day["date"], "news": new_news})
    return clean_days

def inject_to_html(all_days: List[Dict], current_date: str):
    if not HTML_FILE.exists():
        print(f"[ERROR] 找不到 HTML 文件: {HTML_FILE}")
        return False

    content = HTML_FILE.read_text(encoding="utf-8")

    # 1. 准备数据
    safe_days = sanitize_news(all_days)
    data_json = json.dumps(
        {"currentDate": current_date, "allDays": safe_days},
        ensure_ascii=False,
        separators=(",", ":")
    )

    # 2. 安全处理：防止新闻标题中的 </script> 破坏 HTML 结构
    data_json = data_json.replace("</script>", r"<\/script>")

    new_js_block = f'const EMBEDDED_DATA = {data_json};'

    # 3. 正则注入（使用 Lambda 避免正则转义符 \ 引起的 backreference 报错）
    pattern = r'(<script id="embedded-data">)(.*?)(</script>)'
    
    # 使用函数作为 re.sub 的第二个参数，是处理包含反斜杠字符串的唯一安全方法
    def replacer(match):
        return f"{match.group(1)}\n{new_js_block}\n{match.group(3)}"

    new_html, count = re.subn(pattern, replacer, content, flags=re.DOTALL)

    if count == 0:
        print("[ERROR] 未找到 <script id=\"embedded-data\"> 标签，注入失败")
        return False

    HTML_FILE.write_text(new_html, encoding="utf-8")
    print(f"[✅] 已成功注入 {len(all_days)} 天数据，当前日期: {current_date}")
    return True

def main():
    # 获取目标日期
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        date_str = Path(arg).stem if arg.endswith(".json") else arg
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"[INFO] 开始注入数据，目标日期: {date_str}")

    try:
        # 验证当日数据是否存在
        load_today_json(date_str)
        
        # 扫描历史数据
        all_days = scan_all_days()
        if not all_days:
            print("[ERROR] 没有任何可用的 JSON 数据")
            sys.exit(1)

        # 执行注入
        if inject_to_html(all_days, date_str):
            sys.exit(0)
        else:
            sys.exit(1)

    except FileNotFoundError:
        print(f"[ERROR] 找不到日期为 {date_str} 的数据文件，请先运行采集脚本")
        sys.exit(1)
    except Exception as e:
        print(f"[CRITICAL] 注入过程中发生未知错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
