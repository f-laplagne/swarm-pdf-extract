"""Utility to start the PDF/corrections HTTP server exactly once.

Both app.py and 11_verification_pdf.py call `ensure_started()` so the server
launches regardless of which page the user visits first.

Interfaces amont : app.py, 11_verification_pdf.py
Interfaces aval  : http.server daemon thread (GET PDFs, OPTIONS CORS, POST /corrections)
"""

from __future__ import annotations

import functools
import http.server
import json as _json
import socket
import threading
from pathlib import Path


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0


def ensure_started(engine, samples_dir: Path, port: int) -> None:
    """Start the PDF/corrections HTTP server if the port is free.

    Idempotent: if the port is already bound, this is a no-op.
    The engine is captured in a closure so do_POST always uses
    the same DB connection as the caller.

    Args:
        engine:      SQLAlchemy engine (used for POST /corrections).
        samples_dir: Directory served for GET requests (PDF files).
        port:        TCP port to listen on (typically 8504).
    """
    if not _port_free(port):
        return

    _engine = engine  # closure capture — valid for the lifetime of the thread

    class _CORSHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

        def log_message(self, *_):
            pass

        def do_OPTIONS(self):
            """CORS preflight — required by fetch() from the page-11 iframe."""
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self):
            """POST /corrections — persists inline corrections from page 11."""
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

    handler = functools.partial(_CORSHandler, directory=str(samples_dir))
    srv = http.server.HTTPServer(("localhost", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
