"""Domain models — pure Python, zero external dependencies.

Only stdlib imports allowed: dataclasses, datetime, enum.
"""

from dataclasses import dataclass
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
