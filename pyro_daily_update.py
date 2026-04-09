#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pyro_daily_update.py  v3.2 (Freshness Optimized)
每日热解科研资讯自动采集
修复点：优化 CrossRef 排序逻辑以提高每日更新的差异度
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
from typing import Optional, List, Dict, Set, Tuple

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
    "废轮胎", "废橡胶", "生物质", "生物炭", "生物油", "焦油", "焦炭", "沸石", "分子筛", "合成气", "原位热解", 
    "聚乙烯", "聚丙烯", "聚苯乙烯", "秸秆", "木质素", "纤维素", "高纯氢", "碳纳米管", "微波", "等离子体", "串联催化", 
    "plastic","pyrolysis", "catalytic pyrolysis", "thermal pyrolysis", "co-pyrolysis", "Hydrogen", "Methane", 
    "waste plastic", "polyolefin", "polyethylene", "polypropylene", "polystyrene","sygas", "gas", "in-situ", 
    "biochar", "bio-oil", "hydrogen production", "carbon nanotube", "zeolite", "microwave", "plasma", "ex-situ", "series connection", 
]
CORE_KW_RE = re.compile("|".join(CORE_KEYWORDS), re.IGNORECASE)

# ──────────────────────────────────────────
# 采集配额
# ──────────────────────────────────────────
CATEGORY_QUOTA = {"塑料热解": 5, "生物质热解": 3, "催化热解": 3, "创新催化剂": 3, "科研圈": 3, "科研技巧": 5}
JOURNAL_QUOTA = {"塑料热解": 5, "生物质热解": 3, "催化热解": 3, "创新催化剂": 3, "科研圈": 2, "科研技巧": 0}
CAT_ICONS = {"塑料热解": "♻️", "生物质热解": "🌿", "催化热解": "⚗️", "创新催化剂": "✨", "科研圈": "🎓", "科研技巧": "💡"}

# 设置 CrossRef 检索起始时间（最近 120 天）
CROSSREF_START_DATE = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")

# ──────────────────────────────────────────
# 采集任务清单
# ──────────────────────────────────────────
CROSSREF_TASKS = [
    ("plastic pyrolysis catalytic pyrolysis thermal pyrolysis co-pyrolysis waste-plastic polyolefin polyethylene polypropylene sygas hydrogen-production carbon-nanotube zeolite microwave plasma ex-situ in-situ series connection", "塑料热解", 10),
    ("pyrolysis biomass biochar bio-oil lignin", "生物质热解", 10),
    ("catalytic pyrolysis mechanism selectivity", "催化热解", 10),
    ("pyrolysis zeolite catalyst ZSM SAPO single-atom metal oxide", "创新催化剂", 10),
    ("pyrolysis review progress recent journal", "科研圈", 10),
    # 新增科研圈抓取任务（多维度扩充）
    ("scientific research progress pyrolysis perspective outlook", "科研圈", 10),
    ("热解 综述 进展 研究前沿 科研动态 学术会议", "科研圈", 10),
]

ARXIV_TASKS = [
    ("ti:pyrolysis AND ti:plastic", "塑料热解", 10),
    ("ti:pyrolysis AND ti:catalytic", "催化热解", 10),
]

