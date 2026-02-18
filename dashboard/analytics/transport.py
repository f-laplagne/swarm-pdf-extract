"""Transport analytics — shipment listing for route visualization."""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from dashboard.data.models import Document, LigneFacture, Fournisseur
from dashboard.data.entity_resolution import get_mappings, get_prefix_mappings, resolve_column


def liste_expeditions(session: Session) -> pd.DataFrame:
    """Load all shipments with location data for map visualization.

    Returns a DataFrame with columns:
        id, date_depart, date_arrivee, lieu_depart, lieu_arrivee,
        resolved_lieu_depart, resolved_lieu_arrivee, route,
        type_matiere, prix_total, fournisseur, delai_jours, document_id
    """
    rows = (
        session.query(
            LigneFacture.id,
            LigneFacture.date_depart,
            LigneFacture.date_arrivee,
            LigneFacture.lieu_depart,
            LigneFacture.lieu_arrivee,
            LigneFacture.type_matiere,
            LigneFacture.prix_total,
            LigneFacture.document_id,
        )
        .filter(
            LigneFacture.lieu_depart.isnot(None),
            LigneFacture.lieu_arrivee.isnot(None),
            LigneFacture.supprime != True,
        )
        .all()
    )
    df = pd.DataFrame(rows, columns=[
        "id", "date_depart", "date_arrivee", "lieu_depart", "lieu_arrivee",
        "type_matiere", "prix_total", "document_id",
    ])
    if df.empty:
        return df

    # Entity resolution on locations
    mappings_loc = get_mappings(session, "location")
    prefix_loc = get_prefix_mappings(session, "location")
    resolve_column(df, "lieu_depart", mappings_loc, prefix_loc)
    resolve_column(df, "lieu_arrivee", mappings_loc, prefix_loc)

    df["route"] = df["resolved_lieu_depart"] + " \u2192 " + df["resolved_lieu_arrivee"]

    # Compute delay if both dates present
    df["depart"] = pd.to_datetime(df["date_depart"], errors="coerce")
    df["arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce")
    mask = df["depart"].notna() & df["arrivee"].notna()
    df["delai_jours"] = None
    df.loc[mask, "delai_jours"] = (df.loc[mask, "arrivee"] - df.loc[mask, "depart"]).dt.days

    # Join fournisseur name
    fournisseurs = {
        r.id: r.nom
        for r in session.query(Document.id, Fournisseur.nom)
        .join(Fournisseur, Document.fournisseur_id == Fournisseur.id)
        .all()
    }
    df["fournisseur"] = df["document_id"].map(fournisseurs)

    return df
