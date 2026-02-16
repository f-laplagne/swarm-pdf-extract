import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture, EntityMapping
from dashboard.analytics.achats import (
    top_fournisseurs_by_montant,
    prix_moyen_par_matiere,
    ecarts_prix_fournisseurs,
    indice_fragmentation,
    economie_potentielle,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def sample_data(db_session):
    f1 = Fournisseur(nom="Fournisseur A")
    f2 = Fournisseur(nom="Fournisseur B")
    db_session.add_all([f1, f2])
    db_session.flush()

    d1 = Document(fichier="f1.pdf", type_document="facture", fournisseur_id=f1.id,
                  montant_ht=5000, confiance_globale=0.9)
    d2 = Document(fichier="f2.pdf", type_document="facture", fournisseur_id=f2.id,
                  montant_ht=3000, confiance_globale=0.9)
    db_session.add_all([d1, d2])
    db_session.flush()

    lignes = [
        LigneFacture(document_id=d1.id, ligne_numero=1, type_matiere="Acier",
                     unite="kg", prix_unitaire=10.0, quantite=100, prix_total=1000.0),
        LigneFacture(document_id=d1.id, ligne_numero=2, type_matiere="Cuivre",
                     unite="kg", prix_unitaire=25.0, quantite=50, prix_total=1250.0),
        LigneFacture(document_id=d2.id, ligne_numero=1, type_matiere="Acier",
                     unite="kg", prix_unitaire=12.0, quantite=200, prix_total=2400.0),
    ]
    db_session.add_all(lignes)
    db_session.commit()
    return db_session


def test_top_fournisseurs(sample_data):
    result = top_fournisseurs_by_montant(sample_data, limit=5)
    assert len(result) == 2
    assert result.iloc[0]["fournisseur"] == "Fournisseur A"


def test_prix_moyen_par_matiere(sample_data):
    result = prix_moyen_par_matiere(sample_data)
    acier = result[result["type_matiere"] == "Acier"].iloc[0]
    # Weighted average: (10*100 + 12*200) / (100+200) = 3400/300 = 11.33
    assert abs(acier["prix_unitaire_moyen"] - 11.33) < 0.01


def test_ecarts_prix(sample_data):
    result = ecarts_prix_fournisseurs(sample_data)
    # Acier: A=10, B=12 → ecart = (12-10)/10 = 20%
    acier_row = result[result["type_matiere"] == "Acier"]
    assert len(acier_row) > 0


def test_fragmentation(sample_data):
    result = indice_fragmentation(sample_data)
    acier = result[result["type_matiere"] == "Acier"].iloc[0]
    assert acier["nb_fournisseurs"] == 2
    cuivre = result[result["type_matiere"] == "Cuivre"].iloc[0]
    assert cuivre["nb_fournisseurs"] == 1


def test_economie_potentielle(sample_data):
    result = economie_potentielle(sample_data)
    # Acier: best price=10, Fournisseur B pays 12 for 200 units → savings = (12-10)*200 = 400
    assert result["total_economie"] > 0


# ---------------------------------------------------------------------------
# Entity resolution integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
def resolved_data(db_session):
    """Create data with supplier/material variants and entity mappings."""
    # Two suppliers that are actually the same entity
    f1 = Fournisseur(nom="Alpha")
    f2 = Fournisseur(nom="Alpha Transport")
    f3 = Fournisseur(nom="Beta Logistics")
    db_session.add_all([f1, f2, f3])
    db_session.flush()

    d1 = Document(fichier="r1.pdf", type_document="facture", fournisseur_id=f1.id,
                  montant_ht=4000, confiance_globale=0.9)
    d2 = Document(fichier="r2.pdf", type_document="facture", fournisseur_id=f2.id,
                  montant_ht=6000, confiance_globale=0.9)
    d3 = Document(fichier="r3.pdf", type_document="facture", fournisseur_id=f3.id,
                  montant_ht=2000, confiance_globale=0.9)
    db_session.add_all([d1, d2, d3])
    db_session.flush()

    lignes = [
        # "Acier inox" and "Acier Inoxydable" should resolve to "Acier Inoxydable"
        LigneFacture(document_id=d1.id, ligne_numero=1, type_matiere="Acier inox",
                     unite="kg", prix_unitaire=10.0, quantite=100, prix_total=1000.0),
        LigneFacture(document_id=d2.id, ligne_numero=1, type_matiere="Acier Inoxydable",
                     unite="kg", prix_unitaire=15.0, quantite=200, prix_total=3000.0),
        LigneFacture(document_id=d3.id, ligne_numero=1, type_matiere="Cuivre",
                     unite="kg", prix_unitaire=20.0, quantite=50, prix_total=1000.0),
    ]
    db_session.add_all(lignes)

    # Create entity mappings: merge suppliers
    db_session.add(EntityMapping(
        entity_type="supplier", raw_value="Alpha",
        canonical_value="Alpha Transport", match_mode="exact",
        status="approved", confidence=1.0,
    ))
    # Material mapping: "Acier inox" -> "Acier Inoxydable"
    db_session.add(EntityMapping(
        entity_type="material", raw_value="Acier inox",
        canonical_value="Acier Inoxydable", match_mode="exact",
        status="approved", confidence=1.0,
    ))

    db_session.commit()
    return db_session


def test_top_fournisseurs_with_resolution(resolved_data):
    """After mapping 'Alpha' -> 'Alpha Transport', they appear as one entry."""
    result = top_fournisseurs_by_montant(resolved_data, limit=10)
    fournisseur_names = result["fournisseur"].tolist()

    # "Alpha" and "Alpha Transport" merged into "Alpha Transport"
    assert "Alpha" not in fournisseur_names
    assert "Alpha Transport" in fournisseur_names

    # The merged entry should have combined montant: 4000 + 6000 = 10000
    merged = result[result["fournisseur"] == "Alpha Transport"].iloc[0]
    assert merged["montant_total"] == 10000
    assert merged["nb_documents"] == 2


def test_prix_moyen_with_resolution(resolved_data):
    """Material variants resolve to canonical name."""
    result = prix_moyen_par_matiere(resolved_data)

    # "Acier inox" and "Acier Inoxydable" merged into "Acier Inoxydable"
    assert "Acier inox" not in result["type_matiere"].values
    assert "Acier Inoxydable" in result["type_matiere"].values

    acier = result[result["type_matiere"] == "Acier Inoxydable"].iloc[0]
    # Weighted average: (10*100 + 15*200) / (100+200) = 4000/300 = 13.33
    assert abs(acier["prix_unitaire_moyen"] - 13.33) < 0.01


def test_fragmentation_with_resolution(resolved_data):
    """After supplier resolution, 'Acier Inoxydable' has 2 resolved suppliers."""
    result = indice_fragmentation(resolved_data)
    acier = result[result["type_matiere"] == "Acier Inoxydable"].iloc[0]
    # "Alpha" -> "Alpha Transport" and "Alpha Transport" -> "Alpha Transport"
    # So Acier Inoxydable has 1 resolved supplier (Alpha Transport)
    # Only Cuivre from Beta Logistics is a separate supplier
    assert acier["nb_fournisseurs"] == 1


def test_no_mappings_backward_compat(sample_data):
    """Without entity mappings, behavior is identical to before."""
    # sample_data fixture has no EntityMapping entries
    result = top_fournisseurs_by_montant(sample_data, limit=5)
    assert len(result) == 2
    assert result.iloc[0]["fournisseur"] == "Fournisseur A"

    result_prix = prix_moyen_par_matiere(sample_data)
    acier = result_prix[result_prix["type_matiere"] == "Acier"].iloc[0]
    assert abs(acier["prix_unitaire_moyen"] - 11.33) < 0.01
