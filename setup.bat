@echo off
REM ============================================================================
REM  setup.bat - one-click launcher for setup.ps1 (the DMbot installer).
REM
REM  Double-click this. It runs setup.ps1 with -ExecutionPolicy Bypass so you do
REM  NOT have to change any Windows script-execution settings first (that snag is
REM  the #1 reason setup "won't run" on a fresh machine).
REM
REM  Any arguments are passed straight through, e.g.:
REM     setup.bat -SkipOllama
REM     setup.bat -SkipPrefetch
REM     setup.bat -StartBot
REM ============================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
echo.
pause
