"""Integration tests for SQLAlchemy repository adapters.

Uses an in-memory SQLite database to verify the adapters correctly
map between ORM models and domain models.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import (
    Base,
    Document as OrmDocument,
    EntityMapping as OrmEntityMapping,
    Fournisseur as OrmFournisseur,
    LigneFacture as OrmLigneFacture,
)
from dashboard.adapters.outbound.sqlalchemy_repos import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyLineItemRepository,
    SqlAlchemyMappingRepository,
)
from domain.models import (
    Document as DomainDocument,
    EntityMapping as DomainEntityMapping,
    Fournisseur as DomainFournisseur,
    LigneFacture as DomainLigneFacture,
    ScoreConfiance,
    StatutMapping,
    TypeDocument,
)


@pytest.fixture
def session():
    """Create an in-memory SQLite session with schema initialized."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


class TestSqlAlchemyMappingRepository:
    """Integration tests for the MappingRepository SQLAlchemy adapter."""

    def test_get_mappings_returns_exact_approved(self, session):
        """Only approved exact mappings should be returned."""
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="ACME SA",
                canonical_value="ACME",
                status="approved",
                match_mode="exact",
            )
        )
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="PENDING",
                canonical_value="TEST",
                status="pending_review",
                match_mode="exact",
            )
        )
        session.flush()

        repo = SqlAlchemyMappingRepository(session)
        result = repo.get_mappings("supplier")
        assert result == {"ACME SA": "ACME"}
        # pending should not appear
        assert "PENDING" not in result

    def test_get_mappings_excludes_prefix_mode(self, session):
        """Prefix-mode mappings should not appear in exact get_mappings."""
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="PREFIX_VAL",
                canonical_value="CANONICAL",
                status="approved",
                match_mode="prefix",
            )
        )
        session.flush()

        repo = SqlAlchemyMappingRepository(session)
        result = repo.get_mappings("supplier")
        assert result == {}

    def test_get_prefix_mappings(self, session):
        """Only approved prefix mappings should be returned."""
        session.add(
            OrmEntityMapping(
                entity_type="location",
                raw_value="PARIS",
                canonical_value="PARIS IDF",
                status="approved",
                match_mode="prefix",
            )
        )
        session.add(
            OrmEntityMapping(
                entity_type="location",
                raw_value="LYON",
                canonical_value="LYON AURA",
                status="approved",
                match_mode="exact",
            )
        )
        session.flush()

        repo = SqlAlchemyMappingRepository(session)
        result = repo.get_prefix_mappings("location")
        assert result == {"PARIS": "PARIS IDF"}
        assert "LYON" not in result

    def test_get_reverse_mappings(self, session):
        """Reverse mappings should group raw values by canonical value."""
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="ACME SA",
                canonical_value="ACME",
                status="approved",
                match_mode="exact",
            )
        )
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="ACME SARL",
                canonical_value="ACME",
                status="approved",
                match_mode="exact",
            )
        )
        session.flush()

        repo = SqlAlchemyMappingRepository(session)
        result = repo.get_reverse_mappings("supplier")
        assert "ACME" in result
        assert sorted(result["ACME"]) == ["ACME SA", "ACME SARL"]

    def test_get_reverse_mappings_excludes_rejected(self, session):
        """Rejected mappings should not appear in reverse mappings."""
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="BAD",
                canonical_value="GOOD",
                status="rejected",
                match_mode="exact",
            )
        )
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="OK",
                canonical_value="GOOD",
                status="approved",
                match_mode="exact",
            )
        )
        session.flush()

        repo = SqlAlchemyMappingRepository(session)
        result = repo.get_reverse_mappings("supplier")
        assert result == {"GOOD": ["OK"]}

    def test_save_mapping(self, session):
        """save_mapping should persist to DB and return domain object with id."""
        repo = SqlAlchemyMappingRepository(session)
        mapping = DomainEntityMapping(
            entity_type="material",
            raw_value="BETON B25",
            canonical_value="BETON",
            statut=StatutMapping.APPROVED,
            confidence=0.95,
            source="auto",
        )
        result = repo.save_mapping(mapping)
        assert result.id is not None
        # Verify it's in DB
        orm = session.get(OrmEntityMapping, result.id)
        assert orm is not None
        assert orm.raw_value == "BETON B25"
        assert orm.canonical_value == "BETON"
        assert orm.status == "approved"
        assert orm.confidence == 0.95
        assert orm.source == "auto"

    def test_save_mapping_pending_review(self, session):
        """save_mapping should correctly persist pending_review status."""
        repo = SqlAlchemyMappingRepository(session)
        mapping = DomainEntityMapping(
            entity_type="supplier",
            raw_value="MAYBE",
            canonical_value="MAYBE_CANONICAL",
            statut=StatutMapping.PENDING_REVIEW,
            confidence=0.6,
            source="auto",
        )
        result = repo.save_mapping(mapping)
        orm = session.get(OrmEntityMapping, result.id)
        assert orm.status == "pending_review"

    def test_get_pending_reviews(self, session):
        """get_pending_reviews should return domain objects ordered by confidence desc."""
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="X",
                canonical_value="Y",
                status="pending_review",
                confidence=0.8,
            )
        )
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="A",
                canonical_value="B",
                status="pending_review",
                confidence=0.9,
            )
        )
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="C",
                canonical_value="D",
                status="approved",
                confidence=1.0,
            )
        )
        session.flush()

        repo = SqlAlchemyMappingRepository(session)
        result = repo.get_pending_reviews("supplier")
        assert len(result) == 2
        # Should be ordered by confidence desc
        assert result[0].confidence >= result[1].confidence
        assert result[0].raw_value == "A"
        assert result[1].raw_value == "X"
        # All should be domain objects
        assert all(isinstance(m, DomainEntityMapping) for m in result)
        # All should have pending_review status
        assert all(m.statut == StatutMapping.PENDING_REVIEW for m in result)

    def test_get_pending_reviews_excludes_other_entity_types(self, session):
        """get_pending_reviews should filter by entity_type."""
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="S1",
                canonical_value="S1C",
                status="pending_review",
                confidence=0.7,
            )
        )
        session.add(
            OrmEntityMapping(
                entity_type="material",
                raw_value="M1",
                canonical_value="M1C",
                status="pending_review",
                confidence=0.8,
            )
        )
        session.flush()

        repo = SqlAlchemyMappingRepository(session)
        result = repo.get_pending_reviews("supplier")
        assert len(result) == 1
        assert result[0].entity_type == "supplier"

    def test_get_mappings_filters_by_entity_type(self, session):
        """get_mappings should only return mappings for the requested entity_type."""
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="A",
                canonical_value="B",
                status="approved",
                match_mode="exact",
            )
        )
        session.add(
            OrmEntityMapping(
                entity_type="material",
                raw_value="C",
                canonical_value="D",
                status="approved",
                match_mode="exact",
            )
        )
        session.flush()

        repo = SqlAlchemyMappingRepository(session)
        result = repo.get_mappings("supplier")
        assert len(result) == 1
        assert "A" in result
        assert "C" not in result

    def test_get_mappings_empty_result(self, session):
        """get_mappings should return empty dict when no data matches."""
        repo = SqlAlchemyMappingRepository(session)
        result = repo.get_mappings("nonexistent")
        assert result == {}

    def test_get_pending_reviews_empty(self, session):
        """get_pending_reviews should return empty list when no pending reviews."""
        repo = SqlAlchemyMappingRepository(session)
        result = repo.get_pending_reviews("supplier")
        assert result == []

    def test_to_domain_maps_all_fields(self, session):
        """Verify ORM-to-domain conversion preserves all fields."""
        session.add(
            OrmEntityMapping(
                entity_type="supplier",
                raw_value="RAW",
                canonical_value="CANON",
                status="pending_review",
                confidence=0.75,
                source="auto",
                match_mode="exact",
            )
        )
        session.flush()

        repo = SqlAlchemyMappingRepository(session)
        results = repo.get_pending_reviews("supplier")
        assert len(results) == 1
        m = results[0]
        assert m.entity_type == "supplier"
        assert m.raw_value == "RAW"
        assert m.canonical_value == "CANON"
        assert m.statut == StatutMapping.PENDING_REVIEW
        assert m.confidence == 0.75
        assert m.source == "auto"
        assert m.id is not None


