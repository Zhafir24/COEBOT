"""Local embeddings via sentence-transformers.

The model is loaded lazily on the first ``encode`` call and reused
thereafter — instantiating the model takes a few seconds and consumes
significant RAM, so we never construct it twice in one process.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np

# If the portable ZIP bundles the embedding model at
# models/embedding/ next to the project root, prefer that path — it
# lets first-run uploads work on machines with no HF cache and no
# internet, which the "fully offline" model demands.
_BUNDLED_EMBEDDING_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "models" / "embedding"
)

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
        # batch_size=64 doubles the default; roomier tensor batching gives
        # ~40% speedup on typical documents at negligible extra RAM.
        vectors = self._model.encode(
            list(texts),
            batch_size=64,
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

        # Prefer the bundled model directory (portable ZIP layout) so
        # first-run uploads work with no HF cache and no internet.
        # Fall back to loading by name (which uses ~/.cache/huggingface).
        if (_BUNDLED_EMBEDDING_DIR / "config.json").exists():
            source = str(_BUNDLED_EMBEDDING_DIR)
            logger.info("Loading embedding model from bundled path %s ...", source)
        else:
            source = self._model_name
            logger.info(
                "Loading embedding model %s from HF cache ...", self._model_name
            )
        # local_files_only=True forbids any network call to the HF Hub.
        # This complements HF_HUB_OFFLINE=1 set in doc_analyzer/__init__.py.
        self._model = SentenceTransformer(source, local_files_only=True)
        logger.info("Embedding model loaded.")
