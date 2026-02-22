"""
Page 11 — Vérification PDF
Split-view : PDF original (gauche, rendu PDF.js) ↔ extraction structurée + confiances (droite)

Le mini serveur HTTP (port 8504) est démarré depuis app.py (composition root).
Cette page le réutilise via st.session_state.pdf_server_port, avec fallback autonome.
"""
import os, sys, json, threading, socket, functools
import http.server
from pathlib import Path

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
from dashboard.styles.theme import inject_theme
inject_theme()


SAMPLES_DIR     = Path(_PROJECT_ROOT) / "samples"
EXTRACTIONS_DIR = Path(_PROJECT_ROOT) / "output" / "extractions"
PDF_SERVER_PORT = 8504

# ── Mini serveur HTTP pour les PDFs ─────────────────────────────────────────
# Démarre au niveau module (top-level) : s'exécute à chaque rerun Streamlit
# mais le check _port_free() le rend idempotent — un seul serveur par process.
class _CORSHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()
    def log_message(self, *_):
        pass

def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0

if _port_free(PDF_SERVER_PORT):
    _handler = functools.partial(_CORSHandler, directory=str(SAMPLES_DIR))
    _srv = http.server.HTTPServer(("localhost", PDF_SERVER_PORT), _handler)
    threading.Thread(target=_srv.serve_forever, daemon=True).start()

# ── Données ────────────────────────────────────────────────────────────────────
PDF_FILES = sorted(SAMPLES_DIR.glob("*.pdf"))

def find_extraction(pdf_path: Path) -> Path | None:
    stem = pdf_path.stem.replace(" ", "_").replace("+", "").replace("  ", "_")
    for p in EXTRACTIONS_DIR.glob("*_extraction.json"):
        candidate = p.stem.replace("_extraction", "")
        if candidate == stem or candidate == pdf_path.stem.replace(" ", "_"):
            return p
    first = stem.split("_")[0]
    for p in EXTRACTIONS_DIR.glob(f"{first}*_extraction.json"):
        return p
    return None

