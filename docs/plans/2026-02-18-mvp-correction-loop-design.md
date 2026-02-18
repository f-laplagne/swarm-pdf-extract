# MVP Design — Human Correction Loop

**Date:** 2026-02-18
**Status:** Approved
**Approach:** B — Human Correction Loop (compensate for OCR quality with operator validation)

---

## 1. Context & Problem

**Project:** Swarm PDF Extract — multi-agent system extracting structured invoice data
(line items, prices, quantities, routes) from heterogeneous PDFs for a logistics/chemical client.

**Bottleneck:** OCR quality on scanned PDFs produces fields with low confidence scores.
This makes the extracted data untrustworthy for purchasing and logistics decisions.

**Current state:**
- Dashboard: 10 Streamlit pages, 277 passing tests, hexagonal architecture (solid)
- Extraction pipeline: 4 LLM agents (classify → extract → analyze → report)
- `10_corrections.py` page exists with PDF viewer, confidence coloring, correction form,
  bounding box annotation, and correction history — foundation is in place
- Several analytics modules have uncommitted changes (logistique, qualite, tendances, transport)
- `start.sh` / `stop.sh` exist but deployment is not yet documented

---

## 2. MVP Hypothesis

> "A human operator can efficiently validate and correct low-confidence extractions,
> producing data trustworthy enough for purchasing and logistics decisions."

**Success criteria:**
1. An operator can open the dashboard, see which fields are uncertain, and correct them
   in under 2 minutes per document
2. Corrected data is immediately reflected in analytics pages (purchasing, logistics, trends)
3. A corrected field is marked as 100% trusted (human-verified) and never shown in the
   corrections queue again
4. Correction patterns can be applied across similar documents (auto-suggestion)
5. A full audit trail of who corrected what and when is available

**Primary audiences:**
- Internal ops team: efficient daily correction workflow
- Client demo: visible trust signal (data quality proven by human oversight)
- Technical team: clean hexagonal architecture, TDD, extensible

---

## 3. Gap Analysis

| Feature | Current State | MVP Requirement |
|---|---|---|
| Corrections page UI | Built (PDF viewer, form, history) | Verify complete, fix edge cases |
| Confidence reset after correction | Missing | Set corrected field conf to 1.0 |
| Correction → analytics propagation | Unverified | Corrections reflected in all pages |
| Auto-suggestion (same correction across docs) | Missing | Suggest pattern when similar field value exists |
| Domain model for Correction | Only ORM (CorrectionLog) | Domain entity in `domain/models.py` |
| End-to-end pipeline: upload → correction queue | Manual CLI trigger | Automated via upload pipeline |
| Demo packaging | Partial | Sample data, clean setup, walkthrough |

---

## 4. Architecture

### 4.1 Domain layer additions

Add `Correction` and `CorrectionStatut` to `domain/models.py`:

```python
class CorrectionStatut(Enum):
    EN_ATTENTE = "en_attente"
    APPLIQUEE = "appliquee"
    REJETEE = "rejetee"

@dataclass
class Correction:
    ligne_id: int
    champ: str
    valeur_originale: str | None
    valeur_corrigee: str
    confiance_originale: float | None
    corrige_par: str
    statut: CorrectionStatut = CorrectionStatut.APPLIQUEE
    notes: str | None = None
    timestamp: datetime | None = None
    id: int | None = None
```

Add `CorrectionPort` to `domain/ports.py`:

```python
class CorrectionPort(ABC):
    @abstractmethod
    def sauvegarder(self, correction: Correction) -> Correction: ...
    @abstractmethod
    def historique(self, ligne_id: int) -> list[Correction]: ...
    @abstractmethod
    def suggestions(self, champ: str, valeur: str) -> list[str]: ...
```

Add `CorrectionService` to a new `domain/correction_service.py`:
- `appliquer(ligne, champ, valeur, corrige_par)` → sets field + sets `conf_<champ> = 1.0`
- `suggerer(champ, valeur)` → finds most common corrected value for similar raw values
- `propaguer(champ, valeur_originale, valeur_corrigee)` → applies suggestion to all lines
  with same raw value and conf < threshold

### 4.2 Adapter layer

`dashboard/adapters/outbound/sqlalchemy_correction_repo.py` — implements `CorrectionPort`
using existing `CorrectionLog` ORM model. Wire into `app.py` composition root.

### 4.3 Analytics propagation

Ensure all analytics query functions (`achats`, `logistique`, `tendances`, `transport`,
`qualite`) use corrected field values. Currently analytics read raw ORM values — no change
needed if corrections mutate the ORM record directly (which `appliquer_correction()` does).
Verify with integration tests.

### 4.4 Upload → Correction Queue

Extend `dashboard/data/upload_pipeline.py` to call extraction + ingestion after upload,
so low-confidence lines automatically appear in the corrections queue. This closes the
end-to-end loop without requiring manual CLI intervention.

---

## 5. Phased Plan

### Phase 1 — Audit & Stabilize (week 1)

**Goal:** Clean, committed, fully-tested baseline.

1. Commit or stash uncommitted analytics changes (logistique, qualite, tendances, transport, entites)
2. Run full test suite — identify any failures
3. Write integration test: upload JSON → DB → corrections page shows low-confidence lines → apply correction → analytics page reflects corrected value
4. Verify `conf_<field>` is NOT reset to 1.0 after correction (document the gap)

### Phase 2 — Harden the Correction Loop (weeks 2–3)

**Goal:** Corrections are complete, trustworthy, and propagatable.

TDD cycle for each item (Red → Green → Refactor):

1. Domain model: `Correction`, `CorrectionStatut` in `domain/models.py`
2. Domain service: `CorrectionService` with `appliquer()`, `suggerer()`, `propaguer()`
3. Port interface: `CorrectionPort` in `domain/ports.py`
4. Adapter: `SqlAlchemyCorrectionRepository` implementing `CorrectionPort`
5. Feature: confidence reset — corrected field gets `conf = 1.0`, recalculate `confiance_globale`
6. Feature: auto-suggestion — when correcting a field, show similar corrections from history
7. Feature: bulk propagation — "apply this correction to all similar lines" button in UI
8. Wire `CorrectionService` into `10_corrections.py` via `app.py` composition root

### Phase 3 — Demo Packaging (week 4)

**Goal:** Any of the 3 audiences can run and evaluate the MVP.

1. Sample dataset: 3–5 invoices with known low-confidence extractions pre-loaded in DB
2. `start.sh` / `stop.sh`: verified working, documented
3. Demo walkthrough in `docs/demo.md`: 5-minute script showing the full correction loop
4. Dashboard UX: add confidence summary KPI to main tableau de bord page
5. Final test run: all tests pass, dashboard starts cleanly, demo flows without errors

---

## 6. Out of Scope for MVP

- OCR pre-processing improvements (deferred to a future iteration)
- Cloud OCR (Google Document AI, AWS Textract)
- Multi-user authentication / role-based access
- Real-time notifications when new documents need correction
- Mobile / offline support

---

## 7. Test Strategy

All new domain code follows TDD (Red → Green → Refactor):

- `tests/unit/test_correction_service.py` — pure domain tests, no I/O
- `dashboard/tests/unit/test_correction_domain.py` — domain model tests
- `dashboard/tests/integration/test_correction_integration.py` — end-to-end: correct field → confidence reset → analytics reflects value

Coverage target: ≥ 90% for all new modules.
