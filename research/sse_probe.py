#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSE (Shanghai Stock Exchange) listed ETF daily 规模 / 份额 probe.

Verified facts (2026-11-18, macOS / Python 3.11 / requests 2.31):

1) SSE official daily history  =  query.sse.com.cn/commonQuery.do
   sqlId=COMMON_JJZWZ_JJLB_JJXQ_JJGM_CKLSGM_L   ("基金历史规模", api.js:getScaleList)
   Required params: FUND_CODE=<6 digit>, optional START_DATE / END_DATE in **yyyymmdd**
   (plain digits, no dashes -- that is why 2018-01-01 style returned an empty set).
   Result field SCALE is **基金规模 in 亿元 (AUM)**, NOT 份额/万份.
   Coverage observed: 2020-12-18 .. T-1 (1432 rows for 510300), max pageSize 5000
   returns the whole series in one request.

2) SSE publishes no 份额 (share count) field anywhere for ETFs -- only 亿元 AUM.
   => shares(万份) = SCALE(亿元) * 1e4 / NAV(单位净值), error ~0.02% vs 季报份额
      (validated: 2026-09-30 derived 241.238亿份 vs Eastmoney 季报 241.20亿份).

3) Free daily NAV (2018+): api.fund.eastmoney.com/f10/lsjz  (needs Referer fundf10.eastmoney.com)

4) True 份额 snapshot, whole universe, 1-2 calls:
   datacenter-web.eastmoney.com RPT_FUND_ETFLIST -> DEC_TOTALSHARE (**份**, 1720 ETFs)
   xueqiu quote.json -> total_shares (**份**)

5) Quarterly 份额 back to 2012 (only free 2018-era data):
   fundf10.eastmoney.com/FundArchivesDatas.aspx?type=gmbd  (期末总份额 亿份)

Usage:
  python sse_probe.py --code 510300 --start 20201218 --end 20261117 \
      --out research/sse_sample.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from typing import Any

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SSE_URL = "https://query.sse.com.cn/commonQuery.do"
SSE_SQL_SCALE_HIST = "COMMON_JJZWZ_JJLB_JJXQ_JJGM_CKLSGM_L"
SSE_HEADERS = {
    "User-Agent": UA,
    # Referer must be an sse.com.cn host, otherwise ExceptionInterceptor
    "Referer": "https://etf.sse.com.cn/",
    "Accept": "*/*",
}

EM_NAV_URL = "https://api.fund.eastmoney.com/f10/lsjz"
EM_HEADERS = {"User-Agent": UA, "Referer": "https://fundf10.eastmoney.com/"}
EM_DC_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EM_Gmbd_URL = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"


# --------------------------------------------------------------------------- #
# SSE
# --------------------------------------------------------------------------- #
def _get(url: str, headers: dict, params: dict, retries: int = 3,
         timeout: int = 40) -> requests.Response:
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"request failed: {last}")


