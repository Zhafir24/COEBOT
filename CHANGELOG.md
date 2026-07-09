# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-09

Initial public release.

### Added
- In-process LLM inference via `llama-cpp-python==0.3.18` (CPU wheel, pinned pre-AVX-512).
- `PrefixKVCache` — a persistent, disk-backed longest-prefix KV cache that survives restarts, fixing the `LlamaDiskCache` read-and-delete defect.
- RAG pipeline: chunk → embed (`all-MiniLM-L6-v2`) → ChromaDB retrieval → grounded answer with page-level citations.
- Full-document (deep-read) mode: reads entire documents in one prompt when they fit the context window.
- Multi-format parsers: PDF (`pypdf` + `pypdfium2` fallback), DOCX (`mammoth`), XLSX (`openpyxl`).
- Local authentication: scrypt-hashed passwords + active-session tracking in local JSON files.
- Per-user memory: personal facts remembered across chats, injected only when relevant, placed after document text so they don't invalidate KV-cached prefixes.
- Streamlit UI with PNM branding, offline-served Plus Jakarta Sans fonts, and per-chat history persisted as standalone JSON files.
- Windows-first launcher (`start_coebot.bat` + `launch-windows.ps1`).
- Quality gates: `ruff`, `mypy --strict`, `pytest` (≥80% coverage), pre-commit hooks, GitHub Actions CI.
- Documentation: README with 7-step beginner install guide + troubleshooting, `docs/architecture.md`, `CONTRIBUTING.md`, `SECURITY.md`.

### Security
- `.gitignore` blocks all runtime data by default: `data/users.json`, `data/memory.json`, `data/chats/`, session state, GGUF weights, vector DB, and per-session UI state.
- No outbound network calls at runtime after the first-run embedding-model download.

[0.1.0]: https://github.com/Zhafir24/COEBOT/releases/tag/v0.1.0
