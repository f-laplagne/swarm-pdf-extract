"""
Page 11 — Vérification PDF
Architecture définitive :
- CSS pour masquer le header Streamlit (Deploy button)
- UNE seule st.components.v1.html() avec le split-view complet
- Sélecteur de document : <select> HTML natif DANS l'iframe (pure JS, 0 rerun)
- Hauteur dynamique via window.parent.postMessage setFrameHeight (0 rerun, 0 conflit CSS)
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

# Stratégie de pleine page :
#   1. Masquer header/footer Streamlit
#   2. Cibler les CONTENEURS PARENTS de l'iframe (jamais l'iframe elle-même → boucle rerun)
#   3. Mettre toute la chaîne de conteneurs à height:100vh + overflow:hidden
#   4. L'iframe Python est à height=2000 (dépasse toujours le viewport)
#   5. overflow:hidden sur les parents la clippe à exactement 100vh → pleine page
st.markdown("""
<style>
header[data-testid="stHeader"]   { display: none !important; }
footer[data-testid="stFooter"]   { display: none !important; }
#MainMenu                         { display: none !important; }
.stDeployButton                   { display: none !important; }

/* Chaîne de clip : du conteneur principal jusqu'à l'élément précédant l'iframe.
   NE PAS cibler <iframe> directement → déclencherait un rerun Streamlit infini. */
[data-testid="stMain"]            { height: 100vh !important; overflow: hidden !important;
                                    padding: 0 !important; }
.block-container                  { padding: 0 !important; max-width: 100% !important;
                                    height: 100vh !important; overflow: hidden !important; }
[data-testid="stVerticalBlock"]   { gap: 0 !important; height: 100vh !important;
                                    overflow: hidden !important; }
.element-container                { margin: 0 !important; height: 100vh !important;
                                    overflow: hidden !important; }
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

PDF_FILES = sorted(SAMPLES_DIR.glob("*.pdf"))

def find_extraction(pdf_path: Path) -> Path | None:
    # Normalisation : espaces → underscores, suppression +, underscores doubles → simple
    stem = pdf_path.stem.replace(" ", "_").replace("+", "")
    while "__" in stem:
        stem = stem.replace("__", "_")
    stem = stem.strip("_")

    # Étape 1 : égalité exacte (cas où JSON et PDF ont le même nom court)
    for p in sorted(EXTRACTIONS_DIR.glob("*_extraction.json")):
        cand = p.stem.replace("_extraction", "")
        if cand == stem:
            return p

    # Étape 2 : le JSON stem est un PRÉFIXE du PDF stem.
    # Ex. "Facture_24-110192" est préfixe de "Facture_24-110192_complements_general_fr".
    # On retient le candidat le plus long (plus spécifique).
    best: Path | None = None
    best_len = 0
    for p in sorted(EXTRACTIONS_DIR.glob("*_extraction.json")):
        cand = p.stem.replace("_extraction", "")
        if stem == cand or stem.startswith(cand + "_"):
            if len(cand) > best_len:
                best = p
                best_len = len(cand)
    return best

# ── Palette thème ────────────────────────────────────────────────────────────
def _pal() -> dict:
    if _current() == "light":
        return dict(
            body_bg="#f2f4f8",   hdr_bg="#e8ecf2",
            card_bg="#ffffff",   border="#d0d7e3",    border_light="#e0e5ef",
            txt_p="#1a2035",     txt_s="#5a6a88",     txt_m="#8a97ab",
            txt_dim="#aab3c5",   txt_num="#1a3060",
            row_even="#f8fafc",  row_odd="#ffffff",
            pdf_bg="#d8d8d8",    split_bg="#d8dce6",
            alert_bg="#fffbeb",  alert_border="#d97706",
            notes_bg="#f8fafc",  notes_border="#d0d7e3",
            accent="#2563eb",    select_bg="#e8ecf2",
        )
    return dict(
        body_bg="#0d0f14",   hdr_bg="#080b11",
        card_bg="#0a0d14",   border="#1a2035",    border_light="#131825",
        txt_p="#c8d0e0",     txt_s="#3a4258",     txt_m="#2d3748",
        txt_dim="#4a5568",   txt_num="#c8d0e0",
        row_even="#0a0c12",  row_odd="#0d0f17",
        pdf_bg="#1a1a1a",    split_bg="#1a2035",
        alert_bg="#0d0f14",  alert_border="#ff8c42",
        notes_bg="#0a0c12",  notes_border="#1a2035",
        accent="#4a90d9",    select_bg="#080b11",
    )

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
        f'font-family:JetBrains Mono,monospace;font-size:9px;font-weight:600;'
        f'padding:1px 7px;border-radius:3px;white-space:nowrap">⬤ {pct}</span>'
    )

