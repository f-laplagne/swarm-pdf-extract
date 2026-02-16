"""Corrections manuelles -- interface pour corriger les extractions a faible confiance."""

import pandas as pd
import streamlit as st

from dashboard.data.db import get_session
from dashboard.data.models import LigneFacture
from dashboard.analytics.corrections import (
    EDITABLE_FIELDS,
    FIELD_CONF_PAIRS,
    appliquer_correction,
    champs_faibles_pour_ligne,
    documents_a_corriger,
    historique_corrections,
    lignes_a_corriger,
    stats_corrections,
)
from dashboard.components.data_table import data_table
from dashboard.components.kpi_card import kpi_row

st.set_page_config(page_title="Corrections manuelles", page_icon="\u270F\uFE0F", layout="wide")
st.title("\u270F\uFE0F Corrections manuelles")

engine = st.session_state.get("engine")
if not engine:
    from dashboard.data.db import get_engine, init_db

    engine = get_engine()
    init_db(engine)

session = get_session(engine)
config = st.session_state.get("config", {})
default_seuil = config.get("confidence", {}).get("correction_seuil", 0.70)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
seuil = st.sidebar.slider(
    "Seuil de confiance", min_value=0.0, max_value=1.0,
    value=default_seuil, step=0.05, key="correction_seuil_slider",
    help="Les champs avec une confiance inferieure a ce seuil sont consideres comme faibles.",
)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_docs, tab_corriger, tab_historique = st.tabs(
    ["Documents a corriger", "Corriger une ligne", "Historique"]
)

# ============================================================
# Tab 1: Documents a corriger
# ============================================================
with tab_docs:
    stats = stats_corrections(session)
    df_docs = documents_a_corriger(session, seuil=seuil)

    kpi_row([
        {"label": "Documents a corriger", "value": str(len(df_docs))},
        {"label": "Lignes faibles (total)", "value": str(int(df_docs["nb_lignes_faibles"].sum())) if not df_docs.empty else "0"},
        {"label": "Corrections effectuees", "value": str(stats["total"])},
    ])

    if not df_docs.empty:
        data_table(df_docs, title="Documents avec lignes a faible confiance", export=False)
    else:
        st.success("Aucun document ne necessite de correction au seuil actuel.")

# ============================================================
# Tab 2: Corriger une ligne
# ============================================================
with tab_corriger:
    df_docs_tab2 = documents_a_corriger(session, seuil=seuil)

    if df_docs_tab2.empty:
        st.info("Aucune ligne a corriger au seuil actuel.")
    else:
        # Document selector
        doc_options = {
            f"{row['fichier']} ({row['nb_lignes_faibles']} lignes faibles)": row["document_id"]
            for _, row in df_docs_tab2.iterrows()
        }
        selected_doc_label = st.selectbox(
            "Document", options=list(doc_options.keys()), key="correction_doc_select",
        )
        selected_doc_id = doc_options[selected_doc_label]

        # Line selector
        df_lignes = lignes_a_corriger(session, selected_doc_id, seuil=seuil)
        if df_lignes.empty:
            st.info("Aucune ligne faible pour ce document.")
        else:
            ligne_options = {
                f"Ligne {row['ligne_numero']} — {row['type_matiere'] or '?'} ({row['nb_champs_faibles']} champs faibles)": row["ligne_id"]
                for _, row in df_lignes.iterrows()
            }
            selected_ligne_label = st.selectbox(
                "Ligne", options=list(ligne_options.keys()), key="correction_ligne_select",
            )
            selected_ligne_id = ligne_options[selected_ligne_label]

            # Load the line
            ligne = session.get(LigneFacture, selected_ligne_id)
            if ligne is None:
                st.error("Ligne introuvable.")
            else:
                faibles = set(champs_faibles_pour_ligne(ligne, seuil))

                st.markdown("---")
                st.subheader("Champs de la ligne")

                # Build form
                with st.form("correction_form"):
                    field_values = {}
                    # 3 fields per row
                    FLOAT_FIELDS = {"prix_unitaire", "quantite", "prix_total"}
                    for i in range(0, len(EDITABLE_FIELDS), 3):
                        batch = EDITABLE_FIELDS[i:i+3]
                        cols = st.columns(len(batch))
                        for col, field in zip(cols, batch):
                            conf_field = f"conf_{field}"
                            conf_val = getattr(ligne, conf_field, None)
                            current_val = getattr(ligne, field)
                            is_weak = field in faibles

                            with col:
                                # Confidence badge
                                if is_weak:
                                    conf_display = f"{conf_val:.0%}" if conf_val is not None else "N/A"
                                    st.markdown(
                                        f"**{field}** &nbsp; :red[conf: {conf_display}]"
                                    )
                                else:
                                    conf_display = f"{conf_val:.0%}" if conf_val is not None else "N/A"
                                    st.markdown(
                                        f"**{field}** &nbsp; :green[conf: {conf_display}]"
                                    )

                                # Input widget
                                if field in FLOAT_FIELDS:
                                    field_values[field] = st.number_input(
                                        field, value=float(current_val) if current_val is not None else 0.0,
                                        format="%.4f", key=f"input_{field}",
                                        label_visibility="collapsed",
                                    )
                                else:
                                    field_values[field] = st.text_input(
                                        field, value=str(current_val) if current_val is not None else "",
                                        key=f"input_{field}",
                                        label_visibility="collapsed",
                                    )

                    st.markdown("---")
                    notes = st.text_area("Notes (optionnel)", key="correction_notes", height=80)
                    submitted = st.form_submit_button("Appliquer les corrections", type="primary")

                if submitted:
                    # Only log changed fields
                    changes = {}
                    for field, new_val in field_values.items():
                        current = getattr(ligne, field)
                        if field in FLOAT_FIELDS:
                            new_float = float(new_val)
                            old_float = float(current) if current is not None else 0.0
                            if abs(new_float - old_float) > 1e-6:
                                changes[field] = new_float
                        else:
                            old_str = str(current) if current is not None else ""
                            if str(new_val) != old_str:
                                changes[field] = str(new_val)

                    if changes:
                        logs = appliquer_correction(
                            session, selected_ligne_id, changes,
                            corrige_par="admin", notes=notes.strip() or None,
                        )
                        st.success(f"{len(logs)} champ(s) corrige(s) avec succes.")
                        st.rerun()
                    else:
                        st.warning("Aucune modification detectee.")

# ============================================================
# Tab 3: Historique
# ============================================================
with tab_historique:
    # Optional document filter
    all_docs = documents_a_corriger(session, seuil=1.0)  # all docs
    doc_filter_options = {"Tous les documents": None}
    if not all_docs.empty:
        for _, row in all_docs.iterrows():
            doc_filter_options[row["fichier"]] = row["document_id"]

    selected_filter = st.selectbox(
        "Filtrer par document", options=list(doc_filter_options.keys()),
        key="historique_doc_filter",
    )
    filter_doc_id = doc_filter_options[selected_filter]

    df_hist = historique_corrections(session, document_id=filter_doc_id)
    if not df_hist.empty:
        data_table(df_hist, title="Journal des corrections")
    else:
        st.info("Aucune correction enregistree.")

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
session.close()
