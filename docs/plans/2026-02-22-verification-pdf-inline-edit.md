# Verification PDF — Inline Edit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow human operators to edit extraction fields with confidence < 50% directly in the verification PDF split-view, with immediate persistence to the database via the existing correction infrastructure.

**Architecture:** Extend the existing mini HTTP server (port 8504) in `11_verification_pdf.py` with a `POST /corrections` endpoint. At render time, enrich the extraction panel HTML with `data-ligne-id` attributes by querying the DB. JS in the iframe handles click-to-edit, sends the POST, and updates the DOM optimistically on success. All persistence goes through the existing `appliquer_correction()` function which updates `LigneFacture` directly and logs to `CorrectionLog`.

**Tech Stack:** Python `http.server`, SQLAlchemy (new session per request), `dashboard.analytics.corrections.appliquer_correction`, PDF.js (unchanged), vanilla JS `fetch`.

---

## Context for the implementer

### Key files to understand before starting

- `dashboard/pages/11_verification_pdf.py` — the ONLY file you will modify. Read it fully before starting. It is a single `st.components.v1.html()` SPA with no Streamlit reruns.
- `dashboard/analytics/corrections.py` — `appliquer_correction(session, ligne_id, {champ: new_val}, corrige_par)` updates `LigneFacture.{champ}`, sets `conf_{champ}=1.0`, logs to `CorrectionLog`, recalculates `confiance_globale`. This is what you call in the HTTP handler. Do NOT reimplement it.
- `dashboard/adapters/outbound/sqlalchemy_models.py` — `LigneFacture` ORM model. Fields: `id`, `ligne_numero`, `document_id`, `type_matiere`, `unite`, `prix_unitaire`, `quantite`, `prix_total`, `date_depart`, `date_arrivee`, `lieu_depart`, `lieu_arrivee`, and their `conf_*` counterparts.
- `dashboard/data/db.py` — `get_engine()` creates the SQLAlchemy engine; `get_session(engine)` returns a session.

### How page 11 works today

1. At module load, Python reads all JSON files from `output/extractions/` and renders them into HTML strings via `build_extraction_panel()`.
2. All HTML strings are embedded as a JSON blob (`ALL_DOCS`) in the single `st.components.v1.html()` call.
3. The JS selects a document → replaces innerHTML with the pre-rendered HTML. No Python reruns.
4. A daemon thread serves PDFs via HTTP on port 8504 using `_CORSHandler(SimpleHTTPRequestHandler)`.

### What you are adding

- A module-level `_DB_ENGINE` variable so the HTTP handler can access SQLAlchemy without Streamlit.
- A `get_ligne_ids(engine, fichier)` function that returns `{ligne_numero: ligne_id}` from the DB.
- `_handle_correction_post(body, engine)` — pure function containing the POST logic (testable without HTTP).
- `do_POST()` on `_CORSHandler` that calls `_handle_correction_post()`.
- Updated `build_extraction_panel()` signature: add `ligne_ids: dict[int, int] | None = None`. Cells where `conf < 0.5` AND `ligne_id` available get `data-*` attributes and a hidden `<input>`.
- CSS for editable cells (dashed orange border, pencil icon on hover).
- JS event delegation for click-to-edit + `fetch` POST + DOM update.

### Running tests

```bash
# Unit/integration tests for the new functions (no Streamlit needed)
PYTHONPATH=. pytest dashboard/tests/integration/test_verification_inline_edit.py -v

# Full dashboard test suite (regression check)
PYTHONPATH=. pytest dashboard/tests/ -v
```

### Confidence threshold

The threshold is **0.5** (fixed, not configurable from this page). The existing `conf_tier()` function already classifies `score < 0.5` as `"faible"`.

---

## Task 1: Create the test file and write tests for `get_ligne_ids()`

**Files:**
- Create: `dashboard/tests/integration/test_verification_inline_edit.py`

**Step 1: Write the failing tests**

```python
"""Integration tests for the new functions added to 11_verification_pdf.py."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Base, Document, Fournisseur, LigneFacture


@pytest.fixture
def engine():
    """In-memory SQLite engine with schema."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    s = Session(engine)
    yield s
    s.close()


@pytest.fixture
def doc_with_lines(session):
    """A document with 3 lines in the DB."""
    fournisseur = Fournisseur(nom="Test SA")
    session.add(fournisseur)
    session.flush()

    doc = Document(
        fichier="facture_test.pdf",
        type_document="facture",
        confiance_globale=0.45,
        fournisseur_id=fournisseur.id,
    )
    session.add(doc)
    session.flush()

    lignes = [
        LigneFacture(document_id=doc.id, ligne_numero=1, type_matiere="Acier",
                     conf_type_matiere=0.8),
        LigneFacture(document_id=doc.id, ligne_numero=2, type_matiere="Cuivre",
                     conf_type_matiere=0.3),
        LigneFacture(document_id=doc.id, ligne_numero=3, type_matiere="Alu",
                     conf_type_matiere=0.4),
    ]
    for l in lignes:
        session.add(l)
    session.commit()
    return doc, lignes


# ── get_ligne_ids ────────────────────────────────────────────────────────────

def test_get_ligne_ids_returns_mapping(engine, doc_with_lines):
    """get_ligne_ids returns {ligne_numero: ligne_id} for a known document."""
    from dashboard.pages._verification_helpers import get_ligne_ids  # will be extracted

    doc, lignes = doc_with_lines
    result = get_ligne_ids(engine, "facture_test.pdf")

    assert isinstance(result, dict)
    assert len(result) == 3
    for ligne in lignes:
        assert ligne.ligne_numero in result
        assert result[ligne.ligne_numero] == ligne.id


def test_get_ligne_ids_unknown_document_returns_empty(engine):
    """get_ligne_ids returns {} for a document not in the DB."""
    from dashboard.pages._verification_helpers import get_ligne_ids

    result = get_ligne_ids(engine, "inexistant.pdf")
    assert result == {}
```

