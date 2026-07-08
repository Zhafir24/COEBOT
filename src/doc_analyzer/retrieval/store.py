"""Vector store backed by ChromaDB.

Persistence is on by default: vectors are written to disk under
``settings.chroma_persist_dir`` and survive process restarts. The store
is non-agentic — only ``add`` and ``query`` are exposed; there is no
auto-update, no background sync, no remote retrieval.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.config import Settings as ChromaSettings

from doc_analyzer.models import Chunk

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk returned by a similarity search, with its score."""

    text: str
    source: Path
    page_index: int
    chunk_index: int
    score: float


class VectorStore:
    """Thin wrapper over a persistent ChromaDB collection."""

    def __init__(self, *, persist_dir: Path, collection_name: str) -> None:
        self._persist_dir = persist_dir
        self._collection_name = collection_name
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    def add(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        """Persist a batch of chunks together with their embeddings.

        Raises:
            ValueError: if ``chunks`` and ``embeddings`` have different lengths.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) length mismatch"
            )
        if not chunks:
            return

        ids = [str(uuid.uuid4()) for _ in chunks]
        documents = [c.text for c in chunks]
        # ChromaDB's metadata Mapping type is a broader Union than what we use,
        # but mypy can't narrow it from our concrete dict — cast for strictness.
        metadatas = cast(
            Any,
            [
                {
                    "source": str(c.source),
                    "page_index": c.page_index,
                    "chunk_index": c.chunk_index,
                }
                for c in chunks
            ],
        )
        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=cast(Any, [list(e) for e in embeddings]),
        )
        logger.info("Added %d chunks to collection %s", len(chunks), self._collection_name)

    def query(
        self,
        query_embedding: Sequence[float],
        *,
        top_k: int,
        source_paths: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Return the top-k nearest chunks for ``query_embedding``.

        Args:
            query_embedding: The embedded query vector.
            top_k: Maximum number of chunks to return.
            source_paths: If given, retrieval is scoped to chunks whose
                stored ``source`` metadata exactly matches one of these
                path strings (as produced by ``str(chunk.source)`` at
                ingestion). The filter is applied INSIDE the vector
                search via a Chroma ``where`` clause, so ranking happens
                only among the scoped documents' chunks. Post-filtering
                the global top-k is NOT equivalent: in a store with many
                documents, the scoped document's chunks may not appear
                in the global top-k at all, producing zero results.
                If the exact-path filter matches nothing (e.g. legacy
                rows stored with different path forms), a basename
                post-filter over an over-fetched result is used as a
                fallback.

        Duplicate chunks (same source/page/text) are collapsed — the
        store may contain duplicates from historical re-ingestion.
        """
        if top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")
        if self.count == 0:
            return []

        # Over-fetch to leave headroom for deduplication — the store may
        # hold several copies of each chunk from historical re-ingestion.
        fetch_n = min(max(top_k * 6, top_k), self.count)

        where: Any = None
        if source_paths:
            paths = [str(p) for p in source_paths]
            where = {"source": paths[0]} if len(paths) == 1 else {"source": {"$in": paths}}

        result = self._collection.query(
            query_embeddings=cast(Any, [list(query_embedding)]),
            n_results=fetch_n,
            where=cast(Any, where),
        )
        hits = self._to_chunks(result, top_k=top_k, allowed_basenames=None)
        if hits or source_paths is None:
            return hits

        # Fallback: exact-path filter matched nothing — retry unscoped
        # and post-filter by basename (legacy rows may have stored the
        # source under a different path form).
        allowed = {Path(str(p)).name for p in source_paths}
        result = self._collection.query(
            query_embeddings=cast(Any, [list(query_embedding)]),
            n_results=min(max(top_k * 10, top_k), self.count),
        )
        return self._to_chunks(result, top_k=top_k, allowed_basenames=allowed)

    def _to_chunks(
        self,
        result: Any,
        *,
        top_k: int,
        allowed_basenames: set[str] | None,
    ) -> list[RetrievedChunk]:
        """Convert a raw Chroma result into deduplicated RetrievedChunks."""
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        seen: set[tuple[str, int, str]] = set()
        out: list[RetrievedChunk] = []
        for text, meta, dist in zip(documents, metadatas, distances, strict=True):
            source = Path(str(meta.get("source", "")))
            if allowed_basenames is not None and source.name not in allowed_basenames:
                continue
            page_index = _as_int(meta.get("page_index", 0))
            dedupe_key = (source.name, page_index, text)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            out.append(
                RetrievedChunk(
                    text=text,
                    source=source,
                    page_index=page_index,
                    chunk_index=_as_int(meta.get("chunk_index", 0)),
                    # Convert distance (lower = closer) to a similarity-ish score in [0, 1].
                    score=max(0.0, 1.0 - float(dist)),
                )
            )
            if len(out) >= top_k:
                break
        return out

    def clear(self) -> None:
        """Delete the collection and recreate it empty.

        Useful when the user uploads a new set of documents and wants
        to start fresh.
        """
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Cleared collection %s", self._collection_name)

    def delete_by_source(self, source: Path) -> None:
        """Delete every chunk belonging to a given source file."""
        target = str(source)
        self._collection.delete(where=cast(Any, {"source": target}))
        logger.info("Deleted chunks for source %s", target)


def _as_int(value: object) -> int:
    """Defensively coerce a metadata value to int, returning 0 on failure."""
    if isinstance(value, bool):
        # bool is a subclass of int — guard so True/False don't slip through.
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0
