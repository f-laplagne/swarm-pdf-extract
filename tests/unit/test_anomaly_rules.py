"""Tests for domain.anomaly_rules — calculation, date, and confidence rules."""

from datetime import date

import pytest

from domain.anomaly_rules import (
    check_calculation_coherence,
    check_date_order,
    check_low_confidence,
)
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


class TestCheckDateOrder:
    """Tests for check_date_order anomaly rule."""

    def test_valid_order(self):
        ligne = LigneFacture(
            ligne_numero=1,
            date_depart=date(2024, 1, 1),
            date_arrivee=date(2024, 1, 5),
        )
        result = check_date_order(ligne)
        assert result.est_valide is True
        assert result.code_regle == "DATE_001"
        assert "coherentes" in result.description.lower()

    def test_same_day(self):
        ligne = LigneFacture(
            ligne_numero=1,
            date_depart=date(2024, 3, 15),
            date_arrivee=date(2024, 3, 15),
        )
        result = check_date_order(ligne)
        assert result.est_valide is True

    def test_invalid_order(self):
        ligne = LigneFacture(
            ligne_numero=1,
            date_depart=date(2024, 6, 10),
            date_arrivee=date(2024, 6, 5),
        )
        result = check_date_order(ligne)
        assert result.est_valide is False
        assert result.code_regle == "DATE_001"
        assert "anterieure" in result.description.lower()
        assert "depart" in result.details
        assert "arrivee" in result.details

    def test_missing_date_depart(self):
        ligne = LigneFacture(
            ligne_numero=1,
            date_depart=None,
            date_arrivee=date(2024, 1, 5),
        )
        result = check_date_order(ligne)
        assert result.est_valide is True
        assert "manquantes" in result.description.lower()

    def test_missing_date_arrivee(self):
        ligne = LigneFacture(
            ligne_numero=1,
            date_depart=date(2024, 1, 1),
            date_arrivee=None,
        )
        result = check_date_order(ligne)
        assert result.est_valide is True
        assert "manquantes" in result.description.lower()

    def test_both_dates_missing(self):
        ligne = LigneFacture(ligne_numero=1)
        result = check_date_order(ligne)
        assert result.est_valide is True
        assert "manquantes" in result.description.lower()


class TestCheckLowConfidence:
    """Tests for check_low_confidence anomaly rule."""

    def test_above_threshold(self):
        result = check_low_confidence(0.85)
        assert result.est_valide is True
        assert result.code_regle == "CONF_001"
        assert "suffisante" in result.description.lower()

    def test_below_threshold(self):
        result = check_low_confidence(0.45)
        assert result.est_valide is False
        assert result.code_regle == "CONF_001"
        assert "confiance" in result.description.lower()
        assert result.details["confiance"] == 0.45
        assert result.details["seuil"] == 0.6

    def test_at_threshold(self):
        result = check_low_confidence(0.6)
        assert result.est_valide is True

    def test_custom_threshold(self):
        result = check_low_confidence(0.75, seuil=0.8)
        assert result.est_valide is False

        result_pass = check_low_confidence(0.85, seuil=0.8)
        assert result_pass.est_valide is True

    def test_zero_confidence(self):
        result = check_low_confidence(0.0)
        assert result.est_valide is False

    def test_perfect_confidence(self):
        result = check_low_confidence(1.0)
        assert result.est_valide is True
