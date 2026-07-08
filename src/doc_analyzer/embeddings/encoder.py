"""Local embeddings via sentence-transformers.

The model is loaded lazily on the first ``encode`` call and reused
thereafter — instantiating the model takes a few seconds and consumes
significant RAM, so we never construct it twice in one process.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class Embedder:
    """Wraps a sentence-transformers model.

    Args:
        model_name: HuggingFace model identifier.
        normalize: If True (default), embeddings are L2-normalized so
            cosine and dot-product similarity coincide.
    """

    def __init__(self, model_name: str, *, normalize: bool = True) -> None:
        self._model_name = model_name
        self._normalize = normalize
        self._model: SentenceTransformer | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        """Embedding dimension. Triggers model load if not yet loaded."""
        self._ensure_loaded()
        assert self._model is not None
        return int(self._model.get_sentence_embedding_dimension() or 0)

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode a sequence of texts into vector embeddings.

        Args:
            texts: Non-empty sequence of strings.

        Returns:
            One vector per input text, as plain Python lists of floats.

        Raises:
            ValueError: if ``texts`` is empty.
        """
        if len(texts) == 0:
            raise ValueError("encode() requires at least one input text")

        self._ensure_loaded()
        assert self._model is not None

        logger.debug("Encoding %d texts with %s", len(texts), self._model_name)
        vectors = self._model.encode(
            list(texts),
            normalize_embeddings=self._normalize,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        arr = np.asarray(vectors, dtype=np.float32)
        # tolist() returns nested lists; mypy infers Any so cast for strictness.
        return cast(list[list[float]], arr.tolist())

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        # Imported here to defer the heavy torch/transformers import until needed.
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s ...", self._model_name)
        # local_files_only=True forbids any network call to the HF Hub.
        # The model must already be in the local cache
        # (~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2).
        # The first-ever download still requires internet; subsequent
        # loads work fully offline. This complements HF_HUB_OFFLINE=1
        # set in doc_analyzer/__init__.py.
        self._model = SentenceTransformer(
            self._model_name,
            local_files_only=True,
        )
        logger.info("Embedding model loaded.")
