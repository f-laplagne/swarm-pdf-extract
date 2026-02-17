"""Tests for domain port interfaces (ABC contracts).

Every port must be an ABC that cannot be instantiated directly.
"""

from __future__ import annotations

import pytest
from abc import ABC

from domain.ports import (
    # Repository ports
    DocumentRepository,
    SupplierRepository,
    LineItemRepository,
    AnomalyRepository,
    MappingRepository,
    AuditRepository,
    # Infrastructure ports
    CachePort,
    GeocodingPort,
    PDFTextExtractorPort,
    OCRProcessorPort,
    TableExtractorPort,
    FileSystemPort,
    # Service ports
    IngestionService,
    AnomalyDetectionService,
    EntityResolutionService,
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


# ── Infrastructure ports are ABCs ─────────────────────────────────────────


class TestCachePort:
    def test_is_abstract(self):
        assert issubclass(CachePort, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            CachePort()


class TestGeocodingPort:
    def test_is_abstract(self):
        assert issubclass(GeocodingPort, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            GeocodingPort()


class TestPDFTextExtractorPort:
    def test_is_abstract(self):
        assert issubclass(PDFTextExtractorPort, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            PDFTextExtractorPort()


class TestOCRProcessorPort:
    def test_is_abstract(self):
        assert issubclass(OCRProcessorPort, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            OCRProcessorPort()


class TestTableExtractorPort:
    def test_is_abstract(self):
        assert issubclass(TableExtractorPort, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            TableExtractorPort()


class TestFileSystemPort:
    def test_is_abstract(self):
        assert issubclass(FileSystemPort, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            FileSystemPort()


# ── Service ports are ABCs ────────────────────────────────────────────────


class TestIngestionService:
    def test_is_abstract(self):
        assert issubclass(IngestionService, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            IngestionService()


class TestAnomalyDetectionService:
    def test_is_abstract(self):
        assert issubclass(AnomalyDetectionService, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            AnomalyDetectionService()


class TestEntityResolutionService:
    def test_is_abstract(self):
        assert issubclass(EntityResolutionService, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            EntityResolutionService()
