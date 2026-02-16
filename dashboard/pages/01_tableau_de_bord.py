import streamlit as st
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.db import get_session
from dashboard.data.models import Document, LigneFacture, Fournisseur, Anomalie
from dashboard.analytics.achats import top_fournisseurs_by_montant
from dashboard.analytics.anomalies import get_anomaly_stats
from dashboard.analytics.qualite import score_global
from dashboard.analytics.logistique import delai_moyen_livraison
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import bar_chart

st.set_page_config(page_title="Tableau de bord", page_icon="\U0001F3E0", layout="wide")
st.title("\U0001F3E0 Tableau de bord")

engine = st.session_state.get("engine")
if not engine:
    st.error("Base de donnees non initialisee. Lancez l'application depuis app.py.")
    st.stop()

session = get_session(engine)

# --- KPIs Row 1: Overview ---
nb_docs = session.query(func.count(Document.id)).scalar()
nb_lignes = session.query(func.count(LigneFacture.id)).scalar()
nb_fournisseurs = session.query(func.count(Fournisseur.id)).scalar()
montant_total = session.query(func.sum(Document.montant_ht)).scalar() or 0

kpi_row([
    {"label": "Documents", "value": str(nb_docs)},
    {"label": "Lignes de facture", "value": str(nb_lignes)},
    {"label": "Fournisseurs", "value": str(nb_fournisseurs)},
    {"label": "Montant total HT", "value": f"{montant_total:,.2f} EUR"},
])

st.markdown("---")

# --- KPIs Row 2: Quality + Anomalies ---
quality = score_global(session)
anomaly_stats = get_anomaly_stats(session)
delai = delai_moyen_livraison(session)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Score qualite moyen", f"{quality['score_moyen']:.0%}")
with col2:
    st.metric("Docs fiables (>80%)", f"{quality['pct_fiables']:.0f}%")
with col3:
    st.metric("Anomalies detectees", str(anomaly_stats["total"]))
with col4:
    st.metric("Delai moyen livraison", f"{delai['delai_moyen_jours']:.1f} j")

st.markdown("---")

# --- Top Fournisseurs Chart ---
st.subheader("Top fournisseurs par montant")
top_f = top_fournisseurs_by_montant(session, limit=10)
if not top_f.empty:
    st.plotly_chart(bar_chart(top_f, x="fournisseur", y="montant_total",
                              title="Montant HT par fournisseur"), use_container_width=True)
else:
    st.info("Aucune donnee disponible. Importez des extractions via le module Admin.")

session.close()
