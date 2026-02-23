"""Pure helper functions extracted from 11_verification_pdf.py for testability.

Interfaces amont : appelé par 11_verification_pdf.py au rendu et par _CORSHandler.do_POST
Interfaces aval  : SQLAlchemy Session (lecture LigneFacture/Document), appliquer_correction()
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Document, LigneFacture
from dashboard.analytics.corrections import EDITABLE_FIELDS, appliquer_correction

# Fields that must be parseable as positive floats
FLOAT_FIELDS = {"prix_unitaire", "quantite", "prix_total"}
# Fields that must be valid ISO 8601 dates (YYYY-MM-DD)
DATE_FIELDS = {"date_depart", "date_arrivee"}
_DATE_FMT = "%Y-%m-%d"


def _parse_date(value: str):
    """Parse a YYYY-MM-DD string. Raises ValueError if format is wrong."""
    return datetime.strptime(value, _DATE_FMT).date()


_LIGNE_VALUE_FIELDS = [
    "type_matiere", "unite", "prix_unitaire", "quantite", "prix_total",
    "date_depart", "date_arrivee", "lieu_depart", "lieu_arrivee",
]
_LIGNE_CONF_FIELDS = [f"conf_{f}" for f in _LIGNE_VALUE_FIELDS]


def get_ligne_data(engine, fichier: str) -> dict[int, dict]:
    """Return {ligne_numero: {id, all value fields, all conf fields}} from DB.

    Used by the verification panel to overlay corrected values on top of the
    original extraction JSON — so that operator corrections persist across
    page reloads.  Returns empty dict when engine is None or document not in DB.
    """
    if engine is None:
        return {}
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
        result = {}
        for l in lignes:
            entry: dict = {"id": l.id}
            for f in _LIGNE_VALUE_FIELDS:
                entry[f] = getattr(l, f)
            for f in _LIGNE_CONF_FIELDS:
                entry[f] = getattr(l, f)
            result[l.ligne_numero] = entry
        return result


def get_ligne_ids(engine, fichier: str) -> dict[int, int]:
    """Return {ligne_numero: ligne_id} for all active lines of a document.

    Args:
        engine: SQLAlchemy engine (thread-safe, shared). May be None if the
                page is loaded before app.py initializes session state —
                in that case all cells are rendered read-only.
        fichier: filename as stored in documents.fichier (basename only).

    Returns:
        Empty dict if engine is None, document not found in DB, or has no lines.
    """
    if engine is None:
        return {}
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

    # ── Validation du type ────────────────────────────────────────────────────
    if champ in FLOAT_FIELDS:
        try:
            float(valeur_corrigee)
        except (TypeError, ValueError):
            return 400, {
                "success": False,
                "error": f"Valeur numérique attendue pour « {champ} » (reçu : {valeur_corrigee!r})",
            }

    if champ in DATE_FIELDS:
        try:
            nouvelle_date = _parse_date(str(valeur_corrigee))
        except (TypeError, ValueError):
            return 400, {
                "success": False,
                "error": (
                    f"Format de date invalide pour « {champ} » — attendu AAAA-MM-JJ "
                    f"(reçu : {valeur_corrigee!r})"
                ),
            }

        # ── Validation de l'ordre des dates (cohérence départ/arrivée) ───────
        with Session(engine) as session:
            ligne = session.get(LigneFacture, ligne_id)
            if ligne is None:
                return 404, {"success": False, "error": f"Ligne {ligne_id} introuvable"}

            if champ == "date_arrivee" and ligne.date_depart:
                try:
                    date_depart = _parse_date(ligne.date_depart)
                    if nouvelle_date < date_depart:
                        return 400, {
                            "success": False,
                            "error": (
                                f"La date d'arrivée ({valeur_corrigee}) ne peut pas être "
                                f"antérieure à la date de départ ({ligne.date_depart})"
                            ),
                        }
                except ValueError:
                    pass  # date_depart already in DB is malformed — skip cross-check

            if champ == "date_depart" and ligne.date_arrivee:
                try:
                    date_arrivee = _parse_date(ligne.date_arrivee)
                    if nouvelle_date > date_arrivee:
                        return 400, {
                            "success": False,
                            "error": (
                                f"La date de départ ({valeur_corrigee}) ne peut pas être "
                                f"après la date d'arrivée ({ligne.date_arrivee})"
                            ),
                        }
                except ValueError:
                    pass  # date_arrivee in DB is malformed — skip cross-check

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
