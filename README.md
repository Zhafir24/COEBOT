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
> - You install **two apps manually**: Git (Step 1) and Python (Step 2). That is the full list of installers you download and run.
> - Python already includes **`pip`** (the package installer used in Step 5) and **`venv`** (the isolation tool used in Step 4). You do **not** download or install pip or venv separately — they come with Python 3.12.
> - Everything else the chatbot needs — **Streamlit, llama-cpp-python, ChromaDB, sentence-transformers, python-docx, openpyxl, pypdf, pandas, numpy**, and about 190 supporting libraries — is downloaded and installed automatically by the one `pip install` command in Step 5.
> - The GGUF model file (Step 6) is a third manual download, but it is data (the model itself), not a program.
>
> **The order between Steps 1 and 2 does not technically matter** — Git and Python are independent installers, neither depends on the other. The steps below put Git first because it is the smaller, faster install and immediately gives you the `git clone` command you need for Step 3. The real ordering rule is later: Git must exist before **Step 3** (clone) and Python must exist before **Step 4** (virtual environment). Never install Streamlit, ChromaDB, or any other Python package by itself — Step 5 handles all of them together.

### Step 1 — Install Git

1. Open https://git-scm.com/download/win — the download will start automatically.
2. Run the installer you just downloaded.
3. Click **Next** on every screen to accept the defaults. Do not change anything.

**Check:** Press <kbd>Win</kbd> + <kbd>R</kbd>, type `powershell`, press Enter. In the blue window that opens, type `git --version` and press Enter. You should see `git version 2.4x.x` or similar. Keep this PowerShell window open — you will use it for the rest of the steps.

### Step 2 — Install Python

1. Open https://www.python.org/downloads/ and click the big yellow **Download Python 3.12.x** button.
2. Run the installer you just downloaded.
3. **CRITICAL:** On the very first installer screen, at the bottom, tick the checkbox **"Add python.exe to PATH"**. If you skip this, nothing later will work.
4. Click **Install Now** and wait for it to finish.

**Check:** In your open PowerShell window, type `py --version` and press Enter. You should see something like `Python 3.12.7`.

**If you see "'py' is not recognized":** You forgot the PATH checkbox during install, **or** the PowerShell window was open before Python was installed and did not pick up the new PATH. Try closing and reopening PowerShell first. If it still fails, uninstall Python from **Settings → Apps**, then reinstall from scratch with the checkbox ticked.

**Note — what you just installed:** the Python installer put three things on your machine at once:

- **`python`** (or `py`) — the language runtime that runs code.
- **`pip`** — the package installer you'll use in Step 5. Try `pip --version` in PowerShell to confirm.
- **`venv`** — the virtual environment tool you'll use in Step 4. Ships as a Python module (`python -m venv`).

You do **not** need separate downloads for pip or venv. They come bundled with Python since 2014.

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

**Check — CRITICAL:** Your PowerShell prompt **must** now start with `(.venv)`. Example:

```
(.venv) PS C:\Users\yourname\Documents\COEBOT>
```

If the `(.venv)` prefix is missing, **stop and fix it before Step 5** — without it, Step 5's `pip install` puts Streamlit and 200 other packages in the wrong place (system-wide Python), and Step 7's launcher will fail with "streamlit is not installed."

**⚠️ New PowerShell windows lose the venv:** The `(.venv)` marker is per-window and does **not** persist. If you close this PowerShell and open a new one later, the venv is inactive again — before running any COEBOT command in the new window, first `cd` into the COEBOT folder and re-run `.\.venv\Scripts\Activate.ps1`. Check for the `(.venv)` marker every single time before pip/python/streamlit commands.

**If `Activate.ps1` fails with "cannot be loaded because running scripts is disabled":** Windows blocks unsigned scripts by default. Run this **once**, then retry Step 4:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Answer **Y** when prompted.

### Step 5 — Install COEBOT and its dependencies

**Before you paste the command below, look at your PowerShell prompt.** It **must** start with `(.venv)`. If it does not, return to Step 4 and re-run `.\.venv\Scripts\Activate.ps1` first. This is the single biggest cause of the "Streamlit is not installed" error later.

Then, in the `(.venv)` PowerShell:

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

**Check — verifies that the critical packages actually landed in the venv:**

```powershell
python -c "import streamlit, llama_cpp, chromadb, doc_analyzer; print('All 4 packages installed')"
```

You should see `All 4 packages installed`. If instead you see `ModuleNotFoundError: No module named 'streamlit'` (or `llama_cpp`, or `chromadb`), the install did not complete inside the venv — see the **"Streamlit / a package is not installed"** row in Troubleshooting below.

### Step 6 — Download a GGUF model

COEBOT needs a language model file (5–17 GB) to work. This file is too large for the GitHub repo, so you download it separately from Hugging Face. The links below are **direct downloads** — clicking one starts the download immediately in your browser; you don't need to click around on Hugging Face's site.

#### For 16 GB RAM laptops (recommended default)

**Model:** `Qwen3.5-9B-UD-Q4_K_XL.gguf` — 5.56 GB

1. Click this direct-download link:
   **https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-UD-Q4_K_XL.gguf?download=true**

   Your browser starts downloading immediately. Chrome/Edge may show a "large file" prompt at the bottom of the window — click **Keep** or **Save**. If the link instead opens a Hugging Face page (rare, depends on the browser), find the **⬇ download** button on that page and click it.

2. Wait for the download to finish. It lands in your **Downloads** folder — usually `C:\Users\<yourname>\Downloads\Qwen3.5-9B-UD-Q4_K_XL.gguf`. Expect **10–30 minutes** on a home connection.

3. Move the file into COEBOT's `models\` folder. **Fastest way — in PowerShell:**

   ```powershell
   move $HOME\Downloads\Qwen3.5-9B-UD-Q4_K_XL.gguf $HOME\Documents\COEBOT\models\
   ```

   Or by hand: open File Explorer, go to `C:\Users\<yourname>\Documents\COEBOT\models\` in one window and `C:\Users\<yourname>\Downloads\` in another, then drag the `.gguf` file from Downloads into the `models\` window.

#### For 32 GB+ RAM machines (higher-quality but heavier)

**Model:** `Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf` — 17.28 GB

1. Direct-download link:
   **https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/resolve/main/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf?download=true**

2. Same routine as above — the file lands in `Downloads\`, then:

   ```powershell
   move $HOME\Downloads\Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf $HOME\Documents\COEBOT\models\
   ```

**Check:** In PowerShell, from inside the COEBOT folder, type:

```powershell
ls models\*.gguf
```

You should see one line naming your `.gguf` file with its size. If the output is empty, the model is not in the right place — the file must be **directly inside `models\`**, not in a subfolder like `models\Qwen3.5-9B-GGUF\`. If you accidentally created a subfolder, move the `.gguf` up one level.

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
| **"Streamlit is not installed"** (or `ModuleNotFoundError: No module named 'streamlit'`, `'llama_cpp'`, `'chromadb'`, etc.) | pip installed into the wrong Python because the `(.venv)` prompt marker was missing when you ran Step 5 — most commonly caused by opening a new PowerShell window mid-flow, or skipping `Activate.ps1` | Reactivate the venv and re-run Step 5. In PowerShell: `cd $HOME\Documents\COEBOT` → `.\.venv\Scripts\Activate.ps1` → confirm the prompt now shows `(.venv)` → then paste Step 5's `pip install --extra-index-url ...` line again. The install is idempotent — it just fills in whatever is missing. Finish with the Step 5 check to confirm |
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
