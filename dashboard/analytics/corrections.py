"""Query and mutation functions for manual correction of low-confidence extractions."""

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from dashboard.data.models import BoundingBox, CorrectionLog, Document, LigneFacture

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
            if ligne.supprime:
                continue
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
        .filter(LigneFacture.document_id == document_id, LigneFacture.supprime != True)
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
    query = (
        session.query(CorrectionLog, Document.fichier)
        .join(Document, CorrectionLog.document_id == Document.id)
        .order_by(CorrectionLog.corrige_at.desc())
    )
    if document_id is not None:
        query = query.filter(CorrectionLog.document_id == document_id)
    entries = query.all()
    if not entries:
        return pd.DataFrame(columns=[
            "id", "fichier", "ligne_id", "champ",
            "ancienne_valeur", "nouvelle_valeur",
            "ancienne_confiance", "corrige_par", "corrige_at", "notes",
        ])
    rows = []
    for e, fichier in entries:
        rows.append({
            "id": e.id,
            "fichier": fichier,
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


def detail_confiance_document(session: Session, document_id: int) -> pd.DataFrame:
    """Per-line, per-field confidence grid for a document. Each cell is the conf value."""
    lignes = (
        session.query(LigneFacture)
        .filter(LigneFacture.document_id == document_id, LigneFacture.supprime != True)
        .order_by(LigneFacture.ligne_numero)
        .all()
    )
    rows = []
    for ligne in lignes:
        row = {"ligne": ligne.ligne_numero, "matiere": ligne.type_matiere or "?"}
        for field, conf_field in FIELD_CONF_PAIRS:
            row[field] = getattr(ligne, conf_field)
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ligne", "matiere"] + EDITABLE_FIELDS
    )


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


def supprimer_ligne(
    session: Session,
    ligne_id: int,
    supprime_par: str = "admin",
    notes: str | None = None,
) -> CorrectionLog:
    """Soft-delete a line: mark as supprime, log the action, recalculate confiance_globale."""
    ligne = session.get(LigneFacture, ligne_id)
    if ligne is None:
        raise ValueError(f"Ligne {ligne_id} introuvable")

    ligne.supprime = True

    log = CorrectionLog(
        ligne_id=ligne.id,
        document_id=ligne.document_id,
        champ="__suppression__",
        ancienne_valeur=f"Ligne {ligne.ligne_numero}: {ligne.type_matiere}",
        nouvelle_valeur="supprimee",
        ancienne_confiance=None,
        corrige_par=supprime_par,
        notes=notes,
    )
    session.add(log)
    session.flush()
    recalculer_confiance_globale(session, ligne.document_id)
    session.commit()
    return log


def recalculer_confiance_globale(session: Session, document_id: int) -> float | None:
    """Recompute confiance_globale as mean of all non-null conf fields across active lines."""
    lignes = (
        session.query(LigneFacture)
        .filter(LigneFacture.document_id == document_id, LigneFacture.supprime != True)
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


# ---------------------------------------------------------------------------
# Bounding box CRUD
# ---------------------------------------------------------------------------

def sauvegarder_bbox(
    session: Session,
    ligne_id: int,
    document_id: int,
    champ: str,
    page_number: int,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    source: str = "manual",
    cree_par: str = "admin",
    correction_log_id: int | None = None,
) -> BoundingBox:
    """Validate normalized coords and persist a bounding box."""
    for coord_name, val in [("x_min", x_min), ("y_min", y_min), ("x_max", x_max), ("y_max", y_max)]:
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"{coord_name}={val} hors de l'intervalle [0, 1]")
    if x_min >= x_max or y_min >= y_max:
        raise ValueError("Coordonnees invalides : min doit etre < max")

    bbox = BoundingBox(
        ligne_id=ligne_id,
        document_id=document_id,
        champ=champ,
        page_number=page_number,
        x_min=x_min,
        y_min=y_min,
        x_max=x_max,
        y_max=y_max,
        source=source,
        cree_par=cree_par,
        correction_log_id=correction_log_id,
    )
    session.add(bbox)
    session.commit()
    return bbox


def bboxes_pour_page(session: Session, document_id: int, page_number: int) -> list[BoundingBox]:
    """All bounding boxes for a given document page."""
    return (
        session.query(BoundingBox)
        .filter(BoundingBox.document_id == document_id, BoundingBox.page_number == page_number)
        .all()
    )


def bboxes_pour_ligne(session: Session, ligne_id: int) -> list[BoundingBox]:
    """All bounding boxes for a given line."""
    return (
        session.query(BoundingBox)
        .filter(BoundingBox.ligne_id == ligne_id)
        .all()
    )


def supprimer_bbox(session: Session, bbox_id: int) -> None:
    """Delete a bounding box by id."""
    bbox = session.get(BoundingBox, bbox_id)
    if bbox is None:
        raise ValueError(f"BoundingBox {bbox_id} introuvable")
    session.delete(bbox)
    session.commit()
