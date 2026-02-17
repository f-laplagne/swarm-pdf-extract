"""SQLAlchemy implementations of domain repository ports.

Each adapter translates between ORM models (sqlalchemy_models) and
pure domain models (domain.models), keeping the domain layer free
of any infrastructure dependency.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import (
    Document as OrmDocument,
    EntityMapping as OrmEntityMapping,
    Fournisseur as OrmFournisseur,
    LigneFacture as OrmLigneFacture,
)
from domain.models import (
    Document as DomainDocument,
    EntityMapping as DomainEntityMapping,
    Fournisseur as DomainFournisseur,
    LigneFacture as DomainLigneFacture,
    ScoreConfiance,
    StatutMapping,
    TypeDocument,
)
from domain.ports import DocumentRepository, LineItemRepository, MappingRepository


class SqlAlchemyMappingRepository(MappingRepository):
    """SQLAlchemy adapter for the MappingRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Queries ────────────────────────────────────────────────────────

    def get_mappings(self, entity_type: str) -> dict[str, str]:
        """Return {raw_value: canonical_value} for approved exact mappings."""
        stmt = (
            select(OrmEntityMapping.raw_value, OrmEntityMapping.canonical_value)
            .where(OrmEntityMapping.entity_type == entity_type)
            .where(OrmEntityMapping.status == "approved")
            .where(OrmEntityMapping.match_mode == "exact")
        )
        return {
            row.raw_value: row.canonical_value
            for row in self._session.execute(stmt)
        }

    def get_prefix_mappings(self, entity_type: str) -> dict[str, str]:
        """Return {raw_value: canonical_value} for approved prefix mappings."""
        stmt = (
            select(OrmEntityMapping.raw_value, OrmEntityMapping.canonical_value)
            .where(OrmEntityMapping.entity_type == entity_type)
            .where(OrmEntityMapping.status == "approved")
            .where(OrmEntityMapping.match_mode == "prefix")
        )
        return {
            row.raw_value: row.canonical_value
            for row in self._session.execute(stmt)
        }

    def get_reverse_mappings(self, entity_type: str) -> dict[str, list[str]]:
        """Return {canonical_value: [raw_value, ...]} for approved mappings."""
        stmt = (
            select(OrmEntityMapping.raw_value, OrmEntityMapping.canonical_value)
            .where(OrmEntityMapping.entity_type == entity_type)
            .where(OrmEntityMapping.status == "approved")
        )
        result: dict[str, list[str]] = {}
        for row in self._session.execute(stmt):
            result.setdefault(row.canonical_value, []).append(row.raw_value)
        return result

    def get_pending_reviews(self, entity_type: str) -> list[DomainEntityMapping]:
        """Return domain EntityMapping objects for pending_review status, ordered by confidence desc."""
        stmt = (
            select(OrmEntityMapping)
            .where(OrmEntityMapping.entity_type == entity_type)
            .where(OrmEntityMapping.status == "pending_review")
            .order_by(OrmEntityMapping.confidence.desc())
        )
        return [self._to_domain(orm) for orm in self._session.scalars(stmt)]

    # ── Commands ───────────────────────────────────────────────────────

    def save_mapping(self, mapping: DomainEntityMapping) -> DomainEntityMapping:
        """Persist a domain EntityMapping and return it with its assigned id."""
        orm_obj = OrmEntityMapping(
            entity_type=mapping.entity_type,
            raw_value=mapping.raw_value,
            canonical_value=mapping.canonical_value,
            source=mapping.source,
            confidence=mapping.confidence,
            status=mapping.statut.value,
        )
        if mapping.id is not None:
            orm_obj.id = mapping.id
        self._session.add(orm_obj)
        self._session.flush()
        mapping.id = orm_obj.id
        return mapping

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _to_domain(orm: OrmEntityMapping) -> DomainEntityMapping:
        """Convert an ORM EntityMapping row to a domain EntityMapping."""
        valid_statuts = {s.value for s in StatutMapping}
        statut = (
            StatutMapping(orm.status)
            if orm.status in valid_statuts
            else StatutMapping.PENDING_REVIEW
        )
        return DomainEntityMapping(
            entity_type=orm.entity_type,
            raw_value=orm.raw_value,
            canonical_value=orm.canonical_value,
            statut=statut,
            confidence=orm.confidence or 0.0,
            source=orm.source or "manual",
            id=orm.id,
        )