def sse_scale_history(code: str, start: str | None = None,
                      end: str | None = None, page_size: int = 5000) -> list[dict]:
    """Daily 基金规模 (亿元) for one SSE ETF, ascending by date.

    start / end: 'YYYYMMDD' (digits only). Omit for full available history.
    """
    params: dict[str, Any] = {
        "isPagination": "true",
        "sqlId": SSE_SQL_SCALE_HIST,
        "FUND_CODE": code,
        "pageHelp.pageSize": str(page_size),
        "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1",
        "pageHelp.cacheSize": "1",
        "pageHelp.endPage": "1",
    }
    if start:
        params["START_DATE"] = start.replace("-", "")
    if end:
        params["END_DATE"] = end.replace("-", "")

    js = _get(SSE_URL, SSE_HEADERS, params).json()
    if js.get("error"):
        raise RuntimeError(f"SSE error: {js['error']}")

    rows = []
    for x in js.get("result") or []:
        try:
            scale = float(x["SCALE"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({
            "trade_date": x["TRADE_DATE"],
            "fund_code": x["FUND_CODE"],
            "fund_abbr": x.get("FUND_ABBR"),
            "fund_name": x.get("FUND_EXPANSION_ABBR"),
            "scale_yi": scale,          # 亿元 AUM
        })
    rows.sort(key=lambda r: r["trade_date"])
    return rows


# --------------------------------------------------------------------------- #
# Eastmoney helpers
# --------------------------------------------------------------------------- #
def em_nav_history_fast(code: str) -> dict[str, float]:
    """Whole 单位净值 history from one request (~0.5 MB, 2-3 s)."""
    from datetime import datetime, timedelta, timezone
    r = _get(f"https://fund.eastmoney.com/pingzhongdata/{code}.js",
             {"User-Agent": UA, "Referer": "https://fund.eastmoney.com/"},
             {}, timeout=60)
    m = re.search(r"Data_netWorthTrend\s*=\s*(\[.*?\]);", r.text, re.S)
    if not m:
        return {}
    out: dict[str, float] = {}
    tz = timezone(timedelta(hours=8))
    for pt in json.loads(m.group(1)):
        try:
            d = datetime.fromtimestamp(pt["x"] / 1000, tz).strftime("%Y-%m-%d")
            out[d] = float(pt["y"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def em_nav_history(code: str, start: str, end: str) -> dict[str, float]:
    """单位净值 by date (YYYY-MM-DD). Works back to 2018 (and earlier)."""
    fast = em_nav_history_fast(code)
    if fast:
        return {d: v for d, v in fast.items() if start <= d <= end}
    # NOTE: api.fund.eastmoney.com/f10/lsjz caps a page at 20 rows regardless of
    # the pageSize asked for, so page until an empty/short page comes back.
    navs: dict[str, float] = {}
    page = 1
    while page <= 400:
        js = _get(EM_NAV_URL, EM_HEADERS, {
            "fundCode": code, "pageIndex": str(page), "pageSize": "20",
            "startDate": start, "endDate": end,
        }).json()
        data = ((js.get("Data") or {}).get("LSJZList") or [])
        if not data:
            break
        before = len(navs)
        for x in data:
            try:
                navs[x["FSRQ"]] = float(x["DWJZ"])
            except (KeyError, TypeError, ValueError):
                pass
        # past the requested window, or a page that added nothing new
        if len(data) < 20 or len(navs) == before or min(navs) <= start:
            break
        page += 1
        time.sleep(0.1)
    return navs


def em_etf_universe(page_size: int = 1000) -> list[dict]:
    """Whole ETF universe snapshot: DEC_TOTALSHARE in 份 (= 万份 * 1e4)."""
    out, page = [], 1
    while True:
        js = _get(EM_DC_URL, {"User-Agent": UA, "Referer": "https://data.eastmoney.com/"},
                  {"reportName": "RPT_FUND_ETFLIST",
                   "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,DEC_TOTALSHARE,DEC_NAV",
                   "pageNumber": str(page), "pageSize": str(page_size),
                   "source": "WEB", "client": "WEB"}).json()
        res = js.get("result") or {}
        data = res.get("data") or []
        if not data:
            break
        for x in data:
            shares = x.get("DEC_TOTALSHARE")
            out.append({
                "fund_code": x.get("SECURITY_CODE"),
                "fund_name": x.get("SECURITY_NAME_ABBR"),
                "shares_wan": round(shares / 1e4, 2) if shares else None,  # 万份
            })
        if len(out) >= (res.get("count") or 0) or len(data) < page_size:
            break
        page += 1
        time.sleep(0.3)
    return out


def em_quarterly_shares(code: str) -> list[dict]:
    """季报 期末总份额 (亿份) -- the only free 2018-era 份额 history found."""
    r = _get(EM_Gmbd_URL, {"User-Agent": UA,
                           "Referer": f"https://fundf10.eastmoney.com/gmbd_{code}.html"},
             {"type": "gmbd", "mode": "0", "code": code, "rt": str(time.time())})
    pat = (r"<tr><td>(\d{4}-\d{2}-\d{2})</td><td[^>]*>([\d,\.\-]+)</td>"
           r"<td[^>]*>([\d,\.\-]+)</td><td[^>]*>([\d,\.\-]+)</td><td[^>]*>([\d,\.\-]+)</td>")
    rows = []
    for d, _buy, _sell, end_share, end_asset in re.findall(pat, r.text):
        try:
            rows.append({
                "period_end": d,
                "shares_yi": float(end_share.replace(",", "")),      # 期末总份额 亿份
                "net_assets_yi": float(end_asset.replace(",", "")),   # 期末净资产 亿元
            })
        except ValueError:
            continue
    rows.sort(key=lambda x: x["period_end"], reverse=True)
    return rows


def xueqiu_snapshot(codes: list[str]) -> list[dict]:
    """True 份额 snapshot (份). Symbol form: SH510300."""
    s = requests.Session()
    hdr = {"User-Agent": UA}
    s.get("https://xueqiu.com/", headers=hdr, timeout=25)  # sets xq_a_token cookie
    out = []
    for sym in codes:
        try:
            q = s.get(f"https://stock.xueqiu.com/v5/stock/quote.json?symbol={sym}&extend=detail",
                      headers={**hdr, "Referer": f"https://xueqiu.com/S/{sym}"},
                      timeout=25).json()["data"]["quote"]
            out.append({
                "symbol": sym,
                "fund_name": q.get("name"),
                "shares_wan": round(q["total_shares"] / 1e4, 2),
                "unit_nav": q.get("unit_nav"),
                "ts": q.get("timestamp"),
            })
        except Exception as exc:  # noqa: BLE001
            out.append({"symbol": sym, "error": repr(exc)})
        time.sleep(0.3)
    return out


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="510300")
    ap.add_argument("--start", default="20201218")
    ap.add_argument("--end", default=time.strftime("%Y%m%d"))
    ap.add_argument("--out", default="research/sse_sample.json")
    a = ap.parse_args()

    code = a.code
    print(f"[1/4] SSE scale history {code} {a.start}..{a.end}", file=sys.stderr)
    scale = sse_scale_history(code, a.start, a.end)
    print(f"      {len(scale)} rows  {scale[0]['trade_date']} .. {scale[-1]['trade_date']}",
          file=sys.stderr)

    print("[2/4] Eastmoney NAV history", file=sys.stderr)
    navs = em_nav_history(code, f"{a.start[:4]}-{a.start[4:6]}-{a.start[6:]}",
                          f"{a.end[:4]}-{a.end[4:6]}-{a.end[6:]}")
    print(f"      {len(navs)} nav rows", file=sys.stderr)

    print("[3/4] deriving 份额 (万份) = scale_yi * 1e4 / nav", file=sys.stderr)
    merged = []
    for r in scale:
        nav = navs.get(r["trade_date"])
        merged.append({**r,
                       "nav": nav,
                       "shares_wan": round(r["scale_yi"] * 1e4 / nav, 2) if nav else None})

    print("[4/4] snapshots + 2018 quarterly reference", file=sys.stderr)
    quarterly = em_quarterly_shares(code)

    # extra evidence: 2018 is outside the SSE retention window
    try:
        probe18 = _get(SSE_URL, SSE_HEADERS, {
            "isPagination": "true", "sqlId": SSE_SQL_SCALE_HIST, "FUND_CODE": code,
            "START_DATE": "20180101", "END_DATE": "20180110",
            "pageHelp.pageSize": "10", "pageHelp.pageNo": "1",
        }).json()
        probe18 = {"request": f"FUND_CODE={code}&START_DATE=20180101&END_DATE=20180110",
                   "total": (probe18.get("pageHelp") or {}).get("total"),
                   "result": probe18.get("result")}
    except Exception as exc:  # noqa: BLE001
        probe18 = {"error": repr(exc)}

    # accuracy of the derived 份额 against 季报 期末总份额
    by_date = {r["trade_date"]: r for r in merged}
    acc = []
    for q in quarterly:
        d = q["period_end"]
        row = by_date.get(d)
        if row and row["shares_wan"]:
            ref_wan = q["shares_yi"] * 1e4
            acc.append({"period_end": d,
                        "derived_wan": row["shares_wan"],
                        "reported_wan": round(ref_wan, 2),
                        "diff_pct": round((row["shares_wan"] - ref_wan) / ref_wan * 100, 3)})

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "endpoint": {
            "url": "https://query.sse.com.cn/commonQuery.do",
            "sqlId": SSE_SQL_SCALE_HIST,
            "method": "GET",
            "required_headers": {"Referer": "https://etf.sse.com.cn/", "User-Agent": "<browser UA>"},
            "params": {
                "isPagination": "true",
                "sqlId": SSE_SQL_SCALE_HIST,
                "FUND_CODE": code,
                "START_DATE": "YYYYMMDD (digits only)",
                "END_DATE": "YYYYMMDD (digits only)",
                "pageHelp.pageSize": "5000 (max; returns full series in one call)",
                "pageHelp.pageNo": "1",
                "pageHelp.beginPage": "1",
                "pageHelp.cacheSize": "1",
                "pageHelp.endPage": "1",
            },
            "notes": "SCALE = 基金规模 in 亿元 (AUM); no 份额 field exists on SSE.",
        },
        "coverage": {"first_trade_date": scale[0]["trade_date"] if scale else None,
                     "last_trade_date": scale[-1]["trade_date"] if scale else None,
                     "rows": len(scale)},
        "sample_rows_raw_sse": scale[-3:],                      # newest 3 raw SSE rows
        "sample_rows_derived": merged[-3:],                     # + nav + shares_wan
        "earliest_available_row": scale[0] if scale else None,
        "sse_2018_probe": probe18,
        "eastmoney_quarterly_2018": [r for r in quarterly
                                     if r["period_end"].startswith(("2018", "2019"))],
        "derived_accuracy_vs_quarterly": acc,
        "snapshot_true_shares": xueqiu_snapshot(["SH510300", "SH510050", "SH510500",
                                                 "SH512100", "SH588000"]),
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"wrote {a.out}", file=sys.stderr)

    for r in merged[-3:]:
        print(f"  {r['trade_date']}  scale={r['scale_yi']:>10.4f}亿  "
              f"nav={r['nav']}  shares={r['shares_wan']}万份")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
