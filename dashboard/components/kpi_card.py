import streamlit as st


def kpi_card(label: str, value: str, delta: str | None = None, delta_color: str = "normal"):
    """Display a single KPI metric."""
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def kpi_row(metrics: list[dict]):
    """Display a row of KPI cards. Each dict has: label, value, delta (optional)."""
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            kpi_card(
                label=m["label"],
                value=m["value"],
                delta=m.get("delta"),
                delta_color=m.get("delta_color", "normal"),
            )
