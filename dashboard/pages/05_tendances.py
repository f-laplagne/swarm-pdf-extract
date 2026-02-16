import streamlit as st
from dashboard.data.db import get_session
from dashboard.analytics.tendances import volume_mensuel, evolution_prix_matiere
from dashboard.data.entity_resolution import get_distinct_values, expand_canonical
from dashboard.components.charts import bar_chart, line_chart
from dashboard.components.data_table import data_table

st.set_page_config(page_title="Tendances", page_icon="\U0001F4C8", layout="wide")
st.title("\U0001F4C8 Tendances Temporelles")

engine = st.session_state.get("engine")
if not engine:
    from dashboard.data.db import get_engine, init_db
    engine = get_engine()
    init_db(engine)

session = get_session(engine)

# --- Volume mensuel ---
st.subheader("Volume d'achats mensuel")
vol = volume_mensuel(session)
if not vol.empty:
    st.plotly_chart(bar_chart(vol, x="mois", y="montant_total",
                              title="Montant HT mensuel"), use_container_width=True)

# --- Evolution prix par matiere ---
st.subheader("Evolution des prix par matiere")
matieres = get_distinct_values(session, "material")

if matieres:
    selected = st.selectbox("Selectionner une matiere", matieres)
    if selected:
        raw_values = expand_canonical(session, "material", selected)
        evo = evolution_prix_matiere(session, selected, raw_values=raw_values)
        if not evo.empty:
            st.plotly_chart(line_chart(evo, x="mois", y="prix_unitaire_moyen",
                                       title=f"Prix unitaire moyen -- {selected}"), use_container_width=True)
            data_table(evo, f"Detail prix -- {selected}")
        else:
            st.info("Pas de donnees temporelles pour cette matiere.")

session.close()
