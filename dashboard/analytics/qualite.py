import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture


CONF_FIELDS = [
    "conf_type_matiere", "conf_unite", "conf_prix_unitaire", "conf_quantite",
    "conf_prix_total", "conf_date_depart", "conf_date_arrivee",
    "conf_lieu_depart", "conf_lieu_arrivee",
]

FIELD_NAMES = [f.replace("conf_", "") for f in CONF_FIELDS]


def score_global(session: Session, seuil_fiable: float = 0.8) -> dict:
    docs = session.query(Document.confiance_globale).all()
    scores = [d[0] for d in docs if d[0] is not None]
    if not scores:
        return {"score_moyen": 0, "nb_documents": 0, "pct_fiables": 0}

    nb_fiables = sum(1 for s in scores if s >= seuil_fiable)
    return {
        "score_moyen": sum(scores) / len(scores),
        "nb_documents": len(scores),
        "pct_fiables": (nb_fiables / len(scores)) * 100,
    }


def confiance_par_champ(session: Session) -> pd.DataFrame:
    results = {}
    for conf_field, field_name in zip(CONF_FIELDS, FIELD_NAMES):
        col = getattr(LigneFacture, conf_field)
        row = session.query(
            func.avg(col),
            func.min(col),
            func.max(col),
            func.count(col),
        ).filter(col.isnot(None), LigneFacture.supprime != True).one()
        results[field_name] = {
            "moyenne": row[0] or 0,
            "min": row[1] or 0,
            "max": row[2] or 0,
            "nb_valeurs": row[3] or 0,
        }
    return pd.DataFrame(results).T


def documents_par_qualite(session: Session) -> pd.DataFrame:
    rows = (
        session.query(
            Document.fichier, Document.confiance_globale,
            Document.strategie_utilisee, Document.format_pdf,
        )
        .order_by(Document.confiance_globale.desc())
        .all()
    )
    return pd.DataFrame(rows, columns=[
        "fichier", "confiance_globale", "strategie", "format_pdf",
    ])
