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
    "塑料","热解", "催化热解", "热裂解", "催化裂解", "快速热解", "共热解", "废塑料", "塑料回收",
    "废轮胎", "废橡胶", "生物质", "生物炭", "生物油", "焦油", "焦炭", "沸石", "分子筛", "合成气",
    "聚乙烯", "聚丙烯", "聚苯乙烯", "秸秆", "木质素", "纤维素", "高纯氢", "碳纳米管", "微波", "等离子体",
    "plastic","pyrolysis", "catalytic pyrolysis", "thermal pyrolysis", "co-pyrolysis",
    "waste plastic", "polyolefin", "polyethylene", "polypropylene", "polystyrene","sygas", "gas",
    "biochar", "bio-oil", "hydrogen production", "carbon nanotube", "zeolite", "microwave", "plasma",
]
CORE_KW_RE = re.compile("|".join(CORE_KEYWORDS), re.IGNORECASE)

# ──────────────────────────────────────────
# 采集配额
# ──────────────────────────────────────────
CATEGORY_QUOTA = {"塑料热解": 6, "生物质热解": 3, "催化热解": 4, "创新催化剂": 4, "科研圈": 3, "科研技巧": 5}
JOURNAL_QUOTA = {"塑料热解": 3, "生物质热解": 2, "催化热解": 2, "创新催化剂": 2, "科研圈": 2, "科研技巧": 0}
CAT_ICONS = {"塑料热解": "♻️", "生物质热解": "🌿", "催化热解": "⚗️", "创新催化剂": "✨", "科研圈": "🎓", "科研技巧": "💡"}

# 设置 CrossRef 检索起始时间（最近 120 天）
CROSSREF_START_DATE = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")

# ──────────────────────────────────────────
# 采集任务清单
# ──────────────────────────────────────────
CROSSREF_TASKS = [
    ("plastic pyrolysis catalytic pyrolysis thermal pyrolysis co-pyrolysis waste polyolefin polyethylene polypropylene polystyrene sygas gas hydrogen production carbon nanotube zeolite microwave plasma", "塑料热解", 10),
    ("pyrolysis biomass biochar bio-oil lignin", "生物质热解", 10),
    ("catalytic pyrolysis mechanism selectivity", "催化热解", 10),
    ("pyrolysis zeolite catalyst ZSM SAPO single-atom metal oxide", "创新催化剂", 10),
    ("pyrolysis review progress recent journal", "科研圈", 10),
]

ARXIV_TASKS = [
    ("ti:pyrolysis AND ti:plastic", "塑料热解", 5),
    ("ti:pyrolysis AND ti:catalytic", "催化热解", 5),
]

WEIXIN_TASKS = [
    ("塑料 热解 产业化 化学回收 塑料热解 塑料 热解 催化热解 热裂解 催化裂解 快速热解 共热解 废塑料 塑料回收 焦油 焦炭 沸石 分子筛 合成气 聚乙烯 聚丙烯 聚苯乙烯 高纯氢 碳纳米管 微波 等离子体", "塑料热解" 8),
    ("生物质热解 生物炭 生物油 塑料 热解 催化热解 热裂解 催化裂解 快速热解 共热解 废塑料 塑料回收 废轮胎 废橡胶 生物质 生物炭 生物油 焦油 焦炭 沸石 分子筛 合成气 聚乙烯 聚丙烯 聚苯乙烯 秸秆 木质素 纤维素 高纯氢 碳纳米管 微波 等离子体", "生物质热解" 6),
    ("催化热解 机理 选择性 产率 合成气 三态产物", "催化热解", 6),
    ("科研技巧 XRD 拉曼 红外 TPR TPD origin 科研绘图 SEM 期刊分区 TEM XPS", "科研技巧", 6),
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
    """核心修复点：将排序改为 published，并增加采样 rows 以防止每日内容重复"""
    r = http_get(
        "https://api.crossref.org/works",
        params={
            "query.title": query,
            "filter": f"from-pub-date:{CROSSREF_START_DATE},type:journal-article",
            "rows": max_results * 10,  # 采样池扩大到10倍
            "sort": "published",       # 改为按日期排序，保证每天都有新鲜内容
            "order": "desc",
        },
        headers=API_HEADERS
    )
    if not r: return []
    items = []
    try:
        for w in r.json()["message"]["items"]:
            title_list = w.get("title")
            if not title_list: continue
            title = title_list[0].strip()
            journal = (w.get("container-title") or [""])[0]
            if journal and not JOURNAL_WHITELIST_RE.search(journal): continue
            
            items.append({
                "title": title,
                "body": (w.get("abstract") or "点击原文查看详情。")[:200],
                "url": w.get("URL", ""),
                "source_tag": f"【{journal[:15]}】" if journal else "【学术期刊】",
                "source": "doi.org"
            })
    except: pass
    return items

def fetch_weixin(keyword: str, max_results: int = 8) -> List[Dict]:
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

    # B. 微信补足
    for kw, cat, num in WEIXIN_TASKS:
        if len(category_pool[cat]) < CATEGORY_QUOTA[cat]:
            for item in fetch_weixin(kw, num): try_add(item, cat)
            time.sleep(3)

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
