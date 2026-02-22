"""
Page 11 — Vérification PDF
Split-view plein écran : PDF original (gauche, PDF.js) ↔ extraction structurée (droite).
Supporte le thème dark/light via st.session_state._rationalize_theme.
"""
import os, sys, json, threading, socket, functools
import http.server
from pathlib import Path
from urllib.parse import quote

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st

st.set_page_config(
    page_title="Vérification PDF",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)
from dashboard.styles.theme import inject_theme, _current
inject_theme()

# ── CSS plein écran (page-specific, vient après inject_theme) ────────────────
st.markdown("""
<style>
/* Supprimer tous les espaces pour le mode plein écran */
.block-container          { padding: 0 !important; }
[data-testid="stVerticalBlock"] { gap: 0 !important; }
.element-container        { margin: 0 !important; }
/* Barre d'outils (sélecteur de fichier) */
[data-testid="stHorizontalBlock"] {
    background: var(--bg-secondary) !important;
    padding: 5px 18px !important;
    border-bottom: 1px solid var(--border) !important;
    align-items: center !important;
}
/* Le sélecteur de document : label masqué, style compact */
div[data-testid="stSelectbox"] label { display: none; }
div[data-testid="stSelectbox"] > div > div {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-mono) !important;
    font-size: 12px !important;
}
/* Forcer l'iframe à occuper toute la hauteur restante */
iframe {
    height: calc(100vh - 52px) !important;
    width: 100% !important;
    border: none !important;
    display: block !important;
}
</style>
""", unsafe_allow_html=True)

# ── Mini serveur HTTP pour les PDFs ─────────────────────────────────────────
SAMPLES_DIR     = Path(_PROJECT_ROOT) / "samples"
EXTRACTIONS_DIR = Path(_PROJECT_ROOT) / "output" / "extractions"
PDF_SERVER_PORT = 8504

class _CORSHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()
    def log_message(self, *_): pass

def _port_free(p: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", p)) != 0

if _port_free(PDF_SERVER_PORT):
    _h = functools.partial(_CORSHandler, directory=str(SAMPLES_DIR))
    threading.Thread(
        target=http.server.HTTPServer(("localhost", PDF_SERVER_PORT), _h).serve_forever,
        daemon=True,
    ).start()

# ── Données ──────────────────────────────────────────────────────────────────
PDF_FILES = sorted(SAMPLES_DIR.glob("*.pdf"))

def find_extraction(pdf_path: Path) -> Path | None:
    stem = pdf_path.stem.replace(" ", "_").replace("+", "").replace("  ", "_")
    for p in EXTRACTIONS_DIR.glob("*_extraction.json"):
        cand = p.stem.replace("_extraction", "")
        if cand in (stem, pdf_path.stem.replace(" ", "_")):
            return p
    first = stem.split("_")[0]
    for p in EXTRACTIONS_DIR.glob(f"{first}*_extraction.json"):
        return p
    return None

# ── Palette thème ─────────────────────────────────────────────────────────────
def _pal() -> dict:
    if _current() == "light":
        return dict(
            body_bg="#f2f4f8",    hdr_bg="#e8ecf2",   pane_lbl_bg="#eaeef5",
            border="#d0d7e3",     border_light="#e0e5ef",
            split_bg="#d8dce6",
            txt_p="#1a2035",      txt_s="#5a6a88",     txt_m="#8a97ab",
            txt_dim="#aab3c5",    txt_num="#1a3060",
            card_bg="#ffffff",    card_bg2="#f4f6fb",
            row_even="#f8fafc",   row_odd="#ffffff",
            pdf_bg="#d8d8d8",
            accent="#2563eb",     accent_bg="#eff4ff",  accent_border="#bfdbfe",
            alert_bg="#fffbeb",   alert_border="#d97706",
            notes_bg="#f8fafc",   notes_border="#d0d7e3",
            status_bg="#e8ecf2",  status_border="#d0d7e3",
            hdr_file_bg="#dbe8ff", hdr_file_color="#2563eb", hdr_file_border="#bfdbfe",
        )
    return dict(
        body_bg="#0d0f14",    hdr_bg="#080b11",    pane_lbl_bg="#080b11",
        border="#1a2035",     border_light="#131825",
        split_bg="#1a2035",
        txt_p="#c8d0e0",      txt_s="#3a4258",     txt_m="#2d3748",
        txt_dim="#4a5568",    txt_num="#c8d0e0",
        card_bg="#0a0d14",    card_bg2="#0a0c12",
        row_even="#0a0c12",   row_odd="#0d0f17",
        pdf_bg="#1a1a1a",
        accent="#4a90d9",     accent_bg="#0d1828",  accent_border="#1a3a5c",
        alert_bg="#0d0f14",   alert_border="#ff8c42",
        notes_bg="#0a0c12",   notes_border="#1a2035",
        status_bg="#080b11",  status_border="#1a2035",
        hdr_file_bg="#0d1828", hdr_file_color="#4a90d9", hdr_file_border="#1a3a5c",
    )

# ── Confiance ─────────────────────────────────────────────────────────────────
_CONF = {
    "absent":  ("#ff4d4d", "#2a1010"),
    "faible":  ("#ff8c42", "#2a1a0a"),
    "moyen":   ("#f0c040", "#2a220a"),
    "bon":     ("#52c77f", "#0a2018"),
    "parfait": ("#34d399", "#061a12"),
}
_CONF_LIGHT = {
    "absent":  ("#dc2626", "#fff1f1"),
    "faible":  ("#ea580c", "#fff7ed"),
    "moyen":   ("#d97706", "#fffbeb"),
    "bon":     ("#16a34a", "#f0fdf4"),
    "parfait": ("#059669", "#ecfdf5"),
}

def _conf_colors():
    return _CONF_LIGHT if _current() == "light" else _CONF

def conf_tier(score):
    if score is None or score == 0: return "absent",  "0%"
    if score < 0.5:                  return "faible",  f"{score:.0%}"
    if score < 0.7:                  return "moyen",   f"{score:.0%}"
    if score < 0.9:                  return "bon",     f"{score:.0%}"
    return                                  "parfait", f"{score:.0%}"

def conf_badge(score, cc: dict) -> str:
    tier, pct = conf_tier(score)
    fg, bg = cc[tier]
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {fg}55;'
        f'font-family:\'JetBrains Mono\',monospace;font-size:9px;font-weight:600;'
        f'padding:1px 7px;border-radius:3px;white-space:nowrap">⬤ {pct}</span>'
    )

