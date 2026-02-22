import streamlit as st
from dashboard.data.db import get_session
from dashboard.analytics.tendances import (
    volume_mensuel,
    evolution_prix_matiere,
    delai_expedition_stats,
    distribution_delais,
    evolution_delai_mensuel,
    delai_par_route,
    delai_par_fournisseur,
    detail_expeditions,
)
from dashboard.data.entity_resolution import get_distinct_values, expand_canonical
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import bar_chart, line_chart
from dashboard.components.data_table import data_table

st.set_page_config(page_title="Tendances", page_icon="\U0001F4C8", layout="wide")
from dashboard.styles.theme import inject_theme
inject_theme()

st.title("\U0001F4C8 Tendances Temporelles")

engine = st.session_state.get("engine")
if not engine:
    from dashboard.data.db import get_engine, init_db
    engine = get_engine()
    init_db(engine)

session = get_session(engine)

# ===================================================================
# Delais d'expedition (primary section)
# ===================================================================
st.header("Delais d'expedition")

stats = delai_expedition_stats(session)
kpi_row([
    {"label": "Expeditions analysees", "value": str(stats["nb_trajets"])},
    {"label": "Delai moyen", "value": f"{stats['delai_moyen']} j"},
    {"label": "Delai median", "value": f"{stats['delai_median']} j"},
    {"label": "Min / Max", "value": f"{stats['delai_min']}j - {stats['delai_max']}j"},
])

st.markdown("---")

tab_dist, tab_evo, tab_route, tab_fourn, tab_detail = st.tabs([
    "Distribution", "Evolution mensuelle", "Par route", "Par fournisseur", "Detail expeditions",
])

with tab_dist:
    dist = distribution_delais(session)
    if not dist.empty:
        st.plotly_chart(
            bar_chart(dist, x="delai_jours", y="nb_expeditions",
                      title="Distribution des delais d'expedition (jours)"),
            use_container_width=True,
        )
    else:
        st.info("Pas de donnees de delai disponibles (date_depart et date_arrivee requises).")

with tab_evo:
    evo_delai = evolution_delai_mensuel(session)
    if not evo_delai.empty:
        st.plotly_chart(
            line_chart(evo_delai, x="mois", y="delai_moyen",
                       title="Delai moyen d'expedition par mois (jours)"),
            use_container_width=True,
        )
        data_table(evo_delai, "Detail mensuel")
    else:
        st.info("Pas de donnees temporelles de delai.")

with tab_route:
    dr = delai_par_route(session)
    if not dr.empty:
        st.plotly_chart(
            bar_chart(dr, x="route", y="delai_moyen",
                      title="Delai moyen par route (jours)"),
            use_container_width=True,
        )
        data_table(dr, "Delais par route")
    else:
        st.info("Pas de donnees de route avec delai.")

with tab_fourn:
    df_fourn = delai_par_fournisseur(session)
    if not df_fourn.empty:
        st.plotly_chart(
            bar_chart(df_fourn, x="fournisseur", y="delai_moyen",
                      title="Delai moyen par fournisseur (jours)"),
            use_container_width=True,
        )
        data_table(df_fourn, "Delais par fournisseur")
    else:
        st.info("Pas de donnees fournisseur avec delai.")

with tab_detail:
    det = detail_expeditions(session)
    if not det.empty:
        data_table(det, "Toutes les expeditions avec delai")
    else:
        st.info("Aucune expedition avec date de depart et date d'arrivee.")

# ===================================================================
# Volume et prix (secondary section)
# ===================================================================
st.markdown("---")
st.header("Volume et prix")

col_vol, col_prix = st.columns(2)

with col_vol:
    st.subheader("Volume d'achats mensuel")
    vol = volume_mensuel(session)
    if not vol.empty:
        st.plotly_chart(bar_chart(vol, x="mois", y="montant_total",
                                  title="Montant HT mensuel"), use_container_width=True)

with col_prix:
    st.subheader("Evolution des prix par matiere")
    matieres = get_distinct_values(session, "material")
    if matieres:
        selected = st.selectbox("Selectionner une matiere", matieres)
        if selected:
            raw_values = expand_canonical(session, "material", selected)
            evo = evolution_prix_matiere(session, selected, raw_values=raw_values)
            if not evo.empty:
                st.plotly_chart(line_chart(evo, x="mois", y="prix_unitaire_moyen",
                                           title=f"Prix unitaire moyen -- {selected}"),
                               use_container_width=True)
                data_table(evo, f"Detail prix -- {selected}")
            else:
                st.info("Pas de donnees temporelles pour cette matiere.")

session.close()
