"""Integration test: ingest real extraction JSONs -> run analytics -> verify outputs."""
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Document, LigneFacture, Fournisseur
from dashboard.data.ingestion import ingest_extraction_json
from dashboard.analytics.achats import top_fournisseurs_by_montant, economie_potentielle
from dashboard.analytics.anomalies import run_anomaly_detection, get_anomaly_stats
from dashboard.analytics.logistique import top_routes, delai_moyen_livraison
from dashboard.analytics.qualite import score_global, confiance_par_champ


SAMPLE_1 = {
    "fichier": "Facture_A.pdf",
    "type_document": "facture",
    "strategie_utilisee": "pdfplumber_tables",
    "metadonnees": {
        "numero_document": "A-001",
        "date_document": "2024-01-15",
        "fournisseur": {"nom": "Alpha Transport", "adresse": "Paris", "siret": None, "tva_intra": None},
        "client": {"nom": "Client X", "adresse": "Lyon"},
        "montant_ht": 5000, "montant_tva": 1000, "montant_ttc": 6000,
        "devise": "EUR", "conditions_paiement": "30j",
        "references": {"commande": "CMD-1", "contrat": None, "bon_livraison": None},
    },
    "lignes": [
        {"ligne_numero": 1, "type_matiere": "Acier", "unite": "t", "prix_unitaire": 500,
         "quantite": 10, "prix_total": 5000, "date_depart": "2024-01-10", "date_arrivee": "2024-01-12",
         "lieu_depart": "Paris", "lieu_arrivee": "Lyon",
         "confiance": {"type_matiere": 0.95, "unite": 0.9, "prix_unitaire": 0.98,
                       "quantite": 0.98, "prix_total": 0.99, "date_depart": 0.9,
                       "date_arrivee": 0.9, "lieu_depart": 0.95, "lieu_arrivee": 0.95}},
    ],
    "confiance_globale": 0.95,
    "champs_manquants": [],
    "warnings": [],
}

SAMPLE_2 = {
    "fichier": "Facture_B.pdf",
    "type_document": "facture",
    "strategie_utilisee": "ocr_tesseract",
    "metadonnees": {
        "numero_document": "B-001",
        "date_document": "2024-02-20",
        "fournisseur": {"nom": "Beta Logistics", "adresse": "Marseille", "siret": None, "tva_intra": None},
        "client": {"nom": "Client X", "adresse": "Lyon"},
        "montant_ht": 3000, "montant_tva": 600, "montant_ttc": 3600,
        "devise": "EUR", "conditions_paiement": "60j",
        "references": {"commande": "CMD-2", "contrat": None, "bon_livraison": None},
    },
    "lignes": [
        {"ligne_numero": 1, "type_matiere": "Acier", "unite": "t", "prix_unitaire": 600,
         "quantite": 5, "prix_total": 3000, "date_depart": "2024-02-15", "date_arrivee": "2024-02-18",
         "lieu_depart": "Marseille", "lieu_arrivee": "Lyon",
         "confiance": {"type_matiere": 0.7, "unite": 0.5, "prix_unitaire": 0.3,
                       "quantite": 0.4, "prix_total": 0.3, "date_depart": 0.6,
                       "date_arrivee": 0.6, "lieu_depart": 0.7, "lieu_arrivee": 0.7}},
    ],
    "confiance_globale": 0.45,
    "champs_manquants": [],
    "warnings": ["OCR quality poor on price columns"],
}


@pytest.fixture
def full_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest_extraction_json(session, SAMPLE_1)
        ingest_extraction_json(session, SAMPLE_2)
        session.commit()
        yield session
    Base.metadata.drop_all(engine)


def test_full_pipeline_achats(full_db):
    top = top_fournisseurs_by_montant(full_db, limit=5)
    assert len(top) == 2
    eco = economie_potentielle(full_db)
    # Alpha=500/t, Beta=600/t -> savings on Beta's 5t = (600-500)*5 = 500
    assert eco["total_economie"] == 500.0


def test_full_pipeline_anomalies(full_db):
    rules = [
        {"id": "CONF_001", "type": "qualite_donnees", "severite": "info", "seuil_confiance": 0.6},
    ]
    anomalies = run_anomaly_detection(full_db, rules)
    full_db.commit()
    # SAMPLE_2 has confiance 0.45 < 0.6
    assert len(anomalies) == 1
    stats = get_anomaly_stats(full_db)
    assert stats["total"] == 1


def test_full_pipeline_logistique(full_db):
    routes = top_routes(full_db, limit=5)
    assert len(routes) == 2  # Paris->Lyon, Marseille->Lyon
    delai = delai_moyen_livraison(full_db)
    assert delai["nb_trajets"] == 2


def test_full_pipeline_qualite(full_db):
    quality = score_global(full_db)
    assert quality["nb_documents"] == 2
    assert quality["pct_fiables"] == 50.0  # 1 of 2 above 0.8

    conf = confiance_par_champ(full_db)
    assert not conf.empty
