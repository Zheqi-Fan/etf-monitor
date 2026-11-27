#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""美国核心经济数据官方发布日程（人工维护）

为什么需要这个文件：
    BLS（bls.gov / data.bls.gov / api.bls.gov / blsmon1.bls.gov）与 Census
    （census.gov / api.census.gov）对本项目所在网络一律返回 403，
    FRED 也在若干次请求后被阻断。CPI、PPI、非农、零售销售因此无法在运行时抓取。

    但这几家的日程是「年初一次性公布全年、极少改动」的，所以改为把官方日程
    落到这个文件里。BEA（GDP / PCE）与美联储（FOMC）仍由网络实时抓取。

维护方式：
    每年官方公布次年日程后，在 RELEASES 里追加对应行，并更新 VERIFIED_ON。
    fetch_econ.py 会在日程即将用尽时（meta.schedule_until 已过）输出提醒。
"""
from datetime import date

# 本表对照的官方日程版本
VERIFIED_ON = "2026-11-27"
# 官方日程覆盖到的最后一天，超过之后只能靠规则推算，页面会提示
COVERAGE_NOTE = "官方日程已维护至 2027-12"

SRC_BLS = "BLS 官方日程"
SRC_CENSUS = "Census 官方日程"
RELEASE_TIME_ET = "08:30"

# (类别, 数据所属月 YYYY-MM, 发布日 YYYY-MM-DD)
# 非农 = Employment Situation；CPI / PPI 为 BLS 月度物价指数；
# 零售 = Census Advance Monthly Sales for Retail and Food Services。
RELEASES = [
    # ---------------- 非农 Employment Situation ----------------
    ("非农", "2026-10", "2026-11-06"),
    ("非农", "2026-11", "2026-12-04"),
    ("非农", "2026-12", "2027-01-08"),
    ("非农", "2027-01", "2027-02-05"),
    ("非农", "2027-02", "2027-03-05"),
    ("非农", "2027-06", "2027-07-02"),

    # ---------------- CPI Consumer Price Index ----------------
    ("CPI", "2026-01", "2026-02-13"),
    ("CPI", "2026-02", "2026-03-11"),
    ("CPI", "2026-03", "2026-04-10"),
    ("CPI", "2026-04", "2026-05-12"),
    ("CPI", "2026-05", "2026-06-10"),
    ("CPI", "2026-06", "2026-07-14"),
    ("CPI", "2026-07", "2026-08-12"),
    ("CPI", "2026-08", "2026-09-11"),
    ("CPI", "2026-09", "2026-10-14"),
    ("CPI", "2026-10", "2026-11-10"),
    ("CPI", "2026-11", "2026-12-10"),
    ("CPI", "2026-12", "2027-01-13"),
    ("CPI", "2027-01", "2027-02-11"),
    ("CPI", "2027-02", "2027-03-10"),
    ("CPI", "2027-03", "2027-04-13"),
    ("CPI", "2027-04", "2027-05-12"),
    ("CPI", "2027-05", "2027-06-10"),
    ("CPI", "2027-06", "2027-07-14"),
    ("CPI", "2027-07", "2027-08-11"),
    ("CPI", "2027-08", "2027-09-14"),
    ("CPI", "2027-09", "2027-10-14"),
    ("CPI", "2027-10", "2027-11-10"),
    ("CPI", "2027-11", "2027-12-10"),

    # ---------------- PPI Producer Price Index ----------------
    ("PPI", "2026-08", "2026-09-10"),
    ("PPI", "2026-10", "2026-11-13"),
    ("PPI", "2026-11", "2026-12-15"),
    ("PPI", "2026-12", "2027-01-14"),
    ("PPI", "2027-01", "2027-02-12"),
    ("PPI", "2027-02", "2027-03-12"),
    ("PPI", "2027-03", "2027-04-14"),
    ("PPI", "2027-04", "2027-05-13"),
    ("PPI", "2027-05", "2027-06-11"),
    ("PPI", "2027-06", "2027-07-15"),
    ("PPI", "2027-07", "2027-08-10"),
    ("PPI", "2027-08", "2027-09-10"),
    ("PPI", "2027-09", "2027-10-15"),

    # ---------------- 零售 Advance Monthly Retail Trade ----------------
    ("零售", "2026-11", "2026-12-16"),
    ("零售", "2026-12", "2027-01-15"),
    ("零售", "2027-01", "2027-02-17"),
    ("零售", "2027-02", "2027-03-16"),
    ("零售", "2027-11", "2027-12-15"),
]

_TITLES = {
    "非农": "非农就业报告（{m}）",
    "CPI": "CPI 消费者物价指数（{m}）",
    "PPI": "PPI 生产者物价指数（{m}）",
    "零售": "零售销售初值（{m}）",
}
_SOURCES = {"非农": SRC_BLS, "CPI": SRC_BLS, "PPI": SRC_BLS, "零售": SRC_CENSUS}


def _month_label(ym):
    y, m = ym.split("-")
    return f"{y}-{m}"


def events():
    """展开为 fetch_econ 统一使用的事件结构。"""
    out = []
    for cat, ref_month, rel_date in RELEASES:
        out.append({
            "date": rel_date,
            "time_et": RELEASE_TIME_ET,
            "title": _TITLES[cat].format(m=_month_label(ref_month)),
            "cat": cat,
            "source": _SOURCES[cat],
            "confirmed": True,
            "forecast": None,
            "previous": None,
            "importance": "高",
            "ref_month": ref_month,
        })
    return out


def latest_date():
    return max(r[2] for r in RELEASES)


def covered_nfp_months():
    """已被官方日程覆盖的非农发布月份 {(y, m)}，用于避免规则推算重复。"""
    return {(int(d[:4]), int(d[5:7])) for c, _ref, d in RELEASES if c == "非农"}


if __name__ == "__main__":
    ev = events()
    print(f"官方日程 {len(ev)} 条，覆盖至 {latest_date()}（核对日 {VERIFIED_ON}）")
    for e in sorted(ev, key=lambda x: x["date"]):
        if e["date"] >= date.today().isoformat():
            print(f'  {e["date"]} {e["time_et"]} {e["cat"]:>4}  {e["title"]}  [{e["source"]}]')
