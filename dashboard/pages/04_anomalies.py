import streamlit as st
import yaml
import os
from dashboard.data.db import get_session
from dashboard.data.models import Anomalie, Document
from dashboard.analytics.anomalies import run_anomaly_detection, get_anomaly_stats
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import bar_chart
from dashboard.components.data_table import data_table
import pandas as pd

st.set_page_config(page_title="Anomalies", page_icon="\u26A0\uFE0F", layout="wide")
st.title("\u26A0\uFE0F Detection d'Anomalies")

engine = st.session_state.get("engine")
config = st.session_state.get("config", {})
if not engine:
    from dashboard.data.db import get_engine, init_db
    engine = get_engine()
    init_db(engine)

session = get_session(engine)

# Run detection button
if st.button("Relancer la detection d'anomalies"):
    rules = config.get("anomalies", {}).get("regles", [])
    with st.spinner("Analyse en cours..."):
        anomalies = run_anomaly_detection(session, rules)
        session.commit()
    st.success(f"{len(anomalies)} anomalies detectees.")

# --- Stats ---
stats = get_anomaly_stats(session)

kpi_row([
    {"label": "Total anomalies", "value": str(stats["total"])},
    {"label": "Critiques", "value": str(stats["par_severite"].get("critique", 0))},
    {"label": "Warnings", "value": str(stats["par_severite"].get("warning", 0))},
    {"label": "Info", "value": str(stats["par_severite"].get("info", 0))},
])

st.markdown("---")

# --- Anomaly list ---
anomalies = (
    session.query(
        Anomalie.regle_id, Anomalie.type_anomalie, Anomalie.severite,
        Anomalie.description, Document.fichier,
    )
    .join(Document, Anomalie.document_id == Document.id)
    .all()
)

if anomalies:
    df = pd.DataFrame(anomalies, columns=["Regle", "Type", "Severite", "Description", "Document"])

    # Filter
    severite_filter = st.multiselect("Filtrer par severite", ["critique", "warning", "info"],
                                     default=["critique", "warning", "info"])
    df_filtered = df[df["Severite"].isin(severite_filter)]

    # Chart
    type_counts = df_filtered["Type"].value_counts().reset_index()
    type_counts.columns = ["type", "count"]
    st.plotly_chart(bar_chart(type_counts, x="type", y="count",
                              title="Anomalies par type"), use_container_width=True)

    data_table(df_filtered, "Liste des anomalies")
else:
    st.info("Aucune anomalie detectee. Cliquez sur 'Relancer la detection' pour analyser.")

session.close()
