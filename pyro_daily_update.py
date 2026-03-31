#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pyro_daily_update.py  v2.0
每日热解科研资讯自动采集（只抓国内科研/学术平台，严格过滤无关内容）
依赖：pip install requests beautifulsoup4
"""

import json
import re
import sys
import time
import random
import logging
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("缺少依赖，请先运行：pip install requests beautifulsoup4")
    sys.exit(1)

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
# 域名白名单（只允许这些来源）
# ──────────────────────────────────────────
DOMAIN_WHITELIST = [
    "zhihu.com",
    "zhuanlan.zhihu.com",
    "mp.weixin.qq.com",
    "weixin.qq.com",
    "sciencenet.cn",
    "cnki.net",
    "wanfangdata.com.cn",
    "cqvip.com",
    "kns.cnki.net",
    "pubs.rsc.org",          # RSC（化学类顶刊，学术来源）
    "www.sciencedirect.com", # Elsevier（仅学术）
    "academic.oup.com",
    "xhslink.com",
    "xiaohongshu.com",
    "bilibili.com",          # B站学术视频
    "sohu.com",              # 搜狐号（部分科研机构）
    "guancha.cn",
    "cas.cn",                # 中科院
    "most.gov.cn",           # 科技部
    "nsfc.gov.cn",           # 国自然基金委
    "sinopec.com",
    "pnnl.gov",
    "nrel.gov",
    "energy.gov",
]

# ──────────────────────────────────────────
# 内容黑名单（标题/摘要中出现任一词则丢弃）
# ──────────────────────────────────────────
BLACKLIST_PATTERNS = [
    r"破解|crack|keygen|license.?key|激活码|序列号",
    r"色情|黄色|成人|裸|性感|约炮|交友|找小姐|招聘.*女|夜场",
    r"博彩|赌博|彩票|赌场|棋牌|老虎机|百家乐",
    r"贷款|网贷|小额贷|提现|套现|刷单|兼职.*赚钱",
    r"VPN|翻墙|代理.*软件|科学上网",
    r"盗版|破解版|免费下载.*软件",
    r"发票|洗钱|走私",
    r"纪检|纪委|反腐|贪污|案件审判",  # 非科研内容
    r"明星|八卦|娱乐|综艺|追星",
    r"减肥|美容|养生|保健品|壮阳",
    r"菜谱|美食|旅游|攻略.*景点",
    r"stock|forex|cryptocurrency|比特币|炒股",
    r"BBC|CNN|NYT|foreign.*policy|washington.?post",  # 外媒无关内容
]

BLACKLIST_RE = re.compile("|".join(BLACKLIST_PATTERNS), re.IGNORECASE)

# ──────────────────────────────────────────
# 热解核心关键词（标题必须包含其中之一才入库）
# ──────────────────────────────────────────
CORE_KEYWORDS = [
    "热解", "pyrolysis", "催化", "catalytic", "生物质", "biomass",
    "废塑料", "塑料回收", "生物炭", "生物油", "废轮胎", "废橡胶",
    "共热解", "co-pyrolysis", "液化", "气化", "焦炭", "焦油",
    "沸石", "zeolite", "分子筛", "ZSM", "MCM", "SAPO",
    "催化裂解", "热裂解", "快速热解", "慢速热解", "闪速热解",
    "聚乙烯", "聚丙烯", "聚苯乙烯", "PE热解", "PP热解",
    "秸秆", "木质素", "纤维素", "半纤维素",
]
CORE_KW_RE = re.compile("|".join(CORE_KEYWORDS), re.IGNORECASE)

# ──────────────────────────────────────────
# 分类配置
# ──────────────────────────────────────────
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

# 每个分类对应的搜狗微信/知乎搜索词
SEARCH_TASKS = [
    # (搜索词,              目标分类)
    ("废塑料 热解",          "塑料热解"),
    ("塑料热解 回收",        "塑料热解"),
    ("生物质热解",           "生物质热解"),
    ("生物炭 生物油",        "生物质热解"),
    ("催化热解 机理",        "催化热解"),
    ("共热解 反应器",        "催化热解"),
    ("沸石催化剂 热解",      "创新催化剂"),
    ("新型催化剂 热解",      "创新催化剂"),
    ("热解 论文 科研",       "科研圈"),
    ("热解 课题组 进展",     "科研圈"),
]

# ──────────────────────────────────────────
# HTTP 通用请求
# ──────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def get(url: str, params: dict = None, timeout: int = 12) -> requests.Response | None:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning(f"  请求失败 {url}: {e}")
        return None


# ──────────────────────────────────────────
# 过滤核心逻辑
# ──────────────────────────────────────────

def in_whitelist(url: str) -> bool:
    """URL 必须属于白名单域名"""
    try:
        host = url.split("/")[2].lower().replace("www.", "")
        return any(host == d or host.endswith("." + d) for d in DOMAIN_WHITELIST)
    except Exception:
        return False


def is_clean(title: str, body: str) -> bool:
    """通过黑名单 + 核心关键词双重校验"""
    combined = title + " " + body
    # 黑名单命中 → 丢弃
    if BLACKLIST_RE.search(combined):
        log.debug(f"  黑名单命中，丢弃: {title[:40]}")
        return False
    # 标题不含热解相关词 → 丢弃
    if not CORE_KW_RE.search(title):
        log.debug(f"  核心词未命中，丢弃: {title[:40]}")
        return False
    return True


# ──────────────────────────────────────────
# 数据源 1：搜狗微信搜索（最接近公众号）
# ──────────────────────────────────────────

def fetch_weixin(keyword: str, max_results: int = 8) -> list[dict]:
    """通过搜狗微信搜索抓取微信公众号文章"""
    url = "https://weixin.sogou.com/weixin"
    params = {"type": "2", "query": keyword, "ie": "utf8"}
    r = get(url, params=params)
    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for li in soup.select("ul.news-list li")[:max_results]:
        a_tag = li.select_one("h3 a")
        p_tag = li.select_one("p.txt-info")
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        body  = p_tag.get_text(strip=True) if p_tag else ""
        href  = a_tag.get("href", "")
        # 搜狗返回的是重定向链接，实际是 mp.weixin.qq.com
        if not href:
            continue
        items.append({"title": title, "body": body, "url": href, "source_tag": "【微信公众号】"})
    log.info(f"  搜狗微信「{keyword}」→ {len(items)} 条")
    return items


# ──────────────────────────────────────────
# 数据源 2：知乎搜索
# ──────────────────────────────────────────

def fetch_zhihu(keyword: str, max_results: int = 6) -> list[dict]:
    """知乎搜索（文章/专栏）"""
    url = "https://www.zhihu.com/search"
    params = {"type": "content", "q": keyword}
    r = get(url, params=params)
    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = []

    for card in soup.select("div.SearchResult-Card")[:max_results]:
        a_tag = card.select_one("h2 a, .ContentItem-title a")
        p_tag = card.select_one("div.RichContent-inner p, .SearchItem-excerpt")
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        body  = p_tag.get_text(strip=True)[:200] if p_tag else ""
        href  = a_tag.get("href", "")
        if href.startswith("/"):
            href = "https://www.zhihu.com" + href
        if not href:
            continue
        items.append({"title": title, "body": body, "url": href, "source_tag": "【知乎】"})

    log.info(f"  知乎「{keyword}」→ {len(items)} 条")
    return items


# ──────────────────────────────────────────
# 数据源 3：科学网（中国科研门户）
# ──────────────────────────────────────────

def fetch_sciencenet(keyword: str, max_results: int = 6) -> list[dict]:
    """科学网搜索"""
    url = "http://www.sciencenet.cn/m/search.aspx"
    params = {"c": "news", "q": keyword}
    r = get(url, params=params)
    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for li in soup.select("div#divNews ul li")[:max_results]:
        a_tag = li.select_one("a")
        p_tag = li.select_one("p.abstract, p")
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        body  = p_tag.get_text(strip=True)[:200] if p_tag else ""
        href  = a_tag.get("href", "")
        if href.startswith("/"):
            href = "http://www.sciencenet.cn" + href
        if not href:
            continue
        items.append({"title": title, "body": body, "url": href, "source_tag": "【科学网】"})

    log.info(f"  科学网「{keyword}」→ {len(items)} 条")
    return items


# ──────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────

def extract_domain(url: str) -> str:
    try:
        return url.split("/")[2].replace("www.", "")
    except Exception:
        return "未知来源"


def extract_tags(title: str, category: str) -> list:
    keyword_map = {
        "废塑料": "废塑料", "聚乙烯": "PE", "聚丙烯": "PP", "PE": "PE", "PP": "PP",
        "生物质": "生物质", "生物油": "生物油", "生物炭": "生物炭", "秸秆": "秸秆",
        "沸石": "沸石", "分子筛": "分子筛", "单原子": "单原子催化剂", "双金属": "双金属",
        "共热解": "共热解", "反应器": "反应器", "机理": "反应机理",
        "产业化": "产业化", "投产": "工业化",
        "JACS": "JACS", "Nature": "Nature",
        "zeolite": "Zeolite", "ZSM": "ZSM-5", "MOF": "MOF",
    }
    tags = [category]
    for kw, tag in keyword_map.items():
        if kw.lower() in title.lower() and tag not in tags:
            tags.append(tag)
        if len(tags) >= 4:
            break
    return tags[:4]


# ──────────────────────────────────────────
# 主采集逻辑
# ──────────────────────────────────────────

def collect_news() -> list[dict]:
    category_pool: dict[str, list] = {k: [] for k in CATEGORY_QUOTA}
    seen_urls: set[str] = set()

    for keyword, category in SEARCH_TASKS:
        log.info(f"搜索：「{keyword}」→ {category}")

        # 三个数据源都尝试
        raw_items: list[dict] = []
        raw_items += fetch_weixin(keyword, max_results=6)
        time.sleep(random.uniform(1.5, 3.0))
        raw_items += fetch_zhihu(keyword, max_results=5)
        time.sleep(random.uniform(1.5, 3.0))
        raw_items += fetch_sciencenet(keyword, max_results=4)
        time.sleep(random.uniform(1.0, 2.0))

        for item in raw_items:
            title = item["title"].strip()
            body  = item["body"].strip()
            url   = item["url"].strip()
            tag   = item.get("source_tag", "")

            # 基础过滤
            if not title or not url:
                continue
            if url in seen_urls:
                continue

            # 域名白名单（搜狗微信返回的是 /link?url=... 相对路径，视为合法）
            is_weixin_redirect = (
                "weixin.sogou.com" in url
                or "mp.weixin.qq.com" in url
                or url.startswith("/link?url=")   # 搜狗站内重定向
            )
            if not is_weixin_redirect and not in_whitelist(url):
                log.debug(f"  域名不在白名单，丢弃: {url}")
                continue

            # 内容清洁度校验
            if not is_clean(title, body):
                continue

            seen_urls.add(url)
            # 搜狗重定向链接补全为完整 URL
            if url.startswith("/link?url="):
                url = "https://weixin.sogou.com" + url
            display_title = f"{tag} {title}" if tag else title

            category_pool[category].append({
                "category": category,
                "title":    display_title,
                "summary":  body[:200] if body else "点击原文查看详情。",
                "source":   "weixin.qq.com" if is_weixin_redirect else extract_domain(url),
                "url":      url,
                "tags":     extract_tags(title, category),
            })

        log.info(f"  当前「{category}」池：{len(category_pool[category])} 条")

    # 按配额拼装
    news_list = []
    item_id = 1
    for category, quota in CATEGORY_QUOTA.items():
        items = category_pool[category][:quota]
        if len(items) < quota:
            log.warning(f"分类「{category}」只有 {len(items)} 条（目标 {quota}）")
        for it in items:
            it["id"] = item_id
            news_list.append(it)
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

        cats = Counter(n["category"] for n in news)
        log.info("分类统计：" + "  ".join(
            f"{CAT_ICONS.get(c, '•')}{c}:{n}条" for c, n in cats.items()
        ))

    run_inject()
    log.info("========== 更新完成 ==========")


if __name__ == "__main__":
    main()
