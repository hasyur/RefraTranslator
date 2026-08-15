@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title RefraTranslator OCR Test Scenes
cd /d "%~dp0"
set "VENV_PYTHON=.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
set "PYTHONNOUSERSITE=1"
set "QT_QPA_PLATFORM=windows"
set "QT_PLUGIN_PATH="
set "QT_QPA_PLATFORM_PLUGIN_PATH="

if not exist "%VENV_PYTHON%" (
  echo Error: project virtual environment not found.
  echo Run: powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 -WithGui
  pause
  exit /b 1
)

"%VENV_PYTHON%" -u ".\tests\manual\animated_ocr_scenes.py" %*
set "scene_exit=%ERRORLEVEL%"
if not "%scene_exit%"=="0" (
  echo.
  echo Error: OCR test scenes exited unexpectedly ^(exit code %scene_exit%^).
  pause
)
exit /b %scene_exit%
