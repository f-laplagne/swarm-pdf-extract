import streamlit as st
from dashboard.data.db import get_session
from dashboard.analytics.logistique import (
    top_routes, matrice_od, delai_moyen_livraison, opportunites_regroupement,
)
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import bar_chart, heatmap
from dashboard.components.data_table import data_table

st.set_page_config(page_title="Logistique", page_icon="\U0001F69B", layout="wide")
st.title("\U0001F69B Optimisation Logistique")

engine = st.session_state.get("engine")
if not engine:
    st.error("DB non initialisee.")
    st.stop()

session = get_session(engine)

# --- KPIs ---
delai = delai_moyen_livraison(session)
routes = top_routes(session, limit=10)
regroupements = opportunites_regroupement(session, fenetre_jours=7)

kpi_row([
    {"label": "Routes distinctes", "value": str(len(routes))},
    {"label": "Delai moyen", "value": f"{delai['delai_moyen_jours']:.1f} jours"},
    {"label": "Trajets analyses", "value": str(delai["nb_trajets"])},
    {"label": "Regroupements possibles", "value": str(len(regroupements))},
])

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["Top Routes", "Matrice O/D", "Regroupements"])

with tab1:
    if not routes.empty:
        st.plotly_chart(bar_chart(routes, x="route", y="nb_trajets",
                                  title="Routes les plus frequentes"), use_container_width=True)
        data_table(routes, "Detail des routes")

with tab2:
    od = matrice_od(session)
    if not od.empty:
        st.plotly_chart(heatmap(od, title="Matrice Origine / Destination"), use_container_width=True)

with tab3:
    if not regroupements.empty:
        data_table(regroupements, "Opportunites de regroupement")
    else:
        st.info("Pas d'opportunite de regroupement identifiee.")

session.close()
