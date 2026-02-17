"""Integration tests for PDF extraction adapters."""

import pytest
from abc import ABC
from domain.ports import PDFTextExtractorPort, OCRProcessorPort
from tools.adapters.pdfplumber_extractor import PdfplumberExtractor
from tools.adapters.tesseract_ocr import TesseractOCR


class TestPdfplumberExtractor:
    def test_implements_port(self):
        assert issubclass(PdfplumberExtractor, PDFTextExtractorPort)
        assert isinstance(PdfplumberExtractor(), PDFTextExtractorPort)

    def test_extract_nonexistent_file(self):
        extractor = PdfplumberExtractor()
        result = extractor.extract_text("/nonexistent/path.pdf")
        assert result["success"] is False
        assert "error" in result
        assert result["strategy"] == "pdfplumber"

    def test_extract_returns_expected_structure(self):
        extractor = PdfplumberExtractor()
        result = extractor.extract_text("/nonexistent/path.pdf")
        assert "success" in result
        assert "pages" in result
        assert "strategy" in result


class TestTesseractOCR:
    def test_implements_port(self):
        assert issubclass(TesseractOCR, OCRProcessorPort)
        assert isinstance(TesseractOCR(), OCRProcessorPort)

    def test_extract_nonexistent_file(self):
        ocr = TesseractOCR()
        result = ocr.extract_text_ocr("/nonexistent/path.pdf")
        # Either Tesseract not installed or file doesn't exist -- both return failure
        assert result["success"] is False
        assert "error" in result
        assert result["strategy"] == "tesseract"

    def test_extract_returns_expected_structure(self):
        ocr = TesseractOCR()
        result = ocr.extract_text_ocr("/nonexistent/path.pdf")
        assert "success" in result
        assert "pages" in result
        assert "strategy" in result

    def test_default_lang(self):
        ocr = TesseractOCR()
        # Test that the method accepts the default lang parameter
        result = ocr.extract_text_ocr("/nonexistent/path.pdf", lang="eng")
        assert result["strategy"] == "tesseract"
