"""Tests for the in-process LLM client backed by llama-cpp-python.

`llama_cpp.Llama` is mocked — these tests never load a real model file
(the pipeline would need a multi-gigabyte GGUF for a real load).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from doc_analyzer.llm.client import (
    ChatMessage,
    LlmClient,
    LlmClientError,
    PrefixKVCache,
)


def _fake_response(content: str) -> dict[str, Any]:
    """Match llama_cpp's OpenAI-compatible response dict shape."""
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def _build_client(tmp_path: Path, **overrides: Any) -> tuple[LlmClient, MagicMock]:
    """Build an LlmClient with a mocked Llama instance.

    A dummy `.gguf` file is created at ``tmp_path`` so the client's
    existence check passes — no real weights are loaded, since the
    llama_cpp constructor is mocked out.
    """
    dummy_gguf = tmp_path / "fake-model.gguf"
    dummy_gguf.write_bytes(b"")
    with patch("llama_cpp.Llama") as llama_cls:
        instance = MagicMock()
        llama_cls.return_value = instance
        kwargs: dict[str, Any] = {
            "model_path": dummy_gguf,
            "n_ctx": 4096,
            "n_threads": 0,
            "strip_think_tags": True,
        }
        kwargs.update(overrides)
        client = LlmClient(**kwargs)
    return client, instance


_MSG: list[ChatMessage] = [{"role": "user", "content": "hi"}]


class TestConstruction:
    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.gguf"
        with pytest.raises(FileNotFoundError, match="Model file not found"):
            LlmClient(model_path=missing)

    def test_model_property_returns_filename(self, tmp_path: Path) -> None:
        client, _ = _build_client(tmp_path)
        assert client.model == "fake-model.gguf"


class TestChatBasics:
    def test_returns_content(self, tmp_path: Path) -> None:
        client, inner = _build_client(tmp_path)
        inner.create_chat_completion.return_value = _fake_response("hello world")
        assert client.chat(_MSG) == "hello world"

    def test_strips_leading_and_trailing_whitespace(self, tmp_path: Path) -> None:
        client, inner = _build_client(tmp_path)
        inner.create_chat_completion.return_value = _fake_response("  hi  \n")
        assert client.chat(_MSG) == "hi"

    def test_empty_messages_raises_without_calling_llama(self, tmp_path: Path) -> None:
        client, inner = _build_client(tmp_path)
        with pytest.raises(ValueError, match="at least one message"):
            client.chat([])
        inner.create_chat_completion.assert_not_called()

    def test_temperature_and_max_tokens_propagated(self, tmp_path: Path) -> None:
        client, inner = _build_client(tmp_path)
        inner.create_chat_completion.return_value = _fake_response("ok")
        client.chat(_MSG, temperature=0.7, num_predict=123)
        kwargs = inner.create_chat_completion.call_args.kwargs
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 123


class TestThinkTagStripping:
    def test_strips_think_block_when_enabled(self, tmp_path: Path) -> None:
        client, inner = _build_client(tmp_path, strip_think_tags=True)
        inner.create_chat_completion.return_value = _fake_response(
            "<think>internal reasoning</think>The answer is 42."
        )
        assert client.chat(_MSG) == "The answer is 42."

    def test_strips_multiline_think_block(self, tmp_path: Path) -> None:
        client, inner = _build_client(tmp_path, strip_think_tags=True)
        inner.create_chat_completion.return_value = _fake_response(
            "<think>\nline one\nline two\n</think>\nFinal answer."
        )
        assert client.chat(_MSG) == "Final answer."

    def test_strips_multiple_think_blocks(self, tmp_path: Path) -> None:
        client, inner = _build_client(tmp_path, strip_think_tags=True)
        inner.create_chat_completion.return_value = _fake_response(
            "<think>A</think>part1<think>B</think>part2"
        )
        assert client.chat(_MSG) == "part1part2"

    def test_does_not_strip_when_disabled(self, tmp_path: Path) -> None:
        client, inner = _build_client(tmp_path, strip_think_tags=False)
        inner.create_chat_completion.return_value = _fake_response("<think>x</think>y")
        assert client.chat(_MSG) == "<think>x</think>y"


class TestErrorSurfacing:
    def test_llama_cpp_exception_wraps_into_llm_client_error(self, tmp_path: Path) -> None:
        client, inner = _build_client(tmp_path)
        inner.create_chat_completion.side_effect = RuntimeError("out of memory")
        with pytest.raises(LlmClientError, match="llama_cpp inference failed"):
            client.chat(_MSG)

    def test_malformed_response_raises_llm_client_error(self, tmp_path: Path) -> None:
        client, inner = _build_client(tmp_path)
        inner.create_chat_completion.return_value = {"unexpected": "shape"}
        with pytest.raises(LlmClientError, match="Unexpected response shape"):
            client.chat(_MSG)


