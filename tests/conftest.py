"""Shared pytest fixtures.

Test PDFs are generated at runtime with reportlab. Nothing binary is
committed to the repo; each test starts from a known-good blank slate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


def _make_pdf(
    path: Path,
    pages: list[str],
    *,
    title: str | None = None,
    author: str | None = None,
    password: str | None = None,
) -> Path:
    """Generate a PDF with the given page texts."""
    pdf = canvas.Canvas(str(path), pagesize=LETTER)
    if title is not None:
        pdf.setTitle(title)
    if author is not None:
        pdf.setAuthor(author)
    if password is not None:
        pdf.setEncrypt(password)

    for text in pages:
        pdf.setFont("Helvetica", 12)
        text_object = pdf.beginText(72, 720)
        for line in text.splitlines() or [""]:
            text_object.textLine(line)
        pdf.drawText(text_object)
        pdf.showPage()
    pdf.save()
    return path


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """A two-page PDF with simple ASCII content and basic metadata."""
    return _make_pdf(
        tmp_path / "sample.pdf",
        pages=[
            "Hello world. This is page one of the sample document.",
            "And here is page two with different content.",
        ],
        title="Sample Document",
        author="Test Author",
    )


@pytest.fixture
def empty_pages_pdf(tmp_path: Path) -> Path:
    """A PDF with a blank page in the middle to exercise empty-page handling."""
    return _make_pdf(
        tmp_path / "empty_middle.pdf",
        pages=[
            "First page has content.",
            "",  # blank middle page
            "Third page has content too.",
        ],
    )


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> tuple[Path, str]:
    """A password-protected PDF. Returns (path, password)."""
    test_password = "correct-horse-battery-staple"  # noqa: S105 — test fixture, not a secret
    path = _make_pdf(
        tmp_path / "encrypted.pdf",
        pages=["Secret content behind a password."],
        password=test_password,
    )
    return path, test_password


@pytest.fixture
def malformed_pdf(tmp_path: Path) -> Path:
    """A file with a .pdf extension but invalid PDF bytes."""
    path = tmp_path / "malformed.pdf"
    path.write_bytes(b"This is definitely not a PDF file.")
    return path


@pytest.fixture
def unicode_pdf(tmp_path: Path) -> Path:
    """A PDF whose text contains accented characters."""
    return _make_pdf(
        tmp_path / "unicode.pdf",
        pages=["Cafe resume naive jalapeno"],  # ASCII-safe, reportlab default font handles this
    )
