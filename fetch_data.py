# -*- coding: utf-8 -*-
"""
国家队 ETF 资金流监测 —— 数据抓取与指标计算
数据源：
  1) Tushare Pro: etf_share_size（份额/净值，2018+）+ fund_daily（价格/成交额）——唯一主源
  2) Tushare Pro: index_daily（指数日线）——指数主源，失败才回退东财
  3) 深交所/新浪：**仅用于交叉校验**（写入 data/verification.json），不回填主数据
     （上交所源已停用：出口 IP 被其 WAF 封禁，代码不再发起任何 sse.com.cn 请求）
  4) 新浪财经 7x24：重要财经快讯 → 事件线索（data/news.json）
用法：
  python3 fetch_data.py            # 增量更新
  python3 fetch_data.py --full     # 全量重建
  python3 fetch_data.py --no-verify --no-news   # 只算数据，跳过校验与新闻
"""
import argparse
import json
import math
import os
import random
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import pandas as pd
import requests

import config
import news_source
import tushare_source as ts_src

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "data", "raw")
DATA = os.path.join(ROOT, "data")
os.makedirs(RAW, exist_ok=True)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
TODAY = date.today().isoformat()

def get(url, headers=None, retries=4, timeout=35):
    """每次使用独立连接：requests.Session 不是线程安全的。"""
    last = None
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    for i in range(retries):
        try:
            r = requests.get(url, headers=h, timeout=timeout)
            if r.status_code == 200 and len(r.content) > 0:
                return r
            # 4xx 不重试：被封禁时重试只会加重封禁（上交所 WAF 会升级为 IP 级拦截）
            if r.status_code in (400, 401, 403, 404):
                raise RuntimeError(f"HTTP {r.status_code}")
            last = RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:  # noqa
            if isinstance(e, RuntimeError) and str(e).startswith("HTTP 4"):
                raise
            last = e
        time.sleep(0.5 * (i + 1) + random.random() * 0.4)
    raise last


def read_cache(code, cols):
    p = os.path.join(RAW, f"{code}.csv")
    if os.path.exists(p):
        df = pd.read_csv(p)
        if len(df):
            return df
    return pd.DataFrame(columns=cols)


def write_cache(code, df):
    df = df.drop_duplicates(subset=["date"]).sort_values("date")
    df.to_csv(os.path.join(RAW, f"{code}.csv"), index=False)
    return df


def mark_source(code, source):
    """记录本次实际使用的数据源，避免 Tushare 失败后仍读旧 TS 缓存。"""
    with open(os.path.join(RAW, f"source_{code}.txt"), "w", encoding="utf-8") as f:
        f.write(source)


def read_source(code):
    p = os.path.join(RAW, f"source_{code}.txt")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    return None


# ----------------------------------------------------------------------------- 深交所
def fetch_szse_shares(code, start, end, force=False):
    """深交所基金规模，current_size 单位：万份。6 个月窗口 + 翻页。"""
    cid = f"szse_{code}"
    old = pd.DataFrame() if force else read_cache(cid, ["date", "shares_wan"])
    if len(old):
        start = max(config.START_DATE, (pd.to_datetime(old["date"].max()) - pd.Timedelta(days=20)).strftime("%Y-%m-%d"))
    rows = []
    cur = pd.to_datetime(start).date()
    end_d = pd.to_datetime(end).date()
    headers = {"Referer": "https://www.szse.cn/market/fund/volume/etf/", "User-Agent": UA}
    while cur <= end_d:
        chunk_end = min(cur + timedelta(days=150), end_d)
        page = 1
        while True:
            url = (
                "https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON"
                "&CATALOGID=scsj_fund_jjgm&TABKEY=tab1"
                f"&txtStart={cur}&txtEnd={chunk_end}&jjlb=ETF&txtDm={code}"
                f"&random={random.random()}&tab1PAGENO={page}"
            )
            try:
                j = get(url, headers=headers).json()
                block = j[0]
                for it in (block.get("data") or []):
                    rows.append({"date": it["size_date"], "shares_wan": float(it["current_size"].replace(",", ""))})
                pc = int(block["metadata"].get("pagecount") or 1)
                if page >= pc:
                    break
                page += 1
                time.sleep(0.12)
            except Exception as e:
                print(f"  [SZSE {code}] {cur}~{chunk_end} p{page} 失败: {str(e)[:60]}")
                break
        cur = chunk_end + timedelta(days=1)
        time.sleep(0.15)
    new = pd.DataFrame(rows)
    df = pd.concat([old, new], ignore_index=True) if len(old) else new
    if len(df):
        df = write_cache(cid, df)
    return df