def val_cell(val, P: dict) -> str:
    if val is None:
        return f'<span style="color:{P["txt_dim"]};font-style:italic">—</span>'
    if isinstance(val, float):
        return (f'<span style="font-family:JetBrains Mono,monospace;'
                f'color:{P["txt_num"]}">{val:,.2f}</span>')
    return str(val)

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
        {meta.get('date_document','—')}
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

    col_defs = [
        ("#","36px","center"), ("Matière / Pièce","auto","left"),
        ("Unité","52px","center"), ("Quantité","76px","right"),
        ("Prix unit.","80px","right"), ("Total €","80px","right"),
        ("Date dép.","88px","center"), ("Date arr.","88px","center"),
        ("Départ","110px","left"), ("Arrivée","110px","left"),
    ]
    conf_fields = [
        ("type_matiere","Matière"),("unite","Unité"),("quantite","Qté"),
        ("prix_unitaire","PU"),("prix_total","Total"),("date_depart","D.dép"),
        ("date_arrivee","D.arr"),("lieu_depart","Départ"),("lieu_arrivee","Arrivée"),
    ]

    th = (f"font-family:Manrope,sans-serif;font-size:9px;font-weight:700;"
          f"letter-spacing:.1em;text-transform:uppercase;color:{P['txt_m']};"
          f"padding:8px 10px;border-bottom:2px solid {P['border']};white-space:nowrap;")
    headers = "".join(
        f'<th style="{th}text-align:{a};width:{w}">{n}</th>'
        for n, w, a in col_defs
    )

    rows = ""
    for i, ligne in enumerate(lignes):
        conf  = ligne.get("confiance", {})
        bg_r  = P["row_even"] if i % 2 == 0 else P["row_odd"]
        pu, qt, pt = ligne.get("prix_unitaire"), ligne.get("quantite"), ligne.get("prix_total")
        total_c = "#ff6b6b" if (pu and qt and pt and abs(round(pu*qt,2)-pt) > 0.02) else P["txt_p"]
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
        f'<div style="overflow-x:auto;border:1px solid {P["border"]};'
        f'border-radius:6px;margin-bottom:14px">'
        f'<table style="border-collapse:collapse;width:100%;min-width:880px">'
        f'<thead><tr style="background:{P["hdr_bg"]}">{headers}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>'
    )

    alerts_html = ""
    if warns or champs:
        champ_li = "".join(
            f'<li style="font-family:JetBrains Mono,monospace;font-size:10px;'
            f'color:#ff4d4d;margin-bottom:3px">{c}</li>' for c in champs)
        warn_li = "".join(
            f'<li style="font-family:Manrope,sans-serif;font-size:11px;color:#ff8c42;'
            f'margin-bottom:5px;line-height:1.5">{w}</li>' for w in warns)
        ul_champs = f'<ul style="margin:0;padding-left:14px;margin-bottom:8px">{champ_li}</ul>' if champs else ""
        ul_warns  = f'<ul style="margin:0;padding-left:14px">{warn_li}</ul>' if warns else ""
        alerts_html = (
            f'<div style="border:1px solid {P["alert_border"]};border-left:3px solid {P["alert_border"]};'
            f'border-radius:4px;padding:12px 16px;margin-bottom:12px;background:{P["alert_bg"]}">'
            f'<div style="font-family:Manrope,sans-serif;font-size:9px;font-weight:700;'
            f'color:{P["alert_border"]};letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px">'
            f'⚠ Alertes & Champs manquants</div>'
            f'{ul_champs}{ul_warns}</div>'
        )

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

    return meta_card + table + alerts_html + notes_html


# ── Construction de tous les panneaux ────────────────────────────────────────
P  = _pal()
cc = _conf_colors()

all_docs: dict = {}
for pdf_path in PDF_FILES:
    ext_path = find_extraction(pdf_path)
    ext = json.loads(ext_path.read_text(encoding="utf-8")) if ext_path else None
    nb_l  = len(ext.get("lignes", [])) if ext else 0
    conf  = ext.get("confiance_globale", 0) if ext else 0
    tier, pct = conf_tier(conf)
    fg, _ = cc[tier]
    all_docs[pdf_path.name] = {
        "url":        f"http://localhost:{PDF_SERVER_PORT}/{quote(pdf_path.name)}",
        "panel":      build_extraction_panel(ext, P, cc),
        "nb_lignes":  nb_l,
        "nb_champs":  len(ext.get("champs_manquants", [])) if ext else 0,
        "nb_warns":   len(ext.get("warnings", [])) if ext else 0,
        "conf_pct":   pct,
        "conf_color": fg,
        "dot_color":  "#52c77f" if ext else "#ff4d4d",
        "ext_label":  "extraction OK" if ext else "extraction introuvable",
    }

