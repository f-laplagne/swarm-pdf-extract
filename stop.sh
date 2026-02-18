#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.streamlit.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "Dashboard stopped (PID $PID)"
    else
        echo "Process $PID already stopped"
    fi
    rm -f "$PID_FILE"
else
    pkill -f "streamlit run.*app.py" 2>/dev/null && echo "Dashboard stopped" || echo "No running dashboard found"
fi