def val_cell(val, P: dict) -> str:
    if val is None:
        return f'<span style="color:{P["txt_dim"]};font-style:italic">—</span>'
    if isinstance(val, float):
        return (f'<span style="font-family:\'JetBrains Mono\',monospace;'
                f'color:{P["txt_num"]}">{val:,.2f}</span>')
    return str(val)

# ── Sélection document ────────────────────────────────────────────────────────
P = _pal()

col_lbl, col_sel, _spc = st.columns([1, 6, 3])
with col_lbl:
    st.markdown(
        f"<p style='font-family:Manrope,sans-serif;font-size:10px;font-weight:700;"
        f"letter-spacing:.12em;text-transform:uppercase;color:{P['txt_dim']};"
        f"padding-top:10px;margin:0'>Document</p>",
        unsafe_allow_html=True,
    )
with col_sel:
    selected_pdf = st.selectbox("", PDF_FILES, format_func=lambda p: p.name)

extraction_path = find_extraction(selected_pdf)
extraction = json.loads(extraction_path.read_text(encoding="utf-8")) if extraction_path else None
pdf_url    = f"http://localhost:{PDF_SERVER_PORT}/{quote(selected_pdf.name)}"

# ── Panneau extraction ────────────────────────────────────────────────────────
def build_extraction_panel(ext: dict | None, P: dict, cc: dict) -> str:
    if not ext:
        return (f"<p style='color:{P['txt_dim']};padding:40px;"
                f"font-family:Manrope,sans-serif'>Extraction introuvable.</p>")

    meta   = ext.get("metadonnees", {})
    fourn  = meta.get("fournisseur", {}) or {}
    client = meta.get("client", {}) or {}
    refs   = meta.get("references", {}) or {}
    lignes = ext.get("lignes", [])
    warns  = ext.get("warnings", [])
    champs = ext.get("champs_manquants", [])
    conf_g = ext.get("confiance_globale", 0)

    tier_g, pct_g = conf_tier(conf_g)
    fg_g, bg_g    = cc[tier_g]

    strat_labels = {
        "pdfplumber_tables":       "PDF natif — tableaux",
        "auto_pdfplumber":         "PDF natif",
        "ocr_tesseract":           "OCR Tesseract",
        "auto_fallback_paddleocr": "OCR PaddleOCR",
    }
    type_labels = {
        "facture":          "Facture",
        "facture_attentes": "Facture Attentes",
    }

    def mrow(label, value):
        if not value: return ""
        return (
            f'<tr>'
            f'<td style="font-family:Manrope,sans-serif;font-size:10px;font-weight:600;'
            f'letter-spacing:.07em;text-transform:uppercase;color:{P["txt_s"]};'
            f'padding:5px 14px 5px 0;white-space:nowrap;vertical-align:top">{label}</td>'
            f'<td style="font-family:Manrope,sans-serif;font-size:12px;color:{P["txt_p"]};'
            f'padding:5px 0;line-height:1.5">{value}</td>'
            f'</tr>'
        )

    meta_card = f"""
    <div style="background:{P['card_bg']};border:1px solid {P['border']};border-radius:6px;
                padding:16px 20px;margin-bottom:14px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
        <div>
          <div style="font-family:'DM Serif Display',serif;font-size:22px;
                      color:{P['txt_p']};letter-spacing:.01em">
            {meta.get('numero_document','—')}
          </div>
          <div style="font-family:Manrope,sans-serif;font-size:10px;color:{P['txt_s']};
                      letter-spacing:.1em;text-transform:uppercase;margin-top:2px">
            {type_labels.get(ext.get('type_document',''), ext.get('type_document',''))}
            &nbsp;·&nbsp; {meta.get('date_document','—')}
            &nbsp;·&nbsp; {strat_labels.get(ext.get('strategie_utilisee',''), ext.get('strategie_utilisee',''))}
          </div>
        </div>
        <div style="background:{bg_g};border:1px solid {fg_g}55;border-radius:5px;
                    padding:8px 14px;text-align:center;flex-shrink:0;margin-left:16px">
          <div style="font-family:'JetBrains Mono',monospace;font-size:22px;
                      font-weight:700;color:{fg_g};line-height:1">{pct_g}</div>
          <div style="font-family:Manrope,sans-serif;font-size:8px;color:{fg_g};
                      letter-spacing:.1em;text-transform:uppercase;margin-top:3px;opacity:.7">confiance</div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 32px">
        <table style="border-collapse:collapse">
          {mrow("Fournisseur", fourn.get("nom"))}
          {mrow("TVA fourn.", fourn.get("tva_intra"))}
          {mrow("Client", client.get("nom"))}
          {mrow("Commande", refs.get("commande"))}
        </table>
        <table style="border-collapse:collapse">
          {mrow("HT",  f"{meta.get('montant_ht'):,.2f} {meta.get('devise','EUR')}" if meta.get('montant_ht') else None)}
          {mrow("TTC", f"{meta.get('montant_ttc'):,.2f} {meta.get('devise','EUR')}" if meta.get('montant_ttc') else None)}
          {mrow("Paiement", meta.get("conditions_paiement"))}
          {mrow("Champs ∅", ", ".join(champs) if champs else None)}
        </table>
      </div>
    </div>"""

    # Légende confiance
    legend = (
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;'
        f'margin-bottom:12px;padding:8px 12px;background:{P["card_bg"]};'
        f'border:1px solid {P["border"]};border-radius:4px">'
        f'<span style="font-family:Manrope,sans-serif;font-size:9px;font-weight:700;'
        f'color:{P["txt_m"]};letter-spacing:.1em;text-transform:uppercase;'
        f'margin-right:4px">Confiance :</span>'
    )
    for label, tier in [("0%","absent"),("<50%","faible"),("50-70%","moyen"),("70-90%","bon"),(">90%","parfait")]:
        fg, bg = cc[tier]
        legend += (f'<span style="background:{bg};color:{fg};border:1px solid {fg}44;'
                   f'font-family:Manrope,sans-serif;font-size:9px;padding:2px 8px;border-radius:3px">'
                   f'⬤ {label}</span>')
    legend += "</div>"

    # Colonnes du tableau
    col_defs = [
        ("#",             "36px",  "center"),
        ("Matière / Pièce","auto", "left"),
        ("Unité",         "52px",  "center"),
        ("Quantité",      "76px",  "right"),
        ("Prix unit.",    "80px",  "right"),
        ("Total €",       "80px",  "right"),
        ("Date dép.",     "88px",  "center"),
        ("Date arr.",     "88px",  "center"),
        ("Départ",        "110px", "left"),
        ("Arrivée",       "110px", "left"),
    ]
    conf_fields = [
        ("type_matiere","Matière"),("unite","Unité"),
        ("quantite","Qté"),("prix_unitaire","PU"),
        ("prix_total","Total"),("date_depart","D.dép"),
        ("date_arrivee","D.arr"),("lieu_depart","Départ"),
        ("lieu_arrivee","Arrivée"),
    ]

    th = (f"font-family:Manrope,sans-serif;font-size:9px;font-weight:700;letter-spacing:.1em;"
          f"text-transform:uppercase;color:{P['txt_m']};padding:8px 10px;"
          f"border-bottom:2px solid {P['border']};white-space:nowrap;")
    headers = "".join(
        f'<th style="{th}text-align:{a};width:{w}">{n}</th>'
        for n, w, a in col_defs
    )

    rows = ""
    for i, ligne in enumerate(lignes):
        conf  = ligne.get("confiance", {})
        bg_r  = P["row_even"] if i % 2 == 0 else P["row_odd"]
        pu, qt, pt = ligne.get("prix_unitaire"), ligne.get("quantite"), ligne.get("prix_total")
        total_c = "#ff6b6b" if (pu and qt and pt and abs(round(pu * qt, 2) - pt) > 0.02) else P["txt_p"]
        td = (f'style="padding:7px 10px;border-bottom:1px solid {P["border_light"]};'
              f'vertical-align:middle;background:{bg_r};')
        rows += f"""
        <tr>
          <td {td}text-align:center;color:{P['txt_dim']};font-family:'JetBrains Mono',monospace;font-size:11px">{ligne.get('ligne_numero','')}</td>
          <td {td}color:{P['txt_p']};font-family:Manrope,sans-serif;font-size:12px">{val_cell(ligne.get('type_matiere'),P)}</td>
          <td {td}text-align:center;font-family:'JetBrains Mono',monospace;font-size:11px;color:{P['txt_s']}">{val_cell(ligne.get('unite'),P)}</td>
          <td {td}text-align:right;font-family:'JetBrains Mono',monospace;font-size:11px;color:{P['txt_p']}">{val_cell(ligne.get('quantite'),P)}</td>
          <td {td}text-align:right;font-family:'JetBrains Mono',monospace;font-size:11px;color:{P['txt_p']}">{val_cell(ligne.get('prix_unitaire'),P)}</td>
          <td {td}text-align:right;font-family:'JetBrains Mono',monospace;font-size:11px;color:{total_c}">{val_cell(ligne.get('prix_total'),P)}</td>
          <td {td}text-align:center;font-family:'JetBrains Mono',monospace;font-size:10px;color:{P['txt_dim']}">{val_cell(ligne.get('date_depart'),P)}</td>
          <td {td}text-align:center;font-family:'JetBrains Mono',monospace;font-size:10px;color:{P['txt_dim']}">{val_cell(ligne.get('date_arrivee'),P)}</td>
          <td {td}color:{P['txt_s']};font-family:Manrope,sans-serif;font-size:11px">{val_cell(ligne.get('lieu_depart'),P)}</td>
          <td {td}color:{P['txt_s']};font-family:Manrope,sans-serif;font-size:11px">{val_cell(ligne.get('lieu_arrivee'),P)}</td>
        </tr>
        <tr>
          <td colspan="10" style="padding:3px 10px 9px;background:{bg_r};border-bottom:1px solid {P['border_light']}">
            <div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">
              <span style="font-family:Manrope,sans-serif;font-size:9px;color:{P['txt_m']};
                           font-weight:600;letter-spacing:.07em;text-transform:uppercase;
                           margin-right:3px">conf.</span>
              {"".join(
                  f'<span style="display:inline-flex;align-items:center;gap:3px">'
                  f'<span style="font-family:Manrope,sans-serif;font-size:9px;color:{P["txt_m"]}">{label}</span>'
                  f'{conf_badge(conf.get(key), cc)}</span>'
                  for key, label in conf_fields
              )}
            </div>
          </td>
        </tr>"""

    table = (
        f'<div style="overflow-x:auto;border:1px solid {P["border"]};border-radius:6px;margin-bottom:14px">'
        f'<table style="border-collapse:collapse;width:100%;min-width:880px">'
        f'<thead><tr style="background:{P["hdr_bg"]}">{headers}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>'
    )

    # Alertes
    alerts_html = ""
    if warns or champs:
        champ_li = "".join(
            f'<li style="font-family:\'JetBrains Mono\',monospace;font-size:10px;'
            f'color:#ff4d4d;margin-bottom:3px">{c}</li>' for c in champs)
        warn_li = "".join(
            f'<li style="font-family:Manrope,sans-serif;font-size:11px;color:#ff8c42;'
            f'margin-bottom:5px;line-height:1.5">{w}</li>' for w in warns)
        alerts_html = (
            f'<div style="border:1px solid {P["alert_border"]};border-left:3px solid {P["alert_border"]};'
            f'border-radius:4px;padding:12px 16px;margin-bottom:12px;background:{P["alert_bg"]}">'
            f'<div style="font-family:Manrope,sans-serif;font-size:9px;font-weight:700;'
            f'color:{P["alert_border"]};letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px">'
            f'⚠ Alertes & Champs manquants</div>'
            f'{"<ul style=\"margin:0;padding-left:14px;margin-bottom:8px\">" + champ_li + "</ul>" if champs else ""}'
            f'{"<ul style=\"margin:0;padding-left:14px\">" + warn_li + "</ul>" if warns else ""}'
            f'</div>'
        )

    # Notes
    notes = ext.get("extraction_notes", "")
    notes_html = ""
    if notes:
        notes_html = (
            f'<div style="border:1px solid {P["notes_border"]};border-radius:4px;'
            f'padding:12px 16px;background:{P["notes_bg"]}">'
            f'<div style="font-family:Manrope,sans-serif;font-size:9px;font-weight:700;'
            f'color:{P["txt_m"]};letter-spacing:.12em;text-transform:uppercase;margin-bottom:7px">'
            f'Notes d\'extraction</div>'
            f'<p style="font-family:Manrope,sans-serif;font-size:11px;color:{P["txt_s"]};'
            f'line-height:1.7;margin:0">{notes}</p>'
            f'</div>'
        )

    return meta_card + legend + table + alerts_html + notes_html


