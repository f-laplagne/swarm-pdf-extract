"""SQLAlchemy adapter implementing CorrectionPort."""

from __future__ import annotations

from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import CorrectionLog, LigneFacture
from domain.models import Correction
from domain.ports import CorrectionPort


class SqlAlchemyCorrectionRepository(CorrectionPort):
    """Reads/writes Correction domain objects via CorrectionLog ORM model."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def sauvegarder(self, correction: Correction) -> Correction:
        ligne = self._session.get(LigneFacture, correction.ligne_id)
        if ligne is None:
            raise ValueError(f"Ligne {correction.ligne_id} introuvable")
        log = CorrectionLog(
            ligne_id=correction.ligne_id,
            document_id=ligne.document_id,
            champ=correction.champ,
            ancienne_valeur=correction.valeur_originale,
            nouvelle_valeur=correction.valeur_corrigee,
            ancienne_confiance=correction.confiance_originale,
            corrige_par=correction.corrige_par,
            notes=correction.notes,
        )
        self._session.add(log)
        self._session.commit()
        correction.id = log.id
        return correction

    def historique(self, champ: str, valeur_originale: str) -> list[Correction]:
        logs = (
            self._session.query(CorrectionLog)
            .filter(
                CorrectionLog.champ == champ,
                CorrectionLog.ancienne_valeur == valeur_originale,
            )
            .all()
        )
        return [
            Correction(
                ligne_id=log.ligne_id,
                champ=log.champ,
                valeur_originale=log.ancienne_valeur,
                valeur_corrigee=log.nouvelle_valeur or "",
                confiance_originale=log.ancienne_confiance,
                corrige_par=log.corrige_par or "admin",
                notes=log.notes,
                id=log.id,
            )
            for log in logs
        ]
