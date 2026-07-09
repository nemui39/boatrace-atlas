#!/bin/bash
# 当日ライブ同期ループ: 5分毎に sub PC から吸い出して data/live_today.json を更新し push する。
# 使い方: nohup bash tools/live_sync_loop.sh >/tmp/botrace_live_sync.log 2>&1 &
cd "$(dirname "$0")/.." || exit 1
while true; do
  if python3 tools/export_live_today.py; then
    if ! git diff --quiet -- data/live_today.json 2>/dev/null || [ -n "$(git status --porcelain data/live_today.json)" ]; then
      git add data/live_today.json
      git commit -qm "live: sync $(date +%H:%M)"
      git push -q
    fi
  fi
  sleep 300
done
