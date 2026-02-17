import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import (
    Base, Fournisseur, Document, LigneFacture, Anomalie,
    EntityMapping, MergeAuditLog, UploadLog,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_create_fournisseur(db_session):
    f = Fournisseur(nom="Transports Fockedey s.a.", siret=None, tva_intra="BE0439.237.690")
    db_session.add(f)
    db_session.commit()
    assert f.id is not None
    assert f.nom == "Transports Fockedey s.a."


def test_create_document_with_fournisseur(db_session):
    f = Fournisseur(nom="Fockedey")
    db_session.add(f)
    db_session.flush()

    d = Document(
        fichier="facture_test.pdf",
        type_document="facture",
        fournisseur_id=f.id,
        montant_ht=19597.46,
        confiance_globale=0.96,
    )
    db_session.add(d)
    db_session.commit()
    assert d.id is not None
    assert d.fournisseur.nom == "Fockedey"


def test_create_ligne_facture(db_session):
    f = Fournisseur(nom="Test")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="test.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.9)
    db_session.add(d)
    db_session.flush()

    ligne = LigneFacture(
        document_id=d.id,
        ligne_numero=1,
        type_matiere="Nitrate Ethyle Hexyl",
        unite="voyage",
        prix_unitaire=1620.00,
        quantite=1,
        prix_total=1620.00,
        date_depart="2024-11-05",
        lieu_depart="Sorgues",
        lieu_arrivee="Kallo",
        conf_type_matiere=0.98,
        conf_prix_unitaire=0.99,
    )
    db_session.add(ligne)
    db_session.commit()
    assert ligne.id is not None
    assert d.lignes[0].type_matiere == "Nitrate Ethyle Hexyl"


def test_create_anomalie(db_session):
    f = Fournisseur(nom="Test")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="test.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.5)
    db_session.add(d)
    db_session.flush()

    a = Anomalie(
        document_id=d.id,
        regle_id="CONF_001",
        type_anomalie="qualite_donnees",
        severite="info",
        description="Confiance globale < 0.6",
    )
    db_session.add(a)
    db_session.commit()
    assert a.id is not None
    assert len(d.anomalies) == 1


def test_create_entity_mapping(db_session):
    em = EntityMapping(
        entity_type="location",
        raw_value="Sorgues (84)",
        canonical_value="Sorgues",
        match_mode="prefix",
        source="manual",
        confidence=0.95,
        status="approved",
        notes="Normalisation commune Vaucluse",
    )
    db_session.add(em)
    db_session.commit()
    assert em.id is not None
    assert em.entity_type == "location"
    assert em.raw_value == "Sorgues (84)"
    assert em.canonical_value == "Sorgues"
    assert em.match_mode == "prefix"
    assert em.source == "manual"
    assert em.confidence == 0.95
    assert em.status == "approved"
    assert em.created_by == "admin"
    assert em.created_at is not None


def test_entity_mapping_defaults(db_session):
    em = EntityMapping(
        entity_type="material",
        raw_value="Nitrate Ethyle Hexyl",
        canonical_value="Nitrate Ethyle Hexyl",
    )
    db_session.add(em)
    db_session.commit()
    assert em.match_mode == "exact"
    assert em.source == "manual"
    assert em.confidence == 1.0
    assert em.status == "approved"
    assert em.created_by == "admin"


def test_entity_mapping_unique_type_raw(db_session):
    em1 = EntityMapping(entity_type="supplier", raw_value="Fockedey", canonical_value="Transports Fockedey s.a.")
    db_session.add(em1)
    db_session.commit()

    em2 = EntityMapping(entity_type="supplier", raw_value="Fockedey", canonical_value="Fockedey SA")
    db_session.add(em2)
    with pytest.raises(Exception):
        db_session.commit()


def test_create_merge_audit_log(db_session):
    log = MergeAuditLog(
        entity_type="location",
        action="merge",
        canonical_value="Sorgues",
        raw_values_json='["Sorgues (84)", "SORGUES", "sorgues"]',
        performed_by="admin",
        notes="Fusion des variantes de Sorgues",
    )
    db_session.add(log)
    db_session.commit()
    assert log.id is not None
    assert log.entity_type == "location"
    assert log.action == "merge"
    assert log.canonical_value == "Sorgues"
    assert log.raw_values_json == '["Sorgues (84)", "SORGUES", "sorgues"]'
    assert log.performed_by == "admin"
    assert log.performed_at is not None
    assert log.reverted is False
    assert log.reverted_at is None


def test_merge_audit_log_defaults(db_session):
    log = MergeAuditLog(
        entity_type="material",
        action="update",
        canonical_value="Nitrate Ethyle Hexyl",
        raw_values_json='["NEH"]',
    )
    db_session.add(log)
    db_session.commit()
    assert log.performed_by == "admin"
    assert log.reverted is False


def test_create_upload_log(db_session):
    f = Fournisseur(nom="Test")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="facture_upload.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.9)
    db_session.add(d)
    db_session.flush()

    ul = UploadLog(
        filename="facture_upload.pdf",
        content_hash="sha256_abc123def456",
        file_size=102400,
        uploaded_by="admin",
        status="completed",
        document_id=d.id,
    )
    db_session.add(ul)
    db_session.commit()
    assert ul.id is not None
    assert ul.filename == "facture_upload.pdf"
    assert ul.content_hash == "sha256_abc123def456"
    assert ul.file_size == 102400
    assert ul.status == "completed"
    assert ul.document_id == d.id
    assert ul.uploaded_at is not None


def test_upload_log_defaults(db_session):
    ul = UploadLog(
        filename="test.pdf",
        content_hash="sha256_unique",
    )
    db_session.add(ul)
    db_session.commit()
    assert ul.uploaded_by == "admin"
    assert ul.status == "uploaded"
    assert ul.error_message is None
    assert ul.document_id is None


def test_upload_log_unique_hash(db_session):
    ul1 = UploadLog(filename="file1.pdf", content_hash="sha256_same_hash")
    db_session.add(ul1)
    db_session.commit()

    ul2 = UploadLog(filename="file2.pdf", content_hash="sha256_same_hash")
    db_session.add(ul2)
    with pytest.raises(Exception):
        db_session.commit()
