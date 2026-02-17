#!/usr/bin/env python3
"""
pdf_reader.py — Extraction de texte multi-stratégie depuis un PDF.

Usage:
    python tools/pdf_reader.py <fichier.pdf> [--output json|text] [--strategy auto|text|ocr|paddleocr|mlx]

Stratégies:
    auto       — Chaîne de fallback : pdfplumber → PP-StructureV3 → MLX VLM → Tesseract
    text       — pdfplumber uniquement
    ocr        — OCR Tesseract uniquement
    paddleocr  — PP-StructureV3 (détection native de tableaux)
    mlx        — MLX VLM OCR (GPU Metal Apple Silicon)
"""

import sys
import json
import os
from pathlib import Path

from domain.extraction.strategy_selector import select_strategy, ExtractionStrategy

try:
    import pdfplumber
except ImportError:
    print("ERREUR: pdfplumber non installé. Exécutez: pip install pdfplumber", file=sys.stderr)
    sys.exit(1)


def extract_text_pdfplumber(pdf_path: str) -> dict:
    """Extraction de texte via pdfplumber."""
    result = {
        "fichier": os.path.basename(pdf_path),
        "methode": "pdfplumber",
        "pages": [],
        "texte_complet": "",
        "nombre_pages": 0,
        "tables": [],
        "metadata": {}
    }
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            result["nombre_pages"] = len(pdf.pages)
            result["metadata"] = {
                "title": pdf.metadata.get("Title", ""),
                "author": pdf.metadata.get("Author", ""),
                "creator": pdf.metadata.get("Creator", ""),
                "producer": pdf.metadata.get("Producer", ""),
            }
            
            all_text = []
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                all_text.append(page_text)
                
                # Extraction des tableaux
                page_tables = page.extract_tables() or []
                for j, table in enumerate(page_tables):
                    result["tables"].append({
                        "page": i + 1,
                        "table_index": j,
                        "headers": table[0] if table else [],
                        "rows": table[1:] if table else [],
                        "num_rows": len(table) - 1 if table else 0,
                        "num_cols": len(table[0]) if table and table[0] else 0
                    })
                
                result["pages"].append({
                    "page": i + 1,
                    "texte": page_text,
                    "longueur": len(page_text),
                    "tables_count": len(page_tables)
                })
            
            result["texte_complet"] = "\n\n--- PAGE ---\n\n".join(all_text)
    
    except Exception as e:
        result["erreur"] = str(e)
    
    return result


def extract_text_ocr(pdf_path: str) -> dict:
    """Extraction de texte via OCR (Tesseract)."""
    result = {
        "fichier": os.path.basename(pdf_path),
        "methode": "ocr_tesseract",
        "pages": [],
        "texte_complet": "",
        "nombre_pages": 0,
        "tables": [],
        "metadata": {}
    }
    
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        result["erreur"] = "pdf2image ou pytesseract non installé. pip install pdf2image pytesseract"
        return result
    
    try:
        images = convert_from_path(pdf_path, dpi=300)
        result["nombre_pages"] = len(images)
        
        all_text = []
        for i, image in enumerate(images):
            page_text = pytesseract.image_to_string(image, lang='fra+eng')
            all_text.append(page_text)
            result["pages"].append({
                "page": i + 1,
                "texte": page_text,
                "longueur": len(page_text),
                "tables_count": 0
            })
        
        result["texte_complet"] = "\n\n--- PAGE ---\n\n".join(all_text)
    
    except Exception as e:
        result["erreur"] = str(e)
    
    return result


def extract_text_paddleocr(pdf_path: str) -> dict:
    """Extraction via PP-StructureV3 (détection native de tableaux)."""
    try:
        from tools.paddleocr_processor import ocr_paddleocr_native
    except ImportError:
        try:
            from paddleocr_processor import ocr_paddleocr_native
        except ImportError:
            return {"erreur": "paddleocr_processor non disponible", "fichier": os.path.basename(pdf_path)}
    return ocr_paddleocr_native(pdf_path)


