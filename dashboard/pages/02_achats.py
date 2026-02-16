import streamlit as st
from dashboard.data.db import get_session
from dashboard.analytics.achats import (
    top_fournisseurs_by_montant, prix_moyen_par_matiere,
    ecarts_prix_fournisseurs, indice_fragmentation, economie_potentielle,
)
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import bar_chart, scatter_chart
from dashboard.components.data_table import data_table

st.set_page_config(page_title="Achats", page_icon="\U0001F4B0", layout="wide")
st.title("\U0001F4B0 Rationalisation Achats")

engine = st.session_state.get("engine")
if not engine:
    from dashboard.data.db import get_engine, init_db
    engine = get_engine()
    init_db(engine)

session = get_session(engine)

# --- KPIs ---
top_f = top_fournisseurs_by_montant(session, limit=5)
fragmentation = indice_fragmentation(session)
eco = economie_potentielle(session)

nb_multi = len(fragmentation[fragmentation["nb_fournisseurs"] > 1]) if not fragmentation.empty else 0

kpi_row([
    {"label": "Fournisseurs actifs", "value": str(len(top_f))},
    {"label": "Matieres multi-fournisseurs", "value": str(nb_multi)},
    {"label": "Economie potentielle", "value": f"{eco['total_economie']:,.2f} EUR"},
])

st.markdown("---")

# --- Top fournisseurs ---
tab1, tab2, tab3 = st.tabs(["Benchmark prix", "Fragmentation", "Ecarts fournisseurs"])

with tab1:
    prix = prix_moyen_par_matiere(session)
    if not prix.empty:
        st.plotly_chart(bar_chart(prix, x="type_matiere", y="prix_unitaire_moyen",
                                  title="Prix unitaire moyen par matiere"), use_container_width=True)
        data_table(prix, "Detail prix par matiere")

with tab2:
    if not fragmentation.empty:
        data_table(fragmentation, "Indice de fragmentation fournisseurs")

with tab3:
    ecarts = ecarts_prix_fournisseurs(session)
    if not ecarts.empty:
        st.plotly_chart(bar_chart(ecarts, x="type_matiere", y="ecart_pct",
                                  title="Ecarts de prix entre fournisseurs (%)"), use_container_width=True)
        data_table(ecarts, "Detail des ecarts")
    else:
        st.info("Pas d'ecart significatif detecte.")

# --- Savings details ---
if not eco["details"].empty:
    st.subheader("Detail des economies potentielles")
    data_table(eco["details"], "Economies par ligne")

session.close()
