import os
import sys
import threading
import socket
import functools
import http.server
from pathlib import Path

# Ensure project root is in sys.path so "from dashboard.*" imports work
# regardless of where Streamlit is launched from (cd dashboard/ or project root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st
import yaml

from dashboard.data.db import init_db, get_engine, get_session
from dashboard.styles.theme import inject_theme

# Page config
st.set_page_config(
    page_title="Rationalize",
    page_icon="\U0001F4CA",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_theme()

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

# Init DB — db.py resolves relative sqlite paths from dashboard dir
engine = get_engine(config["database"]["url"])
init_db(engine)

# Store in session state
if "engine" not in st.session_state:
    st.session_state.engine = engine
    st.session_state.config = config

    # Composition root: instantiate adapters
    from dashboard.adapters.outbound.redis_cache import RedisCacheAdapter

    # Session factory for repositories (pages create repos from session)
    st.session_state.get_session = get_session

    # Cache adapter (Redis if available, otherwise no-op)
    redis_client = None
    redis_url = config.get("cache", {}).get("redis_url") or os.environ.get(
        "REDIS_URL"
    )
    if redis_url:
        try:
            import redis

            redis_client = redis.from_url(redis_url)
            redis_client.ping()
        except Exception:
            redis_client = None
    st.session_state.cache = RedisCacheAdapter(redis_client=redis_client)

    # ── Mini serveur HTTP pour les PDFs (Vérification PDF) ──────────────────
    # Sert les fichiers depuis samples/ sur un port dédié, utilisé par PDF.js
    PDF_SERVER_PORT = 8504
    SAMPLES_DIR = Path(_PROJECT_ROOT) / "samples"

    def _port_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("localhost", port)) != 0

    class _CORSHandler(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()
        def log_message(self, *_):
            pass

    if _port_free(PDF_SERVER_PORT):
        handler = functools.partial(_CORSHandler, directory=str(SAMPLES_DIR))
        srv = http.server.HTTPServer(("localhost", PDF_SERVER_PORT), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    st.session_state.pdf_server_port = PDF_SERVER_PORT

st.title("\U0001F4CA Rationalize")
st.markdown("### Outil d'Analyse & Optimisation des Achats et Logistique")
st.markdown("---")
st.markdown("Utilisez le menu lateral pour naviguer entre les modules d'analyse.")
st.markdown("""
**Modules disponibles :**
- **Tableau de bord** -- Vue executive avec KPIs globaux
- **Achats** -- Rationalisation et benchmark fournisseurs
- **Logistique** -- Optimisation des flux et regroupement
- **Anomalies** -- Detection d'incoherences et doublons
- **Tendances** -- Evolution temporelle des prix et volumes
- **Qualite** -- Suivi de la qualite des donnees extraites
- **Transport** -- Visualisation des routes d'expedition sur carte
- **Corrections** -- Correction manuelle des extractions faibles
- **Admin** -- Ingestion et configuration
- **Vérification PDF** -- Comparaison PDF original / données extraites
""")
