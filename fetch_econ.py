#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心美国经济数据日历 → data/econ_data.js

只保留最核心的六类：非农、CPI、PPI、PCE、GDP、零售销售。

数据来源与可得性（已实测）：
- BEA 官网日程 ✅      官方确认的 GDP / Personal Income & Outlays 等发布日期
- ForexFactory 周历 ✅ 本周美国中高影响事件，带预期与前值（含 CPI/PPI/零售），偶发 429
- BLS 官网 ❌          bls.gov / data.bls.gov / api.bls.gov / blsmon1.bls.gov 全部 403
- Census ❌            census.gov / api.census.gov 403
- FRED ❌              首次 200，若干次请求后被阻断
- TradingEconomics ❌  表格由 JS 渲染，服务端只返回骨架

所以 CPI / PPI / 非农 / 零售 改用 econ_schedule.py 里人工维护的官方年度日程
（这些日程由官方年初一次性公布、极少变动），BEA 与美联储仍实时抓取。
ForexFactory 只负责补齐「预期 / 前值」，并作为临近发布日的交叉校验。
未被官方日程覆盖的月份，非农退化为「每月第一个周五」规则推算，并如实标注。

抓取失败一律保留旧数据，不影响主站发布。
    python3 fetch_econ.py
"""
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta

import requests

import econ_schedule

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
OUT_JSON = os.path.join(DATA, "econ_data.json")
OUT_JS = os.path.join(DATA, "econ_data.js")
CACHE = os.path.join(RAW, "econ_calendar.csv")

BEA_URL = "https://www.bea.gov/news/schedule"
BEA_NEXT_URL = "https://www.bea.gov/news/schedule/next-year"
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}

# 只有命中这些类别的发布才收录
CATS = [
    ("FOMC", r"fomc|federal open market"),
    ("非农", r"employment situation|non-?farm payroll|nonfarm employment"),
    ("CPI", r"consumer price index|\bCPI\b"),
    ("PPI", r"producer price index|\bPPI\b"),
    ("PCE", r"personal income and outlays|core pce|\bPCE\b"),
    ("GDP", r"gross domestic product|\bGDP\b"),
    ("零售", r"retail sales|advance monthly sales for retail"),
    ("ISM", r"\bISM\b|purchasing managers"),
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


def _get(url, as_json=False, tries=3, timeout=25):
    """ForexFactory 偶发 429，BEA 偶发超时，统一做指数退避重试。

    重试预算要压在 run_update 给本脚本的调用超时之内。
    """
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
            if r.status_code in (429, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json() if as_json else r.text
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(6 * (2 ** i))
    raise last


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
        # GDP 一季报三次，第二次和第三次估算市场基本没有反应，只留初值
        if cat == "GDP" and not re.search(r"advance", title, re.I):
            continue
        d = date(year, MONTHS[mon.group(1)], int(mon.group(2)))
        hm = "08:30"
        if tm:
            h = int(tm.group(1)) % 12 + (12 if tm.group(3) == "PM" else 0)
            hm = f"{h:02d}:{tm.group(2)}"
        out.append({"date": d.isoformat(), "time_et": hm, "title": pretty_bea_title(title, cat),
                    "cat": cat, "source": "BEA", "confirmed": True,
                    "forecast": None, "previous": None, "importance": "高"})
    return out


def pretty_bea_title(title, cat):
    """BEA 原始标题是长句，压成可读的一行。"""
    t = title
    est = ""
    for k, v in (("advance", "初值"), ("prelim", "修正值"),
                 ("second estimate", "第二次估算"), ("third estimate", "第三次估算")):
        if re.search(k, t, re.I):
            est = v
            break
    q = re.search(r"(\d)(?:st|nd|rd|th)\s+Quarter(?:\s+and\s+Year)?\s+(\d{4})", t, re.I)
    mon = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{4})", t)
    if cat == "GDP":
        base = "GDP 国内生产总值"
        if q:
            base += f"（{q.group(2)}Q{q.group(1)}"
            base += f"，{est}）" if est else "）"
        elif est:
            base += f"（{est}）"
        return base
    if cat == "PCE":
        base = "核心 PCE 物价"
        if mon:
            base += f"（{mon.group(2)}-{MONTHS[mon.group(1)]:02d}）"
        return base
    return title


_FF_TITLES = [
    (r"^core pce price index m/m$", "核心 PCE 月环比"),
    (r"^pce price index m/m$", "PCE 月环比"),
    (r"^core pce price index y/y$", "核心 PCE 同比"),
    (r"^cpi m/m$", "CPI 月环比"),
    (r"^core cpi m/m$", "核心 CPI 月环比"),
    (r"^cpi y/y$", "CPI 同比"),
    (r"^core cpi y/y$", "核心 CPI 同比"),
    (r"^ppi m/m$", "PPI 月环比"),
    (r"^core ppi m/m$", "核心 PPI 月环比"),
    (r"^retail sales m/m$", "零售销售 月环比"),
    (r"^core retail sales m/m$", "核心零售销售 月环比"),
    (r"^gdp q/q$", "GDP 季环比"),
    (r"^prelim gdp q/q$", "GDP 季环比（修正）"),
    (r"^advance gdp q/q$", "GDP 季环比（初值）"),
    (r"^ism manufacturing pmi$", "ISM 制造业 PMI"),
    (r"^ism services pmi$", "ISM 服务业 PMI"),
    (r"^non-?farm employment change$", "非农就业人数变动"),
    (r"^unemployment rate$", "失业率"),
]


def pretty_ff_title(title):
    t = title.strip()
    for pat, zh in _FF_TITLES:
        if re.match(pat, t, re.I):
            return zh
    return t


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
                    "title": pretty_ff_title(title), "cat": cat, "source": "ForexFactory",
                    "confirmed": True, "forecast": it.get("forecast") or None,
                    "previous": it.get("previous") or None,
                    "importance": it.get("impact")})
    return out


# ------------------------------------------------------------------ 非农
def gen_nfp(today, months=12, skip_months=None):
    """BLS 长期惯例：非农在每月第一个周五美东 08:30 发布。

    skip_months 里已由官方日程覆盖的发布月直接跳过，避免与官方日期并存。
    """
    skip_months = skip_months or set()
    out = []
    y, m = today.year, today.month
    for _ in range(months + 1):
        d0 = date(y, m, 1)
        first_fri = d0 + timedelta(days=(4 - d0.weekday()) % 7)
        # 元旦 / 独立日 / 圣诞若落在周五，BLS 会顺延到下一个周五
        while (first_fri.month, first_fri.day) in ((1, 1), (7, 4), (12, 25)):
            first_fri += timedelta(days=7)
        if first_fri >= today and (first_fri.year, first_fri.month) not in skip_months:
            dm = (first_fri.replace(day=1) - timedelta(days=1))
            out.append({"date": first_fri.isoformat(), "time_et": "08:30",
                        "title": f"非农就业报告（{dm.year}-{dm.month:02d}）",
                        "cat": "非农",
                        "source": "BLS 规则推算", "confirmed": False,
                        "forecast": None, "previous": None, "importance": "高"})
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out[:months]


_US_FIXED_HOLIDAYS = [(1, 1), (6, 19), (7, 4), (11, 11), (12, 25)]


def _is_us_holiday(d):
    """只判 ISM 会实际避开的固定日与「顺延到周一/周五」的情形。

    浮动假日（MLK、总统日、劳动节等）都落在周一，不参与 ISM 的工作日计数。
    """
    def observed(m, day):
        h = date(d.year, m, day)
        wd = h.weekday()
        if wd == 5:      # 周六 → 前一个周五
            return h - timedelta(days=1)
        if wd == 6:      # 周日 → 后一个周一
            return h + timedelta(days=1)
        return h
    return any(d == observed(m, day) for m, day in _US_FIXED_HOLIDAYS)


def _business_days(year, month, n):
    """该月第 n 个工作日（周一至周五且非联邦假日），ISM 的发布规则就是按这个数。"""
    d = date(year, month, 1)
    cnt = 0
    for _ in range(31):
        if d.weekday() < 5 and not _is_us_holiday(d):
            cnt += 1
            if cnt == n:
                return d
        d += timedelta(days=1)
    return None


def gen_ism(today, months=12):
    """ISM 采购经理人指数：制造业每月第 1 个工作日、服务业第 3 个工作日，美东 10:00。

    ISM 官网（ismworld.org）对本网络不可达，但发布时间规则多年未变，属于可靠推算。
    """
    out = []
    y, m = today.year, today.month
    for _ in range(months + 1):
        for nth, label in ((1, "制造业"), (3, "服务业")):
            d = _business_days(y, m, nth)
            if d and d >= today:
                out.append({"date": d.isoformat(), "time_et": "10:00",
                            "title": f"ISM {label} PMI（{y}-{m:02d}）", "cat": "ISM",
                            "source": "ISM 规则推算", "confirmed": False,
                            "forecast": None, "previous": None, "importance": "高"})
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out[:months * 2]


def gen_fomc():
    """从已生成的 fomc_data.js 里取会议决议日，避免重复抓美联储官网。"""
    path = os.path.join(DATA, "fomc_data.js")
    if not os.path.exists(path):
        return []
    try:
        s = open(path, encoding="utf-8").read()
        doc = json.loads(s[s.index("=") + 1:].rstrip().rstrip(";"))
    except Exception:
        return []
    out = []
    for m in doc.get("meetings") or []:
        if m["end"] < date.today().isoformat():
            continue  # 历史会议已在 FOMC 子页，日历只关心未来
        out.append({
            "date": m["end"], "time_et": "14:00",
            "title": "FOMC 利率决议" + ("（含 SEP）" if m.get("sep") else ""),
            "cat": "FOMC", "source": "Federal Reserve", "confirmed": True,
            "forecast": None, "previous": None, "importance": "高",
        })
    return out


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

    official = econ_schedule.events()
    events += official
    print(f"官方年度日程：{len(official)} 条（覆盖至 {econ_schedule.latest_date()}）")

    bea = []
    for url, label in ((BEA_URL, "当年"), (BEA_NEXT_URL, "次年")):
        try:
            got = parse_bea(_get(url, tries=2, timeout=20))
            bea += got
            print(f"BEA 官方（{label}日程）：{len(got)} 条核心发布")
        except Exception as e:
            print(f"BEA {label}日程抓取失败：{str(e)[:100]}")
            notes.append(f"BEA {label}日程本次抓取失败，沿用上一次结果")
    if bea:
        events += bea
    else:
        events += [x for x in old.get("events", []) if x.get("source") == "BEA"]

    ff = []
    try:
        ff = parse_ff(_get(FF_URL, as_json=True, tries=4, timeout=20))
        events += ff
        print(f"ForexFactory 本周：{len(ff)} 条核心事件")
    except Exception as e:
        print(f"ForexFactory 抓取失败（保留旧数据）：{str(e)[:100]}")
        ff = [x for x in old.get("events", []) if x.get("source") == "ForexFactory"]
        for x in ff:
            x["title"] = pretty_ff_title(x.get("title") or "")
        events += ff
        notes.append("ForexFactory 本次抓取失败，沿用上一次结果；预期/前值可能滞后")

    nfp = gen_nfp(today, skip_months=econ_schedule.covered_nfp_months())
    events += nfp
    print(f"非农规则推算：{len(nfp)} 个未来日期（官方日程未覆盖的月份）")

    ism = gen_ism(today)
    events += ism
    print(f"ISM 规则推算：{len(ism)} 条（每月第 1 / 3 个工作日）")

    fomc = gen_fomc()
    events += fomc
    print(f"FOMC 决议：{len(fomc)} 场")

    # 合并去重：同一天同一类别只留一条，官方来源优先
    prio = {econ_schedule.SRC_BLS: 5, econ_schedule.SRC_CENSUS: 5,
            "Federal Reserve": 5, "BEA": 4, "ForexFactory": 3,
            "BLS 规则推算": 1, "ISM 规则推算": 1}
    best = {}
    for e in events:
        k = (e["date"], e["cat"])
        if k not in best or prio.get(e["source"], 0) > prio.get(best[k]["source"], 0):
            best[k] = e

    # 官方日程不提供预期/前值，从 ForexFactory 同一类别的临近日借过来
    for e in best.values():
        if e.get("forecast") or not ff:
            continue
        near = [x for x in ff if x["cat"] == e["cat"]
                and abs((date.fromisoformat(x["date"]) - date.fromisoformat(e["date"])).days) <= 1]
        if near:
            e["forecast"] = near[0]["forecast"]
            e["previous"] = near[0]["previous"]

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

    high_flags = ("High", "高")
    week_end = (today + timedelta(days=14)).isoformat()
    sched_until = econ_schedule.latest_date()
    if sched_until < today.isoformat():
        notes.append(f"官方年度日程已过期（止于 {sched_until}），请更新 econ_schedule.py。")

    doc = {
        "meta": {
            "generated_at": f"{datetime.now():%Y-%m-%d %H:%M}",
            "asof": today.isoformat(),
            "next": future[0]["date"] if future else None,
            "days_to_next": ((date.fromisoformat(future[0]["date"]) - today).days if future else None),
            "future_count": len(future),
            "week_high": len([e for e in rows if e["importance"] in high_flags
                              and today.isoformat() <= e["date"] <= week_end]),
            "week_high_days": 14,
            "cats": by_cat,
            "sched_until": sched_until,
            "sched_verified": econ_schedule.VERIFIED_ON,
            "notes": notes + [
                "CPI、PPI、非农、零售的日期取自官方年度发布日程（BLS / Census），"
                f"由 econ_schedule.py 维护，当前核对日 {econ_schedule.VERIFIED_ON}、"
                f"覆盖至 {sched_until}。官方日程之外不再猜日期。",
                "BLS / Census / FRED / ISM 官网对本项目所在网络返回 403 或连接中断，"
                "日程无法在运行时抓取，只能按官方公布的表人工登记或按规则推算；"
                "这是数据可得性的硬约束，不是遗漏。",
                "ISM 按「制造业每月第 1 个工作日、服务业第 3 个工作日」推算，已排除美国联邦假日。",
                "FOMC 决议日取自美联储官网实时抓取；BEA 的 GDP（仅初值）与核心 PCE 同样实时抓取。",
                "刻意不收：JOLTS（滞后两个月，美联储已降低引用频率）、初请失业金（每周一条会淹没日历）、"
                "GDP 第二/三次估算（市场基本无反应）。",
                "ForexFactory 周历只覆盖当周，用于补齐「预期 / 前值」并交叉校验官方日期。",
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
