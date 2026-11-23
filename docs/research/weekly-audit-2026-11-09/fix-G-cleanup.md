# Пакет Г (уборка) недельного аудита 09.11 — исполнитель

Файлы игры (src/, bin/, user/mods/, CHANGELOG.md) не тронуты. Кириллица в новых файлах — UTF-8 с BOM.

## Коммиты

| Пункт | Коммит | Что |
|---|---|---|
| 1 сироты | fdf9cf41a | `git rm` 37 из 44 сирот, −4 030 строк |
| 2 хлам | 0f772abdc + a9020aebe | `/Выпуск/weekly/**/*.png` в .gitignore; 10 PNG (9,5 МБ) сняты с учёта (`git rm --cached`), на диске остались. Первый коммит по ошибке (пути в `git commit <путь>` перечитали рабочее дерево) взял только .gitignore, второй досняли PNG |
| 3 settings.json | ccac31dce | `docker-ssh-guard.ps1`, `ticket-commander.md`, `ticket-dedup.md`, `ticket-ideas.md` и тест хука `tools/test_docker_ssh_guard.py` (был неотслеживаемым, проходит) |
| 4 тесты хуков | 30dac1541 | `tools/test_guard_paths_guard.py` (25 случаев + 4 «не роняет сессию»), `test_bom_guard.py` (20 проверок), `test_session_start_hook.py` (в пустом проекте-заглушке, настоящий .index и очередь не трогает); плюс правка `guard-paths.ps1` и R-871 (см. ниже) |
| 6 стейдж | be9647e65 | `tools/build/build.ps1`, +8 строк в `Invoke-ModStep` |
| 5 зеркало Codex | без коммита | `.codex/` и `.agents/` неотслеживаемые целиком (в гите их нет) |

## 1. Удалённые сироты (37)

Проверка: `git grep -w <имя>` по всему репозиторию, а не только по списку папок задания; ссылаются лишь отчёты прошлого аудита 27.10.

`tools/`: backdrop_colors, collapse_holdout3, hd_tabs_shots, portal_mod_art (.py); `tools/sfx/hb518_install.py`.
`tools/hdart/`: b3b_build, base_census, blood_spray_pack, cockpit_census, craft_launch_pack, doll_gnome_assemble, doll_gnome_heads, doll_neko_heads_531, egg_build, forest_tree_fix, hb515_install, hb516_install, hb517_install, hd_tracks_gen, item_backpack_hd, jungle_509_install, jungle_spot, p509_bush3_cut, p509_gen, promo_compare, shore_build, t1031_sheet, t1031b_notes, t1031b_scene384, t1031b_sheet, t1031b_verify, t1031c_install, t435b_install, t_grass, t_installed, t_regen_sheet, t_slope_edge_install.
(b3b_build назван в jungle_509_install только строкой-меткой источника, оба сироты, ушли вместе.)

**Оставлено 7 из 44:**
- `tools/hdart/floor_scene.py` — floor_batch.py (строка 579) выдаёт его имя как команду-подсказку «нужна сцена floor_scene --env», R-314.
- `tools/lua_stage3/stage5.py` — стадия 5 автопроверки Lua-модов (LUA_MODS.md §8.2), в паре с test_check/test_sandbox; Lua-моды ждут запуска в песочнице, решать Vitali.
- `tools/hdart/doll_dd/dd_cut, dd_panel, dd_pasty, dd_tint, dd_view` — шаги конвейера кукол DEMONESS/DOGE, добавлены сегодня, страница dd_r1 ещё не принята.

Не нашёл: в `Выпуск/` и на `portal/deploy` ссылок на удалённое нет.

## 2. Хлам

- `nul` (46 байт) и `c330_cand.png` (292 КБ) были неотслеживаемыми, удалены с диска; упоминания только в отчётах аудита.
- `tools/hdart/pedia_compare.html` и `pedia_prompts.html` **в гите и на диске уже нет** (вынесены ещё в аудите 26.09, G-3); строка отчёта устарела, делать нечего.
- `Выпуск/weekly/*.png`: никто не отдаёт (build/release/портал/инструкции ссылок не имеют); `summary.md` оставлен в гите.

## 4. Тесты хуков и найденная ошибка (R-871)

