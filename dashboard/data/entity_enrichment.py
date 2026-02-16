"""Auto-resolution engine for entity enrichment.

Provides suggestion engines that find duplicate entities (locations, materials,
suppliers) using fuzzy string matching and optional geocoding, then applies
automatic merges or creates pending-review mappings based on confidence
thresholds.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from rapidfuzz import fuzz, process
from sqlalchemy import select, union_all
from sqlalchemy.orm import Session

from dashboard.data.entity_resolution import merge_entities
from dashboard.data.models import (
    EntityMapping,
    Fournisseur,
    LigneFacture,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

# Common legal suffixes to strip from supplier names
_LEGAL_SUFFIXES = re.compile(
    r"\b(SA|SARL|SAS|S\.A\.S\.?|S\.A\.R\.L\.?|S\.A\.?|EURL|SCI|SNC|"
    r"GmbH|AG|Ltd\.?|Inc\.?|LLC|PLC|Co\.?|Corp\.?|BV|NV)\s*$",
    re.IGNORECASE,
)

# Leading quantity pattern: digits + optional unit words
_LEADING_QTY = re.compile(
    r"^\d+[\s,.]?\d*\s*"
    r"(bobines?|rouleaux?|futs?|palettes?|tonnes?|kg|litres?|"
    r"sacs?|pièces?|lots?|bidons?|containers?|m[23]?)\b\s*(de\s+|d['\u2019])?",
    re.IGNORECASE,
)


def _normalize_supplier(name: str) -> str:
    """Case-fold and strip legal suffixes from a supplier name."""
    result = name.strip().casefold()
    result = _LEGAL_SUFFIXES.sub("", result).strip()
    # Remove trailing punctuation left by suffix removal
    result = result.rstrip(".,- ")
    return result


def _normalize_material(name: str) -> str:
    """Normalise a material name: strip operational details after ' - ',
    remove leading quantities, and case-fold."""
    # Strip after " - " separator (operational details)
    if " - " in name:
        name = name.split(" - ")[0]
    name = name.strip()
    # Remove leading quantities (e.g., "60 bobines de cellulose" -> "cellulose")
    # Actually we want "bobines de cellulose" vs just "cellulose" -- keep the unit
    # The requirement says: "60 bobines de cellulose" -> "bobines de cellulose"
    name = _LEADING_QTY.sub("", name).strip()
    return name.casefold()


# ---------------------------------------------------------------------------
# Distinct value fetching (with exclusion of already-mapped values)
# ---------------------------------------------------------------------------


def _get_distinct_locations(session: Session) -> set[str]:
    """Return all distinct non-null location values from the database."""
    subq = union_all(
        select(LigneFacture.lieu_depart.label("val")).where(
            LigneFacture.lieu_depart.isnot(None)
        ),
        select(LigneFacture.lieu_arrivee.label("val")).where(
            LigneFacture.lieu_arrivee.isnot(None)
        ),
    ).subquery()
    rows = session.execute(select(subq.c.val).distinct())
    return {str(r.val).strip() for r in rows if r.val and str(r.val).strip()}


def _get_distinct_materials(session: Session) -> set[str]:
    """Return all distinct non-null material values."""
    rows = session.execute(
        select(LigneFacture.type_matiere).distinct().where(
            LigneFacture.type_matiere.isnot(None)
        )
    )
    return {str(r[0]).strip() for r in rows if r[0] and str(r[0]).strip()}


def _get_distinct_suppliers(session: Session) -> set[str]:
    """Return all distinct non-null supplier names."""
    rows = session.execute(
        select(Fournisseur.nom).distinct().where(Fournisseur.nom.isnot(None))
    )
    return {str(r[0]).strip() for r in rows if r[0] and str(r[0]).strip()}


def _get_approved_raw_values(session: Session, entity_type: str) -> set[str]:
    """Return the set of raw values that already have an approved mapping."""
    stmt = (
        select(EntityMapping.raw_value)
        .where(EntityMapping.entity_type == entity_type)
        .where(EntityMapping.status == "approved")
    )
    return {row.raw_value for row in session.execute(stmt)}


# ---------------------------------------------------------------------------
# Suggestion engines
# ---------------------------------------------------------------------------


def suggest_location_merges(session: Session) -> list[dict]:
    """Find location duplicates using fuzzy matching + optional geocoding.

    Strategy:
    1. Fuzzy match all distinct location values (fast, no API calls).
    2. Only attempt geocoding as a secondary strategy if fuzzy matching is
       inconclusive (not implemented here to avoid rate-limiting issues).

    Returns list of {canonical, aliases, confidence, source}.
    """
    values = sorted(_get_distinct_locations(session))
    if len(values) < 2:
        return []

    suggestions: list[dict] = []
    used: set[str] = set()

    for i, val in enumerate(values):
        if val in used:
            continue
        # Find fuzzy matches among remaining values
        candidates = [v for v in values[i + 1:] if v not in used]
        if not candidates:
            break

        matches = process.extract(
            val, candidates, scorer=fuzz.ratio, limit=None, score_cutoff=50
        )
        if not matches:
            continue

        group_aliases = []
        best_confidence = 0.0
        for match_val, score, _ in matches:
            confidence = score / 100.0
            if confidence > best_confidence:
                best_confidence = confidence
            group_aliases.append(match_val)
            used.add(match_val)

        if group_aliases:
            used.add(val)
            suggestions.append({
                "canonical": val,
                "aliases": group_aliases,
                "confidence": best_confidence,
                "source": "fuzzy",
            })

    return suggestions


def suggest_location_merges_with_geocoding(
    session: Session, user_agent: str = "rationalize-dashboard", timeout: int = 5
) -> list[dict]:
    """Enhanced location merge suggestions using geopy geocoding.

    This function augments fuzzy-match suggestions with geocoding to resolve
    cases where names differ but refer to the same geographic location.
    Geocoding is only attempted for inconclusive fuzzy matches (0.5-0.8 range).

    Returns list of {canonical, aliases, confidence, source}.
    """
    try:
        from geopy.geocoders import Nominatim
        from geopy.distance import geodesic
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError
    except ImportError:
        logger.warning("geopy not available, falling back to fuzzy-only matching")
        return suggest_location_merges(session)

    # Start with fuzzy suggestions
    suggestions = suggest_location_merges(session)

    # Attempt geocoding enhancement for mid-confidence matches
    geocoder = Nominatim(user_agent=user_agent, timeout=timeout)
    geocode_cache: dict[str, tuple[float, float] | None] = {}

    def _geocode(name: str) -> tuple[float, float] | None:
        if name in geocode_cache:
            return geocode_cache[name]
        try:
            location = geocoder.geocode(name)
            if location:
                coords = (location.latitude, location.longitude)
                geocode_cache[name] = coords
                return coords
        except (GeocoderTimedOut, GeocoderServiceError, Exception) as e:
            logger.debug("Geocoding failed for %r: %s", name, e)
        geocode_cache[name] = None
        return None

    enhanced = []
    for suggestion in suggestions:
        conf = suggestion["confidence"]
        # Only geocode-enhance mid-confidence matches
        if 0.5 <= conf < 0.8:
            canonical_coords = _geocode(suggestion["canonical"])
            if canonical_coords:
                for alias in suggestion["aliases"]:
                    alias_coords = _geocode(alias)
                    if alias_coords:
                        dist = geodesic(canonical_coords, alias_coords).km
                        if dist < 1.0:
                            suggestion = {
                                **suggestion,
                                "confidence": 0.95,
                                "source": "geocoding",
                            }
                            break
        enhanced.append(suggestion)

    return enhanced


def suggest_material_merges(session: Session) -> list[dict]:
    """Find material duplicates using prefix extraction + fuzzy matching.

    Strategy: strip operational details (after ' - '), normalize quantities,
    then fuzzy match base names.

    Returns list of {canonical, aliases, confidence, source}.
    """
    raw_values = sorted(_get_distinct_materials(session))
    if len(raw_values) < 2:
        return []

    # Build normalized -> [original_values] mapping
    norm_groups: dict[str, list[str]] = {}
    for val in raw_values:
        normed = _normalize_material(val)
        if normed:
            norm_groups.setdefault(normed, []).append(val)

    # Phase 1: exact normalized matches (these are high confidence)
    suggestions: list[dict] = []
    used_normed: set[str] = set()

    for normed, originals in norm_groups.items():
        if len(originals) > 1:
            # Multiple raw values normalize to the same string
            # Pick the shortest original as canonical (most likely the clean form)
            canonical = min(originals, key=len)
            aliases = [v for v in originals if v != canonical]
            suggestions.append({
                "canonical": canonical,
                "aliases": aliases,
                "confidence": 0.95,
                "source": "normalization",
            })
            used_normed.add(normed)

    # Phase 2: fuzzy match among remaining normalized values
    remaining_normed = sorted(set(norm_groups.keys()) - used_normed)
    if len(remaining_normed) >= 2:
        used_fuzzy: set[str] = set()
        for i, normed in enumerate(remaining_normed):
            if normed in used_fuzzy:
                continue
            candidates = [n for n in remaining_normed[i + 1:] if n not in used_fuzzy]
            if not candidates:
                break

            matches = process.extract(
                normed, candidates, scorer=fuzz.ratio, limit=None, score_cutoff=50
            )
            if not matches:
                continue

            for match_normed, score, _ in matches:
                confidence = score / 100.0
                # Pick original values for canonical and alias
                canonical_originals = norm_groups[normed]
                alias_originals = norm_groups[match_normed]
                canonical = min(canonical_originals, key=len)
                aliases = [v for v in canonical_originals if v != canonical] + alias_originals
                if aliases:
                    suggestions.append({
                        "canonical": canonical,
                        "aliases": aliases,
                        "confidence": confidence,
                        "source": "fuzzy",
                    })
                used_fuzzy.add(match_normed)
            used_fuzzy.add(normed)

    return suggestions


def suggest_supplier_merges(session: Session) -> list[dict]:
    """Find supplier duplicates using case-insensitive normalization + fuzzy matching.

    Strategy: case-fold, strip legal suffixes, then fuzzy match.

    Returns list of {canonical, aliases, confidence, source}.
    """
    raw_values = sorted(_get_distinct_suppliers(session))
    if len(raw_values) < 2:
        return []

    # Build normalized -> [original_values] mapping
    norm_groups: dict[str, list[str]] = {}
    for val in raw_values:
        normed = _normalize_supplier(val)
        if normed:
            norm_groups.setdefault(normed, []).append(val)

    suggestions: list[dict] = []
    used_normed: set[str] = set()

    # Phase 1: exact normalized matches (high confidence)
    for normed, originals in norm_groups.items():
        if len(originals) > 1:
            canonical = min(originals, key=len)
            aliases = [v for v in originals if v != canonical]
            suggestions.append({
                "canonical": canonical,
                "aliases": aliases,
                "confidence": 0.95,
                "source": "normalization",
            })
            used_normed.add(normed)

    # Phase 2: fuzzy match among remaining normalized values
    remaining_normed = sorted(set(norm_groups.keys()) - used_normed)
    if len(remaining_normed) >= 2:
        used_fuzzy: set[str] = set()
        for i, normed in enumerate(remaining_normed):
            if normed in used_fuzzy:
                continue
            candidates = [n for n in remaining_normed[i + 1:] if n not in used_fuzzy]
            if not candidates:
                break

            matches = process.extract(
                normed, candidates, scorer=fuzz.ratio, limit=None, score_cutoff=50
            )
            if not matches:
                continue

            for match_normed, score, _ in matches:
                confidence = score / 100.0
                canonical_originals = norm_groups[normed]
                alias_originals = norm_groups[match_normed]
                canonical = min(canonical_originals, key=len)
                aliases = [v for v in canonical_originals if v != canonical] + alias_originals
                if aliases:
                    suggestions.append({
                        "canonical": canonical,
                        "aliases": aliases,
                        "confidence": confidence,
                        "source": "fuzzy",
                    })
                used_fuzzy.add(match_normed)
            used_fuzzy.add(normed)

    return suggestions


# ---------------------------------------------------------------------------
# Auto-resolution orchestrator
# ---------------------------------------------------------------------------


def run_auto_resolution(session: Session, config: dict) -> dict:
    """Run all suggestion engines and apply merges based on confidence thresholds.

    For each suggestion:
    - confidence >= auto_merge_threshold (default 0.9): auto-merge via merge_entities()
    - confidence >= review_threshold (default 0.5): create pending_review EntityMapping
    - confidence < review_threshold: ignore

    Skips values that already have approved mappings to avoid overwriting manual
    merges.

    Returns stats: {auto_merged: int, pending_review: int, ignored: int}.
    """
    er_config = config.get("entity_resolution", {})
    auto_merge_threshold = er_config.get("auto_merge_threshold", 0.90)
    review_threshold = er_config.get("review_threshold", 0.50)

    stats = {"auto_merged": 0, "pending_review": 0, "ignored": 0}

    # Collect suggestions from all engines
    engines: list[tuple[str, list[dict]]] = [
        ("location", suggest_location_merges(session)),
        ("material", suggest_material_merges(session)),
        ("supplier", suggest_supplier_merges(session)),
    ]

    for entity_type, suggestions in engines:
        # Get existing approved mappings to skip
        approved = _get_approved_raw_values(session, entity_type)

        for suggestion in suggestions:
            confidence = suggestion["confidence"]
            canonical = suggestion["canonical"]
            aliases = suggestion["aliases"]

            # Filter out aliases that already have approved mappings
            new_aliases = [a for a in aliases if a not in approved]
            # Also skip if canonical itself is already mapped as a raw value
            # (but canonical being in approved is OK -- it means it's already
            # the target of a mapping, which is fine)

            if not new_aliases:
                stats["ignored"] += 1
                continue

            if confidence >= auto_merge_threshold:
                # Auto-merge: use merge_entities which creates approved mappings
                try:
                    merge_entities(
                        session,
                        entity_type=entity_type,
                        canonical=canonical,
                        raw_values=new_aliases,
                        match_mode="exact",
                        source="auto",
                        confidence=confidence,
                        performed_by="auto_resolution",
                        notes=f"Auto-merged by enrichment engine (source={suggestion['source']})",
                    )
                    stats["auto_merged"] += 1
                except Exception:
                    logger.exception(
                        "Failed to auto-merge %s -> %s", new_aliases, canonical
                    )
                    stats["ignored"] += 1

            elif confidence >= review_threshold:
                # Create pending_review mappings directly
                for alias in new_aliases:
                    # Check if mapping already exists (any status)
                    existing = session.execute(
                        select(EntityMapping).where(
                            EntityMapping.entity_type == entity_type,
                            EntityMapping.raw_value == alias,
                        )
                    ).scalar_one_or_none()

                    if existing is None:
                        mapping = EntityMapping(
                            entity_type=entity_type,
                            raw_value=alias,
                            canonical_value=canonical,
                            match_mode="exact",
                            source="auto",
                            confidence=confidence,
                            status="pending_review",
                            created_by="auto_resolution",
                            notes=f"Suggested by enrichment engine (source={suggestion['source']})",
                        )
                        session.add(mapping)
                session.commit()
                stats["pending_review"] += 1

            else:
                stats["ignored"] += 1

    return stats
