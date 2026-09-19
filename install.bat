@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title RefraTranslator Installer
cd /d "%~dp0"

echo RefraTranslator isolated environment installer
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" -WithGui
set "install_exit=%ERRORLEVEL%"
if not "%install_exit%"=="0" goto :install_failed

echo.
echo Installation completed successfully.
echo Double-click start_gui.bat to launch RefraTranslator.
echo.
pause
exit /b 0

:install_failed
echo.
echo Error: installation failed ^(exit code %install_exit%^).
echo Fix the error shown above, then run install.bat again.
echo.
pause
exit /b %install_exit%
