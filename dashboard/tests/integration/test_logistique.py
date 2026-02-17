import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture, EntityMapping
from dashboard.analytics.logistique import (
    top_routes,
    matrice_od,
    delai_moyen_livraison,
    opportunites_regroupement,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def logistics_data(db_session):
    f = Fournisseur(nom="Transport Co")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="t.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.9)
    db_session.add(d)
    db_session.flush()

    lignes = [
        LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="Acier",
                     lieu_depart="Sorgues", lieu_arrivee="Kallo",
                     date_depart="2024-01-05", date_arrivee="2024-01-07",
                     prix_total=1620),
        LigneFacture(document_id=d.id, ligne_numero=2, type_matiere="Acier",
                     lieu_depart="Sorgues", lieu_arrivee="Kallo",
                     date_depart="2024-01-06", date_arrivee="2024-01-08",
                     prix_total=1620),
        LigneFacture(document_id=d.id, ligne_numero=3, type_matiere="Cuivre",
                     lieu_depart="Paris", lieu_arrivee="Lyon",
                     date_depart="2024-02-01", date_arrivee="2024-02-02",
                     prix_total=500),
    ]
    db_session.add_all(lignes)
    db_session.commit()
    return db_session


def test_top_routes(logistics_data):
    result = top_routes(logistics_data, limit=5)
    assert len(result) == 2
    assert result.iloc[0]["route"] == "Sorgues \u2192 Kallo"
    assert result.iloc[0]["nb_trajets"] == 2


def test_matrice_od(logistics_data):
    result = matrice_od(logistics_data)
    assert result.loc["Sorgues", "Kallo"] == 2


def test_delai_moyen(logistics_data):
    result = delai_moyen_livraison(logistics_data)
    # Trip 1: 2 days, Trip 2: 2 days, Trip 3: 1 day → mean = 5/3
    assert abs(result["delai_moyen_jours"] - 5 / 3) < 0.01


def test_regroupement(logistics_data):
    result = opportunites_regroupement(logistics_data, fenetre_jours=7)
    # Sorgues->Kallo has 2 trips within 7 days
    assert len(result) >= 1
    assert result.iloc[0]["nb_trajets_regroupables"] == 2


# ---------------------------------------------------------------------------
# Entity resolution integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
def resolved_logistics(db_session):
    """Create logistics data with location variants and entity mappings."""
    f = Fournisseur(nom="Transport Co")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="t.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.9)
    db_session.add(d)
    db_session.flush()

    lignes = [
        # "Sorgues" and "SORGUES (84)" should resolve to "Sorgues"
        LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="Acier",
                     lieu_depart="Sorgues", lieu_arrivee="Kallo",
                     date_depart="2024-01-05", date_arrivee="2024-01-07",
                     prix_total=1620),
        LigneFacture(document_id=d.id, ligne_numero=2, type_matiere="Acier",
                     lieu_depart="SORGUES (84)", lieu_arrivee="Kallo (BE)",
                     date_depart="2024-01-06", date_arrivee="2024-01-08",
                     prix_total=1620),
        LigneFacture(document_id=d.id, ligne_numero=3, type_matiere="Cuivre",
                     lieu_depart="Paris", lieu_arrivee="Lyon",
                     date_depart="2024-02-01", date_arrivee="2024-02-02",
                     prix_total=500),
    ]
    db_session.add_all(lignes)

    # Location mappings
    db_session.add(EntityMapping(
        entity_type="location", raw_value="SORGUES (84)",
        canonical_value="Sorgues", match_mode="exact",
        status="approved", confidence=1.0,
    ))
    db_session.add(EntityMapping(
        entity_type="location", raw_value="Kallo (BE)",
        canonical_value="Kallo", match_mode="exact",
        status="approved", confidence=1.0,
    ))

    db_session.commit()
    return db_session


def test_top_routes_with_resolution(resolved_logistics):
    """Location variants merge into canonical routes."""
    result = top_routes(resolved_logistics, limit=10)

    # "Sorgues -> Kallo" and "SORGUES (84) -> Kallo (BE)" merge into one route
    routes = result["route"].tolist()
    assert "Sorgues \u2192 Kallo" in routes
    sorgues_kallo = result[result["route"] == "Sorgues \u2192 Kallo"].iloc[0]
    assert sorgues_kallo["nb_trajets"] == 2
    assert sorgues_kallo["cout_total"] == 3240


def test_matrice_od_with_resolution(resolved_logistics):
    """OD matrix uses resolved location names."""
    result = matrice_od(resolved_logistics)
    # After resolution: Sorgues->Kallo has 2 trips
    assert result.loc["Sorgues", "Kallo"] == 2
    # Variant names should not appear
    assert "SORGUES (84)" not in result.index
    assert "Kallo (BE)" not in result.columns


def test_regroupement_with_resolution(resolved_logistics):
    """Trips on variant routes now cluster together after resolution."""
    result = opportunites_regroupement(resolved_logistics, fenetre_jours=7)
    # Both Sorgues trips (original + variant) now on same resolved route
    assert len(result) >= 1
    sorgues_route = result[result["route"] == "Sorgues \u2192 Kallo"]
    assert len(sorgues_route) == 1
    assert sorgues_route.iloc[0]["nb_trajets_regroupables"] == 2


def test_no_location_mappings_backward_compat(logistics_data):
    """Without entity mappings, behavior is identical to before."""
    result = top_routes(logistics_data, limit=5)
    assert len(result) == 2
    assert result.iloc[0]["route"] == "Sorgues \u2192 Kallo"
    assert result.iloc[0]["nb_trajets"] == 2
