@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title RefraTranslator
cd /d "%~dp0"
set "VENV_PYTHON=.venv\Scripts\python.exe"
set "LOG_DIR=output"
set "LOG_FILE=%LOG_DIR%\launcher.log"
set "PYTHONFAULTHANDLER=1"
set "PYTHONUTF8=1"
set "PYTHONNOUSERSITE=1"
set "QT_QPA_PLATFORM=windows"
set "QT_PLUGIN_PATH="
set "QT_QPA_PLATFORM_PLUGIN_PATH="

if not exist "%VENV_PYTHON%" (
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

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%LOG_DIR%" (
  echo Error: failed to create the output directory.
  pause
  exit /b 1
)

> "%LOG_FILE%" echo RefraTranslator launcher diagnostics
>> "%LOG_FILE%" echo Working directory: "%CD%"

echo Checking the isolated Python and GUI dependencies...
"%VENV_PYTHON%" -u -X faulthandler -c "import sys; print('Python:', sys.version, flush=True); print('Executable:', sys.executable, flush=True); import PySide6; print('PySide6:', PySide6.__version__, flush=True); from PySide6.QtWidgets import QApplication; print('QtWidgets import: OK', flush=True); app = QApplication([]); print('Qt platform:', app.platformName(), flush=True); import game_screen_translator.gui.launcher; print('GUI module import: OK', flush=True)" >> "%LOG_FILE%" 2>&1
set "launcher_exit=%ERRORLEVEL%"
if not "%launcher_exit%"=="0" goto :launch_failed

echo Starting RefraTranslator GUI...
echo Diagnostic log: "%CD%\%LOG_FILE%"
"%VENV_PYTHON%" -u -X faulthandler -m game_screen_translator --config config.toml gui %* >> "%LOG_FILE%" 2>&1
set "launcher_exit=%ERRORLEVEL%"
if not "%launcher_exit%"=="0" goto :launch_failed
exit /b 0

:launch_failed
echo.
echo Error: RefraTranslator GUI failed to start ^(exit code %launcher_exit%^).
echo Diagnostic log: "%CD%\%LOG_FILE%"
echo.
type "%LOG_FILE%"
echo.
pause
exit /b %launcher_exit%
