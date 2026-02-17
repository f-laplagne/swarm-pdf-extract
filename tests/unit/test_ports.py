"""Tests for domain port interfaces (ABC contracts).

Every port must be an ABC that cannot be instantiated directly.
"""

from __future__ import annotations

import pytest
from abc import ABC

from domain.ports import (
    DocumentRepository,
    SupplierRepository,
    LineItemRepository,
    AnomalyRepository,
    MappingRepository,
    AuditRepository,
)


# ── Repository ports are ABCs ────────────────────────────────────────────


class TestDocumentRepository:
    def test_is_abstract(self):
        assert issubclass(DocumentRepository, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            DocumentRepository()


class TestSupplierRepository:
    def test_is_abstract(self):
        assert issubclass(SupplierRepository, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            SupplierRepository()


class TestLineItemRepository:
    def test_is_abstract(self):
        assert issubclass(LineItemRepository, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            LineItemRepository()


class TestAnomalyRepository:
    def test_is_abstract(self):
        assert issubclass(AnomalyRepository, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            AnomalyRepository()


class TestMappingRepository:
    def test_is_abstract(self):
        assert issubclass(MappingRepository, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            MappingRepository()


class TestAuditRepository:
    def test_is_abstract(self):
        assert issubclass(AuditRepository, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            AuditRepository()
