# Migration Architecture Hexagonale + TDD

**Date** : 2026-02-17
**Branche** : `refactor/hexagonal-tdd`
**Statut** : Approuvé

## Contexte

Le POC swarm-pdf-extract fonctionne mais souffre d'un couplage fort entre logique métier et infrastructure (SQLAlchemy, Streamlit, pdfplumber, Redis). L'objectif est de restructurer le projet en architecture hexagonale (Ports & Adapters) avec du TDD obligatoire, sans casser l'existant.

## Décisions

- **Approche A retenue** : domaine centralisé partagé (`domain/` à la racine)
- **Migration en parallèle** : dashboard et pipeline d'extraction simultanément
- **Tests existants** : gardés et adaptés progressivement (pas de réécriture)
- **Nommage** : code en anglais, modèles domaine en français (vocabulaire métier)

## Structure cible

```
swarm-pdf-extract/
├── domain/                          # Coeur métier partagé, ZÉRO dépendance externe
│   ├── __init__.py
│   ├── models.py                    # Entités : Document, LigneFacture, Anomalie, etc.
│   ├── ports.py                     # Interfaces ABC (repositories, services, providers)
│   ├── entity_resolution.py         # resolve_value(), expand_canonical()
│   ├── normalization.py             # normalize_supplier(), normalize_material()
│   ├── anomaly_rules.py             # check_calculation_coherence(), check_date_order()
│   ├── ingestion_rules.py           # Parsing dates, transformation JSON → entités
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── achats.py                # weighted_average_price(), rank_suppliers_by_amount()
│   │   ├── logistique.py            # Délais, regroupement, routes
│   │   ├── qualite.py               # Scores de confiance, fiabilité
│   │   └── tendances.py             # Agrégations temporelles
│   └── extraction/
│       ├── __init__.py
│       ├── strategy_selector.py     # select_strategy(), build_fallback_chain()
│       ├── table_analysis.py        # Inférence types colonnes, mapping champs
│       └── confidence.py            # Seuils et calculs de confiance
│
├── dashboard/
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── outbound/
│   │   │   ├── __init__.py
│   │   │   ├── sqlalchemy_repos.py  # Implémente les ports Repository
│   │   │   ├── sqlalchemy_models.py # ORM models (ex data/models.py)
│   │   │   ├── redis_cache.py       # Implémente CachePort
│   │   │   └── geocoding.py         # Implémente GeocodingPort
│   │   └── inbound/
│   │       └── __init__.py
│   ├── data/                        # Conservé pendant la migration
│   ├── analytics/                   # Deviennent des façades → domain/analytics/
│   ├── components/                  # Inchangé
│   ├── pages/                       # Inchangé (adaptateurs entrants implicites)
│   └── tests/
│       ├── unit/                    # Tests domaine (rapides)
│       └── integration/             # Tests existants migrés
│
├── tools/
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── pdfplumber_extractor.py  # Implémente PDFTextExtractorPort
│   │   ├── tesseract_ocr.py         # Implémente OCRProcessorPort
│   │   ├── paddleocr_adapter.py     # Implémente OCRProcessorPort
│   │   └── mlx_adapter.py           # Implémente OCRProcessorPort
│   ├── pdf_reader.py                # Façade mince → domain + adapters
│   └── ...
│
├── tests/
│   ├── unit/
│   └── integration/
```

## Modèles domaine

Dataclasses Python pures, aucune dépendance externe.

```python
# domain/models.py
from dataclasses import dataclass, field
from datetime import date, datetime
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

## Ports (interfaces ABC)

```python
# domain/ports.py — nommage anglais

# OUTBOUND PORTS
class DocumentRepository(ABC):
    def save(self, document: Document) -> Document: ...
    def find_by_filename(self, filename: str) -> Document | None: ...
    def list_all(self) -> list[Document]: ...

class SupplierRepository(ABC):
    def find_or_create(self, name: str, address: str | None = None) -> Fournisseur: ...
    def list_all(self) -> list[Fournisseur]: ...

class LineItemRepository(ABC):
    def list_by_document(self, document_id: int) -> list[LigneFacture]: ...
    def list_with_supplier(self) -> list[tuple[LigneFacture, str]]: ...

class AnomalyRepository(ABC):
    def save(self, anomaly: Anomalie) -> Anomalie: ...
    def delete_by_document(self, document_id: int) -> int: ...
    def list_all(self) -> list[Anomalie]: ...
    def count_by_severity(self) -> dict[str, int]: ...

class MappingRepository(ABC):
    def get_mappings(self, entity_type: str) -> dict[str, str]: ...
    def get_prefix_mappings(self, entity_type: str) -> dict[str, str]: ...
    def get_reverse_mappings(self, entity_type: str) -> dict[str, list[str]]: ...
    def save_mapping(self, mapping: EntityMapping) -> EntityMapping: ...
    def get_pending_reviews(self, entity_type: str) -> list[EntityMapping]: ...

