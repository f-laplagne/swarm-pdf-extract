"""
Page 11 — Vérification PDF
Architecture définitive :
- CSS pour masquer le header Streamlit (Deploy button)
- UNE seule st.components.v1.html() avec le split-view complet
- Sélecteur de document : <select> HTML natif DANS l'iframe (pure JS, 0 rerun)
- Hauteur dynamique via window.parent.postMessage setFrameHeight (0 rerun, 0 conflit CSS)
"""
import os, sys, json
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
from dashboard.pages.verification_pdf_panel import build_extraction_panel, conf_tier, conf_badge
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

# ── Chemins ──────────────────────────────────────────────────────────────────
SAMPLES_DIR     = Path(_PROJECT_ROOT) / "samples"
EXTRACTIONS_DIR = Path(_PROJECT_ROOT) / "output" / "extractions"
PDF_SERVER_PORT = 8504
# Le serveur HTTP (port 8504) est démarré une seule fois dans app.py (composition root).
# Il gère GET (PDFs), OPTIONS (CORS preflight) et POST /corrections.

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


# ── Construction de tous les panneaux ────────────────────────────────────────
P  = _pal()
cc = _conf_colors()

from dashboard.pages._verification_helpers import get_ligne_ids, get_ligne_data
from dashboard.pages._pdf_server_startup import ensure_started as _ensure_pdf_server

# ── Fallback : si app.py n'a pas encore tourné dans cette session ─────────────
# (l'utilisateur a ouvert directement la page 11 sans passer par l'accueil)
_engine_for_render = st.session_state.get("engine")

if _engine_for_render is None:
    import yaml as _yaml
    from dashboard.data.db import get_engine as _get_engine, init_db as _init_db
    _cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(_cfg_path) as _f:
        _engine_for_render = _get_engine(_yaml.safe_load(_f)["database"]["url"])
    _init_db(_engine_for_render)
    st.session_state.engine = _engine_for_render
    st.session_state.pdf_server_port = PDF_SERVER_PORT

# Démarre le serveur HTTP 8504 s'il n'est pas encore actif
_ensure_pdf_server(_engine_for_render, SAMPLES_DIR, PDF_SERVER_PORT)

all_docs: dict = {}

