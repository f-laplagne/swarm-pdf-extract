"""Tests for domain.anomaly_rules — check_calculation_coherence."""

import pytest

from domain.anomaly_rules import check_calculation_coherence
from domain.models import LigneFacture


class TestCheckCalculationCoherence:
    """Tests for check_calculation_coherence anomaly rule."""

    def test_coherent_calculation(self):
        ligne = LigneFacture(
            ligne_numero=1, prix_unitaire=10.0, quantite=5.0, prix_total=50.0
        )
        result = check_calculation_coherence(ligne)
        assert result.est_valide is True
        assert result.code_regle == "CALC_001"
        assert "coherent" in result.description.lower()

    def test_incoherent_calculation(self):
        ligne = LigneFacture(
            ligne_numero=1, prix_unitaire=10.0, quantite=5.0, prix_total=100.0
        )
        result = check_calculation_coherence(ligne)
        assert result.est_valide is False
        assert result.code_regle == "CALC_001"
        assert "ecart" in result.description.lower()
        assert "attendu" in result.details
        assert result.details["attendu"] == 50.0
        assert result.details["reel"] == 100.0

    def test_within_tolerance(self):
        # prix_unitaire * quantite = 50.0, prix_total = 50.4
        # ecart = 0.4/50.4 ~= 0.0079 which is < 0.01 tolerance
        ligne = LigneFacture(
            ligne_numero=1, prix_unitaire=10.0, quantite=5.0, prix_total=50.4
        )
        result = check_calculation_coherence(ligne)
        assert result.est_valide is True

    def test_missing_prix_unitaire(self):
        ligne = LigneFacture(
            ligne_numero=1, prix_unitaire=None, quantite=5.0, prix_total=50.0
        )
        result = check_calculation_coherence(ligne)
        assert result.est_valide is True
        assert "manquants" in result.description.lower()

    def test_missing_quantite(self):
        ligne = LigneFacture(
            ligne_numero=1, prix_unitaire=10.0, quantite=None, prix_total=50.0
        )
        result = check_calculation_coherence(ligne)
        assert result.est_valide is True
        assert "manquants" in result.description.lower()

    def test_missing_prix_total(self):
        ligne = LigneFacture(
            ligne_numero=1, prix_unitaire=10.0, quantite=5.0, prix_total=None
        )
        result = check_calculation_coherence(ligne)
        assert result.est_valide is True
        assert "manquants" in result.description.lower()

    def test_custom_tolerance(self):
        # ecart = |50 - 55| / 55 = 0.0909 -> > 0.05 tolerance
        ligne = LigneFacture(
            ligne_numero=1, prix_unitaire=10.0, quantite=5.0, prix_total=55.0
        )
        result_strict = check_calculation_coherence(ligne, tolerance=0.05)
        assert result_strict.est_valide is False

        # Same data but with tolerance=0.10, should pass
        result_lenient = check_calculation_coherence(ligne, tolerance=0.10)
        assert result_lenient.est_valide is True

    def test_exact_at_tolerance_boundary(self):
        # prix_unitaire * quantite = 100.0, prix_total = 101.0
        # ecart = 1/101 ~= 0.0099 which is < 0.01
        ligne = LigneFacture(
            ligne_numero=1, prix_unitaire=10.0, quantite=10.0, prix_total=101.0
        )
        result = check_calculation_coherence(ligne)
        assert result.est_valide is True
