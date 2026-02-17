# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent POC for automated data extraction from heterogeneous PDFs (invoices, delivery notes, quotes) with a Streamlit analytics dashboard. Two main subsystems: an **extraction pipeline** (Python tools + 4 LLM agent prompts) and a **Streamlit dashboard** ("Rationalize") with SQLite/SQLAlchemy storage, entity resolution, and anomaly detection.

**Language**: French-first codebase (variable names, comments, UI labels, agent prompts). Python 3.11+.

## Commands

```bash
# Run all tests (root-level: domain unit + extraction integration)
pytest tests/

# Run all dashboard tests (PYTHONPATH required for dashboard.* imports)
PYTHONPATH=. pytest dashboard/tests/

# Run only domain unit tests (fast, no I/O)
pytest tests/unit/

# Run only integration tests
pytest tests/integration/
PYTHONPATH=. pytest dashboard/tests/integration/

# Run a single test file
PYTHONPATH=. pytest dashboard/tests/integration/test_entity_resolution.py

# Run a single test
PYTHONPATH=. pytest dashboard/tests/integration/test_achats.py -k test_top_fournisseurs -v

# Run the Streamlit dashboard
cd dashboard && streamlit run app.py

# Start Docker services (PaddleOCR + Redis + dashboard)
docker compose up

# PDF extraction tools
python tools/pdf_reader.py samples/facture1.pdf                    # text extraction (auto strategy)
python tools/pdf_reader.py samples/scan.pdf --strategy ocr         # force OCR
python tools/table_extractor.py samples/facture1.pdf               # table extraction
python tools/ocr_processor.py samples/scan.pdf                     # Tesseract OCR
python tools/json_validator.py output/extractions/f.json schemas/extraction.json  # validate JSON
python tools/batch_runner.py samples/ output/                      # batch all PDFs

# Install dependencies
pip install -r requirements.txt              # extraction tools
pip install -r dashboard/requirements.txt    # dashboard
```

## Méthodologie de développement

### Architecture hexagonale (obligatoire)

Tout nouveau code DOIT respecter l'architecture hexagonale (Ports & Adapters). Cette structure isole la logique métier des dépendances externes (DB, API, fichiers, UI).

**Structure cible par module :**

```
module/
├── domain/           # Coeur métier — AUCUNE dépendance externe
│   ├── models.py     # Entités et value objects du domaine
│   ├── services.py   # Logique métier pure (use cases)
│   └── ports.py      # Interfaces (ABC) définissant les contrats d'entrée/sortie
├── adapters/
│   ├── inbound/      # Adaptateurs entrants (CLI, API, Streamlit handlers)
│   └── outbound/     # Adaptateurs sortants (DB, fichiers, API externes, OCR)
└── tests/
    ├── unit/         # Tests du domaine (rapides, sans I/O)
    └── integration/  # Tests des adaptateurs (avec fixtures/mocks)
```

**Règles strictes :**

1. **Le domaine ne dépend de rien** — `domain/` n'importe jamais depuis `adapters/`, ni depuis des bibliothèques d'infrastructure (SQLAlchemy, Streamlit, Redis, pdfplumber, etc.)
2. **Inversion de dépendances** — Le domaine définit des `ports` (interfaces ABC). Les `adapters` les implémentent. L'injection se fait à la composition (point d'entrée).
3. **Flux de données** — Adaptateur entrant → Port entrant → Service domaine → Port sortant → Adaptateur sortant
4. **Pas de logique métier dans les adaptateurs** — Les adaptateurs font uniquement la traduction entre le monde extérieur et le domaine (mapping, sérialisation, appels I/O)
5. **Testabilité** — Tout service du domaine doit être testable avec des fakes/stubs, sans aucune infrastructure réelle

**Application au projet :**

- **Extraction pipeline** : les stratégies OCR/PDF sont des adaptateurs sortants, la logique de classification/extraction est dans le domaine
- **Dashboard** : SQLAlchemy, Redis, Streamlit sont des adaptateurs. La résolution d'entités, la détection d'anomalies, les calculs analytiques sont dans le domaine
- **Nouveau module** : toujours commencer par définir les ports (interfaces) et le domaine avant d'écrire un adaptateur

### TDD obligatoire (Test-Driven Development)

Tout développement DOIT suivre le cycle TDD strict : **Red → Green → Refactor**.

**Cycle obligatoire :**

