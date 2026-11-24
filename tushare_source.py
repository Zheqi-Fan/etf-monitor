# -*- coding: utf-8 -*-
"""Tushare Pro（含自定义网关）ETF 份额/行情适配器。

- 默认从环境变量或 .env 读取 TUSHARE_TOKEN / TUSHARE_URL
- 只负责抓取并缓存，不做业务计算
- 任何失败都抛出异常，由 fetch_data.py 决定是否回退到交易所源
"""
import os
import time
from datetime import date, timedelta

import pandas as pd
import requests

import config

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw")
os.makedirs(RAW, exist_ok=True)
TODAY = date.today().isoformat()


def enabled():
    return bool(config.TUSHARE_TOKEN)


# 网关限流码：不限次数重试会加重封禁，改为指数退避
RATE_LIMIT_CODES = {429}
_RL_RETRIES = 4          # 429 最多重试次数
_RL_BASE = 6.0           # 首次等待秒数，之后 ×2


def _query(api_name, params, fields=""):
    if not enabled():
        raise RuntimeError("TUSHARE_TOKEN 未配置")
    payload = {"api_name": api_name, "token": config.TUSHARE_TOKEN, "params": params, "fields": fields}
    last = None
    for attempt in range(_RL_RETRIES + 1):
        r = requests.post(config.TUSHARE_URL, json=payload, timeout=25)
        j = r.json()
        code = j.get("code")
        if code == 0:
            data = j.get("data") or {}
            cols = data.get("fields") or []
            items = data.get("items") or []
            return pd.DataFrame(items, columns=cols)
        last = f"{api_name}: {code} {j.get('msg')}"
        if code in RATE_LIMIT_CODES and attempt < _RL_RETRIES:
            wait = _RL_BASE * (2 ** attempt)
            print(f"   [TS {api_name}] 限流，{wait:.0f}s 后重试 ({attempt + 1}/{_RL_RETRIES})")
            time.sleep(wait)
            continue
        raise RuntimeError(last)
    raise RuntimeError(last)


def _read(path, cols):
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except Exception:
            pass
    return pd.DataFrame(columns=cols)


def _write(path, df):
    df = df.drop_duplicates(subset=["date"]).sort_values("date")
    df.to_csv(path, index=False)
    return df


def _ts_code(code, ex):
    return code + (".SH" if ex == "SH" else ".SZ")


def fetch_share(code, ex, force=False):
    """ETF 每日总份额（万份）+ 单位净值，2018 至今。"""
    path = os.path.join(RAW, f"ts_share_{code}.csv")
    cols = ["date", "shares_wan", "nav", "aum_wan"]
    old = pd.DataFrame() if force else _read(path, cols)
    start = config.START_DATE
    if len(old):
        start = max(config.START_DATE, (pd.to_datetime(old["date"].max()) - pd.Timedelta(days=20)).strftime("%Y-%m-%d"))
    df = _query(
        "etf_share_size",
        {"ts_code": _ts_code(code, ex), "start_date": pd.to_datetime(start).strftime("%Y%m%d"), "end_date": pd.to_datetime(TODAY).strftime("%Y%m%d")},
        "trade_date,ts_code,etf_name,total_share,total_size,nav,close",
    )
    if df.empty:
        return old
    df = df.rename(columns={"trade_date": "date", "total_share": "shares_wan", "total_size": "aum_wan"})
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    for c in ("shares_wan", "nav", "aum_wan"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["shares_wan", "nav"])[["date", "shares_wan", "nav", "aum_wan"]]
    df = pd.concat([old, df], ignore_index=True) if len(old) else df
    if len(df):
        df = _write(path, df)
    time.sleep(0.12)
    return df


def fetch_daily(code, ex, force=False):
    """ETF 日线收盘价与成交额（元），2018 至今。"""
    path = os.path.join(RAW, f"ts_daily_{code}.csv")
    cols = ["date", "close", "amount"]
    old = pd.DataFrame() if force else _read(path, cols)
    start = config.START_DATE
    if len(old):
        start = max(config.START_DATE, (pd.to_datetime(old["date"].max()) - pd.Timedelta(days=20)).strftime("%Y-%m-%d"))
    df = _query(
        "fund_daily",
        {"ts_code": _ts_code(code, ex), "start_date": pd.to_datetime(start).strftime("%Y%m%d"), "end_date": pd.to_datetime(TODAY).strftime("%Y%m%d")},
        "trade_date,close,amount",
    )
    if df.empty:
        return old
    df = df.rename(columns={"trade_date": "date"})
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    # Tushare fund_daily amount 单位为千元
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce") * 1000.0
    df = df.dropna(subset=["close"])[["date", "close", "amount"]]
    df = pd.concat([old, df], ignore_index=True) if len(old) else df
    if len(df):
        df = _write(path, df)
    time.sleep(0.12)
    return df


TS_INDEX = {
    "000300": "000300.SH", "000905": "000905.SH", "000852": "000852.SH",
    "000016": "000016.SH", "000688": "000688.SH", "399006": "399006.SZ",
    "000001": "000001.SH", "399106": "399106.SZ",
}


def fetch_index(icode, force=False):
    """指数日线（收盘/成交额，成交额转为元），2018+。"""
    path = os.path.join(RAW, f"ts_idx_{icode}.csv")
    cols = ["date", "close", "amount"]
    old = pd.DataFrame() if force else _read(path, cols)
    start = config.START_DATE
    if len(old):
        start = max(config.START_DATE, (pd.to_datetime(old["date"].max()) - pd.Timedelta(days=20)).strftime("%Y-%m-%d"))
    df = _query(
        "index_daily",
        {"ts_code": TS_INDEX[icode], "start_date": pd.to_datetime(start).strftime("%Y%m%d"), "end_date": pd.to_datetime(TODAY).strftime("%Y%m%d")},
        "trade_date,close,amount",
    )
    if df.empty:
        return old
    df = df.rename(columns={"trade_date": "date"})
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce") * 1000.0
    df = df.dropna(subset=["close"])[["date", "close", "amount"]]
    df = pd.concat([old, df], ignore_index=True) if len(old) else df
    if len(df):
        df = _write(path, df)
    time.sleep(0.08)
    return df
