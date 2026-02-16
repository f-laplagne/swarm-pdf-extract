# Design : Outil d'Analyse & Rationalisation/Optimisation

**Date** : 2026-02-16
**Statut** : Validé
**Auteur** : Claude (brainstorming collaboratif)

## 1. Contexte & Objectif

Le projet swarm-pdf-extract extrait des données structurées depuis des PDFs hétérogènes (factures, BL, devis) via un pipeline multi-agents. Les données extraites (9 champs par ligne : matière, unité, prix, quantité, dates, lieux + métadonnées fournisseur/client + scores de confiance) constituent une base exploitable pour de l'analyse décisionnelle.

**Objectif** : Construire un dashboard web interactif permettant :
- La rationalisation des achats (benchmark fournisseurs, consolidation, dérives tarifaires)
- L'optimisation logistique (flux, regroupement, coûts trajets)
- La détection d'anomalies (incohérences, doublons, surfacturations)
- L'analyse de tendances temporelles (volumes, prix, saisonnalité)
- Le suivi de qualité des données extraites (confiance, couverture)

**Utilisateurs cibles** :
- Décideurs / CTO : vue exécutive KPIs, alertes, tendances macro
- Analystes / Contrôleurs : exploration détaillée, filtres, drill-down, export

**Volume cible** : 10 000+ documents/an (architecture scalable requise)

## 2. Approche retenue

**Streamlit + SQLite (→ PostgreSQL) + Redis**

Raisons du choix :
- Cohérence avec l'écosystème Python existant du pipeline d'extraction
- Time-to-value le plus court pour un POC fonctionnel
- Chemin d'évolution clair : SQLite → PostgreSQL, Streamlit → Next.js si besoin
- Redis pour cacher les agrégations lourdes sur volumes importants

Approches écartées :
- Next.js + PostgreSQL : trop long pour le POC, double stack
- Marimo + DuckDB : pas adapté multi-utilisateur

