# Rationalize Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an interactive Streamlit dashboard ("Rationalize") that analyzes extracted PDF invoice data for purchasing rationalization, logistics optimization, anomaly detection, temporal trends, and data quality monitoring.

**Architecture:** Streamlit multi-page app with SQLAlchemy ORM over SQLite (upgradable to PostgreSQL), Redis cache for heavy aggregations, and a service layer (`analytics/`) separating business logic from UI. The ingestion pipeline loads JSON extraction outputs from the existing swarm-pdf-extract pipeline into the DB.

**Tech Stack:** Python 3.11+, Streamlit >= 1.40, SQLAlchemy 2.x, Pandas 2.x, Plotly 5.x, Redis 5.x, Docker Compose.

---

## Task 1: Project Scaffolding

**Files:**
- Create: `dashboard/requirements.txt`
- Create: `dashboard/config.yaml`
- Create: `dashboard/data/__init__.py`
- Create: `dashboard/analytics/__init__.py`
- Create: `dashboard/pages/__init__.py`
- Create: `dashboard/components/__init__.py`

**Step 1: Create dashboard directory structure**

```bash
mkdir -p dashboard/{data,analytics,pages,components}
touch dashboard/data/__init__.py
touch dashboard/analytics/__init__.py
touch dashboard/pages/__init__.py
touch dashboard/components/__init__.py
```

**Step 2: Write requirements.txt**

Create `dashboard/requirements.txt`:

```
# UI
streamlit>=1.40.0

# Data
pandas>=2.0.0
sqlalchemy>=2.0.0

# Charts
plotly>=5.0.0

# Cache
redis>=5.0.0

# Config
pyyaml>=6.0

# Export
openpyxl>=3.1.0

# Geocoding (logistics module)
geopy>=2.4.0

# Testing
pytest>=8.0.0
pytest-cov>=5.0.0
```

**Step 3: Write config.yaml**

Create `dashboard/config.yaml`:

```yaml
database:
  url: "sqlite:///data/rationalize.db"

redis:
  url: "redis://localhost:6379/0"
  ttl: 3600  # cache TTL in seconds

# Paths to extraction JSONs (relative to project root)
ingestion:
  extractions_dir: "../output/extractions"

# Anomaly detection thresholds
anomalies:
  regles:
    - id: "CALC_001"
      nom: "Incohérence prix x quantité"
      type: "coherence_calcul"
      severite: "critique"
      seuil_tolerance: 0.01  # 1%

    - id: "PRIX_001"
      nom: "Surfacturation potentielle"
      type: "prix_anormal"
      severite: "warning"
      seuil_multiplicateur: 2.0  # 2x average

    - id: "DUP_001"
      nom: "Doublon potentiel"
      type: "doublon"
      severite: "critique"
      seuil_jours: 7

    - id: "DATE_001"
      nom: "Date arrivée avant départ"
      type: "date_invalide"
      severite: "warning"

    - id: "CONF_001"
      nom: "Extraction faible confiance"
      type: "qualite_donnees"
      severite: "info"
      seuil_confiance: 0.6

    - id: "PRIX_002"
      nom: "Dérive tarifaire"
      type: "prix_anormal"
      severite: "warning"
      seuil_variation: 0.20  # 20%
      periode_mois: 3

    - id: "MANQ_001"
      nom: "Prix manquant"
      type: "donnees_manquantes"
      severite: "warning"
      seuil_confiance_min: 0.3

# UI display
ui:
  page_title: "Rationalize"
  page_icon: "📊"
  layout: "wide"

# Confidence thresholds (from parent project)
confidence:
  minimum: 0.3
  fiable: 0.8
  document_succes: 0.6
```

**Step 4: Commit**

```bash
git add dashboard/
git commit -m "feat: scaffold dashboard project structure and config"
```

---

## Task 2: SQLAlchemy Models

**Files:**
- Create: `dashboard/data/models.py`
- Create: `dashboard/data/db.py`
- Test: `dashboard/tests/test_models.py`

**Step 1: Write the failing test**

Create `dashboard/tests/__init__.py` and `dashboard/tests/test_models.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture, Anomalie


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_create_fournisseur(db_session):
    f = Fournisseur(nom="Transports Fockedey s.a.", siret=None, tva_intra="BE0439.237.690")
    db_session.add(f)
    db_session.commit()
    assert f.id is not None
    assert f.nom == "Transports Fockedey s.a."


def test_create_document_with_fournisseur(db_session):
    f = Fournisseur(nom="Fockedey")
    db_session.add(f)
    db_session.flush()

    d = Document(
        fichier="facture_test.pdf",
        type_document="facture",
        fournisseur_id=f.id,
        montant_ht=19597.46,
        confiance_globale=0.96,
    )
    db_session.add(d)
    db_session.commit()
    assert d.id is not None
    assert d.fournisseur.nom == "Fockedey"


def test_create_ligne_facture(db_session):
    f = Fournisseur(nom="Test")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="test.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.9)
    db_session.add(d)
    db_session.flush()

    ligne = LigneFacture(
        document_id=d.id,
        ligne_numero=1,
        type_matiere="Nitrate Ethyle Hexyl",
        unite="voyage",
        prix_unitaire=1620.00,
        quantite=1,
        prix_total=1620.00,
        date_depart="2024-11-05",
        lieu_depart="Sorgues",
        lieu_arrivee="Kallo",
        conf_type_matiere=0.98,
        conf_prix_unitaire=0.99,
    )
    db_session.add(ligne)
    db_session.commit()
    assert ligne.id is not None
    assert d.lignes[0].type_matiere == "Nitrate Ethyle Hexyl"


def test_create_anomalie(db_session):
    f = Fournisseur(nom="Test")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="test.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.5)
    db_session.add(d)
    db_session.flush()

    a = Anomalie(
        document_id=d.id,
        regle_id="CONF_001",
        type_anomalie="qualite_donnees",
        severite="info",
        description="Confiance globale < 0.6",
    )
    db_session.add(a)
    db_session.commit()
    assert a.id is not None
    assert len(d.anomalies) == 1
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/fred/AI_Projects/swarm-pdf-extract && python -m pytest dashboard/tests/test_models.py -v`
Expected: FAIL (ImportError, module not found)

**Step 3: Write models.py**

Create `dashboard/data/models.py`:

```python
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Text, ForeignKey, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Fournisseur(Base):
    __tablename__ = "fournisseurs"

    id = Column(Integer, primary_key=True)
    nom = Column(String, nullable=False)
    adresse = Column(Text)
    siret = Column(String)
    tva_intra = Column(String)

    documents = relationship("Document", back_populates="fournisseur")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    fichier = Column(String, nullable=False, unique=True)
    type_document = Column(String)
    format_pdf = Column(String)
    fournisseur_id = Column(Integer, ForeignKey("fournisseurs.id"))
    client_nom = Column(String)
    client_adresse = Column(Text)
    date_document = Column(Date)
    numero_document = Column(String)
    montant_ht = Column(Float)
    montant_tva = Column(Float)
    montant_ttc = Column(Float)
    devise = Column(String, default="EUR")
    conditions_paiement = Column(Text)
    ref_commande = Column(String)
    ref_contrat = Column(String)
    ref_bon_livraison = Column(String)
    confiance_globale = Column(Float)
    strategie_utilisee = Column(String)
    complexite = Column(Integer)
    date_ingestion = Column(DateTime, default=datetime.utcnow)

    fournisseur = relationship("Fournisseur", back_populates="documents")
    lignes = relationship("LigneFacture", back_populates="document", cascade="all, delete-orphan")
    anomalies = relationship("Anomalie", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_documents_fournisseur", "fournisseur_id"),
        Index("idx_documents_date", "date_document"),
    )


class LigneFacture(Base):
    __tablename__ = "lignes_facture"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    ligne_numero = Column(Integer)
    type_matiere = Column(Text)
    unite = Column(String)
    prix_unitaire = Column(Float)
    quantite = Column(Float)
    prix_total = Column(Float)
    date_depart = Column(String)  # ISO 8601 string, nullable
    date_arrivee = Column(String)
    lieu_depart = Column(Text)
    lieu_arrivee = Column(Text)
    conf_type_matiere = Column(Float)
    conf_unite = Column(Float)
    conf_prix_unitaire = Column(Float)
    conf_quantite = Column(Float)
    conf_prix_total = Column(Float)
    conf_date_depart = Column(Float)
    conf_date_arrivee = Column(Float)
    conf_lieu_depart = Column(Float)
    conf_lieu_arrivee = Column(Float)

    document = relationship("Document", back_populates="lignes")

    __table_args__ = (
        Index("idx_lignes_document", "document_id"),
        Index("idx_lignes_matiere", "type_matiere"),
        Index("idx_lignes_dates", "date_depart", "date_arrivee"),
        Index("idx_lignes_lieux", "lieu_depart", "lieu_arrivee"),
    )


class Anomalie(Base):
    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    ligne_id = Column(Integer, ForeignKey("lignes_facture.id"), nullable=True)
    regle_id = Column(String)
    type_anomalie = Column(String)
    severite = Column(String)
    description = Column(Text)
    valeur_attendue = Column(String)
    valeur_trouvee = Column(String)
    date_detection = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="anomalies")
    ligne = relationship("LigneFacture")

    __table_args__ = (
        Index("idx_anomalies_document", "document_id"),
        Index("idx_anomalies_type", "type_anomalie"),
    )
```

**Step 4: Write db.py**

Create `dashboard/data/db.py`:

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dashboard.data.models import Base


def get_engine(url: str | None = None):
    db_url = url or os.environ.get("DATABASE_URL", "sqlite:///data/rationalize.db")
    return create_engine(db_url, echo=False)


def init_db(engine=None):
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session(engine=None):
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()
```

**Step 5: Run tests to verify they pass**

Run: `cd /Users/fred/AI_Projects/swarm-pdf-extract && python -m pytest dashboard/tests/test_models.py -v`
Expected: 4 tests PASS

**Step 6: Commit**

```bash
git add dashboard/data/ dashboard/tests/
git commit -m "feat: add SQLAlchemy ORM models for documents, lignes, fournisseurs, anomalies"
```

---

## Task 3: Ingestion Pipeline

**Files:**
- Create: `dashboard/data/ingestion.py`
- Test: `dashboard/tests/test_ingestion.py`

**Step 1: Write the failing test**

Create `dashboard/tests/test_ingestion.py`:

```python
import json
import os
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture
from dashboard.data.ingestion import ingest_extraction_json, ingest_directory


