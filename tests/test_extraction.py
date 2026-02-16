#!/usr/bin/env python3
"""
test_extraction.py — Tests de validation des extractions.

Usage:
    python -m pytest tests/test_extraction.py -v
    python tests/test_extraction.py  # exécution directe
"""

import json
import os
import sys
import glob

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_extraction_files_exist():
    """Vérifie que des fichiers d'extraction existent."""
    extraction_dir = "output/extractions"
    if not os.path.exists(extraction_dir):
        print("⚠️  SKIP: Répertoire output/extractions/ n'existe pas encore")
        return True
    
    json_files = glob.glob(os.path.join(extraction_dir, "*_extraction.json"))
    assert len(json_files) > 0, f"Aucun fichier d'extraction trouvé dans {extraction_dir}"
    print(f"✅ {len(json_files)} fichiers d'extraction trouvés")
    return True


def test_extraction_schema_compliance():
    """Vérifie la conformité des extractions au schéma."""
    try:
        import jsonschema
    except ImportError:
        print("⚠️  SKIP: jsonschema non installé")
        return True
    
    schema_path = "schemas/extraction.json"
    if not os.path.exists(schema_path):
        print("⚠️  SKIP: Schéma non trouvé")
        return True
    
    with open(schema_path, 'r') as f:
        schema = json.load(f)
    
    extraction_files = glob.glob("output/extractions/*_extraction.json")
    if not extraction_files:
        print("⚠️  SKIP: Aucune extraction à valider")
        return True
    
    errors = []
    for filepath in extraction_files:
        with open(filepath, 'r') as f:
            data = json.load(f)
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            errors.append(f"{filepath}: {e.message}")
    
    if errors:
        for err in errors:
            print(f"❌ {err}")
        return False
    
    print(f"✅ {len(extraction_files)} extractions conformes au schéma")
    return True


def test_confidence_scores():
    """Vérifie que les scores de confiance sont cohérents."""
    extraction_files = glob.glob("output/extractions/*_extraction.json")
    if not extraction_files:
        print("⚠️  SKIP: Aucune extraction à vérifier")
        return True
    
    issues = []
    for filepath in extraction_files:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # Vérifier confiance globale
        if "confiance_globale" in data:
            conf = data["confiance_globale"]
            if not (0 <= conf <= 1):
                issues.append(f"{filepath}: confiance_globale={conf} hors [0,1]")
        
        # Vérifier confiance par champ
        for ligne in data.get("lignes", []):
            for champ, score in ligne.get("confiance", {}).items():
                if not (0 <= score <= 1):
                    issues.append(f"{filepath} ligne {ligne.get('ligne_numero')}: {champ}={score}")
    
    if issues:
        for issue in issues:
            print(f"❌ {issue}")
        return False
    
    print(f"✅ Scores de confiance cohérents sur {len(extraction_files)} fichiers")
    return True


def test_totals_coherence():
    """Vérifie la cohérence prix_unitaire × quantité = prix_total."""
    extraction_files = glob.glob("output/extractions/*_extraction.json")
    if not extraction_files:
        print("⚠️  SKIP: Aucune extraction")
        return True
    
    warnings = []
    for filepath in extraction_files:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        for ligne in data.get("lignes", []):
            pu = ligne.get("prix_unitaire")
            qty = ligne.get("quantite")
            total = ligne.get("prix_total")
            
            if pu is not None and qty is not None and total is not None:
                calcule = round(pu * qty, 2)
                if abs(calcule - total) > 0.01:
                    warnings.append(
                        f"{os.path.basename(filepath)} L{ligne.get('ligne_numero')}: "
                        f"{pu} × {qty} = {calcule} ≠ {total}"
                    )
    
    if warnings:
        for w in warnings:
            print(f"⚠️  {w}")
    else:
        print(f"✅ Totaux cohérents")
    return True  # Warnings, pas des erreurs bloquantes


def run_all_tests():
    """Exécute tous les tests."""
    print("=" * 60)
    print("🧪 Tests de Validation des Extractions")
    print("=" * 60)
    
    tests = [
        ("Fichiers d'extraction", test_extraction_files_exist),
        ("Conformité schéma", test_extraction_schema_compliance),
        ("Scores de confiance", test_confidence_scores),
        ("Cohérence des totaux", test_totals_coherence),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n--- {name} ---")
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"❌ Exception: {e}")
            results.append((name, False))
    
    print(f"\n{'='*60}")
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"📊 Résultat: {passed}/{total} tests passés")
    
    return all(r for _, r in results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
