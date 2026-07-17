# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-07-16

### Added
- **Session mode is now functional.** "Recording" saves chats and memory
  as before; "Nobody" opens a temporary conversation — no chat file, no
  Recents entry, no chat pointer, no attachment state, and memory is
  neither read nor written. Explicit "remember …" commands are politely
  refused in Nobody mode. Opening a saved chat from Recents exits
  Nobody mode. Semantics mirror ChatGPT/Claude temporary chats.

### Fixed
- **Sidebar overhaul for Streamlit 1.58+.** The framework's new DOM
  shape (extra wrapper div) and screen-based canvas sizing clipped the
  bottom of the sidebar — the Sign out button could be invisible at
  common window sizes. The app canvas is now clamped to the real
  viewport, and the sidebar uses a Claude-style layout: the sidebar
  itself never scrolls, the recents list is the one elastic region
  with internal scrolling, and the profile group is pinned to the
  bottom by plain flexbox (the fragile pushSignOutUp JS hack is gone).
- Chat rows are compact single-line with ellipsis, left-aligned.
- Launcher (`launch-windows.ps1`) now puts the venv's Scripts dir on
  PATH: Streamlit 1.58 spawns the app in a child process, and without
  activation semantics the child could resolve the wrong Python.

### Changed
- Streamlit dependency pinned to `>=1.58.0,<1.60` — the sidebar CSS
  targets framework DOM internals; untested version jumps silently
  break layout.
- Package version aligned with release tags (0.1.0 → 1.1.0).

## [0.1.0] — 2026-07-09

Initial public release.

### Added
- In-process LLM inference via `llama-cpp-python==0.3.18` (CPU wheel, pinned pre-AVX-512).
- `PrefixKVCache` — a persistent, disk-backed longest-prefix KV cache that survives restarts, fixing the `LlamaDiskCache` read-and-delete defect.
- RAG pipeline: chunk → embed (`all-MiniLM-L6-v2`) → ChromaDB retrieval → grounded answer with page-level citations.
- Full-document (deep-read) mode: reads entire documents in one prompt when they fit the context window.
- Multi-format parsers: PDF (`pypdf` + `pypdfium2` fallback), DOCX (`python-docx` for text, `mammoth` for HTML preview), XLSX (`openpyxl`).
- Local authentication: scrypt-hashed passwords + active-session tracking in local JSON files.
- Per-user memory: personal facts remembered across chats, injected only when relevant, placed after document text so they don't invalidate KV-cached prefixes.
- Streamlit UI with PNM branding, offline-served Plus Jakarta Sans fonts, and per-chat history persisted as standalone JSON files.
- Windows-first launcher (`start_coebot.bat` + `launch-windows.ps1`).
- Quality gates: `ruff`, `mypy --strict`, `pytest` (≥80% coverage), pre-commit hooks, GitHub Actions CI.
- Documentation: README with 7-step beginner install guide + troubleshooting, `docs/architecture.md`, `CONTRIBUTING.md`, `SECURITY.md`.

### Security
- `.gitignore` blocks all runtime data by default: `data/users.json`, `data/memory.json`, `data/chats/`, session state, GGUF weights, vector DB, and per-session UI state.
- No outbound network calls at runtime after the first-run embedding-model download.

[1.1.0]: https://github.com/Zhafir24/COEBOT/releases/tag/v1.1.0
[0.1.0]: https://github.com/Zhafir24/COEBOT/releases/tag/v1.0.0
