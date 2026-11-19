# Аудит кода — 2026-10-05

Заказ Vitali: глубокий аудит всего кода, порядок, оптимизация, удаление ненужных веток развития,
«лоск», всеми агентами; не мешать идущим процессам и не трогать файлы, с которыми работают; отчёт через час.
Старт 18:28, отчёт 19:25 (JST). Подотчёты агентов — папка `docs/research/code-audit-2026-10-05/`
(11 файлов, пути в тексте ниже).

## Рамки, которые я себе поставил

- **`src/` не правил вовсе.** Любая правка движка идёт через очередь `tools/editq.py`, требует сборки и дампов
  IDENTICAL (k=1 и k=4) — в час с идущими прогонами это не укладывается, а «почти верная» правка рендера хуже,
  чем её отсутствие. Все находки по `src/` — список для отдельной сессии (ниже, раздел 4).
- **Занятые файлы** — все 31 `M` и 231 `??` из `git status` на старте (снимок:
  `scratchpad/audit/protected_status.txt`) плюс скрипты идущих заданий очереди видеокарты
  (`prod_two_pass_v2/v1`, `strict_ctl_v1`, `obj_photo`, `photo_base`, `photo_render`, `weapon_*`, `agent_pose`,
  `tools/gpuq.py`, `tools/gpt_check.py`). Их не трогал, даже где находка очевидна (помечено «ЗАНЯТ»).
- **Агенты только читали.** 11 агентов (Explore, qa, optimizer, overseer, scout, git-warden и общие), каждый
  в своей области, с запретом на правки; все их отчёты лежат рядом как есть.
- **Удаление веток и worktree** классификатор режима auto отклонил («мешает идущим процессам») — команды
  готовы для Vitali (раздел 5), сам не добивался.

## 1. Что сделано (правки в незанятых, не-игровых файлах)

