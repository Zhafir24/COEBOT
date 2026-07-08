# Architecture

This document captures the system shape and the rationale behind key
decisions. Updated whenever a major component changes.

## Design principles

1. **Local-only.** No outbound network calls beyond the Ollama daemon on `localhost:11434`. The embedding model is downloaded once from HuggingFace, then cached; air-gapped operation is possible after the first run.
2. **Simple over agentic.** This is a deterministic RAG pipeline, not an agent. No tool-use loops, no multi-step reasoning chains, no autonomous decisions. Each stage's behavior is predictable and independently testable.
3. **Strict module boundaries.** Data passing between modules is validated by Pydantic models. This catches integration bugs at the boundary instead of deep inside the pipeline.
4. **Defense-in-depth quality.** Static typing (mypy --strict), linting (ruff), formatting, unit tests (≥80% coverage), pre-commit hooks, and CI on every PR.

## Component overview

```
                                  ┌──────────────────┐
                                  │  Streamlit UI    │ (Phase 3)
                                  └────────┬─────────┘
                                           │
                                  ┌────────▼─────────┐
                                  │  Orchestrator    │ (Phase 2)
                                  └────────┬─────────┘
                                           │
                ┌──────────────────────────┼──────────────────────────┐
                │                          │                          │
       ┌────────▼─────────┐       ┌────────▼─────────┐       ┌────────▼─────────┐
       │  Ingestion       │       │  Retrieval       │       │  LLM Client      │
       │  (Phase 1)       │       │  (Phase 2)       │       │  (Phase 1)       │
       └────────┬─────────┘       └────────┬─────────┘       └──────────────────┘
                │                          │
       ┌────────▼─────────┐       ┌────────▼─────────┐
       │  Parser → Chunker│       │  Embedder        │
       │  → Embedder      │       │  → Vector Search │
       │  → Vector Store  │       └──────────────────┘
       └──────────────────┘
```

## Module responsibilities

| Module                       | Responsibility                                                                  |
|------------------------------|---------------------------------------------------------------------------------|
| `doc_analyzer.models`        | Frozen Pydantic data types (`Document`, `Chunk`) that flow between modules.     |
| `doc_analyzer.config`        | Single Settings object loaded from environment + `.env`.                        |
| `doc_analyzer.parsers.pdf`   | PDF → `Document`. Explicit error types for each failure class.                  |
| `doc_analyzer.chunking`      | `Document` → list of `Chunk`. Token-aware splitting via `tiktoken`. (Phase 2)   |
| `doc_analyzer.embeddings`    | Wraps `sentence-transformers`. Caches the model singleton. (Phase 2)            |
| `doc_analyzer.retrieval`     | ChromaDB persistence + similarity search. (Phase 2)                             |
| `doc_analyzer.llm`           | Ollama chat client with retry + timeout. (Phase 1)                              |
| `doc_analyzer.ui.app`        | Streamlit interface. (Phase 3)                                                  |
| `doc_analyzer.cli`           | CLI entry point.                                                                |

## Key decisions

### Why Ollama (not llama.cpp directly)?

Ollama provides a stable HTTP API and handles model lifecycle (download, quantization, memory management) cleanly. We don't need llama.cpp's lower-level control, and Ollama's daemon model fits enterprise deployment patterns (systemd service, Windows service).

### Why ChromaDB (not FAISS)?

ChromaDB persists to disk automatically and supports metadata filtering — both needed for multi-document collections. FAISS is faster but requires us to manage persistence and metadata separately. ChromaDB's embedded mode means no extra service to operate.

### Why sentence-transformers (not Ollama embeddings)?

`all-MiniLM-L6-v2` is ~22 MB, fast on CPU, and well-benchmarked. Using Ollama for embeddings would tie us to whatever embedding model the user's Ollama instance has, with less control over consistency.

### Why pydantic frozen models?

Mutable dicts and dataclasses are a frequent source of "ghost mutation" bugs in pipelines. Frozen Pydantic models force a copy-on-change discipline at module boundaries.

## Testing strategy

- **Unit tests** (`tests/test_*.py`) — fast, isolated, no real services. Generated test PDFs via reportlab.
- **Integration tests** (`@pytest.mark.integration`) — touch real Ollama / ChromaDB. Excluded from CI; run locally with `pytest -m integration`.
- **End-to-end smoke** — manual run of Streamlit with a known document set, with answers verified against the source.

## Non-goals

The following are explicitly out of scope to keep the surface small:

- OCR (scanned PDFs). Phase 4 if requested.
- Multi-modal documents (images, tables). Phase 4.
- Multi-user authentication. The app assumes a trusted local user.
- Cloud deployment. The architecture allows it but is not validated.
- Agentic behavior (tool use, planning, multi-step reasoning).
