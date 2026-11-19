# -*- coding: utf-8 -*-
"""新浪财经 7x24 快讯 → 事件线索。

只做两件事：按关键词筛选、按时间去重累积。
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

# 标签 → 触发词。命中任一即收录，并打上对应标签。
TAG_KEYWORDS = {
    "汇金": ["汇金"],
    "证金": ["证金"],
    "平准": ["平准"],
    "国家队": ["国家队"],
    "宽基ETF": ["宽基", "沪深300ETF", "中证500ETF", "中证1000ETF", "上证50ETF", "科创50ETF", "创业板ETF"],
    "ETF": ["ETF", "etf"],
    "增持": ["增持"],
    "回购": ["回购"],
    "央行": ["中国人民银行", "人民银行", "中国央行", "降准", "降息", "MLF", "LPR", "逆回购", "公开市场操作"],
    "监管": ["证监会", "金融监管总局", "国常会", "政治局"],
    "国资": ["诚通", "国新"],
}
MAX_ITEMS = 400
# 强标签：命中其一即可收录；弱标签（增持/回购/国资）只能作为附加标签，
# 避免"某券商维持某股增持评级"这类噪音。
STRONG_TAGS = {"汇金", "证金", "平准", "国家队", "宽基ETF", "ETF", "央行"}


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


def _tags(text):
    hit = [tag for tag, words in TAG_KEYWORDS.items() if any(w in text for w in words)]
    if not any(t in STRONG_TAGS for t in hit):
        return []
    return hit


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
            return json.load(f).get("items", [])
    except Exception:
        return []


def collect(pages=3):
    """抓取并累积新闻线索，返回 (items, newly_added_count)。"""
    old = _load_existing()
    seen = {x["title"] for x in old}
    new_items = []
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
            tags = _tags(text)
            if not tags:
                continue
            title = _headline(text)
            if not title or title in seen:
                continue
            seen.add(title)
            new_items.append({
                "date": (it.get("create_time") or "")[:10],
                "time": (it.get("create_time") or "")[11:16],
                "title": title,
                "url": it.get("docurl") or "",
                "tags": tags,
                "source": "新浪财经",
            })

    items = sorted(old + new_items, key=lambda x: (x.get("date", ""), x.get("time", "")), reverse=True)
    items = items[:MAX_ITEMS]
    os.makedirs(DATA, exist_ok=True)
    with open(NEWS_JSON, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "items": items},
                  f, ensure_ascii=False, indent=1)
    return items, len(new_items)
