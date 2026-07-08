"""Tests for the text chunker."""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_analyzer.chunking.text import chunk_document
from doc_analyzer.models import Document


class TestChunkDocument:
    def test_short_document_returns_single_chunk(self) -> None:
        doc = Document(source=Path("a.pdf"), pages=("Just a tiny page.",))
        chunks = chunk_document(doc, chunk_size=100, chunk_overlap=10)
        assert len(chunks) == 1
        assert chunks[0].text == "Just a tiny page."
        assert chunks[0].page_index == 0
        assert chunks[0].chunk_index == 0

    def test_long_document_splits_into_multiple(self) -> None:
        page = ("This is a sentence. " * 50).strip()  # ~1000 chars
        doc = Document(source=Path("a.pdf"), pages=(page,))
        chunks = chunk_document(doc, chunk_size=200, chunk_overlap=20)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.text) <= 200 + 20  # allow overlap headroom

    def test_chunks_have_sequential_indices_across_pages(self) -> None:
        long = "Sentence. " * 60
        doc = Document(source=Path("a.pdf"), pages=(long, long))
        chunks = chunk_document(doc, chunk_size=150, chunk_overlap=10)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_page_indices_attributed_correctly(self) -> None:
        doc = Document(source=Path("a.pdf"), pages=("page zero text", "page one text"))
        chunks = chunk_document(doc, chunk_size=100, chunk_overlap=0)
        pages = {c.page_index for c in chunks}
        assert pages == {0, 1}

    def test_empty_pages_produce_no_chunks(self) -> None:
        doc = Document(source=Path("a.pdf"), pages=("content", "   ", "more content"))
        chunks = chunk_document(doc, chunk_size=100, chunk_overlap=0)
        pages = {c.page_index for c in chunks}
        assert 1 not in pages

    def test_overlap_zero_produces_no_overlap(self) -> None:
        text = "ABCDEFGHIJ" * 20  # 200 chars, no whitespace
        doc = Document(source=Path("a.pdf"), pages=(text,))
        chunks = chunk_document(doc, chunk_size=50, chunk_overlap=0)
        # When concatenated, the chunks should reconstruct the source (allowing trailing whitespace).
        reconstructed = "".join(c.text for c in chunks)
        assert reconstructed.replace(" ", "") == text.replace(" ", "")

    def test_invalid_chunk_size_raises(self) -> None:
        doc = Document(source=Path("a.pdf"), pages=("hi",))
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_document(doc, chunk_size=0, chunk_overlap=0)

    def test_negative_overlap_raises(self) -> None:
        doc = Document(source=Path("a.pdf"), pages=("hi",))
        with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
            chunk_document(doc, chunk_size=100, chunk_overlap=-1)

    def test_overlap_not_smaller_than_size_raises(self) -> None:
        doc = Document(source=Path("a.pdf"), pages=("hi",))
        with pytest.raises(ValueError, match="must be smaller than chunk_size"):
            chunk_document(doc, chunk_size=100, chunk_overlap=100)

    def test_chunk_source_matches_document(self) -> None:
        doc = Document(source=Path("specific.pdf"), pages=("content",))
        chunks = chunk_document(doc, chunk_size=100, chunk_overlap=0)
        assert all(c.source == Path("specific.pdf") for c in chunks)
