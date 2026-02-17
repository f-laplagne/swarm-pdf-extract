"""OCR text extraction adapter using Tesseract."""

from domain.ports import OCRProcessorPort


class TesseractOCR(OCRProcessorPort):
    """Extracts text from scanned PDF images using Tesseract OCR."""

    def extract_text_ocr(self, pdf_path: str, lang: str = "fra+eng") -> dict:
        try:
            import subprocess
            result = subprocess.run(
                ["tesseract", "--version"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError("Tesseract not available")
        except (FileNotFoundError, RuntimeError):
            return {
                "success": False,
                "error": "Tesseract not installed or not in PATH",
                "pages": [],
                "strategy": "tesseract",
            }

        try:
            from pdf2image import convert_from_path
            import pytesseract

            images = convert_from_path(pdf_path)
            pages = []
            for i, img in enumerate(images, 1):
                text = pytesseract.image_to_string(img, lang=lang)
                pages.append({
                    "page": i,
                    "text": text,
                    "chars_count": len(text),
                })
            return {
                "success": True,
                "pages": pages,
                "total_pages": len(pages),
                "strategy": "tesseract",
            }
        except ImportError as e:
            return {
                "success": False,
                "error": f"Missing dependency: {e}",
                "pages": [],
                "strategy": "tesseract",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "pages": [],
                "strategy": "tesseract",
            }
