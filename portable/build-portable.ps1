# ============================================================
# COEBOT Portable Edition build script
#
# Reproduces the exact procedure that built the released
# COEBOT-v1.0.0-windows-portable.zip:
#   1. Download the Windows embeddable Python (self-contained)
#   2. Enable site-packages + add ..\src to the path file
#   3. Bootstrap pip, install all runtime deps (prebuilt wheels)
#   4. Copy app source + assets from this repository
#   5. Pre-download the embedding model into the bundle
#   6. Add the portable launcher + readme from this folder
#   7. Smoke-test, then zip
#
# Run from the repository root:
#   .\portable\build-portable.ps1
# Output: .\dist\COEBOT-<version>-windows-portable.zip
# ============================================================

$ErrorActionPreference = "Stop"

$PYTHON_EMBED_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$WHEEL_INDEX      = "https://abetlen.github.io/llama-cpp-python/whl/cpu"
$VERSION          = "v1.1.0"

$RepoRoot = Split-Path $PSScriptRoot -Parent
$Work     = Join-Path $RepoRoot "dist\portable-build"
$Bundle   = Join-Path $Work "COEBOT"

Write-Host "== 1/7 Preparing workspace ==" -ForegroundColor Cyan
if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
New-Item -ItemType Directory -Force "$Bundle\python" | Out-Null

Write-Host "== 2/7 Embeddable Python ==" -ForegroundColor Cyan
$embedZip = Join-Path $Work "python-embed.zip"
Invoke-WebRequest -Uri $PYTHON_EMBED_URL -OutFile $embedZip
Expand-Archive -Path $embedZip -DestinationPath "$Bundle\python" -Force
# Enable site-packages and expose ..\src (PYTHONPATH is ignored when a
# ._pth file exists, so the source path must live in the ._pth itself).
Set-Content -Path "$Bundle\python\python312._pth" -Encoding ascii -Value @(
    "python312.zip", ".", "..\src", "import site"
)

Write-Host "== 3/7 pip + dependencies ==" -ForegroundColor Cyan
$getPip = Join-Path $Work "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
& "$Bundle\python\python.exe" $getPip --no-warn-script-location
# Install ONLY the dependency list from pyproject.toml. The project
# itself is not pip-installed (hatchling cannot build inside the
# embeddable Python); the app runs from src\ via the ._pth entry.
$reqs = & "$Bundle\python\python.exe" -c "import tomllib; print('\n'.join(tomllib.loads(open(r'$RepoRoot\pyproject.toml','rb').read().decode())['project']['dependencies']))"
$reqFile = Join-Path $Work "requirements.txt"
$reqs | Out-File -FilePath $reqFile -Encoding ascii
& "$Bundle\python\python.exe" -m pip install --no-warn-script-location --extra-index-url $WHEEL_INDEX -r $reqFile
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "== 4/7 App source + assets ==" -ForegroundColor Cyan
Copy-Item -Recurse "$RepoRoot\src"        "$Bundle\src"
Copy-Item -Recurse "$RepoRoot\static"     "$Bundle\static"
Copy-Item -Recurse "$RepoRoot\.streamlit" "$Bundle\.streamlit"
New-Item -ItemType Directory -Force "$Bundle\models", "$Bundle\data\documents", "$Bundle\data\chroma_db" | Out-Null
Copy-Item "$RepoRoot\models\README.md" "$Bundle\models\README.md"
Copy-Item "$RepoRoot\.env.example"     "$Bundle\.env"
Copy-Item "$RepoRoot\LICENSE"          "$Bundle\LICENSE"
Copy-Item "$RepoRoot\README.md"        "$Bundle\README-full.md"

Write-Host "== 5/7 Pre-download embedding model ==" -ForegroundColor Cyan
$env:HF_HOME = "$Bundle\data\hf-cache"
& "$Bundle\python\python.exe" -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); print('embedding cached:', m.encode(['test']).shape)"
if ($LASTEXITCODE -ne 0) { throw "embedding prefetch failed" }

Write-Host "== 6/7 Portable launcher + readme ==" -ForegroundColor Cyan
Copy-Item "$PSScriptRoot\start_coebot.bat" "$Bundle\start_coebot.bat"
Copy-Item "$PSScriptRoot\BACA-DULU (READ-ME-FIRST).txt" "$Bundle\BACA-DULU (READ-ME-FIRST).txt"

Write-Host "== 7/7 Smoke test + zip ==" -ForegroundColor Cyan
& "$Bundle\python\python.exe" -c "import streamlit, llama_cpp, chromadb, doc_analyzer; print('imports OK')"
if ($LASTEXITCODE -ne 0) { throw "smoke test failed" }
$zip = Join-Path $RepoRoot "dist\COEBOT-$VERSION-windows-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
# bsdtar (ships with Windows 10+) handles zip64 for 55k+ entries.
& "$env:SystemRoot\System32\tar.exe" -a -cf $zip -C (Split-Path $Bundle -Parent) "COEBOT"
Get-FileHash $zip -Algorithm SHA256 | Format-List
Write-Host "DONE: $zip" -ForegroundColor Green
Write-Host "Upload it to a GitHub release and publish the SHA-256 above in the notes."
