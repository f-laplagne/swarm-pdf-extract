#!/usr/bin/env python3
"""Load sample data with known low-confidence extractions for demo purposes.

Usage:
    PYTHONPATH=. python scripts/load_demo_data.py

Creates 3 documents with mixed confidence scores in the DB.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.orm import Session

from dashboard.data.db import get_engine, init_db
from dashboard.adapters.outbound.sqlalchemy_models import (
    Base, Document, Fournisseur, LigneFacture,
)

DB_URL = "sqlite:///dashboard/data/rationalize.db"


def main():
    engine = get_engine(DB_URL)
    init_db(engine)

    with Session(engine) as session:
        # Fournisseurs
        f1 = Fournisseur(nom="Transport Durand SARL")
        f2 = Fournisseur(nom="Chimex SA")
        session.add_all([f1, f2])
        session.flush()

        # Document 1: mostly low confidence (scanned invoice with OCR errors)
        d1 = Document(
            fichier="FACTURE_DEMO_001.pdf", type_document="facture",
            fournisseur_id=f1.id, confiance_globale=0.42,
        )
        session.add(d1)
        session.flush()
        session.add_all([
            LigneFacture(
                document_id=d1.id, ligne_numero=1,
                type_matiere="sble fin", unite="T", prix_unitaire=45.0,
                quantite=10.0, prix_total=450.0,
                lieu_depart="Marseile", lieu_arrivee="Lyon",
                conf_type_matiere=0.35, conf_unite=0.80, conf_prix_unitaire=0.40,
                conf_quantite=0.90, conf_prix_total=0.40,
                conf_lieu_depart=0.30, conf_lieu_arrivee=0.85,
            ),
            LigneFacture(
                document_id=d1.id, ligne_numero=2,
                type_matiere="gravir", unite="M3", prix_unitaire=32.0,
                quantite=5.0, prix_total=160.0,
                lieu_depart="Marseile", lieu_arrivee="Lyon",
                conf_type_matiere=0.25, conf_unite=0.70, conf_prix_unitaire=0.55,
                conf_quantite=0.85, conf_prix_total=0.55,
                conf_lieu_depart=0.30, conf_lieu_arrivee=0.85,
            ),
        ])

        # Document 2: mixed confidence
        d2 = Document(
            fichier="FACTURE_DEMO_002.pdf", type_document="facture",
            fournisseur_id=f2.id, confiance_globale=0.68,
        )
        session.add(d2)
        session.flush()
        session.add_all([
            LigneFacture(
                document_id=d2.id, ligne_numero=1,
                type_matiere="Acide sulfurique", unite="L", prix_unitaire=12.50,
                quantite=200.0, prix_total=2500.0,
                conf_type_matiere=0.90, conf_unite=0.88, conf_prix_unitaire=0.75,
                conf_quantite=0.92, conf_prix_total=0.75,
            ),
            LigneFacture(
                document_id=d2.id, ligne_numero=2,
                type_matiere="soude caustiq", unite="KG", prix_unitaire=8.0,
                quantite=50.0, prix_total=400.0,
                conf_type_matiere=0.40, conf_unite=0.85, conf_prix_unitaire=0.60,
                conf_quantite=0.88, conf_prix_total=0.60,
            ),
        ])

        # Document 3: high confidence (for contrast)
        d3 = Document(
            fichier="FACTURE_DEMO_003.pdf", type_document="facture",
            fournisseur_id=f1.id, confiance_globale=0.95,
        )
        session.add(d3)
        session.flush()
        session.add(LigneFacture(
            document_id=d3.id, ligne_numero=1,
            type_matiere="Sable fin", unite="T", prix_unitaire=45.0,
            quantite=20.0, prix_total=900.0,
            conf_type_matiere=0.98, conf_unite=0.95, conf_prix_unitaire=0.97,
            conf_quantite=0.99, conf_prix_total=0.97,
            lieu_depart="Marseille", lieu_arrivee="Lyon",
            conf_lieu_depart=0.95, conf_lieu_arrivee=0.96,
        ))

        session.commit()
        print("Demo data loaded: 3 documents, 5 lines with mixed confidence scores.")
        print("Run: PYTHONPATH=. streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
