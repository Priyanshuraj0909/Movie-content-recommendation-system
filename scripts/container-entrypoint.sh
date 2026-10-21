#!/usr/bin/env bash
set -euo pipefail

cd /app
scripts/setup_demo.sh --skip-evaluation

uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 &
api_pid=$!
streamlit run frontend/app.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.headless true &
ui_pid=$!

cleanup() {
  kill -TERM "$api_pid" "$ui_pid" 2>/dev/null || true
  wait "$api_pid" "$ui_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

status=0
wait -n "$api_pid" "$ui_pid" || status=$?
exit "$status"
