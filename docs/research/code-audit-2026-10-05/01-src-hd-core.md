# Аудит ядра HD-рендера (src/Engine/Hd*, HD-вставки Battlescape)

Дата: 2026-10-05. Ветка hd-render, HEAD e6af0d5ed. Только чтение; ничего в E:\OpenXCom не менялось.
Метод: `.index/symbols.tsv` (сборка 18:34) + скрипты `scratchpad/audit/dead_scan.py` (543 символа области против
всех 878 файлов `src/`, упоминания без строки объявления) и `comment_scan.py` (блоки комментариев от 5 строк,
похожие на код) + `git grep` по именам ручек. Все числа - по grep, не на глаз.

Занятость: `protected_status.txt` не содержит ни одного файла `src/` - в области **ничего не ЗАНЯТО**.

## Сводка числами

| Что | Число |
|---|---|
| Файлов области (Hd*.cpp/.h, 21 файл; `HdPack*` не существует) | 8 239 строк, из них HdCanvas.cpp 2 475, HdSprites.cpp 1 455 |
| Символов области проверено на упоминания | 543 |
| Мёртвый код (0 вызовов) | **2**: `Canvas32::toneValue`, `Canvas32::setDeferred` (+ недостижимая ветка `record()`) |
| Ручки окружения `getenv("OXCE_HD_*")` в области | 7 (FRAMELOG, SMOOTH_CAP, PACK_BUDGET, DUMP_FX, DUMP_FX_ONLY, DUMP_KILLCAM; DUMP_FX читается дважды) |
| …вне области (Game.cpp, MainMenuState.cpp, BattlescapeState.cpp) | 13 |
| Ручек без документации (ни docs/, ни tools/, ни CLAUDE.md/AGENTS.md) | 5: DUMP_FX_ONLY, DUMP_KILLCAM, TYPE, SET, SAVES |
| Временные логи (temporary/dbg/DBG/E1DBG/check/sparse/probe) | **0** - R-057 и R-224 подтверждены: сняты |
| Постоянные логи в области | 36 строк Log(...), все LOG_INFO/WARNING/ERROR с префиксом «HD …»; 1 LOG_DEBUG |
| Закомментированный код ≥ 5 строк | 1 блок, и тот upstream (Yankes 2017) |
| Дубли помощников | luma ×6 (два разных набора коэффициентов), смесители пикселей ×3, масштаб-с-зажимом ×4, FNV-хэши ×3 (+2 своих) |
| TODO/FIXME/HACK/XXX | **0** (HdFx.cpp:215 «SHACK» - ложное срабатывание) |
| Антипаттерны R-009 (отметки) | 6 мест, все либо на промахе кэша, либо на буфере базового размера |
| Брошенные ветки | 1 (непосредственное исполнение `_deferred = false`), опций-заглушек нет |

## Мёртвый код

| # | Символ | Где | Упоминаний вне объявления | Вердикт |
|---|---|---|---|---|
| 1 | `Canvas32::toneValue(int shade, int value, int channel) const` | `src/Engine/HdCanvas.h:465` (inline, «exposed for tests») | **0** во всём `src/` | **можно удалить без влияния на кадр (не вызывается)**. Тестов, которые бы его звали, в `tools/` нет (grep `toneValue` по `tools/` - пусто). Появился в 187df8dd3 вместе с `_toneFactor`; сама таблица `_toneFactor` жива (HdCanvas.cpp:373, 377, 2121-2123, 2326, 2423-2425) |
| 2 | `Canvas32::setDeferred(bool)` | объявление `HdCanvas.h:463`, тело `HdCanvas.cpp:195-199` | **0** вызовов (только объявление и определение) | **можно удалить без влияния на кадр**. `_deferred` ставится в `true` в конструкторе (HdCanvas.cpp:158) и больше нигде не меняется |
| 3 | ветка `else { execute(cmd, cmd.y0, cmd.y1); }` в `Canvas32::record` | `HdCanvas.cpp:456-459` | недостижима (см. №2) | **можно удалить вместе с полем `_deferred` (HdCanvas.h:291) и №2** - `execute()` сам по себе жив (его зовут полосы `flush`) |

