import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import (
    Base, CorrectionLog, Document, Fournisseur, LigneFacture,
)
from dashboard.adapters.outbound.sqlalchemy_correction_repo import SqlAlchemyCorrectionRepository
from domain.models import Correction


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def ligne_fixture(db_session):
    f = Fournisseur(nom="TestFour")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="test.pdf", type_document="facture", fournisseur_id=f.id)
    db_session.add(d)
    db_session.flush()
    l = LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="sble", conf_type_matiere=0.45)
    db_session.add(l)
    db_session.commit()
    return l


def test_sauvegarder_cree_correction_log(db_session, ligne_fixture):
    repo = SqlAlchemyCorrectionRepository(db_session)
    c = Correction(
        ligne_id=ligne_fixture.id,
        champ="type_matiere",
        valeur_originale="sble",
        valeur_corrigee="Sable",
        confiance_originale=0.45,
        corrige_par="admin",
    )
    saved = repo.sauvegarder(c)
    assert saved.id is not None
    log = db_session.get(CorrectionLog, saved.id)
    assert log is not None
    assert log.nouvelle_valeur == "Sable"


def test_historique_retourne_corrections_pour_champ(db_session, ligne_fixture):
    repo = SqlAlchemyCorrectionRepository(db_session)
    for _ in range(2):
        repo.sauvegarder(Correction(
            ligne_id=ligne_fixture.id,
            champ="type_matiere", valeur_originale="sble", valeur_corrigee="Sable",
            confiance_originale=0.4, corrige_par="admin",
        ))
    history = repo.historique("type_matiere", "sble")
    assert len(history) == 2
    assert all(c.valeur_corrigee == "Sable" for c in history)


def test_historique_vide_si_aucune_correction(db_session, ligne_fixture):
    repo = SqlAlchemyCorrectionRepository(db_session)
    history = repo.historique("unite", "kg")
    assert history == []
