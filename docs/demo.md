# Demo — Correction Loop MVP (5 minutes)

## Setup

```bash
# Load sample data (first time only)
PYTHONPATH=. python scripts/load_demo_data.py

# Start the dashboard
bash start.sh
# or: PYTHONPATH=. streamlit run dashboard/app.py
```

Open http://localhost:8501

## Walkthrough

### 1. See the data quality problem (1 min)

- Go to **Tableau de bord** — note the low global confidence scores
- Go to **Qualite** — see fields colored red/orange for uncertain extractions

### 2. Navigate to the Correction Workflow (30 sec)

- Go to **Corrections** (left sidebar)
- Tab **"Documents à corriger"** — shows 2 documents needing attention
- Adjust the confidence threshold slider to see more/fewer flagged documents

### 3. Correct a low-confidence field (2 min)

- Click tab **"Corriger une ligne"**
- Select `FACTURE_DEMO_001.pdf`
- The right column shows confidence card — mostly red/orange
- Select **"Ligne 1 — sble fin (6 champs faibles)"**
- `type_matiere` shows `:red[conf: 35%]`
- If previous corrections exist: a suggestion appears automatically → `**Sable fin**`
- Type `Sable fin` in the field, click **Appliquer les corrections**
- Confidence resets to 100%, global document confidence rises

### 4. Propagate a correction across all documents (1 min)

- Expand **"Propagation en masse"** (below the correction form)
- Champ: `lieu_depart`
- Valeur originale: `Marseile` (the OCR typo)
- Valeur corrigée: `Marseille`
- Click **Propager** — fixes the typo across all 2 affected lines at once

### 5. Verify in analytics (30 sec)

- Go to **Achats** — corrected material names appear correctly
- Go to **Corrections** → tab **"Historique"** — full audit trail shows all corrections

## What This Proves

- **Accuracy**: Human operators can find and fix low-confidence extractions efficiently
- **Trust**: Corrected fields are marked 100% confident — they appear correctly in all analytics
- **Speed**: One bulk propagation fixes a recurring error across all documents
- **Auditability**: Every correction is logged with who corrected what and when