Проверены и **живы** (1-2 упоминания, но это объявление + настоящий вызов): все остальные 540 символов.
Отдельно: `TonedKey::operator==` (HdCanvas.h:329) грепом «не вызывается», но его использует
`std::unordered_map<TonedKey,…>` неявно - **оставить**.

Константы и статики, проверенные на использование (все живы): HdFx.cpp:49-54 (FOLDER, BUDGET 96 МБ, IDLE 3000,
FLASH_MS 120); HdSprites.cpp:145-147 (MAX_VARIANTS 15, MAX_DOT 4); HdSmooth.cpp:44 ISO_NEIGHBOURS;
HdOutline.cpp:64-69 (HALO_RGB, HALO_ALPHA, STATE_ALPHA, STATE_REACH); HdBase.cpp:42-79 (FOLDER, ANIM, MAX_PHASES 64,
STEP 200, NEVER, STILL/LOOP/BURST, masterOffset, бюджет 64 МБ); HdCanvas.cpp:1685-1688 (GROUND_WAVE/WAVE2/EDGE/RAGGED);
Camera.cpp:478-488 (GLIDE_TIME/FAR/GAP/STEP - читаются в 520, 536, 538, 577); HdGentle.h constexpr UNIT_SPEED,
FIRE_SPEED, TRACE_PROJECTILES, REACTION_COLOR, REACTION_ARROW_MS - читаются через inline-функции и напрямую
(BattlescapeState.cpp:2560, Map.cpp:3518, 3542). Поля `HdDrawStats` (recordUs, unitsUs, scriptUs, smoothUs/New,
tonedUs/New, flushUs, stripMaxUs, cmds) - каждое читается в Game.cpp:706 и пишется в Hd*/Map.cpp.

## Отладочные ручки и логи

### Таблица `getenv("OXCE_HD_…")`

| Ручка | Где читается (file:line) | Что делает | Документация | Класс |
|---|---|---|---|---|
| `OXCE_HD_FRAMELOG` | `HdCanvas.cpp:39` (`HdDrawStats::on`, один раз при старте); также `Game.cpp:691` | включает замер времени по этапам кадра и строки «HD frame» | `docs/research/units-perf-baseline.md`, `tools/unit_perf.py`, комментарий `HdCanvas.h:37` | ручка замера - **оставить** (R-091: единственный источник drawMs по этапам) |
| `OXCE_HD_SMOOTH_CAP` | `HdCanvas.cpp:1162-1165` (`trimSmooth`, static-инициализатор) | потолок кэша xBRZ в МБ вместо 256 | `docs/research/audit-2026-09-26-fixes.md`, `docs/research/units-engine.md` | ручка теста вытеснения - **снять после слова Vitali** или оставить (0 стоимости: читается один раз) |
| `OXCE_HD_PACK_BUDGET` | `HdSprites.cpp:523-530` (`budgetBytes`, `static bool budgetRead`) | бюджет ленивых кадров паков в МБ вместо 384 | `CLAUDE.md`, `tools/hdtest_README.md`, 3 файла docs/research | ручка теста - **оставить** (упомянута в CLAUDE.md как штатная) |
| `OXCE_HD_DUMP_FX` | `HdFx.cpp:573` (`noteForTest`, static) и `HdFx.cpp:599` (`takeTestDump`, повторный getenv на каждый дамп) | до 4 дампов кадра через 50 мс после старта эффекта | `docs/RAKES.md` (R-085, R-214), `tools/hdtest_README.md`, описание в `HdFx.h:88` | ручка приёмки эффектов - **оставить**; повторный `getenv` на :599 можно заменить на уже прочитанный `prefix` (косметика) |
| `OXCE_HD_DUMP_FX_ONLY` | `HdFx.cpp:578-579` | фильтр имён клипов для дампа (`_unit`, `_armor`) | **не документирована** (только комментарий в коде :577) | ручка приёмки - **оставить, дописать строку в `tools/hdtest_README.md`** |
| `OXCE_HD_DUMP_KILLCAM` | `HdKillCam.cpp:183` (`takeTestDump`, 5 моментов 200…3700 мс); вызов из `BattlescapeState.cpp:3201` | дампы кадров kill-cam | **не документирована** | ручка приёмки (HdKillCam вне списка области, но HD-ядро) - **оставить, дописать в hdtest_README** |

