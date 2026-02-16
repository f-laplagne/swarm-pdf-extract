# 🐝 Swarm Claude Code — POC Extraction PDF Multi-Format

## Vision

Architecture **multi-agents orchestrée** utilisant Claude Code en mode swarm pour évaluer les capacités d'extraction d'information à partir de ~100 documents PDF hétérogènes (factures, BL, devis, etc.).

**Objectif du pilote** : Définir les possibilités et les défis pour aider un architecte de solution à établir une méthode, les outils nécessaires, la durée et le budget d'une mission d'expertise.

---

## Architecture Swarm

```
                    ┌─────────────────────────────┐
                    │      🎯 ORCHESTRATOR         │
                    │   (orchestrator.md)           │
                    │   Coordination & Dispatch     │
                    └──────────┬──────────────────┘
                               │
            ┌──────────────────┼──────────────────────┐
            │                  │                       │
            ▼                  ▼                       ▼
  ┌─────────────────┐ ┌───────────────┐ ┌──────────────────────┐
  │ 📄 CLASSIFIER   │ │ 🔍 EXTRACTOR │ │ 📊 ANALYZER          │
  │ (classifier.md) │ │(extractor.md) │ │ (analyzer.md)        │
  │                  │ │               │ │                      │
  │ • Détecte type   │ │ • Extraction  │ │ • Qualité données    │
  │   de document    │ │   structurée  │ │ • Patterns détectés  │
  │ • Format PDF     │ │ • Multi-strat │ │ • Anomalies          │
  │ • Langue         │ │   (text/table │ │ • Statistiques       │
  │ • Complexité     │ │    /OCR/LLM)  │ │ • Scoring confiance  │
  └────────┬─────────┘ └──────┬────────┘ └──────────┬───────────┘
           │                  │                      │
           ▼                  ▼                      ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                   💾 OUTPUT LAYER                            │
  │  output/extractions/  output/analyses/  output/reports/      │
  │  (JSON structurés)    (scoring)         (synthèse finale)    │
  └─────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                  📋 REPORTER                                 │
  │                 (reporter.md)                                 │
  │  Synthèse finale : faisabilité, méthode, outils, budget     │
  └─────────────────────────────────────────────────────────────┘
```

---

## Démarrage Rapide

### Prérequis

```bash
# Claude Code installé (npm)
npm install -g @anthropic-ai/claude-code

# Python 3.11+ avec les dépendances
pip install -r requirements.txt
```

### Utilisation

```bash
# 1. Placer vos PDFs dans samples/
cp vos-factures/*.pdf samples/

# 2. Lancer l'orchestrateur depuis Claude Code
cd swarm-pdf-extract
claude

# 3. Dans Claude Code, charger le prompt orchestrateur :
# > Lis le fichier CLAUDE.md et exécute le workflow complet sur les PDFs dans samples/
```

### Workflow pas-à-pas (manuel)

```bash
# Étape 1 : Classification de tous les PDFs
# > Exécute le rôle de classifier (prompts/classifier.md) sur chaque PDF dans samples/

# Étape 2 : Extraction des données structurées  
# > Exécute le rôle d'extractor (prompts/extractor.md) en utilisant les résultats de classification

# Étape 3 : Analyse qualité et patterns
# > Exécute le rôle d'analyzer (prompts/analyzer.md) sur toutes les extractions

# Étape 4 : Rapport de synthèse
# > Exécute le rôle de reporter (prompts/reporter.md) pour le rapport final
```

---

## Structure du Projet

```
swarm-pdf-extract/
├── CLAUDE.md                  # 🧠 Prompt système principal (orchestrateur)
├── README.md                  # Ce fichier
├── requirements.txt           # Dépendances Python
├── pyproject.toml             # Config projet Python
│
├── prompts/                   # 🎭 Prompts des agents spécialisés
│   ├── classifier.md          #   Agent de classification
│   ├── extractor.md           #   Agent d'extraction
│   ├── analyzer.md            #   Agent d'analyse qualité
│   └── reporter.md            #   Agent de synthèse/rapport
│
├── schemas/                   # 📐 Schémas de données JSON
│   ├── classification.json    #   Schéma de classification doc
│   ├── extraction.json        #   Schéma d'extraction facture
│   └── analysis.json          #   Schéma d'analyse qualité
│
├── tools/                     # 🔧 Scripts Python utilitaires
│   ├── pdf_reader.py          #   Lecture multi-stratégie PDF
│   ├── table_extractor.py     #   Extraction de tableaux
│   ├── ocr_processor.py       #   OCR pour PDFs scannés
│   ├── json_validator.py      #   Validation des sorties JSON
│   └── batch_runner.py        #   Exécution batch sur N fichiers
│
├── scripts/                   # 🚀 Scripts d'orchestration
│   ├── run_pipeline.sh        #   Pipeline complet
│   ├── run_classification.sh  #   Classification seule
│   └── run_extraction.sh      #   Extraction seule
│
├── config/                    # ⚙️ Configuration
│   └── settings.yaml          #   Paramètres du POC
│
├── samples/                   # 📁 PDFs d'entrée (vos factures ici)
│   └── .gitkeep
│
├── output/                    # 📤 Résultats produits
│   ├── extractions/           #   JSON extraits par document
│   ├── analyses/              #   Rapports d'analyse
│   └── reports/               #   Rapport de synthèse final
│
└── tests/                     # ✅ Tests de validation
    ├── test_extraction.py     #   Tests d'extraction
    └── test_schemas.py        #   Tests de conformité schéma
```

---

## Champs Cibles (Factures)

| Champ | Description | Exemple |
|-------|-------------|---------|
| `type_matiere` | Type de matière / pièce | "Acier inox 304L", "Tube cuivre" |
| `unite` | Unité de mesure | "kg", "mètre", "pièce", "lot" |
| `prix_unitaire` | Prix unitaire HT | 12.50 |
| `quantite` | Quantité | 100 |
| `prix_total` | Prix total ligne HT | 1250.00 |
| `date_depart` | Date de départ / expédition | "2025-01-15" |
| `date_arrivee` | Date d'arrivée / livraison | "2025-01-17" |
| `lieu_depart` | Lieu de départ | "Usine Lyon" |
| `lieu_arrivee` | Lieu d'arrivée / livraison | "Chantier Bordeaux" |

---

## Métriques du POC

Le rapport final évalue :

1. **Taux d'extraction** — % de champs extraits avec succès par type de document
2. **Score de confiance** — Confiance moyenne par champ (0-1)
3. **Couverture formats** — Nombre de formats PDF différents traités
4. **Défis identifiés** — Catalogue des problèmes rencontrés
5. **Recommandations** — Méthode, outils et budget pour industrialisation