SAMPLE_EXTRACTION = {
    "fichier": "Facture 24-110193.pdf",
    "type_document": "facture",
    "strategie_utilisee": "pdfplumber_tables",
    "metadonnees": {
        "numero_document": "24/110193",
        "date_document": "2024-11-30",
        "fournisseur": {
            "nom": "Transports Fockedey s.a.",
            "adresse": "Zone Industrielle, 7900 Leuze",
            "siret": None,
            "tva_intra": "BE0439.237.690"
        },
        "client": {
            "nom": "Eurenco France SAS",
            "adresse": "F-84700 Sorgues"
        },
        "montant_ht": 19597.46,
        "montant_tva": 0,
        "montant_ttc": 19597.46,
        "devise": "EUR",
        "conditions_paiement": "30 jours",
        "references": {
            "commande": "4600039119",
            "contrat": None,
            "bon_livraison": None
        }
    },
    "lignes": [
        {
            "ligne_numero": 1,
            "type_matiere": "Nitrate Ethyle Hexyl",
            "unite": "voyage",
            "prix_unitaire": 1620.00,
            "quantite": 1,
            "prix_total": 1620.00,
            "date_depart": "2024-11-05",
            "date_arrivee": "2024-11-07",
            "lieu_depart": "Sorgues",
            "lieu_arrivee": "Kallo",
            "confiance": {
                "type_matiere": 0.98,
                "unite": 0.95,
                "prix_unitaire": 0.99,
                "quantite": 0.99,
                "prix_total": 0.99,
                "date_depart": 0.95,
                "date_arrivee": 0.95,
                "lieu_depart": 0.98,
                "lieu_arrivee": 0.98
            }
        }
    ],
    "confiance_globale": 0.96,
    "champs_manquants": [],
    "warnings": []
}


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_ingest_single_extraction(db_session):
    doc = ingest_extraction_json(db_session, SAMPLE_EXTRACTION)
    db_session.commit()

    assert doc.fichier == "Facture 24-110193.pdf"
    assert doc.montant_ht == 19597.46
    assert doc.fournisseur.nom == "Transports Fockedey s.a."
    assert len(doc.lignes) == 1
    assert doc.lignes[0].type_matiere == "Nitrate Ethyle Hexyl"
    assert doc.lignes[0].conf_prix_unitaire == 0.99


def test_ingest_deduplicates_fournisseur(db_session):
    ingest_extraction_json(db_session, SAMPLE_EXTRACTION)
    db_session.commit()

    # Ingest a second doc with same fournisseur
    data2 = {**SAMPLE_EXTRACTION, "fichier": "Facture_2.pdf"}
    data2["metadonnees"] = {**SAMPLE_EXTRACTION["metadonnees"], "numero_document": "24/999"}
    ingest_extraction_json(db_session, data2)
    db_session.commit()

    fournisseurs = db_session.query(Fournisseur).all()
    assert len(fournisseurs) == 1  # same fournisseur reused


def test_ingest_skips_duplicate_fichier(db_session):
    ingest_extraction_json(db_session, SAMPLE_EXTRACTION)
    db_session.commit()

    # Same file again should skip
    result = ingest_extraction_json(db_session, SAMPLE_EXTRACTION)
    assert result is None


def test_ingest_directory(db_session, tmp_path):
    # Write two extraction files
    for i, name in enumerate(["doc1_extraction.json", "doc2_extraction.json"]):
        data = {**SAMPLE_EXTRACTION, "fichier": f"doc{i}.pdf"}
        data["metadonnees"] = {**SAMPLE_EXTRACTION["metadonnees"], "numero_document": f"NUM-{i}"}
        (tmp_path / name).write_text(json.dumps(data))

    # Also write a classification file that should be ignored
    (tmp_path / "doc1_classification.json").write_text("{}")

    stats = ingest_directory(db_session, str(tmp_path))
    assert stats["ingested"] == 2
    assert stats["skipped"] == 0
    assert stats["errors"] == 0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest dashboard/tests/test_ingestion.py -v`
Expected: FAIL (ImportError)

**Step 3: Write ingestion.py**

Create `dashboard/data/ingestion.py`:

```python
import json
import glob
import os
from datetime import date, datetime
from sqlalchemy.orm import Session

from dashboard.data.models import Fournisseur, Document, LigneFacture


def _parse_date(s: str | None) -> str | None:
    """Keep ISO date strings as-is, return None for empty/null."""
    if not s:
        return None
    return s


def _get_or_create_fournisseur(session: Session, fournisseur_data: dict | None) -> Fournisseur | None:
    if not fournisseur_data or not fournisseur_data.get("nom"):
        return None

    nom = fournisseur_data["nom"]
    existing = session.query(Fournisseur).filter_by(nom=nom).first()
    if existing:
        return existing

    f = Fournisseur(
        nom=nom,
        adresse=fournisseur_data.get("adresse"),
        siret=fournisseur_data.get("siret"),
        tva_intra=fournisseur_data.get("tva_intra"),
    )
    session.add(f)
    session.flush()
    return f


def ingest_extraction_json(session: Session, data: dict) -> Document | None:
    """Ingest a single extraction JSON dict into the database.
    Returns the Document or None if skipped (duplicate)."""

    fichier = data["fichier"]

    # Skip if already ingested
    existing = session.query(Document).filter_by(fichier=fichier).first()
    if existing:
        return None

    meta = data.get("metadonnees", {})
    refs = meta.get("references", {}) or {}

    fournisseur = _get_or_create_fournisseur(session, meta.get("fournisseur"))

    client = meta.get("client", {}) or {}

    doc = Document(
        fichier=fichier,
        type_document=data.get("type_document"),
        format_pdf=None,  # from classification, not extraction
        fournisseur_id=fournisseur.id if fournisseur else None,
        client_nom=client.get("nom"),
        client_adresse=client.get("adresse"),
        date_document=_parse_date(meta.get("date_document")),
        numero_document=meta.get("numero_document"),
        montant_ht=meta.get("montant_ht"),
        montant_tva=meta.get("montant_tva"),
        montant_ttc=meta.get("montant_ttc"),
        devise=meta.get("devise", "EUR"),
        conditions_paiement=meta.get("conditions_paiement"),
        ref_commande=refs.get("commande"),
        ref_contrat=refs.get("contrat"),
        ref_bon_livraison=refs.get("bon_livraison"),
        confiance_globale=data.get("confiance_globale"),
        strategie_utilisee=data.get("strategie_utilisee"),
    )
    session.add(doc)
    session.flush()

    for ligne_data in data.get("lignes", []):
        conf = ligne_data.get("confiance", {})
        ligne = LigneFacture(
            document_id=doc.id,
            ligne_numero=ligne_data.get("ligne_numero"),
            type_matiere=ligne_data.get("type_matiere"),
            unite=ligne_data.get("unite"),
            prix_unitaire=ligne_data.get("prix_unitaire"),
            quantite=ligne_data.get("quantite"),
            prix_total=ligne_data.get("prix_total"),
            date_depart=_parse_date(ligne_data.get("date_depart")),
            date_arrivee=_parse_date(ligne_data.get("date_arrivee")),
            lieu_depart=ligne_data.get("lieu_depart"),
            lieu_arrivee=ligne_data.get("lieu_arrivee"),
            conf_type_matiere=conf.get("type_matiere"),
            conf_unite=conf.get("unite"),
            conf_prix_unitaire=conf.get("prix_unitaire"),
            conf_quantite=conf.get("quantite"),
            conf_prix_total=conf.get("prix_total"),
            conf_date_depart=conf.get("date_depart"),
            conf_date_arrivee=conf.get("date_arrivee"),
            conf_lieu_depart=conf.get("lieu_depart"),
            conf_lieu_arrivee=conf.get("lieu_arrivee"),
        )
        session.add(ligne)

    return doc


