# COEBOT

Fully-local document analysis chatbot. Runs Qwen3 (or any GGUF chat model) in-process via `llama-cpp-python`, retrieves context from your own PDFs, DOCXs, and XLSXs, and answers with page-level citations. No API calls. No telemetry. Air-gap deployable.

## Prerequisites

Install these three things before running the Quick Start:

- **Python 3.12 or 3.13** — download from https://www.python.org/downloads/. During install, tick **"Add Python to PATH"** at the bottom of the first installer screen.
- **Git** — download from https://git-scm.com/download/win. Accept the default options; the installer includes Git Bash and Git Credential Manager for future pushes.
- **A GGUF chat-tuned model file** — downloaded separately from Hugging Face and placed inside `models/`:
  - **16 GB RAM laptop:** `unsloth/Qwen3.5-9B-GGUF` → file `UD-Q4_K_XL` (~6 GB)
  - **32 GB+ RAM machine:** `unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF` → file `Q4_K_M` (~19 GB)
  - See [`models/README.md`](models/README.md) for other options and multi-model setups.

Windows 10 or 11 already ships with everything else COEBOT needs (PowerShell 5.1+, Visual C++ Redistributable 2015-2022, and AVX2 CPU support on any 2015+ machine). Linux and macOS work too, but the launcher script is Windows-first — on other platforms run `streamlit run src/doc_analyzer/ui/app.py` directly after `pip install -e .`.

## Quick Start

`main` is the only branch — every release lands here directly.

```bash
git clone https://github.com/Zhafir24/COEBOT.git
cd COEBOT
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e .
cp .env.example .env
```

Drop your GGUF model into `models/` (from the Prerequisites), then double-click `start_coebot.bat` or run `.\launch-windows.ps1` in PowerShell. The app opens at `http://127.0.0.1/` once the model finishes loading (~30 seconds for a Q4_K_M model on CPU).

Linux/macOS notes, hardware-matched model recommendations, and the persistent KV cache tuning live in [`docs/architecture.md`](docs/architecture.md).

## Features

- **Chat + Documents** — grounded question-answering over your own files with inline page citations.
- **RAG mode** — chunk + embed + top-k retrieval for large document sets that exceed the context window.
- **Full-document mode** — reads entire documents when they fit, so short PDFs get an uncompressed answer.
- **Persistent KV cache** — prompt-prefix state is saved to disk, so re-asking about the same documents (even after restart) skips the expensive prefill phase.
- **Multi-format parsers** — PDF (`pypdf`), DOCX (`mammoth`), and XLSX out of the box.
- **Local auth** — per-user login backed by hashed passwords in a local JSON store.
- **Memory** — personal facts remembered per user, injected into prompts only when relevant.
- **Chat history** — every conversation persisted as a standalone JSON file for easy backup, export, or deletion.
- **Themed UI** — PNM-branded Streamlit app with self-hosted Plus Jakarta Sans (no external font CDN, fully offline).

## Demo

A pipeline diagram and end-to-end walkthrough live in [`docs/architecture.md`](docs/architecture.md).

## Contributing

Contributions welcome. Best entry points are additional file parsers, retrieval improvements, and UI polish. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for coding conventions and the pre-commit + CI flow.

## Security

COEBOT is designed to run air-gapped. No data leaves the machine, no telemetry is emitted, and no external API is called. Keep model files (`*.gguf`) out of version control, never commit `data/users.json`, `data/memory.json`, or the contents of `data/chats/` and `data/documents/` — the shipped `.gitignore` already blocks these paths. Report vulnerabilities per [`SECURITY.md`](SECURITY.md).
