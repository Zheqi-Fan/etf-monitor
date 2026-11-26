# -*- coding: utf-8 -*-
"""衍生品与两融数据适配器（Tushare）。

三个子域：
1. 股指期货日线 —— 用于年化基差与对冲成本（IF/IH/IC/IM）
2. ETF 融资融券明细 —— 用于杠杆/反向头寸拥挤度
3. 全市场两融余额 —— 作为风险偏好背景

各接口都带本地 CSV 缓存，日常增量只补最近窗口。
失败一律抛异常，由调用方决定是否降级（页面显示"未更新"而不是崩溃）。
"""
import os
from datetime import date, timedelta

import pandas as pd

import config
import tushare_source as ts

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw")
os.makedirs(RAW, exist_ok=True)

# 期货品种 → 对应现货指数（TS_INDEX 里已有）
FUT_PRODUCTS = {
    "IF": {"name": "沪深300", "index": "000300"},
    "IH": {"name": "上证50", "index": "000016"},
    "IC": {"name": "中证500", "index": "000905"},
    "IM": {"name": "中证1000", "index": "000852"},
}

TS_CODE = {
    "000300": "000300.SH", "000016": "000016.SH",
    "000905": "000905.SH", "000852": "000852.SH",
}


def _ymd(d):
    return pd.to_datetime(d).strftime("%Y%m%d")


def _read(path, cols):
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            if len(df):
                return df
        except Exception:
            pass
    return pd.DataFrame(columns=cols)


def _merge_write(path, old, new, subset=("date",), sort="date"):
    df = pd.concat([old, new], ignore_index=True) if len(old) else new
    df = df.drop_duplicates(subset=list(subset)).sort_values(sort)
    df.to_csv(path, index=False)
    return df


# ---------------------------------------------------------------- 期货合约
def fetch_contracts(prefix, window_start):
    """某品种在 window_start 之后仍有交易的合约清单（按月，约 3-4 个/月）。"""
    path = os.path.join(RAW, f"fut_basic_{prefix}.csv")
    old = _read(path, ["ts_code", "symbol", "name", "list_date", "delist_date"])
    df = ts._query(
        "fut_basic",
        {"exchange": "CFFEX", "fut_type": "1"},
        "ts_code,symbol,name,list_date,delist_date",
    )
    df = df[df["ts_code"].str.startswith(prefix)].copy()
    df = df[df["delist_date"] >= _ymd(window_start)]
    df = df.sort_values("delist_date").reset_index(drop=True)
    if len(df):
        df.drop_duplicates(subset=["ts_code"]).sort_values("delist_date").to_csv(path, index=False)
    return df


def fetch_fut_daily(ts_code_, start, end=None, force=False):
    """单合约日线（收盘/结算/持仓量）。"""
    path = os.path.join(RAW, f"fut_{ts_code_.replace('.', '_')}.csv")
    cols = ["date", "close", "settle", "oi", "vol"]
    old = pd.DataFrame() if force else _read(path, cols)
    start_ = start
    if len(old):
        start_ = min(max(start, (pd.to_datetime(old["date"].max()) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")),
                     start)
    df = ts._query(
        "fut_daily",
        {"ts_code": ts_code_, "start_date": _ymd(start_), "end_date": _ymd(end or date.today())},
        "trade_date,close,settle,oi,vol",
    )
    if df.empty:
        return old
    df = df.rename(columns={"trade_date": "date"})
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    for c in ("close", "settle", "oi", "vol"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"])[cols]
    return _merge_write(path, old, df)


# ---------------------------------------------------------------- ETF 两融
def fetch_margin(code, ex, start):
    """单只 ETF 的融资融券明细。金额单位统一为元。"""
    path = os.path.join(RAW, f"margin_{code}.csv")
    cols = ["date", "rzye", "rqye", "rzmre", "rzrqye"]
    old = _read(path, cols)
    start_ = start
    if len(old):
        start_ = min(max(start, (pd.to_datetime(old["date"].max()) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")),
                     start)
    df = ts._query(
        "margin_detail",
        {"ts_code": code + (".SH" if ex == "SH" else ".SZ"),
         "start_date": _ymd(start_), "end_date": _ymd(date.today())},
        "trade_date,rzye,rqye,rzmre,rzrqye",
    )
    if df.empty:
        return old
    df = df.rename(columns={"trade_date": "date"})
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    for c in cols[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return _merge_write(path, old, df[cols])


# ------------------------------------------------------------ 全市场两融
def fetch_market_margin(start):
    """交易所层面的两融余额汇总（沪深两市合计）。"""
    path = os.path.join(RAW, "margin_market.csv")
    cols = ["date", "rzye", "rqye"]
    old = _read(path, cols)
    start_ = start
    if len(old):
        start_ = min(max(start, (pd.to_datetime(old["date"].max()) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")),
                     start)
    df = ts._query(
        "margin",
        {"start_date": _ymd(start_), "end_date": _ymd(date.today())},
        "trade_date,exchange_id,rzye,rqye",
    )
    if df.empty:
        return old
    df = df.rename(columns={"trade_date": "date"})
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    for c in ("rzye", "rqye"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.groupby("date", as_index=False)[["rzye", "rqye"]].sum()
    return _merge_write(path, old, df[cols])


def index_close(icode):
    """现货收盘价，复用 ts_idx_*.csv 缓存（fetch_index 已经写好）。"""
    path = os.path.join(RAW, f"ts_idx_{icode}.csv")
    df = _read(path, ["date", "close", "amount"])
    if not len(df):
        return pd.DataFrame(columns=["date", "close"])
    return df[["date", "close"]].dropna()
