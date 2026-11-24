#!/bin/bash
# launchd 入口：不经过 DSH Agent，直接执行 run_update.py。
# 09:30 / 11:30 两个 calendar 时间共用一个 job；用目录锁防止重叠。
cd "$(dirname "$0")" || exit 1
LOCK="$PWD/.launchd.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "SKIP overlap: another update is running"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# /usr/bin/python3 已确认包含 pandas / requests（macOS 自带 Python 3.9）
/usr/bin/python3 run_update.py
