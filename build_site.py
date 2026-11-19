#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成可直接上传到 Netlify / GitHub Pages / Firebase 的纯静态目录 dist/。"""
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
FILES = [
    ("index.html", "index.html"),
    ("assets/style.css", "assets/style.css"),
    ("assets/app.js", "assets/app.js"),
    ("assets/echarts.min.js", "assets/echarts.min.js"),
    ("assets/favicon.svg", "assets/favicon.svg"),
    ("assets/preview.png", "assets/preview.png"),
    ("data/dashboard_data.js", "data/dashboard_data.js"),
    ("data/etf_latest.csv", "data/etf_latest.csv"),
    ("data/daily.csv", "data/daily.csv"),
]
HEADERS = """/*
  Cache-Control: no-cache, must-revalidate
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
"""


def main():
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    for src, dst in FILES:
        target = os.path.join(DIST, dst)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, src), target)
    with open(os.path.join(DIST, "_headers"), "w", encoding="utf-8") as f:
        f.write(HEADERS)
    print(f"built {DIST}")
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(DIST) for f in fs)
    print(f"files: {len(FILES)}  size: {total/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
