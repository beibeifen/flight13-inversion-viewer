@echo off
title Flight 13 Viewer
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-viewer.ps1" %*
if errorlevel 1 (
  echo.
  echo Startup failed. Send the error shown above to Codex.
  pause
)
