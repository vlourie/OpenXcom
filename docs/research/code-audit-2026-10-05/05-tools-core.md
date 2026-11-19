# Аудит tools_core (только чтение) — 2026-10-05

Область: `tools/*.py` (138, из них 92 `test_*.py`), `tools/*.ps1`, `tools/*.cmd`, `tools/build/**`, `tools/merge/**`,
`tools/sfx/**`, `tools/aibench/**`, `tools/intro/**`, `tools/ai_speed/**`, `Выпуск/*`, `.claude/hooks/*.ps1`.
Всего 221 файл (включая данные подпапок). `tools/hdart/**` не смотрел. Ничего в `E:\OpenXCom` не менял, игру и сборку не запускал.

Инструменты аудита (в блокноте сессии `scratchpad/audit/`): `inv.py` (инвентарь + граф ссылок, один проход по корпусу:
CLAUDE.md, AGENTS.md, docs/**, .claude/**, tools/** вкл. hdart, Выпуск/**, portal/** без bin/obj/third_party, gpu_scripts.txt,
editq_paths.txt), `dump2.py` (R-001 по записям, `py -3`, тесты, хуки, досье), результаты `inv.json`, `tests.json`, `hooks.json`,
`py3.tsv`, `dump2_out.txt`. `tools/fix_bom.ps1` запускался без `-Fix` (по шапке — только проверка).

Пометка **ЗАНЯТ** — файл в `protected_status.txt` (M или ??), его правит другая сессия.

---

## 1. Граф ссылок: сироты и тесты

Ссылка = имя файла (`foo.py`) или `import foo` в любом файле корпуса, кроме самого скрипта. Сирот среди не-тестов — **8 из 129**.

| Скрипт | Изменён | Размер / строк | Что это | Улика | Предложение |
|---|---|---|---|---|---|
| `tools/hd_coverage.py` | 2026-09-18 | 11 308 / 237 | «Покрытие мода HD-графикой» по карте index_mod; старый конвейер | 0 ссылок по имени; по stem только `docs/DECISIONS.md:1964` (контекст решения о его ошибке подсчёта). Ту же задачу решает `tools/art_status.py` (CLAUDE.md: «что рисовать следующим», `docs/ART_STATUS.md`) | кандидат в `tools/attic/` или удаление после решения Vitali |
| `tools/hd_match_report.py` | 2026-09-19 | 5 985 / 140 | повтор `HdUiArt::pictureMatch` вне игры (distance/shape для hd/UI) | 0 ссылок; последний коммит 2026-09-19 | оставить как диагностический, но вписать в `docs/` (R-033 «is far from» — он объясняет эти строки) либо в attic |
| `tools/aibench/geo_report.py` | 2026-09-20 | 4 288 / 117 | форма боя по ходам из CSV `run_series.py --states` | 0 ссылок (README aibench его не называет; `style_report.py` упомянут, этот — нет) | дописать строку в `tools/aibench/README.md` или attic (aibench в целом — «форк Brutal не собирать», память) |
| `tools/ai_speed/blocked_step.py` | 2026-10-01 | 6 640 / 130 | сводка REPEATED_BLOCKED_STEP_V1 по серии | 0 ссылок; соседние `blocked_pair.py`, `blocked_repeat.py`, `blocked_kr.py` упомянуты в docs | один из ~30 одноразовых переписей ai_speed; см. раздел 4 |
| `tools/merge/merge_upstream_87.ps1` | 2026-09-24 | 6 395 / 115 | одноразовое слияние с MeridianOXC 8.7.0 (commit cf59d42b2), ветка отката `hd-render-before-8.7` | 0 ссылок; CLAUDE.md называет только папку `tools/merge/`; слияние выполнено (R-078 про его последствия) | остаток: оставить как образец для следующего слияния, но переименовать/описать в README папки |
| `tools/sfx/listen_page.py` | 2026-09-26 | 5 598 / 124 | страница прослушивания проб звука (`art/sfx/probe/listen.html`) | 0 ссылок; `docs/AUDIO_ROADMAP.md` по имени не называет; без argparse | дописать в AUDIO_ROADMAP или attic вместе с пробами этапа 0 |
| `tools/xpiratez_stat_report.py` | 2026-09-21 | 26 833 / 417 | генерирует `docs/research/xpiratez-stat-caps.md` | 0 ссылок; сам `.md` его не называет; без argparse (`sys.argv`), читает рулсеты обычным PyYAML (`import yaml`, строка 9) — противоречит R-046 | вписать в шапку сгенерированного `.md` или attic |
| `tools/piratez_weapons.py` | 2026-10-04 | 18 636 / 383 | таблица оружия Пираток → `docs/research/piratez-weapons*.html` | **ЗАНЯТ** (??, не в гите); шаблон `tools/piratez_weapons.html.in` тоже ?? | не трогать — свежая работа другой сессии |

Не сироты, но «висят на одной нитке» (одна ссылка): `tools/launcher_smoke.py` (только `docs/portal/RELEASING.md`),
`tools/launcher_press_play.ps1` (только из `launcher_smoke.py`), `tools/launcher_icon.py` (только `portal/.../Skin.cs`),
`tools/site_art_2x.py` (только `SiteServices.cs`), `tools/packs_seed.py`, `tools/portal_palette.py`, `tools/gfx_unused.py`,
`tools/git_hunks.py` (только RAKES R-094), `tools/art_tidy.py` (только RAKES), `tools/award_pages_en.py` (только RAKES),
`tools/optimize_assets.ps1` (только `tools/README.md`; работает с `assets/10_generated`, **папки `assets/` в репозитории нет**),
`tools/build/BuildGUI.ps1` (только `Выпуск/OXCE_Build.cmd` — это нормально), `tools/aibench/setup_brutal_bench.ps1` (только README aibench).

### Тесты: предмет на месте?

92 теста. Одноимённого модуля нет у 12, но предмет у всех существует:

| Тест | Предмет | Где |
|---|---|---|
| `test_acceptance_freeze.py` | `acceptance_plan`, `asset_rev`, `obj_gen_spec` | `tools/hdart/*.py` — есть (ЗАНЯТ, ??) |
| `test_ai_arena_commit.py`, `test_ai_arena_contract.py` | `ai_arena.py` | есть |
| `test_gentle_determinism.py` | `ai_probe.py` + `src/Engine/HdGentle` | есть |
| `test_gentle_scope.py` | дерево `src/` (греп вызовов) | предмет — код движка |
| `test_gpu_scripts.py` | `tools/gpu_scripts.txt` | есть (ЗАНЯТ, M) |
| `test_map_paint_input.py`, `test_map_paint_tiled.py`, `test_map_scenes.py` | `tools/hdart/map_paint.py`, `map_mockup.py` | есть; но по памяти проекта map_paint «забракован» — тесты охраняют отвергнутый конвейер (решение Vitali: держать как регрессию R-004/R-005/R-016 или убрать вместе с map_paint) |
| `test_option_defaults.py` | `src/Engine/Options.cpp` (через git show) | предмет — код движка |
| `test_read_pck.py` | `tools/hdart/xcom_sprites.py` | есть |
| `test_voice_duplex.py` | `voice_deps.py`, `voice_ma_patch.py` | есть |

Тестов с исчезнувшим предметом — **нет**. 63 из 92 тестов не в гите (?? — ЗАНЯТ, работа hdart-сессий).

---

## 2. Правило R-001 (кодировка)

### 2.1 Python: записи текста без `utf-8-sig` в файлах с кириллицей в литералах

Проверялись только записи (`open(...,'w'/'a')`, `write_text`); чтения с `errors="replace"` и `sys.stdout.reconfigure` — не нарушения.
Законные исключения R-001 (файлы читает игра/браузер/питон, не PowerShell) отмечены.

| Файл:строка | Что пишет | Оценка |
|---|---|---|
| `tools/index_project.py:181`, `tools/index_mod.py:256`, `tools/hd_coverage.py:214` | `meta.json` через `write_text(json.dumps(...))` **без encoding** | `json.dumps` без `ensure_ascii=False` даёт чистый ASCII — сейчас безвредно, но первая же кириллица в meta уйдёт в cp1251. Безопасно дописать `encoding="utf-8-sig"` (читатель — python с `utf-8-sig`? проверить `index_project.py` чтение meta) |
| `tools/ai_arena.py:212, 231, 420` | `*.data_manifest.tsv` (utf-8), `prov` (append utf-8), `tmp.write_text(...)` без encoding | читает тот же скрипт — безвредно; строка 420 без encoding — привести к `utf-8-sig` или хотя бы явному utf-8 |
| `tools/gpuq.py:520` | `open(yield_file(jid), "w").close()` — пустой файл-маркер | безвредно. **ЗАНЯТ** |
| `tools/ai_speed/mutual_diag_audit.py:199` | кэш (append utf-8), читает сам | безвредно |
| `tools/intro/build_intro.py:166, 317`; `tools/award_pages_en.py:153`; `tools/game_hidden.py:59`; `tools/rupatch_levels.py` | `.rul`, `.yml`, `options.cfg` — **читает игра** | исключение R-001, верно |
| `tools/portal_palette.py:182` (CSS), `tools/sfx/listen_page.py:119` (HTML, помечено «НЕ ТРОГАТЬ»), `tools/piratez_weapons.py:361,364` (HTML, ЗАНЯТ) | для браузера | верно без спецификации; у `piratez_weapons.py:364` encoding не указан вовсе — дописать `utf-8` |
| тесты (`test_editq.py`, `test_game_guard.py`, `test_rul_map.py`, `test_unit_census.py`, `test_routing_*`, …) | временные фикстуры | не нарушение; `test_rul_map`/`test_unit_census` пишут `.rul`/`.yml`/`options.cfg` — верно без BOM |

Итог: настоящих нарушений R-001 по записи в области **нет**; три `meta.json` — профилактика.

`fix_bom.ps1 -ShowReads` отдельно выделяет «ЗАПИСЬ посмотреть глазами» у `voice_ma_patch.py`, `sfx/listen_page.py`, ряда тестов — это те же строки, что выше.

### 2.2 .ps1 / .cmd: спецификация

- Все 9 `.ps1` области с кириллицей (`tools/*.ps1`, `.claude/hooks/*.ps1`, `tools/build/*.ps1`, `Выпуск/release.ps1`, `tools/aibench/*.ps1`, `tools/merge/*.ps1`) — **с BOM**. `fix_bom.ps1` по `.claude/hooks`: «8, все в UTF-8 с BOM и CRLF».
- `Выпуск/OXCE_Build.cmd`, `Выпуск/OXCE_Release.cmd` — без BOM, кириллицы нет: **верно** (BOM в `.cmd` ломает cmd.exe).
- `fix_bom.ps1` по `Выпуск`: `release.ps1 — не CRLF` (переводы строк LF). Работает, но проверка его помечает как «плохо»; при `-Fix` будет переписан. Файл не занят.
- `fix_bom.ps1` по `tools`: помимо `hdart\gen_all.ps1`, `hdart\setup_qwen21.ps1` (не CRLF; не моя область) ругается на `hdart\.venv-qwen21\Scripts\Activate.ps1` и `sfx\.venv-sa3\Scripts\activate.ps1` и выводит сотни строк из `sfx\.venv-sa3\Lib\site-packages\transformers\*.py`. Причина: `$skipDirs = @('\.git\', '\.index\', '\node_modules\', '\.venv\')` — шаблон `\.venv\` не ловит `.venv-sa3`, `.venv-qwen21`. Правка одной строки в `tools/fix_bom.ps1` (не занят): `'\.venv'` без закрывающей косой.

### 2.3 print кириллицы без `reconfigure` там, где вывод перенаправлен

Проверено по факту: в этой среде `py -3.13 -c "..." | cat` даёт `sys.stdout.encoding = cp1252`, `PYTHONIOENCODING` и `PYTHONUTF8` не заданы.

| Скрипт | Кто зовёт с перенаправлением | Улика | Риск |
|---|---|---|---|
| `tools/index_project.py` | `.claude/hooks/session-start.ps1:20` — `& $py.Source tools/index_project.py --if-stale --quiet 2>&1 \| Out-String` | печатает `Индекс собран: …` (стр. 189) и `ВНИМАНИЕ: ctags не установлен…` (191) без `reconfigure`; `--quiet` глушит только строку 208 | **Воспроизведено в этой сессии**: SessionStart-хук выдал «КАРТА: индексатор не отработал — Traceback (most recent call last):»; `.index/meta.json` записан 18:59:26.585, вывод хука сохранён 18:59:26.873 — индекс пересобран, падение на первом `print` с кириллицей в трубу cp1252 (хук с `$ErrorActionPreference='Stop'` ловит первую строку stderr). Каждая новая сессия при устаревшем индексе видит трассировку вместо «КАРТА: …». Правка: `sys.stdout.reconfigure(encoding="utf-8")` в `main()` (как в `rake.py:23`) или `PYTHONIOENCODING=utf-8` в хуке |
| `tools/game_hidden.py` | агенты через Bash (вывод в трубу); game-guard его же и предписывает | `print("pid", …, "(скрытый рабочий стол)")` стр. 80, «таймаут» 86, «код» 89, «дамп» 90 — без `reconfigure` | падение после запуска игры, если агент не поставил `PYTHONIOENCODING=utf-8` (в подсказке game-guard:97 его нет) |
| `tools/describe_modules.py`, `tools/sfx/probe_*.py` | очередь `gpuq.py` | gpuq задаёт заданиям `PYTHONIOENCODING=utf-8, PYTHONUTF8=1` (gpuq.py:669) | закрыто очередью |
| `tools/editq.py`, `tools/gpuq.py`, `tools/rake.py` (хуки) | хуки settings.json, session-start, rake-check, gpu-guard | `reconfigure` есть (editq.py:865, gpuq.py, rake.py:23) | в порядке |

Остальные скрипты с print кириллицы без `reconfigure` (art_status, art_tidy, index_mod, pck_census, pck_roadmap, rul_map, save_profile,
subject_plan/report, unit_coverage, gfx_unused, hd_coverage, hd_match_report, launcher_icon, packs_seed, portal_*, site_art_2x,
aibench/decide_diff, parse_aibench, style_report, intro/make_script, ai_speed/ambush_fail и ~35 тестов) зовутся людьми из консоли —
там работает, падают только при `> файл` (третья сторона R-001).

---

## 3. Запуск интерпретатора `py -3` без версии (R-101, R-139)

Всего 141 упоминание (без `tools/hdart`). Что исполняется (а не просто текст подсказки):

| Файл:строка | Команда | Оценка |
|---|---|---|
| `.claude/settings.json:57, 69, 110, 121` | `py -3 "$CLAUDE_PROJECT_DIR/tools/editq.py" hook post/stop/pre` | исполняется на каждый Edit/Write/Bash. `editq.py` — только stdlib и сам делает `reconfigure`, поэтому под 3.14 работает; но правило R-139 — «не зависеть от того, какой питон новейший». **ЗАНЯТ** (M) |
| `.claude/hooks/session-start.ps1:54` | `& py -3 tools/editq.py brief` | то же |
| `.claude/hooks/session-start.ps1:16–20` | `Get-Command python` → `& $py.Source tools/index_project.py` | берёт первый `python` из PATH (какой — не проверяется); stdlib-only, но см. 2.3 |
| `portal/publish.ps1:27` | `& py -3 tools/voice_deps.py --check` | stdlib-only — работает; вне области, отмечено |
| `tools/sfx/probe_mmaudio.py:8`, `probe_stable_audio.py:11` (docstring) | `py -3 tools/gpuq.py add … -- tools/sfx/.venv/Scripts/python.exe …` | и `py -3`, и относительный путь интерпретатора — ровно R-097 (gpuq теперь сам абсолютизирует, но образец в docstring копируют) |

Текст подсказок/документации с `py -3`:
- **CLAUDE.md:90, 99, 110, 111** — `py -3 tools\gpuq.py add`, `py -3 tools/editq.py wait/done` (ЗАНЯТ, M). Сам CLAUDE.md противоречит R-101/R-139.
- `.claude/hooks/gpu-guard.ps1:106` — подсказка «py -3 tools/gpuq.py add» в отказе хука.
- `tools/editq.py` — 15 строк (docstring 22–27, 41 и сообщения хука 455, 457, 478, 503, 506, 521, 522, 546, 659): каждое сообщение отказа учит `py -3`.
- `tools/gpuq.py:9–11, 621` (ЗАНЯТ); `tools/gpt_check.py:8–12` и `.claude/skills/gpt-check/SKILL.md` (6 строк) — ЗАНЯТ (??).
- `tools/art_status.py:16–17`, `art_tidy.py:24,25,315`, `git_hunks.py:3–4`, `rul_map.py:6–7`, `save_profile.py:9–10`, `pck_census.py:17`, `pck_roadmap.py:16`, `portal_palette.py:20–21`, `portal_wiki.py:16`, `award_pages_en.py:20`, `rupatch_levels.py:4`, `xpiratez_stat_report.py:4`, `gfx_unused.py:8`, `aibench/style_report.py:13,20`, `hd_demo_mod/make_demo_frames.py:5,28`, `hd_test_mod/make_demo_frames.py:5,28`, `savecheck/soldier_stat_audit.py:22`.
- docs: `GENERATORS.md` 13, `RAKES.md` 8 (ЗАНЯТ), `SETUP.md` 4, `tools/hdtest_README.md` 4, `research/hd-fonts.md` 5, `research/gen3-audit.md`, `pck-census.md`, `piratez-ruleset.md` по 2, ещё 6 по одной; `portal/deploy/README.txt:155`, `portal/deploy/pack.ps1:49`.
- Тесты (`test_gpu_guard.py` 5, `test_game_guard.py` 3, `test_backslash_guard.py`, `test_editq.py`, `test_gpuq.py`, `test_gentle_scope.py` 2, `test_option_defaults.py` 2, `test_map_scenes.py`, `test_rul_map.py`) — строки под проверкой или docstring; `test_gpu_guard` и `test_game_guard` нарочно проверяют команды с `py -3`.
- `.claude/settings.local.json:9` — разрешение `Bash(py -3 -)` — это ровно запрещённый R-184 запуск (хук его блокирует, но allow-список противоречит); строки 14, 17, 18 — разрешения с путями scratchpad **чужой** сессии `393c2d37-…` — мусор.

Полный список: `scratchpad/audit/py3.tsv`.

---

## 4. Пересечения по назначению

| Группа | Скрипт (строк) | Что делает | Кто ссылается | Предложение |
|---|---|---|---|---|
| **Запуск игры** | `tools/game_hidden.py` (94) | невидимый запуск + дамп экрана по кликам `OXCE_HD_CLICK` | 13: game-guard, RAKES, HD_UNITS, portal/* | канонический, оставить |
| | `tools/ai_probe.py` (438) | класс `Hidden` (рабочий стол + SDL dummy) + проба хода ИИ | 26: AI_*, RAKES, unit_perf, builds_accept, launcher_smoke, xcf_probe, ai_blind, test_gentle_determinism | `Hidden` — общая библиотека, живёт внутри скрипта проб. Кандидат на вынос в `tools/hidden_desktop.py`, чтобы `game_hidden` и `ai_probe` делили один код |
| | `tools/measure_hd.ps1` (107) | замер памяти HD-рендера, CSV | 6: PERF.md, RAKES R-012/R-091 (как источник цифр), test_game_guard | `Start-Process $Exe` (стр. 70) **без SDL dummy** — game-guard (`$Safe` стр. 26) такую команду агенту блокирует; с R-124 (28.09) скрипт агентом не запускаем. Либо перевести на `game_hidden`/`ai_probe.Hidden`, либо снять ссылки из RAKES R-091 на него как на источник замеров |
| | `tools/unit_perf.py` (257) | p50/p95/p99 кадра боя через `ai_probe.Hidden` | RAKES, units-perf-baseline | пересекается с measure_hd по цели (perf HD); замена measure_hd для боя |
| | `tools/ai_arena.py` (552), `tools/ai_blind.py` (185) | серии боёв ИИ / тест слепоты | AI_ROADMAP, AI_TRAINING | оба на `ai_probe` — в порядке |
| **Лаунчер** | `tools/launcher_smoke.py` (298) + `launcher_press_play.ps1` (37), `tools/builds_accept.py` (285), `tools/compat/xcf_probe.py` | каждый сам строит временную установку Пираток соединениями (R-047) и снимает их `rmdir` | RELEASING.md / MULTIMOD_STAGE1.md / — | три копии логики «временная установка из junction'ов»; в `aibench/run_series.py` есть `prepare_dir` с тем же. Вынести в одну функцию рядом с `ai_probe.Hidden` |
| | `tools/shot_window.ps1` (83) | снимок видимого окна (PrintWindow, DPI-aware) | RAKES R-059, R-070 | другой случай (видимое окно по просьбе Vitali) — оставить |
| **Сравнение дампов** | `tools/hdtest_compare.py` (219) | IDENTICAL/DIFFERENT двух дампов F8 + perf | CLAUDE.md, AGENTS.md, PROJECT, SETUP, RAKES | единственный; `tools/compat/xcf_compare.py` сравнивает HD-паки с другой игрой — иная задача; `aibench/decide_diff.py`, `ai_speed/cmp_runs.py`, `ai_speed/series_eq.py` — сравнения прогонов ИИ, не кадров |
| **Листы/сверки** | `tools/hd_sheet.py` (129) | лист «оригинал \| как вышло» по кадрам мода | RAKES R-087 (R-019) | листы в `hdart` — другой аудитор; здесь один |
| **Карты/индексы** | `tools/index_project.py` (214) | `.index/symbols.tsv`, `files.tsv` (ctags) | session-start, skills/index, scout.md | канонический |
| | `tools/index_mod.py` (281) | `.index/mod/<мод>/entries.tsv, sprites.tsv` из рулсетов | RAKES, hd_coverage, hdart gen_hd/subjects_terrain/triage | и |
| | `tools/rul_map.py` (750) | `.index/mod/Piratez/rul/values.tsv, refs.tsv` — разбор рулсетов по содержимому | CLAUDE.md, piratez-ruleset.md, gfx_unused, piratez_weapons | два разбора рулсетов Пираток в соседние папки `.index/mod/Piratez/` — index_mod (где объявлено) и rul_map (что в полях). Не дубль, но единый вход (`rul_map` вызывает `index_mod`?) — нет: каждый грузит YAML сам |
| **Покрытие/очередь арта** | `tools/art_status.py` (162) | очередь перерисовки по диску → `docs/ART_STATUS.md` | CLAUDE.md | канонический |
| | `tools/hd_coverage.py` (237) | то же для старого конвейера | 0 | **вытеснен** art_status — см. раздел 1 |
| | `tools/pck_census.py` (419) / `pck_roadmap.py` (153) | перепись PCK, очередь по охвату карт | CLAUDE.md, portal PackSeed.cs | канонические |
| | `tools/subject_plan.py` / `subject_report.py` | темы наборов для старого gen_hd | hdart/subjects_terrain | живут вместе с gen_hd (hdart) |
| **Переписи юнитов** | `unit_census.py` (1229) → `unit_coverage.py` (1985), `unit_explicit.py` (1171) | семейство одного документа HD_UNITS | HD_UNITS.md | связаны по данным; дубля нет |
| **Генерация вне hdart** | `tools/gen_gpu.py` (154) | мост к ComfyUI / A1111-Forge, «агент gpu-forge вызывает этот скрипт» | `.claude/agents/gpu-forge.md`, `tools/README.md`, `setup_workstation.ps1` | вся генерация давно в `tools/hdart` (diffusers/Qwen через gpuq); gen_gpu не в `gpu_scripts.txt` и очередь его не знает. Либо снять из агента gpu-forge, либо описать как альтернативу — решение Vitali |
| | `tools/optimize_assets.ps1` (74) | `assets/10_generated → 20_optimized` | `tools/README.md` | папки `assets/` нет; остаток старой схемы |
| **Демо-моды** | `tools/hd_demo_mod/make_demo_frames.py` и `tools/hd_test_mod/make_demo_frames.py` | одинаковы, кроме одного слова в docstring (`diff`: строка 3) | `tools/hdtest_README.md` | вне строгой области (подпапка), но дубль в `tools/`: оставить один |
| **Звук** | `tools/sfx/probe_mmaudio.py`, `probe_stable_audio.py`, `probe_sa3.py` + `probe_tasks.py`, `listen_page.py` | три пробы одного этапа 0 на одном списке заданий | AUDIO_ROADMAP, gpu_scripts | по замыслу (сравнение моделей); доживают этап 0 |
| **ai_speed** | 30 скриптов (`ambush_*`, `blocked_*`, `mutual_*`, `stale_*`, `stagnation_*`, `*_census`, `hang_*`, `prof_*`) | пассивные переписи по архивам серий, по одной на гипотезу/пункт аудита | `tools/ai_speed/README.md` (65 КБ), docs/research/ai-* | `gzip.open(path, "rt", encoding="utf-8")` + разбор `[AI…]`-строк повторён в ≥12 файлах, `_common.py` — 40 строк. Мораторий на новые механики ИИ (память 04.10): папку можно заморозить и вынести чтение архивов в `_common.py` при следующем касании |

---

## 5. Остатки

| Признак | Что нашлось | Оценка |
|---|---|---|
| `*_old`, `*_tmp`, `*.bak`, `*.orig`, `*_copy` | в области — **нет** | — |
| пустые файлы | **нет** | — |
| `_v1` при `_v2` | только тесты: `test_aligned_recolor_v1/v2`, `test_arbiter`/`_v2`, `test_hd_e2e_v1` + `_r2/_r3/_r31`, `test_relation_discovery_v2…v5`, `test_relation_holdout_v4/v5/v7`, `test_routing_holdout_v5/v7/v8`, `test_routing_rules_v5/v6/v7`, `test_routing_model_v8`, `test_two_component_v1`, `test_assembly_*_v1`, `test_derive_recolor_acceptance_v2` — 24 файла, все **??** (ЗАНЯТ), предметы в `tools/hdart` | версии тестов копятся вместе с версиями hdart-модулей — вопрос другому аудитору; здесь только факт |
| docstring «проба/черновик/временно» | `tools/sfx/probe_*.py` («пробный прогон, этап 0»), `tools/art_tidy.py` (одноразовая уборка корня, выполнена 22.09), `tools/merge/merge_upstream_87.ps1` (одноразовое слияние, выполнено 24.09), `tools/rupatch_levels.py` (перенос страниц между версиями RU-патча — по случаю) | одноразовые, сработавшие: кандидаты в `tools/attic/` (как уже сделано в `tools/hdart/attic/`) |
| устаревшие схемы | `tools/optimize_assets.ps1` (нет `assets/`), `tools/gen_gpu.py` (ComfyUI/A1111), `tools/hd_coverage.py` | см. раздел 4 |
| дубли | `hd_demo_mod/make_demo_frames.py` = `hd_test_mod/make_demo_frames.py` | один убрать |
| не в гите, но в `tools/` | `tools/piratez_weapons.py`, `tools/piratez_weapons.html.in`, `tools/gpt_check.py`, 63 теста | ЗАНЯТ — чужая незакоммиченная работа; в отчёт только как факт |
| `.claude/settings.local.json` | allow-строки с путями scratchpad чужой сессии (`393c2d37-…`, строки 14, 17, 18) и `Bash(py -3 -)` (строка 9) | мусор разрешений; файл не в protected-списке |
| `Выпуск/release.ps1` | LF вместо CRLF (fix_bom «не CRLF») | работает; нормализовать при случае |

---

## 6. Хуки

Подключение (`.claude/settings.json`, ЗАНЯТ — M):

| Событие | Матчер | Команды |
|---|---|---|
| SessionStart | — | `session-start.ps1` |
| PreToolUse | `Bash\|PowerShell` | `backslash-guard.ps1`, `gpu-guard.ps1`, `game-guard.ps1`, `pack-guard.ps1`, `py -3 tools/editq.py hook pre` |
| PreToolUse | `Edit\|Write\|NotebookEdit` | `py -3 tools/editq.py hook pre`, `guard-paths.ps1`, `rake-check.ps1` |
| PostToolUse | `Edit\|Write` | `bom-guard.ps1`, `py -3 tools/editq.py hook post` |
| Stop | — | `py -3 tools/editq.py hook stop` |

Что зовут хуки и существует ли (все — **есть**):

| Хук | Зовёт | Тест | Занят |
|---|---|---|---|
| `backslash-guard.ps1` (162) | — (сам); тест `tools/test_backslash_guard.py` | есть | M |
| `bom-guard.ps1` (50) | — | **нет** | — |
| `game-guard.ps1` (103) | упоминает `tools/game_hidden.py` (есть) | `test_game_guard.py` есть | — |
| `gpu-guard.ps1` (112) | читает `tools/gpu_scripts.txt` (есть), упоминает `tools/gpuq.py`, `tools/rake.py` | `test_gpu_guard.py` есть | — |
| `guard-paths.ps1` (81) | — | **нет** | M |
| `pack-guard.ps1` (94) | `tools/hdart/build_hd_pack.py` (есть, ??) | `test_pack_guard.py` есть (??) | ?? |
| `rake-check.ps1` (61, изменён сегодня 18:45, закоммичен) | `tools/rake.py match` (есть) | **нет** | — |
| `session-start.ps1` (70) | `python tools/index_project.py --if-stale --quiet`, `py -3 tools/editq.py brief`, `tools/rake.py` | **нет** | — |

Замечания: (а) `session-start.ps1` берёт `python` из PATH без проверки версии, а `editq` — через `py -3` (R-139); (б) вывод `index_project.py` ловится в трубу без `PYTHONIOENCODING` — см. 2.3; (в) у четырёх хуков нет тестов, хотя протокол RAKES требует «тест или хук» — для самих хуков защиты нет; (г) `test_editq.py` покрывает очередь, но не её вызов из settings.json (R-055 — проверка «виден ли хук в работе» только руками).

В этой сессии хуки видны в работе: backslash-guard остановил `sed -i` с обратной косой, R-184-проверка остановила случайный `python3 -`.

---

## 7. Качество по верхам

**Без argparse / `--help` среди вызываемых людьми:** из скриптов, названных в CLAUDE.md (`hdtest_compare`, `rake`, `gpuq`, `editq`,
`art_status`, `rul_map`, `fix_bom.ps1`, `build.ps1`, `release.ps1`, `pck_census`, `pck_roadmap`) — у всех argparse/param есть.
Без argparse (`sys.argv` или без аргументов), но названы в docs/RAKES: `tools/git_hunks.py` (R-094), `tools/rupatch_levels.py` (R-074, EDITIONS.md),
`tools/save_profile.py` (AI_*), `tools/xpiratez_stat_report.py`, `tools/launcher_icon.py`, `tools/sfx/listen_page.py`,
`tools/merge/merge_upstream_87.ps1` (без `param`), `tools/aibench/setup_brutal_bench.ps1`; в ai_speed: `attach_all`, `ambush_fail`, `hang_count`,
`hang_stack`, `mutual_block`, `par_test`, `prof_report`, `stale_late_est`, `stale_shadow_report`, `stale_trigger_est`.

**Длиннее 1500 строк:** `tools/unit_coverage.py` — 1985. На подходе: `unit_census.py` 1229, `unit_explicit.py` 1171,
`tools/build/build.ps1` 1071, `editq.py` 899, `gpuq.py` 875, `rul_map.py` 750, `portal_wiki.py` 716.

**Прочее по пути:** `tools/xpiratez_stat_report.py` читает рулсеты обычным `yaml` (строка 9) вопреки R-046 (терпимый загрузчик в `pck_census.Tolerant`);
`tools/fix_bom.ps1` не пропускает `.venv-*` (см. 2.2).

---

## Безопасно применить сейчас
(файлы не заняты, сборка не нужна, механика не задета)

1. `tools/fix_bom.ps1`: `$skipDirs` — `'\.venv\'` → `'\.venv'`, чтобы не сканировать `sfx\.venv-sa3` и `hdart\.venv-qwen21` (сотни ложных строк).
2. `tools/index_project.py`: `sys.stdout.reconfigure(encoding="utf-8")` в начале `main()` — строки 189/191 печатают кириллицу в трубу session-start.ps1, и сегодня в 18:59:26 хук этой сессии на этом упал (см. 2.3); заодно `encoding="utf-8-sig"` у `meta.json` (стр. 181). То же в `tools/index_mod.py:256`, `tools/hd_coverage.py:214`. Самая срочная из безопасных: ломает старт каждой сессии при устаревшем индексе.
3. `tools/game_hidden.py`: `reconfigure` stdout (строки 80–90 с кириллицей), либо добавить `PYTHONIOENCODING=utf-8` в подсказку `.claude/hooks/game-guard.ps1:97`.
4. `.claude/hooks/session-start.ps1:54`: `py -3` → `py -3.13` (и `:16` — явный выбор питона вместо первого `python` из PATH).
5. `.claude/hooks/gpu-guard.ps1:106`: подсказка `py -3 tools/gpuq.py add` → `py -3.13`.
6. Docstring-подсказки `py -3` → `py -3.13` в незанятых: `art_status.py`, `art_tidy.py`, `git_hunks.py`, `rul_map.py`, `save_profile.py`, `pck_census.py`, `pck_roadmap.py`, `portal_palette.py`, `portal_wiki.py`, `award_pages_en.py`, `rupatch_levels.py`, `xpiratez_stat_report.py`, `gfx_unused.py`, `aibench/style_report.py`, `sfx/probe_mmaudio.py`, `sfx/probe_stable_audio.py` (там же — абсолютный путь интерпретатора, R-097), `tools/hdtest_README.md`, `docs/SETUP.md`, `docs/GENERATORS.md`.
7. `.claude/settings.local.json`: убрать разрешения с путями чужой сессии `393c2d37-…` (строки 14, 17, 18) и `Bash(py -3 -)` (строка 9).
8. Удалить один из дублей `tools/hd_demo_mod/make_demo_frames.py` / `tools/hd_test_mod/make_demo_frames.py` (проверить, какой мод живой по `tools/hdtest_README.md`).
9. Вписать сирот в их документы одной строкой: `geo_report.py` → `tools/aibench/README.md`; `listen_page.py` → `docs/AUDIO_ROADMAP.md`; `xpiratez_stat_report.py` → шапка `docs/research/xpiratez-stat-caps.md`; `hd_match_report.py` → рядом с R-033 в docs.
10. `Выпуск/release.ps1`: нормализовать LF→CRLF (`fix_bom.ps1 -Fix -Path Выпуск`) — только после того, как убедиться, что никто его не правит (не в protected-списке).

## Требует решения Vitali

1. **`tools/measure_hd.ps1`** запускает игру видимо (`Start-Process`, стр. 70) — game-guard агенту её блокирует; RAKES R-091 называет её источником замеров. Переписать на `game_hidden`/`ai_probe.Hidden` или объявить «только руками Vitali» и снять из R-091 (RAKES ЗАНЯТ).
2. **CLAUDE.md:90, 99, 110, 111 и `tools/editq.py` (15 строк), `tools/gpuq.py`, `.claude/settings.json`** учат `py -3` (ЗАНЯТЫ). Правило R-139 выполнено только в gpuq (самоперезапуск); решить: везде `py -3.13` или зафиксировать «`py -3` допустим для stdlib-скриптов с reconfigure» в DECISIONS.
3. **Attic для одноразовых**: `tools/hd_coverage.py` (вытеснен art_status), `tools/merge/merge_upstream_87.ps1`, `tools/art_tidy.py`, `tools/optimize_assets.ps1` (нет `assets/`), `tools/gen_gpu.py` (ComfyUI-мост, но на него ссылается агент `gpu-forge.md`) — удалять или переносить в `tools/attic/` по образцу `tools/hdart/attic/`.
4. **`tools/ai_speed/`** (30 скриптов, мораторий на механики ИИ): заморозить как есть или свести чтение архивов в `_common.py` и убрать переписи закрытых гипотез (`blocked_step.py` — сирота).
5. **Тесты `test_map_paint_*.py`, `test_map_scenes.py`** охраняют забракованный `map_paint` — держать как регрессию граблей R-004/R-005/R-016 или убрать вместе с конвейером (предмет — hdart).
6. **Вынос `ai_probe.Hidden` и «временной установки из junction'ов»** в общий модуль (сейчас повторено в `launcher_smoke`, `builds_accept`, `compat/xcf_probe`, `aibench/run_series.prepare_dir`) — рефакторинг, задевает запускатели проб.
7. **Тесты для хуков без тестов** (`bom-guard`, `guard-paths`, `rake-check`, `session-start`) и проверка подключения хуков из `settings.json` (R-055) — нужна ли автоматика, или хватает ручной проверки новой сессией.
8. `tools/xpiratez_stat_report.py` — PyYAML вместо `Tolerant` (R-046): чинить или в attic вместе с отчётом.
