"""Integration test: corrections are reflected in analytics queries.

Proves that after appliquer_correction() is called, the analytics functions
(prix_moyen_par_matiere, indice_fragmentation) return the corrected value
instead of the original typo.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Document, Fournisseur, LigneFacture
from dashboard.analytics.achats import prix_moyen_par_matiere, indice_fragmentation
from dashboard.analytics.corrections import appliquer_correction


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_correction_refletee_dans_analytics(db_session):
    """After correcting type_matiere 'sble' -> 'Sable', analytics show 'Sable' not 'sble'."""
    f = Fournisseur(nom="Fournisseur Test")
    db_session.add(f)
    db_session.flush()

    d = Document(
        fichier="facture_test.pdf",
        type_document="facture",
        fournisseur_id=f.id,
        montant_ht=500.0,
        confiance_globale=0.5,
    )
    db_session.add(d)
    db_session.flush()

    l = LigneFacture(
        document_id=d.id,
        ligne_numero=1,
        type_matiere="sble",
        prix_unitaire=20.0,
        quantite=10.0,
        prix_total=200.0,
        conf_type_matiere=0.45,
    )
    db_session.add(l)
    db_session.commit()

    # BEFORE correction: analytics show the typo "sble"
    result_avant = prix_moyen_par_matiere(db_session)
    assert "sble" in result_avant["type_matiere"].values, (
        "Expected 'sble' in analytics before correction"
    )
    assert "Sable" not in result_avant["type_matiere"].values, (
        "Expected 'Sable' NOT in analytics before correction"
    )

    # Apply correction
    appliquer_correction(db_session, l.id, {"type_matiere": "Sable"})
    db_session.expire_all()

    # AFTER correction: analytics show "Sable", not "sble"
    result_apres = prix_moyen_par_matiere(db_session)
    assert "Sable" in result_apres["type_matiere"].values, (
        "Expected 'Sable' in analytics after correction"
    )
    assert "sble" not in result_apres["type_matiere"].values, (
        "Expected 'sble' NOT in analytics after correction"
    )


def test_correction_met_confiance_a_1(db_session):
    """After correction, conf field is 1.0 and confiance_globale is recalculated."""
    f = Fournisseur(nom="F")
    db_session.add(f)
    db_session.flush()

    d = Document(
        fichier="t.pdf",
        type_document="facture",
        fournisseur_id=f.id,
        confiance_globale=0.4,
    )
    db_session.add(d)
    db_session.flush()

    l = LigneFacture(
        document_id=d.id,
        ligne_numero=1,
        type_matiere="sble",
        conf_type_matiere=0.45,
    )
    db_session.add(l)
    db_session.commit()

    appliquer_correction(db_session, l.id, {"type_matiere": "Sable"})
    db_session.expire_all()

    updated = db_session.get(LigneFacture, l.id)
    assert updated.conf_type_matiere == 1.0

    updated_doc = db_session.get(Document, d.id)
    # Only conf_type_matiere is non-None, so global = 1.0 / 1 = 1.0
    assert updated_doc.confiance_globale == 1.0
