"""Domain extraction strategy selection — pure functions, zero external dependencies.

Only stdlib imports allowed.
"""

from enum import Enum


class ExtractionStrategy(Enum):
    """Available PDF extraction strategies."""

    PDFPLUMBER_TEXT = "pdfplumber_text"
    PDFPLUMBER_TABLES = "pdfplumber_tables"
    OCR_TESSERACT = "ocr_tesseract"
    OCR_PADDLEOCR = "ocr_paddleocr"
    OCR_MLX_VLM = "ocr_mlx_vlm"
    MIXED = "mixed_strategy"


def select_strategy(chars_per_page, has_tables, threshold=50):
    """Select extraction strategy based on PDF characteristics."""
    if chars_per_page < threshold:
        return ExtractionStrategy.OCR_TESSERACT
    if has_tables:
        return ExtractionStrategy.PDFPLUMBER_TABLES
    return ExtractionStrategy.PDFPLUMBER_TEXT


def build_fallback_chain(primary):
    """Build ordered fallback chain starting from the primary strategy."""
    full_chain = [
        ExtractionStrategy.PDFPLUMBER_TEXT,
        ExtractionStrategy.OCR_PADDLEOCR,
        ExtractionStrategy.OCR_MLX_VLM,
        ExtractionStrategy.OCR_TESSERACT,
    ]
    if primary in full_chain:
        idx = full_chain.index(primary)
        return full_chain[idx:]
    return full_chain