Вне области, для полноты (Game.cpp:441-449, 524, 560; MainMenuState.cpp:277-356): `OXCE_HD_DUMP`, `_DUMP_AFTER`,
`_MOUSE`, `_CLICK`, `_TYPE`, `_SET`, `_KEY`, `_EXPORT`, `_EXPORT_SETS`, `_START`, `_SAVES`, `_ARTICLE`. Из них
**не документированы** `OXCE_HD_TYPE`, `OXCE_HD_SET`, `OXCE_HD_SAVES` (остальные - в `tools/hdtest_README.md`,
`tools/game_hidden.py`, `docs/AI_ROADMAP.md`, RAKES). Все они - скрытый прогон `game_hidden.py`; их аудит - в отчёте
по интерфейсу/Game.cpp.

Ручки семейства `OXCE_HD_GLUE_*` (R-123: KEEP, OBJKEEP, WARM, STANDIN, SETS, CROP, ADDR, STABLE, SHIFT, PAN, MAT,
CAP, AMP) упоминаются в docs/RAKES и docs/research, **в `src/` их больше нет** - документация описывает снятый
эксперимент; править RAKES не нужно (история), но в `docs/research` стоит пометить «снято».

Обёрток `SDL_getenv` / `std::getenv` помимо перечисленных в области нет.

### Логи и счётчики

Временных логов (temporary/dbg/DBG/E1DBG/check/sparse/probe) в области и во всём `src/` **нет**:
- R-057 «HD sparse check» / «HD globe» - грепом отсутствуют: сняты, как и записано в RAKES.
- R-224 «E1DBG» - отсутствует: разбивка осталась только в черновике блокнота, как и записано.

Постоянные логи области (все с префиксом «HD …», уровень INFO/WARNING/ERROR):

| Файл | Строк | Заметное |
|---|---|---|
| HdCanvas.cpp | 3 | `:1080` LOG_ERROR «frame registry changed…» один раз (`static bool told` :1076); `:1248` «HD perf: smooth cache trimmed» при каждом вытеснении; **`:1284` «HD perf: …» каждые 2 с безусловно** (`perfReport()` из `flush` :1151, без проверки `HdDrawStats::on`) |
| HdSprites.cpp | 18 | загрузка паков, предупреждения о размере/палитре; `:664` единственный LOG_DEBUG |
| HdWorkers.cpp | 2 | `:48` «HD render: N thread(s)», `:51` «HD setup:» - один раз при старте |
| HdTest.cpp | 5 | дампы Ctrl+F8 |
| HdFx.cpp | 2 | `:109` «HD fx:», `:265` «clip … MISSING» |
| HdItems.cpp | 4 | `:159, :187, :327, :377` - по одному разу на тип (`noGrid`/`noHand` множества :76-77) |
| HdOutline.cpp | 2 | `:106, :128` |
| HdBase.cpp | 5 | `:200, :226, :351, :557, :567` |
| Map.cpp | 2 | `:1061` «HD test: frozen … N of M color(s)» (защита R-086 - **оставить**); `:1541` LOG_DEBUG «HD blast area:» |

Статические флаги и счётчики (все по делу, не остатки): `HdCanvas.cpp:139 static bool busy` (защита от
повторного входа flushLiveCanvases ← HdSprites::trim); `HdCanvas.cpp:1076 static bool told`;
`HdSprites.cpp:526 static bool budgetRead`; `HdFx.cpp:567-568 testDumps / testDumped` (только под DUMP_FX);
`HdItems.cpp:223 static std::unique_ptr<Surface> scratch` (черновик для `recoloured()`, R-198);
`HdItems.cpp:85, :93` `attached`/`watched` - намеренная утечка `*new std::map` с комментарием «Never destroyed:
~Surface asks it» (порядок разрушения статиков) - **оставить**.

Единственный спорный лог - `perfReport` (HdCanvas.cpp:1276-1291): пишет в `openxcom.log` 7 полей каждые 2 секунды
боя у **каждого игрока**, не только при `OXCE_HD_FRAMELOG`. За бой в 20 минут это ~600 строк. `docs/PERF.md`
и R-091 называют строки «HD perf» источником чисел расхода - значит это осознанно. **Требует решения Vitali**:
оставить как есть, или включать только при `HdDrawStats::on`, или реже (раз в 10 с).

