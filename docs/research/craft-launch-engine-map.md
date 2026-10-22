# Вылет и посадка корабля: карта движка (22.10.2026)

Справка к `docs/research/craft-launch-2026-10-22.md`: куда в движке встаёт ролик вылета и посадки и
наезд на ангар. Собрано разбором кода 22.10 (агент Explore, проверено по строкам).

## 1. Как HD-кадр попадает в окно

- `Screen::_world` — 32-бит слой `baseW*k × baseH*k`, пиксель `0xAARRGGBB`; есть только при
  `isLayered()`. Вне боя `k = clamp(round(displayHeight/baseHeight), 1..8)` при HD-картинках/HD UI.
- `Screen::flip()` (`Screen.cpp:202-261`): без `HdUi::active()` классический 8-бит слой ложится поверх
  world (индекс 0 прозрачный), дальше `Zoom::flipWithZoom` до окна с полосами.
- `Game::run`: `think()` верхнего → `_screen->clear()` (обнуляет и world) → `blit()` всех state от
  верхнего `isScreen()` вверх → курсор → `flip()`. Хук рисования State — `virtual blit()`.
- Образцы записи в world из State: `CraftInfoState::blit()` (`:572-589`), `BaseView::drawHd()`.
- Для видео: свой State без Surface'ов, `blit()` пишет в `Screen::current()->getWorldSurface()`
  вписыванием кадра (билинейно, строки на `HdWorkers`, образец `Canvas32::copyZoomed`,
  `HdCanvas.cpp:1591`). Без `isLayered()` world нет — ролик не играть.

## 2. Хука «поверх всего» нет

`HdKillCam` — только состояние, зум делает `Map::blit` (`Map.cpp:1464`) через `Canvas32::copyZoomed`.
Для наезда на базу нужна своя функция «world → копия → ресэмпл» по этому образцу.

## 3. Вылет и посадка

- Вылет: `ConfirmDestinationState::btnOkClick` (`:324-408`): лидер `setDestination(_target)`, при
  `isTakingOff()` (`_takeoff == 60`, ставится только если статус был не `STR_OUT`) — звук взлёта
  `takeoffSound`; потом всем `setStatus("STR_OUT")`, два `popState()`. Ошибки (`:326-356`) — раньше.
- Автопатруль: `GeoscapeState::time30Minutes`, `:1981-1982` — без игрока, ролик не нужен.
- Трансфер корабля: `btnTransferClick` (`:468-469`) — без звука, ролик не нужен.
- Посадка: `GeoscapeState::time5Seconds`, `:1241-1248`: `if (xcraft->think())` — корабль сел на базу
  (`Craft::think` уже сделал `checkup()`). State ставить через `popup(...)` (очередь попапов, время
  встаёт, `:792-797` показывает по одному).

## 4. Опции HD

Три места: `Options.inc.h` (`OPT int ...`), `Options.cpp` (`OptionInfo(OPTION_OXCE, "имя", &var,
умолчание, "STR_...", "STR_HD_INTERFACE")`), строки `bin/common/Language/OXCE/<язык>.yml` (`STR_X`,
`STR_X_DESC`, для int — `STR_X_0..N`). Экран `OptionsHdState`: int — ветка в `valueText`
(`:290-348`) и пределы в `changeSetting` (`:502-…`).

## 5. Файлы мода

Логический путь `HdSprites::artPath("LAUNCH/<тип>.mpg")` → `hd/LAUNCH/...` (или `hd_18+/...`);
`FileMap::fileExists`, чтение целиком `FileMap::getRWopsReadAll` + `SDL_LoadFile_RW`
(`SDL2Helpers.h`). Для zip-мода `fullpath` — не файл на диске, поэтому `plm_create_with_memory`.

## 6. Звук

`Mod::getSound(set, id)->play()`; произвольный файл мода — `Sound::load(path)` (SDL_mixer). Звук
MP2 из pl_mpeg в SDL_mixer напрямую не идёт (нужен свой поток PCM) — ролики без звука, звук взлёта
играет игра.

## 7. State поверх геоскейпа

`pushState`/`popState`; ввод — переопределить `handle(Action*)`; пока наверху другой state,
`GeoscapeState::think` не идёт — время стоит. `VideoState`/`FlcPlayer` блокирующие (свой цикл
`flip`) — для ролика вылета не годятся.

## 8. Вид базы и ангар корабля

`BaseView` 192×192 в `(0,8)` у `BasescapeState`; HD рисует `drawHd()` в масштабе `k`, параметра
зума нет. Ангар корабля — повторить раздачу «Draw crafts» (`BaseView.cpp:1324-1363`): корабли базы
по порядку → постройки с `getBuildTime()==0 && getRules()->getCrafts()>0` по порядку, один на один,
и вылетевший тоже занимает свой. Прямоугольник в world:
`((view.x + fac.x*32)*k, (view.y + fac.y*32)*k, sizeX*32*k, sizeY*32*k)`.

## 9. CMake

Новые `.cpp` — в `engine_src` (`src/CMakeLists.txt`, рядом с `Engine/HdKillCam.cpp`) и в
`src/OpenXcom.2010.vcxproj(.filters)`. pl_mpeg — `#include "../../libs/pl_mpeg/pl_mpeg.h"` как
miniz, реализация в одном `.cpp` (`PL_MPEG_IMPLEMENTATION`).
