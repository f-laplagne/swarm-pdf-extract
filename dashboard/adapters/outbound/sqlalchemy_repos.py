"""SQLAlchemy implementations of domain repository ports.

Each adapter translates between ORM models (sqlalchemy_models) and
pure domain models (domain.models), keeping the domain layer free
of any infrastructure dependency.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import (
    EntityMapping as OrmEntityMapping,
)
from domain.models import EntityMapping as DomainEntityMapping, StatutMapping
from domain.ports import MappingRepository


class SqlAlchemyMappingRepository(MappingRepository):
    """SQLAlchemy adapter for the MappingRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Queries ────────────────────────────────────────────────────────

    def get_mappings(self, entity_type: str) -> dict[str, str]:
        """Return {raw_value: canonical_value} for approved exact mappings."""
        stmt = (
            select(OrmEntityMapping.raw_value, OrmEntityMapping.canonical_value)
            .where(OrmEntityMapping.entity_type == entity_type)
            .where(OrmEntityMapping.status == "approved")
            .where(OrmEntityMapping.match_mode == "exact")
        )
        return {
            row.raw_value: row.canonical_value
            for row in self._session.execute(stmt)
        }

    def get_prefix_mappings(self, entity_type: str) -> dict[str, str]:
        """Return {raw_value: canonical_value} for approved prefix mappings."""
        stmt = (
            select(OrmEntityMapping.raw_value, OrmEntityMapping.canonical_value)
            .where(OrmEntityMapping.entity_type == entity_type)
            .where(OrmEntityMapping.status == "approved")
            .where(OrmEntityMapping.match_mode == "prefix")
        )
        return {
            row.raw_value: row.canonical_value
            for row in self._session.execute(stmt)
        }

    def get_reverse_mappings(self, entity_type: str) -> dict[str, list[str]]:
        """Return {canonical_value: [raw_value, ...]} for approved mappings."""
        stmt = (
            select(OrmEntityMapping.raw_value, OrmEntityMapping.canonical_value)
            .where(OrmEntityMapping.entity_type == entity_type)
            .where(OrmEntityMapping.status == "approved")
        )
        result: dict[str, list[str]] = {}
        for row in self._session.execute(stmt):
            result.setdefault(row.canonical_value, []).append(row.raw_value)
        return result

    def get_pending_reviews(self, entity_type: str) -> list[DomainEntityMapping]:
        """Return domain EntityMapping objects for pending_review status, ordered by confidence desc."""
        stmt = (
            select(OrmEntityMapping)
            .where(OrmEntityMapping.entity_type == entity_type)
            .where(OrmEntityMapping.status == "pending_review")
            .order_by(OrmEntityMapping.confidence.desc())
        )
        return [self._to_domain(orm) for orm in self._session.scalars(stmt)]

    # ── Commands ───────────────────────────────────────────────────────

    def save_mapping(self, mapping: DomainEntityMapping) -> DomainEntityMapping:
        """Persist a domain EntityMapping and return it with its assigned id."""
        orm_obj = OrmEntityMapping(
            entity_type=mapping.entity_type,
            raw_value=mapping.raw_value,
            canonical_value=mapping.canonical_value,
            source=mapping.source,
            confidence=mapping.confidence,
            status=mapping.statut.value,
        )
        if mapping.id is not None:
            orm_obj.id = mapping.id
        self._session.add(orm_obj)
        self._session.flush()
        mapping.id = orm_obj.id
        return mapping

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _to_domain(orm: OrmEntityMapping) -> DomainEntityMapping:
        """Convert an ORM EntityMapping row to a domain EntityMapping."""
        valid_statuts = {s.value for s in StatutMapping}
        statut = (
            StatutMapping(orm.status)
            if orm.status in valid_statuts
            else StatutMapping.PENDING_REVIEW
        )
        return DomainEntityMapping(
            entity_type=orm.entity_type,
            raw_value=orm.raw_value,
            canonical_value=orm.canonical_value,
            statut=statut,
            confidence=orm.confidence or 0.0,
            source=orm.source or "manual",
            id=orm.id,
        )
