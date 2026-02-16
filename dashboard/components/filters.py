import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session

from dashboard.data.models import Fournisseur, Document, LigneFacture


def sidebar_filters(session: Session) -> dict:
    """Render common sidebar filters and return selected values."""
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

    # Fournisseur
    fournisseurs = [f[0] for f in session.query(Fournisseur.nom).order_by(Fournisseur.nom).all()]
    selected_fournisseurs = st.sidebar.multiselect("Fournisseur", fournisseurs, default=fournisseurs)

    # Type matiere
    matieres = [m[0] for m in session.query(LigneFacture.type_matiere).distinct().filter(
        LigneFacture.type_matiere.isnot(None)
    ).all()]
    selected_matieres = st.sidebar.multiselect("Type matiere", sorted(matieres), default=sorted(matieres))

    return {
        "date_range": date_range,
        "fournisseurs": selected_fournisseurs,
        "matieres": selected_matieres,
    }
