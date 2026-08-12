@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Error: project virtual environment not found. Run bootstrap.ps1 first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m game_screen_translator --config config.toml gui
if errorlevel 1 pause
