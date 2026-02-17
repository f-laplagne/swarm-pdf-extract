# Hexagonal Architecture + TDD Migration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure swarm-pdf-extract into hexagonal architecture (Ports & Adapters) with TDD, without breaking the existing codebase.

**Architecture:** Centralized `domain/` package at project root, shared by dashboard and tools. Domain contains pure business logic (models, ports, services). Adapters implement ports using infrastructure (SQLAlchemy, Redis, pdfplumber). Migration is progressive — existing files become thin facades before cleanup.

**Tech Stack:** Python 3.11+, dataclasses, ABC, pytest. No new dependencies.

**Design doc:** `docs/plans/2026-02-17-hexagonal-tdd-migration-design.md`

**Branch:** `refactor/hexagonal-tdd`

**Existing tests baseline:** Run `pytest tests/ && PYTHONPATH=. pytest dashboard/tests/` before starting — all must pass. These tests must remain green throughout the migration.

---

## Phase 1: Domain Layer — Models & Enums

### Task 1: Scaffold domain package

**Files:**
- Create: `domain/__init__.py`
- Create: `domain/analytics/__init__.py`
- Create: `domain/extraction/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `dashboard/tests/unit/__init__.py`

**Step 1: Create directory structure**

```bash
mkdir -p domain/analytics domain/extraction tests/unit dashboard/tests/unit
touch domain/__init__.py domain/analytics/__init__.py domain/extraction/__init__.py
touch tests/unit/__init__.py dashboard/tests/unit/__init__.py
```

**Step 2: Verify existing tests still pass**

Run: `pytest tests/ -x -q && PYTHONPATH=. pytest dashboard/tests/ -x -q`
Expected: All existing tests PASS (no regression)

**Step 3: Commit**

```bash
git add domain/ tests/unit/ dashboard/tests/unit/
git commit -m "chore: scaffold domain package structure"
```

---

### Task 2: Domain models — Enums

**Files:**
- Create: `domain/models.py`
- Create: `tests/unit/test_models.py`

**Step 1: Write failing test for enums**

```python
# tests/unit/test_models.py
from domain.models import TypeDocument, StatutMapping, NiveauSeverite


def test_type_document_valeurs():
    assert TypeDocument.FACTURE.value == "facture"
    assert TypeDocument.BON_LIVRAISON.value == "bon_livraison"
    assert TypeDocument.DEVIS.value == "devis"
    assert TypeDocument.BON_COMMANDE.value == "bon_commande"
    assert TypeDocument.AVOIR.value == "avoir"
    assert TypeDocument.RELEVE.value == "releve"
    assert TypeDocument.AUTRE.value == "autre"


def test_statut_mapping_valeurs():
    assert StatutMapping.APPROVED.value == "approved"
    assert StatutMapping.PENDING_REVIEW.value == "pending_review"
    assert StatutMapping.REJECTED.value == "rejected"


def test_niveau_severite_valeurs():
    assert NiveauSeverite.INFO.value == "info"
    assert NiveauSeverite.WARNING.value == "warning"
    assert NiveauSeverite.ERROR.value == "error"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py -x -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain.models'`

**Step 3: Write minimal implementation**

```python
# domain/models.py
from enum import Enum


class TypeDocument(Enum):
    FACTURE = "facture"
    BON_LIVRAISON = "bon_livraison"
    DEVIS = "devis"
    BON_COMMANDE = "bon_commande"
    AVOIR = "avoir"
    RELEVE = "releve"
    AUTRE = "autre"


class StatutMapping(Enum):
    APPROVED = "approved"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class NiveauSeverite(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_models.py -x -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add domain/models.py tests/unit/test_models.py
git commit -m "feat(domain): add TypeDocument, StatutMapping, NiveauSeverite enums"
```

---

### Task 3: Domain models — ScoreConfiance value object

**Files:**
- Modify: `domain/models.py`
- Modify: `tests/unit/test_models.py`

**Step 1: Write failing test**

```python
# tests/unit/test_models.py — append
from domain.models import ScoreConfiance


def test_score_confiance_defaults():
    score = ScoreConfiance()
    assert score.type_matiere == 0.0
    assert score.unite == 0.0
    assert score.prix_unitaire == 0.0
    assert score.quantite == 0.0
    assert score.prix_total == 0.0
    assert score.date_depart == 0.0
    assert score.date_arrivee == 0.0
    assert score.lieu_depart == 0.0
    assert score.lieu_arrivee == 0.0


def test_score_confiance_custom_values():
    score = ScoreConfiance(type_matiere=0.9, prix_unitaire=0.75)
    assert score.type_matiere == 0.9
    assert score.prix_unitaire == 0.75
    assert score.unite == 0.0  # default


def test_score_confiance_is_frozen():
    score = ScoreConfiance()
    try:
        score.type_matiere = 0.5
        assert False, "Should raise FrozenInstanceError"
    except AttributeError:
        pass
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py::test_score_confiance_defaults -x -v`
Expected: FAIL — `ImportError: cannot import name 'ScoreConfiance'`

**Step 3: Write minimal implementation**

Append to `domain/models.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScoreConfiance:
    type_matiere: float = 0.0
    unite: float = 0.0
    prix_unitaire: float = 0.0
    quantite: float = 0.0
    prix_total: float = 0.0
    date_depart: float = 0.0
    date_arrivee: float = 0.0
    lieu_depart: float = 0.0
    lieu_arrivee: float = 0.0
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_models.py -x -v`
Expected: 6 PASSED

**Step 5: Commit**

```bash
git add domain/models.py tests/unit/test_models.py
git commit -m "feat(domain): add ScoreConfiance frozen value object"
```

---

### Task 4: Domain models — LigneFacture, Fournisseur, Document entities

