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
import time
import urllib.request

import config

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "update.log")
TIMEOUT = 600


def main():
    t0 = time.time()
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        log.flush()
        try:
            r = subprocess.run(
                [sys.executable, "fetch_data.py"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            print(f"RESULT status=timeout after {TIMEOUT}s")
            log.write("TIMEOUT\n")
            return 1
        log.write(r.stdout or "")
        if r.stderr:
            log.write("\n[stderr]\n" + r.stderr[-4000:])
        if r.returncode != 0:
            print((r.stderr or r.stdout or "fetch failed")[-1500:])
            print(f"RESULT status=failed code={r.returncode}")
            return 1

    # 如果配置了 Netlify Deploy Hook：重建 dist 并触发线上发布
    if config.NETLIFY_DEPLOY_HOOK:
        try:
            subprocess.run([sys.executable, "build_site.py"], cwd=ROOT, check=True, capture_output=True, text=True, timeout=120)
            req = urllib.request.Request(config.NETLIFY_DEPLOY_HOOK, method="POST")
            urllib.request.urlopen(req, timeout=30).read()
            print("DEPLOY triggered netlify")
        except Exception as e:
            print(f"DEPLOY failed: {str(e)[:120]}")

    try:
        src = open(os.path.join(ROOT, "data", "dashboard_data.js"), encoding="utf-8").read()
        d = json.loads(src[len("window.DASHBOARD_DATA="):-2])
        x = d["latest"]
        print(f"RESULT status=ok date={x['date']} flow={x['flow']} flow5={x['flow5']} "
              f"flow20={x['flow20']} coverage={x['coverage']} start={d['meta']['start']} "
              f"elapsed={time.time()-t0:.0f}s")
    except Exception as e:
        print(f"RESULT status=ok_but_parse_failed error={e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
