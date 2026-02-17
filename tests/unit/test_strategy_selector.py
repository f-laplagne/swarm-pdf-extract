"""Tests for domain.extraction.strategy_selector — strategy selection and fallback."""

import pytest

from domain.extraction.strategy_selector import (
    ExtractionStrategy,
    build_fallback_chain,
    select_strategy,
)


class TestSelectStrategy:
    """Tests for select_strategy."""

    def test_text_pdf_high_chars(self):
        result = select_strategy(chars_per_page=500, has_tables=False)
        assert result == ExtractionStrategy.PDFPLUMBER_TEXT

    def test_table_pdf(self):
        result = select_strategy(chars_per_page=500, has_tables=True)
        assert result == ExtractionStrategy.PDFPLUMBER_TABLES

    def test_scanned_pdf_low_chars(self):
        result = select_strategy(chars_per_page=10, has_tables=False)
        assert result == ExtractionStrategy.OCR_TESSERACT

    def test_scanned_pdf_with_tables_low_chars(self):
        # Low chars trumps tables — OCR needed first
        result = select_strategy(chars_per_page=10, has_tables=True)
        assert result == ExtractionStrategy.OCR_TESSERACT

    def test_threshold_boundary_below(self):
        result = select_strategy(chars_per_page=49, has_tables=False)
        assert result == ExtractionStrategy.OCR_TESSERACT

    def test_threshold_boundary_at(self):
        result = select_strategy(chars_per_page=50, has_tables=False)
        assert result == ExtractionStrategy.PDFPLUMBER_TEXT

    def test_threshold_boundary_above(self):
        result = select_strategy(chars_per_page=51, has_tables=False)
        assert result == ExtractionStrategy.PDFPLUMBER_TEXT

    def test_custom_threshold(self):
        result = select_strategy(chars_per_page=80, has_tables=False, threshold=100)
        assert result == ExtractionStrategy.OCR_TESSERACT

    def test_zero_chars(self):
        result = select_strategy(chars_per_page=0, has_tables=False)
        assert result == ExtractionStrategy.OCR_TESSERACT


class TestBuildFallbackChain:
    """Tests for build_fallback_chain."""

    def test_fallback_from_pdfplumber_text(self):
        chain = build_fallback_chain(ExtractionStrategy.PDFPLUMBER_TEXT)
        assert chain == [
            ExtractionStrategy.PDFPLUMBER_TEXT,
            ExtractionStrategy.OCR_PADDLEOCR,
            ExtractionStrategy.OCR_MLX_VLM,
            ExtractionStrategy.OCR_TESSERACT,
        ]

    def test_fallback_from_paddleocr(self):
        chain = build_fallback_chain(ExtractionStrategy.OCR_PADDLEOCR)
        assert chain == [
            ExtractionStrategy.OCR_PADDLEOCR,
            ExtractionStrategy.OCR_MLX_VLM,
            ExtractionStrategy.OCR_TESSERACT,
        ]

    def test_fallback_from_mlx(self):
        chain = build_fallback_chain(ExtractionStrategy.OCR_MLX_VLM)
        assert chain == [
            ExtractionStrategy.OCR_MLX_VLM,
            ExtractionStrategy.OCR_TESSERACT,
        ]

    def test_fallback_from_tesseract(self):
        chain = build_fallback_chain(ExtractionStrategy.OCR_TESSERACT)
        assert chain == [ExtractionStrategy.OCR_TESSERACT]

    def test_fallback_from_non_chain_strategy(self):
        # PDFPLUMBER_TABLES and MIXED are not in the full_chain
        chain = build_fallback_chain(ExtractionStrategy.PDFPLUMBER_TABLES)
        assert chain == [
            ExtractionStrategy.PDFPLUMBER_TEXT,
            ExtractionStrategy.OCR_PADDLEOCR,
            ExtractionStrategy.OCR_MLX_VLM,
            ExtractionStrategy.OCR_TESSERACT,
        ]

    def test_fallback_from_mixed(self):
        chain = build_fallback_chain(ExtractionStrategy.MIXED)
        assert chain == [
            ExtractionStrategy.PDFPLUMBER_TEXT,
            ExtractionStrategy.OCR_PADDLEOCR,
            ExtractionStrategy.OCR_MLX_VLM,
            ExtractionStrategy.OCR_TESSERACT,
        ]


class TestExtractionStrategyEnum:
    """Tests for ExtractionStrategy enum values."""

    def test_all_strategies_exist(self):
        assert ExtractionStrategy.PDFPLUMBER_TEXT.value == "pdfplumber_text"
        assert ExtractionStrategy.PDFPLUMBER_TABLES.value == "pdfplumber_tables"
        assert ExtractionStrategy.OCR_TESSERACT.value == "ocr_tesseract"
        assert ExtractionStrategy.OCR_PADDLEOCR.value == "ocr_paddleocr"
        assert ExtractionStrategy.OCR_MLX_VLM.value == "ocr_mlx_vlm"
        assert ExtractionStrategy.MIXED.value == "mixed_strategy"
