"""
Centralized theme system for the Rationalize dashboard.

Usage in any page:
    from dashboard.styles.theme import inject_theme
    inject_theme()   # injects CSS + renders sidebar toggle

Charts:
    from dashboard.styles.theme import get_plotly_layout
    fig.update_layout(**get_plotly_layout())
"""

import streamlit as st

# ── Session-state key ───────────────────────────────────────────────────────
_KEY = "_rationalize_theme"          # "dark" | "light"


def _current() -> str:
    return st.session_state.get(_KEY, "dark")


# ── Color palettes ──────────────────────────────────────────────────────────
COLORS = {
    "dark": {
        "bg_primary":    "#0d0f14",
        "bg_secondary":  "#080b11",
        "bg_card":       "#0a0d14",
        "bg_hover":      "#151824",
        "border":        "#1a2035",
        "text_primary":  "#c8d0e0",
        "text_secondary":"#7a8599",
        "text_muted":    "#4a5568",
        "accent_blue":   "#4a90d9",
        "accent_green":  "#52c77f",
        "accent_orange": "#ff8c42",
        "accent_red":    "#ff4d4d",
        "accent_yellow": "#f0c040",
    },
    "light": {
        "bg_primary":    "#f2f4f8",
        "bg_secondary":  "#e8ecf2",
        "bg_card":       "#ffffff",
        "bg_hover":      "#eaeef5",
        "border":        "#d0d7e3",
        "text_primary":  "#1a2035",
        "text_secondary":"#4a5568",
        "text_muted":    "#8a97ab",
        "accent_blue":   "#2563eb",
        "accent_green":  "#16a34a",
        "accent_orange": "#ea580c",
        "accent_red":    "#dc2626",
        "accent_yellow": "#d97706",
    },
}

# ── CSS variable blocks (swapped on toggle) ─────────────────────────────────
_VARS = {
    "dark": """
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
    --shadow:        0 2px 8px rgba(0,0,0,0.5);
}""",
    "light": """
:root {
    --bg-primary:    #f2f4f8;
    --bg-secondary:  #e8ecf2;
    --bg-card:       #ffffff;
    --bg-hover:      #eaeef5;
    --border:        #d0d7e3;
    --text-primary:  #1a2035;
    --text-secondary:#4a5568;
    --text-muted:    #8a97ab;
    --accent-blue:   #2563eb;
    --accent-green:  #16a34a;
    --accent-orange: #ea580c;
    --accent-red:    #dc2626;
    --accent-yellow: #d97706;
    --font-display:  'DM Serif Display', Georgia, serif;
    --font-mono:     'JetBrains Mono', 'Fira Code', monospace;
    --font-body:     'Manrope', -apple-system, BlinkMacSystemFont, sans-serif;
    --radius:        8px;
    --radius-sm:     4px;
    --shadow:        0 2px 8px rgba(0,0,0,0.08);
}""",
}

# ── Component styles (theme-agnostic — use CSS vars throughout) ─────────────
_BASE_CSS = """
/* === FONTS === */
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=JetBrains+Mono:wght@400;500;600&family=Manrope:wght@300;400;500;600;700&display=swap');

/* === BASE === */
html, body, [class*="css"] {
    font-family: var(--font-body) !important;
    transition: background 0.25s ease, color 0.25s ease;
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
    transition: background 0.25s ease;
}
[data-testid="stSidebar"] * {
    color: var(--text-primary) !important;
}
[data-testid="stSidebar"] .stMarkdown p {
    color: var(--text-secondary) !important;
    font-size: 0.8rem;
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
    background: rgba(74, 144, 217, 0.12) !important;
    border-left: 2px solid var(--accent-blue) !important;
}

/* === TYPOGRAPHY === */
h1 {
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

/* Masquer les spans internes Streamlit dans les headers d'expanders */
details summary span[class^="_"],
details summary span[class*=" _"] {
    font-size: 0 !important;
    color: transparent !important;
    user-select: none !important;
}

/* === KPI METRICS === */
[data-testid="metric-container"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1rem 1.25rem !important;
    box-shadow: var(--shadow) !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
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

/* === TOGGLE (theme switch) === */
[data-testid="stToggle"] {
    gap: 0.5rem;
}
[data-testid="stToggle"] label {
    font-family: var(--font-body) !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    color: var(--text-secondary) !important;
}
[data-testid="stToggle"] [data-baseweb="toggle"] {
    background-color: var(--border) !important;
    border: none !important;
}
[data-testid="stToggle"] [data-checked="true"] [data-baseweb="toggle"] {
    background-color: var(--accent-blue) !important;
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
    box-shadow: 0 0 0 2px rgba(74,144,217,0.15) !important;
}
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    color: var(--text-primary) !important;
}
[data-baseweb="select"] > div {
    background: var(--bg-card) !important;
    border-color: var(--border) !important;
}
[data-baseweb="popover"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    box-shadow: var(--shadow) !important;
}
[data-baseweb="menu"] {
    background: var(--bg-card) !important;
}
[data-baseweb="menu"] li:hover {
    background: var(--bg-hover) !important;
}

/* === DATAFRAMES === */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    overflow: hidden !important;
    box-shadow: var(--shadow) !important;
}
[data-testid="stDataFrame"] > div {
    overflow-x: auto !important;
}

/* === EXPANDERS === */
[data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    box-shadow: var(--shadow) !important;
}
[data-testid="stExpander"] summary {
    color: var(--text-primary) !important;
    font-family: var(--font-body) !important;
    font-size: 0.85rem !important;
}

/* === ALERTS === */
[data-testid="stInfo"] {
    background: rgba(74,144,217,0.08) !important;
    border-left: 3px solid var(--accent-blue) !important;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0 !important;
}
[data-testid="stWarning"] {
    background: rgba(240,192,64,0.08) !important;
    border-left: 3px solid var(--accent-yellow) !important;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0 !important;
}
[data-testid="stError"] {
    background: rgba(255,77,77,0.08) !important;
    border-left: 3px solid var(--accent-red) !important;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0 !important;
}
[data-testid="stSuccess"] {
    background: rgba(82,199,127,0.08) !important;
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

/* === SCROLLBAR === */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }
* { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }

/* === RESPONSIVE — columns wrap === */
@media (max-width: 900px) {
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
    [data-testid="column"] { flex: 1 1 calc(50% - 1rem) !important; min-width: 180px !important; }
    .block-container { padding: 1rem 1.25rem 1.5rem !important; }
    h1 { font-size: 1.35rem !important; }
}
@media (max-width: 600px) {
    [data-testid="column"] { flex: 1 1 100% !important; min-width: unset !important; }
    .block-container { padding: 0.75rem 0.9rem 1rem !important; }
    h1 { font-size: 1.2rem !important; }
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
    }
}

/* === HIDE STREAMLIT CHROME === */
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent !important; }

/* Hide sidebar collapse-button icon text (Material icon name leaks as plain text) */
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] span,
button[data-testid="baseButton-header"] span {
    font-size: 0 !important;
    color: transparent !important;
}
/* Keep the button itself visible but hide overflowing icon label */
[data-testid="stSidebarCollapsedControl"] {
    overflow: hidden !important;
}
"""


