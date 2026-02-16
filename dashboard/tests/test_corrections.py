import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, CorrectionLog, Document, Fournisseur, LigneFacture
from dashboard.analytics.corrections import (
    appliquer_correction,
    champs_faibles_pour_ligne,
    documents_a_corriger,
    historique_corrections,
    lignes_a_corriger,
    recalculer_confiance_globale,
    stats_corrections,
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


def test_empty_db(db_session):
    df_docs = documents_a_corriger(db_session, seuil=0.70)
    assert len(df_docs) == 0
    df_lignes = lignes_a_corriger(db_session, document_id=999, seuil=0.70)
    assert len(df_lignes) == 0
    stats = stats_corrections(db_session)
    assert stats["total"] == 0
    df_hist = historique_corrections(db_session)
    assert len(df_hist) == 0
