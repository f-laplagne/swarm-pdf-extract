"""Dashboard purchasing analytics -- facade over domain/analytics/achats.py.

This module uses pandas DataFrames for Streamlit compatibility.
Domain-pure equivalents: domain.analytics.achats (weighted_average_price,
rank_suppliers_by_amount, fragmentation_index).
"""

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture, Fournisseur
from dashboard.data.entity_resolution import get_mappings, get_prefix_mappings, resolve_column


def _lignes_avec_fournisseur(session: Session) -> pd.DataFrame:
    """Query all invoice lines joined with fournisseur info.

    After building the DataFrame, entity resolution is applied on
    ``type_matiere`` and ``fournisseur`` columns, producing
    ``resolved_type_matiere`` and ``resolved_fournisseur`` columns.
    """
    rows = (
        session.query(
            LigneFacture.type_matiere,
            LigneFacture.unite,
            LigneFacture.prix_unitaire,
            LigneFacture.quantite,
            LigneFacture.prix_total,
            LigneFacture.date_depart,
            Fournisseur.nom.label("fournisseur"),
            Document.date_document,
        )
        .join(Document, LigneFacture.document_id == Document.id)
        .join(Fournisseur, Document.fournisseur_id == Fournisseur.id)
        .filter(LigneFacture.type_matiere.isnot(None), LigneFacture.supprime != True)
        .all()
    )
    df = pd.DataFrame(rows, columns=[
        "type_matiere", "unite", "prix_unitaire", "quantite",
        "prix_total", "date_depart", "fournisseur", "date_document",
    ])

    # Entity resolution: add resolved_type_matiere and resolved_fournisseur
    mappings_mat = get_mappings(session, "material")
    prefix_mat = get_prefix_mappings(session, "material")
    resolve_column(df, "type_matiere", mappings_mat, prefix_mat)

    mappings_sup = get_mappings(session, "supplier")
    prefix_sup = get_prefix_mappings(session, "supplier")
    resolve_column(df, "fournisseur", mappings_sup, prefix_sup)

    return df


def top_fournisseurs_by_montant(session: Session, limit: int = 5) -> pd.DataFrame:
    """Top fournisseurs ranked by total montant HT.

    Queries ungrouped (Document.montant_ht, Fournisseur.nom) pairs, resolves
    fournisseur names via entity resolution, then re-aggregates with pandas.
    """
    rows = (
        session.query(
            Fournisseur.nom.label("fournisseur"),
            Document.montant_ht,
            Document.id.label("doc_id"),
        )
        .join(Document, Fournisseur.id == Document.fournisseur_id)
        .all()
    )
    df = pd.DataFrame(rows, columns=["fournisseur", "montant_ht", "doc_id"])

    # Apply entity resolution on fournisseur names
    mappings_sup = get_mappings(session, "supplier")
    prefix_sup = get_prefix_mappings(session, "supplier")
    resolve_column(df, "fournisseur", mappings_sup, prefix_sup)

    result = (
        df.groupby("resolved_fournisseur")
        .agg(
            montant_total=("montant_ht", "sum"),
            nb_documents=("doc_id", "nunique"),
        )
        .reset_index()
        .rename(columns={"resolved_fournisseur": "fournisseur"})
        .sort_values("montant_total", ascending=False)
        .head(limit)
        .reset_index(drop=True)
    )
    return result


def prix_moyen_par_matiere(session: Session) -> pd.DataFrame:
    """Weighted average unit price per material type."""
    df = _lignes_avec_fournisseur(session)
    df = df.dropna(subset=["prix_unitaire", "quantite"])

    result = (
        df.groupby("resolved_type_matiere")
        .apply(
            lambda g: pd.Series({
                "prix_unitaire_moyen": (g["prix_unitaire"] * g["quantite"]).sum() / g["quantite"].sum()
                if g["quantite"].sum() > 0 else 0,
                "quantite_totale": g["quantite"].sum(),
                "nb_lignes": len(g),
            }),
            include_groups=False,
        )
        .reset_index()
        .rename(columns={"resolved_type_matiere": "type_matiere"})
    )
    return result


def ecarts_prix_fournisseurs(session: Session, seuil: float = 0.15) -> pd.DataFrame:
    """Find materials with price variance > seuil across suppliers."""
    df = _lignes_avec_fournisseur(session)
    df = df.dropna(subset=["prix_unitaire"])

    grouped = (
        df.groupby(["resolved_type_matiere", "resolved_fournisseur"])["prix_unitaire"]
        .mean()
        .reset_index()
    )
    pivot = grouped.pivot(index="resolved_type_matiere", columns="resolved_fournisseur", values="prix_unitaire")

    results = []
    for matiere in pivot.index:
        prices = pivot.loc[matiere].dropna()
        if len(prices) < 2:
            continue
        min_p, max_p = prices.min(), prices.max()
        ecart = (max_p - min_p) / min_p if min_p > 0 else 0
        if ecart >= seuil:
            results.append({
                "type_matiere": matiere,
                "prix_min": min_p,
                "prix_max": max_p,
                "ecart_pct": ecart,
                "fournisseur_min": prices.idxmin(),
                "fournisseur_max": prices.idxmax(),
            })
    return pd.DataFrame(results)


def indice_fragmentation(session: Session) -> pd.DataFrame:
    """Number of distinct suppliers per material type."""
    df = _lignes_avec_fournisseur(session)
    result = (
        df.groupby("resolved_type_matiere")
        .agg(
            nb_fournisseurs=("resolved_fournisseur", "nunique"),
            nb_lignes=("resolved_fournisseur", "count"),
        )
        .reset_index()
        .rename(columns={"resolved_type_matiere": "type_matiere"})
        .sort_values("nb_fournisseurs", ascending=False)
    )
    return result


def economie_potentielle(session: Session) -> dict:
    """Estimate savings if all purchases used the best price per material."""
    df = _lignes_avec_fournisseur(session)
    df = df.dropna(subset=["prix_unitaire", "quantite"])

    best_prices = df.groupby("resolved_type_matiere")["prix_unitaire"].min()

    savings_details = []
    total = 0.0
    for _, row in df.iterrows():
        best = best_prices.get(row["resolved_type_matiere"], row["prix_unitaire"])
        if row["prix_unitaire"] > best and row["quantite"]:
            saving = (row["prix_unitaire"] - best) * row["quantite"]
            total += saving
            savings_details.append({
                "type_matiere": row["resolved_type_matiere"],
                "fournisseur": row["resolved_fournisseur"],
                "prix_actuel": row["prix_unitaire"],
                "meilleur_prix": best,
                "quantite": row["quantite"],
                "economie": saving,
            })

    return {
        "total_economie": total,
        "details": pd.DataFrame(savings_details) if savings_details else pd.DataFrame(),
    }
