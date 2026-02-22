"""
Centralized dark theme for the Rationalize dashboard.

Usage in any page or component:
    from dashboard.styles.theme import inject_theme
    inject_theme()
"""

import streamlit as st

# ── Palette ────────────────────────────────────────────────────────────────
COLORS = {
    "bg_primary":   "#0d0f14",
    "bg_secondary": "#080b11",
    "bg_card":      "#0a0d14",
    "bg_hover":     "#151824",
    "border":       "#1a2035",
    "text_primary": "#c8d0e0",
    "text_secondary": "#7a8599",
    "text_muted":   "#4a5568",
    "accent_blue":  "#4a90d9",
    "accent_green": "#52c77f",
    "accent_orange": "#ff8c42",
    "accent_red":   "#ff4d4d",
    "accent_yellow": "#f0c040",
}

# ── Plotly layout defaults (apply to every figure) ─────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="#0a0d14",
    plot_bgcolor="#0a0d14",
    font=dict(family="Manrope, sans-serif", color="#c8d0e0", size=12),
    title_font=dict(family="'DM Serif Display', Georgia, serif", color="#c8d0e0", size=15),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#1a2035", borderwidth=1),
    xaxis=dict(gridcolor="#1a2035", linecolor="#1a2035", tickcolor="#4a5568"),
    yaxis=dict(gridcolor="#1a2035", linecolor="#1a2035", tickcolor="#4a5568"),
    margin=dict(l=24, r=24, t=44, b=24),
)

