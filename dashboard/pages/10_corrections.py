"""Corrections manuelles — interface pour corriger les extractions à faible confiance."""

import http.server, json, os, socket, sys, threading
from pathlib import Path
from urllib.parse import quote

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st

st.set_page_config(
    page_title="Corrections manuelles",
    page_icon="✏️",
    layout="wide",
    initial_sidebar_state="expanded",
)
from dashboard.styles.theme import inject_theme, _current
inject_theme()

from dashboard.data.db import get_session
from dashboard.data.models import Document, LigneFacture
from dashboard.analytics.corrections import (
    EDITABLE_FIELDS,
    appliquer_correction,
    champs_faibles_pour_ligne,
    detail_confiance_document,
    documents_a_corriger,
    historique_corrections,
    lignes_a_corriger,
    propager_correction,
    stats_corrections,
    suggestion_pour_champ,
    supprimer_ligne,
)
from dashboard.components.data_table import data_table
from dashboard.components.kpi_card import kpi_row

# ── Mini serveur HTTP (port 8505) servant PDFs depuis samples/ et uploads/ ────
_DASHBOARD_DIR   = Path(__file__).parent.parent
SAMPLES_DIR      = Path(_PROJECT_ROOT) / "samples"
UPLOADS_DIR      = _DASHBOARD_DIR / "data" / "uploads"
CORRECTIONS_PORT = 8505


class _MultiDirHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        fname = self.path.lstrip("/").split("?")[0]
        for d in (UPLOADS_DIR, SAMPLES_DIR):
            p = d / fname
            if p.is_file():
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_): pass


def _port_free(p: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", p)) != 0


if _port_free(CORRECTIONS_PORT):
    threading.Thread(
        target=http.server.HTTPServer(
            ("localhost", CORRECTIONS_PORT), _MultiDirHandler
        ).serve_forever,
        daemon=True,
    ).start()


def _pdf_url(fichier: str) -> str | None:
    """Retourne l'URL HTTP locale pour un PDF, ou None si introuvable."""
    basename = os.path.basename(fichier)
    for d in (UPLOADS_DIR, SAMPLES_DIR):
        if (d / basename).is_file():
            return f"http://localhost:{CORRECTIONS_PORT}/{quote(basename)}"
    return None


# ── Palette thème ─────────────────────────────────────────────────────────────
def _pal() -> dict:
    if _current() == "light":
        return dict(
            body_bg="#f2f4f8", border="#d0d7e3",
            txt_m="#8a97ab",
            status_bg="#e8ecf2", status_border="#d0d7e3",
        )
    return dict(
        body_bg="#0d0f14", border="#1a2035",
        txt_m="#2d3748",
        status_bg="#080b11", status_border="#1a2035",
    )


def _build_pdf_viewer(pdf_url: str, P: dict) -> str:
    """Génère un viewer PDF.js minimal (une colonne, hauteur fixe)."""
    url_js = json.dumps(pdf_url)
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Manrope:wght@400;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;overflow:hidden;background:{P['body_bg']};
  color:#c8d0e0;font-family:'Manrope',sans-serif;display:flex;flex-direction:column}}
#pdf-container{{flex:1;overflow-y:auto;padding:10px;
  display:flex;flex-direction:column;align-items:center;gap:8px;
  scrollbar-width:thin;scrollbar-color:{P['border']} transparent}}
#pdf-container canvas{{box-shadow:0 4px 20px rgba(0,0,0,.35);border-radius:2px;
  max-width:100%;display:block}}
#pdf-loading{{font-family:'JetBrains Mono',monospace;font-size:11px;
  color:{P['txt_m']};padding:40px;text-align:center}}
.statusbar{{height:22px;background:{P['status_bg']};border-top:1px solid {P['status_border']};
  display:flex;align-items:center;padding:0 14px;
  font-family:'JetBrains Mono',monospace;font-size:9px;color:{P['txt_m']};flex-shrink:0}}
