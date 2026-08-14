@echo off
setlocal
title RefraTranslator
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Error: project virtual environment not found.
  echo Run: powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 -WithOcr -WithGui
  pause
  exit /b 1
)
if not exist "config.toml" (
  if not exist "config.example.toml" (
    echo Error: config.example.toml not found.
    pause
    exit /b 1
  )
  copy /y "config.example.toml" "config.toml" >nul
  if errorlevel 1 (
    echo Error: failed to create config.toml.
    pause
    exit /b 1
  )
  echo Created config.toml from the public template.
)
".venv\Scripts\python.exe" -m game_screen_translator --config config.toml gui
if errorlevel 1 pause