**Step 2: Run tests to verify they fail (RED)**

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_verification_inline_edit.py::test_get_ligne_ids_returns_mapping -v
```

Expected: `ModuleNotFoundError: No module named 'dashboard.pages._verification_helpers'`

---

## Task 2: Create `_verification_helpers.py` and implement `get_ligne_ids()`

**Files:**
- Create: `dashboard/pages/_verification_helpers.py`

**Step 1: Write minimal implementation**

```python
"""Pure helper functions extracted from 11_verification_pdf.py for testability.

Interfaces amont : appelé par 11_verification_pdf.py au rendu et par _CORSHandler.do_POST
Interfaces aval  : SQLAlchemy Session (lecture LigneFacture/Document), appliquer_correction()
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Document, LigneFacture


def get_ligne_ids(engine, fichier: str) -> dict[int, int]:
    """Return {ligne_numero: ligne_id} for all active lines of a document.

    Args:
        engine: SQLAlchemy engine (thread-safe, shared).
        fichier: filename as stored in documents.fichier (basename only).

    Returns:
        Empty dict if document not found in DB or has no lines.
    """
    with Session(engine) as session:
        doc = session.query(Document).filter(Document.fichier == fichier).first()
        if doc is None:
            return {}
        lignes = (
            session.query(LigneFacture)
            .filter(
                LigneFacture.document_id == doc.id,
                LigneFacture.supprime != True,
            )
            .all()
        )
        return {ligne.ligne_numero: ligne.id for ligne in lignes}
```

**Step 2: Run tests to verify they pass (GREEN)**

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_verification_inline_edit.py::test_get_ligne_ids_returns_mapping dashboard/tests/integration/test_verification_inline_edit.py::test_get_ligne_ids_unknown_document_returns_empty -v
```

Expected: 2 passed.

**Step 3: Commit**

```bash
git add dashboard/pages/_verification_helpers.py dashboard/tests/integration/test_verification_inline_edit.py
git commit -m "feat(verification-pdf): add get_ligne_ids() helper with tests"
```

---

## Task 3: Write tests for `_handle_correction_post()`

**Files:**
- Modify: `dashboard/tests/integration/test_verification_inline_edit.py`

**Step 1: Add the failing tests**

Append to the existing test file:

```python
# ── _handle_correction_post ──────────────────────────────────────────────────

def test_handle_correction_post_valid(engine, doc_with_lines):
    """Valid body persists correction and returns {success: true, correction_id: N}."""
    from dashboard.pages._verification_helpers import handle_correction_post

    doc, lignes = doc_with_lines
    ligne_faible = lignes[1]  # ligne_numero=2, conf_type_matiere=0.3

    body = {
        "ligne_id": ligne_faible.id,
        "champ": "type_matiere",
        "valeur_originale": "Cuivre",
        "valeur_corrigee": "Cuivre rouge recyclé",
        "confiance_originale": 0.3,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 200
    assert response["success"] is True
    assert "correction_id" in response

    # Verify DB was actually updated
    with Session(engine) as s:
        ligne = s.get(LigneFacture, ligne_faible.id)
        assert ligne.type_matiere == "Cuivre rouge recyclé"
        assert ligne.conf_type_matiere == 1.0


def test_handle_correction_post_invalid_ligne(engine):
    """Unknown ligne_id returns 404 with error message."""
    from dashboard.pages._verification_helpers import handle_correction_post

    body = {
        "ligne_id": 99999,
        "champ": "type_matiere",
        "valeur_originale": "x",
        "valeur_corrigee": "y",
        "confiance_originale": 0.2,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 404
    assert response["success"] is False
    assert "error" in response


def test_handle_correction_post_invalid_champ(engine, doc_with_lines):
    """Unknown field name returns 400."""
    from dashboard.pages._verification_helpers import handle_correction_post

    doc, lignes = doc_with_lines
    body = {
        "ligne_id": lignes[0].id,
        "champ": "champ_inexistant",
        "valeur_originale": "x",
        "valeur_corrigee": "y",
        "confiance_originale": 0.2,
    }

    status_code, response = handle_correction_post(body, engine)

    assert status_code == 400
    assert response["success"] is False


def test_handle_correction_post_missing_field(engine):
    """Missing required field returns 400."""
    from dashboard.pages._verification_helpers import handle_correction_post

    status_code, response = handle_correction_post({}, engine)

    assert status_code == 400
    assert response["success"] is False
```

**Step 2: Run to verify RED**

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_verification_inline_edit.py -k "handle_correction_post" -v
```

Expected: `ImportError: cannot import name 'handle_correction_post'`

---

## Task 4: Implement `handle_correction_post()`

**Files:**
- Modify: `dashboard/pages/_verification_helpers.py`

**Step 1: Add implementation**

Append to `_verification_helpers.py`:

```python
from dashboard.analytics.corrections import EDITABLE_FIELDS, appliquer_correction


def handle_correction_post(body: dict, engine) -> tuple[int, dict]:
    """Process a correction POST request and persist it to the DB.

    Args:
        body: Parsed JSON dict with keys: ligne_id, champ, valeur_originale,
              valeur_corrigee, confiance_originale.
        engine: SQLAlchemy engine.

    Returns:
        (http_status_code, response_dict)
        Success: (200, {"success": True, "correction_id": N})
        Error:   (4xx, {"success": False, "error": "..."})
    """
    required = {"ligne_id", "champ", "valeur_corrigee"}
    missing = required - body.keys()
    if missing:
        return 400, {"success": False, "error": f"Champs manquants : {missing}"}

    champ = body.get("champ", "")
    if champ not in EDITABLE_FIELDS:
        return 400, {"success": False, "error": f"Champ inconnu : {champ!r}. Valides : {EDITABLE_FIELDS}"}

    ligne_id = body.get("ligne_id")
    valeur_corrigee = body.get("valeur_corrigee")

    try:
        with Session(engine) as session:
            logs = appliquer_correction(
                session,
                ligne_id,
                {champ: valeur_corrigee},
                corrige_par="operateur_verification",
                notes=None,
            )
            if not logs:
                return 404, {"success": False, "error": f"Ligne {ligne_id} introuvable"}
            return 200, {"success": True, "correction_id": logs[0].id}
    except ValueError as exc:
        return 404, {"success": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return 500, {"success": False, "error": f"Erreur interne : {exc}"}
```

**Step 2: Run tests GREEN**

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_verification_inline_edit.py -v
```

Expected: All 6 tests pass.

**Step 3: Commit**

```bash
git add dashboard/pages/_verification_helpers.py dashboard/tests/integration/test_verification_inline_edit.py
git commit -m "feat(verification-pdf): add handle_correction_post() with TDD"
```

---

## Task 5: Write tests for `build_extraction_panel()` editable cells

**Files:**
- Modify: `dashboard/tests/integration/test_verification_inline_edit.py`

**Step 1: Add tests**

Append to the test file:

```python
# ── build_extraction_panel editable cells ────────────────────────────────────

def _make_ext(lignes_data: list[dict]) -> dict:
    """Build a minimal extraction dict matching the JSON schema."""
    return {
        "metadonnees": {"numero_document": "TEST-001", "date_document": "2024-01-01"},
        "lignes": lignes_data,
        "confiance_globale": 0.5,
        "warnings": [],
        "champs_manquants": [],
    }


def _palette():
    """Minimal palette dict for build_extraction_panel."""
    return dict(
        card_bg="#fff", border="#ccc", border_light="#eee",
        txt_p="#000", txt_s="#666", txt_m="#999", txt_dim="#aaa",
        txt_num="#000", hdr_bg="#f5f5f5", row_even="#fff", row_odd="#f9f9f9",
        alert_bg="#fff", alert_border="#f00", notes_bg="#f5f5f5", notes_border="#ccc",
    )


def _conf_colors():
    return {
        "absent":  ("#ff4d4d", "#2a1010"),
        "faible":  ("#ff8c42", "#2a1a0a"),
        "moyen":   ("#f0c040", "#2a220a"),
        "bon":     ("#52c77f", "#0a2018"),
        "parfait": ("#34d399", "#061a12"),
    }


def test_editable_cell_rendered_when_conf_below_threshold(engine, doc_with_lines):
    """Cells with conf < 0.5 get class cell-editable and data-ligne-id attribute."""
    from dashboard.pages.verification_pdf_panel import build_extraction_panel

    doc, lignes = doc_with_lines
    # ligne_numero=2 has conf_type_matiere=0.3 → should be editable
    ligne_faible = lignes[1]

    ext = _make_ext([
        {"ligne_numero": 2, "type_matiere": "Cuivre",
         "confiance": {"type_matiere": 0.3, "unite": 0.9}},
    ])

    ligne_ids = {2: ligne_faible.id}
    html = build_extraction_panel(ext, _palette(), _conf_colors(), ligne_ids=ligne_ids)

    assert f'data-ligne-id="{ligne_faible.id}"' in html
    assert 'data-champ="type_matiere"' in html
    assert 'cell-editable' in html


def test_no_editable_cell_when_conf_above_threshold(engine, doc_with_lines):
    """Cells with conf >= 0.5 are NOT editable even if ligne_id is provided."""
    from dashboard.pages.verification_pdf_panel import build_extraction_panel

    doc, lignes = doc_with_lines
    ligne = lignes[0]  # conf_type_matiere=0.8

    ext = _make_ext([
        {"ligne_numero": 1, "type_matiere": "Acier",
         "confiance": {"type_matiere": 0.8}},
    ])

    ligne_ids = {1: ligne.id}
    html = build_extraction_panel(ext, _palette(), _conf_colors(), ligne_ids=ligne_ids)

    # High-confidence cell should NOT have editable class
    assert 'cell-editable' not in html or f'data-champ="type_matiere"' not in html


def test_no_editable_cell_when_no_ligne_id(engine):
    """Cells with conf < 0.5 but no ligne_id mapping are read-only (graceful fallback)."""
    from dashboard.pages.verification_pdf_panel import build_extraction_panel

    ext = _make_ext([
        {"ligne_numero": 1, "type_matiere": "Cuivre",
         "confiance": {"type_matiere": 0.2}},
    ])

    html = build_extraction_panel(ext, _palette(), _conf_colors(), ligne_ids={})

    assert 'cell-editable' not in html
```

**Step 2: Run RED**

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_verification_inline_edit.py -k "editable_cell" -v
```

Expected: `ModuleNotFoundError: No module named 'dashboard.pages.verification_pdf_panel'`

---

## Task 6: Extract `build_extraction_panel()` into `verification_pdf_panel.py`

The function currently lives inside `11_verification_pdf.py`. Extract it so it can be imported by tests (Streamlit pages can't be imported cleanly).

**Files:**
- Create: `dashboard/pages/verification_pdf_panel.py`
- Modify: `dashboard/pages/11_verification_pdf.py`

**Step 1: Create `verification_pdf_panel.py`**

Copy `build_extraction_panel`, `conf_tier`, `conf_badge`, `val_cell` from `11_verification_pdf.py` into the new file, then add the `ligne_ids` parameter.

```python
"""Pure rendering functions for the verification PDF panel.

