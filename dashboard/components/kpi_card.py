import html as _html
import streamlit as st


def kpi_card(label: str, value: str, delta: str | None = None,
             delta_color: str = "normal"):
    """Display a single KPI metric (native Streamlit, used inside st.columns)."""
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def kpi_row(metrics: list[dict]):
    """Display KPI cards in a responsive CSS grid.

    Each dict accepts: label (str), value (str), delta (str|None),
    delta_color ('normal'|'inverse'|'off').
    Cards auto-wrap: ≥150 px each, up to 1 per column on mobile.
    """
    cards_html = ""
    for m in metrics:
        label = _html.escape(str(m.get("label", "")))
        value = _html.escape(str(m.get("value", "—")))
        delta = m.get("delta")

        delta_html = ""
        if delta is not None:
            try:
                raw = float(str(delta).replace("%", "").replace("+", "").strip())
                color = "var(--accent-green)" if raw >= 0 else "var(--accent-red)"
                prefix = "▲" if raw >= 0 else "▼"
            except ValueError:
                color = "var(--text-secondary)"
                prefix = ""
            delta_html = (
                f'<div class="kpi-delta" style="color:{color}">'
                f'{prefix} {_html.escape(str(delta))}</div>'
            )

        cards_html += f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            {delta_html}
        </div>"""

    st.markdown(
        f"""
<style>
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 0.65rem;
    margin-bottom: 0.75rem;
}}
.kpi-card {{
    background: var(--bg-card, #0a0d14);
    border: 1px solid var(--border, #1a2035);
    border-radius: 8px;
    padding: 0.9rem 1.1rem;
    transition: border-color 0.15s ease;
}}
.kpi-card:hover {{
    border-color: var(--accent-blue, #4a90d9);
}}
.kpi-label {{
    font-family: var(--font-body, 'Manrope', sans-serif);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-weight: 600;
    color: var(--text-secondary, #7a8599);
    margin-bottom: 0.35rem;
}}
.kpi-value {{
    font-family: var(--font-mono, 'JetBrains Mono', monospace);
    font-size: clamp(1.05rem, 2.2vw, 1.55rem);
    font-weight: 600;
    color: var(--text-primary, #c8d0e0);
    line-height: 1.2;
    word-break: break-all;
}}
.kpi-delta {{
    font-family: var(--font-body, 'Manrope', sans-serif);
    font-size: 0.73rem;
    margin-top: 0.3rem;
    font-weight: 500;
}}
</style>
<div class="kpi-grid">{cards_html}</div>
""",
        unsafe_allow_html=True,
    )