class TestSqlAlchemyDocumentRepository:
    """Integration tests for the DocumentRepository SQLAlchemy adapter."""

    def test_save_document_basic(self, session):
        """save() should persist a document with no fournisseur and assign an id."""
        repo = SqlAlchemyDocumentRepository(session)
        doc = DomainDocument(
            fichier="facture_001.pdf",
            type_document=TypeDocument.FACTURE,
            confiance_globale=0.85,
            montant_ht=1000.0,
            montant_tva=200.0,
            montant_ttc=1200.0,
            date_document=date(2025, 6, 15),
        )
        result = repo.save(doc)

        assert result.id is not None
        # Verify in DB
        orm = session.get(OrmDocument, result.id)
        assert orm is not None
        assert orm.fichier == "facture_001.pdf"
        assert orm.type_document == "facture"
        assert orm.confiance_globale == 0.85
        assert orm.montant_ht == 1000.0
        assert orm.montant_tva == 200.0
        assert orm.montant_ttc == 1200.0
        assert orm.date_document == date(2025, 6, 15)
        assert orm.fournisseur_id is None

    def test_save_document_with_fournisseur(self, session):
        """save() should create the fournisseur and link it to the document."""
        repo = SqlAlchemyDocumentRepository(session)
        doc = DomainDocument(
            fichier="facture_002.pdf",
            type_document=TypeDocument.DEVIS,
            confiance_globale=0.72,
            fournisseur=DomainFournisseur(nom="ACME Corp", adresse="123 Rue de Paris"),
        )
        result = repo.save(doc)

        assert result.id is not None
        assert result.fournisseur is not None
        assert result.fournisseur.id is not None

        # Verify document in DB
        orm_doc = session.get(OrmDocument, result.id)
        assert orm_doc is not None
        assert orm_doc.fournisseur_id == result.fournisseur.id

        # Verify fournisseur in DB
        orm_fourn = session.get(OrmFournisseur, result.fournisseur.id)
        assert orm_fourn is not None
        assert orm_fourn.nom == "ACME Corp"
        assert orm_fourn.adresse == "123 Rue de Paris"

    def test_save_document_existing_fournisseur(self, session):
        """save() should reuse an existing fournisseur by name instead of creating a duplicate."""
        # Pre-create a fournisseur
        existing = OrmFournisseur(nom="Existing Supplier", adresse="Old address")
        session.add(existing)
        session.flush()
        existing_id = existing.id

        repo = SqlAlchemyDocumentRepository(session)
        doc = DomainDocument(
            fichier="facture_003.pdf",
            type_document=TypeDocument.FACTURE,
            confiance_globale=0.90,
            fournisseur=DomainFournisseur(nom="Existing Supplier", adresse="New address"),
        )
        result = repo.save(doc)

        assert result.fournisseur is not None
        assert result.fournisseur.id == existing_id

        # Verify the document points to the existing fournisseur
        orm_doc = session.get(OrmDocument, result.id)
        assert orm_doc.fournisseur_id == existing_id

        # Verify no duplicate fournisseur was created
        from sqlalchemy import func, select
        count = session.scalar(select(func.count()).select_from(OrmFournisseur))
        assert count == 1

    def test_find_by_filename_found(self, session):
        """find_by_filename() should return a domain Document when the file exists."""
        # Insert via ORM
        orm_fourn = OrmFournisseur(nom="Test Supplier", adresse="456 Avenue")
        session.add(orm_fourn)
        session.flush()

        orm_doc = OrmDocument(
            fichier="found_doc.pdf",
            type_document="bon_livraison",
            confiance_globale=0.65,
            montant_ht=500.0,
            montant_ttc=600.0,
            date_document=date(2025, 3, 10),
            fournisseur_id=orm_fourn.id,
        )
        session.add(orm_doc)
        session.flush()

        repo = SqlAlchemyDocumentRepository(session)
        result = repo.find_by_filename("found_doc.pdf")

        assert result is not None
        assert isinstance(result, DomainDocument)
        assert result.fichier == "found_doc.pdf"
        assert result.type_document == TypeDocument.BON_LIVRAISON
        assert result.confiance_globale == 0.65
        assert result.montant_ht == 500.0
        assert result.montant_ttc == 600.0
        assert result.date_document == date(2025, 3, 10)
        assert result.id == orm_doc.id
        # Fournisseur should be mapped
        assert result.fournisseur is not None
        assert result.fournisseur.nom == "Test Supplier"
        assert result.fournisseur.adresse == "456 Avenue"
        assert result.fournisseur.id == orm_fourn.id

    def test_find_by_filename_not_found(self, session):
        """find_by_filename() should return None when the file does not exist."""
        repo = SqlAlchemyDocumentRepository(session)
        result = repo.find_by_filename("nonexistent.pdf")
        assert result is None

    def test_list_all(self, session):
        """list_all() should return all documents as domain objects."""
        session.add(OrmDocument(fichier="a.pdf", type_document="facture", confiance_globale=0.9))
        session.add(OrmDocument(fichier="b.pdf", type_document="devis", confiance_globale=0.7))
        session.add(OrmDocument(fichier="c.pdf", type_document="avoir", confiance_globale=0.5))
        session.flush()

        repo = SqlAlchemyDocumentRepository(session)
        result = repo.list_all()

        assert len(result) == 3
        assert all(isinstance(d, DomainDocument) for d in result)
        filenames = {d.fichier for d in result}
        assert filenames == {"a.pdf", "b.pdf", "c.pdf"}

    def test_list_all_empty(self, session):
        """list_all() should return an empty list when no documents exist."""
        repo = SqlAlchemyDocumentRepository(session)
        result = repo.list_all()
        assert result == []


