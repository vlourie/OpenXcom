# Аудит инфраструктуры агентов (.claude, хуки, skills, очереди)
Дата: 2026-10-05 | Режим: только чтение (в E:\OpenXCom ничего не менялось) | Уверенность: высокая там, где есть улика; «средняя» помечена

Пометка «ЗАНЯТ» - файл в protected_status.txt (правят другие сессии): .claude/settings.json, .claude/hooks/backslash-guard.ps1, .claude/hooks/guard-paths.ps1, .claude/launch.json, CLAUDE.md, AGENTS.md, tools/gpu_scripts.txt, tools/gpuq.py, docs/RAKES.md.

Что запускал: тесты `tools/test_backslash_guard.py`, `test_game_guard.py`, `test_gpu_guard.py`, `test_pack_guard.py`, `test_gpu_scripts.py` (все читают, модель не грузят), `ollama list`, замер времени каждого ps1-хука на пустой команде `ls`, `py -3 tools/editq.py hook pre` на той же команде, `tools/rake.py match` на тестовом пути. test_editq.py не запускал (трогает состояние очереди).

---------------------------------------------------------------------

## 1. .claude/settings.json (ЗАНЯТ) - хуки и permissions

### 1.1 Таблица хуков

| # | Событие / матчер | Команда | Скрипт на диске | R-055 | Таймаут |
|---|---|---|---|---|---|
| 1 | SessionStart / (все) | `& "$env:CLAUDE_PROJECT_DIR/.claude/hooks/session-start.ps1"` | есть | да | 120 |
| 2 | PostToolUse / Edit\|Write | bom-guard.ps1 (тот же вид вызова) | есть | да | 15 |
| 3 | PostToolUse / Edit\|Write | `py -3 "$CLAUDE_PROJECT_DIR/tools/editq.py" hook post` (без `shell`, значит оболочка по умолчанию) | tools/editq.py есть | не применимо (не ps1) | 20 |
| 4 | Stop / (все) | `py -3 ... editq.py hook stop` | есть | не применимо | 20 |
| 5 | PreToolUse / Bash\|PowerShell | backslash-guard.ps1 (ЗАНЯТ) | есть | да | 15 |
| 6 | то же | gpu-guard.ps1 | есть | да | 15 |
| 7 | то же | game-guard.ps1 | есть | да | 15 |
| 8 | то же | pack-guard.ps1 | есть, но в гите НЕ отслеживается (`??`) | да | 15 |
| 9 | то же | `py -3 ... editq.py hook pre` | есть | не применимо | 20 |
| 10 | PreToolUse / Edit\|Write\|NotebookEdit | `py -3 ... editq.py hook pre` | есть | не применимо | 20 |
| 11 | то же | guard-paths.ps1 (ЗАНЯТ) | есть | да | 15 |
| 12 | то же | rake-check.ps1 | есть | да | 20 |

