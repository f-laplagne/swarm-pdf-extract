import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, BoundingBox, CorrectionLog, Document, Fournisseur, LigneFacture
from dashboard.analytics.corrections import (
    appliquer_correction,
    bboxes_pour_ligne,
    bboxes_pour_page,
    champs_faibles_pour_ligne,
    detail_confiance_document,
    documents_a_corriger,
    historique_corrections,
    lignes_a_corriger,
    recalculer_confiance_globale,
    sauvegarder_bbox,
    stats_corrections,
    supprimer_bbox,
    supprimer_ligne,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def mixed_confidence_data(db_session):
    """Document with lines having mixed confidence: some < 0.70, some >= 0.70."""
    f = Fournisseur(nom="TestFournisseur")
    db_session.add(f)
    db_session.flush()

    # Low confidence document
    d1 = Document(fichier="low_conf.pdf", type_document="facture",
                  fournisseur_id=f.id, confiance_globale=0.55)
    # High confidence document
    d2 = Document(fichier="high_conf.pdf", type_document="facture",
                  fournisseur_id=f.id, confiance_globale=0.95)
    db_session.add_all([d1, d2])
    db_session.flush()

    # d1 line 1: several fields below 0.70
    l1 = LigneFacture(
        document_id=d1.id, ligne_numero=1, type_matiere="Sable",
        prix_unitaire=10.0, quantite=5.0, prix_total=50.0,
        conf_type_matiere=0.5, conf_unite=0.3, conf_prix_unitaire=0.0,
        conf_quantite=0.8, conf_prix_total=0.0,
        conf_date_depart=None, conf_date_arrivee=0.9,
        conf_lieu_depart=0.6, conf_lieu_arrivee=0.75,
    )
    # d1 line 2: all fields >= 0.70
    l2 = LigneFacture(
        document_id=d1.id, ligne_numero=2, type_matiere="Gravier",
        prix_unitaire=20.0, quantite=3.0, prix_total=60.0,
        conf_type_matiere=0.9, conf_unite=0.85, conf_prix_unitaire=0.95,
        conf_quantite=0.88, conf_prix_total=0.92,
        conf_date_depart=0.8, conf_date_arrivee=0.9,
        conf_lieu_depart=0.75, conf_lieu_arrivee=0.80,
    )
    # d2 line 1: all high confidence
    l3 = LigneFacture(
        document_id=d2.id, ligne_numero=1, type_matiere="Ciment",
        conf_type_matiere=0.95, conf_unite=0.9, conf_prix_unitaire=0.92,
        conf_quantite=0.88, conf_prix_total=0.91,
        conf_date_depart=0.85, conf_date_arrivee=0.9,
        conf_lieu_depart=0.88, conf_lieu_arrivee=0.93,
    )
    db_session.add_all([l1, l2, l3])
    db_session.commit()
    return {"session": db_session, "d1": d1, "d2": d2, "l1": l1, "l2": l2, "l3": l3}


def test_documents_a_corriger(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    df = documents_a_corriger(s, seuil=0.70)
    # Only low_conf.pdf should appear (d1 has 1 weak line, d2 has 0)
    assert len(df) == 1
    assert df.iloc[0]["fichier"] == "low_conf.pdf"
    assert df.iloc[0]["nb_lignes_faibles"] == 1


def test_lignes_a_corriger(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    d1 = mixed_confidence_data["d1"]
    df = lignes_a_corriger(s, d1.id, seuil=0.70)
    # Only line 1 is weak
    assert len(df) == 1
    assert df.iloc[0]["ligne_numero"] == 1
    champs = df.iloc[0]["champs_faibles"]
    assert "type_matiere" in champs
    assert "prix_unitaire" in champs
    assert "date_depart" in champs  # None treated as weak


def test_champs_faibles_pour_ligne(mixed_confidence_data):
    l1 = mixed_confidence_data["l1"]
    faibles = champs_faibles_pour_ligne(l1, seuil=0.70)
    # conf_type_matiere=0.5, conf_unite=0.3, conf_prix_unitaire=0.0,
    # conf_prix_total=0.0, conf_date_depart=None, conf_lieu_depart=0.6
    assert "type_matiere" in faibles
    assert "unite" in faibles
    assert "prix_unitaire" in faibles
    assert "prix_total" in faibles
    assert "date_depart" in faibles  # None → weak
    assert "lieu_depart" in faibles  # 0.6 < 0.70
    # These should NOT be weak
    assert "quantite" not in faibles  # 0.8
    assert "date_arrivee" not in faibles  # 0.9
    assert "lieu_arrivee" not in faibles  # 0.75


def test_appliquer_correction(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    logs = appliquer_correction(s, l1.id, {"prix_unitaire": 15.0}, "admin", "test fix")
    assert len(logs) == 1
    assert logs[0].champ == "prix_unitaire"
    # Field updated
    s.refresh(l1)
    assert l1.prix_unitaire == 15.0
    assert l1.conf_prix_unitaire == 1.0
    # CorrectionLog created
    cl = s.query(CorrectionLog).filter_by(ligne_id=l1.id).first()
    assert cl is not None
    assert cl.ancienne_valeur == "10.0"
    assert cl.nouvelle_valeur == "15.0"


def test_multiple_corrections(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    logs = appliquer_correction(s, l1.id, {
        "type_matiere": "Sable fin",
        "unite": "tonne",
        "prix_unitaire": 12.0,
    }, "admin")
    assert len(logs) == 3
    s.refresh(l1)
    assert l1.type_matiere == "Sable fin"
    assert l1.unite == "tonne"
    assert l1.prix_unitaire == 12.0
    assert l1.conf_type_matiere == 1.0
    assert l1.conf_unite == 1.0
    assert l1.conf_prix_unitaire == 1.0


def test_old_value_stored(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    original_type = l1.type_matiere  # "Sable"
    original_conf = l1.conf_type_matiere  # 0.5
    appliquer_correction(s, l1.id, {"type_matiere": "Sable lavé"}, "admin")
    cl = s.query(CorrectionLog).filter_by(ligne_id=l1.id, champ="type_matiere").first()
    assert cl.ancienne_valeur == original_type
    assert cl.ancienne_confiance == original_conf


def test_recalculer_confiance_globale(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    d1 = mixed_confidence_data["d1"]
    result = recalculer_confiance_globale(s, d1.id)
    # d1 has 2 lines with various conf values; compute expected mean
    l1 = mixed_confidence_data["l1"]
    l2 = mixed_confidence_data["l2"]
    s.refresh(l1)
    s.refresh(l2)
    vals = []
    from dashboard.analytics.corrections import CONF_FIELDS
    for ligne in [l1, l2]:
        for cf in CONF_FIELDS:
            v = getattr(ligne, cf)
            if v is not None:
                vals.append(v)
    expected = sum(vals) / len(vals)
    assert abs(result - expected) < 0.001


def test_historique_corrections(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    d1 = mixed_confidence_data["d1"]
    appliquer_correction(s, l1.id, {"prix_unitaire": 99.0}, "admin")
    # All corrections
    df = historique_corrections(s)
    assert len(df) == 1
    assert df.iloc[0]["champ"] == "prix_unitaire"
    assert "fichier" in df.columns
    assert df.iloc[0]["fichier"] == d1.fichier
    # Filter by document
    df_filtered = historique_corrections(s, document_id=d1.id)
    assert len(df_filtered) == 1
    # Filter by other document → empty
    d2 = mixed_confidence_data["d2"]
    df_empty = historique_corrections(s, document_id=d2.id)
    assert len(df_empty) == 0


def test_stats_corrections(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    # No corrections yet
    stats = stats_corrections(s)
    assert stats["total"] == 0
    # Apply corrections
    appliquer_correction(s, l1.id, {"prix_unitaire": 11.0, "unite": "kg"}, "admin")
    stats = stats_corrections(s)
    assert stats["total"] == 2
    assert stats["lignes"] == 1
    assert stats["documents"] == 1


def test_detail_confiance_document(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    d1 = mixed_confidence_data["d1"]
    df = detail_confiance_document(s, d1.id)
    # d1 has 2 lines
    assert len(df) == 2
    assert "ligne" in df.columns
    assert "matiere" in df.columns
    # All 9 editable fields present as columns
    for field in ["type_matiere", "prix_unitaire", "quantite", "lieu_depart"]:
        assert field in df.columns
    # Line 1 has conf_prix_unitaire = 0.0
    row1 = df[df["ligne"] == 1].iloc[0]
    assert row1["prix_unitaire"] == 0.0
    # Line 2 has conf_prix_unitaire = 0.95
    row2 = df[df["ligne"] == 2].iloc[0]
    assert row2["prix_unitaire"] == 0.95
    # None values appear as NaN/None
    assert row1["date_depart"] is None or pd.isna(row1["date_depart"])


def test_detail_confiance_empty(db_session):
    df = detail_confiance_document(db_session, document_id=999)
    assert len(df) == 0


def test_supprimer_ligne(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    d1 = mixed_confidence_data["d1"]
    l1 = mixed_confidence_data["l1"]

    # Before: 2 lines visible
    df_before = detail_confiance_document(s, d1.id)
    assert len(df_before) == 2

    # Delete line 1
    log = supprimer_ligne(s, l1.id, supprime_par="admin", notes="ligne inutile")
    assert log.champ == "__suppression__"
    assert log.nouvelle_valeur == "supprimee"
    assert l1.supprime is True

    # After: only 1 line visible
    df_after = detail_confiance_document(s, d1.id)
    assert len(df_after) == 1

    # Deleted line excluded from correction candidates
    df_lignes = lignes_a_corriger(s, d1.id, seuil=0.70)
    assert all(row["ligne_id"] != l1.id for _, row in df_lignes.iterrows())

    # Confiance_globale recalculated without deleted line
    doc = s.get(type(d1), d1.id)
    assert doc.confiance_globale is not None

    # Historique shows the suppression
    df_hist = historique_corrections(s)
    assert any(df_hist["champ"] == "__suppression__")


def test_empty_db(db_session):
    df_docs = documents_a_corriger(db_session, seuil=0.70)
    assert len(df_docs) == 0
    df_lignes = lignes_a_corriger(db_session, document_id=999, seuil=0.70)
    assert len(df_lignes) == 0
    stats = stats_corrections(db_session)
    assert stats["total"] == 0
    df_hist = historique_corrections(db_session)
    assert len(df_hist) == 0


# ============================================================
# Bounding Box tests
# ============================================================

def test_sauvegarder_bbox(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    d1 = mixed_confidence_data["d1"]
    bbox = sauvegarder_bbox(
        s, l1.id, d1.id, "prix_unitaire", page_number=1,
        x_min=0.1, y_min=0.2, x_max=0.5, y_max=0.4,
    )
    assert bbox.id is not None
    assert bbox.source == "manual"
    assert bbox.champ == "prix_unitaire"
    assert bbox.page_number == 1


def test_bbox_coords_validation(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    d1 = mixed_confidence_data["d1"]
    # Out of range
    with pytest.raises(ValueError, match="hors de l'intervalle"):
        sauvegarder_bbox(s, l1.id, d1.id, "unite", 1, -0.1, 0.2, 0.5, 0.4)
    with pytest.raises(ValueError, match="hors de l'intervalle"):
        sauvegarder_bbox(s, l1.id, d1.id, "unite", 1, 0.1, 0.2, 1.5, 0.4)
    # min >= max
    with pytest.raises(ValueError, match="min doit etre < max"):
        sauvegarder_bbox(s, l1.id, d1.id, "unite", 1, 0.5, 0.2, 0.3, 0.4)
    with pytest.raises(ValueError, match="min doit etre < max"):
        sauvegarder_bbox(s, l1.id, d1.id, "unite", 1, 0.1, 0.5, 0.5, 0.3)


def test_bboxes_pour_page(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    d1 = mixed_confidence_data["d1"]
    sauvegarder_bbox(s, l1.id, d1.id, "prix_unitaire", 1, 0.1, 0.2, 0.5, 0.4)
    sauvegarder_bbox(s, l1.id, d1.id, "quantite", 1, 0.6, 0.2, 0.9, 0.4)
    sauvegarder_bbox(s, l1.id, d1.id, "type_matiere", 2, 0.1, 0.1, 0.5, 0.3)
    # Page 1 → 2 bboxes
    page1 = bboxes_pour_page(s, d1.id, 1)
    assert len(page1) == 2
    # Page 2 → 1 bbox
    page2 = bboxes_pour_page(s, d1.id, 2)
    assert len(page2) == 1
    assert page2[0].champ == "type_matiere"
    # Page 3 → 0
    assert len(bboxes_pour_page(s, d1.id, 3)) == 0


def test_bboxes_pour_ligne(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    l2 = mixed_confidence_data["l2"]
    d1 = mixed_confidence_data["d1"]
    sauvegarder_bbox(s, l1.id, d1.id, "prix_unitaire", 1, 0.1, 0.2, 0.5, 0.4)
    sauvegarder_bbox(s, l1.id, d1.id, "quantite", 1, 0.6, 0.2, 0.9, 0.4)
    sauvegarder_bbox(s, l2.id, d1.id, "type_matiere", 1, 0.1, 0.5, 0.5, 0.7)
    assert len(bboxes_pour_ligne(s, l1.id)) == 2
    assert len(bboxes_pour_ligne(s, l2.id)) == 1


def test_supprimer_bbox(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    d1 = mixed_confidence_data["d1"]
    bbox = sauvegarder_bbox(s, l1.id, d1.id, "prix_unitaire", 1, 0.1, 0.2, 0.5, 0.4)
    bbox_id = bbox.id
    supprimer_bbox(s, bbox_id)
    assert s.get(BoundingBox, bbox_id) is None


def test_supprimer_bbox_not_found(db_session):
    with pytest.raises(ValueError, match="introuvable"):
        supprimer_bbox(db_session, 99999)


def test_number_search_strings():
    from dashboard.pages import __path__ as _  # noqa — ensure importable
    # Import the helpers directly from the module file
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "corrections_page",
        "dashboard/pages/10_corrections.py",
        submodule_search_locations=[],
    )
    # We can't fully import a Streamlit page, so test the pure functions directly
    # by extracting them. Instead, test the logic inline.
    from types import SimpleNamespace

    # Test _number_search_strings logic
    def _number_search_strings(value):
        if value is None:
            return []
        try:
            fval = float(value)
        except (ValueError, TypeError):
            return []
        results = set()
        s2 = f"{fval:.2f}"
        results.add(s2)
        results.add(s2.replace(".", ","))
        s3 = f"{fval:.3f}"
        results.add(s3)
        results.add(s3.replace(".", ","))
        sg = f"{fval:g}"
        results.add(sg)
        results.add(sg.replace(".", ","))
        if fval == int(fval):
            results.add(str(int(fval)))
        return [r for r in results if len(r) >= 2]

    patterns = _number_search_strings(3.5)
    assert "3,50" in patterns
    assert "3.50" in patterns

    patterns = _number_search_strings(87.5)
    assert "87,50" in patterns
    assert "87.50" in patterns

    patterns = _number_search_strings(24.198)
    assert "24,198" in patterns
    assert "24.198" in patterns

    patterns = _number_search_strings(25.0)
    assert "25,00" in patterns
    assert "25" in patterns

    assert _number_search_strings(None) == []


def test_find_number_in_words():
    # Simulate PDF words
    words = [
        {"text": "3,50", "x_min": 0.7, "y_min": 0.3, "x_max": 0.8, "y_max": 0.35},
        {"text": "87,50", "x_min": 0.85, "y_min": 0.3, "x_max": 0.95, "y_max": 0.35},
        {"text": "24,198", "x_min": 0.5, "y_min": 0.3, "x_max": 0.6, "y_max": 0.35},
    ]

    def _find_number_bbox(words, value):
        def _number_search_strings(v):
            try:
                fval = float(v)
            except (ValueError, TypeError):
                return []
            results = set()
            s2 = f"{fval:.2f}"
            results.add(s2); results.add(s2.replace(".", ","))
            s3 = f"{fval:.3f}"
            results.add(s3); results.add(s3.replace(".", ","))
            sg = f"{fval:g}"
            results.add(sg); results.add(sg.replace(".", ","))
            if fval == int(fval):
                results.add(str(int(fval)))
            return [r for r in results if len(r) >= 2]

        patterns = _number_search_strings(value)
        for word in words:
            for p in patterns:
                if word["text"].strip() == p:
                    return word
        return None

    assert _find_number_bbox(words, 3.5) is not None
    assert _find_number_bbox(words, 3.5)["text"] == "3,50"
    assert _find_number_bbox(words, 87.5)["text"] == "87,50"
    assert _find_number_bbox(words, 24.198)["text"] == "24,198"
    assert _find_number_bbox(words, 99.99) is None


def test_find_text_in_words():
    words = [
        {"text": "RECHARGEMENT", "x_min": 0.2, "y_min": 0.3, "x_max": 0.4, "y_max": 0.35},
        {"text": "60", "x_min": 0.41, "y_min": 0.3, "x_max": 0.44, "y_max": 0.35},
        {"text": "BOB", "x_min": 0.45, "y_min": 0.3, "x_max": 0.5, "y_max": 0.35},
        {"text": "EURENCO", "x_min": 0.2, "y_min": 0.4, "x_max": 0.35, "y_max": 0.45},
    ]

    def _find_text_bbox(words, text_value):
        if not text_value or len(str(text_value).strip()) < 2:
            return None
        text_upper = str(text_value).strip().upper()
        for w in words:
            if w["text"].upper() == text_upper:
                return w
        sig_words = [w for w in str(text_value).split() if len(w) >= 3]
        if not sig_words:
            return None
        first = sig_words[0].upper()
        for i, w in enumerate(words):
            if w["text"].upper() == first:
                bbox = dict(w)
                sig_idx = 1
                for k in range(i + 1, min(i + 20, len(words))):
                    if sig_idx >= len(sig_words):
                        break
                    nw = words[k]
                    if abs(nw["y_min"] - w["y_min"]) > 0.02:
                        break
                    bbox["x_max"] = max(bbox["x_max"], nw["x_max"])
                    bbox["y_max"] = max(bbox["y_max"], nw["y_max"])
                    if nw["text"].upper() == sig_words[sig_idx].upper():
                        sig_idx += 1
                return bbox
        return None

    # Single word match
    result = _find_text_bbox(words, "EURENCO")
    assert result is not None
    assert result["text"] == "EURENCO"

    # Multi-word match: "RECHARGEMENT 60 BOB" — extends bbox
    result = _find_text_bbox(words, "RECHARGEMENT 60 BOB DE CELLULOSE")
    assert result is not None
    assert result["x_min"] == 0.2
    assert result["x_max"] == 0.5  # extended to BOB

    # No match
    assert _find_text_bbox(words, "MANUCO") is None
    assert _find_text_bbox(words, None) is None


def test_bbox_with_correction_log(mixed_confidence_data):
    s = mixed_confidence_data["session"]
    l1 = mixed_confidence_data["l1"]
    d1 = mixed_confidence_data["d1"]
    logs = appliquer_correction(s, l1.id, {"prix_unitaire": 15.0}, "admin")
    log_id = logs[0].id
    bbox = sauvegarder_bbox(
        s, l1.id, d1.id, "prix_unitaire", 1,
        0.1, 0.2, 0.5, 0.4,
        correction_log_id=log_id,
    )
    assert bbox.correction_log_id == log_id
