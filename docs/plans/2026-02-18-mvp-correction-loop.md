# MVP Correction Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the human correction loop so operators can detect, fix, and propagate low-confidence extractions, making data trustworthy for business decisions.

**Architecture:** Domain-first (hexagonal). New pure-domain `Correction` model + `CorrectionPort` + `CorrectionService` for auto-suggestion logic. Adapter layer wires SQLAlchemy. UI layer gets two new features: suggestion display and bulk propagation. All existing infrastructure (confidence reset, logging, confiance_globale recalculation) is already implemented in `dashboard/analytics/corrections.py`.

**Tech Stack:** Python 3.11, SQLAlchemy, Streamlit, pytest, rapidfuzz (already installed)

---

## What Already Works (Do NOT re-implement)

- `appliquer_correction()` in `dashboard/analytics/corrections.py:147` — sets `conf_<field> = 1.0`, logs to `CorrectionLog`, recalculates `confiance_globale`. **Already complete.**
- `CorrectionLog`, `BoundingBox` ORM models in `dashboard/adapters/outbound/sqlalchemy_models.py:154`
- Full corrections UI: `dashboard/pages/10_corrections.py` — PDF viewer, confidence colors, correction form, history tab
- 277 passing integration tests in `dashboard/tests/`

---

## Task 1: Commit Pending Analytics Changes

**Files:** `dashboard/analytics/logistique.py`, `qualite.py`, `tendances.py`, `transport.py`, `dashboard/pages/08_entites.py`

**Step 1: Verify all tests still pass**

```bash
PYTHONPATH=. pytest dashboard/tests/ -x -q
```

Expected: `277 passed, 1 skipped`

**Step 2: Commit the minor pending modifications**

```bash
git add dashboard/analytics/logistique.py dashboard/analytics/qualite.py \
        dashboard/analytics/tendances.py dashboard/analytics/transport.py \
        dashboard/pages/08_entites.py
git commit -m "fix(analytics): minor corrections to logistics/quality/trends/transport/entities pages"
```

---

## Task 2: Add `Correction` Domain Model

**Files:**
- Modify: `domain/models.py`
- Create: `tests/unit/test_correction_model.py`

**Step 1: Write failing test**

```python
# tests/unit/test_correction_model.py
from domain.models import Correction, CorrectionStatut

def test_correction_cree_avec_statut_par_defaut():
    c = Correction(
        ligne_id=1,
        champ="type_matiere",
        valeur_originale="sble",
        valeur_corrigee="Sable",
        confiance_originale=0.45,
        corrige_par="admin",
    )
    assert c.statut == CorrectionStatut.APPLIQUEE
    assert c.notes is None
    assert c.id is None

def test_correction_statut_enum_valeurs():
    assert CorrectionStatut.APPLIQUEE.value == "appliquee"
    assert CorrectionStatut.REJETEE.value == "rejetee"
```

**Step 2: Run to verify it fails**

```bash
pytest tests/unit/test_correction_model.py -v
```

Expected: `ImportError: cannot import name 'Correction'`

**Step 3: Add to `domain/models.py`** (after the `MergeAuditEntry` dataclass, before `ClassementFournisseur`)

```python
class CorrectionStatut(Enum):
    """Status of a manual correction."""

    APPLIQUEE = "appliquee"
    REJETEE = "rejetee"


@dataclass
class Correction:
    """A human correction applied to an extracted field."""

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

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_correction_model.py -v
```

Expected: `2 passed`

**Step 5: Verify domain purity** — domain must have zero external dependencies

```bash
grep -r "sqlalchemy\|streamlit\|redis\|pdfplumber" domain/
```

Expected: no output

**Step 6: Commit**

```bash
git add domain/models.py tests/unit/test_correction_model.py
git commit -m "feat(domain): add Correction entity and CorrectionStatut enum"
```

---

## Task 3: Add `CorrectionPort` to `domain/ports.py`

**Files:**
- Modify: `domain/ports.py`
- Create: `tests/unit/test_correction_port.py`

**Step 1: Write failing test**

```python
# tests/unit/test_correction_port.py
from domain.ports import CorrectionPort
from domain.models import Correction, CorrectionStatut

class FakeCorrectionRepository(CorrectionPort):
    def __init__(self):
        self._store: list[Correction] = []

    def sauvegarder(self, correction: Correction) -> Correction:
        correction.id = len(self._store) + 1
        self._store.append(correction)
        return correction

    def historique(self, champ: str, valeur_originale: str) -> list[Correction]:
        return [
            c for c in self._store
            if c.champ == champ and c.valeur_originale == valeur_originale
        ]

def test_correction_port_peut_sauvegarder_et_lire():
    repo = FakeCorrectionRepository()
    c = Correction(
        ligne_id=1, champ="type_matiere",
        valeur_originale="sble", valeur_corrigee="Sable",
        confiance_originale=0.45, corrige_par="admin",
    )
    saved = repo.sauvegarder(c)
    assert saved.id == 1
    history = repo.historique("type_matiere", "sble")
    assert len(history) == 1
    assert history[0].valeur_corrigee == "Sable"
```

