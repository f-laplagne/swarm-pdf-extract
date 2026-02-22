import streamlit as st


def kpi_card(label: str, value: str, delta: str | None = None,
             delta_color: str = "normal"):
    """Display a single KPI metric (native Streamlit, used inside st.columns)."""
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def kpi_row(metrics: list[dict]):
    """Display KPI cards in a responsive row of native st.metric widgets.

    Each dict accepts: label (str), value (str), delta (str|None),
    delta_color ('normal'|'inverse'|'off').
    """
    if not metrics:
        return
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            st.metric(
                label=m.get("label", ""),
                value=m.get("value", "—"),
                delta=m.get("delta"),
                delta_color=m.get("delta_color", "normal"),
            )
