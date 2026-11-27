#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""港股与南向资金 → data/hk_data.js / data/hk.csv

数据源（均已实测）：
- 腾讯 ifzq 港股日线       恒生指数 / 恒生科技，含恒指成交额（字段 5，单位港币）
- Tushare ggt_daily        港股通每日买入额/卖出额（亿元），2017-01 起 2264 个交易日
- Tushare ggt_top10        港股通十大成交股，含沪港通/深港通两侧净买入额
- 新浪财经 rt_hkHSAHP      AH 溢价指数（只有实时，无历史）

口径说明：
- 南向净买入 = ggt_daily 的 buy_amount − sell_amount。这是成交口径直接相减，
  不受 2024-08 官方停止披露「净买入」的影响（北向那条 moneyflow_hsgt 从此改了口径）。
- 南向成交占比 =（买入额 + 卖出额）/ 恒指成交额。两者币种口径若不同，会有约 8%
  的常数偏移，趋势可用、绝对水平仅供参考，页面上如实标注。
    python3 fetch_hk.py
"""
import csv
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT_JSON = os.path.join(DATA, "hk_data.json")
OUT_JS = os.path.join(DATA, "hk_data.js")
OUT_CSV = os.path.join(DATA, "hk.csv")

# 腾讯单次最多返回 2000 条，超过就直接返回空数组（实测 n=2400 时 body 只有 39 字节）。
# 第 4 个参数是结束日期，靠它往前翻页才能拿到 2017 年以前的历史。
HK_KLINE = ("https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get"
            "?param={sym},day,,{end},{n},qfq")
HK_SINCE = "2016-12-01"
SINA_AH = "https://hq.sinajs.cn/list=rt_hkHSAHP"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

INDICES = [("HSI", "hkHSI", "恒生指数"), ("HSTECH", "hkHSTECH", "恒生科技")]


def _get(url, referer="https://gu.qq.com", tries=3, timeout=30, gbk=False):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Referer": referer}, timeout=timeout)
            if r.status_code in (429, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.content.decode("gbk", "ignore") if gbk else r.text
        except Exception as e:
            last = e
            if i < tries - 1:
                time.sleep(4 * (2 ** i))
    raise last


def _num(v):
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------ 港股指数
def _one_page(sym, end):
    """取 end 之前最近 2000 条日线；返回 {date: {close, amount}}。"""
    url = HK_KLINE.format(sym=sym, end=end or "", n=2000)
    block = (json.loads(_get(url)).get("data") or {}).get(sym) or {}
    rows = {}
    for key in ("day", "qfqday"):
        for it in block.get(key) or []:
            if len(it) < 6:
                continue
            amt = None
            v = _num(it[5])
            if v and v > 0:
                amt = round(v / 1e8, 1)          # 港币 → 亿
            rows[it[0]] = {"close": round(float(it[2]), 2), "amount": amt}
    return rows


def fetch_indices():
    """{code: {date: {close, amount}}}；amount 为成交额（亿港元），恒指有、恒生科技无。"""
    out = {}
    for code, sym, name in INDICES:
        rows, end, pages = {}, "", 0
        try:
            while pages < 6:
                page = _one_page(sym, end)
                if not page:
                    break
                new = {k: v for k, v in page.items() if k not in rows}
                rows.update(new)
                pages += 1
                if not new or min(rows) <= HK_SINCE:
                    break
                # 上一页的结束日 = 本页最早一天的前一天
                y, m, d = (int(x) for x in min(rows).split("-"))
                end = (date(y, m, d) - timedelta(days=1)).isoformat()
                time.sleep(1)
            if not rows:
                raise RuntimeError("空数据")
            out[code] = rows
            print(f"{name}：{len(rows)} 个交易日 {min(rows)} ~ {max(rows)}（{pages} 页）")
        except Exception as e:
            print(f"{name} 抓取失败：{str(e)[:80]}")
    return out


# ------------------------------------------------------------ 南向资金
def fetch_southbound(pro):
    import pandas as pd
    frames = []
    for y in range(2017, date.today().year + 1):
        for attempt in range(3):
            try:
                df = pro.ggt_daily(start_date=f"{y}0101", end_date=f"{y}1231")
                if len(df):
                    frames.append(df)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  ggt_daily {y} 失败：{str(e)[:60]}")
                time.sleep(3 * (attempt + 1))
        time.sleep(0.4)
    if not frames:
        raise RuntimeError("ggt_daily 全部失败")
    d = pd.concat(frames)
    d["trade_date"] = d["trade_date"].astype(str)
    for c in ("buy_amount", "sell_amount"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.drop_duplicates("trade_date").dropna(subset=["buy_amount", "sell_amount"])
    d = d.sort_values("trade_date").reset_index(drop=True)
    d["net"] = (d["buy_amount"] - d["sell_amount"]).round(2)
    print(f"南向：{len(d)} 个交易日 {d['trade_date'].min()} ~ {d['trade_date'].max()}")
    return d


def fetch_top10(pro):
    """港股通十大成交股。market_type 2=沪港通、4=深港通，净买入分落在 sh_/sz_ 列。"""
    for back in range(0, 8):
        td = date.fromordinal(date.today().toordinal() - back).strftime("%Y%m%d")
        try:
            df = pro.ggt_top10(trade_date=td)
        except Exception:
            time.sleep(1.5)
            continue
        if not len(df):
            continue
        agg = {}
        for _, r in df.iterrows():
            code = str(r.get("ts_code") or "")
            if not code:
                continue
            cur = agg.setdefault(code, {
                "code": code, "name": r.get("name") or code,
                "close": _num(r.get("close")), "chg": _num(r.get("p_change")),
                "net": 0.0, "turnover": 0.0, "rank": 99,
            })
            for side in ("sh_net_amount", "sz_net_amount"):
                v = _num(r.get(side))
                if v is not None:
                    cur["net"] += v / 1e8
            for side in ("sh_amount", "sz_amount"):
                v = _num(r.get(side))
                if v is not None:
                    cur["turnover"] += v / 1e8
            rk = _num(r.get("rank"))
            if rk is not None:
                cur["rank"] = min(cur["rank"], int(rk))
        rows = sorted(agg.values(), key=lambda x: -x["net"])
        for r in rows:
            r["net"] = round(r["net"], 2)
            r["turnover"] = round(r["turnover"], 2)
            r["rank"] = None if r["rank"] == 99 else r["rank"]
            # p_change 是绝对涨跌额（港元），换算成百分比
            prev = (r["close"] - r["chg"]) if (r["close"] is not None and r["chg"] is not None) else None
            r["pct"] = round(r["chg"] / prev * 100, 2) if prev else None
            r.pop("chg", None)
        if rows:
            print(f"十大成交股：{td} 共 {len(rows)} 只")
            return td, rows
    print("十大成交股：近期均无数据")
    return None, []


def fetch_ah():
    """AH 溢价指数：新浪只有实时快照。字段 6=现价、8=涨跌幅、17/18=日期时间。"""
    try:
        txt = _get(SINA_AH, referer="https://finance.sina.com.cn", gbk=True)
        body = txt.split('"')[1] if '"' in txt else ""
        f = body.split(",")
        if len(f) < 9:
            return None, None, None
        return (round(float(f[6]), 2), round(float(f[8]), 2),
                (f[17] + " " + f[18]) if len(f) > 18 else None)
    except Exception as e:
        print(f"AH 溢价抓取失败：{str(e)[:70]}")
        return None, None, None


def main():
    import tushare as ts
    import config

    pro = ts.pro_api(config.TUSHARE_TOKEN)
    pro._DataApi__token = config.TUSHARE_TOKEN
    pro._DataApi__http_url = config.TUSHARE_URL

    idx = fetch_indices()
    south = fetch_southbound(pro)
    top_date, top10 = fetch_top10(pro)
    ah, ah_chg, ah_at = fetch_ah()

    # 以港股通交易日为主轴：南向只在两地同时开市时才有数据
    # ggt_daily 的日期是 YYYYMMDD，腾讯是 YYYY-MM-DD，先统一再对齐
    dates = [f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in south["trade_date"]]
    hsi, hstech, amt, buy, sell, net = [], [], [], [], [], []
    last_hsi = last_hstech = None
    for i, d in enumerate(dates):
        a = (idx.get("HSI") or {}).get(d)
        b = (idx.get("HSTECH") or {}).get(d)
        if a:
            last_hsi = a
        if b:
            last_hstech = b
        hsi.append(last_hsi["close"] if last_hsi else None)
        hstech.append(last_hstech["close"] if last_hstech else None)
        amt.append(last_hsi.get("amount") if last_hsi else None)
        buy.append(round(float(south["buy_amount"].iloc[i]), 2))
        sell.append(round(float(south["sell_amount"].iloc[i]), 2))
        net.append(round(float(south["net"].iloc[i]), 2))

    cum, run = [], 0.0
    for v in net:
        run += v
        cum.append(round(run, 1))
    net20 = []
    for i in range(len(net)):
        w = net[max(0, i - 19):i + 1]
        net20.append(round(sum(w), 1) if len(w) == 20 else None)
    share = [round((buy[i] + sell[i]) / amt[i] * 100, 2) if amt[i] else None
             for i in range(len(net))]

    doc = {
        "meta": {
            "generated_at": f"{datetime.now():%Y-%m-%d %H:%M}",
            "asof": dates[-1],
            "sources": {
                "index": "腾讯财经 港股日线",
                "south": "Tushare ggt_daily（港股通买入/卖出额）",
                "top10": "Tushare ggt_top10",
                "ah": "新浪财经 rt_hkHSAHP（仅实时）",
            },
            "ah": ah, "ah_chg": ah_chg, "ah_at": ah_at,
            "top10_date": top_date,
            "from": dates[0], "days": len(dates),
            "south_20d": net20[-1],
            "south_ytd": round(sum(v for d, v in zip(dates, net) if d[:4] == dates[-1][:4]), 1),
            "share_last": share[-1],
        },
        "dates": dates, "hsi": hsi, "hstech": hstech, "hk_turnover": amt,
        "buy": buy, "sell": sell, "net": net, "cum": cum,
        "net20": net20, "share": share, "top10": top10,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("window.HK_DATA=")
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["日期", "恒生指数", "恒生科技", "恒指成交额(亿港元)",
                    "南向买入(亿)", "南向卖出(亿)", "南向净买入(亿)",
                    "南向累计净买入(亿)", "南向20日净买入(亿)", "南向成交占比(%)"])
        for i, d in enumerate(dates):
            w.writerow([d, hsi[i], hstech[i], amt[i], buy[i], sell[i],
                        net[i], cum[i], net20[i], share[i]])

    print("\n=== 完成 ===")
    print(f"区间 {dates[0]} ~ {dates[-1]}（{len(dates)} 个交易日）")
    print(f"最新 恒指 {hsi[-1]} / 恒生科技 {hstech[-1]}；"
          f"南向净买入 {net[-1]} 亿，20日 {net20[-1]} 亿，年内 {doc['meta']['south_ytd']} 亿")
    if ah:
        print(f"AH 溢价 {ah}（{ah_chg:+.2f}%，{ah_at}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