**Files:**
- Modify: `domain/models.py`
- Modify: `tests/unit/test_models.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_models.py — append
from datetime import date
from domain.models import LigneFacture, Fournisseur, Document


def test_ligne_facture_minimal():
    ligne = LigneFacture(ligne_numero=1)
    assert ligne.ligne_numero == 1
    assert ligne.type_matiere is None
    assert ligne.prix_unitaire is None
    assert ligne.confiance == ScoreConfiance()
    assert ligne.id is None


def test_ligne_facture_complete():
    ligne = LigneFacture(
        ligne_numero=1,
        type_matiere="Gravier 0/20",
        unite="t",
        prix_unitaire=12.50,
        quantite=25.0,
        prix_total=312.50,
        date_depart=date(2025, 1, 15),
        date_arrivee=date(2025, 1, 16),
        lieu_depart="Paris",
        lieu_arrivee="Lyon",
        confiance=ScoreConfiance(type_matiere=0.95, prix_unitaire=0.88),
    )
    assert ligne.prix_total == 312.50
    assert ligne.confiance.type_matiere == 0.95


def test_fournisseur_minimal():
    f = Fournisseur(nom="ACME SA")
    assert f.nom == "ACME SA"
    assert f.adresse is None
    assert f.id is None


def test_document_avec_lignes():
    f = Fournisseur(nom="ACME SA", id=1)
    doc = Document(
        fichier="facture_001.pdf",
        type_document=TypeDocument.FACTURE,
        confiance_globale=0.85,
        montant_ht=1000.0,
        fournisseur=f,
    )
    doc.lignes.append(LigneFacture(ligne_numero=1, type_matiere="Sable"))
    assert doc.fichier == "facture_001.pdf"
    assert doc.type_document == TypeDocument.FACTURE
    assert len(doc.lignes) == 1
    assert doc.lignes[0].type_matiere == "Sable"


def test_document_defaults():
    doc = Document(fichier="test.pdf", type_document=TypeDocument.AUTRE)
    assert doc.confiance_globale == 0.0
    assert doc.montant_ht is None
    assert doc.fournisseur is None
    assert doc.lignes == []
    assert doc.id is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py::test_ligne_facture_minimal -x -v`
Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

Append to `domain/models.py`:

```python
from datetime import date, datetime


@dataclass
class LigneFacture:
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
    nom: str
    adresse: str | None = None
    id: int | None = None


@dataclass
class Document:
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_models.py -x -v`
Expected: 11 PASSED

**Step 5: Commit**

```bash
git add domain/models.py tests/unit/test_models.py
git commit -m "feat(domain): add LigneFacture, Fournisseur, Document entities"
```

---

### Task 5: Domain models — Anomalie, EntityMapping, MergeAuditEntry, result value objects

**Files:**
- Modify: `domain/models.py`
- Modify: `tests/unit/test_models.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_models.py — append
from datetime import datetime
from domain.models import (
    Anomalie, EntityMapping, MergeAuditEntry,
    ClassementFournisseur, ResultatAnomalie,
)


def test_anomalie_creation():
    a = Anomalie(
        code_regle="CALC_001",
        description="Ecart de calcul",
        severite=NiveauSeverite.WARNING,
        document_id=1,
        ligne_id=5,
        details={"ecart": 0.15},
    )
    assert a.code_regle == "CALC_001"
    assert a.severite == NiveauSeverite.WARNING
    assert a.details["ecart"] == 0.15


def test_entity_mapping_defaults():
    m = EntityMapping(
        entity_type="supplier",
        raw_value="ACME SA",
        canonical_value="ACME",
    )
    assert m.statut == StatutMapping.PENDING_REVIEW
    assert m.confidence == 0.0
    assert m.source == "manual"


def test_merge_audit_entry():
    entry = MergeAuditEntry(
        entity_type="supplier",
        canonical_value="ACME",
        merged_values=["ACME SA", "ACME SARL"],
        action="merge",
    )
    assert len(entry.merged_values) == 2
    assert entry.timestamp is None


def test_classement_fournisseur_frozen():
    c = ClassementFournisseur(nom="ACME", montant_total=5000.0, nombre_documents=3)
    assert c.montant_total == 5000.0
    try:
        c.montant_total = 999.0
        assert False, "Should be frozen"
    except AttributeError:
        pass


def test_resultat_anomalie_valide():
    r = ResultatAnomalie(est_valide=True, code_regle="CALC_001", description="OK")
    assert r.est_valide is True
    assert r.details == {}


def test_resultat_anomalie_invalide():
    r = ResultatAnomalie(
        est_valide=False, code_regle="CALC_001",
        description="Ecart", details={"ecart": 0.15},
    )
    assert r.est_valide is False
    assert r.details["ecart"] == 0.15
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py::test_anomalie_creation -x -v`
Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

Append to `domain/models.py`:

```python
@dataclass
class Anomalie:
    code_regle: str
    description: str
    severite: NiveauSeverite
    document_id: int
    ligne_id: int | None = None
    details: dict = field(default_factory=dict)
    id: int | None = None


@dataclass
class EntityMapping:
    entity_type: str
    raw_value: str
    canonical_value: str
    statut: StatutMapping = StatutMapping.PENDING_REVIEW
    confidence: float = 0.0
    source: str = "manual"
    id: int | None = None


@dataclass
class MergeAuditEntry:
    entity_type: str
    canonical_value: str
    merged_values: list[str]
    action: str
    timestamp: datetime | None = None
    id: int | None = None


@dataclass(frozen=True)
class ClassementFournisseur:
    nom: str
    montant_total: float
    nombre_documents: int


@dataclass(frozen=True)
class ResultatAnomalie:
    est_valide: bool
    code_regle: str
    description: str
    details: dict = field(default_factory=dict)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_models.py -x -v`
Expected: 17 PASSED

**Step 5: Verify no regression**

