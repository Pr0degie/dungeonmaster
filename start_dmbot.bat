@echo off
REM ============================================================
REM  Start DMbot (the DM brain) - Phase 2 voice receive.
REM  Works from anywhere: if this .bat sits in the repo it uses
REM  its own folder; if it was copied elsewhere (e.g. the
REM  Desktop) it falls back to the fixed repo path below.
REM ============================================================

setlocal

REM Where the bot lives. Default: the folder this .bat is in.
set "PROJECT_DIR=%~dp0"

REM If that folder is not the project (no pyproject.toml next to it), use the repo path.
if not exist "%PROJECT_DIR%pyproject.toml" set "PROJECT_DIR=C:\Users\tobo2\repos\dungeonmaster\"

cd /d "%PROJECT_DIR%"

REM UTF-8 console so the PCM-log glyphs and German text render correctly.
chcp 65001 >nul
set PYTHONUTF8=1

REM Window theme: black background, dark-green text (matches the colourised transcript
REM output; also a green baseline if ANSI ever doesn't render).
color 02

where uv >nul 2>nul
if errorlevel 1 (
    echo [!] 'uv' was not found on PATH. Install uv or open the right shell.
    echo.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [!] .env not found in %CD%.
    echo     Copy .env.example to .env and fill in DISCORD_TOKEN_DMBOT.
    echo.
    pause
    exit /b 1
)

REM ============================================================
REM  Make sure the LLM is ready BEFORE the bot needs it, so a not-running Ollama can't
REM  fail a DM turn mid-game (the "All connection attempts failed" traceback) and the first
REM  turn isn't a ~15 s cold load. Only for a LOCAL OLLAMA_HOST: a remote host (e.g. the 5080
REM  over Tailscale, ADR 002) is that machine's responsibility, so we never start one here.
REM  Read host/model from .env; fall back to the code defaults.
set "OLLAMA_HOST_CFG=http://127.0.0.1:11434"
for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"OLLAMA_HOST=" ".env"') do set "OLLAMA_HOST_CFG=%%B"
set "OLLAMA_MODEL_CFG=mistral-nemo"
for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"OLLAMA_MODEL=" ".env"') do set "OLLAMA_MODEL_CFG=%%B"

where ollama >nul 2>nul
if errorlevel 1 (
    echo [!] 'ollama' not on PATH - skipping the LLM warm-up. Make sure your LLM host is reachable.
    goto after_ollama
)
echo %OLLAMA_HOST_CFG% | findstr /i "127.0.0.1 localhost" >nul
if errorlevel 1 (
    echo [i] OLLAMA_HOST is remote ^(%OLLAMA_HOST_CFG%^) - not starting a local Ollama.
    goto after_ollama
)
echo Warming up Ollama in the background ^(daemon + model load run in parallel with the bot^)...
REM 'ollama list' boots the Windows Ollama app if it isn't already running (quick).
ollama list >nul 2>nul
REM Load the model into VRAM in the BACKGROUND so the bot launches immediately instead of waiting
REM ~15s on a cold start; the model is ready well before the first DM turn (which needs a !join +
REM speech first). Single-GPU Ollama just queues the first turn behind the warm-up if it's not done.
start "" /b cmd /c "ollama run %OLLAMA_MODEL_CFG% ok >nul 2>&1"
:after_ollama

echo Starting DMbot ...  (press Ctrl+C to stop)
echo Project: %CD%
echo.
uv run python -m dmbot
set EXITCODE=%ERRORLEVEL%

echo.
echo DMbot exited with code %EXITCODE%.
pause
endlocal
