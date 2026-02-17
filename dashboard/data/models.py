# dashboard/data/models.py — backwards compatibility facade
# ORM models moved to dashboard/adapters/outbound/sqlalchemy_models.py
from dashboard.adapters.outbound.sqlalchemy_models import (  # noqa: F401
    Base,
    Fournisseur,
    Document,
    LigneFacture,
    Anomalie,
    EntityMapping,
    MergeAuditLog,
    CorrectionLog,
    BoundingBox,
    UploadLog,
)
