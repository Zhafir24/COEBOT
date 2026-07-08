"""Tests for the ChromaDB vector store wrapper.

Uses a per-test ``tmp_path`` so each test gets a fresh, isolated DB.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_analyzer.models import Chunk
from doc_analyzer.retrieval.store import VectorStore


def _make_chunks(n: int, source: Path = Path("doc.pdf")) -> list[Chunk]:
    return [
        Chunk(text=f"chunk {i} content", source=source, page_index=i // 2, chunk_index=i)
        for i in range(n)
    ]


def _make_embeddings(n: int, dim: int = 4) -> list[list[float]]:
    # Make each embedding distinct in a predictable way.
    return [[float(i) + j * 0.01 for j in range(dim)] for i in range(n)]


class TestVectorStoreLifecycle:
    def test_empty_count_is_zero(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        assert store.count == 0

    def test_add_increases_count(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        store.add(_make_chunks(3), _make_embeddings(3))
        assert store.count == 3

    def test_persistence_across_instances(self, tmp_path: Path) -> None:
        store1 = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        store1.add(_make_chunks(2), _make_embeddings(2))
        store2 = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        assert store2.count == 2

    def test_clear_empties_collection(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        store.add(_make_chunks(3), _make_embeddings(3))
        store.clear()
        assert store.count == 0


class TestVectorStoreAdd:
    def test_mismatched_lengths_raise(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        with pytest.raises(ValueError, match="length mismatch"):
            store.add(_make_chunks(3), _make_embeddings(2))

    def test_empty_batch_is_noop(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        store.add([], [])
        assert store.count == 0


class TestVectorStoreQuery:
    def test_query_empty_store_returns_empty_list(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        results = store.query([1.0, 1.0, 1.0, 1.0], top_k=4)
        assert results == []

    def test_query_returns_at_most_top_k(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        store.add(_make_chunks(5), _make_embeddings(5))
        results = store.query([0.0, 0.0, 0.0, 0.0], top_k=3)
        assert len(results) == 3

    def test_query_with_more_top_k_than_stored_capped(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        store.add(_make_chunks(2), _make_embeddings(2))
        results = store.query([0.0, 0.0, 0.0, 0.0], top_k=10)
        assert len(results) == 2

    def test_query_results_have_metadata_round_trip(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        chunks = _make_chunks(3, source=Path("specific.pdf"))
        store.add(chunks, _make_embeddings(3))
        results = store.query([0.0, 0.0, 0.0, 0.0], top_k=3)
        assert all(r.source == Path("specific.pdf") for r in results)
        assert all(0.0 <= r.score <= 1.0 for r in results)

    def test_query_zero_top_k_raises(self, tmp_path: Path) -> None:
        store = VectorStore(persist_dir=tmp_path / "db", collection_name="test_collection")
        store.add(_make_chunks(1), _make_embeddings(1))
        with pytest.raises(ValueError, match="top_k must be positive"):
            store.query([0.0, 0.0, 0.0, 0.0], top_k=0)
