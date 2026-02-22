"""Integration tests for the new functions added to 11_verification_pdf.py."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Base, Document, Fournisseur, LigneFacture


@pytest.fixture
def engine():
    """In-memory SQLite engine with schema."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    s = Session(engine)
    yield s
    s.close()


@pytest.fixture
def doc_with_lines(session):
    """A document with 3 lines in the DB."""
    fournisseur = Fournisseur(nom="Test SA")
    session.add(fournisseur)
    session.flush()

    doc = Document(
        fichier="facture_test.pdf",
        type_document="facture",
        confiance_globale=0.45,
        fournisseur_id=fournisseur.id,
    )
    session.add(doc)
    session.flush()

    lignes = [
        LigneFacture(document_id=doc.id, ligne_numero=1, type_matiere="Acier",
                     conf_type_matiere=0.8),
        LigneFacture(document_id=doc.id, ligne_numero=2, type_matiere="Cuivre",
                     conf_type_matiere=0.3),
        LigneFacture(document_id=doc.id, ligne_numero=3, type_matiere="Alu",
                     conf_type_matiere=0.4),
    ]
    for l in lignes:
        session.add(l)
    session.commit()
    return doc, lignes


# ── get_ligne_ids ────────────────────────────────────────────────────────────

def test_get_ligne_ids_returns_mapping(engine, doc_with_lines):
    """get_ligne_ids returns {ligne_numero: ligne_id} for a known document."""
    from dashboard.pages._verification_helpers import get_ligne_ids  # will be extracted

    doc, lignes = doc_with_lines
    result = get_ligne_ids(engine, "facture_test.pdf")

    assert isinstance(result, dict)
    assert len(result) == 3
    for ligne in lignes:
        assert ligne.ligne_numero in result
        assert result[ligne.ligne_numero] == ligne.id


def test_get_ligne_ids_unknown_document_returns_empty(engine):
    """get_ligne_ids returns {} for a document not in the DB."""
    from dashboard.pages._verification_helpers import get_ligne_ids

    result = get_ligne_ids(engine, "inexistant.pdf")
    assert result == {}


# ── _handle_correction_post ──────────────────────────────────────────────────

def test_handle_correction_post_valid(engine, doc_with_lines):
    """Valid body persists correction and returns {success: true, correction_id: N}."""
    from dashboard.pages._verification_helpers import handle_correction_post

    doc, lignes = doc_with_lines
    ligne_faible = lignes[1]  # ligne_numero=2, conf_type_matiere=0.3

    body = {
        "ligne_id": ligne_faible.id,
        "champ": "type_matiere",
        "valeur_originale": "Cuivre",
        "valeur_corrigee": "Cuivre rouge recyclé",
        "confiance_originale": 0.3,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 200
    assert response["success"] is True
    assert "correction_id" in response

    # Verify DB was actually updated
    with Session(engine) as s:
        ligne = s.get(LigneFacture, ligne_faible.id)
        assert ligne.type_matiere == "Cuivre rouge recyclé"
        assert ligne.conf_type_matiere == 1.0


def test_handle_correction_post_invalid_ligne(engine):
    """Unknown ligne_id returns 404 with error message."""
    from dashboard.pages._verification_helpers import handle_correction_post

    body = {
        "ligne_id": 99999,
        "champ": "type_matiere",
        "valeur_originale": "x",
        "valeur_corrigee": "y",
        "confiance_originale": 0.2,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 404
    assert response["success"] is False
    assert "error" in response


def test_handle_correction_post_invalid_champ(engine, doc_with_lines):
    """Unknown field name returns 400."""
    from dashboard.pages._verification_helpers import handle_correction_post

    doc, lignes = doc_with_lines
    body = {
        "ligne_id": lignes[0].id,
        "champ": "champ_inexistant",
        "valeur_originale": "x",
        "valeur_corrigee": "y",
        "confiance_originale": 0.2,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 400
    assert response["success"] is False


def test_handle_correction_post_missing_field(engine):
    """Missing required field returns 400."""
    from dashboard.pages._verification_helpers import handle_correction_post

    status_code, response = handle_correction_post({}, engine)

    assert status_code == 400
    assert response["success"] is False
