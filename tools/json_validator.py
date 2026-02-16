#!/usr/bin/env python3
"""
json_validator.py — Validation de fichiers JSON contre un schéma.

Usage:
    python tools/json_validator.py <fichier.json> <schema.json>
    python tools/json_validator.py output/extractions/ schemas/extraction.json  # batch
"""

import sys
import json
import os
import glob

try:
    import jsonschema
    from jsonschema import validate, ValidationError
except ImportError:
    print("ERREUR: jsonschema non installé. pip install jsonschema", file=sys.stderr)
    sys.exit(1)


def validate_file(json_path: str, schema_path: str) -> dict:
    """Valide un fichier JSON contre un schéma."""
    result = {
        "fichier": json_path,
        "schema": schema_path,
        "valide": False,
        "erreurs": []
    }
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
        
        validate(instance=data, schema=schema)
        result["valide"] = True
    
    except json.JSONDecodeError as e:
        result["erreurs"].append(f"JSON invalide: {str(e)}")
    
    except ValidationError as e:
        result["erreurs"].append(f"Validation échouée: {e.message}")
        result["chemin_erreur"] = list(e.absolute_path)
    
    except FileNotFoundError as e:
        result["erreurs"].append(f"Fichier non trouvé: {str(e)}")
    
    except Exception as e:
        result["erreurs"].append(f"Erreur inattendue: {str(e)}")
    
    return result


def validate_batch(directory: str, schema_path: str) -> dict:
    """Valide tous les fichiers JSON d'un répertoire."""
    results = {
        "schema": schema_path,
        "total": 0,
        "valides": 0,
        "invalides": 0,
        "details": []
    }
    
    json_files = sorted(glob.glob(os.path.join(directory, "*.json")))
    results["total"] = len(json_files)
    
    for json_file in json_files:
        result = validate_file(json_file, schema_path)
        results["details"].append(result)
        if result["valide"]:
            results["valides"] += 1
        else:
            results["invalides"] += 1
    
    return results


def main():
    if len(sys.argv) < 3:
        print("Usage: python json_validator.py <fichier_ou_dossier.json> <schema.json>")
        sys.exit(1)
    
    target = sys.argv[1]
    schema_path = sys.argv[2]
    
    if os.path.isdir(target):
        results = validate_batch(target, schema_path)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        
        # Résumé console
        print(f"\n{'='*50}", file=sys.stderr)
        print(f"Résultats: {results['valides']}/{results['total']} valides", file=sys.stderr)
        if results["invalides"] > 0:
            print(f"⚠️  {results['invalides']} fichiers invalides:", file=sys.stderr)
            for d in results["details"]:
                if not d["valide"]:
                    print(f"  ❌ {d['fichier']}: {d['erreurs'][0]}", file=sys.stderr)
        sys.exit(0 if results["invalides"] == 0 else 1)
    
    else:
        result = validate_file(target, schema_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        if result["valide"]:
            print(f"✅ {target} est valide", file=sys.stderr)
        else:
            print(f"❌ {target} est invalide: {result['erreurs']}", file=sys.stderr)
        
        sys.exit(0 if result["valide"] else 1)


if __name__ == "__main__":
    main()
