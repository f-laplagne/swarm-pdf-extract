import streamlit as st
import os
from dashboard.data.db import get_session, init_db
from dashboard.data.ingestion import ingest_directory
from dashboard.data.models import Document, LigneFacture, Fournisseur, Anomalie
from sqlalchemy import func

st.set_page_config(page_title="Administration", page_icon="\u2699\uFE0F", layout="wide")
st.title("\u2699\uFE0F Administration")

engine = st.session_state.get("engine")
config = st.session_state.get("config", {})
if not engine:
    st.error("DB non initialisee.")
    st.stop()

session = get_session(engine)

# --- Ingestion ---
st.subheader("Ingestion des donnees")

extractions_dir = config.get("ingestion", {}).get("extractions_dir", "../output/extractions")
# Resolve relative to dashboard dir
abs_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", extractions_dir))

st.text(f"Repertoire source : {abs_dir}")

if st.button("Lancer l'ingestion"):
    if os.path.isdir(abs_dir):
        with st.spinner("Ingestion en cours..."):
            stats = ingest_directory(session, abs_dir)
        st.success(f"Ingestion terminee : {stats['ingested']} importes, {stats['skipped']} deja presents, {stats['errors']} erreurs.")
        if stats["files"]:
            st.json(stats["files"])
    else:
        st.error(f"Repertoire introuvable : {abs_dir}")

st.markdown("---")

# --- DB Stats ---
st.subheader("Etat de la base de donnees")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Documents", session.query(func.count(Document.id)).scalar())
with col2:
    st.metric("Lignes", session.query(func.count(LigneFacture.id)).scalar())
with col3:
    st.metric("Fournisseurs", session.query(func.count(Fournisseur.id)).scalar())
with col4:
    st.metric("Anomalies", session.query(func.count(Anomalie.id)).scalar())

st.markdown("---")

# --- Reset DB ---
st.subheader("Maintenance")
if st.button("Reinitialiser la base de donnees", type="secondary"):
    from dashboard.data.models import Base
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    st.success("Base de donnees reinitialisee.")
    st.rerun()

session.close()
