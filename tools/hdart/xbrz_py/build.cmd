@echo off
rem Сборка xbrz.dll для tools/hdart (xbrz_py/__init__.py). Нужен MinGW из MSYS2 (tools\build\build_config.json, MsysBin).
set PATH=C:\msys64\mingw64\bin;%PATH%
cd /d "%~dp0"
g++ -O2 -std=c++17 -shared -static -o xbrz.dll xbrz_c.cpp ..\..\..\src\Engine\Scalers\xbrz.cpp
