import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture, Anomalie


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_create_fournisseur(db_session):
    f = Fournisseur(nom="Transports Fockedey s.a.", siret=None, tva_intra="BE0439.237.690")
    db_session.add(f)
    db_session.commit()
    assert f.id is not None
    assert f.nom == "Transports Fockedey s.a."


def test_create_document_with_fournisseur(db_session):
    f = Fournisseur(nom="Fockedey")
    db_session.add(f)
    db_session.flush()

    d = Document(
        fichier="facture_test.pdf",
        type_document="facture",
        fournisseur_id=f.id,
        montant_ht=19597.46,
        confiance_globale=0.96,
    )
    db_session.add(d)
    db_session.commit()
    assert d.id is not None
    assert d.fournisseur.nom == "Fockedey"


def test_create_ligne_facture(db_session):
    f = Fournisseur(nom="Test")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="test.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.9)
    db_session.add(d)
    db_session.flush()

    ligne = LigneFacture(
        document_id=d.id,
        ligne_numero=1,
        type_matiere="Nitrate Ethyle Hexyl",
        unite="voyage",
        prix_unitaire=1620.00,
        quantite=1,
        prix_total=1620.00,
        date_depart="2024-11-05",
        lieu_depart="Sorgues",
        lieu_arrivee="Kallo",
        conf_type_matiere=0.98,
        conf_prix_unitaire=0.99,
    )
    db_session.add(ligne)
    db_session.commit()
    assert ligne.id is not None
    assert d.lignes[0].type_matiere == "Nitrate Ethyle Hexyl"


def test_create_anomalie(db_session):
    f = Fournisseur(nom="Test")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="test.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.5)
    db_session.add(d)
    db_session.flush()

    a = Anomalie(
        document_id=d.id,
        regle_id="CONF_001",
        type_anomalie="qualite_donnees",
        severite="info",
        description="Confiance globale < 0.6",
    )
    db_session.add(a)
    db_session.commit()
    assert a.id is not None
    assert len(d.anomalies) == 1