**Step 2: Run to verify it fails**

```bash
pytest tests/unit/test_correction_port.py -v
```

Expected: `ImportError: cannot import name 'CorrectionPort'`

**Step 3: Add to `domain/ports.py`** — add import at top then add class after `AuditRepository`

Add to imports at line 10:
```python
from domain.models import (
    Anomalie,
    Correction,        # add this
    Document,
    EntityMapping,
    Fournisseur,
    LigneFacture,
    MergeAuditEntry,
)
```

Add new port class after `AuditRepository` (around line 99):
```python
class CorrectionPort(ABC):
    """Persistence port for field-level corrections."""

    @abstractmethod
    def sauvegarder(self, correction: Correction) -> Correction: ...

    @abstractmethod
    def historique(self, champ: str, valeur_originale: str) -> list[Correction]: ...
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_correction_port.py -v
```

Expected: `1 passed`

**Step 5: Run full domain unit tests**

```bash
pytest tests/unit/ -q
```

Expected: all pass

**Step 6: Commit**

```bash
git add domain/ports.py tests/unit/test_correction_port.py
git commit -m "feat(domain): add CorrectionPort interface"
```

---

## Task 4: Add `CorrectionService.suggerer()` — Pure Domain Logic

**Files:**
- Create: `domain/correction_service.py`
- Create: `tests/unit/test_correction_service.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_correction_service.py
from domain.correction_service import CorrectionService
from domain.models import Correction

def _make_correction(valeur_corrigee: str, n: int = 1) -> list[Correction]:
    return [
        Correction(
            ligne_id=i, champ="type_matiere",
            valeur_originale="sble", valeur_corrigee=valeur_corrigee,
            confiance_originale=0.4, corrige_par="admin",
        )
        for i in range(n)
    ]

def test_suggerer_retourne_valeur_la_plus_frequente():
    historique = (
        _make_correction("Sable", 3)
        + _make_correction("SABLE", 1)
    )
    suggestion = CorrectionService.suggerer("type_matiere", "sble", historique)
    assert suggestion == "Sable"

def test_suggerer_retourne_none_si_historique_vide():
    suggestion = CorrectionService.suggerer("type_matiere", "xyz", [])
    assert suggestion is None

def test_suggerer_retourne_none_si_aucune_correction_pour_ce_champ():
    historique = _make_correction("Sable", 2)
    suggestion = CorrectionService.suggerer("unite", "sble", historique)
    assert suggestion is None
```

**Step 2: Run to verify it fails**

```bash
pytest tests/unit/test_correction_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'domain.correction_service'`

**Step 3: Create `domain/correction_service.py`**

```python
"""Domain service for correction logic — pure Python, zero external dependencies."""

from __future__ import annotations

from collections import Counter

from domain.models import Correction


class CorrectionService:
    """Pure domain logic for correction suggestion and propagation decisions."""

    @staticmethod
    def suggerer(
        champ: str,
        valeur_originale: str,
        historique: list[Correction],
    ) -> str | None:
        """Return the most frequent correction applied to this (champ, valeur_originale) pair.

        Returns None if no relevant history exists.
        """
        candidats = [
            c.valeur_corrigee
            for c in historique
            if c.champ == champ and c.valeur_originale == valeur_originale
        ]
        if not candidats:
            return None
        counter = Counter(candidats)
        return counter.most_common(1)[0][0]
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_correction_service.py -v
```

Expected: `3 passed`

**Step 5: Run all unit tests**

```bash
pytest tests/unit/ -q
```

Expected: all pass

**Step 6: Commit**

```bash
git add domain/correction_service.py tests/unit/test_correction_service.py
git commit -m "feat(domain): add CorrectionService.suggerer() pure domain logic"
```

---

## Task 5: Add `CorrectionService.lignes_a_propager()` — Propagation Decision

**Files:**
- Modify: `domain/correction_service.py`
- Modify: `tests/unit/test_correction_service.py`

**Step 1: Write failing test — add to `tests/unit/test_correction_service.py`**

