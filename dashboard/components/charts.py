import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from dashboard.styles.theme import PLOTLY_LAYOUT

# Discrete color sequence that reads well on dark backgrounds
_COLORS = [
    "#4a90d9", "#52c77f", "#ff8c42", "#f0c040",
    "#c97dd4", "#38bdf8", "#fb7185", "#a3e635",
]


def _apply_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_LAYOUT)
    return fig


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str,
              color: str | None = None, **kwargs) -> go.Figure:
    fig = px.bar(df, x=x, y=y, title=title, color=color,
                 color_discrete_sequence=_COLORS, **kwargs)
    return _apply_theme(fig)


def line_chart(df: pd.DataFrame, x: str, y: str, title: str,
               color: str | None = None, **kwargs) -> go.Figure:
    fig = px.line(df, x=x, y=y, title=title, color=color, markers=True,
                  color_discrete_sequence=_COLORS, **kwargs)
    return _apply_theme(fig)


def scatter_chart(df: pd.DataFrame, x: str, y: str, title: str,
                  color: str | None = None, size: str | None = None,
                  **kwargs) -> go.Figure:
    fig = px.scatter(df, x=x, y=y, title=title, color=color, size=size,
                     color_discrete_sequence=_COLORS, **kwargs)
    return _apply_theme(fig)


def radar_chart(categories: list[str], values: list[float],
                title: str) -> go.Figure:
    fig = go.Figure(data=go.Scatterpolar(
        r=values + [values[0]],
        theta=categories + [categories[0]],
        fill="toself",
        line=dict(color="#4a90d9"),
        fillcolor="rgba(74,144,217,0.15)",
    ))
    fig.update_layout(
        polar=dict(
            bgcolor="#0a0d14",
            radialaxis=dict(visible=True, range=[0, 1], gridcolor="#1a2035",
                            linecolor="#1a2035", tickcolor="#4a5568"),
            angularaxis=dict(gridcolor="#1a2035", linecolor="#1a2035"),
        ),
        title=title,
        **PLOTLY_LAYOUT,
    )
    return fig


def heatmap(df: pd.DataFrame, title: str) -> go.Figure:
    fig = px.imshow(df, title=title, text_auto=True, aspect="auto",
                    color_continuous_scale=[[0, "#0a0d14"], [0.5, "#1e3a5f"],
                                            [1, "#4a90d9"]])
    return _apply_theme(fig)
