#!/usr/bin/env python3
"""
paddleocr_processor.py — PP-StructureV3 natif (CPU) ou via API Docker.

Usage:
    python tools/paddleocr_processor.py <fichier.pdf> [--mode native|docker] [--docker-url http://localhost:8080]

Modes:
    native  — API Python PPStructureV3 directe (CPU sur Mac)
    docker  — Appel REST API au conteneur Docker
"""

import sys
import json
import os
import re
import time


def extract_tables_from_markdown(markdown_text: str) -> list:
    """Parse les tableaux Markdown produits par PP-StructureV3."""
    tables = []
    lines = markdown_text.split("\n")
    current_table = None

    for line in lines:
        stripped = line.strip()
        if "|" in stripped and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            # Ignorer les lignes de séparation (|---|---|)
            if all(re.match(r"^[-:]+$", c) for c in cells if c):
                continue
            if current_table is None:
                current_table = {"headers": cells, "rows": []}
            else:
                current_table["rows"].append(cells)
        else:
            if current_table is not None:
                current_table["num_rows"] = len(current_table["rows"])
                current_table["num_cols"] = len(current_table["headers"])
                tables.append(current_table)
                current_table = None

    # Dernier tableau en cours
    if current_table is not None:
        current_table["num_rows"] = len(current_table["rows"])
        current_table["num_cols"] = len(current_table["headers"])
        tables.append(current_table)

    return tables


def ocr_paddleocr_native(pdf_path: str) -> dict:
    """OCR via PP-StructureV3 en mode natif (CPU)."""
    try:
        from paddleocr import PPStructureV3
    except ImportError:
        return {
            "erreur": "paddleocr non installé. pip install paddleocr>=3.4.0 paddlepaddle==3.3.0"
        }

    result = {
        "fichier": os.path.basename(pdf_path),
        "methode": "paddleocr_native",
        "pages": [],
        "texte_complet": "",
        "nombre_pages": 0,
        "qualite_estimee": 0.0,
        "tables_detectees": [],
    }

    try:
        print("Initialisation PP-StructureV3...", file=sys.stderr)
        start = time.time()
        pipeline = PPStructureV3()

        print(f"Traitement de {pdf_path}...", file=sys.stderr)
        output = pipeline.predict(input=pdf_path)

        all_text = []
        all_tables = []
        page_num = 0

        for res in output:
            page_num += 1
            page_text_parts = []

            for item in res:
                item_str = str(item)
                page_text_parts.append(item_str)

                # Extraire les tableaux du markdown
                tables = extract_tables_from_markdown(item_str)
                for t in tables:
                    t["page"] = page_num
                    all_tables.append(t)

            page_text = "\n".join(page_text_parts)
            all_text.append(page_text)

            result["pages"].append({
                "page": page_num,
                "texte": page_text,
                "longueur": len(page_text),
                "confiance_moyenne": 0.8,  # PP-StructureV3 ne fournit pas de score mot-à-mot
                "tables_count": len(tables),
            })

        elapsed = time.time() - start
        result["texte_complet"] = "\n\n--- PAGE ---\n\n".join(all_text)
        result["nombre_pages"] = page_num
        result["tables_detectees"] = all_tables
        result["temps_traitement"] = round(elapsed, 2)

        # Qualité estimée : basée sur la longueur du texte et le nombre de tableaux
        total_chars = sum(p["longueur"] for p in result["pages"])
        if total_chars > 500 and len(all_tables) > 0:
            result["qualite_estimee"] = 0.85
        elif total_chars > 200:
            result["qualite_estimee"] = 0.7
        elif total_chars > 50:
            result["qualite_estimee"] = 0.5
        else:
            result["qualite_estimee"] = 0.2

    except Exception as e:
        result["erreur"] = str(e)

    return result


def ocr_paddleocr_docker(pdf_path: str, docker_url: str = "http://localhost:8080") -> dict:
    """OCR via PP-StructureV3 en mode Docker (API REST)."""
    import base64

    try:
        import requests
    except ImportError:
        return {"erreur": "requests non installé. pip install requests"}

    result = {
        "fichier": os.path.basename(pdf_path),
        "methode": "paddleocr_docker",
        "pages": [],
        "texte_complet": "",
        "nombre_pages": 0,
        "qualite_estimee": 0.0,
        "tables_detectees": [],
    }

    try:
        # Vérifier que le service est accessible
        health_url = f"{docker_url}/health"
        try:
            resp = requests.get(health_url, timeout=5)
            if resp.status_code != 200:
                return {"erreur": f"Service Docker non disponible sur {docker_url}"}
        except requests.ConnectionError:
            return {"erreur": f"Impossible de se connecter à {docker_url}. Le conteneur est-il démarré ?"}

        # Envoyer le PDF encodé en base64
        with open(pdf_path, "rb") as f:
            file_bytes = f.read()

        payload = {
            "file_base64": base64.b64encode(file_bytes).decode("utf-8"),
            "suffix": ".pdf",
        }

        start = time.time()
        predict_url = f"{docker_url}/predict"
        resp = requests.post(predict_url, json=payload, timeout=300)
        elapsed = time.time() - start

        if resp.status_code != 200:
            return {"erreur": f"Erreur API Docker: {resp.status_code} — {resp.text}"}

        data = resp.json()
        if data.get("status") != "ok":
            return {"erreur": f"Erreur PP-StructureV3: {data.get('message', 'inconnue')}"}

        # Parser les résultats
        all_text = []
        all_tables = []
        for i, item_str in enumerate(data.get("results", [])):
            all_text.append(item_str)
            tables = extract_tables_from_markdown(item_str)
            for t in tables:
                t["page"] = i + 1
                all_tables.append(t)

        combined_text = "\n\n--- PAGE ---\n\n".join(all_text)
        result["texte_complet"] = combined_text
        result["nombre_pages"] = len(data.get("results", []))
        result["tables_detectees"] = all_tables
        result["temps_traitement"] = round(elapsed, 2)

        # Pages individuelles
        for i, text in enumerate(all_text):
            page_tables = [t for t in all_tables if t.get("page") == i + 1]
            result["pages"].append({
                "page": i + 1,
                "texte": text,
                "longueur": len(text),
                "confiance_moyenne": 0.8,
                "tables_count": len(page_tables),
            })

        total_chars = sum(p["longueur"] for p in result["pages"])
        if total_chars > 500 and len(all_tables) > 0:
            result["qualite_estimee"] = 0.85
        elif total_chars > 200:
            result["qualite_estimee"] = 0.7
        elif total_chars > 50:
            result["qualite_estimee"] = 0.5
        else:
            result["qualite_estimee"] = 0.2

    except Exception as e:
        result["erreur"] = str(e)

    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="PP-StructureV3 OCR (natif ou Docker)")
    parser.add_argument("pdf_path", help="Chemin vers le fichier PDF")
    parser.add_argument(
        "--mode",
        choices=["native", "docker"],
        default="native",
        help="Mode d'exécution",
    )
    parser.add_argument(
        "--docker-url",
        default="http://localhost:8080",
        help="URL du service Docker PP-StructureV3",
    )
    parser.add_argument("--output", choices=["json", "text"], default="json")
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"ERREUR: Fichier non trouvé: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    if args.mode == "native":
        result = ocr_paddleocr_native(args.pdf_path)
    else:
        result = ocr_paddleocr_docker(args.pdf_path, docker_url=args.docker_url)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("texte_complet", ""))


if __name__ == "__main__":
    main()
