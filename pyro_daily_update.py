#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pyro_daily_update.py  v3.0
每日热解科研资讯自动采集
数据源：搜狗微信公众号 + CrossRef 学术期刊 API + arXiv 预印本
依赖：pip install requests beautifulsoup4
"""

import html
import json
import re
import sys
import time
import random
import logging
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta
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
# 内容黑名单（标题/摘要中出现任一词则丢弃）
# ──────────────────────────────────────────
BLACKLIST_PATTERNS = [
    r"破解|crack|keygen|license.?key|激活码|序列号",
    r"色情|黄色|成人|裸露|性感|约炮|交友|找小姐|招聘.*女|夜场",
    r"博彩|赌博|彩票|赌场|棋牌|老虎机|百家乐",
    r"贷款|网贷|小额贷|提现|套现|刷单|兼职.*赚钱",
    r"VPN|翻墙|代理.*软件|科学上网",
    r"盗版|破解版|免费下载.*软件",
    r"发票|洗钱|走私",
    r"纪检|纪委|反腐|贪污|案件审判",
    r"明星|八卦|娱乐|综艺|追星",
    r"减肥|美容|养生|保健品|壮阳",
    r"菜谱|美食|旅游|攻略.*景点",
    r"股票|cryptocurrency|比特币|炒股|forex",
]
BLACKLIST_RE = re.compile("|".join(BLACKLIST_PATTERNS), re.IGNORECASE)

# ──────────────────────────────────────────
# 期刊精确白名单（CrossRef container-title 必须包含其中之一，不区分大小写）
# 只收与热解/催化/能源/环境直接相关的核心期刊
# ──────────────────────────────────────────
APPROVED_JOURNALS = [
    # 热解专属
    "journal of analytical and applied pyrolysis",
    "journal of analytical & applied pyrolysis",
    # 燃料/能源
    "fuel",
    "fuel processing technology",
    "energy & fuels",
    "energy and fuels",
    "applied energy",
    "energy",                                       # Energy (Elsevier)
    "energy conversion and management",
    "joule",
    "international journal of hydrogen energy",
    "energy & environmental science",
    "energy and environmental science",
    "renewable energy",
    "renewable and sustainable energy reviews",
    "journal of the energy institute",
    # 化学工程
    "chemical engineering journal",
    "industrial & engineering chemistry research",
    "industrial and engineering chemistry research",
    "chemical engineering science",
    "aiche journal",
    "chemsuschem",
    # 催化
    "applied catalysis b",
    "applied catalysis a",
    "acs catalysis",
    "journal of catalysis",
    "catalysis today",
    "catalysis communications",
    "catalysis reviews",
    "catalysis science",
    "microporous and mesoporous materials",         # zeolite/分子筛
    # 环境
    "environmental science & technology",
    "environmental science and technology",
    "acs sustainable chemistry",
    "green chemistry",
    "waste management",
    "bioresource technology",
    "journal of cleaner production",
    "science of the total environment",
    "resources, conservation and recycling",
    "resources conservation and recycling",
    "separation and purification technology",
    # 生物质
    "biomass and bioenergy",
    "biomass conversion and biorefinery",
    "industrial crops and products",
    # 高影响综合/化学
    "nature",
    "science",
    "nature communications",
    "nature energy",
    "nature chemistry",
    "science advances",
    "angewandte chemie",
    "journal of the american chemical society",
    "acs nano",
    "advanced materials",
    "advanced energy materials",
    "advanced functional materials",
    "chemical society reviews",
    "accounts of chemical research",
    "progress in energy and combustion science",
    # 材料/高分子
    "polymer degradation",
    "polymer degradation and stability",
    "journal of hazardous materials",
    "chemosphere",
]

JOURNAL_WHITELIST_RE = re.compile(
    "|".join(re.escape(j) for j in APPROVED_JOURNALS),
    re.IGNORECASE,
)

# ──────────────────────────────────────────
# 热解核心关键词（标题必须包含其中之一才入库）
# ──────────────────────────────────────────
CORE_KEYWORDS = [
    # 中文热解核心
    "热解", "催化热解", "热裂解", "催化裂解", "快速热解",
    "共热解", "废塑料", "塑料回收", "废轮胎", "废橡胶",
    "生物质", "生物炭", "生物油", "焦油", "焦炭",
    "沸石", "分子筛", "聚乙烯", "聚丙烯", "聚苯乙烯",
    "秸秆", "木质素", "纤维素", "高纯氢", "碳纳米管",
    "微波热解", "等离子体热解", "催化气化",
    # 英文热解核心（短语优先，防止宽泛单词误命中）
    "pyrolysis", "catalytic pyrolysis", "thermal pyrolysis",
    "co-pyrolysis", "flash pyrolysis", "fast pyrolysis",
    "slow pyrolysis", "microwave pyrolysis", "plasma pyrolysis",
    "in-situ catalytic", "ex-situ catalytic",
    "pyrolysis-catalysis",
    "catalytic cracking", "thermal cracking",
    "catalytic gasification",
    # 废塑料/聚烯烃
    "waste plastic", "waste polyolefin", "waste polyolefins",
    "waste polyethylene", r"\bwaste PE\b", r"\bwaste PP\b",
    "waste polypropylene", "waste polystyrene",
    r"\bPE pyrolysis\b", r"\bPP pyrolysis\b",
    r"\bPET pyrolysis\b", r"\bPVC pyrolysis\b",
    r"\bPS pyrolysis\b",
    "polyolefin", "polyolefins",
    "polyethylene", "polypropylene", "polystyrene",
    # 产物/催化剂
    "biochar", "bio-oil", "biocrude",
    "hydrogen production", "hydrogen generation",
    r"\bH2 production\b", r"\bH₂ production\b",
    "high-purity hydrogen",
    "carbon nanotube", "carbon nanotubes", r"\bCNT\b", r"\bCNTs\b",
    "zeolite", r"\bZSM\b", r"\bMCM\b", r"\bSAPO\b",
    "single-atom", "single atom catalyst",
    # 生物质
    "biomass", "lignocellulosic", "lignin", "cellulose",
    # 带词边界的短词（防误匹配）
    r"\btar\b", r"\bchar\b",
]
CORE_KW_RE = re.compile("|".join(CORE_KEYWORDS), re.IGNORECASE)

# ──────────────────────────────────────────
# 分类配置
# 塑料热解6 / 生物质热解3 / 催化热解4 / 创新催化剂4 / 科研圈3  合计20
# ──────────────────────────────────────────
CATEGORY_QUOTA = {
    "塑料热解":   6,
    "生物质热解": 3,
    "催化热解":   4,
    "创新催化剂": 4,
    "科研圈":     3,
    "科研技巧":   5,
}

# 每个分类期刊/预印本来源的目标条数（剩余用微信公众号补足）
# 约各占一半：期刊3/微信3、期刊2/微信1、期刊2/微信2、期刊2/微信2、期刊2/微信1
# 科研技巧全部来自微信公众号，期刊配额为0
JOURNAL_QUOTA = {
    "塑料热解":   3,
    "生物质热解": 2,
    "催化热解":   2,
    "创新催化剂": 2,
    "科研圈":     2,
    "科研技巧":   0,
}

CAT_ICONS = {
    "塑料热解":   "♻️",
    "生物质热解": "🌿",
    "催化热解":   "⚗️",
    "创新催化剂": "✨",
    "科研圈":     "🎓",
    "科研技巧":   "💡",
}

# ──────────────────────────────────────────
# CrossRef 学术期刊查询配置（英文期刊论文，先跑）
# 每条查询用多关键词组合，CrossRef 会做 OR 全文检索，覆盖更多相关论文
# ──────────────────────────────────────────
# 查最近90天内的论文
CROSSREF_START_DATE = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

CROSSREF_TASKS = [
    # ── 塑料热解（废塑料/聚烯烃/PP/PE/PET/PVC/PS/油品/氢气/CNTs）──
    # query.title 按标题关键词检索，relevance 排序，更精准
    ("pyrolysis plastic polyolefin polyethylene polypropylene",    "塑料热解",   10),
    ("pyrolysis PET PVC polystyrene thermal cracking plastic",    "塑料热解",   10),
    ("plastic pyrolysis hydrogen carbon nanotube CNT upcycling",  "塑料热解",   8),
    ("plastic pyrolysis microwave plasma catalytic",              "塑料热解",   8),

    # ── 生物质热解（生物炭/生物油/木质素/纤维素/秸秆）──
    ("pyrolysis biomass biochar bio-oil lignin cellulose",        "生物质热解", 10),
    ("biomass pyrolysis fast catalytic co-pyrolysis bio-oil",    "生物质热解", 8),

    # ── 催化热解（机理/选择性/共热解/原位/异位/气化）──
    ("catalytic pyrolysis mechanism selectivity in-situ",         "催化热解",   10),
    ("co-pyrolysis plastic biomass synergy product",              "催化热解",   8),
    ("pyrolysis gasification thermal cracking coupling",          "催化热解",   8),

    # ── 创新催化剂（沸石/单原子/ZSM/MCM/SAPO/新型）──
    ("pyrolysis zeolite catalyst cracking ZSM SAPO MCM",         "创新催化剂", 10),
    ("pyrolysis single-atom catalyst hydrogen carbon",            "创新催化剂", 8),
    ("polyolefin pyrolysis catalyst hydrogen high-purity",        "创新催化剂", 8),

    # ── 科研圈（综述/进展/高影响论文）──
    ("pyrolysis plastic biomass review progress",                 "科研圈",     10),
    ("waste plastic chemical recycling hydrogen review",          "科研圈",     8),
]

# ──────────────────────────────────────────
# arXiv 查询配置（预印本，补期刊不足时使用）
# ──────────────────────────────────────────
ARXIV_TASKS = [
    # (arXiv 搜索词,                                                  目标分类,    取条数)
    ("ti:pyrolysis AND (ti:plastic OR ti:polyolefin OR ti:polyethylene OR ti:polypropylene)",
                                                                      "塑料热解",  6),
    ("ti:pyrolysis AND (ti:hydrogen OR ti:\"carbon nanotube\" OR ti:CNT)",
                                                                      "塑料热解",  4),
    ("ti:pyrolysis AND (ti:biomass OR ti:biochar OR ti:lignin OR ti:cellulose)",
                                                                      "生物质热解",6),
    ("ti:pyrolysis AND (ti:catalytic OR ti:\"in-situ\" OR ti:\"co-pyrolysis\")",
                                                                      "催化热解",  6),
    ("ti:pyrolysis AND (ti:zeolite OR ti:\"single-atom\" OR ti:ZSM OR ti:catalyst)",
                                                                      "创新催化剂",6),
    ("ti:pyrolysis AND ti:review",                                    "科研圈",    4),
]

# ──────────────────────────────────────────
# 搜狗微信搜索词配置（中文公众号，后跑补足）
# ──────────────────────────────────────────
WEIXIN_TASKS = [
    # (关键词,                        目标分类,      最多取条数)
    ("废塑料 热解 产业化 化学回收",   "塑料热解",    6),
    ("塑料热解 氢气 碳纳米管",        "塑料热解",    6),
    ("聚乙烯 聚丙烯 热解 催化",       "塑料热解",    6),
    ("生物质热解 生物炭 生物油",      "生物质热解",  6),
    ("秸秆 木质素 热解 催化",         "生物质热解",  5),
    ("催化热解 原位 异位 机理",       "催化热解",    6),
    ("共热解 协同效应 反应器",        "催化热解",    5),
    ("沸石催化剂 ZSM 热解 选择性",   "创新催化剂",  6),
    ("单原子催化剂 热解 氢气",        "创新催化剂",  6),
    ("热解 综述 进展 最新",           "科研圈",      6),
    ("催化热解 课题组 论文",           "科研圈",      6),
    # ── 科研技巧（覆盖分子筛百科/研之成理/DFT茶水间/MS建模/科技学术写作等公众号）──
    ("科研技巧 论文写作 学术写作 投稿",    "科研技巧",    6),
    ("DFT 计算化学 第一性原理 催化",       "科研技巧",    6),
    ("Materials Studio 建模 分子筛 沸石",  "科研技巧",    6),
    ("催化剂表征 实验技巧 科研方法",       "科研技巧",    6),
    ("研究生 科研经验 文献管理 论文",      "科研技巧",    6),
]

# ──────────────────────────────────────────
# HTTP 通用配置
# ──────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
API_HEADERS = {
    "User-Agent": "pyrolysis-daily/3.0 (academic research tool; github-actions)",
}


def http_get(url: str, params: dict = None, headers: dict = None,
             timeout: int = 15) -> requests.Response | None:
    h = headers or BROWSER_HEADERS
    try:
        r = requests.get(url, params=params, headers=h, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning(f"  请求失败 {url[:60]}: {e}")
        return None


# ──────────────────────────────────────────
# 内容过滤
# ──────────────────────────────────────────

def is_clean(title: str, body: str = "", skip_core_kw: bool = False) -> bool:
    """黑名单 + 核心词双重过滤；skip_core_kw=True 时跳过核心词检查（用于科研技巧分类）"""
    combined = title + " " + body
    if BLACKLIST_RE.search(combined):
        log.debug(f"  [黑名单] 丢弃: {title[:50]}")
        return False
    if not skip_core_kw and not CORE_KW_RE.search(title):
        log.debug(f"  [核心词] 丢弃: {title[:50]}")
        return False
    return True


def extract_domain(url: str) -> str:
    try:
        return url.split("/")[2].replace("www.", "")
    except Exception:
        return "未知来源"


def extract_tags(title: str, category: str) -> list:
    keyword_map = {
        "废塑料": "废塑料", "聚乙烯": "PE", "聚丙烯": "PP",
        "polyethylene": "PE", "polypropylene": "PP", "polystyrene": "PS",
        "生物质": "生物质", "biomass": "生物质",
        "生物油": "生物油", "bio-oil": "生物油",
        "生物炭": "生物炭", "biochar": "生物炭",
        "秸秆": "秸秆", "lignin": "木质素", "cellulose": "纤维素",
        "沸石": "沸石", "zeolite": "Zeolite", "ZSM": "ZSM-5",
        "共热解": "共热解", "co-pyrolysis": "共热解",
        "反应器": "反应器", "机理": "反应机理", "mechanism": "反应机理",
        "产业化": "产业化",
        "JACS": "JACS", "Nature": "Nature", "Science": "Science",
    }
    tags = [category]
    for kw, tag in keyword_map.items():
        if kw.lower() in title.lower() and tag not in tags:
            tags.append(tag)
        if len(tags) >= 4:
            break
    return tags[:4]


# ──────────────────────────────────────────
# 数据源 A：搜狗微信公众号（中文行业/科研资讯）
# ──────────────────────────────────────────

def fetch_weixin(keyword: str, max_results: int = 8) -> list[dict]:
    """搜狗微信搜索，返回公众号文章"""
    r = http_get(
        "https://weixin.sogou.com/weixin",
        params={"type": "2", "query": keyword, "ie": "utf8"},
    )
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
        href  = a_tag.get("href", "").strip()
        if not href or not title:
            continue
        # 补全搜狗站内重定向路径
        if href.startswith("/link?"):
            href = "https://weixin.sogou.com" + href
        items.append({
            "title":      title,
            "body":       body,
            "url":        href,
            "source_tag": "【微信公众号】",
            "source":     "weixin.qq.com",
        })
    log.info(f"  搜狗微信「{keyword}」→ 原始 {len(items)} 条")
    return items


# ──────────────────────────────────────────
# 数据源 B：CrossRef API（正式期刊论文）
# ──────────────────────────────────────────

def fetch_crossref(query: str, max_results: int = 5) -> list[dict]:
    """CrossRef REST API，检索近期正式发表的期刊论文"""
    r = http_get(
        "https://api.crossref.org/works",
        params={
            "query.title": query,              # 标题字段精确检索，比 query 全文更精准
            "filter":  f"from-pub-date:{CROSSREF_START_DATE},type:journal-article",
            "rows":    max_results * 3,        # 多取以补过滤损耗
            "select":  "title,abstract,URL,published,container-title,author",
            "sort":    "relevance",            # 按相关性排序（原 published 会导致无关文章置顶）
            "order":   "desc",
        },
        headers={**API_HEADERS, "Accept": "application/json"},
    )
    if not r:
        return []

    items = []
    try:
        data = r.json()
        for w in data["message"]["items"]:
            title_list = w.get("title", [])
            if not title_list:
                continue
            title   = title_list[0].strip()
            journal_raw = (w.get("container-title") or [""])[0]
            # CrossRef 偶尔返回 HTML 实体（如 &amp;），统一解码后再做白名单匹配
            journal = html.unescape(journal_raw)
            url     = w.get("URL", "").strip()
            # 期刊白名单过滤：只收化工/能源/环境/材料类期刊
            if journal and not JOURNAL_WHITELIST_RE.search(journal):
                log.debug(f"  [期刊白名单] 丢弃 {journal}: {title[:40]}")
                continue
            # abstract 可能是 jats XML 格式，简单清洗
            abstract_raw = w.get("abstract", "")
            body = re.sub(r"<[^>]+>", "", abstract_raw).strip()[:200]
            if not body:
                body = f"发表于 {journal}，点击原文查看摘要。" if journal else "点击原文查看详情。"
            # 作者
            authors = w.get("author", [])
            author_str = ""
            if authors:
                first = authors[0]
                author_str = f"{first.get('family','')} {first.get('given','')}".strip()
                if len(authors) > 1:
                    author_str += " 等"
            items.append({
                "title":      title,
                "body":       body,
                "url":        url,
                "source_tag": f"【{journal[:20]}】" if journal else "【学术期刊】",
                "source":     extract_domain(url) if url else "doi.org",
                "author":     author_str,
            })
    except Exception as e:
        log.warning(f"  CrossRef 解析失败: {e}")
    log.info(f"  CrossRef「{query[:35]}」→ 原始 {len(items)} 条（期刊白名单过滤后）")
    return items


# ──────────────────────────────────────────
# 数据源 C：arXiv API（预印本）
# ──────────────────────────────────────────

def fetch_arxiv(query: str, max_results: int = 3) -> list[dict]:
    """arXiv Atom API，检索最新预印本"""
    r = http_get(
        "http://export.arxiv.org/api/query",
        params={
            "search_query": query,
            "start":        0,
            "max_results":  max_results * 2,
            "sortBy":       "submittedDate",
            "sortOrder":    "descending",
        },
        headers=API_HEADERS,
    )
    if not r:
        return []

    items = []
    try:
        root = ET.fromstring(r.text)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title   = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            summary = entry.find("atom:summary", ns).text.strip()[:200]
            url     = entry.find("atom:id", ns).text.strip()
            pub     = entry.find("atom:published", ns).text[:10]
            items.append({
                "title":      title,
                "body":       f"[arXiv {pub}] {summary}",
                "url":        url,
                "source_tag": "【arXiv预印本】",
                "source":     "arxiv.org",
            })
    except Exception as e:
        log.warning(f"  arXiv 解析失败: {e}")
    log.info(f"  arXiv「{query[:35]}」→ 原始 {len(items)} 条")
    return items


# ──────────────────────────────────────────
# 主采集逻辑
# ──────────────────────────────────────────

def collect_news() -> list[dict]:
    category_pool: dict[str, list] = {k: [] for k in CATEGORY_QUOTA}
    seen_titles: set[str] = set()   # 用标题去重（跨平台 URL 可能不同）
    seen_urls:   set[str] = set()

    def try_add(item: dict, category: str):
        title = item["title"].strip()
        body  = item.get("body", "").strip()
        url   = item.get("url", "").strip()
        tag   = item.get("source_tag", "")

        if not title or not url:
            return
        # 标题去重（忽略大小写/空格）
        title_key = re.sub(r"\s+", "", title).lower()
        if title_key in seen_titles or url in seen_urls:
            return
        # 内容过滤（科研技巧分类跳过核心词检查，允许非热解类文章通过）
        if not is_clean(title, body, skip_core_kw=(category == "科研技巧")):
            return

        seen_titles.add(title_key)
        seen_urls.add(url)

        display_title = f"{tag} {title}" if tag else title
        category_pool[category].append({
            "category": category,
            "title":    display_title,
            "summary":  body if body else "点击原文查看详情。",
            "source":   item.get("source", extract_domain(url)),
            "url":      url,
            "tags":     extract_tags(title, category),
        })

    # ── 阶段A: CrossRef 学术期刊（先跑，按 JOURNAL_QUOTA 严格上限）──
    log.info("=== 阶段A：CrossRef 学术期刊 ===")
    journal_counts: dict[str, int] = {k: 0 for k in CATEGORY_QUOTA}
    for query, category, num in CROSSREF_TASKS:
        jq = JOURNAL_QUOTA.get(category, 2)
        if journal_counts[category] >= jq:
            log.info(f"  「{category}」期刊已达上限{jq}，跳过")
            continue
        results = fetch_crossref(query, max_results=num)
        for item in results:
            if journal_counts[category] < jq:
                prev = len(category_pool[category])
                try_add(item, category)
                if len(category_pool[category]) > prev:
                    journal_counts[category] += 1
        log.info(f"  池「{category}」: {len(category_pool[category])} 条（期刊 {journal_counts[category]}/{jq}）")
        time.sleep(random.uniform(1.0, 2.5))

    # ── 阶段B: arXiv 预印本（期刊不足时补，同样受 JOURNAL_QUOTA 约束）──
    log.info("=== 阶段B：arXiv 预印本 ===")
    for query, category, num in ARXIV_TASKS:
        jq = JOURNAL_QUOTA.get(category, 2)
        if journal_counts[category] >= jq:
            continue
        results = fetch_arxiv(query, max_results=num)
        for item in results:
            if journal_counts[category] < jq:
                prev = len(category_pool[category])
                try_add(item, category)
                if len(category_pool[category]) > prev:
                    journal_counts[category] += 1
        log.info(f"  池「{category}」: {len(category_pool[category])} 条（期刊 {journal_counts[category]}/{jq}）")
        time.sleep(random.uniform(0.5, 1.5))

    log.info("期刊/预印本阶段完成：" + "  ".join(
        f"{c} 期刊{journal_counts[c]}条" for c in CATEGORY_QUOTA
    ))

    # ── 阶段C: 搜狗微信公众号（补足总配额，不受期刊限制）──
    log.info("=== 阶段C：搜狗微信公众号（补足剩余配额）===")
    for keyword, category, num in WEIXIN_TASKS:
        quota = CATEGORY_QUOTA.get(category, 4)
        if len(category_pool[category]) >= quota:
            log.info(f"  「{category}」已满 {quota} 条，跳过")
            continue
        results = fetch_weixin(keyword, max_results=num)
        for item in results:
            try_add(item, category)
        log.info(f"  池「{category}」: {len(category_pool[category])} / {quota} 条")
        time.sleep(random.uniform(2.0, 4.0))

    # ── 按配额拼装 ──
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
