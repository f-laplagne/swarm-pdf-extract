import json
import os
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture
from dashboard.data.ingestion import ingest_extraction_json, ingest_directory


SAMPLE_EXTRACTION = {
    "fichier": "Facture 24-110193.pdf",
    "type_document": "facture",
    "strategie_utilisee": "pdfplumber_tables",
    "metadonnees": {
        "numero_document": "24/110193",
        "date_document": "2024-11-30",
        "fournisseur": {
            "nom": "Transports Fockedey s.a.",
            "adresse": "Zone Industrielle, 7900 Leuze",
            "siret": None,
            "tva_intra": "BE0439.237.690"
        },
        "client": {
            "nom": "Eurenco France SAS",
            "adresse": "F-84700 Sorgues"
        },
        "montant_ht": 19597.46,
        "montant_tva": 0,
        "montant_ttc": 19597.46,
        "devise": "EUR",
        "conditions_paiement": "30 jours",
        "references": {
            "commande": "4600039119",
            "contrat": None,
            "bon_livraison": None
        }
    },
    "lignes": [
        {
            "ligne_numero": 1,
            "type_matiere": "Nitrate Ethyle Hexyl",
            "unite": "voyage",
            "prix_unitaire": 1620.00,
            "quantite": 1,
            "prix_total": 1620.00,
            "date_depart": "2024-11-05",
            "date_arrivee": "2024-11-07",
            "lieu_depart": "Sorgues",
            "lieu_arrivee": "Kallo",
            "confiance": {
                "type_matiere": 0.98,
                "unite": 0.95,
                "prix_unitaire": 0.99,
                "quantite": 0.99,
                "prix_total": 0.99,
                "date_depart": 0.95,
                "date_arrivee": 0.95,
                "lieu_depart": 0.98,
                "lieu_arrivee": 0.98
            }
        }
    ],
    "confiance_globale": 0.96,
    "champs_manquants": [],
    "warnings": []
}


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_ingest_single_extraction(db_session):
    doc = ingest_extraction_json(db_session, SAMPLE_EXTRACTION)
    db_session.commit()

    assert doc.fichier == "Facture 24-110193.pdf"
    assert doc.montant_ht == 19597.46
    assert doc.fournisseur.nom == "Transports Fockedey s.a."
    assert len(doc.lignes) == 1
    assert doc.lignes[0].type_matiere == "Nitrate Ethyle Hexyl"
    assert doc.lignes[0].conf_prix_unitaire == 0.99


def test_ingest_deduplicates_fournisseur(db_session):
    ingest_extraction_json(db_session, SAMPLE_EXTRACTION)
    db_session.commit()

    # Ingest a second doc with same fournisseur
    data2 = {**SAMPLE_EXTRACTION, "fichier": "Facture_2.pdf"}
    data2["metadonnees"] = {**SAMPLE_EXTRACTION["metadonnees"], "numero_document": "24/999"}
    ingest_extraction_json(db_session, data2)
    db_session.commit()

    fournisseurs = db_session.query(Fournisseur).all()
    assert len(fournisseurs) == 1  # same fournisseur reused


def test_ingest_skips_duplicate_fichier(db_session):
    ingest_extraction_json(db_session, SAMPLE_EXTRACTION)
    db_session.commit()

    # Same file again should skip
    result = ingest_extraction_json(db_session, SAMPLE_EXTRACTION)
    assert result is None


def test_ingest_directory(db_session, tmp_path):
    # Write two extraction files
    for i, name in enumerate(["doc1_extraction.json", "doc2_extraction.json"]):
        data = {**SAMPLE_EXTRACTION, "fichier": f"doc{i}.pdf"}
        data["metadonnees"] = {**SAMPLE_EXTRACTION["metadonnees"], "numero_document": f"NUM-{i}"}
        (tmp_path / name).write_text(json.dumps(data))

    # Also write a classification file that should be ignored
    (tmp_path / "doc1_classification.json").write_text("{}")

    stats = ingest_directory(db_session, str(tmp_path))
    assert stats["ingested"] == 2
    assert stats["skipped"] == 0
    assert stats["errors"] == 0
