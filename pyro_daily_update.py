#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pyro_daily_update.py
每日热解新闻自动采集脚本（纯 Python，无需 LobsterAI/Claude）
依赖：pip install duckduckgo-search
"""

import json
import sys
import time
import random
import logging
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────
# 路径配置
# ──────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
DATA_DIR   = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(SCRIPT_DIR / "update.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────
# 搜索关键词 & 分类映射
# ──────────────────────────────────────────
QUERIES = [
    # (搜索词, 目标分类, 每次取结果数)
    ("废塑料 热解 最新进展 2026",              "塑料热解",   5),
    ("plastic pyrolysis industry news 2026",  "塑料热解",   4),
    ("生物质热解 生物油 生物炭 最新 2026",      "生物质热解", 5),
    ("biomass pyrolysis biochar 2026",        "生物质热解", 4),
    ("催化热解 共热解 反应器 机理 2026",        "催化热解",   5),
    ("catalytic pyrolysis mechanism 2026",    "催化热解",   4),
    ("新型催化剂 沸石 热解 单原子 2026",        "创新催化剂", 5),
    ("novel catalyst zeolite pyrolysis 2026", "创新催化剂", 4),
    ("热解 科研 期刊 论文 知乎 科普 2026",      "科研圈",     5),
]

# 每个分类最多保留几条（总计 20 条）
CATEGORY_QUOTA = {
    "塑料热解":   4,
    "生物质热解": 4,
    "催化热解":   4,
    "创新催化剂": 4,
    "科研圈":     4,
}

CAT_ICONS = {
    "塑料热解":   "♻️",
    "生物质热解": "🌿",
    "催化热解":   "⚗️",
    "创新催化剂": "✨",
    "科研圈":     "🎓",
}


# ──────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────

def detect_source_tag(url: str, title: str) -> str:
    combined = (url + title).lower()
    if "zhihu" in combined or "知乎" in combined:
        return "【知乎】"
    if "weixin.qq" in combined or "mp.weixin" in combined or "微信" in combined or "公众号" in combined:
        return "【微信公众号】"
    if "xiaohongshu" in combined or "小红书" in combined:
        return "【小红书】"
    if "douyin" in combined or "抖音" in combined:
        return "【抖音】"
    if "bilibili" in combined or "b站" in combined:
        return "【B站】"
    if "neste" in combined:
        return "【Neste官网】"
    if "sciencenet" in combined or "科学网" in combined:
        return "【科学网】"
    if any(d in combined for d in ["nature.", "science.", "acs.", "elsevier.", "wiley.", "springer."]):
        return "【学术期刊】"
    return ""


def extract_tags(title: str, category: str) -> list:
    keyword_map = {
        "废塑料": "废塑料", "聚乙烯": "PE", "聚丙烯": "PP", "PE": "PE", "PP": "PP",
        "生物质": "生物质", "生物油": "生物油", "生物炭": "生物炭", "秸秆": "秸秆",
        "沸石": "沸石", "分子筛": "分子筛", "单原子": "单原子催化剂", "双金属": "双金属催化剂",
        "共热解": "共热解", "反应器": "反应器", "机理": "反应机理",
        "产业化": "产业化", "投产": "工业化",
        "JACS": "JACS", "Nature": "Nature", "ACS": "ACS期刊",
        "zeolite": "Zeolite", "ZSM": "ZSM-5", "MOF": "MOF",
    }
    tags = [category]
    for kw, tag in keyword_map.items():
        if kw.lower() in title.lower() and tag not in tags:
            tags.append(tag)
        if len(tags) >= 4:
            break
    return tags[:4]


def extract_domain(url: str) -> str:
    try:
        host = url.split("/")[2].replace("www.", "")
        return host
    except Exception:
        return "未知来源"


# ──────────────────────────────────────────
# 搜索核心
# ──────────────────────────────────────────

def search_duckduckgo(query: str, max_results: int) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            log.error("缺少依赖，请先运行：pip install ddgs")
            sys.exit(1)

    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results, region="cn-zh"):
                results.append({
                    "title": r.get("title", "").strip(),
                    "body":  r.get("body", "").strip(),
                    "url":   r.get("href", "").strip(),
                })
        log.info(f"  查询「{query[:35]}」→ {len(results)} 条")
    except Exception as e:
        log.warning(f"  查询「{query[:35]}」失败: {e}")
    time.sleep(random.uniform(2.0, 4.5))  # 礼貌延迟
    return results


def collect_news() -> list[dict]:
    category_pool: dict[str, list] = {k: [] for k in CATEGORY_QUOTA}

    for query, category, num in QUERIES:
        results = search_duckduckgo(query, num)
        seen_in_cat = {n["url"] for n in category_pool[category]}
        for r in results:
            title = r["title"]
            body  = r["body"]
            url   = r["url"]
            if not title or not url or url in seen_in_cat:
                continue
            seen_in_cat.add(url)

            tag = detect_source_tag(url, title)
            display_title = f"{tag} {title}" if tag else title

            category_pool[category].append({
                "category": category,
                "title":    display_title,
                "summary":  body[:200] if body else "点击原文查看详情。",
                "source":   extract_domain(url),
                "url":      url,
                "tags":     extract_tags(title, category),
            })

    # 按配额拼装，不足的分类打印警告
    news_list = []
    item_id = 1
    for category, quota in CATEGORY_QUOTA.items():
        items = category_pool[category][:quota]
        if len(items) < quota:
            log.warning(f"分类「{category}」只有 {len(items)} 条（目标 {quota}）")
        for item in items:
            item["id"] = item_id
            news_list.append(item)
            item_id += 1

    return news_list


# ──────────────────────────────────────────
# 写文件 & 注入 HTML
# ──────────────────────────────────────────

def save_json(news_list: list[dict], date_str: str) -> Path:
    out_path = DATA_DIR / f"{date_str}.json"
    payload = {
        "date":         date_str,
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "news":         news_list,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info(f"数据已保存：{out_path}")
    return out_path


def run_inject():
    inject_script = SCRIPT_DIR / "inject_daily_data.py"
    result = subprocess.run(
        [sys.executable, str(inject_script)],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode == 0:
        log.info(result.stdout.strip())
    else:
        log.error(f"注入失败:\n{result.stderr}")


# ──────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    log.info(f"========== 热解日报更新开始 {today} ==========")

    out_path = DATA_DIR / f"{today}.json"
    if out_path.exists():
        log.info("今日数据已存在，直接执行注入步骤")
    else:
        news = collect_news()
        if not news:
            log.error("未获取到任何新闻，退出")
            sys.exit(1)
        save_json(news, today)

        # 打印统计
        cats = Counter(n["category"] for n in news)
        log.info(f"分类统计：" + "  ".join(
            f"{CAT_ICONS.get(c,'•')}{c}:{n}条" for c, n in cats.items()
        ))

    run_inject()
    log.info("========== 更新完成 ==========")


if __name__ == "__main__":
    main()
