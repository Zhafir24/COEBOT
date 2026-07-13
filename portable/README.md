# Portable Edition — source of truth

This folder contains everything that differs between the developer repository and the **portable ZIP** shipped on the [Releases page](https://github.com/Zhafir24/COEBOT/releases):

| File | Role |
|---|---|
| `start_coebot.bat` | The launcher at the root of the portable ZIP. Checks bundled packages (hard gate), warns-but-continues if no model is present, then starts Streamlit from the embedded Python. **Edit it here, then rebuild** — never edit it only inside a shipped ZIP. |
| `BACA-DULU (READ-ME-FIRST).txt` | Bilingual (EN/ID) end-user instructions at the root of the ZIP. |
| `build-portable.ps1` | Reproducible build: downloads embeddable Python 3.12, installs all dependencies from `pyproject.toml` as prebuilt wheels, copies the app, pre-caches the embedding model, adds the launcher, smoke-tests, zips. |

## Building a release

```powershell
# from the repository root
.\portable\build-portable.ps1
```

Output lands in `dist\COEBOT-<version>-windows-portable.zip` with its SHA-256 printed at the end. Upload the ZIP as a release asset and put the hash in the release notes.

## Design notes

- The embeddable Python ignores `PYTHONPATH` (by design of `._pth` files); the app source is exposed via a `..\src` entry in `python312._pth` instead.
- The project package itself is **not** pip-installed — `hatchling` cannot build inside the embeddable distribution. Only the dependency list is installed; `doc_analyzer` resolves from `src\`.
- The GGUF model is never bundled: GitHub caps release assets at 2 GB per file.
- `llama-cpp-python` must come from the maintainer's CPU wheel index (`--extra-index-url`) — PyPI has no binary wheels for it, and the embeddable Python cannot compile from source.
