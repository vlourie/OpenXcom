# Карта исправлений по аудиту 2026-09-26

Источник: `docs/research/audit-2026-09-26.md`. Здесь — порядок работ и статус.
Закрываем по одному пункту; пункт закрыт, когда выполнена его приёмка и есть коммит.
Статус: `☐` не начато, `◐` в работе, `☑` закрыто, `?` ждёт решения Vitali.

После аудита (`109e87b65`) пришли коммиты `a5169ac79` (HdFx), `195761f11`, `b92740656`:
HdFx закоммичен **без** правок §5 — они остаются в этапе 3.

**В рабочем дереве чужая незаконченная работа — не трогать, не коммитить**:
`src/Battlescape/Map.cpp` (строка `HD fx DBG flash` + автодамп на каждой вспышке),
`src/Battlescape/ProjectileFlyBState.cpp` (`hdMuzzle(getPosition(0))`), `docs/research/README.md`.

---

## Этап 0 — репозиторий в безопасности (20 мин)

| ID | Что | Приёмка | Статус |
|---|---|---|---|
| G-1 | `git rm rollback_ui_globe.ps1` — удаляет 18 живых файлов HD-интерфейса | файла нет в `git ls-files` | ☑ |
| G-2 | `git rm tools/global_transfers tools/apply_global_transfers_patch.py` — патч в `src/` с июня, копия устарела | `src/Basescape/GlobalTransfersState.cpp` на месте | ☑ |
| G-3 | `pedia_compare.html`, `pedia_prompts.html`, `intro_prompts.html` — перенести в `art/_review/`, `git rm --cached` | файлы в `art/_review/html`, в гите нет | ☑ |
| G-4 | `build_dataset_v2.py` — мёртвая копия (A-1) | ни одного импорта | ☑ |
| G-5 | `.gitignore` += `/dataset*/`, `/new mod/`, `tools/hdart/.venv*/` | `git status` их не показывает | ☑ |

## Этап 1 — механика (правило 2)

| ID | Что | Где | Приёмка | Статус |
|---|---|---|---|---|
| M-1 | вернуть обёртку `if (getSide() == FACTION_PLAYER)` у Ctrl+Shift+Del | `BattlescapeState.cpp:2876` | дифф против `441cae1b0` пуст в этом месте | ☑ `f67648cdd` |
| M-2 | битая ссылка на исследование в арке: ERROR в лог и пропуск, в сейв не писать | `GeoscapeState.cpp:3790/3802/3821`, `Mod.cpp:5130` | случайная арка пропускает пустышку, последовательная встаёт на дыре; сборка без предупреждений | ☑ `bde0ba3c3` |
| M-4 | вернуть строки из `441cae1b0`: `STR_NOT_PURCHASABLE` (en, ru), `STR_SELECT_VOICE_SET_FOR` (en, ru), `STR_RANDOM_EVENTS` (ru). Сверено: `STR_SELECT_AVATAR_FOR`, `STR_SOLDIER_BONUSES_FOR` на месте | `bin/common/Language/OXCE/` — **Святое правило**: предупредить, перенести в Пиратки, сказать | `Assert-DataSync` зелёный | ? |
| M-3 | сортировка бойцов по убыванию (`>`) — коммит `c1d6af8df` rackrossum 2023 «descending sorting», осознанный QOL | `SoldierSortUtil.h:37` | запись в DECISIONS или правка | ? |

## Этап 2 — инвариант `k = 1 IDENTICAL`

| ID | Что | Где | Статус |
|---|---|---|---|
| K-1 | режим 0 при `k = 1`: пар и вспышка в `Canvas32` через LUT палитры (побайтно как `Canvas8`) либо `Canvas8` | `Screen.cpp:112`, `Map::createCanvas`, `HdCanvas.cpp:1124-1167` | ☐ |
| K-2 | `hdTestFreeze` оставляет детерминированный пар, а не пустой | `Map.cpp:830-837` | ☐ |
| V-1 | турель (`separateTurret`/`bigTurret`) — закрыть `HD_MODE_NEAREST` | `UnitSprite` | ☐ |
| V-2 | покачивание `oxceHdHoverBob`: закрыть режимом 0, показать в опциях, заморозить в дампе | `Map.cpp:2652`, `Options.cpp:513` | ☐ |
| V-9 | пульс (`6c9ce3cb0`) — закрыть режимом 0 | `Map.cpp:1534` | ☐ |
| K-3 | эталонные дампы `k = 1` и `k = 4` с паром и вспышкой, `hdtest_compare.py` → IDENTICAL | нужен запуск игры | ☐ |

