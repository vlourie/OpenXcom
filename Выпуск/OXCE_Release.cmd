@echo off
rem OXCE HD release in one go: build both -> sign -> publish -> verify -> archive for the station.
rem   OXCE_Release.cmd                  channel from release_config.json (stable)
rem   OXCE_Release.cmd test             another channel
rem   OXCE_Release.cmd nobuild          sign what the last build left in dist\_stage
rem   OXCE_Release.cmd test nobuild
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0release.ps1" %*
pause
