"""Tests for domain.entity_resolution — resolve_value and expand_canonical."""

import math

import pytest

from domain.entity_resolution import expand_canonical, resolve_value


class TestResolveValue:
    """Tests for resolve_value with exact and prefix matching."""

    def test_exact_match(self):
        mappings = {"Acme Corp": "ACME CORPORATION"}
        assert resolve_value("Acme Corp", mappings) == "ACME CORPORATION"

    def test_no_match_returns_original(self):
        mappings = {"Acme Corp": "ACME CORPORATION"}
        assert resolve_value("Unknown Ltd", mappings) == "Unknown Ltd"

    def test_none_returns_none(self):
        mappings = {"Acme Corp": "ACME CORPORATION"}
        assert resolve_value(None, mappings) is None

    def test_nan_returns_nan(self):
        mappings = {"Acme Corp": "ACME CORPORATION"}
        result = resolve_value(float("nan"), mappings)
        assert isinstance(result, float)
        assert math.isnan(result)

    def test_prefix_match(self):
        mappings = {}
        prefix_mappings = {"Acme": "ACME CORPORATION"}
        assert resolve_value("Acme Ltd", mappings, prefix_mappings) == "ACME CORPORATION"

    def test_longest_prefix_wins(self):
        mappings = {}
        prefix_mappings = {
            "Acme": "ACME GENERIC",
            "Acme Co": "ACME COMPANY",
        }
        assert resolve_value("Acme Corp", mappings, prefix_mappings) == "ACME COMPANY"

    def test_exact_match_takes_priority_over_prefix(self):
        mappings = {"Acme Corp": "EXACT MATCH"}
        prefix_mappings = {"Acme": "PREFIX MATCH"}
        assert resolve_value("Acme Corp", mappings, prefix_mappings) == "EXACT MATCH"

    def test_numeric_value_converted_to_string(self):
        mappings = {"42": "QUARANTE-DEUX"}
        assert resolve_value(42, mappings) == "QUARANTE-DEUX"

    def test_empty_mappings(self):
        assert resolve_value("something", {}) == "something"

    def test_prefix_no_match(self):
        mappings = {}
        prefix_mappings = {"Xyz": "XYZ CORP"}
        assert resolve_value("Acme Ltd", mappings, prefix_mappings) == "Acme Ltd"


class TestExpandCanonical:
    """Tests for expand_canonical reverse entity lookup."""

    def test_with_aliases(self):
        reverse = {"ACME CORPORATION": ["Acme Corp", "Acme Ltd"]}
        result = expand_canonical("ACME CORPORATION", reverse)
        assert result == ["ACME CORPORATION", "Acme Corp", "Acme Ltd"]

    def test_no_aliases(self):
        reverse = {}
        result = expand_canonical("ACME CORPORATION", reverse)
        assert result == ["ACME CORPORATION"]

    def test_sorted_output(self):
        reverse = {"BETA": ["Zeta", "Alpha", "Gamma"]}
        result = expand_canonical("BETA", reverse)
        assert result == ["Alpha", "BETA", "Gamma", "Zeta"]

    def test_canonical_included_even_if_in_aliases(self):
        reverse = {"ACME": ["ACME", "Acme Corp"]}
        result = expand_canonical("ACME", reverse)
        # set deduplicates, sorted output
        assert result == ["ACME", "Acme Corp"]

    def test_empty_alias_list(self):
        reverse = {"ACME": []}
        result = expand_canonical("ACME", reverse)
        assert result == ["ACME"]