def extract_text_mlx(pdf_path: str) -> dict:
    """Extraction via MLX VLM OCR (GPU Metal Apple Silicon)."""
    try:
        from tools.paddleocr_mlx import ocr_pdf_mlx
    except ImportError:
        try:
            from paddleocr_mlx import ocr_pdf_mlx
        except ImportError:
            return {"erreur": "paddleocr_mlx non disponible", "fichier": os.path.basename(pdf_path)}
    return ocr_pdf_mlx(pdf_path)


def extract_auto(pdf_path: str) -> dict:
    """Stratégie automatique : pdfplumber → PP-StructureV3 → MLX VLM → Tesseract."""
    result = extract_text_pdfplumber(pdf_path)

    # Vérifier si le texte est suffisant
    total_chars = sum(p.get("longueur", 0) for p in result.get("pages", []))
    pages = result.get("nombre_pages", 1)
    chars_per_page = total_chars / max(pages, 1)
    has_tables = len(result.get("tables", [])) > 0

    # Delegate strategy decision to domain
    strategy = select_strategy(chars_per_page, has_tables)

    if strategy in (ExtractionStrategy.PDFPLUMBER_TEXT, ExtractionStrategy.PDFPLUMBER_TABLES):
        result["methode"] = "auto_pdfplumber"
        return result

    # OCR needed — follow existing fallback chain
    if strategy == ExtractionStrategy.OCR_TESSERACT:
        print(f"⚠️  Texte insuffisant ({total_chars} chars pour {pages} pages), tentative PP-StructureV3...", file=sys.stderr)

        # Fallback 1 : PP-StructureV3 natif (détection tableaux)
        paddle_result = extract_text_paddleocr(pdf_path)
        if "erreur" not in paddle_result:
            paddle_result["methode"] = "auto_fallback_paddleocr"
            paddle_result["note"] = f"Fallback PP-StructureV3 car pdfplumber n'a extrait que {total_chars} caractères"
            return paddle_result
        print(f"⚠️  PP-StructureV3 indisponible ({paddle_result.get('erreur', '?')}), tentative MLX VLM...", file=sys.stderr)

        # Fallback 2 : MLX VLM (compréhension sémantique GPU Metal)
        mlx_result = extract_text_mlx(pdf_path)
        if "erreur" not in mlx_result:
            mlx_result["methode"] = "auto_fallback_mlx"
            mlx_result["note"] = f"Fallback MLX VLM car pdfplumber et PP-StructureV3 ont échoué"
            return mlx_result
        print(f"⚠️  MLX VLM indisponible ({mlx_result.get('erreur', '?')}), tentative Tesseract...", file=sys.stderr)

        # Fallback 3 : Tesseract (legacy)
        ocr_result = extract_text_ocr(pdf_path)
        if "erreur" not in ocr_result:
            ocr_result["methode"] = "auto_fallback_ocr"
            ocr_result["note"] = f"Fallback Tesseract car pdfplumber, PP-StructureV3 et MLX VLM ont échoué"
            return ocr_result
        else:
            result["warning"] = f"Tous les fallbacks OCR ont échoué: {ocr_result['erreur']}"

    result["methode"] = "auto_pdfplumber"
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extraction de texte depuis un PDF")
    parser.add_argument("pdf_path", help="Chemin vers le fichier PDF")
    parser.add_argument("--output", choices=["json", "text"], default="json", help="Format de sortie")
    parser.add_argument("--strategy", choices=["auto", "text", "ocr", "paddleocr", "mlx"], default="auto", help="Stratégie d'extraction")
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"ERREUR: Fichier non trouvé: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    strategies = {
        "auto": extract_auto,
        "text": extract_text_pdfplumber,
        "ocr": extract_text_ocr,
        "paddleocr": extract_text_paddleocr,
        "mlx": extract_text_mlx,
    }
    
    result = strategies[args.strategy](args.pdf_path)
    
    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("texte_complet", ""))


if __name__ == "__main__":
    main()