def _make_cache(tmp_path: Path, **overrides: Any) -> PrefixKVCache:
    kwargs: dict[str, Any] = {
        # Tiny thresholds so tests can use short token sequences.
        "min_prefix_tokens": 4,
        "store_min_tokens": 4,
        "covered_fraction": 0.8,
    }
    kwargs.update(overrides)
    return PrefixKVCache(str(tmp_path / "kv"), **kwargs)


class TestPrefixKVCache:
    """The whole point of this class is fixing LlamaDiskCache's defect:
    its __getitem__ pops entries from disk, so every hit destroys the
    cached state. These tests pin the corrected semantics."""

    def test_hit_does_not_delete_entry(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        key = list(range(10))
        cache[key] = "state"
        assert cache[key] == "state"
        # The read above must NOT have consumed the entry.
        assert cache[key] == "state"

    def test_longest_prefix_match_wins(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        cache[[1, 2, 3, 4, 9, 9]] = "short-match"
        cache[[1, 2, 3, 4, 5, 6, 7]] = "long-match"
        # Query shares 6 tokens with long-match, 4 with short-match.
        assert cache[[1, 2, 3, 4, 5, 6, 99]] == "long-match"

    def test_miss_when_prefix_too_short(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path, min_prefix_tokens=5)
        cache[[1, 2, 3, 4, 5, 6]] = "state"
        # Only 3 shared tokens — a trivial overlap (e.g. both prompts
        # starting "You are") must not trigger a state load.
        with pytest.raises(KeyError):
            cache[[1, 2, 3, 99, 98, 97]]

    def test_miss_when_live_context_already_covers(self, tmp_path: Path) -> None:
        live = [1, 2, 3, 4, 5, 6]
        cache = _make_cache(tmp_path, live_tokens_fn=lambda: live)
        cache[[1, 2, 3, 4, 5, 6]] = "state"
        # The in-RAM context matches the prompt as well as the disk
        # entry would — loading from disk is pure waste.
        with pytest.raises(KeyError):
            cache[[1, 2, 3, 4, 5, 6, 7]]

    def test_hit_when_disk_beats_live_context(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path, live_tokens_fn=lambda: [9, 9, 9])
        cache[[1, 2, 3, 4, 5, 6]] = "state"
        assert cache[[1, 2, 3, 4, 5, 6, 7]] == "state"

    def test_small_states_are_not_stored(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path, store_min_tokens=100)
        cache[list(range(10))] = "chat-turn"
        with pytest.raises(KeyError):
            cache[list(range(10))]

    def test_covered_prefix_is_not_stored_again(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        base = list(range(100))
        cache[[*base, 201, 202]] = "first-question"
        # Second question about the same document: 100 of 103 tokens
        # (~97%) already covered — must be a no-op, not a second
        # multi-GB write.
        cache[[*base, 301, 302, 303]] = "second-question"
        assert cache[[*base, 999]] == "first-question"

    def test_uncovered_prefix_is_stored(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        cache[[1, 2, 3, 4, 5]] = "doc-a"
        cache[[7, 8, 9, 10, 11]] = "doc-b"
        assert cache[[7, 8, 9, 10, 11, 12]] == "doc-b"

    def test_contains_respects_min_prefix(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path, min_prefix_tokens=5)
        cache[[1, 2, 3, 4, 5, 6]] = "state"
        assert [1, 2, 3, 4, 5, 99] in cache
        assert [1, 2, 99, 98, 97, 96] not in cache

    def test_eviction_above_capacity(self, tmp_path: Path) -> None:
        # ~1 MB values against a 2 MB cap: inserting a third entry must
        # evict the oldest rather than grow without bound.
        cache = _make_cache(tmp_path, capacity_bytes=2 * 1024 * 1024)
        big = "x" * (1024 * 1024)
        cache[[1, 2, 3, 4, 5]] = big
        cache[[6, 7, 8, 9, 10]] = big
        cache[[11, 12, 13, 14, 15]] = big
        stored = sum(
            1 for key in ([1, 2, 3, 4, 5], [6, 7, 8, 9, 10], [11, 12, 13, 14, 15]) if key in cache
        )
        assert stored < 3
        assert [11, 12, 13, 14, 15] in cache  # newest survives