```python
from domain.models import LigneFacture

def test_lignes_a_propager_retourne_lignes_avec_meme_valeur_et_faible_confiance():
    # Two lines with same raw value and low conf, one with high conf
    lignes = [
        LigneFacture(ligne_numero=1, type_matiere="sble"),
        LigneFacture(ligne_numero=2, type_matiere="sble"),
        LigneFacture(ligne_numero=3, type_matiere="Sable"),  # already correct
    ]
    # Simulate conf scores: line 1 & 2 are weak, line 3 is fine
    # LigneFacture domain model doesn't carry conf — pass it separately
    conf_map = {1: 0.45, 2: 0.30, 3: 1.0}
    result = CorrectionService.lignes_a_propager(
        champ="type_matiere",
        valeur_originale="sble",
        lignes=lignes,
        conf_par_ligne=conf_map,
        seuil=0.70,
    )
    numeros = [l.ligne_numero for l in result]
    assert 1 in numeros
    assert 2 in numeros
    assert 3 not in numeros  # already different value

def test_lignes_a_propager_exclut_lignes_confiance_haute():
    lignes = [LigneFacture(ligne_numero=1, type_matiere="sble")]
    conf_map = {1: 0.95}  # high confidence — don't overwrite
    result = CorrectionService.lignes_a_propager(
        champ="type_matiere", valeur_originale="sble",
        lignes=lignes, conf_par_ligne=conf_map, seuil=0.70,
    )
    assert result == []
```

**Step 2: Run to verify it fails**

```bash
pytest tests/unit/test_correction_service.py::test_lignes_a_propager_retourne_lignes_avec_meme_valeur_et_faible_confiance -v
```

Expected: `AttributeError: type object 'CorrectionService' has no attribute 'lignes_a_propager'`

**Step 3: Add `lignes_a_propager` to `domain/correction_service.py`**

```python
    @staticmethod
    def lignes_a_propager(
        champ: str,
        valeur_originale: str,
        lignes: list,
        conf_par_ligne: dict[int, float | None],
        seuil: float = 0.70,
    ) -> list:
        """Return lines eligible for bulk propagation of a correction.

        A line is eligible if:
        - Its field value equals valeur_originale
        - Its confidence for that field is below seuil (or unknown)

        Args:
            champ: The field name to check (e.g. "type_matiere").
            valeur_originale: The raw value that was corrected.
            lignes: All candidate LigneFacture domain objects.
            conf_par_ligne: Map of ligne.ligne_numero -> confidence score.
            seuil: Confidence threshold below which propagation is applied.
        """
        eligible = []
        for ligne in lignes:
            valeur_actuelle = getattr(ligne, champ, None)
            if valeur_actuelle != valeur_originale:
                continue
            conf = conf_par_ligne.get(ligne.ligne_numero)
            if conf is None or conf < seuil:
                eligible.append(ligne)
        return eligible
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_correction_service.py -v
```

Expected: `5 passed`

**Step 5: Commit**

```bash
git add domain/correction_service.py tests/unit/test_correction_service.py
git commit -m "feat(domain): add CorrectionService.lignes_a_propager() for bulk propagation"
```

---

## Task 6: Add `SqlAlchemyCorrectionRepository` Adapter

**Files:**
- Create: `dashboard/adapters/outbound/sqlalchemy_correction_repo.py`
- Create: `dashboard/tests/integration/test_correction_repo.py`

**Step 1: Write failing integration test**

```python
# dashboard/tests/integration/test_correction_repo.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Base, CorrectionLog, Document, Fournisseur, LigneFacture
from dashboard.adapters.outbound.sqlalchemy_correction_repo import SqlAlchemyCorrectionRepository
from domain.models import Correction, CorrectionStatut


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def ligne_fixture(db_session):
    f = Fournisseur(nom="TestFour")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="test.pdf", type_document="facture", fournisseur_id=f.id)
    db_session.add(d)
    db_session.flush()
    l = LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="sble", conf_type_matiere=0.45)
    db_session.add(l)
    db_session.commit()
    return l


def test_sauvegarder_cree_correction_log(db_session, ligne_fixture):
    repo = SqlAlchemyCorrectionRepository(db_session)
    c = Correction(
        ligne_id=ligne_fixture.id,
        champ="type_matiere",
        valeur_originale="sble",
        valeur_corrigee="Sable",
        confiance_originale=0.45,
        corrige_par="admin",
    )
    saved = repo.sauvegarder(c)
    assert saved.id is not None
    # Verify persisted in DB
    log = db_session.get(CorrectionLog, saved.id)
    assert log is not None
    assert log.nouvelle_valeur == "Sable"


def test_historique_retourne_corrections_pour_champ(db_session, ligne_fixture):
    repo = SqlAlchemyCorrectionRepository(db_session)
    # Save two corrections for same (champ, valeur_originale)
    for _ in range(2):
        repo.sauvegarder(Correction(
            ligne_id=ligne_fixture.id,
            champ="type_matiere", valeur_originale="sble", valeur_corrigee="Sable",
            confiance_originale=0.4, corrige_par="admin",
        ))
    history = repo.historique("type_matiere", "sble")
    assert len(history) == 2
    assert all(c.valeur_corrigee == "Sable" for c in history)


def test_historique_vide_si_aucune_correction(db_session, ligne_fixture):
    repo = SqlAlchemyCorrectionRepository(db_session)
    history = repo.historique("unite", "kg")
    assert history == []
```