# ── Rendu ─────────────────────────────────────────────────────────────────────
cc         = _conf_colors()
right_html = build_extraction_panel(extraction, P, cc)
nb_lignes  = len(extraction.get("lignes", [])) if extraction else 0
conf_g     = extraction.get("confiance_globale", 0) if extraction else 0
tier_st, pct_st = conf_tier(conf_g)
fg_st, _        = cc[tier_st]

nb_champs  = len(extraction.get("champs_manquants", [])) if extraction else 0
nb_warns   = len(extraction.get("warnings", []))          if extraction else 0
dot_color  = "#52c77f" if extraction else "#ff4d4d"
ext_label  = "extraction OK" if extraction else "extraction introuvable"

html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;600&family=Manrope:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;overflow:hidden}}
body{{
  background:{P['body_bg']};
  color:{P['txt_p']};
  font-family:'Manrope',sans-serif;
  display:flex;flex-direction:column;
}}

/* Split layout */
.split{{display:flex;flex:1;overflow:hidden;height:calc(100vh - 22px)}}

/* PDF pane */
.pane-pdf{{
  flex:0 0 50%;border-right:2px solid {P['border']};
  display:flex;flex-direction:column;
  background:{P['pdf_bg']};min-width:280px
}}
.pane-lbl{{
  font-family:'Manrope',sans-serif;font-size:9px;font-weight:700;
  letter-spacing:.15em;text-transform:uppercase;
  padding:7px 14px;background:{P['pane_lbl_bg']};
  border-bottom:1px solid {P['border']};color:{P['txt_m']};flex-shrink:0
}}