## Этап 3 — HdFx (закоммичен в `a5169ac79` без правок)

| ID | Что | Статус |
|---|---|---|
| F-1 | опция `oxceHdFx` (выключатель) | ☐ |
| F-2 | вид вспышки `none` — не рисовать клип (203 ствола) | ☐ |
| F-3 | недостижимые ветки `hit_blunt`/`whip`/`daze` — сделать достижимыми или убрать | ☐ |
| F-4 | кэш `colour()` без ключа палитры | ☐ |
| F-5 | промах получает клип попадания — `ExplosionBState.cpp` ~364 | ☐ |
| F-6 | декодирование PNG на пути рисования (R-009); `active()` по кадру, а не по времени | ☐ |

## Этап 4 — HD-интерфейс, предохранители

| ID | Что | Статус |
|---|---|---|
| U-1 | `drawIfPicture`: проверка площади до хэша (как R-014), порог по площади и сторонам | ☐ |
| U-2 | crop scan 97 мс в главном потоке; порог 2048 пропускает 128×16 | ☐ |

## Этап 5 — gpu-guard и кодировки

| ID | Что | Статус |
|---|---|---|
| A-4 | `gpu_scripts.txt`: +`sweep.sh`, `run_pilot.sh`, `run18.sh`, `run_ab_refine.sh`, `run2.py`, `ab_sdxl.py`; −ложные `score_batch`/`build_dataset`; тест «каждый скрипт с загрузкой модели в списке» | ☐ |
| A-4b | `gpu-guard`: запуском считать только первый python-аргумент (ложно ловит `rake.py match gen_hd.py`) | ☐ |
| A-5 | `encoding="utf-8"` → `utf-8-sig` на запись в 9 местах (в т. ч. `gpuq.py:260`) | ☐ |
| A-5b | `pedia_flatbg.py`: `convert("RGB")` → чтение индексами (R-043) | ☐ |

## Этап 6 — документы, которые читает `warmup`

| ID | Что | Статус |
|---|---|---|
| D-1 | `PROJECT.md` заново: интерфейс жив, портал — вторая ветвь, Пиратки первыми | ☐ |
| D-2 | `STATUS.md`, `BACKLOG.md`, `STYLE.md` — заполнить или удалить | ☐ |
| D-3 | `README.md` про OXCE-HD | ☐ |
| D-4 | `GENERATORS.md` пересверить по argparse (A-9) | ☐ |

## Этап 7 — диета граблей

| ID | Что | Статус |
|---|---|---|
| R-1 | `Файлы:` у R-002/R-011 сузить; `rake.py list --short` в хуке | ☐ |
| R-2 | слить 11 семей, вынести aibench и portal в свои файлы | ☐ |
| R-3 | тесты/хуки на 8 повторных без защиты (R-007, 009, 010, 011, 037, 039, 044, 066) | ☐ |
| R-4 | R-035: хук ловит и `sed` с `\\` в пайпе | ☐ |

## Этап 8 — `tools/hdart`

| ID | Что | Статус |
|---|---|---|
| A-2 | G1–G3 в `tools/hdart/attic/` с README; библиотечные части остаются | ☐ |
| A-3 | `hdart/common.py` (лист, хэш, TSV, пути), `hdart/models.py` | ☐ |
| A-8 | R-081: две копии мода `hd` — сверка списков в `build.ps1` | ☐ |

## Остаток (по возможности)

V-3…V-8 (ядро), U-3…U-8 (интерфейс), P-1…P-11 (портал и лаунчер), `CHANGELOG` по выпускам,
относительные пути в `build_config.json`/`release_config.json`, `SETUP.md` под настоящий тулчейн,
`.index` для `tools/` и `portal/`, `dist/ KeepLast: 2`, BrutalAI за пределы дерева,
`MASTER_OFFSET` из `Mod::getOffset`.

---

## Журнал

| Дата | ID | Коммит | Заметка |
|---|---|---|---|
| 2026-09-26 | G-1…G-5 | `421a6d737` | html-отчёты сохранены в `art/_review/html` |
| 2026-09-26 | M-1 | `f67648cdd` | |
| 2026-09-26 | M-2 | `bde0ba3c3` | игру не запускал, путь проверен только сборкой |
