#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 FOMC 会议日历与联邦基金目标利率，生成 data/fomc_data.js。

数据源（官方，权威且稳定）：
- https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm  会议日程 + 纪要日期
- https://www.federalreserve.gov/monetarypolicy/openmarket.htm      目标利率变动表

只做两件事：解析 + 落盘。抓取失败时保留旧数据，不影响主看板发布。
    python3 fetch_fomc.py
"""
import json
import os
import re
import sys
from datetime import date, datetime

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT_JSON = os.path.join(DATA, "fomc_data.json")
OUT_JS = os.path.join(DATA, "fomc_data.js")

CAL_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
RATE_URL = "https://www.federalreserve.gov/monetarypolicy/openmarket.htm"
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

    doc = {
        "meta": {
            "generated_at": f"{datetime.now():%Y-%m-%d %H:%M}",
            "source": "Federal Reserve (federalreserve.gov)",
            "asof": today,
            "next": future[0]["end"] if future else None,
            "days_to_next": (datetime.strptime(future[0]["end"], "%Y-%m-%d").date()
                             - date.today()).days if future else None,
            "past_count": len(past),
            "future_count": len(future),
        },
        "meetings": meetings,
        "rates": rates,
        "current": current,
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
