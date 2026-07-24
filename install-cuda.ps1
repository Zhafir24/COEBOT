# ============================================================
# COEBOT CUDA installer — run this ON A PC WITH AN NVIDIA GPU.
#
# Rebuilds the EXACT llama-cpp-python version already installed
# in COEBOT's venv, from source, with CUDA enabled — so generation
# runs on the NVIDIA GPU and model compatibility stays identical.
#
# Why a source build: prebuilt CUDA wheels stop at v0.3.4, which
# is too old for Qwen3-family models. Building the installed
# version locally is the only way to get BOTH CUDA and the models
# COEBOT uses.
#
# Prerequisites on the target PC (checked below, with links):
#   1. NVIDIA GPU + driver            (nvidia-smi must work)
#   2. CUDA Toolkit 12.x              (nvcc must be on PATH)
#   3. Visual Studio Build Tools 2022 (C++ workload)
#
# The build takes 15–40 minutes. Before building, the current
# working install is backed up; ANY failure restores it, so
# COEBOT keeps working no matter what.
#
# Note on Windows MAX_PATH: llama-cpp-python vendors the full
# llama.cpp source tree, including a deeply-nested Svelte web UI
# (tools\ui\src\lib\components\...). Combined with pip's own temp
# folder names under %TEMP%, this can exceed Windows' 260-char
# path limit during extraction. This script redirects TEMP/TMP to
# a short path for the duration of the build to avoid that.
# ============================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$BackupDir   = Join-Path $ProjectRoot ".cuda-backup"

function Fail($msg) {
    Write-Host ""
    Write-Host "ERROR: $msg" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

# Works for both layouts: developer install (.venv) and portable ZIP
# (bundled embedded Python in the python\ folder).
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $VenvPython = Join-Path $ProjectRoot "python\python.exe"
}
if (-not (Test-Path $VenvPython)) {
    Fail "COEBOT's Python was not found (.venv\Scripts\python.exe or python\python.exe). Install COEBOT first (see README)."
}

# --- Detect the installed llama-cpp-python version --------------------
$Version = & $VenvPython -c "import importlib.metadata; print(importlib.metadata.version('llama-cpp-python'))" 2>$null
if (-not $Version) { Fail "llama-cpp-python is not installed in the venv. Install COEBOT first." }
$SitePkgs = & $VenvPython -c "import llama_cpp, os; print(os.path.dirname(os.path.dirname(llama_cpp.__file__)))" 2>$null
if (-not $SitePkgs -or -not (Test-Path $SitePkgs)) {
    Fail "Could not resolve the site-packages path for llama_cpp. Try reinstalling COEBOT's dependencies first."
}
Write-Host "Installed llama-cpp-python: $Version (will rebuild this exact version with CUDA)" -ForegroundColor Cyan

# --- 1. NVIDIA GPU + driver ------------------------------------------
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $smi) {
    Fail ("No NVIDIA driver found (nvidia-smi missing). This PC has no NVIDIA GPU " +
          "or the driver is not installed. CUDA only works on NVIDIA hardware - " +
          "on other machines COEBOT runs on CPU, which works fine.")
}
$gpuName = (& nvidia-smi --query-gpu=name --format=csv,noheader) | Select-Object -First 1
Write-Host "NVIDIA GPU detected: $gpuName" -ForegroundColor Green

# --- 2. CUDA Toolkit (nvcc) ------------------------------------------
$nvcc = Get-Command nvcc -ErrorAction SilentlyContinue
if (-not $nvcc) {
    Fail ("CUDA Toolkit not found (nvcc missing from PATH). Install CUDA Toolkit 12.x " +
          "from https://developer.nvidia.com/cuda-downloads then re-run this script.")
}
$nvccVer = (& nvcc --version | Select-String "release").ToString().Trim()
Write-Host "CUDA Toolkit found: $nvccVer" -ForegroundColor Green