Run: `pytest tests/ -x -q && PYTHONPATH=. pytest dashboard/tests/ -x -q`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add domain/models.py tests/unit/test_models.py
git commit -m "feat(domain): add Anomalie, EntityMapping, MergeAuditEntry, result VOs"
```

---

## Phase 1b: Domain Layer — Ports

### Task 6: Ports — Repository interfaces

**Files:**
- Create: `domain/ports.py`
- Create: `tests/unit/test_ports.py`

**Step 1: Write failing test**

```python
# tests/unit/test_ports.py
from abc import ABC
from domain.ports import (
    DocumentRepository, SupplierRepository, LineItemRepository,
    AnomalyRepository, MappingRepository, AuditRepository,
)


def test_document_repository_is_abstract():
    assert issubclass(DocumentRepository, ABC)
    # Cannot instantiate directly
    try:
        DocumentRepository()
        assert False, "Should not instantiate ABC"
    except TypeError:
        pass


def test_all_repositories_are_abstract():
    for repo_class in [
        DocumentRepository, SupplierRepository, LineItemRepository,
        AnomalyRepository, MappingRepository, AuditRepository,
    ]:
        assert issubclass(repo_class, ABC)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ports.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# domain/ports.py
from abc import ABC, abstractmethod
from domain.models import (
    Document, LigneFacture, Fournisseur, Anomalie,
    EntityMapping, MergeAuditEntry,
)


# ============================================================
# OUTBOUND PORTS — Repositories
# ============================================================

class DocumentRepository(ABC):
    @abstractmethod
    def save(self, document: Document) -> Document: ...
    @abstractmethod
    def find_by_filename(self, filename: str) -> Document | None: ...
    @abstractmethod
    def list_all(self) -> list[Document]: ...


class SupplierRepository(ABC):
    @abstractmethod
    def find_or_create(self, name: str, address: str | None = None) -> Fournisseur: ...
    @abstractmethod
    def list_all(self) -> list[Fournisseur]: ...


class LineItemRepository(ABC):
    @abstractmethod
    def list_by_document(self, document_id: int) -> list[LigneFacture]: ...
    @abstractmethod
    def list_with_supplier(self) -> list[tuple[LigneFacture, str]]: ...


class AnomalyRepository(ABC):
    @abstractmethod
    def save(self, anomaly: Anomalie) -> Anomalie: ...
    @abstractmethod
    def delete_by_document(self, document_id: int) -> int: ...
    @abstractmethod
    def list_all(self) -> list[Anomalie]: ...
    @abstractmethod
    def count_by_severity(self) -> dict[str, int]: ...


class MappingRepository(ABC):
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
    @abstractmethod
    def record(self, entry: MergeAuditEntry) -> MergeAuditEntry: ...
    @abstractmethod
    def list_by_type(self, entity_type: str) -> list[MergeAuditEntry]: ...
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_ports.py -x -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add domain/ports.py tests/unit/test_ports.py
git commit -m "feat(domain): add repository port interfaces"
```

---

### Task 7: Ports — Service & infrastructure interfaces

**Files:**
- Modify: `domain/ports.py`
- Modify: `tests/unit/test_ports.py`

**Step 1: Write failing test**

```python
# tests/unit/test_ports.py — append
from domain.ports import (
    CachePort, GeocodingPort,
    PDFTextExtractorPort, OCRProcessorPort, TableExtractorPort,
    FileSystemPort,
    IngestionService, AnomalyDetectionService, EntityResolutionService,
)


def test_all_service_ports_are_abstract():
    for port_class in [
        CachePort, GeocodingPort,
        PDFTextExtractorPort, OCRProcessorPort, TableExtractorPort,
        FileSystemPort,
        IngestionService, AnomalyDetectionService, EntityResolutionService,
    ]:
        assert issubclass(port_class, ABC)
        try:
            port_class()
            assert False, f"{port_class.__name__} should not be instantiable"
        except TypeError:
            pass
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ports.py::test_all_service_ports_are_abstract -x -v`
Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

Append to `domain/ports.py`:

```python
# ============================================================
# OUTBOUND PORTS — External services
# ============================================================

class CachePort(ABC):
    @abstractmethod
    def get(self, key: str) -> object | None: ...
    @abstractmethod
    def set(self, key: str, value: object, ttl: int = 3600) -> None: ...
    @abstractmethod
    def invalidate(self, prefix: str) -> None: ...


class GeocodingPort(ABC):
    @abstractmethod
    def geocode(self, address: str) -> tuple[float, float] | None: ...
    @abstractmethod
    def distance_km(self, coord1: tuple, coord2: tuple) -> float: ...


class PDFTextExtractorPort(ABC):
    @abstractmethod
    def extract_text(self, pdf_path: str) -> dict: ...


class OCRProcessorPort(ABC):
    @abstractmethod
    def extract_text_ocr(self, pdf_path: str, lang: str = "fra+eng") -> dict: ...


class TableExtractorPort(ABC):
    @abstractmethod
    def extract_tables(self, pdf_path: str) -> dict: ...


class FileSystemPort(ABC):
    @abstractmethod
    def read_json(self, path: str) -> dict: ...
    @abstractmethod
    def write_json(self, path: str, data: dict) -> None: ...
    @abstractmethod
    def list_files(self, directory: str, pattern: str) -> list[str]: ...
    @abstractmethod
    def save_upload(self, content: bytes, filename: str) -> tuple[str, str]: ...


# ============================================================
# INBOUND PORTS — Use cases
# ============================================================

class IngestionService(ABC):
    @abstractmethod
    def ingest_extraction(self, data: dict) -> Document | None: ...
    @abstractmethod
    def ingest_directory(self, directory: str) -> dict: ...


class AnomalyDetectionService(ABC):
    @abstractmethod
    def detect(self, rules: list[dict]) -> list[Anomalie]: ...