/* PDF.js */
#pdf-container{{
  flex:1;overflow-y:auto;overflow-x:auto;padding:12px;
  display:flex;flex-direction:column;align-items:center;gap:8px;
  scrollbar-width:thin;scrollbar-color:{P['border']} transparent
}}
#pdf-container::-webkit-scrollbar{{width:5px}}
#pdf-container::-webkit-scrollbar-thumb{{background:{P['border']};border-radius:3px}}
#pdf-container canvas{{
  box-shadow:0 4px 20px rgba(0,0,0,.35);border-radius:2px;
  max-width:100%;display:block
}}
#pdf-loading{{
  font-family:'JetBrains Mono',monospace;font-size:11px;
  color:{P['txt_m']};padding:40px;text-align:center
}}
#pdf-error{{
  font-family:'Manrope',sans-serif;font-size:12px;
  color:#ff4d4d;padding:20px;text-align:center
}}

/* Resizer */
.resizer{{
  flex:0 0 4px;background:{P['border']};
  cursor:col-resize;transition:background .15s;z-index:10
}}
.resizer:hover,.resizer.active{{background:{P['accent']}}}

/* Extraction pane */
.pane-ext{{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:360px}}
.ext-scroll{{
  flex:1;overflow-y:auto;padding:14px 18px 32px;
  scrollbar-width:thin;scrollbar-color:{P['border']} transparent;
  background:{P['body_bg']}
}}
.ext-scroll::-webkit-scrollbar{{width:5px}}
.ext-scroll::-webkit-scrollbar-thumb{{background:{P['border']};border-radius:3px}}

