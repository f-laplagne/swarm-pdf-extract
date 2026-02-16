import streamlit as st
import yaml
import os

from dashboard.data.db import init_db, get_engine, get_session

# Page config
st.set_page_config(
    page_title="Rationalize",
    page_icon="\U0001F4CA",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
""")
