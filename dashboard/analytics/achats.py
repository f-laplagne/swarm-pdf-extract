import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture, Fournisseur


def _lignes_avec_fournisseur(session: Session) -> pd.DataFrame:
    """Query all invoice lines joined with fournisseur info."""
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
        .filter(LigneFacture.type_matiere.isnot(None))
        .all()
    )
    return pd.DataFrame(rows, columns=[
        "type_matiere", "unite", "prix_unitaire", "quantite",
        "prix_total", "date_depart", "fournisseur", "date_document",
    ])


def top_fournisseurs_by_montant(session: Session, limit: int = 5) -> pd.DataFrame:
    """Top fournisseurs ranked by total montant HT."""
    rows = (
        session.query(
            Fournisseur.nom.label("fournisseur"),
            func.sum(Document.montant_ht).label("montant_total"),
            func.count(Document.id).label("nb_documents"),
        )
        .join(Document, Fournisseur.id == Document.fournisseur_id)
        .group_by(Fournisseur.nom)
        .order_by(func.sum(Document.montant_ht).desc())
        .limit(limit)
        .all()
    )
    return pd.DataFrame(rows, columns=["fournisseur", "montant_total", "nb_documents"])


def prix_moyen_par_matiere(session: Session) -> pd.DataFrame:
    """Weighted average unit price per material type."""
    df = _lignes_avec_fournisseur(session)
    df = df.dropna(subset=["prix_unitaire", "quantite"])

    result = (
        df.groupby("type_matiere")
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
    )
    return result


def ecarts_prix_fournisseurs(session: Session, seuil: float = 0.15) -> pd.DataFrame:
    """Find materials with price variance > seuil across suppliers."""
    df = _lignes_avec_fournisseur(session)
    df = df.dropna(subset=["prix_unitaire"])

    grouped = (
        df.groupby(["type_matiere", "fournisseur"])["prix_unitaire"]
        .mean()
        .reset_index()
    )
    pivot = grouped.pivot(index="type_matiere", columns="fournisseur", values="prix_unitaire")

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
        df.groupby("type_matiere")
        .agg(nb_fournisseurs=("fournisseur", "nunique"), nb_lignes=("fournisseur", "count"))
        .reset_index()
        .sort_values("nb_fournisseurs", ascending=False)
    )
    return result


def economie_potentielle(session: Session) -> dict:
    """Estimate savings if all purchases used the best price per material."""
    df = _lignes_avec_fournisseur(session)
    df = df.dropna(subset=["prix_unitaire", "quantite"])

    best_prices = df.groupby("type_matiere")["prix_unitaire"].min()

    savings_details = []
    total = 0.0
    for _, row in df.iterrows():
        best = best_prices.get(row["type_matiere"], row["prix_unitaire"])
        if row["prix_unitaire"] > best and row["quantite"]:
            saving = (row["prix_unitaire"] - best) * row["quantite"]
            total += saving
            savings_details.append({
                "type_matiere": row["type_matiere"],
                "fournisseur": row["fournisseur"],
                "prix_actuel": row["prix_unitaire"],
                "meilleur_prix": best,
                "quantite": row["quantite"],
                "economie": saving,
            })

    return {
        "total_economie": total,
        "details": pd.DataFrame(savings_details) if savings_details else pd.DataFrame(),
    }
