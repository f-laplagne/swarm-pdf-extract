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


# ── build_extraction_panel editable cells ────────────────────────────────────

def _make_ext(lignes_data: list[dict]) -> dict:
    """Build a minimal extraction dict matching the JSON schema."""
    return {
        "metadonnees": {"numero_document": "TEST-001", "date_document": "2024-01-01"},
        "lignes": lignes_data,
        "confiance_globale": 0.5,
        "warnings": [],
        "champs_manquants": [],
    }


def _palette():
    """Minimal palette dict for build_extraction_panel."""
    return dict(
        card_bg="#fff", border="#ccc", border_light="#eee",
        txt_p="#000", txt_s="#666", txt_m="#999", txt_dim="#aaa",
        txt_num="#000", hdr_bg="#f5f5f5", row_even="#fff", row_odd="#f9f9f9",
        alert_bg="#fff", alert_border="#f00", notes_bg="#f5f5f5", notes_border="#ccc",
    )


def _conf_colors():
    return {
        "absent":  ("#ff4d4d", "#2a1010"),
        "faible":  ("#ff8c42", "#2a1a0a"),
        "moyen":   ("#f0c040", "#2a220a"),
        "bon":     ("#52c77f", "#0a2018"),
        "parfait": ("#34d399", "#061a12"),
    }


def test_editable_cell_rendered_when_conf_below_threshold(engine, doc_with_lines):
    """Cells with conf < 0.5 get class cell-editable and data-ligne-id attribute."""
    from dashboard.pages.verification_pdf_panel import build_extraction_panel

    doc, lignes = doc_with_lines
    # ligne_numero=2 has conf_type_matiere=0.3 → should be editable
    ligne_faible = lignes[1]

    ext = _make_ext([
        {"ligne_numero": 2, "type_matiere": "Cuivre",
         "confiance": {"type_matiere": 0.3, "unite": 0.9}},
    ])

    ligne_ids = {2: ligne_faible.id}
    html = build_extraction_panel(ext, _palette(), _conf_colors(), ligne_ids=ligne_ids)

    assert f'data-ligne-id="{ligne_faible.id}"' in html
    assert 'data-champ="type_matiere"' in html
    assert 'cell-editable' in html


def test_no_editable_cell_when_conf_above_threshold(engine, doc_with_lines):
    """Cells with conf >= 0.5 are NOT editable even if ligne_id is provided."""
    from dashboard.pages.verification_pdf_panel import build_extraction_panel

    doc, lignes = doc_with_lines
    ligne = lignes[0]  # conf_type_matiere=0.8

    ext = _make_ext([
        {"ligne_numero": 1, "type_matiere": "Acier",
         "confiance": {"type_matiere": 0.8}},
    ])

    ligne_ids = {1: ligne.id}
    html = build_extraction_panel(ext, _palette(), _conf_colors(), ligne_ids=ligne_ids)

    # High-confidence cell should NOT have editable class
    assert 'cell-editable' not in html or f'data-champ="type_matiere"' not in html


def test_no_editable_cell_when_no_ligne_id(engine):
    """Cells with conf < 0.5 but no ligne_id mapping are read-only (graceful fallback)."""
    from dashboard.pages.verification_pdf_panel import build_extraction_panel

    ext = _make_ext([
        {"ligne_numero": 1, "type_matiere": "Cuivre",
         "confiance": {"type_matiere": 0.2}},
    ])

    html = build_extraction_panel(ext, _palette(), _conf_colors(), ligne_ids={})

    assert 'cell-editable' not in html


# ── Validation des types et des règles métier ─────────────────────────────────

@pytest.fixture
def doc_with_dates(session):
    """A document with one line that has both date_depart and date_arrivee set."""
    fournisseur = Fournisseur(nom="Transport SA")
    session.add(fournisseur)
    session.flush()

    doc = Document(
        fichier="transport_test.pdf",
        type_document="bon_livraison",
        confiance_globale=0.4,
        fournisseur_id=fournisseur.id,
    )
    session.add(doc)
    session.flush()

    ligne = LigneFacture(
        document_id=doc.id,
        ligne_numero=1,
        date_depart="2024-05-10",
        date_arrivee="2024-05-15",
        conf_date_depart=0.3,
        conf_date_arrivee=0.3,
        prix_unitaire=100.0,
        conf_prix_unitaire=0.3,
    )
    session.add(ligne)
    session.commit()
    return doc, ligne


def test_handle_correction_post_date_format_invalide(engine, doc_with_dates):
    """A date value not matching YYYY-MM-DD returns 400."""
    from dashboard.pages._verification_helpers import handle_correction_post

    _, ligne = doc_with_dates
    body = {
        "ligne_id": ligne.id,
        "champ": "date_arrivee",
        "valeur_corrigee": "15/05/2024",  # wrong format
        "confiance_originale": 0.3,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 400
    assert response["success"] is False
    assert "date" in response["error"].lower()


def test_handle_correction_post_date_arrivee_avant_date_depart(engine, doc_with_dates):
    """Setting date_arrivee earlier than existing date_depart returns 400."""
    from dashboard.pages._verification_helpers import handle_correction_post

    _, ligne = doc_with_dates  # date_depart="2024-05-10"
    body = {
        "ligne_id": ligne.id,
        "champ": "date_arrivee",
        "valeur_corrigee": "2024-05-05",  # before date_depart
        "confiance_originale": 0.3,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 400
    assert response["success"] is False
    assert "antérieure" in response["error"] or "avant" in response["error"] or "départ" in response["error"]


def test_handle_correction_post_date_depart_apres_date_arrivee(engine, doc_with_dates):
    """Setting date_depart later than existing date_arrivee returns 400."""
    from dashboard.pages._verification_helpers import handle_correction_post

    _, ligne = doc_with_dates  # date_arrivee="2024-05-15"
    body = {
        "ligne_id": ligne.id,
        "champ": "date_depart",
        "valeur_corrigee": "2024-05-20",  # after date_arrivee
        "confiance_originale": 0.3,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 400
    assert response["success"] is False
    assert "arrivée" in response["error"] or "après" in response["error"] or "arrivee" in response["error"]


def test_handle_correction_post_date_valide_acceptee(engine, doc_with_dates):
    """A date within valid range is accepted."""
    from dashboard.pages._verification_helpers import handle_correction_post

    _, ligne = doc_with_dates  # date_depart="2024-05-10", date_arrivee="2024-05-15"
    body = {
        "ligne_id": ligne.id,
        "champ": "date_arrivee",
        "valeur_corrigee": "2024-05-12",  # between depart and 15
        "confiance_originale": 0.3,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 200
    assert response["success"] is True


def test_handle_correction_post_float_invalide(engine, doc_with_dates):
    """A non-numeric value for a float field returns 400."""
    from dashboard.pages._verification_helpers import handle_correction_post

    _, ligne = doc_with_dates
    body = {
        "ligne_id": ligne.id,
        "champ": "prix_unitaire",
        "valeur_corrigee": "pas_un_nombre",
        "confiance_originale": 0.3,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 400
    assert response["success"] is False
    assert "numérique" in response["error"] or "nombre" in response["error"]


def test_handle_correction_post_float_valide(engine, doc_with_dates):
    """A valid numeric string for a float field is accepted."""
    from dashboard.pages._verification_helpers import handle_correction_post

    _, ligne = doc_with_dates
    body = {
        "ligne_id": ligne.id,
        "champ": "prix_unitaire",
        "valeur_corrigee": "42.75",
        "confiance_originale": 0.3,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 200
    assert response["success"] is True