Extracted from 11_verification_pdf.py for testability.
No Streamlit or HTTP imports allowed here.
"""

from __future__ import annotations

# ── Confidence helpers ────────────────────────────────────────────────────────

def conf_tier(score) -> tuple[str, str]:
    if score is None or score == 0: return "absent",  "0%"
    if score < 0.5:                  return "faible",  f"{score:.0%}"
    if score < 0.7:                  return "moyen",   f"{score:.0%}"
    if score < 0.9:                  return "bon",     f"{score:.0%}"
    return                                  "parfait", f"{score:.0%}"


def conf_badge(score, cc: dict) -> str:
    tier, pct = conf_tier(score)
    fg, bg = cc[tier]
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {fg}55;'
        f'font-family:JetBrains Mono,monospace;font-size:9px;font-weight:600;'
        f'padding:1px 7px;border-radius:3px;white-space:nowrap">⬤ {pct}</span>'
    )


def val_cell(val, P: dict) -> str:
    if val is None:
        return f'<span style="color:{P["txt_dim"]};font-style:italic">—</span>'
    if isinstance(val, float):
        return (f'<span style="font-family:JetBrains Mono,monospace;'
                f'color:{P["txt_num"]}">{val:,.2f}</span>')
    return str(val)


# ── Main panel builder ────────────────────────────────────────────────────────

CONF_SEUIL_EDITABLE = 0.5  # Fields below this threshold are editable
FLOAT_FIELDS = {"prix_unitaire", "quantite", "prix_total"}

CONF_FIELDS_MAP = [
    ("type_matiere", "Matière"), ("unite", "Unité"), ("quantite", "Qté"),
    ("prix_unitaire", "PU"), ("prix_total", "Total"), ("date_depart", "D.dép"),
    ("date_arrivee", "D.arr"), ("lieu_depart", "Départ"), ("lieu_arrivee", "Arrivée"),
]


def build_extraction_panel(
    ext: dict | None,
    P: dict,
    cc: dict,
    ligne_ids: dict[int, int] | None = None,
) -> str:
    """Build the HTML for the extraction data panel.

    Args:
        ext: Parsed extraction JSON dict, or None if extraction not found.
        P: Color palette dict.
        cc: Confidence colors dict.
        ligne_ids: Optional {ligne_numero: db_ligne_id}. When provided, cells
                   with conf < CONF_SEUIL_EDITABLE get editable attributes.
                   If None or empty, all cells are read-only.

    Returns:
        HTML string for the right panel.
    """
    if ligne_ids is None:
        ligne_ids = {}

    if not ext:
        return (f"<p style='color:{P['txt_dim']};padding:40px;"
                f"font-family:Manrope,sans-serif'>Extraction introuvable.</p>")

    meta   = ext.get("metadonnees", {})
    fourn  = meta.get("fournisseur", {}) or {}
    client = meta.get("client", {}) or {}
    refs   = meta.get("references", {}) or {}
    lignes = ext.get("lignes", [])
    warns  = ext.get("warnings", [])
    champs = ext.get("champs_manquants", [])
    conf_g = ext.get("confiance_globale", 0)

    tier_g, pct_g = conf_tier(conf_g)
    fg_g, bg_g    = cc[tier_g]

    strat_labels = {
        "pdfplumber_tables":       "PDF natif — tableaux",
        "auto_pdfplumber":         "PDF natif",
        "ocr_tesseract":           "OCR Tesseract",
        "auto_fallback_paddleocr": "OCR PaddleOCR",
    }

    def mrow(label, value):
        if not value: return ""
        return (
            f'<tr>'
            f'<td style="font-family:Manrope,sans-serif;font-size:10px;font-weight:600;'
            f'letter-spacing:.07em;text-transform:uppercase;color:{P["txt_s"]};'
            f'padding:5px 14px 5px 0;white-space:nowrap;vertical-align:top">{label}</td>'
            f'<td style="font-family:Manrope,sans-serif;font-size:12px;color:{P["txt_p"]};'
            f'padding:5px 0;line-height:1.5">{value}</td>'
            f'</tr>'
        )

    meta_card = f"""
