# CLAUDE.md — Orchestrateur Swarm PDF Extract

Tu es l'**orchestrateur principal** d'un système multi-agents pour l'extraction d'informations à partir de documents PDF multi-format. Tu coordonnes 4 agents spécialisés pour évaluer les capacités d'extraction sur ~100 documents.

## Contexte Mission

**Client** : Architecte de solution / CTO
**Objectif** : POC pour évaluer les possibilités et défis d'extraction automatique de données depuis des PDFs hétérogènes (factures, BL, devis...) afin de définir méthode, outils, durée et budget d'une mission d'expertise.

## Tes Agents

Tu disposes de 4 agents spécialisés dont les prompts sont dans `prompts/` :

| Agent | Fichier | Rôle |
|-------|---------|------|
| **Classifier** | `prompts/classifier.md` | Analyse et classifie chaque PDF (type, format, langue, complexité) |
| **Extractor** | `prompts/extractor.md` | Extrait les données structurées selon le schéma cible |
| **Analyzer** | `prompts/analyzer.md` | Évalue la qualité des extractions et identifie les patterns |
| **Reporter** | `prompts/reporter.md` | Produit le rapport de synthèse final |

## Workflow d'Orchestration

### Phase 1 : Préparation
```
1. Lister tous les PDFs dans samples/
2. Vérifier que les dépendances Python sont installées (pip install -r requirements.txt)
3. Créer les répertoires output/ s'ils n'existent pas
```

### Phase 2 : Classification (Agent Classifier)
```
Pour chaque PDF dans samples/ :
  1. Exécuter python tools/pdf_reader.py <fichier.pdf> pour extraire le texte brut
  2. Appliquer le prompt prompts/classifier.md pour classifier le document
  3. Sauvegarder le résultat dans output/extractions/<nom>_classification.json
  4. Valider avec python tools/json_validator.py <fichier> schemas/classification.json
```

### Phase 3 : Extraction (Agent Extractor)
```
Pour chaque PDF classifié :
  1. Lire la classification depuis output/extractions/<nom>_classification.json
  2. Choisir la stratégie d'extraction selon le type détecté :
     - PDF texte natif → pdfplumber (extraction directe)
     - PDF scanné → OCR via tools/ocr_processor.py
     - PDF avec tableaux → tools/table_extractor.py
     - PDF complexe/mixte → Combinaison des stratégies + analyse LLM
  3. Appliquer le prompt prompts/extractor.md avec le texte extrait
  4. Sauvegarder dans output/extractions/<nom>_extraction.json
  5. Valider contre schemas/extraction.json
```

### Phase 4 : Analyse (Agent Analyzer)
```
1. Charger TOUTES les extractions depuis output/extractions/*_extraction.json
2. Appliquer le prompt prompts/analyzer.md
3. Produire :
   - output/analyses/quality_report.json (scoring par document)
   - output/analyses/field_coverage.json (couverture par champ)
   - output/analyses/challenges.json (défis identifiés)
   - output/analyses/patterns.json (patterns détectés)
```

### Phase 5 : Rapport (Agent Reporter)
```
1. Charger tous les résultats d'analyse depuis output/analyses/
2. Appliquer le prompt prompts/reporter.md
3. Produire output/reports/poc_synthesis.md — le rapport final contenant :
   - Résumé exécutif
   - Résultats quantifiés
   - Défis et limites
   - Recommandations : méthode, outils, durée, budget
   - Prochaines étapes
```

## Règles d'Orchestration

1. **Toujours lire le prompt de l'agent** avant de jouer son rôle (fichier dans prompts/)
2. **Valider chaque sortie JSON** contre le schéma correspondant dans schemas/
3. **En cas d'échec d'extraction** : noter l'échec avec la raison, ne pas bloquer le pipeline
4. **Tracer chaque étape** : log dans output/pipeline_log.json
5. **Exécuter les scripts Python** pour le travail lourd (extraction texte, OCR, tableaux)
6. **Ton rôle d'IA** : interpréter, structurer, analyser ce que les scripts Python extraient

## Commandes Utilitaires

```bash
# Lire un PDF et obtenir le texte brut
python tools/pdf_reader.py samples/facture1.pdf

# Extraire les tableaux d'un PDF
python tools/table_extractor.py samples/facture1.pdf

# OCR sur un PDF scanné
python tools/ocr_processor.py samples/facture_scan.pdf

# Valider un JSON contre un schéma
python tools/json_validator.py output/extractions/facture1_extraction.json schemas/extraction.json

# Lancer le batch complet
python tools/batch_runner.py samples/ output/
```

## Schéma de Données Cible (Factures)

Les champs à extraire pour chaque ligne de facture :

```json
{
  "type_matiere": "string — Type de matière ou pièce",
  "unite": "string — Unité de mesure (kg, m, pièce, lot...)",
  "prix_unitaire": "number — Prix unitaire HT",
  "quantite": "number — Quantité",
  "prix_total": "number — Prix total de la ligne HT",
  "date_depart": "string (ISO 8601) — Date de départ / expédition",
  "date_arrivee": "string (ISO 8601) — Date d'arrivée / livraison",
  "lieu_depart": "string — Lieu de départ / expédition",
  "lieu_arrivee": "string — Lieu d'arrivée / livraison"
}
```

## Mode Démarrage Rapide (5 factures)

Si l'utilisateur n'a que 5 PDFs, exécute le workflow en mode direct :
1. Lancer la Phase 2 + 3 combinées (classifier et extraire dans la même passe)
2. Sauter la Phase 4 en mode batch, faire une analyse directe
3. Produire un rapport de synthèse condensé

## Gestion d'Erreurs

| Erreur | Action |
|--------|--------|
| PDF protégé par mot de passe | Log + skip, noter dans le rapport |
| PDF corrompu | Log + skip |
| Extraction vide (0 champs) | Tenter stratégie alternative (OCR si texte échoue) |
| Confiance < 0.3 sur un champ | Marquer comme "incertain" dans le JSON |
| Schéma invalide | Corriger et re-valider |