</style></head><body>
<div id="pdf-container"><div id="pdf-loading">⏳ Chargement du PDF…</div></div>
<div class="statusbar" id="status-bar">Initialisation…</div>
<script>
pdfjsLib.GlobalWorkerOptions.workerSrc =
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
const cont = document.getElementById('pdf-container');
const sbar = document.getElementById('status-bar');
pdfjsLib.getDocument({url_js}).promise.then(pdf => {{
  const tot = pdf.numPages;
  document.getElementById('pdf-loading').remove();
  const render = n => {{
    if (n > tot) {{ sbar.textContent = '· ' + tot + ' page(s) chargée(s)'; return; }}
    pdf.getPage(n).then(pg => {{
      const vp = pg.getViewport({{scale: 1.6}});
      const c = document.createElement('canvas');
      c.height = vp.height; c.width = vp.width;
      cont.appendChild(c);
      pg.render({{canvasContext: c.getContext('2d'), viewport: vp}})
        .promise.then(() => {{ sbar.textContent = '· Page ' + n + ' / ' + tot; render(n+1); }});
    }});
  }};
  render(1);
}}).catch(err => {{
  document.getElementById('pdf-loading').remove();
  cont.innerHTML = '<div style="color:#ff4d4d;padding:20px;font-family:Manrope,sans-serif">❌ '
    + err.message + '</div>';
  sbar.textContent = '· Erreur PDF';
}});
</script></body></html>"""


# ── DB / session ──────────────────────────────────────────────────────────────
engine = st.session_state.get("engine")
if not engine:
    from dashboard.data.db import get_engine, init_db
    engine = get_engine()
    init_db(engine)

session = get_session(engine)
config = st.session_state.get("config", {})
default_seuil = config.get("confidence", {}).get("correction_seuil", 0.70)

FLOAT_FIELDS = {"prix_unitaire", "quantite", "prix_total"}


def _conf_color(val):
    """CSS de fond pour une cellule de confiance (utilisé dans df.style.map)."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "background-color: #ffcccc"
    if v < 0.30: return "background-color: #ff4d4d; color: white"
    if v < 0.60: return "background-color: #ff9966"
    if v < seuil: return "background-color: #ffdd57"
    if v < 0.80: return "background-color: #d4edda"
    return "background-color: #28a745; color: white"


def _fmt_conf(val):
    try:
        return f"{float(val):.0%}"
    except (TypeError, ValueError):
        return "N/A"


# ── Sidebar ───────────────────────────────────────────────────────────────────
seuil = st.sidebar.slider(
    "Seuil de confiance",
    min_value=0.0, max_value=1.0,
    value=default_seuil, step=0.05,
    key="correction_seuil_slider",
    help="Champs avec une confiance inférieure à ce seuil → à corriger.",
)

