@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "LAUNCHER_PYTHON=.venv\Scripts\pythonw.exe"

if not exist "%LAUNCHER_PYTHON%" (
  echo Error: project virtual environment not found.
  echo Double-click install.bat first.
  pause
  exit /b 1
)

start "" /b "%LAUNCHER_PYTHON%" -s -X utf8 -m game_screen_translator.gui_entry %* >nul 2>&1
if errorlevel 1 (
  echo Error: failed to start RefraTranslator.
  pause
  exit /b 1
)
exit /b 0