<div style="background:{P['card_bg']};border:1px solid {P['border']};border-radius:6px;
            padding:16px 20px;margin-bottom:14px">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
    <div>
      <div style="font-family:'DM Serif Display',serif;font-size:22px;
                  color:{P['txt_p']};letter-spacing:.01em">
        {meta.get('numero_document','—')}
      </div>
      <div style="font-family:Manrope,sans-serif;font-size:10px;color:{P['txt_s']};
                  letter-spacing:.1em;text-transform:uppercase;margin-top:2px">
        {meta.get('date_document','—')}
        &nbsp;·&nbsp; {strat_labels.get(ext.get('strategie_utilisee',''), ext.get('strategie_utilisee',''))}
      </div>
    </div>
    <div style="background:{bg_g};border:1px solid {fg_g}55;border-radius:5px;
                padding:8px 14px;text-align:center;flex-shrink:0;margin-left:16px">
      <div style="font-family:'JetBrains Mono',monospace;font-size:22px;
                  font-weight:700;color:{fg_g};line-height:1">{pct_g}</div>
      <div style="font-family:Manrope,sans-serif;font-size:8px;color:{fg_g};
                  letter-spacing:.1em;text-transform:uppercase;margin-top:3px;opacity:.7">confiance</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 32px">
    <table style="border-collapse:collapse">
      {mrow("Fournisseur", fourn.get("nom"))}
      {mrow("TVA fourn.", fourn.get("tva_intra"))}
      {mrow("Client", client.get("nom"))}
      {mrow("Commande", refs.get("commande"))}
    </table>
    <table style="border-collapse:collapse">
      {mrow("HT",  f"{meta.get('montant_ht'):,.2f} {meta.get('devise','EUR')}" if meta.get('montant_ht') else None)}
      {mrow("TTC", f"{meta.get('montant_ttc'):,.2f} {meta.get('devise','EUR')}" if meta.get('montant_ttc') else None)}
      {mrow("Paiement", meta.get("conditions_paiement"))}
      {mrow("Champs ∅", ", ".join(champs) if champs else None)}
    </table>
  </div>
