"""Pure helper functions extracted from 11_verification_pdf.py for testability.

Interfaces amont : appelé par 11_verification_pdf.py au rendu et par _CORSHandler.do_POST
Interfaces aval  : SQLAlchemy Session (lecture LigneFacture/Document), appliquer_correction()
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Document, LigneFacture
from dashboard.analytics.corrections import EDITABLE_FIELDS, appliquer_correction


def get_ligne_ids(engine, fichier: str) -> dict[int, int]:
    """Return {ligne_numero: ligne_id} for all active lines of a document.

    Args:
        engine: SQLAlchemy engine (thread-safe, shared).
        fichier: filename as stored in documents.fichier (basename only).

    Returns:
        Empty dict if document not found in DB or has no lines.
    """
    with Session(engine) as session:
        doc = session.query(Document).filter(Document.fichier == fichier).first()
        if doc is None:
            return {}
        lignes = (
            session.query(LigneFacture)
            .filter(
                LigneFacture.document_id == doc.id,
                LigneFacture.supprime != True,
            )
            .all()
        )
        return {ligne.ligne_numero: ligne.id for ligne in lignes}


def handle_correction_post(body: dict, engine) -> tuple[int, dict]:
    """Process a correction POST request and persist it to the DB.

    Args:
        body: Parsed JSON dict with keys: ligne_id, champ, valeur_originale,
              valeur_corrigee, confiance_originale.
        engine: SQLAlchemy engine.

    Returns:
        (http_status_code, response_dict)
        Success: (200, {"success": True, "correction_id": N})
        Error:   (4xx, {"success": False, "error": "..."})
    """
    required = {"ligne_id", "champ", "valeur_corrigee"}
    missing = required - body.keys()
    if missing:
        return 400, {"success": False, "error": f"Champs manquants : {missing}"}

    champ = body.get("champ", "")
    if champ not in EDITABLE_FIELDS:
        return 400, {"success": False, "error": f"Champ inconnu : {champ!r}. Valides : {EDITABLE_FIELDS}"}

    ligne_id = body.get("ligne_id")
    valeur_corrigee = body.get("valeur_corrigee")

    try:
        with Session(engine) as session:
            logs = appliquer_correction(
                session,
                ligne_id,
                {champ: valeur_corrigee},
                corrige_par="operateur_verification",
                notes=None,
            )
            if not logs:
                return 404, {"success": False, "error": f"Ligne {ligne_id} introuvable"}
            return 200, {"success": True, "correction_id": logs[0].id}
    except ValueError as exc:
        return 404, {"success": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return 500, {"success": False, "error": f"Erreur interne : {exc}"}
