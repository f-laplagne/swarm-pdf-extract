import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session

from dashboard.data.models import Document
from dashboard.data.entity_resolution import get_distinct_values


def sidebar_filters(session: Session) -> dict:
    """Render common sidebar filters and return selected (canonical) values."""
    st.sidebar.header("Filtres")

    # Date range
    dates = session.query(Document.date_document).filter(
        Document.date_document.isnot(None)
    ).all()
    if dates:
        date_values = sorted([d[0] for d in dates if d[0]])
        if date_values:
            date_range = st.sidebar.date_input(
                "Periode",
                value=(pd.to_datetime(date_values[0]), pd.to_datetime(date_values[-1])),
            )
        else:
            date_range = None
    else:
        date_range = None

    # Fournisseur — canonical names via entity resolution
    fournisseurs = get_distinct_values(session, "supplier")
    selected_fournisseurs = st.sidebar.multiselect("Fournisseur", fournisseurs, default=fournisseurs)

    # Type matiere — canonical names via entity resolution
    matieres = get_distinct_values(session, "material")
    selected_matieres = st.sidebar.multiselect("Type matiere", matieres, default=matieres)

    return {
        "date_range": date_range,
        "fournisseurs": selected_fournisseurs,
        "matieres": selected_matieres,
    }
