@echo off
REM Launch changedetector with no console window (headless).
REM Edit the path below if your project lives elsewhere.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m changedetector run --config "%~dp0config.yaml"