initial_name = list(all_docs.keys())[0] if all_docs else ""
all_docs_json = json.dumps(all_docs).replace("</", "<\\/")

options_html = "\n".join(
    f'<option value="{n}"{" selected" if n == initial_name else ""}>{n}</option>'
    for n in all_docs.keys()
) if all_docs else '<option value="">Aucun PDF</option>'

init       = all_docs.get(initial_name, {})
nb_lignes  = init.get("nb_lignes", 0)
nb_champs  = init.get("nb_champs", 0)
nb_warns   = init.get("nb_warns",  0)
dot_color  = init.get("dot_color", "#ff4d4d")
ext_label  = init.get("ext_label", "")
pct_st     = init.get("conf_pct",  "0%")
fg_st      = init.get("conf_color","#4a5568")
right_html = init.get("panel", "<p>Aucun document trouvé.</p>")

# ── Rendu — UNE seule iframe, hauteur dynamique via postMessage ──────────────
html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;600&family=Manrope:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;overflow:hidden;background:{P['body_bg']};color:{P['txt_p']};font-family:'Manrope',sans-serif}}
#root{{display:flex;flex-direction:column;height:100%}}
.split{{display:flex;flex:1;overflow:hidden}}
.pane-pdf{{flex:0 0 50%;border-right:2px solid {P['border']};display:flex;flex-direction:column;background:{P['pdf_bg']};min-width:280px}}
.pane-lbl{{font-family:'Manrope',sans-serif;font-size:9px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;padding:5px 14px;background:{P['hdr_bg']};border-bottom:1px solid {P['border']};color:{P['txt_m']};flex-shrink:0;display:flex;align-items:center;gap:8px;min-height:30px}}
#doc-selector{{background:{P['select_bg']};border:1px solid {P['border']};color:{P['txt_p']};font-family:'Manrope',sans-serif;font-size:11px;font-weight:500;padding:3px 8px;border-radius:4px;cursor:pointer;outline:none;flex:1;max-width:340px}}
#doc-selector option{{background:{P['select_bg']};color:{P['txt_p']}}}
#pdf-container{{flex:1;overflow-y:auto;overflow-x:auto;padding:12px;display:flex;flex-direction:column;align-items:center;gap:8px;scrollbar-width:thin;scrollbar-color:{P['border']} transparent}}
#pdf-container::-webkit-scrollbar{{width:5px}}
#pdf-container::-webkit-scrollbar-thumb{{background:{P['border']};border-radius:3px}}
#pdf-container canvas{{box-shadow:0 4px 20px rgba(0,0,0,.35);border-radius:2px;max-width:100%;display:block}}
#pdf-loading{{font-family:'JetBrains Mono',monospace;font-size:11px;color:{P['txt_m']};padding:40px;text-align:center}}
.resizer{{flex:0 0 4px;background:{P['border']};cursor:col-resize;transition:background .15s;z-index:10}}
.resizer:hover,.resizer.active{{background:{P['accent']}}}
.pane-ext{{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:360px}}
.ext-scroll{{flex:1;overflow-y:auto;padding:14px 18px 32px;scrollbar-width:thin;scrollbar-color:{P['border']} transparent;background:{P['body_bg']}}}
.ext-scroll::-webkit-scrollbar{{width:5px}}
.ext-scroll::-webkit-scrollbar-thumb{{background:{P['border']};border-radius:3px}}
.status{{height:22px;background:{P['hdr_bg']};border-top:1px solid {P['border']};display:flex;align-items:center;padding:0 14px;gap:14px;flex-shrink:0}}
.si{{font-family:'JetBrains Mono',monospace;font-size:9px;color:{P['txt_m']};display:flex;align-items:center;gap:4px}}
.dot{{width:5px;height:5px;border-radius:50%}}
</style>
</head>
<body>
<div id="root">
  <div class="split" id="split">
    <div class="pane-pdf" id="pane-pdf">
      <div class="pane-lbl">
        📄
        <select id="doc-selector" onchange="switchDoc(this.value)">
          {options_html}
        </select>
      </div>
      <div id="pdf-container">
        <div id="pdf-loading">⏳ Chargement du PDF…</div>
      </div>
    </div>
    <div class="resizer" id="resizer"></div>
    <div class="pane-ext" id="pane-ext">
      <div class="pane-lbl" id="ext-pane-lbl">🧬 Extraction — {nb_lignes} ligne(s)</div>
      <div class="ext-scroll" id="ext-scroll">{right_html}</div>
    </div>
  </div>
  <div class="status">
    <div class="si"><div class="dot" style="background:{dot_color}"></div><span id="status-ext">{ext_label}</span></div>
    <div class="si">· confiance : <span id="status-conf" style="color:{fg_st};margin-left:3px">{pct_st}</span></div>
    <div class="si"><span id="status-champs">· {nb_champs} champ(s) manquant(s)</span></div>
    <div class="si"><span id="status-warns">· {nb_warns} alerte(s)</span></div>
    <div class="si" id="pdf-status">· chargement PDF…</div>
  </div>