- Хуков на несуществующие скрипты: **0**. Скриптов-сирот в .claude/hooks/: **0** (все 8 ps1 упомянуты).
- Все 7 powershell-хуков вызваны по R-055 (`& "$env:CLAUDE_PROJECT_DIR/..."`). Нарушений нет.
- Задержка: каждый ps1-хук на пустой команде 280-340 мс (замер: backslash 280, gpu 336, game 342, pack 296), `editq hook pre` 135 мс. Если Claude Code гонит хуки одного матчера параллельно - около 0,35 с на каждый вызов Bash; если по очереди - около 1,3 с. Не проверял, как именно.
- `py -3` сейчас = Python 3.14.7 (R-139). editq.py, rake.py и index_project.py используют только stdlib (импорты проверены), поэтому хуки работают; но зависимость от «самого нового питона» хрупкая: достаточно одного `import psutil` в editq.
- PostToolUse-хук editq (#3) не стоит на NotebookEdit, тогда как PreToolUse (#10) стоит. Правка ноутбука билет берёт, а «post» не вызывается. Мелочь.
- Правки файлов через `Bash` (python-скрипт, sed) editq не видит: это R-108, в settings это не закрыто.

### 1.2 Находки по хукам

| Находка | Улика | Уверенность |
|---|---|---|
| **rake-check выводит предупреждение через `systemMessage` - модель его, судя по всему, не получает.** Хук нашёл грабли (запись в .index/rake-hits.log сделана), но текста «ГРАБЛИ на ...» в результате вызова нет. `systemMessage` в Claude Code - сообщение пользователю; для модели нужно `hookSpecificOutput.additionalContext` (так сделаны bom-guard и session-start). | rake-check.ps1:~58 `@{ systemMessage = ... }`; в этой сессии я записал `scratchpad/audit/dbg2.ps1`: в rake-hits.log появилась строка `2026-10-05T18:34:13 ...\dbg2.ps1` (совпало R-001 `*.ps1`), а в моём ответе на Write пришёл только текст bom-guard, без «ГРАБЛИ». Это ровно тот сценарий, ради которого хук написан (CLAUDE.md и RAKES.md: «хук показывает их перед правкой») | средняя (не проверял документацию версии Claude Code; улика косвенная, одна запись) |
| **guard-paths.ps1 (ЗАНЯТ): кириллический шаблон `(^|/)Пиратки/` читает stdin в IBM437.** Скрипт ставит только `[Console]::OutputEncoding`, а `InputEncoding` не трогает. Воспроизведение: JSON с путём `E:/OpenXCom/Пиратки/a.txt`, поданный на stdin powershell 5.1, даёт `InputEncoding=IBM437`, длину пути 32 вместо 25 символов и `-match 'Пиратки'` = False (шаблон собран из кодов символов, чтобы исключить влияние кодировки самого скрипта). В живой сессии кодовая страница консоли хука может быть другой, но UTF-8 она не будет. Тогда запрет «Пиратки/ - только чтение» не срабатывает; срабатывают только ASCII-ветки (bin/UFO, bin/TFTD, build-release, dist, user/mods/hd/hd - последняя новая, ASCII, сработает). | воспроизведено вне сессии на тестовом stdin: scratchpad/audit/dbg2.ps1. В живой сессии не проверял: запись в Пиратки для пробы запрещена правилами аудита | средняя-высокая |
| guard-paths: у ветки `game/` нет объекта (`ls game` - нет такого каталога; в .gitignore есть `/game`, но каталога нет), а build-ai*/ (build-ai, build-ai10 ... build-ai17+) не защищены - только `build-release/`. `bin/TFTD` защищён и существует. | find по дереву, guard-paths.ps1 список `$denied` | высокая |
| На guard-paths нет теста (`tools/test_*paths*` - нет). Кириллическая ветка вообще ничем не проверяется - отсюда и находка выше. | см. раздел 2 | высокая |
| pack-guard и всё, что с ним связано, не в гите: `.claude/hooks/pack-guard.ps1`, `tools/test_pack_guard.py`, `tools/hdart/build_hd_pack.py`, `docs/HD_PIPELINE_V2.md` - все `??`. Если закоммитить settings.json без этих файлов, хук #8 станет «ошибкой неблокирующей» (как в R-055: молча не выполняется). | `git ls-files --error-unmatch` по четырём путям - ни один не известен гиту | высокая |
| gpu-guard: обход одним словом `GPUQ_BYPASS=1` в любом месте команды (R-127 уже записана). Список скриптов сопоставляется по имени файла без пути: общие имена (`run2.py`, `sweep.sh`, `run18.sh`) совпадут с чужим файлом из другой папки. | gpu-guard.ps1 Test-Command; gpu_scripts.txt строки run2.py, sweep.sh | высокая (по коду); ложные срабатывания не воспроизводил |
| game-guard и pack-guard применяются к `Bash\|PowerShell`; запись в Пиратки через Bash (`cp`, `>`) guard-paths (Edit/Write) не покрывает вообще, pack-guard - только `mods/hd/hd`. | матчеры в settings.json | высокая |

### 1.3 permissions

settings.json (ЗАНЯТ):

| Правило | Замечание |
|---|---|
| allow `Bash(python tools/:*)` | В проекте везде `py -3` / `py -3.13`, а правило покрывает только `python tools/...`. Реальные вызовы `py -3.13 tools/...` идут через локальный список или запрос. |
| allow `Bash(git add:*)` | Хук editq запрещает `git add -A/.`, но само разрешение широкое. Противоречия allow/deny нет. |
| ask: `git push`, `git reset`, `git rebase`; deny: `git push --force`, `rm -rf` | `git push --force:*` в deny + `git push:*` в ask - конфликта нет (deny приоритетнее). `rm -rf:*` ловит только эту форму (`rm -fr`, `rm -r -f`, `Remove-Item -Recurse -Force` проходят). Нет `git stash`, `git checkout --`, `git reset --hard` в ask/deny, хотя R-152 запрещает их в общем дереве (`git reset` в ask - частично закрывает). |
| deny на запись в Пиратки/bin/UFO на уровне permissions отсутствует | Защита держится только на guard-paths (см. находку про IBM437). Вторая страховка: `Edit(Пиратки/**)`, `Write(Пиратки/**)`, `Edit(bin/UFO/**)` в deny - движок разбирает UTF-8 сам. |

settings.local.json (в гите не лежит, личный): 28 allow-правил, это накопленный мусор разовых команд:

| Тип | Примеры | Проблема |
|---|---|---|
| Привязка к чужим сессиям | пути `scratchpad` сессий `393c2d37-...` и `05fcb89f-...` | эти блокноты исчезнут, правила мёртвые |
| Несуществующие файлы | `tools/hdart/prompt_writer.py` и `tools/hdart/paint3.py` (теперь в `tools/hdart/attic/`), `hdart_sheets_pz/CORP.PCK/...` (каталога нет) | устаревшие пути |
| Опасно широкие | `Bash(py -3 -)`, `Bash(py -3 -c ' *)`, `Bash(git commit *)`, `Bash(export PYTHONIOENCODING=utf-8)` | `py -3 -` - это именно запуск программы со stdin (R-184); хук backslash-guard его блокирует, но разрешение лежит в списке. `git commit *` позволяет коммитить мимо editq done. |
| Пути вне проекта | `E:/train/DiffSynth-Studio`, `E:/train/model_paths.json`, `.venv-train` (существуют) | нормально, но привязано к машине |
| Дубли | `py -3.13 tools/gpuq.py list` / `--help` / `resume` | `resume` разрешён без вопросов - возобновляет очередь |

Рекомендация: вычистить список (раздел «Безопасно применить»).

---------------------------------------------------------------------

## 2. .claude/hooks/*.ps1 - BOM, зависимости, тесты

BOM проверен `head -c3`: все 8 файлов `EF BB BF`.

| Хук | BOM | Зовёт tools/*.py | Они существуют | Тест | Тест есть | Тест прошёл (мой запуск) |
|---|---|---|---|---|---|---|
| backslash-guard.ps1 (ЗАНЯТ) | да | нет | - | tools/test_backslash_guard.py | да | «всё верно» |
| bom-guard.ps1 | да | нет | - | нет | **нет** | - (в этой сессии сработал вживую на моём Write dbg2.ps1) |
| game-guard.ps1 | да | нет | - | tools/test_game_guard.py | да | «всё верно» |
| gpu-guard.ps1 | да | читает tools/gpu_scripts.txt; тест по полноте - tools/test_gpu_scripts.py | да | tools/test_gpu_guard.py | да | «всё верно» |
| guard-paths.ps1 (ЗАНЯТ) | да | нет | - | нет | **нет** | - |
| pack-guard.ps1 (не в гите) | да | упоминает tools/hdart/build_hd_pack.py (в сообщении и в исключении) | да (не в гите) | tools/test_pack_guard.py | да (не в гите) | «итог: всё прошло» |
| rake-check.ps1 | да | `python tools/rake.py match` | да | нет | **нет** | - (rake.py match вручную с кириллическим путём работает) |
| session-start.ps1 | да | `python tools/index_project.py --if-stale --quiet`, `python tools/rake.py list --short`, `py -3 tools/editq.py brief` | да, все три | нет | **нет** | - |
| (не ps1) editq hook pre/post/stop | - | tools/editq.py | да | tools/test_editq.py | да | не запускал |

Без теста: 4 из 8 (bom-guard, guard-paths, rake-check, session-start). Для guard-paths тест особенно нужен (находка выше), для rake-check - проверка, что вывод доходит до модели (находка выше).

Прочее по хукам:
- session-start.ps1 и rake-check.ps1 вызывают `python` (в PATH сейчас Python 3.13.7, есть заглушка `WindowsApps\python3`). Остальной проект - `py -3.13`. Если `python` из PATH исчезнет, session-start молча выдаёт «Карты проекта нет» / не печатает грабли (весь блок под `if ($py ...)`).
- session-start печатает `.index/files.md`-строку только если файл есть; файла нет (раздел 7), строка не печатается - это нормально.
- rake-check пишет `.index/rake-hits.log`: 628 КБ, 10 227 строк, без ротации; пишет и пути вне репозитория (блокнот сессии). Лог в `.index/` (игнорируется).

---------------------------------------------------------------------

## 3. .claude/agents/*.md (12 агентов)

| Агент | model | tools | Ссылки на несуществующее |
|---|---|---|---|
| artist | sonnet | Read, Write, Edit, Glob, Grep, Bash | `assets/ref/<...>`, `docs/assets/<имя>.spec.md` (каталог docs/assets есть, но там только README и один png) |
| asset-smith | sonnet | Read, Write, Glob, Grep, Bash | `assets/10_generated` -> `20_optimized` -> `30_final`: **каталога assets/ в проекте нет** |
| coder | opus | Read, Grep, Glob, Edit, Write, Bash, TodoWrite | нет |
| director | opus | ..., `Agent(scout, coder, artist, gpu-forge, asset-smith, view-keeper, optimizer, git-warden, overseer, qa, scribe)` | **все 11 имён существуют**; но в таблице «Кого на что звать» нет `view-keeper` |
| git-warden | haiku | Read, Grep, Glob, `Bash(git *)`, `Bash(du *)`, `Bash(ls *)` | нет |
| gpu-forge | sonnet | Read, Write, Glob, Grep, Bash | `tools/gen_gpu.py --check` (файл есть - мост к ComfyUI/A1111 на портах 8188/7860, в проекте не используется; ни `gpuq`, ни diffusers, ни Qwen-Image там нет), `assets/10_generated/<имя>/` (каталога нет) |
| optimizer | opus | Read, Grep, Glob, Edit, Bash, TodoWrite | нет |
| overseer | sonnet | Read, Grep, Glob, Write, Edit, `Bash(git *)`, `Bash(ls *)`, `Bash(du *)`, `Bash(find *)` | нет; `docs/STATUS.md` последний раз менялся 2026-09-26 |
| qa | sonnet | Read, Grep, Glob, Bash, Write | нет |
| scout | sonnet | Read, Grep, Glob, WebSearch, WebFetch, Bash, Write | в шаблоне `путь/к/файлу.cpp:123` (это пример, не ссылка) |
| scribe | haiku | Read, Grep, Glob, Write, Edit, `Bash(git log *)`, `Bash(git diff *)`, `Bash(git tag *)` | нет |
| view-keeper | sonnet | Read, Grep, Glob, Bash | нет (tools/hdart/battle_view.py есть) |

Ссылок на несуществующих агентов (`Agent(...)`): **0**. Проверил все пути, упомянутые в агентах и skills скриптом (`scratchpad/audit/paths.py`): отсутствуют только `.index/files.md`, `docs/research/sprite-format.md` (skill rake, пример), шаблонный путь scout.

Расхождения с реальным конвейером:

| Что | Улика | Следствие |
|---|---|---|
| Ни один агент не упоминает `editq` (очередь правок) и `gpuq` (очередь карты) | `grep -n "editq\|gpuq\|gpu_scripts" .claude/agents/*.md` - пусто | `coder`/`optimizer` правят `src/` и узнают об очереди только от хука-отказа; `gpu-forge` по тексту запускает генерацию напрямую - gpu-guard это остановит |
| Конвейер ассетов в agents/skills `assets/00..30` + `docs/assets/*.spec.md` + `tools/gen_gpu.py` не совпадает с реальным (`art/`, `tools/hdart/`, `gpuq`, view-keeper, Qwen/diffusers). Реальная работа идёт мимо этих агентов. | `ls assets` - нет; `art/README.md`; `tools/gen_gpu.py` - мост к ComfyUI/A1111; CLAUDE.md «Карта проекта» | agents `gpu-forge`, `asset-smith`, `artist` и skill `asset` - шаблон другого проекта; `asset-smith`/`gpu-forge` пересекаются по назначению (оба «путь от сырого PNG к игре») с реальными tools/hdart/*, которые никакой агент не описывает |
| `qa.md` не содержит ни `hdtest_compare`, ни IDENTICAL, ни Definition of Done проекта (проверено grep) | grep по agents: пусто | приёмка по шаблону, а не по «режим 0 при k=1 побайтно» |
| `git-warden` по тексту «ничего не коммитит», а tools-строка `Bash(git *)` разрешает и commit, и stash, и reset | git-warden.md строки 1-6 | запрет только словами. Для `overseer` то же + Write/Edit |
| Директор и warmup требуют прочитать `docs/DECISIONS.md` целиком, а в нём 1968 строк / 480 КБ (AGENTS.md: «грепом по теме») | wc -lc | выполнить буквально нельзя |

Дубли по назначению: `gpu-forge` / `asset-smith` / `artist` (см. выше) - единый шаблонный цикл; `overseer` и skill `status` - одно и то же (skill просто вызывает overseer).

---------------------------------------------------------------------

## 4. .claude/skills/*/SKILL.md (9 skills)

| Skill | allowed-tools / зовёт | Существует | Замечания |
|---|---|---|---|
| asset | Agent(artist, gpu-forge, asset-smith, scout, qa, view-keeper) | все | пути `docs/assets/`, `assets/10_generated|20_optimized|30_final` - assets/ нет. Не упоминает gpuq |
| feature | Agent(director, scout, coder, qa, git-warden, scribe); `docs/PROJECT.md`, `docs/QA/`, `CHANGELOG.md` | все | про editq не говорит; дублирует работу director (skill «передай задачу director») |
| gpt-check (не в гите) | `Bash(py -3 tools/gpt_check.py:*)`, `Bash(git *)`; tools/gpt_check.py, AGENTS.md | да (оба не в гите) | `py -3` = 3.14.7; сам скрипт — stdlib. codex в PATH (`AppData\Roaming\npm\codex`). `Bash(git *)` шире нужного. Ссылается на `.gptcheck/`: каталог есть, в .gitignore строка добавлена, но не закоммичена |
| index | Read, Glob, Grep, Bash; `python tools/index_project.py [--full]`, `python tools/describe_modules.py` | оба есть | `--full` требует Doxyfile - **Doxyfile в корне нет**; `describe_modules.py` стоит в gpu_scripts.txt (Ollama) - напрямую его запустить хук запретит, skill про gpuq молчит; модель `qwen3.8:27b` (LOCAL_MODEL) - в `ollama list` только `orcarouter/Qwen3.8-27B-Uncensored:q5_K_M` |
| rake | `Bash(python tools/rake.py:*)`; `rake.py list/hit/disarm/add` | есть | тест советует класть в `tests/test_r0NN_*.py` - каталога `tests/` нет, проект кладёт тесты в `tools/test_*.py`; формат `rake.py add` с многострочным `\` в Bash — под backslash-guard (R-035) |
| research | Agent(scout) | есть | дублирует то, что делает прямой вызов scout; но нужен как шаг в asset |
| ship | Agent(qa, git-warden, scribe, overseer, optimizer); `docs/STATUS.md`, `docs/PERF.md`, `git tag` | да | **не отражает реальный выпуск**: в проекте выпуск = `Выпуск\OXCE_Release.cmd` / `release.ps1` (есть) и автовыпуск editq через 15 минут; skill собирает «архив мода» вручную и предлагает `git tag`. Прямое противоречие с памятью («Собирай = выпуск всем»). |
| status | Agent(overseer) | есть | дубль overseer; STATUS.md не обновлялся с 26.09 |
| warmup | Read..., `Bash(git *)`; `!git log`, docs/PROJECT.md, DECISIONS.md, STATUS.md, BACKLOG.md | все | «прочитай DECISIONS.md» — 480 КБ; не печатает состояние editq/gpuq; SessionStart-хук уже даёт карту, грабли и `editq brief` — warmup частично дублирует session-start |

Дубли: feature / ship / asset не дублируют друг друга по тексту (разные циклы), но все три построены на шаблонных агентах и не знают editq, gpuq, Выпуск/, hdtest_compare. status дублирует overseer; warmup частично дублирует session-start.

---------------------------------------------------------------------

## 5. .claude/launch.json (ЗАНЯТ)

10 конфигураций: map-pick, voice-probe, pilot-sheet, pilot-review, detail-probe, asset-review, struct-accept-review, prod-identity-review, prod2-identity-review, asset-review-test.

| Проверка | Результат |
|---|---|
| runtimeExecutable: `E:/OpenXCom/tools/hdart/.venv/Scripts/python.exe` и `py` | есть (py -0p: 3.14, 3.13, 3.12, uv-3.14.3) |
| Скрипты `tools/hdart/map_pick.py`, `review_server.py` | есть; флаги `--port`, `--logs`, `--accept` у review_server есть (строки 342-344); `serve` у map_pick есть |
| Каталоги и файлы: `portal/deploy/voice-probe/web`, `art/objects/generation/{pilot_v1,runs}`, три `identity_list.json` в `probes/...` | все существуют |
| Порты 8765, 8772, 8774-8779, 8781, 8782 | уникальны |
| **asset-review-test**: `--logs C:/Users/user/AppData/Local/Temp/claude/E--OpenXCom/05fcb89f-.../scratchpad/review_logs` | путь существует сегодня, но это блокнот ЧУЖОЙ сессии; конфигурация живёт ровно пока цела та папка |
| Смесь стилей путей: map-pick - абсолютный, остальные - относительные (от корня) | работает, если cwd = корень |

Устаревших путей кроме asset-review-test нет.

---------------------------------------------------------------------

## 6. tools/gpu_scripts.txt (ЗАНЯТ) против gpu-guard

Как матчит gpu-guard (gpu-guard.ps1, прочитан целиком): берёт команду из tool_input.command, режет на части по `&& || ; |` вне кавычек; часть, начинающаяся с читалки (grep, cat, git, ls, sed, ... ), пропускается; в остальных ищет интерпретатор (python/py/pythonw/accelerate/powershell/pwsh/sh/bash) и берёт ПЕРВЫЙ после него файл `.py|.ps1|.sh`; если его имя (без пути) есть в списке - deny; либо первое слово части - сам скрипт из списка. Пропуск: `gpuq.py` в команде, `GPUQ_BYPASS=1`, `--help|-h|--dry-run|-DryRun`.

| Проверка | Результат |
|---|---|
| tools/test_gpu_guard.py | всё верно |
| tools/test_gpu_scripts.py (классифицирует все .py/.sh/.ps1/.cmd в tools и art/maps/paint по графу вызовов) | **5 ошибок**, 0 пропусков: GPU_MODEL_SCRIPT 66, CPU_SCRIPT 278, UTILITY 125, LEGACY 13; в списке 79 |
| Пять «в списке, но модель не грузит» (хук без нужды блокирует им прямой запуск) | `strict_ctl_v1.py`, `unit_parts.py`, `weapons_synth.py`, `weapons_redraw.py`, `agent_full.py` (все в tools/hdart/) |
| Скрипты с from_pretrained / diffusers / torch.cuda / ollama / .cuda() в tools/*.py и tools/hdart/*.py, которых нет в списке (мой grep) | `model_lock.py`, `obj_gen_spec.py`, `vx_control.py` (библиотеки/проверки по классификации теста), `gpuq.py` (сам диспетчер), `test_gpu_scripts.py`, `test_model_lock.py` (тесты). Запускаемых скриптов с моделью, пропущенных в список: **0** (совпадает с тестом) |
| Имена из списка без файла в дереве | только `train.py` (внешняя программа DiffSynth, законно по описанию теста). `prompt_writer.py`, `paint3.py` лежат в `tools/hdart/attic` |
| `tools/gen_gpu.py` не в списке | верно: это HTTP-мост к ComfyUI/A1111, модель сам не грузит |

Замечание: список и файл тестов правятся прямо сейчас другой сессией (git diff: +37 строк в списке, убран `vx_control.py`); пять ошибок теста - возможно, её незавершённая работа. Из-за «в списке, но CPU» хук блокирует агенту обычный CPU-запуск, например `agent_full.py` (в `git log` есть коммит о нём).

---------------------------------------------------------------------

## 7. AGENTS.md (ЗАНЯТ) против CLAUDE.md (ЗАНЯТ); .index

| Аспект | Результат |
|---|---|
| Противоречия команд | **нет**: AGENTS (роль: Codex читает; запрет правок, игры, GPU, сборки) согласуется с CLAUDE.md (editq, gpuq, game-guard). CLAUDE.md и AGENTS не дают разных команд на одно действие. |
| Дубли | AGENTS кратко повторяет пункты 2-4 «Правил для всех агентов» CLAUDE.md и DoD (раздел «Что считается ошибкой») и ссылается на CLAUDE.md целиком: намеренное дублирование, расхождения по смыслу не нашёл |
| Расхождение фактов | AGENTS: «docs/RAKES.md 200 КБ» - на диске **329 469 байт, 1398 строк** (в git diff +543 строки неотправленных) |
| Выше всех: RAKES.md | CLAUDE.md импортирует `@docs/RAKES.md` целиком в контекст каждой сессии, а сам RAKES.md в шапке требует «больше ~150 строк - пора обезвреживать и удалять». Размер сейчас ~9x от собственного лимита; это основной расход контекста всех агентов. Для Codex в AGENTS.md сделано правильно: «грепни имя файла». |
| DECISIONS.md | CLAUDE.md (правило 1) и agents/skills: «обязательно прочитать»; факт: 1968 строк / 480 КБ. AGENTS.md: «грепом». Правило 1 в CLAUDE.md невыполнимо буквально |
| Размер CLAUDE.md | 166 строк, 15 КБ - нормально |
| Исходные шаблоны | В AGENTS.md и CLAUDE.md не описан `.claude/agents`/skills и то, что они не знают editq |

.index:
- `.index/meta.json`: built_human `2026-10-05 18:27:44`, 1733 файла, 529 985 строк, 68 063 символов, ctags true, clangd true, doxygen_run false, 2,71 с. Свежий (SessionStart перестраивает `--if-stale`).
- Скрипт пересборки: skill `index` -> `python tools/index_project.py` (есть; флаги `--if-stale`, `--full`, `--quiet` есть - строки 197-199). ctags найден (WinGet UniversalCtags), doxygen есть (`C:\Program Files\doxygen`).
- Не работает: `index full` (нужен `Doxyfile` - в корне нет, `docs/SETUP.md` его не упоминает), `index describe` (нет `.index/files.md`; `LOCAL_MODEL=qwen3.8:27b` из settings.json env не совпадает с единственной моделью Ollama `orcarouter/Qwen3.8-27B-Uncensored:q5_K_M`; `describe_modules.py` в gpu_scripts.txt - только через gpuq).
- `.index/INDEX.md` и `files.tsv` свежие (18:27). `.index/rake-hits.log` 628 КБ без ротации.

---------------------------------------------------------------------

## 8. .gitignore против .claude/

`git ls-files .claude` (отслеживается 29 файлов): 12 agents, 7 hooks (без pack-guard), 8 skills (без gpt-check), launch.json, settings.json.

| Объект | Статус в гите | Чем игнорируется | Замечание |
|---|---|---|---|
| `.claude/settings.local.json` | не отслеживается | **глобальным** `C:\Users\user\.config\git\ignore` (`**/.claude/settings.local.json`), в репозитории — нет | на второй машине (и у любого, кто клонирует) файл не игнорируется и может уйти в коммит |
| `.claude/worktrees/` (3 worktree, 107 МБ: elegant-gauss-40b634 и vigorous-easley-829978 - detached `911ca487f`, keen-robinson-8bc1d3 - ветка `claude/gpuq-psutil`) | не отслеживается | только `.git/info/exclude` (локально, не клонируется) | в `.gitignore` репозитория строки нет; все три зарегистрированы в `git worktree list`. Внутри копии `.claude/agents` и CLAUDE.md - дают лишние совпадения в grep по `.claude`. Есть ещё внешний worktree `E:/OpenXCom-glue` (ветка hdglue-test) |
| `.claude/state/` | пустой каталог | `/.claude/state/` в .gitignore | ссылок на него в хуках/editq/rake/CLAUDE.md не нашёл (grep по ps1, editq.py, rake.py, CLAUDE.md пусто) - вероятно мёртвый |
| логи хуков | `.index/rake-hits.log` | `/.index/` | не трекается, нормально |
| `.gptcheck/` | каталог существует (ответы Codex) | строка добавлена в `.gitignore` (не закоммичена, ЗАНЯТ-файл .gitignore в списке изменённых) | до коммита .gitignore ответы Codex видны как `??` |
| `.gpuq/`, `.editq/` | не трекаются | .gitignore строки 141, 143 | нормально |
| Неотслеживаемые, но нужные: `.claude/hooks/pack-guard.ps1`, `.claude/skills/gpt-check/`, `AGENTS.md`, `tools/gpt_check.py`, `tools/test_pack_guard.py`, `tools/hdart/build_hd_pack.py`, `docs/HD_PIPELINE_V2.md` | `??` | - | всё это связано с модифицированным settings.json; коммитить пачкой |
| Должно ли трекаться, но нет | `.claude/hooks/`-тесты есть в tools/ (трекаются); тестов для 4 хуков нет | - | см. раздел 2 |
| Трекается, но не должно | не нашёл | - | - |

---------------------------------------------------------------------

## Безопасно применить сейчас (файлы НЕ заняты)

1. `.claude/hooks/rake-check.ps1`: вывод через `hookSpecificOutput = @{ hookEventName='PreToolUse'; additionalContext=... }` вместо `systemMessage` (оставить и systemMessage, если нужно показывать человеку). Проверка: правка файла с известными граблями (напр. любой `*.ps1`) обязана показать их в ответе инструмента.
2. Новые тесты (новые файлы, ничего не ломают): `tools/test_guard_paths.py` (JSON на stdin powershell, в том числе путь с кириллицей `Пиратки/...` и ASCII-пути; сейчас кириллический будет FAIL - это и есть красный тест), `tools/test_rake_check.py` (хук на файл с граблями выдаёт additionalContext), `tools/test_session_start.py` (хук отдаёт валидный JSON). bom-guard покрыть тестом на временном файле.
3. `.claude/hooks/session-start.ps1`, `rake-check.ps1`: заменить `python` на `py -3.13` (как остальной проект) с запасным `python`.
4. `.claude/settings.local.json` (личный, не в гите): убрать правила на `scratchpad` чужих сессий, на несуществующие `prompt_writer.py`/`paint3.py`/`hdart_sheets_pz`, `Bash(py -3 -)`, `Bash(py -3 -c ' *)`, `Bash(git commit *)`; оставить нужные `py -3.13 tools/...`.
5. `.claude/agents/*.md`, `.claude/skills/*/SKILL.md` (не заняты): (a) в `gpu-forge`, `coder`, `optimizer` добавить абзац про `gpuq`/`editq`; (b) в `qa` - `tools/hdtest_compare.py` и IDENTICAL с контрольным опытом (R-086); (c) в `director` - строку `view-keeper` в таблицу; (d) в skill `rake` заменить `tests/test_r0NN_*.py` на `tools/test_*.py`; (e) в skill `index` - `describe` только через `gpuq.py add`, про отсутствие Doxyfile; (f) в `git-warden`, `overseer`, `scribe` ужесточить tools: `Bash(git status *)`, `Bash(git diff *)`, `Bash(git log *)` вместо `Bash(git *)`.
6. Каталог `.claude/state/` пустой и не используется - можно удалить (мёртвый, не в гите).
7. `.git/info/exclude` -> добавить в **.gitignore** (после освобождения файла) `/.claude/worktrees/` и `.claude/settings.local.json`, чтобы это не зависело от машины.
8. `docs/SETUP.md`: убрать упоминание `Doxyfile` или добавить сам файл.

## Требует решения Vitali

1. **docs/RAKES.md 329 КБ / 1398 строк в `@import` CLAUDE.md** (ЗАНЯТ): лимит в самом файле 150 строк. Варианты: оставить только активные в импорте, остальное в `docs/rakes/<область>.md` (механизм уже есть), либо импортировать короткий индекс. Затрагивает каждую сессию и каждого агента.
2. **docs/DECISIONS.md 480 КБ**: правило 1 CLAUDE.md «обязательно читать» невыполнимо. Заменить на «грепом по теме + последние N записей».
3. **guard-paths.ps1 (ЗАНЯТ) и кодировка stdin**: исправить `[Console]::InputEncoding = UTF8` (или читать stdin байтами и декодировать UTF-8) и/или добавить `deny` в permissions для `Пиратки/**`, `bin/UFO/**`. Нужно слово Vitali про живую проверку (запись в Пиратки для пробы - нарушение правила).
4. **Агенты и skills `asset`, `gpu-forge`, `asset-smith`, `artist`, `ship`, `feature`** - шаблон, не совпадающий с проектом (assets/, gen_gpu.py ComfyUI, ручная сборка архива). Решить: переписать под art/, tools/hdart/, gpuq, editq, Выпуск/ либо пометить как неиспользуемые и убрать (tools/gen_gpu.py тогда тоже).
5. **ship vs Выпуск/OXCE_Release.cmd и автовыпуск editq**: два способа выпуска; skill `ship` предлагает `git tag`. Оставить одно.
6. **Коммит пачки** pack-guard + build_hd_pack + test_pack_guard + HD_PIPELINE_V2.md + settings.json + AGENTS.md + gpt_check + skill gpt-check - иначе хук #8 в чужой копии ссылается на отсутствующий скрипт.
7. **gpu_scripts.txt**: 5 CPU-скриптов в списке (`strict_ctl_v1`, `unit_parts`, `weapons_synth`, `weapons_redraw`, `agent_full`) - блокируются хуком без нужды; закончить текущую правку той сессии (ЗАНЯТ) или убрать из списка.
8. **LOCAL_MODEL=qwen3.8:27b** в settings.json env (ЗАНЯТ) не совпадает с моделью в Ollama (`orcarouter/Qwen3.8-27B-Uncensored:q5_K_M`): что считать верным - поправить env или переименовать модель (`ollama cp`).
9. **settings.local.json** под глобальным git-ignore: решить, дублировать ли правило в `.gitignore` репозитория.
10. **Worktree'ы** `.claude/worktrees/*` (107 МБ, 3 штуки; две в detached HEAD): оставить или удалить через `git worktree remove` (не `rm -rf`, R-047).
11. `Bash(git commit *)` в личных allow: оставить ли (обходит editq done).
