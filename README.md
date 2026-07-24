# COEBOT

Fully-local document analysis chatbot. Runs Qwen3 / Qwen3.5 / Qwen3.6 (or any GGUF chat model) in-process via `llama-cpp-python`, retrieves context from your own PDFs, DOCXs, and XLSXs, and answers with page-level citations. No API calls. No telemetry. Air-gap deployable.

**Version 2.0.2** — new Starlette + custom web UI (Streamlit removed), background document indexing, LENGTH-aware answer style, optional NVIDIA CUDA acceleration, ~70-page deep-read out of the box.

---

## 🚀 Easiest install — Portable ZIP (no Python, no Git, no compiler)

**Not a developer? Use this.** The portable edition bundles Python 3.12, all packages (including a precompiled `llama-cpp-python` for any modern Windows CPU), and the sentence-transformers embedding model:

1. Download **`COEBOT-portable-v2.0.2.zip`** (~478 MB) from the **[Releases page](https://github.com/Zhafir24/COEBOT/releases/latest)** and extract it to a short path, e.g. `C:\COEBOT`.
2. Download a `.gguf` model into the extracted `models\` folder — recommended:
   - **[Qwen3.5-9B-UD-Q4_K_XL.gguf](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-UD-Q4_K_XL.gguf?download=true)** (~5.6 GB, needs 16 GB RAM)
   - or [Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507-GGUF/resolve/main/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf?download=true) (~18 GB, needs 32 GB RAM)
3. Double-click **`start_coebot.bat`**. Your browser opens at `http://127.0.0.1/` — create an account and chat.

Optional GPU acceleration (NVIDIA only): double-click **`install-cuda.bat`** after step 3. It self-elevates, checks CUDA Toolkit + Build Tools (with links if missing), builds the GPU engine, and automatically restores the CPU engine if anything fails.

Everything below this line is the **developer install** for editing the source code, running tests, or contributing.

---

## Developer install (from source)

### Prerequisites

- **Python 3.12 or 3.13** — https://www.python.org/downloads/ (tick "Add python.exe to PATH")
- **Git** — https://git-scm.com/download/win
- A `.gguf` chat model file (see model links above)

Windows 10/11 already includes what you need at runtime (VC++ 2015-2022 redistributable, PowerShell 5.1+, AVX2 CPU support on any ~2015+ machine). The install command below uses a **precompiled wheel** for `llama-cpp-python`, so you don't need Visual Studio unless you plan to build the CUDA variant yourself.

### Steps

```powershell
# 1. Clone and enter the repo
git clone https://github.com/Zhafir24/COEBOT.git
cd COEBOT

# 2. Create and activate a virtual environment
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
#    -> your prompt must now start with (.venv)

# 3. Install COEBOT and its dependencies (prebuilt CPU wheel of llama-cpp-python)
pip install --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu -e .
copy .env.example .env

# 4. Put a .gguf model file in the models/ folder

# 5. Run the app
.\start_coebot.bat
#    -> the browser opens at http://127.0.0.1/
```

**Note on the `--extra-index-url` flag:** `llama-cpp-python` publishes only source code to PyPI; the prebuilt Windows CPU wheels live on the maintainer's own index. Omit the flag and pip will try to compile from C++ source and fail.

## Architecture

- **Backend** — Starlette + uvicorn ([`src/doc_analyzer/server.py`](src/doc_analyzer/server.py)), zero UI framework
- **Frontend** — hand-written HTML/CSS/JS in [`src/doc_analyzer/webui/`](src/doc_analyzer/webui/) served as static files
- **LLM** — [`llama-cpp-python`](https://github.com/abetlen/llama-cpp-python) 0.3.32 in-process; models loaded from `models/*.gguf`
- **Retrieval** — [ChromaDB](https://github.com/chroma-core/chroma) local vector store + `sentence-transformers/all-MiniLM-L6-v2` embeddings
- **Parsers** — `pypdf` (PDF), `python-docx` (DOCX), `openpyxl` (XLSX)
- **Auth** — scrypt-hashed local accounts in `data/users.json`, itsdangerous-signed session cookies

Every runtime file lives inside the project folder — chats, uploaded documents, ChromaDB, memory, session secret — nothing leaves the machine.

## Configuration (`.env`)

Copy `.env.example` to `.env` and edit if needed. Everything ships with sensible defaults tuned for real use:

- `MODEL_N_CTX=40960` — context window (~70 pages of deep-read). Lower to 32768 on tight RAM.
- `MODEL_MAX_TOKENS=12000` — max generated tokens per response.
- `MODEL_N_THREADS=0` — CPU threads (0 = auto-detect).
- `MODEL_N_GPU_LAYERS=-1` — GPU layers (only used if llama-cpp-python was built with CUDA; -1 offloads all).
- `MODEL_FILENAME=` — leave empty to auto-detect the first `.gguf` in `models/`.

## Optional: NVIDIA GPU (CUDA)

Only relevant on machines with an NVIDIA card. Two ways:

- **Portable ZIP users**: double-click `install-cuda.bat` inside the extracted folder — it self-elevates, checks prerequisites (with download links for CUDA Toolkit and Visual Studio Build Tools if missing), enables Windows Long Path support, and builds the CUDA variant of the pinned `llama-cpp-python` version. Automatic backup + restore if anything fails.
- **Developer install**: same script works with the venv layout too. Or manually: `$env:CMAKE_ARGS="-DGGML_CUDA=on"; $env:FORCE_CMAKE="1"; pip install --force-reinstall --no-cache-dir --no-build-isolation llama-cpp-python==0.3.32`.

The build takes 15–40 minutes and requires CUDA Toolkit 12.x + VS Build Tools with the C++ workload.

## Development

```powershell
.\scripts\dev.ps1 check       # ruff lint + format check + mypy
.\scripts\dev.ps1 format      # ruff format + auto-fix
.\scripts\dev.ps1 test        # pytest (unit tests only)
.\scripts\dev.ps1 test-all    # pytest (includes integration tests that hit real ChromaDB)
```

Continuous integration runs on Ubuntu and Windows for every push to `main` and every pull request — see `.github/workflows/ci.yml`.

## License

MIT — see [`LICENSE`](LICENSE).
