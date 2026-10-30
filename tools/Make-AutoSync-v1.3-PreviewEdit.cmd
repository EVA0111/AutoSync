@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0resources\engine\autosync.py" (
  echo This helper must be placed inside your existing AutoSync v1.3 portable folder.
  echo No files were changed.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Make-AutoSync-v1.3-PreviewEdit.ps1" -V13Directory "%~dp0."
if errorlevel 1 (
  echo.
  echo Merge failed. The original v1.3 installation is unchanged.
) else (
  echo.
  echo New v1.3 Preview and Edit portable folder and ZIP created beside the original.
)
pause