# --- 3. Visual Studio Build Tools (C++ compiler) ----------------------
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$hasMsvc = $false
if (Test-Path $vswhere) {
    $inst = & $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -latest -property installationPath 2>$null
    if ($inst) { $hasMsvc = $true }
}
if (-not $hasMsvc) {
    Fail ("Visual Studio Build Tools with the C++ workload were not found. Install from " +
          "https://visualstudio.microsoft.com/visual-cpp-build-tools/ (select 'Desktop " +
          "development with C++') then re-run this script.")
}
Write-Host "Visual Studio C++ Build Tools found." -ForegroundColor Green

# --- 4. Windows Long Path support -------------------------------------
# llama-cpp-python vendors llama.cpp's full source tree, including a
# deeply-nested Svelte web UI. Some of its file paths are 170+ chars on
# their own (before even adding pip's temp-folder prefix), so nothing
# short of removing the 260-char limit entirely is reliable here.
$LongPathRegPath = "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem"
$LongPathValue = (Get-ItemProperty -Path $LongPathRegPath -Name "LongPathsEnabled" -ErrorAction SilentlyContinue).LongPathsEnabled
$IsElevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($LongPathValue -eq 1) {
    Write-Host "Windows Long Path support already enabled." -ForegroundColor Green
} elseif ($IsElevated) {
    New-ItemProperty -Path $LongPathRegPath -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force | Out-Null
    Write-Host "Enabled Windows Long Path support (was required - llama-cpp-python's" -ForegroundColor Green
    Write-Host "vendored UI source paths exceed 260 chars)." -ForegroundColor Green
} else {
    Fail (
        "llama-cpp-python's vendored source tree contains paths longer than " +
        "Windows' 260-character limit (its bundled web UI has very deeply " +
        "nested folders). Fixing this requires enabling Windows Long Path " +
        "support, which needs Administrator rights.`n`n" +
        "Right-click this script (or its .bat launcher) and choose " +
        "'Run as administrator', then try again. Or run this once in an " +
        "elevated PowerShell window, then re-run this script normally:`n`n" +
        "  New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force"
    )
}

