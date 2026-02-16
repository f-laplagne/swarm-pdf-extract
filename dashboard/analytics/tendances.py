import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture, Fournisseur
from dashboard.data.entity_resolution import get_mappings, get_prefix_mappings, resolve_column


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
    """Price evolution over time for a given material type."""
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


# --- Shipping delay analytics ---


def _lignes_avec_delai(session: Session) -> pd.DataFrame:
    """Load all lines with both date_depart and date_arrivee, compute delay."""
    rows = (
        session.query(
            LigneFacture.date_depart,
            LigneFacture.date_arrivee,
            LigneFacture.lieu_depart,
            LigneFacture.lieu_arrivee,
            LigneFacture.type_matiere,
            LigneFacture.prix_total,
            LigneFacture.document_id,
        )
        .filter(
            LigneFacture.date_depart.isnot(None),
            LigneFacture.date_arrivee.isnot(None),
        )
        .all()
    )
    df = pd.DataFrame(rows, columns=[
        "date_depart", "date_arrivee", "lieu_depart", "lieu_arrivee",
        "type_matiere", "prix_total", "document_id",
    ])
    if df.empty:
        return df

    df["depart"] = pd.to_datetime(df["date_depart"])
    df["arrivee"] = pd.to_datetime(df["date_arrivee"])
    df["delai_jours"] = (df["arrivee"] - df["depart"]).dt.days

    # Entity resolution on locations
    mappings_loc = get_mappings(session, "location")
    prefix_loc = get_prefix_mappings(session, "location")
    if df["lieu_depart"].notna().any():
        resolve_column(df, "lieu_depart", mappings_loc, prefix_loc)
    else:
        df["resolved_lieu_depart"] = df["lieu_depart"]
    if df["lieu_arrivee"].notna().any():
        resolve_column(df, "lieu_arrivee", mappings_loc, prefix_loc)
    else:
        df["resolved_lieu_arrivee"] = df["lieu_arrivee"]

    df["route"] = df["resolved_lieu_depart"] + " \u2192 " + df["resolved_lieu_arrivee"]

    # Join fournisseur name
    fournisseurs = {
        r.id: r.nom
        for r in session.query(Document.id, Fournisseur.nom)
        .join(Fournisseur, Document.fournisseur_id == Fournisseur.id)
        .all()
    }
    df["fournisseur"] = df["document_id"].map(fournisseurs)

    return df[df["delai_jours"] >= 0]


def delai_expedition_stats(session: Session) -> dict:
    """Global KPIs for shipping delays."""
    df = _lignes_avec_delai(session)
    if df.empty:
        return {
            "nb_trajets": 0,
            "delai_moyen": 0.0,
            "delai_median": 0.0,
            "delai_min": 0,
            "delai_max": 0,
        }
    return {
        "nb_trajets": len(df),
        "delai_moyen": round(df["delai_jours"].mean(), 1),
        "delai_median": round(df["delai_jours"].median(), 1),
        "delai_min": int(df["delai_jours"].min()),
        "delai_max": int(df["delai_jours"].max()),
    }


def distribution_delais(session: Session) -> pd.DataFrame:
    """Histogram data: count of shipments per delay bucket."""
    df = _lignes_avec_delai(session)
    if df.empty:
        return pd.DataFrame(columns=["delai_jours", "nb_expeditions"])
    counts = df["delai_jours"].value_counts().sort_index().reset_index()
    counts.columns = ["delai_jours", "nb_expeditions"]
    return counts


def evolution_delai_mensuel(session: Session) -> pd.DataFrame:
    """Monthly average shipping delay trend."""
    df = _lignes_avec_delai(session)
    if df.empty:
        return pd.DataFrame(columns=["mois", "delai_moyen", "delai_median", "nb_expeditions"])
    df["mois"] = df["depart"].dt.to_period("M")
    result = df.groupby("mois").agg(
        delai_moyen=("delai_jours", "mean"),
        delai_median=("delai_jours", "median"),
        nb_expeditions=("delai_jours", "count"),
    ).reset_index()
    result["delai_moyen"] = result["delai_moyen"].round(1)
    result["delai_median"] = result["delai_median"].round(1)
    result["mois"] = result["mois"].astype(str)
    return result


def delai_par_route(session: Session) -> pd.DataFrame:
    """Average delay per route."""
    df = _lignes_avec_delai(session)
    if df.empty:
        return pd.DataFrame(columns=["route", "delai_moyen", "delai_min", "delai_max", "nb_expeditions"])
    result = df.groupby("route").agg(
        delai_moyen=("delai_jours", "mean"),
        delai_min=("delai_jours", "min"),
        delai_max=("delai_jours", "max"),
        nb_expeditions=("delai_jours", "count"),
    ).reset_index().sort_values("nb_expeditions", ascending=False)
    result["delai_moyen"] = result["delai_moyen"].round(1)
    return result


def delai_par_fournisseur(session: Session) -> pd.DataFrame:
    """Average delay per supplier."""
    df = _lignes_avec_delai(session)
    if df.empty:
        return pd.DataFrame(columns=["fournisseur", "delai_moyen", "delai_median", "nb_expeditions"])
    df = df.dropna(subset=["fournisseur"])
    if df.empty:
        return pd.DataFrame(columns=["fournisseur", "delai_moyen", "delai_median", "nb_expeditions"])
    result = df.groupby("fournisseur").agg(
        delai_moyen=("delai_jours", "mean"),
        delai_median=("delai_jours", "median"),
        nb_expeditions=("delai_jours", "count"),
    ).reset_index().sort_values("nb_expeditions", ascending=False)
    result["delai_moyen"] = result["delai_moyen"].round(1)
    result["delai_median"] = result["delai_median"].round(1)
    return result


def detail_expeditions(session: Session) -> pd.DataFrame:
    """Detailed table of all shipments with delay data."""
    df = _lignes_avec_delai(session)
    if df.empty:
        return pd.DataFrame()
    return df[["date_depart", "date_arrivee", "delai_jours", "route",
               "type_matiere", "fournisseur", "prix_total"]].sort_values("date_depart")
