# Настройка рабочей машины

Что нужно, чтобы на новой машине собрать игру, выпуск и арт. Порядок — сверху вниз: без первого
раздела не работает ничего, остальные нужны только для своей части работы.

Пути ниже — как на основной машине (`E:\OpenXCom`, модели в `E:\models`, ключи на `D:`). Пути
сборки и выпуска в `tools\build\build_config.json` и `Выпуск\release_config.json` записаны от
корня репозитория, поэтому на второй машине их править не нужно — только то, что лежит вне
репозитория (`MsysBin`, `Key`, `Pub`, `Repo`).

## 1. Движок: MSYS2 + MinGW + Ninja

1. Поставить MSYS2 в `C:\msys64` (https://www.msys2.org).
2. В оболочке MSYS2 MINGW64:
   ```sh
   pacman -S --needed mingw-w64-x86_64-gcc mingw-w64-x86_64-cmake mingw-w64-x86_64-ninja mingw-w64-x86_64-pkgconf \
     mingw-w64-x86_64-SDL mingw-w64-x86_64-SDL_image mingw-w64-x86_64-SDL_mixer mingw-w64-x86_64-SDL_gfx \
     mingw-w64-x86_64-zlib mingw-w64-x86_64-yaml-cpp
   ```
3. MSYS2 **не** добавлять в постоянный PATH: он перебивает системные python, git и cc (грабли R-002).
   Только в сессию:
   ```powershell
   $env:Path = "C:\msys64\mingw64\bin;$env:Path"
   cd build-release
   cmake -G Ninja -DCMAKE_BUILD_TYPE=Release ..   # один раз и при правке CMakeLists
   ninja
   ```
   Готовый `build-release\bin\openxcom.exe` запускается только с этим PATH — ему нужны DLL MinGW.
4. Игра для проверки — установка X-Piratez в `Пиратки\Dioxine_XPiratez` (в гит не идёт, копируется
   с основной машины целиком). `bin\UFO` — оригинальные данные DOS-версии.

Проверка: `ninja` без ошибок, дамп Ctrl+F8 и `python tools\hdtest_compare.py` (см. `tools\hdtest_README.md`).

## 2. Упаковка выпуска

| Программа | Где её ищет сборка | Зачем |
|---|---|---|
| Enigma Virtual Box | `Program Files (x86)\Enigma Virtual Box\enigmavbconsole.exe` или `EnigmaConsole` | DLL внутрь exe |
| 7-Zip | `Program Files\7-Zip\7z.exe` или `SevenZip` | архивы `dist\OXCE-HD_*.zip` |
| .NET SDK 10 (`portal\global.json`) | `dotnet` в PATH | лаунчер, `xp-release`, портал |
| Visual Studio или Build Tools с C++ | `vswhere` (`portal\publish.ps1` находит сам) | NativeAOT лаунчера линкуется MSVC |

Сборка — `Выпуск\OXCE_Build.cmd` (или `tools\build\build.ps1 -Target Both`), выпуск —
`Выпуск\OXCE_Release.cmd`. Выпуску нужен диск `D:` с ключом `D:\keys\xp-prod\release.key` и
хранилищем `D:\xp-repo`; без диска он останавливается с понятной ошибкой. Подробно — `Выпуск\README.md`.

Сервер сайта (Docker, PostgreSQL, Caddy) ставится на станции, не здесь: `portal\deploy\README.md`.

## 3. Арт: видеокарта, два окружения, модели

Генерация живёт в своих venv — в системном `py -3` нет diffusers. Нужна карта NVIDIA 50-й серии
или новее и PyTorch под CUDA 12.8 (сборки под cu121 на Blackwell не заводятся).

| Окружение | Ставит | Для чего |
|---|---|---|
| `tools\hdart\.venv` | `tools\hdart\setup_gen.ps1`, поверх — `setup_photo.ps1` | SDXL + ControlNet (`gen_hd.py`, `map_paint.py`), `photo_ui.py` |
| `tools\hdart\.venv-qwen21` | `tools\hdart\setup_qwen21.ps1` | Qwen-Image-2.1 (`--painter qwen21`, курсоры, эффекты) |
| `E:\train` (вне репозитория) | `tools\hdart\setup_train.ps1` | обучение LoRA (DiffSynth-Studio) |

Модели качаются этими же скриптами в `E:\models` (ключ `-Models`); скачивание возобновляемое.

Всё, что грузит модель на карту, запускается только через очередь:
```powershell
py -3 tools\gpuq.py add --name <имя> -- tools\hdart\.venv\Scripts\python.exe tools\hdart\<скрипт>.py ...
py -3 tools\gpuq.py list
```
Прямой запуск останавливает хук `gpu-guard`; список скриптов с моделью — `tools\gpu_scripts.txt`.

## 4. Инструменты агентов

```powershell
.\tools\setup_workstation.ps1          # -WhatIfOnly - посмотреть, -SkipModel - без 18 ГБ модели
```

| Программа | Зачем | Без неё |
|---|---|---|
| **Python 3** (`py -3`) | `rake.py`, `index_project.py`, `hdtest_compare.py`, перепись | не работает ни карта, ни грабли, ни сверка кадров |
| **universal-ctags** | `.index\symbols.tsv` | карта проекта пустая, агенты читают файлы целиком |
| **clangd** (LLVM), **doxygen + graphviz** | точный индекс C++ и граф вызовов | ctags путает перегрузки |
| **ImageMagick**, **oxipng** | ресайз, палитра, сжатие PNG | ассеты тяжелее, `asset-smith` бессилен |
| **Ollama + qwen3.8:27b** | черновые описания модулей (`.index\files.md`) | остальное работает |

Локальная модель пишет только смысл: имена, сигнатуры и строки берутся из `.index\symbols.tsv`,
27B уверенно выдумывает имена, которых в коде нет. В запросах к Ollama задавать `num_ctx`
(грабли R-064), модель выгружает очередь `gpuq`.

Проверка:
```powershell
python tools\index_project.py
python tools\rake.py list
```
Первая команда отчитывается числом файлов и символов; ноль символов — не установлен ctags.
