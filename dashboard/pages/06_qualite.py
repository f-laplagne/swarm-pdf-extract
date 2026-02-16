import streamlit as st
import pandas as pd
from dashboard.data.db import get_session
from dashboard.data.models import LigneFacture, Fournisseur, Document
from dashboard.analytics.qualite import score_global, confiance_par_champ, documents_par_qualite
from dashboard.data.entity_resolution import get_mappings, get_prefix_mappings, resolve_column
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import radar_chart, bar_chart
from dashboard.components.data_table import data_table

st.set_page_config(page_title="Qualite", page_icon="\U0001F50D", layout="wide")
st.title("\U0001F50D Qualite des Donnees")

engine = st.session_state.get("engine")
if not engine:
    from dashboard.data.db import get_engine, init_db
    engine = get_engine()
    init_db(engine)

session = get_session(engine)

# --- KPIs ---
quality = score_global(session)

kpi_row([
    {"label": "Score moyen", "value": f"{quality['score_moyen']:.0%}"},
    {"label": "Documents analyses", "value": str(quality["nb_documents"])},
    {"label": "Docs fiables (>80%)", "value": f"{quality['pct_fiables']:.0f}%"},
])

st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs([
    "Confiance par champ", "Documents par qualite",
    "Qualite par matiere", "Qualite par fournisseur",
])

with tab1:
    conf = confiance_par_champ(session)
    if not conf.empty:
        categories = conf.index.tolist()
        values = conf["moyenne"].tolist()
        st.plotly_chart(radar_chart(categories, values,
                                     title="Score de confiance moyen par champ"), use_container_width=True)
        data_table(conf.reset_index().rename(columns={"index": "champ"}), "Detail confiance par champ")

with tab2:
    docs = documents_par_qualite(session)
    if not docs.empty:
        st.plotly_chart(bar_chart(docs, x="fichier", y="confiance_globale",
                                  title="Confiance globale par document"), use_container_width=True)
        data_table(docs, "Documents tries par qualite")

with tab3:
    rows = (
        session.query(
            LigneFacture.type_matiere,
            LigneFacture.conf_type_matiere,
            LigneFacture.conf_prix_unitaire,
            LigneFacture.conf_quantite,
            LigneFacture.conf_prix_total,
        )
        .filter(LigneFacture.type_matiere.isnot(None))
        .all()
    )
    if rows:
        df_mat = pd.DataFrame(rows, columns=[
            "type_matiere", "conf_matiere", "conf_prix", "conf_quantite", "conf_total",
        ])
        mat_mappings = get_mappings(session, "material")
        mat_prefix = get_prefix_mappings(session, "material")
        resolve_column(df_mat, "type_matiere", mat_mappings, mat_prefix)

        agg = (
            df_mat.groupby("resolved_type_matiere")
            .agg(
                confiance_moyenne=("conf_matiere", "mean"),
                conf_prix_moy=("conf_prix", "mean"),
                nb_lignes=("conf_matiere", "count"),
            )
            .reset_index()
            .rename(columns={"resolved_type_matiere": "Matiere"})
            .sort_values("confiance_moyenne", ascending=False)
        )
        st.plotly_chart(bar_chart(agg, x="Matiere", y="confiance_moyenne",
                                  title="Confiance moyenne par matiere (resolu)"), use_container_width=True)
        data_table(agg, "Detail qualite par matiere")
    else:
        st.info("Aucune donnee de matiere disponible.")

with tab4:
    rows = (
        session.query(
            Fournisseur.nom,
            Document.confiance_globale,
        )
        .join(Document, Document.fournisseur_id == Fournisseur.id)
        .filter(Fournisseur.nom.isnot(None))
        .all()
    )
    if rows:
        df_four = pd.DataFrame(rows, columns=["fournisseur", "confiance_globale"])
        sup_mappings = get_mappings(session, "supplier")
        sup_prefix = get_prefix_mappings(session, "supplier")
        resolve_column(df_four, "fournisseur", sup_mappings, sup_prefix)

        agg = (
            df_four.groupby("resolved_fournisseur")
            .agg(
                confiance_moyenne=("confiance_globale", "mean"),
                nb_documents=("confiance_globale", "count"),
            )
            .reset_index()
            .rename(columns={"resolved_fournisseur": "Fournisseur"})
            .sort_values("confiance_moyenne", ascending=False)
        )
        st.plotly_chart(bar_chart(agg, x="Fournisseur", y="confiance_moyenne",
                                  title="Confiance moyenne par fournisseur (resolu)"), use_container_width=True)
        data_table(agg, "Detail qualite par fournisseur")
    else:
        st.info("Aucune donnee de fournisseur disponible.")

session.close()