for pdf_path in PDF_FILES:
    ext_path = find_extraction(pdf_path)
    ext      = json.loads(ext_path.read_text(encoding="utf-8")) if ext_path else None

    # Load DB data (corrected values + IDs) for lines that exist in DB
    _ligne_data = get_ligne_data(_engine_for_render, pdf_path.name) if ext else {}
    _ligne_ids  = {num: row["id"] for num, row in _ligne_data.items()}  # backward compat

    nb_l  = len(ext.get("lignes", [])) if ext else 0
    conf  = ext.get("confiance_globale", 0) if ext else 0
    tier, pct = conf_tier(conf)
    fg, _ = cc[tier]
    all_docs[pdf_path.name] = {
        "url":        f"http://localhost:{PDF_SERVER_PORT}/{quote(pdf_path.name)}",
        "panel":      build_extraction_panel(ext, P, cc, ligne_ids=_ligne_ids, ligne_data=_ligne_data),
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
/* ── Editable cells ─────────────────────────────────────── */
.cell-editable {{
  position: relative;
  cursor: pointer;
  border-bottom: 2px dashed #ff8c42 !important;
}}
.cell-editable::after {{
  content: '✏';
  font-size: 9px;
  opacity: 0;
  position: absolute;
  top: 4px; right: 4px;
  transition: opacity .15s;
  pointer-events: none;
}}
.cell-editable:hover::after {{ opacity: .6; }}
.cell-editable.editing {{
  border-bottom: 2px solid #ff8c42 !important;
  background: rgba(255,140,66,.07) !important;
}}
.cell-editable.saved {{
  border-bottom: 2px solid #52c77f !important;
}}
.cell-editable.error {{
  border-bottom: 2px solid #ff4d4d !important;
}}
.cell-input {{
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1px solid #ff8c42;
  color: inherit;
  font-family: inherit;
  font-size: inherit;
  outline: none;
  padding: 0;
}}
.save-spinner {{
  font-size: 10px;
  color: #ff8c42;
  margin-left: 4px;
}}
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
// ── PDF.js init — guard: if CDN fails to load, corrections still work ─────
let _pdfJsReady = false;
try {{
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  _pdfJsReady = true;
}} catch(e) {{
  const ld = document.getElementById('pdf-loading');
  if (ld) ld.textContent = '⚠ Visionneur PDF indisponible (CDN inaccessible). Les corrections restent actives.';
  const st = document.getElementById('pdf-status');
  if (st) st.textContent = '· PDF.js indisponible';
}}

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
  if (!_pdfJsReady) {{
    container.innerHTML = '<div id="pdf-loading" style="color:#f90;padding:20px;font-size:12px">⚠ Visionneur PDF indisponible — corrigez les données à droite normalement.</div>';
    return;
  }}
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

// ── Inline cell editing (conf < 50%) ─────────────────────────────────────────
const CORRECTION_URL = 'http://localhost:{PDF_SERVER_PORT}/corrections';

function showError(cell, msg) {{
  cell.classList.remove('editing');
  cell.classList.add('error');
  const tt = document.createElement('div');
  tt.style.cssText = 'position:absolute;bottom:100%;left:0;background:#ff4d4d;color:#fff;'
    + 'font-family:Manrope,sans-serif;font-size:10px;padding:3px 8px;border-radius:3px;'
    + 'white-space:nowrap;z-index:100;pointer-events:none';
  tt.textContent = '⚠ ' + msg;
  cell.style.position = 'relative';
  cell.appendChild(tt);
  setTimeout(() => {{ tt.remove(); cell.classList.remove('error'); }}, 3500);
}}

function updateConfBadge(ligneId, champ) {{
  // Replace the confidence badge for this field with a "✓ corrigé" badge
  document.querySelectorAll('.conf-badge-container').forEach(container => {{
    if (container.dataset.ligneId == ligneId && container.dataset.champ === champ) {{
      const badge = container.querySelector('span:last-child');
      if (badge) {{
        badge.style.cssText = 'background:#0a2018;color:#52c77f;border:1px solid #52c77f55;'
          + 'font-family:JetBrains Mono,monospace;font-size:9px;font-weight:600;'
          + 'padding:1px 7px;border-radius:3px;white-space:nowrap';
        badge.textContent = '✓ corrigé';
      }}
    }}
  }});
}}

async function saveCorrection(cell, ligneId, champ, valeurOriginale, confOriginale, newValue) {{
  const display = cell.querySelector('.cell-display');
  const input   = cell.querySelector('.cell-input');

  // Show spinner
  const spinner = document.createElement('span');
  spinner.className = 'save-spinner';
  spinner.textContent = '⏳';
  cell.appendChild(spinner);
  input.disabled = true;

  try {{
    const resp = await fetch(CORRECTION_URL, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        ligne_id: parseInt(ligneId),
        champ: champ,
        valeur_originale: valeurOriginale,
        valeur_corrigee: newValue,
        confiance_originale: parseFloat(confOriginale) || null,
      }}),
    }});
    const data = await resp.json();

    if (data.success) {{
      // Update DOM: show new value, keep cell-editable so it can be re-edited
      display.textContent = newValue || '—';
      display.style.display = '';
      input.style.display = 'none';
      input.disabled = false;
      cell.classList.remove('editing');
      cell.classList.add('saved');       // green border = saved indicator
      cell.dataset.original = newValue; // update baseline for next edit
      updateConfBadge(ligneId, champ);
    }} else {{
      // Revert
      input.value = valeurOriginale;
      input.disabled = false;
      display.style.display = '';
      input.style.display = 'none';
      cell.classList.remove('editing');
      showError(cell, data.error || 'Erreur inconnue');
    }}
  }} catch (err) {{
    input.value = valeurOriginale;
    input.disabled = false;
    display.style.display = '';
    input.style.display = 'none';
    cell.classList.remove('editing');
    showError(cell, 'Réseau : ' + err.message);
  }} finally {{
    spinner.remove();
  }}
}}

