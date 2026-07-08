"""Tests for the Embedder.

We never instantiate the real SentenceTransformer in unit tests — it
takes seconds and downloads model weights. Tests mock the model.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from doc_analyzer.embeddings.encoder import Embedder


def _fake_model(dim: int = 4) -> MagicMock:
    """Build a fake SentenceTransformer that returns deterministic vectors."""
    m = MagicMock()
    m.get_sentence_embedding_dimension.return_value = dim

    def encode(texts: list[str], **_: Any) -> np.ndarray:
        # Make each row distinct so tests can verify ordering.
        return np.array(
            [[float(len(t) + j) for j in range(dim)] for t in texts],
            dtype=np.float32,
        )

    m.encode.side_effect = encode
    return m


class TestEmbedder:
    def test_lazy_load_does_not_construct_until_used(self) -> None:
        with patch("sentence_transformers.SentenceTransformer") as st_cls:
            embedder = Embedder("fake-model")
            st_cls.assert_not_called()  # constructor must be deferred

            st_cls.return_value = _fake_model()
            embedder.encode(["hello"])
            st_cls.assert_called_once_with("fake-model", local_files_only=True)

    def test_subsequent_encodes_reuse_loaded_model(self) -> None:
        with patch("sentence_transformers.SentenceTransformer") as st_cls:
            st_cls.return_value = _fake_model()
            embedder = Embedder("fake-model")
            embedder.encode(["a"])
            embedder.encode(["b"])
            st_cls.assert_called_once()

    def test_encode_returns_one_vector_per_input(self) -> None:
        with patch("sentence_transformers.SentenceTransformer") as st_cls:
            st_cls.return_value = _fake_model(dim=4)
            embedder = Embedder("fake-model")
            vectors = embedder.encode(["one", "two", "three"])
            assert len(vectors) == 3
            assert all(len(v) == 4 for v in vectors)

    def test_encode_returns_plain_python_lists_of_floats(self) -> None:
        with patch("sentence_transformers.SentenceTransformer") as st_cls:
            st_cls.return_value = _fake_model(dim=4)
            embedder = Embedder("fake-model")
            vectors = embedder.encode(["x"])
            assert isinstance(vectors, list)
            assert isinstance(vectors[0], list)
            assert all(isinstance(v, float) for v in vectors[0])

    def test_dimension_triggers_load(self) -> None:
        with patch("sentence_transformers.SentenceTransformer") as st_cls:
            st_cls.return_value = _fake_model(dim=384)
            embedder = Embedder("fake-model")
            assert embedder.dimension == 384

    def test_model_name_property(self) -> None:
        embedder = Embedder("hf/some-model")
        assert embedder.model_name == "hf/some-model"

    def test_encode_empty_input_raises(self) -> None:
        embedder = Embedder("fake-model")
        with pytest.raises(ValueError, match="at least one input text"):
            embedder.encode([])