Первый запуск `test_guard_paths_guard.py` дал 5 FAIL: **запрет записи в `Пиратки/...` не срабатывал совсем** (ASCII-запреты bin/UFO, dist, game, user/mods/hd/hd работали). Причина: Windows PowerShell 5.1 читает stdin через `[Console]::In` в кодовой странице консоли (437/866), а событие приходит в UTF-8, слово «Пиратки» превращалось в мусор. Исправлено двумя строками в `.claude/hooks/guard-paths.ps1` (`[Console]::InputEncoding` = UTF-8), все 5 случаев теперь deny. Остальные хуки не-ASCII в шаблонах не имеют, их не менял. Грабли R-871 записаны (в коммит вошёл только мой раздел: в рабочем `docs/RAKES.md` лежит ещё ~230 строк чужих неотслеживаемых правок, их не трогал).

Замечание для Vitali: CLAUDE.md делает исключением `bin/common/Language/OXCE` (спрашивать не нужно), а хук `guard-paths` по-прежнему даёт `ask` на весь `bin/common`. Не менял — это решение, а не уборка.

Весь набор `tools/test_*.py` (114): **105 PASS, 9 FAIL, ни один не связан с моей уборкой** (вывод ни одного не называет удалённых файлов):
- `test_knowledge_armor` — не тест, требует `--base`; `test_voicepack_audit` — нет модуля `soundfile`;
- `test_gentle_scope` — `CollapsePilot.cpp:1987` — чужая незакоммиченная правка src;
- `test_release_fresh` — дерево с чужими незакоммиченными src (проверка и должна падать);
- `test_battle_view` (48 «ракурс своими словами» в старых hdart-скриптах), `test_gpu_scripts` (40 ошибок списка `gpu_scripts.txt`, файл сейчас изменён чужой сессией), `test_collapse_lock_eol` (checkout/autocrlf), `test_floor_batch_variants` (`read_set` вернул None: нет данных игры), `test_gentle_determinism` (контрольный бой не изменил игру, нужны сейвы) — старые, не от этой уборки. `test_gpu_scripts` модель не грузит, запускал с `GPUQ_BYPASS=1`.

Новые три теста и `test_docker_ssh_guard`, `test_backslash_guard`, `test_game_guard`, `test_pack_guard`, `test_junction_guard`, `test_gpu_guard`, `test_recipe_guard`, `test_rake_check` — PASS.

## 5. Зеркало Codex (файлы на диске, в гите их нет)

`.codex/hooks/`: скопированы с `.claude/hooks/` (побайтно) `gpu-guard.ps1` (был старый, без сверки по имени файла), `guard-paths.ps1` (с правкой R-871), `docker-ssh-guard.ps1` (отсутствовал). Остальные 7 хуков уже совпадали. Теперь все 10 копий идентичны.
`.agents/skills/tickets/SKILL.md`: догнан с `.claude/skills/tickets` (правила командира, снимок `--keep`, один прогон на пачку) с заменой CLAUDE.md на AGENTS.md. Остальные skills отличаются только этой заменой.
Не трогал: `.codex/hooks.json` подключает только editq (ps1-хуки Codex туда не вписаны — решение, а не копия), `.codex/agents/*.toml` — переводы агентов, а не копии (нет `scout`; версии `ticket-*` не сверял построчно). Codex не запускался. Коммитить `.codex/` и `.agents/` (целиком неотслеживаемые) не стал: нужен твой выбор, нужны ли они в гите.

## 6. Стейдж

Шаг копирования в стейдж — `Invoke-ModStep` в `tools/build/build.ps1` (не Выпуск/release.ps1): `robocopy /MIR /XD /XF`. `/MIR` не стирает в приёмнике файлы, подпавшие под `/XF`, поэтому `hd.zip` (26,4 МБ) в `dist/_stage/user/mods/intro_voice` остался с 17.10. Добавлена зачистка по тем же спискам `ModExcludeFiles`/`ModExcludeDirs` сразу после robocopy (`-Filter`, не `-Include`, R-290). Разбор PowerShell — 0 ошибок; логику зачистки прогнал на временной папке (hd.zip, *.exe, *.pyc, preview/, __pycache__ ушли, остальное осталось). Выпуск не запускал. Устаревший `hd.zip` из `dist/_stage` удалён вручную; другого исключённого в `user/mods` стейджа нет (`dist/_stage/xp-bootstrap.exe` лежит в корне стейджа, не в моде).

## Не сделано / для решения

- Остальные 172 одноразовых `tNNN_*.py`, поколения, обвязка обрушения — по решению Vitali (раздел «Твоё решение» README).
- «Мёртвый код лаунчера (~1 000)» из README, пункт Г — вне списка этого задания, не трогал.
- Коммит `.codex/`, `.agents/` и строки RAKES.md чужих сессий.
