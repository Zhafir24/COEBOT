# ============================================================
# COEBOT launcher (PowerShell)
# Called by start_coebot.bat / Desktop shortcut.
# Starts the COEBOT server (uvicorn + the custom web UI) in this
# terminal and opens the browser automatically once it is ready.
# ============================================================

$ErrorActionPreference = "Stop"

# Resolve project root (this script's own folder).
$ProjectRoot = $PSScriptRoot
$VenvPython  = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Url         = "http://127.0.0.1/"

if (-not (Test-Path $VenvPython)) {
    Write-Host ""
    Write-Host "ERROR: Virtual environment not found at $VenvPython" -ForegroundColor Red
    Write-Host "Run once to set up: py -3.12 -m venv .venv ; .\.venv\Scripts\pip install -e ." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

# Verify critical packages exist inside the venv BEFORE launching, so
# a broken install shows a clear message instead of a traceback.
& $VenvPython -c "import starlette, uvicorn, llama_cpp, chromadb, doc_analyzer" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: COEBOT dependencies are not installed in the virtual environment." -ForegroundColor Red
    Write-Host "Fix: activate the venv and run:" -ForegroundColor Yellow
    Write-Host "  pip install --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu -e ." -ForegroundColor White
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

# Venv activation semantics for any child processes.
$env:PATH = "$ProjectRoot\.venv\Scripts;" + $env:PATH
$env:VIRTUAL_ENV = "$ProjectRoot\.venv"

Write-Host ""
Write-Host "Starting COEBOT..." -ForegroundColor Cyan
Write-Host "Browser will open at $Url in a few seconds." -ForegroundColor DarkGray
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

# Open the browser once the server is up.
Start-Job -ScriptBlock {
    param($u)
    Start-Sleep -Seconds 3
    Start-Process $u
} -ArgumentList $Url | Out-Null

& $VenvPython -m uvicorn doc_analyzer.server:app --host 127.0.0.1 --port 80 --app-dir "$ProjectRoot\src"
