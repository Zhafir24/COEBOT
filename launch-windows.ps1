# ============================================================
# COEBOT launcher (PowerShell)
# Called by start_coebot.bat / Desktop shortcut.
# Starts Streamlit in this terminal and opens the browser
# automatically once the server is ready.
# ============================================================

$ErrorActionPreference = "Stop"

# Resolve project root (this script's own folder).
$ProjectRoot = $PSScriptRoot
$VenvPython  = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$AppScript   = Join-Path $ProjectRoot "src\doc_analyzer\ui\app.py"
$Url         = "http://127.0.0.1/"

if (-not (Test-Path $VenvPython)) {
    Write-Host ""
    Write-Host "ERROR: Virtual environment not found at $VenvPython" -ForegroundColor Red
    Write-Host "Run once to set up: py -3.12 -m venv .venv ; .\.venv\Scripts\pip install -e ." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

# Verify critical packages are installed inside the venv BEFORE
# launching Streamlit. If pip install -e . was skipped or failed —
# or was run in the wrong Python — the app crashes with a cryptic
# "No module named streamlit" or "No module named 'doc_analyzer'"
# traceback that leaves users guessing. Catching it here shows a
# copy-paste recovery command instead.
$depCheck = & $VenvPython -c "import streamlit, llama_cpp, chromadb, doc_analyzer" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: COEBOT dependencies are not installed in the virtual environment." -ForegroundColor Red
    Write-Host "       Missing at least one of: streamlit, llama_cpp, chromadb, doc_analyzer" -ForegroundColor Red
    Write-Host ""
    Write-Host "This means Step 5 of the install (pip install -e .) either did not run," -ForegroundColor Yellow
    Write-Host "did not finish successfully, or ran against system-wide Python instead" -ForegroundColor Yellow
    Write-Host "of the .venv (the (.venv) prompt marker was missing at the time)." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Fix — copy and paste these four commands into PowerShell, in order:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  cd `"$ProjectRoot`"" -ForegroundColor White
    Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host "  pip install --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu -e ." -ForegroundColor White
    Write-Host "  python -c `"import streamlit, llama_cpp, chromadb, doc_analyzer; print('All packages OK')`"" -ForegroundColor White
    Write-Host ""
    Write-Host "The last command should print 'All packages OK'. If it prints a" -ForegroundColor DarkGray
    Write-Host "ModuleNotFoundError instead, share that message with whoever set up COEBOT." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Full step-by-step guide: see README.md, section 'Installation — step by step'." -ForegroundColor DarkGray
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "Starting COEBOT..." -ForegroundColor Cyan
Write-Host "Browser will open at $Url in a few seconds." -ForegroundColor DarkGray
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

# Open the browser after a 4-second delay so Streamlit has time to
# bind to port 80. Runs in a hidden background job so the main
# Streamlit process keeps the terminal foreground.
Start-Job -ScriptBlock {
    param($u)
    Start-Sleep -Seconds 4
    Start-Process $u
} -ArgumentList $Url | Out-Null

& $VenvPython -m streamlit run $AppScript --server.headless true
