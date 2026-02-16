import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session

from dashboard.data.models import LigneFacture


def _lignes_logistiques(session: Session) -> pd.DataFrame:
    lignes = (
        session.query(
            LigneFacture.lieu_depart, LigneFacture.lieu_arrivee,
            LigneFacture.date_depart, LigneFacture.date_arrivee,
            LigneFacture.prix_total, LigneFacture.type_matiere,
            LigneFacture.quantite,
        )
        .filter(
            LigneFacture.lieu_depart.isnot(None),
            LigneFacture.lieu_arrivee.isnot(None),
        )
        .all()
    )
    return pd.DataFrame(lignes, columns=[
        "lieu_depart", "lieu_arrivee", "date_depart", "date_arrivee",
        "prix_total", "type_matiere", "quantite",
    ])


def top_routes(session: Session, limit: int = 5) -> pd.DataFrame:
    df = _lignes_logistiques(session)
    df["route"] = df["lieu_depart"] + " \u2192 " + df["lieu_arrivee"]
    result = (
        df.groupby("route")
        .agg(nb_trajets=("route", "count"), cout_total=("prix_total", "sum"))
        .reset_index()
        .sort_values("nb_trajets", ascending=False)
        .head(limit)
    )
    return result


def matrice_od(session: Session) -> pd.DataFrame:
    df = _lignes_logistiques(session)
    return pd.crosstab(df["lieu_depart"], df["lieu_arrivee"])


def delai_moyen_livraison(session: Session) -> dict:
    df = _lignes_logistiques(session)
    df = df.dropna(subset=["date_depart", "date_arrivee"])
    df["depart"] = pd.to_datetime(df["date_depart"])
    df["arrivee"] = pd.to_datetime(df["date_arrivee"])
    df["delai"] = (df["arrivee"] - df["depart"]).dt.days

    valid = df[df["delai"] >= 0]
    if valid.empty:
        return {"delai_moyen_jours": 0, "delai_median_jours": 0, "nb_trajets": 0}

    return {
        "delai_moyen_jours": valid["delai"].mean(),
        "delai_median_jours": valid["delai"].median(),
        "nb_trajets": len(valid),
    }


def opportunites_regroupement(session: Session, fenetre_jours: int = 7) -> pd.DataFrame:
    df = _lignes_logistiques(session)
    df = df.dropna(subset=["date_depart"])
    df["route"] = df["lieu_depart"] + " \u2192 " + df["lieu_arrivee"]
    df["depart"] = pd.to_datetime(df["date_depart"])

    results = []
    for route, group in df.groupby("route"):
        if len(group) < 2:
            continue
        group = group.sort_values("depart")
        dates = group["depart"].values
        # Count trips within fenetre_jours of each other
        clusters = []
        current_cluster = [dates[0]]
        for d in dates[1:]:
            if (d - current_cluster[0]) / pd.Timedelta(days=1) <= fenetre_jours:
                current_cluster.append(d)
            else:
                if len(current_cluster) >= 2:
                    clusters.append(current_cluster)
                current_cluster = [d]
        if len(current_cluster) >= 2:
            clusters.append(current_cluster)

        for cluster in clusters:
            results.append({
                "route": route,
                "nb_trajets_regroupables": len(cluster),
                "periode_debut": pd.Timestamp(cluster[0]),
                "periode_fin": pd.Timestamp(cluster[-1]),
            })

    return pd.DataFrame(results) if results else pd.DataFrame(
        columns=["route", "nb_trajets_regroupables", "periode_debut", "periode_fin"]
    )
