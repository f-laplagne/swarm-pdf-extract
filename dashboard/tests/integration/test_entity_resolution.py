"""Tests for dashboard.data.entity_resolution module.

Uses an in-memory SQLite database via a shared ``db_session`` fixture.  Every
test function gets a fresh, empty database so there is no cross-contamination
between tests.
"""

import json

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.entity_resolution import (
    expand_canonical,
    get_distinct_values,
    get_mappings,
    get_pending_reviews,
    get_prefix_mappings,
    get_reverse_mappings,
    merge_entities,
    resolve_column,
    revert_merge,
)
from dashboard.data.models import (
    Base,
    Document,
    EntityMapping,
    Fournisseur,
    LigneFacture,
    MergeAuditLog,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def seeded_session(db_session):
    """Session pre-loaded with a handful of entity mappings."""
    mappings = [
        EntityMapping(
            entity_type="location",
            raw_value="Sorgues (84)",
            canonical_value="Sorgues",
            match_mode="exact",
            status="approved",
        ),
        EntityMapping(
            entity_type="location",
            raw_value="SORGUES",
            canonical_value="Sorgues",
            match_mode="exact",
            status="approved",
        ),
        EntityMapping(
            entity_type="location",
            raw_value="sorgues",
            canonical_value="Sorgues",
            match_mode="exact",
            status="approved",
        ),
        EntityMapping(
            entity_type="location",
            raw_value="Kallo",
            canonical_value="Kallo (BE)",
            match_mode="prefix",
            status="approved",
        ),
        EntityMapping(
            entity_type="material",
            raw_value="NEH",
            canonical_value="Nitrate Ethyle Hexyl",
            match_mode="exact",
            status="approved",
        ),
        # A pending_review mapping -- should NOT appear in get_mappings
        EntityMapping(
            entity_type="location",
            raw_value="Dunkerque",
            canonical_value="Dunkerque",
            match_mode="exact",
            status="pending_review",
            confidence=0.75,
        ),
        # A rejected mapping -- should NOT appear in get_mappings
        EntityMapping(
            entity_type="location",
            raw_value="Rejected Place",
            canonical_value="ShouldNotAppear",
            match_mode="exact",
            status="rejected",
        ),
    ]
    db_session.add_all(mappings)
    db_session.commit()
    return db_session


# ---------------------------------------------------------------------------
# get_mappings
# ---------------------------------------------------------------------------


class TestGetMappings:
    def test_returns_exact_approved_only(self, seeded_session):
        m = get_mappings(seeded_session, "location")
        assert "Sorgues (84)" in m
        assert m["Sorgues (84)"] == "Sorgues"
        assert "SORGUES" in m
        assert "sorgues" in m
        # Prefix mapping should NOT be returned
        assert "Kallo" not in m
        # Pending / rejected should NOT be returned
        assert "Dunkerque" not in m
        assert "Rejected Place" not in m

    def test_empty_for_unknown_type(self, seeded_session):
        m = get_mappings(seeded_session, "unknown_type")
        assert m == {}

    def test_empty_db(self, db_session):
        m = get_mappings(db_session, "location")
        assert m == {}

    def test_material_type(self, seeded_session):
        m = get_mappings(seeded_session, "material")
        assert m == {"NEH": "Nitrate Ethyle Hexyl"}


# ---------------------------------------------------------------------------
# get_prefix_mappings
# ---------------------------------------------------------------------------


class TestGetPrefixMappings:
    def test_returns_prefix_approved_only(self, seeded_session):
        m = get_prefix_mappings(seeded_session, "location")
        assert "Kallo" in m
        assert m["Kallo"] == "Kallo (BE)"
        # Exact mappings should NOT be returned
        assert "Sorgues (84)" not in m

    def test_empty_for_type_without_prefix(self, seeded_session):
        m = get_prefix_mappings(seeded_session, "material")
        assert m == {}


# ---------------------------------------------------------------------------
# get_reverse_mappings
# ---------------------------------------------------------------------------


class TestGetReverseMappings:
    def test_groups_by_canonical(self, seeded_session):
        rm = get_reverse_mappings(seeded_session, "location")
        assert "Sorgues" in rm
        assert set(rm["Sorgues"]) == {"Sorgues (84)", "SORGUES", "sorgues"}
        assert "Kallo (BE)" in rm
        assert rm["Kallo (BE)"] == ["Kallo"]

    def test_excludes_non_approved(self, seeded_session):
        rm = get_reverse_mappings(seeded_session, "location")
        # Pending and rejected should not appear
        assert "Dunkerque" not in rm
        assert "ShouldNotAppear" not in rm

    def test_empty_type(self, db_session):
        rm = get_reverse_mappings(db_session, "location")
        assert rm == {}


# ---------------------------------------------------------------------------
# resolve_column — exact matching
# ---------------------------------------------------------------------------


class TestResolveColumnExact:
    def test_exact_match(self):
        df = pd.DataFrame({"lieu_depart": ["Sorgues (84)", "SORGUES", "Paris"]})
        mappings = {
            "Sorgues (84)": "Sorgues",
            "SORGUES": "Sorgues",
        }
        result = resolve_column(df, "lieu_depart", mappings)
        assert "resolved_lieu_depart" in result.columns
        assert list(result["resolved_lieu_depart"]) == [
            "Sorgues",
            "Sorgues",
            "Paris",
        ]

    def test_no_mappings(self):
        df = pd.DataFrame({"lieu_depart": ["Paris", "Lyon"]})
        result = resolve_column(df, "lieu_depart", {})
        assert list(result["resolved_lieu_depart"]) == ["Paris", "Lyon"]

    def test_all_mapped(self):
        df = pd.DataFrame({"type_matiere": ["NEH", "NEH"]})
        mappings = {"NEH": "Nitrate Ethyle Hexyl"}
        result = resolve_column(df, "type_matiere", mappings)
        assert list(result["resolved_type_matiere"]) == [
            "Nitrate Ethyle Hexyl",
            "Nitrate Ethyle Hexyl",
        ]

    def test_none_values_preserved(self):
        df = pd.DataFrame({"lieu_depart": [None, "Paris"]})
        result = resolve_column(df, "lieu_depart", {"Paris": "Paris (FR)"})
        assert result["resolved_lieu_depart"].iloc[0] is None
        assert result["resolved_lieu_depart"].iloc[1] == "Paris (FR)"

    def test_nan_values_preserved(self):
        df = pd.DataFrame({"lieu_depart": [float("nan"), "Paris"]})
        result = resolve_column(df, "lieu_depart", {"Paris": "Paris (FR)"})
        assert pd.isna(result["resolved_lieu_depart"].iloc[0])
        assert result["resolved_lieu_depart"].iloc[1] == "Paris (FR)"

    def test_empty_dataframe(self):
        df = pd.DataFrame({"lieu_depart": pd.Series([], dtype="object")})
        result = resolve_column(df, "lieu_depart", {"X": "Y"})
        assert "resolved_lieu_depart" in result.columns
        assert len(result) == 0


# ---------------------------------------------------------------------------
# resolve_column — prefix matching
# ---------------------------------------------------------------------------


class TestResolveColumnPrefix:
    def test_prefix_match(self):
        df = pd.DataFrame(
            {"lieu_depart": ["Kallo Terminal 1", "Kallo North", "Paris"]}
        )
        mappings = {}  # no exact matches
        prefix_mappings = {"Kallo": "Kallo (BE)"}
        result = resolve_column(df, "lieu_depart", mappings, prefix_mappings)
        assert list(result["resolved_lieu_depart"]) == [
            "Kallo (BE)",
            "Kallo (BE)",
            "Paris",
        ]

    def test_exact_takes_priority_over_prefix(self):
        df = pd.DataFrame({"lieu": ["Kallo Terminal 1"]})
        mappings = {"Kallo Terminal 1": "Kallo Terminal 1 (exact)"}
        prefix_mappings = {"Kallo": "Kallo (BE)"}
        result = resolve_column(df, "lieu", mappings, prefix_mappings)
        assert result["resolved_lieu"].iloc[0] == "Kallo Terminal 1 (exact)"

    def test_longest_prefix_wins(self):
        df = pd.DataFrame({"lieu": ["Kallo North Dock"]})
        prefix_mappings = {
            "Kallo": "Kallo (BE)",
            "Kallo North": "Kallo North (BE)",
        }
        result = resolve_column(df, "lieu", {}, prefix_mappings)
        assert result["resolved_lieu"].iloc[0] == "Kallo North (BE)"

    def test_no_prefix_match(self):
        df = pd.DataFrame({"lieu": ["Paris"]})
        prefix_mappings = {"Kallo": "Kallo (BE)"}
        result = resolve_column(df, "lieu", {}, prefix_mappings)
        assert result["resolved_lieu"].iloc[0] == "Paris"


# ---------------------------------------------------------------------------
# expand_canonical
# ---------------------------------------------------------------------------


class TestExpandCanonical:
    def test_basic_expansion(self, seeded_session):
        values = expand_canonical(seeded_session, "location", "Sorgues")
        assert "Sorgues" in values
        assert "Sorgues (84)" in values
        assert "SORGUES" in values
        assert "sorgues" in values
        assert len(values) == 4  # canonical + 3 raw

    def test_canonical_always_included(self, seeded_session):
        """Even when the canonical itself is not a raw_value in any mapping."""
        values = expand_canonical(seeded_session, "material", "Nitrate Ethyle Hexyl")
        assert "Nitrate Ethyle Hexyl" in values
        assert "NEH" in values

    def test_no_mappings(self, seeded_session):
        values = expand_canonical(seeded_session, "location", "UnknownCity")
        assert values == ["UnknownCity"]

    def test_empty_db(self, db_session):
        values = expand_canonical(db_session, "location", "Paris")
        assert values == ["Paris"]


# ---------------------------------------------------------------------------
# merge_entities
# ---------------------------------------------------------------------------


class TestMergeEntities:
    def test_basic_merge(self, db_session):
        audit = merge_entities(
            db_session,
            entity_type="location",
            canonical="Sorgues",
            raw_values=["Sorgues (84)", "SORGUES", "sorgues"],
            performed_by="test_user",
            notes="Test merge",
        )
        assert audit.id is not None
        assert audit.entity_type == "location"
        assert audit.action == "merge"
        assert audit.canonical_value == "Sorgues"
        assert json.loads(audit.raw_values_json) == [
            "Sorgues (84)",
            "SORGUES",
            "sorgues",
        ]
        assert audit.performed_by == "test_user"
        assert audit.reverted is False

        # Verify mappings were created
        m = get_mappings(db_session, "location")
        assert m["Sorgues (84)"] == "Sorgues"
        assert m["SORGUES"] == "Sorgues"
        assert m["sorgues"] == "Sorgues"

    def test_merge_with_prefix_mode(self, db_session):
        audit = merge_entities(
            db_session,
            entity_type="location",
            canonical="Kallo (BE)",
            raw_values=["Kallo"],
            match_mode="prefix",
        )
        assert audit.id is not None

        # Should NOT appear in exact mappings
        exact = get_mappings(db_session, "location")
        assert "Kallo" not in exact

        # Should appear in prefix mappings
        prefix = get_prefix_mappings(db_session, "location")
        assert prefix["Kallo"] == "Kallo (BE)"

    def test_merge_updates_existing_mapping(self, db_session):
        # Create initial mapping
        merge_entities(
            db_session,
            entity_type="material",
            canonical="OldName",
            raw_values=["NEH"],
        )
        m = get_mappings(db_session, "material")
        assert m["NEH"] == "OldName"

        # Merge again with new canonical
        merge_entities(
            db_session,
            entity_type="material",
            canonical="Nitrate Ethyle Hexyl",
            raw_values=["NEH"],
            source="auto",
            confidence=0.9,
        )
        m = get_mappings(db_session, "material")
        assert m["NEH"] == "Nitrate Ethyle Hexyl"

    def test_merge_creates_audit_log(self, db_session):
        merge_entities(
            db_session,
            entity_type="location",
            canonical="Sorgues",
            raw_values=["Sorgues (84)"],
        )
        logs = db_session.query(MergeAuditLog).all()
        assert len(logs) == 1
        assert logs[0].action == "merge"
        assert logs[0].canonical_value == "Sorgues"

    def test_merge_sets_approved_status(self, db_session):
        # First create a pending mapping
        pending = EntityMapping(
            entity_type="location",
            raw_value="Dunkerque Port",
            canonical_value="Dunkerque",
            status="pending_review",
            confidence=0.6,
        )
        db_session.add(pending)
        db_session.commit()

        # Now merge -- should update to approved
        merge_entities(
            db_session,
            entity_type="location",
            canonical="Dunkerque",
            raw_values=["Dunkerque Port"],
            confidence=1.0,
        )
        m = get_mappings(db_session, "location")
        assert m["Dunkerque Port"] == "Dunkerque"

    def test_merge_empty_raw_values(self, db_session):
        audit = merge_entities(
            db_session,
            entity_type="location",
            canonical="Nowhere",
            raw_values=[],
        )
        assert audit.id is not None
        assert json.loads(audit.raw_values_json) == []
        m = get_mappings(db_session, "location")
        assert m == {}


# ---------------------------------------------------------------------------
# revert_merge
# ---------------------------------------------------------------------------


class TestRevertMerge:
    def test_basic_revert(self, db_session):
        audit = merge_entities(
            db_session,
            entity_type="location",
            canonical="Sorgues",
            raw_values=["Sorgues (84)", "SORGUES"],
        )
        # Verify mappings exist
        assert len(get_mappings(db_session, "location")) == 2

        success = revert_merge(db_session, audit.id, performed_by="admin")
        assert success is True

        # Mappings should be deleted
        assert get_mappings(db_session, "location") == {}

        # Audit log should be marked reverted
        db_session.refresh(audit)
        assert audit.reverted is True
        assert audit.reverted_at is not None

    def test_revert_nonexistent_id(self, db_session):
        assert revert_merge(db_session, 9999) is False

    def test_revert_already_reverted(self, db_session):
        audit = merge_entities(
            db_session,
            entity_type="location",
            canonical="Sorgues",
            raw_values=["SORGUES"],
        )
        assert revert_merge(db_session, audit.id) is True
        # Trying again should return False
        assert revert_merge(db_session, audit.id) is False

    def test_revert_does_not_affect_other_mappings(self, db_session):
        # Create two separate merges
        audit1 = merge_entities(
            db_session,
            entity_type="location",
            canonical="Sorgues",
            raw_values=["SORGUES"],
        )
        _audit2 = merge_entities(
            db_session,
            entity_type="location",
            canonical="Paris",
            raw_values=["PARIS"],
        )

        # Revert only the first merge
        revert_merge(db_session, audit1.id)

        m = get_mappings(db_session, "location")
        assert "SORGUES" not in m
        assert "PARIS" in m
        assert m["PARIS"] == "Paris"

    def test_revert_notes_appended(self, db_session):
        audit = merge_entities(
            db_session,
            entity_type="material",
            canonical="NEH",
            raw_values=["neh"],
            notes="Original note",
        )
        revert_merge(db_session, audit.id, performed_by="bob")
        db_session.refresh(audit)
        assert "Reverted by bob" in audit.notes


# ---------------------------------------------------------------------------
# get_pending_reviews
# ---------------------------------------------------------------------------


class TestGetPendingReviews:
    def test_returns_pending_ordered_by_confidence(self, db_session):
        db_session.add_all(
            [
                EntityMapping(
                    entity_type="location",
                    raw_value="A",
                    canonical_value="A_canon",
                    status="pending_review",
                    confidence=0.5,
                ),
                EntityMapping(
                    entity_type="location",
                    raw_value="B",
                    canonical_value="B_canon",
                    status="pending_review",
                    confidence=0.9,
                ),
                EntityMapping(
                    entity_type="location",
                    raw_value="C",
                    canonical_value="C_canon",
                    status="approved",
                    confidence=1.0,
                ),
            ]
        )
        db_session.commit()

        pending = get_pending_reviews(db_session)
        assert len(pending) == 2
        # Highest confidence first
        assert pending[0].raw_value == "B"
        assert pending[1].raw_value == "A"

    def test_empty_when_none_pending(self, db_session):
        db_session.add(
            EntityMapping(
                entity_type="location",
                raw_value="X",
                canonical_value="X_canon",
                status="approved",
            )
        )
        db_session.commit()
        assert get_pending_reviews(db_session) == []

    def test_empty_db(self, db_session):
        assert get_pending_reviews(db_session) == []


# ---------------------------------------------------------------------------
# get_distinct_values
# ---------------------------------------------------------------------------


class TestGetDistinctValues:
    @pytest.fixture
    def populated_session(self, db_session):
        """Session with LigneFacture, Fournisseur, Document rows."""
        # Create a fournisseur + document so we can add lines
        f = Fournisseur(nom="Transports Fockedey s.a.")
        db_session.add(f)
        db_session.flush()

        d = Document(
            fichier="test.pdf",
            type_document="facture",
            fournisseur_id=f.id,
            client_nom="ACME Corp",
            confiance_globale=0.9,
        )
        db_session.add(d)
        db_session.flush()

        # Lines with location and material data
        lines = [
            LigneFacture(
                document_id=d.id,
                type_matiere="NEH",
                lieu_depart="Sorgues (84)",
                lieu_arrivee="Kallo Terminal 1",
            ),
            LigneFacture(
                document_id=d.id,
                type_matiere="Acide Sulfurique",
                lieu_depart="SORGUES",
                lieu_arrivee="Paris",
            ),
            LigneFacture(
                document_id=d.id,
                type_matiere="NEH",
                lieu_depart="Lyon",
                lieu_arrivee="Kallo North",
            ),
        ]
        db_session.add_all(lines)

        # Add a second fournisseur
        f2 = Fournisseur(nom="Fockedey")
        db_session.add(f2)

        # Add another document with a different client
        d2 = Document(
            fichier="test2.pdf",
            type_document="facture",
            fournisseur_id=f2.id,
            client_nom="BigCo",
            confiance_globale=0.8,
        )
        db_session.add(d2)
        db_session.commit()
        return db_session

    def test_location_without_mappings(self, populated_session):
        values = get_distinct_values(populated_session, "location")
        # All raw values should be returned as-is, sorted
        expected = sorted(
            {"Sorgues (84)", "SORGUES", "Lyon", "Kallo Terminal 1", "Kallo North", "Paris"}
        )
        assert values == expected

    def test_location_with_exact_mappings(self, populated_session):
        # Map the Sorgues variants
        merge_entities(
            populated_session,
            entity_type="location",
            canonical="Sorgues",
            raw_values=["Sorgues (84)", "SORGUES"],
        )
        values = get_distinct_values(populated_session, "location")
        # Sorgues (84) and SORGUES should resolve to "Sorgues"
        assert "Sorgues" in values
        assert "Sorgues (84)" not in values
        assert "SORGUES" not in values
        # Others remain
        assert "Lyon" in values
        assert "Paris" in values

    def test_location_with_prefix_mappings(self, populated_session):
        merge_entities(
            populated_session,
            entity_type="location",
            canonical="Kallo (BE)",
            raw_values=["Kallo"],
            match_mode="prefix",
        )
        values = get_distinct_values(populated_session, "location")
        # "Kallo Terminal 1" and "Kallo North" should both resolve to "Kallo (BE)"
        assert "Kallo (BE)" in values
        assert "Kallo Terminal 1" not in values
        assert "Kallo North" not in values

    def test_material(self, populated_session):
        values = get_distinct_values(populated_session, "material")
        assert "NEH" in values
        assert "Acide Sulfurique" in values

    def test_material_with_mapping(self, populated_session):
        merge_entities(
            populated_session,
            entity_type="material",
            canonical="Nitrate Ethyle Hexyl",
            raw_values=["NEH"],
        )
        values = get_distinct_values(populated_session, "material")
        assert "Nitrate Ethyle Hexyl" in values
        assert "NEH" not in values
        assert "Acide Sulfurique" in values

    def test_supplier(self, populated_session):
        values = get_distinct_values(populated_session, "supplier")
        assert "Transports Fockedey s.a." in values
        assert "Fockedey" in values

    def test_supplier_with_mapping(self, populated_session):
        merge_entities(
            populated_session,
            entity_type="supplier",
            canonical="Transports Fockedey s.a.",
            raw_values=["Fockedey"],
        )
        values = get_distinct_values(populated_session, "supplier")
        assert "Transports Fockedey s.a." in values
        assert "Fockedey" not in values
        assert len(values) == 1

    def test_company(self, populated_session):
        values = get_distinct_values(populated_session, "company")
        assert "ACME Corp" in values
        assert "BigCo" in values

    def test_unknown_entity_type(self, db_session):
        values = get_distinct_values(db_session, "nonexistent")
        assert values == []

    def test_empty_db(self, db_session):
        values = get_distinct_values(db_session, "location")
        assert values == []

    def test_null_values_excluded(self, db_session):
        f = Fournisseur(nom="Test")
        db_session.add(f)
        db_session.flush()
        d = Document(
            fichier="test.pdf",
            type_document="facture",
            fournisseur_id=f.id,
            confiance_globale=0.9,
        )
        db_session.add(d)
        db_session.flush()
        # Line with null locations
        line = LigneFacture(
            document_id=d.id,
            type_matiere=None,
            lieu_depart=None,
            lieu_arrivee="Paris",
        )
        db_session.add(line)
        db_session.commit()

        values = get_distinct_values(db_session, "location")
        assert values == ["Paris"]

        values = get_distinct_values(db_session, "material")
        assert values == []


# ---------------------------------------------------------------------------
# Integration: full merge -> resolve -> expand -> revert cycle
# ---------------------------------------------------------------------------


class TestIntegrationCycle:
    def test_full_cycle(self, db_session):
        # 1. Merge
        audit = merge_entities(
            db_session,
            entity_type="location",
            canonical="Sorgues",
            raw_values=["Sorgues (84)", "SORGUES", "sorgues"],
            notes="Initial merge",
        )

        # 2. Verify mappings
        m = get_mappings(db_session, "location")
        assert len(m) == 3

        # 3. Resolve a DataFrame
        df = pd.DataFrame(
            {"lieu": ["Sorgues (84)", "SORGUES", "sorgues", "Paris"]}
        )
        df = resolve_column(df, "lieu", m)
        assert list(df["resolved_lieu"]) == [
            "Sorgues",
            "Sorgues",
            "Sorgues",
            "Paris",
        ]

        # 4. Expand canonical for filtering
        expanded = expand_canonical(db_session, "location", "Sorgues")
        assert set(expanded) == {"Sorgues", "Sorgues (84)", "SORGUES", "sorgues"}

        # 5. Reverse mappings
        rev = get_reverse_mappings(db_session, "location")
        assert set(rev["Sorgues"]) == {"Sorgues (84)", "SORGUES", "sorgues"}

        # 6. Revert the merge
        assert revert_merge(db_session, audit.id) is True

        # 7. Verify mappings gone
        m = get_mappings(db_session, "location")
        assert m == {}

        # 8. expand_canonical now returns just the canonical itself
        expanded = expand_canonical(db_session, "location", "Sorgues")
        assert expanded == ["Sorgues"]
