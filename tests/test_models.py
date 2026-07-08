"""Tests for the shared data models."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from doc_analyzer.models import Chunk, Document


class TestDocument:
    def test_construction_with_minimal_fields(self) -> None:
        doc = Document(source=Path("foo.pdf"), pages=("hello",))
        assert doc.source == Path("foo.pdf")
        assert doc.pages == ("hello",)
        assert doc.metadata == {}

    def test_page_count_matches_pages_tuple(self) -> None:
        doc = Document(source=Path("foo.pdf"), pages=("a", "b", "c"))
        assert doc.page_count == 3

    def test_full_text_joins_with_double_newline(self) -> None:
        doc = Document(source=Path("foo.pdf"), pages=("first", "second"))
        assert doc.full_text == "first\n\nsecond"

    def test_full_text_preserves_empty_pages(self) -> None:
        doc = Document(source=Path("foo.pdf"), pages=("first", "", "third"))
        assert doc.full_text == "first\n\n\n\nthird"

    def test_zero_pages_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least one page"):
            Document(source=Path("foo.pdf"), pages=())

    def test_is_frozen(self) -> None:
        doc = Document(source=Path("foo.pdf"), pages=("hello",))
        with pytest.raises(ValidationError):
            doc.pages = ("changed",)  # type: ignore[misc]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs"):
            Document(source=Path("foo.pdf"), pages=("hi",), bogus="value")  # type: ignore[call-arg]


class TestChunk:
    def test_valid_chunk(self) -> None:
        chunk = Chunk(
            text="some content",
            source=Path("foo.pdf"),
            page_index=0,
            chunk_index=0,
        )
        assert chunk.text == "some content"
        assert chunk.page_index == 0

    def test_empty_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Chunk(text="", source=Path("foo.pdf"), page_index=0, chunk_index=0)

    def test_negative_page_index_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Chunk(text="x", source=Path("foo.pdf"), page_index=-1, chunk_index=0)

    def test_negative_chunk_index_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Chunk(text="x", source=Path("foo.pdf"), page_index=0, chunk_index=-1)
