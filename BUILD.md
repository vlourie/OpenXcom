# Сборка openxcom.exe (MuRuCoN build)

Инструкция по сборке исполняемого файла и упаковке его в единый portable-exe.

---

## Требования

| Инструмент | Установка |
|---|---|
| [MSYS2](https://www.msys2.org/) | Установить в `C:\msys64` |
| MinGW-w64 GCC 16 | `pacman -S mingw-w64-x86_64-gcc` в MSYS2 |
| CMake | `pacman -S mingw-w64-x86_64-cmake` |
| Ninja | `pacman -S mingw-w64-x86_64-ninja` |
| [Enigma Virtual Box](https://enigmaprotector.com/en/aboutvb.html) | для упаковки DLL в exe |

---

## Сборка

### 1. Добавить MSYS2 в PATH (PowerShell)

```powershell
$env:PATH = "C:\msys64\mingw64\bin;C:\msys64\usr\bin;" + $env:PATH
```

> Это нужно делать **каждый раз** в новой сессии PowerShell.  
> Без этого компилятор запускается, но падает без вывода ошибок (не находит свои DLL).

### 2. Создать папку сборки и сконфигурировать CMake

```powershell
cd F:\ChatGPT\OpenXcom
cmake -B build-release -G Ninja `
  -DCMAKE_BUILD_TYPE=Release `
  -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/c++.exe `
  -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/gcc.exe
```

> Делается **один раз**. Повторять только если менялись CMakeLists.txt.

### 3. Собрать

```powershell
cd F:\ChatGPT\OpenXcom\build-release
ninja -j4
```

Готовый файл: `build-release\bin\openxcom.exe`

---

## Упаковка DLL через Enigma Virtual Box

После сборки `openxcom.exe` **не является portable** — он требует наличия рядом нескольких DLL из MSYS2/MinGW.  
Enigma Virtual Box запаковывает их внутрь exe.

### Настройка проекта

Файл проекта: `build-release\bin\openxcom.evb`

| Поле | Значение |
|---|---|
| Input | `build-release\bin\openxcom.exe` |
| Output | `build-release\bin\openxcom_boxed.exe` |

### Список DLL (вкладка Files → %DEFAULT FOLDER%)

| DLL | Назначение |
|---|---|
| `libFLAC.dll` | Декодирование FLAC-аудио |
| `libogg-0.dll` | Ogg-контейнер |
| `libwinpthread-1.dll` | Потоки MinGW |
| `libvorbis-0.dll` | Vorbis-аудио |
| `libvorbisfile-3.dll` | Vorbis file API |

DLL лежат в `C:\msys64\mingw64\bin\`.

### Процесс

1. Открыть Enigma Virtual Box
2. `File → Open` → выбрать `openxcom.evb`
3. Нажать **Process**
4. Готовый файл: `build-release\bin\openxcom_boxed.exe`
5. Переименовать в `openxcom_MuRuCoN.exe` для релиза

---

## Публикация релиза на GitHub

```powershell
# Переименовать упакованный exe
Copy-Item build-release\bin\openxcom_boxed.exe build-release\bin\openxcom_MuRuCoN.exe

# Создать тег и релиз
git tag v8.6
git push origin v8.6
gh release create v8.6 build-release\bin\openxcom_MuRuCoN.exe `
  --title "v8.6 MuRuCoN" `
  --notes "Сборка v8.6. Portable exe — DLL внутри, ничего рядом класть не нужно."
```

---

## Структура веток

| Ветка | Назначение |
|---|---|
| `community_build_local` | Рабочая ветка с патчами MuRuCoN |
| `main` | Чистый upstream от MeridianOXC |

Патчи коммитятся в `community_build_local`, upstream тянется через `git fetch upstream`.
