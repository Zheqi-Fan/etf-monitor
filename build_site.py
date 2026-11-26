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
    ("assets/style.css", "assets/style.css"),
    ("assets/app.js", "assets/app.js"),
    ("assets/echarts.min.js", "assets/echarts.min.js"),
    ("assets/favicon.svg", "assets/favicon.svg"),
    ("assets/preview.png", "assets/preview.png"),
    ("data/dashboard_data.js", "data/dashboard_data.js"),
    ("data/etf_latest.csv", "data/etf_latest.csv"),
    ("data/daily.csv", "data/daily.csv"),
]
# 由 run_update.py 生成；首次构建时可能还不存在
OPTIONAL = [
    ("data/status.js", "data/status.js"),
]
ASSET_RE = re.compile(r'((?:src|href)=")((?:assets|data)/[^"?]+\.(?:js|css))(")')


def _version_assets():
    """给 dist/index.html 里的 js/css 加 ?v=，绕开 GitHub Pages 的 10 分钟缓存。

    GitHub Pages 对所有文件固定 max-age=600，且忽略 _headers（那是 Netlify 语法）。
    加版本号后，只要拿到新 HTML，引用的脚本/数据必然是新的。
    """
    path = os.path.join(DIST, "index.html")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    ver = str(int(os.path.getmtime(os.path.join(ROOT, "data", "dashboard_data.js"))))
    html, n = ASSET_RE.subn(lambda m: f'{m.group(1)}{m.group(2)}?v={ver}{m.group(3)}', html)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  versioned {n} assets (v={ver})")


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