class AuditRepository(ABC):
    def record(self, entry: MergeAuditEntry) -> MergeAuditEntry: ...
    def list_by_type(self, entity_type: str) -> list[MergeAuditEntry]: ...

class CachePort(ABC):
    def get(self, key: str) -> object | None: ...
    def set(self, key: str, value: object, ttl: int = 3600) -> None: ...
    def invalidate(self, prefix: str) -> None: ...

class GeocodingPort(ABC):
    def geocode(self, address: str) -> tuple[float, float] | None: ...
    def distance_km(self, coord1: tuple, coord2: tuple) -> float: ...

class PDFTextExtractorPort(ABC):
    def extract_text(self, pdf_path: str) -> dict: ...

class OCRProcessorPort(ABC):
    def extract_text_ocr(self, pdf_path: str, lang: str = "fra+eng") -> dict: ...

class TableExtractorPort(ABC):
    def extract_tables(self, pdf_path: str) -> dict: ...

class FileSystemPort(ABC):
    def read_json(self, path: str) -> dict: ...
    def write_json(self, path: str, data: dict) -> None: ...
    def list_files(self, directory: str, pattern: str) -> list[str]: ...
    def save_upload(self, content: bytes, filename: str) -> tuple[str, str]: ...

# INBOUND PORTS
class IngestionService(ABC):
    def ingest_extraction(self, data: dict) -> Document | None: ...
    def ingest_directory(self, directory: str) -> dict: ...

class AnomalyDetectionService(ABC):
    def detect(self, rules: list[dict]) -> list[Anomalie]: ...

class EntityResolutionService(ABC):
    def merge(self, entity_type, canonical, raw_values, source) -> MergeAuditEntry: ...
    def revert_merge(self, audit_id: int) -> None: ...
    def run_auto_resolution(self, config: dict) -> dict: ...
```

## Services domaine (logique pure)

### entity_resolution.py
- `resolve_value(value, mappings, prefix_mappings)` — résolution exacte/préfixe
- `expand_canonical(canonical, reverse_mappings)` — expansion inverse

### normalization.py
- `normalize_supplier(name)` — strip suffixes légaux, uppercase
- `normalize_material(name)` — strip quantités, séparateurs

### anomaly_rules.py
- `check_calculation_coherence(ligne, tolerance)` — prix_unitaire x quantite vs prix_total
- `check_date_order(ligne)` — date_arrivee >= date_depart
- `check_low_confidence(confiance, seuil)` — confiance >= seuil

### analytics/achats.py
- `weighted_average_price(items)` — moyenne pondérée
- `rank_suppliers_by_amount(lines, limit)` — classement décroissant
- `fragmentation_index(lines)` — fournisseurs distincts par matière

### extraction/strategy_selector.py
- `select_strategy(chars_per_page, has_tables, threshold)` — choix de stratégie
- `build_fallback_chain(primary)` — chaîne de fallback

## Stratégie de migration

Migration progressive en 5 phases, sans big bang :

1. **Phase 1** : Créer `domain/` (models, ports, services) + tests unitaires
   - L'existant continue de fonctionner sans modification
2. **Phase 2** : Créer les adaptateurs (`sqlalchemy_repos`, `redis_cache`, `pdfplumber_extractor`)
   - Implémentent les ports, mappent ORM ↔ domaine
3. **Phase 3** : Brancher les modules existants sur le domaine
   - `dashboard/analytics/*.py` deviennent des façades minces
   - `tools/*.py` délèguent aux adaptateurs
4. **Phase 4** : Migrer les tests vers `unit/` et `integration/`
   - Déplacement, pas réécriture
5. **Phase 5** : Nettoyer les façades transitoires

### Exemple de façade transitoire (phase 3)

```python
# dashboard/analytics/achats.py — façade
from domain.analytics.achats import weighted_average_price, rank_suppliers_by_amount
from dashboard.adapters.outbound.sqlalchemy_repos import SqlAlchemyLineItemRepository

def top_fournisseurs_by_montant(session, limit=5):
    repo = SqlAlchemyLineItemRepository(session)
    lines = repo.list_with_supplier()
    return rank_suppliers_by_amount(lines, limit)
```

## Matrice de couplage actuelle

| Module | Logique pure | Infrastructure | Action |
|--------|-------------|---------------|--------|
| entity_enrichment.py | 60% | 40% | Extraire domaine |
| anomalies.py | 40% | 60% | Extraire règles |
| entity_resolution.py | 30% | 70% | Extraire resolve_value |
| achats.py | 10% | 90% | Façade → domaine |
| pdf_reader.py | 5% | 95% | Adapter via port |
| models.py | 0% | 100% | Reste en adaptateur |