# ============================================================
# Everything from here on touches the existing install, so it
# all runs inside one try/catch. ANY unexpected terminating
# error (locked file, permission denied, disk full, etc.) is
# caught below and triggers the same restore-and-explain path
# instead of letting the console die silently mid-operation.
# ============================================================
try {
    # --- Back up the current working install ------------------------------
    Write-Host ""
    Write-Host "Backing up the current llama-cpp-python install..." -ForegroundColor Cyan
    if (Test-Path $BackupDir) { Remove-Item -Recurse -Force $BackupDir -Confirm:$false }
    New-Item -ItemType Directory -Force $BackupDir | Out-Null
    Copy-Item -Recurse (Join-Path $SitePkgs "llama_cpp") (Join-Path $BackupDir "llama_cpp")
    $distInfo = Get-ChildItem $SitePkgs -Directory -Filter "llama_cpp_python-*.dist-info" | Select-Object -First 1
    if ($distInfo) { Copy-Item -Recurse $distInfo.FullName (Join-Path $BackupDir $distInfo.Name) }
    Write-Host "Backup saved to $BackupDir" -ForegroundColor Green

    # --- Redirect TEMP to a short path for this build (Windows MAX_PATH) --
    # llama-cpp-python's sdist contains paths 150+ chars deep on its own
    # (vendored Svelte UI components). The default %TEMP%
    # (C:\Users\<you>\AppData\Local\Temp\...) plus pip's own
    # "pip-install-XXXXXXXX\llama-cpp-python_<hash>\" folder names is
    # often enough on its own to push individual files past Windows'
    # 260-character path limit, causing an OSError mid-extraction before
    # the build even starts. Using a short root-level temp dir instead
    # buys back ~30 characters, which is normally enough headroom.
    $OrigTemp  = $env:TEMP
    $OrigTmp   = $env:TMP
    $ShortTemp = Join-Path $env:SystemDrive "cb-build-tmp"
    if (Test-Path $ShortTemp) { Remove-Item -Recurse -Force $ShortTemp -Confirm:$false -ErrorAction SilentlyContinue }
    New-Item -ItemType Directory -Force $ShortTemp | Out-Null
    $env:TEMP = $ShortTemp
    $env:TMP  = $ShortTemp
    Write-Host "Using short temp path for build (avoids Windows MAX_PATH): $ShortTemp" -ForegroundColor DarkGray

    # --- Install the build backend into the environment -------------------
    # COEBOT ships an embedded/portable Python. pip's default "build
    # isolation" creates a throwaway env, installs the build backend
    # (scikit-build-core) there, then runs the build in a subprocess -
    # but embedded Python's python*._pth restricts sys.path, so that
    # subprocess can't import scikit_build_core and fails with
    # "BackendUnavailable: Cannot import 'scikit_build_core.build'".
    # The fix is to install the build backend directly into COEBOT's
    # Python and build with --no-build-isolation (below), which uses this
    # same working environment instead of the broken isolated one.
    # Build requirement pinned to match llama-cpp-python 0.3.x's
    # pyproject.toml: scikit-build-core[pyproject]>=0.9.2.
    Write-Host "Installing build backend (scikit-build-core) into the environment..." -ForegroundColor Cyan
    & $VenvPython -m pip install --no-cache-dir "scikit-build-core[pyproject]>=0.9.2"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install the build backend (scikit-build-core). Cannot continue." }

    # With build isolation off, pip won't auto-provide cmake/ninja either.
    # scikit-build-core can fetch them itself, but installing them here is
    # more reliable and avoids depending on network access mid-build.
    Write-Host "Installing build tools (cmake, ninja) into the environment..." -ForegroundColor Cyan
    & $VenvPython -m pip install --no-cache-dir cmake ninja
    if ($LASTEXITCODE -ne 0) { throw "Failed to install cmake/ninja. Cannot continue." }

    # --- Build with CUDA --------------------------------------------------
    Write-Host ""
    Write-Host "Building llama-cpp-python $Version with CUDA. This takes 15-40 minutes..." -ForegroundColor Cyan
    Write-Host "(COEBOT must be closed while this runs.)" -ForegroundColor DarkGray
    Write-Host ""

    $env:CMAKE_ARGS = "-DGGML_CUDA=on"
    $env:FORCE_CMAKE = "1"
    # --no-build-isolation: use the env we just set up (see note above).
    # --no-deps: runtime deps (numpy, diskcache, jinja2...) are already
    #   installed; we only want to rebuild the compiled package itself.
    & $VenvPython -m pip install --force-reinstall --no-deps --no-cache-dir --no-build-isolation "llama-cpp-python==$Version"
    $buildOk = ($LASTEXITCODE -eq 0)

    # --- Verify GPU offload actually works --------------------------------
    $gpuOk = $false
    if ($buildOk) {
        & $VenvPython -c "import llama_cpp; raise SystemExit(0 if llama_cpp.llama_supports_gpu_offload() else 1)"
        $gpuOk = ($LASTEXITCODE -eq 0)
    }

    if ($buildOk -and $gpuOk) {
        Remove-Item -Recurse -Force $BackupDir -Confirm:$false
        Write-Host ""
        Write-Host "SUCCESS: llama-cpp-python $Version built with CUDA. GPU offload is active." -ForegroundColor Green
        Write-Host "Start COEBOT normally (start_coebot.bat). All model layers are offloaded" -ForegroundColor Green
        Write-Host "by default; if the model is bigger than your VRAM and fails to load, add" -ForegroundColor Green
        Write-Host "MODEL_N_GPU_LAYERS=20 (or lower) to the .env file." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "Build failed or CUDA not active - restoring the previous working install..." -ForegroundColor Yellow
        Write-Host "(Check the error above. Common causes: a compiler/CUDA toolkit" -ForegroundColor DarkGray
        Write-Host "version mismatch, or out-of-memory during compilation. The previous" -ForegroundColor DarkGray
        Write-Host "working install is being restored below either way.)" -ForegroundColor DarkGray
        $target = Join-Path $SitePkgs "llama_cpp"
        if (Test-Path $target) { Remove-Item -Recurse -Force $target -Confirm:$false }
        Get-ChildItem $SitePkgs -Directory -Filter "llama_cpp_python-*.dist-info" |
            ForEach-Object { Remove-Item -Recurse -Force $_.FullName -Confirm:$false }
        Copy-Item -Recurse (Join-Path $BackupDir "llama_cpp") $target
        Get-ChildItem $BackupDir -Directory -Filter "llama_cpp_python-*.dist-info" |
            ForEach-Object { Copy-Item -Recurse $_.FullName (Join-Path $SitePkgs $_.Name) }
        & $VenvPython -c "import llama_cpp; print('restore check: llama_cpp', llama_cpp.__version__, 'OK')"
        if ($LASTEXITCODE -eq 0) {
            Remove-Item -Recurse -Force $BackupDir -Confirm:$false
            Write-Host "Previous install restored. COEBOT works as before (CPU)." -ForegroundColor Green
        } else {
            Write-Host "Restore verification failed. Backup is kept at $BackupDir" -ForegroundColor Red
            Write-Host "Copy its contents back into $SitePkgs manually." -ForegroundColor Red
        }
    }
}
catch {
    # Catches anything unexpected above (locked files, permission denied,
    # disk full, etc.) that isn't already handled by the buildOk/gpuOk
    # branch. Best-effort restore, then always explain what happened
    # instead of letting the window close on a raw stack trace.
    Write-Host ""
    Write-Host "UNEXPECTED ERROR: $($_.Exception.Message)" -ForegroundColor Red

    $target = Join-Path $SitePkgs "llama_cpp"
    $backedUp = Test-Path (Join-Path $BackupDir "llama_cpp")
    if ($backedUp) {
        Write-Host "Attempting to restore the previous install from backup..." -ForegroundColor Yellow
        try {
            if (Test-Path $target) { Remove-Item -Recurse -Force $target -Confirm:$false }
            Get-ChildItem $SitePkgs -Directory -Filter "llama_cpp_python-*.dist-info" -ErrorAction SilentlyContinue |
                ForEach-Object { Remove-Item -Recurse -Force $_.FullName -Confirm:$false }
            Copy-Item -Recurse (Join-Path $BackupDir "llama_cpp") $target
            Get-ChildItem $BackupDir -Directory -Filter "llama_cpp_python-*.dist-info" -ErrorAction SilentlyContinue |
                ForEach-Object { Copy-Item -Recurse $_.FullName (Join-Path $SitePkgs $_.Name) }
            & $VenvPython -c "import llama_cpp; print('restore check: llama_cpp', llama_cpp.__version__, 'OK')" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Previous install restored successfully. COEBOT works as before (CPU)." -ForegroundColor Green
                Remove-Item -Recurse -Force $BackupDir -Confirm:$false -ErrorAction SilentlyContinue
            } else {
                Write-Host "Restore verification failed. Backup is kept at $BackupDir" -ForegroundColor Red
                Write-Host "Copy its contents back into $SitePkgs manually." -ForegroundColor Red
            }
        } catch {
            Write-Host "Restore attempt itself failed: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "Backup is still safe at $BackupDir - copy it back into $SitePkgs manually." -ForegroundColor Red
        }
    } else {
        Write-Host "No backup was completed before the error, so nothing was changed -" -ForegroundColor Yellow
        Write-Host "your existing llama-cpp-python install should be untouched." -ForegroundColor Yellow
    }
}
finally {
    # Always restore the real TEMP/TMP and clean up the short temp dir,
    # whether the build succeeded, failed cleanly, or hit an unexpected error.
    if ($OrigTemp) { $env:TEMP = $OrigTemp }
    if ($OrigTmp)  { $env:TMP  = $OrigTmp }
    if ($ShortTemp -and (Test-Path $ShortTemp)) {
        Remove-Item -Recurse -Force $ShortTemp -Confirm:$false -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Read-Host "Press Enter to close"