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

REM Window theme: black background so the colourised transcript output reads well.
color 0F

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

echo Starting DMbot ...  (press Ctrl+C to stop)
echo Project: %CD%
echo.
uv run python -m dmbot
set EXITCODE=%ERRORLEVEL%

echo.
echo DMbot exited with code %EXITCODE%.
pause
endlocal
