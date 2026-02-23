#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.streamlit.pid"
LOG_FILE="$SCRIPT_DIR/.streamlit.log"
PDF_PID_FILE="$SCRIPT_DIR/.pdf_server.pid"
PDF_LOG_FILE="$SCRIPT_DIR/.pdf_server.log"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Dashboard already running (PID $(cat "$PID_FILE"))"
    exit 0
fi

# ── Serveur PDF (port 8504) ────────────────────────────────────────────────
# Démarré indépendamment de Streamlit pour éviter tout problème de timing de session.
if ! nc -z localhost 8504 2>/dev/null; then
    nohup env PYTHONPATH="$SCRIPT_DIR" python -m dashboard.services.pdf_server \
        > "$PDF_LOG_FILE" 2>&1 &
    echo $! > "$PDF_PID_FILE"
    sleep 1
    if nc -z localhost 8504 2>/dev/null; then
        echo "PDF server started  (PID $(cat "$PDF_PID_FILE")) → http://localhost:8504"
    else
        echo "⚠ PDF server failed to start — check $PDF_LOG_FILE"
    fi
else
    echo "PDF server already running on port 8504"
fi

# ── Dashboard Streamlit (port 8501) ───────────────────────────────────────
nohup env PYTHONPATH="$SCRIPT_DIR" streamlit run "$SCRIPT_DIR/dashboard/app.py" \
    --server.port 8501 --server.headless true > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
sleep 2

if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Dashboard started       (PID $(cat "$PID_FILE")) → http://localhost:8501"
else
    echo "Failed to start dashboard. Check $LOG_FILE"
    exit 1
fi
