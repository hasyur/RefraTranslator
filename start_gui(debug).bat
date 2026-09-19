@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title RefraTranslator Debug
cd /d "%~dp0"
set "LAUNCHER_PYTHON=.venv\Scripts\python.exe"

if not exist "%LAUNCHER_PYTHON%" (
  echo Error: project virtual environment not found.
  echo Double-click install.bat first.
  pause
  exit /b 1
)

"%LAUNCHER_PYTHON%" -s -X utf8 -m game_screen_translator.gui_entry %*
set "launcher_exit=%ERRORLEVEL%"
echo.
if not "%launcher_exit%"=="0" (
  echo RefraTranslator exited with code %launcher_exit%.
  echo Diagnostic log: "%CD%\output\launcher.log"
) else (
  echo RefraTranslator exited normally.
)
echo.
pause
exit /b %launcher_exit%
