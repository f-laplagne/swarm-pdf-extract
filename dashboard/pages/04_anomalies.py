import streamlit as st
import yaml
import os
from dashboard.data.db import get_session
from dashboard.data.models import Anomalie, Document, LigneFacture, Fournisseur
from dashboard.analytics.anomalies import run_anomaly_detection, get_anomaly_stats
from dashboard.data.entity_resolution import get_mappings, get_prefix_mappings, resolve_column
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

# --- Anomaly list with entity resolution ---
anomalies = (
    session.query(
        Anomalie.regle_id, Anomalie.type_anomalie, Anomalie.severite,
        Anomalie.description, Document.fichier,
        LigneFacture.type_matiere, LigneFacture.lieu_depart,
        LigneFacture.lieu_arrivee, Fournisseur.nom.label("fournisseur"),
    )
    .join(Document, Anomalie.document_id == Document.id)
    .outerjoin(LigneFacture, Anomalie.ligne_id == LigneFacture.id)
    .outerjoin(Fournisseur, Document.fournisseur_id == Fournisseur.id)
    .all()
)

if anomalies:
    df = pd.DataFrame(anomalies, columns=[
        "Regle", "Type", "Severite", "Description", "Document",
        "type_matiere", "lieu_depart", "lieu_arrivee", "fournisseur",
    ])

    # Apply entity resolution to show canonical names
    mat_mappings = get_mappings(session, "material")
    mat_prefix = get_prefix_mappings(session, "material")
    resolve_column(df, "type_matiere", mat_mappings, mat_prefix)

    loc_mappings = get_mappings(session, "location")
    loc_prefix = get_prefix_mappings(session, "location")
    resolve_column(df, "lieu_depart", loc_mappings, loc_prefix)
    resolve_column(df, "lieu_arrivee", loc_mappings, loc_prefix)

    sup_mappings = get_mappings(session, "supplier")
    sup_prefix = get_prefix_mappings(session, "supplier")
    resolve_column(df, "fournisseur", sup_mappings, sup_prefix)

    # Rename resolved columns for display
    df["Matiere"] = df["resolved_type_matiere"]
    df["Fournisseur"] = df["resolved_fournisseur"]
    df["Lieu depart"] = df["resolved_lieu_depart"]
    df["Lieu arrivee"] = df["resolved_lieu_arrivee"]

    display_cols = ["Regle", "Type", "Severite", "Description", "Document",
                    "Matiere", "Fournisseur", "Lieu depart", "Lieu arrivee"]

    # Filter
    severite_filter = st.multiselect("Filtrer par severite", ["critique", "warning", "info"],
                                     default=["critique", "warning", "info"])
    df_filtered = df[df["Severite"].isin(severite_filter)]

    # Chart
    type_counts = df_filtered["Type"].value_counts().reset_index()
    type_counts.columns = ["type", "count"]
    st.plotly_chart(bar_chart(type_counts, x="type", y="count",
                              title="Anomalies par type"), use_container_width=True)

    data_table(df_filtered[display_cols], "Liste des anomalies")
else:
    st.info("Aucune anomalie detectee. Cliquez sur 'Relancer la detection' pour analyser.")

session.close()