</div>"""

    col_defs = [
        ("#","36px","center"), ("Matière / Pièce","auto","left"),
        ("Unité","52px","center"), ("Quantité","76px","right"),
        ("Prix unit.","80px","right"), ("Total €","80px","right"),
        ("Date dép.","88px","center"), ("Date arr.","88px","center"),
        ("Départ","110px","left"), ("Arrivée","110px","left"),
    ]

    th = (f"font-family:Manrope,sans-serif;font-size:9px;font-weight:700;"
          f"letter-spacing:.1em;text-transform:uppercase;color:{P['txt_m']};"
          f"padding:8px 10px;border-bottom:2px solid {P['border']};white-space:nowrap;")
    headers = "".join(
        f'<th style="{th}text-align:{a};width:{w}">{n}</th>'
        for n, w, a in col_defs
    )

    # Map: JSON field name → column index in the table (for editable cells)
    # Columns: 0=#, 1=type_matiere, 2=unite, 3=quantite, 4=prix_unitaire, 5=prix_total,
    #          6=date_depart, 7=date_arrivee, 8=lieu_depart, 9=lieu_arrivee
    FIELD_TO_COL = {
        "type_matiere": 1, "unite": 2, "quantite": 3,
        "prix_unitaire": 4, "prix_total": 5,
        "date_depart": 6, "date_arrivee": 7,
        "lieu_depart": 8, "lieu_arrivee": 9,
    }

    rows = ""
    for i, ligne in enumerate(lignes):
        conf       = ligne.get("confiance", {})
        bg_r       = P["row_even"] if i % 2 == 0 else P["row_odd"]
        pu, qt, pt = ligne.get("prix_unitaire"), ligne.get("quantite"), ligne.get("prix_total")
        total_c    = "#ff6b6b" if (pu and qt and pt and abs(round(pu*qt,2)-pt) > 0.02) else P["txt_p"]
        td         = (f'style="padding:7px 10px;border-bottom:1px solid {P["border_light"]};'
                      f'vertical-align:middle;background:{bg_r};')

        ligne_num = ligne.get("ligne_numero")
        db_id     = ligne_ids.get(ligne_num)  # None if not in DB

        def _cell(field: str, value, align: str, extra_style: str = "") -> str:
            """Render a data cell, editable if conf < threshold and db_id available."""
            score = conf.get(field)
            is_editable = (
                db_id is not None
                and score is not None
                and score < CONF_SEUIL_EDITABLE
            )
            display_val = ""
            if value is None:
                display_val = f'<span style="color:{P["txt_dim"]};font-style:italic">—</span>'
            elif isinstance(value, float):
                display_val = f'{value:,.4f}' if field in FLOAT_FIELDS else f'{value:,.2f}'
            else:
                display_val = str(value)

            if not is_editable:
                return (f'<td {td}text-align:{align};{extra_style}">'
                        f'{display_val}</td>')

            # Editable cell: span (display) + input (hidden)
            input_type = "number" if field in FLOAT_FIELDS else "text"
            input_step = ' step="0.0001"' if field in FLOAT_FIELDS else ""
            raw_val    = str(value) if value is not None else ""
            orig_escaped = raw_val.replace('"', '&quot;')
            return (
                f'<td class="cell-editable" {td}text-align:{align};{extra_style}"'
                f' data-ligne-id="{db_id}"'
                f' data-champ="{field}"'
                f' data-original="{orig_escaped}"'
                f' data-conf="{score}">'
                f'<span class="cell-display">{display_val}</span>'
                f'<input class="cell-input" type="{input_type}"{input_step}'
                f' value="{orig_escaped}" style="display:none">'
                f'</td>'
            )

        rows += f"""
<tr>
  <td {td}text-align:center;color:{P['txt_dim']};font-family:'JetBrains Mono',monospace;font-size:11px">{ligne_num or ''}</td>
  {_cell("type_matiere", ligne.get("type_matiere"), "left", f"color:{P['txt_p']};font-family:Manrope,sans-serif;font-size:12px")}
  {_cell("unite",        ligne.get("unite"),        "center", f"font-family:'JetBrains Mono',monospace;font-size:11px;color:{P['txt_s']}")}
  {_cell("quantite",     ligne.get("quantite"),     "right",  f"font-family:'JetBrains Mono',monospace;font-size:11px;color:{P['txt_p']}")}
  {_cell("prix_unitaire",ligne.get("prix_unitaire"),"right",  f"font-family:'JetBrains Mono',monospace;font-size:11px;color:{P['txt_p']}")}
  {_cell("prix_total",   ligne.get("prix_total"),   "right",  f"font-family:'JetBrains Mono',monospace;font-size:11px;color:{total_c}")}
  {_cell("date_depart",  ligne.get("date_depart"),  "center", f"font-family:'JetBrains Mono',monospace;font-size:10px;color:{P['txt_dim']}")}
  {_cell("date_arrivee", ligne.get("date_arrivee"), "center", f"font-family:'JetBrains Mono',monospace;font-size:10px;color:{P['txt_dim']}")}
  {_cell("lieu_depart",  ligne.get("lieu_depart"),  "left",   f"color:{P['txt_s']};font-family:Manrope,sans-serif;font-size:11px")}
  {_cell("lieu_arrivee", ligne.get("lieu_arrivee"), "left",   f"color:{P['txt_s']};font-family:Manrope,sans-serif;font-size:11px")}
</tr>
<tr>
  <td colspan="10" style="padding:3px 10px 9px;background:{bg_r};border-bottom:1px solid {P['border_light']}">
    <div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">
      <span style="font-family:Manrope,sans-serif;font-size:9px;color:{P['txt_m']};
                   font-weight:600;letter-spacing:.07em;text-transform:uppercase;
                   margin-right:3px">conf.</span>
      {"".join(
          f'<span class="conf-badge-container" style="display:inline-flex;align-items:center;gap:3px"'
          f' data-ligne-id="{db_id or ""}" data-champ="{key}">'
          f'<span style="font-family:Manrope,sans-serif;font-size:9px;color:{P["txt_m"]}">{label}</span>'
          f'{conf_badge(conf.get(key), cc)}</span>'
          for key, label in CONF_FIELDS_MAP
      )}
    </div>
  </td>