class SqlAlchemyDocumentRepository(DocumentRepository):
    """SQLAlchemy adapter for the DocumentRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Commands ───────────────────────────────────────────────────────

    def save(self, document: DomainDocument) -> DomainDocument:
        """Persist a domain Document (and its fournisseur if present)."""
        orm_fournisseur_id = None
        if document.fournisseur:
            existing = self._session.execute(
                select(OrmFournisseur).where(
                    OrmFournisseur.nom == document.fournisseur.nom
                )
            ).scalar_one_or_none()
            if existing:
                orm_fournisseur_id = existing.id
            else:
                f = OrmFournisseur(
                    nom=document.fournisseur.nom,
                    adresse=document.fournisseur.adresse,
                )
                self._session.add(f)
                self._session.flush()
                orm_fournisseur_id = f.id

        orm_doc = OrmDocument(
            fichier=document.fichier,
            type_document=document.type_document.value,
            confiance_globale=document.confiance_globale,
            montant_ht=document.montant_ht,
            montant_tva=document.montant_tva,
            montant_ttc=document.montant_ttc,
            date_document=document.date_document,
            fournisseur_id=orm_fournisseur_id,
        )
        self._session.add(orm_doc)
        self._session.flush()
        document.id = orm_doc.id
        if document.fournisseur:
            document.fournisseur.id = orm_fournisseur_id
        return document

    # ── Queries ────────────────────────────────────────────────────────

    def find_by_filename(self, filename: str) -> DomainDocument | None:
        """Return a domain Document matching the filename, or None."""
        orm = self._session.execute(
            select(OrmDocument).where(OrmDocument.fichier == filename)
        ).scalar_one_or_none()
        if orm is None:
            return None
        return self._to_domain(orm)

    def list_all(self) -> list[DomainDocument]:
        """Return all documents as domain objects."""
        return [
            self._to_domain(orm)
            for orm in self._session.scalars(select(OrmDocument))
        ]

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _to_domain(orm: OrmDocument) -> DomainDocument:
        """Convert an ORM Document row to a domain Document."""
        fournisseur = None
        if orm.fournisseur:
            fournisseur = DomainFournisseur(
                nom=orm.fournisseur.nom,
                adresse=orm.fournisseur.adresse,
                id=orm.fournisseur.id,
            )
        return DomainDocument(
            fichier=orm.fichier,
            type_document=(
                TypeDocument(orm.type_document)
                if orm.type_document
                else TypeDocument.AUTRE
            ),
            confiance_globale=orm.confiance_globale or 0.0,
            montant_ht=orm.montant_ht,
            montant_tva=orm.montant_tva,
            montant_ttc=orm.montant_ttc,
            date_document=orm.date_document,
            fournisseur=fournisseur,
            id=orm.id,
        )


class SqlAlchemyLineItemRepository(LineItemRepository):
    """SQLAlchemy adapter for the LineItemRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Queries ────────────────────────────────────────────────────────

    def list_by_document(self, document_id: int) -> list[DomainLigneFacture]:
        """Return all non-deleted lines for a document, ordered by ligne_numero."""
        stmt = (
            select(OrmLigneFacture)
            .where(OrmLigneFacture.document_id == document_id)
            .where(OrmLigneFacture.supprime == False)  # noqa: E712
            .order_by(OrmLigneFacture.ligne_numero)
        )
        return [self._to_domain(orm) for orm in self._session.scalars(stmt)]

    def list_with_supplier(self) -> list[tuple[DomainLigneFacture, str]]:
        """Return all non-deleted lines joined with their supplier name.

        Joins lignes -> documents -> fournisseurs.  When a document has no
        fournisseur the supplier name defaults to ``"Inconnu"``.
        """
        stmt = (
            select(OrmLigneFacture, OrmFournisseur.nom)
            .join(OrmDocument, OrmLigneFacture.document_id == OrmDocument.id)
            .outerjoin(OrmFournisseur, OrmDocument.fournisseur_id == OrmFournisseur.id)
            .where(OrmLigneFacture.supprime == False)  # noqa: E712
        )
        result: list[tuple[DomainLigneFacture, str]] = []
        for row in self._session.execute(stmt):
            ligne_orm, fournisseur_nom = row
            result.append((self._to_domain(ligne_orm), fournisseur_nom or "Inconnu"))
        return result

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _to_domain(orm: OrmLigneFacture) -> DomainLigneFacture:
        """Convert an ORM LigneFacture row to a domain LigneFacture."""
        # Parse ISO date strings to date objects if present
        date_depart = None
        if orm.date_depart:
            try:
                date_depart = date.fromisoformat(orm.date_depart)
            except (ValueError, TypeError):
                pass

        date_arrivee = None
        if orm.date_arrivee:
            try:
                date_arrivee = date.fromisoformat(orm.date_arrivee)
            except (ValueError, TypeError):
                pass

        confiance = ScoreConfiance(
            type_matiere=orm.conf_type_matiere or 0.0,
            unite=orm.conf_unite or 0.0,
            prix_unitaire=orm.conf_prix_unitaire or 0.0,
            quantite=orm.conf_quantite or 0.0,
            prix_total=orm.conf_prix_total or 0.0,
            date_depart=orm.conf_date_depart or 0.0,
            date_arrivee=orm.conf_date_arrivee or 0.0,
            lieu_depart=orm.conf_lieu_depart or 0.0,
            lieu_arrivee=orm.conf_lieu_arrivee or 0.0,
        )
        return DomainLigneFacture(
            ligne_numero=orm.ligne_numero or 0,
            type_matiere=orm.type_matiere,
            unite=orm.unite,
            prix_unitaire=orm.prix_unitaire,
            quantite=orm.quantite,
            prix_total=orm.prix_total,
            date_depart=date_depart,
            date_arrivee=date_arrivee,
            lieu_depart=orm.lieu_depart,
            lieu_arrivee=orm.lieu_arrivee,
            confiance=confiance,
            id=orm.id,
        )
