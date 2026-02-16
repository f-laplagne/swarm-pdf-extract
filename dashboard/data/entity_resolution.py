"""Entity resolution core logic.

Provides functions to manage entity mappings (raw value -> canonical value),
resolve DataFrame columns against those mappings, and audit merge/revert
operations.  All query helpers accept a SQLAlchemy ``Session`` so they work
transparently with both the production database and in-memory SQLite fixtures.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy import select, union_all
from sqlalchemy.orm import Session

from dashboard.data.models import (
    Document,
    EntityMapping,
    Fournisseur,
    LigneFacture,
    MergeAuditLog,
)

# ---------------------------------------------------------------------------
# Mapping retrieval
# ---------------------------------------------------------------------------


def get_mappings(session: Session, entity_type: str) -> dict[str, str]:
    """Return ``{raw_value: canonical_value}`` for **approved exact** mappings.

    Only rows with ``status='approved'`` and ``match_mode='exact'`` are
    included so that callers get a simple dict suitable for direct look-ups.
    """
    stmt = (
        select(EntityMapping.raw_value, EntityMapping.canonical_value)
        .where(EntityMapping.entity_type == entity_type)
        .where(EntityMapping.status == "approved")
        .where(EntityMapping.match_mode == "exact")
    )
    return {row.raw_value: row.canonical_value for row in session.execute(stmt)}


def get_prefix_mappings(session: Session, entity_type: str) -> dict[str, str]:
    """Return ``{raw_value: canonical_value}`` for **approved prefix** mappings.

    These are used by :func:`resolve_column` for prefix-based matching where
    any value *starting with* ``raw_value`` should resolve to ``canonical_value``.
    """
    stmt = (
        select(EntityMapping.raw_value, EntityMapping.canonical_value)
        .where(EntityMapping.entity_type == entity_type)
        .where(EntityMapping.status == "approved")
        .where(EntityMapping.match_mode == "prefix")
    )
    return {row.raw_value: row.canonical_value for row in session.execute(stmt)}


def get_reverse_mappings(
    session: Session, entity_type: str
) -> dict[str, list[str]]:
    """Return ``{canonical_value: [raw_value1, ...]}`` for approved mappings.

    Useful for filter expansion: given a canonical name, find all raw
    variants that the user might have in the data.
    """
    stmt = (
        select(EntityMapping.raw_value, EntityMapping.canonical_value)
        .where(EntityMapping.entity_type == entity_type)
        .where(EntityMapping.status == "approved")
    )
    result: dict[str, list[str]] = {}
    for row in session.execute(stmt):
        result.setdefault(row.canonical_value, []).append(row.raw_value)
    return result


# ---------------------------------------------------------------------------
# Column resolution (DataFrame-level)
# ---------------------------------------------------------------------------


def resolve_column(
    df: pd.DataFrame,
    column: str,
    mappings: dict[str, str],
    prefix_mappings: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Add a ``resolved_{column}`` column to *df*.

    Resolution order for each value:
    1. **Exact match** -- ``value`` appears as a key in *mappings*.
    2. **Prefix match** -- ``value`` starts with a key in *prefix_mappings*
       (longest prefix wins).
    3. **No match** -- the original value is kept as-is.

    The original DataFrame is returned (modified in place) with the new column
    appended.
    """
    prefix_mappings = prefix_mappings or {}

    # Pre-sort prefix keys by descending length so that the first match is the
    # longest (most specific) prefix.
    sorted_prefixes = sorted(prefix_mappings.keys(), key=len, reverse=True)

    def _resolve(value):
        if pd.isna(value) or value is None:
            return value

        val = str(value)

        # 1. Exact match
        if val in mappings:
            return mappings[val]

        # 2. Prefix match (longest prefix first)
        for prefix in sorted_prefixes:
            if val.startswith(prefix):
                return prefix_mappings[prefix]

        # 3. No match
        return val

    resolved_col = f"resolved_{column}"
    df[resolved_col] = df[column].map(_resolve)
    return df


# ---------------------------------------------------------------------------
# Canonical expansion (for SQL IN clauses / filter chips)
# ---------------------------------------------------------------------------


def expand_canonical(
    session: Session, entity_type: str, canonical: str
) -> list[str]:
    """Return all raw values that map to *canonical* (approved mappings only).

    The canonical value itself is always included in the result so that SQL
    ``IN`` clauses match both raw variants and the canonical name.
    """
    stmt = (
        select(EntityMapping.raw_value)
        .where(EntityMapping.entity_type == entity_type)
        .where(EntityMapping.canonical_value == canonical)
        .where(EntityMapping.status == "approved")
    )
    raw_values = [row.raw_value for row in session.execute(stmt)]
    # Always include the canonical value itself
    if canonical not in raw_values:
        raw_values.insert(0, canonical)
    return raw_values


# ---------------------------------------------------------------------------
# Merge / revert operations (transactional)
# ---------------------------------------------------------------------------


