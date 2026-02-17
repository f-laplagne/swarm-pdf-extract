"""Tests for domain models — pure Python, no external dependencies."""

from datetime import date, datetime
from enum import Enum

import pytest


# ── Task 2: Enum tests ─────────────────────────────────────────────────


class TestTypeDocument:
    def test_is_enum(self):
        from domain.models import TypeDocument
        assert issubclass(TypeDocument, Enum)

    def test_values(self):
        from domain.models import TypeDocument
        expected = {
            "facture",
            "bon_livraison",
            "devis",
            "bon_commande",
            "avoir",
            "releve",
            "autre",
        }
        assert {m.value for m in TypeDocument} == expected

    def test_lookup_by_value(self):
        from domain.models import TypeDocument
        assert TypeDocument("facture") is TypeDocument.FACTURE

    def test_lookup_by_name(self):
        from domain.models import TypeDocument
        assert TypeDocument["BON_LIVRAISON"] is TypeDocument.BON_LIVRAISON


class TestStatutMapping:
    def test_is_enum(self):
        from domain.models import StatutMapping
        assert issubclass(StatutMapping, Enum)

    def test_values(self):
        from domain.models import StatutMapping
        expected = {"approved", "pending_review", "rejected"}
        assert {m.value for m in StatutMapping} == expected

    def test_lookup_by_value(self):
        from domain.models import StatutMapping
        assert StatutMapping("approved") is StatutMapping.APPROVED

    def test_lookup_by_name(self):
        from domain.models import StatutMapping
        assert StatutMapping["PENDING_REVIEW"] is StatutMapping.PENDING_REVIEW


class TestNiveauSeverite:
    def test_is_enum(self):
        from domain.models import NiveauSeverite
        assert issubclass(NiveauSeverite, Enum)

    def test_values(self):
        from domain.models import NiveauSeverite
        expected = {"info", "warning", "error"}
        assert {m.value for m in NiveauSeverite} == expected

    def test_lookup_by_value(self):
        from domain.models import NiveauSeverite
        assert NiveauSeverite("warning") is NiveauSeverite.WARNING

    def test_lookup_by_name(self):
        from domain.models import NiveauSeverite
        assert NiveauSeverite["ERROR"] is NiveauSeverite.ERROR


# ── Task 3: ScoreConfiance value object tests ──────────────────────────


class TestScoreConfiance:
    def test_defaults_are_zero(self):
        from domain.models import ScoreConfiance
        sc = ScoreConfiance()
        for field_name in (
            "type_matiere", "unite", "prix_unitaire", "quantite",
            "prix_total", "date_depart", "date_arrivee",
            "lieu_depart", "lieu_arrivee",
        ):
            assert getattr(sc, field_name) == 0.0

    def test_custom_values(self):
        from domain.models import ScoreConfiance
        sc = ScoreConfiance(
            type_matiere=0.95,
            unite=0.80,
            prix_unitaire=0.70,
            quantite=0.60,
            prix_total=0.50,
            date_depart=0.40,
            date_arrivee=0.30,
            lieu_depart=0.20,
            lieu_arrivee=0.10,
        )
        assert sc.type_matiere == 0.95
        assert sc.unite == 0.80
        assert sc.prix_unitaire == 0.70
        assert sc.quantite == 0.60
        assert sc.prix_total == 0.50
        assert sc.date_depart == 0.40
        assert sc.date_arrivee == 0.30
        assert sc.lieu_depart == 0.20
        assert sc.lieu_arrivee == 0.10

    def test_frozen_cannot_mutate(self):
        from domain.models import ScoreConfiance
        sc = ScoreConfiance(type_matiere=0.9)
        with pytest.raises(AttributeError):
            sc.type_matiere = 0.5  # type: ignore[misc]

    def test_equality(self):
        from domain.models import ScoreConfiance
        a = ScoreConfiance(type_matiere=0.9, unite=0.8)
        b = ScoreConfiance(type_matiere=0.9, unite=0.8)
        assert a == b


# ── Task 4: LigneFacture, Fournisseur, Document entity tests ──────────