# ── Sélection ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;600&family=Manrope:wght@300;400;500;600;700&display=swap');
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1rem 1.5rem 0 !important; max-width: 100% !important; }
.stApp { background: #0d0f14; }
div[data-testid="stSelectbox"] label { display: none; }
div[data-testid="stSelectbox"] > div > div {
    background: #13161e !important;
    border: 1px solid #1e2535 !important;
    color: #c8d0e0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
}
</style>
""", unsafe_allow_html=True)

col_lbl, col_sel, col_info = st.columns([1, 5, 3])
with col_lbl:
    st.markdown(
        "<p style='font-family:Manrope;font-size:11px;font-weight:700;"
        "letter-spacing:.12em;text-transform:uppercase;color:#4a5568;"
        "padding-top:10px;margin:0'>Document</p>",
        unsafe_allow_html=True,
    )
with col_sel:
    selected_pdf = st.selectbox("", PDF_FILES, format_func=lambda p: p.name)

extraction_path = find_extraction(selected_pdf)
extraction      = json.loads(extraction_path.read_text(encoding="utf-8")) if extraction_path else None

# URL du PDF via le mini serveur local
from urllib.parse import quote
pdf_url = f"http://localhost:{PDF_SERVER_PORT}/{quote(selected_pdf.name)}"

# ── Helpers qualité ────────────────────────────────────────────────────────────
CONF_COLORS = {
    "absent":  ("#ff4d4d", "#2a1010"),
    "faible":  ("#ff8c42", "#2a1a0a"),
    "moyen":   ("#f0c040", "#2a220a"),
    "bon":     ("#52c77f", "#0a2018"),
    "parfait": ("#34d399", "#061a12"),
}

def conf_tier(score):
    if score is None or score == 0: return "absent",  "0%"
    if score < 0.5:                  return "faible",  f"{score:.0%}"
    if score < 0.7:                  return "moyen",   f"{score:.0%}"
    if score < 0.9:                  return "bon",     f"{score:.0%}"
    return                                  "parfait", f"{score:.0%}"

def conf_badge(score) -> str:
    tier, pct = conf_tier(score)
    fg, bg = CONF_COLORS[tier]
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {fg}44;'
        f'font-family:JetBrains Mono,monospace;font-size:9px;font-weight:600;'
        f'padding:1px 7px;border-radius:3px;white-space:nowrap">⬤ {pct}</span>'
    )

def val_cell(val) -> str:
    if val is None:
        return '<span style="color:#2d3748;font-style:italic">—</span>'
    if isinstance(val, float):
        return f'<span style="font-family:JetBrains Mono,monospace">{val:,.2f}</span>'
    return str(val)

# ── Panneau droit : extraction ─────────────────────────────────────────────────
def build_extraction_panel(ext: dict) -> str:
    if not ext:
        return "<p style='color:#4a5568;padding:40px;font-family:Manrope'>Extraction introuvable.</p>"

    meta   = ext.get("metadonnees", {})
    fourn  = meta.get("fournisseur", {}) or {}
    client = meta.get("client", {}) or {}
    refs   = meta.get("references", {}) or {}
    lignes = ext.get("lignes", [])
    warns  = ext.get("warnings", [])
    champs = ext.get("champs_manquants", [])
    conf_g = ext.get("confiance_globale", 0)

    tier_g, pct_g = conf_tier(conf_g)
    fg_g, bg_g    = CONF_COLORS[tier_g]

    strategie_labels = {
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
            f'<td style="font-family:Manrope;font-size:10px;font-weight:600;'
            f'letter-spacing:.07em;text-transform:uppercase;color:#3a4258;'
            f'padding:5px 14px 5px 0;white-space:nowrap;vertical-align:top">{label}</td>'
            f'<td style="font-family:Manrope;font-size:12px;color:#c8d0e0;'
            f'padding:5px 0;line-height:1.5">{value}</td>'
            f'</tr>'
        )

    # ── Carte document ──
    meta_card = f"""
    <div style="background:#0a0d14;border:1px solid #1a2035;border-radius:6px;
                padding:16px 20px;margin-bottom:14px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
        <div>
          <div style="font-family:'DM Serif Display',serif;font-size:22px;
                      color:#e2e8f0;letter-spacing:.01em">
            {meta.get('numero_document','—')}
          </div>
          <div style="font-family:Manrope;font-size:10px;color:#3a4258;
                      letter-spacing:.1em;text-transform:uppercase;margin-top:2px">
            {type_labels.get(ext.get('type_document',''), ext.get('type_document',''))}
            &nbsp;·&nbsp; {meta.get('date_document','—')}
            &nbsp;·&nbsp; {strategie_labels.get(ext.get('strategie_utilisee',''), ext.get('strategie_utilisee',''))}
          </div>
        </div>
        <div style="background:{bg_g};border:1px solid {fg_g}44;border-radius:5px;
                    padding:8px 14px;text-align:center;flex-shrink:0;margin-left:16px">
          <div style="font-family:'JetBrains Mono',monospace;font-size:22px;
                      font-weight:700;color:{fg_g};line-height:1">{pct_g}</div>
          <div style="font-family:Manrope;font-size:8px;color:{fg_g}99;
                      letter-spacing:.1em;text-transform:uppercase;margin-top:3px">confiance</div>
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
          {mrow("HT", f"{meta.get('montant_ht'):,.2f} {meta.get('devise','EUR')}" if meta.get('montant_ht') else None)}
          {mrow("TTC", f"{meta.get('montant_ttc'):,.2f} {meta.get('devise','EUR')}" if meta.get('montant_ttc') else None)}
          {mrow("Paiement", meta.get("conditions_paiement"))}
          {mrow("Champs ∅", ", ".join(champs) if champs else None)}
        </table>
      </div>
    </div>"""

    # ── Légende ──
    legend = '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;' \
             'margin-bottom:12px;padding:8px 12px;background:#0a0d14;' \
             'border:1px solid #1a2035;border-radius:4px">' \
             '<span style="font-family:Manrope;font-size:9px;font-weight:700;' \
             'color:#2d3748;letter-spacing:.1em;text-transform:uppercase;' \
             'margin-right:4px">Confiance :</span>'
    for label, tier in [("0%", "absent"), ("<50%", "faible"),
                         ("50-70%", "moyen"), ("70-90%", "bon"), (">90%", "parfait")]:
        fg, bg = CONF_COLORS[tier]
        legend += (f'<span style="background:{bg};color:{fg};border:1px solid {fg}33;'
                   f'font-family:Manrope;font-size:9px;padding:2px 8px;border-radius:3px">'
                   f'⬤ {label}</span>')
    legend += "</div>"

    # ── Tableau lignes ──
    col_defs = [
        ("#",          "36px",  "center"),
        ("Matière / Pièce", "auto", "left"),
        ("Unité",      "52px",  "center"),
        ("Quantité",   "76px",  "right"),
        ("Prix unit.", "80px",  "right"),
        ("Total €",    "80px",  "right"),
        ("Date dép.",  "88px",  "center"),
        ("Date arr.",  "88px",  "center"),
        ("Départ",     "110px", "left"),
        ("Arrivée",    "110px", "left"),
    ]
    conf_fields = [
        ("type_matiere", "Matière"), ("unite", "Unité"),
        ("quantite", "Qté"),         ("prix_unitaire", "PU"),
        ("prix_total", "Total"),      ("date_depart", "D.dép"),
        ("date_arrivee", "D.arr"),    ("lieu_depart", "Départ"),
        ("lieu_arrivee", "Arrivée"),
    ]

    th = ("font-family:Manrope;font-size:9px;font-weight:700;letter-spacing:.1em;"
          "text-transform:uppercase;color:#2d3748;padding:8px 10px;"
          "border-bottom:2px solid #1a2035;white-space:nowrap;")
    headers = "".join(
        f'<th style="{th}text-align:{a};width:{w}">{n}</th>'
        for n, w, a in col_defs
    )

    rows = ""
    for i, ligne in enumerate(lignes):
        conf = ligne.get("confiance", {})
        bg   = "#0a0c12" if i % 2 == 0 else "#0d0f17"
        pu, qt, pt = ligne.get("prix_unitaire"), ligne.get("quantite"), ligne.get("prix_total")
        if pu and qt and pt:
            ecart = abs(round(pu * qt, 2) - pt)
            total_c = "#ff6b6b" if ecart > 0.02 else "#c8d0e0"
        else:
            total_c = "#3a4258"
        td = f'style="padding:7px 10px;border-bottom:1px solid #111520;vertical-align:middle;background:{bg};'
        rows += f"""
        <tr>
          <td {td}text-align:center;color:#2d3748;font-family:'JetBrains Mono',monospace;font-size:11px">{ligne.get('ligne_numero','')}</td>
          <td {td}color:#c8d0e0;font-family:Manrope;font-size:12px">{val_cell(ligne.get('type_matiere'))}</td>
          <td {td}text-align:center;font-family:'JetBrains Mono',monospace;font-size:11px;color:#7b8ca8">{val_cell(ligne.get('unite'))}</td>
          <td {td}text-align:right;font-family:'JetBrains Mono',monospace;font-size:11px;color:#c8d0e0">{val_cell(ligne.get('quantite'))}</td>
          <td {td}text-align:right;font-family:'JetBrains Mono',monospace;font-size:11px;color:#c8d0e0">{val_cell(ligne.get('prix_unitaire'))}</td>
          <td {td}text-align:right;font-family:'JetBrains Mono',monospace;font-size:11px;color:{total_c}">{val_cell(ligne.get('prix_total'))}</td>
          <td {td}text-align:center;font-family:'JetBrains Mono',monospace;font-size:10px;color:#4a5568">{val_cell(ligne.get('date_depart'))}</td>
          <td {td}text-align:center;font-family:'JetBrains Mono',monospace;font-size:10px;color:#4a5568">{val_cell(ligne.get('date_arrivee'))}</td>
          <td {td}color:#7b8ca8;font-family:Manrope;font-size:11px">{val_cell(ligne.get('lieu_depart'))}</td>
          <td {td}color:#7b8ca8;font-family:Manrope;font-size:11px">{val_cell(ligne.get('lieu_arrivee'))}</td>
        </tr>
        <tr>
          <td colspan="10" style="padding:3px 10px 9px;background:{bg};border-bottom:1px solid #131825">
            <div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">
              <span style="font-family:Manrope;font-size:9px;color:#2d3748;
                           font-weight:600;letter-spacing:.07em;text-transform:uppercase;
                           margin-right:3px">conf.</span>
              {"".join(
                  f'<span style="display:inline-flex;align-items:center;gap:3px">'
                  f'<span style="font-family:Manrope;font-size:9px;color:#2d3748">{label}</span>'
                  f'{conf_badge(conf.get(key))}</span>'
                  for key, label in conf_fields
              )}
            </div>
          </td>
        </tr>"""

    table = f"""
    <div style="overflow-x:auto;border:1px solid #1a2035;border-radius:6px;margin-bottom:14px">
      <table style="border-collapse:collapse;width:100%;min-width:880px">
        <thead><tr style="background:#080b11">{headers}</tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""

    # ── Alertes ──
    alerts_html = ""
    if warns or champs:
        champ_li = "".join(
            f'<li style="font-family:JetBrains Mono,monospace;font-size:10px;'
            f'color:#ff4d4d;margin-bottom:3px">{c}</li>' for c in champs)
        warn_li = "".join(
            f'<li style="font-family:Manrope;font-size:11px;color:#ff8c42;'
            f'margin-bottom:5px;line-height:1.5">{w}</li>' for w in warns)
        alerts_html = f"""
        <div style="border:1px solid #3a1a0a;border-left:3px solid #ff8c42;
                    border-radius:4px;padding:12px 16px;margin-bottom:12px;background:#0d0f14">
          <div style="font-family:Manrope;font-size:9px;font-weight:700;color:#ff8c42;
                      letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px">
            ⚠ Alertes & Champs manquants
          </div>
          {"<ul style='margin:0;padding-left:14px;margin-bottom:8px'>" + champ_li + "</ul>" if champs else ""}
          {"<ul style='margin:0;padding-left:14px'>" + warn_li + "</ul>" if warns else ""}
        </div>"""

    # ── Notes ──
    notes = ext.get("extraction_notes", "")
    notes_html = ""
    if notes:
        notes_html = f"""
        <div style="border:1px solid #1a2035;border-radius:4px;padding:12px 16px;
                    background:#0a0c12">
          <div style="font-family:Manrope;font-size:9px;font-weight:700;color:#2d3748;
                      letter-spacing:.12em;text-transform:uppercase;margin-bottom:7px">
            Notes d'extraction
          </div>
          <p style="font-family:Manrope;font-size:11px;color:#4a5568;
                    line-height:1.7;margin:0">{notes}</p>
        </div>"""

    return meta_card + legend + table + alerts_html + notes_html


right_html = build_extraction_panel(extraction)
nb_lignes  = len(extraction.get("lignes", [])) if extraction else 0
conf_g     = extraction.get("confiance_globale", 0) if extraction else 0
tier_status, pct_status = conf_tier(conf_g)
fg_status, _ = CONF_COLORS[tier_status]

# ── HTML complet ───────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;600&family=Manrope:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d0f14;color:#c8d0e0;font-family:'Manrope',sans-serif;
      height:100vh;overflow:hidden;display:flex;flex-direction:column}}

