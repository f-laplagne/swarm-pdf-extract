import os
import sys
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

# ── Mini serveur HTTP pour les PDFs + corrections (Vérification PDF) ─────────
# Démarré ici ET dans 11_verification_pdf.py (fallback) grâce à ensure_started().
# La fonction est idempotente : si le port est déjà pris, elle ne fait rien.
PDF_SERVER_PORT = 8504
SAMPLES_DIR = Path(_PROJECT_ROOT) / "samples"

from dashboard.pages._pdf_server_startup import ensure_started as _ensure_pdf_server
_ensure_pdf_server(engine, SAMPLES_DIR, PDF_SERVER_PORT)

# Store in session state
if "engine" not in st.session_state:
    st.session_state.engine = engine
    st.session_state.config = config
    st.session_state.pdf_server_port = PDF_SERVER_PORT

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
