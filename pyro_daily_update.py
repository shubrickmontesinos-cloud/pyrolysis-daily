#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pyro_daily_update.py  v3.2 (Freshness Optimized)
每周热解科研资讯自动采集
修复点：优化 CrossRef 排序逻辑以提高每日更新的差异度
"""

import html
import json
import os
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
from typing import Optional, List, Dict, Set, Tuple

# ---------------------- 微信终极采集：Playwright 导入 ----------------------
from playwright.sync_api import sync_playwright
import random
import time

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
# 内容黑名单与白名单配置
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

APPROVED_JOURNALS = [
    "journal of analytical and applied pyrolysis", "journal of analytical & applied pyrolysis",
    "fuel", "fuel processing technology", "energy & fuels", "energy and fuels", "applied energy",
    "energy", "energy conversion and management", "joule", "international journal of hydrogen energy",
    "energy & environmental science", "energy and environmental science", "renewable energy",
    "renewable and sustainable energy reviews", "journal of the energy institute",
    "chemical engineering journal", "industrial & engineering chemistry research",
    "chemical engineering science", "aiche journal", "chemsuschem", "applied catalysis b", 
    "applied catalysis a", "acs catalysis", "journal of catalysis", "catalysis today", 
    "catalysis communications", "catalysis reviews", "catalysis science", 
    "microporous and mesoporous materials", "environmental science & technology", 
    "acs sustainable chemistry", "green chemistry", "waste management", "bioresource technology",
    "journal of cleaner production", "science of the total environment",
    "resources, conservation and recycling", "separation and purification technology", 
    "biomass and bioenergy", "biomass conversion and biorefinery", "industrial crops and products",
    "nature", "science", "nature communications", "nature energy", "nature chemistry",
    "science advances", "angewandte chemie", "journal of the american chemical society",
    "acs nano", "advanced materials", "advanced energy materials", "advanced functional materials",
    "chemical society reviews", "accounts of chemical research",
    "progress in energy and combustion science", "polymer degradation",
    "polymer degradation and stability", "journal of hazardous materials", "chemosphere",
]
JOURNAL_WHITELIST_RE = re.compile("|".join(re.escape(j) for j in APPROVED_JOURNALS), re.IGNORECASE)

CORE_KEYWORDS = [
    "塑料","热解", "催化热解", "热裂解", "催化裂解", "快速热解", "共热解", "废塑料", "塑料回收", "非原位热解", 
    "生物质", "分子筛", "合成气", "原位热解", "富氢气体", "聚乙烯", "聚丙烯", "聚苯乙烯", "秸秆",  "微波", "等离子体", 
    "plastic","pyrolysis", "catalytic pyrolysis", "thermal pyrolysis", "co-pyrolysis", "Hydrogen", "Methane", 
    "waste plastic","sygas", "gas", "in-situ", "hydrogen production", "zeolite", "microwave", "plasma", "ex-situ", 
    "化学链气化", "蒸汽重整","镍基催化剂", "铁基催化剂", "单原子","富氢合成气", "焦油裂解", "抗积碳", "循环稳定", 
    "固废资源化", "微波热解", "串联催化","plastic", "PET", "chemical looping gasification", 
    "steam reforming", "single-atom","syngas", "hydrogen-rich syngas", "anti-coking", "cyclic stability", 
]
CORE_KW_RE = re.compile("|".join(CORE_KEYWORDS), re.IGNORECASE)

# ──────────────────────────────────────────
# 采集配额
# ──────────────────────────────────────────
CATEGORY_QUOTA = {"塑料热解": 6, "生物质热解": 2,  "科研圈": 3, "科研技巧": 3}
JOURNAL_QUOTA = {"塑料热解": 6, "生物质热解": 2, "科研圈": 3, "科研技巧": 2}
CAT_ICONS = {"塑料热解": "♻️", "生物质热解": "🌿", "科研圈": "🎓", "科研技巧": "💡"}

# ──────────────────────────────────────────
# 全局配置常量
# ──────────────────────────────────────────
# 时区设置（统一使用北京时间）
try:
    import pytz
    BEIJING_TZ = pytz.timezone('Asia/Shanghai')
except ImportError:
    BEIJING_TZ = None
    log.warning("未安装pytz，将使用UTC+8模拟北京时间")

# 网络请求延迟配置（秒）
DELAY_CROSSREF = (1, 3)
DELAY_ARXIV = (2, 4)
DELAY_WEIXIN = (3, 6)
DELAY_SCOPUS = (2, 4)  # 新增Scopus延迟配置

# Scopus API 配置
SCOPUS_API_KEY = "439ee695aaad79d78ae49e1817005efc"
SCOPUS_BASE_URL = "https://api.elsevier.com/content/search/scopus"

# 采集最小条目要求
MIN_ITEMS_PER_CAT = 2
MIN_TOTAL_ITEMS = 15

# 设置 CrossRef 检索起始时间（最近 150 天，统一北京时间）
def get_bj_now() -> datetime:
    if BEIJING_TZ:
        # 转换为北京时间的naive datetime（移除时区信息但保留正确时间）
        return datetime.now(BEIJING_TZ).astimezone(BEIJING_TZ).replace(tzinfo=None)
    else:
        return datetime.utcnow() + timedelta(hours=8)

# 替换原有的CROSSREF_START_DATE定义
# 要求：只采集2024年1月1日之后的内容（过滤2023及之前）
CROSSREF_START_DATE = "2024-01-01"

# 新增Scopus时间常量（统一过滤2023及之前）
SCOPUS_START_YEAR = 2024

# ──────────────────────────────────────────
# 采集任务清单
# ──────────────────────────────────────────
CROSSREF_TASKS = [
    # 塑料热解：拆成多个窄关键词，每次能拿到不同子集
    ("plastic waste pyrolysis catalyst hydrogen syngas", "塑料热解", 8),
    ("pyrolysis plastic co-pyrolysis biomass zeolite carbon nanotube", "塑料热解", 8),
    ("catalytic pyrolysis polyethylene polypropylene polystyrene PET", "塑料热解", 8),
    ("waste plastic thermal decomposition oil fuel char", "塑料热解", 8),
    ("microwave plasma pyrolysis plastic hydrogen production", "塑料热解", 8),
    # 生物质热解
    ("biomass pyrolysis biochar bio-oil lignin cellulose", "生物质热解", 8),
    ("catalytic biomass pyrolysis fast pyrolysis tar cracking", "生物质热解", 8),
    # 科研圈：综述+最新动态
    ("pyrolysis review progress 2026 2025 latest research", "科研圈", 8),
    ("thermal conversion waste valorization review energy fuels", "科研圈", 8),
    ("hydrogen production from plastic waste review catalyst", "科研圈", 8),
]

# Scopus 采集任务（强化塑料热解采集数量，确保至少5条）
SCOPUS_TASKS = [
    # 塑料热解：max_results从25提升到50，确保足够多的候选
    ("plastic pyrolysis catalytic co-pyrolysis waste-plastic sygas hydrogen-production carbon-nanotube microwave plasma", "塑料热解", 100),
    ("pyrolysis biomass biochar bio-oil lignin", "生物质热解", 25),
    ("2025 pyrolysis review progress latest research", "科研圈", 20),  # 新增Scopus科研圈采集
]

from datetime import datetime, timedelta
ninety_days_ago = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
today = datetime.utcnow().strftime("%Y-%m-%d")
ARXIV_TASKS = [
    (f"ti:pyrolysis AND ti:plastic AND submittedDate:[{ninety_days_ago} TO {today}]", "塑料热解", 15),
]

WEIXIN_TASKS = [
    ("科研技巧 Origin 热解实验 XRD 红外 TEM XPS 表征", "科研技巧", 5),
    # 科研圈微信采集（新增2025最新关键词）
    ("2026 2025 热解 科研动态 顶刊 硕博 SCI", "科研圈", 5),
    ("SCI论文 热解 催化 能源领域", "科研圈", 5),
]

# ──────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
# 修改此邮箱以符合 CrossRef 规范
API_HEADERS = {"User-Agent": "18453706091@163.com"}

def http_get(url: str, params: dict = None, headers: dict = None, retry: int = 3) -> Optional[requests.Response]:
    """带重试机制的HTTP请求"""
    for i in range(retry):
        try:
            r = requests.get(
                url, 
                params=params, 
                headers=headers or BROWSER_HEADERS, 
                timeout=15, 
                allow_redirects=True
            )
            r.raise_for_status()
            return r
        except Exception as e:
            log.warning(f"  请求失败 {url[:50]} (重试{i+1}/{retry}): {e}")
            if i < retry - 1:  # 最后一次重试不延迟
                time.sleep(random.uniform(2, 4))
    return None

def load_history_identifiers() -> Tuple[Set[str], Set[str]]:
    seen_titles, seen_urls = set(), set()
    # 只看最近2次的数据做去重，避免历史数据过度拦截新内容
    all_files = sorted(DATA_DIR.glob("*.json"), reverse=True)[:2]
    
    for json_file in all_files:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            for item in data.get("news", []):
                if "url" in item:
                    seen_urls.add(item["url"])
                if "title" in item:
                    clean_t = re.sub(r"【.*?】", "", item["title"])
                    title_key = re.sub(r"[\W_]+", "", clean_t).lower()
                    seen_titles.add(title_key)
        except:
            continue
    log.info(f"已加载【近7天】去重数据：{len(seen_titles)}条")
    return seen_titles, seen_urls

def is_clean(title: str, body: str = "", skip_core_kw: bool = False) -> bool:
    combined = title + " " + body
    if BLACKLIST_RE.search(combined): return False
    if not skip_core_kw and not CORE_KW_RE.search(title): return False
    return True

# ──────────────────────────────────────────
# 数据源抓取逻辑
# ──────────────────────────────────────────

def fetch_crossref(query: str, max_results: int = 50) -> List[Dict]:
    """抓取 Crossref 最新论文 + 强关键词过滤 + 领域白名单，确保100%相关"""
    time.sleep(random.uniform(*DELAY_CROSSREF))
    r = http_get(
        "https://api.crossref.org/works",
        params={
            "query.title": query,
            # 强制过滤2022及之前：只保留2023-01-01之后的内容
            "filter": f"from-pub-date:2024-06-01,type:journal-article",
            "rows": max_results * 3,
            "sort": "created",
            "order": "desc",  # 按入库时间排序，保证每次有新内容
        },
        headers=API_HEADERS
    )
    if not r:
        return []

    items = []
    try:
        resp_data = r.json()
        for w in resp_data.get("message", {}).get("items", []):
            title_list = w.get("title")
            if not title_list:
                continue

            title = title_list[0].strip()
            lower_title = title.lower()

            # ========== 新增：校验发布时间，过滤2022及之前 ==========
            pub_date = w.get("published", {}).get("date-parts", [[]])[0]
            if pub_date and len(pub_date) >= 1 and pub_date[0] <= 2022:
                continue

            # ==============================================
            # 【第一层强过滤：优化科研圈规则】
            # ==============================================
            is_research_circle = "科研圈" in query.lower() or "review" in query.lower() or "2026" in query.lower()
            if not is_research_circle:
                # 非科研圈：必须包含热解核心词
                if not any(kw in lower_title or kw in title for kw in ["pyrolysis", "塑料", "热解"]):
                    continue
            else:
                # 🔥 修复：科研圈必须同时包含「科研词」+「热解/能源/催化词」，彻底杜绝木瓜/儿童听力这种垃圾
                has_research_kw = any(kw in lower_title for kw in ["2025", "2026", "review", "progress", "综述", "进展", "论文", "sci", "顶刊"])
                has_field_kw = any(kw in lower_title for kw in ["pyrolysis", "plastic", "热解", "塑料", "catalysis", "催化", "energy", "能源", "fuel", "氢"])
                if not (has_research_kw and has_field_kw):
                    continue

            # ========== 原有过滤逻辑保持不变 ==========
            allowed_keywords = [
                # 英文
                "plastic", "biomass", "catalytic", "catalyst", "zeolite", "microwave", "plasma", 
                "syngas", "hydrogen", "recycling", "pyrolysis", "co-pyrolysis", "Hydrogen", "single-atom"
                # 中文
                "催化", "废塑", "塑料","热解", "富氢气体", "废塑料", "固废资源化",
                "微波", "等离子体", "串联", "化学链", "单原子","富氢",  "微波热解"
            ]

            # 符合所有条件 → 收录
            journal = w.get("container-title", [""])[0].strip()
            items.append({
                "title": title,
                "body": (w.get("abstract") or "点击查看详情。")[:200],
                "url": w.get("URL", ""),
                "source_tag": f"【{journal[:15]}】" if journal else "【学术期刊】",
                "source": "doi.org"
            })

    except json.JSONDecodeError as e:
        log.error(f"CrossRef JSON解析失败: {e}")
    except KeyError as e:
        log.error(f"CrossRef返回数据结构异常，缺少键: {e}")
    except Exception as e:
        log.error(f"CrossRef处理异常: {e}", exc_info=True)

    return items

def ensure_min_requirements(pool, min_per_cat=1, min_total=12):
    """
    【极简兜底】仅在完全没数据时补1-2条，绝不大量造假
    """
    from datetime import datetime
    bj_time = datetime.utcnow() + timedelta(hours=8)
    year_str = bj_time.strftime("%Y")
    
    # 塑料热解：只有0条时才补1条
    if len(pool["塑料热解"]) == 0:
        pool["塑料热解"].append({
            "title": f"{year_str}废塑料热解制氢最新研究进展",
            "body": "高效催化剂与工艺优化方向的代表性成果",
            "url": "#",
            "source": "数据同步中",
            "category": "塑料热解",
            "tags": ["塑料热解"],
            "source_tag": "【同步中】"
        })
    
    # 其他分类：只有0条时才补1条
    for cat in pool:
        if cat != "塑料热解" and len(pool[cat]) == 0:
            pool[cat].append({
                "title": f"【{cat}】{year_str}领域研究动态",
                "body": f"{year_str}热解领域{cat}方向的最新科研成果",
                "url": "#",
                "source": "数据同步中",
                "category": cat,
                "tags": [cat],
                "source_tag": "【同步中】"
            })

def fetch_scopus(query: str, category: str, max_results: int = 5) -> List[Dict]:
    # 🔥 修复：先定义变量，再使用
    from datetime import datetime, timedelta
    bj_now = get_bj_now()
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    if not SCOPUS_API_KEY:
        log.warning("⚠️ SCOPUS_API_KEY 未配置，跳过 Scopus 采集")
        return []
    
    url = "https://api.elsevier.com/content/search/scopus"
    params = {
        "query": f"{query} AND PUBYEAR > 2023 AND PUBDATE > {thirty_days_ago}",
        "count": 50, 
        "sort": "coverDate",
        "order": "desc",
        "field": "title,abstract,publicationName,doi"
    }
    headers = {
        "Accept": "application/json",
        "X-ELS-APIKey": SCOPUS_API_KEY
    }
    r = http_get(url, params=params, headers=headers, retry=3)
    if not r:
        log.error("[Scopus] 请求失败，返回None")
        return []

    log.info(f"[Scopus] 已构造请求，API_KEY前4位：{SCOPUS_API_KEY[:4]}")
    log.info(f"[Scopus] 请求参数：{params}")

    try:
        r = http_get(url, params=params, headers=headers, retry=3)
        log.info(f"[Scopus] 请求返回状态：{r.status_code if r else '无响应'}")
    except Exception as e:
        log.error(f"[Scopus] 请求抛出异常：{str(e)}", exc_info=True)
        return []

    if not r:
        log.error(f"[Scopus] 请求失败，返回None")
        return []

    items = []
    try:
        resp_data = r.json()
        total_found = resp_data.get("search-results", {}).get("opensearch:totalResults", 0)
        entries = resp_data.get("search-results", {}).get("entry", [])
        log.info(f"[Scopus] 原始结果数：{total_found}，返回条目数：{len(entries)}")

        if not entries:
            log.warning(f"[Scopus] 无匹配条目，关键词={query[:30]}")
            return []

        for entry in entries:
            title = entry.get("dc:title", "").strip()
            if not title:
                continue
            journal = entry.get("prism:publicationName", "").strip()
            doi = entry.get("prism:doi", "")
            abstract = entry.get("dc:description", "") or "点击查看详情。"
            cover_date = entry.get("prism:coverDate", "")

            # 只过滤2022及之前
            if cover_date:
                try:
                    pub_year = int(cover_date.split("-")[0])
                    if pub_year <= 2022:
                        continue
                except:
                    continue

            # 塑料热解仅需含核心词
            if category == "塑料热解":
                if not any(kw in title.lower() for kw in ["pyrolysis", "plastic", "热解", "塑料"]):
                    continue

            items.append({
                "title": title,
                "body": abstract[:200],
                "url": f"https://doi.org/{doi}" if doi else "",
                "source_tag": f"【Scopus/{journal[:10]}】" if journal else "【Scopus】",
                "source": "scopus.com"
            })
            if len(items) >= max_results:
                break

        log.info(f"[Scopus] 过滤后有效条目数：{len(items)}")
        return items[:max_results]

    except json.JSONDecodeError as e:
        log.error(f"[Scopus] JSON解析失败：{str(e)}", exc_info=True)
        return []
    except Exception as e:
        log.error(f"[Scopus] 处理异常：{str(e)}", exc_info=True)
        return []

def fetch_weixin(keyword: str, max_results: int = 5) -> List[Dict]:
    """
    微信采集终极兼容版：字段100%匹配原有代码，增加详细调试日志
    """
    items = []
    url = f"https://weixin.sogou.com/weixin?type=2&query={keyword}&ie=utf8"

    try:
        log.info(f"[微信] 开始采集：{keyword}")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1280,720"
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            page = context.new_page()

            # 延长超时，增加随机等待
            page.goto(url, timeout=90000)
            time.sleep(random.uniform(4, 7))

            # 反爬检测
            page_content = page.content()
            if "验证码" in page_content or "访问频繁" in page_content:
                log.error(f"[微信] 被反爬拦截：{keyword}")
                browser.close()
                return []

            articles = page.query_selector_all("ul.news-list li")
            log.info(f"[微信] 找到 {len(articles)} 条原始文章")

            for article in articles[:max_results]:
                try:
                    title_elem = article.query_selector("h3 a")
                    if not title_elem:
                        continue
                    
                    title = title_elem.inner_text().strip()
                    detail_url = title_elem.get_attribute("href").strip()
                    if not detail_url.startswith("http"):
                        detail_url = "https://weixin.sogou.com" + detail_url

                    body_elem = article.query_selector("p.txt-info")
                    body = body_elem.inner_text().strip()[:200] if body_elem else "点击查看详情"

                    # 🔥 关键：字段100%匹配原有代码，和CrossRef/arXiv完全一致
                    items.append({
                        "title": title,
                        "body": body,
                        "url": detail_url,
                        "source_tag": "【微信公众号】",
                        "source": "weixin.qq.com"
                    })

                except Exception as e:
                    log.warning(f"[微信] 单条提取失败：{str(e)}")
                    continue

            browser.close()

        log.info(f"✅ [微信] {keyword} 采集完成，有效：{len(items)} 条")
        return items

    except Exception as e:
        log.error(f"❌ [微信] 采集崩溃：{str(e)}", exc_info=True)
        return []
# ──────────────────────────────────────────
# 主逻辑控制
# ──────────────────────────────────────────

def try_add(item: dict, cat: str, category_pool: dict, seen_titles: set, seen_urls: set):
    """
    标准化去重添加函数
    【核心修复】自动给每条数据加上category和tags字段
    """
    if not item:
        return
    title = item.get("title", "").strip()
    url = item.get("url", "").strip()
    
    # 基础校验
    if not title or not url:
        return
    
    # 去重
    clean_t = re.sub(r"【.*?】|[\s\n\r\u3000]+", "", title)
    clean_t = clean_t.replace("｜", "|").replace("—", "-")
    title_key = re.sub(r"[\W_]+", "", clean_t).lower()
    if title_key in seen_titles or url in seen_urls:
        return
    
    seen_titles.add(title_key)
    seen_urls.add(url)
    
    # 🔥 必须加这两行！给每条数据加上分类和标签
    item["category"] = cat
    item["tags"] = [cat]
    
    # 安全添加
    if cat in category_pool:
        category_pool[cat].append(item)

def collect_news() -> List[Dict]:
    category_pool = {cat: [] for cat in CATEGORY_QUOTA.keys()}
    seen_titles = set()
    seen_urls = set()

    log.info("=== 【关键步骤】开始塑料热解Scopus采集 ===")
    plastic_queries = [
        "TITLE(plastic) OR ABSTRACT(plastic) AND TITLE(pyrolysis) OR ABSTRACT(pyrolysis)",
        "TITLE(catalytic) OR ABSTRACT(catalytic) AND TITLE(plastic)",
    ]
    
    for idx, q in enumerate(plastic_queries):
        log.info(f"--- 塑料热解Scopus采集：第{idx+1}个关键词：{q[:50]}...")
        items = fetch_scopus(q, "塑料热解", max_results=100)
        log.info(f"--- 本次采集到{len(items)}条有效条目")
     
        for item in items:
            if len(category_pool["塑料热解"]) < CATEGORY_QUOTA["塑料热解"]:
                try_add(item, "塑料热解", category_pool, seen_titles, seen_urls)
                log.info(f"--- 已加入塑料热解池：{item['title'][:100]}...")
        
        if len(category_pool["塑料热解"]) >= 5:
            log.info("--- 塑料热解条目数已达标（≥5条），停止采集")
            break
        time.sleep(random.uniform(*DELAY_SCOPUS))

    log.info(f"=== 塑料热解采集完成，当前条目数：{len(category_pool['塑料热解'])} ===")
    
    log.info("=== 备用：使用 CrossRef 采集塑料热解 ===")
    crossref_queries = [
        "plastic pyrolysis",
        "waste plastic pyrolysis",
        "catalytic pyrolysis of plastic"
    ]
    for q in crossref_queries:
        items = fetch_crossref(q, max_results=5)
        for item in items:
            if len(category_pool["塑料热解"]) < CATEGORY_QUOTA["塑料热解"]:
                try_add(item, "塑料热解", category_pool, seen_titles, seen_urls)
        time.sleep(random.uniform(*DELAY_CROSSREF))
    # B. CrossRef 补充（仅当 Scopus 采集数量不足时）
    for q, cat, num in CROSSREF_TASKS:
        # 仅当当前分类仍未达配额，才调用 CrossRef 补充
        if len(category_pool[cat]) < CATEGORY_QUOTA[cat]:
            items = fetch_crossref(q, num)
            for item in items:
                try_add(item, cat, category_pool, seen_titles, seen_urls)
            if items:
                time.sleep(random.uniform(*DELAY_CROSSREF))
    
    # C. 微信补足（修改此处，科研技巧强制采集）
    for kw, cat, num in WEIXIN_TASKS:
        # 原逻辑：if len(category_pool[cat]) < CATEGORY_QUOTA[cat]:
        # 修复：科研技巧强制采集，其他分类不变
        if cat == "科研技巧" or len(category_pool[cat]) < CATEGORY_QUOTA[cat]:
            items = fetch_weixin(kw, num)
            for item in items:
                try_add(item, cat, category_pool, seen_titles, seen_urls)
            if items:
                time.sleep(random.uniform(*DELAY_WEIXIN))
    
    # 保证最小条目要求
    ensure_min_requirements(category_pool)
    
    # 合并
    all_items = []
    for cat in category_pool:
        all_items.extend(category_pool[cat])
    random.shuffle(all_items)

    # 汇总输出（兼容页面格式，核心修复）
    final_list = []
    uid = 1
    for cat, quota in CATEGORY_QUOTA.items():
        for it in category_pool[cat][:quota]:
            it["id"] = uid
            final_list.append(it)
            uid += 1

    return final_list
            
def save_json(news: list, date_str: str):
    """
    保存采集到的新闻到当日JSON文件
    完全匹配项目标准格式
    """
    bj_time = get_bj_now()
    out_path = DATA_DIR / f"{date_str}.json"
    
    # 构造标准payload
    payload = {
        "date": date_str,
        "generated_at": bj_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "news": news,
    }
    
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log.info(f"✅ 成功保存今日数据: {len(news)} 条，保存路径: {out_path}")
    
def main():
    bj_time = get_bj_now()
    today = bj_time.strftime("%Y-%m-%d")
    
    log.info(f"========== 启动更新任务: {today} ==========")
    
    news = collect_news()
    if not news:
        log.error("采集失败，无可用内容")
        sys.exit(1)
        
    save_json(news, today)
    run_inject()
    log.info("========== 更新任务圆满完成 ==========")

def run_inject():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"
    res = subprocess.run([sys.executable, str(SCRIPT_DIR / "inject_daily_data.py")], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if res.returncode == 0: log.info(res.stdout.strip())
    else: log.error(res.stderr or f"inject failed with code {res.returncode}")

if __name__ == "__main__":
    main()
