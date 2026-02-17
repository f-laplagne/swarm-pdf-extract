#!/usr/bin/env python3
"""
test_schemas.py — Tests de validité des schémas JSON eux-mêmes.

Usage:
    python tests/test_schemas.py
"""

import json
import os
import sys
import glob


def test_schemas_are_valid_json():
    """Vérifie que tous les schémas sont du JSON valide."""
    schema_files = glob.glob("schemas/*.json")
    
    if not schema_files:
        print("⚠️  Aucun schéma trouvé dans schemas/")
        return True
    
    errors = []
    for schema_path in schema_files:
        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)
            
            # Vérifier les propriétés de base d'un JSON Schema
            assert "$schema" in schema, f"Pas de $schema dans {schema_path}"
            assert "type" in schema, f"Pas de type dans {schema_path}"
            print(f"  ✅ {os.path.basename(schema_path)}: {schema.get('title', 'sans titre')}")
        
        except json.JSONDecodeError as e:
            errors.append(f"{schema_path}: JSON invalide — {e}")
        except AssertionError as e:
            errors.append(str(e))
    
    if errors:
        for err in errors:
            print(f"  ❌ {err}")
        return False
    
    return True


def test_schemas_have_required_fields():
    """Vérifie que les schémas définissent les champs requis."""
    expected = {
        "classification.json": ["fichier", "type_document", "format_pdf", "complexite"],
        "extraction.json": ["fichier", "metadonnees", "lignes", "confiance_globale"],
        "analysis.json": ["documents", "statistiques_globales"],
    }
    
    errors = []
    for schema_file, required_fields in expected.items():
        schema_path = os.path.join("schemas", schema_file)
        if not os.path.exists(schema_path):
            errors.append(f"Schéma manquant: {schema_path}")
            continue
        
        with open(schema_path, 'r') as f:
            schema = json.load(f)
        
        schema_required = schema.get("required", [])
        for field in required_fields:
            if field not in schema_required:
                errors.append(f"{schema_file}: champ requis manquant '{field}'")
    
    if errors:
        for err in errors:
            print(f"  ❌ {err}")
        return False
    
    print(f"  ✅ Tous les schémas ont les champs requis attendus")
    return True


def run_all_tests():
    """Exécute tous les tests de schémas."""
    print("=" * 60)
    print("🧪 Tests de Validation des Schémas JSON")
    print("=" * 60)
    
    tests = [
        ("Schémas JSON valides", test_schemas_are_valid_json),
        ("Champs requis présents", test_schemas_have_required_fields),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n--- {name} ---")
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            results.append((name, False))
    
    print(f"\n{'='*60}")
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"📊 Résultat: {passed}/{total} tests passés")
    return all(r for _, r in results)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