</tr>"""

    table = (
        f'<div style="overflow-x:auto;border:1px solid {P["border"]};'
        f'border-radius:6px;margin-bottom:14px">'
        f'<table style="border-collapse:collapse;width:100%;min-width:880px">'
        f'<thead><tr style="background:{P["hdr_bg"]}">{headers}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>'
    )

    alerts_html = ""
    if warns or champs:
        champ_li = "".join(
            f'<li style="font-family:JetBrains Mono,monospace;font-size:10px;'
            f'color:#ff4d4d;margin-bottom:3px">{c}</li>' for c in champs)
        warn_li = "".join(
            f'<li style="font-family:Manrope,sans-serif;font-size:11px;color:#ff8c42;'
            f'margin-bottom:5px;line-height:1.5">{w}</li>' for w in warns)
        ul_champs = f'<ul style="margin:0;padding-left:14px;margin-bottom:8px">{champ_li}</ul>' if champs else ""
        ul_warns  = f'<ul style="margin:0;padding-left:14px">{warn_li}</ul>' if warns else ""
        alerts_html = (
            f'<div style="border:1px solid {P["alert_border"]};border-left:3px solid {P["alert_border"]};'
            f'border-radius:4px;padding:12px 16px;margin-bottom:12px;background:{P["alert_bg"]}">'
            f'<div style="font-family:Manrope,sans-serif;font-size:9px;font-weight:700;'
            f'color:{P["alert_border"]};letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px">'
            f'⚠ Alertes & Champs manquants</div>'
            f'{ul_champs}{ul_warns}</div>'
        )

    notes = ext.get("extraction_notes", "")
    notes_html = ""
    if notes:
        notes_html = (
            f'<div style="border:1px solid {P["notes_border"]};border-radius:4px;'
            f'padding:12px 16px;background:{P["notes_bg"]}">'
            f'<div style="font-family:Manrope,sans-serif;font-size:9px;font-weight:700;'
            f'color:{P["txt_m"]};letter-spacing:.12em;text-transform:uppercase;margin-bottom:7px">'
            f'Notes d\'extraction</div>'
            f'<p style="font-family:Manrope,sans-serif;font-size:11px;color:{P["txt_s"]};'
            f'line-height:1.7;margin:0">{notes}</p>'
            f'</div>'
        )

    return meta_card + table + alerts_html + notes_html
```

**Step 2: Update imports in `11_verification_pdf.py`**

At the top of `11_verification_pdf.py`, replace the local definitions of `conf_tier`, `conf_badge`, `val_cell`, and `build_extraction_panel` with:

```python
from dashboard.pages.verification_pdf_panel import (
    build_extraction_panel, conf_tier, conf_badge,
)
```

Remove the old function definitions from `11_verification_pdf.py`.

**Step 3: Run tests GREEN**

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_verification_inline_edit.py -k "editable_cell" -v
```

Expected: 3 passed.

**Step 4: Run full test suite (regression)**

```bash
PYTHONPATH=. pytest dashboard/tests/ -v
pytest tests/ -v
```

Expected: no regressions.

**Step 5: Commit**

```bash
git add dashboard/pages/verification_pdf_panel.py dashboard/pages/11_verification_pdf.py dashboard/tests/integration/test_verification_inline_edit.py
git commit -m "refactor(verification-pdf): extract build_extraction_panel with editable cell support"
```

---

## Task 7: Add DB init and `do_POST` to `11_verification_pdf.py`

**Files:**
- Modify: `dashboard/pages/11_verification_pdf.py`

**Step 1: Add DB engine init**

After the existing `SAMPLES_DIR` / `EXTRACTIONS_DIR` / `PDF_SERVER_PORT` block and before the `_CORSHandler` class definition, add:

```python
# ── DB engine (module-level, thread-safe) ────────────────────────────────────
# Needed by _CORSHandler.do_POST() to persist corrections.
_DB_ENGINE = None

def _get_or_init_engine():
    """Return existing engine from session_state, or create one."""
    global _DB_ENGINE
    if _DB_ENGINE is not None:
        return _DB_ENGINE
    # Try to get from Streamlit session_state (set by app.py composition root)
    engine = st.session_state.get("engine")
    if engine is None:
        from dashboard.data.db import get_engine, init_db
        engine = get_engine()
        init_db(engine)
    _DB_ENGINE = engine
    return _DB_ENGINE
```

**Step 2: Extend `_CORSHandler` with `do_POST`**

Replace the existing `_CORSHandler` class definition with:

```python
class _CORSHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, *_): pass

    def do_OPTIONS(self):
        """Handle CORS preflight requests from the iframe fetch."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        """Handle POST /corrections from the iframe JS."""
        import json as _json
        from dashboard.pages._verification_helpers import handle_correction_post

        if self.path != "/corrections":
            self.send_response(404)
            self.end_headers()
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            raw    = self.rfile.read(length)
            body   = _json.loads(raw)
        except Exception:
            status, resp = 400, {"success": False, "error": "JSON invalide"}
        else:
            engine = _get_or_init_engine()
            status, resp = handle_correction_post(body, engine)

        payload = _json.dumps(resp).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)
```

**Step 3: Initialize the engine before the server starts**

Immediately after the `_get_or_init_engine` function definition, call it once so the engine is warm before the HTTP server starts:

```python
# Initialize engine eagerly so do_POST is ready immediately
_get_or_init_engine()
```

**Step 4: Manual smoke test** — start the dashboard, open page 11, and confirm no import errors in the terminal.

```bash
PYTHONPATH=. streamlit run dashboard/app.py
```

**Step 5: Commit**

```bash
git add dashboard/pages/11_verification_pdf.py
git commit -m "feat(verification-pdf): add POST /corrections endpoint to mini HTTP server"
```

---

## Task 8: Wire `ligne_ids` into the `all_docs` construction loop

**Files:**
- Modify: `dashboard/pages/11_verification_pdf.py`

**Step 1: Update the `all_docs` construction loop**

Find the existing loop:

```python
all_docs: dict = {}
for pdf_path in PDF_FILES:
    ext_path = find_extraction(pdf_path)
    ext = json.loads(ext_path.read_text(encoding="utf-8")) if ext_path else None
    ...
    all_docs[pdf_path.name] = {
        ...
        "panel": build_extraction_panel(ext, P, cc),
        ...
    }
```

Replace with:

```python
from dashboard.pages._verification_helpers import get_ligne_ids

all_docs: dict = {}
_engine_for_render = _get_or_init_engine()

for pdf_path in PDF_FILES:
    ext_path = find_extraction(pdf_path)
    ext      = json.loads(ext_path.read_text(encoding="utf-8")) if ext_path else None

    # Enrich with DB ligne IDs so editable cells can be rendered
    _ligne_ids = get_ligne_ids(_engine_for_render, pdf_path.name) if ext else {}

    nb_l  = len(ext.get("lignes", [])) if ext else 0
    conf  = ext.get("confiance_globale", 0) if ext else 0
    tier, pct = conf_tier(conf)
    fg, _ = cc[tier]
    all_docs[pdf_path.name] = {
        "url":        f"http://localhost:{PDF_SERVER_PORT}/{quote(pdf_path.name)}",
        "panel":      build_extraction_panel(ext, P, cc, ligne_ids=_ligne_ids),
        "nb_lignes":  nb_l,
        "nb_champs":  len(ext.get("champs_manquants", [])) if ext else 0,
        "nb_warns":   len(ext.get("warnings", [])) if ext else 0,
        "conf_pct":   pct,
        "conf_color": fg,
        "dot_color":  "#52c77f" if ext else "#ff4d4d",
        "ext_label":  "extraction OK" if ext else "extraction introuvable",
    }
```

**Step 2: Run full regression**

```bash
PYTHONPATH=. pytest dashboard/tests/ -v
```

Expected: all existing tests pass.

**Step 3: Commit**

```bash
git add dashboard/pages/11_verification_pdf.py
git commit -m "feat(verification-pdf): pass ligne_ids to panel builder for editable cells"
```

---

## Task 9: Add CSS for editable cells to the HTML template

**Files:**
- Modify: `dashboard/pages/11_verification_pdf.py`

**Step 1: Add CSS rules**

In the `<style>` block inside the `html = f"""..."""` string, add the following rules after the existing `.status` / `.si` / `.dot` rules:

```css
/* ── Editable cells ─────────────────────────────────────── */
.cell-editable {{
  position: relative;
  cursor: pointer;
  border-bottom: 2px dashed #ff8c42 !important;
}}
.cell-editable::after {{
  content: '✏';
  font-size: 9px;
  opacity: 0;
  position: absolute;
  top: 4px; right: 4px;
  transition: opacity .15s;
  pointer-events: none;
}}
.cell-editable:hover::after {{ opacity: .6; }}
.cell-editable.editing {{
  border-bottom: 2px solid #ff8c42 !important;
  background: rgba(255,140,66,.07) !important;
}}
.cell-editable.saved {{
  border-bottom: 2px solid #52c77f !important;
}}
.cell-editable.error {{
  border-bottom: 2px solid #ff4d4d !important;
}}
.cell-input {{
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1px solid #ff8c42;
  color: inherit;
  font-family: inherit;
  font-size: inherit;
  outline: none;
  padding: 0;
}}
.save-spinner {{
  font-size: 10px;
  color: #ff8c42;
  margin-left: 4px;
}}
```

**Step 2: Manual visual check** — open page 11, pick a document with low-confidence fields, verify dashed orange borders appear on the expected cells.

**Step 3: Commit**

```bash
git add dashboard/pages/11_verification_pdf.py
git commit -m "feat(verification-pdf): CSS for editable cells (dashed orange border)"
```

---

## Task 10: Add JS for click-to-edit and fetch POST

**Files:**
- Modify: `dashboard/pages/11_verification_pdf.py`

**Step 1: Add JS**

In the `<script>` block, after the `// Drag-to-resize` section and before the closing `</script>`, add:

```javascript
// ── Inline cell editing (conf < 50%) ─────────────────────────────────────────
const CORRECTION_URL = 'http://localhost:{PDF_SERVER_PORT}/corrections';

function showError(cell, msg) {{
  cell.classList.remove('editing');
  cell.classList.add('error');
  const tt = document.createElement('div');
  tt.style.cssText = 'position:absolute;bottom:100%;left:0;background:#ff4d4d;color:#fff;'
    + 'font-family:Manrope,sans-serif;font-size:10px;padding:3px 8px;border-radius:3px;'
    + 'white-space:nowrap;z-index:100;pointer-events:none';
  tt.textContent = '⚠ ' + msg;
  cell.style.position = 'relative';
  cell.appendChild(tt);
  setTimeout(() => {{ tt.remove(); cell.classList.remove('error'); }}, 3500);
}}

function updateConfBadge(ligneId, champ) {{
  // Replace the confidence badge for this field with a "✓ corrigé" badge
  document.querySelectorAll('.conf-badge-container').forEach(container => {{
    if (container.dataset.ligneId == ligneId && container.dataset.champ === champ) {{
      const badge = container.querySelector('span:last-child');
      if (badge) {{
        badge.style.cssText = 'background:#0a2018;color:#52c77f;border:1px solid #52c77f55;'
          + 'font-family:JetBrains Mono,monospace;font-size:9px;font-weight:600;'
          + 'padding:1px 7px;border-radius:3px;white-space:nowrap';
        badge.textContent = '✓ corrigé';
      }}
    }}
  }});
}}

async function saveCorrection(cell, ligneId, champ, valeurOriginale, confOriginale, newValue) {{
  const display = cell.querySelector('.cell-display');
  const input   = cell.querySelector('.cell-input');

  // Show spinner
  const spinner = document.createElement('span');
  spinner.className = 'save-spinner';
  spinner.textContent = '⏳';
  cell.appendChild(spinner);
  input.disabled = true;

  try {{
    const resp = await fetch(CORRECTION_URL, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        ligne_id: parseInt(ligneId),
        champ: champ,
        valeur_originale: valeurOriginale,
        valeur_corrigee: newValue,
        confiance_originale: parseFloat(confOriginale) || null,
      }}),
    }});
    const data = await resp.json();

    if (data.success) {{
      // Update DOM: show new value, remove editable class
      display.textContent = newValue || '—';
      display.style.display = '';
      input.style.display = 'none';
      cell.classList.remove('editing', 'cell-editable');
      cell.classList.add('saved');
      cell.dataset.original = newValue;
      updateConfBadge(ligneId, champ);
    }} else {{
      // Revert
      input.value = valeurOriginale;
      input.disabled = false;
      display.style.display = '';
      input.style.display = 'none';
      cell.classList.remove('editing');
      showError(cell, data.error || 'Erreur inconnue');
    }}
  }} catch (err) {{
    input.value = valeurOriginale;
    input.disabled = false;
    display.style.display = '';
    input.style.display = 'none';
    cell.classList.remove('editing');
    showError(cell, 'Réseau : ' + err.message);
  }} finally {{
    spinner.remove();
  }}
}}

// Event delegation: handle clicks on editable cells
document.getElementById('ext-scroll').addEventListener('click', function(e) {{
  const cell = e.target.closest('.cell-editable');
  if (!cell || cell.classList.contains('saved')) return;

  const display  = cell.querySelector('.cell-display');
  const input    = cell.querySelector('.cell-input');
  if (!display || !input) return;

  // Switch to edit mode
  display.style.display = 'none';
  input.style.display   = '';
  input.value = cell.dataset.original || '';
  cell.classList.add('editing');
  input.focus();
  input.select();

  function commitEdit() {{
    const newVal   = input.value.trim();
    const origVal  = cell.dataset.original || '';
    display.style.display = '';
    input.style.display   = 'none';
    cell.classList.remove('editing');

    if (newVal === origVal || newVal === '') return; // no change

    saveCorrection(
      cell,
      cell.dataset.ligneId,
      cell.dataset.champ,
      origVal,
      cell.dataset.conf,
      newVal,
    );
  }}

  function cancelEdit() {{
    input.value = cell.dataset.original || '';
    display.style.display = '';
    input.style.display   = 'none';
    cell.classList.remove('editing');
  }}

  input.addEventListener('blur',    commitEdit,  {{ once: true }});
  input.addEventListener('keydown', function(ke) {{
    if (ke.key === 'Enter')  {{ ke.preventDefault(); input.blur(); }}
    if (ke.key === 'Escape') {{ ke.preventDefault(); input.removeEventListener('blur', commitEdit); cancelEdit(); }}
  }}, {{ once: true }});
}});

// Re-attach delegation when switchDoc replaces innerHTML
const _origSwitchDoc = switchDoc;
window.switchDoc = function(filename) {{
  _origSwitchDoc(filename);
  // Re-attach happens automatically via event delegation on #ext-scroll
}};
```

**Important**: The `{PDF_SERVER_PORT}` in the JS will be interpolated by Python's f-string — this is intentional and already the pattern used in the rest of the script block.

**Step 2: Manual end-to-end test**

1. Start the dashboard: `PYTHONPATH=. streamlit run dashboard/app.py`
2. Navigate to page 11 (Vérification PDF)
3. Select a document that has been ingested in the DB (via page 7 Admin → Ingérer)
4. Find a cell with an orange dashed border (conf < 50%)
5. Click it → verify input appears
6. Type a new value, press Enter
7. Verify: cell updates, badge becomes "✓ corrigé" (green)
8. Open page 10 (Corrections) → tab Historique → verify the correction is logged
9. Open page 2 (Achats) → verify the corrected value appears in analytics

**Step 3: Commit**

```bash
git add dashboard/pages/11_verification_pdf.py
git commit -m "feat(verification-pdf): JS inline editing with fetch POST and optimistic DOM update"
```

---

## Task 11: Final regression and cleanup

**Step 1: Run all tests**

```bash
# Root domain + extraction tests
pytest tests/ -v

# Dashboard tests
PYTHONPATH=. pytest dashboard/tests/ -v
```

Expected: no regressions.

**Step 2: Verify domain purity**

```bash
grep -r "sqlalchemy\|streamlit\|redis\|pdfplumber" domain/
```

Expected: no matches (domain/ must remain pure).

**Step 3: Verify editable cells are absent for documents not in DB**

1. Create a new extraction JSON in `output/extractions/` for a PDF not yet ingested
2. Open page 11, select that document
3. Verify: NO dashed orange borders (graceful fallback)

**Step 4: Final commit if any cleanup needed**

```bash
git add -p
git commit -m "chore(verification-pdf): final cleanup and regression pass"
```

---

## Summary of files changed

| File | Action |
|------|--------|
| `dashboard/pages/_verification_helpers.py` | **New** — `get_ligne_ids()`, `handle_correction_post()` |
| `dashboard/pages/verification_pdf_panel.py` | **New** — `build_extraction_panel()`, `conf_tier()`, `conf_badge()`, `val_cell()` extracted from page 11 |
| `dashboard/pages/11_verification_pdf.py` | **Modified** — import from helpers + panel module; add `_DB_ENGINE`, `_get_or_init_engine()`; extend `_CORSHandler` with `do_POST`; wire `ligne_ids` in loop; add CSS + JS |
| `dashboard/tests/integration/test_verification_inline_edit.py` | **New** — 9 TDD tests |

No changes to domain/, analytics/, or adapters/ — all persistence is delegated to the existing `appliquer_correction()`.