def merge_entities(
    session: Session,
    entity_type: str,
    canonical: str,
    raw_values: list[str],
    match_mode: str = "exact",
    source: str = "manual",
    confidence: float = 1.0,
    performed_by: str = "admin",
    notes: str | None = None,
) -> MergeAuditLog:
    """Create or update :class:`EntityMapping` rows and record an audit entry.

    For each *raw_value* in *raw_values*:
    - If an ``EntityMapping`` already exists for ``(entity_type, raw_value)``,
      update its ``canonical_value``, ``match_mode``, ``source``,
      ``confidence``, and set ``status='approved'``.
    - Otherwise create a new row.

    A :class:`MergeAuditLog` entry is created to record the operation.  The
    whole operation is committed atomically.
    """
    for raw in raw_values:
        existing = session.execute(
            select(EntityMapping).where(
                EntityMapping.entity_type == entity_type,
                EntityMapping.raw_value == raw,
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.canonical_value = canonical
            existing.match_mode = match_mode
            existing.source = source
            existing.confidence = confidence
            existing.status = "approved"
            existing.created_by = performed_by
            existing.notes = notes
        else:
            mapping = EntityMapping(
                entity_type=entity_type,
                raw_value=raw,
                canonical_value=canonical,
                match_mode=match_mode,
                source=source,
                confidence=confidence,
                status="approved",
                created_by=performed_by,
                notes=notes,
            )
            session.add(mapping)

    audit = MergeAuditLog(
        entity_type=entity_type,
        action="merge",
        canonical_value=canonical,
        raw_values_json=json.dumps(raw_values, ensure_ascii=False),
        performed_by=performed_by,
        notes=notes,
    )
    session.add(audit)
    session.commit()
    return audit


def revert_merge(
    session: Session,
    audit_log_id: int,
    performed_by: str = "admin",
) -> bool:
    """Revert a merge operation identified by *audit_log_id*.

    Deletes the :class:`EntityMapping` rows that were created by the merge and
    marks the audit log entry as reverted.  Returns ``True`` on success, or
    ``False`` if the audit log entry does not exist or was already reverted.
    """
    audit: MergeAuditLog | None = session.get(MergeAuditLog, audit_log_id)
    if audit is None or audit.reverted:
        return False

    raw_values: list[str] = json.loads(audit.raw_values_json)

    for raw in raw_values:
        mapping = session.execute(
            select(EntityMapping).where(
                EntityMapping.entity_type == audit.entity_type,
                EntityMapping.raw_value == raw,
            )
        ).scalar_one_or_none()
        if mapping is not None:
            session.delete(mapping)

    audit.reverted = True
    audit.reverted_at = datetime.now(timezone.utc)
    audit.notes = (audit.notes or "") + f"\nReverted by {performed_by}"
    session.commit()
    return True


# ---------------------------------------------------------------------------
# Pending reviews
# ---------------------------------------------------------------------------


def get_pending_reviews(session: Session) -> list[EntityMapping]:
    """Return mappings with ``status='pending_review'``, highest confidence first."""
    stmt = (
        select(EntityMapping)
        .where(EntityMapping.status == "pending_review")
        .order_by(EntityMapping.confidence.desc())
    )
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------------
# Distinct values for filter drop-downs
# ---------------------------------------------------------------------------

# Mapping from entity_type to the query logic needed to fetch raw values.
_ENTITY_TYPE_QUERIES = {
    "location": lambda: union_all(
        select(LigneFacture.lieu_depart.label("val")).where(
            LigneFacture.lieu_depart.isnot(None)
        ),
        select(LigneFacture.lieu_arrivee.label("val")).where(
            LigneFacture.lieu_arrivee.isnot(None)
        ),
    ),
    "material": lambda: select(LigneFacture.type_matiere.label("val")).where(
        LigneFacture.type_matiere.isnot(None)
    ),
    "supplier": lambda: select(Fournisseur.nom.label("val")).where(
        Fournisseur.nom.isnot(None)
    ),
    "company": lambda: select(Document.client_nom.label("val")).where(
        Document.client_nom.isnot(None)
    ),
}


def get_distinct_values(session: Session, entity_type: str) -> list[str]:
    """Return sorted, distinct canonical names for use in filter drop-downs.

    For each unique raw value found in the database:
    - If an approved mapping exists, the *canonical* value is used.
    - Otherwise the raw value is returned as-is.

    The result is a deduplicated, alphabetically-sorted list.
    """
    query_factory = _ENTITY_TYPE_QUERIES.get(entity_type)
    if query_factory is None:
        return []

    subq = query_factory().subquery()
    # Wrap in a subquery so we can select distinct values
    raw_values_set: set[str] = set()
    for row in session.execute(select(subq.c.val).distinct()):
        if row.val is not None and str(row.val).strip():
            raw_values_set.add(str(row.val))

    if not raw_values_set:
        return []

    # Fetch approved mappings (exact + prefix) for resolution
    exact = get_mappings(session, entity_type)
    prefix = get_prefix_mappings(session, entity_type)
    sorted_prefixes = sorted(prefix.keys(), key=len, reverse=True)

    resolved: set[str] = set()
    for val in raw_values_set:
        if val in exact:
            resolved.add(exact[val])
        else:
            matched = False
            for pfx in sorted_prefixes:
                if val.startswith(pfx):
                    resolved.add(prefix[pfx])
                    matched = True
                    break
            if not matched:
                resolved.add(val)

    return sorted(resolved)
