import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture, Fournisseur, Anomalie


def _check_calc_coherence(session: Session, rule: dict) -> list[Anomalie]:
    """CALC_001: prix_unitaire * quantite != prix_total."""
    tolerance = rule.get("seuil_tolerance", 0.01)
    anomalies = []

    lignes = (
        session.query(LigneFacture)
        .filter(
            LigneFacture.prix_unitaire.isnot(None),
            LigneFacture.quantite.isnot(None),
            LigneFacture.prix_total.isnot(None),
        )
        .all()
    )

    for ligne in lignes:
        expected = ligne.prix_unitaire * ligne.quantite
        if ligne.prix_total == 0:
            continue
        ecart = abs(expected - ligne.prix_total) / abs(ligne.prix_total)
        if ecart > tolerance:
            anomalies.append(Anomalie(
                document_id=ligne.document_id,
                ligne_id=ligne.id,
                regle_id=rule["id"],
                type_anomalie=rule["type"],
                severite=rule["severite"],
                description=f"PU({ligne.prix_unitaire}) x Qte({ligne.quantite}) = {expected:.2f} != Total({ligne.prix_total})",
                valeur_attendue=f"{expected:.2f}",
                valeur_trouvee=f"{ligne.prix_total:.2f}",
            ))

    return anomalies


def _check_date_invalide(session: Session, rule: dict) -> list[Anomalie]:
    """DATE_001: date_arrivee < date_depart."""
    anomalies = []

    lignes = (
        session.query(LigneFacture)
        .filter(
            LigneFacture.date_depart.isnot(None),
            LigneFacture.date_arrivee.isnot(None),
        )
        .all()
    )

    for ligne in lignes:
        if ligne.date_arrivee < ligne.date_depart:
            anomalies.append(Anomalie(
                document_id=ligne.document_id,
                ligne_id=ligne.id,
                regle_id=rule["id"],
                type_anomalie=rule["type"],
                severite=rule["severite"],
                description=f"Date arrivee ({ligne.date_arrivee}) avant depart ({ligne.date_depart})",
                valeur_attendue=f">= {ligne.date_depart}",
                valeur_trouvee=ligne.date_arrivee,
            ))

    return anomalies


def _check_low_confidence(session: Session, rule: dict) -> list[Anomalie]:
    """CONF_001: document confidence below threshold."""
    seuil = rule.get("seuil_confiance", 0.6)
    anomalies = []

    docs = session.query(Document).filter(Document.confiance_globale < seuil).all()
    for doc in docs:
        anomalies.append(Anomalie(
            document_id=doc.id,
            regle_id=rule["id"],
            type_anomalie=rule["type"],
            severite=rule["severite"],
            description=f"Confiance globale {doc.confiance_globale:.2f} < seuil {seuil}",
            valeur_attendue=f">= {seuil}",
            valeur_trouvee=f"{doc.confiance_globale:.2f}",
        ))

    return anomalies


_RULE_HANDLERS = {
    "coherence_calcul": _check_calc_coherence,
    "date_invalide": _check_date_invalide,
    "qualite_donnees": _check_low_confidence,
}


def run_anomaly_detection(session: Session, rules: list[dict]) -> list[Anomalie]:
    """Run all anomaly rules and persist results. Returns list of new anomalies."""
    # Clear existing anomalies before re-running
    session.query(Anomalie).delete()

    all_anomalies = []
    for rule in rules:
        handler = _RULE_HANDLERS.get(rule["type"])
        if handler:
            new_anomalies = handler(session, rule)
            all_anomalies.extend(new_anomalies)

    session.add_all(all_anomalies)
    session.flush()
    return all_anomalies


def get_anomaly_stats(session: Session) -> dict:
    """Get summary statistics of detected anomalies."""
    total = session.query(Anomalie).count()

    par_severite = dict(
        session.query(Anomalie.severite, func.count(Anomalie.id))
        .group_by(Anomalie.severite)
        .all()
    )

    par_type = dict(
        session.query(Anomalie.type_anomalie, func.count(Anomalie.id))
        .group_by(Anomalie.type_anomalie)
        .all()
    )

    return {"total": total, "par_severite": par_severite, "par_type": par_type}
