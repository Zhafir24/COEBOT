@echo off
setlocal
cd /d "%~dp0"
title COEBOT
set "HF_HOME=%~dp0data\hf-cache"

rem ---- Sanity check: bundled packages present? (hard gate) ----
"%~dp0python\python.exe" -c "import streamlit, llama_cpp, chromadb, doc_analyzer" 2>nul
if errorlevel 1 (
  echo.
  echo ERROR: The bundled Python packages are missing or damaged.
  echo This usually means the ZIP was not fully extracted.
  echo Delete this folder, re-extract the ENTIRE ZIP, and try again.
  echo.
  pause
  exit /b 1
)

rem ---- Model check: warn but continue (UI works without a model) ----
dir /b "%~dp0models\*.gguf" >nul 2>&1
if errorlevel 1 (
  echo.
  echo ============================================================
  echo  NOTE: No AI model found yet - starting the UI anyway.
  echo ============================================================
  echo  You can explore the interface, register an account, and
  echo  upload documents. ANSWERING QUESTIONS needs the model.
  echo.
  echo  Get the model here - download starts instantly:
  echo.
  echo  https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-UD-Q4_K_XL.gguf?download=true
  echo.
  echo  Then MOVE the downloaded .gguf file into:
  echo.
  echo     %~dp0models
  echo.
  echo  and restart COEBOT.
  echo ============================================================
  echo.
)

echo.
echo Starting COEBOT...
echo The browser opens automatically in a few seconds.
echo The FIRST question after every start takes a while - the model
echo is loading into memory. That is normal.
echo.
echo To stop COEBOT: close this window.
echo.
start "" /b cmd /c "timeout /t 6 >nul & start http://127.0.0.1/"
"%~dp0python\python.exe" -m streamlit run "%~dp0src\doc_analyzer\ui\app.py" --server.headless true
pause
