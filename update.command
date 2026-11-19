#!/bin/bash
cd "$(dirname "$0")" || exit 1
echo "正在更新数据并发布上线，请稍候…"
python3 run_update.py
echo
read -n 1 -s -r -p "按任意键关闭窗口"
