@echo off
setlocal
cd /d "%~dp0..\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-portable.ps1" %*
if errorlevel 1 (echo Build failed. See the error above.) else (echo Portable ZIP created under dist.)
pause
