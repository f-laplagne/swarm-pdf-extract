"""Corrections manuelles -- interface pour corriger les extractions a faible confiance."""

import os
from types import SimpleNamespace

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from dashboard.data.db import get_session
from dashboard.data.models import BoundingBox, Document, LigneFacture
from dashboard.analytics.corrections import (
    EDITABLE_FIELDS,
    FIELD_CONF_PAIRS,
    appliquer_correction,
    bboxes_pour_page,
    champs_faibles_pour_ligne,
    detail_confiance_document,
    documents_a_corriger,
    historique_corrections,
    lignes_a_corriger,
    sauvegarder_bbox,
    stats_corrections,
    supprimer_ligne,
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
        candidate = os.path.join(search_dir, basename)
        if os.path.isfile(candidate):
            return candidate
        for f in os.listdir(search_dir):
            if f.endswith(basename):
                return os.path.join(search_dir, f)
    return None


@st.cache_data(show_spinner="Rendu du PDF...")
def _pdf_to_images(pdf_path: str, max_pages: int = 10):
    """Convert PDF pages to PIL images using pdf2image (poppler)."""
    from pdf2image import convert_from_path
    images = convert_from_path(
        pdf_path, dpi=150, first_page=1, last_page=max_pages,
    )
    return images


def _render_pdf(pdf_path: str, max_pages: int = 10):
    """Display PDF pages as images inside a scrollable container."""
    try:
        images = _pdf_to_images(pdf_path, max_pages=max_pages)
    except Exception as e:
        st.error(f"Impossible de convertir le PDF en images : {e}")
        return

    total_pages = len(images)
    st.caption(f"{total_pages} page(s) affichee(s)")
    for i, img in enumerate(images):
        st.image(img, caption=f"Page {i + 1}", use_container_width=True)


# ---------------------------------------------------------------------------
# Helpers for confidence display
# ---------------------------------------------------------------------------

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


def _styled_conf_df(df, conf_cols):
    """Apply confidence coloring + formatting to a DataFrame."""
    return (
        df.style
        .map(_conf_color, subset=conf_cols)
        .format({c: _format_conf for c in conf_cols})
    )


# ---------------------------------------------------------------------------
# Bounding box overlay helpers
# ---------------------------------------------------------------------------

def _conf_to_bbox_color(conf_val):
    """Return RGBA color tuple for a bbox based on confidence value."""
    if conf_val is None or (isinstance(conf_val, float) and pd.isna(conf_val)):
        return (255, 50, 50, 160)  # red — unknown
    if conf_val < 0.30:
        return (255, 50, 50, 160)  # red
    if conf_val < 0.60:
        return (255, 140, 60, 150)  # orange
    if conf_val < 0.80:
        return (255, 200, 50, 140)  # yellow
    return (30, 160, 60, 140)  # green


def _overlay_bboxes(
    page_img: Image.Image,
    bboxes: list[BoundingBox],
    ligne_map: dict[int, LigneFacture],
    selected_ligne_id: int | None = None,
    selected_champ: str | None = None,
) -> Image.Image:
    """Draw semi-transparent colored rectangles on a copy of the page image.

    Args:
        page_img: Original PIL image for the page.
        bboxes: BoundingBox objects to overlay.
        ligne_map: Mapping of ligne_id -> LigneFacture for confidence lookup.
        selected_ligne_id: Currently selected line (gets blue highlight).
        selected_champ: Currently selected field (gets blue highlight).

    Returns a new image — never mutates the cached original.
    """
    overlay = page_img.copy().convert("RGBA")
    draw_layer = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(draw_layer)

    w, h = overlay.size

    for bbox in bboxes:
        x1 = int(bbox.x_min * w)
        y1 = int(bbox.y_min * h)
        x2 = int(bbox.x_max * w)
        y2 = int(bbox.y_max * h)

        # Determine color from confidence
        ligne = ligne_map.get(bbox.ligne_id)
        conf_val = None
        if ligne:
            conf_val = getattr(ligne, f"conf_{bbox.champ}", None)
        fill_color = _conf_to_bbox_color(conf_val)

        # Blue highlight for active selection
        is_selected = (
            bbox.ligne_id == selected_ligne_id
            and bbox.champ == selected_champ
        )
        if is_selected:
            fill_color = (66, 133, 244, 130)  # blue
            outline_color = (66, 133, 244, 255)
            outline_width = 4
        else:
            outline_color = fill_color[:3] + (240,)
            outline_width = 2

        draw.rectangle([x1, y1, x2, y2], fill=fill_color)
        # Draw outline (multiple passes for thickness)
        for i in range(outline_width):
            draw.rectangle([x1 - i, y1 - i, x2 + i, y2 + i], outline=outline_color)

        # Label
        lnum = ligne.ligne_numero if ligne else "?"
        label = f"L{lnum}:{bbox.champ}"
        font = None
        for font_path in [
            "/System/Library/Fonts/Helvetica.ttc",  # macOS
            "/System/Library/Fonts/SFNSMono.ttf",  # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        ]:
            try:
                font = ImageFont.truetype(font_path, 12)
                break
            except (OSError, IOError):
                continue
        if font is None:
            font = ImageFont.load_default()
        label_y = max(0, y1 - 16)
        text_bbox = draw.textbbox((x1, label_y), label, font=font)
        draw.rectangle(text_bbox, fill=(255, 255, 255, 220))
        draw.text((x1, label_y), label, fill=(0, 0, 0, 255), font=font)

    result = Image.alpha_composite(overlay, draw_layer)
    return result.convert("RGB")


# ---------------------------------------------------------------------------
# Auto-detection: match extracted values to PDF text positions
# ---------------------------------------------------------------------------

_FLOAT_FIELDS = {"prix_unitaire", "quantite", "prix_total"}
_TEXT_FIELDS = {"type_matiere", "unite", "lieu_depart", "lieu_arrivee"}
_DATE_FIELDS = {"date_depart", "date_arrivee"}


@st.cache_data(show_spinner=False)
def _page_words(pdf_path: str, page_number: int) -> list[dict]:
    """Extract words with normalized bboxes (0-1) from a PDF page via pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        return []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                return []
            page = pdf.pages[page_number - 1]
            pw, ph = float(page.width), float(page.height)
            return [
                {
                    "text": w["text"],
                    "x_min": w["x0"] / pw,
                    "y_min": w["top"] / ph,
                    "x_max": w["x1"] / pw,
                    "y_max": w["bottom"] / ph,
                }
                for w in page.extract_words(keep_blank_chars=False)
            ]
    except Exception:
        return []


def _number_search_strings(value) -> list[str]:
    """Generate possible text representations of a numeric value (FR + EN formatting)."""
    if value is None:
        return []
    try:
        fval = float(value)
    except (ValueError, TypeError):
        return []

    results = set()
    # 2 decimals
    s2 = f"{fval:.2f}"
    results.add(s2)                    # 3.50
    results.add(s2.replace(".", ","))   # 3,50
    # 3 decimals
    s3 = f"{fval:.3f}"
    results.add(s3)                    # 24.198
    results.add(s3.replace(".", ","))   # 24,198
    # Compact (no trailing zeros)
    sg = f"{fval:g}"
    results.add(sg)
    results.add(sg.replace(".", ","))
    # Integer form
    if fval == int(fval):
        results.add(str(int(fval)))
    # Thousands separator (space, common in FR)
    if fval >= 1000:
        int_part = int(fval)
        dec_part = s2.split(".")[1]
        formatted_int = f"{int_part:,}".replace(",", " ")
        results.add(f"{formatted_int},{dec_part}")
        results.add(f"{formatted_int}.{dec_part}")
    return [r for r in results if len(r) >= 2]


def _find_number_bbox(words: list[dict], value) -> dict | None:
    """Find a numeric value in word list, return normalized bbox or None."""
    patterns = _number_search_strings(value)
    if not patterns:
        return None
    for word in words:
        wtext = word["text"].strip()
        for pattern in patterns:
            if wtext == pattern:
                return {
                    "x_min": word["x_min"], "y_min": word["y_min"],
                    "x_max": word["x_max"], "y_max": word["y_max"],
                }
    return None


def _find_text_bbox(words: list[dict], text_value) -> dict | None:
    """Find a text value in word list by matching its first significant word(s)."""
    if not text_value:
        return None
    text_str = str(text_value).strip()
    if len(text_str) < 2:
        return None

    # Exact single-word match
    text_upper = text_str.upper()
    for word in words:
        if word["text"].upper() == text_upper:
            return {
                "x_min": word["x_min"], "y_min": word["y_min"],
                "x_max": word["x_max"], "y_max": word["y_max"],
            }

    # Multi-word: match first significant word then extend to subsequent words on same line
    sig_words = [w for w in text_str.split() if len(w) >= 3]
    if not sig_words:
        return None
    first_upper = sig_words[0].upper()
    for i, word in enumerate(words):
        if word["text"].upper() == first_upper:
            bbox = {
                "x_min": word["x_min"], "y_min": word["y_min"],
                "x_max": word["x_max"], "y_max": word["y_max"],
            }
            # Scan forward through remaining PDF words on the same line
            sig_idx = 1  # next significant word to match
            for k in range(i + 1, min(i + 20, len(words))):
                if sig_idx >= len(sig_words):
                    break
                nw = words[k]
                # Must be on the same line
                if abs(nw["y_min"] - word["y_min"]) > 0.02:
                    break
                # Extend bbox for any word on the line (even short ones)
                bbox["x_max"] = max(bbox["x_max"], nw["x_max"])
                bbox["y_max"] = max(bbox["y_max"], nw["y_max"])
                # Check if this word matches the next significant word
                if nw["text"].upper() == sig_words[sig_idx].upper():
                    sig_idx += 1
            return bbox
    return None


def _auto_bboxes_for_page(
    pdf_path: str,
    page_number: int,
    lignes: list[LigneFacture],
    document_id: int,
    existing_keys: set | None = None,
) -> list:
    """Auto-detect bounding boxes by matching extracted values to PDF text positions.

    Args:
        existing_keys: set of (ligne_id, champ) already stored in DB — skip those.

    Returns list of SimpleNamespace objects compatible with _overlay_bboxes().
    """
    words = _page_words(pdf_path, page_number)
    if not words:
        return []

    if existing_keys is None:
        existing_keys = set()

    results = []
    for ligne in lignes:
        for field, conf_field in FIELD_CONF_PAIRS:
            if (ligne.id, field) in existing_keys:
                continue
            value = getattr(ligne, field)
            if value is None:
                continue

            bbox = None
            if field in _FLOAT_FIELDS:
                bbox = _find_number_bbox(words, value)
            elif field in _TEXT_FIELDS:
                bbox = _find_text_bbox(words, value)
            elif field in _DATE_FIELDS:
                date_str = str(value)
                # ISO "2024-03-01" → French "01/03/2024"
                if len(date_str) >= 10 and "-" in date_str:
                    parts = date_str[:10].split("-")
                    if len(parts) == 3:
                        french = f"{parts[2]}/{parts[1]}/{parts[0]}"
                        bbox = _find_text_bbox(words, french)
                if bbox is None:
                    bbox = _find_text_bbox(words, date_str)

            if bbox:
                results.append(SimpleNamespace(
                    ligne_id=ligne.id,
                    document_id=document_id,
                    champ=field,
                    page_number=page_number,
                    x_min=bbox["x_min"],
                    y_min=bbox["y_min"],
                    x_max=bbox["x_max"],
                    y_max=bbox["y_max"],
                    source="extraction",
                ))

    return results


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
            .map(_conf_color, subset=["Confiance globale"])
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
                    st.dataframe(
                        _styled_conf_df(df_detail, conf_cols),
                        use_container_width=True, hide_index=True,
                    )
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
        # Document selector (full width, above the split)
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

        # --- Two independent scrollable columns ---
        col_pdf, col_right = st.columns([1, 1])

        # Initialize annotation session state
        if "pending_bboxes" not in st.session_state:
            st.session_state.pending_bboxes = []

        # ---- LEFT: Split PDF viewer (two independent panes) ----
        with col_pdf:
            st.markdown("#### Document original")
            if pdf_path:
                images = _pdf_to_images(pdf_path, max_pages=10)
                total_pages = len(images)

                # Build ligne_map for overlay
                _all_lignes = (
                    session.query(LigneFacture)
                    .filter(LigneFacture.document_id == selected_doc_id, LigneFacture.supprime != True)
                    .all()
                )
                _ligne_map = {l.id: l for l in _all_lignes}

                # Get currently selected line/field for highlight (set below in right col)
                _sel_ligne_id = st.session_state.get("_active_ligne_id")
                _sel_champ = st.session_state.get("annotation_champ_select")

                # Annotation mode state — read from widget keys directly
                # (Streamlit updates widget-keyed state BEFORE rerun, unlike manual session_state)
                annotation_active = st.session_state.get("annotation_toggle", False)
                annot_pane = st.session_state.get("annotation_pane_radio", "haut")

                top_page = st.number_input(
                    "Page (haut)", min_value=1, max_value=total_pages,
                    value=1, step=1, key="pdf_top_page",
                )
                # Fetch bboxes: DB-stored + auto-detected from PDF text
                top_db_bboxes = bboxes_pour_page(session, selected_doc_id, top_page)
                _existing_keys = {(b.ligne_id, b.champ) for b in top_db_bboxes}
                top_auto_bboxes = _auto_bboxes_for_page(
                    pdf_path, top_page, _all_lignes, selected_doc_id, _existing_keys,
                )
                top_bboxes = list(top_db_bboxes) + top_auto_bboxes
                top_base_img = images[top_page - 1]
                top_overlay_img = _overlay_bboxes(
                    top_base_img, top_bboxes, _ligne_map, _sel_ligne_id, _sel_champ,
                )

                # Show canvas or image for top pane
                if top_bboxes:
                    st.caption(f"Page {top_page}/{total_pages} — {len(top_bboxes)} annotation(s)")
                if annotation_active and annot_pane == "haut":
                    try:
                        from streamlit_drawable_canvas import st_canvas

                        canvas_h = 550
                        canvas_w = int(canvas_h * top_overlay_img.width / top_overlay_img.height)
                        bg = top_overlay_img.resize((canvas_w, canvas_h))
                        st.caption(f"Dessinez un rectangle pour annoter")
                        canvas_result = st_canvas(
                            fill_color="rgba(66, 133, 244, 0.3)",
                            stroke_width=2,
                            stroke_color="#4285F4",
                            background_image=bg,
                            height=canvas_h,
                            width=canvas_w,
                            drawing_mode="rect",
                            key="canvas_top",
                        )
                        if canvas_result and canvas_result.json_data:
                            for obj in canvas_result.json_data.get("objects", []):
                                if obj.get("type") == "rect":
                                    # Normalize to 0-1
                                    nx_min = max(0.0, obj["left"] / canvas_w)
                                    ny_min = max(0.0, obj["top"] / canvas_h)
                                    nx_max = min(1.0, (obj["left"] + obj["width"] * obj.get("scaleX", 1)) / canvas_w)
                                    ny_max = min(1.0, (obj["top"] + obj["height"] * obj.get("scaleY", 1)) / canvas_h)
                                    pending = {
                                        "page_number": top_page,
                                        "x_min": round(nx_min, 4),
                                        "y_min": round(ny_min, 4),
                                        "x_max": round(nx_max, 4),
                                        "y_max": round(ny_max, 4),
                                    }
                                    # Avoid duplicates
                                    if pending not in st.session_state.pending_bboxes:
                                        st.session_state.pending_bboxes.append(pending)
                    except ImportError:
                        st.warning("streamlit-drawable-canvas non installe. `pip install streamlit-drawable-canvas`")
                        with st.container(height=550):
                            st.image(top_overlay_img, caption=f"Page {top_page}/{total_pages}", use_container_width=True)
                else:
                    with st.container(height=550):
                        st.image(top_overlay_img, caption=f"Page {top_page}/{total_pages}", use_container_width=True)

                bottom_page = st.number_input(
                    "Page (bas)", min_value=1, max_value=total_pages,
                    value=min(2, total_pages), step=1, key="pdf_bottom_page",
                )
                btm_db_bboxes = bboxes_pour_page(session, selected_doc_id, bottom_page)
                _existing_keys_btm = {(b.ligne_id, b.champ) for b in btm_db_bboxes}
                btm_auto_bboxes = _auto_bboxes_for_page(
                    pdf_path, bottom_page, _all_lignes, selected_doc_id, _existing_keys_btm,
                )
                bottom_bboxes = list(btm_db_bboxes) + btm_auto_bboxes
                bottom_base_img = images[bottom_page - 1]
                bottom_overlay_img = _overlay_bboxes(
                    bottom_base_img, bottom_bboxes, _ligne_map, _sel_ligne_id, _sel_champ,
                )

                # Show canvas or image for bottom pane
                if bottom_bboxes:
                    st.caption(f"Page {bottom_page}/{total_pages} — {len(bottom_bboxes)} annotation(s)")
                if annotation_active and annot_pane == "bas":
                    try:
                        from streamlit_drawable_canvas import st_canvas

                        canvas_h = 550
                        canvas_w = int(canvas_h * bottom_overlay_img.width / bottom_overlay_img.height)
                        bg = bottom_overlay_img.resize((canvas_w, canvas_h))
                        st.caption(f"Dessinez un rectangle pour annoter")
                        canvas_result_btm = st_canvas(
                            fill_color="rgba(66, 133, 244, 0.3)",
                            stroke_width=2,
                            stroke_color="#4285F4",
                            background_image=bg,
                            height=canvas_h,
                            width=canvas_w,
                            drawing_mode="rect",
                            key="canvas_bottom",
                        )
                        if canvas_result_btm and canvas_result_btm.json_data:
                            for obj in canvas_result_btm.json_data.get("objects", []):
                                if obj.get("type") == "rect":
                                    nx_min = max(0.0, obj["left"] / canvas_w)
                                    ny_min = max(0.0, obj["top"] / canvas_h)
                                    nx_max = min(1.0, (obj["left"] + obj["width"] * obj.get("scaleX", 1)) / canvas_w)
                                    ny_max = min(1.0, (obj["top"] + obj["height"] * obj.get("scaleY", 1)) / canvas_h)
                                    pending = {
                                        "page_number": bottom_page,
                                        "x_min": round(nx_min, 4),
                                        "y_min": round(ny_min, 4),
                                        "x_max": round(nx_max, 4),
                                        "y_max": round(ny_max, 4),
                                    }
                                    if pending not in st.session_state.pending_bboxes:
                                        st.session_state.pending_bboxes.append(pending)
                    except ImportError:
                        st.warning("streamlit-drawable-canvas non installe. `pip install streamlit-drawable-canvas`")
                        with st.container(height=550):
                            st.image(bottom_overlay_img, caption=f"Page {bottom_page}/{total_pages}", use_container_width=True)
                else:
                    with st.container(height=550):
                        st.image(bottom_overlay_img, caption=f"Page {bottom_page}/{total_pages}", use_container_width=True)
            else:
                st.warning(
                    f"PDF introuvable : *{selected_doc.fichier}*\n\n"
                    "Placez le fichier dans `samples/` ou `dashboard/data/uploads/` "
                    "pour l'afficher ici."
                )

        # ---- RIGHT: Confidence card + line selector + correction form ----
        with col_right:

            # -- Confidence overview --
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

            # -- All active lines for this document (for delete) --
            all_active_lignes = (
                session.query(LigneFacture)
                .filter(LigneFacture.document_id == selected_doc_id, LigneFacture.supprime != True)
                .order_by(LigneFacture.ligne_numero)
                .all()
            )

            df_detail = detail_confiance_document(session, selected_doc_id)
            if not df_detail.empty:
                conf_cols = [c for c in df_detail.columns if c not in ("ligne", "matiere")]
                st.dataframe(
                    _styled_conf_df(df_detail, conf_cols),
                    use_container_width=True, hide_index=True,
                )

            # -- Delete a line --
            if all_active_lignes:
                with st.expander("Supprimer une ligne"):
                    del_options = {
                        f"Ligne {l.ligne_numero} — {l.type_matiere or '?'}": l.id
                        for l in all_active_lignes
                    }
                    del_label = st.selectbox(
                        "Ligne a supprimer", options=list(del_options.keys()),
                        key="delete_ligne_select",
                    )
                    del_notes = st.text_input(
                        "Raison (optionnel)", key="delete_ligne_notes",
                    )
                    if st.button("Supprimer cette ligne", type="secondary", key="delete_ligne_btn"):
                        del_id = del_options[del_label]
                        supprimer_ligne(session, del_id, supprime_par="admin", notes=del_notes.strip() or None)
                        st.success(f"Ligne supprimee : {del_label}")
                        st.rerun()

            st.markdown("---")

            # -- Line selector --
            df_lignes = lignes_a_corriger(session, selected_doc_id, seuil=seuil)
            if df_lignes.empty:
                st.info("Aucune ligne faible pour ce document.")
            else:
                ligne_options = {
                    f"Ligne {row['ligne_numero']} — {row['type_matiere'] or '?'} "
                    f"({row['nb_champs_faibles']} champs faibles)": row["ligne_id"]
                    for _, row in df_lignes.iterrows()
                }
                selected_ligne_label = st.selectbox(
                    "Ligne", options=list(ligne_options.keys()),
                    key="correction_ligne_select",
                )
                selected_ligne_id = ligne_options[selected_ligne_label]

                # Load the line
                ligne = session.get(LigneFacture, selected_ligne_id)
                if ligne is None:
                    st.error("Ligne introuvable.")
                else:
                    faibles = set(champs_faibles_pour_ligne(ligne, seuil))

                    # Store active selection for bbox highlight in left pane
                    st.session_state["_active_ligne_id"] = selected_ligne_id

                    # -- Annotation controls --
                    st.markdown("---")
                    st.subheader("Annotation")
                    annot_col1, annot_col2, annot_col3 = st.columns([1, 1, 1])
                    with annot_col1:
                        st.toggle(
                            "Mode annotation",
                            key="annotation_toggle",
                        )
                    with annot_col2:
                        # Default to first weak field
                        weak_fields = list(faibles) if faibles else EDITABLE_FIELDS
                        all_field_options = weak_fields + [f for f in EDITABLE_FIELDS if f not in weak_fields]
                        annot_champ = st.selectbox(
                            "Champ a annoter", options=all_field_options,
                            key="annotation_champ_select",
                        )
                    with annot_col3:
                        st.radio(
                            "Annoter sur", options=["haut", "bas"],
                            horizontal=True, key="annotation_pane_radio",
                        )

                    # Show pending bboxes count
                    pending = st.session_state.get("pending_bboxes", [])
                    if pending:
                        st.info(f"{len(pending)} annotation(s) en attente de sauvegarde.")
                        if st.button("Effacer les annotations en attente", key="clear_pending"):
                            st.session_state.pending_bboxes = []
                            st.rerun()

                    st.markdown("---")
                    st.subheader("Champs de la ligne")

                    # Regular widgets (no st.form — Enter confirms field, not submit)
                    field_values = {}
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
                                conf_display = f"{conf_val:.0%}" if conf_val is not None else "N/A"
                                if is_weak:
                                    st.markdown(
                                        f"**{field}** &nbsp; :red[conf: {conf_display}]"
                                    )
                                else:
                                    st.markdown(
                                        f"**{field}** &nbsp; :green[conf: {conf_display}]"
                                    )

                                if field in FLOAT_FIELDS:
                                    field_values[field] = st.number_input(
                                        field,
                                        value=float(current_val) if current_val is not None else 0.0,
                                        format="%.4f", key=f"input_{field}",
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
                        "Notes (optionnel)", key="correction_notes", height=80,
                    )

                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        submit_corrections = st.button(
                            "Appliquer les corrections", type="primary", key="correction_submit",
                        )
                    with btn_col2:
                        save_annot_only = st.button(
                            "Sauvegarder annotations seules", key="save_annot_only",
                            disabled=not st.session_state.get("pending_bboxes"),
                        )

                    def _save_pending_bboxes(ligne_id, doc_id, champ, correction_log_id=None):
                        """Save all pending bboxes and clear the list."""
                        saved = 0
                        for pb in st.session_state.get("pending_bboxes", []):
                            try:
                                sauvegarder_bbox(
                                    session, ligne_id, doc_id, champ,
                                    pb["page_number"], pb["x_min"], pb["y_min"],
                                    pb["x_max"], pb["y_max"],
                                    source="manual", cree_par="admin",
                                    correction_log_id=correction_log_id,
                                )
                                saved += 1
                            except ValueError:
                                pass  # skip invalid coords
                        st.session_state.pending_bboxes = []
                        return saved

                    if submit_corrections:
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

                        has_pending = bool(st.session_state.get("pending_bboxes"))

                        if changes:
                            logs = appliquer_correction(
                                session, selected_ligne_id, changes,
                                corrige_par="admin",
                                notes=notes.strip() or None,
                            )
                            # Save pending bboxes linked to the first correction log
                            bbox_count = 0
                            if has_pending:
                                log_id = logs[0].id if logs else None
                                bbox_count = _save_pending_bboxes(
                                    selected_ligne_id, selected_doc_id, annot_champ, log_id,
                                )
                            msg = f"{len(logs)} champ(s) corrige(s)"
                            if bbox_count:
                                msg += f", {bbox_count} annotation(s) sauvegardee(s)"
                            st.success(msg + ".")
                            st.rerun()
                        elif has_pending:
                            # No field changes but has annotations
                            bbox_count = _save_pending_bboxes(
                                selected_ligne_id, selected_doc_id, annot_champ,
                            )
                            st.success(f"{bbox_count} annotation(s) sauvegardee(s).")
                            st.rerun()
                        else:
                            st.warning("Aucune modification detectee.")

                    if save_annot_only:
                        bbox_count = _save_pending_bboxes(
                            selected_ligne_id, selected_doc_id, annot_champ,
                        )
                        if bbox_count:
                            st.success(f"{bbox_count} annotation(s) sauvegardee(s).")
                            st.rerun()
                        else:
                            st.warning("Aucune annotation valide a sauvegarder.")

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
