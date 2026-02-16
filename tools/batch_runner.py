#!/usr/bin/env python3
"""
batch_runner.py — Exécution batch des outils d'extraction sur un répertoire de PDFs.

Usage:
    python tools/batch_runner.py <dossier_pdfs> <dossier_output> [--strategy auto]

Exécute pdf_reader.py et table_extractor.py sur chaque PDF,
et produit les fichiers de données brutes prêts pour les agents Claude.
"""

import sys
import json
import os
import glob
import time
from pathlib import Path

# Importer nos outils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_reader import extract_auto
from table_extractor import extract_tables


def process_single_pdf(pdf_path: str, output_dir: str) -> dict:
    """Traite un seul PDF : extraction texte + tableaux."""
    filename = Path(pdf_path).stem
    start_time = time.time()
    
    result = {
        "fichier": os.path.basename(pdf_path),
        "statut": "en_cours",
        "temps_traitement": 0,
        "extraction_texte": None,
        "extraction_tableaux": None,
        "erreurs": []
    }
    
    # 1. Extraction de texte
    try:
        text_result = extract_auto(pdf_path)
        result["extraction_texte"] = {
            "methode": text_result.get("methode", "unknown"),
            "nombre_pages": text_result.get("nombre_pages", 0),
            "longueur_texte": len(text_result.get("texte_complet", "")),
            "fichier_sortie": f"{filename}_text.json"
        }
        
        # Sauvegarder
        text_output_path = os.path.join(output_dir, f"{filename}_text.json")
        with open(text_output_path, 'w', encoding='utf-8') as f:
            json.dump(text_result, f, ensure_ascii=False, indent=2)
    
    except Exception as e:
        result["erreurs"].append(f"Extraction texte: {str(e)}")
    
    # 2. Extraction de tableaux
    try:
        table_result = extract_tables(pdf_path)
        result["extraction_tableaux"] = {
            "total_tables": table_result.get("total_tables", 0),
            "total_lignes": table_result.get("total_lignes", 0),
            "fichier_sortie": f"{filename}_tables.json"
        }
        
        # Sauvegarder
        table_output_path = os.path.join(output_dir, f"{filename}_tables.json")
        with open(table_output_path, 'w', encoding='utf-8') as f:
            json.dump(table_result, f, ensure_ascii=False, indent=2)
    
    except Exception as e:
        result["erreurs"].append(f"Extraction tableaux: {str(e)}")
    
    elapsed = time.time() - start_time
    result["temps_traitement"] = round(elapsed, 2)
    result["statut"] = "succes" if not result["erreurs"] else "partiel"
    
    return result


def run_batch(input_dir: str, output_dir: str) -> dict:
    """Traite tous les PDFs d'un répertoire."""
    
    # Créer les répertoires de sortie
    os.makedirs(output_dir, exist_ok=True)
    
    # Trouver tous les PDFs
    pdf_files = sorted(
        glob.glob(os.path.join(input_dir, "*.pdf")) + 
        glob.glob(os.path.join(input_dir, "*.PDF"))
    )
    
    if not pdf_files:
        print(f"⚠️  Aucun PDF trouvé dans {input_dir}", file=sys.stderr)
        return {"total": 0, "documents": []}
    
    print(f"📁 {len(pdf_files)} PDFs trouvés dans {input_dir}", file=sys.stderr)
    
    batch_result = {
        "input_dir": input_dir,
        "output_dir": output_dir,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": len(pdf_files),
        "succes": 0,
        "partiels": 0,
        "echecs": 0,
        "temps_total": 0,
        "documents": []
    }
    
    start_total = time.time()
    
    for i, pdf_path in enumerate(pdf_files, 1):
        filename = os.path.basename(pdf_path)
        print(f"\n[{i}/{len(pdf_files)}] 📄 Traitement de {filename}...", file=sys.stderr)
        
        doc_result = process_single_pdf(pdf_path, output_dir)
        batch_result["documents"].append(doc_result)
        
        if doc_result["statut"] == "succes":
            batch_result["succes"] += 1
            status_icon = "✅"
        elif doc_result["statut"] == "partiel":
            batch_result["partiels"] += 1
            status_icon = "⚠️"
        else:
            batch_result["echecs"] += 1
            status_icon = "❌"
        
        text_info = doc_result.get("extraction_texte", {})
        table_info = doc_result.get("extraction_tableaux", {})
        print(
            f"  {status_icon} {doc_result['temps_traitement']}s — "
            f"Texte: {text_info.get('longueur_texte', 0)} chars, "
            f"Tables: {table_info.get('total_tables', 0)} "
            f"({table_info.get('total_lignes', 0)} lignes)",
            file=sys.stderr
        )
    
    batch_result["temps_total"] = round(time.time() - start_total, 2)
    
    # Sauvegarder le rapport batch
    report_path = os.path.join(output_dir, "_batch_report.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(batch_result, f, ensure_ascii=False, indent=2)
    
    # Résumé
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"📊 Résumé: {batch_result['succes']} succès, "
          f"{batch_result['partiels']} partiels, "
          f"{batch_result['echecs']} échecs "
          f"en {batch_result['temps_total']}s", file=sys.stderr)
    print(f"📁 Résultats dans: {output_dir}", file=sys.stderr)
    print(f"📋 Rapport batch: {report_path}", file=sys.stderr)
    
    return batch_result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch processing de PDFs")
    parser.add_argument("input_dir", help="Répertoire contenant les PDFs")
    parser.add_argument("output_dir", help="Répertoire de sortie")
    args = parser.parse_args()
    
    result = run_batch(args.input_dir, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
