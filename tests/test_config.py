"""Tests for the Settings configuration object."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from doc_analyzer.config import Settings


class TestSettings:
    def test_defaults_are_valid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Strip any real env vars so we test pure defaults.
        for var in [
            "MODEL_FILENAME",
            "MODEL_N_CTX",
            "MODEL_N_THREADS",
            "CHUNK_SIZE",
            "CHUNK_OVERLAP",
            "LOG_LEVEL",
        ]:
            monkeypatch.delenv(var, raising=False)
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.model_filename == ""  # empty = auto-detect
        assert s.model_n_ctx == 8192
        assert s.chunk_size == 800
        assert s.chunk_overlap == 120
        assert s.retrieval_top_k == 10

    def test_env_var_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MODEL_FILENAME", "qwen2.5-7b.gguf")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.model_filename == "qwen2.5-7b.gguf"

    def test_chunk_overlap_rejected_when_equal_to_size(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHUNK_SIZE", "500")
        monkeypatch.setenv("CHUNK_OVERLAP", "500")
        with pytest.raises(ValidationError, match="smaller than chunk_size"):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_chunk_overlap_rejected_when_greater_than_size(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHUNK_SIZE", "200")
        monkeypatch.setenv("CHUNK_OVERLAP", "300")
        with pytest.raises(ValidationError, match="smaller than chunk_size"):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_invalid_log_level_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
        with pytest.raises(ValidationError, match="log_level must be one of"):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_log_level_normalized_to_uppercase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "debug")
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.log_level == "DEBUG"

    def test_chunk_size_zero_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHUNK_SIZE", "0")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_retrieval_top_k_above_limit_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RETRIEVAL_TOP_K", "500")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]
