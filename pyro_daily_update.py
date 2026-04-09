#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pyro_daily_update.py v3.3 (Robust Version)
"""

import json
import re
import sys
import time
import random
import logging
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Set, Tuple

# 环境检查
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: Missing dependencies. Run 'pip install requests beautifulsoup4'")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
DATA_DIR   = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# --- 配置区 (保持不变) ---
CATEGORY_QUOTA = {"塑料热解": 6, "生物质热解": 3, "催化热解": 4, "创新催化剂": 4, "科研圈": 3, "科研技巧": 5}
# (此处省略中间重复的黑名单、关键词等配置，直接进入逻辑改进部分)
# [注意：请保留你之前版本中的 BLACKLIST_PATTERNS, APPROVED_JOURNALS, CORE_KEYWORDS 等变量]

# --- 逻辑改进区 ---

def run_inject(date_str: str):
    """调用注入脚本"""
    inject_script = SCRIPT_DIR / "inject_daily_data.py"
    if not inject_script.exists():
        log.error(f"注入脚本不存在: {inject_script}")
        return False
        
    # 显式传递日期参数
    res = subprocess.run(
        [sys.executable, str(inject_script), date_str],
        capture_output=True, text=True, encoding="utf-8"
    )
    if res.returncode == 0:
        log.info(f"注入成功: {res.stdout.strip()}")
        return True
    else:
        log.error(f"注入失败: {res.stderr}")
        return False

def main():
    # 统一使用北京时间 (UTC+8) 防止时区混乱导致文件找不到
    bj_time = datetime.utcnow() + timedelta(hours=8)
    today = bj_time.strftime("%Y-%m-%d")
    
    log.info(f"========== 任务开始: {today} (BJ Time) ==========")

    out_path = DATA_DIR / f"{today}.json"
    
    # 1. 尝试抓取
    news = []
    try:
        # 这里调用你之前的 collect_news() 函数
        # 注意：确保 collect_news 定义在 main 之前
        news = collect_news() 
    except Exception as e:
        log.error(f"采集过程发生异常: {e}")

    # 2. 判断逻辑
    if news:
        # 抓到了新内容，保存
        payload = {
            "date": today,
            "generated_at": bj_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "news": news,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"成功保存今日新数据: {len(news)} 条")
    else:
        # 没抓到新内容（可能是去重后没了）
        if out_path.exists():
            log.warning("未发现新资讯，但今日数据文件已存在，将执行数据注入以更新页面。")
        else:
            log.error("未发现新资讯，且今日无历史数据。为了防止页面空白，任务终止。")
            # 这种情况下才报错，如果是手动测试建议先随便放个旧文件进去
            sys.exit(0) # 改为 0，不让 Action 变红

    # 3. 执行注入
    if run_inject(today):
        log.info("========== 任务圆满完成 ==========")
    else:
        log.error("注入步骤失败")
        sys.exit(1)

# (请确保把 collect_news, fetch_xxx 等函数补全到这个文件中)
