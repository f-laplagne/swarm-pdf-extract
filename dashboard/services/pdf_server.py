"""Standalone PDF/corrections HTTP server.

Lancé par start.sh en arrière-plan, indépendamment de Streamlit.
Écoute sur le port 8504 :
  GET  /<fichier>.pdf  → sert les PDFs depuis samples/
  OPTIONS /corrections → préflight CORS
  POST    /corrections → persiste les corrections inline (page 11)

Usage (appelé par start.sh) :
    PYTHONPATH=<project_root> python -m dashboard.services.pdf_server

Interfaces amont : start.sh (démarrage), 11_verification_pdf.py (fetch JS)
Interfaces aval  : SQLAlchemy engine (corrections DB), samples/ directory (PDFs)
"""

from __future__ import annotations

import functools
import http.server
import json as _json
import os
import sys
from pathlib import Path

# ── Résolution du répertoire projet ──────────────────────────────────────────
_SERVICES_DIR = Path(__file__).parent
_DASHBOARD_DIR = _SERVICES_DIR.parent
_PROJECT_ROOT = _DASHBOARD_DIR.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Configuration ─────────────────────────────────────────────────────────────
import yaml

_CONFIG_PATH = _DASHBOARD_DIR / "config.yaml"
with open(_CONFIG_PATH) as _f:
    _config = yaml.safe_load(_f)

_PDF_SERVER_PORT = int(os.environ.get("PDF_SERVER_PORT", 8504))
_SAMPLES_DIR = _PROJECT_ROOT / "samples"

# ── Engine SQLAlchemy ─────────────────────────────────────────────────────────
from dashboard.data.db import get_engine, init_db

_engine = get_engine(_config["database"]["url"])
init_db(_engine)


# ── Handler HTTP ──────────────────────────────────────────────────────────────
class _CORSHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, *_):
        pass  # silence les logs de requête

    def do_OPTIONS(self):
        """CORS preflight — requis par fetch() depuis l'iframe de la page 11."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        """POST /corrections — persiste les corrections inline."""
        from dashboard.pages._verification_helpers import handle_correction_post
        if self.path != "/corrections":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = _json.loads(self.rfile.read(length))
        except Exception:
            status, resp = 400, {"success": False, "error": "JSON invalide"}
        else:
            status, resp = handle_correction_post(body, _engine)
        payload = _json.dumps(resp).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


# ── Démarrage ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    handler = functools.partial(_CORSHandler, directory=str(_SAMPLES_DIR))
    srv = http.server.HTTPServer(("localhost", _PDF_SERVER_PORT), handler)
    print(f"PDF server listening on http://localhost:{_PDF_SERVER_PORT}", flush=True)
    srv.serve_forever()
