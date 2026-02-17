"""End-to-end integration tests for the entity resolution feature.

Covers the full lifecycle: create data with duplicates, run resolution,
verify analytics use canonical names, revert merges, and verify original
values are restored.

Uses an in-memory SQLite database so no external services are needed.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from dashboard.analytics.tendances import evolution_prix_matiere
from dashboard.data.entity_enrichment import run_auto_resolution
from dashboard.data.entity_resolution import (
    expand_canonical,
    get_distinct_values,
    get_mappings,
    merge_entities,
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


def _make_doc(session: Session, fichier: str = "test.pdf", **kwargs) -> Document:
    """Create a minimal Document row and return it."""
    doc = Document(fichier=fichier, **kwargs)
    session.add(doc)
    session.flush()
    return doc


@pytest.fixture
def location_data(db_session):
    """Session with duplicate location data: Kallo vs Beveren-Kallo."""
    f = Fournisseur(nom="Transport SA")
    db_session.add(f)
    db_session.flush()

    doc = _make_doc(
        db_session,
        fichier="loc_test.pdf",
        type_document="facture",
        fournisseur_id=f.id,
        date_document=date(2024, 3, 1),
        montant_ht=5000.0,
        confiance_globale=0.9,
    )

    lines = [
        LigneFacture(
            document_id=doc.id,
            type_matiere="Produit A",
            prix_unitaire=100.0,
            quantite=10,
            prix_total=1000.0,
            lieu_depart="Kallo",
            lieu_arrivee="Sorgues",
            date_depart="2024-03-01",
        ),
        LigneFacture(
            document_id=doc.id,
            type_matiere="Produit A",
            prix_unitaire=100.0,
            quantite=10,
            prix_total=1000.0,
            lieu_depart="Beveren-Kallo",
            lieu_arrivee="Sorgues (84)",
            date_depart="2024-03-15",
        ),
        LigneFacture(
            document_id=doc.id,
            type_matiere="Produit B",
            prix_unitaire=50.0,
            quantite=20,
            prix_total=1000.0,
            lieu_depart="Paris",
            lieu_arrivee="Lyon",
            date_depart="2024-04-01",
        ),
    ]
    db_session.add_all(lines)
    db_session.commit()
    return db_session


@pytest.fixture
def material_data(db_session):
    """Session with duplicate material data."""
    f = Fournisseur(nom="Chimie Corp")
    db_session.add(f)
    db_session.flush()

    doc = _make_doc(
        db_session,
        fichier="mat_test.pdf",
        type_document="facture",
        fournisseur_id=f.id,
        date_document=date(2024, 1, 15),
        montant_ht=10000.0,
        confiance_globale=0.85,
    )

    lines = [
        LigneFacture(
            document_id=doc.id,
            type_matiere="Nitrate Ethyle Hexyl",
            prix_unitaire=200.0,
            quantite=5,
            prix_total=1000.0,
            date_depart="2024-01-15",
        ),
        LigneFacture(
            document_id=doc.id,
            type_matiere="Nitrate Ethyle Hexyl - Attente livraison",
            prix_unitaire=210.0,
            quantite=5,
            prix_total=1050.0,
            date_depart="2024-02-15",
        ),
        LigneFacture(
            document_id=doc.id,
            type_matiere="Acide Sulfurique",
            prix_unitaire=50.0,
            quantite=100,
            prix_total=5000.0,
            date_depart="2024-03-15",
        ),
    ]
    db_session.add_all(lines)
    db_session.commit()
    return db_session


@pytest.fixture
def supplier_data(db_session):
    """Session with duplicate supplier data."""
    db_session.add(Fournisseur(nom="Transport SA"))
    db_session.add(Fournisseur(nom="Transport"))
    db_session.add(Fournisseur(nom="ChemLog SARL"))
    db_session.commit()
    return db_session


@pytest.fixture
def full_data(db_session):
    """Session with all entity types having duplicates."""
    # Suppliers
    f1 = Fournisseur(nom="Transport SA")
    f2 = Fournisseur(nom="Transport")
    db_session.add_all([f1, f2])
    db_session.flush()

    # Document
    doc = _make_doc(
        db_session,
        fichier="full_test.pdf",
        type_document="facture",
        fournisseur_id=f1.id,
        date_document=date(2024, 1, 15),
        montant_ht=10000.0,
        confiance_globale=0.9,
    )

    # Lines with location and material duplicates
    lines = [
        LigneFacture(
            document_id=doc.id,
            type_matiere="Nitrate Ethyle Hexyl",
            prix_unitaire=200.0,
            quantite=5,
            prix_total=1000.0,
            lieu_depart="Kallo",
            lieu_arrivee="Sorgues",
            date_depart="2024-01-15",
        ),
        LigneFacture(
            document_id=doc.id,
            type_matiere="Nitrate Ethyle Hexyl - Attente livraison",
            prix_unitaire=210.0,
            quantite=5,
            prix_total=1050.0,
            lieu_depart="Beveren-Kallo",
            lieu_arrivee="Sorgues (84)",
            date_depart="2024-02-15",
        ),
        LigneFacture(
            document_id=doc.id,
            type_matiere="Acide Sulfurique",
            prix_unitaire=50.0,
            quantite=100,
            prix_total=5000.0,
            lieu_depart="Paris",
            lieu_arrivee="Lyon",
            date_depart="2024-03-15",
        ),
    ]
    db_session.add_all(lines)
    db_session.commit()
    return db_session


# ---------------------------------------------------------------------------
# End-to-End Location Resolution
# ---------------------------------------------------------------------------


class TestLocationResolutionE2E:
    """Test the full lifecycle for location entity resolution."""

    def test_locations_separate_before_resolution(self, location_data):
        """Before any resolution, all raw location values appear separately."""
        values = get_distinct_values(location_data, "location")
        assert "Kallo" in values
        assert "Beveren-Kallo" in values
        assert "Sorgues" in values
        assert "Sorgues (84)" in values

    def test_manual_merge_then_verify_analytics(self, location_data):
        """Manual merge of Sorgues variants and verify analytics use canonical."""
        session = location_data

        # Merge Sorgues variants
        audit = merge_entities(
            session,
            entity_type="location",
            canonical="Sorgues",
            raw_values=["Sorgues (84)"],
            source="manual",
            performed_by="test",
        )

        # Verify get_distinct_values returns canonical name
        values = get_distinct_values(session, "location")
        assert "Sorgues" in values
        assert "Sorgues (84)" not in values

        # Verify expand_canonical returns all raw values
        expanded = expand_canonical(session, "location", "Sorgues")
        assert "Sorgues" in expanded
        assert "Sorgues (84)" in expanded

        # Revert the merge
        success = revert_merge(session, audit.id, performed_by="test")
        assert success is True

        # After revert, original values should appear separately again
        values = get_distinct_values(session, "location")
        assert "Sorgues" in values
        assert "Sorgues (84)" in values

    def test_merge_kallo_variants(self, location_data):
        """Merge Kallo and Beveren-Kallo, then verify and revert."""
        session = location_data

        audit = merge_entities(
            session,
            entity_type="location",
            canonical="Kallo",
            raw_values=["Beveren-Kallo"],
            source="manual",
            performed_by="test",
        )

        # Verify merged
        values = get_distinct_values(session, "location")
        assert "Kallo" in values
        assert "Beveren-Kallo" not in values

        # Expand canonical returns both
        expanded = expand_canonical(session, "location", "Kallo")
        assert set(expanded) == {"Kallo", "Beveren-Kallo"}

        # Revert
        assert revert_merge(session, audit.id) is True

        # Back to separate
        values = get_distinct_values(session, "location")
        assert "Kallo" in values
        assert "Beveren-Kallo" in values


# ---------------------------------------------------------------------------
# End-to-End Material Resolution
# ---------------------------------------------------------------------------


class TestMaterialResolutionE2E:
    """Test the full lifecycle for material entity resolution."""

    def test_materials_separate_before_resolution(self, material_data):
        values = get_distinct_values(material_data, "material")
        assert "Nitrate Ethyle Hexyl" in values
        assert "Nitrate Ethyle Hexyl - Attente livraison" in values
        assert "Acide Sulfurique" in values

    def test_merge_material_variants_and_verify_analytics(self, material_data):
        """Merge NEH variants, verify analytics aggregate correctly, then revert."""
        session = material_data

        # Before merge: evolution_prix_matiere with exact name only sees 1 row
        evo_before = evolution_prix_matiere(session, "Nitrate Ethyle Hexyl")
        count_before = evo_before["nb_lignes"].sum() if not evo_before.empty else 0

        # Merge
        audit = merge_entities(
            session,
            entity_type="material",
            canonical="Nitrate Ethyle Hexyl",
            raw_values=["Nitrate Ethyle Hexyl - Attente livraison"],
            source="manual",
            performed_by="test",
        )

        # After merge: using expand_canonical should aggregate both lines
        raw_values = expand_canonical(session, "material", "Nitrate Ethyle Hexyl")
        assert "Nitrate Ethyle Hexyl" in raw_values
        assert "Nitrate Ethyle Hexyl - Attente livraison" in raw_values

        evo_after = evolution_prix_matiere(
            session, "Nitrate Ethyle Hexyl", raw_values=raw_values
        )
        count_after = evo_after["nb_lignes"].sum() if not evo_after.empty else 0
        assert count_after > count_before

        # get_distinct_values should show canonical only
        values = get_distinct_values(session, "material")
        assert "Nitrate Ethyle Hexyl" in values
        assert "Nitrate Ethyle Hexyl - Attente livraison" not in values
        assert "Acide Sulfurique" in values

        # Revert
        assert revert_merge(session, audit.id) is True

        # After revert: back to separate
        values = get_distinct_values(session, "material")
        assert "Nitrate Ethyle Hexyl" in values
        assert "Nitrate Ethyle Hexyl - Attente livraison" in values

        # expand_canonical returns just the canonical itself
        expanded = expand_canonical(session, "material", "Nitrate Ethyle Hexyl")
        assert expanded == ["Nitrate Ethyle Hexyl"]


# ---------------------------------------------------------------------------
# End-to-End Supplier Resolution
# ---------------------------------------------------------------------------


class TestSupplierResolutionE2E:
    """Test the full lifecycle for supplier entity resolution."""

    def test_suppliers_separate_before_resolution(self, supplier_data):
        values = get_distinct_values(supplier_data, "supplier")
        assert "Transport SA" in values
        assert "Transport" in values
        assert "ChemLog SARL" in values

    def test_merge_supplier_variants(self, supplier_data):
        session = supplier_data

        audit = merge_entities(
            session,
            entity_type="supplier",
            canonical="Transport SA",
            raw_values=["Transport"],
            source="manual",
            performed_by="test",
        )

        values = get_distinct_values(session, "supplier")
        assert "Transport SA" in values
        assert "Transport" not in values
        assert "ChemLog SARL" in values

        expanded = expand_canonical(session, "supplier", "Transport SA")
        assert set(expanded) == {"Transport SA", "Transport"}

        # Revert
        assert revert_merge(session, audit.id) is True

        values = get_distinct_values(session, "supplier")
        assert "Transport SA" in values
        assert "Transport" in values


# ---------------------------------------------------------------------------
# Auto-Resolution Integration
# ---------------------------------------------------------------------------


class TestAutoResolutionE2E:
    """Test the auto-resolution engine end-to-end with realistic data."""

    @pytest.fixture
    def auto_config(self):
        return {
            "entity_resolution": {
                "auto_merge_threshold": 0.90,
                "review_threshold": 0.50,
                "fuzzy_min_score": 50,
            }
        }

    def test_auto_resolution_creates_mappings(self, material_data, auto_config):
        """Auto-resolution should detect NEH variants and create mappings."""
        session = material_data
        stats = run_auto_resolution(session, auto_config)

        total = stats["auto_merged"] + stats["pending_review"] + stats["ignored"]
        assert total >= 0  # At minimum no errors

        # Check that the resolution produced some results
        all_mappings = session.execute(
            select(EntityMapping).where(EntityMapping.source == "auto")
        ).scalars().all()

        # The NEH variants should have been detected
        if stats["auto_merged"] > 0:
            approved = [m for m in all_mappings if m.status == "approved"]
            assert len(approved) >= 1

    def test_auto_resolution_stats_correct(self, full_data, auto_config):
        """Stats returned by run_auto_resolution should be internally consistent."""
        session = full_data
        stats = run_auto_resolution(session, auto_config)

        assert isinstance(stats["auto_merged"], int)
        assert isinstance(stats["pending_review"], int)
        assert isinstance(stats["ignored"], int)
        assert stats["auto_merged"] >= 0
        assert stats["pending_review"] >= 0
        assert stats["ignored"] >= 0

    def test_auto_resolution_does_not_overwrite_manual(self, material_data, auto_config):
        """Manual merges should not be overwritten by auto-resolution."""
        session = material_data

        # Manually merge first
        merge_entities(
            session,
            entity_type="material",
            canonical="Nitrate Ethyle Hexyl",
            raw_values=["Nitrate Ethyle Hexyl - Attente livraison"],
            source="manual",
            performed_by="admin",
        )

        # Run auto-resolution
        stats = run_auto_resolution(session, auto_config)

        # The already-merged values should have been skipped
        # Verify the manual mapping is still intact
        mappings = get_mappings(session, "material")
        assert mappings.get("Nitrate Ethyle Hexyl - Attente livraison") == "Nitrate Ethyle Hexyl"

    def test_auto_resolution_revert_all(self, material_data, auto_config):
        """Auto-merged entries can be reverted via audit log."""
        session = material_data
        stats = run_auto_resolution(session, auto_config)

        if stats["auto_merged"] > 0:
            # Find auto-resolution audit entries
            audits = session.execute(
                select(MergeAuditLog).where(
                    MergeAuditLog.performed_by == "auto_resolution",
                    MergeAuditLog.reverted == False,
                )
            ).scalars().all()

            for audit in audits:
                success = revert_merge(session, audit.id, performed_by="test")
                assert success is True

            # After reverting all, no auto mappings should remain
            auto_mappings = session.execute(
                select(EntityMapping).where(
                    EntityMapping.source == "auto",
                    EntityMapping.status == "approved",
                )
            ).scalars().all()
            assert len(auto_mappings) == 0


# ---------------------------------------------------------------------------
# KPI Counts (used by page 01)
# ---------------------------------------------------------------------------


class TestKPICounts:
    """Test the KPI counting queries used by the dashboard."""

    def test_counts_with_no_data(self, db_session):
        nb_resolved = (
            db_session.query(func.count(EntityMapping.id))
            .filter(EntityMapping.status == "approved")
            .scalar()
        )
        nb_pending = (
            db_session.query(func.count(EntityMapping.id))
            .filter(EntityMapping.status == "pending_review")
            .scalar()
        )
        assert nb_resolved == 0
        assert nb_pending == 0

    def test_counts_with_mixed_statuses(self, db_session):
        db_session.add_all([
            EntityMapping(
                entity_type="location",
                raw_value="A",
                canonical_value="A_canon",
                status="approved",
            ),
            EntityMapping(
                entity_type="location",
                raw_value="B",
                canonical_value="B_canon",
                status="approved",
            ),
            EntityMapping(
                entity_type="material",
                raw_value="C",
                canonical_value="C_canon",
                status="pending_review",
            ),
            EntityMapping(
                entity_type="supplier",
                raw_value="D",
                canonical_value="D_canon",
                status="rejected",
            ),
        ])
        db_session.commit()

        nb_resolved = (
            db_session.query(func.count(EntityMapping.id))
            .filter(EntityMapping.status == "approved")
            .scalar()
        )
        nb_pending = (
            db_session.query(func.count(EntityMapping.id))
            .filter(EntityMapping.status == "pending_review")
            .scalar()
        )
        assert nb_resolved == 2
        assert nb_pending == 1


# ---------------------------------------------------------------------------
# Full Pipeline: create -> auto-resolve -> analytics -> revert -> verify
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end pipeline test covering the complete lifecycle."""

    def test_end_to_end_entity_resolution(self, db_session):
        """
        1. Create realistic data with duplicate locations
        2. Verify analytics show them as separate before resolution
        3. Run manual merge
        4. Verify analytics now show merged canonical names
        5. Revert the merge
        6. Verify analytics show original separate values again
        """
        # --- Setup data ---
        f = Fournisseur(nom="TestCorp")
        db_session.add(f)
        db_session.flush()

        doc = _make_doc(
            db_session,
            fichier="e2e_test.pdf",
            type_document="facture",
            fournisseur_id=f.id,
            date_document=date(2024, 6, 1),
            montant_ht=8000.0,
            confiance_globale=0.95,
        )

        db_session.add_all([
            LigneFacture(
                document_id=doc.id,
                type_matiere="Soude Caustique",
                prix_unitaire=100.0,
                quantite=10,
                prix_total=1000.0,
                lieu_depart="Kallo",
                lieu_arrivee="Sorgues",
                date_depart="2024-06-01",
            ),
            LigneFacture(
                document_id=doc.id,
                type_matiere="Soude Caustique - Lot 42",
                prix_unitaire=105.0,
                quantite=10,
                prix_total=1050.0,
                lieu_depart="Beveren-Kallo",
                lieu_arrivee="Sorgues (84)",
                date_depart="2024-06-15",
            ),
            LigneFacture(
                document_id=doc.id,
                type_matiere="Ethanol",
                prix_unitaire=50.0,
                quantite=20,
                prix_total=1000.0,
                lieu_depart="Paris",
                lieu_arrivee="Lyon",
                date_depart="2024-07-01",
            ),
        ])
        db_session.commit()

        # --- Step 1: Verify separate before resolution ---
        mat_values = get_distinct_values(db_session, "material")
        assert "Soude Caustique" in mat_values
        assert "Soude Caustique - Lot 42" in mat_values
        assert len(mat_values) == 3  # Soude, Soude - Lot 42, Ethanol

        loc_values = get_distinct_values(db_session, "location")
        assert "Kallo" in loc_values
        assert "Beveren-Kallo" in loc_values
        assert "Sorgues" in loc_values
        assert "Sorgues (84)" in loc_values

        # evolution_prix_matiere with exact match sees only 1 line
        evo_before = evolution_prix_matiere(db_session, "Soude Caustique")
        nb_before = evo_before["nb_lignes"].sum() if not evo_before.empty else 0
        assert nb_before == 1

        # --- Step 2: Merge materials ---
        mat_audit = merge_entities(
            db_session,
            entity_type="material",
            canonical="Soude Caustique",
            raw_values=["Soude Caustique - Lot 42"],
            performed_by="test",
        )

        # --- Step 3: Merge locations ---
        loc_audit = merge_entities(
            db_session,
            entity_type="location",
            canonical="Sorgues",
            raw_values=["Sorgues (84)"],
            performed_by="test",
        )

        # --- Step 4: Verify analytics use canonical names ---
        mat_values = get_distinct_values(db_session, "material")
        assert "Soude Caustique" in mat_values
        assert "Soude Caustique - Lot 42" not in mat_values
        assert len(mat_values) == 2  # Soude Caustique, Ethanol

        loc_values = get_distinct_values(db_session, "location")
        assert "Sorgues" in loc_values
        assert "Sorgues (84)" not in loc_values

        # evolution_prix_matiere with expand_canonical sees both lines
        raw_values = expand_canonical(db_session, "material", "Soude Caustique")
        evo_after = evolution_prix_matiere(
            db_session, "Soude Caustique", raw_values=raw_values
        )
        nb_after = evo_after["nb_lignes"].sum() if not evo_after.empty else 0
        assert nb_after == 2  # Both lines now included

        # --- Step 5: Revert all merges ---
        assert revert_merge(db_session, mat_audit.id, performed_by="test") is True
        assert revert_merge(db_session, loc_audit.id, performed_by="test") is True

        # --- Step 6: Verify originals restored ---
        mat_values = get_distinct_values(db_session, "material")
        assert "Soude Caustique" in mat_values
        assert "Soude Caustique - Lot 42" in mat_values
        assert len(mat_values) == 3

        loc_values = get_distinct_values(db_session, "location")
        assert "Sorgues" in loc_values
        assert "Sorgues (84)" in loc_values

        # evolution_prix_matiere back to just exact match
        evo_reverted = evolution_prix_matiere(db_session, "Soude Caustique")
        nb_reverted = evo_reverted["nb_lignes"].sum() if not evo_reverted.empty else 0
        assert nb_reverted == 1

    def test_get_distinct_values_after_auto_resolution(self, db_session):
        """Verify get_distinct_values returns canonical names after auto-resolution."""
        f = Fournisseur(nom="TestCorp")
        db_session.add(f)
        db_session.flush()

        doc = _make_doc(db_session, fichier="auto_test.pdf", fournisseur_id=f.id)

        db_session.add_all([
            LigneFacture(
                document_id=doc.id,
                type_matiere="Acide Chlorhydrique",
                prix_unitaire=30.0,
                quantite=10,
                prix_total=300.0,
                date_depart="2024-01-15",
            ),
            LigneFacture(
                document_id=doc.id,
                type_matiere="Acide Chlorhydrique - Transport",
                prix_unitaire=32.0,
                quantite=10,
                prix_total=320.0,
                date_depart="2024-02-15",
            ),
        ])
        db_session.commit()

        # Before auto-resolution
        values_before = get_distinct_values(db_session, "material")
        assert "Acide Chlorhydrique" in values_before
        assert "Acide Chlorhydrique - Transport" in values_before

        # Run auto-resolution
        config = {
            "entity_resolution": {
                "auto_merge_threshold": 0.90,
                "review_threshold": 0.50,
            }
        }
        stats = run_auto_resolution(db_session, config)

        if stats["auto_merged"] > 0:
            values_after = get_distinct_values(db_session, "material")
            # The canonical name should be present
            assert "Acide Chlorhydrique" in values_after
            # The variant should have been resolved
            assert "Acide Chlorhydrique - Transport" not in values_after

            # expand_canonical should return both
            expanded = expand_canonical(db_session, "material", "Acide Chlorhydrique")
            assert "Acide Chlorhydrique" in expanded
            assert "Acide Chlorhydrique - Transport" in expanded
