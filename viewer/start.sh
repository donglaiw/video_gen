#!/usr/bin/env bash
# Start the video viewer in a detached tmux session (idempotent).
# Localhost only; from the Mac:  ssh -N -L 8765:localhost:8765 donglai@cajal
set -euo pipefail
PORT="${PORT:-8765}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/../env/bin/python"
[ -x "$PY" ] || PY=python3

if tmux has-session -t viewer 2>/dev/null; then
  echo "viewer already running (tmux attach -t viewer). Restart: tmux kill-session -t viewer && $0"
else
  tmux new-session -d -s viewer "$PY $HERE/server.py --port $PORT 2>&1 | tee -a $HERE/../logs/viewer.log"
  echo "started in tmux session 'viewer' on 127.0.0.1:$PORT"
fi
echo "Mac: ssh -N -L $PORT:localhost:$PORT donglai@cajal   then open http://localhost:$PORT"
