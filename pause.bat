@echo off
REM Suppress alerts while you work. Double-click or run from a terminal.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m changedetector pause --config "%~dp0config.yaml"
timeout /t 2 >nul
