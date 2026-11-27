#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心美国经济数据日历 → data/econ_data.js

只保留最核心的六类：非农、CPI、PPI、PCE、GDP、零售销售。

数据来源与可得性（已实测）：
- BEA 官网日程 ✅      官方确认的 GDP / Personal Income & Outlays 等发布日期
- ForexFactory 周历 ✅ 本周美国中高影响事件，带预期与前值（含 CPI/PPI/零售）
- BLS 官网 ❌          对本网络返回 403，无法预取 CPI/PPI/非农的全年官方面日期
- FRED ❌              请求若干次后被阻断

因此非农日期用「每月第一个周五」规则推算（BLS 长期稳定遵循），并标注来源。
抓取失败一律保留旧数据，不影响主站发布。
    python3 fetch_econ.py
"""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
OUT_JSON = os.path.join(DATA, "econ_data.json")
OUT_JS = os.path.join(DATA, "econ_data.js")
CACHE = os.path.join(RAW, "econ_calendar.csv")

BEA_URL = "https://www.bea.gov/news/schedule"
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}

# 只有命中这些类别的发布才收录
CATS = [
    ("非农", r"employment situation|non-?farm payroll|nonfarm employment"),
    ("CPI", r"consumer price index|\bCPI\b"),
    ("PPI", r"producer price index|\bPPI\b"),
    ("PCE", r"personal income and outlays|core pce|\bPCE\b"),
    ("GDP", r"gross domestic product|\bGDP\b"),
    ("零售", r"retail sales|advance monthly sales for retail"),
]
# 明显不属于核心的，直接排除
EXCLUDE = r"by county|by state|international transactions|trade in goods|price index q/q|flash|confidence|jolts|inventories|revisions"


def categorize(title):
    t = title.lower()
    if re.search(EXCLUDE, t):
        return None
    for name, pat in CATS:
        if re.search(pat, title, re.I):
            return name
    return None


def is_us_dst(d):
    """美国夏令时：3 月第二个周日 ~ 11 月第一个周日。"""
    def nth_sunday(year, month, n):
        d0 = date(year, month, 1)
        off = (6 - d0.weekday()) % 7
        return d0 + timedelta(days=off + 7 * (n - 1))
    return nth_sunday(d.year, 3, 2) <= d < nth_sunday(d.year, 11, 1)


def to_beijing(d, hm):
    """美东时间 → 北京时间。EDT 差 12h，EST 差 13h。"""
    h, m = [int(x) for x in hm.split(":")]
    dt = datetime(d.year, d.month, d.day, h, m) + timedelta(hours=12 if is_us_dst(d) else 13)
    return dt.strftime("%H:%M"), dt.date().isoformat()


def _get(url, as_json=False):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json() if as_json else r.text


# ------------------------------------------------------------------ BEA
def parse_bea(html):
    out = []
    year = None
    m = re.search(r"Year (\d{4})", html)
    if m:
        year = int(m.group(1))
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        txt = re.sub(r"<[^>]+>", "|", tr)
        txt = re.sub(r"\s+", " ", txt)
        parts = [p.strip() for p in txt.split("|") if p.strip()]
        if len(parts) < 3:
            continue
        mon = re.match(r"([A-Z][a-z]+) (\d{1,2})$", parts[0])
        if not mon or mon.group(1) not in MONTHS:
            continue
        tm = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", txt)
        title = parts[-1]
        cat = categorize(title)
        if not cat or not year:
            continue
        d = date(year, MONTHS[mon.group(1)], int(mon.group(2)))
        hm = "08:30"
        if tm:
            h = int(tm.group(1)) % 12 + (12 if tm.group(3) == "PM" else 0)
            hm = f"{h:02d}:{tm.group(2)}"
        out.append({"date": d.isoformat(), "time_et": hm, "title": title,
                    "cat": cat, "source": "BEA", "confirmed": True,
                    "forecast": None, "previous": None, "importance": "高"})
    return out


# ------------------------------------------------------- ForexFactory
def parse_ff(items):
    out = []
    for it in items or []:
        if it.get("country") != "USD":
            continue
        if it.get("impact") not in ("High", "Medium"):
            continue
        title = (it.get("title") or "").strip()
        cat = categorize(title)
        if not cat:
            continue
        raw = it.get("date") or ""
        try:
            dt = datetime.strptime(raw[:16], "%Y-%m-%dT%H:%M")
        except ValueError:
            continue
        out.append({"date": dt.date().isoformat(), "time_et": dt.strftime("%H:%M"),
                    "title": title, "cat": cat, "source": "ForexFactory",
                    "confirmed": True, "forecast": it.get("forecast") or None,
                    "previous": it.get("previous") or None,
                    "importance": it.get("impact")})
    return out


# ------------------------------------------------------------------ 非农
def gen_nfp(today, months=12):
    """BLS 长期惯例：非农在每月第一个周五美东 08:30 发布。"""
    out = []
    y, m = today.year, today.month
    for _ in range(months + 1):
        d0 = date(y, m, 1)
        first_fri = d0 + timedelta(days=(4 - d0.weekday()) % 7)
        # 元旦 / 独立日 / 圣诞若落在周五，BLS 会顺延到下一个周五
        while (first_fri.month, first_fri.day) in ((1, 1), (7, 4), (12, 25)):
            first_fri += timedelta(days=7)
        if first_fri >= today:
            out.append({"date": first_fri.isoformat(), "time_et": "08:30",
                        "title": "Employment Situation（非农就业报告）", "cat": "非农",
                        "source": "BLS 规则推算", "confirmed": False,
                        "forecast": None, "previous": None, "importance": "高"})
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out[:months]


def main():
    today = date.today()
    old = {}
    if os.path.exists(OUT_JSON):
        try:
            old = json.load(open(OUT_JSON, encoding="utf-8"))
        except Exception:
            old = {}

    events = []
    notes = []

    try:
        bea = parse_bea(_get(BEA_URL))
        events += bea
        print(f"BEA 官方：{len(bea)} 条核心发布")
    except Exception as e:
        print(f"BEA 抓取失败（保留旧数据）：{str(e)[:100]}")
        events += [x for x in old.get("events", []) if x.get("source") == "BEA"]
        notes.append("BEA 本次抓取失败，沿用上一次结果")

    try:
        ff = parse_ff(_get(FF_URL, as_json=True))
        events += ff
        print(f"ForexFactory 本周：{len(ff)} 条核心事件")
    except Exception as e:
        print(f"ForexFactory 抓取失败（保留旧数据）：{str(e)[:100]}")
        events += [x for x in old.get("events", []) if x.get("source") == "ForexFactory"]
        notes.append("ForexFactory 本次抓取失败，沿用上一次结果")

    nfp = gen_nfp(today)
    events += nfp
    print(f"非农规则推算：{len(nfp)} 个未来日期")

    # 合并去重：同一天同一类别只留一条，官方来源优先
    prio = {"BEA": 3, "ForexFactory": 2, "BLS 规则推算": 1}
    best = {}
    for e in events:
        k = (e["date"], e["cat"])
        if k not in best or prio.get(e["source"], 0) > prio.get(best[k]["source"], 0):
            best[k] = e

    rows = []
    for e in best.values():
        bj, bj_date = to_beijing(date.fromisoformat(e["date"]), e["time_et"])
        e = dict(e)
        e["time_bj"] = bj
        e["date_bj"] = bj_date
        rows.append(e)
    rows.sort(key=lambda x: (x["date"], x["time_et"]))

    # 累积缓存，便于将来看更长窗口
    os.makedirs(RAW, exist_ok=True)
    try:
        seen = set()
        if os.path.exists(CACHE):
            for ln in open(CACHE, encoding="utf-8").read().splitlines()[1:]:
                seen.add(ln.split(",")[0:2] and tuple(ln.split(",")[:2]))
        with open(CACHE, "a", encoding="utf-8") as f:
            if not seen:
                f.write("date,cat,title,source,time_et\n")
            for e in rows:
                k = (e["date"], e["cat"])
                if k in seen:
                    continue
                seen.add(k)
                f.write(f'{e["date"]},{e["cat"]},"{e["title"]}",{e["source"]},{e["time_et"]}\n')
    except Exception as ex:
        print(f"缓存写入失败：{str(ex)[:80]}")

    future = [e for e in rows if e["date"] >= today.isoformat()]
    by_cat = {}
    for e in rows:
        by_cat.setdefault(e["cat"], 0)
        by_cat[e["cat"]] += 1

    doc = {
        "meta": {
            "generated_at": f"{datetime.now():%Y-%m-%d %H:%M}",
            "asof": today.isoformat(),
            "next": future[0]["date"] if future else None,
            "days_to_next": ((date.fromisoformat(future[0]["date"]) - today).days if future else None),
            "future_count": len(future),
            "week_high": len([e for e in rows if e["importance"] == "High"
                              and today.isoformat() <= e["date"] <= (today + timedelta(days=7)).isoformat()]),
            "cats": by_cat,
            "notes": notes + [
                "BLS 与 FRED 对本项目网络返回 403/连接中断，CPI、PPI 的全年官方日期无法预取；"
                "这两类在临近时由 ForexFactory 周历补充。",
                "非农日期由“每月第一个周五”规则推算，BLS 极少例外。",
            ],
        },
        "events": rows,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("window.ECON_DATA=")
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    print(f"\n=== 完成 === 共 {len(rows)} 条，其中未来 {len(future)} 条")
    if future:
        n = future[0]
        print(f"下一项 {n['date_bj']} {n['time_bj']}（北京）{n['title'][:40]} · {n['source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
