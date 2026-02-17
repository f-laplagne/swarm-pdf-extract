"""Tests for dashboard.analytics.transport — shipment listing."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture
from dashboard.analytics.transport import liste_expeditions


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def shipment_data(db_session):
    f = Fournisseur(nom="TransportCo")
    db_session.add(f)
    db_session.flush()

    d = Document(
        fichier="bl_001.pdf", type_document="bon_livraison",
        fournisseur_id=f.id, montant_ht=5000, confiance_globale=0.9,
    )
    db_session.add(d)
    db_session.flush()

    db_session.add(LigneFacture(
        document_id=d.id, ligne_numero=1, type_matiere="Acier",
        prix_unitaire=50.0, quantite=100, prix_total=5000.0,
        date_depart="2024-03-01", date_arrivee="2024-03-03",
        lieu_depart="Sorgues (F-84706)", lieu_arrivee="Dunkerque (59140)",
    ))
    db_session.add(LigneFacture(
        document_id=d.id, ligne_numero=2, type_matiere="Cuivre",
        prix_unitaire=80.0, quantite=50, prix_total=4000.0,
        date_depart="2024-03-05", date_arrivee=None,
        lieu_depart="Lyon", lieu_arrivee="Marseille",
    ))
    # Line without locations — should be excluded
    db_session.add(LigneFacture(
        document_id=d.id, ligne_numero=3, type_matiere="Zinc",
        prix_unitaire=30.0, quantite=200, prix_total=6000.0,
    ))
    db_session.commit()
    return db_session


def test_liste_expeditions(shipment_data):
    df = liste_expeditions(shipment_data)
    # Only 2 lines have both lieu_depart and lieu_arrivee
    assert len(df) == 2
    assert "route" in df.columns
    assert "resolved_lieu_depart" in df.columns
    assert "fournisseur" in df.columns
    assert df["fournisseur"].iloc[0] == "TransportCo"


def test_liste_expeditions_delay(shipment_data):
    df = liste_expeditions(shipment_data)
    # First line has both dates: 2024-03-01 -> 2024-03-03 = 2 days
    row_with_dates = df[df["date_arrivee"].notna()].iloc[0]
    assert row_with_dates["delai_jours"] == 2
    # Second line has no date_arrivee
    row_no_arrivee = df[df["date_arrivee"].isna()].iloc[0]
    assert row_no_arrivee["delai_jours"] is None


def test_liste_expeditions_empty(db_session):
    df = liste_expeditions(db_session)
    assert df.empty
