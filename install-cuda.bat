@echo off
rem ============================================================
rem COEBOT CUDA installer - double-click on a PC with an NVIDIA GPU.
rem
rem This launcher self-elevates: if not already running as
rem Administrator, it re-launches itself via UAC so that the
rem PowerShell script can enable Windows Long Path support
rem (required - llama-cpp-python's vendored source tree exceeds
rem the 260-char path limit).
rem ============================================================

rem --- Are we already elevated? ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

rem --- Elevated: run the actual installer ---
rem cd into the script's own folder so $PSScriptRoot / relative
rem paths resolve correctly even though UAC starts us in system32.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-cuda.ps1"