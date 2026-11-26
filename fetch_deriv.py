#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""衍生品/两融数据管线 → data/deriv_data.json / .js / basis.csv / crowding.csv

两块内容：
1. 基差：IF/IH/IC/IM 主力合约的年化基差（含期限结构、IM−IF 价差）
2. 拥挤度：核心池 ETF 的融资/融券余额、期货持仓量、全市场两融余额

设计原则：本脚本失败不应影响主看板发布，因此 run_update.py 里做降级处理。
    python3 fetch_deriv.py            # 增量
    python3 fetch_deriv.py --force    # 全量重抓（首次或修数据时用）
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

import pandas as pd

import config
import deriv_source as ds
import tushare_source as ts

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
MAIN_DATA = os.path.join(DATA, "dashboard_data.json")

START = getattr(config, "DERIV_START", "2023-01-01")


def _r(v, n=2):
    if v is None or (isinstance(v, float) and (pd.isna(v) or v in (float("inf"), float("-inf")))):
        return None
    return round(float(v), n)


def build_basis(force=False):
    """主力合约年化基差。主力 = 当日持仓量最大的合约。"""
    out = {}
    all_dates = set()
    for prod, meta in ds.FUT_PRODUCTS.items():
        spot = ds.index_close(meta["index"]).rename(columns={"close": "spot"})
        if not len(spot):
            print(f"   [basis] {prod} 缺少现货序列，跳过")
            continue
        contracts = ds.fetch_contracts(prod, START)
        if not len(contracts):
            continue
        expiry = dict(zip(contracts["ts_code"], contracts["delist_date"]))

        frames = []
        # 已摘牌超过 5 天的合约不会再有新数据：只读缓存，完全不发请求
        cutoff = (pd.Timestamp.today() - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
        # delist_date 是 YYYYMMDD，必须先格式化再比较，否则会误判为全部“未到期”
        delist = pd.to_datetime(contracts["delist_date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
        live = set(contracts.loc[delist >= cutoff, "ts_code"])
        calls = 0
        for i, code in enumerate(contracts["ts_code"]):
            cache = os.path.join(ds.RAW, f"fut_{code.replace('.', '_')}.csv")
            try:
                if not force and code not in live and os.path.exists(cache):
                    df = pd.read_csv(cache)
                else:
                    df = ds.fetch_fut_daily(code, START, force=force)
                    calls += 1
            except Exception as e:
                print(f"   [basis] {code} 抓取失败 {str(e)[:60]}")
                continue
            if len(df):
                df = df.copy()
                df["code"] = code
                df["delist"] = expiry.get(code)
                frames.append(df[["date", "code", "close", "settle", "oi", "delist"]])
            if i % 20 == 19:
                print(f"   [basis] {prod} {i + 1}/{len(contracts)}")
        if not frames:
            continue
        long = pd.concat(frames, ignore_index=True)
        long = long.merge(spot, on="date", how="inner")
        if long.empty:
            continue
        long["dte"] = (pd.to_datetime(long["delist"]) - pd.to_datetime(long["date"])).dt.days
        long = long[(long["dte"] > 0) & long["spot"].gt(0)]
        long["basis_pct"] = (long["close"] - long["spot"]) / long["spot"] * 100
        long["basis_ann"] = long["basis_pct"] * 365 / long["dte"]

        # 每日按持仓量取主力 + 次主力
        rows = []
        for d, g in long.groupby("date"):
            g = g.sort_values("oi", ascending=False)
            if not len(g):
                continue
            top = g.iloc[0]
            nxt = g.iloc[1] if len(g) > 1 else None
            rows.append({
                "date": d,
                "basis_ann": _r(top["basis_ann"]),
                "basis_pct": _r(top["basis_pct"]),
                "dte": int(top["dte"]),
                "oi": _r(top["oi"], 0),
                "code": top["code"],
                "next_ann": _r(nxt["basis_ann"]) if nxt is not None else None,
                "next_code": nxt["code"] if nxt is not None else None,
            })
        s = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        out[prod] = s
        all_dates |= set(s["date"])
        print(f"   [basis] {prod} {len(s)} 个交易日，年化基差 {s['basis_ann'].iloc[-1]:+.2f}%（API {calls} 次，其余读缓存）")

    return out


def build_crowding(payload):
    """核心池 ETF 两融余额 + 期货持仓量。金额统一为亿元。"""
    core = [e for e in payload["etfs"] if e.get("tier") == 1]
    frames, meta = [], []
    for e in core:
        try:
            df = ds.fetch_margin(e["code"], e["ex"], START)
        except Exception as ex:
            print(f"   [crowd] {e['code']} 两融抓取失败 {str(ex)[:60]}")
            continue
        if not len(df):
            continue
        f = df[["date", "rzye", "rqye"]].copy()
        f["code"] = e["code"]
        frames.append(f)
        meta.append(e)

    if not frames:
        return None
    long = pd.concat(frames, ignore_index=True)
    long["rzye_yi"] = pd.to_numeric(long["rzye"], errors="coerce") / 1e8
    long["rqye_yi"] = pd.to_numeric(long["rqye"], errors="coerce") / 1e8

    agg = long.groupby("date", as_index=False)[["rzye_yi", "rqye_yi"]].sum().sort_values("date")

    # 对齐核心池规模（%）
    aum = pd.DataFrame({"date": payload["dates"], "aum": payload["total"]["aum"]}).dropna()
    agg = agg.merge(aum, on="date", how="left")
    agg["rz_pct"] = agg["rzye_yi"] / agg["aum"] * 100

    market = pd.DataFrame()
    try:
        market = ds.fetch_market_margin(START)
    except Exception as ex:
        print(f"   [crowd] 全市场两融失败 {str(ex)[:60]}")
    if len(market):
        market = market.assign(mkt_rzye=pd.to_numeric(market["rzye"], errors="coerce") / 1e8)
        agg = agg.merge(market[["date", "mkt_rzye"]], on="date", how="left")
    else:
        agg["mkt_rzye"] = None

    # 个股截面（最新一天）
    last_day = agg["date"].iloc[-1]
    snap = long[long["date"] == last_day].groupby("code", as_index=False)[["rzye_yi", "rqye_yi"]].sum()
    rows = []
    for e in meta:
        row = snap[snap["code"] == e["code"]]
        if not len(row):
            continue
        rz = _r(row["rzye_yi"].iloc[0], 2)
        rq = _r(row["rqye_yi"].iloc[0], 2)
        aum_last = e.get("aum_last")
        rows.append({
            "code": e["code"], "name": e["name"], "family": e["family"],
            "rz": rz, "rq": rq, "aum": aum_last,
            "rz_pct": _r(rz / aum_last * 100, 2) if rz is not None and aum_last else None,
            "f20pct": e.get("f20pct"),
        })
    rows.sort(key=lambda x: -(x["rz"] or 0))
    return {"series": agg, "etfs": rows, "asof": last_day}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略缓存全量重抓")
    args = ap.parse_args()

    if not ts.enabled():
        print("TUSHARE_TOKEN 未配置，跳过衍生品数据")
        return 1
    if not os.path.exists(MAIN_DATA):
        print("缺少 data/dashboard_data.json，先跑 fetch_data.py")
        return 1

    t0 = time.time()
    print(f"=== 衍生品数据 {datetime.now():%Y-%m-%d %H:%M} ===")
    payload = json.load(open(MAIN_DATA, encoding="utf-8"))

    print("[1/2] 股指期货基差 …")
    basis = build_basis(force=args.force)

    print("[2/2] 两融与持仓 …")
    crowd = build_crowding(payload)

    dates = sorted({d for s in basis.values() for d in s["date"]}) if basis else []
    doc = {
        "meta": {
            "generated_at": f"{datetime.now():%Y-%m-%d %H:%M}",
            "start": dates[0] if dates else None,
            "end": dates[-1] if dates else None,
            "products": list(basis.keys()),
            "note": "期权持仓量因 Tushare opt_daily 单次返回上限 15000 行且标的过滤失效，未纳入",
        },
        "dates": dates,
        "basis": {p: {
            "ann": [s.set_index("date")["basis_ann"].get(d) for d in dates],
            "pct": [s.set_index("date")["basis_pct"].get(d) for d in dates],
            "oi": [s.set_index("date")["oi"].get(d) for d in dates],
            "next": [s.set_index("date")["next_ann"].get(d) for d in dates],
        } for p, s in basis.items()},
        "latest_basis": {p: s.iloc[-1].to_dict() for p, s in basis.items()},
    }

    if crowd is not None:
        agg = crowd["series"]
        cdates = list(agg["date"])
        doc["crowding"] = {
            "dates": cdates,
            "asof": crowd["asof"],
            "rz": [_r(v, 2) for v in agg["rzye_yi"]],
            "rq": [_r(v, 2) for v in agg["rqye_yi"]],
            "rz_pct": [_r(v, 3) for v in agg["rz_pct"]],
            "aum": [_r(v, 1) for v in agg["aum"]],
            "mkt_rz": [_r(v, 1) for v in agg["mkt_rzye"]],
            "etfs": crowd["etfs"],
        }

    # IM − IF 年化基差价差（小盘相对大盘的对冲成本）
    if "IM" in doc["basis"] and "IF" in doc["basis"]:
        im, iff = doc["basis"]["IM"]["ann"], doc["basis"]["IF"]["ann"]
        doc["spread_im_if"] = [None if a is None or b is None else round(a - b, 2) for a, b in zip(im, iff)]

    with open(os.path.join(DATA, "deriv_data.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA, "deriv_data.js"), "w", encoding="utf-8") as f:
        f.write("window.DERIV_DATA=")
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    if basis:
        bdf = pd.DataFrame({"日期": dates})
        for p, s in basis.items():
            m = s.set_index("date")
            bdf[f"{p}年化基差(%)"] = [m["basis_ann"].get(d) for d in dates]
            bdf[f"{p}持仓量(手)"] = [m["oi"].get(d) for d in dates]
        bdf.to_csv(os.path.join(DATA, "basis.csv"), index=False, encoding="utf-8-sig")
    if crowd is not None:
        pd.DataFrame(crowd["etfs"]).to_csv(os.path.join(DATA, "crowding.csv"), index=False, encoding="utf-8-sig")

    print(f"\n=== 完成 {time.time() - t0:.0f}s ===")
    print(f"基差区间 {doc['meta']['start']} ~ {doc['meta']['end']}，品种 {list(basis.keys())}")
    if basis:
        for p, s in basis.items():
            r = s.iloc[-1]
            print(f"  {p}: {r['code']} 年化 {r['basis_ann']:+.2f}%  剩 {r['dte']} 天  OI {r['oi']:,.0f}")
    if crowd is not None:
        e = crowd["series"].iloc[-1]
        print(f"  核心池融资余额 {e['rzye_yi']:,.1f} 亿（占规模 {e['rz_pct']:.2f}%），融券 {e['rqye_yi']:,.1f} 亿")
    return 0


if __name__ == "__main__":
    sys.exit(main())
