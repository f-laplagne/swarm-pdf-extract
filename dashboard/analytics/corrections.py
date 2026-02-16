"""Query and mutation functions for manual correction of low-confidence extractions."""

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from dashboard.data.models import CorrectionLog, Document, LigneFacture

# The 9 editable field / confidence pairs on LigneFacture
EDITABLE_FIELDS = [
    "type_matiere", "unite", "prix_unitaire", "quantite", "prix_total",
    "date_depart", "date_arrivee", "lieu_depart", "lieu_arrivee",
]

CONF_FIELDS = [f"conf_{f}" for f in EDITABLE_FIELDS]

FIELD_CONF_PAIRS = list(zip(EDITABLE_FIELDS, CONF_FIELDS))


def champs_faibles_pour_ligne(ligne: LigneFacture, seuil: float = 0.70) -> list[str]:
    """Return field names where confidence is below threshold. None is treated as weak."""
    faibles = []
    for field, conf_field in FIELD_CONF_PAIRS:
        conf = getattr(ligne, conf_field, None)
        if conf is None or conf < seuil:
            faibles.append(field)
    return faibles


def documents_a_corriger(session: Session, seuil: float = 0.70) -> pd.DataFrame:
    """Documents with at least one line having any confidence field below seuil."""
    docs = session.query(Document).join(Document.lignes).all()
    seen = set()
    rows = []
    for doc in docs:
        if doc.id in seen:
            continue
        seen.add(doc.id)
        nb_faibles = 0
        for ligne in doc.lignes:
            if champs_faibles_pour_ligne(ligne, seuil):
                nb_faibles += 1
        if nb_faibles > 0:
            rows.append({
                "document_id": doc.id,
                "fichier": doc.fichier,
                "type_document": doc.type_document,
                "confiance_globale": doc.confiance_globale,
                "nb_lignes_faibles": nb_faibles,
            })
    df = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["document_id", "fichier", "type_document", "confiance_globale", "nb_lignes_faibles"]
    )
    if not df.empty:
        df = df.sort_values("nb_lignes_faibles", ascending=False).reset_index(drop=True)
    return df


def lignes_a_corriger(session: Session, document_id: int, seuil: float = 0.70) -> pd.DataFrame:
    """Weak lines for a document, with a 'champs_faibles' column listing weak field names."""
    lignes = (
        session.query(LigneFacture)
        .filter(LigneFacture.document_id == document_id)
        .order_by(LigneFacture.ligne_numero)
        .all()
    )
    rows = []
    for ligne in lignes:
        faibles = champs_faibles_pour_ligne(ligne, seuil)
        if faibles:
            rows.append({
                "ligne_id": ligne.id,
                "ligne_numero": ligne.ligne_numero,
                "type_matiere": ligne.type_matiere,
                "champs_faibles": ", ".join(faibles),
                "nb_champs_faibles": len(faibles),
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ligne_id", "ligne_numero", "type_matiere", "champs_faibles", "nb_champs_faibles"]
    )


def stats_corrections(session: Session) -> dict:
    """KPIs: total corrections, distinct lines corrected, distinct documents corrected."""
    total = session.query(func.count(CorrectionLog.id)).scalar() or 0
    lignes = session.query(func.count(func.distinct(CorrectionLog.ligne_id))).scalar() or 0
    documents = session.query(func.count(func.distinct(CorrectionLog.document_id))).scalar() or 0
    return {"total": total, "lignes": lignes, "documents": documents}


def historique_corrections(session: Session, document_id: int | None = None) -> pd.DataFrame:
    """Correction log table, optionally filtered by document."""
    query = session.query(CorrectionLog).order_by(CorrectionLog.corrige_at.desc())
    if document_id is not None:
        query = query.filter(CorrectionLog.document_id == document_id)
    entries = query.all()
    if not entries:
        return pd.DataFrame(columns=[
            "id", "document_id", "ligne_id", "champ",
            "ancienne_valeur", "nouvelle_valeur",
            "ancienne_confiance", "corrige_par", "corrige_at", "notes",
        ])
    rows = []
    for e in entries:
        rows.append({
            "id": e.id,
            "document_id": e.document_id,
            "ligne_id": e.ligne_id,
            "champ": e.champ,
            "ancienne_valeur": e.ancienne_valeur,
            "nouvelle_valeur": e.nouvelle_valeur,
            "ancienne_confiance": e.ancienne_confiance,
            "corrige_par": e.corrige_par,
            "corrige_at": e.corrige_at.strftime("%Y-%m-%d %H:%M") if e.corrige_at else "",
            "notes": e.notes or "",
        })
    return pd.DataFrame(rows)


def appliquer_correction(
    session: Session,
    ligne_id: int,
    corrections_dict: dict[str, object],
    corrige_par: str = "admin",
    notes: str | None = None,
) -> list[CorrectionLog]:
    """Apply edits to a line, log each change, set conf to 1.0, recalculate confiance_globale."""
    ligne = session.get(LigneFacture, ligne_id)
    if ligne is None:
        raise ValueError(f"Ligne {ligne_id} introuvable")

    logs = []
    for champ, nouvelle_valeur in corrections_dict.items():
        if champ not in EDITABLE_FIELDS:
            continue
        ancienne_valeur = getattr(ligne, champ)
        conf_field = f"conf_{champ}"
        ancienne_confiance = getattr(ligne, conf_field)

        # Update field and confidence
        setattr(ligne, champ, nouvelle_valeur)
        setattr(ligne, conf_field, 1.0)

        log = CorrectionLog(
            ligne_id=ligne.id,
            document_id=ligne.document_id,
            champ=champ,
            ancienne_valeur=str(ancienne_valeur) if ancienne_valeur is not None else None,
            nouvelle_valeur=str(nouvelle_valeur) if nouvelle_valeur is not None else None,
            ancienne_confiance=ancienne_confiance,
            corrige_par=corrige_par,
            notes=notes,
        )
        session.add(log)
        logs.append(log)

    session.flush()
    recalculer_confiance_globale(session, ligne.document_id)
    session.commit()
    return logs


def recalculer_confiance_globale(session: Session, document_id: int) -> float | None:
    """Recompute confiance_globale as mean of all non-null conf fields across all lines."""
    lignes = (
        session.query(LigneFacture)
        .filter(LigneFacture.document_id == document_id)
        .all()
    )
    values = []
    for ligne in lignes:
        for conf_field in CONF_FIELDS:
            v = getattr(ligne, conf_field)
            if v is not None:
                values.append(v)

    doc = session.get(Document, document_id)
    if doc is None:
        return None
    if values:
        doc.confiance_globale = sum(values) / len(values)
    else:
        doc.confiance_globale = None
    session.flush()
    return doc.confiance_globale
