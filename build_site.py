#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成可直接上传到 Netlify / GitHub Pages / Firebase 的纯静态目录 dist/。"""
import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
FILES = [
    ("index.html", "index.html"),
    ("method.html", "method.html"),
    ("basis.html", "basis.html"),
    ("crowding.html", "crowding.html"),
    ("assets/style.css", "assets/style.css"),
    ("assets/app.js", "assets/app.js"),
    ("assets/deriv.js", "assets/deriv.js"),
    ("assets/echarts.min.js", "assets/echarts.min.js"),
    ("assets/favicon.svg", "assets/favicon.svg"),
    ("assets/preview.png", "assets/preview.png"),
    ("data/dashboard_data.js", "data/dashboard_data.js"),
    ("data/etf_latest.csv", "data/etf_latest.csv"),
    ("data/daily.csv", "data/daily.csv"),
    ("data/basis.csv", "data/basis.csv"),
    ("data/crowding.csv", "data/crowding.csv"),
]
# 由 run_update.py 生成；首次构建时可能还不存在
OPTIONAL = [
    ("data/status.js", "data/status.js"),
    ("data/deriv_data.js", "data/deriv_data.js"),
]
ASSET_RE = re.compile(r'((?:src|href)=")((?:assets|data)/[^"?]+\.(?:js|css))(")')


def _version_assets():
    """给 dist/index.html 里的 js/css 各自加 ?v=<自身 mtime>，绕开 GitHub Pages 10 分钟缓存。

    GitHub Pages 对所有文件固定 max-age=600，且忽略 _headers（Netlify 语法）。
    按文件单独取版本号：改动的文件 URL 变化，未改的（如 echarts 1MB）保持命中缓存。
    """
    def repl(m):
        rel = m.group(2)
        src = os.path.join(ROOT, rel)
        v = int(os.path.getmtime(src)) if os.path.exists(src) else 0
        return f"{m.group(1)}{rel}?v={v}{m.group(3)}"

    total = 0
    for name in ("index.html", "method.html", "basis.html", "crowding.html"):
        path = os.path.join(DIST, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            html = f.read()
        html, n = ASSET_RE.subn(repl, html)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        total += n
    print(f"  versioned {total} assets")


HEADERS = """/*
  Cache-Control: no-cache, must-revalidate
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
"""


def main():
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    copied = 0
    for src, dst in FILES:
        target = os.path.join(DIST, dst)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, src), target)
        copied += 1
    for src, dst in OPTIONAL:
        path = os.path.join(ROOT, src)
        if not os.path.exists(path):
            continue
        target = os.path.join(DIST, dst)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    _version_assets()
    with open(os.path.join(DIST, "_headers"), "w", encoding="utf-8") as f:
        f.write(HEADERS)
    print(f"built {DIST}")
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(DIST) for f in fs)
    print(f"files: {copied}  size: {total/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
