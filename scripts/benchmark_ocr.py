#!/usr/bin/env python3
"""
benchmark_ocr.py — Comparaison Tesseract vs PaddleOCR vs MLX VLM.

Lance chaque stratégie OCR sur les PDFs scannés et produit un tableau comparatif.

Usage:
    python scripts/benchmark_ocr.py [--samples-dir samples/] [--output-dir output/benchmark/]
"""

import sys
import os
import json
import re
import time

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_eur_amounts(text: str) -> list:
    """Trouve les montants en EUR dans le texte."""
    patterns = [
        r"(\d[\d\s]*[\.,]\d{2})\s*(?:€|EUR|eur)",
        r"(?:€|EUR)\s*(\d[\d\s]*[\.,]\d{2})",
        r"(\d{1,3}(?:[\s.]\d{3})*,\d{2})",  # Format FR : 1 234,56
    ]
    amounts = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            val = match.group(1) if match.lastindex else match.group(0)
            val = val.replace(" ", "").replace(".", "").replace(",", ".")
            try:
                amounts.append(float(val))
            except ValueError:
                pass
    return amounts


def count_tables_in_text(text: str) -> int:
    """Compte les tableaux Markdown détectés dans le texte."""
    lines = text.split("\n")
    table_count = 0
    in_table = False
    for line in lines:
        stripped = line.strip()
        if "|" in stripped and stripped.startswith("|"):
            if not in_table:
                table_count += 1
                in_table = True
        else:
            in_table = False
    return table_count


def run_tesseract(pdf_path: str) -> dict:
    """Benchmark Tesseract OCR."""
    try:
        from tools.ocr_processor import ocr_pdf
    except ImportError:
        from ocr_processor import ocr_pdf

    start = time.time()
    result = ocr_pdf(pdf_path, lang="fra+eng", dpi=300)
    elapsed = time.time() - start

    text = result.get("texte_complet", "")
    return {
        "strategie": "Tesseract",
        "temps_sec": round(elapsed, 2),
        "longueur_texte": len(text),
        "nombre_pages": result.get("nombre_pages", 0),
        "tableaux_detectes": 0,  # Tesseract ne détecte pas les tableaux
        "montants_eur": find_eur_amounts(text),
        "qualite_estimee": result.get("qualite_estimee", 0),
        "erreur": result.get("erreur"),
    }


def run_paddleocr(pdf_path: str) -> dict:
    """Benchmark PaddleOCR PP-StructureV3."""
    try:
        from tools.paddleocr_processor import ocr_paddleocr_native
    except ImportError:
        try:
            from paddleocr_processor import ocr_paddleocr_native
        except ImportError:
            return {
                "strategie": "PaddleOCR",
                "erreur": "paddleocr non installé",
                "temps_sec": 0,
                "longueur_texte": 0,
                "nombre_pages": 0,
                "tableaux_detectes": 0,
                "montants_eur": [],
                "qualite_estimee": 0,
            }

    start = time.time()
    result = ocr_paddleocr_native(pdf_path)
    elapsed = time.time() - start

    text = result.get("texte_complet", "")
    return {
        "strategie": "PaddleOCR",
        "temps_sec": round(elapsed, 2),
        "longueur_texte": len(text),
        "nombre_pages": result.get("nombre_pages", 0),
        "tableaux_detectes": len(result.get("tables_detectees", [])),
        "montants_eur": find_eur_amounts(text),
        "qualite_estimee": result.get("qualite_estimee", 0),
        "erreur": result.get("erreur"),
    }


def run_mlx(pdf_path: str) -> dict:
    """Benchmark MLX VLM OCR."""
    try:
        from tools.paddleocr_mlx import ocr_pdf_mlx
    except ImportError:
        try:
            from paddleocr_mlx import ocr_pdf_mlx
        except ImportError:
            return {
                "strategie": "MLX VLM",
                "erreur": "mlx-vlm non installé",
                "temps_sec": 0,
                "longueur_texte": 0,
                "nombre_pages": 0,
                "tableaux_detectes": 0,
                "montants_eur": [],
                "qualite_estimee": 0,
            }

    start = time.time()
    result = ocr_pdf_mlx(pdf_path)
    elapsed = time.time() - start

    text = result.get("texte_complet", "")
    return {
        "strategie": "MLX VLM",
        "temps_sec": round(elapsed, 2),
        "longueur_texte": len(text),
        "nombre_pages": result.get("nombre_pages", 0),
        "tableaux_detectes": count_tables_in_text(text),
        "montants_eur": find_eur_amounts(text),
        "qualite_estimee": result.get("qualite_estimee", 0),
        "erreur": result.get("erreur"),
    }


