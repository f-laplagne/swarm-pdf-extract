import io
import streamlit as st
import pandas as pd


def data_table(df: pd.DataFrame, title: str | None = None, export: bool = True):
    """Display an interactive data table with optional CSV/Excel export."""
    if title:
        st.markdown(
            f'<p style="font-family:var(--font-body,Manrope,sans-serif);'
            f'font-size:0.75rem;text-transform:uppercase;letter-spacing:0.06em;'
            f'font-weight:600;color:var(--text-secondary,#7a8599);'
            f'margin:0.75rem 0 0.4rem">{title}</p>',
            unsafe_allow_html=True,
        )

    st.dataframe(df, use_container_width=True)

    if export and not df.empty:
        col1, col2, _spacer = st.columns([1, 1, 4])
        with col1:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇ CSV", csv,
                file_name=f"{title or 'data'}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col2:
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False, engine="openpyxl")
            st.download_button(
                "⬇ Excel", buffer.getvalue(),
                file_name=f"{title or 'data'}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
