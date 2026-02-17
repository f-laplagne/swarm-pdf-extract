"""Tests for domain models — pure Python, no external dependencies."""

from enum import Enum

import pytest


# ── Task 2: Enum tests ─────────────────────────────────────────────────


class TestTypeDocument:
    def test_is_enum(self):
        from domain.models import TypeDocument
        assert issubclass(TypeDocument, Enum)

    def test_values(self):
        from domain.models import TypeDocument
        expected = {
            "facture",
            "bon_livraison",
            "devis",
            "bon_commande",
            "avoir",
            "releve",
            "autre",
        }
        assert {m.value for m in TypeDocument} == expected

    def test_lookup_by_value(self):
        from domain.models import TypeDocument
        assert TypeDocument("facture") is TypeDocument.FACTURE

    def test_lookup_by_name(self):
        from domain.models import TypeDocument
        assert TypeDocument["BON_LIVRAISON"] is TypeDocument.BON_LIVRAISON


class TestStatutMapping:
    def test_is_enum(self):
        from domain.models import StatutMapping
        assert issubclass(StatutMapping, Enum)

    def test_values(self):
        from domain.models import StatutMapping
        expected = {"approved", "pending_review", "rejected"}
        assert {m.value for m in StatutMapping} == expected

    def test_lookup_by_value(self):
        from domain.models import StatutMapping
        assert StatutMapping("approved") is StatutMapping.APPROVED

    def test_lookup_by_name(self):
        from domain.models import StatutMapping
        assert StatutMapping["PENDING_REVIEW"] is StatutMapping.PENDING_REVIEW


class TestNiveauSeverite:
    def test_is_enum(self):
        from domain.models import NiveauSeverite
        assert issubclass(NiveauSeverite, Enum)

    def test_values(self):
        from domain.models import NiveauSeverite
        expected = {"info", "warning", "error"}
        assert {m.value for m in NiveauSeverite} == expected

    def test_lookup_by_value(self):
        from domain.models import NiveauSeverite
        assert NiveauSeverite("warning") is NiveauSeverite.WARNING

    def test_lookup_by_name(self):
        from domain.models import NiveauSeverite
        assert NiveauSeverite["ERROR"] is NiveauSeverite.ERROR


# ── Task 3: ScoreConfiance value object tests ──────────────────────────


class TestScoreConfiance:
    def test_defaults_are_zero(self):
        from domain.models import ScoreConfiance
        sc = ScoreConfiance()
        for field_name in (
            "type_matiere", "unite", "prix_unitaire", "quantite",
            "prix_total", "date_depart", "date_arrivee",
            "lieu_depart", "lieu_arrivee",
        ):
            assert getattr(sc, field_name) == 0.0

    def test_custom_values(self):
        from domain.models import ScoreConfiance
        sc = ScoreConfiance(
            type_matiere=0.95,
            unite=0.80,
            prix_unitaire=0.70,
            quantite=0.60,
            prix_total=0.50,
            date_depart=0.40,
            date_arrivee=0.30,
            lieu_depart=0.20,
            lieu_arrivee=0.10,
        )
        assert sc.type_matiere == 0.95
        assert sc.unite == 0.80
        assert sc.prix_unitaire == 0.70
        assert sc.quantite == 0.60
        assert sc.prix_total == 0.50
        assert sc.date_depart == 0.40
        assert sc.date_arrivee == 0.30
        assert sc.lieu_depart == 0.20
        assert sc.lieu_arrivee == 0.10

    def test_frozen_cannot_mutate(self):
        from domain.models import ScoreConfiance
        sc = ScoreConfiance(type_matiere=0.9)
        with pytest.raises(AttributeError):
            sc.type_matiere = 0.5  # type: ignore[misc]

    def test_equality(self):
        from domain.models import ScoreConfiance
        a = ScoreConfiance(type_matiere=0.9, unite=0.8)
        b = ScoreConfiance(type_matiere=0.9, unite=0.8)
        assert a == b