/* Status bar */
.status{{
  height:22px;background:{P['status_bg']};
  border-top:1px solid {P['status_border']};
  display:flex;align-items:center;padding:0 14px;gap:14px;flex-shrink:0
}}
.si{{
  font-family:'JetBrains Mono',monospace;font-size:9px;
  color:{P['txt_m']};display:flex;align-items:center;gap:4px
}}
.dot{{width:5px;height:5px;border-radius:50%}}
</style>
</head>
<body>

<div class="split" id="split">

  <!-- PDF -->
  <div class="pane-pdf" id="pane-pdf">
    <div class="pane-lbl">📄 Document original — {selected_pdf.name}</div>
    <div id="pdf-container">
      <div id="pdf-loading">⏳ Chargement du PDF…</div>
    </div>
  </div>

  <div class="resizer" id="resizer"></div>

  <!-- Extraction -->
  <div class="pane-ext" id="pane-ext">
    <div class="pane-lbl">🧬 Extraction — {nb_lignes} ligne(s)</div>
    <div class="ext-scroll">{right_html}</div>
  </div>

</div>

<div class="status">
  <div class="si"><div class="dot" style="background:{dot_color}"></div>{ext_label}</div>
  <div class="si">· confiance : <span style="color:{fg_st};margin-left:3px">{pct_st}</span></div>
  <div class="si">· {nb_champs} champ(s) manquant(s)</div>
  <div class="si">· {nb_warns} alerte(s)</div>
  <div class="si" id="pdf-status">· chargement PDF…</div>
