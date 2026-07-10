# COEBOT

Fully-local document analysis chatbot. Runs Qwen3 (or any GGUF chat model) in-process via `llama-cpp-python`, retrieves context from your own PDFs, DOCXs, and XLSXs, and answers with page-level citations. No API calls. No telemetry. Air-gap deployable.

## Prerequisites

Before you start, you need three things installed:

- **Python 3.12 or 3.13** — https://www.python.org/downloads/
- **Git** — https://git-scm.com/download/win
- **A GGUF chat-tuned model file** — downloaded from Hugging Face (see Step 6 below)

Windows 10 or 11 already ships with the runtime components COEBOT needs (Visual C++ Redistributable 2015-2022, PowerShell 5.1+, AVX2 CPU support on any 2015+ machine). The install command in **Step 5** uses a special index URL to pull a **prebuilt Windows binary wheel** for `llama-cpp-python`, so you do **not** need Visual Studio, Visual C++ Build Tools, or any C++ compiler. Do not skip the `--extra-index-url` flag or the install will try to compile from C++ source and fail.

## Installation — step by step

Follow these seven steps in order. Each includes a **check** you can run to verify that step worked, and a note for the most common problem if it didn't.

> **What you install by hand vs. what the computer installs for you:**
>
> - You install **two apps manually**: Python (Step 1) and Git (Step 2). That is the full list of installers you download and run.
> - Python already includes **`pip`** (the package installer used in Step 5) and **`venv`** (the isolation tool used in Step 4). You do **not** download or install pip or venv separately — they come with Python 3.12.
> - Everything else the chatbot needs — **Streamlit, llama-cpp-python, ChromaDB, sentence-transformers, python-docx, openpyxl, pypdf, pandas, numpy**, and about 190 supporting libraries — is downloaded and installed automatically by the one `pip install` command in Step 5.
> - The GGUF model file (Step 6) is a third manual download, but it is data (the model itself), not a program.
>
> **Order matters:** Python must be installed first because pip and venv only exist after Python is installed. Git can be installed at any time before Step 3. Never install Streamlit, ChromaDB, or any other Python package by itself — Step 5 handles all of them together.

### Step 1 — Install Python

1. Open https://www.python.org/downloads/ and click the big yellow **Download Python 3.12.x** button.
2. Run the installer you just downloaded.
3. **CRITICAL:** On the very first installer screen, at the bottom, tick the checkbox **"Add python.exe to PATH"**. If you skip this, nothing later will work.
4. Click **Install Now** and wait for it to finish.

**Check:** Press <kbd>Win</kbd> + <kbd>R</kbd>, type `powershell`, press Enter. In the blue window that opens, type `py --version` and press Enter. You should see something like `Python 3.12.7`.

**If you see "'py' is not recognized":** You forgot the PATH checkbox. Uninstall Python from **Settings → Apps**, then reinstall from scratch with the box ticked.

**Note — what you just installed:** the Python installer put three things on your machine at once:

- **`python`** (or `py`) — the language runtime that runs code.
- **`pip`** — the package installer you'll use in Step 5. Try `pip --version` in PowerShell to confirm.
- **`venv`** — the virtual environment tool you'll use in Step 4. Ships as a Python module (`python -m venv`).

You do **not** need separate downloads for pip or venv. They come bundled with Python since 2014.

### Step 2 — Install Git

1. Open https://git-scm.com/download/win — the download will start automatically.
2. Run the installer.
3. Click **Next** on every screen to accept the defaults. Do not change anything.

**Check:** In PowerShell, type `git --version`. You should see `git version 2.4x.x` or similar.

### Step 3 — Download COEBOT from GitHub

1. Open PowerShell (<kbd>Win</kbd> + <kbd>R</kbd>, type `powershell`, Enter).
2. Type these commands one at a time, pressing Enter after each:

   ```powershell
   cd $HOME\Documents
   git clone https://github.com/Zhafir24/COEBOT.git
   cd COEBOT
   ```

**Check:** Type `ls` and press Enter. You should see a list of files including `README.md`, `pyproject.toml`, and folders like `src/`, `tests/`, `models/`.

### Step 4 — Create a virtual environment

A virtual environment is a private folder for COEBOT's Python packages, so they don't conflict with anything else on your computer. Still in PowerShell inside the `COEBOT` folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Check:** Your PowerShell prompt should now start with `(.venv)`. That means the virtual environment is active.

**If `Activate.ps1` fails with "cannot be loaded because running scripts is disabled":** Windows blocks unsigned scripts by default. Run this **once**, then retry Step 4:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Answer **Y** when prompted.

### Step 5 — Install COEBOT and its dependencies

Still in PowerShell (prompt should still show `(.venv)`):

```powershell
pip install --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu -e .
copy .env.example .env
```

The `--extra-index-url` flag is **required**. It tells pip to fetch `llama-cpp-python` as a prebuilt binary wheel from the maintainer's own wheel server, because that specific package publishes only source code to PyPI. Without this flag, pip would try to compile 20+ MB of C++ code on your machine and fail unless you happen to have Visual Studio Build Tools installed.

