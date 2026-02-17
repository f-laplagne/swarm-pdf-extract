import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture
from dashboard.analytics.tendances import volume_mensuel, evolution_prix_matiere


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def temporal_data(db_session):
    f = Fournisseur(nom="F1")
    db_session.add(f)
    db_session.flush()

    for month_str in ["2024-01-15", "2024-02-15", "2024-03-15"]:
        d_date = date.fromisoformat(month_str)
        month_num = d_date.month
        d = Document(fichier=f"doc_{month_str}.pdf", type_document="facture",
                     fournisseur_id=f.id, date_document=d_date,
                     montant_ht=1000 * month_num, confiance_globale=0.9)
        db_session.add(d)
        db_session.flush()
        db_session.add(LigneFacture(
            document_id=d.id, ligne_numero=1, type_matiere="Acier",
            prix_unitaire=10.0 + month_num, quantite=10, prix_total=100 + month_num * 10,
            date_depart=month_str,
        ))
    db_session.commit()
    return db_session


def test_volume_mensuel(temporal_data):
    result = volume_mensuel(temporal_data)
    assert len(result) == 3
    assert result.iloc[0]["montant_total"] > 0


def test_evolution_prix(temporal_data):
    result = evolution_prix_matiere(temporal_data, "Acier")
    assert len(result) == 3
    # Price increases each month (11, 12, 13)
    assert result.iloc[-1]["prix_unitaire_moyen"] > result.iloc[0]["prix_unitaire_moyen"]