## Закомментированное

Блоков закомментированного кода от 5 строк в области **нет**. Единственная находка - вне `Hd*`:

- `src/Battlescape/ProjectileFlyBState.cpp:864-868`: `//do not work yet` + закомментированный вызов
  `_parent->getTileEngine()->explode(...)` для дробовых пуль. `git blame`: **Yankes, 2017-11-04, upstream OXCE**.
  Наш HD-код (`:862 explosion->setHdFx(...)`) стоит строкой выше, но блок не наш. **Оставить** - upstream, при слиянии
  с MeridianOXC пропадёт сам или вернётся; трогать - лишний конфликт слияния.

## Дубли

### Яркость (luma) - шесть мест, **два разных набора коэффициентов**

| Место | Формула | Тип |
|---|---|---|
| `HdCanvas.cpp:267` (`rebuildToneTables`) | `0.299 r + 0.587 g + 0.114 b` / 255 | double |
| `HdCanvas.cpp:751-752` (множитель «только свет», R-228) | `0.299f r + 0.587f g + 0.114f b` | float |
| `HdCanvas.cpp:905-906` (перекраска скриптом, R-030) | то же | float |
| `HdCraftBack.cpp:62-65` `inline float luma(float r, float g, float b)` | то же | float, своя функция |
| `HdUiArt.cpp:221-222` | то же | double |
| `HdCanvas.cpp:2379` (`RECOLOR` в полосе блита) | `(r*77 + g*151 + b*28) >> 8` | целочисленная, ≈ 0.301/0.590/0.109 |

Первые пять - один и тот же Rec.601, можно вынести в один `inline` в `HdCanvas.h` (или новый `HdMath.h`) без
изменения ни одного пикселя (те же константы, тот же тип на месте вызова). Шестое - **другие коэффициенты** (целые, с
ошибкой до 1 уровня яркости); приводить к общей функции нельзя без дампа k=1/k=4 - **требует решения Vitali**
(скорее всего «оставить как есть»: горячий путь полосы, целочисленная арифметика нарочно).

### Смесители пикселей - три

| Место | Сигнатура | Отличия |
|---|---|---|
| `HdCanvas.cpp:1328` `inline Uint32 mix2(Uint32 a, Uint32 b, Uint32 w)` | вес 0..256, упакованные каналы (RB/AG парами) | целочисленный, с альфой |
| `HdBattleHud.cpp:464` `Uint32 mix(Uint32 a, Uint32 b, float t)` | вес float | альфа принудительно FF |
| `HdUiDraw.cpp:173` `Uint32 HdUi::mixed(Uint32 a, Uint32 b, float t)` (объявлен `HdUi.h:111`) | вес float | альфа смешивается |

Семантика трёх функций различна (альфа), результаты при одинаковом входе не обязаны совпадать до бита. Объединять
можно только `HdBattleHud::mix` → `HdUi::mixed` + `| 0xFF000000` (HdBattleHud.cpp:464 вне области, рисует панель;
влияет только на интерфейс, не на кадр боя). `mix2` - горячий путь полос, трогать не надо.

### Масштаб канала с зажимом - четыре повторения трёх строк

`std::min(255, (int)(ch * f + 0.5f))` ×3 канала: `HdCanvas.cpp:884-886`, `HdCanvas.cpp:915-917`,
`HdUiArt.cpp:549-551`, `HdUiDraw.cpp:167-169` (`HdUi::scaled`). Единая функция существует - `HdUi::scaled`
(HdUiDraw.cpp:165); два места в HdCanvas.cpp могли бы её звать, но HdCanvas не включает HdUi.h (слойность: холст
не зависит от интерфейса). Если выносить - в общий заголовок без зависимостей. Арифметика побитно та же.

### Хэши

| Место | Алгоритм |
|---|---|
| `HdCanvas.cpp:680-708` и `:936-942` | FNV-64 (простое 1099511628211ULL), по результату скрипта |
| `HdFx.cpp:398-401` | FNV-32 (2166136261u / 16777619u), по палитре |
| `HdCanvas.cpp:1651` `groundHash` | murmur-подобный |
| `HdCanvas.h:333` `TonedKeyHash` | свой |
| `HdBattleHud.cpp:517` лямбда `hash` | свой |