WEIXIN_TASKS = [
    ("塑料 热解 原位热解 非原位热解 串联催化 金属氧化物 产业化 化学回收 催化热解 热裂解 快速热解 共热解 废塑料 塑料回收 沸石 分子筛 合成气 聚乙烯 聚丙烯 聚苯乙烯 高纯氢 碳纳米管 微波 等离子体", "塑料热解", 8),
    ("生物质热解 生物炭 生物油 塑料 热解 催化热解 热裂解 催化裂解 快速热解 共热解 废塑料 塑料回收 废轮胎 废橡胶 生物质 生物炭 生物油 焦油 焦炭 沸石 分子筛 合成气 聚乙烯 聚丙烯 聚苯乙烯 秸秆 木质素 纤维素 高纯氢 碳纳米管 微波 等离子体", "生物质热解", 6),
    ("催化热解 机理 选择性 产率 合成气 三态产物", "催化热解", 10),
    ("科研技巧 XRD 拉曼 红外 TPR TPD origin 科研绘图 SEM 期刊分区 TEM XPS", "科研技巧", 15),
    ("Origin绘图 论文写作 数据处理 实验设计 文献管理 EndNote Zotero 投稿技巧 审稿回复 "
     "科研数据可视化 热解实验方法 催化表征 论文润色 学术写作", "科研技巧", 15),  # 关键词扩充，数量从6→15
    ("pyrolysis review progress recent journal", "科研圈", 10),
    # 新增科研圈抓取任务（多维度扩充）
    ("scientific research progress pyrolysis perspective outlook", "科研圈", 15),
    ("热解 综述 进展 研究前沿 科研动态 学术会议", "科研圈", 15),
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

def http_get(url: str, params: dict = None, headers: dict = None) -> Optional[requests.Response]:
    try:
        r = requests.get(url, params=params, headers=headers or BROWSER_HEADERS, timeout=15)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning(f"  请求失败 {url[:50]}: {e}")
        return None

def load_history_identifiers() -> Tuple[Set[str], Set[str]]:
    seen_titles, seen_urls = set(), set()
    for json_file in DATA_DIR.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            for item in data.get("news", []):
                if "url" in item: seen_urls.add(item["url"])
                if "title" in item:
                    clean_t = re.sub(r"【.*?】", "", item["title"])
                    seen_titles.add(re.sub(r"\s+", "", clean_t).lower())
        except: continue
    log.info(f"已加载历史数据：{len(seen_titles)} 条标题用于去重")
    return seen_titles, seen_urls

def is_clean(title: str, body: str = "", skip_core_kw: bool = False) -> bool:
    combined = title + " " + body
    if BLACKLIST_RE.search(combined): return False
    if not skip_core_kw and not CORE_KW_RE.search(title): return False
    return True

# ──────────────────────────────────────────
# 数据源抓取逻辑
# ──────────────────────────────────────────

def fetch_crossref(query: str, max_results: int = 5) -> List[Dict]:
    """抓取 Crossref 最新论文 + 强关键词过滤 + 领域白名单，确保100%相关"""
    r = http_get(
        "https://api.crossref.org/works",
        params={
            "query.title": query,
            "filter": f"from-pub-date:{CROSSREF_START_DATE},type:journal-article",
            "rows": max_results * 10,
            "sort": "published",
            "order": "desc",
        },
        headers=API_HEADERS
    )
    if not r:
        return []

    items = []
    try:
        for w in r.json()["message"]["items"]:
            title_list = w.get("title")
            if not title_list:
                continue

            title = title_list[0].strip()
            lower_title = title.lower()

            # ==============================================
            # 【第一层强过滤：必须包含热解核心词】
            # 新增：如果是科研圈分类，放宽核心词要求
        is_research_circle = "科研圈" in query.lower() or "review" in query.lower()
        if not is_research_circle:
            # 原有核心词校验（给其他分类保留）
            if not any(kw in lower_title or kw in title for kw in ["pyrolysis", "塑料", "热解"...]):
                continue
        else:
            # 科研圈仅需包含「综述/进展/科研」等弱相关词即可
            if not any(kw in lower_title for kw in ["review", "progress", "perspective", "outlook", "综述", "进展", "科研"]):
                continue
            # ==============================================
            if not any(kw in lower_title or kw in title for kw in ["pyrolysis", "plastic", "pyrolysis", "catalytic pyrolysis", "thermal pyrolysis", "co-pyrolysis", "Hydrogen", "Methane", "waste plastic", "polyolefin", "polyethylene", "polypropylene", "polystyrene","sygas", "gas", "in-situ", "biochar", "bio-oil", "hydrogen production", "carbon nanotube", "zeolite", "microwave", "plasma", "ex-situ", "in-situ", "series connection", "塑料", "热解", "催化热解", "热裂解", "催化裂解", "快速热解", "共热解", "废塑料", "塑料回收", "非原位热解", "废轮胎", "废橡胶", "生物质", "生物炭", "生物油", "焦油", "焦炭", "沸石", "分子筛", "合成气", "原位热解", "聚乙烯", "聚丙烯", "聚苯乙烯", "秸秆", "木质素", "纤维素", "高纯氢", "碳纳米管", "微波", "等离子体", "串联催化", ]):
                continue

            # ==============================================
            # 【第二层领域白名单：只允许你的研究领域】
            # ==============================================
            allowed_keywords = [
                # 英文
                "plastic", "polyethylene", "polypropylene", "polystyrene", "plastic waste",
                "biomass", "lignin", "cellulose", "biochar", "bio-oil",
                "catalytic", "catalyst", "zeolite",
                "energy", "fuel", "syngas", "hydrogen",
                "waste", "recycling", "circular economy", "pyrolysis", "catalytic pyrolysis", "thermal pyrolysis", "co-pyrolysis", "Hydrogen", "Methane", 
                "waste plastic", "polyolefin", "polyethylene", "polypropylene", "polystyrene","sygas", "gas", "in-situ", 
                "hydrogen production", "carbon nanotube", "zeolite", "microwave", "plasma", "ex-situ", "series connection"
                # 中文
                "催化", "能源", "废塑", "回收", "塑料","热解", "催化热解", 
                "热裂解", "催化裂解", "快速热解", "共热解", "废塑料", "塑料回收", 
                "非原位热解", "废轮胎", "废橡胶", "生物质", "生物炭", "生物油", "焦油", 
                "焦炭", "沸石", "分子筛", "合成气", "原位热解", "聚乙烯", "聚丙烯", "聚苯乙烯", 
                "秸秆", "木质素", "纤维素", "高纯氢", "碳纳米管", "微波", "等离子体", "串联催化",
            ]

            # 如果标题里没有任何白名单关键词 → 直接丢掉
            if not any(keyword in lower_title or keyword in title for keyword in allowed_keywords):
                continue

            # ==============================================
            # 【第三层：期刊白名单】
            # ==============================================
            journal = (w.get("container-title") or [""])[0]
            if journal and not JOURNAL_WHITELIST_RE.search(journal):
                continue

            # 符合所有条件 → 收录
            items.append({
                "title": title,
                "body": (w.get("abstract") or "点击查看详情。")[:200],
                "url": w.get("URL", ""),
                "source_tag": f"【{journal[:15]}】" if journal else "【学术期刊】",
                "source": "doi.org"
            })
    except Exception:
        pass

    return items

# 极简兜底：保证每个分类至少 2 条内容
def ensure_min_items(pool, min_count=2):
    default = {
        "塑料热解": [
            {"title": "塑料热解最新行业动态", "summary": "每日更新塑料热解前沿进展", "url": "#", "source": "系统"},
            {"title": "废塑料化学回收技术进展", "summary": "热解资源化利用最新研究", "url": "#", "source": "系统"}
        ],
        "生物质热解": [
            {"title": "生物质热解研究进展", "summary": "生物炭、生物油最新研究", "url": "#", "source": "系统"},
            {"title": "秸秆木质素热解利用", "summary": "农业废弃物高值化利用", "url": "#", "source": "系统"}
        ],
        "催化热解": [
            {"title": "催化热解机理研究", "summary": "催化剂与反应路径研究", "url": "#", "source": "系统"},
            {"title": "热解催化剂改性研究", "summary": "高选择性催化体系开发", "url": "#", "source": "系统"}
        ],
        "创新催化剂": [
            {"title": "新型热解催化剂开发", "summary": "高稳定、抗积碳催化剂进展", "url": "#", "source": "系统"},
            {"title": "分子筛催化热解应用", "summary": "ZSM-5、SAPO等催化体系", "url": "#", "source": "系统"}
        ],
        "科研圈": [
            {"title": "热解领域最新科研进展", "summary": "顶刊论文、综述、前沿动态", "url": "#", "source": "系统"},
            {"title": "热解国际学术动态汇总", "summary": "全球热解科研最新成果", "url": "#", "source": "系统"}
        ],
        "科研技巧": [
            {"title": "热解科研数据处理技巧", "summary": "Origin绘图、数据分析方法", "url": "#", "source": "系统"},
            {"title": "论文写作与期刊投稿指南", "summary": "科研作图、文献管理技巧", "url": "#", "source": "系统"}
        ]
    }

    for cat in pool:
        while len(pool[cat]) < min_count:
            pool[cat].append(default[cat][len(pool[cat])])
            
def fetch_weixin(keyword: str, max_results: int = 8) -> List[Dict]:
    # 新增：随机延迟+更换请求头
    time.sleep(random.uniform(3, 6))  # 随机延迟，避免高频请求
    headers = BROWSER_HEADERS.copy()
    # 新增多个User-Agent备选，随机选一个
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ]
    headers["User-Agent"] = random.choice(user_agents)
    
    # 修改请求：添加headers参数，使用新的请求头
    r = http_get("https://weixin.sogou.com/weixin", 
                 params={"type": "2", "query": keyword, "ie": "utf8"},
                 headers=headers)  # 新增headers参数
    r = http_get("https://weixin.sogou.com/weixin", params={"type": "2", "query": keyword, "ie": "utf8"})
    if not r or "antispider" in r.url:
        log.error(f"  [!] 搜狗微信反爬拦截 (关键字: {keyword})")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for li in soup.select("ul.news-list li")[:max_results]:
        a = li.select_one("h3 a")
        if not a: continue
        items.append({
            "title": a.get_text(strip=True),
            "body": li.select_one("p.txt-info").get_text(strip=True) if li.select_one("p.txt-info") else "",
            "url": "https://weixin.sogou.com" + a["href"] if a["href"].startswith("/link") else a["href"],
            "source_tag": "【微信公众号】",
            "source": "weixin.qq.com"
        })
    return items