| Файл | Что | Зачем |
|---|---|---|
| `.claude/hooks/rake-check.ps1` | ответ хука несёт `hookSpecificOutput.additionalContext`, не только `systemMessage`; пути с прямыми косыми обрезаются до корня так же, как с обратными | **Дефект**: грабли по правимому файлу доходили только до человека в интерфейсе, модель их не видела (`.index/rake-hits.log` писал мои правки 18:42–18:45 без единого предупреждения в сессии). После починки предупреждения пошли в контекст — видно в этой же сессии. Абсолютный путь с `/` уходил в `rake.py` как есть, и глобы с папкой (`.claude/hooks/*.ps1`, R-055, R-151) не совпадали |
| `tools/test_rake_check.py` (новый) | тест хука: файл с граблями → в `additionalContext` все номера, которые даёт `rake.py match`; контроль `LICENSE` → хук молчит | защита найденного дефекта (протокол граблей: «наступил раз — запись, два — тест»). `py -3.13 tools/test_rake_check.py` — PASS |
| `docs/STATUS.md` | блок «Статус — 2026-10-05» (overseer) над записью 26.09 | состояние проекта 9 дней не обновлялось |
| `docs/SETUP.md:81` | `.index\files.md` → `.index\files.tsv` | битая ссылка |
| `tools/hdtest_README.md` | дописаны ручки `OXCE_HD_DUMP_FX_ONLY`, `OXCE_HD_DUMP_KILLCAM`, `OXCE_HD_SET`, `OXCE_HD_SAVES` | четыре getenv-ручки движка жили только в коде (`HdFx.cpp:565`, `HdKillCam.cpp:181`, `Game.cpp:522`, `MainMenuState.cpp:329`) |
| `docs/research/hd-glue-test.md` | пометка: переключателей `OXCE_HD_GLUE_*` в `src/` больше нет, код только в `E:/OpenXCom-glue` | документ читался как описание живой функции |
| `.claude/agents/director.md` | строка таблицы «Промпт графики боя → `view-keeper`» | агент был в frontmatter, но не в таблице выбора исполнителя |
| `.claude/agents/gpu-forge.md`, `coder.md`, `optimizer.md` | абзац «Очереди проекта»: gpuq, editq, battle_view, IDENTICAL с контролем R-086, цифры только из замера (R-091) | ни один из трёх не знал об очередях и о проверке IDENTICAL — агент-шаблон «под мод», не под этот проект |
| `.claude/skills/rake/SKILL.md` | `tests/test_r0NN_<кратко>.py` → `tools/test_<кратко>.py` | папки `tests/` в проекте нет, все тесты в `tools/` |
| `.claude/skills/index/SKILL.md` | `describe` — только через `gpuq.py add`; пометка, что `Doxyfile` для `--full` отсутствует | `describe_modules.py` в `tools/gpu_scripts.txt`, прямой запуск останавливает `gpu-guard`; `index --full` без `Doxyfile` не работает |
| `.claude/state/` | удалена пустая папка | мёртвая |
| `tools/index_project.py` | `stdout`/`stderr` переключены на UTF-8 в `main()` | **живой сбой**: хук `session-start` зовёт индексатор через трубу (cp1252), и тот падал на первой кириллице уже после пересборки — в этой сессии хук выдал «КАРТА: индексатор не отработал — Traceback». Проверено: запуск через трубу без `PYTHONIOENCODING` печатает «Индекс собран: 1734 файлов, 68069 символов» |
| `tools/game_hidden.py` | то же переключение потоков | та же беда при выводе в файл (R-001, третья сторона) |
| `tools/fix_bom.ps1` | `skipDirs`: `\.venv\` → `\.venv` | сканировал `.venv-sa3`, `.venv-qwen21` (тысячи чужих файлов); проверено запуском `-Path E:/OpenXCom` |

Все файлы с кириллицей — UTF-8 со спецификацией (проверено `od`); `.ps1` спецификацию сохранил.
Проверки: `py -3.13 tools/test_rake_check.py` → PASS; хук вживую: правка `.claude/hooks/rake-check.ps1`
в этой сессии показала R-002, R-055, R-090, R-151.

**Не сделано из безопасного списка и почему**: перенос 8 скриптов-сирот `tools/hdart` в `attic/` (у каждого
`sys.path.insert(0, HERE)` — после переноса ломаются импорты `tile_forge`/`xcom_sprites`, нужна правка каждого
файла по образцу `attic/ab_sdxl.py`; HD_PIPELINE_V2 §30 требует сначала `SCRIPT_STATUS.json`). Команды — раздел 5.

## 2. Тесты: 92 файла `tools/test_*.py` (подотчёт `07-tests.md`)

PASS 87, FAIL 2, SKIP 3.

- `test_battle_view.py` FAIL — 31 нарушение охвата (17 генераторов без блока ракурса, 14 пишут ракурс своими
  словами). Это долг, не поломка теста; список — `11-battle-view.md`. Переводить промпты на `battle_view`
  только со слова Vitali (R-112: одобренные промпты не менять ради «правильности»).
- `test_gpu_scripts.py` FAIL — 5 скриптов в `gpu_scripts.txt` без прямого импорта модели (`strict_ctl_v1`,
  `unit_parts`, `weapons_synth`, `weapons_redraw`, `agent_full`): грузят модель косвенно через `obj_photo`/
  `render_chunks`/`photo_ui`. Тесту нужен список исключений «запускатель модели», файл ЗАНЯТ.
- SKIP: `test_gentle_determinism` (нужна игра), `test_map_paint_input` (скрипт GPU), `test_voice_duplex` (gcc).
- `test_gpuq.py` идёт 161 с при лимите 180 — на грани.
- Мусор: `Выпуск/weekly/` появилась от чужой сессии; `game-guard` ложно срабатывает на текст heredoc с именем exe.

## 3. Ядро HD-рендера `src/Engine/Hd*` (подотчёты `01-src-hd-core.md`, `02-src-hd-ui.md`)

Проверено 1342 символа (543 холст и паки, 799 интерфейс) грепом по `src`. Мёртвого кода **7**:

| Где | Что | Чем опасно удаление |
|---|---|---|
| `HdCanvas.h:465` | `Canvas32::toneValue` | ничем — не вызывается |
| `HdCanvas.cpp:195-199`, `HdCanvas.h:291,463` | `setDeferred`, поле `_deferred` (всегда true), недостижимая ветка `else execute(...)` в `record()` (`HdCanvas.cpp:456-459`) | ничем |
| `HdUi.h:215` | `HdUi::cachedSurfaces` | ничем |
| `HdFont.h:69`, `HdFont.cpp:331` | `HdFont::clearCache` | ничем |
| `HdUiDraw.cpp:54` | `CAP_BIG`, `CAP_SMALL` | ничем |
| `HdRadar.cpp:48` | `FAR_OUT` | ничем |

Остальное по ядру: временных логов 0 (R-057, R-224 сняты); TODO в HD-коде 0; закомментированный блок
`ProjectileFlyBState.cpp:864-868` — апстрим Yankes 2017, оставить; `OXCE_HD_DUMP_FX` читается дважды
(`HdFx.cpp:573` и `:599`); два одинаковых FNV-64 цикла (`HdCanvas.cpp:680-708` и `:936-942`); дубли мелочи —
`luma` ×6 (целочисленная в `HdCanvas.cpp:2379` — не сводить, она на пути IDENTICAL), `packColor` = `HdUi::rgba`,
`withAlpha` ×2, смесители ×3. Все 32 опции `oxceHd*`/`oxceAdult*` живы и действуют; 11 из них нигде не
задокументированы (BattleHud, BattleHudColor, BlastArea, CraftOutlines, EnemyNumber, FirePace, GlobeScale,
Radar, Reticle, ReticleDamageColor, SmokePace); `oxceHdBaseAnim` действует после перезапуска, игроку не сказано.
getenv-ручек 29 (все тестовые, цены в кадре нет). Антипаттерны R-014/R-056/R-057 защищены.

**Один коммит через editq, когда очередь свободна** (кадр не меняет, после — сборка и дамп k=1/k=4):
удалить семь мёртвых символов, убрать повторный getenv `HdFx.cpp:599`, слить два FNV-цикла,
`packColor`→`rgba`, `withAlpha`→одна. Спорное на решение Vitali: лог `HD perf:` каждые 2 с у каждого игрока
(`HdCanvas.cpp:1276-1291`, ~600 строк за бой) и `HD interface: ms/frame` раз в 600 кадров (`HdUi.cpp:1125`);
`HD frame` раз в 2 с оставить — по нему стенд ловит зависший экран.

## 4. Изоляция механики от HD (подотчёт `03-mechanics-isolation.md`)

Рисование изолировано: в `Hd*` 0 обращений к RNG, только const-указатели на состояние боя. Но под меткой «HD»
в истории лежат **правки механики** — это нарушение правила 2 CLAUDE.md, и о нём надо знать:

| № | Где | Что меняет | Коммит |
|---|---|---|---|
| П1 | `GeoscapeState.cpp:3794-3816`, `RuleArcScript.cpp:96,102`, `RuleEventScript.cpp:111`, `RuleMissionScript.cpp:138`, `Mod.cpp:5286` (`getResearchOrPlaceholder`) | арки/события/миссии с «пустышками» исследований — поведение геоскейпа | `bde0ba3c3`, `03421b28a` |
| П2 | `BattlescapeGenerator.cpp:1236,1258,1288`, `ItemContainer.cpp:240` (`getContentsInListOrder`) | порядок раскладки предметов при старте боя — id предметов и авто-экипировка; **без флага** | `c4eb8720a` |
| П3 | `ProjectileFlyBState.cpp:404` `>= 2` вместо `> 2` | только камера | `699a5d520` |
| П4 | `Map.cpp:990-1003`, `Tile.cpp:727`, `SavedBattleGame.h:422` | Ctrl+F8 (`hdTestFreeze`) пишет `_animFrame` и анимацию тайлов — только при дампе | — |
| П5 | `UnitDieBState.cpp:275-278` | задержка kill-cam — только темп | — |
| П6 | `Ufo.cpp` `_hdDecoded` | поле в сейве | — |

П1 и П2 — решение Vitali: признать исключениями и записать в `docs/DECISIONS.md`, либо снять метку «HD» и
проверить парным боем (`tools/ai_probe.py`, одинаковый сейв и сид). `OXCE_AI_DEV` в `build-release` OFF
(`AiProbe` — заглушки), но `tools/build/build.ps1` этого не проверяет — одна строка в `Assert-*` закрыла бы риск.

## 5. Гит и ветки (подотчёт `10-git.md`)

Мусора и секретов в трекинге нет; `.git` 168 МБ; `hd-render` на 472 коммита впереди `origin`.
Ветки, влитые по содержимому (проверено `git cherry`: все коммиты «-») и годные к удалению; классификатор
отклонил их удаление из сессии, поэтому — команды Vitali, по одной на строку:

```bash
git worktree remove --force .claude/worktrees/elegant-gauss-40b634
```
```bash
git worktree remove --force .claude/worktrees/keen-robinson-8bc1d3
```
```bash
git worktree remove --force .claude/worktrees/vigorous-easley-829978
```
```bash
git worktree prune
```
```bash
git branch -d claude/elegant-gauss-40b634 claude/keen-robinson-8bc1d3 claude/vigorous-easley-829978 claude/gpuq-psutil
```
```bash
git branch -D worktree-agent-a9746e1040e51735b
```
```bash
git tag -a hd-render-before-8.7 017eb82bb -m "hd-render до слияния с OXCE 8.7"
```
```bash
git branch -d hd-render-before-8.7
```

`hdglue-test` влита, но дерево `E:/OpenXCom-glue` держит 5 изменённых `src` и `build-glue/` — незавершённый опыт
R-123; решает Vitali (удалить дерево и ветку или оставить как стенд). Push 472 коммитов — тоже его слово.

Перенос скриптов-сирот `tools/hdart` в `attic/` (после слова Vitali; у каждого перед этим заменить
`sys.path.insert(0, HERE)` на родительскую папку по образцу `attic/ab_sdxl.py:29`):

```bash
git mv tools/hdart/dupe_view.py tools/hdart/floor_sheets.py tools/hdart/list_ground_sets.py tools/hdart/map_hint_sheet.py tools/hdart/orig_sheet.py tools/hdart/pedia_compare.py tools/hdart/pedia_pick.py tools/hdart/sweep_sheet.py tools/hdart/attic/
```

## 6. Производительность — долг без цифр (подотчёт `04-perf.md`)

Цифры ускорения не называю (R-091): всё ниже — места, где код делает лишнее, порядок по ожидаемой цене.
Единственный замер в отчёте — существующий: первый кадр боя `toned` 67–91 мс.

1. `tonedFor` (`HdCanvas.cpp:2077-2154`), `blitScripted` (`:738-913`), `HdSprites::find→load` (`:395-421`) —
   затенение, перекраска и декод PNG на главном потоке при промахе кэша. Лечение: двухфазная запись с
   `pool.run` в `flush` плюс прогрев (`docs/HD_UNITS.md` разд. 9 — кода нет).
2. `HdFx.cpp:470-492` — декод клипов эффектов на главном потоке, мимо `pack_ms`.
3. `HdUiArt.cpp:71-84` `hashPixels` побайтовый FNV; `HdUi.cpp:602/744/819` — хэш каждой поверхности каждый кадр.
4. `Map.cpp:2063` — `std::vector<int> pixelMaskArray(4*k*k)` на каждый тайл; `Map.cpp:811-848` `updateHdLight` без кэша.
5. `Screen.cpp:225-232` — копия world→screen одним потоком.

Кэши без байтового бюджета: `HdUi::_sparse/_fitted/_glyphs`, `Canvas32::_spans`; ключ-указатель без проверки
содержимого: `Canvas32::_smooth/_spans` (класс R-056). `docs/PERF.md` устарел (таблица кэшей, закрытые пункты).

## 7. tools/hdart — 264 модуля (подотчёты `06-hdart.md`, `06-hdart-classes.tsv`)

ACTIVE 67, ACTIVE-LIB 93, FROZEN 30, LEGACY 51, SUPERSEDED 2, ORPHAN 9, ATTIC 12. Главное:

- **148 файлов не в гите** — весь стек v2 (relation/routing/derive_recolor/hd_e2e, photo_*, weapon_*, unit_*,
  `prod_two_pass_v1/v2`, `restore_batch_v1`), то есть всё, на чём идёт сегодняшнее производство (#408).
- 61 «замороженный» модуль держится в ACTIVE-LIB одной цепочкой `prod_two_pass_v2 → prod_two_pass_v1 →
  restore_batch_v1 / hd_e2e_v1_run → hd_e2e_v1` ради `sprite_frame` и чтения детекторов V7. Вынести их в
  тонкую библиотеку — и 61 модуль можно морозить физически.
- **Дыра `gpu-guard`**: хук матчит только basename первого скрипта после интерпретатора. `render_chunks.py`
  (Popen рендера после `--`, 29 постановок) и `agent_pose.py` (запускает `agent_full.py build`) не в
  `tools/gpu_scripts.txt` — прямой запуск пройдёт. Файл ЗАНЯТ, дописать через ту сессию.
- R-001: 44 модуля пишут с `encoding='utf-8'` при кириллице; 12 из них — md/tsv/txt/csv/log (`identity_auto` 7,
  `visual_judge` 4, `build_dataset` 2, `agent_full` 2, `agent_pose` 2, `tank_turret`, `weapon_judge`,
  `attic/keep_batch`, `base_pack`, `fx_map`, `gen_fx`, `score_batch`); 5 из 12 ЗАНЯТЫ.
- Каркас приёмок копируется файлом: `write_md` 34 копии, `do_report` 30, `do_check` 27. Либо `acceptance_kit.py`
  до следующей приёмки, либо принцип «одна приёмка — один файл» (удобен для заморозки sha256) — слово Vitali.
- Семейств версий 15 (57 файлов); формально SUPERSEDED только 2, потому что каждая vN+1 импортирует vN.

## 8. Документация (подотчёт `08-docs.md`)

- `docs/RAKES.md` — 1398 строк, 329 КБ, 150 записей (CLAUDE.md просит ~150 строк); 69 без защиты; со счётчиком ≥2
  и без защиты 9 (R-010, R-071, R-167, R-177, R-208, R-210, R-211, R-217, R-227). Предложение выноса по областям
  (как уже сделано для aibench/portal): `docs/rakes/hdart.md` — 79 номеров, `docs/rakes/engine.md` — 32 номера
  (списки `scratchpad/audit/rakes_move_hdart.txt`, `rakes_move_engine.txt`); в контексте останется ~86 КБ вместо 325.
  Файл ЗАНЯТ — не трогал.
- `docs/DECISIONS.md` — 480 КБ, 107 записей, 10 цепочек противоречий (способ рисования предметов, два разных «V7»,
  нарушен порядок дат). Нужна сводная запись «как рисуем предметы сегодня». ЗАНЯТ.
- Битые ссылки: `CLAUDE.md:38` `census/` → `tools/` (ЗАНЯТ); `HD_PIPELINE_V2.md:975` `SCRIPT_STATUS.json` нет на
  диске (ЗАНЯТ); R-007 ссылается на `photo_hints.txt`, его нет; `AI_TRAINING.md` называет ~25 скриптов не в гите.
- `docs/research/`: 65 из 96 файлов не упомянуты в `README.md` (ЗАНЯТ — ссылку на этот отчёт туда не добавил).
- `docs/ART_STATUS.md` 13 дней не пересчитан (`tools/art_status.py`).

## 9. Конфигурация Claude (подотчёт `09-claude-config.md`)

- `guard-paths.ps1` (ЗАНЯТ) читает stdin в IBM437 — кириллический запрет `Пиратки/` может не срабатывать;
  `build-ai*/` не защищены. Предложение: `deny` на `Пиратки/**` в `permissions` settings.json.
- Пачка `pack-guard` (`pack-guard.ps1`, `build_hd_pack.py`, `test_pack_guard.py`, `HD_PIPELINE_V2.md`,
  `settings.json`, `AGENTS.md`, `gpt_check.py`, skill `gpt-check`) не в гите.
- 4 хука без тестов: `bom-guard`, `guard-paths`, `session-start` (для `rake-check` тест теперь есть).
- `.index/rake-hits.log` 628 КБ без ротации; `.claude/worktrees` 107 МБ (команды в разделе 5);
  `settings.local.json` — 28 allow-правил с мусором (`Bash(py -3 -)`, `Bash(git commit *)`, чужие scratchpad).
- `LOCAL_MODEL=qwen3.8:27b` не совпадает с именем модели в Ollama (`orcarouter/Qwen3.8-27B-Uncensored:q5_K_M`).
- Агенты `asset-smith`/`artist`/`ship`/`feature` — шаблон «под мод» (`assets/`, `gen_gpu.py`), не под проект;
  skill `ship` и `Выпуск/OXCE_Release.cmd` — два способа выпуска.

## 10. battle_view (подотчёт `11-battle-view.md`)

57 скриптов с моделью: USES 4, MISSING 17, no-words 14, NOT_BATTLE 14, NO_PROMPT 6, PROTECTED 2.
`prompt_block` против `docs/research/battle-render.md` — без противоречий; `DIRV`/`DIR_VEC` совпадают с движком.
Противоречие по тени у `ground_relief`. Перевод промптов — только со слова Vitali.

## 10а. tools/ — ядро, сборка, очереди, portal (подотчёт `05-tools-core.md`)

- Сирот 8 из 129 не-тестов: `hd_coverage.py` (вытеснен `art_status.py`), `hd_match_report.py`,
  `aibench/geo_report.py`, `ai_speed/blocked_step.py`, `merge/merge_upstream_87.ps1` (одноразовое, выполнено),
  `sfx/listen_page.py`, `xpiratez_stat_report.py` (PyYAML вопреки R-046), `piratez_weapons.py` (ЗАНЯТ).
  63 из 92 тестов не в гите.
- `py -3` без версии (R-101/R-139): 141 упоминание; исполняются в `settings.json` (4 строки editq, ЗАНЯТ),
  `session-start.ps1:54`, `portal/publish.ps1:27`; подсказки в `CLAUDE.md:90,99,110,111` (ЗАНЯТ), `editq.py` (15),
  `gpu-guard.ps1:106`, `gpuq.py` (ЗАНЯТ, сам себя перезапускает). Не менял: `gpuq.py` и `editq.py` живут под
  `py -3` по CLAUDE.md, менять надо все вместе одним решением.
- `fix_bom.ps1` после правки `skipDirs` (59 скриптов вместо тысяч чужих): без BOM-проблем, LF вместо CRLF у трёх —
  `Выпуск/release.ps1` (зовёт автовыпуск editq, не трогал), `tools/hdart/gen_all.ps1`, `tools/hdart/setup_qwen21.ps1`;
  чинится `tools/fix_bom.ps1 -Fix` в спокойную минуту. `settings.local.json:9` разрешает `Bash(py -3 -)` (запрещено R-184).
- Четыре запускателя игры: `game_hidden.py`, `ai_probe.Hidden`, `unit_perf.py` и `measure_hd.ps1` — последний
  видимый `Start-Process` (R-124 против R-091, который зовёт его источником замеров) — решение Vitali.
  «Временная установка из соединений» повторена в `launcher_smoke`, `builds_accept`, `compat/xcf_probe`,
  `aibench/run_series`; `index_mod.py` и `rul_map.py` оба разбирают рулсеты Пираток.
- Остатки: дубль `hd_demo_mod/make_demo_frames.py` = `hd_test_mod/make_demo_frames.py`; `gen_gpu.py` (мост
  ComfyUI, на него ссылается `gpu-forge.md`); `optimize_assets.ps1` работает с несуществующей папкой `assets/`;
  `ai_speed/` — 30 одноразовых переписей с повторённым чтением gzip-логов (заморозить или чистить).
- Хуки: все вызываемые скрипты существуют; без тестов `bom-guard`, `guard-paths`, `session-start`
  (`rake-check` — тест с сегодняшнего дня).

## 11. Решения за Vitali (сводно)

1. П1/П2 (раздел 4): исключения в DECISIONS или снять метку HD и проверить парным боем.
2. Вынос RAKES в `docs/rakes/hdart.md` и `engine.md` по готовым спискам.
3. Коммит 148 файлов `tools/hdart` как есть или сначала раскладка (`attic/`, `frozen/`, `SCRIPT_STATUS.json`).
4. `gpu_scripts.txt`: дописать `render_chunks.py`, `agent_pose.py`; решить судьбу 5 «CPU»-строк и `unit_refit`
   (остановлен по R-208); нужна ли очередь Codex-скриптам (`weapon_judge`, `visual_judge`, `identity_auto`,
   `weapons_chatgpt`) как сериализация.
5. Логи `HD perf` каждые 2 с и `HD interface` раз в 600 кадров — под условие или оставить.
6. Один коммит мёртвого кода ядра HD (раздел 3) и перф-долг (раздел 6) — кому и когда.
7. `CLAUDE.md:38` `census/`→`tools/`; `guard-paths` кодировка и `deny` на `Пиратки/**`; `LOCAL_MODEL`.
8. `E:/OpenXCom-glue` и ветка `hdglue-test`; push 472 коммитов.
9. Проверка `OXCE_AI_DEV=OFF` в `build.ps1`.
10. DECISIONS: сводная запись о способе рисования предметов и развести два «V7».
11. `py -3` → `py -3.13` разом в CLAUDE.md, `settings.json`, `editq.py`, `gpuq.py`, хуках; судьба `measure_hd.ps1`;
    `ai_speed/` и 8 сирот `tools/` — в attic или удалить.

## 12. Грабли — записаны в RAKES.md как R-233 (19:25, `rake.py add` + `disarm`)

```
## R-233  Хук отдаёт грабли в systemMessage - их видит человек, а модель правит без предупреждения
Статус:   обезврежены
Файлы:    .claude/hooks/*.ps1, .claude/settings.json
Симптом:  .index/rake-hits.log пишет каждую правку, а в сессии ни одного предупреждения о граблях; кажется, что хук не работает вовсе (R-055), хотя он честно отрабатывает
Причина:  Модели доходит только hookSpecificOutput.additionalContext; systemMessage показывается в интерфейсе человеку. Второе: путь с прямыми косыми не обрезался до корня (StartsWith против обратных), и rake.py получал абсолютный путь - глобы с папкой не совпадали
Правило:  Всё, что хук хочет сказать МОДЕЛИ, - в hookSpecificOutput.additionalContext; systemMessage - только дубль для человека. Пути в хуках приводить к одному виду косых до сравнения с корнем. Хук проверять тестом по JSON-ответу, а не по логу попаданий
Защита:   tools/test_rake_check.py (контроль: файл без граблей - пустой ответ)
Наступал: 1   Последний: 2026-10-05
```

## Оговорки

- Ссылка на этот отчёт в `docs/research/README.md` не добавлена — файл занят другой сессией.
- В первой волне ничего из `src/`, `bin/`, модов, очередей и идущих заданий не менялось. Во второй волне (ниже) `src/Engine/Hd*` правились через очередь правок, билет #171, коммит `b584d763c`.

## 13. Вторая волна, 19:15–19:45 (по слову Vitali «делай всё»)

**Сделано.**

- **Спецификация на записи** — 7 мест в 5 файлах: `gen_fx.py:1197` (hit_styles.txt), `tank_turret.py:732`, `pedia_review.py:150` (report.csv), `agent_pose.py:507,509` и `agent_full.py:584,586` (color.txt — `HdSprites::readColour` спецификацию снимает сам). Оставлено 8 мест с причиной: `.anim.txt` и `hd/FX/weapons.txt` читает игра через `getline`/`>>` без снятия спецификации (`HdBase.cpp`, `HdFx.cpp:85`); подписи, `metadata.csv`, `dataset.toml` читает тренер; `.rul`/`.yml`/JSON не трогаем. `test_base_pack.py`, `test_ai_arena_contract.py` — OK.
- **Мёртвый код HD-ядра** — коммит `b584d763c`, 8 файлов, +7 −36: `toneValue`, `setDeferred`/`_deferred` (поле было всегда `true`, ветка `else` в `Canvas32::record` недостижима), `HdUi::cachedSurfaces`, `HdFont::clearCache`, `CAP_BIG`/`CAP_SMALL`, `FAR_OUT`; `getenv` в `HdFx::takeTestDump` читается один раз. Сборка без новых предупреждений в своих файлах. Режим 0, k=1, прежний exe против нового: геоскейп (сейв, 100 с) и главное меню — 0 отличающихся пикселей. **Оговорка:** бой не дампился (сейв геоскейпа), довод по `record()` статический; контрольного DIFFERENT не делалось — правка ничего видимого не меняет. Автовыпуск после `editq done` отменён.
- **`py -3` → `py -3.13`** — 171 строка в 81 файле агентом плюс 9 строк в 5 файлах вручную (`agent_full.py`, `agent_pose.py`, `pedia_review.py`, `docs/SETUP.md`, `tools/hdtest_README.md`). Из `.claude/settings.local.json` убрано разрешение `Bash(py -3 -)` (R-184). Тесты `test_backslash_guard`, `test_gpuq`, `test_editq`, `test_game_guard` до и после — код 0. Осталось 84 строки: занятые файлы (`CLAUDE.md` 4, `settings.json` 4, `RAKES.md` 8, `gpuq.py` 5, `gpt_check.py` 5, `skills/gpt-check/SKILL.md` 6, хуки 2, `tools/hdart` 12, `test_gpuq.py` и `test_backslash_guard.py` по 1), намеренные (входы тестов хуков, исторические доки, этот аудит), `tools/hdart/attic` 6.
- **Грабли R-233** записаны через `rake.py add` и обезврежены (`disarm`, `tools/test_rake_check.py`). Хук теперь показывает грабли модели — подтверждено вживую на правке этого файла.
- **`fix_bom.ps1 -Fix`** (запустил Vitali): три `.ps1` переведены на CRLF; для гита содержание не изменилось (индекс LF, `text=auto`).
- Утверждение агента «инструмент Edit обрезает пробел в конце new_string» **не подтвердилось**: проба на файле — пробел сохранён; склейки `py -3.13tools` были ошибкой самого агента, исправлены им и проверены по кускам диффа. В грабли не записано.

**Классификатор auto-режима запретил мне две операции — их выполнил Vitali руками (19:50–20:05).**

Ветки и worktree (все три worktree чистые, их ветки слиты, 0 коммитов впереди; у `worktree-agent-…` 13 коммитов, все уже в `hd-render` по `git cherry`) — выполнено Vitali, все команды прошли без ошибок:

```
git worktree remove .claude/worktrees/elegant-gauss-40b634
git worktree remove .claude/worktrees/keen-robinson-8bc1d3
git worktree remove .claude/worktrees/vigorous-easley-829978
git worktree prune
git branch -d claude/elegant-gauss-40b634 claude/gpuq-psutil claude/keen-robinson-8bc1d3 claude/vigorous-easley-829978
git branch -D worktree-agent-a9746e1040e51735b
git tag hd-render-before-8.7 017eb82bb
```

Сироты в `tools/attic/` (раздел 10а; все под гитом, поэтому `git mv`; `tools/ai_speed/` — 35 файлов, все в гите) — выполнено Vitali, в индексе 42 переноса (`R`, содержимое не менялось). Первая попытка упала на `fatal: destination 'tools/attic/' is not a directory`: `git mv` папку не создаёт, помог `mkdir tools/attic`.

```
git mv tools/hd_coverage.py tools/hd_match_report.py tools/xpiratez_stat_report.py tools/optimize_assets.ps1 tools/attic/
git mv tools/aibench/geo_report.py tools/attic/aibench_geo_report.py
git mv tools/merge/merge_upstream_87.ps1 tools/attic/merge_upstream_87.ps1
git mv tools/sfx/listen_page.py tools/attic/sfx_listen_page.py
git mv tools/ai_speed tools/attic/ai_speed
```

Поправка к разделу 10а после переноса: `tools/ai_speed/` сиротой **не был** — `tools/test_blocked_pair.py` (защита R-176) импортирует из него `blocked_pair` и `blocked_kr` и после переноса упал с `ModuleNotFoundError`. Тест перенаправлен на `attic/ai_speed`, прогон — `итог: OK`. Прочие ссылки на старые пути: таблица `tools/README.md` (строка `optimize_assets.ps1` поправлена), шесть строк комментариев в `tools/ai_probe.py` (`tools/ai_speed/README.md` — ссылка на приёмку флагов стенда; файл стенда ИИ, оставлен его сессии) и отчёты в `docs/research/` и `docs/rakes/aibench.md` (история, не правятся).

`tools/gen_gpu.py` и дубль `make_demo_frames.py` (hd_demo_mod / hd_test_mod) — решение по подотчёту 05, перед переносом грепнуть ссылки ещё раз.

Дыра gpu-guard (`render_chunks.py`, `agent_pose.py` не в `tools/gpu_scripts.txt`): файл в активной правке другой сессии (диф +33 строки), не трогал; её `test_gpu_scripts.py` сейчас даёт 5 ошибок по её же правке.
