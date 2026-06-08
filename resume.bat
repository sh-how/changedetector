@echo off
REM Re-enable alerts (rebaselines on resume). Double-click or run from a terminal.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m changedetector resume --config "%~dp0config.yaml"
timeout /t 2 >nul
