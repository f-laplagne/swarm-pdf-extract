"""Domain models — pure Python, zero external dependencies.

Only stdlib imports allowed: dataclasses, datetime, enum.
"""

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