# ── Plotly layouts ──────────────────────────────────────────────────────────
_PLOTLY = {
    "dark": dict(
        paper_bgcolor="#0a0d14",
        plot_bgcolor="#0a0d14",
        font=dict(family="Manrope, sans-serif", color="#c8d0e0", size=12),
        title_font=dict(family="'DM Serif Display', Georgia, serif",
                        color="#c8d0e0", size=15),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#1a2035", borderwidth=1),
        xaxis=dict(gridcolor="#1a2035", linecolor="#1a2035", tickcolor="#4a5568"),
        yaxis=dict(gridcolor="#1a2035", linecolor="#1a2035", tickcolor="#4a5568"),
        margin=dict(l=24, r=24, t=44, b=24),
    ),
    "light": dict(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8fafc",
        font=dict(family="Manrope, sans-serif", color="#1a2035", size=12),
        title_font=dict(family="'DM Serif Display', Georgia, serif",
                        color="#1a2035", size=15),
        legend=dict(bgcolor="rgba(255,255,255,0.8)", bordercolor="#d0d7e3",
                    borderwidth=1),
        xaxis=dict(gridcolor="#e8ecf2", linecolor="#d0d7e3", tickcolor="#8a97ab"),
        yaxis=dict(gridcolor="#e8ecf2", linecolor="#d0d7e3", tickcolor="#8a97ab"),
        margin=dict(l=24, r=24, t=44, b=24),
    ),
}

# Keep backward compat for any code that imported PLOTLY_LAYOUT directly
PLOTLY_LAYOUT = _PLOTLY["dark"]


def get_plotly_layout() -> dict:
    """Return Plotly layout dict for the current theme (call at chart render time)."""
    return _PLOTLY[_current()]


# ── Public API ──────────────────────────────────────────────────────────────
def inject_theme() -> None:
    """Inject CSS theme + render the sidebar dark/light toggle.

    Call once per page after st.set_page_config().
    """
    theme = _current()

    # 1. CSS variables + component styles
    css = f"<style>{_VARS[theme]}{_BASE_CSS}</style>"
    st.markdown(css, unsafe_allow_html=True)

    # 2. Sidebar toggle  ── rendered at top of sidebar on every page
    with st.sidebar:
        is_dark = theme == "dark"
        # Thin separator above toggle
        st.markdown(
            "<div style='border-top:1px solid var(--border);margin:0.5rem 0 0.75rem'></div>",
            unsafe_allow_html=True,
        )
        toggled = st.toggle(
            "🌙  Mode sombre" if is_dark else "☀️  Mode clair",
            value=is_dark,
            key="_theme_toggle_widget",
            help="Basculer entre le thème sombre et le thème clair",
        )
        if toggled != is_dark:
            st.session_state[_KEY] = "dark" if toggled else "light"
            st.rerun()
        st.markdown(
            "<div style='border-bottom:1px solid var(--border);margin:0.75rem 0 0.5rem'></div>",
            unsafe_allow_html=True,
        )