This single command installs **about 200 Python packages** — this is why Streamlit, ChromaDB, and the other libraries do not appear as separate steps. The important ones you might have wondered about:

- **`streamlit`** — the web UI framework that renders the chat interface at `http://127.0.0.1/`.
- **`llama-cpp-python`** — the in-process LLM engine that loads and runs the GGUF file.
- **`chromadb`** — the local vector database used for retrieval.
- **`sentence-transformers`** — downloads the `all-MiniLM-L6-v2` embedding model on first run (~90 MB, one-time).
- **`python-docx`, `openpyxl`, `pypdf`, `pypdfium2`, `mammoth`** — the document parsers for DOCX, XLSX, and PDF uploads.
- **`pydantic`, `pydantic-settings`, `python-dotenv`, `pandas`, `numpy`, `diskcache`** — supporting libraries used by the pipeline.

The command takes **2–5 minutes** depending on your internet speed. Watch the progress; when it finishes you'll see something like `Successfully installed doc_analyzer-0.1.0 streamlit-1.xx.x llama-cpp-python-0.3.18 chromadb-0.5.x ...` (with many more names).

**Check:** Type `python -c "import doc_analyzer; print('OK')"` — you should see `OK` printed on the next line.

### Step 6 — Download a GGUF model

COEBOT needs a language model file to work. This file is too large to include in the GitHub repo, so you download it separately.

**For 16 GB RAM laptops** (recommended default):

1. Open https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/tree/main in your browser.
2. Find the file named **`Qwen3.5-9B-UD-Q4_K_XL.gguf`** (about 6 GB).
3. Click the small **⬇ download** icon next to that file.
4. Wait for the download to finish (10–30 minutes depending on your connection).
5. Move the downloaded `.gguf` file into the `models/` folder inside your `COEBOT` folder.

**For 32 GB+ RAM machines** (higher-quality but slower on smaller CPUs):
Use https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF instead, and download the file with **`Q4_K_M`** in its name (about 19 GB).

**Check:** In PowerShell, type `ls models\*.gguf`. You should see your `.gguf` file listed.

### Step 7 — Launch COEBOT

1. Close PowerShell.
2. Open File Explorer and go to `Documents\COEBOT`.
3. Double-click **`start_coebot.bat`**.
4. A black terminal window opens. Wait ~30 seconds for the message *"You can now view your Streamlit app in your browser."*
5. Your default browser opens automatically at **http://127.0.0.1/**.
6. On the first visit, register an account (username + password) — these are stored **only on your computer**, never sent anywhere.
7. Once logged in, upload a PDF, DOCX, or XLSX file from the left panel and start asking questions.

**To stop COEBOT:** close the black terminal window.

**To start it next time:** just double-click `start_coebot.bat` again. Steps 1–6 are one-time setup.

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `py --version` says "not recognized" | Python's PATH checkbox was missed during install | Uninstall Python from Settings → Apps, reinstall with **"Add python.exe to PATH"** ticked |
| `Activate.ps1` cannot be loaded | PowerShell script execution is blocked | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, answer **Y**, then retry |
| `pip install` fails with `error: Microsoft Visual C++ 14.0 or greater is required` | You ran `pip install -e .` **without** the `--extra-index-url` flag, so pip tried to compile `llama-cpp-python` from source | Delete the `.venv\` folder, re-run Step 4, then re-run Step 5 **exactly as written** — the `--extra-index-url` flag pulls a prebuilt wheel and avoids compilation entirely. Only install Visual Studio Build Tools (https://visualstudio.microsoft.com/visual-cpp-build-tools/) if you have a specific reason to build from source. |
| `pip install` says `ERROR: No matching distribution found for llama-cpp-python==0.3.18` | Same cause — the `--extra-index-url` flag was missing or misspelled | Copy Step 5's command exactly. The full URL is `https://abetlen.github.io/llama-cpp-python/whl/cpu` — no typos, no trailing slash needed |
| App loads but errors *"No .gguf file found in models/"* | Model file not placed correctly | Confirm the file ends in `.gguf` and is directly inside `models/`, not in a subfolder |
| Browser shows "This site can't be reached" | Streamlit hasn't finished starting yet | Wait 30 seconds after the terminal opens, then refresh |
| Chatbot is very slow (< 1 token/sec) | Not enough free RAM, or single-channel memory | Close other apps; if the laptop has one RAM slot filled, adding a matched second stick roughly doubles inference speed |

## Features

- **Chat + Documents** — grounded question-answering over your own files with inline page citations.
- **RAG mode** — chunk + embed + top-k retrieval for large document sets that exceed the context window.
- **Full-document mode** — reads entire documents when they fit, so short PDFs get an uncompressed answer.
- **Persistent KV cache** — prompt-prefix state is saved to disk, so re-asking about the same documents (even after restart) skips the expensive prefill phase.
- **Multi-format parsers** — PDF (`pypdf`), DOCX (`python-docx`), and XLSX (`openpyxl`) out of the box.
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
