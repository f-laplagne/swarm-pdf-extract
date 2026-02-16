import streamlit as st
from dashboard.data.db import get_session
from dashboard.analytics.qualite import score_global, confiance_par_champ, documents_par_qualite
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

tab1, tab2 = st.tabs(["Confiance par champ", "Documents par qualite"])

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

session.close()
