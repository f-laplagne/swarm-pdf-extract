#!/usr/bin/env python3
"""
ocr_processor.py — OCR pour PDFs scannés avec pré-traitement d'image.

Usage:
    python tools/ocr_processor.py <fichier.pdf> [--lang fra] [--dpi 300] [--preprocess]

Pré-traitements disponibles:
    --preprocess  Active le deskew, binarisation et débruitage avant OCR
"""

import sys
import json
import os
import tempfile

try:
    from pdf2image import convert_from_path
except ImportError:
    print("ERREUR: pdf2image non installé. pip install pdf2image", file=sys.stderr)
    print("Note: nécessite aussi poppler-utils (apt install poppler-utils)", file=sys.stderr)
    sys.exit(1)

try:
    import pytesseract
except ImportError:
    print("ERREUR: pytesseract non installé. pip install pytesseract", file=sys.stderr)
    print("Note: nécessite aussi tesseract-ocr (apt install tesseract-ocr tesseract-ocr-fra)", file=sys.stderr)
    sys.exit(1)


def preprocess_image(image):
    """Pré-traitement d'image pour améliorer l'OCR."""
    try:
        import cv2
        import numpy as np
        
        # Convertir PIL → OpenCV
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
        
        # Binarisation adaptative
        img = cv2.adaptiveThreshold(
            img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        
        # Débruitage
        img = cv2.medianBlur(img, 1)
        
        # Reconvertir en PIL
        from PIL import Image
        return Image.fromarray(img)
    
    except ImportError:
        # Si OpenCV n'est pas disponible, retourner l'image telle quelle
        return image


def ocr_pdf(pdf_path: str, lang: str = "fra", dpi: int = 300, do_preprocess: bool = False) -> dict:
    """OCR complet d'un PDF."""
    result = {
        "fichier": os.path.basename(pdf_path),
        "methode": "ocr_tesseract",
        "langue_ocr": lang,
        "dpi": dpi,
        "preprocess": do_preprocess,
        "pages": [],
        "texte_complet": "",
        "nombre_pages": 0,
        "qualite_estimee": 0.0
    }
    
    try:
        # Convertir PDF en images
        images = convert_from_path(pdf_path, dpi=dpi)
        result["nombre_pages"] = len(images)
        
        all_text = []
        all_confidences = []
        
        for i, image in enumerate(images):
            # Pré-traitement si demandé
            if do_preprocess:
                image = preprocess_image(image)
            
            # OCR avec données de confiance
            ocr_data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
            
            # Texte simple
            page_text = pytesseract.image_to_string(image, lang=lang)
            
            # Calculer la confiance moyenne
            confidences = [int(c) for c in ocr_data["conf"] if c != "-1" and str(c).strip()]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            all_confidences.extend(confidences)
            
            all_text.append(page_text)
            
            result["pages"].append({
                "page": i + 1,
                "texte": page_text,
                "longueur": len(page_text),
                "confiance_moyenne": round(avg_confidence, 1),
                "mots_detectes": len([w for w in ocr_data["text"] if w.strip()]),
                "tables_count": 0  # OCR ne détecte pas les tableaux nativement
            })
        
        result["texte_complet"] = "\n\n--- PAGE ---\n\n".join(all_text)
        
        # Qualité globale estimée
        if all_confidences:
            result["qualite_estimee"] = round(sum(all_confidences) / len(all_confidences) / 100, 2)
        
    except Exception as e:
        result["erreur"] = str(e)
    
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="OCR pour PDFs scannés")
    parser.add_argument("pdf_path", help="Chemin vers le fichier PDF")
    parser.add_argument("--lang", default="fra", help="Langue Tesseract (fra, eng, fra+eng)")
    parser.add_argument("--dpi", type=int, default=300, help="DPI pour la conversion")
    parser.add_argument("--preprocess", action="store_true", help="Activer le pré-traitement d'image")
    parser.add_argument("--output", choices=["json", "text"], default="json")
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf_path):
        print(f"ERREUR: Fichier non trouvé: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)
    
    result = ocr_pdf(args.pdf_path, lang=args.lang, dpi=args.dpi, do_preprocess=args.preprocess)
    
    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result.get("texte_complet", ""))


if __name__ == "__main__":
    main()
