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
