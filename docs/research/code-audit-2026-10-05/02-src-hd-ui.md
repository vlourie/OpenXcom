# Аудит HD-интерфейса (src/Engine/HdUi*, HdFont, HdBattleHud, HdRadar, HdKillCam, HdCraft*, вставки HD в Interface/Menu/Geoscape/Basescape/Game/Screen/Surface/Options)

Только чтение, 2026-10-05. Ничего в E:/OpenXCom не менялось, игра и сборка не запускались.
Занятых файлов в области нет: protected_status.txt не содержит ни одного пути src/ - пометок «ЗАНЯТ» нет.
Метод: .index/symbols.tsv (799 коротких символов области) + grep по всему src; скрипты и сырые выдачи -
scratchpad/audit/{hdui_syms.py, hdui_refs.txt, hdui_scan.py, options.txt, comments.txt, hdr_api.py, hdr_api.txt}.

## Сводка числами

| Что | Сколько |
|---|---|
| Файлов области (Hd* UI + OptionsHdState, AdultChoiceState, GentleChoiceState, HdGentle.h) | 21, 7691 строк |
| Символов проверено на ссылки | 799 (функции, члены, константы) |
| Мёртвых: не вызывается нигде | 5 (2 метода, 3 константы) |
| Публичных методов, нужных только изнутри своего класса | 1 (HdUi::ttfWidth) |
| Опций oxceHd*/oxceAdult*/keyBattleHd* | 32: все объявлены, все читаются, 30 со STR_ в en-US и ru; 2 клавиши без STR_ (скрытые, OPTION_KEY) |
| Опций без упоминания в CLAUDE.md/docs | 11 |
| Опций с одним местом чтения | 4 (oxceHdUiSmooth, oxceHdLight, oxceHdHoverBob, oxceHdReticleDamageColor) - все действуют |
| getenv-ручек в области | 22 (Game.cpp 9, MainMenuState 5, HdKillCam 1, NewBattleState 7 под #ifdef OXCE_AI_DEV) |
| Log() в Hd*-файлах области | 23; периодических без условия - 2 (HdUi.cpp:1125 раз в 600 кадров, Game.cpp:737 раз в 2 с) |
| Закомментированных блоков кода >= 5 строк | 3, все апстрим OXCE; в HD-коде 0 |
| Дублей помощников | 6 групп |
| TODO/FIXME/HACK/XXX в HD-коде | 0; апстримных в файлах области 11 |
| Антипаттернов R-014/R-056/R-057 без защиты | 0; остаточных мест «ключ по указателю» 2 |
| Брошенных веток (флаг никогда не включается, hdMirror всегда в откат) | 0 |

## Мёртвый код

| Где | Что | Вердикт |
|---|---|---|
| src/Engine/HdUi.h:215 | `size_t cachedSurfaces() const { return _smooth.size(); }` | не вызывается - можно удалить (grep по src: только объявление) |
| src/Engine/HdFont.h:69, src/Engine/HdFont.cpp:331 | `HdFont::clearCache()` | не вызывается - можно удалить; между кадрами работает `trimCache` (HdUi.cpp:1103), а HdUi::clearCaches (HdUi.cpp:1132) шрифты не трогает - это осознанно: глифы отданы по ссылке |
| src/Engine/HdUiDraw.cpp:54 | `const float CAP_BIG = 13.0f * CAP_RATIO_BIG, CAP_SMALL = 8.0f * CAP_RATIO_SMALL;` | не используются - можно удалить (комментарий в строке 53 говорит про NumberText и каретку, но те берут размер из метрик шрифта по букве 'H', R-010) |
| src/Engine/HdRadar.cpp:48 | `const Sint16 FAR_OUT = -32000;` | не используется - можно удалить |
| src/Engine/HdUi.cpp:41 | `packColor(const SDL_Color&)` - 6 вызовов в HdUi.cpp | дубль `HdUi::rgba` (см. «Дубли»): заменить и удалить |

Ложные срабатывания сканера, оставить: `HdUi::drawSurface::Timing::~Timing` (HdUi.cpp:576) и
`FrameTiming::~FrameTiming` (HdUiDraw.cpp:137) - RAII-деструкторы, вызываются компилятором.

Публичное, но нужное только своему классу: `HdUi::ttfWidth` (HdUi.h:161) - единственный вызов HdUiDraw.cpp:805;
можно перенести в private. Не ошибка, а запас API.

Геттеры `lastCalls/lastWorstMs/lastWorstW/lastWorstH/lastWorstWhy` (HdUi.h:204-209) читает только строка
«HD stall» в Game.cpp:723-731 - оставить, это диагностика зависаний (R-014 защита).

## Опции

Все 30 oxceHd*/oxceAdult* объявлены в createOptionsOXCE (src/Engine/Options.cpp:509-547) с категорией
STR_HD_ART / STR_HD_GENTLE / STR_HD_BATTLE / STR_HD_INTERFACE / STR_HD_SPEED, и вкладка HD
(src/Menu/OptionsHdState.cpp:104-128) берёт их по категории автоматически; исключения на вкладке три и
осознанные: oxceAdultAsk без дерева 18+, oxceHdFire без паков огня, oxceHdReticle без паков прицела
(OptionsHdState.cpp:114-119). STR_ каждого ключа и STR_*_DESC есть в bin/common/Language/OXCE/en-US.yml и ru.yml
(полная таблица - scratchpad/audit/options.txt).

| Опция | Где читается | Замечание |
|---|---|---|
| oxceHdScale, oxceHdMode, oxceHdUi | Screen.cpp:112/419/581, HdUi.cpp:67/78, HdWorkers.cpp:52-53, Game.cpp:522-549, Feedback.cpp:286-287, Mod.cpp:973 | ядро; задокументированы в CLAUDE.md и docs/HD_MENU.md |
| oxceHdUiSkin | HdUiDraw.cpp:144 (`skin()`), :149 (`style()`), OptionsHdState.cpp:413 | все hdMirror ветвятся по нему |
| oxceHdUiFont | HdUiDraw.cpp:190/263, OptionsHdState.cpp:223-476 | |
| oxceHdUiSmooth | **только** Screen.cpp:419 | действует: `smooth = oxceHdUiSmooth && (!_worldScaleFixed || oxceHdMode > 0)` - xBRZ классического слоя над миром; документирована в HD_MENU.md |
| oxceHdPictures | Screen.cpp:112/581, HdUiArt.cpp:630, BaseView.cpp:49, CraftInfoState.cpp:576 | |
| oxceHdBattleHud | HdBattleHud.cpp:721 (`on()`), HdBattleHud.h:28 | **не задокументирована** |
| oxceHdBattleHudColor | HdBattleHud.cpp:34/71, OptionsHdState.cpp:254-448 | **не задокументирована** |
| oxceHdGlobeScale | HdUi.cpp:709, Globe.cpp:2158/2164 | **не задокументирована** |
| oxceHdRadar | Globe.cpp:1944/2008, HdRadar.h:29/31 | **не задокументирована** |
| oxceHdCraftOutlines | Globe.cpp:1850, DogfightState.cpp:2350 | **не задокументирована** |
| oxceHdBaseAnim | BaseView.cpp:561/613/640/716 | BaseView.cpp:561 `static const bool pictures = Options::oxceHdBaseAnim;` - снимок при первом вызове, смена в меню действует после перезапуска; это написано в комментарии над функцией (строка 555), но на вкладке HD игроку не сказано |
| oxceHdCraftLights | BaseView.cpp:655-716, CraftInfoState.cpp:576 | только docs/research |
| oxceHdReticle | Mod.cpp:1096, OptionsHdState.cpp:119-481 | **не задокументирована** |
| oxceHdReticleDamageColor | **только** Map.cpp:200 | действует (чужая область - ядро рендера); **не задокументирована** |
| oxceHdLight | **только** Map.cpp:624 | действует; документирована |
| oxceHdHoverBob | **только** Map.cpp:3040 | действует; только docs/research |
| oxceHdBlastArea | Map.cpp:1462 | **не задокументирована** |
| oxceHdEnemyNumber | BattlescapeState.cpp:2565-2567 | **не задокументирована** |
| oxceHdFire / oxceHdFirePace / oxceHdSmokePace | Map.cpp:468/2140/2157-2159, UnitSprite.cpp:277-278 | FirePace и SmokePace **не задокументированы** |
| oxceHdFx | Map.cpp:600/2748/2794, ProjectileFlyBState.cpp:436 | только docs/research |
| oxceHdKillCam | HdGentle.h:58/65/92 | только docs/research |
| oxceHdGroundVariants | Map.cpp:230 | документирована |
| oxceHdThreads, oxceHdFrameSkip | HdWorkers.cpp:35/53, BattlescapeState.cpp:155 | документированы |
| oxceAdultArt | HdSprites.cpp:88/113, AdultChoiceState.cpp:130/138, OptionsHdState.cpp:282-295 | STR_ пустой намеренно: на вкладке своя строка ROW_ART (OptionsHdState.cpp:185) |
| oxceAdultAsk | AdultChoiceState.cpp:62, OptionsHdState.cpp:114 | |
| oxceGentle / oxceGentleAsk | GentleChoiceState.cpp:38/104-105, HdGentle.h, OptionsAdvancedState.cpp:255-535, OptionsBattlescapeState.cpp:176-177 | oxceGentleAsk объявлена вне блока 509-547 (не проверял STR_; в HD_CATEGORIES есть STR_HD_GENTLE) |
| keyBattleHdTestDump (F8) | BattlescapeState.cpp:3279, Game.cpp:374 | OPTION_KEY без STR_ - в меню клавиш не показывается; в CLAUDE.md описана |
| keyBattleHdModeToggle (F11) | BattlescapeState.cpp:3285 | OPTION_KEY без STR_; в HD_MENU.md описана. Options.cpp:1341-1344: разовая миграция F9 -> F11 для конфигов, где ключ делил F9 с keyQuickLoad |

Кандидатов «не читается» и «читается, но ни на что не влияет» - нет.
Кандидаты на документацию (11): oxceHdBattleHud, oxceHdBattleHudColor, oxceHdBlastArea, oxceHdCraftOutlines,
oxceHdEnemyNumber, oxceHdFirePace, oxceHdGlobeScale, oxceHdRadar, oxceHdReticle, oxceHdReticleDamageColor,
oxceHdSmokePace - ни в CLAUDE.md, ни в docs/*.md, ни в docs/research.

## Отладочные ручки и логи

### getenv

| Ручка | Где | Кто пользуется | Вердикт |
|---|---|---|---|
| OXCE_HD_DUMP, OXCE_HD_DUMP_AFTER | Game.cpp:441-442 | tools (6 и 3 файла: game_hidden.py и прогоны) | оставить: стенд скрытых дампов (R-124) |
| OXCE_HD_MOUSE, OXCE_HD_CLICK | Game.cpp:447-448 | tools (1 и 5 файлов) | оставить (R-103) |
| OXCE_HD_TYPE | Game.cpp:449 | в tools/docs не найдена | ручка эксперимента - после слова Vitali (парная к CLICK, цена нулевая) |
| OXCE_HD_SET | Game.cpp:524 (oxceHdUi / k на лету, лог «HD test:» :546) | в tools/docs не найдена | ручка эксперимента - после слова Vitali |
| OXCE_HD_KEY | Game.cpp:560 | tools (3 файла; R-102) | оставить |
| OXCE_HD_FRAMELOG | Game.cpp:691 (TSV с HdDrawStats) | tools (2 файла: unit_perf) | оставить: замеры R-091/R-199 |
| OXCE_HD_EXPORT, OXCE_HD_EXPORT_SETS | MainMenuState.cpp:277/281 | tools (11 и 3) | оставить (R-182) |
| OXCE_HD_START, OXCE_HD_SAVES, OXCE_HD_ARTICLE | MainMenuState.cpp:289/330/356 | START - 5 файлов; ARTICLE - 1 файл; SAVES - 0 в tools/docs | START и ARTICLE оставить; SAVES - ручка эксперимента, после слова Vitali |
| OXCE_HD_DUMP_KILLCAM | HdKillCam.cpp:183 (5 моментов сцены) | не найдена в tools/docs | ручка эксперимента - после слова Vitali (приёмка киллкама глазами) |
| OXCE_AI_REALTIME | Game.cpp:173 | стенд ИИ | оставить (чужая область) |
| OXCE_AI_LOADOUT_FIX, _CAMPAIGN, _CRAFT, _SQUAD, _MISSION, _RACE, _DIFF | NewBattleState.cpp:622-899, под `#ifdef OXCE_AI_DEV` | стенд ИИ | оставить: в выпуск не попадают |

Все ручки читаются один раз (`static const char*`), стоимости в кадре нет.

### Логи и счётчики на кадр

| Где | Что | Вердикт |
|---|---|---|
| Game.cpp:737 | «HD frame: N fr, worst ... >=33 ms ... >=100 ms» **каждые 2 с без условия**, счётчики hdFrames/hdWorst/hdSlow/hdStalls на кадр | оставить: по этой строке прогоны ловят зависший экран (tools/ai_probe.py, tools/builds_accept.py, tools/compat/hd_split.py; R-110 stuck_on, R-095, R-203) - это интерфейс стенда, не мусор |
| Game.cpp:723 | «HD stall» при кадре >= 100 мс с разбивкой по фазам и худшей поверхностью HD UI | оставить (R-014 защита) |
| HdUi.cpp:1125 | «HD interface: ms/frame, surfaces/frame, smoothed cached, glyphs» раз в 600 кадров; `_totalMs/_calls/_frames` считаются на каждый вызов | временная статистика: при 60 к/с - строка каждые 10 с всю игру. Кандидат на условие (только при OXCE_HD_FRAMELOG или LOG_DEBUG) - после слова Vitali, docs/PERF.md на неё ссылается? не проверял |
| HdUi.cpp:284 | «HD smooth» при xBRZ >= 20 мс | оставить: ловит R-014/R-057 |
| HdUi.cpp:599 | «HD oversize surface» не больше 4 раз | оставить |
| HdUi.cpp:652 | «HD crop scan» при переборе >= 20 мс | оставить: защита R-056 по ней и проверяется |
| HdUi.cpp:1105/1110 | сброс кэшей глифов | оставить, редко |
| HdUiDraw.cpp:253/287/293, HdUiArt.cpp:95/133/274/293/301, HdFont.cpp:89/176, HdCraftBack.cpp:260, HdCraftLights.cpp:158/171/196 | при загрузке, не в кадре | оставить (R-020, R-033 на них держатся) |
| HdKillCam.cpp:70/94/108 | по событию сцены | оставить |
| HdUi.h:279-282 (`_frameMs/_worstMs/_worstW/_worstH/_worstWhy` и их `_last*`) | замер на каждый drawSurface через RAII Timing (HdUi.cpp:576) - `steady_clock::now()` дважды на поверхность | цена ~50-100 нс на вызов при ~сотне поверхностей в кадре - в шуме; оставить, это и есть диагностика R-014 |

## Закомментированное

В HD-коде закомментированных блоков кода >= 5 строк нет (scratchpad/audit/comments.txt: все блоки >= 5 строк в
Hd*-файлах - документация ///, не код). В файлах области с апстримным кодом три блока, все пришли из OXCE:

| Где | Что | Вердикт |
|---|---|---|
| src/Engine/Screen.cpp:495-509 | `/* SDL_Color *newcolors = ... */` старая установка палитры, 15 строк | апстрим - не трогать (R-078: диф с upstream MeridianOXC) |
| src/Engine/Surface.cpp:763-775 | `/* SDL_BlitSurface uses colour matching ... */`, 13 строк | апстрим - не трогать |
| src/Engine/Options.cpp:117-122 | `//_info.push_back(... baseXResolution ...)` 6 строк | апстрим - не трогать |

## Дубли

| Группа | Где | Вердикт |
|---|---|---|
| Упаковка SDL_Color в 0xAARRGGBB | `packColor` HdUi.cpp:41 (6 вызовов) против `HdUi::rgba` (HdUi.h, вызывается по всему Interface/*) | безопасно: заменить packColor на rgba, удалить |
| withAlpha | HdUiDraw.cpp:156 и HdBattleHud.cpp:74 - побайтно одинаковые `(c & 0x00FFFFFF) | (a << 24)` | безопасно: оставить одну (вынести в HdUi.h как static inline рядом с scaled/mixed) |
| Смешение цветов | `HdBattleHud.cpp:464 mix(a,b,t)` (альфа всегда FF) против `HdUi::mixed` HdUiDraw.cpp:173 (альфа смешивается) | не побайтный дубль: mix форсирует непрозрачность. Замена `mix` на `mixed(...) | 0xFF000000` даёт тот же байт - безопасно, но нужен контроль листом панели боя |
| ease | HdBattleHud.cpp:512 квадратичный `t*(2-t)` (float) и HdKillCam.cpp:49 smoothstep (double) | разные кривые, одно имя - не сливать; переименовать для ясности (не обязательно) |
| Яркость 0.299/0.587/0.114 | HdCraftBack.cpp:62-64 (функция luma), HdUiArt.cpp:221-222 (inline), HdCanvas.cpp:267/751-752/905-906 (inline, чужая область), HdCanvas.cpp:2379 (целочисленная 77/151/28) | HdUi-область: одна функция luma на HdCraftBack и HdUiArt - безопасно; с HdCanvas не объединять (другой агент, и там горячий путь) |
| blend | `HdUi::blend` HdUiDraw.cpp:523 - обёртка над `blendPixel` :103 | не дубль, экспорт для Interface; оставить |

Ширину текста считают в одном месте (HdFont::measure, через HdUi::ttfWidth :805) - дублей измерения нет.
clamp: `HdRadar.cpp:168 clamp01(double)`, `HdBattleHud.cpp:512` inline min/max, `HdUi::style()` clamp 1..3 -
три разных типа и диапазона, объединять нечего.

## TODO

В HD-коде области (Hd*.cpp/.h, OptionsHdState, AdultChoiceState, GentleChoiceState, hdMirror-вставки)
TODO/FIXME/HACK/XXX - 0.
Апстримные в файлах области (не наши, не трогать): Surface.cpp:83, Options.cpp:443, GeoscapeState.cpp:1673/2138,
TextEdit.cpp:343, ModListState.cpp:91, NewBattleState.cpp:1178, TestState.cpp:954, BaseView.cpp:860,
ManufactureStartState.cpp:123, SoldierAvatarState.cpp:212.

## Антипаттерны

| Грабли | Где | Состояние |
|---|---|---|
| R-014 (сглаживание поверхности больше экрана) | HdUi.cpp:594 `oversize = w*h > 4 * экран` до хэша, лог :599 | защищено; drawSurfaceWorld (HdUi.cpp:704+) идёт через тот же кэш - проверки oversize там не видел: глобус 320x200 в s раз, s <= k - в норме, но при правке hdEarthScale пересмотреть |
| R-056 (промах дорогого поиска по указателю) | HdUi.cpp:640-655 `_cropMisses` по (pixelHash,w,h), сброс при смене пака :632-634 | защищено. Остаток: `SmoothEntry::artMisses` (HdUi.h:226, HdUi.cpp:624) по-прежнему по указателю - теперь только второй рубеж, можно убрать вместе с полем |
| R-057 (почти пустой слой целиком) | HdUi.cpp:692 drawSparse при w*h >= 65536 | защищено; контрольное сравнение с целым сглаживанием снято (RAKES: вернуть при правке drawSparse) |
| ключ кэша по указателю | `_smooth` HdUi.h:261 (unordered_map<const Surface*, SmoothEntry>) - запись проверяется по `k` и `pixelHash` (HdUi.cpp:400-411, :611); `_sparse` HdUi.h:304 - тоже по Surface*, pixelHash передаётся (HdUi.cpp:692) | ложного попадания нет; но освобождённый Surface* может переиспользоваться новым - запись не протухает, а живёт до вытеснения LRU (192 МБ, HdUi.cpp:39). Утечки нет, только занятое место; пометка |
| снимок опции в static const | BaseView.cpp:561 `static const bool pictures = Options::oxceHdBaseAnim` | задокументировано комментарием :555; на вкладке HD без пометки «после перезапуска» - см. «Требует решения» |

## Брошенные ветки

Не найдено. Проверены все hdMirror области: ArrowButton.cpp:96, Bar.cpp:176, Cursor.cpp:85, Frame.cpp:126,
NumberText.cpp:275, ProgressBar.cpp:134, ScrollBar.cpp:188, Text.cpp:747, TextButton.cpp:287/294,
TextEdit.cpp:304, TextList.cpp:1173, ToggleTextButton.cpp:79, Window.cpp:323, ActionMenuItem.cpp:168,
WarningMessage.cpp:163, Globe.cpp:2177, HdHudPanel (HdBattleHud.cpp:769). Каждая ветвится по
`HdUi::skin()` (oxceHdUiSkin > 0, HdUiDraw.cpp:144) или `HdBattleHud::on()` (oxceHdBattleHud && skin,
HdBattleHud.cpp:719) с откатом в Surface::hdMirror (Surface.cpp:744) - обе ветки достижимы с вкладки HD.
Globe::hdMirror уходит в откат при oxceHdGlobeScale 0 или >= k (Globe.cpp:2164-2169) - это и есть умолчание.

Особые места, не ветки, а условия:
- Text.cpp:747-749 `if (Options::debugUi) Surface::hdMirror();` - апстримный флаг отладки (Game.cpp:353, клавиша),
  рисует классический текст под TTF для сверки; законно.
- TextButton.cpp:294-309: без скина, при `_hdBase` не того размера, уходит в drawSurface и **не рисует** `_text->hdDrawAt`
  (return в :307) - текст кнопки тогда идёт из классических пикселей; ветка рабочая, просто другой путь.
- Options.cpp:1341-1344 миграция F9 -> F11: срабатывает только у конфигов, где оба ключа на F9; удалять нельзя,
  пока у игроков живут такие options.cfg (R-105: сохранённое значение перебивает умолчание).
- Surface.cpp:716-737: при HD-интерфейсе картинка с HD-паком (`HdUiArt::drawIfPicture`) не рисуется - её рисует
  hdMirror; без HD-интерфейса наоборот. Обе ветки живые (oxceHdUi 0 и > 0).

## Безопасно применить сейчас

Ни одно не меняет кадр: мёртвые символы и побайтно равные помощники. После - сборка и дамп режима 0 при k=1/k=4
на всякий случай (DoD), менять ничего не должен.

1. Удалить `HdUi::cachedSurfaces` - src/Engine/HdUi.h:215.
2. Удалить `HdFont::clearCache` - src/Engine/HdFont.h:69, src/Engine/HdFont.cpp:331 (тело).
3. Удалить `CAP_BIG`, `CAP_SMALL` и комментарий над ними - src/Engine/HdUiDraw.cpp:53-54.
4. Удалить `FAR_OUT` и комментарий над ним - src/Engine/HdRadar.cpp:47-48.
5. `packColor` (src/Engine/HdUi.cpp:41) заменить на `HdUi::rgba` в шести вызовах HdUi.cpp, функцию удалить.
6. `withAlpha` оставить одну: вынести в HdUi.h (static inline, рядом с scaled/mixed), убрать копии
   HdUiDraw.cpp:156 и HdBattleHud.cpp:74.
7. `luma`: HdUiArt.cpp:221-222 перевести на функцию из HdCraftBack.cpp:62 (вынести в общий заголовок HdUi.h или
   HdUiArt.h); HdCanvas не трогать.
8. `HdUi::ttfWidth` (HdUi.h:161) перенести в private - единственный вызов внутри класса.

## Требует решения Vitali

1. Ручки без потребителя в tools/docs: OXCE_HD_TYPE (Game.cpp:449), OXCE_HD_SET (Game.cpp:524-556, включая лог
   «HD test:» :546), OXCE_HD_SAVES (MainMenuState.cpp:330), OXCE_HD_DUMP_KILLCAM (HdKillCam.cpp:183).
   Цены в кадре нет; вопрос только, нужны ли они стенду дальше. OXCE_HD_ARTICLE проверить отдельно (grep прерван).
2. Строка «HD interface: ... ms/frame» раз в 600 кадров (HdUi.cpp:1121-1129) и счётчики под неё: всю игру по
   строке каждые ~10 с. Либо оставить как есть (docs/PERF.md может на неё опираться - не проверял), либо печатать
   только при OXCE_HD_FRAMELOG / LOG_DEBUG. «HD frame» раз в 2 с (Game.cpp:737) трогать нельзя - по ней стенд
   ловит зависший экран.
3. `SmoothEntry::artMisses` (HdUi.h:226, HdUi.cpp:624-627, 412-450): после `_cropMisses` это второй, более слабый
   рубеж по указателю. Убрать поле и ветку - упрощение, не ускорение; решать вместе с правкой drawSurface.
4. 11 опций HD без единого слова в docs (список в «Опции»): дописать в docs/HD_MENU.md таблицу «опция - что делает -
   где читается». Это docs, не src - но кто пишет и в каком объёме, решать Vitali.
5. oxceHdBaseAnim действует после перезапуска (BaseView.cpp:561 static const), а на вкладке HD пометки нет -
   либо строка в STR_HD_BASE_ANIM_DESC (это bin/common/Language/OXCE - Святое правило, исключение, но перенос в
   Пиратки обязателен), либо убрать static и дать опции действовать сразу (проверка: переключение в меню базы).
6. `mix` в HdBattleHud.cpp:464 -> `HdUi::mixed | 0xFF000000`: байт тот же, но панель боя - образец Vitali
   (коммиты 1acd2706a..dbacb62e2); менять только с листом панели до/после.
7. Миграция F9 -> F11 (Options.cpp:1341-1344): оставить до тех пор, пока у игроков могут жить конфиги до выпуска,
   где ключ переехал; дата того выпуска - у Vitali.
