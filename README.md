# COEBOT

Fully-local document analysis chatbot. Runs Qwen3 (or any GGUF chat model) in-process via `llama-cpp-python`, retrieves context from your own PDFs, DOCXs, and XLSXs, and answers with page-level citations. No API calls. No telemetry. Air-gap deployable.

## Prerequisites

Before you start, you need three things installed:

- **Python 3.12 or 3.13** — https://www.python.org/downloads/
- **Git** — https://git-scm.com/download/win
- **A GGUF chat-tuned model file** — downloaded from Hugging Face (see Step 6 below)

Windows 10 or 11 already ships with everything else COEBOT needs (PowerShell 5.1+, Visual C++ Redistributable, and AVX2 CPU support on any 2015+ machine).

## Installation — step by step

Follow these seven steps in order. Each includes a **check** you can run to verify that step worked, and a note for the most common problem if it didn't.

### Step 1 — Install Python

1. Open https://www.python.org/downloads/ and click the big yellow **Download Python 3.12.x** button.
2. Run the installer you just downloaded.
3. **CRITICAL:** On the very first installer screen, at the bottom, tick the checkbox **"Add python.exe to PATH"**. If you skip this, nothing later will work.
4. Click **Install Now** and wait for it to finish.

**Check:** Press <kbd>Win</kbd> + <kbd>R</kbd>, type `powershell`, press Enter. In the blue window that opens, type `py --version` and press Enter. You should see something like `Python 3.12.7`.

**If you see "'py' is not recognized":** You forgot the PATH checkbox. Uninstall Python from **Settings → Apps**, then reinstall from scratch with the box ticked.

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
pip install -e .
copy .env.example .env
```

The first command downloads and installs about 200 Python packages. It takes **2–5 minutes** depending on your internet speed. Watch the progress; when it finishes you'll see `Successfully installed doc_analyzer-0.1.0 ...`.

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
| `pip install` fails with `error: Microsoft Visual C++ 14.0 or greater is required` | Missing MSVC build tools (rare on Windows 10/11) | Install Visual Studio Build Tools from https://visualstudio.microsoft.com/visual-cpp-build-tools/ |
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
