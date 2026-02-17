"""Integration tests for SqlAlchemyMappingRepository.

Uses an in-memory SQLite database to verify the adapter correctly
maps between ORM models and domain models.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import (
    Base,
    EntityMapping as OrmEntityMapping,
)
from dashboard.adapters.outbound.sqlalchemy_repos import SqlAlchemyMappingRepository
from domain.models import EntityMapping as DomainEntityMapping, StatutMapping


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
