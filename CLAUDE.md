# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-agent POC for automated data extraction from heterogeneous PDFs (invoices, delivery notes, quotes) with a Streamlit analytics dashboard. Two main subsystems: an **extraction pipeline** (Python tools + 4 LLM agent prompts) and a **Streamlit dashboard** ("Rationalize") with SQLite/SQLAlchemy storage, entity resolution, and anomaly detection.

**Language**: French-first codebase (variable names, comments, UI labels, agent prompts). Python 3.11+.

## Commands

```bash
# Run all tests (root-level extraction tests)
pytest tests/

# Run all dashboard tests
pytest dashboard/tests/

# Run a single test file
pytest dashboard/tests/test_entity_resolution.py

# Run a single test
pytest dashboard/tests/test_achats.py::TestAchats::test_top_fournisseurs -v

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

## Architecture

### Extraction Pipeline

4 LLM agents orchestrated sequentially. Agent prompts live in `prompts/` (read them before invoking an agent role). JSON schemas for validation in `schemas/`.

```
samples/*.pdf → tools/pdf_reader.py → Agent Classifier → Agent Extractor → output/extractions/
                                                                              ↓
                                                           Agent Analyzer → output/analyses/
                                                                              ↓
                                                           Agent Reporter → output/reports/
```

**Extraction strategies** (auto-detected by `pdf_reader.py`): pdfplumber for native text, Tesseract OCR for scans, PaddleOCR PP-StructureV3 for tables, MLX VLM for Apple Silicon GPU. Fallback chain: pdfplumber → PaddleOCR → MLX → Tesseract.

**Target extraction fields** per invoice line: `type_matiere`, `unite`, `prix_unitaire`, `quantite`, `prix_total`, `date_depart`, `date_arrivee`, `lieu_depart`, `lieu_arrivee`. Each field has a confidence score (0-1). Thresholds: 0.3 minimum, 0.6 document success, 0.8 reliable.

### Dashboard (`dashboard/`)

Streamlit app with 8 pages. Entry point: `dashboard/app.py`. Config: `dashboard/config.yaml`.

**Data flow**: `app.py` initializes SQLite engine → stores in `st.session_state` → pages import engine from session state → analytics modules query DB with entity resolution applied at runtime.

**Key layers**:
- `data/models.py` — 9 SQLAlchemy models: `Document`, `LigneFacture`, `Fournisseur`, `Anomalie`, `EntityMapping`, `MergeAuditLog`, `UploadLog`
- `data/db.py` — Engine/session management; resolves relative SQLite paths from dashboard dir
- `data/entity_resolution.py` — Non-destructive dedup: `resolve_column()` applies mappings to DataFrames at query time (raw data stays intact)
- `data/entity_enrichment.py` — Auto-resolution via rapidfuzz fuzzy matching with supplier/material normalization (strips legal suffixes like SA/SARL/GmbH, operational details)
- `data/ingestion.py` — Loads extraction JSONs into DB
- `data/upload_pipeline.py` — PDF upload with SHA-256 duplicate detection
- `analytics/` — Query modules per page (achats, anomalies, logistique, qualite, tendances)
- `components/` — Reusable Streamlit UI widgets (filters, charts, data_table, kpi_card)
- `pages/` — 8 Streamlit pages (tableau_de_bord, achats, logistique, anomalies, tendances, qualite, admin, entites)

### Entity Resolution

Non-destructive: raw DB values unchanged, `EntityMapping` table stores `raw_value → canonical_value` with status (approved/pending_review/rejected). `MergeAuditLog` tracks all operations for undo. Auto-resolution uses rapidfuzz (thresholds: 0.90 auto-merge, 0.50 review). Analytics modules call `resolve_column()` to apply mappings before rendering.

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
