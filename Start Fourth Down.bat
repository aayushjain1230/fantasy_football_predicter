@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 (
  echo.
  echo Fourth Down could not start. Read the error above, then press any key.
  pause >nul
)

