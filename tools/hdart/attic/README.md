# Чердак tools/hdart

Точки входа прежних поколений генерации террейна. Здесь лежат скрипты, которые никто из живого
кода не импортирует. Они не удалены: на них держатся выводы в граблях и решения, и их можно
запустить снова. Перенесено 2026-09-26 по аудиту (пункт A-2 в
`docs/research/audit-2026-09-26-fixes.md`).

Текущий конвейер — G4 `map_paint.py` (блок карты как сцена), плюс педия. См. `docs/GENERATORS.md`.

## Что здесь и почему спит

| Поколение | Файлы | Почему спит |
|---|---|---|
| G1 SDXL-листы | `run_batch.py`, `repack_all.py`, `check_floors.py`, `field_sweep.py` | набор рисовался плитками: швы (R-005), ковры без вариантов (R-039) |
| G2 LoRA | `gen_tile.py`, `keep_batch.py`, `run_detached.cmd`, `merge_best.py` | годных 47,8 % против 76 % у прежнего пака (R-061); `merge_best` отдавал ничью худшему, его заменил `merge_gens.py` (R-076) |
| G3 Qwen edit | `paint3.py`, `prompt_writer.py`, `ab_sdxl.py`, `ab_sheet.py`, `pick_old_grey.py` | держит пиксельную сетку оригинала, мерки хвалят, глазами хуже (R-066, семья R-088) |

## Что из тех же поколений осталось в tools/hdart и почему

- `gen_hd.py` — движок; его импортирует `map_paint.py` (G4).
- `build_pack.py` — его импортирует `review_floors.py`, а тот — часть приёмки паков в портале
  (`docs/portal/PACK_REVIEW.md`).
- `gen_lora_batch.py` — из него берёт `MCD_DIRS` скрипт `triage/build.py`.
- `gen_lora_test.py` — его импортирует `pedia_ab.py` (педия жива) и `unpanel_batch.py`.
- `tile_forge.py`, `score_batch.py`, `build_dataset.py`, `dupe_plan.py`, `mirror_frames.py`,
  `link_frames.py` — библиотеки с десятком живых импортёров.
- `gen_all.ps1` — тонкая обёртка над `extract_pck`/`gen_hd`/`build_pack`, на ней защита R-015.
- `check_lora.py`, `train_lora.ps1` — обучение LoRA; `build_dataset` жив, обучение может понадобиться.

## Как запускать

Из корня репозитория, по новому пути:

    tools\hdart\.venv\Scripts\python.exe tools\hdart\attic\repack_all.py --help

Каждый скрипт чердака кладёт в `sys.path` и свою папку, и `tools/hdart` уровнем выше: так
библиотеки находятся без переноса. Скрипты с моделью по-прежнему идут только через очередь
(`tools/gpuq.py`): gpu-guard узнаёт их по имени файла, путь ему не важен, а
`tools/test_gpu_scripts.py` чердак обходит наравне с остальными.

Проверено при переносе: все импорты находят модуль, живой код ничего отсюда не импортирует,
`--help` у `ab_sheet`, `repack_all` и `merge_best` отвечает. Модельные скрипты вживую не
запускались.
