"""Domain models — pure Python, zero external dependencies.

Only stdlib imports allowed: dataclasses, datetime, enum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class TypeDocument(Enum):
    """Type of commercial document."""

    FACTURE = "facture"
    BON_LIVRAISON = "bon_livraison"
    DEVIS = "devis"
    BON_COMMANDE = "bon_commande"
    AVOIR = "avoir"
    RELEVE = "releve"
    AUTRE = "autre"


class StatutMapping(Enum):
    """Status of an entity-resolution mapping."""

    APPROVED = "approved"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class NiveauSeverite(Enum):
    """Severity level for anomalies."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ── Value Objects ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScoreConfiance:
    """Per-field confidence scores for an invoice line extraction."""

    type_matiere: float = 0.0
    unite: float = 0.0
    prix_unitaire: float = 0.0
    quantite: float = 0.0
    prix_total: float = 0.0
    date_depart: float = 0.0
    date_arrivee: float = 0.0
    lieu_depart: float = 0.0
    lieu_arrivee: float = 0.0


# ── Entities ────────────────────────────────────────────────────────────


@dataclass
class LigneFacture:
    """A single line item on an invoice."""

    ligne_numero: int
    type_matiere: str | None = None
    unite: str | None = None
    prix_unitaire: float | None = None
    quantite: float | None = None
    prix_total: float | None = None
    date_depart: date | None = None
    date_arrivee: date | None = None
    lieu_depart: str | None = None
    lieu_arrivee: str | None = None
    confiance: ScoreConfiance = field(default_factory=ScoreConfiance)
    id: int | None = None


@dataclass
class Fournisseur:
    """A supplier / vendor."""

    nom: str
    adresse: str | None = None
    id: int | None = None


@dataclass
class Document:
    """A scanned or digital document (invoice, delivery note, quote, etc.)."""

    fichier: str
    type_document: TypeDocument
    confiance_globale: float = 0.0
    montant_ht: float | None = None
    montant_tva: float | None = None
    montant_ttc: float | None = None
    date_document: date | None = None
    fournisseur: Fournisseur | None = None
    lignes: list[LigneFacture] = field(default_factory=list)
    id: int | None = None


@dataclass
class Anomalie:
    """An anomaly detected during document validation."""

    code_regle: str
    description: str
    severite: NiveauSeverite
    document_id: int
    ligne_id: int | None = None
    details: dict = field(default_factory=dict)
    id: int | None = None


@dataclass
class EntityMapping:
    """Maps a raw entity value to its canonical (resolved) form."""

    entity_type: str
    raw_value: str
    canonical_value: str
    statut: StatutMapping = StatutMapping.PENDING_REVIEW
    confidence: float = 0.0
    source: str = "manual"
    id: int | None = None


@dataclass
class MergeAuditEntry:
    """Audit trail for entity merge / split operations."""

    entity_type: str
    canonical_value: str
    merged_values: list[str]
    action: str
    timestamp: datetime | None = None
    id: int | None = None


class CorrectionStatut(Enum):
    """Status of a manual correction."""

    APPLIQUEE = "appliquee"
    REJETEE = "rejetee"


@dataclass
class Correction:
    """A human correction applied to an extracted field."""

    ligne_id: int
    champ: str
    valeur_originale: str | None
    valeur_corrigee: str
    confiance_originale: float | None
    corrige_par: str
    statut: CorrectionStatut = CorrectionStatut.APPLIQUEE
    notes: str | None = None
    timestamp: datetime | None = None
    id: int | None = None


# ── Result Value Objects ────────────────────────────────────────────────


@dataclass(frozen=True)
class ClassementFournisseur:
    """Read-only ranking of a supplier by total spend."""

    nom: str
    montant_total: float
    nombre_documents: int


@dataclass(frozen=True)
class ResultatAnomalie:
    """Read-only result of an anomaly rule check."""

    est_valide: bool
    code_regle: str
    description: str
    details: dict = field(default_factory=dict)