# ----------------------------------------------------------------------------- 净值 / 行情
def fetch_nav(code, force=False):
    cid = f"nav_{code}"
    old = pd.DataFrame() if force else read_cache(cid, ["date", "nav"])
    headers = {"Referer": "https://finance.sina.com.cn/", "User-Agent": UA}
    url = ("https://stock.finance.sina.com.cn/fundInfo/api/openapi.php/"
           f"CaihuiFundInfoService.getNav?symbol={code}&num=5000")
    try:
        j = get(url, headers=headers).json()
        rows = [{"date": x["fbrq"][:10], "nav": float(x["jjjz"])}
                for x in j["result"]["data"]["data"] if x.get("jjjz")]
        new = pd.DataFrame(rows)
    except Exception as e:
        print(f"  [NAV {code}] 失败: {str(e)[:60]}")
        new = pd.DataFrame()
    df = pd.concat([old, new], ignore_index=True) if len(old) else new
    if len(df):
        df = write_cache(cid, df)
    return df


def fetch_kline(secid, cid, beg=None, force=False):
    beg = beg or config.START_DATE.replace("-", "")
    old = pd.DataFrame() if force else read_cache(cid, ["date", "close", "amount", "pct"])
    headers = {"Referer": "https://quote.eastmoney.com/", "User-Agent": UA}
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&klt=101&fqt=0&beg={beg}&end=20500101"
        "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    )
    try:
        j = get(url, headers=headers).json()
        rows = []
        for k in (j.get("data") or {}).get("klines", []):
            p = k.split(",")
            rows.append({"date": p[0], "close": float(p[2]), "amount": float(p[6]), "pct": float(p[8])})
        new = pd.DataFrame(rows)
    except Exception as e:
        print(f"  [KLINE {cid}] 失败: {str(e)[:60]}")
        new = pd.DataFrame()
    df = pd.concat([old, new], ignore_index=True) if len(old) else new
    if len(df):
        df = write_cache(cid, df)
    return df


