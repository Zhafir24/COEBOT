"""Application configuration.

All runtime settings are defined here. Values are read from environment
variables (or a `.env` file in the project root). Defaults are tuned for
local development.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Process-wide configuration loaded from environment + .env."""

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Local LLM (in-process, via llama-cpp-python) ---
    models_dir: Path = Field(
        default=_PROJECT_ROOT / "models",
        description="Directory containing GGUF model files.",
    )
    model_filename: str = Field(
        default="",
        description=(
            "Filename of the GGUF model to load (must live in `models_dir`). "
            "If empty, COEBOT auto-detects the first .gguf file found in "
            "`models_dir` alphabetically."
        ),
    )
    model_n_ctx: int = Field(
        default=8192,
        gt=0,
        le=131072,
        description="Context window size in tokens. Must fit within the model's trained max.",
    )
    model_n_threads: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of CPU threads for inference. 0 = auto-detect (llama.cpp "
            "picks a sensible default based on core count)."
        ),
    )
    model_max_tokens: int = Field(
        default=3072,
        gt=0,
        le=8192,
        description=(
            "Maximum tokens the model may generate per response. Generation "
            "stops at the model's natural end-of-answer token, so this is a "
            "ceiling for long answers, not a target."
        ),
    )
    kv_cache_enabled: bool = Field(
        default=True,
        description=(
            "Persist processed-prompt (KV) state to disk so repeat questions "
            "about the same documents skip the expensive reading phase, even "
            "across restarts. Set false to disable."
        ),
    )
    kv_cache_dir: Path = Field(
        default=_PROJECT_ROOT / "data" / "cache" / "kv",
        description="Directory for the persistent KV cache.",
    )
    kv_cache_gb: int = Field(
        default=8,
        gt=0,
        le=100,
        description="Maximum disk space for the KV cache, in GB (oldest evicted).",
    )

    # --- Embeddings ---
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="HuggingFace embedding model. Downloaded once on first use.",
    )

    # --- Vector store ---
    chroma_persist_dir: Path = Field(
        default=_PROJECT_ROOT / "data" / "chroma_db",
        description="Directory where ChromaDB persists vectors.",
    )
    chroma_collection: str = Field(
        default="documents",
        description="ChromaDB collection name.",
    )

    # --- RAG tuning ---
    chunk_size: int = Field(default=800, gt=0, le=8000)
    chunk_overlap: int = Field(default=120, ge=0)
    # 10 excerpts (~2K tokens) gives enough material for summary and
    # comparison tasks while leaving room in the 8K context for the
    # conversation and a long answer. 4 was tuned for single-fact
    # questions and starved broad "analyze this document" requests.
    retrieval_top_k: int = Field(default=10, gt=0, le=50)

    # --- Strip leftover <think>...</think> from responses ---
    strip_think_tags: bool = Field(
        default=True,
        description="Strip <think>...</think> blocks from model responses.",
    )

    # --- Logging ---
    log_level: str = Field(default="INFO")

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_smaller_than_size(cls, value: int, info: ValidationInfo) -> int:
        # info.data holds fields that have already passed validation in
        # declaration order. chunk_size precedes chunk_overlap, so it is
        # available here when chunk_size itself was valid.
        size = info.data.get("chunk_size")
        if size is not None and value >= size:
            raise ValueError(f"chunk_overlap ({value}) must be smaller than chunk_size ({size})")
        return value

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}, got {value!r}")
        return upper


def get_settings() -> Settings:
    """Return a fresh Settings instance.

    Not cached intentionally — tests that monkeypatch env vars need a
    fresh read. Call sites that care about performance should cache
    locally.
    """
    return Settings()