class TestLigneFacture:
    def test_minimal_creation(self):
        from domain.models import LigneFacture
        ligne = LigneFacture(ligne_numero=1)
        assert ligne.ligne_numero == 1
        assert ligne.type_matiere is None
        assert ligne.unite is None
        assert ligne.prix_unitaire is None
        assert ligne.quantite is None
        assert ligne.prix_total is None
        assert ligne.date_depart is None
        assert ligne.date_arrivee is None
        assert ligne.lieu_depart is None
        assert ligne.lieu_arrivee is None
        assert ligne.id is None

    def test_default_confiance(self):
        from domain.models import LigneFacture, ScoreConfiance
        ligne = LigneFacture(ligne_numero=1)
        assert ligne.confiance == ScoreConfiance()

    def test_complete_creation(self):
        from domain.models import LigneFacture, ScoreConfiance
        ligne = LigneFacture(
            ligne_numero=3,
            type_matiere="sable",
            unite="tonne",
            prix_unitaire=12.50,
            quantite=100.0,
            prix_total=1250.0,
            date_depart=date(2024, 1, 15),
            date_arrivee=date(2024, 1, 16),
            lieu_depart="Paris",
            lieu_arrivee="Lyon",
            confiance=ScoreConfiance(type_matiere=0.95),
            id=42,
        )
        assert ligne.ligne_numero == 3
        assert ligne.type_matiere == "sable"
        assert ligne.unite == "tonne"
        assert ligne.prix_unitaire == 12.50
        assert ligne.quantite == 100.0
        assert ligne.prix_total == 1250.0
        assert ligne.date_depart == date(2024, 1, 15)
        assert ligne.date_arrivee == date(2024, 1, 16)
        assert ligne.lieu_depart == "Paris"
        assert ligne.lieu_arrivee == "Lyon"
        assert ligne.confiance.type_matiere == 0.95
        assert ligne.id == 42

    def test_mutable(self):
        from domain.models import LigneFacture
        ligne = LigneFacture(ligne_numero=1)
        ligne.type_matiere = "gravier"
        assert ligne.type_matiere == "gravier"


class TestFournisseur:
    def test_minimal_creation(self):
        from domain.models import Fournisseur
        f = Fournisseur(nom="Acme SAS")
        assert f.nom == "Acme SAS"
        assert f.adresse is None
        assert f.id is None

    def test_complete_creation(self):
        from domain.models import Fournisseur
        f = Fournisseur(nom="Acme SAS", adresse="10 rue de Paris", id=7)
        assert f.nom == "Acme SAS"
        assert f.adresse == "10 rue de Paris"
        assert f.id == 7


class TestDocument:
    def test_minimal_creation(self):
        from domain.models import Document, TypeDocument
        doc = Document(fichier="facture.pdf", type_document=TypeDocument.FACTURE)
        assert doc.fichier == "facture.pdf"
        assert doc.type_document is TypeDocument.FACTURE
        assert doc.confiance_globale == 0.0
        assert doc.montant_ht is None
        assert doc.montant_tva is None
        assert doc.montant_ttc is None
        assert doc.date_document is None
        assert doc.fournisseur is None
        assert doc.lignes == []
        assert doc.id is None

    def test_complete_creation(self):
        from domain.models import Document, Fournisseur, TypeDocument
        fournisseur = Fournisseur(nom="Acme SAS")
        doc = Document(
            fichier="facture.pdf",
            type_document=TypeDocument.FACTURE,
            confiance_globale=0.85,
            montant_ht=1000.0,
            montant_tva=200.0,
            montant_ttc=1200.0,
            date_document=date(2024, 3, 15),
            fournisseur=fournisseur,
            id=1,
        )
        assert doc.confiance_globale == 0.85
        assert doc.montant_ht == 1000.0
        assert doc.montant_tva == 200.0
        assert doc.montant_ttc == 1200.0
        assert doc.date_document == date(2024, 3, 15)
        assert doc.fournisseur is fournisseur
        assert doc.id == 1

    def test_document_with_lignes(self):
        from domain.models import Document, LigneFacture, TypeDocument
        ligne1 = LigneFacture(ligne_numero=1, type_matiere="sable")
        ligne2 = LigneFacture(ligne_numero=2, type_matiere="gravier")
        doc = Document(
            fichier="facture.pdf",
            type_document=TypeDocument.FACTURE,
            lignes=[ligne1, ligne2],
        )
        assert len(doc.lignes) == 2
        assert doc.lignes[0].type_matiere == "sable"
        assert doc.lignes[1].type_matiere == "gravier"

    def test_lignes_default_independent(self):
        """Each Document should get its own lignes list (no shared mutable default)."""
        from domain.models import Document, LigneFacture, TypeDocument
        doc1 = Document(fichier="a.pdf", type_document=TypeDocument.FACTURE)
        doc2 = Document(fichier="b.pdf", type_document=TypeDocument.FACTURE)
        doc1.lignes.append(LigneFacture(ligne_numero=1))
        assert len(doc2.lignes) == 0


# ── Task 5: Anomalie, EntityMapping, MergeAuditEntry, result VOs ───────


class TestAnomalie:
    def test_minimal_creation(self):
        from domain.models import Anomalie, NiveauSeverite
        a = Anomalie(
            code_regle="PRIX_NEGATIF",
            description="Prix negatif detecte",
            severite=NiveauSeverite.ERROR,
            document_id=1,
        )
        assert a.code_regle == "PRIX_NEGATIF"
        assert a.description == "Prix negatif detecte"
        assert a.severite is NiveauSeverite.ERROR
        assert a.document_id == 1
        assert a.ligne_id is None
        assert a.details == {}
        assert a.id is None

    def test_complete_creation(self):
        from domain.models import Anomalie, NiveauSeverite
        a = Anomalie(
            code_regle="ECART_TOTAL",
            description="Ecart total/lignes",
            severite=NiveauSeverite.WARNING,
            document_id=5,
            ligne_id=3,
            details={"ecart": 12.50, "seuil": 10.0},
            id=99,
        )
        assert a.ligne_id == 3
        assert a.details["ecart"] == 12.50
        assert a.id == 99

    def test_details_default_independent(self):
        from domain.models import Anomalie, NiveauSeverite
        a1 = Anomalie(
            code_regle="R1", description="d", severite=NiveauSeverite.INFO,
            document_id=1,
        )
        a2 = Anomalie(
            code_regle="R2", description="d", severite=NiveauSeverite.INFO,
            document_id=2,
        )
        a1.details["key"] = "val"
        assert "key" not in a2.details


