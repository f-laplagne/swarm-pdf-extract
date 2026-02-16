import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture, Anomalie
from dashboard.analytics.anomalies import run_anomaly_detection, get_anomaly_stats


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def data_with_anomalies(db_session):
    f = Fournisseur(nom="TestCo")
    db_session.add(f)
    db_session.flush()

    d = Document(fichier="test.pdf", type_document="facture", fournisseur_id=f.id,
                 montant_ht=1000, montant_ttc=1200, confiance_globale=0.4,
                 date_document=date(2024, 1, 15))
    db_session.add(d)
    db_session.flush()

    lignes = [
        # CALC_001: prix_total != prix_unitaire * quantite (100 != 10*9 = 90)
        LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="Acier",
                     prix_unitaire=10.0, quantite=9, prix_total=100.0),
        # DATE_001: date_arrivee before date_depart
        LigneFacture(document_id=d.id, ligne_numero=2, type_matiere="Cuivre",
                     prix_unitaire=20.0, quantite=5, prix_total=100.0,
                     date_depart="2024-01-10", date_arrivee="2024-01-05"),
        # Normal line
        LigneFacture(document_id=d.id, ligne_numero=3, type_matiere="Zinc",
                     prix_unitaire=15.0, quantite=10, prix_total=150.0),
    ]
    db_session.add_all(lignes)
    db_session.commit()
    return db_session


DEFAULT_RULES = [
    {"id": "CALC_001", "type": "coherence_calcul", "severite": "critique", "seuil_tolerance": 0.01},
    {"id": "DATE_001", "type": "date_invalide", "severite": "warning"},
    {"id": "CONF_001", "type": "qualite_donnees", "severite": "info", "seuil_confiance": 0.6},
]


def test_detects_calc_incoherence(data_with_anomalies):
    anomalies = run_anomaly_detection(data_with_anomalies, DEFAULT_RULES)
    calc_anomalies = [a for a in anomalies if a.regle_id == "CALC_001"]
    assert len(calc_anomalies) == 1


def test_detects_date_invalide(data_with_anomalies):
    anomalies = run_anomaly_detection(data_with_anomalies, DEFAULT_RULES)
    date_anomalies = [a for a in anomalies if a.regle_id == "DATE_001"]
    assert len(date_anomalies) == 1


def test_detects_low_confidence(data_with_anomalies):
    anomalies = run_anomaly_detection(data_with_anomalies, DEFAULT_RULES)
    conf_anomalies = [a for a in anomalies if a.regle_id == "CONF_001"]
    assert len(conf_anomalies) == 1  # document confiance 0.4 < 0.6


def test_anomaly_stats(data_with_anomalies):
    run_anomaly_detection(data_with_anomalies, DEFAULT_RULES)
    data_with_anomalies.commit()
    stats = get_anomaly_stats(data_with_anomalies)
    assert stats["total"] >= 3
    assert "critique" in stats["par_severite"]