</div>

<script>
pdfjsLib.GlobalWorkerOptions.workerSrc =
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

const PDF_URL   = "{pdf_url}";
const container = document.getElementById('pdf-container');
const statusEl  = document.getElementById('pdf-status');

pdfjsLib.getDocument(PDF_URL).promise
  .then(pdf => {{
    const total = pdf.numPages;
    document.getElementById('pdf-loading').remove();
    statusEl.textContent = '· page 0 / ' + total;
    const render = n => {{
      if (n > total) {{ statusEl.textContent = '· ' + total + ' page(s)'; return; }}
      pdf.getPage(n).then(page => {{
        const vp = page.getViewport({{scale:1.6}});
        const c  = document.createElement('canvas');
        c.height = vp.height; c.width = vp.width;
        container.appendChild(c);
        page.render({{canvasContext:c.getContext('2d'),viewport:vp}})
          .promise.then(() => {{ statusEl.textContent = '· page ' + n + ' / ' + total; render(n+1); }});
      }});
    }};
    render(1);
  }})
  .catch(err => {{
    document.getElementById('pdf-loading').remove();
    container.innerHTML = '<div id="pdf-error">❌ ' + err.message + '</div>';
    statusEl.textContent = '· erreur PDF';
  }});

// Drag-to-resize
const resizer = document.getElementById('resizer');
const pdfPane = document.getElementById('pane-pdf');
const split   = document.getElementById('split');
let dragging=false, startX=0, startW=0;
resizer.addEventListener('mousedown', e => {{
  dragging=true; startX=e.clientX;
  startW=pdfPane.getBoundingClientRect().width;
  resizer.classList.add('active');
  document.body.style.cssText+='cursor:col-resize;user-select:none';
}});
window.addEventListener('mousemove', e => {{
  if (!dragging) return;
  const total = split.getBoundingClientRect().width;
  pdfPane.style.flex = '0 0 ' + Math.min(Math.max(startW+(e.clientX-startX),280),total-360) + 'px';
}});
window.addEventListener('mouseup', () => {{
  dragging=false; resizer.classList.remove('active');
  document.body.style.cursor=document.body.style.userSelect='';
}});
</script>
</body>
</html>"""

st.components.v1.html(html, height=800, scrolling=False)
