import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str, color: str | None = None, **kwargs):
    fig = px.bar(df, x=x, y=y, title=title, color=color, **kwargs)
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    return fig


def line_chart(df: pd.DataFrame, x: str, y: str, title: str, color: str | None = None, **kwargs):
    fig = px.line(df, x=x, y=y, title=title, color=color, markers=True, **kwargs)
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    return fig


def scatter_chart(df: pd.DataFrame, x: str, y: str, title: str, color: str | None = None, size: str | None = None, **kwargs):
    fig = px.scatter(df, x=x, y=y, title=title, color=color, size=size, **kwargs)
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    return fig


def radar_chart(categories: list[str], values: list[float], title: str):
    fig = go.Figure(data=go.Scatterpolar(
        r=values + [values[0]],  # close the polygon
        theta=categories + [categories[0]],
        fill="toself",
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        title=title,
        margin=dict(l=40, r=40, t=40, b=40),
    )
    return fig


def heatmap(df: pd.DataFrame, title: str):
    fig = px.imshow(df, title=title, text_auto=True, aspect="auto", color_continuous_scale="Blues")
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    return fig