class TestSqlAlchemyLineItemRepository:
    """Integration tests for the LineItemRepository SQLAlchemy adapter."""

    def _make_doc(self, session, fichier="doc.pdf", fournisseur_id=None):
        """Helper: insert and return an ORM Document."""
        doc = OrmDocument(
            fichier=fichier,
            type_document="facture",
            confiance_globale=0.8,
            fournisseur_id=fournisseur_id,
        )
        session.add(doc)
        session.flush()
        return doc

    def _make_ligne(self, session, document_id, ligne_numero=1, **kwargs):
        """Helper: insert and return an ORM LigneFacture."""
        defaults = dict(
            document_id=document_id,
            ligne_numero=ligne_numero,
            type_matiere="Gravier",
            unite="tonne",
            prix_unitaire=12.50,
            quantite=10.0,
            prix_total=125.0,
            date_depart="2025-06-01",
            date_arrivee="2025-06-02",
            lieu_depart="Paris",
            lieu_arrivee="Lyon",
            conf_type_matiere=0.95,
            conf_unite=0.90,
            conf_prix_unitaire=0.88,
            conf_quantite=0.92,
            conf_prix_total=0.85,
            conf_date_depart=0.80,
            conf_date_arrivee=0.75,
            conf_lieu_depart=0.70,
            conf_lieu_arrivee=0.65,
            supprime=False,
        )
        defaults.update(kwargs)
        ligne = OrmLigneFacture(**defaults)
        session.add(ligne)
        session.flush()
        return ligne

    def test_list_by_document(self, session):
        """list_by_document() should return only lines belonging to the given document."""
        doc1 = self._make_doc(session, fichier="doc1.pdf")
        doc2 = self._make_doc(session, fichier="doc2.pdf")
        self._make_ligne(session, doc1.id, ligne_numero=1, type_matiere="Sable")
        self._make_ligne(session, doc1.id, ligne_numero=2, type_matiere="Gravier")
        self._make_ligne(session, doc2.id, ligne_numero=1, type_matiere="Ciment")

        repo = SqlAlchemyLineItemRepository(session)
        result = repo.list_by_document(doc1.id)

        assert len(result) == 2
        assert all(isinstance(l, DomainLigneFacture) for l in result)
        matieres = {l.type_matiere for l in result}
        assert matieres == {"Sable", "Gravier"}

    def test_list_by_document_excludes_deleted(self, session):
        """list_by_document() should exclude lines with supprime=True."""
        doc = self._make_doc(session)
        self._make_ligne(session, doc.id, ligne_numero=1, supprime=False)
        self._make_ligne(session, doc.id, ligne_numero=2, supprime=True)

        repo = SqlAlchemyLineItemRepository(session)
        result = repo.list_by_document(doc.id)

        assert len(result) == 1
        assert result[0].ligne_numero == 1

    def test_list_by_document_ordered(self, session):
        """list_by_document() should return lines ordered by ligne_numero."""
        doc = self._make_doc(session)
        # Insert out of order
        self._make_ligne(session, doc.id, ligne_numero=3)
        self._make_ligne(session, doc.id, ligne_numero=1)
        self._make_ligne(session, doc.id, ligne_numero=2)

        repo = SqlAlchemyLineItemRepository(session)
        result = repo.list_by_document(doc.id)

        assert [l.ligne_numero for l in result] == [1, 2, 3]

    def test_list_with_supplier_joins_correctly(self, session):
        """list_with_supplier() should return (LigneFacture, supplier_name) tuples."""
        fourn = OrmFournisseur(nom="ACME Corp", adresse="123 Rue de Paris")
        session.add(fourn)
        session.flush()

        doc = self._make_doc(session, fournisseur_id=fourn.id)
        self._make_ligne(session, doc.id, ligne_numero=1, type_matiere="Sable")
        self._make_ligne(session, doc.id, ligne_numero=2, type_matiere="Gravier")

        repo = SqlAlchemyLineItemRepository(session)
        result = repo.list_with_supplier()

        assert len(result) == 2
        for ligne, supplier_name in result:
            assert isinstance(ligne, DomainLigneFacture)
            assert supplier_name == "ACME Corp"

    def test_list_with_supplier_no_supplier(self, session):
        """list_with_supplier() should return 'Inconnu' when doc has no fournisseur."""
        doc = self._make_doc(session, fournisseur_id=None)
        self._make_ligne(session, doc.id, ligne_numero=1)

        repo = SqlAlchemyLineItemRepository(session)
        result = repo.list_with_supplier()

        assert len(result) == 1
        ligne, supplier_name = result[0]
        assert isinstance(ligne, DomainLigneFacture)
        assert supplier_name == "Inconnu"

    def test_list_with_supplier_excludes_deleted(self, session):
        """list_with_supplier() should exclude lines with supprime=True."""
        fourn = OrmFournisseur(nom="Supplier A")
        session.add(fourn)
        session.flush()

        doc = self._make_doc(session, fournisseur_id=fourn.id)
        self._make_ligne(session, doc.id, ligne_numero=1, supprime=False)
        self._make_ligne(session, doc.id, ligne_numero=2, supprime=True)

        repo = SqlAlchemyLineItemRepository(session)
        result = repo.list_with_supplier()

        assert len(result) == 1
        ligne, supplier_name = result[0]
        assert ligne.ligne_numero == 1
        assert supplier_name == "Supplier A"

    def test_list_by_document_empty(self, session):
        """list_by_document() should return empty list when no lines exist for document."""
        doc = self._make_doc(session)

        repo = SqlAlchemyLineItemRepository(session)
        result = repo.list_by_document(doc.id)

        assert result == []

    def test_to_domain_maps_all_fields(self, session):
        """Verify ORM-to-domain conversion preserves all fields including confidence."""
        doc = self._make_doc(session)
        self._make_ligne(
            session,
            doc.id,
            ligne_numero=5,
            type_matiere="Beton B25",
            unite="m3",
            prix_unitaire=85.0,
            quantite=20.0,
            prix_total=1700.0,
            date_depart="2025-03-15",
            date_arrivee="2025-03-16",
            lieu_depart="Marseille",
            lieu_arrivee="Nice",
            conf_type_matiere=0.95,
            conf_unite=0.90,
            conf_prix_unitaire=0.88,
            conf_quantite=0.92,
            conf_prix_total=0.85,
            conf_date_depart=0.80,
            conf_date_arrivee=0.75,
            conf_lieu_depart=0.70,
            conf_lieu_arrivee=0.65,
        )

        repo = SqlAlchemyLineItemRepository(session)
        result = repo.list_by_document(doc.id)

        assert len(result) == 1
        l = result[0]
        assert l.ligne_numero == 5
        assert l.type_matiere == "Beton B25"
        assert l.unite == "m3"
        assert l.prix_unitaire == 85.0
        assert l.quantite == 20.0
        assert l.prix_total == 1700.0
        assert l.date_depart == date(2025, 3, 15)
        assert l.date_arrivee == date(2025, 3, 16)
        assert l.lieu_depart == "Marseille"
        assert l.lieu_arrivee == "Nice"
        assert l.id is not None
        # Check confidence scores
        assert l.confiance.type_matiere == 0.95
        assert l.confiance.unite == 0.90
        assert l.confiance.prix_unitaire == 0.88
        assert l.confiance.quantite == 0.92
        assert l.confiance.prix_total == 0.85
        assert l.confiance.date_depart == 0.80
        assert l.confiance.date_arrivee == 0.75
        assert l.confiance.lieu_depart == 0.70
        assert l.confiance.lieu_arrivee == 0.65

    def test_to_domain_handles_null_dates(self, session):
        """Verify ORM-to-domain conversion handles None date strings gracefully."""
        doc = self._make_doc(session)
        self._make_ligne(
            session,
            doc.id,
            ligne_numero=1,
            date_depart=None,
            date_arrivee=None,
        )

        repo = SqlAlchemyLineItemRepository(session)
        result = repo.list_by_document(doc.id)

        assert len(result) == 1
        assert result[0].date_depart is None
        assert result[0].date_arrivee is None

    def test_to_domain_handles_invalid_dates(self, session):
        """Verify ORM-to-domain conversion handles malformed date strings."""
        doc = self._make_doc(session)
        self._make_ligne(
            session,
            doc.id,
            ligne_numero=1,
            date_depart="not-a-date",
            date_arrivee="invalid",
        )

        repo = SqlAlchemyLineItemRepository(session)
        result = repo.list_by_document(doc.id)

        assert len(result) == 1
        assert result[0].date_depart is None
        assert result[0].date_arrivee is None