**Step 2: Run to verify it fails**

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_correction_repo.py -v
```

Expected: `ModuleNotFoundError: No module named 'dashboard.adapters.outbound.sqlalchemy_correction_repo'`

**Step 3: Create `dashboard/adapters/outbound/sqlalchemy_correction_repo.py`**

```python
"""SQLAlchemy adapter implementing CorrectionPort."""

from __future__ import annotations

from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import CorrectionLog
from domain.models import Correction, CorrectionStatut
from domain.ports import CorrectionPort


class SqlAlchemyCorrectionRepository(CorrectionPort):
    """Reads/writes Correction domain objects via CorrectionLog ORM model."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def sauvegarder(self, correction: Correction) -> Correction:
        log = CorrectionLog(
            ligne_id=correction.ligne_id,
            document_id=self._session.get(
                __import__("dashboard.adapters.outbound.sqlalchemy_models", fromlist=["LigneFacture"]).LigneFacture,
                correction.ligne_id,
            ).document_id,
            champ=correction.champ,
            ancienne_valeur=correction.valeur_originale,
            nouvelle_valeur=correction.valeur_corrigee,
            ancienne_confiance=correction.confiance_originale,
            corrige_par=correction.corrige_par,
            notes=correction.notes,
        )
        self._session.add(log)
        self._session.commit()
        correction.id = log.id
        return correction

    def historique(self, champ: str, valeur_originale: str) -> list[Correction]:
        logs = (
            self._session.query(CorrectionLog)
            .filter(
                CorrectionLog.champ == champ,
                CorrectionLog.ancienne_valeur == valeur_originale,
            )
            .all()
        )
        return [
            Correction(
                ligne_id=log.ligne_id,
                champ=log.champ,
                valeur_originale=log.ancienne_valeur,
                valeur_corrigee=log.nouvelle_valeur or "",
                confiance_originale=log.ancienne_confiance,
                corrige_par=log.corrige_par or "admin",
                notes=log.notes,
                id=log.id,
            )
            for log in logs
        ]
```

**Step 4: Run integration tests to verify they pass**

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_correction_repo.py -v
```

Expected: `3 passed`

**Step 5: Run full test suite**

```bash
PYTHONPATH=. pytest dashboard/tests/ -q && pytest tests/ -q
```

Expected: all pass

**Step 6: Commit**

```bash
git add dashboard/adapters/outbound/sqlalchemy_correction_repo.py \
        dashboard/tests/integration/test_correction_repo.py
git commit -m "feat(adapters): add SqlAlchemyCorrectionRepository for CorrectionPort"
```

---

## Task 7: Add Auto-Suggestion to the Corrections UI

**Files:**
- Modify: `dashboard/pages/10_corrections.py`
- Modify: `dashboard/analytics/corrections.py`

**Step 1: Add `suggestion_pour_champ()` to `dashboard/analytics/corrections.py`**

Add after `champs_faibles_pour_ligne()` (around line 29):

```python
def suggestion_pour_champ(
    session: Session,
    champ: str,
    valeur_originale: str,
) -> str | None:
    """Return the most frequent historical correction for this (champ, valeur_originale) pair.

    Delegates ranking logic to domain.CorrectionService.suggerer().
    """
    from domain.correction_service import CorrectionService
    from domain.models import Correction as DomainCorrection

    logs = (
        session.query(CorrectionLog)
        .filter(
            CorrectionLog.champ == champ,
            CorrectionLog.ancienne_valeur == str(valeur_originale),
        )
        .all()
    )
    historique = [
        DomainCorrection(
            ligne_id=log.ligne_id,
            champ=log.champ,
            valeur_originale=log.ancienne_valeur,
            valeur_corrigee=log.nouvelle_valeur or "",
            confiance_originale=log.ancienne_confiance,
            corrige_par=log.corrige_par or "admin",
        )
        for log in logs
    ]
    return CorrectionService.suggerer(champ, str(valeur_originale), historique)
```

**Step 2: Write a unit test for this function**

Create `dashboard/tests/integration/test_correction_suggestion.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Base, CorrectionLog, Document, Fournisseur, LigneFacture
from dashboard.analytics.corrections import suggestion_pour_champ


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def correction_history(db_session):
    f = Fournisseur(nom="Four")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="a.pdf", type_document="facture", fournisseur_id=f.id)
    db_session.add(d)
    db_session.flush()
    l = LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="sble")
    db_session.add(l)
    db_session.flush()
    # 3 corrections: "Sable" wins
    for _ in range(3):
        db_session.add(CorrectionLog(
            ligne_id=l.id, document_id=d.id,
            champ="type_matiere", ancienne_valeur="sble", nouvelle_valeur="Sable",
            corrige_par="admin",
        ))
    db_session.add(CorrectionLog(
        ligne_id=l.id, document_id=d.id,
        champ="type_matiere", ancienne_valeur="sble", nouvelle_valeur="SABLE",
        corrige_par="admin",
    ))
    db_session.commit()
    return db_session


def test_suggestion_retourne_valeur_la_plus_frequente(correction_history):
    result = suggestion_pour_champ(correction_history, "type_matiere", "sble")
    assert result == "Sable"


def test_suggestion_retourne_none_si_pas_historique(db_session):
    result = suggestion_pour_champ(db_session, "type_matiere", "xyz_inconnu")
    assert result is None
```

**Step 3: Run to verify tests pass**

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_correction_suggestion.py -v
```

Expected: `2 passed`

**Step 4: Add suggestion display in `dashboard/pages/10_corrections.py`**

In Tab 2, inside the field correction loop (around line 845, after `is_weak` check, before the input widget), add suggestion display:

Find the block that starts:
```python
if is_weak:
    st.markdown(
        f"**{field}** &nbsp; :red[conf: {conf_display}]"
    )
```

Replace it with:
```python
if is_weak:
    current_str = str(current_val) if current_val is not None else ""
    suggestion = suggestion_pour_champ(session, field, current_str) if current_str else None
    suggestion_label = f" → **{suggestion}**" if suggestion else ""
    st.markdown(
        f"**{field}** &nbsp; :red[conf: {conf_display}]{suggestion_label}"
    )
```

Also add the import at the top of Tab 2 section (around line 29 of existing imports):
```python
from dashboard.analytics.corrections import (
    ...
    suggestion_pour_champ,   # add this
)
```

**Step 5: Run all tests**

```bash
PYTHONPATH=. pytest dashboard/tests/ -q
```

Expected: all pass

**Step 6: Commit**

```bash
git add dashboard/analytics/corrections.py \
        dashboard/pages/10_corrections.py \
        dashboard/tests/integration/test_correction_suggestion.py
git commit -m "feat(corrections): add auto-suggestion display for low-confidence fields"
```

---

## Task 8: Add Bulk Propagation Button

**Files:**
- Modify: `dashboard/analytics/corrections.py`
- Modify: `dashboard/pages/10_corrections.py`
- Create: `dashboard/tests/integration/test_propagation.py`

**Step 1: Add `propager_correction()` to `dashboard/analytics/corrections.py`**

Add after `supprimer_ligne()` (around line 217):

```python
def propager_correction(
    session: Session,
    champ: str,
    valeur_originale: str,
    valeur_corrigee: str,
    seuil: float = 0.70,
    corrige_par: str = "admin",
    notes: str | None = None,
) -> int:
    """Apply a correction to all active lines sharing the same raw value and low confidence.

    Uses CorrectionService.lignes_a_propager() for eligibility logic.
    Returns the count of lines corrected.
    """
    from domain.correction_service import CorrectionService

    lignes_orm = (
        session.query(LigneFacture)
        .filter(LigneFacture.supprime != True)
        .all()
    )

    conf_par_ligne = {
        l.ligne_numero: getattr(l, f"conf_{champ}", None)
        for l in lignes_orm
    }

    # Build minimal domain objects for eligibility check
    class _Proxy:
        def __init__(self, orm_obj):
            self._orm = orm_obj
            self.ligne_numero = orm_obj.ligne_numero

        def __getattr__(self, name):
            return getattr(self._orm, name)

    proxies = [_Proxy(l) for l in lignes_orm]
    eligible = CorrectionService.lignes_a_propager(
        champ=champ,
        valeur_originale=valeur_originale,
        lignes=proxies,
        conf_par_ligne=conf_par_ligne,
        seuil=seuil,
    )

    count = 0
    affected_document_ids = set()
    for proxy in eligible:
        ligne = session.get(LigneFacture, proxy._orm.id)
        if ligne is None:
            continue
        setattr(ligne, champ, valeur_corrigee)
        setattr(ligne, f"conf_{champ}", 1.0)
        affected_document_ids.add(ligne.document_id)
        session.add(CorrectionLog(
            ligne_id=ligne.id,
            document_id=ligne.document_id,
            champ=champ,
            ancienne_valeur=valeur_originale,
            nouvelle_valeur=valeur_corrigee,
            ancienne_confiance=conf_par_ligne.get(ligne.ligne_numero),
            corrige_par=corrige_par,
            notes=notes or f"Propagation depuis correction manuelle",
        ))
        count += 1

    session.flush()
    for doc_id in affected_document_ids:
        recalculer_confiance_globale(session, doc_id)
    session.commit()
    return count
```

**Step 2: Write integration test**

```python
# dashboard/tests/integration/test_propagation.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Base, Document, Fournisseur, LigneFacture
from dashboard.analytics.corrections import propager_correction


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def multi_ligne_data(db_session):
    f = Fournisseur(nom="Four")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="b.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.5)
    db_session.add(d)
    db_session.flush()
    # 3 lines: 2 with "sble" + low conf, 1 with "Sable" already correct
    l1 = LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="sble", conf_type_matiere=0.45)
    l2 = LigneFacture(document_id=d.id, ligne_numero=2, type_matiere="sble", conf_type_matiere=0.30)
    l3 = LigneFacture(document_id=d.id, ligne_numero=3, type_matiere="Sable", conf_type_matiere=1.0)
    db_session.add_all([l1, l2, l3])
    db_session.commit()
    return db_session, d, [l1, l2, l3]


def test_propager_corrige_toutes_lignes_eligibles(multi_ligne_data):
    session, doc, lignes = multi_ligne_data
    count = propager_correction(
        session, champ="type_matiere",
        valeur_originale="sble", valeur_corrigee="Sable",
        seuil=0.70,
    )
    assert count == 2
    session.expire_all()
    assert session.get(LigneFacture, lignes[0].id).type_matiere == "Sable"
    assert session.get(LigneFacture, lignes[1].id).type_matiere == "Sable"
    assert session.get(LigneFacture, lignes[2].id).type_matiere == "Sable"  # unchanged


def test_propager_remet_confiance_a_1(multi_ligne_data):
    session, _, lignes = multi_ligne_data
    propager_correction(session, "type_matiere", "sble", "Sable")
    session.expire_all()
    assert session.get(LigneFacture, lignes[0].id).conf_type_matiere == 1.0
    assert session.get(LigneFacture, lignes[1].id).conf_type_matiere == 1.0


def test_propager_ne_touche_pas_lignes_confiance_haute(db_session):
    f = Fournisseur(nom="F2")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="c.pdf", type_document="facture", fournisseur_id=f.id)
    db_session.add(d)
    db_session.flush()
    l = LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="sble", conf_type_matiere=0.95)
    db_session.add(l)
    db_session.commit()

    count = propager_correction(db_session, "type_matiere", "sble", "Sable", seuil=0.70)
    assert count == 0
```

**Step 3: Run to verify tests pass**

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_propagation.py -v
```

Expected: `3 passed`

**Step 4: Add bulk propagation button to `dashboard/pages/10_corrections.py`**

In Tab 2, after the "Appliquer les corrections" submit button block (around line 950), add:

```python
# Add import at top of file with other corrections imports:
# from dashboard.analytics.corrections import (
#     ...
#     propager_correction,
# )

st.markdown("---")
st.subheader("Propagation en masse")
st.caption("Applique la meme correction a toutes les lignes ayant la meme valeur brute et une confiance faible.")

with st.expander("Propager une correction"):
    prop_champ = st.selectbox(
        "Champ", options=EDITABLE_FIELDS, key="prop_champ_select",
    )
    prop_originale = st.text_input("Valeur originale (brute)", key="prop_originale")
    prop_corrigee = st.text_input("Valeur corrigee (cible)", key="prop_corrigee")
    prop_seuil = st.slider(
        "Seuil de confiance max", 0.0, 1.0, 0.70, 0.05, key="prop_seuil",
    )
    if st.button("Propager", type="secondary", key="prop_btn"):
        if prop_originale.strip() and prop_corrigee.strip():
            n = propager_correction(
                session,
                champ=prop_champ,
                valeur_originale=prop_originale.strip(),
                valeur_corrigee=prop_corrigee.strip(),
                seuil=prop_seuil,
            )
            st.success(f"{n} ligne(s) corrigee(s) par propagation.")
            st.rerun()
        else:
            st.warning("Renseignez la valeur originale et la valeur corrigee.")
```

**Step 5: Run all tests**

```bash
PYTHONPATH=. pytest dashboard/tests/ -q && pytest tests/ -q
```

Expected: all pass

**Step 6: Commit**

```bash
git add dashboard/analytics/corrections.py \
        dashboard/pages/10_corrections.py \
        dashboard/tests/integration/test_propagation.py
git commit -m "feat(corrections): add bulk propagation — apply one correction to all similar lines"
```

---

## Task 9: Integration Test — Corrections Reflected in Analytics

**Files:**
- Create: `dashboard/tests/integration/test_correction_analytics_integration.py`

This test verifies the end-to-end claim: correcting a field updates the value seen by analytics queries.

**Step 1: Write the integration test**

```python
# dashboard/tests/integration/test_correction_analytics_integration.py
"""End-to-end test: correction applied → analytics query returns corrected value."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.adapters.outbound.sqlalchemy_models import Base, Document, Fournisseur, LigneFacture
from dashboard.analytics.corrections import appliquer_correction
from dashboard.analytics.achats import top_matieres


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_correction_refleted_in_achats_analytics(db_session):
    """After correcting type_matiere, the analytics top_matieres shows corrected name."""
    f = Fournisseur(nom="TestFour")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="test.pdf", type_document="facture",
                 fournisseur_id=f.id, confiance_globale=0.5)
    db_session.add(d)
    db_session.flush()
    l = LigneFacture(
        document_id=d.id, ligne_numero=1,
        type_matiere="sble",  # typo
        prix_total=100.0,
        conf_type_matiere=0.45,
    )
    db_session.add(l)
    db_session.commit()

    # Before correction: "sble" appears in analytics
    df_before = top_matieres(db_session)
    assert "sble" in df_before["type_matiere"].values

    # Apply correction
    appliquer_correction(db_session, l.id, {"type_matiere": "Sable"})

    # After correction: "Sable" appears, "sble" does not
    db_session.expire_all()
    df_after = top_matieres(db_session)
    assert "Sable" in df_after["type_matiere"].values
    assert "sble" not in df_after["type_matiere"].values