// Event delegation: handle clicks on editable cells
document.getElementById('ext-scroll').addEventListener('click', function(e) {{
  const cell = e.target.closest('.cell-editable');
  if (!cell) return;

  const display  = cell.querySelector('.cell-display');
  const input    = cell.querySelector('.cell-input');
  if (!display || !input) return;

  // Switch to edit mode
  display.style.display = 'none';
  input.style.display   = '';
  input.value = cell.dataset.original || '';
  cell.classList.add('editing');
  const FLOAT_FIELDS_JS = new Set(['prix_unitaire', 'quantite', 'prix_total']);
  const DATE_FIELDS_JS  = new Set(['date_depart', 'date_arrivee']);

  input.focus();
  input.select();

  // Auto-format date fields: user types digits only → YYYY-MM-DD inserted automatically
  if (DATE_FIELDS_JS.has(cell.dataset.champ)) {{
    input.addEventListener('input', function() {{
      const oldVal = input.value;
      const cursorPos = input.selectionStart;
      // Count how many digits are before the cursor in the current (unformatted) value
      const digitsBeforeCursor = oldVal.slice(0, cursorPos).replace(/[^0-9]/g, '').length;
      // Build formatted string from digits only
      const raw = oldVal.replace(/[^0-9]/g, '').slice(0, 8);
      let fmt = raw;
      if (raw.length > 6) fmt = raw.slice(0,4) + '-' + raw.slice(4,6) + '-' + raw.slice(6);
      else if (raw.length > 4) fmt = raw.slice(0,4) + '-' + raw.slice(4);
      if (oldVal !== fmt) {{
        input.value = fmt;
        // Restore cursor: find position in formatted string with same number of digits before it
        let digitCount = 0, newPos = fmt.length;
        for (let i = 0; i < fmt.length; i++) {{
          if (digitCount >= digitsBeforeCursor) {{ newPos = i; break; }}
          if (fmt[i] !== '-') digitCount++;
        }}
        input.setSelectionRange(newPos, newPos);
      }}
    }});
  }}

  function parseDate(s) {{
    // Returns Date or null
    const m = /^([0-9]{{4}})-([0-9]{{2}})-([0-9]{{2}})$/.exec(s);
    if (!m) return null;
    const d = new Date(Date.UTC(+m[1], +m[2]-1, +m[3]));
    // re-check for invalid calendar dates (e.g. 2024-02-30)
    return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2]-1 && d.getUTCDate() === +m[3] ? d : null;
  }}

  function findSiblingDate(champ) {{
    // Find the other date cell in the same table row (2 rows above for the conf-badge row)
    let row = cell.parentElement;
    // cell is a <td> inside a <tr>
    const tds = row.querySelectorAll('td[data-champ]');
    for (const td of tds) {{
      if (td.dataset.champ === champ) return td.dataset.original || null;
    }}
    return null;
  }}

  function commitEdit() {{
    const newVal   = input.value.trim();
    const origVal  = cell.dataset.original || '';
    const champ    = cell.dataset.champ;
    display.style.display = '';
    input.style.display   = 'none';
    cell.classList.remove('editing');

    if (newVal === origVal || newVal === '') return; // no change

    // Client-side type validation (mirrors server-side rules for instant feedback)
    if (FLOAT_FIELDS_JS.has(champ)) {{
      if (isNaN(parseFloat(newVal)) || !isFinite(newVal)) {{
        showError(cell, 'Valeur numérique attendue (ex: 42.50)');
        return;
      }}
    }}

    if (DATE_FIELDS_JS.has(champ)) {{
      const d = parseDate(newVal);
      if (!d) {{
        showError(cell, 'Format de date invalide — attendu AAAA-MM-JJ');
        return;
      }}
      if (champ === 'date_arrivee') {{
        const depStr = findSiblingDate('date_depart');
        if (depStr) {{
          const dep = parseDate(depStr);
          if (dep && d < dep) {{
            showError(cell, 'Date d\\'arrivée antérieure au départ (' + depStr + ')');
            return;
          }}
        }}
      }}
      if (champ === 'date_depart') {{
        const arrStr = findSiblingDate('date_arrivee');
        if (arrStr) {{
          const arr = parseDate(arrStr);
          if (arr && d > arr) {{
            showError(cell, 'Date de départ après la date d\\'arrivée (' + arrStr + ')');
            return;
          }}
        }}
      }}
    }}

    saveCorrection(
      cell,
      cell.dataset.ligneId,
      champ,
      origVal,
      cell.dataset.conf,
      newVal,
    );
  }}

  function cancelEdit() {{
    input.value = cell.dataset.original || '';
    display.style.display = '';
    input.style.display   = 'none';
    cell.classList.remove('editing');
  }}

  input.addEventListener('blur', commitEdit, {{ once: true }});
  function onKeydown(ke) {{
    if (ke.key === 'Enter')  {{ ke.preventDefault(); input.removeEventListener('keydown', onKeydown); input.blur(); }}
    if (ke.key === 'Escape') {{ ke.preventDefault(); input.removeEventListener('keydown', onKeydown); input.removeEventListener('blur', commitEdit); cancelEdit(); }}
  }}
  input.addEventListener('keydown', onKeydown);
}});
</script>
</body>
</html>"""

# height=2000 : dépasse tout viewport — les conteneurs parents (100vh+overflow:hidden)
# clippent l'iframe à la hauteur exacte du viewport, sans toucher l'iframe elle-même.
st.components.v1.html(html, height=2000, scrolling=False)
