import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture, Fournisseur


def volume_mensuel(session: Session) -> pd.DataFrame:
    rows = (
        session.query(Document.date_document, Document.montant_ht)
        .filter(Document.date_document.isnot(None), Document.montant_ht.isnot(None))
        .all()
    )
    df = pd.DataFrame(rows, columns=["date_document", "montant_total"])
    df["date_document"] = pd.to_datetime(df["date_document"])
    df["mois"] = df["date_document"].dt.to_period("M")
    result = df.groupby("mois").agg(
        montant_total=("montant_total", "sum"),
        nb_documents=("montant_total", "count"),
    ).reset_index()
    result["mois"] = result["mois"].astype(str)
    return result


def evolution_prix_matiere(
    session: Session, type_matiere: str, raw_values: list[str] | None = None,
) -> pd.DataFrame:
    """Price evolution over time for a given material type.

    Parameters
    ----------
    type_matiere:
        The canonical material name.
    raw_values:
        Optional list of raw DB values (from ``expand_canonical()``) to match
        with an ``IN`` clause.  When *None*, an exact ``==`` filter is used.
    """
    query = session.query(
        LigneFacture.date_depart,
        LigneFacture.prix_unitaire,
        LigneFacture.quantite,
    )

    if raw_values is not None:
        query = query.filter(LigneFacture.type_matiere.in_(raw_values))
    else:
        query = query.filter(LigneFacture.type_matiere == type_matiere)

    rows = (
        query
        .filter(
            LigneFacture.date_depart.isnot(None),
            LigneFacture.prix_unitaire.isnot(None),
        )
        .all()
    )
    df = pd.DataFrame(rows, columns=["date_depart", "prix_unitaire", "quantite"])
    df["date_depart"] = pd.to_datetime(df["date_depart"])
    df["mois"] = df["date_depart"].dt.to_period("M")
    result = df.groupby("mois").agg(
        prix_unitaire_moyen=("prix_unitaire", "mean"),
        nb_lignes=("prix_unitaire", "count"),
    ).reset_index()
    result["mois"] = result["mois"].astype(str)
    return result
