import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture, Fournisseur, Anomalie
from domain.anomaly_rules import (
    check_calculation_coherence as domain_check_calc,
    check_date_order as domain_check_date,
    check_low_confidence as domain_check_conf,
)
from domain.models import LigneFacture as DomainLigne


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
            LigneFacture.supprime != True,
        )
        .all()
    )

    for ligne in lignes:
        domain_ligne = DomainLigne(
            ligne_numero=ligne.ligne_numero or 0,
            prix_unitaire=ligne.prix_unitaire,
            quantite=ligne.quantite,
            prix_total=ligne.prix_total,
        )
        result = domain_check_calc(domain_ligne, tolerance)
        if not result.est_valide:
            attendu = result.details.get("attendu")
            reel = result.details.get("reel")
            anomalies.append(Anomalie(
                document_id=ligne.document_id,
                ligne_id=ligne.id,
                regle_id=rule["id"],
                type_anomalie=rule["type"],
                severite=rule["severite"],
                description=result.description,
                valeur_attendue=f"{attendu:.2f}" if attendu is not None else "",
                valeur_trouvee=f"{reel:.2f}" if reel is not None else "",
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
            LigneFacture.supprime != True,
        )
        .all()
    )

    for ligne in lignes:
        domain_ligne = DomainLigne(
            ligne_numero=ligne.ligne_numero or 0,
            date_depart=ligne.date_depart,
            date_arrivee=ligne.date_arrivee,
        )
        result = domain_check_date(domain_ligne)
        if not result.est_valide:
            anomalies.append(Anomalie(
                document_id=ligne.document_id,
                ligne_id=ligne.id,
                regle_id=rule["id"],
                type_anomalie=rule["type"],
                severite=rule["severite"],
                description=result.description,
                valeur_attendue=f">= {result.details.get('depart', '')}",
                valeur_trouvee=result.details.get("arrivee", ""),
            ))

    return anomalies


def _check_low_confidence(session: Session, rule: dict) -> list[Anomalie]:
    """CONF_001: document confidence below threshold."""
    seuil = rule.get("seuil_confiance", 0.6)
    anomalies = []

    docs = session.query(Document).filter(Document.confiance_globale < seuil).all()
    for doc in docs:
        result = domain_check_conf(doc.confiance_globale, seuil)
        if not result.est_valide:
            anomalies.append(Anomalie(
                document_id=doc.id,
                regle_id=rule["id"],
                type_anomalie=rule["type"],
                severite=rule["severite"],
                description=result.description,
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
