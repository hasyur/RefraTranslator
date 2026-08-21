@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title RefraTranslator Updater
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
set "update_exit=%ERRORLEVEL%"
if not "%update_exit%"=="0" goto :update_failed

echo.
echo RefraTranslator update completed successfully.
echo.
pause
exit /b 0

:update_failed
echo.
echo Error: update failed ^(exit code %update_exit%^).
echo No local configuration, profile, cache, or virtual environment was removed.
echo.
pause
exit /b %update_exit%
