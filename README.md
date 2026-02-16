# Swarm PDF Extract

Multi-agent PDF extraction system with a Streamlit analytics dashboard. Built to evaluate automated data extraction from heterogeneous PDF documents (invoices, delivery notes, quotes) for a logistics/chemical industry client.

## Architecture

```
swarm-pdf-extract/
├── prompts/            # Agent prompts (classifier, extractor, analyzer, reporter)
├── tools/              # PDF processing (pdfplumber, OCR, table extraction)
├── schemas/            # JSON validation schemas
├── dashboard/          # Streamlit analytics dashboard
│   ├── analytics/      #   Purchasing, logistics, trends, quality modules
│   ├── components/     #   Shared UI components (filters, charts)
│   ├── data/           #   Models, ingestion, entity resolution, upload pipeline
│   ├── pages/          #   8 dashboard pages
│   └── tests/          #   174 tests
├── samples/            # Input PDFs (not tracked)
└── output/             # Extraction results (not tracked)
```

### Extraction Pipeline

Four specialized agents coordinated by an orchestrator:

1. **Classifier** — Detects document type, PDF format, language, complexity
2. **Extractor** — Structured data extraction (text, tables, OCR, LLM strategies)
3. **Analyzer** — Quality scoring, pattern detection, field coverage analysis
4. **Reporter** — Executive summary with feasibility, method, tools, budget recommendations

### Analytics Dashboard

Streamlit dashboard with 8 pages for exploring extracted data:

| Page | Description |
|------|-------------|
| Tableau de bord | KPIs, document/line counts, entity resolution stats |
| Achats | Supplier rankings, material pricing, cost optimization |
| Logistique | Route analysis, OD matrix, delivery times, consolidation |
| Anomalies | Data quality issues and validation rules |
| Tendances | Price trends by material over time |
| Qualite | Extraction confidence scores and coverage |
| Admin | Data ingestion, PDF upload, DB stats, maintenance |
| Entites | Entity resolution: mappings, manual merge, audit log, review queue |

## Key Features

### Entity Resolution

Non-destructive entity deduplication — raw data stays intact, mappings applied at query time:

- **Manual merge**: Select 2+ entity variants, assign canonical name (exact or prefix match)
- **Auto-resolution**: Fuzzy matching (rapidfuzz) with configurable thresholds — high confidence auto-merges, medium confidence goes to review queue
- **Material normalization**: Strips operational details after " - " separator, removes leading quantities
- **Supplier normalization**: Case-folding, legal suffix removal (SA, SARL, SAS, GmbH, Ltd)
- **Full audit trail**: Every merge logged, revertible at any time
- **Backward compatible**: Zero mappings = identical behavior to pre-resolution code

### PDF Upload

- Drag-and-drop PDF upload with size validation
- SHA-256 content hashing for duplicate detection
- Upload history with status tracking (uploaded/processing/completed/failed)
- Path traversal protection

## Quick Start

### Prerequisites

- Python 3.11+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (for running extraction agents)

### Install & Run Dashboard

```bash
# Clone
git clone https://github.com/f-laplagne/swarm-pdf-extract.git
cd swarm-pdf-extract

# Install dependencies
pip install -r dashboard/requirements.txt

# Run dashboard
PYTHONPATH=. streamlit run dashboard/app.py
```

### Run Extraction Pipeline

```bash
# Install extraction dependencies
pip install -r requirements.txt

# Place PDFs in samples/
cp your-invoices/*.pdf samples/

# Launch Claude Code orchestrator
claude
# > Read CLAUDE.md and execute the full workflow on PDFs in samples/
```

### Run Tests

```bash
pip install -r dashboard/requirements.txt
python -m pytest dashboard/tests/ -v
# 174 passed, 1 skipped
```

## Target Schema (Invoices)

Each invoice line extracts:

| Field | Type | Description |
|-------|------|-------------|
| `type_matiere` | string | Material or part type |
| `unite` | string | Unit of measure (kg, m, piece, lot) |
| `prix_unitaire` | number | Unit price excl. tax |
| `quantite` | number | Quantity |
| `prix_total` | number | Line total excl. tax |
| `date_depart` | ISO 8601 | Departure / shipping date |
| `date_arrivee` | ISO 8601 | Arrival / delivery date |
| `lieu_depart` | string | Origin location |
| `lieu_arrivee` | string | Destination location |

## Configuration

Dashboard configuration in `dashboard/config.yaml`:

```yaml
upload:
  directory: "data/uploads"
  max_file_size_mb: 50

entity_resolution:
  auto_merge_threshold: 0.90    # >= auto-merge
  review_threshold: 0.50        # >= pending review
  fuzzy_min_score: 50
```

## Tech Stack

- **Extraction**: pdfplumber, pytesseract, pdf2image, OpenCV
- **Dashboard**: Streamlit, Plotly, Pandas
- **Database**: SQLAlchemy + SQLite
- **Entity resolution**: rapidfuzz, geopy
- **Testing**: pytest (174 tests)
