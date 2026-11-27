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
from datetime import date, datetime

import config

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
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
    results = []
    try:
        for remote in (config.PUBLISH_REMOTES or ["origin"]):
            p = _run(["git", "push", remote, config.PUBLISH_BRANCH], 300, log, env=env)
            if p is None:
                results.append(f"{remote}:timeout")
            elif p.returncode != 0:
                results.append(f"{remote}:failed")
            else:
                results.append(f"{remote}:ok")
    finally:
        if askpass and os.path.exists(askpass):
            os.remove(askpass)

    if all(r.endswith(":ok") for r in results):
        return "ok"
    # 只要有一个成功就算已发布，但把失败明细带出去
    if any(r.endswith(":ok") for r in results):
        return "ok(" + ",".join(results) + ")"
    return "push_failed(" + ",".join(results) + ")"


def _data_end():
    """当前数据文件覆盖到的最后交易日，用于失败时提示「信息更新到哪天」。"""
    try:
        src = open(os.path.join(ROOT, "data", "dashboard_data.js"), encoding="utf-8").read()
        return json.loads(src[len("window.DASHBOARD_DATA="):-2])["meta"]["end"]
    except Exception:
        return ""


def write_status(status, publish, detail="", elapsed=0, extra=None):
    """写入 data/status.json（完整记录）与 data/status.js（页面用，只含展示字段）。

    publish 在推送前未知，故不写入 status.js，避免页面拿到 pending 这类中间值。
    """
    payload = {
        "status": status,
        "at": time.strftime("%Y-%m-%d %H:%M"),
        "date": _data_end(),
        "publish": publish,
        "elapsed": round(elapsed),
    }
    if detail:
        payload["detail"] = detail[:500]
    if extra:
        payload.update(extra)
    with open(os.path.join(DATA, "status.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    page = {k: payload[k] for k in ("status", "at", "date", "detail") if k in payload}
    with open(os.path.join(DATA, "status.js"), "w", encoding="utf-8") as f:
        f.write("window.UPDATE_STATUS=")
        json.dump(page, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    return payload


def _fomc_stale(days):
    path = os.path.join(ROOT, "data", "fomc_data.json")
    if not os.path.exists(path):
        return True
    try:
        gen = (json.load(open(path, encoding="utf-8")).get("meta") or {}).get("generated_at")
        if not gen:
            return True
        age = (datetime.now() - datetime.strptime(gen, "%Y-%m-%d %H:%M")).days
        return age > days
    except Exception:
        return True


def _deriv_stale(days):
    """衍生品数据是否超过 days 天未更新。"""
    path = os.path.join(ROOT, "data", "deriv_data.json")
    if not os.path.exists(path):
        return True
    try:
        d = json.load(open(path, encoding="utf-8"))
        end = (d.get("meta") or {}).get("end")
        if not end:
            return True
        age = (date.today() - datetime.strptime(end, "%Y-%m-%d").date()).days
        return age > days
    except Exception:
        return True


def main():
    t0 = time.time()
    status, detail, extra, rc = "ok", "", {}, 0

    with open(LOG, "a", encoding="utf-8") as log:
        log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        log.flush()

        r = _run([sys.executable, "fetch_data.py"], TIMEOUT, log)
        if r is None:
            status, detail, rc = "timeout", f"fetch_data 超时（{TIMEOUT}s）", 1
        elif r.returncode != 0:
            status, detail, rc = "failed", (r.stderr or r.stdout or "fetch failed")[-500:], 1

        if rc == 0:
            try:
                src = open(os.path.join(ROOT, "data", "dashboard_data.js"), encoding="utf-8").read()
                m = json.loads(src[len("window.DASHBOARD_DATA="):-2])["meta"]
                extra = {"verify": (m.get("verification") or {}).get("status", "?"),
                         "news": len(m.get("news") or [])}
            except Exception:
                pass

        # 衍生品子页（基差/拥挤度）数据量大且网关慢，只在数据陈旧超过 3 天时刷新；
        # 失败不影响主看板，页面自身会显示上一次的 as-of 日期。
        if rc == 0 and _deriv_stale(3):
            log.write("\n--- fetch_deriv ---\n")
            log.flush()
            rd = _run([sys.executable, "fetch_deriv.py"], 900, log)
            log.write(f"DERIV {'ok' if rd is not None and rd.returncode == 0 else 'failed'}\n")
            log.flush()
        elif rc == 0:
            log.write("DERIV skipped (fresh)\n")

        # 经济数据日历：周历每周变化，7 天内刷新一次即可
        if rc == 0 and _fomc_stale(7):
            log.write("\n--- fetch_econ ---\n")
            log.flush()
            re_ = _run([sys.executable, "fetch_econ.py"], 300, log)
            log.write(f"ECON {'ok' if re_ is not None and re_.returncode == 0 else 'failed'}\n")
            log.flush()

        # FOMC 会议日历通常一年才变一次，7 天刷新即可
        if rc == 0 and _fomc_stale(7):
            log.write("\n--- fetch_fomc ---\n")
            log.flush()
            rf = _run([sys.executable, "fetch_fomc.py"], 180, log)
            log.write(f"FOMC {'ok' if rf is not None and rf.returncode == 0 else 'failed'}\n")
            log.flush()

        # 先把本次结果落盘，再构建发布：这样失败信息也能上线被人看到
        write_status(status, "pending", detail, time.time() - t0, extra)

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

        write_status(status, pub, detail, time.time() - t0, extra)

        if rc != 0:
            log.write(f"\nSTATUS {status}: {detail[:300]}\n")
            print((detail or "fetch failed")[-1500:])
            print(f"RESULT status={status} date={_data_end()} publish={pub} "
                  f"elapsed={time.time()-t0:.0f}s")

    if rc != 0:
        return 1

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
