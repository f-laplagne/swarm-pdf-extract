# Design — Édition inline dans la page Vérification PDF

**Date :** 2026-02-22
**Statut :** Approuvé
**Scope :** `dashboard/pages/11_verification_pdf.py`

---

## Contexte

La page 11 (Vérification PDF) est une SPA entièrement rendue dans un seul `st.components.v1.html()`. Elle affiche un split-view PDF.js / données d'extraction en HTML statique, sans aucun rerun Streamlit.

L'objectif est de permettre à un opérateur humain de corriger en place les champs d'extraction dont la confiance est inférieure à 50 %, avec persistance immédiate en base de données via l'infrastructure de correction existante (`appliquer_correction()`, `CorrectionLog`).

---

## Architecture globale

```
[Startup Python]
  1. Init engine SQLAlchemy (session_state ou local)
  2. Pour chaque PDF : lecture JSON + query DB → {ligne_numero: ligne_id}
  3. build_extraction_panel() reçoit ce mapping en paramètre
  4. Cellules conf < 0.5 → attributs data-ligne-id + data-champ + data-original + data-conf

[_CORSHandler étendu — port 8504]
  do_GET  → PDF serving (inchangé)
  do_POST /corrections → session SQLAlchemy → appliquer_correction() → JSON response

[HTML/JS dans l'iframe]
  click cellule faible → <input> affiché
  blur/Enter avec changement → fetch POST localhost:8504/corrections
  réponse OK → DOM update (valeur + badge "✓ corrigé")
```

**Contrainte clé :** page 11 lit les JSON d'extraction mais pas la DB. Le mapping `{ligne_numero → ligne_id}` est ajouté au pipeline de rendu. Si le document n'est pas ingéré en DB, les cellules restent en lecture seule (graceful fallback).

---

## Composant 1 — Enrichissement DB au rendu

Dans la boucle `for pdf_path in PDF_FILES:`, après `find_extraction()` :

- Si l'extraction JSON existe → query `Document` par `fichier`, puis `LigneFacture` par `document_id`
- Construire `ligne_ids: dict[int, int]` = `{ligne_numero: ligne.id}`
- Passer `ligne_ids` à `build_extraction_panel()`

Si le document n'est pas en DB → `ligne_ids = {}` → les cellules s'affichent sans `data-ligne-id` → non éditables.

---

## Composant 2 — Rendu HTML des cellules éditables

`build_extraction_panel(ext, P, cc, ligne_ids={})` — nouveau paramètre optionnel.

Pour chaque ligne, chaque champ valeur (colonne du tableau) :

- Si `conf.get(champ) < 0.5` **ET** `ligne_id` disponible dans `ligne_ids` :
  ```html
  <td class="cell-editable"
      data-ligne-id="42" data-champ="type_matiere"
      data-original="feraille" data-conf="0.32">
    <span class="cell-display">feraille</span>
    <input class="cell-input" type="text" value="feraille" style="display:none">
  </td>
  ```
- Sinon : `<td>` statique (comportement actuel inchangé)

Champs numériques (`prix_unitaire`, `quantite`, `prix_total`) → `type="number" step="0.0001"`.

Styling CSS des cellules éditables :
- Bordure orange pointillée en bas + icône ✏ au hover
- Sur click : bordure orange pleine, input visible, focus

---

## Composant 3 — Endpoint HTTP `POST /corrections`

Extension de `_CORSHandler` avec `do_POST()` :

**Corps JSON attendu :**
```json
{
  "ligne_id": 42,
  "champ": "type_matiere",
  "valeur_originale": "feraille",
  "valeur_corrigee": "Ferraille acier",
  "confiance_originale": 0.32
}
```

**Réponse succès :**
```json
{"success": true, "correction_id": 7}
```

**Réponse erreur :**
```json
{"success": false, "error": "Ligne 42 introuvable"}
```

**Thread safety :** l'engine SQLAlchemy est créé une fois (module-level, thread-safe). Chaque requête POST crée sa propre session (`Session(engine)`), appelle `appliquer_correction()`, ferme la session.

`appliquer_correction()` existant :
- Met à jour `LigneFacture.{champ}` directement en DB
- Passe `conf_{champ} = 1.0`
- Logue dans `CorrectionLog`
- Recalcule `confiance_globale` du document

→ Propagation automatique à tous les services (achats, logistique, anomalies, qualité, tendances).

---

## Composant 4 — Interaction JS et feedback visuel

| Étape | Action JS | Feedback visuel |
|-------|-----------|-----------------|
| Click cellule faible | `span` caché, `input` visible, focus | Bordure orange pleine |
| Escape | Retour `span`, valeur originale | Bordure pointillée |
| Enter/blur sans changement | Retour `span` | Inchangé |
| POST en cours | Input désactivé | `⏳` dans cellule |
| POST succès | `span` mis à jour, input caché, class `editable` retirée | Badge conf → `✓ corrigé` (vert) |
| POST erreur | Input réactivé, valeur originale restaurée | Tooltip `⚠ {message}` (rouge) |

Après correction réussie, la cellule perd son caractère éditable pour la session courante (rechargement de page pour ré-éditer).

---

## Périmètre strict (YAGNI)

**Inclus :**
- Édition inline des 9 champs pour `conf < 0.5` (seuil fixe)
- Persistance via `appliquer_correction()` existant
- Fallback gracieux si document non ingéré en DB

**Exclus :**
- Propagation bulk (page 10)
- Suppression de lignes (page 10)
- Historique corrections (page 10, tab 3)
- Undo dans l'iframe
- Slider de seuil dans cette page

---

## Fichiers modifiés

| Fichier | Nature de la modification |
|---------|--------------------------|
| `dashboard/pages/11_verification_pdf.py` | Enrichissement DB au rendu + `do_POST` sur `_CORSHandler` + HTML/JS éditables |

Aucun autre fichier modifié — toute la logique de persistance est dans `dashboard/analytics/corrections.py` (existant).
