#!/bin/bash
# 当日ライブ同期ループ(完全ローカル): 3分毎に sub PC から吸い出して
# data/live_today.json を更新する。git には触らない。
# 使い方: nohup bash tools/live_sync_loop.sh >/tmp/botrace_live_sync.log 2>&1 &
cd "$(dirname "$0")/.." || exit 1
while true; do
  python3 tools/export_live_today.py
  sleep 180
done