Два FNV-64 в HdCanvas.cpp - одно и то же тело цикла по строкам `_scriptDst`; можно одну функцию
`hashRows(SurfaceRaw, seed)`. Остальные - разные входы, дубля нет.

Мелочь: `HdRadar.cpp:168 clamp01` - единственное место, не дубль.

Структурный дубль: `Canvas32::spansFor` (HdCanvas.cpp:407-431, по индексу 0 палитрового кадра) и
`HdFrame::buildSpans` (HdSprites.cpp, по альфе RGBA) считают один и тот же «непрозрачный отрезок строки» для разных
форматов пикселя - это две разные функции по праву, не дубль.

## TODO

В области (`src/Engine/Hd*`) и в HD-вставках Battlescape TODO/FIXME/HACK/XXX - **0**.
`HdFx.cpp:215` содержит «SHACK» (имя клипа) - ложное срабатывание грепа по HACK.

## Антипаттерны (R-009) - только отметки

| Место | Что | Оценка |
|---|---|---|
| `HdCanvas.cpp:680-708` | хэш результата скрипта по всем пикселям базового кадра на **каждый** вызов `blitScripted` (каждый юнит, каждый кадр) | буфер базового размера (32×40 = 1 280 байт, у 2×2 юнитов 4-кратно) - дёшево; нужен как ключ кэша `_smoothScripted`. Норма |
| `HdCanvas.cpp:936-942` | то же для режима 2 | то же |
| `HdCanvas.cpp:763-768` | `votes.assign(256*256*(own?2:1), 0)` - 256-512 КБ | **только на промахе кэша** (`it == _smoothScripted.end()`, :736) и только если у кадра есть HD-пиксели над пустыми базовыми (`buildMap` ленивый). Норма |
| `HdCanvas.cpp:1846, 1860` | `std::vector<float> level, ragged`, `out->pixels.assign` при склейке вариантов земли | на промахе `_ground` (после создания записи :1836). Норма |
| `HdCanvas.cpp:974, 1003, 1031` | `_arena.resize` на команду | арена переиспользуется между кадрами (`clear()` не освобождает ёмкость), это и есть кэш. Норма |
| `Map.cpp:627` | `_hdShadeCache.assign(mapSizeXYZ, -1)` каждый кадр при HD-свете | memset ~15-60 КБ на кадр. Норма |
| `Map.cpp:2796` | `std::vector<...> flashes` на кадр | пустой вектор почти всегда (вспышек нет) - без аллокации. Норма |
| `Map.cpp:164` | `static std::map<…, HdFrame> cache` в `blastDiamond` | кэш по (цвет, альфа, k), строится раз. Норма |
| `HdCanvas.cpp:1343-1375` `copyZoomed` | `std::vector<int> cols`, `colWeights` на вызов + попиксельный проход | только kill-cam, идёт через `HdWorkers::run` (jobs по полосам). Норма |

Однопоточных попиксельных путей на весь экран за пределами `HdWorkers` в области **не найдено**: `flush` исполняет
полосы на пуле, `copyTo`/`copyZoomed`/`saveDump` - пулом либо одноразовые (дамп).

## Брошенные ветки

| Место | Что | Вердикт |
|---|---|---|
| `HdCanvas.cpp:448-459` + `HdCanvas.h:291 _deferred` + `setDeferred` | режим «исполнять команду сразу, без отложенного списка» (комментарий «tests, single-threaded use») - никогда не включается | **можно удалить без влияния на кадр**: `_deferred` всегда true |
| Опции `oxceHd*` (Options.inc.h:163-214, 28 штук) | все 28 читаются хотя бы в одном месте вне `Options.*`; «объявлена, но читается в одном месте и всегда по умолчанию» - **нет таких** | - |

Опции с одним местом чтения (норма, не брошены): `oxceHdUiSmooth` (Screen.cpp:419), `oxceHdLight` (Map.cpp:624),
`oxceHdReticleDamageColor` (Map.cpp:200), `oxceHdHoverBob` (Map.cpp:3040), `oxceHdThreads` (HdWorkers.cpp:35),
`oxceHdFrameSkip` (BattlescapeState.cpp:155), `oxceHdKillCam` (только через `HdGentle::killCam`, HdGentle.h:58 →
UnitDieBState.cpp:153). Все имеют строку на экране опций (`STR_HD_*`) - игроку доступны.