## 3. Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit App                       │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ Vue Exec │  │ Vue Ana- │  │  Vue Qualité      │  │
│  │ (KPIs)   │  │ lytique  │  │  Données          │  │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────┘  │
│       └──────────────┼─────────────────┘             │
│                      ▼                               │
│            ┌─────────────────┐                       │
│            │  Service Layer  │                       │
│            │  (analytics/)   │                       │
│            └────────┬────────┘                       │
│                     ▼                                │
│       ┌─────────────┴─────────────┐                  │
│       │  Redis Cache              │                  │
│       └─────────────┬─────────────┘                  │
│                     ▼                                │
│            ┌─────────────────┐                       │
│            │  SQLite / Pg    │                       │
│            │  (data store)   │                       │
│            └────────┬────────┘                       │
└─────────────────────┼───────────────────────────────┘
                      ▲
          ┌───────────┴──────────┐
          │  Ingestion Pipeline  │
          │  (JSON → DB loader)  │
          └───────────┬──────────┘
                      ▲
        ┌─────────────┴─────────────┐
        │  output/extractions/*.json │
        │  (from swarm-pdf-extract)  │
        └───────────────────────────┘
```

## 4. Modèle de données

### Table `fournisseurs`

| Colonne | Type | Description |
|---------|------|-------------|
| id | INTEGER PK | Identifiant auto |
| nom | TEXT NOT NULL | Nom du fournisseur |
| adresse | TEXT | Adresse complète |
| siret | TEXT | Numéro SIRET |
| tva_intra | TEXT | Numéro TVA intracommunautaire |

### Table `documents`

| Colonne | Type | Description |
|---------|------|-------------|
| id | INTEGER PK | Identifiant auto |
| fichier | TEXT NOT NULL UNIQUE | Nom du fichier source |
| type_document | TEXT | facture, bon_livraison, devis... |
| format_pdf | TEXT | text_native, scanned, mixed, form |
| fournisseur_id | INTEGER FK | Référence fournisseur |
| client_nom | TEXT | Nom du client |
| client_adresse | TEXT | Adresse du client |
| date_document | DATE | Date du document |
| numero_document | TEXT | Numéro de facture/BL |
| montant_ht | REAL | Montant HT total |
| montant_tva | REAL | Montant TVA |
| montant_ttc | REAL | Montant TTC |
| devise | TEXT DEFAULT 'EUR' | Devise |
| conditions_paiement | TEXT | Conditions de paiement |
| ref_commande | TEXT | Référence commande |
| ref_contrat | TEXT | Référence contrat |
| ref_bon_livraison | TEXT | Référence BL |
| confiance_globale | REAL | Score confiance 0-1 |
| strategie_utilisee | TEXT | Stratégie d'extraction |
| complexite | INTEGER | Complexité 1-5 |
| date_ingestion | DATETIME | Date d'import dans le dashboard |

### Table `lignes_facture`

| Colonne | Type | Description |
|---------|------|-------------|
| id | INTEGER PK | Identifiant auto |
| document_id | INTEGER FK | Référence document |
| ligne_numero | INTEGER | Numéro de ligne |
| type_matiere | TEXT | Type de matière / description |
| unite | TEXT | Unité de mesure normalisée |
| prix_unitaire | REAL | Prix unitaire HT |
| quantite | REAL | Quantité |
| prix_total | REAL | Prix total ligne HT |
| date_depart | DATE | Date de départ |
| date_arrivee | DATE | Date d'arrivée |
| lieu_depart | TEXT | Lieu de départ |
| lieu_arrivee | TEXT | Lieu d'arrivée |
| conf_type_matiere | REAL | Confiance type_matiere |
| conf_unite | REAL | Confiance unité |
| conf_prix_unitaire | REAL | Confiance prix unitaire |
| conf_quantite | REAL | Confiance quantité |
| conf_prix_total | REAL | Confiance prix total |
| conf_date_depart | REAL | Confiance date départ |
| conf_date_arrivee | REAL | Confiance date arrivée |
| conf_lieu_depart | REAL | Confiance lieu départ |
| conf_lieu_arrivee | REAL | Confiance lieu arrivée |

### Table `anomalies`

| Colonne | Type | Description |
|---------|------|-------------|
| id | INTEGER PK | Identifiant auto |
| document_id | INTEGER FK | Référence document |
| ligne_id | INTEGER FK NULL | Référence ligne (si applicable) |
| regle_id | TEXT | Identifiant de la règle déclenchée |
| type_anomalie | TEXT | coherence_calcul, prix_anormal, doublon, date_invalide, qualite_donnees |
| severite | TEXT | critique, warning, info |
| description | TEXT | Description humaine |
| valeur_attendue | TEXT | Ce qu'on attendait |
| valeur_trouvee | TEXT | Ce qu'on a trouvé |
| date_detection | DATETIME | Date de détection |

### Index recommandés

```sql
CREATE INDEX idx_lignes_document ON lignes_facture(document_id);
CREATE INDEX idx_lignes_matiere ON lignes_facture(type_matiere);
CREATE INDEX idx_lignes_dates ON lignes_facture(date_depart, date_arrivee);
CREATE INDEX idx_lignes_lieux ON lignes_facture(lieu_depart, lieu_arrivee);
CREATE INDEX idx_documents_fournisseur ON documents(fournisseur_id);
CREATE INDEX idx_documents_date ON documents(date_document);
CREATE INDEX idx_anomalies_document ON anomalies(document_id);
CREATE INDEX idx_anomalies_type ON anomalies(type_anomalie);
```

## 5. Modules d'analyse

### Module 1 — Rationalisation Achats

**Vue exécutive :**
- Top 5 fournisseurs par montant total
- Prix unitaire moyen par type de matière (benchmark)
- Alerte : écarts de prix > 15% pour une même matière entre fournisseurs

**Vue analytique :**
- Tableau comparatif fournisseur x matière x prix unitaire
- Évolution du prix unitaire dans le temps (courbe par matière)
- Scatter plot : prix unitaire vs quantité (détecter les remises volume)
- Filtres : période, fournisseur, type matière, unité
- Export CSV des données filtrées

**Métriques de rationalisation :**
- Indice de fragmentation : nombre de fournisseurs par matière (> 1 = opportunité)
- Économie potentielle : (prix_actuel - meilleur_prix) x quantité_totale par matière
- Score de négociation : écart-type des prix par matière (élevé = marge de négo)

### Module 2 — Optimisation Logistique

**Vue exécutive :**
- Carte des flux principaux (lieu_depart → lieu_arrivee) avec épaisseur = volume
- Top 5 routes les plus fréquentes
- Délai moyen de livraison (date_arrivee - date_depart)

**Vue analytique :**
- Matrice origine/destination avec volumes et coûts
- Timeline des livraisons (Gantt) pour détecter les regroupements possibles
- Analyse de fréquence : livraisons multiples même jour/semaine sur même route
- Simulation : "si on regroupe les livraisons de la même semaine/route, on économise X trajets"

**Métriques d'optimisation :**
- Taux de remplissage : quantité par trajet vs capacité estimée
- Indice de regroupement : livraisons même route/même semaine regroupables
- Coût par km estimé : prix_total / distance_estimée (si geocoding)

### Module 3 — Détection d'Anomalies

**Vue exécutive :**
- Compteur d'anomalies par sévérité (critique / warning / info)
- Taux d'anomalies par fournisseur
- Top anomalies récurrentes

**Vue analytique :**
- Liste détaillée avec filtre par type
- Drill-down vers le document source

**Règles de détection (extensibles via config.yaml) :**

| ID | Nom | Type | Sévérité | Condition |
|----|-----|------|----------|-----------|
| CALC_001 | Incohérence prix x quantité | coherence_calcul | critique | abs(PU * Q - PT) / PT > 1% |
| PRIX_001 | Surfacturation potentielle | prix_anormal | warning | PU > 2x moyenne historique matière |
| DUP_001 | Doublon potentiel | doublon | critique | même fournisseur + même montant + delta < 7j |
| DATE_001 | Date arrivée avant départ | date_invalide | warning | date_arrivee < date_depart |
| CONF_001 | Extraction faible confiance | qualite_donnees | info | confiance_globale < 0.6 |
| PRIX_002 | Dérive tarifaire | prix_anormal | warning | variation > 20% sur 3 mois pour même matière |
| MANQ_001 | Prix manquant | donnees_manquantes | warning | prix_unitaire IS NULL AND confiance > 0.3 |

### Module 4 — Tendances Temporelles

**Vue exécutive :**
- Volume d'achats mensuel (barres) + tendance (ligne)
- Inflation prix matières (% variation mois/mois)
- Saisonnalité détectée (pics de commandes)

**Vue analytique :**
- Courbes empilées par fournisseur ou matière
- Comparaison période N vs N-1
- Prévision simple (moving average / tendance linéaire)
- Heatmap jour x semaine des livraisons

### Module 5 — Qualité des Données

**Vue exécutive :**
- Score moyen de confiance global
- % de documents avec confiance > 0.8
- Champs les plus problématiques (radar chart)

**Vue analytique :**
- Score par document, par champ, par stratégie d'extraction
- Corrélation format PDF → qualité extraction
- Suggestions d'amélioration (quels docs retraiter)
- Historique de qualité (tendance)

## 6. Scoring global

- **Score de rationalisation (0-100)** : composite achats + logistique + anomalies
- **Potentiel d'économie** : somme des économies identifiées (consolidation achats + regroupement logistique)

## 7. Navigation de l'application

```
Rationalize — Outil d'Analyse & Optimisation
│
├── Tableau de bord (vue exécutive globale — KPIs des 5 modules)
├── Rationalisation Achats (synthèse + détail)
├── Optimisation Logistique (synthèse + détail)
├── Détection d'Anomalies (synthèse + détail)
├── Tendances Temporelles (synthèse + détail)
├── Qualité Données (synthèse + détail)
└── Administration (ingestion, seuils, export)
```

## 8. Arborescence fichiers

```
dashboard/
├── app.py                     # Point d'entrée Streamlit
├── requirements.txt           # Dépendances dashboard
├── config.yaml                # Seuils, paramètres, règles anomalies
│
├── data/
│   ├── db.py                  # SQLAlchemy engine + session
│   ├── models.py              # ORM models (Document, Ligne, Fournisseur, Anomalie)
│   ├── ingestion.py           # JSON extraction → DB loader
│   └── cache.py               # Redis cache wrapper
│
├── analytics/
│   ├── achats.py              # Logique rationalisation achats
│   ├── logistique.py          # Logique optimisation logistique
│   ├── anomalies.py           # Moteur de détection d'anomalies (rule engine)
│   ├── tendances.py           # Analyse temporelle
│   └── qualite.py             # Analyse qualité données
│
├── pages/
│   ├── 01_tableau_de_bord.py  # Vue exécutive globale
│   ├── 02_achats.py           # Module achats
│   ├── 03_logistique.py       # Module logistique
│   ├── 04_anomalies.py        # Module anomalies
│   ├── 05_tendances.py        # Module tendances
│   ├── 06_qualite.py          # Module qualité
│   └── 07_admin.py            # Administration
│
└── components/
    ├── kpi_card.py            # Composant carte KPI réutilisable
    ├── filters.py             # Sidebar de filtres communs
    ├── charts.py              # Wrappers Plotly standardisés
    └── data_table.py          # Tableau interactif avec export
```

## 9. Stack technique

| Composant | Technologie | Version | Raison |
|-----------|-------------|---------|--------|
| UI | Streamlit | >= 1.40 | Rapide, Python-natif |
| Graphiques | Plotly Express + Graph Objects | >= 5.x | Interactifs, riches |
| Cartes | Plotly Mapbox ou Folium | — | Flux logistiques |
| Data | Pandas + SQLAlchemy | >= 2.x | Flexibilité requête/manipulation |
| DB | SQLite (dev) → PostgreSQL (prod) | — | Progressivité |
| Cache | Redis via redis-py + st.cache_data | >= 5.x | Agrégations lourdes 10k+ docs |
| Geocoding | API adresse.data.gouv.fr (FR) / Nominatim | — | Coordonnées pour cartographie |
| Export | openpyxl (Excel) + reportlab (PDF) | — | Rapports téléchargeables |
| Deploy | Docker Compose | — | Cohérent avec projet existant |

## 10. Déploiement Docker

Ajout au `docker-compose.yml` existant :

```yaml
services:
  dashboard:
    build: ./dashboard
    ports:
      - "8501:8501"
    volumes:
      - ./output:/app/output:ro
      - ./dashboard/data:/app/data
    environment:
      - DATABASE_URL=sqlite:///data/rationalize.db
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

## 11. Chemin d'évolution

| Phase | Scope | Durée estimée |
|-------|-------|---------------|
| POC (actuel) | 5 modules sur 5-42 lignes, SQLite, Docker local | 1-2 semaines |
| V1 | PostgreSQL, 100+ docs, geocoding, export PDF | 2-3 semaines |
| V2 | 10k+ docs, auth multi-utilisateur, alertes email | 4-6 semaines |
| V3 (optionnel) | Migration Next.js si besoin UI premium, API REST | 6-8 semaines |
