---
name: index
description: Пересобрать карту проекта — индекс символов и файлов в .index/, по которому агенты ищут вместо чтения исходников. Использовать после крупных правок, после смены ветки и когда поиск по карте начал промахиваться.
argument-hint: "[full | describe]"
allowed-tools: Read, Glob, Grep, Bash
---

Режим: **$ARGUMENTS** (пусто — обычная пересборка)

## Обычная пересборка

!`python tools/index_project.py`

Секунды. Даёт `.index/symbols.tsv`, `.index/files.tsv`, `.index/INDEX.md`.

## `full` — плюс doxygen

Добавляет граф вызовов и наследования. Нужен `Doxyfile` в корне и установленные doxygen с graphviz. Минуты, не секунды.

```
python tools/index_project.py --full
```

## `describe` — смысловые описания локальной моделью

```
python tools/describe_modules.py --check
python tools/describe_modules.py
```

Гоняет Qwen3.8-27B через Ollama, пишет `.index/files.md` — по абзацу на файл. Долго, зато бесплатно и локально; можно оставить работать.

**Граница жёсткая:** `files.md` — это смысл, черновик. Имена, сигнатуры и номера строк берутся только из `symbols.tsv`. Если описание расходится с кодом — прав код.

## После пересборки

Покажи из `.index/INDEX.md`: сколько файлов и символов, языки, крупнейшие файлы. Если ctags не установлен — скажи прямо, что символов нет и карта неполная, и дай команду установки из `docs/SETUP.md`.
