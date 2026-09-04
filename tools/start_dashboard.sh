#!/bin/bash
# BOTRACE dashboard 一括起動 (再起動後の@reboot用、二重起動ガード付き)
sleep 15  # boot直後のnetwork/ssh鍵エージェント待ち
cd /home/nemui/boatrace-atlas
LOG=/home/nemui/boatrace-atlas/data/dashboard_boot.log
echo "[$(date '+%F %T')] start_dashboard invoked" >> $LOG
if ! pgrep -f "tools/serve_public.py" > /dev/null; then
  setsid nohup /usr/bin/python3 tools/serve_public.py >> $LOG 2>&1 < /dev/null &
  echo "[$(date '+%F %T')] serve_public started" >> $LOG
else
  echo "[$(date '+%F %T')] serve_public already running" >> $LOG
fi
if ! pgrep -f "live_sync_loop.sh" > /dev/null; then
  setsid nohup ./tools/live_sync_loop.sh >> $LOG 2>&1 < /dev/null &
  echo "[$(date '+%F %T')] live_sync_loop started" >> $LOG
else
  echo "[$(date '+%F %T')] live_sync_loop already running" >> $LOG
fi
