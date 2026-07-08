"""PDF parsing.

Wraps `pypdf` with explicit handling for the failure modes we care about:
encrypted PDFs, malformed files, empty pages, and Unicode edge cases.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from doc_analyzer.models import Document

logger = logging.getLogger(__name__)


class PdfParserError(Exception):
    """Base class for all PDF parsing failures."""


class PdfFileNotFoundError(PdfParserError):
    """The path does not exist or is not a regular file."""


class PdfEncryptedError(PdfParserError):
    """The PDF is password-protected and no password was supplied."""


class PdfMalformedError(PdfParserError):
    """The file exists but pypdf cannot parse it as a valid PDF."""


def parse_pdf(path: str | Path, *, password: str | None = None) -> Document:
    """Parse a PDF file into a :class:`Document`.

    Args:
        path: Filesystem path to the PDF.
        password: Optional password for encrypted PDFs.

    Returns:
        A Document with one page entry per source page (empty pages
        preserved as empty strings).

    Raises:
        PdfFileNotFoundError: ``path`` is not an existing regular file.
        PdfEncryptedError: PDF is encrypted and the password (if any) is wrong.
        PdfMalformedError: pypdf cannot parse the file.
    """
    pdf_path = Path(path)

    if not pdf_path.is_file():
        raise PdfFileNotFoundError(f"PDF file does not exist: {pdf_path}")

    try:
        reader = PdfReader(str(pdf_path))
    except PdfReadError as exc:
        raise PdfMalformedError(f"Failed to parse PDF: {pdf_path}") from exc
    except Exception as exc:  # pypdf raises various uncategorized errors
        raise PdfMalformedError(f"Unexpected error reading PDF: {pdf_path}: {exc}") from exc

    if reader.is_encrypted:
        decrypted = False
        if password is not None:
            try:
                # pypdf returns an int: 0 = failed, 1 or 2 = success.
                decrypted = bool(reader.decrypt(password))
            except Exception as exc:
                raise PdfEncryptedError(f"Failed to decrypt PDF {pdf_path}: {exc}") from exc
        if not decrypted:
            raise PdfEncryptedError(f"PDF is encrypted and could not be decrypted: {pdf_path}")

    pages: list[str] = []
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            # Page-level errors should not abort the whole document.
            logger.warning("Failed to extract text from page %d of %s: %s", index, pdf_path, exc)
            text = ""
        pages.append(text)

    if not pages:
        # A valid PDF with zero pages is technically possible; we treat it
        # as malformed because the caller cannot do anything useful with it.
        raise PdfMalformedError(f"PDF has no pages: {pdf_path}")

    metadata = _extract_metadata(reader)

    return Document(source=pdf_path, pages=tuple(pages), metadata=metadata)


def _extract_metadata(reader: PdfReader) -> dict[str, str]:
    """Pull a subset of standard PDF metadata into plain strings."""
    if reader.metadata is None:
        return {}

    raw = reader.metadata
    result: dict[str, str] = {}
    # pypdf returns Optional[str | TextStringObject]; we coerce defensively.
    for key, attr in (("title", "title"), ("author", "author"), ("subject", "subject")):
        value = getattr(raw, attr, None)
        if value:
            result[key] = str(value)
    return result