Недокументированные ручки окружения - см. таблицу выше (DUMP_FX_ONLY, DUMP_KILLCAM в области; TYPE, SET, SAVES вне).

## Безопасно применить сейчас

Ничего из этого не меняет ни одного пикселя (не вызывается или арифметика побитно та же); режим 0 при k=1/k=4
останется IDENTICAL по определению, но дамп после правки всё равно снять (правило 3).

1. Удалить `Canvas32::toneValue` - `src/Engine/HdCanvas.h:464-465` (две строки: doc-комментарий и inline).
2. Удалить `Canvas32::setDeferred` - `HdCanvas.h:462-463`, `HdCanvas.cpp:195-199`; поле `_deferred` `HdCanvas.h:291`
   и инициализацию в конструкторе `HdCanvas.cpp:158`; в `record()` `HdCanvas.cpp:448-459` оставить только тело
   ветки `if (_deferred)`.
3. `HdFx.cpp:599`: вместо второго `getenv("OXCE_HD_DUMP_FX")` использовать `prefix` из `noteForTest` (вынести static
   в анонимное пространство имён рядом с `testDumps` :567).
4. Дописать в `tools/hdtest_README.md` строки про `OXCE_HD_DUMP_FX_ONLY` и `OXCE_HD_DUMP_KILLCAM` (и вне области -
   `OXCE_HD_TYPE`, `OXCE_HD_SET`, `OXCE_HD_SAVES`); документация, не код.
5. В `docs/research`, где упоминаются `OXCE_HD_GLUE_*`, пометить «снято из src» (RAKES не трогать).
6. Два FNV-64 цикла в `HdCanvas.cpp:680-708` и `:936-942` свести в одну статическую функцию - побайтно тот же хэш.

Пункты 1-3, 6 - один коммит `hd: мёртвый код ядра HD (toneValue, setDeferred, повторный getenv)`, через очередь
`editq`, с дампом режим 0 k=1 и k=4 до/после.

## Требует решения Vitali

1. **`perfReport` каждые 2 с безусловно** (`HdCanvas.cpp:1151 → 1276-1291`): ~600 строк «HD perf:» за бой в логе
   каждого игрока. Варианты: оставить (docs/PERF.md на них опирается), включать только при `OXCE_HD_FRAMELOG`, или
   раз в 10 с. Отчёт игрока F8 и R-091 ссылаются на эти строки - без слова Vitali не трогать.
2. **`OXCE_HD_SMOOTH_CAP`** (`HdCanvas.cpp:1162`) - ручка одного теста вытеснения (R-014 эпоха). Снять или оставить
   как парную к `OXCE_HD_PACK_BUDGET`? Стоимость нулевая, но это недокументированное в CLAUDE.md поведение.
3. **Целочисленная luma `(77,151,28)>>8` в `HdCanvas.cpp:2379`** против `0.299/0.587/0.114` в пяти других местах:
   объединять нельзя без изменения пикселей перекраски (±1 уровень). Предлагаю **оставить** и лишь дописать
   комментарий «нарочно целочисленная, не сводить к luma()», чтобы следующий аудит не предлагал слияние.
4. Три смесителя (`mix2` / `HdBattleHud::mix` / `HdUi::mixed`) - сводить ли `HdBattleHud::mix` к `HdUi::mixed`?
   Влияет только на цвета панели (интерфейс), на кадр боя - нет; выгода косметическая. Вне области (HdBattleHud).
5. Upstream-блок `ProjectileFlyBState.cpp:864-868` - оставить (рекомендация), иначе конфликт при слиянии с MeridianOXC.

## Что не найдено (отрицательный результат, чтобы не искать снова)

- `HdPack*.*` - файлов нет (пак читает `HdSprites::loadPack`, HdSprites.cpp).
- Обёрток getenv, временных логов, TODO, закомментированного кода в `Hd*` - нет.
- Ручек `OXCE_HD_GLUE_*` в `src/` - нет (только в docs).
- Опций-заглушек (объявлены, не читаются) - нет.
- Файлов области в `protected_status.txt` - нет; ничего не ЗАНЯТО.
