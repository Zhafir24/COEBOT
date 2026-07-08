"""Tests for the RAG pipeline orchestrator.

All heavy dependencies (embedder, store, llm) are mocked so the
orchestrator's logic is tested in isolation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from doc_analyzer.config import Settings
from doc_analyzer.pipeline import (
    Answer,
    answer_full_documents,
    answer_question,
    ingest_pdf,
)
from doc_analyzer.retrieval.store import RetrievedChunk


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for var in ["CHUNK_SIZE", "CHUNK_OVERLAP", "RETRIEVAL_TOP_K"]:
        monkeypatch.delenv(var, raising=False)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def _make_retrieved(text: str = "context", source: str = "doc.pdf") -> RetrievedChunk:
    return RetrievedChunk(
        text=text,
        source=Path(source),
        page_index=0,
        chunk_index=0,
        score=0.9,
    )


class TestIngestPdf:
    def test_calls_parser_chunker_embedder_store_in_order(
        self, sample_pdf: Path, settings: Settings
    ) -> None:
        embedder = MagicMock()
        embedder.encode.return_value = [[0.1, 0.2, 0.3, 0.4]] * 5
        store = MagicMock()

        result = ingest_pdf(sample_pdf, embedder=embedder, store=store, settings=settings)

        assert result.source == sample_pdf
        assert result.page_count == 2
        assert result.chunk_count > 0
        embedder.encode.assert_called_once()
        store.add.assert_called_once()

    def test_returns_chunk_count_from_chunker(self, sample_pdf: Path, settings: Settings) -> None:
        embedder = MagicMock()
        embedder.encode.side_effect = lambda texts: [[0.0] * 4 for _ in texts]
        store = MagicMock()

        result = ingest_pdf(sample_pdf, embedder=embedder, store=store, settings=settings)
        # embedder is called with one vector per chunk
        assert embedder.encode.call_args.args[0]
        assert result.chunk_count == len(embedder.encode.call_args.args[0])


class TestAnswerQuestion:
    def test_empty_question_returns_prompt_for_question(self, settings: Settings) -> None:
        embedder = MagicMock()
        store = MagicMock()
        llm = MagicMock()

        result = answer_question("", embedder=embedder, store=store, llm=llm, settings=settings)
        assert isinstance(result, Answer)
        assert "Please enter" in result.text
        llm.chat.assert_not_called()

    def test_empty_store_returns_no_documents_message(self, settings: Settings) -> None:
        embedder = MagicMock()
        store = MagicMock()
        store.count = 0
        llm = MagicMock()

        result = answer_question(
            "what is X?", embedder=embedder, store=store, llm=llm, settings=settings
        )
        assert "No documents" in result.text
        llm.chat.assert_not_called()

    def test_no_retrieval_hits_short_circuits(self, settings: Settings) -> None:
        embedder = MagicMock()
        embedder.encode.return_value = [[0.0, 0.0, 0.0, 0.0]]
        store = MagicMock()
        store.count = 5
        store.query.return_value = []
        llm = MagicMock()

        result = answer_question(
            "what is X?", embedder=embedder, store=store, llm=llm, settings=settings
        )
        assert "do not contain enough information" in result.text
        llm.chat.assert_not_called()

    def test_hits_lead_to_llm_call(self, settings: Settings) -> None:
        embedder = MagicMock()
        embedder.encode.return_value = [[0.0] * 4]
        store = MagicMock()
        store.count = 5
        store.query.return_value = [_make_retrieved("X is documented here")]
        llm = MagicMock()
        llm.chat.return_value = "X is documented here. [p.1]"

        result = answer_question(
            "what is X?", embedder=embedder, store=store, llm=llm, settings=settings
        )
        assert result.text == "X is documented here. [p.1]"
        assert len(result.sources) == 1
        assert result.sources[0].text == "X is documented here"

    def test_llm_prompt_includes_question_and_context(self, settings: Settings) -> None:
        embedder = MagicMock()
        embedder.encode.return_value = [[0.0] * 4]
        store = MagicMock()
        store.count = 1
        store.query.return_value = [_make_retrieved(text="UNIQUE_CONTEXT_SENTINEL")]
        llm = MagicMock()
        llm.chat.return_value = "ok"

        answer_question(
            "what is X?",
            embedder=embedder,
            store=store,
            llm=llm,
            settings=settings,
        )

        messages = llm.chat.call_args.args[0]
        assert any(m["role"] == "system" for m in messages)
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "what is X?" in user_msg["content"]
        assert "UNIQUE_CONTEXT_SENTINEL" in user_msg["content"]

    def test_page_numbers_in_prompt_are_one_indexed(self, settings: Settings) -> None:
        embedder = MagicMock()
        embedder.encode.return_value = [[0.0] * 4]
        store = MagicMock()
        store.count = 1
        hit = RetrievedChunk(
            text="ctx", source=Path("doc.pdf"), page_index=4, chunk_index=0, score=0.9
        )
        store.query.return_value = [hit]
        llm = MagicMock()
        llm.chat.return_value = "ok"

        answer_question("Q?", embedder=embedder, store=store, llm=llm, settings=settings)

        user_msg = next(m for m in llm.chat.call_args.args[0] if m["role"] == "user")
        # internal page_index=4 → "p.5" in prompt
        assert "p.5" in user_msg["content"]


class TestMemoryPlacement:
    """Memory facts must sit LATE in the user prompt, never in the
    system prompt: the KV cache reuses prompts by token prefix, and
    memory grows with use — facts at the front would invalidate every
    cached document prefix each time a new fact is learned."""

    _FACT = "USER_FACT_SENTINEL"

    def test_rag_memory_in_user_prompt_after_context(self, settings: Settings) -> None:
        embedder = MagicMock()
        embedder.encode.return_value = [[0.0] * 4]
        store = MagicMock()
        store.count = 1
        store.query.return_value = [_make_retrieved(text="CONTEXT_SENTINEL")]
        llm = MagicMock()
        llm.chat.return_value = "ok"

        answer_question(
            "what is X?",
            embedder=embedder,
            store=store,
            llm=llm,
            settings=settings,
            memory_facts=[self._FACT],
        )

        messages = llm.chat.call_args.args[0]
        system_msg = next(m for m in messages if m["role"] == "system")
        user_msg = next(m for m in messages if m["role"] == "user")
        assert self._FACT not in system_msg["content"]
        content = user_msg["content"]
        assert (
            content.index("CONTEXT_SENTINEL")
            < content.index(self._FACT)
            < content.index("what is X?")
        )

    def test_deep_read_memory_after_document_text(
        self, sample_pdf: Path, settings: Settings
    ) -> None:
        llm = MagicMock()
        llm.count_tokens.return_value = 100  # comfortably within budget
        llm.chat.return_value = "ok"

        answer_full_documents(
            "what is X?",
            doc_paths=[sample_pdf],
            llm=llm,
            settings=settings,
            memory_facts=[self._FACT],
        )

        messages = llm.chat.call_args.args[0]
        system_msg = next(m for m in messages if m["role"] == "system")
        user_msg = next(m for m in messages if m["role"] == "user")
        assert self._FACT not in system_msg["content"]
        content = user_msg["content"]
        assert (
            content.index("page one")
            < content.index(self._FACT)
            < content.index("QUESTION:")
        )

    def test_no_memory_block_when_no_facts(self, settings: Settings) -> None:
        embedder = MagicMock()
        embedder.encode.return_value = [[0.0] * 4]
        store = MagicMock()
        store.count = 1
        store.query.return_value = [_make_retrieved()]
        llm = MagicMock()
        llm.chat.return_value = "ok"

        answer_question(
            "Q?", embedder=embedder, store=store, llm=llm, settings=settings
        )

        user_msg = next(m for m in llm.chat.call_args.args[0] if m["role"] == "user")
        assert "KNOWN FACTS" not in user_msg["content"]
