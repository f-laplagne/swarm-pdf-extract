#!/usr/bin/env python3
"""
table_extractor.py — Extraction spécialisée de tableaux depuis un PDF.

Usage:
    python tools/table_extractor.py <fichier.pdf> [--format json|csv|markdown]

Produit un JSON structuré avec tous les tableaux détectés, leurs en-têtes
et leurs données, prêts à être interprétés par l'agent Extractor.
"""

import sys
import json
import os

try:
    import pdfplumber
except ImportError:
    print("ERREUR: pdfplumber non installé. pip install pdfplumber", file=sys.stderr)
    sys.exit(1)


def clean_cell(cell) -> str:
    """Nettoie une cellule de tableau."""
    if cell is None:
        return ""
    return str(cell).strip().replace("\n", " ")


def extract_tables(pdf_path: str) -> dict:
    """Extrait tous les tableaux d'un PDF avec analyse structurelle."""
    result = {
        "fichier": os.path.basename(pdf_path),
        "tables": [],
        "total_tables": 0,
        "total_lignes": 0,
        "resume": ""
    }
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if not tables:
                    continue
                
                for table_idx, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue
                    
                    # Nettoyer les données
                    cleaned = [[clean_cell(c) for c in row] for row in table]
                    headers = cleaned[0]
                    rows = cleaned[1:]
                    
                    # Analyser les colonnes
                    col_analysis = []
                    for col_idx, header in enumerate(headers):
                        col_values = [row[col_idx] for row in rows if col_idx < len(row) and row[col_idx]]
                        col_type = _infer_column_type(col_values)
                        col_analysis.append({
                            "index": col_idx,
                            "header": header,
                            "type_infere": col_type,
                            "non_vides": len(col_values),
                            "total_lignes": len(rows)
                        })
                    
                    table_data = {
                        "page": page_num + 1,
                        "table_index": table_idx,
                        "headers": headers,
                        "rows": rows,
                        "num_rows": len(rows),
                        "num_cols": len(headers),
                        "colonnes_analyse": col_analysis,
                        "mapping_suggere": _suggest_mapping(headers)
                    }
                    
                    result["tables"].append(table_data)
                    result["total_lignes"] += len(rows)
            
            result["total_tables"] = len(result["tables"])
            result["resume"] = (
                f"{result['total_tables']} tableaux trouvés, "
                f"{result['total_lignes']} lignes de données au total"
            )
    
    except Exception as e:
        result["erreur"] = str(e)
    
    return result


def _infer_column_type(values: list) -> str:
    """Infère le type d'une colonne à partir de ses valeurs."""
    if not values:
        return "vide"
    
    numeric_count = 0
    date_count = 0
    
    for v in values:
        v_clean = v.replace(" ", "").replace(",", ".").replace("€", "").replace("$", "")
        try:
            float(v_clean)
            numeric_count += 1
            continue
        except ValueError:
            pass
        
        # Test date simple
        if any(sep in v for sep in ["/", "-"]) and any(c.isdigit() for c in v):
            parts = v.replace("-", "/").split("/")
            if len(parts) >= 2 and all(p.strip().isdigit() for p in parts):
                date_count += 1
                continue
    
    ratio = len(values)
    if numeric_count / ratio > 0.7:
        return "numerique"
    elif date_count / ratio > 0.5:
        return "date"
    else:
        return "texte"


def _suggest_mapping(headers: list) -> dict:
    """Suggère un mapping des en-têtes vers les champs cibles."""
    mapping = {}
    
    keywords = {
        "type_matiere": ["désignation", "designation", "description", "article", "libellé", "libelle", 
                         "produit", "matière", "matiere", "pièce", "piece", "prestation", "nature"],
        "unite": ["unité", "unite", "u.", "uom", "unit"],
        "prix_unitaire": ["p.u.", "pu", "prix unit", "prix unitaire", "tarif", "unit price"],
        "quantite": ["qté", "qte", "quantité", "quantite", "qty", "nombre", "nb"],
        "prix_total": ["montant", "total", "prix total", "total ht", "amount", "sous-total"],
        "date_depart": ["date départ", "date depart", "expédition", "expedition", "envoi"],
        "date_arrivee": ["date arrivée", "date arrivee", "livraison", "réception", "reception"],
        "lieu_depart": ["départ", "depart", "origine", "expédié de"],
        "lieu_arrivee": ["arrivée", "arrivee", "destination", "livré à", "adresse livraison"]
    }
    
    for header in headers:
        header_lower = header.lower().strip()
        for field, kws in keywords.items():
            if any(kw in header_lower for kw in kws):
                mapping[header] = field
                break
    
    return mapping


def format_as_markdown(result: dict) -> str:
    """Formate les tableaux en Markdown."""
    lines = [f"# Tableaux extraits de {result['fichier']}\n"]
    
    for table in result["tables"]:
        lines.append(f"\n## Page {table['page']}, Tableau {table['table_index'] + 1}")
        lines.append(f"({table['num_rows']} lignes, {table['num_cols']} colonnes)\n")
        
        headers = table["headers"]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        
        for row in table["rows"]:
            padded = row + [""] * (len(headers) - len(row))
            lines.append("| " + " | ".join(padded[:len(headers)]) + " |")
        
        if table.get("mapping_suggere"):
            lines.append(f"\n**Mapping suggéré:** {json.dumps(table['mapping_suggere'], ensure_ascii=False)}")
    
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extraction de tableaux depuis un PDF")
    parser.add_argument("pdf_path", help="Chemin vers le fichier PDF")
    parser.add_argument("--format", choices=["json", "csv", "markdown"], default="json")
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf_path):
        print(f"ERREUR: Fichier non trouvé: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)
    
    result = extract_tables(args.pdf_path)
    
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.format == "markdown":
        print(format_as_markdown(result))
    elif args.format == "csv":
        for table in result["tables"]:
            print(f"# Page {table['page']}, Tableau {table['table_index'] + 1}")
            print(",".join(f'"{h}"' for h in table["headers"]))
            for row in table["rows"]:
                print(",".join(f'"{c}"' for c in row))
            print()


if __name__ == "__main__":
    main()