# 新增函数：抓取知乎科研技巧内容
def fetch_zhihu(keyword: str, max_results: int = 5) -> List[Dict]:
    r = http_get("https://www.zhihu.com/search", 
                 params={"q": keyword, "type": "content"},
                 headers=BROWSER_HEADERS)
    if not r: return []
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for item in soup.select(".ContentItem")[:max_results]:
        title_elem = item.select_one(".ContentItem-title a")
        if not title_elem: continue
        title = title_elem.get_text(strip=True)
        url = "https://www.zhihu.com" + title_elem["href"]
        body = item.select_one(".RichText").get_text(strip=True)[:200] if item.select_one(".RichText") else ""
        items.append({
            "title": title,
            "body": body,
            "url": url,
            "source_tag": "【知乎】",
            "source": "zhihu.com"
        })
    return items
    
def fetch_arxiv(query: str, max_results: int = 3) -> List[Dict]:
    r = http_get("http://export.arxiv.org/api/query", params={
        "search_query": query, "max_results": max_results * 3, "sortBy": "submittedDate", "sortOrder": "descending"
    })
    if not r: return []
    items = []
    try:
        root = ET.fromstring(r.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            items.append({
                "title": entry.find("atom:title", ns).text.strip().replace("\n", " "),
                "body": entry.find("atom:summary", ns).text.strip()[:200],
                "url": entry.find("atom:id", ns).text.strip(),
                "source_tag": "【arXiv预印本】",
                "source": "arxiv.org"
            })
    except: pass
    return items

# ──────────────────────────────────────────
# 主逻辑控制
# ──────────────────────────────────────────

def collect_news() -> List[Dict]:
    category_pool = {k: [] for k in CATEGORY_QUOTA}
    seen_titles, seen_urls = load_history_identifiers()

    def try_add(item: dict, category: str):
        title, url = item["title"], item["url"]
        title_key = re.sub(r"\s+", "", title).lower()
        if title_key in seen_titles or url in seen_urls: return
        if not is_clean(title, item.get("body", ""), skip_core_kw=(category=="科研技巧")): return

        seen_titles.add(title_key)
        seen_urls.add(url)
        category_pool[category].append({
            "category": category,
            "title": f"{item.get('source_tag','')}{title}",
            "summary": item.get("body", "查看详情"),
            "url": url,
            "source": item.get("source", "未知"),
            "tags": [category]
        })

    log.info("--- 开始多源采集 ---")
    # A. 期刊 (CrossRef & arXiv)
    for q, cat, num in CROSSREF_TASKS:
        for item in fetch_crossref(q, num): try_add(item, cat)
        time.sleep(2)
    for q, cat, num in ARXIV_TASKS:
        for item in fetch_arxiv(q, num): try_add(item, cat)

    # B. 微信补足 + 新增知乎补足科研技巧
    for kw, cat, num in WEIXIN_TASKS:
        if len(category_pool[cat]) < CATEGORY_QUOTA[cat]:
            for item in fetch_weixin(kw, num): try_add(item, cat)
            time.sleep(3)
    # 新增：科研技巧从知乎补充抓取
    if len(category_pool["科研技巧"]) < CATEGORY_QUOTA["科研技巧"]:
        zhihu_kw = "科研技巧 论文写作 Origin绘图 热解实验方法 XRD 拉曼 红外 TPR TPD origin"
        "科研绘图 SEM 期刊分区 TEM XPS Origin绘图 论文写作 数据处理 实验设计 文献管理 EndNote"
        "Zotero 投稿技巧 审稿回复 科研数据可视化 热解实验方法 催化表征 论文润色 学术写作"
        for item in fetch_zhihu(zhihu_kw, 10):
            try_add(item, "科研技巧")

    # ========== 极简加固：保证每个分类至少 2 条 ==========
    ensure_min_items(category_pool, 2)

    # 加在这里！！
ensure_min_total(pool)

    # C. 汇总输出
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
    完全匹配你项目的路径、格式规范
    """
    # 统一使用北京时间，和项目全局逻辑保持一致
    bj_time = datetime.utcnow() + timedelta(hours=8)
    # 生成当日数据文件路径
    out_path = DATA_DIR / f"{date_str}.json"
    # 构造和你项目完全兼容的payload格式
    payload = {
        "date": date_str,
        "generated_at": bj_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "news": news,
    }
    # 写入JSON文件
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log.info(f"✅ 成功保存今日数据: {len(news)} 条，保存路径: {out_path}")
    
def main():
    # 统一使用北京时间 (UTC+8) 防止时区混乱
    bj_time = datetime.utcnow() + timedelta(hours=8)
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
    res = subprocess.run([sys.executable, str(SCRIPT_DIR / "inject_daily_data.py")], capture_output=True, text=True)
    if res.returncode == 0: log.info(res.stdout.strip())
    else: log.error(res.stderr)

if __name__ == "__main__":
    main()

# --------------------------
# 极简加固：保证
# 1) 每个分类至少 2 条
# 2) 总数至少 15 条
# --------------------------
def ensure_min_total(pool):
    # 1. 每个分类至少 2 条
    for cat in pool:
        while len(pool[cat]) < 2:
            pool[cat].append({
                "title": f"【{cat}】今日行业与科研动态",
                "summary": "实时更新行业进展、科研成果",
                "url": "#",
                "source": "系统自动补充"
            })

    # 2. 总数至少 15 条
    total = sum(len(items) for items in pool.values())
    all_cats = list(pool.keys())
    
    while total < 15:
        # 轮着补，均匀凑够 15 条
        for cat in all_cats:
            if total >= 15:
                break
            pool[cat].append({
                "title": f"【{cat}】今日科研与产业动态",
                "summary": "实时更新行业进展、科研成果",
                "url": "#",
                "source": "系统自动补充"
            })
            total += 1
