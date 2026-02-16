import streamlit as st
import pandas as pd
import io


def data_table(df: pd.DataFrame, title: str | None = None, export: bool = True):
    """Display an interactive data table with optional CSV/Excel export."""
    if title:
        st.subheader(title)

    st.dataframe(df, use_container_width=True)

    if export and not df.empty:
        col1, col2 = st.columns(2)
        with col1:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Export CSV", csv, f"{title or 'data'}.csv", "text/csv")
        with col2:
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False, engine="openpyxl")
            st.download_button("Export Excel", buffer.getvalue(), f"{title or 'data'}.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
