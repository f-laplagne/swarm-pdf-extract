#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.streamlit.pid"
LOG_FILE="$SCRIPT_DIR/.streamlit.log"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Dashboard already running (PID $(cat "$PID_FILE"))"
    exit 0
fi

nohup env PYTHONPATH="$SCRIPT_DIR" streamlit run "$SCRIPT_DIR/dashboard/app.py" --server.port 8501 --server.headless true > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
sleep 2

if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Dashboard started (PID $(cat "$PID_FILE")) → http://localhost:8501"
else
    echo "Failed to start. Check $LOG_FILE"
    exit 1
fi
