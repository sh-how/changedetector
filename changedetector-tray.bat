@echo off
REM Launch the changedetector system-tray controller (no console window).
REM Double-click this, then control everything from the tray icon.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m changedetector tray --config "%~dp0config.yaml"
