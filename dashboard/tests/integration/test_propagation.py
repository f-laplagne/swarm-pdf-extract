import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Base, Document, Fournisseur, LigneFacture
from dashboard.analytics.corrections import propager_correction


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def multi_ligne_data(db_session):
    f = Fournisseur(nom="Four")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="b.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.5)
    db_session.add(d)
    db_session.flush()
    l1 = LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="sble", conf_type_matiere=0.45)
    l2 = LigneFacture(document_id=d.id, ligne_numero=2, type_matiere="sble", conf_type_matiere=0.30)
    l3 = LigneFacture(document_id=d.id, ligne_numero=3, type_matiere="Sable", conf_type_matiere=1.0)
    db_session.add_all([l1, l2, l3])
    db_session.commit()
    return db_session, d, [l1, l2, l3]


def test_propager_corrige_toutes_lignes_eligibles(multi_ligne_data):
    session, doc, lignes = multi_ligne_data
    count = propager_correction(
        session, champ="type_matiere",
        valeur_originale="sble", valeur_corrigee="Sable",
        seuil=0.70,
    )
    assert count == 2
    session.expire_all()
    assert session.get(LigneFacture, lignes[0].id).type_matiere == "Sable"
    assert session.get(LigneFacture, lignes[1].id).type_matiere == "Sable"


def test_propager_remet_confiance_a_1(multi_ligne_data):
    session, _, lignes = multi_ligne_data
    propager_correction(session, "type_matiere", "sble", "Sable")
    session.expire_all()
    assert session.get(LigneFacture, lignes[0].id).conf_type_matiere == 1.0
    assert session.get(LigneFacture, lignes[1].id).conf_type_matiere == 1.0


def test_propager_ne_touche_pas_lignes_confiance_haute(db_session):
    f = Fournisseur(nom="F2")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="c.pdf", type_document="facture", fournisseur_id=f.id)
    db_session.add(d)
    db_session.flush()
    l = LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="sble", conf_type_matiere=0.95)
    db_session.add(l)
    db_session.commit()
    count = propager_correction(db_session, "type_matiere", "sble", "Sable", seuil=0.70)
    assert count == 0