def verify_sources(days=8, warn=1.0, fail=2.0):
    """用交易所规模/份额与新浪净值交叉验证 Tushare 主源。

    只读校验，不修改主数据。返回报告 dict，并写入 data/verification.json。
    """
    print("④ 交叉验证（交易所 / 新浪）…")
    since = (pd.Timestamp(TODAY) - pd.Timedelta(days=days * 3)).strftime("%Y-%m-%d")
    items, asof = [], ""

    for e in config.CORE:
        code, ex = e["code"], e["ex"]
        ts = read_cache(f"ts_share_{code}", ["date", "shares_wan", "nav", "aum_wan"])
        if ts.empty:
            continue
        ts = ts.copy()
        ts["date"] = ts["date"].astype(str)
        ts["shares_yi"] = pd.to_numeric(ts["shares_wan"], errors="coerce") / 1e4
        ts["nav"] = pd.to_numeric(ts["nav"], errors="coerce")
        ts["scale_yi"] = ts["shares_yi"] * ts["nav"]
        ts = ts[ts["date"] >= since].dropna(subset=["shares_yi", "nav"])
        if ts.empty:
            continue
        asof = max(asof, ts["date"].max())

        share_dev, nav_dev, src = [], [], "—"
        # 上交所源已停用（出口 IP 被其 WAF 封禁），沪市只做新浪净值校验；深市仍用深交所份额
        if ex == "SZ":
            src = "深交所份额"
            try:
                prov = fetch_szse_shares(code, since, TODAY)
                if not prov.empty:
                    prov = prov.copy()
                    prov["date"] = prov["date"].astype(str)
                    prov["shares_yi_prov"] = pd.to_numeric(prov["shares_wan"], errors="coerce") / 1e4
                    m = ts.merge(prov[["date", "shares_yi_prov"]], on="date")
                    share_dev = [abs(r["shares_yi"] - r["shares_yi_prov"]) / r["shares_yi_prov"] * 100
                                 for _, r in m.iterrows() if r["shares_yi_prov"]]
            except Exception as err:
                print(f"   [VERIFY {code}] 深交所份额校验失败: {str(err)[:50]}")
        else:
            src = "新浪净值"

        try:
            pn = fetch_nav(code)
            if not pn.empty:
                pn = pn.copy()
                pn["date"] = pn["date"].astype(str)
                pn = pn.rename(columns={"nav": "nav_sina"})
                m = ts.merge(pn[["date", "nav_sina"]], on="date")
                nav_dev = [abs(r["nav"] - r["nav_sina"]) / r["nav_sina"] * 100
                           for _, r in m.iterrows() if r["nav_sina"]]
        except Exception as err:
            print(f"   [VERIFY {code}] 新浪净值校验失败: {str(err)[:50]}")

        share_max = round(max(share_dev), 3) if share_dev else None
        nav_max = round(max(nav_dev), 3) if nav_dev else None
        worst = max([x for x in (share_max, nav_max) if x is not None], default=None)
        status = "ok" if worst is None or worst < warn else ("warn" if worst < fail else "fail")
        items.append(dict(code=code, name=e["name"], exch=ex, source=src,
                          days=len(share_dev), share_dev_pct=share_max,
                          nav_dev_pct=nav_max, status=status))
        print(f"   {code} {e['name'][:12]:<14} 份额偏差 {share_max if share_max is not None else '—':>7}%  "
              f"净值偏差 {nav_max if nav_max is not None else '—':>7}%  [{status}]")

    worst = max([x for it in items for x in (it["share_dev_pct"], it["nav_dev_pct"]) if x is not None], default=None)
    overall = "ok" if worst is None or worst < warn else ("warn" if worst < fail else "fail")
    report = dict(generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"), asof=asof,
                  thresholds=dict(warn=warn, fail=fail), max_dev_pct=worst,
                  status=overall, items=items)
    with open(os.path.join(DATA, "verification.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"   → 校验结论: {overall}  最大偏差 {worst}%  （截至 {asof}）")
    return report


# ----------------------------------------------------------------------------- 主流程
def build_raw(force=False):
    print("① 抓取 ETF 份额 / 净值 / 行情 …")
    start, end = config.START_DATE, TODAY

    def one(e):
        code, ex = e["code"], e["ex"]
        # 优先 Tushare（2018+，含份额/净值/成交额）；失败则回退交易所+新浪+东财
        if ts_src.enabled():
            try:
                s = ts_src.fetch_share(code, ex, force)
                k = ts_src.fetch_daily(code, ex, force)
                if len(s) > 100 and len(k) > 100:
                    mark_source(code, "Tushare")
                    return code, len(s), 0, len(k), "Tushare"
                print(f"   [TS {code}] 数据不足，回退交易所")
            except Exception as e:
                cached_s = read_cache(f"ts_share_{code}", ["date", "shares_wan", "nav", "aum_wan"])
                cached_k = read_cache(f"ts_daily_{code}", ["date", "close", "amount"])
                if len(cached_s) > 100 and len(cached_k) > 100:
                    mark_source(code, "Tushare")
                    print(f"   [TS {code}] {str(e)[:60]}，使用本地缓存")
                    return code, len(cached_s), 0, len(cached_k), "Tushare缓存"
                print(f"   [TS {code}] {str(e)[:60]}，回退交易所")
        if ex == "SH":
            # 上交所源已停用：沪市 ETF 在无 Tushare 缓存时无法重建
            print(f"   [SKIP {code}] 上交所源已停用，且无 Tushare 缓存")
            mark_source(code, "缺失")
            return code, 0, 0, 0, "缺失"
        s = fetch_szse_shares(code, start, end, force)
        n = fetch_nav(code, force)
        k = fetch_kline("0." + code, f"k_{code}", config.START_DATE.replace("-", ""), force)
        mark_source(code, "交易所")
        return code, len(s), len(n), len(k), "交易所"

    # 并发压低到 2：网关对突发请求敏感，4 路并发会频繁触发 429
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(one, e) for e in config.ETFS]
        for f in as_completed(futs):
            code, a, b, c, src = f.result()
            print(f"   {code}: 份额 {a} / 净值 {b} / 行情 {c}  [{src}]")

    print("② 抓取指数 …")
    for icode, meta in config.INDEXES.items():
        df = pd.DataFrame()
        # Tushare 指数优先（稳定、含 2018+）；失败或滞后才走东财
        if ts_src.enabled():
            try:
                ti = ts_src.fetch_index(icode, force)
                if len(ti) > 100:
                    ti = ti.copy()
                    ti["pct"] = ti["close"].pct_change() * 100
                    old = read_cache(f"idx_{icode}", ["date", "close", "amount", "pct"])
                    combo = pd.concat([old, ti], ignore_index=True).drop_duplicates(subset=["date"], keep="last").sort_values("date")
                    df = write_cache(f"idx_{icode}", combo)
            except Exception as e:
                print(f"   [TS IDX {icode}] {str(e)[:60]}")
        if df.empty or df["date"].max() < TODAY:
            df2 = fetch_kline(meta["secid"], f"idx_{icode}", config.START_DATE.replace("-", ""), force)
            if len(df2):
                combo = pd.concat([df, df2], ignore_index=True).drop_duplicates(subset=["date"], keep="last").sort_values("date")
                df = write_cache(f"idx_{icode}", combo)
        print(f"   {icode} {meta['name']}: {len(df)}")


def load_series(e):
    """返回单只 ETF 的日频 DataFrame: date, shares_yi, nav, close, scale_yi, flow_yi"""
    code, ex = e["code"], e["ex"]
    source = read_source(code)
    ts_share = read_cache(f"ts_share_{code}", ["date", "shares_wan", "nav", "aum_wan"])
    ts_daily = read_cache(f"ts_daily_{code}", ["date", "close", "amount"])
    use_ts = source == "Tushare" or (source is None and len(ts_share) > 100 and len(ts_daily) > 100)
    if use_ts and len(ts_share) > 100 and len(ts_daily) > 100:
        df = ts_share.merge(ts_daily[["date", "close", "amount"]], on="date", how="left")
        df["shares_yi"] = df["shares_wan"] / 10000.0
        df["scale_yi"] = df["shares_yi"] * df["nav"]
        df = df.dropna(subset=["shares_yi", "nav"]).sort_values("date").reset_index(drop=True)
        df = df[df["date"] >= config.START_DATE].copy()
        df["flow_yi"] = df["shares_yi"].diff() * df["nav"]
        df["d_shares_yi"] = df["shares_yi"].diff()
        df["premium_bps"] = (df["close"] / df["nav"] - 1) * 10000
        df["split_flag"] = (df["d_shares_yi"] / df["shares_yi"].shift(1)).abs() > 0.40
        return df[["date", "shares_yi", "d_shares_yi", "nav", "close", "amount", "scale_yi", "flow_yi", "premium_bps", "split_flag"]]

    nav = read_cache(f"nav_{code}", ["date", "nav"])
    k = read_cache(f"k_{code}", ["date", "close", "amount", "pct"])
    if ex == "SH":
        # 上交所源已停用；沪市 ETF 必须有 Tushare 缓存，否则拒绝重建（避免用冻结的旧缓存冒充新数据）
        raise RuntimeError(f"{code}: 上交所源已停用，且缺少 Tushare 缓存")
    raw = read_cache(f"szse_{code}", ["date", "shares_wan"])
    raw["shares_yi"] = raw["shares_wan"] / 10000.0
    df = raw.merge(nav, on="date", how="left").merge(k[["date", "close", "amount"]], on="date", how="left")
    df["nav"] = df["nav"].ffill(limit=3)
    df["scale_yi"] = df["shares_yi"] * df["nav"]
    df = df.dropna(subset=["shares_yi", "nav"]).sort_values("date").reset_index(drop=True)
    df = df[df["date"] >= config.START_DATE].copy()
    df["flow_yi"] = df["shares_yi"].diff() * df["nav"]
    df["d_shares_yi"] = df["shares_yi"].diff()
    df["premium_bps"] = (df["close"] / df["nav"] - 1) * 10000
    # 拆分/异常跳变标记：份额单日变动 >40% 视为疑似拆分或数据异常
    df["split_flag"] = (df["d_shares_yi"] / df["shares_yi"].shift(1)).abs() > 0.40
    return df[["date", "shares_yi", "d_shares_yi", "nav", "close", "amount", "scale_yi", "flow_yi", "premium_bps", "split_flag"]]


def compute():
    print("③ 计算净申购与滚动指标 …")
    etf_frames = {}
    for e in config.ETFS:
        df = load_series(e)
        if len(df) < 10:
            print(f"   !! {e['code']} 数据不足 ({len(df)})")
            continue
        etf_frames[e["code"]] = df

    # 主交易日历：沪深300 指数交易日
    idx300 = read_cache("idx_000300", ["date", "close", "amount", "pct"]).sort_values("date")
    # 主日历 = 指数交易日 ∪ 所有 ETF 份额日期（避免指数接口延迟导致 T 日被丢掉）
    cal = set(idx300["date"].tolist())
    for df in etf_frames.values():
        cal.update(df["date"].tolist())
    cal = sorted(d for d in cal if d >= config.START_DATE)

    def align(s):
        return s.set_index("date").reindex(cal)

    # 核心池矩阵（亿元）
    core = [e for e in config.CORE if e["code"] in etf_frames]
    flow_mat, aum_mat = {}, {}
    for e in core:
        df = align(etf_frames[e["code"]])
        flow_mat[e["code"]] = df["flow_yi"]
        aum_mat[e["code"]] = df["scale_yi"]
    F = pd.DataFrame(flow_mat, index=cal)
    A = pd.DataFrame(aum_mat, index=cal)

    # 数据覆盖：至少 60% 的核心 ETF 有当日流量
    cover = F.notna().sum(axis=1) / len(core)
    valid = cover >= 0.8

    total_flow = F.sum(axis=1, min_count=3).where(valid)
    total_aum = A.sum(axis=1, min_count=3).where(valid)
    total_shares = pd.Series(index=cal, dtype=float)
    for e in core:
        df = align(etf_frames[e["code"]])
        total_shares = total_shares.add(df["shares_yi"], fill_value=0)
    total_shares = total_shares.where(valid)

    cum = total_flow.fillna(0).cumsum()
    flow5 = total_flow.rolling(5, min_periods=3).sum()
    flow20 = total_flow.rolling(20, min_periods=12).sum()
    flow60 = total_flow.rolling(60, min_periods=30).sum()
    z20 = (flow20 - flow20.rolling(252, min_periods=120).mean()) / flow20.rolling(252, min_periods=120).std()
    rank20 = flow20.rolling(252, min_periods=120).apply(lambda x: (x[-1] > x).mean(), raw=True)

    # 连涨天数
    pos = (total_flow > 0).astype(int)
    streak, cur = [], 0
    for v in pos.fillna(0):
        if v:
            cur = cur + 1 if cur >= 0 else 1
        else:
            cur = cur - 1 if cur <= 0 else -1
        streak.append(cur)
    streak = pd.Series(streak, index=cal)

    # 指数与成交额
    def load_idx(icode):
        df = read_cache(f"idx_{icode}", ["date", "close", "amount", "pct"]).sort_values("date")
        return df.set_index("date").reindex(cal)

    hs300 = load_idx("000300")["close"]
    sh = load_idx("000001")["amount"].fillna(0)
    sz = load_idx("399106")["amount"].fillna(0)
    turnover = (sh + sz) / 1e8
    ratio = total_flow / turnover * 100  # 净申购占全市场成交额 %

    # 核心池 ETF 成交额（亿元）与 20 日量比：对应中信证券“超额成交”验证
    tmat = {}
    for e in core:
        df = align(etf_frames[e["code"]])
        tmat[e["code"]] = df["amount"]
    T = pd.DataFrame(tmat, index=cal)
    etf_turnover = T.sum(axis=1, min_count=3) / 1e8
    etf_turnover_ratio = etf_turnover / etf_turnover.rolling(20, min_periods=10).mean()

    # 加权溢价率
    prem = None
    wsum = 0
    for e in core:
        df = align(etf_frames[e["code"]])
        w = df["scale_yi"].fillna(0)
        p = df["premium_bps"].clip(-500, 500).fillna(0) * w
        prem = p if prem is None else prem + p
        wsum = wsum + w
    prem = prem / wsum.replace(0, math.nan)

    # 分指数族
    fam = {}
    for f in config.FAMILIES:
        cols = [e["code"] for e in core if e["family"] == f]
        if cols:
            fam[f] = F[cols].sum(axis=1, min_count=max(1, len(cols) // 2)).where(valid)

    # 单只 ETF 指标
    last_i = total_flow.last_valid_index()
    etf_out = []
    for e in config.ETFS:
        if e["code"] not in etf_frames:
            continue
        df = etf_frames[e["code"]].set_index("date").reindex(cal).loc[:last_i]
        d = {
            "code": e["code"], "name": e["name"], "ex": e["ex"], "family": e["family"],
            "tier": e["tier"], "index": e["index"],
            "shares": [r(x, 4) for x in df["shares_yi"]],
            "dshares": [r(x, 4) for x in df["d_shares_yi"]],
            "nav": [r(x, 4) for x in df["nav"]],
            "close": [r(x, 3) for x in df["close"]],
            "flow": [r(x, 3) for x in df["flow_yi"]],
            "aum": [r(x, 2) for x in df["scale_yi"]],
            "premium": [r(x, 0) for x in df["premium_bps"]],
        }
        d["flow5"] = r(df["flow_yi"].rolling(5, min_periods=3).sum().iloc[-1], 2)
        d["flow20"] = r(df["flow_yi"].rolling(20, min_periods=12).sum().iloc[-1], 2)
        d["flow_ytd"] = r(df.loc[df.index >= f"{date.today().year}-01-01", "flow_yi"].sum(), 2)
        d["aum_last"] = r(df["scale_yi"].dropna().iloc[-1], 2) if df["scale_yi"].notna().any() else None
        d["shares_last"] = r(df["shares_yi"].dropna().iloc[-1], 4) if df["shares_yi"].notna().any() else None
        d["premium_last"] = r(df["premium_bps"].dropna().iloc[-1], 0) if df["premium_bps"].notna().any() else None
        d["flow_last"] = r(df["flow_yi"].dropna().iloc[-1], 2) if df["flow_yi"].notna().any() else None
        s20 = df["flow_yi"].rolling(20, min_periods=12).sum()
        if s20.notna().sum() > 130:
            mu = s20.rolling(252, min_periods=120).mean().iloc[-1]
            sd = s20.rolling(252, min_periods=120).std().iloc[-1]
            d["z20"] = r((s20.iloc[-1] - mu) / sd, 2) if sd and not math.isnan(sd) else None
        else:
            d["z20"] = None
        d["flag"] = bool(df["split_flag"].fillna(False).iloc[-5:].any())
        etf_out.append(d)

    # 表格权重
    total_aum_last = sum([x["aum_last"] or 0 for x in etf_out if x["tier"] == 1]) or 1
    for x in etf_out:
        x["weight"] = r((x["aum_last"] or 0) / total_aum_last * 100, 2) if x["tier"] == 1 else None

    # 最新状态
    last_i = total_flow.last_valid_index()
    last = cal.index(last_i) if last_i else len(cal) - 1
    fam20 = {}
    for f, v in fam.items():
        val = v.rolling(20, min_periods=12).sum().iloc[last]
        if val is not None and not math.isnan(val):
            fam20[f] = float(val)
    breadth = sum(1 for v in fam20.values() if v > 0)
    top_family = max(fam20, key=fam20.get) if fam20 else None
    top_family_val = fam20.get(top_family, 0) if top_family else 0
    top_family_share = (top_family_val / flow20.iloc[last] * 100) if flow20.iloc[last] else None

    latest = {
        "date": cal[last],
        "flow": r(total_flow.iloc[last], 2),
        "flow5": r(flow5.iloc[last], 2),
        "flow20": r(flow20.iloc[last], 2),
        "flow60": r(flow60.iloc[last], 2),
        "cum": r(cum.iloc[last], 2),
        "ytd": r(total_flow[total_flow.index >= f"{date.today().year}-01-01"].sum(), 2),
        "aum": r(total_aum.iloc[last], 2),
        "shares": r(total_shares.iloc[last], 2),
        "z20": r(z20.iloc[last], 2) if not math.isnan(z20.iloc[last]) else None,
        "rank20": r(rank20.iloc[last] * 100, 1) if not math.isnan(rank20.iloc[last]) else None,
        "streak": int(streak.iloc[last]) if not math.isnan(streak.iloc[last]) else 0,
        "premium": r(prem.iloc[last], 0) if not math.isnan(prem.iloc[last]) else None,
        "turnover": r(turnover.iloc[last], 0),
        "ratio": r(ratio.iloc[last], 2) if not math.isnan(ratio.iloc[last]) else None,
        "hs300": r(hs300.iloc[last], 2),
        "coverage": r(cover.iloc[last] * 100, 1),
        "etf_turnover": r(etf_turnover.iloc[last], 0),
        "etf_turnover_ratio": r(etf_turnover_ratio.iloc[last], 2),
        "breadth": int(breadth),
        "n_families": len(fam20),
        "top_family": top_family,
        "top_family_share": r(top_family_share, 1),
    }

    # 年度统计
    yearly = []
    s = total_flow.dropna()
    for y, g in s.groupby(pd.to_datetime(s.index).year):
        yearly.append({"year": int(y), "flow": r(g.sum(), 1), "days": int((g > 0).sum()),
                       "inflow_days": int((g > 0).sum()), "outflow_days": int((g < 0).sum())})

    n_keep = cal.index(last_i) + 1
    first_i = total_flow.first_valid_index()
    n_start = cal.index(first_i) if first_i else 0
    dates = cal[n_start:n_keep]

    def cut(a):
        return a[n_start:n_keep]

    for x in etf_out:
        for k in ("shares", "dshares", "nav", "close", "flow", "aum", "premium"):
            x[k] = cut(x[k])

    payload = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "start": dates[0], "end": dates[-1], "signal_start": config.SIGNAL_START,
            "n_etf": len(core), "n_total": len(etf_out), "n_extended": len(config.EXTENDED),
            "data_source": "Tushare Pro",
            "sources": ["Tushare", "深交所", "新浪财经", "东方财富"],
            "disclaimer": config.DISCLAIMER,
            "events": config.EVENTS,
            "families": [f for f in config.FAMILIES if f in fam],
        },
        "dates": dates,
        "hs300": [r(x, 2) for x in cut(hs300)],
        "turnover": [r(x, 0) for x in cut(turnover)],
        "premium": [r(x, 0) for x in cut(prem)],
        "coverage": [r(x * 100, 1) for x in cut(cover)],
        "total": {
            "flow": [r(x, 2) for x in cut(total_flow)],
            "cum": [r(x, 2) for x in cut(cum)],
            "aum": [r(x, 1) for x in cut(total_aum)],
            "shares": [r(x, 2) for x in cut(total_shares)],
            "flow5": [r(x, 2) for x in cut(flow5)],
            "flow20": [r(x, 2) for x in cut(flow20)],
            "flow60": [r(x, 2) for x in cut(flow60)],
            "z20": [r(x, 2) for x in cut(z20)],
            "streak": [int(x) for x in cut(streak)],
            "ratio": [r(x, 2) for x in cut(ratio)],
            "etf_turnover": [r(x, 0) for x in cut(etf_turnover)],
            "etf_turnover_ratio": [r(x, 2) for x in cut(etf_turnover_ratio)],
        },
        "families": {k: [r(x, 2) for x in cut(v)] for k, v in fam.items()},
        "family_cum": {k: [r(x, 2) for x in cut(v.fillna(0).cumsum())] for k, v in fam.items()},
        "etfs": etf_out,
        "latest": latest,
        "yearly": yearly,
        "ranges": {
            "all": [dates[0], dates[-1]],
            "signal": [config.SIGNAL_START, dates[-1]],
        },
    }
    return payload


def validate_payload(p):
    """生产写入前的硬校验：日期、数组长度、核心池加总、覆盖率。"""
    dates = p["dates"]
    assert dates and dates == sorted(set(dates)), "日期不唯一或未排序"
    n = len(dates)
    assert len(p["total"]["flow"]) == n, "总量数组长度不一致"
    assert len(p["etfs"]) == len(config.ETFS), "ETF 数量不一致"
    core = [x for x in p["etfs"] if x["tier"] == 1]
    assert len(core) == len(config.CORE), "核心池数量不一致"
    for x in p["etfs"]:
        assert len(x["flow"]) == n, f"{x['code']} 流量数组长度不一致"
    latest = p["latest"]
    assert latest["coverage"] >= 80, f"覆盖率过低: {latest['coverage']}"
    assert latest["aum"] > 0, "核心池规模异常"
    s = sum(x["flow_last"] or 0 for x in core)
    assert abs(s - latest["flow"]) < 0.6, f"核心池加总不一致: {s} vs {latest['flow']}"
    print("   ✓ 数据校验通过")


def r(x, n=2):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return round(float(x), n)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="全量重建")
    ap.add_argument("--skip-fetch", action="store_true", help="只用本地缓存重算，不联网")
    ap.add_argument("--no-verify", action="store_true", help="跳过交易所/新浪交叉校验")
    ap.add_argument("--no-news", action="store_true", help="跳过新闻线索抓取")
    args = ap.parse_args()

    t0 = time.time()
    if not args.skip_fetch:
        build_raw(force=args.full)
    payload = compute()
    validate_payload(payload)

    if args.no_verify:
        payload["meta"]["verification"] = dict(status="skipped")
    else:
        try:
            rep = verify_sources()
            payload["meta"]["verification"] = dict(
                status=rep["status"], asof=rep["asof"], max_dev_pct=rep["max_dev_pct"],
                thresholds=rep["thresholds"], detail="data/verification.json")
        except Exception as e:
            print(f"   [VERIFY] 跳过: {str(e)[:80]}")
            payload["meta"]["verification"] = dict(status="error", error=str(e)[:120])

    if args.no_news:
        payload["meta"]["news"] = []
    else:
        try:
            items, added = news_source.collect()
            payload["meta"]["news"] = items[:80]
            print(f"⑤ 新闻线索：收录 {len(items)} 条（本次新增 {added}）")
        except Exception as e:
            print(f"   [NEWS] 失败: {str(e)[:80]}")
            payload["meta"]["news"] = []
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "dashboard_data.js"), "w", encoding="utf-8") as f:
        f.write("window.DASHBOARD_DATA=")
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    with open(os.path.join(DATA, "dashboard_data.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # 明细 CSV
    rows = []
    for x in payload["etfs"]:
        rows.append({
            "代码": x["code"], "名称": x["name"], "指数": x["family"], "层级": x["tier"],
            "最新份额(亿份)": x["shares_last"], "当日净申购(亿元)": x["flow_last"],
            "5日净申购(亿元)": x["flow5"], "20日净申购(亿元)": x["flow20"],
            "年初至今(亿元)": x["flow_ytd"], "规模(亿元)": x["aum_last"],
            "占比(%)": x["weight"], "20日z": x["z20"], "溢价(bp)": x["premium_last"],
        })
    pd.DataFrame(rows).to_csv(os.path.join(DATA, "etf_latest.csv"), index=False, encoding="utf-8-sig")

    daily = pd.DataFrame({
        "日期": payload["dates"],
        "核心池净申购(亿元)": payload["total"]["flow"],
        "累计净申购(亿元)": payload["total"]["cum"],
        "20日滚动净申购(亿元)": payload["total"]["flow20"],
        "20日z": payload["total"]["z20"],
        "核心池规模(亿元)": payload["total"]["aum"],
        "沪深300": payload["hs300"],
        "全市场成交额(亿元)": payload["turnover"],
        "核心池ETF成交额(亿元)": payload["total"]["etf_turnover"],
        "ETF成交额/20日均值": payload["total"]["etf_turnover_ratio"],
    })
    daily.to_csv(os.path.join(DATA, "daily.csv"), index=False, encoding="utf-8-sig")

    d = payload["latest"]
    print("\n=== 完成 ===")
    print(f"区间 {payload['meta']['start']} ~ {payload['meta']['end']}，{len(payload['dates'])} 个交易日，{payload['meta']['n_etf']} 只核心 ETF（另 {payload['meta']['n_extended']} 只扩展）")
    print(f"最新 {d['date']}: 单日 {d['flow']} 亿 / 5日 {d['flow5']} 亿 / 20日 {d['flow20']} 亿 / 累计 {d['cum']} 亿")
    print(f"总规模 {d['aum']} 亿，20日 z={d['z20']}，分位 {d['rank20']}%，覆盖 {d['coverage']}%")
    print(f"耗时 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