# ── Global CSS (injected once per page) ────────────────────────────────────
_GLOBAL_CSS = """
<style>
/* === FONTS === */
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500;600&family=Manrope:wght@300;400;500;600;700&display=swap');

/* === CSS VARIABLES === */
:root {
    --bg-primary:    #0d0f14;
    --bg-secondary:  #080b11;
    --bg-card:       #0a0d14;
    --bg-hover:      #151824;
    --border:        #1a2035;
    --text-primary:  #c8d0e0;
    --text-secondary:#7a8599;
    --text-muted:    #4a5568;
    --accent-blue:   #4a90d9;
    --accent-green:  #52c77f;
    --accent-orange: #ff8c42;
    --accent-red:    #ff4d4d;
    --accent-yellow: #f0c040;
    --font-display:  'DM Serif Display', Georgia, serif;
    --font-mono:     'JetBrains Mono', 'Fira Code', monospace;
    --font-body:     'Manrope', -apple-system, BlinkMacSystemFont, sans-serif;
    --radius:        8px;
    --radius-sm:     4px;
}

/* === BASE === */
html, body, [class*="css"] {
    font-family: var(--font-body) !important;
}

.stApp {
    background: var(--bg-primary) !important;
}

.block-container {
    max-width: 100% !important;
    padding: 1.5rem 2rem 2rem !important;
}

/* === SIDEBAR === */
[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * {
    color: var(--text-primary) !important;
}
[data-testid="stSidebar"] .stMarkdown p {
    color: var(--text-secondary) !important;
    font-size: 0.8rem;
}
[data-testid="stSidebarNav"] {
    padding-top: 0.5rem;
}
[data-testid="stSidebarNav"] a {
    border-radius: var(--radius-sm) !important;
    padding: 0.35rem 0.75rem !important;
    margin: 1px 0 !important;
    transition: background 0.15s ease !important;
}
[data-testid="stSidebarNav"] a:hover {
    background: var(--bg-hover) !important;
}
[data-testid="stSidebarNav"] a[aria-selected="true"] {
    background: rgba(74, 144, 217, 0.15) !important;
    border-left: 2px solid var(--accent-blue) !important;
}

/* === TYPOGRAPHY === */
h1, [data-testid="stMarkdown"] h1 {
    font-family: var(--font-display) !important;
    color: var(--text-primary) !important;
    font-size: clamp(1.4rem, 3vw, 2rem) !important;
    font-weight: 400 !important;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.5rem;
    margin-bottom: 1rem !important;
}
h2, h3 {
    font-family: var(--font-display) !important;
    color: var(--text-primary) !important;
    font-weight: 400 !important;
}
h2 { font-size: clamp(1.1rem, 2.2vw, 1.4rem) !important; }
h3 { font-size: clamp(0.95rem, 1.8vw, 1.15rem) !important; }

p, li, span, label, .stMarkdown {
    color: var(--text-primary) !important;
    font-family: var(--font-body) !important;
    line-height: 1.6;
}

/* === KPI METRICS (native st.metric) === */
[data-testid="metric-container"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1rem 1.25rem !important;
    transition: border-color 0.2s ease;
}
[data-testid="metric-container"]:hover {
    border-color: var(--accent-blue) !important;
}
[data-testid="metric-container"] label {
    color: var(--text-secondary) !important;
    font-family: var(--font-body) !important;
    font-size: 0.7rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    font-weight: 600 !important;
}
[data-testid="stMetricValue"] {
    color: var(--text-primary) !important;
    font-family: var(--font-mono) !important;
    font-size: clamp(1.1rem, 2.5vw, 1.7rem) !important;
    font-weight: 600 !important;
}
[data-testid="stMetricDelta"] {
    font-family: var(--font-body) !important;
    font-size: 0.78rem !important;
}

/* === TABS === */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
    flex-wrap: wrap;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--text-secondary) !important;
    font-family: var(--font-body) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    padding: 0.55rem 1.1rem !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.15s ease, border-color 0.15s ease !important;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {
    color: var(--text-primary) !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: var(--accent-blue) !important;
    border-bottom-color: var(--accent-blue) !important;
}
[data-testid="stTabs"] [data-baseweb="tab-panel"] {
    padding-top: 1rem !important;
}

/* === BUTTONS === */
.stButton > button {
    background: transparent !important;
    border: 1px solid var(--border) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-body) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    border-radius: 6px !important;
    padding: 0.4rem 1.1rem !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover {
    border-color: var(--accent-blue) !important;
    color: var(--accent-blue) !important;
    background: rgba(74, 144, 217, 0.08) !important;
}
.stButton > button[kind="primary"] {
    background: var(--accent-blue) !important;
    border-color: var(--accent-blue) !important;
    color: #fff !important;
}
.stButton > button[kind="primary"]:hover {
    background: #5a9de0 !important;
    color: #fff !important;
}

/* Download buttons */
[data-testid="stDownloadButton"] > button {
    background: transparent !important;
    border: 1px solid var(--border) !important;
    color: var(--text-secondary) !important;
    font-family: var(--font-body) !important;
    font-size: 0.78rem !important;
    border-radius: 6px !important;
    padding: 0.3rem 0.9rem !important;
}
[data-testid="stDownloadButton"] > button:hover {
    border-color: var(--accent-green) !important;
    color: var(--accent-green) !important;
}

/* === INPUTS === */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea > div > div > textarea {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: var(--text-primary) !important;
    font-family: var(--font-body) !important;
    font-size: 0.85rem !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--accent-blue) !important;
    box-shadow: 0 0 0 2px rgba(74, 144, 217, 0.15) !important;
}

/* Selectbox + Multiselect */
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: var(--text-primary) !important;
}
.stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div {
    background: var(--bg-card) !important;
    border-color: var(--border) !important;
}
/* Dropdown menu */
[data-baseweb="popover"] {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
}

/* === DATAFRAMES === */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    overflow: hidden !important;
}
/* Overflow scroll for narrow screens */
[data-testid="stDataFrame"] > div {
    overflow-x: auto !important;
}

/* === EXPANDERS === */
[data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
}
[data-testid="stExpander"] summary {
    color: var(--text-primary) !important;
    font-family: var(--font-body) !important;
    font-size: 0.85rem !important;
}

/* === ALERTS === */
[data-testid="stInfo"] {
    background: rgba(74, 144, 217, 0.08) !important;
    border-left: 3px solid var(--accent-blue) !important;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0 !important;
    color: var(--text-primary) !important;
}
[data-testid="stWarning"] {
    background: rgba(240, 192, 64, 0.08) !important;
    border-left: 3px solid var(--accent-yellow) !important;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0 !important;
}
[data-testid="stError"] {
    background: rgba(255, 77, 77, 0.08) !important;
    border-left: 3px solid var(--accent-red) !important;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0 !important;
}
[data-testid="stSuccess"] {
    background: rgba(82, 199, 127, 0.08) !important;
    border-left: 3px solid var(--accent-green) !important;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0 !important;
}

/* === DIVIDERS === */
hr {
    border: none !important;
    border-top: 1px solid var(--border) !important;
    margin: 1.25rem 0 !important;
}

/* === FILE UPLOADER === */
[data-testid="stFileUploader"] {
    background: var(--bg-card) !important;
    border: 1px dashed var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 0.5rem !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--accent-blue) !important;
}

/* === RADIO === */
[data-testid="stRadio"] label {
    color: var(--text-primary) !important;
    font-size: 0.85rem !important;
}

/* === SCROLLBAR === */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }
* { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }

/* === RESPONSIVE — Columns wrap on tablet/mobile === */
/* Streamlit's column flex container */
@media (max-width: 900px) {
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    /* Each column: at least 2 per row on tablet */
    [data-testid="column"] {
        flex: 1 1 calc(50% - 1rem) !important;
        min-width: 180px !important;
    }
    .block-container {
        padding: 1rem 1.25rem 1.5rem !important;
    }
    h1 {
        font-size: 1.35rem !important;
    }
}

@media (max-width: 600px) {
    /* Single column on mobile */
    [data-testid="column"] {
        flex: 1 1 100% !important;
        min-width: unset !important;
    }
    .block-container {
        padding: 0.75rem 0.9rem 1rem !important;
    }
    h1 { font-size: 1.2rem !important; }
    /* Tabs: allow horizontal scroll */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
    }
}

/* === HIDE STREAMLIT CHROME === */
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent !important; }
</style>
"""


def inject_theme() -> None:
    """Inject the global dark theme CSS into the current Streamlit page.

    Call this once near the top of each page, after st.set_page_config().
    It is idempotent: calling it multiple times has no visual side-effect.
    """
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