</div>

<script>
pdfjsLib.GlobalWorkerOptions.workerSrc =
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

// ── Hauteur dynamique — API Streamlit Component Protocol ─────────────────
// Le type DOIT être 'streamlit:setFrameHeight' (préfixe requis depuis Streamlit 1.24).
// Séquence : componentReady → Streamlit envoie 'render' → on répond setFrameHeight.
function sendHeight() {{
  try {{
    let h;
    try {{ h = window.parent.innerHeight; }} catch(ex) {{ h = screen.availHeight || 900; }}
    document.getElementById('root').style.height = h + 'px';
    window.parent.postMessage({{
      isStreamlitMessage: true,
      type: 'streamlit:setFrameHeight',
      height: h
    }}, '*');
  }} catch(e) {{}}
}}

// 1) Handshake : signal "composant prêt" vers Streamlit
window.parent.postMessage({{ isStreamlitMessage: true, type: 'streamlit:componentReady', apiVersion: 1 }}, '*');

// 2) Streamlit répond par 'streamlit:render' → on ajuste la hauteur
window.addEventListener('message', function(e) {{
  if (e.data && e.data.isStreamlitMessage && e.data.type === 'streamlit:render') sendHeight();
}});

// 3) Envois proactifs (race-condition guard)
sendHeight();
setTimeout(sendHeight, 150);
setTimeout(sendHeight, 600);
window.addEventListener('resize', sendHeight);

// ── Données et switchDoc ───────────────────────────────────────────────────
const ALL_DOCS = {all_docs_json};

function loadPdf(url) {{
  const container = document.getElementById('pdf-container');
  container.innerHTML = '<div id="pdf-loading">⏳ Chargement du PDF…</div>';
  document.getElementById('pdf-status').textContent = '· chargement PDF…';
  pdfjsLib.getDocument(url).promise
    .then(pdf => {{
      const total = pdf.numPages;
      document.getElementById('pdf-loading').remove();
      document.getElementById('pdf-status').textContent = '· page 0 / ' + total;
      const render = n => {{
        if (n > total) {{ document.getElementById('pdf-status').textContent = '· ' + total + ' page(s)'; return; }}
        pdf.getPage(n).then(page => {{
          const vp = page.getViewport({{scale:1.6}});
          const c  = document.createElement('canvas');
          c.height = vp.height; c.width = vp.width;
          container.appendChild(c);
          page.render({{canvasContext:c.getContext('2d'),viewport:vp}})
            .promise.then(() => {{
              document.getElementById('pdf-status').textContent = '· page ' + n + ' / ' + total;
              render(n + 1);
            }});
        }});
      }};
      render(1);
    }})
    .catch(err => {{
      const ld = document.getElementById('pdf-loading');
      if (ld) ld.remove();
      container.innerHTML = '<div style="color:#f66;padding:20px;font-family:monospace;font-size:12px">❌ ' + err.message + '</div>';
      document.getElementById('pdf-status').textContent = '· erreur PDF';
    }});
}}

function switchDoc(filename) {{
  const doc = ALL_DOCS[filename];
  if (!doc) return;
  document.getElementById('ext-scroll').innerHTML = doc.panel;
  document.getElementById('ext-pane-lbl').textContent = '🧬 Extraction — ' + doc.nb_lignes + ' ligne(s)';
  document.getElementById('status-ext').textContent = doc.ext_label;
  document.getElementById('status-conf').style.color = doc.conf_color;
  document.getElementById('status-conf').textContent = doc.conf_pct;
  document.getElementById('status-champs').textContent = '· ' + doc.nb_champs + ' champ(s) manquant(s)';
  document.getElementById('status-warns').textContent = '· ' + doc.nb_warns + ' alerte(s)';
  loadPdf(doc.url);
}}

// Chargement initial
const initName = {json.dumps(initial_name)};
if (ALL_DOCS[initName]) loadPdf(ALL_DOCS[initName].url);

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

# height=2000 : dépasse tout viewport — les conteneurs parents (100vh+overflow:hidden)
# clippent l'iframe à la hauteur exacte du viewport, sans toucher l'iframe elle-même.
st.components.v1.html(html, height=2000, scrolling=False)
