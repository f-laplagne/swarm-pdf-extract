#!/usr/bin/env python3
"""
paddleocr_mlx.py — OCR VLM via MLX (GPU Metal Apple Silicon).

Usage:
    python tools/paddleocr_mlx.py <fichier.pdf> [--model paddleocr-vl] [--dpi 300] [--output json|text]

Modèles disponibles:
    paddleocr-vl  — mlx-community/PaddleOCR-VL-1.5-4bit (704 MB, Apache 2.0)
"""

import sys
import json
import os
import re
import time

MODELS = {
    "paddleocr-vl": "mlx-community/PaddleOCR-VL-1.5-4bit",
}

EXTRACTION_PROMPT = """Analyse cette image de document (facture/bon de livraison transport français).
Extrais TOUT le texte visible en préservant la structure tabulaire.

Pour les tableaux, utilise le format Markdown avec colonnes alignées :
| Colonne1 | Colonne2 | ... |

Préserve particulièrement :
- Les colonnes de prix (prix unitaire, montant, total HT/TTC)
- Les dates (départ, arrivée, facture)
- Les lieux (départ, arrivée)
- Les descriptions de matières/marchandises
- Les quantités et unités

Si un texte est illisible, indique [illisible].
Retourne le texte brut structuré, pas de commentaire."""

# Cache global pour le modèle chargé
_model_cache = {}


def load_model(model_key: str = "paddleocr-vl"):
    """Charge le modèle MLX une fois, cache pour réutilisation."""
    if model_key in _model_cache:
        return _model_cache[model_key]

    try:
        from mlx_vlm import load
    except ImportError:
        print("ERREUR: mlx-vlm non installé. pip install mlx-vlm>=0.3.11", file=sys.stderr)
        sys.exit(1)

    model_path = MODELS.get(model_key, model_key)
    print(f"Chargement du modèle {model_path}...", file=sys.stderr)

    model, processor = load(model_path)
    _model_cache[model_key] = (model, processor, model_path)
    return model, processor, model_path


def process_page(model, processor, config, image, page_num: int) -> dict:
    """Inference VLM sur une page. L'image PIL est sauvée en temp file car mlx_vlm attend un path."""
    import tempfile
    from mlx_vlm import generate

    start = time.time()

    # mlx_vlm.generate() attend un chemin fichier pour image, pas un objet PIL
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        image.save(tmp, format="PNG")
        tmp_path = tmp.name

    try:
        result_obj = generate(
            model,
            processor,
            EXTRACTION_PROMPT,
            image=tmp_path,
            max_tokens=config["max_tokens"],
            temperature=config["temperature"],
            verbose=False,
        )
    finally:
        os.unlink(tmp_path)

    elapsed = time.time() - start
    # generate() returns a GenerationResult object
    if hasattr(result_obj, 'text'):
        text = result_obj.text.strip()
    elif isinstance(result_obj, str):
        text = result_obj.strip()
    else:
        text = str(result_obj).strip()

    # Heuristique de confiance basée sur la longueur et les marqueurs d'erreur
    illisible_count = len(re.findall(r"\[illisible\]", text, re.IGNORECASE))
    text_length = len(text)

    if text_length < 20:
        confidence = 0.1
    elif text_length < 100:
        confidence = 0.4
    elif illisible_count > 5:
        confidence = 0.5
    elif illisible_count > 0:
        confidence = 0.7
    else:
        confidence = 0.85

    return {
        "page": page_num,
        "texte": text,
        "longueur": text_length,
        "confiance_moyenne": round(confidence, 2),
        "temps_inference": round(elapsed, 2),
        "marqueurs_illisible": illisible_count,
    }


def ocr_pdf_mlx(pdf_path: str, model_key: str = "paddleocr-vl", dpi: int = 300) -> dict:
    """Point d'entrée principal : OCR VLM sur un PDF complet."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        return {"erreur": "pdf2image non installé. pip install pdf2image"}

    config = {
        "max_tokens": 4096,
        "temperature": 0.0,
    }

    result = {
        "fichier": os.path.basename(pdf_path),
        "methode": "mlx_paddleocr_vl",
        "pages": [],
        "texte_complet": "",
        "nombre_pages": 0,
        "qualite_estimee": 0.0,
        "modele_utilise": MODELS.get(model_key, model_key),
        "temps_inference": 0.0,
    }

    try:
        # Charger le modèle
        model, processor, model_path = load_model(model_key)
        result["modele_utilise"] = model_path

        # Convertir PDF en images
        print(f"Conversion PDF → images ({dpi} DPI)...", file=sys.stderr)
        images = convert_from_path(pdf_path, dpi=dpi)
        result["nombre_pages"] = len(images)

        all_text = []
        total_time = 0.0

        for i, image in enumerate(images):
            print(f"  Page {i + 1}/{len(images)}...", file=sys.stderr)
            page_result = process_page(model, processor, config, image, i + 1)
            result["pages"].append(page_result)
            all_text.append(page_result["texte"])
            total_time += page_result["temps_inference"]

        result["texte_complet"] = "\n\n--- PAGE ---\n\n".join(all_text)
        result["temps_inference"] = round(total_time, 2)

        # Qualité globale : moyenne pondérée des confiances par page
        if result["pages"]:
            confidences = [p["confiance_moyenne"] for p in result["pages"]]
            result["qualite_estimee"] = round(sum(confidences) / len(confidences), 2)

    except Exception as e:
        result["erreur"] = str(e)

    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(description="OCR VLM via MLX (GPU Metal)")
    parser.add_argument("pdf_path", help="Chemin vers le fichier PDF")
    parser.add_argument(
        "--model",
        default="paddleocr-vl",
        choices=list(MODELS.keys()),
        help="Modèle VLM à utiliser",
    )
    parser.add_argument("--dpi", type=int, default=300, help="DPI pour la conversion")
    parser.add_argument("--output", choices=["json", "text"], default="json")
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"ERREUR: Fichier non trouvé: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    result = ocr_pdf_mlx(args.pdf_path, model_key=args.model, dpi=args.dpi)

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("texte_complet", ""))


if __name__ == "__main__":
    main()
