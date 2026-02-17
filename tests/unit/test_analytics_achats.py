"""Tests for domain.analytics.achats — purchasing analytics."""

import pytest

from domain.analytics.achats import (
    fragmentation_index,
    rank_suppliers_by_amount,
    weighted_average_price,
)
from domain.models import LigneFacture


class TestWeightedAveragePrice:
    """Tests for weighted_average_price."""

    def test_simple_average(self):
        # All same quantity, so weighted avg = simple avg
        items = [(10.0, 1.0), (20.0, 1.0)]
        assert weighted_average_price(items) == 15.0

    def test_weighted(self):
        # (10 * 3 + 20 * 1) / (3 + 1) = 50 / 4 = 12.5
        items = [(10.0, 3.0), (20.0, 1.0)]
        assert weighted_average_price(items) == 12.5

    def test_empty_list(self):
        assert weighted_average_price([]) == 0.0

    def test_zero_total_quantity(self):
        items = [(10.0, 0.0), (20.0, 0.0)]
        assert weighted_average_price(items) == 0.0

    def test_single_item(self):
        items = [(42.0, 5.0)]
        assert weighted_average_price(items) == 42.0


class TestRankSuppliersByAmount:
    """Tests for rank_suppliers_by_amount."""

    def test_basic_ranking(self):
        lines = [
            (LigneFacture(ligne_numero=1, prix_total=500.0), "Fournisseur A"),
            (LigneFacture(ligne_numero=2, prix_total=300.0), "Fournisseur B"),
            (LigneFacture(ligne_numero=3, prix_total=800.0), "Fournisseur C"),
        ]
        result = rank_suppliers_by_amount(lines)
        assert len(result) == 3
        assert result[0].nom == "Fournisseur C"
        assert result[0].montant_total == 800.0
        assert result[1].nom == "Fournisseur A"
        assert result[2].nom == "Fournisseur B"

    def test_limit(self):
        lines = [
            (LigneFacture(ligne_numero=1, prix_total=100.0), f"F{i}") for i in range(10)
        ]
        result = rank_suppliers_by_amount(lines, limit=3)
        assert len(result) == 3

    def test_empty_list(self):
        result = rank_suppliers_by_amount([])
        assert result == []

    def test_aggregation_same_supplier(self):
        lines = [
            (LigneFacture(ligne_numero=1, prix_total=200.0), "Acme"),
            (LigneFacture(ligne_numero=2, prix_total=300.0), "Acme"),
            (LigneFacture(ligne_numero=3, prix_total=100.0), "Beta"),
        ]
        result = rank_suppliers_by_amount(lines)
        assert result[0].nom == "Acme"
        assert result[0].montant_total == 500.0
        assert result[0].nombre_documents == 2

    def test_none_prix_total_treated_as_zero(self):
        lines = [
            (LigneFacture(ligne_numero=1, prix_total=None), "Acme"),
            (LigneFacture(ligne_numero=2, prix_total=100.0), "Beta"),
        ]
        result = rank_suppliers_by_amount(lines)
        assert result[0].nom == "Beta"
        assert result[0].montant_total == 100.0


class TestFragmentationIndex:
    """Tests for fragmentation_index."""

    def test_basic_fragmentation(self):
        lines = [
            (LigneFacture(ligne_numero=1, type_matiere="Gravier"), "Acme"),
            (LigneFacture(ligne_numero=2, type_matiere="Gravier"), "Beta"),
            (LigneFacture(ligne_numero=3, type_matiere="Sable"), "Acme"),
        ]
        result = fragmentation_index(lines)
        assert result["Gravier"] == 2
        assert result["Sable"] == 1

    def test_none_material(self):
        lines = [
            (LigneFacture(ligne_numero=1, type_matiere=None), "Acme"),
            (LigneFacture(ligne_numero=2, type_matiere=None), "Beta"),
        ]
        result = fragmentation_index(lines)
        assert result["inconnu"] == 2

    def test_single_supplier_per_material(self):
        lines = [
            (LigneFacture(ligne_numero=1, type_matiere="Beton"), "Acme"),
            (LigneFacture(ligne_numero=2, type_matiere="Beton"), "Acme"),
        ]
        result = fragmentation_index(lines)
        assert result["Beton"] == 1

    def test_empty_list(self):
        result = fragmentation_index([])
        assert result == {}
