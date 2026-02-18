"""Domain ports — abstract interfaces for repositories, services, and infrastructure.

Only stdlib (abc) and domain.models imports allowed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import (
    Anomalie,
    Correction,
    Document,
    EntityMapping,
    Fournisseur,
    LigneFacture,
    MergeAuditEntry,
)


# ── Repository Ports ──────────────────────────────────────────────────────


class DocumentRepository(ABC):
    """Persistence port for documents."""

    @abstractmethod
    def save(self, document: Document) -> Document: ...

    @abstractmethod
    def find_by_filename(self, filename: str) -> Document | None: ...

    @abstractmethod
    def list_all(self) -> list[Document]: ...


class SupplierRepository(ABC):
    """Persistence port for suppliers."""

    @abstractmethod
    def find_or_create(self, name: str, address: str | None = None) -> Fournisseur: ...

    @abstractmethod
    def list_all(self) -> list[Fournisseur]: ...


class LineItemRepository(ABC):
    """Persistence port for invoice line items."""

    @abstractmethod
    def list_by_document(self, document_id: int) -> list[LigneFacture]: ...

    @abstractmethod
    def list_with_supplier(self) -> list[tuple[LigneFacture, str]]: ...


class AnomalyRepository(ABC):
    """Persistence port for anomalies."""

    @abstractmethod
    def save(self, anomaly: Anomalie) -> Anomalie: ...

    @abstractmethod
    def delete_by_document(self, document_id: int) -> int: ...

    @abstractmethod
    def list_all(self) -> list[Anomalie]: ...

    @abstractmethod
    def count_by_severity(self) -> dict[str, int]: ...


class MappingRepository(ABC):
    """Persistence port for entity-resolution mappings."""

    @abstractmethod
    def get_mappings(self, entity_type: str) -> dict[str, str]: ...

    @abstractmethod
    def get_prefix_mappings(self, entity_type: str) -> dict[str, str]: ...

    @abstractmethod
    def get_reverse_mappings(self, entity_type: str) -> dict[str, list[str]]: ...

    @abstractmethod
    def save_mapping(self, mapping: EntityMapping) -> EntityMapping: ...

    @abstractmethod
    def get_pending_reviews(self, entity_type: str) -> list[EntityMapping]: ...


class AuditRepository(ABC):
    """Persistence port for merge audit trail."""

    @abstractmethod
    def record(self, entry: MergeAuditEntry) -> MergeAuditEntry: ...

    @abstractmethod
    def list_by_type(self, entity_type: str) -> list[MergeAuditEntry]: ...


class CorrectionPort(ABC):
    """Persistence port for field-level corrections."""

    @abstractmethod
    def sauvegarder(self, correction: Correction) -> Correction: ...

    @abstractmethod
    def historique(self, champ: str, valeur_originale: str) -> list[Correction]: ...


# ── Infrastructure Ports ──────────────────────────────────────────────────


class CachePort(ABC):
    """Port for key-value caching (Redis, in-memory, etc.)."""

    @abstractmethod
    def get(self, key: str) -> object | None: ...

    @abstractmethod
    def set(self, key: str, value: object, ttl: int = 3600) -> None: ...

    @abstractmethod
    def invalidate(self, prefix: str) -> None: ...


class GeocodingPort(ABC):
    """Port for geocoding addresses and computing distances."""

    @abstractmethod
    def geocode(self, address: str) -> tuple[float, float] | None: ...

    @abstractmethod
    def distance_km(self, coord1: tuple, coord2: tuple) -> float: ...


class PDFTextExtractorPort(ABC):
    """Port for extracting text from PDF files."""

    @abstractmethod
    def extract_text(self, pdf_path: str) -> dict: ...


class OCRProcessorPort(ABC):
    """Port for OCR-based text extraction from scanned PDFs."""

    @abstractmethod
    def extract_text_ocr(self, pdf_path: str, lang: str = "fra+eng") -> dict: ...


class TableExtractorPort(ABC):
    """Port for extracting tables from PDF files."""

    @abstractmethod
    def extract_tables(self, pdf_path: str) -> dict: ...


class FileSystemPort(ABC):
    """Port for file system operations (read, write, list, upload)."""

    @abstractmethod
    def read_json(self, path: str) -> dict: ...

    @abstractmethod
    def write_json(self, path: str, data: dict) -> None: ...

    @abstractmethod
    def list_files(self, directory: str, pattern: str) -> list[str]: ...

    @abstractmethod
    def save_upload(self, content: bytes, filename: str) -> tuple[str, str]: ...


# ── Service Ports ─────────────────────────────────────────────────────────


class IngestionService(ABC):
    """Port for ingesting extraction JSON data into the domain."""

    @abstractmethod
    def ingest_extraction(self, data: dict) -> Document | None: ...

    @abstractmethod
    def ingest_directory(self, directory: str) -> dict: ...


class AnomalyDetectionService(ABC):
    """Port for detecting anomalies across documents."""

    @abstractmethod
    def detect(self, rules: list[dict]) -> list[Anomalie]: ...


class EntityResolutionService(ABC):
    """Port for entity resolution (merge, revert, auto-resolve)."""

    @abstractmethod
    def merge(self, entity_type: str, canonical: str,
              raw_values: list[str], source: str) -> MergeAuditEntry: ...

    @abstractmethod
    def revert_merge(self, audit_id: int) -> None: ...

    @abstractmethod
    def run_auto_resolution(self, config: dict) -> dict: ...
