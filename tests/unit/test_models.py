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
