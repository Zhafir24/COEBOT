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

---

## 🐳 Install with Docker Desktop

Cross-platform alternative to the Windows ZIP. Runs in a container, works on Windows, macOS (Intel), and Linux. The container is CPU-only (see notes at the end of this section for GPU + Apple Silicon).

### Prerequisites

| Requirement | Where to get it |
|---|---|
| **Docker Desktop 4.24+** | https://www.docker.com/products/docker-desktop/ |
| **Docker Engine 20.10+** (Linux only, if you prefer no Desktop) | https://docs.docker.com/engine/install/ |
| **Git** | https://git-scm.com/downloads |
| **16 GB RAM** (8B models) or **32 GB RAM** (30B models) | your machine |
| **~10 GB free disk** for the image + a `.gguf` model | your machine |
| **A free host TCP port** (default 8080) | your machine |
| **Internet during the first build** (to pull the base image + Python packages) | your network |

Windows users: Docker Desktop must be running in **WSL2 mode** (the default since 2020). Check via *Settings → General → Use the WSL 2 based engine*.

### Steps (from a fresh clone)

Open a terminal (PowerShell on Windows, Terminal on macOS/Linux) and run:

```bash
# 1. Clone the repository
git clone https://github.com/Zhafir24/COEBOT.git
cd COEBOT

# 2. Make sure Docker is running (icon in system tray / menu bar). Verify:
docker compose version
#    -> Docker Compose version v2.x  (must NOT say "docker-compose")

# 3. Build the image. Takes 15-30 min on first build (llama-cpp-python
#    compiles from source; subsequent builds are cached and fast).
docker compose build

# 4. Put a .gguf model file in the models/ folder (see download links in
#    the ZIP install section above). At least one model must be present
#    or the container will error the first time you send a chat.

# 5. Start the container in the background
docker compose up -d

# 6. Open http://localhost:8080/ in your browser
```

### Verify it worked

```bash
# Should show one container named "coebot" in state "Up (healthy)"
docker compose ps

# Bootstrap endpoint returns a small JSON object
curl http://localhost:8080/api/bootstrap
#   -> {"user":null,"has_users":false}

# Stream logs (Ctrl-C to detach; container keeps running)
docker compose logs -f coebot
```

The health check first turns "healthy" 60–90 s after start (it waits for the embedding model + Python startup).

### Stop, restart, remove

```bash
docker compose stop            # stop containers, keep data + image
docker compose start           # start again
docker compose down            # stop AND remove containers (keeps volumes)
docker compose down -v         # ALSO delete the data/ + models/ contents
docker compose up -d --build   # rebuild the image after a git pull
```

### Data persistence

The compose file bind-mounts two host directories into the container so nothing is lost across restarts:

| Host folder | Container path | What lives there |
|---|---|---|
| `./data/` | `/app/data/` | user accounts, chats, uploaded documents, ChromaDB vector index, session secret, memory |
| `./models/` | `/app/models/` | your `.gguf` model files (put them here before first chat) |

Back up the `./data/` folder to preserve your chats and account across image rebuilds.

### Common configuration overrides

Copy `.env.example` to `.env` next to the compose file and edit — Compose picks it up automatically:

```bash
cp .env.example .env
```

Frequently-changed variables:

- `MODEL_N_CTX=40960` — context window (default 40K = ~70 pages of deep-read)
- `MODEL_MAX_TOKENS=12000` — maximum output tokens per answer
- `MODEL_N_THREADS=0` — CPU threads (0 = auto-detect)

Or change the published port without editing any file:

```bash
COEBOT_PORT=9090 docker compose up -d
```

The compose file reads `${COEBOT_PORT:-8080}`, so this works for any host port you have free. Persist the choice by adding `COEBOT_PORT=9090` to `.env`.

### Notes and current limitations

- **Apple Silicon (M1/M2/M3):** the image builds `linux/amd64` binaries. It will run under Rosetta emulation on Apple Silicon but LLM inference will be very slow. A native `linux/arm64` build is planned but not yet published.
- **NVIDIA GPU:** the Docker image is CPU-only. Enabling GPU inside a container requires the NVIDIA Container Toolkit plus a rebuilt engine wheel with CUDA — not covered here. For GPU use, prefer the native Windows install with `install-cuda.bat` (see the ZIP install section).
- **Slow first build:** the 15–30 min figure is compilation of `llama-cpp-python`. Subsequent `docker compose build` runs reuse the cached layer and take under a minute unless `pyproject.toml` or `src/` changes.
- **Port 80 vs 8080:** Docker publishes container port 80 as host port 8080 to avoid clashing with anything already listening on host port 80. The native (non-Docker) install uses 80 directly.

### Troubleshooting

**"docker: command not found" or "Cannot connect to the Docker daemon."** Docker Desktop isn't running (or, on Linux, the `docker` service is stopped). Open Docker Desktop and wait for the icon to say "Docker Desktop is running" before retrying.

**"Bind for 0.0.0.0:8080 failed: port is already allocated."** Something else on your machine already uses port 8080. Change the left side of the `ports:` mapping in `compose.yaml` to a free port (e.g. `9090:80`) and re-run `docker compose up -d`.

**Container starts then exits immediately.** Run `docker compose logs coebot` — the most common causes are: no `.gguf` file in `models/` (the app can start but can't answer), or the model needs more memory than the compose file's `deploy.resources.limits.memory: 12g` allows (raise it to `24g` for the 30B model).

**"unhealthy" status in `docker compose ps`.** The healthcheck failed. Usually means the app didn't finish starting inside the 90-second grace period. Check `docker compose logs coebot` for the actual error; if the model is genuinely still loading (very large model on slow disk), increase the `healthcheck.start_period` in `compose.yaml`.

**Windows: bind mount fails with "invalid mount config."** Your project folder is on a Windows path Docker Desktop can't share. Move the project into your user profile (`C:\Users\<you>\...`) or enable file sharing for the drive in Docker Desktop → Settings → Resources → File Sharing.

**Build fails during `pip wheel llama-cpp-python`.** Almost always memory exhaustion during compilation. Docker Desktop → Settings → Resources → give the VM at least 6 GB memory, then `docker compose build --no-cache` to retry.

---

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