/* Header */
.hdr{{height:42px;background:#080b11;border-bottom:1px solid #1a2035;
      display:flex;align-items:center;padding:0 18px;gap:12px;flex-shrink:0}}
.hdr-title{{font-family:'DM Serif Display',serif;font-size:15px;color:#e2e8f0}}
.hdr-sep{{width:1px;height:18px;background:#1a2035}}
.hdr-file{{font-family:'JetBrains Mono',monospace;font-size:11px;color:#4a90d9;
           background:#0d1828;padding:3px 10px;border-radius:3px;border:1px solid #1a3a5c}}

/* Split */
.split{{display:flex;flex:1;overflow:hidden}}

/* PDF pane */
.pane-pdf{{flex:0 0 50%;border-right:2px solid #1a2035;display:flex;
           flex-direction:column;background:#1a1a1a;min-width:280px}}
.pane-lbl{{font-family:Manrope;font-size:9px;font-weight:700;letter-spacing:.15em;
           text-transform:uppercase;padding:7px 14px;background:#080b11;
           border-bottom:1px solid #1a2035;color:#2d3748;flex-shrink:0}}

/* PDF.js canvas container */
#pdf-container{{flex:1;overflow-y:auto;overflow-x:auto;padding:12px;
                display:flex;flex-direction:column;align-items:center;gap:8px;
                scrollbar-width:thin;scrollbar-color:#1a2035 transparent}}
#pdf-container::-webkit-scrollbar{{width:5px}}
#pdf-container::-webkit-scrollbar-thumb{{background:#1a2035;border-radius:3px}}
#pdf-container canvas{{box-shadow:0 4px 24px #00000088;border-radius:2px;
                        max-width:100%;display:block}}
#pdf-loading{{font-family:'JetBrains Mono',monospace;font-size:11px;color:#2d3748;
              padding:40px;text-align:center}}
#pdf-error{{font-family:Manrope;font-size:12px;color:#ff4d4d;padding:20px;text-align:center}}

/* Resizer */
.resizer{{flex:0 0 4px;background:#1a2035;cursor:col-resize;transition:background .15s;z-index:10}}
.resizer:hover,.resizer.active{{background:#4a90d9}}

/* Extraction pane */
.pane-ext{{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:360px}}
.ext-scroll{{flex:1;overflow-y:auto;padding:14px 18px 32px;
             scrollbar-width:thin;scrollbar-color:#1a2035 transparent}}
.ext-scroll::-webkit-scrollbar{{width:5px}}
.ext-scroll::-webkit-scrollbar-thumb{{background:#1a2035;border-radius:3px}}

/* Status bar */
.status{{height:22px;background:#080b11;border-top:1px solid #1a2035;
         display:flex;align-items:center;padding:0 14px;gap:14px;flex-shrink:0}}
.si{{font-family:'JetBrains Mono',monospace;font-size:9px;color:#2d3748;
     display:flex;align-items:center;gap:4px}}
.dot{{width:5px;height:5px;border-radius:50%}}
</style>
</head>
<body>

<div class="hdr">
  <span class="hdr-title">🔍 Vérification PDF</span>
  <div class="hdr-sep"></div>
  <span class="hdr-file">{selected_pdf.name}</span>
</div>

<div class="split" id="split">

  <!-- PDF -->
  <div class="pane-pdf" id="pane-pdf">
    <div class="pane-lbl">📄 Document original</div>
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
  <div class="si">
    <div class="dot" style="background:{'#52c77f' if extraction else '#ff4d4d'}"></div>
    {'extraction OK' if extraction else 'extraction introuvable'}
  </div>
  <div class="si">· confiance globale : <span style="color:{fg_status}">{pct_status}</span></div>
  <div class="si">· {len(extraction.get('champs_manquants',[])) if extraction else 0} champ(s) manquant(s)</div>
  <div class="si">· {len(extraction.get('warnings',[])) if extraction else 0} alerte(s)</div>
  <div class="si" id="pdf-status">· chargement PDF…</div>
</div>

<script>
// ── PDF.js ──────────────────────────────────────────────────────────────────
pdfjsLib.GlobalWorkerOptions.workerSrc =
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

const PDF_URL    = "{pdf_url}";
const container  = document.getElementById('pdf-container');
const statusEl   = document.getElementById('pdf-status');
let totalPages   = 0;

pdfjsLib.getDocument(PDF_URL).promise
  .then(pdf => {{
    totalPages = pdf.numPages;
    document.getElementById('pdf-loading').remove();
    statusEl.textContent = '· page 0 / ' + totalPages;

    // Render pages sequentially (less memory than concurrent)
    const renderPage = (n) => {{
      if (n > totalPages) {{
        statusEl.textContent = '· ' + totalPages + ' page(s) rendues';
        return;
      }}
      pdf.getPage(n).then(page => {{
        const vp     = page.getViewport({{ scale: 1.6 }});
        const canvas = document.createElement('canvas');
        canvas.height = vp.height;
        canvas.width  = vp.width;
        container.appendChild(canvas);
        page.render({{ canvasContext: canvas.getContext('2d'), viewport: vp }})
            .promise.then(() => {{
              statusEl.textContent = '· page ' + n + ' / ' + totalPages;
              renderPage(n + 1);
            }});
      }});
    }};
    renderPage(1);
  }})
  .catch(err => {{
    document.getElementById('pdf-loading').remove();
    container.innerHTML =
      '<div id="pdf-error">❌ Impossible de charger le PDF.<br>'
      + '<small style="color:#3a4258">' + err.message + '</small></div>';
    statusEl.textContent = '· erreur PDF';
  }});

// ── Resize ──────────────────────────────────────────────────────────────────
const resizer = document.getElementById('resizer');
const pdfPane = document.getElementById('pane-pdf');
const split   = document.getElementById('split');
let dragging = false, startX = 0, startW = 0;

resizer.addEventListener('mousedown', e => {{
  dragging = true; startX = e.clientX;
  startW   = pdfPane.getBoundingClientRect().width;
  resizer.classList.add('active');
  document.body.style.cursor      = 'col-resize';
  document.body.style.userSelect  = 'none';
}});
window.addEventListener('mousemove', e => {{
  if (!dragging) return;
  const total = split.getBoundingClientRect().width;
  const newW  = Math.min(Math.max(startW + (e.clientX - startX), 280), total - 360);
  pdfPane.style.flex = '0 0 ' + newW + 'px';
}});
window.addEventListener('mouseup', () => {{
  dragging = false;
  resizer.classList.remove('active');
  document.body.style.cursor = document.body.style.userSelect = '';
}});
</script>
</body>
</html>"""

st.components.v1.html(html, height=870, scrolling=False)
