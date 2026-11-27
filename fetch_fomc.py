#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 FOMC 会议日历与联邦基金目标利率，生成 data/fomc_data.js。

数据源：
- https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm  会议日程 + 纪要日期
- https://www.federalreserve.gov/monetarypolicy/openmarket.htm      目标利率变动表
- 腾讯 ifzq 港股日线        恒生指数 / 恒生科技指数（Tushare index_global 只有 HSI 且 2024 年起）
- Tushare shibor_lpr        1 年期 LPR，用于「中国利率变动」对照列

决议后市场反应的事件研究在这里算完再落盘，前端只负责渲染：
Python 侧能直接读 data/daily.csv，比在浏览器里拼 DASHBOARD_DATA 更好维护。

抓取失败时保留旧数据，不影响主看板发布。
    python3 fetch_fomc.py
"""
import csv
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
OUT_JSON = os.path.join(DATA, "fomc_data.json")
OUT_JS = os.path.join(DATA, "fomc_data.js")
DAILY_CSV = os.path.join(DATA, "daily.csv")
HK_CACHE = os.path.join(RAW, "hk_index.csv")
LPR_CACHE = os.path.join(RAW, "lpr.csv")

CAL_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
RATE_URL = "https://www.federalreserve.gov/monetarypolicy/openmarket.htm"
HK_KLINE = ("https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get"
            "?param={sym},day,,,{n},qfq")
HK_SYMBOLS = [("HSI", "hkHSI", "恒生指数"), ("HSTECH", "hkHSTECH", "恒生科技")]
BASE = "https://www.federalreserve.gov"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}
ABBR = {k[:3]: v for k, v in MONTHS.items()}


def _get(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text


def parse_calendar(html):
    """返回会议列表。跨月会议（如 Apr/May 30-1）单独处理。"""
    out = []
    blocks = re.split(r'<a id="\d+">(\d{4}) FOMC Meetings</a>', html)
    for k in range(1, len(blocks), 2):
        year = int(blocks[k])
        body = blocks[k + 1]
        # 截断到下一个年份面板之前
        nxt = body.find("panel panel-default")
        if nxt > 0:
            body = body[:nxt]
        toks = re.findall(
            r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>'
            r'|fomc-meeting__date[^>]*>\s*([^<]+?)\s*<', body)
        month = None
        for m, d in toks:
            if m:
                month = m.strip()
                continue
            if not month or not d:
                continue
            raw = d.strip()
            sep = "*" in raw
            raw = raw.replace("*", "").strip()
            nums = re.findall(r"\d+", raw)
            if not nums:
                continue
            if "/" in month:
                m1, m2 = [ABBR[x.strip()[:3]] for x in month.split("/")]
            else:
                m1 = m2 = MONTHS.get(month, 0)
            if not m1:
                continue
            start_day = int(nums[0])
            end_day = int(nums[-1])
            out.append({
                "year": year,
                "sep": sep,
                "start": f"{year:04d}-{m1:02d}-{start_day:02d}",
                "end": f"{year:04d}-{m2:02d}-{end_day:02d}",
            })
            month = None
        # 补 statement 链接与纪要发布日期
        for it in out:
            if it["year"] != year or "statement" in it:
                continue
            ymd = it["end"].replace("-", "")
            it["statement"] = f"{BASE}/newsevents/pressreleases/monetary{ymd}a.htm"
            it["presser"] = f"{BASE}/monetarypolicy/fomcpresconf{ymd}.htm"
            mrel = re.search(
                rf'fomcminutes{ymd}\.htm.*?\(Released ([A-Z][a-z]+) (\d{{1,2}}), (\d{{4}})\)',
                body, re.S)
            it["minutes_release"] = (
                f"{mrel.group(3)}-{MONTHS[mrel.group(1)]:02d}-{int(mrel.group(2)):02d}"
                if mrel else None)
    out.sort(key=lambda x: x["start"])
    return out


def parse_rates(html):
    """目标利率变动表：Date / Increase / Decrease / Level。"""
    rows = []
    blocks = re.split(r'<h4>(\d{4})</h4>', html)
    prev_year = None
    # 第一段（2026 表格可能出现在 <h4>2025</h4> 之前）
    for k in range(0, len(blocks)):
        if k % 2 == 0:
            body = blocks[k]
            year = prev_year
        else:
            year = int(blocks[k])
            prev_year = year
            body = blocks[k + 1] if k + 1 < len(blocks) else ""
        for m in re.finditer(
                r'<td class="bold stub"[^>]*>\s*([A-Z][a-z]+) (\d{1,2})\s*</td>\s*'
                r'<td class="stub"[^>]*>\s*([\d.]+)\s*</td>\s*'
                r'<td class="stub"[^>]*>\s*([\d.]+)\s*</td>\s*'
                r'<td class="stub"[^>]*>\s*([\d.\-–]+)\s*</td>', body):
            mon, day, inc, dec, level = m.groups()
            if mon not in MONTHS or not year:
                continue
            # 老表格用 "..." 表示该列不适用（而非 0）
            def _num(x):
                try:
                    return float(x)
                except (TypeError, ValueError):
                    return 0.0
            inc_f, dec_f = _num(inc), _num(dec)
            rows.append({
                "date": f"{year:04d}-{MONTHS[mon]:02d}-{int(day):02d}",
                "change": round(inc_f - dec_f, 2),
                "level": level.replace("–", "-"),
            })
    seen, uniq = set(), []
    for r in sorted(rows, key=lambda x: x["date"]):
        if r["date"] in seen:
            continue
        seen.add(r["date"])
        uniq.append(r)
    return uniq


# -------------------------------------------------...... 港股指数与 LPR
def _read_cache(path, keys):
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[tuple(row[k] for k in keys)] = row
    return out


def fetch_hk_index():
    """腾讯 ifzq 港股日线 → {code: {date: close}}，带 CSV 缓存。"""
    os.makedirs(RAW, exist_ok=True)
    series, failed = {}, []
    for code, sym, name in HK_SYMBOLS:
        rows = {}
        try:
            r = requests.get(HK_KLINE.format(sym=sym, n=2000),
                             headers={"User-Agent": UA, "Referer": "https://gu.qq.com"},
                             timeout=30)
            r.raise_for_status()
            data = (r.json().get("data") or {}).get(sym) or {}
            for k in ("day", "qfqday"):
                for it in data.get(k) or []:
                    if len(it) >= 3:
                        rows[it[0]] = float(it[2])
                if rows:
                    break
        except Exception as e:
            failed.append(f"{name} {str(e)[:60]}")
        if rows:
            series[code] = rows
            print(f"{name}：{len(rows)} 个交易日 {min(rows)} ~ {max(rows)}")
        else:
            failed.append(f"{name} 无数据")
    if not series:
        raise RuntimeError("；".join(failed) or "港股指数全部失败")

    # 合并旧缓存，避免某次只抓到近期数据时丢掉历史
    seen = set()
    if os.path.exists(HK_CACHE):
        with open(HK_CACHE, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                d = row.get("date")
                if d:
                    seen.add(d)
                    for code, _, _ in HK_SYMBOLS:
                        if row.get(code) not in (None, "", "nan"):
                            series.setdefault(code, {})[d] = float(row[code])
    with open(HK_CACHE, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date"] + [c for c, _, _ in HK_SYMBOLS])
        for d in sorted({d for _, s in series.items() for d in s}):
            w.writerow([d] + [series.get(c, {}).get(d, "") for c, _, _ in HK_SYMBOLS])
    return series


def fetch_lpr(pro):
    """Tushare shibor_lpr 1 年期 → {date: rate}，带缓存。"""
    series = {}
    try:
        df = pro.shibor_lpr(start_date="20180801", end_date=date.today().strftime("%Y%m%d"))
        for _, r in df.iterrows():
            v = r.get("1y")
            if v is not None and str(v) != "nan":
                d = str(r["date"])
                series[f"{d[:4]}-{d[4:6]}-{d[6:8]}"] = float(v)
        print(f"LPR 1Y：{len(series)} 条 {min(series)} ~ {max(series)}")
    except Exception as e:
        print(f"LPR 抓取失败（用缓存）：{str(e)[:80]}")
    if os.path.exists(LPR_CACHE):
        with open(LPR_CACHE, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                series.setdefault(row["date"], float(row["rate"]))
    if series:
        os.makedirs(RAW, exist_ok=True)
        with open(LPR_CACHE, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "rate"])
            for d in sorted(series):
                w.writerow([d, series[d]])
    return series


def _load_daily():
    """data/daily.csv → (dates, hs300, flow)。列名带 BOM，统一 strip。"""
    if not os.path.exists(DAILY_CSV):
        return [], [], []
    dates, hs, fl = [], [], []
    with open(DAILY_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            d = (row.get("日期") or "").strip()
            if not d:
                continue
            dates.append(d)
            hs.append(_f(row.get("沪深300")))
            fl.append(_f(row.get("核心池净申购(亿元)")))
    return dates, hs, fl


def _f(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _next_on_or_after(days, target):
    """days 已排序；返回第一个 >= target 的交易日。"""
    lo, hi = 0, len(days)
    while lo < hi:
        mid = (lo + hi) // 2
        if days[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _next_after(days, target):
    """决议在北京时间凌晨公布，港股当日已收盘，所以要看严格晚于决议日的交易日。"""
    lo, hi = 0, len(days)
    while lo < hi:
        mid = (lo + hi) // 2
        if days[mid] <= target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def build_event_study(meetings, rates, hk, lpr):
    """历次决议后的首个 A 股 / 港股交易日表现，以及中美两侧的利率变动。"""
    days, hs, fl = _load_daily()
    if not days:
        print("daily.csv 不可用，跳过事件研究")
        return []
    hk_days = {c: sorted(s) for c, s in hk.items()}
    lpr_days = sorted(lpr)
    rate_dates = {r["date"]: r for r in rates}

    out = []
    prev_cn = None
    for m in meetings:
        dec = m["end"]
        i = _next_after(days, dec)
        if i >= len(days):
            continue  # 决议日之后还没有 A 股数据

        row = {"date": dec, "trade_date_a": days[i]}

        prev = hs[i - 1] if i > 0 else None
        row["hs300_pct"] = round((hs[i] / prev - 1) * 100, 2) if prev and hs[i] else None
        row["pool_flow"] = fl[i]

        for code, _, _ in HK_SYMBOLS:
            seq = hk_days.get(code) or []
            closes = hk.get(code) or {}
            j = _next_after(seq, dec) if seq else 0
            if not seq or j >= len(seq) or j == 0:
                row[code] = None
                continue
            row[code] = round((closes[seq[j]] / closes[seq[j - 1]] - 1) * 100, 2)
            if code == "HSI":
                row["trade_date_hk"] = seq[j]

        # 美国：这次会议是否调整了目标区间；没有调整就沿用上一次的水平
        rr = rate_dates.get(dec)
        if rr is None:
            near = [r for r in rates if abs((date.fromisoformat(r["date"])
                                             - date.fromisoformat(dec)).days) <= 1]
            rr = near[0] if near else None
        row["us_change_bp"] = rr["change"] if rr else 0.0
        row["us_level"] = rr["level"] if rr else None
        if row["us_level"] is None:
            prior = [r for r in rates if r["date"] <= dec]
            row["us_level"] = prior[-1]["level"] if prior else None

        # 中国：决议日当天有效的 1Y LPR，以及与「上一次 FOMC」之间的变动。
        # 用「期间变动」而不是「最近一次调整」，是为了与美国那一列对称，
        # 也避免同一档 LPR 连续四次会议上都重复显示同一个 bp。
        if lpr_days:
            k = _next_after(lpr_days, dec) - 1
            if k >= 0:
                row["cn_lpr_1y"] = lpr[lpr_days[k]]
                row["cn_between_bp"] = (round((lpr[lpr_days[k]] - prev_cn) * 100, 1)
                                        if prev_cn is not None else None)
                j = k
                while j > 0 and abs(lpr[lpr_days[j - 1]] - lpr[lpr_days[k]]) < 1e-9:
                    j -= 1
                row["cn_lpr_date"] = lpr_days[j]
                prev_cn = lpr[lpr_days[k]]
            else:
                row["cn_lpr_1y"] = row["cn_between_bp"] = row["cn_lpr_date"] = None
        out.append(row)

    print(f"事件研究：{len(out)} 场已开会议")
    return out


def main():
    old = {}
    if os.path.exists(OUT_JSON):
        try:
            old = json.load(open(OUT_JSON, encoding="utf-8"))
        except Exception:
            old = {}

    try:
        cal_html = _get(CAL_URL)
        meetings = parse_calendar(cal_html)
        print(f"会议 {len(meetings)} 场：{meetings[0]['start']} ~ {meetings[-1]['end']}")
    except Exception as e:
        print(f"会议日历抓取失败（保留旧数据）：{str(e)[:120]}")
        meetings = old.get("meetings") or []

    try:
        rate_html = _get(RATE_URL)
        rates = parse_rates(rate_html)
        print(f"利率变动 {len(rates)} 条，最新 {rates[-1] if rates else '—'}")
    except Exception as e:
        print(f"利率表抓取失败（保留旧数据）：{str(e)[:120]}")
        rates = old.get("rates") or []

    if not meetings and not rates:
        print("没有任何数据，退出")
        return 1

    today = date.today().isoformat()
    past = [m for m in meetings if m["end"] < today]
    future = [m for m in meetings if m["end"] >= today]
    for m in meetings:
        m["decision"] = m["end"]

    current = None
    if rates:
        last = rates[-1]
        lo, hi = (last["level"].split("-") + [last["level"]])[:2]
        current = {"level": last["level"], "lower": float(lo), "upper": float(hi), "asof": last["date"]}

    # ---------------- 决议后市场反应（含港股与中美两侧利率） ----------------
    study = old.get("event_study") or []
    try:
        hk = fetch_hk_index()
        try:
            import tushare as ts
            import config
            pro = ts.pro_api(config.TUSHARE_TOKEN)
            pro._DataApi__token = config.TUSHARE_TOKEN
            pro._DataApi__http_url = config.TUSHARE_URL
            lpr = fetch_lpr(pro)
        except Exception as e:
            print(f"Tushare 初始化失败（LPR 用缓存）：{str(e)[:80]}")
            lpr = fetch_lpr(None)
        built = build_event_study(meetings, rates, hk, lpr)
        if built:
            study = built
    except Exception as e:
        print(f"事件研究计算失败（保留旧结果）：{str(e)[:120]}")

    doc = {
        "meta": {
            "generated_at": f"{datetime.now():%Y-%m-%d %H:%M}",
            "source": "Federal Reserve (federalreserve.gov)",
            "hk_source": "腾讯财经 港股日线",
            "lpr_source": "Tushare shibor_lpr（1 年期）",
            "asof": today,
            "next": future[0]["end"] if future else None,
            "days_to_next": (datetime.strptime(future[0]["end"], "%Y-%m-%d").date()
                             - date.today()).days if future else None,
            "past_count": len(past),
            "future_count": len(future),
            "study_count": len(study),
        },
        "meetings": meetings,
        "rates": rates,
        "current": current,
        "event_study": study,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("window.FOMC_DATA=")
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    print(f"\n=== 完成 ===")
    print(f"下次会议 {doc['meta']['next']}（{doc['meta']['days_to_next']} 天后），"
          f"已开 {len(past)} 场 / 待开 {len(future)} 场")
    if current:
        print(f"当前目标区间 {current['level']}%（{current['asof']} 起）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
