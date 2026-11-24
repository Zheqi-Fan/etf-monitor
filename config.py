# -*- coding: utf-8 -*-
"""国家队 ETF 资金流监测 —— 标的池、事件与口径配置"""
import os
from pathlib import Path


def _load_env():
    """轻量读取项目目录 .env；shell 环境变量优先。"""
    p = Path(__file__).with_name(".env")
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

START_DATE = "2018-01-01"   # Tushare 份额覆盖 2018+；交易所源可回退到 2021+
SIGNAL_START = "2023-10-23"  # 汇金公告买入 ETF，份额代理开始有信号
TUSHARE_URL = os.getenv("TUSHARE_URL", "https://api.tushare.pro")
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")
NETLIFY_DEPLOY_HOOK = os.getenv("NETLIFY_DEPLOY_HOOK", "")

# 数据更新后自动构建并推送，触发 GitHub Pages 重新部署
AUTO_PUBLISH = os.getenv("AUTO_PUBLISH", "1").strip().lower() not in ("0", "false", "no", "off")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER = os.getenv("GITHUB_USER", "x-access-token")
PUBLISH_BRANCH = os.getenv("PUBLISH_BRANCH", "main")
# 推送目标（空格分隔，可同时推多个）。private=Cloudflare 源，origin=旧 GitHub Pages
PUBLISH_REMOTES = os.getenv("PUBLISH_REMOTES", "private").split()

# tier 1 = 核心信号池（10 只，覆盖完整池约 96.4% 规模，计入总量）
# tier 2 = 扩展池（同指数/小规模产品，仅作完整性参考，不计入总量）
ETFS = [
    # 上交所
    dict(code="510300", name="沪深300ETF华泰柏瑞", ex="SH", family="沪深300", tier=1, index="000300"),
    dict(code="510310", name="沪深300ETF易方达",   ex="SH", family="沪深300", tier=1, index="000300"),
    dict(code="510330", name="沪深300ETF华夏",     ex="SH", family="沪深300", tier=1, index="000300"),
    dict(code="510050", name="上证50ETF华夏",      ex="SH", family="上证50",  tier=1, index="000016"),
    dict(code="510500", name="中证500ETF南方",     ex="SH", family="中证500", tier=1, index="000905"),
    dict(code="512100", name="中证1000ETF南方",    ex="SH", family="中证1000", tier=1, index="000852"),
    dict(code="588000", name="科创50ETF华夏",      ex="SH", family="科创50",  tier=1, index="000688"),
    dict(code="588080", name="科创50ETF易方达",    ex="SH", family="科创50",  tier=1, index="000688"),
    dict(code="512500", name="中证500ETF华夏",     ex="SH", family="中证500", tier=2, index="000905"),
    dict(code="560010", name="中证1000ETF广发",    ex="SH", family="中证1000", tier=2, index="000852"),
    # 深交所
    dict(code="159919", name="沪深300ETF嘉实",     ex="SZ", family="沪深300", tier=1, index="000300"),
    dict(code="159915", name="创业板ETF易方达",    ex="SZ", family="创业板",  tier=1, index="399006"),
    dict(code="159845", name="中证1000ETF华夏",    ex="SZ", family="中证1000", tier=2, index="000852"),
    dict(code="159922", name="中证500ETF嘉实",     ex="SZ", family="中证500", tier=2, index="000905"),
    dict(code="159629", name="中证1000ETF富国",    ex="SZ", family="中证1000", tier=2, index="000852"),
]

CORE = [e for e in ETFS if e["tier"] == 1]
EXTENDED = [e for e in ETFS if e["tier"] == 2]

FAMILIES = ["沪深300", "上证50", "中证500", "中证1000", "创业板", "科创50"]

INDEXES = {
    "000300": dict(secid="1.000300", name="沪深300"),
    "000905": dict(secid="1.000905", name="中证500"),
    "000852": dict(secid="1.000852", name="中证1000"),
    "000016": dict(secid="1.000016", name="上证50"),
    "000688": dict(secid="1.000688", name="科创50"),
    "399006": dict(secid="0.399006", name="创业板指"),
    "000001": dict(secid="1.000001", name="上证指数"),
    "399106": dict(secid="0.399106", name="深证综指"),
}

EVENTS = [
    dict(date="2018-10-19", short="政策底喊话", title="刘鹤与一行两会喊话，政策底起点", level=2),
    dict(date="2020-02-03", short="疫情底", title="疫情后首个交易日，稳市场预期", level=2),
    dict(date="2022-03-16", short="金融委会议", title="金融委专题会议，稳预期", level=2),
    dict(date="2023-07-24", short="政治局会议", title="政治局会议提出“活跃资本市场”", level=2),
    dict(date="2023-08-27", short="印花税减半", title="证券交易印花税减半征收", level=2),
    dict(date="2023-10-11", short="汇金增持四大行", title="中央汇金增持工农中建四大行", level=2),
    dict(date="2023-10-23", short="汇金买入ETF", title="汇金公告当日买入 ETF 并拟继续增持——份额代理起点", level=1),
    dict(date="2024-01-22", short="国常会", title="国常会听取资本市场运行情况汇报", level=2),
    dict(date="2024-02-06", short="扩大ETF增持", title="汇金公告扩大 ETF 增持范围，证监会表态支持", level=1),
    dict(date="2024-04-12", short="新国九条", title="新“国九条”发布", level=2),
    dict(date="2024-09-24", short="政策组合拳", title="一揽子增量政策 + SFISF 5000 亿", level=1),
    dict(date="2025-04-07", short="汇金再增持", title="汇金公告“已再次增持 ETF”", level=2),
    dict(date="2025-04-08", short="类平准基金", title="汇金明确类平准基金定位；央行再贷款支持；诚通/国新增持", level=1),
    dict(date="2026-01-14", short="融资保证金上调", title="融资保证金比例 80%→100%，逆周期降温", level=2),
    dict(date="2026-09-28", short="疑似再入场", title="股票 ETF 连续净流入起点（至 11-03 约 5560 亿）", level=1),
]

DISCLAIMER = (
    "本页面用“ETF 总份额变动 × 净值”估算一级市场净申购，作为国家队资金流向的高频代理指标。"
    "总份额包含所有持有人，不等于汇金/证金持仓；场内买卖不改变份额。"
    "数据仅供研究，不构成投资建议。"
)
