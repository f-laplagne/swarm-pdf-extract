"""PDF text extraction adapter using pdfplumber."""

from domain.ports import PDFTextExtractorPort


class PdfplumberExtractor(PDFTextExtractorPort):
    """Extracts text from native PDF files using pdfplumber."""

    def extract_text(self, pdf_path: str) -> dict:
        try:
            import pdfplumber
        except ImportError:
            return {
                "success": False,
                "error": "pdfplumber not installed",
                "pages": [],
                "strategy": "pdfplumber",
            }

        try:
            pages = []
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    pages.append({
                        "page": i,
                        "text": text,
                        "chars_count": len(text),
                    })
            return {
                "success": True,
                "pages": pages,
                "total_pages": len(pages),
                "strategy": "pdfplumber",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "pages": [],
                "strategy": "pdfplumber",
            }
