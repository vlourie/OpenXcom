@echo off
rem Triage page: original | generation 1 | generation 2. Opens http://127.0.0.1:8765
cd /d "%~dp0..\..\.."
set PYTHONIOENCODING=utf-8
start "" http://127.0.0.1:8765/
"E:\train\.venv-train\Scripts\python.exe" tools\hdart\triage\server.py