# ── En-tête ───────────────────────────────────────────────────────────────────
st.title("✏️ Corrections manuelles")
st.caption(
    "Les corrections sont enregistrées en base de données et **immédiatement "
    "prises en compte dans toutes les analyses du site**."
)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_docs, tab_corriger, tab_historique = st.tabs([
    "📋 Documents à corriger",
    "✏️ Corriger une ligne",
    "📜 Historique",
])


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Vue d'ensemble
# ═══════════════════════════════════════════════════════════════════════════════
with tab_docs:
    stats   = stats_corrections(session)
    df_docs = documents_a_corriger(session, seuil=seuil)

    kpi_row([
        {"label": "Documents à corriger",  "value": str(len(df_docs))},
        {"label": "Lignes faibles",        "value": str(int(df_docs["nb_lignes_faibles"].sum())) if not df_docs.empty else "0"},
        {"label": "Corrections effectuées","value": str(stats["total"])},
        {"label": "Lignes corrigées",      "value": str(stats["lignes"])},
    ])

    if df_docs.empty:
        st.success("✅ Aucun document ne nécessite de correction au seuil actuel.")
    else:
        st.markdown(
            f"**{len(df_docs)} document(s)** ont au moins une ligne en dessous "
            f"du seuil de confiance **{seuil:.0%}**."
        )

        df_display = df_docs.rename(columns={
            "fichier": "Fichier",
            "type_document": "Type",
            "confiance_globale": "Confiance globale",
            "nb_lignes_faibles": "Lignes faibles",
        }).drop(columns=["document_id"])

        st.dataframe(
            df_display.style
            .map(_conf_color, subset=["Confiance globale"])
            .format({"Confiance globale": _fmt_conf}),
            use_container_width=True, hide_index=True,
        )

        st.markdown("#### Détail par document")
        for _, row in df_docs.iterrows():
            label = f"{row['fichier']}  —  confiance : {_fmt_conf(row['confiance_globale'])}"
            with st.expander(label):
                df_detail = detail_confiance_document(session, row["document_id"])
                if not df_detail.empty:
                    conf_cols = [c for c in df_detail.columns if c not in ("ligne", "matiere")]
                    st.dataframe(
                        df_detail.style
                        .map(_conf_color, subset=conf_cols)
                        .format({c: _fmt_conf for c in conf_cols}),
                        use_container_width=True, hide_index=True,
                    )
                else:
                    st.info("Aucune ligne pour ce document.")


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Corriger une ligne
# ═══════════════════════════════════════════════════════════════════════════════
with tab_corriger:
    df_docs_tab2 = documents_a_corriger(session, seuil=seuil)

    if df_docs_tab2.empty:
        st.info("✅ Aucune ligne à corriger au seuil actuel.")
    else:
        # Sélection du document (pleine largeur, au-dessus de la vue partagée)
        doc_options = {
            f"{row['fichier']}  ·  {row['nb_lignes_faibles']} ligne(s) faible(s)": row["document_id"]
            for _, row in df_docs_tab2.iterrows()
        }
        selected_doc_label = st.selectbox(
            "📄 Document",
            options=list(doc_options.keys()),
            key="correction_doc_select",
        )
        selected_doc_id = doc_options[selected_doc_label]
        selected_doc    = session.get(Document, selected_doc_id)
        pdf_url_val     = _pdf_url(selected_doc.fichier) if selected_doc else None

        # ── Vue partagée ──────────────────────────────────────────────────────
        col_pdf, col_form = st.columns([1, 1])

        # ── Gauche : viewer PDF.js ────────────────────────────────────────────
        with col_pdf:
            P = _pal()
            if pdf_url_val:
                st.components.v1.html(
                    _build_pdf_viewer(pdf_url_val, P),
                    height=900, scrolling=False,
                )
            else:
                st.warning(
                    f"PDF introuvable pour **{selected_doc.fichier}**.\n\n"
                    "Déposez le fichier dans `samples/` ou `dashboard/data/uploads/`."
                )

        # ── Droite : formulaire de correction ────────────────────────────────
        with col_form:
            # Confiance globale du document
            conf_globale = selected_doc.confiance_globale if selected_doc else None
            if conf_globale is not None:
                st.progress(
                    min(conf_globale, 1.0),
                    text=f"Confiance globale : **{_fmt_conf(conf_globale)}**",
                )

            # Carte de confiance (heatmap par champ)
            df_detail = detail_confiance_document(session, selected_doc_id)
            if not df_detail.empty:
                conf_cols = [c for c in df_detail.columns if c not in ("ligne", "matiere")]
                with st.expander("🔍 Carte de confiance", expanded=True):
                    st.dataframe(
                        df_detail.style
                        .map(_conf_color, subset=conf_cols)
                        .format({c: _fmt_conf for c in conf_cols}),
                        use_container_width=True, hide_index=True,
                    )

            st.markdown("---")

            # Sélection de la ligne à corriger
            df_lignes = lignes_a_corriger(session, selected_doc_id, seuil=seuil)
            if df_lignes.empty:
                st.info("Aucune ligne faible pour ce document.")
            else:
                ligne_options = {
                    f"Ligne {row['ligne_numero']}  —  {row['type_matiere'] or '?'}  "
                    f"({row['nb_champs_faibles']} champs faibles)": row["ligne_id"]
                    for _, row in df_lignes.iterrows()
                }
                selected_ligne_label = st.selectbox(
                    "✏️ Ligne à corriger",
                    options=list(ligne_options.keys()),
                    key="correction_ligne_select",
                )
                selected_ligne_id = ligne_options[selected_ligne_label]
                ligne = session.get(LigneFacture, selected_ligne_id)

                if ligne:
                    faibles = set(champs_faibles_pour_ligne(ligne, seuil))
                    if faibles:
                        st.markdown(
                            f"**Champs faibles** : {', '.join(sorted(faibles))}"
                        )
                    st.markdown("---")

                    # Champs éditables (grille 3 colonnes)
                    field_values: dict = {}
                    for i in range(0, len(EDITABLE_FIELDS), 3):
                        batch = EDITABLE_FIELDS[i:i + 3]
                        cols = st.columns(len(batch))
                        for col, field in zip(cols, batch):
                            conf_val    = getattr(ligne, f"conf_{field}", None)
                            current_val = getattr(ligne, field)
                            is_weak     = field in faibles
                            conf_str    = _fmt_conf(conf_val)

                            with col:
                                if is_weak:
                                    cur_str = str(current_val) if current_val is not None else ""
                                    sug = suggestion_pour_champ(session, field, cur_str) if cur_str else None
                                    hint = f"  →  *{sug}*" if sug else ""
                                    st.markdown(f"**{field}** :red[{conf_str}]{hint}")
                                else:
                                    st.markdown(f"**{field}** :green[{conf_str}]")

                                if field in FLOAT_FIELDS:
                                    field_values[field] = st.number_input(
                                        field,
                                        value=float(current_val) if current_val is not None else 0.0,
                                        format="%.4f",
                                        key=f"input_{field}",
                                        label_visibility="collapsed",
                                    )
                                else:
                                    field_values[field] = st.text_input(
                                        field,
                                        value=str(current_val) if current_val is not None else "",
                                        key=f"input_{field}",
                                        label_visibility="collapsed",
                                    )

                    st.markdown("---")
                    notes = st.text_area(
                        "Notes (optionnel)", key="correction_notes", height=60,
                    )

                    btn1, btn2 = st.columns(2)

                    with btn1:
                        if st.button("💾 Appliquer les corrections", type="primary", key="correction_submit"):
                            changes: dict = {}
                            for field, new_val in field_values.items():
                                current = getattr(ligne, field)
                                if field in FLOAT_FIELDS:
                                    nf = float(new_val)
                                    of = float(current) if current is not None else 0.0
                                    if abs(nf - of) > 1e-6:
                                        changes[field] = nf
                                else:
                                    new_s = str(new_val) if new_val is not None else ""
                                    old_s = str(current) if current is not None else ""
                                    if new_s != old_s:
                                        changes[field] = new_s

                            if changes:
                                logs = appliquer_correction(
                                    session, selected_ligne_id, changes,
                                    corrige_par="admin",
                                    notes=notes.strip() or None,
                                )
                                st.success(
                                    f"✅ {len(logs)} champ(s) corrigé(s). "
                                    "Pris en compte dans toutes les analyses."
                                )
                                st.rerun()
                            else:
                                st.warning("Aucune modification détectée.")

                    with btn2:
                        # N'autoriser la suppression que s'il reste au moins 2 lignes
                        nb_active = (
                            session.query(LigneFacture)
                            .filter(
                                LigneFacture.document_id == selected_doc_id,
                                LigneFacture.supprime != True,
                            )
                            .count()
                        )
                        if nb_active > 1:
                            if st.button(
                                "🗑️ Supprimer cette ligne",
                                type="secondary", key="delete_ligne_btn",
                            ):
                                supprimer_ligne(
                                    session, selected_ligne_id,
                                    supprime_par="admin",
                                    notes=notes.strip() or None,
                                )
                                st.success("Ligne supprimée.")
                                st.rerun()

                    # Propagation en masse
                    st.markdown("---")
                    with st.expander("🔄 Propager une correction à tout le site"):
                        st.caption(
                            "Corrige toutes les lignes (tous documents) partageant "
                            "la même valeur brute avec une confiance faible."
                        )
                        prop_champ = st.selectbox(
                            "Champ", EDITABLE_FIELDS, key="prop_champ",
                        )
                        pc1, pc2 = st.columns(2)
                        with pc1:
                            prop_orig = st.text_input("Valeur originale", key="prop_orig")
                        with pc2:
                            prop_corr = st.text_input("Valeur corrigée", key="prop_corr")
                        prop_seuil = st.slider(
                            "Seuil confiance max", 0.0, 1.0, 0.70, 0.05, key="prop_seuil",
                        )
                        if st.button("🔄 Propager", key="prop_btn"):
                            if prop_orig.strip() and prop_corr.strip():
                                n = propager_correction(
                                    session, prop_champ,
                                    prop_orig.strip(), prop_corr.strip(),
                                    seuil=prop_seuil,
                                )
                                st.success(
                                    f"✅ {n} ligne(s) corrigée(s) à travers tout le site."
                                )
                                st.rerun()
                            else:
                                st.warning("Renseignez la valeur originale et la valeur corrigée.")


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Historique
# ═══════════════════════════════════════════════════════════════════════════════
with tab_historique:
    all_docs_hist = documents_a_corriger(session, seuil=1.0)
    filter_opts: dict = {"Tous les documents": None}
    if not all_docs_hist.empty:
        for _, row in all_docs_hist.iterrows():
            filter_opts[row["fichier"]] = row["document_id"]

    filter_sel = st.selectbox(
        "Filtrer par document",
        options=list(filter_opts.keys()),
        key="historique_doc_filter",
    )
    filter_id = filter_opts[filter_sel]

    df_hist = historique_corrections(session, document_id=filter_id)
    if not df_hist.empty:
        data_table(df_hist, title="Journal des corrections")
    else:
        st.info("Aucune correction enregistrée.")

# ── Cleanup ───────────────────────────────────────────────────────────────────
session.close()
