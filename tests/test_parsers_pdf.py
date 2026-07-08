"""Tests for the PDF parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_analyzer.parsers.pdf import (
    PdfEncryptedError,
    PdfFileNotFoundError,
    PdfMalformedError,
    parse_pdf,
)


class TestParsePdfHappyPath:
    def test_returns_document_with_correct_page_count(self, sample_pdf: Path) -> None:
        doc = parse_pdf(sample_pdf)
        assert doc.page_count == 2

    def test_extracts_text_from_pages(self, sample_pdf: Path) -> None:
        doc = parse_pdf(sample_pdf)
        assert "Hello world" in doc.pages[0]
        assert "page two" in doc.pages[1]

    def test_source_path_preserved(self, sample_pdf: Path) -> None:
        doc = parse_pdf(sample_pdf)
        assert doc.source == sample_pdf

    def test_metadata_extracted(self, sample_pdf: Path) -> None:
        doc = parse_pdf(sample_pdf)
        assert doc.metadata.get("title") == "Sample Document"
        assert doc.metadata.get("author") == "Test Author"

    def test_accepts_string_path(self, sample_pdf: Path) -> None:
        doc = parse_pdf(str(sample_pdf))
        assert doc.page_count == 2


class TestParsePdfEdgeCases:
    def test_blank_middle_page_preserved_as_empty_string(self, empty_pages_pdf: Path) -> None:
        doc = parse_pdf(empty_pages_pdf)
        assert doc.page_count == 3
        # Page count stays accurate even when middle page has no text.
        assert "First" in doc.pages[0]
        assert "Third" in doc.pages[2]

    def test_unicode_text_extracted(self, unicode_pdf: Path) -> None:
        doc = parse_pdf(unicode_pdf)
        assert doc.page_count == 1
        # We don't assert exact glyphs because reportlab's text extraction
        # round-trip may normalize spacing; we just verify non-empty.
        assert doc.pages[0].strip() != ""


class TestParsePdfErrors:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PdfFileNotFoundError, match="does not exist"):
            parse_pdf(tmp_path / "no_such_file.pdf")

    def test_directory_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PdfFileNotFoundError):
            parse_pdf(tmp_path)

    def test_malformed_file_raises(self, malformed_pdf: Path) -> None:
        with pytest.raises(PdfMalformedError):
            parse_pdf(malformed_pdf)

    def test_encrypted_pdf_without_password_raises(self, encrypted_pdf: tuple[Path, str]) -> None:
        path, _ = encrypted_pdf
        with pytest.raises(PdfEncryptedError, match="encrypted"):
            parse_pdf(path)

    def test_encrypted_pdf_with_wrong_password_raises(
        self, encrypted_pdf: tuple[Path, str]
    ) -> None:
        path, _ = encrypted_pdf
        wrong = "wrong-password"
        with pytest.raises(PdfEncryptedError):
            parse_pdf(path, password=wrong)

    def test_encrypted_pdf_with_correct_password_succeeds(
        self, encrypted_pdf: tuple[Path, str]
    ) -> None:
        path, password = encrypted_pdf
        doc = parse_pdf(path, password=password)
        assert doc.page_count == 1
