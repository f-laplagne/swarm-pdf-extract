"""Tests for domain.normalization — supplier and material normalization."""

import pytest

from domain.normalization import normalize_material, normalize_supplier


class TestNormalizeSupplier:
    """Tests for normalize_supplier."""

    def test_strip_sa(self):
        assert normalize_supplier("Acme SA") == "ACME"

    def test_strip_sarl(self):
        assert normalize_supplier("Dupont SARL") == "DUPONT"

    def test_strip_gmbh(self):
        assert normalize_supplier("Müller GmbH") == "MÜLLER"

    def test_strip_sas_with_dot(self):
        assert normalize_supplier("Transport SAS.") == "TRANSPORT"

    def test_no_suffix_unchanged(self):
        assert normalize_supplier("Acme Corporation") == "ACME CORPORATION"

    def test_extra_spaces(self):
        assert normalize_supplier("  Acme   Corp   SA  ") == "ACME CORP"

    def test_uppercase(self):
        assert normalize_supplier("acme corp") == "ACME CORP"

    def test_strip_ltd(self):
        assert normalize_supplier("British Ltd") == "BRITISH"

    def test_strip_llc(self):
        assert normalize_supplier("American LLC") == "AMERICAN"

    def test_strip_inc(self):
        assert normalize_supplier("Tech Inc") == "TECH"

    def test_strip_sasu(self):
        assert normalize_supplier("Startup SASU") == "STARTUP"

    def test_strip_eurl(self):
        assert normalize_supplier("Solo EURL") == "SOLO"

    def test_multiple_suffixes(self):
        # Only one occurrence per word boundary, but both should be stripped
        assert normalize_supplier("Acme SA SARL") == "ACME"


class TestNormalizeMaterial:
    """Tests for normalize_material."""

    def test_strip_leading_qty_kg(self):
        assert normalize_material("50kg Gravier") == "GRAVIER"

    def test_strip_leading_qty_t(self):
        assert normalize_material("2.5t Sable") == "SABLE"

    def test_strip_after_dash(self):
        assert normalize_material("Gravier 0/20 - Livraison Paris") == "GRAVIER 0/20"

    def test_combined_qty_and_dash(self):
        assert normalize_material("100 kg Beton - Transport inclus") == "BETON"

    def test_no_transform(self):
        assert normalize_material("Gravier fin") == "GRAVIER FIN"

    def test_uppercase(self):
        assert normalize_material("sable blanc") == "SABLE BLANC"

    def test_extra_spaces(self):
        assert normalize_material("  Gravier   0/20  ") == "GRAVIER 0/20"

    def test_strip_leading_qty_liters(self):
        assert normalize_material("10l Bitume") == "BITUME"

    def test_strip_leading_qty_meters(self):
        assert normalize_material("25m Tube PVC") == "TUBE PVC"

    def test_no_leading_qty_no_dash(self):
        assert normalize_material("Beton arme") == "BETON ARME"
