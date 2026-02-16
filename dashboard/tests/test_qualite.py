import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture
from dashboard.analytics.qualite import (
    score_global,
    confiance_par_champ,
    documents_par_qualite,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def quality_data(db_session):
    f = Fournisseur(nom="Q")
    db_session.add(f)
    db_session.flush()

    d1 = Document(fichier="good.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.95)
    d2 = Document(fichier="bad.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.4)
    db_session.add_all([d1, d2])
    db_session.flush()

    db_session.add(LigneFacture(
        document_id=d1.id, ligne_numero=1, type_matiere="X",
        conf_type_matiere=0.98, conf_prix_unitaire=0.95, conf_quantite=0.90,
    ))
    db_session.add(LigneFacture(
        document_id=d2.id, ligne_numero=1, type_matiere="Y",
        conf_type_matiere=0.5, conf_prix_unitaire=0.1, conf_quantite=0.2,
    ))
    db_session.commit()
    return db_session


def test_score_global(quality_data):
    result = score_global(quality_data)
    assert 0 < result["score_moyen"] < 1
    assert result["nb_documents"] == 2
    assert result["pct_fiables"] == 50.0  # 1 out of 2 above 0.8


def test_confiance_par_champ(quality_data):
    result = confiance_par_champ(quality_data)
    assert "type_matiere" in result.index
    assert result.loc["type_matiere", "moyenne"] > 0


def test_documents_par_qualite(quality_data):
    result = documents_par_qualite(quality_data)
    assert len(result) == 2
    assert result.iloc[0]["confiance_globale"] >= result.iloc[1]["confiance_globale"]