class TestEntityMapping:
    def test_minimal_creation(self):
        from domain.models import EntityMapping, StatutMapping
        em = EntityMapping(
            entity_type="fournisseur",
            raw_value="ACME sas",
            canonical_value="Acme SAS",
        )
        assert em.entity_type == "fournisseur"
        assert em.raw_value == "ACME sas"
        assert em.canonical_value == "Acme SAS"
        assert em.statut is StatutMapping.PENDING_REVIEW
        assert em.confidence == 0.0
        assert em.source == "manual"
        assert em.id is None

    def test_complete_creation(self):
        from domain.models import EntityMapping, StatutMapping
        em = EntityMapping(
            entity_type="fournisseur",
            raw_value="ACME sas",
            canonical_value="Acme SAS",
            statut=StatutMapping.APPROVED,
            confidence=0.95,
            source="auto_fuzzy",
            id=42,
        )
        assert em.statut is StatutMapping.APPROVED
        assert em.confidence == 0.95
        assert em.source == "auto_fuzzy"
        assert em.id == 42


class TestMergeAuditEntry:
    def test_minimal_creation(self):
        from domain.models import MergeAuditEntry
        entry = MergeAuditEntry(
            entity_type="fournisseur",
            canonical_value="Acme SAS",
            merged_values=["ACME sas", "acme"],
            action="merge",
        )
        assert entry.entity_type == "fournisseur"
        assert entry.canonical_value == "Acme SAS"
        assert entry.merged_values == ["ACME sas", "acme"]
        assert entry.action == "merge"
        assert entry.timestamp is None
        assert entry.id is None

    def test_complete_creation(self):
        from domain.models import MergeAuditEntry
        ts = datetime(2024, 6, 15, 10, 30, 0)
        entry = MergeAuditEntry(
            entity_type="matiere",
            canonical_value="Sable 0/4",
            merged_values=["sable 0-4", "SABLE 0/4"],
            action="split",
            timestamp=ts,
            id=7,
        )
        assert entry.timestamp == ts
        assert entry.id == 7

    def test_merged_values_default_independent(self):
        from domain.models import MergeAuditEntry
        e1 = MergeAuditEntry(
            entity_type="f", canonical_value="A",
            merged_values=["x"], action="merge",
        )
        e2 = MergeAuditEntry(
            entity_type="f", canonical_value="B",
            merged_values=["y"], action="merge",
        )
        e1.merged_values.append("z")
        assert "z" not in e2.merged_values


class TestClassementFournisseur:
    def test_creation(self):
        from domain.models import ClassementFournisseur
        cf = ClassementFournisseur(
            nom="Acme SAS",
            montant_total=50000.0,
            nombre_documents=12,
        )
        assert cf.nom == "Acme SAS"
        assert cf.montant_total == 50000.0
        assert cf.nombre_documents == 12

    def test_frozen_cannot_mutate(self):
        from domain.models import ClassementFournisseur
        cf = ClassementFournisseur(
            nom="Acme SAS", montant_total=50000.0, nombre_documents=12,
        )
        with pytest.raises(AttributeError):
            cf.nom = "Other"  # type: ignore[misc]

    def test_equality(self):
        from domain.models import ClassementFournisseur
        a = ClassementFournisseur(nom="A", montant_total=100.0, nombre_documents=1)
        b = ClassementFournisseur(nom="A", montant_total=100.0, nombre_documents=1)
        assert a == b


class TestResultatAnomalie:
    def test_creation(self):
        from domain.models import ResultatAnomalie
        ra = ResultatAnomalie(
            est_valide=False,
            code_regle="PRIX_NEGATIF",
            description="Prix negatif",
        )
        assert ra.est_valide is False
        assert ra.code_regle == "PRIX_NEGATIF"
        assert ra.description == "Prix negatif"
        assert ra.details == {}

    def test_creation_with_details(self):
        from domain.models import ResultatAnomalie
        ra = ResultatAnomalie(
            est_valide=True,
            code_regle="OK",
            description="Valide",
            details={"info": "all good"},
        )
        assert ra.details == {"info": "all good"}

    def test_frozen_cannot_mutate(self):
        from domain.models import ResultatAnomalie
        ra = ResultatAnomalie(
            est_valide=True, code_regle="OK", description="ok",
        )
        with pytest.raises(AttributeError):
            ra.est_valide = False  # type: ignore[misc]
