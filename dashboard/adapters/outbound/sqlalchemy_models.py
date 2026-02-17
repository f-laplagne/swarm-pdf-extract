from datetime import date, datetime, timezone
from sqlalchemy import (
    Boolean, Column, Integer, String, Float, Date, DateTime, Text, ForeignKey, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Fournisseur(Base):
    __tablename__ = "fournisseurs"

    id = Column(Integer, primary_key=True)
    nom = Column(String, nullable=False)
    adresse = Column(Text)
    siret = Column(String)
    tva_intra = Column(String)

    documents = relationship("Document", back_populates="fournisseur")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    fichier = Column(String, nullable=False, unique=True)
    type_document = Column(String)
    format_pdf = Column(String)
    fournisseur_id = Column(Integer, ForeignKey("fournisseurs.id"))
    client_nom = Column(String)
    client_adresse = Column(Text)
    date_document = Column(Date)
    numero_document = Column(String)
    montant_ht = Column(Float)
    montant_tva = Column(Float)
    montant_ttc = Column(Float)
    devise = Column(String, default="EUR")
    conditions_paiement = Column(Text)
    ref_commande = Column(String)
    ref_contrat = Column(String)
    ref_bon_livraison = Column(String)
    confiance_globale = Column(Float)
    strategie_utilisee = Column(String)
    complexite = Column(Integer)
    date_ingestion = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    fournisseur = relationship("Fournisseur", back_populates="documents")
    lignes = relationship("LigneFacture", back_populates="document", cascade="all, delete-orphan")
    anomalies = relationship("Anomalie", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_documents_fournisseur", "fournisseur_id"),
        Index("idx_documents_date", "date_document"),
    )


class LigneFacture(Base):
    __tablename__ = "lignes_facture"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    ligne_numero = Column(Integer)
    type_matiere = Column(Text)
    unite = Column(String)
    prix_unitaire = Column(Float)
    quantite = Column(Float)
    prix_total = Column(Float)
    date_depart = Column(String)  # ISO 8601 string, nullable
    date_arrivee = Column(String)
    lieu_depart = Column(Text)
    lieu_arrivee = Column(Text)
    conf_type_matiere = Column(Float)
    conf_unite = Column(Float)
    conf_prix_unitaire = Column(Float)
    conf_quantite = Column(Float)
    conf_prix_total = Column(Float)
    conf_date_depart = Column(Float)
    conf_date_arrivee = Column(Float)
    conf_lieu_depart = Column(Float)
    conf_lieu_arrivee = Column(Float)
    supprime = Column(Boolean, default=False)

    document = relationship("Document", back_populates="lignes")

    __table_args__ = (
        Index("idx_lignes_document", "document_id"),
        Index("idx_lignes_matiere", "type_matiere"),
        Index("idx_lignes_dates", "date_depart", "date_arrivee"),
        Index("idx_lignes_lieux", "lieu_depart", "lieu_arrivee"),
    )


class Anomalie(Base):
    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    ligne_id = Column(Integer, ForeignKey("lignes_facture.id"), nullable=True)
    regle_id = Column(String)
    type_anomalie = Column(String)
    severite = Column(String)
    description = Column(Text)
    valeur_attendue = Column(String)
    valeur_trouvee = Column(String)
    date_detection = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="anomalies")
    ligne = relationship("LigneFacture")

    __table_args__ = (
        Index("idx_anomalies_document", "document_id"),
        Index("idx_anomalies_type", "type_anomalie"),
    )


class EntityMapping(Base):
    __tablename__ = "entity_mappings"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String, nullable=False)  # "location", "material", "supplier", "company"
    raw_value = Column(Text, nullable=False)
    canonical_value = Column(Text, nullable=False)
    match_mode = Column(String, default="exact")  # "exact" or "prefix"
    source = Column(String, default="manual")  # "manual" or "auto"
    confidence = Column(Float, default=1.0)
    status = Column(String, default="approved")  # "approved", "pending_review", "rejected"
    created_by = Column(String, default="admin")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    notes = Column(Text)

    __table_args__ = (
        Index("idx_entity_mappings_type_raw", "entity_type", "raw_value", unique=True),
        Index("idx_entity_mappings_status", "status"),
    )


class MergeAuditLog(Base):
    __tablename__ = "merge_audit_log"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String, nullable=False)
    action = Column(String, nullable=False)  # "merge", "split", "update", "revert"
    canonical_value = Column(Text, nullable=False)
    raw_values_json = Column(Text, nullable=False)  # JSON array
    performed_by = Column(String, default="admin")
    performed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    notes = Column(Text)
    reverted = Column(Boolean, default=False)
    reverted_at = Column(DateTime)


class CorrectionLog(Base):
    __tablename__ = "correction_log"

    id = Column(Integer, primary_key=True)
    ligne_id = Column(Integer, ForeignKey("lignes_facture.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    champ = Column(String, nullable=False)
    ancienne_valeur = Column(Text)
    nouvelle_valeur = Column(Text)
    ancienne_confiance = Column(Float)
    corrige_par = Column(String, default="admin")
    corrige_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    notes = Column(Text)

    ligne = relationship("LigneFacture")
    document = relationship("Document")

    __table_args__ = (
        Index("idx_correction_log_ligne", "ligne_id"),
        Index("idx_correction_log_document", "document_id"),
    )


class BoundingBox(Base):
    __tablename__ = "bounding_boxes"

    id = Column(Integer, primary_key=True)
    ligne_id = Column(Integer, ForeignKey("lignes_facture.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    champ = Column(String, nullable=False)
    page_number = Column(Integer, nullable=False)
    x_min = Column(Float, nullable=False)
    y_min = Column(Float, nullable=False)
    x_max = Column(Float, nullable=False)
    y_max = Column(Float, nullable=False)
    source = Column(String, default="manual")  # "manual" or "extraction"
    cree_par = Column(String, default="admin")
    cree_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    correction_log_id = Column(Integer, ForeignKey("correction_log.id"), nullable=True)

    ligne = relationship("LigneFacture")
    document = relationship("Document")
    correction_log = relationship("CorrectionLog")

    __table_args__ = (
        Index("idx_bbox_document_page", "document_id", "page_number"),
        Index("idx_bbox_ligne_champ", "ligne_id", "champ"),
    )


class UploadLog(Base):
    __tablename__ = "upload_log"

    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    content_hash = Column(String, unique=True)  # SHA-256
    file_size = Column(Integer)
    uploaded_by = Column(String, default="admin")
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(String, default="uploaded")  # "uploaded", "processing", "completed", "failed"
    error_message = Column(Text)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)

    __table_args__ = (
        Index("idx_upload_log_hash", "content_hash"),
        Index("idx_upload_log_status", "status"),
    )