class EntityResolutionService(ABC):
    @abstractmethod
    def merge(self, entity_type: str, canonical: str,
              raw_values: list[str], source: str) -> MergeAuditEntry: ...
    @abstractmethod
    def revert_merge(self, audit_id: int) -> None: ...
    @abstractmethod
    def run_auto_resolution(self, config: dict) -> dict: ...
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_ports.py -x -v`
Expected: 3 PASSED

**Step 5: Verify no regression**

Run: `pytest tests/ -x -q && PYTHONPATH=. pytest dashboard/tests/ -x -q`
Expected: All PASS

**Step 6: Commit**

```bash
git add domain/ports.py tests/unit/test_ports.py
git commit -m "feat(domain): add service and infrastructure port interfaces"
```

---

## Phase 1c: Domain Layer — Business Logic Services

### Task 8: Entity resolution — resolve_value

**Files:**
- Create: `domain/entity_resolution.py`
- Create: `tests/unit/test_entity_resolution_domain.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_entity_resolution_domain.py
import math
from domain.entity_resolution import resolve_value


def test_resolve_value_exact_match():
    mappings = {"ACME SA": "ACME", "Foo Ltd": "Foo"}
    assert resolve_value("ACME SA", mappings) == "ACME"


def test_resolve_value_no_match():
    mappings = {"ACME SA": "ACME"}
    assert resolve_value("Unknown", mappings) == "Unknown"


def test_resolve_value_none():
    assert resolve_value(None, {}) is None


def test_resolve_value_nan():
    assert resolve_value(float("nan"), {}) is not None or True  # NaN passthrough
    result = resolve_value(float("nan"), {})
    assert result is None or (isinstance(result, float) and math.isnan(result))


def test_resolve_value_prefix_match():
    mappings = {}
    prefix = {"75 ": "Paris", "69 ": "Lyon"}
    assert resolve_value("75 001 Paris", mappings, prefix) == "Paris"


def test_resolve_value_prefix_longest_match():
    mappings = {}
    prefix = {"75": "IDF", "75 001": "Paris 1er"}
    assert resolve_value("75 001 Paris", mappings, prefix) == "Paris 1er"


def test_resolve_value_exact_over_prefix():
    mappings = {"75 001 Paris": "Paris Centre"}
    prefix = {"75": "IDF"}
    assert resolve_value("75 001 Paris", mappings, prefix) == "Paris Centre"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_entity_resolution_domain.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# domain/entity_resolution.py
import math


