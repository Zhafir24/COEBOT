"""In-process LLM chat client backed by llama-cpp-python.

The model is loaded ONCE at client construction (typically once per
Streamlit process via a cached factory) and reused for every chat
turn. There is no external LLM service — inference happens inside the
same Python process that runs the Streamlit UI.

Design notes:
- No streaming — keeps the call surface deterministic and the
  Streamlit integration straightforward.
- No retries — in-process calls don't fail with transient network
  errors the way an HTTP client would. If the model errors, the
  exception is surfaced immediately.
- `<think>...</think>` blocks are stripped from responses when
  configured (default) so thinking-capable models don't leak
  internal reasoning into user-visible answers.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:  # pragma: no cover
    from llama_cpp import Llama

logger = logging.getLogger(__name__)

_THINK_TAG_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)

# Default output budget per response. Generation stops naturally at the
# model's end-of-answer token, so a high ceiling does NOT slow short
# answers — it only lets long, structured answers (tables, multi-part
# explanations) finish instead of truncating mid-sentence.
_DEFAULT_MAX_TOKENS = 3072

_TRUNCATION_NOTE = (
    "\n\n⚠️ *(Output reached the length limit — say \"continue\" to get the rest.)*"
)


class ChatMessage(TypedDict):
    role: str
    content: str


class LlmClientError(Exception):
    """The underlying llama_cpp call raised an error."""


class PrefixKVCache:
    """Persistent longest-prefix KV cache for llama.cpp (disk-backed).

    Replaces llama-cpp-python's bundled ``LlamaDiskCache``, whose
    ``__getitem__`` pops the entry from disk on every read (the re-insert
    is commented out upstream as broken), so its cache can never
    accumulate — each lookup destroys the very state it found.

    Differences from the bundled implementation:

    - Reads never delete. A cached document state survives being used.
    - A hit requires a meaningful shared prefix (``min_prefix_tokens``),
      so a few incidentally-shared system-prompt tokens can't trigger a
      multi-GB state load that saves nothing.
    - When the live context already covers the prompt at least as well
      as the disk entry would (``live_tokens_fn``), the lookup reports a
      miss instead of unpickling a state llama.cpp would then discard.
    - Writes are skipped for small states (``store_min_tokens``) and for
      prompts whose prefix an existing entry already covers, so chat
      turns don't churn gigabytes of disk after every answer.
    - Oldest entries are evicted once ``capacity_bytes`` is exceeded.
    """

    def __init__(
        self,
        cache_dir: str,
        *,
        capacity_bytes: int = 8 * 1024**3,
        min_prefix_tokens: int = 512,
        store_min_tokens: int = 1024,
        covered_fraction: float = 0.8,
        live_tokens_fn: Callable[[], list[int]] | None = None,
    ) -> None:
        import diskcache

        # diskcache silently defaults size_limit to 1 GB and auto-culls
        # anything beyond it — a deep-read document state (~1.7 GB at
        # 24K context) would be written and then immediately destroyed.
        # The library's limit must match ours or it wins.
        self._cache = diskcache.Cache(cache_dir, size_limit=capacity_bytes)
        self._capacity_bytes = capacity_bytes
        self._min_prefix_tokens = min_prefix_tokens
        self._store_min_tokens = store_min_tokens
        self._covered_fraction = covered_fraction
        self._live_tokens_fn = live_tokens_fn

    @staticmethod
    def _shared_prefix_len(a: Sequence[int], b: Sequence[int]) -> int:
        n = 0
        for x, y in zip(a, b):
            if x != y:
                break
            n += 1
        return n

    def _best_prefix(self, key: tuple[int, ...]) -> tuple[tuple[int, ...] | None, int]:
        """Return the stored key sharing the longest prefix with ``key``."""
        best_key: tuple[int, ...] | None = None
        best_len = 0
        for stored in self._cache.iterkeys():
            length = self._shared_prefix_len(stored, key)
            if length > best_len:
                best_len = length
                best_key = stored
        return best_key, best_len

    def __getitem__(self, key: Sequence[int]) -> Any:
        key = tuple(key)
        best_key, best_len = self._best_prefix(key)
        if best_key is None or best_len < self._min_prefix_tokens:
            raise KeyError("no cached prefix long enough to be useful")
        if self._live_tokens_fn is not None:
            try:
                live_len = self._shared_prefix_len(self._live_tokens_fn(), key)
            except Exception:  # noqa: BLE001 — advisory check only
                live_len = 0
            if live_len >= best_len:
                raise KeyError("live context already covers the cached prefix")
        value = self._cache.get(best_key, default=None)
        if value is None:
            raise KeyError("cache entry vanished")
        logger.info("KV cache hit: reusing %d prompt tokens from disk", best_len)
        return value

    def __contains__(self, key: Sequence[int]) -> bool:
        _, best_len = self._best_prefix(tuple(key))
        return best_len >= self._min_prefix_tokens

    def __setitem__(self, key: Sequence[int], value: Any) -> None:
        key = tuple(key)
        if len(key) < self._store_min_tokens:
            return  # chat-sized states aren't worth the disk churn
        best_key, best_len = self._best_prefix(key)
        if best_key is not None and best_len >= int(len(key) * self._covered_fraction):
            return  # an existing entry already covers this prefix
        self._cache[key] = value
        logger.info("KV cache stored: %d-token state saved to disk", len(key))
        while self._cache.volume() > self._capacity_bytes and len(self._cache) > 0:
            oldest = next(iter(self._cache))
            del self._cache[oldest]


class LlmClient:
    """Loads and holds a llama-cpp `Llama` instance in-process.

    Args:
        model_path: Absolute path to a `.gguf` file on disk. The file
            must exist at construction time — a clear ``FileNotFoundError``
            is raised otherwise.
        n_ctx: Context window size in tokens (must not exceed the
            model's trained maximum; too large a value causes
            llama_cpp to error at load time).
        n_threads: CPU thread count. ``None`` or 0 lets llama_cpp
            pick a default based on the machine's core count.
        strip_think_tags: If True, ``<think>...</think>`` blocks are
            removed from responses before returning to callers.
    """

    def __init__(
        self,
        *,
        model_path: Path,
        n_ctx: int = 8192,
        n_threads: int | None = None,
        strip_think_tags: bool = True,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        kv_cache_dir: Path | None = None,
        kv_cache_bytes: int = 8 * 1024**3,
    ) -> None:
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model file not found at {model_path}. "
                "Place a .gguf file in the models/ directory."
            )
        # Imported here to defer the heavy llama_cpp import until the
        # client is actually constructed (rather than at module import).
        from llama_cpp import Llama

        logger.info("Loading GGUF model from %s ...", model_path)
        self._llm: Llama = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=n_threads if n_threads else None,
            verbose=False,
        )
        self._model_path = model_path
        self._strip_think_tags = strip_think_tags
        self._max_tokens = max_tokens
        logger.info("Model loaded: %s (n_ctx=%d)", model_path.name, n_ctx)

        # Optional persistent KV cache: llama.cpp saves the processed
        # prompt state to disk keyed by token prefix, so re-asking about
        # the same documents (even after a restart) skips most of the
        # expensive prefill ("reading") phase. Best-effort — any failure
        # degrades to normal uncached behavior.
        if kv_cache_dir is not None:
            try:
                kv_cache_dir.mkdir(parents=True, exist_ok=True)
                self._llm.set_cache(
                    PrefixKVCache(
                        str(kv_cache_dir),
                        capacity_bytes=kv_cache_bytes,
                        live_tokens_fn=lambda: self._llm._input_ids.tolist(),
                    )
                )
                logger.info(
                    "KV disk cache enabled at %s (cap %.1f GB)",
                    kv_cache_dir,
                    kv_cache_bytes / 1024**3,
                )
            except Exception:  # noqa: BLE001 — cache is an optimization only
                logger.warning(
                    "KV disk cache unavailable — continuing without it",
                    exc_info=True,
                )

    @property
    def model(self) -> str:
        """The filename of the loaded model (for display in the UI)."""
        return self._model_path.name

    def count_tokens(self, text: str) -> int:
        """Count tokens for ``text`` using the loaded model's tokenizer.

        Used to decide whether full documents fit the context budget.
        """
        return len(self._llm.tokenize(text.encode("utf-8"), add_bos=False, special=False))

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        num_predict: int | None = None,
        max_attempts: int = 3,  # accepted for API compatibility; unused in-process
    ) -> str:
        """Send a chat turn and return the cleaned text response.

        Args:
            messages: Conversation history. Must be non-empty.
            temperature: Sampling temperature, 0 = deterministic.
            num_predict: Maximum tokens to generate. ``None`` uses the
                client-wide ``max_tokens`` set at construction.
            max_attempts: Retained for API compatibility with the previous
                HTTP-based client. In-process inference has no transient
                failure mode, so retries are not exercised. Non-fatal
                errors from the model are surfaced immediately.

        Returns:
            The model's text response with any leftover ``<think>``
            blocks stripped if configured. If generation was cut off by
            the length limit, a visible truncation note is appended so
            the user knows the answer is incomplete.

        Raises:
            LlmClientError: if llama_cpp raises during generation.
            ValueError: if ``messages`` is empty.
        """
        del max_attempts  # kept for signature compat; see docstring
        if not messages:
            raise ValueError("chat() requires at least one message")

        try:
            response = self._llm.create_chat_completion(
                messages=list(messages),
                temperature=temperature,
                max_tokens=num_predict if num_predict is not None else self._max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 — wrap and re-raise
            logger.exception("llama_cpp chat completion failed")
            raise LlmClientError(f"llama_cpp inference failed: {exc}") from exc

        # llama_cpp mirrors OpenAI's response schema:
        # {"choices": [{"message": {"role": "assistant", "content": "..."}}], ...}
        try:
            choice = response["choices"][0]
            content = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmClientError(
                f"Unexpected response shape from llama_cpp: {response!r}"
            ) from exc

        if self._strip_think_tags:
            content = _THINK_TAG_PATTERN.sub("", content)
        content = content.strip()

        # Make truncation visible instead of silently stopping mid-sentence.
        if choice.get("finish_reason") == "length":
            content += _TRUNCATION_NOTE
        return content