def identify_scanned_pdfs(samples_dir: str) -> list:
    """Identifie les PDFs scannés (peu de texte natif)."""
    import pdfplumber

    scanned = []
    for fname in sorted(os.listdir(samples_dir)):
        if not fname.lower().endswith(".pdf"):
            continue
        pdf_path = os.path.join(samples_dir, fname)
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_chars = sum(len(page.extract_text() or "") for page in pdf.pages)
                chars_per_page = total_chars / max(len(pdf.pages), 1)
                if chars_per_page < 50:
                    scanned.append(pdf_path)
        except Exception:
            pass
    return scanned


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Benchmark OCR : Tesseract vs PaddleOCR vs MLX")
    parser.add_argument("--samples-dir", default="samples/", help="Répertoire des PDFs")
    parser.add_argument("--output-dir", default="output/benchmark/", help="Répertoire de sortie")
    parser.add_argument("--all", action="store_true", help="Tester tous les PDFs (pas seulement les scannés)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Identifier les PDFs à tester
    if args.all:
        pdfs = [
            os.path.join(args.samples_dir, f)
            for f in sorted(os.listdir(args.samples_dir))
            if f.lower().endswith(".pdf")
        ]
    else:
        pdfs = identify_scanned_pdfs(args.samples_dir)
        if not pdfs:
            print("Aucun PDF scanné détecté. Utilisez --all pour tester tous les PDFs.")
            # Fallback : tester tous les PDFs
            pdfs = [
                os.path.join(args.samples_dir, f)
                for f in sorted(os.listdir(args.samples_dir))
                if f.lower().endswith(".pdf")
            ]

    print(f"PDFs à tester : {len(pdfs)}")
    for p in pdfs:
        print(f"  - {os.path.basename(p)}")
    print()

    strategies = [
        ("Tesseract", run_tesseract),
        ("PaddleOCR", run_paddleocr),
        ("MLX VLM", run_mlx),
    ]

    all_results = []

    for pdf_path in pdfs:
        fname = os.path.basename(pdf_path)
        print(f"{'=' * 60}")
        print(f"PDF : {fname}")
        print(f"{'=' * 60}")

        for strat_name, strat_func in strategies:
            print(f"  {strat_name}...", end=" ", flush=True)
            try:
                bench = strat_func(pdf_path)
            except Exception as e:
                bench = {
                    "strategie": strat_name,
                    "erreur": str(e),
                    "temps_sec": 0,
                    "longueur_texte": 0,
                    "nombre_pages": 0,
                    "tableaux_detectes": 0,
                    "montants_eur": [],
                    "qualite_estimee": 0,
                }

            bench["fichier"] = fname
            nb_montants = len(bench.get("montants_eur", []))

            if bench.get("erreur"):
                print(f"ERREUR: {bench['erreur']}")
            else:
                print(
                    f"{bench['temps_sec']}s | "
                    f"{bench['longueur_texte']} chars | "
                    f"{bench['tableaux_detectes']} tables | "
                    f"{nb_montants} montants EUR | "
                    f"qualité {bench['qualite_estimee']}"
                )

            all_results.append(bench)

        print()

    # Tableau comparatif
    try:
        from tabulate import tabulate

        headers = ["Fichier", "Stratégie", "Temps (s)", "Texte (chars)", "Tables", "Montants EUR", "Qualité", "Erreur"]
        rows = []
        for r in all_results:
            rows.append([
                r.get("fichier", "?")[:30],
                r["strategie"],
                r["temps_sec"],
                r["longueur_texte"],
                r["tableaux_detectes"],
                len(r.get("montants_eur", [])),
                r["qualite_estimee"],
                (r.get("erreur") or "")[:40],
            ])
        print("\n" + tabulate(rows, headers=headers, tablefmt="grid"))
    except ImportError:
        print("\n(tabulate non installé — pas de tableau formaté)")

    # Sauvegarder les résultats
    output_path = os.path.join(args.output_dir, "ocr_comparison.json")
    # Convertir les montants pour la sérialisation JSON
    for r in all_results:
        r["nombre_montants_eur"] = len(r.get("montants_eur", []))
        r["montants_eur"] = [round(m, 2) for m in r.get("montants_eur", [])]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\nRésultats sauvegardés dans {output_path}")


if __name__ == "__main__":
    main()
