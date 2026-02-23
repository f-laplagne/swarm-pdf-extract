#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.streamlit.pid"
PDF_PID_FILE="$SCRIPT_DIR/.pdf_server.pid"

# ── Arrêt Dashboard Streamlit ─────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "Dashboard stopped (PID $PID)"
    else
        echo "Dashboard process $PID already stopped"
    fi
    rm -f "$PID_FILE"
else
    pkill -f "streamlit run.*app.py" 2>/dev/null && echo "Dashboard stopped" || echo "No running dashboard found"
fi

# ── Arrêt PDF server ──────────────────────────────────────────────────────
if [ -f "$PDF_PID_FILE" ]; then
    PDF_PID=$(cat "$PDF_PID_FILE")
    if kill -0 "$PDF_PID" 2>/dev/null; then
        kill "$PDF_PID" && echo "PDF server stopped (PID $PDF_PID)"
    else
        echo "PDF server process $PDF_PID already stopped"
    fi
    rm -f "$PDF_PID_FILE"
else
    pkill -f "dashboard.services.pdf_server" 2>/dev/null && echo "PDF server stopped" || echo "No running PDF server found"
fi
