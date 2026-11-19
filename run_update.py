#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定时任务入口：带硬超时，避免自动化 session 因等待管道而挂起。

用法：python3 run_update.py
输出最后一行 RESULT 供自动化读取；完整日志写入 update.log。
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import config

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "update.log")
TIMEOUT = 900


def _run(cmd, timeout, log, env=None):
    """执行命令并把输出写入日志；超时返回 None。"""
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        log.write(f"TIMEOUT after {timeout}s: {' '.join(cmd)}\n")
        return None
    if r.stdout:
        log.write(r.stdout)
    if r.stderr:
        log.write(r.stderr)
    return r


def _git_env():
    """push 用环境：优先 .env 的 GITHUB_TOKEN，未配置则回退 macOS 钥匙串。"""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    token = config.GITHUB_TOKEN
    if not token:
        return env, None
    fd, path = tempfile.mkstemp(prefix="etf-askpass-", suffix=".sh")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write('#!/bin/sh\n'
                'case "$1" in\n'
                '  *sername*) printf "%s\\n" "$ETF_GIT_USER" ;;\n'
                '  *) printf "%s\\n" "$ETF_GIT_TOKEN" ;;\n'
                'esac\n')
    os.chmod(path, 0o700)
    env["ETF_GIT_USER"] = config.GITHUB_USER
    env["ETF_GIT_TOKEN"] = token
    env["GIT_ASKPASS"] = path
    env["SSH_ASKPASS"] = path
    return env, path


def publish(log):
    """重建 dist，并把 data/ 的改动提交推送到 GitHub，触发 Pages 自动部署。"""
    if not config.AUTO_PUBLISH:
        return "disabled"

    r = _run([sys.executable, "build_site.py"], 180, log)
    if r is None or r.returncode != 0:
        return "build_failed"

    _run(["git", "add", "-A", "data"], 120, log)
    staged = _run(["git", "diff", "--cached", "--quiet"], 60, log)
    if staged is not None and staged.returncode == 0:
        return "no_change"

    msg = f"data: auto update {time.strftime('%Y-%m-%d %H:%M')}"
    c = _run(["git", "commit", "-m", msg], 120, log)
    if c is None or c.returncode != 0:
        return "commit_failed"

    env, askpass = _git_env()
    try:
        p = _run(["git", "push", "origin", config.PUBLISH_BRANCH], 300, log, env=env)
        if p is None:
            return "push_timeout"
        return "ok" if p.returncode == 0 else "push_failed"
    finally:
        if askpass and os.path.exists(askpass):
            os.remove(askpass)


def main():
    t0 = time.time()
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        log.flush()

        r = _run([sys.executable, "fetch_data.py"], TIMEOUT, log)
        if r is None:
            print(f"RESULT status=timeout after {TIMEOUT}s")
            log.write("TIMEOUT\n")
            return 1
        if r.returncode != 0:
            print((r.stderr or r.stdout or "fetch failed")[-1500:])
            print(f"RESULT status=failed code={r.returncode}")
            return 1

        # 发布：GitHub Pages（默认）或 Netlify Deploy Hook
        if config.NETLIFY_DEPLOY_HOOK:
            try:
                subprocess.run([sys.executable, "build_site.py"], cwd=ROOT, check=True,
                               capture_output=True, text=True, timeout=180)
                req = urllib.request.Request(config.NETLIFY_DEPLOY_HOOK, method="POST")
                urllib.request.urlopen(req, timeout=30).read()
                pub = "netlify"
            except Exception as e:
                log.write(f"NETLIFY failed: {str(e)[:200]}\n")
                pub = "netlify_failed"
        else:
            pub = publish(log)
        log.write(f"\nPUBLISH {pub}\n")
        log.flush()

    try:
        src = open(os.path.join(ROOT, "data", "dashboard_data.js"), encoding="utf-8").read()
        d = json.loads(src[len("window.DASHBOARD_DATA="):-2])
        x = d["latest"]
        ver = d["meta"].get("verification", {}).get("status", "?")
        news = len(d["meta"].get("news") or [])
        print(f"RESULT status=ok date={x['date']} flow={x['flow']} flow5={x['flow5']} "
              f"flow20={x['flow20']} coverage={x['coverage']} start={d['meta']['start']} "
              f"verify={ver} news={news} publish={pub} elapsed={time.time()-t0:.0f}s")
    except Exception as e:
        print(f"RESULT status=ok_but_parse_failed error={e} publish={pub}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
