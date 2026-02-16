"""Corrections manuelles -- interface pour corriger les extractions a faible confiance."""

import base64
import os

import pandas as pd
import streamlit as st

from dashboard.data.db import get_session
from dashboard.data.models import Document, LigneFacture
from dashboard.analytics.corrections import (
    EDITABLE_FIELDS,
    FIELD_CONF_PAIRS,
    appliquer_correction,
    champs_faibles_pour_ligne,
    detail_confiance_document,
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
# PDF viewer helper
# ---------------------------------------------------------------------------
# Directories where original PDFs can live
_DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_DASHBOARD_DIR)
_PDF_SEARCH_DIRS = [
    os.path.join(_DASHBOARD_DIR, "data", "uploads"),
    os.path.join(_PROJECT_ROOT, "samples"),
]


def _find_pdf(fichier: str) -> str | None:
    """Locate the PDF file on disk given the Document.fichier name."""
    basename = os.path.basename(fichier)
    for search_dir in _PDF_SEARCH_DIRS:
        if not os.path.isdir(search_dir):
            continue
        # Exact match
        candidate = os.path.join(search_dir, basename)
        if os.path.isfile(candidate):
            return candidate
        # Also check hash-prefixed uploads (format: <hash12>_<filename>)
        for f in os.listdir(search_dir):
            if f.endswith(basename):
                return os.path.join(search_dir, f)
    return None


def _render_pdf(pdf_path: str, height: int = 700):
    """Embed a PDF in the page using an iframe with base64 data URI."""
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_html = (
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="{height}px" '
        f'style="border: 1px solid #ccc; border-radius: 4px;" '
        f'type="application/pdf"></iframe>'
    )
    st.components.v1.html(pdf_html, height=height + 10, scrolling=False)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_docs, tab_corriger, tab_historique = st.tabs(
    ["Documents a corriger", "Corriger une ligne", "Historique"]
)

# ============================================================
# Helpers for confidence display
# ============================================================

def _conf_color(val):
    """Return background color CSS for a confidence value."""
    if val is None or pd.isna(val):
        return "background-color: #ffcccc"  # red — unknown
    if val < 0.30:
        return "background-color: #ff4d4d; color: white"  # strong red
    if val < 0.60:
        return "background-color: #ff9966"  # orange
    if val < seuil:
        return "background-color: #ffdd57"  # yellow
    if val < 0.80:
        return "background-color: #d4edda"  # light green
    return "background-color: #28a745; color: white"  # strong green


def _format_conf(val):
    """Format a confidence value as percentage string."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "N/A"
    return f"{val:.0%}"


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
        st.subheader("Documents avec lignes a faible confiance")
        st.caption(f"Seuil actuel : **{seuil:.0%}** — les documents ci-dessous ont au moins une ligne en dessous.")

        df_display = df_docs.rename(columns={
            "fichier": "Fichier",
            "type_document": "Type",
            "confiance_globale": "Confiance globale",
            "nb_lignes_faibles": "Lignes faibles",
        }).drop(columns=["document_id"])

        styled = (
            df_display.style
            .applymap(_conf_color, subset=["Confiance globale"])
            .format({"Confiance globale": _format_conf})
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # Expandable per-document confidence detail
        st.markdown("#### Detail par document")
        for _, row in df_docs.iterrows():
            with st.expander(f"{row['fichier']} — confiance globale : {_format_conf(row['confiance_globale'])}"):
                df_detail = detail_confiance_document(session, row["document_id"])
                if not df_detail.empty:
                    conf_cols = [c for c in df_detail.columns if c not in ("ligne", "matiere")]
                    styled_detail = (
                        df_detail.style
                        .applymap(_conf_color, subset=conf_cols)
                        .format({c: _format_conf for c in conf_cols})
                    )
                    st.dataframe(styled_detail, use_container_width=True, hide_index=True)
                else:
                    st.info("Aucune ligne pour ce document.")
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

        # Fetch document record for PDF lookup
        selected_doc = session.get(Document, selected_doc_id)
        pdf_path = _find_pdf(selected_doc.fichier) if selected_doc else None

        # --- Side-by-side: PDF original + confidence heatmap ---
        col_pdf, col_conf = st.columns([1, 1])

        with col_pdf:
            st.markdown("#### Document original")
            if pdf_path:
                _render_pdf(pdf_path, height=600)
            else:
                st.warning(
                    f"PDF introuvable : *{selected_doc.fichier}*\n\n"
                    "Placez le fichier dans `samples/` ou `dashboard/data/uploads/` "
                    "pour l'afficher ici."
                )

        with col_conf:
            st.markdown("#### Carte de confiance")
            st.caption("Rouge = le systeme ne fait pas confiance, vert = fiable.")
            if selected_doc:
                conf_globale = selected_doc.confiance_globale
                st.markdown(
                    f"**Confiance globale du document : "
                    f"{_format_conf(conf_globale)}**"
                )
                if conf_globale is not None:
                    st.progress(min(conf_globale, 1.0))

            df_detail = detail_confiance_document(session, selected_doc_id)
            if not df_detail.empty:
                conf_cols = [c for c in df_detail.columns if c not in ("ligne", "matiere")]
                styled_overview = (
                    df_detail.style
                    .applymap(_conf_color, subset=conf_cols)
                    .format({c: _format_conf for c in conf_cols})
                )
                st.dataframe(styled_overview, use_container_width=True, hide_index=True)

        st.markdown("---")

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