1. **Red** — Écrire un test qui échoue. Le test décrit le comportement attendu AVANT toute implémentation. Lancer le test et vérifier qu'il échoue pour la bonne raison.
2. **Green** — Écrire le code MINIMUM pour faire passer le test. Pas d'optimisation, pas de généralisation prématurée.
3. **Refactor** — Nettoyer le code (domaine ET test) en gardant tous les tests au vert. Éliminer la duplication, améliorer la lisibilité.

**Règles strictes :**

1. **Jamais de code de production sans test échouant au préalable** — Si aucun test ne motive l'écriture du code, le code ne doit pas exister
2. **Un test à la fois** — Ne pas écrire plusieurs tests qui échouent en même temps. Un seul cycle Red→Green→Refactor à la fois
3. **Tests du domaine d'abord** — Commencer par les tests unitaires du domaine (rapides, sans I/O), puis les tests d'intégration des adaptateurs
4. **Exécuter les tests à chaque étape** — Après chaque modification (Red, Green, Refactor), lancer les tests concernés pour vérifier l'état
5. **Couverture minimale** — Tout nouveau code doit avoir une couverture de tests ≥ 90%. Les cas limites (None, listes vides, erreurs) doivent être testés
6. **Nommage des tests** — `test_<comportement_attendu>` en français : `test_extraction_echoue_si_pdf_vide`, `test_resolution_ignore_valeurs_none`

**Commandes de vérification :**

```bash
# Vérifier que le test échoue (Red)
PYTHONPATH=. pytest dashboard/tests/unit/test_mon_module.py -x -v

# Vérifier que le test passe (Green)
PYTHONPATH=. pytest dashboard/tests/unit/test_mon_module.py -x -v

# Vérifier que tout reste au vert (Refactor)
PYTHONPATH=. pytest dashboard/tests/ -x -v
pytest tests/ -x -v
```

## Architecture

### Hexagonal Architecture (Ports & Adapters)

The codebase follows hexagonal architecture with a centralized `domain/` package at project root shared by both subsystems.

```
domain/                          # Pure business logic — ZERO external dependencies
├── models.py                    # Entities, value objects, enums (French names)
├── ports.py                     # ABC interfaces (English method names)
├── entity_resolution.py         # resolve_value(), expand_canonical()
├── normalization.py             # normalize_supplier(), normalize_material()
├── anomaly_rules.py             # check_calculation_coherence(), check_date_order(), check_low_confidence()
├── analytics/achats.py          # weighted_average_price(), rank_suppliers_by_amount(), fragmentation_index()
└── extraction/strategy_selector.py  # select_strategy(), build_fallback_chain()

dashboard/
├── adapters/
│   ├── outbound/
│   │   ├── sqlalchemy_models.py # ORM models (canonical location)
│   │   ├── sqlalchemy_repos.py  # SqlAlchemyMappingRepository, DocumentRepository, LineItemRepository
│   │   └── redis_cache.py       # RedisCacheAdapter, InMemoryCacheAdapter
│   └── inbound/                 # (future: Streamlit handlers)
├── data/                        # Facades — delegate to domain + adapters
│   ├── models.py                # Re-exports from adapters/outbound/sqlalchemy_models.py
│   ├── entity_resolution.py     # resolve_column() delegates to domain.entity_resolution
│   └── ...
├── analytics/                   # Facades — anomalies.py delegates to domain.anomaly_rules
├── app.py                       # Composition root: engine, session factory, cache adapter
└── tests/
    ├── unit/                    # Tests without I/O (mocks)
    └── integration/             # Tests with in-memory SQLite

tools/
├── adapters/
│   ├── pdfplumber_extractor.py  # PdfplumberExtractor (PDFTextExtractorPort)
│   └── tesseract_ocr.py         # TesseractOCR (OCRProcessorPort)
└── pdf_reader.py                # Facade — strategy selection delegates to domain

tests/
├── unit/                        # Domain unit tests (~158 tests, <0.1s)
└── integration/                 # Adapter + extraction tests
```

**Domain purity rule**: `domain/` imports only Python stdlib (dataclasses, datetime, enum, abc, math, re). Verify with: `grep -r "sqlalchemy\|streamlit\|redis\|pdfplumber" domain/`

**Naming convention**: English for code/method names, French for domain model names (Fournisseur, LigneFacture, Anomalie, etc.)

### Port Interfaces (`domain/ports.py`)

- **Repository ports**: DocumentRepository, SupplierRepository, LineItemRepository, AnomalyRepository, MappingRepository, AuditRepository
- **Infrastructure ports**: CachePort, GeocodingPort, PDFTextExtractorPort, OCRProcessorPort, TableExtractorPort, FileSystemPort
- **Service ports**: IngestionService, AnomalyDetectionService, EntityResolutionService

