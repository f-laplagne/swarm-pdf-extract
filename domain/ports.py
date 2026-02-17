"""Domain ports — abstract interfaces for repositories, services, and infrastructure.

Only stdlib (abc) and domain.models imports allowed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import (
    Anomalie,
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