def test_correction_met_confiance_a_1(db_session):
    """After correction, conf field is 1.0 and confiance_globale is recalculated."""
    f = Fournisseur(nom="F")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="t.pdf", type_document="facture",
                 fournisseur_id=f.id, confiance_globale=0.4)
    db_session.add(d)
    db_session.flush()
    l = LigneFacture(
        document_id=d.id, ligne_numero=1,
        type_matiere="sble", conf_type_matiere=0.45,
    )
    db_session.add(l)
    db_session.commit()

    appliquer_correction(db_session, l.id, {"type_matiere": "Sable"})
    db_session.expire_all()

    updated = db_session.get(LigneFacture, l.id)
    assert updated.conf_type_matiere == 1.0
```

**Step 2: Run to verify test passes** (if `top_matieres` signature differs, check `dashboard/analytics/achats.py` and adjust the call)

```bash
PYTHONPATH=. pytest dashboard/tests/integration/test_correction_analytics_integration.py -v
```

Expected: `2 passed`

**Step 3: Run full suite**

```bash
PYTHONPATH=. pytest dashboard/tests/ -q && pytest tests/ -q
```

Expected: all pass

**Step 4: Commit**

```bash
git add dashboard/tests/integration/test_correction_analytics_integration.py
git commit -m "test(integration): verify corrections are reflected in analytics queries"
```

---

## Task 10: Sample Data Loader + Demo Script

**Files:**
- Create: `scripts/load_demo_data.py`
- Create: `docs/demo.md`

**Step 1: Create `scripts/load_demo_data.py`**

```python
#!/usr/bin/env python3
"""Load sample data with known low-confidence extractions for demo purposes.

Usage:
    PYTHONPATH=. python scripts/load_demo_data.py

Creates 3 documents with mixed confidence scores in the DB.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dashboard.data.db import get_engine, init_db
from dashboard.adapters.outbound.sqlalchemy_models import (
    Base, Document, Fournisseur, LigneFacture,
)
from sqlalchemy.orm import Session

DB_URL = "sqlite:///dashboard/data/rationalize.db"


def main():
    engine = get_engine(DB_URL)
    init_db(engine)

    with Session(engine) as session:
        # Fournisseurs
        f1 = Fournisseur(nom="Transport Durand SARL")
        f2 = Fournisseur(nom="Chimex SA")
        session.add_all([f1, f2])
        session.flush()

        # Document 1: mostly low confidence (scanned invoice)
        d1 = Document(
            fichier="FACTURE_DEMO_001.pdf", type_document="facture",
            fournisseur_id=f1.id, confiance_globale=0.42,
        )
        session.add(d1)
        session.flush()
        session.add_all([
            LigneFacture(
                document_id=d1.id, ligne_numero=1,
                type_matiere="sble fin", unite="T", prix_unitaire=45.0,
                quantite=10.0, prix_total=450.0,
                lieu_depart="Marseile", lieu_arrivee="Lyon",
                conf_type_matiere=0.35, conf_unite=0.80, conf_prix_unitaire=0.40,
                conf_quantite=0.90, conf_prix_total=0.40,
                conf_lieu_depart=0.30, conf_lieu_arrivee=0.85,
            ),
            LigneFacture(
                document_id=d1.id, ligne_numero=2,
                type_matiere="gravir", unite="M3", prix_unitaire=32.0,
                quantite=5.0, prix_total=160.0,
                lieu_depart="Marseile", lieu_arrivee="Lyon",
                conf_type_matiere=0.25, conf_unite=0.70, conf_prix_unitaire=0.55,
                conf_quantite=0.85, conf_prix_total=0.55,
                conf_lieu_depart=0.30, conf_lieu_arrivee=0.85,
            ),
        ])

        # Document 2: mixed confidence
        d2 = Document(
            fichier="FACTURE_DEMO_002.pdf", type_document="facture",
            fournisseur_id=f2.id, confiance_globale=0.68,
        )
        session.add(d2)
        session.flush()
        session.add_all([
            LigneFacture(
                document_id=d2.id, ligne_numero=1,
                type_matiere="Acide sulfurique", unite="L", prix_unitaire=12.50,
                quantite=200.0, prix_total=2500.0,
                conf_type_matiere=0.90, conf_unite=0.88, conf_prix_unitaire=0.75,
                conf_quantite=0.92, conf_prix_total=0.75,
            ),
            LigneFacture(
                document_id=d2.id, ligne_numero=2,
                type_matiere="soude caustiq", unite="KG", prix_unitaire=8.0,
                quantite=50.0, prix_total=400.0,
                conf_type_matiere=0.40, conf_unite=0.85, conf_prix_unitaire=0.60,
                conf_quantite=0.88, conf_prix_total=0.60,
            ),
        ])

        # Document 3: high confidence (for contrast)
        d3 = Document(
            fichier="FACTURE_DEMO_003.pdf", type_document="facture",
            fournisseur_id=f1.id, confiance_globale=0.95,
        )
        session.add(d3)
        session.flush()
        session.add(LigneFacture(
            document_id=d3.id, ligne_numero=1,
            type_matiere="Sable fin", unite="T", prix_unitaire=45.0,
            quantite=20.0, prix_total=900.0,
            conf_type_matiere=0.98, conf_unite=0.95, conf_prix_unitaire=0.97,
            conf_quantite=0.99, conf_prix_total=0.97,
            lieu_depart="Marseille", lieu_arrivee="Lyon",
            conf_lieu_depart=0.95, conf_lieu_arrivee=0.96,
        ))

        session.commit()
        print("Demo data loaded: 3 documents, 5 lines with mixed confidence scores.")
        print("Run: PYTHONPATH=. streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
```

**Step 2: Run to verify it works**

```bash
PYTHONPATH=. python scripts/load_demo_data.py
```

Expected: `Demo data loaded: 3 documents, 5 lines with mixed confidence scores.`

**Step 3: Create `docs/demo.md`** (5-minute walkthrough)

```markdown
# Demo Script — Correction Loop MVP (5 minutes)

## Setup

```bash
PYTHONPATH=. python scripts/load_demo_data.py   # load sample data
bash start.sh                                    # start dashboard
```

Open http://localhost:8501

## Walkthrough

### 1. See the data quality problem (1 min)
- Go to **Tableau de bord** — note low global confidence scores
- Go to **Qualite** — see fields colored red/orange for uncertain extractions

### 2. Navigate to the Correction Workflow (1 min)
- Go to **Corrections**
- Tab "Documents à corriger" shows 2 documents needing attention
- Adjust confidence threshold slider to see more/fewer flagged documents

### 3. Correct a low-confidence field (2 min)
- Click Tab "Corriger une ligne"
- Select FACTURE_DEMO_001.pdf
- See the PDF on the left, confidence card on the right
- Select "Ligne 1 — sble fin (5 champs faibles)"
- Field `type_matiere` shows :red[conf: 35%] → suggestion **Sable fin** appears automatically
- Accept the suggestion: type "Sable fin", click **Appliquer les corrections**
- Confidence resets to 100%, global document confidence rises

### 4. Propagate to all similar lines (1 min)
- Expand "Propagation en masse"
- Champ: `lieu_depart` / Valeur originale: `Marseile` / Valeur corrigée: `Marseille`
- Click **Propager** — fixes the typo across all documents at once

### 5. Verify in analytics (30 sec)
- Go to **Achats** — "Sable fin" appears correctly in material rankings
- Go to **Historique** tab in Corrections — full audit trail visible
```

**Step 4: Commit**

```bash
git add scripts/load_demo_data.py docs/demo.md
git commit -m "feat(demo): add sample data loader and 5-minute demo walkthrough script"
```

---

## Task 11: Final Verification

**Step 1: Run all tests**

```bash
PYTHONPATH=. pytest dashboard/tests/ -q && pytest tests/ -q
```

Expected: all pass (no failures)

**Step 2: Verify domain purity**

```bash
grep -r "sqlalchemy\|streamlit\|redis\|pdfplumber" domain/
```

Expected: no output

**Step 3: Load demo data and start dashboard**

```bash
PYTHONPATH=. python scripts/load_demo_data.py
bash start.sh
```

Walk through the demo script in `docs/demo.md` to confirm the full flow works without errors.

**Step 4: Final commit**

```bash
git add .
git commit -m "chore: final MVP verification — all tests pass, demo flow confirmed"
```

---

## Summary

| Task | Files Created/Modified | Key Outcome |
|------|------------------------|-------------|
| 1 | 5 analytics files | Clean baseline committed |
| 2 | `domain/models.py` + test | `Correction` domain entity |
| 3 | `domain/ports.py` + test | `CorrectionPort` interface |
| 4 | `domain/correction_service.py` + test | `suggerer()` pure logic |
| 5 | same | `lignes_a_propager()` pure logic |
| 6 | `sqlalchemy_correction_repo.py` + test | Adapter implementing port |
| 7 | `corrections.py` + page + test | Auto-suggestion in UI |
| 8 | `corrections.py` + page + test | Bulk propagation in UI |
| 9 | integration test | Analytics reflects corrections |
| 10 | `load_demo_data.py` + `docs/demo.md` | Demo-ready |
| 11 | — | Final verification |