def resolve_value(
    value: str | None,
    mappings: dict[str, str],
    prefix_mappings: dict[str, str] | None = None,
) -> str | None:
    """Resolve a raw value to its canonical form using exact then prefix matching."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return value
    val = str(value)
    if val in mappings:
        return mappings[val]
    if prefix_mappings:
        for prefix in sorted(prefix_mappings, key=len, reverse=True):
            if val.startswith(prefix):
                return prefix_mappings[prefix]
    return val
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_entity_resolution_domain.py -x -v`
Expected: 7 PASSED

**Step 5: Commit**

```bash
git add domain/entity_resolution.py tests/unit/test_entity_resolution_domain.py
git commit -m "feat(domain): add resolve_value with exact and prefix matching"
```

---

### Task 9: Entity resolution — expand_canonical

**Files:**
- Modify: `domain/entity_resolution.py`
- Modify: `tests/unit/test_entity_resolution_domain.py`

**Step 1: Write failing test**

```python
# tests/unit/test_entity_resolution_domain.py — append
from domain.entity_resolution import expand_canonical


def test_expand_canonical_with_aliases():
    reverse = {"ACME": ["ACME SA", "ACME SARL"]}
    result = expand_canonical("ACME", reverse)
    assert "ACME" in result
    assert "ACME SA" in result
    assert "ACME SARL" in result
    assert len(result) == 3


def test_expand_canonical_no_aliases():
    result = expand_canonical("Unknown", {})
    assert result == ["Unknown"]


def test_expand_canonical_sorted():
    reverse = {"Z": ["C", "A", "B"]}
    result = expand_canonical("Z", reverse)
    assert result == ["A", "B", "C", "Z"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_entity_resolution_domain.py::test_expand_canonical_with_aliases -x -v`
Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

Append to `domain/entity_resolution.py`:

```python
def expand_canonical(
    canonical: str,
    reverse_mappings: dict[str, list[str]],
) -> list[str]:
    """Return all raw values + canonical, sorted."""
    values = set(reverse_mappings.get(canonical, []))
    values.add(canonical)
    return sorted(values)
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_entity_resolution_domain.py -x -v`
Expected: 10 PASSED

**Step 5: Commit**

```bash
git add domain/entity_resolution.py tests/unit/test_entity_resolution_domain.py
git commit -m "feat(domain): add expand_canonical for reverse entity lookup"
```

---

### Task 10: Normalization — normalize_supplier, normalize_material

**Files:**
- Create: `domain/normalization.py`
- Create: `tests/unit/test_normalization.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_normalization.py
from domain.normalization import normalize_supplier, normalize_material


class TestNormalizeSupplier:
    def test_strip_sa(self):
        assert normalize_supplier("ACME SA") == "ACME"

    def test_strip_sarl(self):
        assert normalize_supplier("Transport Martin SARL") == "TRANSPORT MARTIN"

    def test_strip_gmbh(self):
        assert normalize_supplier("Müller GmbH") == "MÜLLER"

    def test_strip_sas_with_dot(self):
        assert normalize_supplier("Durand SAS.") == "DURAND"

    def test_no_suffix(self):
        assert normalize_supplier("ACME") == "ACME"

    def test_extra_spaces(self):
        assert normalize_supplier("  ACME   SA  ") == "ACME"

    def test_uppercase(self):
        assert normalize_supplier("acme") == "ACME"


class TestNormalizeMaterial:
    def test_strip_leading_quantity_kg(self):
        assert normalize_material("25 kg Gravier") == "GRAVIER"

    def test_strip_leading_quantity_t(self):
        assert normalize_material("10t Sable") == "SABLE"

    def test_strip_after_dash(self):
        assert normalize_material("Gravier 0/20 - livré") == "GRAVIER 0/20"

    def test_combined(self):
        assert normalize_material("25 kg Gravier 0/20 - livré") == "GRAVIER 0/20"

    def test_no_transform_needed(self):
        assert normalize_material("Sable fin") == "SABLE FIN"

    def test_extra_spaces(self):
        assert normalize_material("  Sable   fin  ") == "SABLE FIN"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_normalization.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# domain/normalization.py
import re

_LEGAL_SUFFIXES = re.compile(
    r"\b(SA|SARL|SAS|SASU|EURL|SNC|GmbH|AG|BV|NV|Ltd|LLC|Inc|PLC)\b\.?",
    re.IGNORECASE,
)
_LEADING_QTY = re.compile(r"^\d+[\s,.]?\d*\s*(kg|t|m|l)\s+", re.IGNORECASE)


def normalize_supplier(name: str) -> str:
    """Normalize a supplier name for comparison: strip legal suffixes, uppercase."""
    result = _LEGAL_SUFFIXES.sub("", name)
    return " ".join(result.split()).strip().upper()


def normalize_material(name: str) -> str:
    """Normalize a material name: strip leading quantities and post-dash details."""
    result = _LEADING_QTY.sub("", name)
    if " - " in result:
        result = result.split(" - ")[0]
    return " ".join(result.split()).strip().upper()
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_normalization.py -x -v`
Expected: 13 PASSED

**Step 5: Commit**

```bash
git add domain/normalization.py tests/unit/test_normalization.py
git commit -m "feat(domain): add supplier and material normalization"
```

---

### Task 11: Anomaly rules — check_calculation_coherence

**Files:**
- Create: `domain/anomaly_rules.py`
- Create: `tests/unit/test_anomaly_rules.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_anomaly_rules.py
from datetime import date
from domain.anomaly_rules import check_calculation_coherence
from domain.models import LigneFacture


def test_coherent_calculation():
    ligne = LigneFacture(ligne_numero=1, prix_unitaire=10.0, quantite=5.0, prix_total=50.0)
    result = check_calculation_coherence(ligne)
    assert result.est_valide is True
    assert result.code_regle == "CALC_001"


def test_incoherent_calculation():
    ligne = LigneFacture(ligne_numero=1, prix_unitaire=10.0, quantite=5.0, prix_total=100.0)
    result = check_calculation_coherence(ligne)
    assert result.est_valide is False
    assert result.details["attendu"] == 50.0
    assert result.details["reel"] == 100.0


def test_within_tolerance():
    # 10 * 5 = 50, total = 50.4 → ecart = 0.8% < 1% tolerance
    ligne = LigneFacture(ligne_numero=1, prix_unitaire=10.0, quantite=5.0, prix_total=50.4)
    result = check_calculation_coherence(ligne)
    assert result.est_valide is True


def test_missing_fields():
    ligne = LigneFacture(ligne_numero=1, prix_unitaire=10.0)
    result = check_calculation_coherence(ligne)
    assert result.est_valide is True  # Cannot check, considered valid


def test_custom_tolerance():
    ligne = LigneFacture(ligne_numero=1, prix_unitaire=10.0, quantite=5.0, prix_total=52.0)
    # ecart = 4% — default 1% fails, 5% passes
    result_strict = check_calculation_coherence(ligne, tolerance=0.01)
    result_loose = check_calculation_coherence(ligne, tolerance=0.05)
    assert result_strict.est_valide is False
    assert result_loose.est_valide is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_anomaly_rules.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# domain/anomaly_rules.py
from domain.models import LigneFacture, ResultatAnomalie


def check_calculation_coherence(
    ligne: LigneFacture,
    tolerance: float = 0.01,
) -> ResultatAnomalie:
    """Check prix_unitaire * quantite ≈ prix_total within tolerance."""
    if not all([ligne.prix_unitaire, ligne.quantite, ligne.prix_total]):
        return ResultatAnomalie(
            est_valide=True, code_regle="CALC_001",
            description="Champs manquants, verification impossible",
        )
    attendu = ligne.prix_unitaire * ligne.quantite
    ecart = abs(attendu - ligne.prix_total) / abs(ligne.prix_total)
    if ecart > tolerance:
        return ResultatAnomalie(
            est_valide=False, code_regle="CALC_001",
            description=f"Ecart de {ecart:.1%} entre calcul et total",
            details={"attendu": attendu, "reel": ligne.prix_total, "ecart_pct": ecart},
        )
    return ResultatAnomalie(
        est_valide=True, code_regle="CALC_001",
        description="Calcul coherent",
    )
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_anomaly_rules.py -x -v`
Expected: 5 PASSED

**Step 5: Commit**

```bash
git add domain/anomaly_rules.py tests/unit/test_anomaly_rules.py
git commit -m "feat(domain): add check_calculation_coherence anomaly rule"
```

---

### Task 12: Anomaly rules — check_date_order, check_low_confidence

**Files:**
- Modify: `domain/anomaly_rules.py`
- Modify: `tests/unit/test_anomaly_rules.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_anomaly_rules.py — append
from domain.anomaly_rules import check_date_order, check_low_confidence


class TestCheckDateOrder:
    def test_valid_order(self):
        ligne = LigneFacture(
            ligne_numero=1,
            date_depart=date(2025, 1, 10),
            date_arrivee=date(2025, 1, 12),
        )
        assert check_date_order(ligne).est_valide is True

    def test_same_day(self):
        ligne = LigneFacture(
            ligne_numero=1,
            date_depart=date(2025, 1, 10),
            date_arrivee=date(2025, 1, 10),
        )
        assert check_date_order(ligne).est_valide is True

    def test_invalid_order(self):
        ligne = LigneFacture(
            ligne_numero=1,
            date_depart=date(2025, 1, 12),
            date_arrivee=date(2025, 1, 10),
        )
        result = check_date_order(ligne)
        assert result.est_valide is False
        assert result.code_regle == "DATE_001"

    def test_missing_dates(self):
        ligne = LigneFacture(ligne_numero=1)
        assert check_date_order(ligne).est_valide is True


class TestCheckLowConfidence:
    def test_above_threshold(self):
        assert check_low_confidence(0.85, seuil=0.6).est_valide is True

    def test_below_threshold(self):
        result = check_low_confidence(0.4, seuil=0.6)
        assert result.est_valide is False
        assert result.code_regle == "CONF_001"

    def test_at_threshold(self):
        assert check_low_confidence(0.6, seuil=0.6).est_valide is True

    def test_custom_threshold(self):
        assert check_low_confidence(0.75, seuil=0.8).est_valide is False
        assert check_low_confidence(0.85, seuil=0.8).est_valide is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_anomaly_rules.py::TestCheckDateOrder -x -v`
Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

Append to `domain/anomaly_rules.py`:

```python
def check_date_order(ligne: LigneFacture) -> ResultatAnomalie:
    """Check date_arrivee >= date_depart."""
    if not ligne.date_depart or not ligne.date_arrivee:
        return ResultatAnomalie(
            est_valide=True, code_regle="DATE_001",
            description="Dates manquantes",
        )
    if ligne.date_arrivee < ligne.date_depart:
        return ResultatAnomalie(
            est_valide=False, code_regle="DATE_001",
            description="Date d'arrivee anterieure au depart",
            details={
                "depart": str(ligne.date_depart),
                "arrivee": str(ligne.date_arrivee),
            },
        )
    return ResultatAnomalie(
        est_valide=True, code_regle="DATE_001",
        description="Dates coherentes",
    )


def check_low_confidence(
    confiance_globale: float,
    seuil: float = 0.6,
) -> ResultatAnomalie:
    """Check global confidence meets threshold."""
    if confiance_globale < seuil:
        return ResultatAnomalie(
            est_valide=False, code_regle="CONF_001",
            description=f"Confiance {confiance_globale:.2f} < seuil {seuil}",
            details={"confiance": confiance_globale, "seuil": seuil},
        )
    return ResultatAnomalie(
        est_valide=True, code_regle="CONF_001",
        description="Confiance suffisante",
    )
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_anomaly_rules.py -x -v`
Expected: 13 PASSED

**Step 5: Commit**

```bash
git add domain/anomaly_rules.py tests/unit/test_anomaly_rules.py
git commit -m "feat(domain): add check_date_order and check_low_confidence rules"
```

---

### Task 13: Analytics — achats (weighted_average_price, rank_suppliers, fragmentation)

**Files:**
- Create: `domain/analytics/achats.py`
- Create: `tests/unit/test_analytics_achats.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_analytics_achats.py
from domain.analytics.achats import (
    weighted_average_price,
    rank_suppliers_by_amount,
    fragmentation_index,
)
from domain.models import LigneFacture, ClassementFournisseur


def test_weighted_average_simple():
    items = [(10.0, 5.0), (20.0, 5.0)]  # (price, qty)
    assert weighted_average_price(items) == 15.0


def test_weighted_average_weighted():
    items = [(10.0, 8.0), (20.0, 2.0)]
    # (10*8 + 20*2) / 10 = 120/10 = 12
    assert weighted_average_price(items) == 12.0


def test_weighted_average_empty():
    assert weighted_average_price([]) == 0.0


def test_weighted_average_zero_quantity():
    items = [(10.0, 0.0), (20.0, 0.0)]
    assert weighted_average_price(items) == 0.0


def test_rank_suppliers():
    lines = [
        (LigneFacture(ligne_numero=1, prix_total=100.0), "ACME"),
        (LigneFacture(ligne_numero=2, prix_total=300.0), "ACME"),
        (LigneFacture(ligne_numero=3, prix_total=200.0), "Beta"),
    ]
    result = rank_suppliers_by_amount(lines, limit=5)
    assert len(result) == 2
    assert result[0].nom == "ACME"
    assert result[0].montant_total == 400.0
    assert result[0].nombre_documents == 2
    assert result[1].nom == "Beta"


def test_rank_suppliers_limit():
    lines = [
        (LigneFacture(ligne_numero=i, prix_total=float(i * 100)), f"Supplier{i}")
        for i in range(1, 11)
    ]
    result = rank_suppliers_by_amount(lines, limit=3)
    assert len(result) == 3
    assert result[0].nom == "Supplier10"


def test_rank_suppliers_empty():
    assert rank_suppliers_by_amount([], limit=5) == []


def test_fragmentation_index():
    lines = [
        (LigneFacture(ligne_numero=1, type_matiere="Sable"), "ACME"),
        (LigneFacture(ligne_numero=2, type_matiere="Sable"), "Beta"),
        (LigneFacture(ligne_numero=3, type_matiere="Gravier"), "ACME"),
    ]
    result = fragmentation_index(lines)
    assert result["Sable"] == 2
    assert result["Gravier"] == 1


def test_fragmentation_none_material():
    lines = [
        (LigneFacture(ligne_numero=1), "ACME"),
    ]
    result = fragmentation_index(lines)
    assert result["inconnu"] == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_analytics_achats.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# domain/analytics/achats.py
from domain.models import LigneFacture, ClassementFournisseur


def weighted_average_price(items: list[tuple[float, float]]) -> float:
    """Weighted average price. items = [(prix_unitaire, quantite), ...]"""
    total_qty = sum(qty for _, qty in items)
    if total_qty == 0:
        return 0.0
    return sum(price * qty for price, qty in items) / total_qty


def rank_suppliers_by_amount(
    lines: list[tuple[LigneFacture, str]],
    limit: int = 5,
) -> list[ClassementFournisseur]:
    """Rank suppliers by total amount descending."""
    by_supplier: dict[str, dict] = {}
    for ligne, fournisseur in lines:
        if fournisseur not in by_supplier:
            by_supplier[fournisseur] = {"montant": 0.0, "count": 0}
        by_supplier[fournisseur]["montant"] += ligne.prix_total or 0
        by_supplier[fournisseur]["count"] += 1
    ranked = [
        ClassementFournisseur(
            nom=name, montant_total=data["montant"],
            nombre_documents=data["count"],
        )
        for name, data in by_supplier.items()
    ]
    ranked.sort(key=lambda s: s.montant_total, reverse=True)
    return ranked[:limit]


def fragmentation_index(
    lines: list[tuple[LigneFacture, str]],
) -> dict[str, int]:
    """Count distinct suppliers per material type."""
    by_material: dict[str, set[str]] = {}
    for ligne, fournisseur in lines:
        mat = ligne.type_matiere or "inconnu"
        by_material.setdefault(mat, set()).add(fournisseur)
    return {mat: len(suppliers) for mat, suppliers in by_material.items()}
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_analytics_achats.py -x -v`
Expected: 9 PASSED

**Step 5: Commit**

```bash
git add domain/analytics/achats.py tests/unit/test_analytics_achats.py
git commit -m "feat(domain): add purchasing analytics (weighted avg, ranking, fragmentation)"
```

---

### Task 14: Extraction — strategy_selector

**Files:**
- Create: `domain/extraction/strategy_selector.py`
- Create: `tests/unit/test_strategy_selector.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_strategy_selector.py
from domain.extraction.strategy_selector import (
    ExtractionStrategy, select_strategy, build_fallback_chain,
)


def test_select_text_strategy():
    assert select_strategy(chars_per_page=200, has_tables=False) == ExtractionStrategy.PDFPLUMBER_TEXT


def test_select_table_strategy():
    assert select_strategy(chars_per_page=200, has_tables=True) == ExtractionStrategy.PDFPLUMBER_TABLES


def test_select_ocr_for_scanned():
    assert select_strategy(chars_per_page=10, has_tables=False) == ExtractionStrategy.OCR_TESSERACT


def test_select_ocr_at_threshold():
    assert select_strategy(chars_per_page=50, has_tables=False) == ExtractionStrategy.PDFPLUMBER_TEXT
    assert select_strategy(chars_per_page=49, has_tables=False) == ExtractionStrategy.OCR_TESSERACT


def test_custom_threshold():
    assert select_strategy(chars_per_page=80, has_tables=False, threshold=100) == ExtractionStrategy.OCR_TESSERACT


def test_fallback_chain_from_text():
    chain = build_fallback_chain(ExtractionStrategy.PDFPLUMBER_TEXT)
    assert chain[0] == ExtractionStrategy.PDFPLUMBER_TEXT
    assert len(chain) == 4


def test_fallback_chain_from_ocr():
    chain = build_fallback_chain(ExtractionStrategy.OCR_PADDLEOCR)
    assert chain[0] == ExtractionStrategy.OCR_PADDLEOCR
    assert ExtractionStrategy.PDFPLUMBER_TEXT not in chain


def test_fallback_chain_unknown():
    chain = build_fallback_chain(ExtractionStrategy.PDFPLUMBER_TABLES)
    assert len(chain) == 4  # Full chain
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_strategy_selector.py -x -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# domain/extraction/strategy_selector.py
from enum import Enum


class ExtractionStrategy(Enum):
    PDFPLUMBER_TEXT = "pdfplumber_text"
    PDFPLUMBER_TABLES = "pdfplumber_tables"
    OCR_TESSERACT = "ocr_tesseract"
    OCR_PADDLEOCR = "ocr_paddleocr"
    OCR_MLX_VLM = "ocr_mlx_vlm"
    MIXED = "mixed_strategy"


def select_strategy(
    chars_per_page: float,
    has_tables: bool,
    threshold: int = 50,
) -> ExtractionStrategy:
    """Select extraction strategy based on detected content."""
    if chars_per_page < threshold:
        return ExtractionStrategy.OCR_TESSERACT
    if has_tables:
        return ExtractionStrategy.PDFPLUMBER_TABLES
    return ExtractionStrategy.PDFPLUMBER_TEXT


def build_fallback_chain(
    primary: ExtractionStrategy,
) -> list[ExtractionStrategy]:
    """Build fallback chain starting from primary strategy."""
    full_chain = [
        ExtractionStrategy.PDFPLUMBER_TEXT,
        ExtractionStrategy.OCR_PADDLEOCR,
        ExtractionStrategy.OCR_MLX_VLM,
        ExtractionStrategy.OCR_TESSERACT,
    ]
    if primary in full_chain:
        idx = full_chain.index(primary)
        return full_chain[idx:]
    return full_chain
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_strategy_selector.py -x -v`
Expected: 8 PASSED

**Step 5: Full regression check**

Run: `pytest tests/ -x -q && PYTHONPATH=. pytest dashboard/tests/ -x -q`
Expected: All PASS

**Step 6: Commit**

```bash
git add domain/extraction/strategy_selector.py tests/unit/test_strategy_selector.py
git commit -m "feat(domain): add extraction strategy selector with fallback chain"
```

---

## Phase 2: Adapters (outlined — detailed steps follow same TDD pattern)

### Task 15: SQLAlchemy models adapter

**Files:**
- Create: `dashboard/adapters/__init__.py`
- Create: `dashboard/adapters/outbound/__init__.py`
- Create: `dashboard/adapters/outbound/sqlalchemy_models.py` (copy from `dashboard/data/models.py`)
- Create: `dashboard/adapters/inbound/__init__.py`

Copy `dashboard/data/models.py` to `dashboard/adapters/outbound/sqlalchemy_models.py` and re-export from original location for backwards compatibility. No test changes needed — existing tests validate the ORM models.

**Step 1: Create adapter directories and copy**

```bash
mkdir -p dashboard/adapters/outbound dashboard/adapters/inbound
touch dashboard/adapters/__init__.py dashboard/adapters/outbound/__init__.py dashboard/adapters/inbound/__init__.py
cp dashboard/data/models.py dashboard/adapters/outbound/sqlalchemy_models.py
```

**Step 2: Update original to re-export**

Replace `dashboard/data/models.py` content with re-exports from new location:

```python
# dashboard/data/models.py — backwards compatibility facade
# ORM models moved to dashboard/adapters/outbound/sqlalchemy_models.py
from dashboard.adapters.outbound.sqlalchemy_models import (  # noqa: F401
    Base, Fournisseur, Document, LigneFacture, Anomalie,
    EntityMapping, MergeAuditLog, CorrectionLog, BoundingBox, UploadLog,
)
```

**Step 3: Verify no regression**

Run: `PYTHONPATH=. pytest dashboard/tests/ -x -q`
Expected: All PASS

**Step 4: Commit**

```bash
git add dashboard/adapters/ dashboard/data/models.py
git commit -m "refactor: move ORM models to adapters/outbound, keep facade"
```

---

### Task 16: SqlAlchemyMappingRepository adapter

**Files:**
- Create: `dashboard/adapters/outbound/sqlalchemy_repos.py`
- Create: `dashboard/tests/integration/test_sqlalchemy_repos.py`
- Create: `dashboard/tests/integration/__init__.py`

Follow TDD pattern: write integration test with SQLite in-memory → implement adapter → verify. The adapter implements `MappingRepository` port using SQLAlchemy session. Test creates a real in-memory SQLite session, inserts test data, then verifies the adapter returns domain objects correctly.

---

### Task 17: SqlAlchemyDocumentRepository adapter

Same TDD pattern as Task 16, implementing `DocumentRepository` port. Key methods: `save()` maps domain `Document` → ORM, `find_by_filename()` maps ORM → domain.

---

### Task 18: SqlAlchemyLineItemRepository adapter

Same TDD pattern, implementing `LineItemRepository`. Key method: `list_with_supplier()` joins LigneFacture with Document/Fournisseur and returns `list[tuple[LigneFacture, str]]`.

---

### Task 19: Redis cache adapter

**Files:**
- Create: `dashboard/adapters/outbound/redis_cache.py`
- Test: `dashboard/tests/integration/test_redis_cache.py`

Implement `CachePort`. Test with mock Redis (or fakeredis if available). Graceful fallback when Redis unavailable.

---

### Task 20: PDF extraction adapters

**Files:**
- Create: `tools/adapters/__init__.py`
- Create: `tools/adapters/pdfplumber_extractor.py`
- Create: `tools/adapters/tesseract_ocr.py`
- Test: `tests/integration/test_pdf_adapters.py`

Implement `PDFTextExtractorPort` and `OCRProcessorPort`. Each adapter wraps the existing extraction logic from `tools/pdf_reader.py` and `tools/ocr_processor.py`.

---

## Phase 3: Wire Existing Modules to Domain (outlined)

### Task 21: Wire dashboard/analytics/achats.py as facade

Replace business logic with calls to `domain/analytics/achats.py` + `SqlAlchemyLineItemRepository`. Keep same function signatures for Streamlit pages compatibility.

### Task 22: Wire dashboard/analytics/anomalies.py as facade

Replace anomaly check logic with calls to `domain/anomaly_rules.py`. Keep same `run_anomaly_detection()` signature.

### Task 23: Wire dashboard/data/entity_resolution.py as facade

Replace `resolve_column()` internals to use `domain/entity_resolution.resolve_value()`. Keep same DataFrame-level API.

### Task 24: Wire tools/pdf_reader.py as facade

Replace strategy selection with `domain/extraction/strategy_selector.py`. Keep CLI interface.

### Task 25: Wire dashboard/app.py composition root

Inject repositories and services via `st.session_state` instead of passing raw sessions.

---

## Phase 4: Migrate Tests (outlined)

### Task 26: Move dashboard tests to unit/ and integration/

Move tests that test pure logic to `dashboard/tests/unit/`. Move tests that need DB/sessions to `dashboard/tests/integration/`. Update imports.

### Task 27: Move root tests to unit/ and integration/

Same split for `tests/test_extraction.py` and `tests/test_schemas.py`.

---

## Phase 5: Cleanup (outlined)

### Task 28: Remove facade code from dashboard/analytics/

Once pages import domain directly, remove the thin facades.

### Task 29: Remove legacy dashboard/data/ modules

Once all imports point to `domain/` and `adapters/`, remove the old files.

### Task 30: Update CLAUDE.md with final architecture

Update the Architecture section to reflect the hexagonal structure.

### Task 31: Final regression check and commit

Run all tests. Verify no import of SQLAlchemy/Streamlit/Redis in `domain/`. Tag the migration as complete.

```bash
# Verify domain purity
grep -r "sqlalchemy\|streamlit\|redis\|pdfplumber" domain/ && echo "FAIL: domain has infrastructure imports" || echo "PASS: domain is pure"
pytest tests/ -x -v && PYTHONPATH=. pytest dashboard/tests/ -x -v
```
