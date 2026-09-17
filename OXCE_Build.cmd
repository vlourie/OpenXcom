@echo off
rem OXCE HD build: no argument = window with buttons; or: OXCE_Build.cmd exe | mod | both
if "%~1"=="" (
  start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "%~dp0tools\build\BuildGUI.ps1"
  exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build\build.ps1" -Target %1
pause
