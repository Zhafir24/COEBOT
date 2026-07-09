# Architecture

This document captures the system shape and the rationale behind key
decisions. Updated whenever a major component changes.

## Design principles

1. **Fully offline.** No outbound network calls at runtime. The LLM (GGUF) is loaded from disk into `llama-cpp-python` in-process; the embedding model is downloaded once from HuggingFace on first run, then cached. After the first run, COEBOT is air-gap deployable.
2. **Simple over agentic.** This is a deterministic RAG pipeline, not an agent. No tool-use loops, no multi-step reasoning chains, no autonomous decisions. Each stage's behavior is predictable and independently testable.
3. **Strict module boundaries.** Data passing between modules is validated by Pydantic models. Integration bugs surface at the boundary, not deep inside the pipeline.
4. **Defense-in-depth quality.** Static typing (mypy --strict), linting (ruff), formatting, unit tests (≥80% coverage), pre-commit hooks, and CI on every PR.

## Component overview

```
                       ┌──────────────────────────┐
                       │  Streamlit UI + local    │
                       │  auth (scrypt)           │
                       └────────────┬─────────────┘
                                    │
                       ┌────────────▼─────────────┐
                       │  Pipeline orchestrator   │
                       │  RAG mode / Deep-read    │
                       └────────────┬─────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
 ┌──────▼────────┐          ┌───────▼──────┐           ┌────────▼─────────┐
 │  Ingestion    │          │  Retrieval   │           │  LLM (in-proc)   │
 │  PDF/DOCX/    │          │  ChromaDB    │           │  llama-cpp +     │
 │  XLSX → chunk │          │  top-k       │           │  Persistent KV   │
 │  → embed →    │          │  passages    │           │  prefix cache    │
 │  Chroma       │          │              │           │  → Qwen3 GGUF    │
 └───────────────┘          └──────────────┘           └──────────────────┘
```

## Module responsibilities

| Module                              | Responsibility                                                                                     |
|-------------------------------------|----------------------------------------------------------------------------------------------------|
| `doc_analyzer.models`               | Frozen Pydantic types (`Document`, `Chunk`, `Answer`) that flow between modules.                    |
| `doc_analyzer.config`               | Settings loaded from environment + `.env` (pydantic-settings).                                      |
| `doc_analyzer.parsers.pdf`          | PDF → `Document` via `pypdf` (with `pypdfium2` fallback for problematic files).                     |
| `doc_analyzer.parsers.docx`         | DOCX → `Document` via `mammoth`.                                                                    |
| `doc_analyzer.parsers.xlsx`         | XLSX → `Document` via `openpyxl`.                                                                   |
| `doc_analyzer.chunking.text`        | `Document` → list of `Chunk`. Token-aware splitting via `tiktoken`.                                 |
| `doc_analyzer.embeddings.encoder`   | Wraps `sentence-transformers` (`all-MiniLM-L6-v2`). Model cached as singleton.                      |
| `doc_analyzer.retrieval.store`      | ChromaDB persistence + similarity search + metadata filtering.                                      |
| `doc_analyzer.llm.client`           | In-process `llama-cpp-python` client. Includes `PrefixKVCache` for persistent prompt-prefix reuse. |
| `doc_analyzer.memory`               | Per-user personal facts. Injected into prompts on relevance match, kept out of KV-cached prefix.    |
| `doc_analyzer.auth.store`           | Local user store with scrypt-hashed passwords + active-session tracker.                             |
| `doc_analyzer.pipeline`             | Orchestrates ingestion + retrieval + inference. Two modes: RAG and full-document deep read.         |
| `doc_analyzer.ui.app`               | Streamlit interface (chat, uploads, chat history, model picker).                                    |
| `doc_analyzer.ui.styles`            | Centralized CSS injection and PNM brand palette.                                                    |
| `doc_analyzer.cli`                  | CLI entry point.                                                                                    |

## Key decisions

### Why `llama-cpp-python` in-process (not Ollama or an HTTP server)?

Ollama was the original choice, but v1 replaced it with in-process inference for three reasons:

1. **No separate daemon to install, run, or manage.** Users double-click one launcher; there is no service to configure or keep running.
2. **Deterministic quantization and threading control.** With Ollama, model behavior can change silently when the daemon updates. In-process, the GGUF file and `n_threads`/`n_ctx` settings pin the behavior.
3. **Persistent KV prefix caching.** `llama-cpp-python` exposes the raw KV state, allowing us to cache prompt prefixes across sessions (see `PrefixKVCache` below). Speedy re-asks about the same document set are the single biggest UX win of v1.

The pinned version `llama-cpp-python==0.3.18` is the last prebuilt CPU wheel that shipped without AVX-512; wheels 0.3.21+ enable AVX-512 which crashes with `STATUS_ILLEGAL_INSTRUCTION` on Meteor Lake CPUs.

### Why ChromaDB (not FAISS)?

ChromaDB persists to disk automatically and supports metadata filtering — both needed for multi-document collections. FAISS is faster but requires us to manage persistence and metadata separately. ChromaDB's embedded mode means no extra service to operate.

### Why `sentence-transformers` for embeddings?

`all-MiniLM-L6-v2` is ~90 MB, fast on CPU, and well-benchmarked. Downloaded once on first run and cached locally.

### Why frozen Pydantic models?

Mutable dicts and dataclasses are a frequent source of "ghost mutation" bugs in pipelines. Frozen Pydantic models force a copy-on-change discipline at module boundaries.

### Why RAG + full-document dual mode?

Small documents fit entirely in the model's context; retrieval would only introduce lossy compression. The pipeline picks per query: if all selected documents' tokenized size fits under the context budget, they are read in full (deep-read mode); otherwise, top-k retrieval kicks in (RAG mode).

## Persistent KV cache

`PrefixKVCache` (`src/doc_analyzer/llm/client.py`) is a disk-backed longest-prefix cache for the `llama.cpp` key-value state. It replaces the bundled `LlamaDiskCache` (whose `__getitem__` popped entries from disk on every read — with the re-insert path commented out upstream as broken — so cached states could never accumulate).

Key properties:

- **Reads never delete.** A cached document state survives being used.
- **Minimum prefix threshold** (`min_prefix_tokens`). A trivial 20-token overlap (e.g. common system prompt words) does not trigger a multi-GB state load.
- **Skip when live already covers.** If the in-RAM context matches the prompt at least as well as the disk entry would, the lookup misses on purpose (the load would be pure waste).
- **Write skip for small states and covered prefixes.** Chat-sized states aren't stored; new prompts whose prefix an existing entry already covers do not re-write.
- **LRU eviction above capacity** (`KV_CACHE_GB` in `.env`).

Configured at `data/cache/kv/` by default (gitignored).

## Testing strategy

- **Unit tests** (`tests/test_*.py`) — fast, isolated, mocked. `llama_cpp.Llama` is mocked so tests never load a real GGUF. Test PDFs are generated on the fly with `reportlab` (see `tests/conftest.py`).
- **Integration tests** (`@pytest.mark.integration`) — touch real ChromaDB and real sentence-transformers. Excluded from CI; run locally with `pytest -m integration`.
- **End-to-end smoke** — launch the app, upload a known document set, verify answers match the source.

## Non-goals

The following are explicitly out of scope to keep the surface small:

- OCR (scanned PDFs).
- Multi-modal input (images, tables as figures).
- Cloud deployment. The architecture allows it, but is not validated.
- Agentic behavior (tool use, planning, multi-step reasoning).
- GPU inference. COEBOT ships CPU-only. A GPU build of `llama-cpp-python` could be swapped in, but is not part of the shipped install.
