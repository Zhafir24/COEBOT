# Dev helper script.
# Run with: .\scripts\dev.ps1 <command>
#
# Commands:
#   check    Run lint, format check, type check
#   format   Run formatter
#   test     Run unit tests with coverage
#   test-all Run all tests including integration (requires Ollama running)
#   clean    Remove build artifacts and caches

param(
    [Parameter(Position = 0)]
    [ValidateSet("check", "format", "test", "test-all", "clean")]
    [string]$Command = "check"
)

$ErrorActionPreference = "Stop"
$VenvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $VenvPython. Run 'py -3.12 -m venv .venv' first."
    exit 1
}

function Invoke-Check {
    Write-Host "==> Ruff lint" -ForegroundColor Cyan
    & $VenvPython -m ruff check src tests
    if ($LASTEXITCODE -ne 0) { exit 1 }

    Write-Host "==> Ruff format check" -ForegroundColor Cyan
    & $VenvPython -m ruff format --check src tests
    if ($LASTEXITCODE -ne 0) { exit 1 }

    Write-Host "==> MyPy type check" -ForegroundColor Cyan
    & $VenvPython -m mypy src
    if ($LASTEXITCODE -ne 0) { exit 1 }

    Write-Host "All checks passed." -ForegroundColor Green
}

function Invoke-Format {
    Write-Host "==> Ruff format" -ForegroundColor Cyan
    & $VenvPython -m ruff format src tests
    Write-Host "==> Ruff fix" -ForegroundColor Cyan
    & $VenvPython -m ruff check --fix src tests
}

function Invoke-Test {
    Write-Host "==> Pytest (unit only)" -ForegroundColor Cyan
    & $VenvPython -m pytest -m "not integration"
}

function Invoke-TestAll {
    Write-Host "==> Pytest (all)" -ForegroundColor Cyan
    & $VenvPython -m pytest
}

function Invoke-Clean {
    @(".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov", "build", "dist", ".coverage") |
        ForEach-Object {
            $p = Join-Path (Split-Path $PSScriptRoot -Parent) $_
            if (Test-Path $p) {
                Remove-Item -Recurse -Force $p
                Write-Host "removed: $_" -ForegroundColor DarkGray
            }
        }
    Get-ChildItem -Path (Split-Path $PSScriptRoot -Parent) -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Remove-Item -Recurse -Force $_.FullName
            Write-Host "removed: $($_.FullName)" -ForegroundColor DarkGray
        }
}

switch ($Command) {
    "check"     { Invoke-Check }
    "format"    { Invoke-Format }
    "test"      { Invoke-Test }
    "test-all"  { Invoke-TestAll }
    "clean"     { Invoke-Clean }
}