def ingest_directory(session: Session, directory: str) -> dict:
    """Ingest all *_extraction.json files from a directory.
    Returns stats dict with ingested/skipped/errors counts."""

    stats = {"ingested": 0, "skipped": 0, "errors": 0, "files": []}

    pattern = os.path.join(directory, "*_extraction.json")
    for filepath in sorted(glob.glob(pattern)):
        filename = os.path.basename(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            result = ingest_extraction_json(session, data)
            if result is None:
                stats["skipped"] += 1
                stats["files"].append({"file": filename, "status": "skipped"})
            else:
                stats["ingested"] += 1
                stats["files"].append({"file": filename, "status": "ingested"})

        except Exception as e:
            stats["errors"] += 1
            stats["files"].append({"file": filename, "status": "error", "error": str(e)})

    session.commit()
    return stats
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest dashboard/tests/test_ingestion.py -v`
Expected: 4 tests PASS

**Step 5: Commit**

```bash
git add dashboard/data/ingestion.py dashboard/tests/test_ingestion.py
git commit -m "feat: add JSON extraction ingestion pipeline with dedup"
```

---

## Task 4: Analytics — Achats (Purchasing Rationalization)

**Files:**
- Create: `dashboard/analytics/achats.py`
- Test: `dashboard/tests/test_achats.py`

**Step 1: Write the failing test**

Create `dashboard/tests/test_achats.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture
from dashboard.analytics.achats import (
    top_fournisseurs_by_montant,
    prix_moyen_par_matiere,
    ecarts_prix_fournisseurs,
    indice_fragmentation,
    economie_potentielle,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def sample_data(db_session):
    f1 = Fournisseur(nom="Fournisseur A")
    f2 = Fournisseur(nom="Fournisseur B")
    db_session.add_all([f1, f2])
    db_session.flush()

    d1 = Document(fichier="f1.pdf", type_document="facture", fournisseur_id=f1.id,
                  montant_ht=5000, confiance_globale=0.9)
    d2 = Document(fichier="f2.pdf", type_document="facture", fournisseur_id=f2.id,
                  montant_ht=3000, confiance_globale=0.9)
    db_session.add_all([d1, d2])
    db_session.flush()

    lignes = [
        LigneFacture(document_id=d1.id, ligne_numero=1, type_matiere="Acier",
                     unite="kg", prix_unitaire=10.0, quantite=100, prix_total=1000.0),
        LigneFacture(document_id=d1.id, ligne_numero=2, type_matiere="Cuivre",
                     unite="kg", prix_unitaire=25.0, quantite=50, prix_total=1250.0),
        LigneFacture(document_id=d2.id, ligne_numero=1, type_matiere="Acier",
                     unite="kg", prix_unitaire=12.0, quantite=200, prix_total=2400.0),
    ]
    db_session.add_all(lignes)
    db_session.commit()
    return db_session


def test_top_fournisseurs(sample_data):
    result = top_fournisseurs_by_montant(sample_data, limit=5)
    assert len(result) == 2
    assert result.iloc[0]["fournisseur"] == "Fournisseur A"


def test_prix_moyen_par_matiere(sample_data):
    result = prix_moyen_par_matiere(sample_data)
    acier = result[result["type_matiere"] == "Acier"].iloc[0]
    # Weighted average: (10*100 + 12*200) / (100+200) = 3400/300 = 11.33
    assert abs(acier["prix_unitaire_moyen"] - 11.33) < 0.01


def test_ecarts_prix(sample_data):
    result = ecarts_prix_fournisseurs(sample_data)
    # Acier: A=10, B=12 → ecart = (12-10)/10 = 20%
    acier_row = result[result["type_matiere"] == "Acier"]
    assert len(acier_row) > 0


def test_fragmentation(sample_data):
    result = indice_fragmentation(sample_data)
    acier = result[result["type_matiere"] == "Acier"].iloc[0]
    assert acier["nb_fournisseurs"] == 2
    cuivre = result[result["type_matiere"] == "Cuivre"].iloc[0]
    assert cuivre["nb_fournisseurs"] == 1


def test_economie_potentielle(sample_data):
    result = economie_potentielle(sample_data)
    # Acier: best price=10, Fournisseur B pays 12 for 200 units → savings = (12-10)*200 = 400
    assert result["total_economie"] > 0
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest dashboard/tests/test_achats.py -v`
Expected: FAIL (ImportError)

**Step 3: Write achats.py**

Create `dashboard/analytics/achats.py`:

```python
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture, Fournisseur


def _lignes_avec_fournisseur(session: Session) -> pd.DataFrame:
    """Query all invoice lines joined with fournisseur info."""
    rows = (
        session.query(
            LigneFacture.type_matiere,
            LigneFacture.unite,
            LigneFacture.prix_unitaire,
            LigneFacture.quantite,
            LigneFacture.prix_total,
            LigneFacture.date_depart,
            Fournisseur.nom.label("fournisseur"),
            Document.date_document,
        )
        .join(Document, LigneFacture.document_id == Document.id)
        .join(Fournisseur, Document.fournisseur_id == Fournisseur.id)
        .filter(LigneFacture.type_matiere.isnot(None))
        .all()
    )
    return pd.DataFrame(rows, columns=[
        "type_matiere", "unite", "prix_unitaire", "quantite",
        "prix_total", "date_depart", "fournisseur", "date_document",
    ])


def top_fournisseurs_by_montant(session: Session, limit: int = 5) -> pd.DataFrame:
    """Top fournisseurs ranked by total montant HT."""
    rows = (
        session.query(
            Fournisseur.nom.label("fournisseur"),
            func.sum(Document.montant_ht).label("montant_total"),
            func.count(Document.id).label("nb_documents"),
        )
        .join(Document, Fournisseur.id == Document.fournisseur_id)
        .group_by(Fournisseur.nom)
        .order_by(func.sum(Document.montant_ht).desc())
        .limit(limit)
        .all()
    )
    return pd.DataFrame(rows, columns=["fournisseur", "montant_total", "nb_documents"])


def prix_moyen_par_matiere(session: Session) -> pd.DataFrame:
    """Weighted average unit price per material type."""
    df = _lignes_avec_fournisseur(session)
    df = df.dropna(subset=["prix_unitaire", "quantite"])

    result = (
        df.groupby("type_matiere")
        .apply(
            lambda g: pd.Series({
                "prix_unitaire_moyen": (g["prix_unitaire"] * g["quantite"]).sum() / g["quantite"].sum()
                if g["quantite"].sum() > 0 else 0,
                "quantite_totale": g["quantite"].sum(),
                "nb_lignes": len(g),
            }),
            include_groups=False,
        )
        .reset_index()
    )
    return result


def ecarts_prix_fournisseurs(session: Session, seuil: float = 0.15) -> pd.DataFrame:
    """Find materials with price variance > seuil across suppliers."""
    df = _lignes_avec_fournisseur(session)
    df = df.dropna(subset=["prix_unitaire"])

    grouped = (
        df.groupby(["type_matiere", "fournisseur"])["prix_unitaire"]
        .mean()
        .reset_index()
    )
    pivot = grouped.pivot(index="type_matiere", columns="fournisseur", values="prix_unitaire")

    results = []
    for matiere in pivot.index:
        prices = pivot.loc[matiere].dropna()
        if len(prices) < 2:
            continue
        min_p, max_p = prices.min(), prices.max()
        ecart = (max_p - min_p) / min_p if min_p > 0 else 0
        if ecart >= seuil:
            results.append({
                "type_matiere": matiere,
                "prix_min": min_p,
                "prix_max": max_p,
                "ecart_pct": ecart,
                "fournisseur_min": prices.idxmin(),
                "fournisseur_max": prices.idxmax(),
            })
    return pd.DataFrame(results)


def indice_fragmentation(session: Session) -> pd.DataFrame:
    """Number of distinct suppliers per material type."""
    df = _lignes_avec_fournisseur(session)
    result = (
        df.groupby("type_matiere")
        .agg(nb_fournisseurs=("fournisseur", "nunique"), nb_lignes=("fournisseur", "count"))
        .reset_index()
        .sort_values("nb_fournisseurs", ascending=False)
    )
    return result


def economie_potentielle(session: Session) -> dict:
    """Estimate savings if all purchases used the best price per material."""
    df = _lignes_avec_fournisseur(session)
    df = df.dropna(subset=["prix_unitaire", "quantite"])

    best_prices = df.groupby("type_matiere")["prix_unitaire"].min()

    savings_details = []
    total = 0.0
    for _, row in df.iterrows():
        best = best_prices.get(row["type_matiere"], row["prix_unitaire"])
        if row["prix_unitaire"] > best and row["quantite"]:
            saving = (row["prix_unitaire"] - best) * row["quantite"]
            total += saving
            savings_details.append({
                "type_matiere": row["type_matiere"],
                "fournisseur": row["fournisseur"],
                "prix_actuel": row["prix_unitaire"],
                "meilleur_prix": best,
                "quantite": row["quantite"],
                "economie": saving,
            })

    return {
        "total_economie": total,
        "details": pd.DataFrame(savings_details) if savings_details else pd.DataFrame(),
    }
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest dashboard/tests/test_achats.py -v`
Expected: 5 tests PASS

**Step 5: Commit**

```bash
git add dashboard/analytics/achats.py dashboard/tests/test_achats.py
git commit -m "feat: add purchasing rationalization analytics module"
```

---

## Task 5: Analytics — Anomalies Detection Engine

**Files:**
- Create: `dashboard/analytics/anomalies.py`
- Test: `dashboard/tests/test_anomalies.py`

**Step 1: Write the failing test**

Create `dashboard/tests/test_anomalies.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture, Anomalie
from dashboard.analytics.anomalies import run_anomaly_detection, get_anomaly_stats


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def data_with_anomalies(db_session):
    f = Fournisseur(nom="TestCo")
    db_session.add(f)
    db_session.flush()

    d = Document(fichier="test.pdf", type_document="facture", fournisseur_id=f.id,
                 montant_ht=1000, montant_ttc=1200, confiance_globale=0.4,
                 date_document="2024-01-15")
    db_session.add(d)
    db_session.flush()

    lignes = [
        # CALC_001: prix_total != prix_unitaire * quantite (100 != 10*9 = 90)
        LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="Acier",
                     prix_unitaire=10.0, quantite=9, prix_total=100.0),
        # DATE_001: date_arrivee before date_depart
        LigneFacture(document_id=d.id, ligne_numero=2, type_matiere="Cuivre",
                     prix_unitaire=20.0, quantite=5, prix_total=100.0,
                     date_depart="2024-01-10", date_arrivee="2024-01-05"),
        # Normal line
        LigneFacture(document_id=d.id, ligne_numero=3, type_matiere="Zinc",
                     prix_unitaire=15.0, quantite=10, prix_total=150.0),
    ]
    db_session.add_all(lignes)
    db_session.commit()
    return db_session


DEFAULT_RULES = [
    {"id": "CALC_001", "type": "coherence_calcul", "severite": "critique", "seuil_tolerance": 0.01},
    {"id": "DATE_001", "type": "date_invalide", "severite": "warning"},
    {"id": "CONF_001", "type": "qualite_donnees", "severite": "info", "seuil_confiance": 0.6},
]


def test_detects_calc_incoherence(data_with_anomalies):
    anomalies = run_anomaly_detection(data_with_anomalies, DEFAULT_RULES)
    calc_anomalies = [a for a in anomalies if a.regle_id == "CALC_001"]
    assert len(calc_anomalies) == 1


def test_detects_date_invalide(data_with_anomalies):
    anomalies = run_anomaly_detection(data_with_anomalies, DEFAULT_RULES)
    date_anomalies = [a for a in anomalies if a.regle_id == "DATE_001"]
    assert len(date_anomalies) == 1


def test_detects_low_confidence(data_with_anomalies):
    anomalies = run_anomaly_detection(data_with_anomalies, DEFAULT_RULES)
    conf_anomalies = [a for a in anomalies if a.regle_id == "CONF_001"]
    assert len(conf_anomalies) == 1  # document confiance 0.4 < 0.6


def test_anomaly_stats(data_with_anomalies):
    run_anomaly_detection(data_with_anomalies, DEFAULT_RULES)
    data_with_anomalies.commit()
    stats = get_anomaly_stats(data_with_anomalies)
    assert stats["total"] >= 3
    assert "critique" in stats["par_severite"]
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest dashboard/tests/test_anomalies.py -v`
Expected: FAIL (ImportError)

**Step 3: Write anomalies.py**

Create `dashboard/analytics/anomalies.py`:

```python
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture, Fournisseur, Anomalie


def _check_calc_coherence(session: Session, rule: dict) -> list[Anomalie]:
    """CALC_001: prix_unitaire * quantite != prix_total."""
    tolerance = rule.get("seuil_tolerance", 0.01)
    anomalies = []

    lignes = (
        session.query(LigneFacture)
        .filter(
            LigneFacture.prix_unitaire.isnot(None),
            LigneFacture.quantite.isnot(None),
            LigneFacture.prix_total.isnot(None),
        )
        .all()
    )

    for ligne in lignes:
        expected = ligne.prix_unitaire * ligne.quantite
        if ligne.prix_total == 0:
            continue
        ecart = abs(expected - ligne.prix_total) / abs(ligne.prix_total)
        if ecart > tolerance:
            anomalies.append(Anomalie(
                document_id=ligne.document_id,
                ligne_id=ligne.id,
                regle_id=rule["id"],
                type_anomalie=rule["type"],
                severite=rule["severite"],
                description=f"PU({ligne.prix_unitaire}) x Qté({ligne.quantite}) = {expected:.2f} != Total({ligne.prix_total})",
                valeur_attendue=f"{expected:.2f}",
                valeur_trouvee=f"{ligne.prix_total:.2f}",
            ))

    return anomalies


def _check_date_invalide(session: Session, rule: dict) -> list[Anomalie]:
    """DATE_001: date_arrivee < date_depart."""
    anomalies = []

    lignes = (
        session.query(LigneFacture)
        .filter(
            LigneFacture.date_depart.isnot(None),
            LigneFacture.date_arrivee.isnot(None),
        )
        .all()
    )

    for ligne in lignes:
        if ligne.date_arrivee < ligne.date_depart:
            anomalies.append(Anomalie(
                document_id=ligne.document_id,
                ligne_id=ligne.id,
                regle_id=rule["id"],
                type_anomalie=rule["type"],
                severite=rule["severite"],
                description=f"Date arrivée ({ligne.date_arrivee}) avant départ ({ligne.date_depart})",
                valeur_attendue=f">= {ligne.date_depart}",
                valeur_trouvee=ligne.date_arrivee,
            ))

    return anomalies


def _check_low_confidence(session: Session, rule: dict) -> list[Anomalie]:
    """CONF_001: document confidence below threshold."""
    seuil = rule.get("seuil_confiance", 0.6)
    anomalies = []

    docs = session.query(Document).filter(Document.confiance_globale < seuil).all()
    for doc in docs:
        anomalies.append(Anomalie(
            document_id=doc.id,
            regle_id=rule["id"],
            type_anomalie=rule["type"],
            severite=rule["severite"],
            description=f"Confiance globale {doc.confiance_globale:.2f} < seuil {seuil}",
            valeur_attendue=f">= {seuil}",
            valeur_trouvee=f"{doc.confiance_globale:.2f}",
        ))

    return anomalies


_RULE_HANDLERS = {
    "coherence_calcul": _check_calc_coherence,
    "date_invalide": _check_date_invalide,
    "qualite_donnees": _check_low_confidence,
}


def run_anomaly_detection(session: Session, rules: list[dict]) -> list[Anomalie]:
    """Run all anomaly rules and persist results. Returns list of new anomalies."""
    # Clear existing anomalies before re-running
    session.query(Anomalie).delete()

    all_anomalies = []
    for rule in rules:
        handler = _RULE_HANDLERS.get(rule["type"])
        if handler:
            new_anomalies = handler(session, rule)
            all_anomalies.extend(new_anomalies)

    session.add_all(all_anomalies)
    session.flush()
    return all_anomalies


def get_anomaly_stats(session: Session) -> dict:
    """Get summary statistics of detected anomalies."""
    total = session.query(Anomalie).count()

    par_severite = dict(
        session.query(Anomalie.severite, func.count(Anomalie.id))
        .group_by(Anomalie.severite)
        .all()
    )

    par_type = dict(
        session.query(Anomalie.type_anomalie, func.count(Anomalie.id))
        .group_by(Anomalie.type_anomalie)
        .all()
    )

    return {"total": total, "par_severite": par_severite, "par_type": par_type}
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest dashboard/tests/test_anomalies.py -v`
Expected: 4 tests PASS

**Step 5: Commit**

```bash
git add dashboard/analytics/anomalies.py dashboard/tests/test_anomalies.py
git commit -m "feat: add anomaly detection engine with configurable rules"
```

---

## Task 6: Analytics — Logistique, Tendances, Qualité

**Files:**
- Create: `dashboard/analytics/logistique.py`
- Create: `dashboard/analytics/tendances.py`
- Create: `dashboard/analytics/qualite.py`
- Test: `dashboard/tests/test_logistique.py`
- Test: `dashboard/tests/test_tendances.py`
- Test: `dashboard/tests/test_qualite.py`

**Step 1: Write failing tests for all three modules**

Create `dashboard/tests/test_logistique.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture
from dashboard.analytics.logistique import (
    top_routes,
    matrice_od,
    delai_moyen_livraison,
    opportunites_regroupement,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def logistics_data(db_session):
    f = Fournisseur(nom="Transport Co")
    db_session.add(f)
    db_session.flush()
    d = Document(fichier="t.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.9)
    db_session.add(d)
    db_session.flush()

    lignes = [
        LigneFacture(document_id=d.id, ligne_numero=1, type_matiere="Acier",
                     lieu_depart="Sorgues", lieu_arrivee="Kallo",
                     date_depart="2024-01-05", date_arrivee="2024-01-07",
                     prix_total=1620),
        LigneFacture(document_id=d.id, ligne_numero=2, type_matiere="Acier",
                     lieu_depart="Sorgues", lieu_arrivee="Kallo",
                     date_depart="2024-01-06", date_arrivee="2024-01-08",
                     prix_total=1620),
        LigneFacture(document_id=d.id, ligne_numero=3, type_matiere="Cuivre",
                     lieu_depart="Paris", lieu_arrivee="Lyon",
                     date_depart="2024-02-01", date_arrivee="2024-02-02",
                     prix_total=500),
    ]
    db_session.add_all(lignes)
    db_session.commit()
    return db_session


def test_top_routes(logistics_data):
    result = top_routes(logistics_data, limit=5)
    assert len(result) == 2
    assert result.iloc[0]["route"] == "Sorgues → Kallo"
    assert result.iloc[0]["nb_trajets"] == 2


def test_matrice_od(logistics_data):
    result = matrice_od(logistics_data)
    assert result.loc["Sorgues", "Kallo"] == 2


def test_delai_moyen(logistics_data):
    result = delai_moyen_livraison(logistics_data)
    assert result["delai_moyen_jours"] == 2.0  # all deliveries are 2 days


def test_regroupement(logistics_data):
    result = opportunites_regroupement(logistics_data, fenetre_jours=7)
    # Sorgues→Kallo has 2 trips within 7 days
    assert len(result) >= 1
    assert result.iloc[0]["nb_trajets_regroupables"] == 2
```

Create `dashboard/tests/test_tendances.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture
from dashboard.analytics.tendances import volume_mensuel, evolution_prix_matiere


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def temporal_data(db_session):
    f = Fournisseur(nom="F1")
    db_session.add(f)
    db_session.flush()

    for month in ["2024-01-15", "2024-02-15", "2024-03-15"]:
        d = Document(fichier=f"doc_{month}.pdf", type_document="facture",
                     fournisseur_id=f.id, date_document=month,
                     montant_ht=1000 * (int(month[5:7])), confiance_globale=0.9)
        db_session.add(d)
        db_session.flush()
        db_session.add(LigneFacture(
            document_id=d.id, ligne_numero=1, type_matiere="Acier",
            prix_unitaire=10.0 + int(month[5:7]), quantite=10, prix_total=100 + int(month[5:7]) * 10,
            date_depart=month,
        ))
    db_session.commit()
    return db_session


def test_volume_mensuel(temporal_data):
    result = volume_mensuel(temporal_data)
    assert len(result) == 3
    assert result.iloc[0]["montant_total"] > 0


def test_evolution_prix(temporal_data):
    result = evolution_prix_matiere(temporal_data, "Acier")
    assert len(result) == 3
    # Price increases each month (11, 12, 13)
    assert result.iloc[-1]["prix_unitaire_moyen"] > result.iloc[0]["prix_unitaire_moyen"]
```

Create `dashboard/tests/test_qualite.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Fournisseur, Document, LigneFacture
from dashboard.analytics.qualite import (
    score_global,
    confiance_par_champ,
    documents_par_qualite,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def quality_data(db_session):
    f = Fournisseur(nom="Q")
    db_session.add(f)
    db_session.flush()

    d1 = Document(fichier="good.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.95)
    d2 = Document(fichier="bad.pdf", type_document="facture", fournisseur_id=f.id, confiance_globale=0.4)
    db_session.add_all([d1, d2])
    db_session.flush()

    db_session.add(LigneFacture(
        document_id=d1.id, ligne_numero=1, type_matiere="X",
        conf_type_matiere=0.98, conf_prix_unitaire=0.95, conf_quantite=0.90,
    ))
    db_session.add(LigneFacture(
        document_id=d2.id, ligne_numero=1, type_matiere="Y",
        conf_type_matiere=0.5, conf_prix_unitaire=0.1, conf_quantite=0.2,
    ))
    db_session.commit()
    return db_session


def test_score_global(quality_data):
    result = score_global(quality_data)
    assert 0 < result["score_moyen"] < 1
    assert result["nb_documents"] == 2
    assert result["pct_fiables"] == 50.0  # 1 out of 2 above 0.8


def test_confiance_par_champ(quality_data):
    result = confiance_par_champ(quality_data)
    assert "type_matiere" in result.index
    assert result.loc["type_matiere", "moyenne"] > 0


def test_documents_par_qualite(quality_data):
    result = documents_par_qualite(quality_data)
    assert len(result) == 2
    assert result.iloc[0]["confiance_globale"] >= result.iloc[1]["confiance_globale"]
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest dashboard/tests/test_logistique.py dashboard/tests/test_tendances.py dashboard/tests/test_qualite.py -v`
Expected: All FAIL (ImportError)

**Step 3: Write logistique.py**

Create `dashboard/analytics/logistique.py`:

```python
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session

from dashboard.data.models import LigneFacture


def _lignes_logistiques(session: Session) -> pd.DataFrame:
    lignes = (
        session.query(
            LigneFacture.lieu_depart, LigneFacture.lieu_arrivee,
            LigneFacture.date_depart, LigneFacture.date_arrivee,
            LigneFacture.prix_total, LigneFacture.type_matiere,
            LigneFacture.quantite,
        )
        .filter(
            LigneFacture.lieu_depart.isnot(None),
            LigneFacture.lieu_arrivee.isnot(None),
        )
        .all()
    )
    return pd.DataFrame(lignes, columns=[
        "lieu_depart", "lieu_arrivee", "date_depart", "date_arrivee",
        "prix_total", "type_matiere", "quantite",
    ])


def top_routes(session: Session, limit: int = 5) -> pd.DataFrame:
    df = _lignes_logistiques(session)
    df["route"] = df["lieu_depart"] + " → " + df["lieu_arrivee"]
    result = (
        df.groupby("route")
        .agg(nb_trajets=("route", "count"), cout_total=("prix_total", "sum"))
        .reset_index()
        .sort_values("nb_trajets", ascending=False)
        .head(limit)
    )
    return result


def matrice_od(session: Session) -> pd.DataFrame:
    df = _lignes_logistiques(session)
    return pd.crosstab(df["lieu_depart"], df["lieu_arrivee"])


def delai_moyen_livraison(session: Session) -> dict:
    df = _lignes_logistiques(session)
    df = df.dropna(subset=["date_depart", "date_arrivee"])
    df["depart"] = pd.to_datetime(df["date_depart"])
    df["arrivee"] = pd.to_datetime(df["date_arrivee"])
    df["delai"] = (df["arrivee"] - df["depart"]).dt.days

    valid = df[df["delai"] >= 0]
    if valid.empty:
        return {"delai_moyen_jours": 0, "delai_median_jours": 0, "nb_trajets": 0}

    return {
        "delai_moyen_jours": valid["delai"].mean(),
        "delai_median_jours": valid["delai"].median(),
        "nb_trajets": len(valid),
    }


def opportunites_regroupement(session: Session, fenetre_jours: int = 7) -> pd.DataFrame:
    df = _lignes_logistiques(session)
    df = df.dropna(subset=["date_depart"])
    df["route"] = df["lieu_depart"] + " → " + df["lieu_arrivee"]
    df["depart"] = pd.to_datetime(df["date_depart"])

    results = []
    for route, group in df.groupby("route"):
        if len(group) < 2:
            continue
        group = group.sort_values("depart")
        dates = group["depart"].values
        # Count trips within fenetre_jours of each other
        clusters = []
        current_cluster = [dates[0]]
        for d in dates[1:]:
            if (d - current_cluster[0]) / pd.Timedelta(days=1) <= fenetre_jours:
                current_cluster.append(d)
            else:
                if len(current_cluster) >= 2:
                    clusters.append(current_cluster)
                current_cluster = [d]
        if len(current_cluster) >= 2:
            clusters.append(current_cluster)

        for cluster in clusters:
            results.append({
                "route": route,
                "nb_trajets_regroupables": len(cluster),
                "periode_debut": pd.Timestamp(cluster[0]),
                "periode_fin": pd.Timestamp(cluster[-1]),
            })

    return pd.DataFrame(results) if results else pd.DataFrame(
        columns=["route", "nb_trajets_regroupables", "periode_debut", "periode_fin"]
    )
```

**Step 4: Write tendances.py**

Create `dashboard/analytics/tendances.py`:

```python
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture, Fournisseur


def volume_mensuel(session: Session) -> pd.DataFrame:
    rows = (
        session.query(Document.date_document, Document.montant_ht)
        .filter(Document.date_document.isnot(None), Document.montant_ht.isnot(None))
        .all()
    )
    df = pd.DataFrame(rows, columns=["date_document", "montant_total"])
    df["date_document"] = pd.to_datetime(df["date_document"])
    df["mois"] = df["date_document"].dt.to_period("M")
    result = df.groupby("mois").agg(
        montant_total=("montant_total", "sum"),
        nb_documents=("montant_total", "count"),
    ).reset_index()
    result["mois"] = result["mois"].astype(str)
    return result


def evolution_prix_matiere(session: Session, type_matiere: str) -> pd.DataFrame:
    rows = (
        session.query(
            LigneFacture.date_depart,
            LigneFacture.prix_unitaire,
            LigneFacture.quantite,
        )
        .filter(
            LigneFacture.type_matiere == type_matiere,
            LigneFacture.date_depart.isnot(None),
            LigneFacture.prix_unitaire.isnot(None),
        )
        .all()
    )
    df = pd.DataFrame(rows, columns=["date_depart", "prix_unitaire", "quantite"])
    df["date_depart"] = pd.to_datetime(df["date_depart"])
    df["mois"] = df["date_depart"].dt.to_period("M")
    result = df.groupby("mois").agg(
        prix_unitaire_moyen=("prix_unitaire", "mean"),
        nb_lignes=("prix_unitaire", "count"),
    ).reset_index()
    result["mois"] = result["mois"].astype(str)
    return result
```

**Step 5: Write qualite.py**

Create `dashboard/analytics/qualite.py`:

```python
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.models import Document, LigneFacture


CONF_FIELDS = [
    "conf_type_matiere", "conf_unite", "conf_prix_unitaire", "conf_quantite",
    "conf_prix_total", "conf_date_depart", "conf_date_arrivee",
    "conf_lieu_depart", "conf_lieu_arrivee",
]

FIELD_NAMES = [f.replace("conf_", "") for f in CONF_FIELDS]


def score_global(session: Session, seuil_fiable: float = 0.8) -> dict:
    docs = session.query(Document.confiance_globale).all()
    scores = [d[0] for d in docs if d[0] is not None]
    if not scores:
        return {"score_moyen": 0, "nb_documents": 0, "pct_fiables": 0}

    nb_fiables = sum(1 for s in scores if s >= seuil_fiable)
    return {
        "score_moyen": sum(scores) / len(scores),
        "nb_documents": len(scores),
        "pct_fiables": (nb_fiables / len(scores)) * 100,
    }


def confiance_par_champ(session: Session) -> pd.DataFrame:
    results = {}
    for conf_field, field_name in zip(CONF_FIELDS, FIELD_NAMES):
        col = getattr(LigneFacture, conf_field)
        row = session.query(
            func.avg(col),
            func.min(col),
            func.max(col),
            func.count(col),
        ).filter(col.isnot(None)).one()
        results[field_name] = {
            "moyenne": row[0] or 0,
            "min": row[1] or 0,
            "max": row[2] or 0,
            "nb_valeurs": row[3] or 0,
        }
    return pd.DataFrame(results).T


def documents_par_qualite(session: Session) -> pd.DataFrame:
    rows = (
        session.query(
            Document.fichier, Document.confiance_globale,
            Document.strategie_utilisee, Document.format_pdf,
        )
        .order_by(Document.confiance_globale.desc())
        .all()
    )
    return pd.DataFrame(rows, columns=[
        "fichier", "confiance_globale", "strategie", "format_pdf",
    ])
```

**Step 6: Run all tests**

Run: `python -m pytest dashboard/tests/ -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add dashboard/analytics/ dashboard/tests/test_logistique.py dashboard/tests/test_tendances.py dashboard/tests/test_qualite.py
git commit -m "feat: add logistics, trends, and data quality analytics modules"
```

---

## Task 7: Redis Cache Wrapper

**Files:**
- Create: `dashboard/data/cache.py`
- Test: `dashboard/tests/test_cache.py`

**Step 1: Write the failing test**

Create `dashboard/tests/test_cache.py`:

```python
import pytest
from unittest.mock import MagicMock
from dashboard.data.cache import CacheManager


def test_cache_get_miss_calls_compute():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # cache miss

    cache = CacheManager(redis_client=mock_redis, ttl=3600)
    result = cache.get_or_compute("test_key", lambda: {"value": 42})

    assert result == {"value": 42}
    mock_redis.setex.assert_called_once()


def test_cache_get_hit_returns_cached():
    import json
    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps({"value": 42}).encode()

    cache = CacheManager(redis_client=mock_redis, ttl=3600)
    compute_called = False

    def compute():
        nonlocal compute_called
        compute_called = True
        return {"value": 99}

    result = cache.get_or_compute("test_key", compute)
    assert result == {"value": 42}
    assert not compute_called


def test_cache_invalidate():
    mock_redis = MagicMock()
    cache = CacheManager(redis_client=mock_redis, ttl=3600)
    cache.invalidate("some_key")
    mock_redis.delete.assert_called_once_with("rationalize:some_key")
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest dashboard/tests/test_cache.py -v`
Expected: FAIL (ImportError)

**Step 3: Write cache.py**

Create `dashboard/data/cache.py`:

```python
import json
import os
from typing import Any, Callable


class CacheManager:
    """Simple Redis cache wrapper with JSON serialization.
    Falls back to no-cache if Redis is unavailable."""

    PREFIX = "rationalize:"

    def __init__(self, redis_client=None, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl

    def _key(self, key: str) -> str:
        return f"{self.PREFIX}{key}"

    def get_or_compute(self, key: str, compute_fn: Callable[[], Any]) -> Any:
        if self.redis:
            cached = self.redis.get(self._key(key))
            if cached is not None:
                return json.loads(cached)

        result = compute_fn()

        if self.redis and result is not None:
            self.redis.setex(self._key(key), self.ttl, json.dumps(result, default=str))

        return result

    def invalidate(self, key: str):
        if self.redis:
            self.redis.delete(self._key(key))

    def invalidate_all(self):
        if self.redis:
            for key in self.redis.scan_iter(f"{self.PREFIX}*"):
                self.redis.delete(key)


def get_cache_manager() -> CacheManager:
    """Factory that creates a CacheManager, connecting to Redis if available."""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis
            client = redis.from_url(redis_url)
            client.ping()
            return CacheManager(redis_client=client)
        except Exception:
            pass
    return CacheManager(redis_client=None)
```

**Step 4: Run tests**

Run: `python -m pytest dashboard/tests/test_cache.py -v`
Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add dashboard/data/cache.py dashboard/tests/test_cache.py
git commit -m "feat: add Redis cache manager with fallback"
```

---

## Task 8: Streamlit UI Components

**Files:**
- Create: `dashboard/components/kpi_card.py`
- Create: `dashboard/components/filters.py`
- Create: `dashboard/components/charts.py`
- Create: `dashboard/components/data_table.py`

**Step 1: Write kpi_card.py**

Create `dashboard/components/kpi_card.py`:

```python
import streamlit as st


def kpi_card(label: str, value: str, delta: str | None = None, delta_color: str = "normal"):
    """Display a single KPI metric."""
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def kpi_row(metrics: list[dict]):
    """Display a row of KPI cards. Each dict has: label, value, delta (optional)."""
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            kpi_card(
                label=m["label"],
                value=m["value"],
                delta=m.get("delta"),
                delta_color=m.get("delta_color", "normal"),
            )
```

**Step 2: Write filters.py**

Create `dashboard/components/filters.py`:

```python
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session

from dashboard.data.models import Fournisseur, Document, LigneFacture


def sidebar_filters(session: Session) -> dict:
    """Render common sidebar filters and return selected values."""
    st.sidebar.header("Filtres")

    # Date range
    dates = session.query(Document.date_document).filter(
        Document.date_document.isnot(None)
    ).all()
    if dates:
        date_values = sorted([d[0] for d in dates if d[0]])
        if date_values:
            date_range = st.sidebar.date_input(
                "Période",
                value=(pd.to_datetime(date_values[0]), pd.to_datetime(date_values[-1])),
            )
        else:
            date_range = None
    else:
        date_range = None

    # Fournisseur
    fournisseurs = [f[0] for f in session.query(Fournisseur.nom).order_by(Fournisseur.nom).all()]
    selected_fournisseurs = st.sidebar.multiselect("Fournisseur", fournisseurs, default=fournisseurs)

    # Type matiere
    matieres = [m[0] for m in session.query(LigneFacture.type_matiere).distinct().filter(
        LigneFacture.type_matiere.isnot(None)
    ).all()]
    selected_matieres = st.sidebar.multiselect("Type matière", sorted(matieres), default=sorted(matieres))

    return {
        "date_range": date_range,
        "fournisseurs": selected_fournisseurs,
        "matieres": selected_matieres,
    }
```

**Step 3: Write charts.py**

Create `dashboard/components/charts.py`:

```python
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str, color: str | None = None, **kwargs):
    fig = px.bar(df, x=x, y=y, title=title, color=color, **kwargs)
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    return fig


def line_chart(df: pd.DataFrame, x: str, y: str, title: str, color: str | None = None, **kwargs):
    fig = px.line(df, x=x, y=y, title=title, color=color, markers=True, **kwargs)
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    return fig


def scatter_chart(df: pd.DataFrame, x: str, y: str, title: str, color: str | None = None, size: str | None = None, **kwargs):
    fig = px.scatter(df, x=x, y=y, title=title, color=color, size=size, **kwargs)
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    return fig


def radar_chart(categories: list[str], values: list[float], title: str):
    fig = go.Figure(data=go.Scatterpolar(
        r=values + [values[0]],  # close the polygon
        theta=categories + [categories[0]],
        fill="toself",
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        title=title,
        margin=dict(l=40, r=40, t=40, b=40),
    )
    return fig


def heatmap(df: pd.DataFrame, title: str):
    fig = px.imshow(df, title=title, text_auto=True, aspect="auto", color_continuous_scale="Blues")
    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20))
    return fig
```

**Step 4: Write data_table.py**

Create `dashboard/components/data_table.py`:

```python
import streamlit as st
import pandas as pd
import io


def data_table(df: pd.DataFrame, title: str | None = None, export: bool = True):
    """Display an interactive data table with optional CSV/Excel export."""
    if title:
        st.subheader(title)

    st.dataframe(df, use_container_width=True)

    if export and not df.empty:
        col1, col2 = st.columns(2)
        with col1:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Export CSV", csv, f"{title or 'data'}.csv", "text/csv")
        with col2:
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False, engine="openpyxl")
            st.download_button("Export Excel", buffer.getvalue(), f"{title or 'data'}.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
```

**Step 5: Commit**

```bash
git add dashboard/components/
git commit -m "feat: add reusable Streamlit UI components (KPI, filters, charts, tables)"
```

---

## Task 9: Streamlit Pages — App Entry Point + Tableau de Bord

**Files:**
- Create: `dashboard/app.py`
- Create: `dashboard/pages/01_tableau_de_bord.py`

**Step 1: Write app.py (main entry point)**

Create `dashboard/app.py`:

```python
import streamlit as st
import yaml
import os

from dashboard.data.db import init_db, get_engine, get_session

# Page config
st.set_page_config(
    page_title="Rationalize",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load config
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

# Init DB
engine = get_engine(config["database"]["url"])
init_db(engine)

# Store in session state
if "engine" not in st.session_state:
    st.session_state.engine = engine
    st.session_state.config = config

st.title("📊 Rationalize")
st.markdown("### Outil d'Analyse & Optimisation des Achats et Logistique")
st.markdown("---")
st.markdown("Utilisez le menu latéral pour naviguer entre les modules d'analyse.")
st.markdown("""
**Modules disponibles :**
- **Tableau de bord** — Vue exécutive avec KPIs globaux
- **Achats** — Rationalisation et benchmark fournisseurs
- **Logistique** — Optimisation des flux et regroupement
- **Anomalies** — Détection d'incohérences et doublons
- **Tendances** — Évolution temporelle des prix et volumes
- **Qualité** — Suivi de la qualité des données extraites
- **Admin** — Ingestion et configuration
""")
```

**Step 2: Write 01_tableau_de_bord.py**

Create `dashboard/pages/01_tableau_de_bord.py`:

```python
import streamlit as st
from sqlalchemy.orm import Session
from sqlalchemy import func

from dashboard.data.db import get_session
from dashboard.data.models import Document, LigneFacture, Fournisseur, Anomalie
from dashboard.analytics.achats import top_fournisseurs_by_montant
from dashboard.analytics.anomalies import get_anomaly_stats
from dashboard.analytics.qualite import score_global
from dashboard.analytics.logistique import delai_moyen_livraison
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import bar_chart

st.set_page_config(page_title="Tableau de bord", page_icon="🏠", layout="wide")
st.title("🏠 Tableau de bord")

engine = st.session_state.get("engine")
if not engine:
    st.error("Base de données non initialisée. Lancez l'application depuis app.py.")
    st.stop()

session = get_session(engine)

# --- KPIs Row 1: Overview ---
nb_docs = session.query(func.count(Document.id)).scalar()
nb_lignes = session.query(func.count(LigneFacture.id)).scalar()
nb_fournisseurs = session.query(func.count(Fournisseur.id)).scalar()
montant_total = session.query(func.sum(Document.montant_ht)).scalar() or 0

kpi_row([
    {"label": "Documents", "value": str(nb_docs)},
    {"label": "Lignes de facture", "value": str(nb_lignes)},
    {"label": "Fournisseurs", "value": str(nb_fournisseurs)},
    {"label": "Montant total HT", "value": f"{montant_total:,.2f} €"},
])

st.markdown("---")

# --- KPIs Row 2: Quality + Anomalies ---
quality = score_global(session)
anomaly_stats = get_anomaly_stats(session)
delai = delai_moyen_livraison(session)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Score qualité moyen", f"{quality['score_moyen']:.0%}")
with col2:
    st.metric("Docs fiables (>80%)", f"{quality['pct_fiables']:.0f}%")
with col3:
    st.metric("Anomalies détectées", str(anomaly_stats["total"]))
with col4:
    st.metric("Délai moyen livraison", f"{delai['delai_moyen_jours']:.1f} j")

st.markdown("---")

# --- Top Fournisseurs Chart ---
st.subheader("Top fournisseurs par montant")
top_f = top_fournisseurs_by_montant(session, limit=10)
if not top_f.empty:
    st.plotly_chart(bar_chart(top_f, x="fournisseur", y="montant_total",
                              title="Montant HT par fournisseur"), use_container_width=True)
else:
    st.info("Aucune donnée disponible. Importez des extractions via le module Admin.")

session.close()
```

**Step 3: Verify app starts without error**

Run: `cd /Users/fred/AI_Projects/swarm-pdf-extract && python -c "from dashboard.data.models import Base; print('OK')"`
Expected: "OK"

**Step 4: Commit**

```bash
git add dashboard/app.py dashboard/pages/01_tableau_de_bord.py
git commit -m "feat: add Streamlit app entry point and executive dashboard page"
```

---

## Task 10: Streamlit Pages — Achats + Anomalies

**Files:**
- Create: `dashboard/pages/02_achats.py`
- Create: `dashboard/pages/04_anomalies.py`

**Step 1: Write 02_achats.py**

Create `dashboard/pages/02_achats.py`:

```python
import streamlit as st
from dashboard.data.db import get_session
from dashboard.analytics.achats import (
    top_fournisseurs_by_montant, prix_moyen_par_matiere,
    ecarts_prix_fournisseurs, indice_fragmentation, economie_potentielle,
)
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import bar_chart, scatter_chart
from dashboard.components.data_table import data_table

st.set_page_config(page_title="Achats", page_icon="💰", layout="wide")
st.title("💰 Rationalisation Achats")

engine = st.session_state.get("engine")
if not engine:
    st.error("DB non initialisée.")
    st.stop()

session = get_session(engine)

# --- KPIs ---
top_f = top_fournisseurs_by_montant(session, limit=5)
fragmentation = indice_fragmentation(session)
eco = economie_potentielle(session)

nb_multi = len(fragmentation[fragmentation["nb_fournisseurs"] > 1]) if not fragmentation.empty else 0

kpi_row([
    {"label": "Fournisseurs actifs", "value": str(len(top_f))},
    {"label": "Matières multi-fournisseurs", "value": str(nb_multi)},
    {"label": "Économie potentielle", "value": f"{eco['total_economie']:,.2f} €"},
])

st.markdown("---")

# --- Top fournisseurs ---
tab1, tab2, tab3 = st.tabs(["Benchmark prix", "Fragmentation", "Écarts fournisseurs"])

with tab1:
    prix = prix_moyen_par_matiere(session)
    if not prix.empty:
        st.plotly_chart(bar_chart(prix, x="type_matiere", y="prix_unitaire_moyen",
                                  title="Prix unitaire moyen par matière"), use_container_width=True)
        data_table(prix, "Détail prix par matière")

with tab2:
    if not fragmentation.empty:
        data_table(fragmentation, "Indice de fragmentation fournisseurs")

with tab3:
    ecarts = ecarts_prix_fournisseurs(session)
    if not ecarts.empty:
        st.plotly_chart(bar_chart(ecarts, x="type_matiere", y="ecart_pct",
                                  title="Écarts de prix entre fournisseurs (%)"), use_container_width=True)
        data_table(ecarts, "Détail des écarts")
    else:
        st.info("Pas d'écart significatif détecté.")

# --- Savings details ---
if not eco["details"].empty:
    st.subheader("Détail des économies potentielles")
    data_table(eco["details"], "Économies par ligne")

session.close()
```

**Step 2: Write 04_anomalies.py**

Create `dashboard/pages/04_anomalies.py`:

```python
import streamlit as st
import yaml
import os
from dashboard.data.db import get_session
from dashboard.data.models import Anomalie, Document
from dashboard.analytics.anomalies import run_anomaly_detection, get_anomaly_stats
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import bar_chart
from dashboard.components.data_table import data_table
import pandas as pd

st.set_page_config(page_title="Anomalies", page_icon="⚠️", layout="wide")
st.title("⚠️ Détection d'Anomalies")

engine = st.session_state.get("engine")
config = st.session_state.get("config", {})
if not engine:
    st.error("DB non initialisée.")
    st.stop()

session = get_session(engine)

# Run detection button
if st.button("Relancer la détection d'anomalies"):
    rules = config.get("anomalies", {}).get("regles", [])
    with st.spinner("Analyse en cours..."):
        anomalies = run_anomaly_detection(session, rules)
        session.commit()
    st.success(f"{len(anomalies)} anomalies détectées.")

# --- Stats ---
stats = get_anomaly_stats(session)

kpi_row([
    {"label": "Total anomalies", "value": str(stats["total"])},
    {"label": "Critiques", "value": str(stats["par_severite"].get("critique", 0))},
    {"label": "Warnings", "value": str(stats["par_severite"].get("warning", 0))},
    {"label": "Info", "value": str(stats["par_severite"].get("info", 0))},
])

st.markdown("---")

# --- Anomaly list ---
anomalies = (
    session.query(
        Anomalie.regle_id, Anomalie.type_anomalie, Anomalie.severite,
        Anomalie.description, Document.fichier,
    )
    .join(Document, Anomalie.document_id == Document.id)
    .all()
)

if anomalies:
    df = pd.DataFrame(anomalies, columns=["Règle", "Type", "Sévérité", "Description", "Document"])

    # Filter
    severite_filter = st.multiselect("Filtrer par sévérité", ["critique", "warning", "info"],
                                     default=["critique", "warning", "info"])
    df_filtered = df[df["Sévérité"].isin(severite_filter)]

    # Chart
    type_counts = df_filtered["Type"].value_counts().reset_index()
    type_counts.columns = ["type", "count"]
    st.plotly_chart(bar_chart(type_counts, x="type", y="count",
                              title="Anomalies par type"), use_container_width=True)

    data_table(df_filtered, "Liste des anomalies")
else:
    st.info("Aucune anomalie détectée. Cliquez sur 'Relancer la détection' pour analyser.")

session.close()
```

**Step 3: Commit**

```bash
git add dashboard/pages/02_achats.py dashboard/pages/04_anomalies.py
git commit -m "feat: add purchasing rationalization and anomaly detection pages"
```

---

## Task 11: Streamlit Pages — Logistique + Tendances + Qualité

**Files:**
- Create: `dashboard/pages/03_logistique.py`
- Create: `dashboard/pages/05_tendances.py`
- Create: `dashboard/pages/06_qualite.py`

**Step 1: Write 03_logistique.py**

Create `dashboard/pages/03_logistique.py`:

```python
import streamlit as st
from dashboard.data.db import get_session
from dashboard.analytics.logistique import (
    top_routes, matrice_od, delai_moyen_livraison, opportunites_regroupement,
)
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import bar_chart, heatmap
from dashboard.components.data_table import data_table

st.set_page_config(page_title="Logistique", page_icon="🚛", layout="wide")
st.title("🚛 Optimisation Logistique")

engine = st.session_state.get("engine")
if not engine:
    st.error("DB non initialisée.")
    st.stop()

session = get_session(engine)

# --- KPIs ---
delai = delai_moyen_livraison(session)
routes = top_routes(session, limit=10)
regroupements = opportunites_regroupement(session, fenetre_jours=7)

kpi_row([
    {"label": "Routes distinctes", "value": str(len(routes))},
    {"label": "Délai moyen", "value": f"{delai['delai_moyen_jours']:.1f} jours"},
    {"label": "Trajets analysés", "value": str(delai["nb_trajets"])},
    {"label": "Regroupements possibles", "value": str(len(regroupements))},
])

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["Top Routes", "Matrice O/D", "Regroupements"])

with tab1:
    if not routes.empty:
        st.plotly_chart(bar_chart(routes, x="route", y="nb_trajets",
                                  title="Routes les plus fréquentes"), use_container_width=True)
        data_table(routes, "Détail des routes")

with tab2:
    od = matrice_od(session)
    if not od.empty:
        st.plotly_chart(heatmap(od, title="Matrice Origine / Destination"), use_container_width=True)

with tab3:
    if not regroupements.empty:
        data_table(regroupements, "Opportunités de regroupement")
    else:
        st.info("Pas d'opportunité de regroupement identifiée.")

session.close()
```

**Step 2: Write 05_tendances.py**

Create `dashboard/pages/05_tendances.py`:

```python
import streamlit as st
from dashboard.data.db import get_session
from dashboard.data.models import LigneFacture
from dashboard.analytics.tendances import volume_mensuel, evolution_prix_matiere
from dashboard.components.charts import bar_chart, line_chart
from dashboard.components.data_table import data_table

st.set_page_config(page_title="Tendances", page_icon="📈", layout="wide")
st.title("📈 Tendances Temporelles")

engine = st.session_state.get("engine")
if not engine:
    st.error("DB non initialisée.")
    st.stop()

session = get_session(engine)

# --- Volume mensuel ---
st.subheader("Volume d'achats mensuel")
vol = volume_mensuel(session)
if not vol.empty:
    st.plotly_chart(bar_chart(vol, x="mois", y="montant_total",
                              title="Montant HT mensuel"), use_container_width=True)

# --- Evolution prix par matière ---
st.subheader("Évolution des prix par matière")
matieres = [m[0] for m in session.query(LigneFacture.type_matiere).distinct().filter(
    LigneFacture.type_matiere.isnot(None)
).all()]

if matieres:
    selected = st.selectbox("Sélectionner une matière", sorted(matieres))
    if selected:
        evo = evolution_prix_matiere(session, selected)
        if not evo.empty:
            st.plotly_chart(line_chart(evo, x="mois", y="prix_unitaire_moyen",
                                       title=f"Prix unitaire moyen — {selected}"), use_container_width=True)
            data_table(evo, f"Détail prix — {selected}")
        else:
            st.info("Pas de données temporelles pour cette matière.")

session.close()
```

**Step 3: Write 06_qualite.py**

Create `dashboard/pages/06_qualite.py`:

```python
import streamlit as st
from dashboard.data.db import get_session
from dashboard.analytics.qualite import score_global, confiance_par_champ, documents_par_qualite
from dashboard.components.kpi_card import kpi_row
from dashboard.components.charts import radar_chart, bar_chart
from dashboard.components.data_table import data_table

st.set_page_config(page_title="Qualité", page_icon="🔍", layout="wide")
st.title("🔍 Qualité des Données")

engine = st.session_state.get("engine")
if not engine:
    st.error("DB non initialisée.")
    st.stop()

session = get_session(engine)

# --- KPIs ---
quality = score_global(session)

kpi_row([
    {"label": "Score moyen", "value": f"{quality['score_moyen']:.0%}"},
    {"label": "Documents analysés", "value": str(quality["nb_documents"])},
    {"label": "Docs fiables (>80%)", "value": f"{quality['pct_fiables']:.0f}%"},
])

st.markdown("---")

tab1, tab2 = st.tabs(["Confiance par champ", "Documents par qualité"])

with tab1:
    conf = confiance_par_champ(session)
    if not conf.empty:
        categories = conf.index.tolist()
        values = conf["moyenne"].tolist()
        st.plotly_chart(radar_chart(categories, values,
                                     title="Score de confiance moyen par champ"), use_container_width=True)
        data_table(conf.reset_index().rename(columns={"index": "champ"}), "Détail confiance par champ")

with tab2:
    docs = documents_par_qualite(session)
    if not docs.empty:
        st.plotly_chart(bar_chart(docs, x="fichier", y="confiance_globale",
                                  title="Confiance globale par document"), use_container_width=True)
        data_table(docs, "Documents triés par qualité")

session.close()
```

**Step 4: Commit**

```bash
git add dashboard/pages/03_logistique.py dashboard/pages/05_tendances.py dashboard/pages/06_qualite.py
git commit -m "feat: add logistics, trends, and data quality dashboard pages"
```

---

## Task 12: Admin Page (Ingestion + Config)

**Files:**
- Create: `dashboard/pages/07_admin.py`

**Step 1: Write 07_admin.py**

Create `dashboard/pages/07_admin.py`:

```python
import streamlit as st
import os
from dashboard.data.db import get_session, init_db
from dashboard.data.ingestion import ingest_directory
from dashboard.data.models import Document, LigneFacture, Fournisseur, Anomalie
from sqlalchemy import func

st.set_page_config(page_title="Administration", page_icon="⚙️", layout="wide")
st.title("⚙️ Administration")

engine = st.session_state.get("engine")
config = st.session_state.get("config", {})
if not engine:
    st.error("DB non initialisée.")
    st.stop()

session = get_session(engine)

# --- Ingestion ---
st.subheader("Ingestion des données")

extractions_dir = config.get("ingestion", {}).get("extractions_dir", "../output/extractions")
# Resolve relative to dashboard dir
abs_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", extractions_dir))

st.text(f"Répertoire source : {abs_dir}")

if st.button("Lancer l'ingestion"):
    if os.path.isdir(abs_dir):
        with st.spinner("Ingestion en cours..."):
            stats = ingest_directory(session, abs_dir)
        st.success(f"Ingestion terminée : {stats['ingested']} importés, {stats['skipped']} déjà présents, {stats['errors']} erreurs.")
        if stats["files"]:
            st.json(stats["files"])
    else:
        st.error(f"Répertoire introuvable : {abs_dir}")

st.markdown("---")

# --- DB Stats ---
st.subheader("État de la base de données")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Documents", session.query(func.count(Document.id)).scalar())
with col2:
    st.metric("Lignes", session.query(func.count(LigneFacture.id)).scalar())
with col3:
    st.metric("Fournisseurs", session.query(func.count(Fournisseur.id)).scalar())
with col4:
    st.metric("Anomalies", session.query(func.count(Anomalie.id)).scalar())

st.markdown("---")

# --- Reset DB ---
st.subheader("Maintenance")
if st.button("Réinitialiser la base de données", type="secondary"):
    from dashboard.data.models import Base
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    st.success("Base de données réinitialisée.")
    st.rerun()

session.close()
```

**Step 2: Commit**

```bash
git add dashboard/pages/07_admin.py
git commit -m "feat: add admin page with ingestion and DB management"
```

---

## Task 13: Docker Configuration

**Files:**
- Create: `dashboard/Dockerfile`
- Modify: `docker-compose.yml`

**Step 1: Write Dockerfile**

Create `dashboard/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

**Step 2: Update docker-compose.yml**

Add dashboard and redis services to the existing `docker-compose.yml` (append after the paddleocr service):

```yaml
  dashboard:
    build: ./dashboard
    ports:
      - "8501:8501"
    volumes:
      - ./output:/app/../output:ro
      - dashboard_data:/app/data
    environment:
      - DATABASE_URL=sqlite:///data/rationalize.db
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  redis_data:
  dashboard_data:
```

**Step 3: Commit**

```bash
git add dashboard/Dockerfile docker-compose.yml
git commit -m "feat: add Docker config for dashboard and Redis"
```

---

## Task 14: Integration Test — Full Pipeline

**Files:**
- Create: `dashboard/tests/test_integration.py`

**Step 1: Write integration test**

Create `dashboard/tests/test_integration.py`:

```python
"""Integration test: ingest real extraction JSONs → run analytics → verify outputs."""
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dashboard.data.models import Base, Document, LigneFacture, Fournisseur
from dashboard.data.ingestion import ingest_extraction_json
from dashboard.analytics.achats import top_fournisseurs_by_montant, economie_potentielle
from dashboard.analytics.anomalies import run_anomaly_detection, get_anomaly_stats
from dashboard.analytics.logistique import top_routes, delai_moyen_livraison
from dashboard.analytics.qualite import score_global, confiance_par_champ


SAMPLE_1 = {
    "fichier": "Facture_A.pdf",
    "type_document": "facture",
    "strategie_utilisee": "pdfplumber_tables",
    "metadonnees": {
        "numero_document": "A-001",
        "date_document": "2024-01-15",
        "fournisseur": {"nom": "Alpha Transport", "adresse": "Paris", "siret": None, "tva_intra": None},
        "client": {"nom": "Client X", "adresse": "Lyon"},
        "montant_ht": 5000, "montant_tva": 1000, "montant_ttc": 6000,
        "devise": "EUR", "conditions_paiement": "30j",
        "references": {"commande": "CMD-1", "contrat": None, "bon_livraison": None},
    },
    "lignes": [
        {"ligne_numero": 1, "type_matiere": "Acier", "unite": "t", "prix_unitaire": 500,
         "quantite": 10, "prix_total": 5000, "date_depart": "2024-01-10", "date_arrivee": "2024-01-12",
         "lieu_depart": "Paris", "lieu_arrivee": "Lyon",
         "confiance": {"type_matiere": 0.95, "unite": 0.9, "prix_unitaire": 0.98,
                       "quantite": 0.98, "prix_total": 0.99, "date_depart": 0.9,
                       "date_arrivee": 0.9, "lieu_depart": 0.95, "lieu_arrivee": 0.95}},
    ],
    "confiance_globale": 0.95,
    "champs_manquants": [],
    "warnings": [],
}

SAMPLE_2 = {
    "fichier": "Facture_B.pdf",
    "type_document": "facture",
    "strategie_utilisee": "ocr_tesseract",
    "metadonnees": {
        "numero_document": "B-001",
        "date_document": "2024-02-20",
        "fournisseur": {"nom": "Beta Logistics", "adresse": "Marseille", "siret": None, "tva_intra": None},
        "client": {"nom": "Client X", "adresse": "Lyon"},
        "montant_ht": 3000, "montant_tva": 600, "montant_ttc": 3600,
        "devise": "EUR", "conditions_paiement": "60j",
        "references": {"commande": "CMD-2", "contrat": None, "bon_livraison": None},
    },
    "lignes": [
        {"ligne_numero": 1, "type_matiere": "Acier", "unite": "t", "prix_unitaire": 600,
         "quantite": 5, "prix_total": 3000, "date_depart": "2024-02-15", "date_arrivee": "2024-02-18",
         "lieu_depart": "Marseille", "lieu_arrivee": "Lyon",
         "confiance": {"type_matiere": 0.7, "unite": 0.5, "prix_unitaire": 0.3,
                       "quantite": 0.4, "prix_total": 0.3, "date_depart": 0.6,
                       "date_arrivee": 0.6, "lieu_depart": 0.7, "lieu_arrivee": 0.7}},
    ],
    "confiance_globale": 0.45,
    "champs_manquants": [],
    "warnings": ["OCR quality poor on price columns"],
}


@pytest.fixture
def full_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ingest_extraction_json(session, SAMPLE_1)
        ingest_extraction_json(session, SAMPLE_2)
        session.commit()
        yield session
    Base.metadata.drop_all(engine)


def test_full_pipeline_achats(full_db):
    top = top_fournisseurs_by_montant(full_db, limit=5)
    assert len(top) == 2
    eco = economie_potentielle(full_db)
    # Alpha=500/t, Beta=600/t → savings on Beta's 5t = (600-500)*5 = 500
    assert eco["total_economie"] == 500.0


def test_full_pipeline_anomalies(full_db):
    rules = [
        {"id": "CONF_001", "type": "qualite_donnees", "severite": "info", "seuil_confiance": 0.6},
    ]
    anomalies = run_anomaly_detection(full_db, rules)
    full_db.commit()
    # SAMPLE_2 has confiance 0.45 < 0.6
    assert len(anomalies) == 1
    stats = get_anomaly_stats(full_db)
    assert stats["total"] == 1


def test_full_pipeline_logistique(full_db):
    routes = top_routes(full_db, limit=5)
    assert len(routes) == 2  # Paris→Lyon, Marseille→Lyon
    delai = delai_moyen_livraison(full_db)
    assert delai["nb_trajets"] == 2


def test_full_pipeline_qualite(full_db):
    quality = score_global(full_db)
    assert quality["nb_documents"] == 2
    assert quality["pct_fiables"] == 50.0  # 1 of 2 above 0.8

    conf = confiance_par_champ(full_db)
    assert not conf.empty
```

**Step 2: Run integration tests**

Run: `python -m pytest dashboard/tests/test_integration.py -v`
Expected: 4 tests PASS

**Step 3: Commit**

```bash
git add dashboard/tests/test_integration.py
git commit -m "test: add full pipeline integration tests"
```

---

## Task 15: Run All Tests + Final Verification

**Step 1: Run the complete test suite**

Run: `cd /Users/fred/AI_Projects/swarm-pdf-extract && python -m pytest dashboard/tests/ -v --tb=short`
Expected: All tests PASS (approximately 20+ tests)

**Step 2: Verify Streamlit app launches**

Run: `cd /Users/fred/AI_Projects/swarm-pdf-extract && timeout 10 streamlit run dashboard/app.py --server.headless true 2>&1 | head -5`
Expected: Streamlit starts on port 8501 without errors

**Step 3: Final commit with all remaining files**

```bash
git add -A dashboard/
git commit -m "feat: complete Rationalize dashboard v1 — all modules functional"
```

---

## Summary of Tasks

| # | Task | Files | Tests |
|---|------|-------|-------|
| 1 | Scaffolding | config, requirements, dirs | — |
| 2 | SQLAlchemy models | models.py, db.py | 4 tests |
| 3 | Ingestion pipeline | ingestion.py | 4 tests |
| 4 | Analytics: Achats | achats.py | 5 tests |
| 5 | Analytics: Anomalies | anomalies.py | 4 tests |
| 6 | Analytics: Logistique + Tendances + Qualité | 3 files | 9 tests |
| 7 | Redis cache | cache.py | 3 tests |
| 8 | UI components | 4 files | — |
| 9 | App + Tableau de bord page | 2 files | — |
| 10 | Achats + Anomalies pages | 2 files | — |
| 11 | Logistique + Tendances + Qualité pages | 3 files | — |
| 12 | Admin page | 1 file | — |
| 13 | Docker config | Dockerfile + compose | — |
| 14 | Integration tests | 1 file | 4 tests |
| 15 | Final verification | — | run all |

**Total: ~29 tests, ~25 files, 15 commits**
