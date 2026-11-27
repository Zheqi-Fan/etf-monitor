# -*- coding: utf-8 -*-
"""新浪财经 7x24 快讯 → 事件线索。

设计原则：
1. 正则精确匹配 + 排除词，避免「保证金」被当成「证金」这类子串误报
2. 相关性打分，低于阈值直接丢弃——宁可少，不要错
3. 标签按分值降序，页面只显示最相关的一两个

不自动判定为"官方事件"——config.EVENTS 里的人工事件轴才是权威口径，
这里产出的只是供复核的线索。
"""
import json
import os
import re
from datetime import datetime

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
NEWS_JSON = os.path.join(DATA, "news.json")
FEED = "https://zhibo.sina.com.cn/api/zhibo/feed"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

MAX_ITEMS = 300
MIN_SCORE = 6          # 低于此分视为无关，直接丢弃

BROAD_INDEX = r"沪深300|上证50|中证500|中证1000|科创50|创业板|双创|科创|创业"
FOREIGN = r"美联储|欧洲央行|日本央行|英国央行|韩国|台湾|泰国|印度|越南|瑞士|美国"
# 例行播报（股指期货每分钟一条、收盘收评），无信息增量
ROUTINE = r"期货|主力合约|(?:A股|沪深两市|两市)(?:收评|午评|开盘|早盘收盘|收盘)"
# 窄基 / 商品 / 境外：只有同时命中宽基或机构主体时才保留
NARROW = r"主动ETF|行业ETF|主题ETF|黄金|白银|芯片|半导体|机器人|医药|军工|红利|算力|CRO|比特币|纳指|标普|恒生|港股|日经|原油|豆粕|有色"

# (标签, 正则, 分值)。命中即加分并记录标签；总分决定是否收录。
RULES = [
    # P0 机构主体：极少出现，但一旦出现价值最高
    ("汇金", r"中央汇金|汇金公司|汇金投资|汇金资管|汇金资产|汇金系|汇金增持", 14),
    ("证金", r"证金公司|中国证金|证金资管|证金增持|中国证券金融", 12),
    ("国家队", r"国家队", 12),
    ("平准", r"平准基金|类平准", 14),
    ("国新诚通", r"国新投资|国新控股|诚通金控|诚旸投资", 10),

    # P1 宽基 ETF 与申赎：本页核心观测对象
    ("核心池", r"510300|510310|510330|510050|510500|512100|588000|588080|159919|159915", 10),
    ("宽基ETF", rf"(?:{BROAD_INDEX})(?:ETF|指数)|宽基(?:ETF|指数)", 6),
    ("ETF成交", r"ETF.{0,8}成交额|成交额.{0,8}ETF|ETF两市成交|ETF.{0,4}放量|宽基.{0,6}放量", 6),
    ("申赎", r"净申购|净赎回|份额变动|ETF.{0,10}净流入", 5),

    # P2 宏观与监管背景（逆回购/净投放属日常操作，不算政策信号）
    ("货币宽松", r"(?:中国人民银行|人民银行|中国央行|央行).{0,30}(?:降准|降息|MLF|LPR)", 6),
    ("监管", r"证监会|金融监管总局|国常会|国务院金融", 4),
]

_COMPILED = [(tag, re.compile(pat), pts) for tag, pat, pts in RULES]
_FOREIGN_RE = re.compile(FOREIGN)
_ROUTINE_RE = re.compile(ROUTINE)
_NARROW_RE = re.compile(NARROW)


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


def _headline(text):
    """优先取【】里的标题，否则取首句。"""
    m = re.search(r"【([^】]{4,80})】", text)
    if m:
        return m.group(1).strip()
    return text.split("。")[0][:80]


def score(text):
    """返回 (总分, 命中标签列表[按分值降序])。"""
    hits = []
    for tag, rx, pts in _COMPILED:
        if not rx.search(text):
            continue
        if tag in ("货币宽松", "监管") and _FOREIGN_RE.search(text) and not re.search(r"中国|中国人民银行", text):
            continue
        hits.append((pts, tag))
    if not hits:
        return 0, []
    hits.sort(key=lambda x: -x[0])
    tags = [t for _, t in hits]
    if _ROUTINE_RE.search(text):
        return 0, []
    if _NARROW_RE.search(text) and not any(
            t in tags for t in ("核心池", "宽基ETF", "汇金", "证金", "国家队", "平准", "国新诚通")):
        return 0, []
    return sum(p for p, _ in hits), tags


def _fetch_page(page, page_size=100):
    r = requests.get(
        FEED,
        params={"page": page, "page_size": page_size, "zhibo_id": 152, "tag_id": 0, "dire": "f", "dpc": 1},
        headers={"Referer": "https://finance.sina.com.cn/7x24/", "User-Agent": UA},
        timeout=20,
    )
    j = r.json()
    return ((j.get("result") or {}).get("data") or {}).get("feed", {}).get("list", []) or []


def _load_existing():
    if not os.path.exists(NEWS_JSON):
        return []
    try:
        with open(NEWS_JSON, encoding="utf-8") as f:
            raw = json.load(f).get("items", [])
    except Exception:
        return []
    out, seen_t, seen_u = [], set(), set()
    for x in raw:
        t, u = x.get("title"), x.get("url") or ""
        if not t or t in seen_t or (u and u in seen_u):
            continue
        seen_t.add(t)
        if u:
            seen_u.add(u)
        out.append(x)
    return out


def collect(pages=4, reset=False):
    """抓取并累积新闻线索，返回 (items, newly_added_count)。"""
    old = [] if reset else _load_existing()
    seen = {x["title"] for x in old}
    seen_url = {x["url"] for x in old if x.get("url")}
    new_items, dropped = [], 0

    for page in range(1, pages + 1):
        try:
            feed = _fetch_page(page)
        except Exception as e:
            print(f"  [NEWS] 第 {page} 页失败: {str(e)[:60]}")
            continue
        if not feed:
            break
        for it in feed:
            text = _clean(it.get("rich_text") or it.get("content") or "")
            if not text:
                continue
            pts, tags = score(text)
            if pts < MIN_SCORE:
                dropped += 1
                continue
            title = _headline(text)
            url = it.get("docurl") or ""
            if not title or title in seen or (url and url in seen_url):
                continue
            seen.add(title)
            if url:
                seen_url.add(url)
            new_items.append({
                "date": (it.get("create_time") or "")[:10],
                "time": (it.get("create_time") or "")[11:16],
                "title": title,
                "url": url,
                "tags": tags,
                "score": pts,
                "source": "新浪财经",
            })

    items = sorted(old + new_items, key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)
    items = items[:MAX_ITEMS]
    os.makedirs(DATA, exist_ok=True)
    with open(NEWS_JSON, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "min_score": MIN_SCORE, "items": items}, f, ensure_ascii=False, indent=1)
    print(f"   [NEWS] 丢弃无关 {dropped} 条")
    return items, len(new_items)