### Extraction Pipeline

4 LLM agents orchestrated sequentially. Agent prompts live in `prompts/` (read them before invoking an agent role). JSON schemas for validation in `schemas/`.

```
samples/*.pdf → tools/pdf_reader.py → Agent Classifier → Agent Extractor → output/extractions/
                                                                              ↓
                                                           Agent Analyzer → output/analyses/
                                                                              ↓
                                                           Agent Reporter → output/reports/
```

**Extraction strategies** (auto-detected by `pdf_reader.py` via `domain.extraction.strategy_selector`): pdfplumber for native text, Tesseract OCR for scans, PaddleOCR PP-StructureV3 for tables, MLX VLM for Apple Silicon GPU. Fallback chain: pdfplumber → PaddleOCR → MLX → Tesseract.

**Target extraction fields** per invoice line: `type_matiere`, `unite`, `prix_unitaire`, `quantite`, `prix_total`, `date_depart`, `date_arrivee`, `lieu_depart`, `lieu_arrivee`. Each field has a confidence score (0-1). Thresholds: 0.3 minimum, 0.6 document success, 0.8 reliable.

### Dashboard (`dashboard/`)

Streamlit app with 8 pages. Entry point: `dashboard/app.py` (composition root). Config: `dashboard/config.yaml`.

**Data flow**: `app.py` initializes SQLite engine + cache adapter → stores in `st.session_state` → pages import engine from session state → analytics modules query DB with entity resolution applied at runtime (delegated to `domain.entity_resolution`).

**Key layers**:
- `adapters/outbound/sqlalchemy_models.py` — 10 ORM models (canonical location)
- `adapters/outbound/sqlalchemy_repos.py` — Repository implementations (MappingRepository, DocumentRepository, LineItemRepository)
- `adapters/outbound/redis_cache.py` — CachePort implementation with Redis fallback
- `data/models.py` — Facade re-exporting ORM models for backwards compatibility
- `data/db.py` — Engine/session management; resolves relative SQLite paths from dashboard dir
- `data/entity_resolution.py` — Facade delegating to `domain.entity_resolution.resolve_value()`
- `data/entity_enrichment.py` — Auto-resolution via rapidfuzz fuzzy matching
- `data/ingestion.py` — Loads extraction JSONs into DB
- `data/upload_pipeline.py` — PDF upload with SHA-256 duplicate detection
- `analytics/` — Query modules per page, anomaly checks delegate to `domain.anomaly_rules`
- `components/` — Reusable Streamlit UI widgets (filters, charts, data_table, kpi_card)
- `pages/` — 8 Streamlit pages

### Entity Resolution

Non-destructive: raw DB values unchanged, `EntityMapping` table stores `raw_value → canonical_value` with status (approved/pending_review/rejected). `MergeAuditLog` tracks all operations for undo. Auto-resolution uses rapidfuzz (thresholds: 0.90 auto-merge, 0.50 review). Core resolution logic in `domain/entity_resolution.py`, DataFrame-level API in `dashboard/data/entity_resolution.py`.

### Database

SQLite at `dashboard/data/rationalize.db`. Key relationships: `Document` → `Fournisseur` (FK), `Document` → `LigneFacture` (1:N), `Document` → `Anomalie` (1:N). Uses timezone-aware UTC datetimes.

## Configuration

- `config/settings.yaml` — Extraction pipeline settings (strategies, OCR config, confidence thresholds, TJM rates)
- `dashboard/config.yaml` — Dashboard settings (DB URL, Redis, anomaly rules, entity resolution thresholds, UI)
- `pyproject.toml` — pytest config points to `tests/` (root-level only; dashboard tests run via `pytest dashboard/tests/`)

## Orchestration Rules

1. **Read the agent prompt** (`prompts/*.md`) before playing an agent role
2. **Validate every JSON output** against `schemas/` (classification.json, extraction.json, analysis.json)
3. **On extraction failure**: log the error with reason, skip the document, don't block the pipeline
4. **Log every step** in `output/pipeline_log.json`
5. **Use Python tools** for heavy lifting (text extraction, OCR, tables); the LLM agent role is to interpret, structure, and analyze the extracted text

## Docker Services

`docker-compose.yml` defines: `paddleocr` (port 8080), `dashboard` (Streamlit port 8501, mounts `/output` read-only), `redis` (port 6379, caching with 3600s TTL).
