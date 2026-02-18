import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Base, CorrectionLog, Document, Fournisseur, LigneFacture
from dashboard.analytics.corrections import suggestion_pour_champ


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def correction_history(db_session):
    f = Fournisseur(nom="Four")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="a.pdf", type_document="facture", fournisseur_id=f.id)
    db_session.add(d)
    db_session.flush()
    l = LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="sble")
    db_session.add(l)
    db_session.flush()
    for _ in range(3):
        db_session.add(CorrectionLog(
            ligne_id=l.id, document_id=d.id,
            champ="type_matiere", ancienne_valeur="sble", nouvelle_valeur="Sable",
            corrige_par="admin",
        ))
    db_session.add(CorrectionLog(
        ligne_id=l.id, document_id=d.id,
        champ="type_matiere", ancienne_valeur="sble", nouvelle_valeur="SABLE",
        corrige_par="admin",
    ))
    db_session.commit()
    return db_session


def test_suggestion_retourne_valeur_la_plus_frequente(correction_history):
    result = suggestion_pour_champ(correction_history, "type_matiere", "sble")
    assert result == "Sable"


def test_suggestion_retourne_none_si_pas_historique(db_session):
    result = suggestion_pour_champ(db_session, "type_matiere", "xyz_inconnu")
    assert result is None
