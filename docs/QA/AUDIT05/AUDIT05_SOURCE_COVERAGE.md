# AUDIT-05 — покрытие исходников

Собирается скриптом `docs/QA/AUDIT05/tools/inventory.py`, руками не править. Отметки о проверке — в
`inventory/review_status.tsv` (их ведёт аудитор), скрипт только переносит их сюда.

Проверяемый SHA: `2c1dff5ae703d9ad3706ac618c05d77b0d65eb26`. Базы происхождения: OpenXcom — `4a4bae5fa` (upstream/master), OXCE 8.7.1 — `441cae1b0`.

Файлов: **989**, строк: **397535**, функций (по индексу): **13921**. Проверено файлов: **65**, не проверено: **924**.
Сторонние библиотеки `libs/` (155 файлов, 79671 строк) в пофайловый список не входят.

Статусы: `NOT_REVIEWED` — не читан аудитором; `PARTIAL` — прочитаны названные функции; `REVIEWED` — прочитан
целиком; `OUT_OF_SCOPE` — исключён с причиной. Сообщения cppcheck и clang-tidy показаны справочно:
файл, который видел только анализатор, проверенным не считается.

## По подсистемам

| Подсистема | Этап | Файлов | Строк | Функций | Своих строк (+) | Файлов с тестом | Проверено |
|---|---|---|---|---|---|---|---|
| HD-слой | F | 89 | 45956 | 1505 | 45956 | 3 | 1 |
| База | E | 139 | 37824 | 977 | 6927 | 0 | 0 |
| Правила и загрузка модов | F | 103 | 34235 | 2119 | 2057 | 0 | 0 |
| Геоскейп | E | 98 | 28733 | 658 | 3995 | 0 | 1 |
| Состояние игры и сейвы | B | 66 | 27258 | 1245 | 1022 | 0 | 5 |
| Движок: масштабирование и звук | G | 19 | 18228 | 209 | 0 | 0 | 0 |
| Состояние боя | B | 13 | 18190 | 992 | 770 | 0 | 3 |
| Бой: ядро | C | 36 | 18160 | 420 | 2000 | 1 | 36 |
| Меню | G | 82 | 17466 | 431 | 5762 | 0 | 5 |
| Скрипты (Y-script, Lua) | F | 9 | 15740 | 1032 | 6541 | 1 | 0 |
| Бой: отрисовка | C | 18 | 14421 | 378 | 9953 | 0 | 0 |
| Бой: экраны и прочее | C | 60 | 14334 | 307 | 1924 | 0 | 1 |
| Движок: данные, файлы, опции | F | 27 | 12496 | 536 | 509 | 2 | 2 |
| Движок: прочее | G | 36 | 12486 | 444 | 6362 | 0 | 0 |
| ИИ: стенд и опытный код | D | 12 | 11431 | 580 | 11431 | 0 | 3 |
| Уфопедия | G | 48 | 10593 | 209 | 368 | 0 | 0 |
| Виджеты | G | 38 | 9278 | 401 | 1516 | 0 | 0 |
| Генерация боя и итог | E | 8 | 8927 | 112 | 330 | 0 | 0 |
| Сторонний код в src | F | 5 | 8623 | 266 | 0 | 0 | 0 |
| Движок: ядро и жизнь объектов | B | 20 | 7901 | 352 | 1377 | 0 | 2 |
| ИИ | D | 2 | 7694 | 138 | 4513 | 0 | 1 |
| Инвентарь | E | 16 | 7117 | 166 | 1304 | 0 | 1 |
| Правила: карты и миссии | E | 16 | 4522 | 278 | 18 | 0 | 1 |
| Поиск пути | D | 6 | 2927 | 92 | 691 | 0 | 1 |
| Меню: сохранение и загрузка | B | 12 | 1528 | 36 | 47 | 0 | 2 |
| Тесты | A | 5 | 692 | 0 | 0 | 0 | 0 |
| Прочее | G | 2 | 391 | 12 | 0 | 0 | 0 |
| Запуск | B | 4 | 384 | 26 | 10 | 0 | 0 |

## По происхождению

«После OXCE» — строки, добавленные после базы OXCE 8.7.1 (итог по дифу); из них «форк» — строки коммитов
автора rackrossum (сумма по коммитам, поэтому может не совпадать с итогом).

| Происхождение | Файлов | Строк | Функций | Добавлено OXCE к OpenXcom | После OXCE | из них форк |
|---|---|---|---|---|---|---|
| OpenXcom | 616 | 240607 | 8551 | 92782 | 28072 | 1117 |
| HD (свой) | 171 | 80675 | 2985 | 0 | 79983 | 0 |
| OXCE | 162 | 41355 | 1665 | 0 | 1405 | 34 |
| чужой форк (rackrossum) | 7 | 1007 | 42 | 0 | 1007 | 966 |
| сторонний (через OpenXcom/OXCE) | 32 | 28992 | 547 | 170 | 17 | 0 |
| сторонний (добавлен нами) | 1 | 4899 | 131 | 0 | 4899 | 0 |

## По файлам

Полные столбцы (опасные операции, владение, глобальные переменные, включения) — `inventory/files.tsv`.


### HD-слой (этап F)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Engine/HdAmmoHint.h` | HD | 36 | 2 | 36/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdBase.cpp` | HD | 681 | 27 | 681/0 | 0/0 | 9 | — | NOT_REVIEWED |
| `src/Engine/HdBase.h` | HD | 92 | 0 | 92/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdBaseLife.cpp` | HD | 1421 | 41 | 1421/0 | 0/0 | 2 | — | NOT_REVIEWED |
| `src/Engine/HdBaseLife.h` | HD | 100 | 0 | 100/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdBaseScene.cpp` | HD | 2949 | 77 | 2949/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdBaseScene.h` | HD | 387 | 0 | 387/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdBattleHud.cpp` | HD | 2870 | 118 | 2870/0 | 0/0 | 17 | — | NOT_REVIEWED |
| `src/Engine/HdBattleHud.h` | HD | 176 | 8 | 176/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdBlit.cpp` | HD | 131 | 4 | 131/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdBlit.h` | HD | 49 | 0 | 49/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdCanvas.cpp` | HD | 3636 | 125 | 3636/0 | 0/2 | 1 | — | NOT_REVIEWED |
| `src/Engine/HdCanvas.h` | HD | 710 | 46 | 710/0 | 0/2 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdChatNotice.cpp` | HD | 394 | 13 | 394/0 | 1/2 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdChatNotice.h` | HD | 89 | 0 | 89/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdControl.cpp` | HD | 964 | 23 | 964/0 | 2/0 | 0 | — | PARTIAL |
| `src/Engine/HdControl.h` | HD | 43 | 0 | 43/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdCraftBack.cpp` | HD | 304 | 11 | 304/0 | 2/0 | 2 | — | NOT_REVIEWED |
| `src/Engine/HdCraftBack.h` | HD | 48 | 0 | 48/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdCraftLights.cpp` | HD | 458 | 13 | 458/0 | 0/0 | 3 | — | NOT_REVIEWED |
| `src/Engine/HdCraftLights.h` | HD | 79 | 0 | 79/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdCraftRoute.cpp` | HD | 223 | 11 | 223/0 | 1/0 | 3 | — | NOT_REVIEWED |
| `src/Engine/HdCraftRoute.h` | HD | 67 | 0 | 67/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdFire.cpp` | HD | 348 | 15 | 348/0 | 1/0 | 2 | — | NOT_REVIEWED |
| `src/Engine/HdFire.h` | HD | 81 | 0 | 81/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdFont.cpp` | HD | 358 | 14 | 358/0 | 2/2 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdFont.h` | HD | 104 | 4 | 104/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdFx.cpp` | HD | 1183 | 60 | 1183/0 | 0/0 | 22 | — | NOT_REVIEWED |
| `src/Engine/HdFx.h` | HD | 159 | 0 | 159/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdGentle.h` | HD | 104 | 13 | 104/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdGpu.cpp` | HD | 430 | 22 | 430/0 | 0/0 | 4 | — | NOT_REVIEWED |
| `src/Engine/HdGpu.h` | HD | 73 | 5 | 73/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdGpuAtlas.h` | HD | 282 | 11 | 282/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdGpuCanvas.cpp` | HD | 1594 | 12 | 1594/0 | 1/3 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdGpuCanvas.h` | HD | 80 | 0 | 80/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdGpuGl.h` | HD | 192 | 0 | 192/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdGpuTold.h` | HD | 72 | 2 | 72/0 | 0/0 | 0 | есть | NOT_REVIEWED |
| `src/Engine/HdGpuWorld.cpp` | HD | 2393 | 76 | 2393/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdGpuWorld.h` | HD | 230 | 3 | 230/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdItems.cpp` | HD | 760 | 26 | 760/0 | 2/0 | 12 | — | NOT_REVIEWED |
| `src/Engine/HdItems.h` | HD | 124 | 0 | 124/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdKillCam.cpp` | HD | 196 | 11 | 196/0 | 0/0 | 4 | — | NOT_REVIEWED |
| `src/Engine/HdKillCam.h` | HD | 60 | 0 | 60/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdLab.h` | HD | 113 | 6 | 113/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdOutline.cpp` | HD | 391 | 11 | 391/0 | 0/0 | 5 | — | NOT_REVIEWED |
| `src/Engine/HdOutline.h` | HD | 63 | 0 | 63/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdPaletteShift.cpp` | HD | 528 | 17 | 528/0 | 0/0 | 5 | — | NOT_REVIEWED |
| `src/Engine/HdPaletteShift.h` | HD | 55 | 0 | 55/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdPilotVoice.cpp` | HD | 283 | 11 | 283/0 | 1/0 | 2 | — | NOT_REVIEWED |
| `src/Engine/HdPilotVoice.h` | HD | 39 | 0 | 39/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdPlateCanvas.cpp` | HD | 298 | 24 | 298/0 | 2/2 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdPlateCanvas.h` | HD | 110 | 1 | 110/0 | 0/2 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdRadar.cpp` | HD | 1222 | 32 | 1222/0 | 0/0 | 1 | — | NOT_REVIEWED |
| `src/Engine/HdRadar.h` | HD | 174 | 4 | 174/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdScreenThemes.cpp` | HD | 653 | 33 | 653/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdScreenThemes.h` | HD | 156 | 4 | 156/0 | 0/2 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdScreens.cpp` | HD | 617 | 31 | 617/0 | 0/0 | 8 | — | NOT_REVIEWED |
| `src/Engine/HdScreens.h` | HD | 61 | 0 | 61/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdShots.cpp` | HD | 611 | 24 | 611/0 | 0/0 | 6 | — | NOT_REVIEWED |
| `src/Engine/HdShots.h` | HD | 97 | 1 | 97/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdSmoke.cpp` | HD | 265 | 12 | 265/0 | 1/0 | 2 | — | NOT_REVIEWED |
| `src/Engine/HdSmoke.h` | HD | 73 | 0 | 73/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdSmooth.cpp` | HD | 390 | 8 | 390/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdSmooth.h` | HD | 50 | 0 | 50/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdSprites.cpp` | HD | 2413 | 86 | 2413/0 | 0/2 | 18 | — | NOT_REVIEWED |
| `src/Engine/HdSprites.h` | HD | 266 | 9 | 266/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdTest.cpp` | HD | 189 | 4 | 189/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdTest.h` | HD | 50 | 0 | 50/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdTrackNotice.cpp` | HD | 164 | 8 | 164/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdTrackNotice.h` | HD | 63 | 0 | 63/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdTurn.cpp` | HD | 362 | 16 | 362/0 | 2/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdTurn.h` | HD | 103 | 1 | 103/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdTurnGroups.cpp` | HD | 192 | 6 | 192/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdTurnGroups.h` | HD | 94 | 4 | 94/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdTurnGroupsTable.inc` | HD | 1324 | 0 | 1324/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdUi.cpp` | HD | 1610 | 48 | 1610/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdUi.h` | HD | 474 | 18 | 474/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdUiArt.cpp` | HD | 1291 | 50 | 1291/0 | 5/0 | 17 | — | NOT_REVIEWED |
| `src/Engine/HdUiArt.h` | HD | 147 | 0 | 147/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdUiDraw.cpp` | HD | 2193 | 97 | 2193/0 | 0/0 | 2 | — | NOT_REVIEWED |
| `src/Engine/HdUpdateNotice.cpp` | HD | 176 | 7 | 176/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdUpdateNotice.h` | HD | 65 | 0 | 65/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdVideo.cpp` | HD | 310 | 10 | 310/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdVideo.h` | HD | 73 | 2 | 73/0 | 0/2 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdWeather.cpp` | HD | 1619 | 57 | 1619/0 | 1/0 | 5 | — | NOT_REVIEWED |
| `src/Engine/HdWeather.h` | HD | 242 | 1 | 242/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HdWeatherExtras.cpp` | HD | 1037 | 48 | 1037/0 | 0/0 | 15 | — | NOT_REVIEWED |
| `src/Engine/HdWorkers.cpp` | HD | 391 | 16 | 391/0 | 0/0 | 0 | есть | NOT_REVIEWED |
| `src/Engine/HdWorkers.h` | HD | 129 | 5 | 129/0 | 0/0 | 0 | есть | NOT_REVIEWED |

### База (этап E)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Basescape/BaseInfoState.cpp` | OpenXcom | 539 | 11 | 18/1 | 48/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/BaseInfoState.h` | OpenXcom | 87 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/BaseSwitch.cpp` | HD | 103 | 2 | 103/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/BaseSwitch.h` | HD | 165 | 8 | 165/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/BaseView.cpp` | OpenXcom | 1902 | 41 | 1178/14 | 4/6 | 1 | — | NOT_REVIEWED |
| `src/Basescape/BaseView.h` | OpenXcom | 149 | 2 | 44/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/BasescapeState.cpp` | OpenXcom | 697 | 24 | 30/21 | 62/1 | 0 | — | NOT_REVIEWED |
| `src/Basescape/BasescapeState.h` | OpenXcom | 98 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/BuildFacilitiesState.cpp` | OpenXcom | 234 | 6 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/BuildFacilitiesState.h` | OpenXcom | 64 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftArmorState.cpp` | OpenXcom | 707 | 16 | 24/2 | 15/1 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftArmorState.h` | OpenXcom | 84 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftEquipmentLoadState.cpp` | OXCE | 129 | 4 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftEquipmentLoadState.h` | OXCE | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftEquipmentSaveState.cpp` | OXCE | 204 | 7 | 0/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftEquipmentSaveState.h` | OXCE | 64 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftEquipmentState.cpp` | OpenXcom | 1287 | 37 | 108/3 | 25/2 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftEquipmentState.h` | OpenXcom | 137 | 0 | 18/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftInfoState.cpp` | OpenXcom | 951 | 23 | 215/0 | 27/2 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftInfoState.h` | OpenXcom | 122 | 0 | 34/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftPilotSelectState.cpp` | OXCE | 149 | 4 | 0/0 | 8/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftPilotSelectState.h` | OXCE | 58 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftPilotsState.cpp` | OXCE | 254 | 7 | 0/0 | 18/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftPilotsState.h` | OXCE | 65 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftSoldiersState.cpp` | OpenXcom | 1107 | 30 | 543/118 | 22/1 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftSoldiersState.h` | OpenXcom | 117 | 0 | 32/3 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftWeaponsState.cpp` | OpenXcom | 317 | 5 | 0/0 | 13/1 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftWeaponsState.h` | OpenXcom | 63 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftsState.cpp` | OpenXcom | 272 | 8 | 48/2 | 15/1 | 0 | — | NOT_REVIEWED |
| `src/Basescape/CraftsState.h` | OpenXcom | 60 | 0 | 4/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/DismantleFacilityState.cpp` | OpenXcom | 260 | 4 | 0/0 | 8/2 | 0 | — | NOT_REVIEWED |
| `src/Basescape/DismantleFacilityState.h` | OpenXcom | 57 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/GlobalAlienContainmentState.cpp` | OXCE | 297 | 7 | 1/1 | 11/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/GlobalAlienContainmentState.h` | OXCE | 61 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/GlobalManufactureState.cpp` | OXCE | 270 | 7 | 1/1 | 15/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/GlobalManufactureState.h` | OXCE | 63 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/GlobalResearchDiaryState.cpp` | OXCE | 389 | 18 | 0/0 | 12/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/GlobalResearchDiaryState.h` | OXCE | 106 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/GlobalResearchState.cpp` | OXCE | 236 | 8 | 1/1 | 14/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/GlobalResearchState.h` | OXCE | 66 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/GlobalTransfersState.cpp` | HD | 191 | 6 | 191/0 | 9/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/GlobalTransfersState.h` | HD | 44 | 0 | 44/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/HighlightLowManaSoldiersMixin.h` | чужой форк (rackrossum) | 33 | 1 | 33/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ItemCountTooltip.cpp` | чужой форк (rackrossum) | 316 | 13 | 316/0 | 2/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ItemCountTooltip.h` | чужой форк (rackrossum) | 71 | 0 | 71/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ItemCountTooltipMixin.h` | чужой форк (rackrossum) | 91 | 8 | 91/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ItemLocationsState.cpp` | OXCE | 107 | 2 | 0/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ItemLocationsState.h` | OXCE | 50 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManageAlienContainmentState.cpp` | OpenXcom | 657 | 29 | 13/0 | 28/2 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManageAlienContainmentState.h` | OpenXcom | 111 | 0 | 2/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureDeliveryPlanState.cpp` | HD | 210 | 8 | 210/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureDeliveryPlanState.h` | HD | 68 | 0 | 68/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureDeliveryState.cpp` | HD | 592 | 37 | 592/0 | 21/4 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureDeliveryState.h` | HD | 139 | 0 | 139/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureDependenciesTreeState.cpp` | OXCE | 354 | 6 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureDependenciesTreeState.h` | OXCE | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureInfoState.cpp` | OpenXcom | 931 | 46 | 155/0 | 40/4 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureInfoState.h` | OpenXcom | 145 | 0 | 14/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureStartState.cpp` | OpenXcom | 300 | 5 | 44/0 | 14/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureStartState.h` | OpenXcom | 61 | 0 | 9/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureState.cpp` | OpenXcom | 460 | 18 | 160/7 | 19/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ManufactureState.h` | OpenXcom | 80 | 0 | 18/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/MiniBaseView.cpp` | OpenXcom | 175 | 11 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/MiniBaseView.h` | OpenXcom | 66 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/MonthlyCostsState.cpp` | OpenXcom | 223 | 3 | 0/0 | 14/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/MonthlyCostsState.h` | OpenXcom | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/NewManufactureListState.cpp` | OpenXcom | 555 | 16 | 24/4 | 12/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/NewManufactureListState.h` | OpenXcom | 91 | 0 | 6/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/NewResearchListState.cpp` | OpenXcom | 421 | 16 | 0/0 | 9/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/NewResearchListState.h` | OpenXcom | 78 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/PlaceFacilityState.cpp` | OpenXcom | 395 | 4 | 1/0 | 34/1 | 0 | — | NOT_REVIEWED |
| `src/Basescape/PlaceFacilityState.h` | OpenXcom | 59 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/PlaceLiftState.cpp` | OpenXcom | 199 | 4 | 1/0 | 8/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/PlaceLiftState.h` | OpenXcom | 62 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/PlaceStartFacilityState.cpp` | OpenXcom | 83 | 3 | 0/0 | 2/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/PlaceStartFacilityState.h` | OpenXcom | 45 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/PurchaseState.cpp` | OpenXcom | 1424 | 42 | 83/5 | 26/2 | 0 | — | NOT_REVIEWED |
| `src/Basescape/PurchaseState.h` | OpenXcom | 139 | 2 | 15/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ResearchInfoState.cpp` | OpenXcom | 496 | 24 | 138/13 | 17/2 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ResearchInfoState.h` | OpenXcom | 99 | 0 | 8/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ResearchState.cpp` | OpenXcom | 410 | 16 | 44/7 | 18/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/ResearchState.h` | OpenXcom | 74 | 0 | 2/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SackSoldierState.cpp` | OpenXcom | 118 | 4 | 0/0 | 5/1 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SackSoldierState.h` | OpenXcom | 54 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SelectStartFacilityState.cpp` | OpenXcom | 117 | 6 | 0/0 | 2/1 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SelectStartFacilityState.h` | OpenXcom | 50 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SellState.cpp` | OpenXcom | 1377 | 46 | 95/1 | 26/6 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SellState.h` | OpenXcom | 143 | 2 | 15/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierArmorState.cpp` | OpenXcom | 344 | 12 | 0/0 | 9/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierArmorState.h` | OpenXcom | 101 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierAvatarState.cpp` | OXCE | 237 | 6 | 4/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierAvatarState.h` | OXCE | 66 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierBonusState.cpp` | OXCE | 282 | 5 | 0/0 | 8/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierBonusState.h` | OXCE | 63 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierDiaryLightState.cpp` | OXCE | 102 | 3 | 0/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierDiaryLightState.h` | OXCE | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierDiaryMissionState.cpp` | OpenXcom | 220 | 6 | 2/2 | 14/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierDiaryMissionState.h` | OpenXcom | 62 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierDiaryOverviewState.cpp` | OpenXcom | 344 | 11 | 0/0 | 19/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierDiaryOverviewState.h` | OpenXcom | 78 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierDiaryPerformanceState.cpp` | OpenXcom | 532 | 15 | 4/1 | 17/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierDiaryPerformanceState.h` | OpenXcom | 96 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierInfoState.cpp` | OpenXcom | 864 | 21 | 52/3 | 65/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierInfoState.h` | OpenXcom | 97 | 0 | 57/58 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierMemorialState.cpp` | OpenXcom | 234 | 9 | 0/0 | 13/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierMemorialState.h` | OpenXcom | 63 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierRankState.cpp` | OXCE | 167 | 5 | 0/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierRankState.h` | OXCE | 69 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierSortUtil.cpp` | OXCE | 191 | 16 | 28/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierSortUtil.h` | OXCE | 113 | 3 | 6/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierTransformState.cpp` | OXCE | 287 | 12 | 0/0 | 8/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierTransformState.h` | OXCE | 92 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierTransformationListState.cpp` | OXCE | 374 | 10 | 0/0 | 11/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierTransformationListState.h` | OXCE | 78 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierTransformationState.cpp` | OXCE | 748 | 15 | 126/1 | 20/2 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierTransformationState.h` | OXCE | 85 | 0 | 12/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierVoiceState.cpp` | OXCE | 368 | 12 | 0/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldierVoiceState.h` | OXCE | 102 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldiersState.cpp` | OpenXcom | 764 | 19 | 57/112 | 28/1 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SoldiersState.h` | OpenXcom | 94 | 0 | 4/3 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/SortSoldiersMixin.h` | чужой форк (rackrossum) | 272 | 14 | 272/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/StoresState.cpp` | OpenXcom | 557 | 24 | 49/0 | 16/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/StoresState.h` | OpenXcom | 122 | 1 | 9/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TechTreeSelectState.cpp` | OXCE | 406 | 8 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TechTreeSelectState.h` | OXCE | 64 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TechTreeViewerState.cpp` | OXCE | 2089 | 21 | 23/0 | 11/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TechTreeViewerState.h` | OXCE | 99 | 0 | 4/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TradeConfirmState.cpp` | HD | 139 | 6 | 139/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TradeConfirmState.h` | HD | 58 | 0 | 58/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TrainingBlocksState.cpp` | HD | 100 | 3 | 100/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TrainingBlocksState.h` | HD | 51 | 0 | 51/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TransferBaseState.cpp` | OpenXcom | 234 | 8 | 97/6 | 9/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TransferBaseState.h` | OpenXcom | 74 | 0 | 16/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TransferConfirmState.cpp` | OpenXcom | 129 | 4 | 11/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TransferConfirmState.h` | OpenXcom | 56 | 0 | 3/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TransferItemsState.cpp` | OpenXcom | 1549 | 42 | 525/130 | 28/2 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TransferItemsState.h` | OpenXcom | 149 | 1 | 23/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TransfersState.cpp` | OpenXcom | 136 | 3 | 24/2 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Basescape/TransfersState.h` | OpenXcom | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Бой: отрисовка (этап C)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Battlescape/Camera.cpp` | OpenXcom | 967 | 45 | 365/39 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/Camera.h` | OpenXcom | 164 | 6 | 46/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/Map.cpp` | OpenXcom | 3792 | 121 | 2024/874 | 17/25 | 1 | — | NOT_REVIEWED |
| `src/Battlescape/Map.h` | OpenXcom | 713 | 16 | 492/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MapAim.cpp` | HD | 766 | 12 | 766/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MapCell.cpp` | HD | 1015 | 15 | 1015/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MapEdge.cpp` | HD | 986 | 21 | 986/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MapFx.cpp` | HD | 489 | 15 | 489/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MapHd.h` | HD | 99 | 1 | 99/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MapLight.cpp` | HD | 566 | 12 | 566/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MapOverlay.cpp` | HD | 783 | 16 | 783/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MapShadows.cpp` | HD | 705 | 14 | 705/0 | 0/0 | 1 | — | NOT_REVIEWED |
| `src/Battlescape/MapSteps.cpp` | HD | 621 | 16 | 621/0 | 0/0 | 1 | — | NOT_REVIEWED |
| `src/Battlescape/MapWeather.cpp` | HD | 762 | 24 | 762/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/UnitSprite.cpp` | OpenXcom | 1622 | 28 | 190/57 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/UnitSprite.h` | OpenXcom | 134 | 5 | 16/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/WarningMessage.cpp` | OpenXcom | 172 | 11 | 25/2 | 2/2 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/WarningMessage.h` | OpenXcom | 65 | 0 | 3/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Бой: экраны и прочее (этап C)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Battlescape/AbortMissionState.cpp` | OpenXcom | 234 | 4 | 2/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/AbortMissionState.h` | OpenXcom | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ActionMenuState.cpp` | OpenXcom | 556 | 10 | 16/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ActionMenuState.h` | OpenXcom | 60 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/AlienInventory.cpp` | OXCE | 298 | 13 | 11/0 | 3/3 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/AlienInventory.h` | OXCE | 72 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/AlienInventoryState.cpp` | OXCE | 515 | 8 | 5/0 | 9/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/AlienInventoryState.h` | OXCE | 62 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/AliensCrashState.cpp` | OpenXcom | 88 | 3 | 2/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/AliensCrashState.h` | OpenXcom | 48 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/BattlescapeMessage.cpp` | OpenXcom | 264 | 15 | 62/3 | 4/4 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/BattlescapeMessage.h` | OpenXcom | 78 | 0 | 4/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/BattlescapeState.cpp` | OpenXcom | 4659 | 110 | 574/41 | 96/3 | 0 | — | PARTIAL |
| `src/Battlescape/BattlescapeState.h` | OpenXcom | 328 | 0 | 36/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CannotReequipState.cpp` | OpenXcom | 202 | 9 | 24/1 | 13/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CannotReequipState.h` | OpenXcom | 71 | 0 | 5/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CommendationLateState.cpp` | OpenXcom | 207 | 4 | 0/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CommendationLateState.h` | OpenXcom | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CommendationState.cpp` | OpenXcom | 215 | 4 | 22/2 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CommendationState.h` | OpenXcom | 58 | 0 | 6/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ConfirmEndMissionState.cpp` | OXCE | 137 | 5 | 19/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ConfirmEndMissionState.h` | OXCE | 57 | 0 | 2/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ExperienceOverviewState.cpp` | OXCE | 220 | 3 | 2/0 | 13/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ExperienceOverviewState.h` | OXCE | 57 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ExtendedBattlescapeLinksState.cpp` | OXCE | 248 | 11 | 0/0 | 27/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ExtendedBattlescapeLinksState.h` | OXCE | 62 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InfoboxOKState.cpp` | OpenXcom | 110 | 4 | 18/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InfoboxOKState.h` | OpenXcom | 50 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InfoboxState.cpp` | OpenXcom | 114 | 5 | 1/0 | 3/1 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InfoboxState.h` | OpenXcom | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MedikitState.cpp` | OpenXcom | 315 | 11 | 1/0 | 14/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MedikitState.h` | OpenXcom | 62 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MedikitView.cpp` | OpenXcom | 132 | 5 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MedikitView.h` | OpenXcom | 49 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MiniMapState.cpp` | OpenXcom | 169 | 8 | 1/0 | 7/1 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MiniMapState.h` | OpenXcom | 60 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MiniMapView.cpp` | OpenXcom | 498 | 11 | 41/5 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/MiniMapView.h` | OpenXcom | 74 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/NextTurnState.cpp` | OpenXcom | 1153 | 14 | 12/2 | 12/2 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/NextTurnState.h` | OpenXcom | 92 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/NoExperienceState.cpp` | OXCE | 109 | 2 | 2/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/NoExperienceState.h` | OXCE | 49 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/PrimeGrenadeState.cpp` | OpenXcom | 198 | 4 | 1/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/PrimeGrenadeState.h` | OpenXcom | 59 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/PromotionsState.cpp` | OpenXcom | 125 | 3 | 0/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/PromotionsState.h` | OpenXcom | 49 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ReequipManufactureState.cpp` | HD | 243 | 6 | 243/0 | 9/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ReequipManufactureState.h` | HD | 64 | 0 | 64/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ScannerState.cpp` | OpenXcom | 137 | 7 | 1/0 | 4/1 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ScannerState.h` | OpenXcom | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ScannerView.cpp` | OpenXcom | 110 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ScannerView.h` | OpenXcom | 45 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/SkillMenuState.cpp` | OXCE | 316 | 5 | 1/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/SkillMenuState.h` | OXCE | 45 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/SoldierStatChangeState.cpp` | HD | 406 | 11 | 406/0 | 11/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/SoldierStatChangeState.h` | HD | 110 | 0 | 110/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/TurnDiaryState.cpp` | OXCE | 105 | 2 | 2/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/TurnDiaryState.h` | OXCE | 50 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/UnitTeleportingState.cpp` | чужой форк (rackrossum) | 159 | 5 | 159/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/UnitTeleportingState.h` | чужой форк (rackrossum) | 65 | 1 | 65/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Бой: ядро (этап C)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Battlescape/BattleState.cpp` | OpenXcom | 96 | 8 | 0/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/BattleState.h` | OpenXcom | 53 | 0 | 0/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/BattlescapeGame.cpp` | OpenXcom | 3794 | 80 | 490/82 | 49/4 | 0 | — | REVIEWED |
| `src/Battlescape/BattlescapeGame.h` | OpenXcom | 313 | 10 | 18/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/Explosion.cpp` | OpenXcom | 136 | 8 | 12/2 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/Explosion.h` | OpenXcom | 86 | 10 | 32/2 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/ExplosionBState.cpp` | OpenXcom | 560 | 7 | 69/5 | 3/1 | 0 | — | REVIEWED |
| `src/Battlescape/ExplosionBState.h` | OpenXcom | 78 | 1 | 9/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/KnowledgeArmor.cpp` | HD | 117 | 3 | 117/0 | 0/0 | 1 | — | REVIEWED |
| `src/Battlescape/KnowledgeArmor.h` | HD | 57 | 0 | 57/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/MeleeAttackBState.cpp` | OpenXcom | 249 | 5 | 4/0 | 1/0 | 0 | — | REVIEWED |
| `src/Battlescape/MeleeAttackBState.h` | OpenXcom | 57 | 0 | 0/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/Particle.cpp` | OpenXcom | 122 | 4 | 15/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/Particle.h` | OpenXcom | 88 | 10 | 15/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/Position.cpp` | OXCE | 43 | 2 | 0/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/Position.h` | OpenXcom | 162 | 25 | 0/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/Projectile.cpp` | OpenXcom | 828 | 20 | 96/1 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/Projectile.h` | OpenXcom | 112 | 4 | 15/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/ProjectileFlyBState.cpp` | OpenXcom | 1083 | 15 | 72/5 | 6/5 | 0 | — | REVIEWED |
| `src/Battlescape/ProjectileFlyBState.h` | OpenXcom | 75 | 0 | 2/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/PsiAttackBState.cpp` | OpenXcom | 124 | 4 | 2/0 | 1/0 | 0 | — | REVIEWED |
| `src/Battlescape/PsiAttackBState.h` | OpenXcom | 50 | 0 | 0/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/TileEngine.cpp` | OpenXcom | 6613 | 156 | 625/65 | 5/0 | 0 | есть | REVIEWED |
| `src/Battlescape/TileEngine.h` | OpenXcom | 316 | 8 | 13/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitDieBState.cpp` | OpenXcom | 475 | 9 | 120/6 | 3/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitDieBState.h` | OpenXcom | 67 | 0 | 9/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitFallBState.cpp` | OpenXcom | 277 | 4 | 5/2 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitFallBState.h` | OpenXcom | 50 | 0 | 0/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitInfoState.cpp` | OpenXcom | 851 | 7 | 112/40 | 74/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitInfoState.h` | OpenXcom | 82 | 0 | 3/1 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitPanicBState.cpp` | OpenXcom | 156 | 5 | 0/0 | 2/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitPanicBState.h` | OpenXcom | 49 | 0 | 0/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitTurnBState.cpp` | OpenXcom | 155 | 5 | 3/2 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitTurnBState.h` | OpenXcom | 48 | 0 | 0/0 | 0/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitWalkBState.cpp` | OpenXcom | 667 | 10 | 85/11 | 3/0 | 0 | — | REVIEWED |
| `src/Battlescape/UnitWalkBState.h` | OpenXcom | 71 | 0 | 0/0 | 0/0 | 0 | — | REVIEWED |

### Виджеты (этап G)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Interface/ArrowButton.cpp` | OpenXcom | 413 | 13 | 38/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Interface/ArrowButton.h` | OpenXcom | 70 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/Bar.cpp` | OpenXcom | 296 | 19 | 78/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/Bar.h` | OpenXcom | 76 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/BattlescapeButton.cpp` | OpenXcom | 294 | 15 | 50/1 | 1/2 | 0 | — | NOT_REVIEWED |
| `src/Interface/BattlescapeButton.h` | OpenXcom | 86 | 3 | 12/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/ComboBox.cpp` | OpenXcom | 477 | 28 | 21/0 | 4/4 | 0 | — | NOT_REVIEWED |
| `src/Interface/ComboBox.h` | OpenXcom | 114 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/Cursor.cpp` | OpenXcom | 132 | 8 | 27/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/Cursor.h` | OpenXcom | 54 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/FpsCounter.cpp` | OpenXcom | 148 | 10 | 24/0 | 2/2 | 0 | — | NOT_REVIEWED |
| `src/Interface/FpsCounter.h` | OpenXcom | 62 | 0 | 3/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/Frame.cpp` | OpenXcom | 192 | 11 | 27/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/Frame.h` | OpenXcom | 58 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/ImageButton.cpp` | OpenXcom | 127 | 8 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/ImageButton.h` | OpenXcom | 57 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/MusicNoteButton.cpp` | HD | 119 | 8 | 119/0 | 1/1 | 1 | — | NOT_REVIEWED |
| `src/Interface/MusicNoteButton.h` | HD | 52 | 0 | 52/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/NumberText.cpp` | OpenXcom | 361 | 11 | 56/0 | 11/2 | 0 | — | NOT_REVIEWED |
| `src/Interface/NumberText.h` | OpenXcom | 69 | 2 | 10/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/ProgressBar.cpp` | OXCE | 162 | 9 | 35/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/ProgressBar.h` | OXCE | 55 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/ScrollBar.cpp` | OpenXcom | 347 | 19 | 20/0 | 2/2 | 0 | — | NOT_REVIEWED |
| `src/Interface/ScrollBar.h` | OpenXcom | 81 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/Slider.cpp` | OpenXcom | 353 | 19 | 45/2 | 4/4 | 0 | — | NOT_REVIEWED |
| `src/Interface/Slider.h` | OpenXcom | 87 | 0 | 3/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/Text.cpp` | OpenXcom | 794 | 34 | 120/4 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/Text.h` | OpenXcom | 133 | 5 | 22/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/TextButton.cpp` | OpenXcom | 434 | 25 | 72/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Interface/TextButton.h` | OpenXcom | 103 | 1 | 10/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/TextEdit.cpp` | OpenXcom | 633 | 30 | 33/0 | 3/3 | 0 | — | NOT_REVIEWED |
| `src/Interface/TextEdit.h` | OpenXcom | 114 | 1 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/TextList.cpp` | OpenXcom | 1773 | 92 | 399/19 | 13/16 | 0 | — | NOT_REVIEWED |
| `src/Interface/TextList.h` | OpenXcom | 253 | 0 | 39/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/ToggleTextButton.cpp` | OpenXcom | 105 | 8 | 13/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/ToggleTextButton.h` | OpenXcom | 49 | 1 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Interface/Window.cpp` | OpenXcom | 445 | 19 | 156/16 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Interface/Window.h` | OpenXcom | 100 | 2 | 14/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Генерация боя и итог (этап E)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Battlescape/BattlescapeGenerator.cpp` | OpenXcom | 4999 | 67 | 196/18 | 7/8 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/BattlescapeGenerator.h` | OpenXcom | 216 | 2 | 4/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/BriefingLightState.cpp` | OXCE | 204 | 7 | 2/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/BriefingLightState.h` | OXCE | 60 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/BriefingState.cpp` | OpenXcom | 317 | 5 | 12/0 | 11/1 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/BriefingState.h` | OpenXcom | 58 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/DebriefingState.cpp` | OpenXcom | 2925 | 30 | 104/1 | 71/8 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/DebriefingState.h` | OpenXcom | 148 | 1 | 10/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Геоскейп (этап E)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Geoscape/AlienBaseState.cpp` | OpenXcom | 134 | 3 | 0/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/AlienBaseState.h` | OpenXcom | 52 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/AllocatePsiTrainingState.cpp` | OpenXcom | 631 | 18 | 16/0 | 17/1 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/AllocatePsiTrainingState.h` | OpenXcom | 93 | 0 | 2/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/AllocateTrainingState.cpp` | OXCE | 651 | 18 | 16/0 | 22/1 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/AllocateTrainingState.h` | OXCE | 93 | 0 | 2/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/BaseDefenseState.cpp` | OpenXcom | 509 | 7 | 0/0 | 9/1 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/BaseDefenseState.h` | OpenXcom | 71 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/BaseDestroyedState.cpp` | OpenXcom | 182 | 3 | 0/0 | 6/1 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/BaseDestroyedState.h` | OpenXcom | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/BaseNameState.cpp` | OpenXcom | 160 | 4 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/BaseNameState.h` | OpenXcom | 60 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/BuildNewBaseState.cpp` | OpenXcom | 412 | 22 | 1/0 | 14/2 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/BuildNewBaseState.h` | OpenXcom | 98 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ConfirmCydoniaState.cpp` | OpenXcom | 117 | 4 | 0/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ConfirmCydoniaState.h` | OpenXcom | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ConfirmDestinationState.cpp` | OpenXcom | 538 | 6 | 39/0 | 11/1 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ConfirmDestinationState.h` | OpenXcom | 61 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ConfirmLandingState.cpp` | OpenXcom | 414 | 8 | 72/0 | 10/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ConfirmLandingState.h` | OpenXcom | 65 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ConfirmNewBaseState.cpp` | OpenXcom | 131 | 4 | 1/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ConfirmNewBaseState.h` | OpenXcom | 56 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/Cord.h` | OpenXcom | 135 | 14 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/CraftErrorState.cpp` | OpenXcom | 120 | 4 | 0/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/CraftErrorState.h` | OpenXcom | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/CraftLaunchState.cpp` | HD | 608 | 21 | 608/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/CraftLaunchState.h` | HD | 97 | 0 | 97/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/CraftNotEnoughPilotsState.cpp` | OXCE | 118 | 4 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/CraftNotEnoughPilotsState.h` | OXCE | 52 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/CraftPatrolState.cpp` | OpenXcom | 112 | 4 | 0/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/CraftPatrolState.h` | OpenXcom | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/DogfightErrorState.cpp` | OpenXcom | 106 | 4 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/DogfightErrorState.h` | OpenXcom | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/DogfightExperienceState.cpp` | OXCE | 126 | 2 | 0/0 | 8/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/DogfightExperienceState.h` | OXCE | 49 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/DogfightState.cpp` | OpenXcom | 2972 | 62 | 223/1 | 29/2 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/DogfightState.h` | OpenXcom | 192 | 0 | 10/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ExtendedGeoscapeLinksState.cpp` | OXCE | 219 | 11 | 0/0 | 25/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ExtendedGeoscapeLinksState.h` | OXCE | 60 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/FundingState.cpp` | OpenXcom | 287 | 13 | 0/0 | 10/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/FundingState.h` | OpenXcom | 91 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/GeoscapeCraftState.cpp` | OpenXcom | 469 | 8 | 90/2 | 21/3 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/GeoscapeCraftState.h` | OpenXcom | 74 | 0 | 6/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/GeoscapeEventState.cpp` | OXCE | 601 | 7 | 0/0 | 19/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/GeoscapeEventState.h` | OXCE | 66 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/GeoscapeGlobalTransfers.cpp` | HD | 25 | 1 | 25/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/GeoscapeState.cpp` | OpenXcom | 5193 | 86 | 213/7 | 138/11 | 1 | — | NOT_REVIEWED |
| `src/Geoscape/GeoscapeState.h` | OpenXcom | 213 | 0 | 10/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/Globe.cpp` | OpenXcom | 2979 | 110 | 845/22 | 13/15 | 1 | — | NOT_REVIEWED |
| `src/Geoscape/Globe.h` | OpenXcom | 338 | 4 | 120/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/GraphsState.cpp` | OpenXcom | 1252 | 24 | 0/0 | 35/2 | 0 | — | PARTIAL |
| `src/Geoscape/GraphsState.h` | OpenXcom | 109 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/InterceptState.cpp` | OpenXcom | 600 | 9 | 65/2 | 23/1 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/InterceptState.h` | OpenXcom | 70 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ItemsArrivingState.cpp` | OpenXcom | 164 | 4 | 0/0 | 9/1 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ItemsArrivingState.h` | OpenXcom | 56 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/LowFuelState.cpp` | OpenXcom | 108 | 4 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/LowFuelState.h` | OpenXcom | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/MissionDetectedState.cpp` | OpenXcom | 134 | 5 | 1/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/MissionDetectedState.h` | OpenXcom | 56 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/MonthlyReportState.cpp` | OpenXcom | 522 | 5 | 1/1 | 18/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/MonthlyReportState.h` | OpenXcom | 64 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/MultipleTargetsState.cpp` | OpenXcom | 171 | 6 | 0/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/MultipleTargetsState.h` | OpenXcom | 64 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/NewPossibleCraftState.cpp` | OXCE | 127 | 3 | 1/1 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/NewPossibleCraftState.h` | OXCE | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/NewPossibleFacilityState.cpp` | OXCE | 128 | 3 | 0/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/NewPossibleFacilityState.h` | OXCE | 57 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/NewPossibleManufactureState.cpp` | OpenXcom | 128 | 3 | 1/1 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/NewPossibleManufactureState.h` | OpenXcom | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/NewPossiblePurchaseState.cpp` | OXCE | 127 | 3 | 1/1 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/NewPossiblePurchaseState.h` | OXCE | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/NewPossibleResearchState.cpp` | OpenXcom | 123 | 3 | 2/2 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/NewPossibleResearchState.h` | OpenXcom | 54 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ProductionCompleteState.cpp` | OpenXcom | 730 | 28 | 485/9 | 17/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ProductionCompleteState.h` | OpenXcom | 113 | 0 | 46/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/PsiTrainingState.cpp` | OpenXcom | 119 | 4 | 1/1 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/PsiTrainingState.h` | OpenXcom | 52 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ResearchCompleteState.cpp` | OpenXcom | 127 | 3 | 0/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ResearchCompleteState.h` | OpenXcom | 51 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ResearchRequiredState.cpp` | OpenXcom | 82 | 2 | 0/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/ResearchRequiredState.h` | OpenXcom | 47 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/SelectDestinationState.cpp` | OpenXcom | 408 | 21 | 21/0 | 13/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/SelectDestinationState.h` | OpenXcom | 92 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/SelectMusicTrackState.cpp` | OXCE | 939 | 44 | 867/76 | 2/1 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/SelectMusicTrackState.h` | OXCE | 56 | 0 | 12/19 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/TargetInfoState.cpp` | OpenXcom | 192 | 6 | 0/0 | 10/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/TargetInfoState.h` | OpenXcom | 63 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/TrainingFinishedState.cpp` | OXCE | 112 | 3 | 2/2 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/TrainingFinishedState.h` | OXCE | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/TrainingState.cpp` | OXCE | 123 | 4 | 1/1 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/TrainingState.h` | OXCE | 52 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/UfoDetectedState.cpp` | OpenXcom | 358 | 8 | 80/0 | 11/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/UfoDetectedState.h` | OpenXcom | 68 | 0 | 8/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/UfoLostState.cpp` | OpenXcom | 86 | 3 | 0/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/UfoLostState.h` | OpenXcom | 50 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/UfoTrackerState.cpp` | OXCE | 258 | 7 | 0/0 | 11/0 | 0 | — | NOT_REVIEWED |
| `src/Geoscape/UfoTrackerState.h` | OXCE | 65 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Движок: данные, файлы, опции (этап F)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Engine/CatFile.cpp` | OpenXcom | 123 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/CatFile.h` | OpenXcom | 52 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Collections.h` | OXCE | 603 | 50 | 0/0 | 0/1 | 0 | — | NOT_REVIEWED |
| `src/Engine/CrossPlatform.cpp` | OpenXcom | 2247 | 79 | 168/16 | 5/0 | 13 | — | PARTIAL |
| `src/Engine/CrossPlatform.h` | OpenXcom | 295 | 16 | 4/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Exception.h` | OpenXcom | 36 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/FileMap.cpp` | OpenXcom | 1344 | 93 | 0/0 | 1/3 | 4 | — | NOT_REVIEWED |
| `src/Engine/FileMap.h` | OpenXcom | 134 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Language.cpp` | OpenXcom | 449 | 13 | 0/0 | 0/1 | 0 | — | NOT_REVIEWED |
| `src/Engine/Language.h` | OpenXcom | 83 | 2 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/LocalizedText.cpp` | OpenXcom | 68 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/LocalizedText.h` | OpenXcom | 154 | 8 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Logger.h` | OpenXcom | 71 | 5 | 0/0 | 0/0 | 0 | есть | NOT_REVIEWED |
| `src/Engine/ModInfo.cpp` | OpenXcom | 389 | 27 | 7/2 | 0/0 | 1 | — | NOT_REVIEWED |
| `src/Engine/ModInfo.h` | OpenXcom | 121 | 1 | 6/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/OptionInfo.cpp` | сторонний (через OpenXcom/OXCE) | 276 | 12 | 16/3 | 0/0 | 0 | — | PARTIAL |
| `src/Engine/OptionInfo.h` | сторонний (через OpenXcom/OXCE) | 81 | 5 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Options.cpp` | OpenXcom | 1710 | 45 | 221/5 | 0/0 | 13 | — | NOT_REVIEWED |
| `src/Engine/Options.h` | OpenXcom | 168 | 0 | 26/0 | 0/0 | 0 | есть | NOT_REVIEWED |
| `src/Engine/RNG.cpp` | OpenXcom | 184 | 13 | 0/0 | 0/0 | 2 | — | NOT_REVIEWED |
| `src/Engine/RNG.h` | OpenXcom | 92 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Unicode.cpp` | OpenXcom | 896 | 35 | 0/0 | 0/0 | 3 | — | NOT_REVIEWED |
| `src/Engine/Unicode.h` | OpenXcom | 96 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Yaml.cpp` | OXCE | 1018 | 77 | 0/0 | 7/0 | 4 | — | NOT_REVIEWED |
| `src/Engine/Yaml.h` | OXCE | 766 | 37 | 0/0 | 0/4 | 0 | — | NOT_REVIEWED |
| `src/Engine/Zoom.cpp` | OpenXcom | 998 | 4 | 59/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Zoom.h` | OpenXcom | 42 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Движок: масштабирование и звук (этап G)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Engine/Adlib/adlplayer.cpp` | сторонний (через OpenXcom/OXCE) | 880 | 27 | 0/0 | 0/0 | 22 | — | NOT_REVIEWED |
| `src/Engine/Adlib/adlplayer.h` | сторонний (через OpenXcom/OXCE) | 21 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Adlib/fmopl.cpp` | сторонний (через OpenXcom/OXCE) | 1407 | 36 | 0/0 | 0/0 | 23 | — | NOT_REVIEWED |
| `src/Engine/Adlib/fmopl.h` | сторонний (через OpenXcom/OXCE) | 171 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/common.h` | сторонний (через OpenXcom/OXCE) | 143 | 15 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/config.h` | сторонний (через OpenXcom/OXCE) | 40 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/hq2x.cpp` | сторонний (через OpenXcom/OXCE) | 2811 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/hq3x.cpp` | сторонний (через OpenXcom/OXCE) | 3789 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/hq4x.cpp` | сторонний (через OpenXcom/OXCE) | 5235 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/hqx.h` | сторонний (через OpenXcom/OXCE) | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/init.cpp` | сторонний (через OpenXcom/OXCE) | 38 | 1 | 0/0 | 0/0 | 2 | — | NOT_REVIEWED |
| `src/Engine/Scalers/scale2x.cpp` | сторонний (через OpenXcom/OXCE) | 1288 | 27 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/scale2x.h` | сторонний (через OpenXcom/OXCE) | 64 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/scale3x.cpp` | сторонний (через OpenXcom/OXCE) | 434 | 9 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/scale3x.h` | сторонний (через OpenXcom/OXCE) | 29 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/scalebit.cpp` | сторонний (через OpenXcom/OXCE) | 501 | 13 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/scalebit.h` | сторонний (через OpenXcom/OXCE) | 33 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/xbrz.cpp` | сторонний (через OpenXcom/OXCE) | 1195 | 72 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Scalers/xbrz.h` | сторонний (через OpenXcom/OXCE) | 94 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Движок: прочее (этап G)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Engine/AdlibMusic.cpp` | сторонний (через OpenXcom/OXCE) | 176 | 7 | 1/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/AdlibMusic.h` | сторонний (через OpenXcom/OXCE) | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/DosFont.h` | OpenXcom | 133 | 0 | 0/0 | 0/0 | 1 | — | NOT_REVIEWED |
| `src/Engine/FastLineClip.cpp` | OpenXcom | 413 | 9 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/FastLineClip.h` | OpenXcom | 53 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Feedback.cpp` | HD | 470 | 26 | 470/0 | 2/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Feedback.h` | HD | 80 | 0 | 80/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/FlcPlayer.cpp` | сторонний (через OpenXcom/OXCE) | 973 | 38 | 0/0 | 3/3 | 0 | — | NOT_REVIEWED |
| `src/Engine/FlcPlayer.h` | сторонний (через OpenXcom/OXCE) | 146 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Functions.h` | OXCE | 114 | 5 | 0/0 | 0/1 | 0 | — | NOT_REVIEWED |
| `src/Engine/GMCat.cpp` | сторонний (через OpenXcom/OXCE) | 394 | 9 | 0/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/GMCat.h` | сторонний (через OpenXcom/OXCE) | 40 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/GraphSubset.h` | OpenXcom | 195 | 17 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/HelperMeta.h` | OXCE | 144 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/LanguagePlurality.cpp` | OpenXcom | 262 | 17 | 0/0 | 8/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/LanguagePlurality.h` | OpenXcom | 54 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/ModCheck.cpp` | HD | 144 | 9 | 144/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/ModCheck.h` | HD | 36 | 0 | 36/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Music.cpp` | OpenXcom | 389 | 20 | 230/1 | 0/0 | 5 | — | NOT_REVIEWED |
| `src/Engine/Music.h` | OpenXcom | 82 | 1 | 26/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/NullableValue.h` | OXCE | 151 | 16 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/OpenGL.cpp` | OpenXcom | 507 | 15 | 6/4 | 2/2 | 23 | — | NOT_REVIEWED |
| `src/Engine/OpenGL.h` | OpenXcom | 91 | 0 | 2/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Options.inc.h` | OpenXcom | 522 | 0 | 342/8 | 0/0 | 309 | — | NOT_REVIEWED |
| `src/Engine/SDL2Helpers.h` | OXCE | 22 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/ShaderDraw.h` | OpenXcom | 286 | 12 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/ShaderDrawHelper.h` | OpenXcom | 418 | 45 | 0/0 | 0/10 | 0 | — | NOT_REVIEWED |
| `src/Engine/ShaderMove.h` | OpenXcom | 160 | 12 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/ShaderRepeat.h` | OpenXcom | 173 | 14 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Sound.cpp` | OpenXcom | 243 | 14 | 113/2 | 0/0 | 3 | — | NOT_REVIEWED |
| `src/Engine/Sound.h` | OpenXcom | 84 | 0 | 13/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/SoundSet.cpp` | OpenXcom | 249 | 10 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/SoundSet.h` | OpenXcom | 66 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/TouchState.cpp` | OXCE | 194 | 10 | 0/0 | 10/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/TouchState.h` | OXCE | 68 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/stb_truetype.h` | сторонний (добавлен нами) | 4899 | 131 | 4899/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Движок: ядро и жизнь объектов (этап B)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Engine/Action.cpp` | OpenXcom | 208 | 17 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Action.h` | OpenXcom | 76 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Font.cpp` | OpenXcom | 249 | 10 | 0/0 | 2/1 | 0 | — | NOT_REVIEWED |
| `src/Engine/Font.h` | OpenXcom | 80 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Game.cpp` | OpenXcom | 1359 | 29 | 563/15 | 13/16 | 0 | — | PARTIAL |
| `src/Engine/Game.h` | OpenXcom | 188 | 29 | 16/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/InteractiveSurface.cpp` | OpenXcom | 577 | 31 | 6/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/InteractiveSurface.h` | OpenXcom | 116 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Palette.cpp` | OpenXcom | 271 | 13 | 0/0 | 3/1 | 0 | — | NOT_REVIEWED |
| `src/Engine/Palette.h` | OpenXcom | 80 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Screen.cpp` | OpenXcom | 1231 | 33 | 510/17 | 0/0 | 4 | — | NOT_REVIEWED |
| `src/Engine/Screen.h` | OpenXcom | 151 | 9 | 47/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/State.cpp` | OpenXcom | 756 | 40 | 62/0 | 0/2 | 0 | — | PARTIAL |
| `src/Engine/State.h` | OpenXcom | 165 | 2 | 11/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Surface.cpp` | OpenXcom | 1133 | 59 | 60/8 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Surface.h` | OpenXcom | 549 | 49 | 15/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/SurfaceSet.cpp` | OpenXcom | 372 | 16 | 68/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/SurfaceSet.h` | OpenXcom | 87 | 0 | 4/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Timer.cpp` | OpenXcom | 174 | 11 | 8/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/Timer.h` | OpenXcom | 79 | 1 | 7/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Запуск (этап B)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/fallthrough.h` | OXCE | 15 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/main.cpp` | OpenXcom | 316 | 26 | 5/1 | 2/1 | 3 | — | NOT_REVIEWED |
| `src/resource.h` | OpenXcom | 19 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/version.h` | OpenXcom | 34 | 0 | 5/1 | 0/0 | 0 | — | NOT_REVIEWED |

### ИИ (этап D)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Battlescape/AIModule.cpp` | OpenXcom | 7250 | 132 | 4229/131 | 0/0 | 0 | — | PARTIAL |
| `src/Battlescape/AIModule.h` | OpenXcom | 444 | 6 | 284/2 | 0/2 | 0 | — | NOT_REVIEWED |

### ИИ: стенд и опытный код (этап D)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Battlescape/AiCandidates.cpp` | HD | 409 | 11 | 409/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/AiCandidates.h` | HD | 89 | 1 | 89/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/AiCoverMap.cpp` | HD | 544 | 30 | 544/0 | 0/0 | 1 | — | PARTIAL |
| `src/Battlescape/AiCoverMap.h` | HD | 75 | 0 | 75/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/AiProbe.cpp` | HD | 6385 | 430 | 6385/0 | 2/0 | 90 | — | PARTIAL |
| `src/Battlescape/AiProbe.h` | HD | 636 | 0 | 636/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CollapseCore.cpp` | HD | 749 | 24 | 749/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CollapseCore.h` | HD | 83 | 0 | 83/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CollapsePilot.cpp` | HD | 2145 | 73 | 2145/0 | 0/0 | 2 | — | PARTIAL |
| `src/Battlescape/CollapsePilot.h` | HD | 79 | 0 | 79/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CollapsePilotData.cpp` | HD | 203 | 11 | 203/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/CollapsePilotData.h` | HD | 34 | 0 | 34/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Инвентарь (этап E)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Battlescape/ActionMenuItem.cpp` | OpenXcom | 232 | 12 | 42/0 | 4/4 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ActionMenuItem.h` | OpenXcom | 74 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ExtendedInventoryLinksState.cpp` | OXCE | 280 | 14 | 98/20 | 29/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ExtendedInventoryLinksState.h` | OXCE | 66 | 0 | 6/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/Inventory.cpp` | OpenXcom | 2260 | 49 | 436/10 | 13/12 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/Inventory.h` | OpenXcom | 189 | 2 | 52/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InventoryLoadState.cpp` | OXCE | 132 | 4 | 2/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InventoryLoadState.h` | OXCE | 54 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InventoryPersonalState.cpp` | OXCE | 146 | 3 | 2/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InventoryPersonalState.h` | OXCE | 50 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InventorySaveState.cpp` | OXCE | 242 | 8 | 2/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InventorySaveState.h` | OXCE | 67 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/InventoryState.cpp` | OpenXcom | 2993 | 69 | 625/12 | 39/1 | 0 | — | PARTIAL |
| `src/Battlescape/InventoryState.h` | OpenXcom | 180 | 0 | 13/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ItemSprite.cpp` | OXCE | 94 | 5 | 19/4 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/ItemSprite.h` | OXCE | 58 | 0 | 5/2 | 0/0 | 0 | — | NOT_REVIEWED |

### Меню (этап G)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Menu/AbandonGameState.cpp` | OpenXcom | 140 | 4 | 7/1 | 7/0 | 0 | — | PARTIAL |
| `src/Menu/AbandonGameState.h` | OpenXcom | 52 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/AdultChoiceState.cpp` | HD | 167 | 7 | 167/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/AdultChoiceState.h` | HD | 68 | 0 | 68/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/CutsceneState.cpp` | OpenXcom | 128 | 5 | 12/1 | 4/0 | 0 | — | PARTIAL |
| `src/Menu/CutsceneState.h` | OpenXcom | 48 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/DeleteGameState.cpp` | OpenXcom | 110 | 4 | 0/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/DeleteGameState.h` | OpenXcom | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ErrorMessageState.cpp` | OpenXcom | 120 | 4 | 1/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ErrorMessageState.h` | OpenXcom | 50 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/GentleChoiceState.cpp` | HD | 135 | 6 | 135/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/GentleChoiceState.h` | HD | 61 | 0 | 61/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/HdLabPasswordState.cpp` | HD | 160 | 6 | 160/0 | 8/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/HdLabPasswordState.h` | HD | 60 | 0 | 60/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/LanguageChoiceState.cpp` | HD | 168 | 6 | 168/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/LanguageChoiceState.h` | HD | 67 | 0 | 67/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ListGamesState.cpp` | OpenXcom | 365 | 17 | 1/0 | 12/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ListGamesState.h` | OpenXcom | 82 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/MainMenuState.cpp` | OpenXcom | 763 | 18 | 224/7 | 29/0 | 0 | — | PARTIAL |
| `src/Menu/MainMenuState.h` | OpenXcom | 84 | 0 | 8/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ModConfirmExtendedState.cpp` | OpenXcom | 168 | 8 | 1/0 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ModConfirmExtendedState.h` | OpenXcom | 64 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ModListState.cpp` | OpenXcom | 548 | 23 | 1/1 | 9/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ModListState.h` | OpenXcom | 89 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/NewBattleState.cpp` | OpenXcom | 1491 | 33 | 359/3 | 49/3 | 0 | — | PARTIAL |
| `src/Menu/NewBattleState.h` | OpenXcom | 124 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/NewGameState.cpp` | OpenXcom | 216 | 4 | 0/0 | 15/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/NewGameState.h` | OpenXcom | 55 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/NotesState.cpp` | OXCE | 293 | 8 | 1/0 | 8/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/NotesState.h` | OXCE | 72 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionDetailState.cpp` | HD | 145 | 5 | 145/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionDetailState.h` | HD | 67 | 0 | 67/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsAdvancedState.cpp` | OpenXcom | 580 | 12 | 111/6 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsAdvancedState.h` | OpenXcom | 82 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsAudioState.cpp` | OpenXcom | 346 | 13 | 53/0 | 19/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsAudioState.h` | OpenXcom | 73 | 0 | 7/3 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsBaseState.cpp` | OpenXcom | 359 | 12 | 20/6 | 29/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsBaseState.h` | OpenXcom | 78 | 0 | 1/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsBattlescapeState.cpp` | OpenXcom | 327 | 11 | 21/0 | 22/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsBattlescapeState.h` | OpenXcom | 74 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsButtonFaceState.cpp` | HD | 269 | 12 | 269/0 | 11/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsButtonFaceState.h` | HD | 73 | 0 | 73/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsButtonInkState.cpp` | HD | 253 | 10 | 253/0 | 13/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsButtonInkState.h` | HD | 66 | 0 | 66/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsConfirmState.cpp` | OpenXcom | 150 | 6 | 1/0 | 6/1 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsConfirmState.h` | OpenXcom | 59 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsControlsState.cpp` | OpenXcom | 339 | 10 | 1/1 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsControlsState.h` | OpenXcom | 77 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsCustomColorState.cpp` | HD | 310 | 11 | 310/0 | 12/0 | 3 | — | NOT_REVIEWED |
| `src/Menu/OptionsCustomColorState.h` | HD | 81 | 0 | 81/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsDefaultsState.cpp` | OpenXcom | 140 | 4 | 7/0 | 4/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsDefaultsState.h` | OpenXcom | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsFoldersState.cpp` | OpenXcom | 145 | 3 | 1/0 | 9/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsFoldersState.h` | OpenXcom | 44 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsGeoscapeState.cpp` | OpenXcom | 240 | 10 | 1/0 | 14/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsGeoscapeState.h` | OpenXcom | 69 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsHdState.cpp` | HD | 1497 | 35 | 1497/0 | 9/0 | 2 | — | NOT_REVIEWED |
| `src/Menu/OptionsHdState.h` | HD | 132 | 0 | 132/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsNoAudioState.cpp` | OpenXcom | 59 | 2 | 1/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsNoAudioState.h` | OpenXcom | 41 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsScreenThemesState.cpp` | HD | 489 | 25 | 489/0 | 22/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsScreenThemesState.h` | HD | 103 | 0 | 103/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsVideoState.cpp` | OpenXcom | 667 | 19 | 1/0 | 22/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/OptionsVideoState.h` | OpenXcom | 99 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/PauseState.cpp` | OpenXcom | 255 | 8 | 39/3 | 16/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/PauseState.h` | OpenXcom | 61 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ReportsState.cpp` | HD | 355 | 18 | 355/0 | 8/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ReportsState.h` | HD | 83 | 0 | 83/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/SetWindowedRootState.cpp` | OpenXcom | 147 | 4 | 1/0 | 8/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/SetWindowedRootState.h` | OpenXcom | 56 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/SlideshowState.cpp` | OpenXcom | 158 | 5 | 12/13 | 3/1 | 0 | — | NOT_REVIEWED |
| `src/Menu/SlideshowState.h` | OpenXcom | 58 | 0 | 2/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/StartState.cpp` | OpenXcom | 370 | 8 | 48/5 | 10/3 | 0 | — | NOT_REVIEWED |
| `src/Menu/StartState.h` | OpenXcom | 73 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/StatisticsState.cpp` | OpenXcom | 355 | 5 | 0/0 | 5/0 | 0 | — | PARTIAL |
| `src/Menu/StatisticsState.h` | OpenXcom | 56 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/TestPaletteState.cpp` | OXCE | 160 | 3 | 0/0 | 2/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/TestPaletteState.h` | OXCE | 47 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/TestState.cpp` | OpenXcom | 959 | 19 | 0/0 | 14/3 | 1 | — | NOT_REVIEWED |
| `src/Menu/TestState.h` | OpenXcom | 95 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/VideoState.cpp` | OpenXcom | 549 | 6 | 0/0 | 2/2 | 6 | — | NOT_REVIEWED |
| `src/Menu/VideoState.h` | OpenXcom | 42 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Меню: сохранение и загрузка (этап B)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Menu/ConfirmLoadState.cpp` | OpenXcom | 103 | 4 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ConfirmLoadState.h` | OpenXcom | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ListLoadOriginalState.cpp` | OpenXcom | 217 | 6 | 1/0 | 14/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ListLoadOriginalState.h` | OpenXcom | 62 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ListLoadState.cpp` | OpenXcom | 148 | 6 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ListLoadState.h` | OpenXcom | 46 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ListSaveState.cpp` | OpenXcom | 198 | 7 | 0/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/ListSaveState.h` | OpenXcom | 57 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/LoadGameState.cpp` | OpenXcom | 269 | 7 | 24/0 | 8/1 | 0 | — | REVIEWED |
| `src/Menu/LoadGameState.h` | OpenXcom | 59 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/SaveGameState.cpp` | OpenXcom | 259 | 6 | 22/2 | 4/0 | 0 | — | REVIEWED |
| `src/Menu/SaveGameState.h` | OpenXcom | 57 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Поиск пути (этап D)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Battlescape/Pathfinding.cpp` | OpenXcom | 2131 | 53 | 605/37 | 0/4 | 0 | — | REVIEWED |
| `src/Battlescape/Pathfinding.h` | OpenXcom | 369 | 13 | 86/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/PathfindingNode.cpp` | OpenXcom | 120 | 9 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/PathfindingNode.h` | OpenXcom | 151 | 11 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/PathfindingOpenSet.cpp` | OpenXcom | 81 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Battlescape/PathfindingOpenSet.h` | OpenXcom | 75 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Правила и загрузка модов (этап F)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Mod/AlienRace.cpp` | OpenXcom | 160 | 10 | 0/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Mod/AlienRace.h` | OpenXcom | 72 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/Armor.cpp` | OpenXcom | 1417 | 93 | 3/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/Armor.h` | OpenXcom | 520 | 72 | 8/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/ArticleDefinition.cpp` | OpenXcom | 393 | 34 | 9/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/ArticleDefinition.h` | OpenXcom | 384 | 6 | 5/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/City.cpp` | OpenXcom | 64 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/City.h` | OpenXcom | 50 | 2 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/CustomPalettes.cpp` | OXCE | 86 | 7 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/CustomPalettes.h` | OXCE | 52 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/ExtraSounds.cpp` | OpenXcom | 160 | 7 | 9/1 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/ExtraSounds.h` | OpenXcom | 58 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/ExtraSprites.cpp` | OpenXcom | 319 | 15 | 0/0 | 2/1 | 0 | — | NOT_REVIEWED |
| `src/Mod/ExtraSprites.h` | OpenXcom | 79 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/ExtraStrings.cpp` | OpenXcom | 74 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/ExtraStrings.h` | OpenXcom | 45 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/LoadYaml.h` | OXCE | 84 | 7 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/MCDPatch.cpp` | OpenXcom | 220 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/MCDPatch.h` | OpenXcom | 46 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/Mod.cpp` | OpenXcom | 8516 | 307 | 1839/80 | 95/80 | 5 | — | NOT_REVIEWED |
| `src/Mod/Mod.h` | OpenXcom | 1306 | 149 | 141/1 | 2/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/ModScript.h` | OXCE | 620 | 9 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/Polygon.cpp` | OpenXcom | 213 | 15 | 0/0 | 12/8 | 0 | — | NOT_REVIEWED |
| `src/Mod/Polygon.h` | OpenXcom | 70 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/Polyline.cpp` | OpenXcom | 115 | 8 | 0/0 | 4/4 | 0 | — | NOT_REVIEWED |
| `src/Mod/Polyline.h` | OpenXcom | 54 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleAlienMission.cpp` | OpenXcom | 265 | 12 | 0/0 | 2/3 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleAlienMission.h` | OpenXcom | 242 | 20 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleArcScript.cpp` | OXCE | 114 | 4 | 3/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleArcScript.h` | OXCE | 115 | 24 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleBaseFacility.cpp` | OpenXcom | 709 | 46 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleBaseFacility.h` | OpenXcom | 242 | 26 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleBaseFacilityFunctions.h` | OXCE | 41 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleCommendations.cpp` | OpenXcom | 153 | 12 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleCommendations.h` | OpenXcom | 88 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleConverter.cpp` | OpenXcom | 64 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleConverter.h` | OpenXcom | 81 | 17 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleCountry.cpp` | OpenXcom | 229 | 14 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleCountry.h` | OpenXcom | 101 | 10 | 1/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleCraft.cpp` | OpenXcom | 844 | 59 | 0/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleCraft.h` | OpenXcom | 425 | 38 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleCraftWeapon.cpp` | OpenXcom | 347 | 25 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleCraftWeapon.h` | OpenXcom | 119 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleDamageType.cpp` | OXCE | 338 | 22 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleDamageType.h` | OXCE | 174 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleEvent.cpp` | OXCE | 88 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleEvent.h` | OXCE | 133 | 28 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleEventScript.cpp` | OXCE | 140 | 5 | 2/1 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleEventScript.h` | OXCE | 119 | 24 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleGlobe.cpp` | OpenXcom | 243 | 8 | 0/0 | 4/6 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleGlobe.h` | OpenXcom | 65 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleInterface.cpp` | OpenXcom | 147 | 11 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleInterface.h` | OpenXcom | 88 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleInventory.cpp` | OpenXcom | 342 | 19 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleInventory.h` | OpenXcom | 100 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleItem.cpp` | OpenXcom | 2998 | 211 | 13/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleItem.h` | OpenXcom | 1045 | 104 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleItemCategory.cpp` | OXCE | 96 | 7 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleItemCategory.h` | OXCE | 60 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleManufacture.cpp` | OpenXcom | 391 | 22 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleManufacture.h` | OpenXcom | 136 | 6 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleManufactureShortcut.cpp` | OXCE | 50 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleManufactureShortcut.h` | OXCE | 55 | 5 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleMissionScript.cpp` | OpenXcom | 417 | 30 | 2/1 | 3/3 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleMissionScript.h` | OpenXcom | 151 | 13 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleMusic.cpp` | OpenXcom | 81 | 6 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleMusic.h` | OpenXcom | 41 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleRegion.cpp` | OpenXcom | 271 | 12 | 0/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleRegion.h` | OpenXcom | 135 | 12 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleResearch.cpp` | OpenXcom | 338 | 21 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleResearch.h` | OpenXcom | 148 | 15 | 1/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleSkill.cpp` | OXCE | 137 | 6 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleSkill.h` | OXCE | 93 | 12 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleSoldier.cpp` | OpenXcom | 767 | 48 | 0/0 | 2/3 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleSoldier.h` | OpenXcom | 261 | 26 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleSoldierBonus.cpp` | OXCE | 170 | 11 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleSoldierBonus.h` | OXCE | 121 | 21 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleSoldierTransformation.cpp` | OXCE | 398 | 33 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleSoldierTransformation.h` | OXCE | 176 | 17 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleStatBonus.cpp` | OXCE | 620 | 43 | 18/0 | 0/0 | 2 | — | NOT_REVIEWED |
| `src/Mod/RuleStatBonus.h` | OXCE | 84 | 3 | 1/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleUfo.cpp` | OpenXcom | 508 | 32 | 0/0 | 1/2 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleUfo.h` | OpenXcom | 189 | 16 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleVideo.cpp` | OpenXcom | 110 | 9 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleVideo.h` | OpenXcom | 70 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleVoiceSet.cpp` | OXCE | 75 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleVoiceSet.h` | OXCE | 86 | 10 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleWeaponSet.cpp` | OXCE | 63 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleWeaponSet.h` | OXCE | 55 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/SoldierNamePool.cpp` | OpenXcom | 207 | 6 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/SoldierNamePool.h` | OpenXcom | 62 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/SoundDefinition.cpp` | OpenXcom | 59 | 5 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/SoundDefinition.h` | OpenXcom | 42 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/StatString.cpp` | OpenXcom | 172 | 8 | 0/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/StatString.h` | OpenXcom | 129 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/StatStringCondition.cpp` | OpenXcom | 88 | 6 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/StatStringCondition.h` | OpenXcom | 46 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/Texture.cpp` | OpenXcom | 214 | 10 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/Texture.h` | OpenXcom | 86 | 5 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/UfoTrajectory.cpp` | OpenXcom | 67 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/UfoTrajectory.h` | OpenXcom | 97 | 5 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/Unit.cpp` | OpenXcom | 611 | 40 | 0/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Mod/Unit.h` | OpenXcom | 626 | 66 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Правила: карты и миссии (этап E)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Mod/AlienDeployment.cpp` | OpenXcom | 900 | 68 | 0/0 | 2/2 | 0 | — | NOT_REVIEWED |
| `src/Mod/AlienDeployment.h` | OpenXcom | 334 | 32 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/MapBlock.cpp` | OpenXcom | 176 | 12 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/MapBlock.h` | OpenXcom | 105 | 7 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/MapData.cpp` | OpenXcom | 586 | 54 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/MapData.h` | OpenXcom | 176 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/MapDataSet.cpp` | OpenXcom | 323 | 12 | 17/1 | 2/2 | 0 | — | PARTIAL |
| `src/Mod/MapDataSet.h` | OpenXcom | 71 | 0 | 1/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/MapScript.cpp` | OpenXcom | 481 | 13 | 0/0 | 2/2 | 0 | — | NOT_REVIEWED |
| `src/Mod/MapScript.h` | OpenXcom | 252 | 23 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleEnviroEffects.cpp` | OXCE | 136 | 7 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleEnviroEffects.h` | OXCE | 87 | 7 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleStartingCondition.cpp` | OXCE | 304 | 10 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleStartingCondition.h` | OXCE | 98 | 11 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleTerrain.cpp` | OpenXcom | 397 | 19 | 0/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Mod/RuleTerrain.h` | OpenXcom | 96 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Прочее (этап G)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/apple/SDLMain.h` | OpenXcom | 15 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/apple/SDLMain.m` | OpenXcom | 376 | 12 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Скрипты (Y-script, Lua) (этап F)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Engine/LuaSandbox.cpp` | HD | 713 | 38 | 713/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Engine/LuaSandbox.h` | HD | 156 | 9 | 156/0 | 0/2 | 0 | есть | NOT_REVIEWED |
| `src/Engine/Script.cpp` | OXCE | 5421 | 250 | 25/4 | 0/0 | 10 | — | NOT_REVIEWED |
| `src/Engine/Script.h` | OXCE | 1983 | 169 | 9/0 | 0/2 | 0 | — | NOT_REVIEWED |
| `src/Engine/ScriptBind.h` | OXCE | 1829 | 155 | 0/0 | 0/7 | 0 | — | NOT_REVIEWED |
| `src/Menu/LuaScreenState.cpp` | HD | 662 | 53 | 662/0 | 13/0 | 0 | — | NOT_REVIEWED |
| `src/Menu/LuaScreenState.h` | HD | 158 | 8 | 158/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Mod/LuaHost.cpp` | HD | 4536 | 323 | 4536/0 | 1/0 | 6 | — | NOT_REVIEWED |
| `src/Mod/LuaHost.h` | HD | 282 | 27 | 282/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Состояние боя (этап B)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Savegame/BattleItem.cpp` | OpenXcom | 1801 | 112 | 6/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/BattleItem.h` | OpenXcom | 250 | 4 | 12/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/BattleUnit.cpp` | OpenXcom | 7683 | 393 | 338/12 | 3/6 | 0 | — | PARTIAL |
| `src/Savegame/BattleUnit.h` | OpenXcom | 997 | 68 | 87/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/BattleUnitStatistics.h` | OpenXcom | 428 | 23 | 0/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/HitLog.cpp` | OXCE | 145 | 5 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/HitLog.h` | OXCE | 70 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Node.cpp` | OpenXcom | 206 | 19 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Node.h` | OpenXcom | 91 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/SavedBattleGame.cpp` | OpenXcom | 3997 | 191 | 246/12 | 15/15 | 0 | — | PARTIAL |
| `src/Savegame/SavedBattleGame.h` | OpenXcom | 697 | 66 | 24/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Tile.cpp` | OpenXcom | 1389 | 83 | 46/0 | 0/0 | 0 | — | PARTIAL |
| `src/Savegame/Tile.h` | OpenXcom | 436 | 25 | 11/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Состояние игры и сейвы (этап B)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Savegame/AlienBase.cpp` | OpenXcom | 220 | 20 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/AlienBase.h` | OpenXcom | 89 | 2 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/AlienMission.cpp` | OpenXcom | 1518 | 29 | 0/0 | 10/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/AlienMission.h` | OpenXcom | 142 | 9 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/AlienStrategy.cpp` | OpenXcom | 254 | 13 | 0/0 | 2/3 | 0 | — | NOT_REVIEWED |
| `src/Savegame/AlienStrategy.h` | OpenXcom | 74 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Base.cpp` | OpenXcom | 2591 | 110 | 10/0 | 12/9 | 0 | — | PARTIAL |
| `src/Savegame/Base.h` | OpenXcom | 356 | 18 | 4/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/BaseFacility.cpp` | OpenXcom | 315 | 23 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/BaseFacility.h` | OpenXcom | 104 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Country.cpp` | OpenXcom | 421 | 23 | 6/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Country.h` | OpenXcom | 102 | 4 | 4/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Craft.cpp` | OpenXcom | 2431 | 125 | 9/1 | 7/8 | 0 | — | PARTIAL |
| `src/Savegame/Craft.h` | OpenXcom | 389 | 15 | 6/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/CraftWeapon.cpp` | OpenXcom | 227 | 14 | 0/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/CraftWeapon.h` | OpenXcom | 73 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/CraftWeaponProjectile.cpp` | OpenXcom | 276 | 26 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/CraftWeaponProjectile.h` | OpenXcom | 109 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/EquipmentLayoutItem.cpp` | OpenXcom | 211 | 14 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/EquipmentLayoutItem.h` | OpenXcom | 72 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/GameTime.cpp` | OpenXcom | 287 | 18 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/GameTime.h` | OpenXcom | 81 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/GeoscapeEvent.cpp` | OXCE | 93 | 6 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/GeoscapeEvent.h` | OXCE | 58 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/ItemContainer.cpp` | OpenXcom | 252 | 17 | 20/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/ItemContainer.h` | OpenXcom | 76 | 2 | 4/0 | 0/1 | 0 | — | NOT_REVIEWED |
| `src/Savegame/MissionSite.cpp` | OpenXcom | 253 | 22 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/MissionSite.h` | OpenXcom | 99 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/MissionStatistics.h` | OpenXcom | 186 | 13 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/MovingTarget.cpp` | OpenXcom | 338 | 18 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/MovingTarget.h` | OpenXcom | 79 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Production.cpp` | OpenXcom | 961 | 39 | 529/1 | 8/1 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Production.h` | OpenXcom | 140 | 6 | 69/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/RankCount.cpp` | OXCE | 136 | 5 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/RankCount.h` | OXCE | 64 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Region.cpp` | OpenXcom | 122 | 10 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Region.h` | OpenXcom | 61 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/ResearchDiary.h` | OXCE | 131 | 5 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/ResearchProject.cpp` | OpenXcom | 169 | 13 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/ResearchProject.h` | OpenXcom | 66 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/SaveConverter.cpp` | OpenXcom | 1303 | 33 | 0/0 | 24/1 | 0 | — | NOT_REVIEWED |
| `src/Savegame/SaveConverter.h` | OpenXcom | 127 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/SavedGame.cpp` | OpenXcom | 3800 | 179 | 112/4 | 25/21 | 0 | — | PARTIAL |
| `src/Savegame/SavedGame.h` | OpenXcom | 545 | 33 | 11/2 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/SerializationHelper.cpp` | OpenXcom | 110 | 3 | 0/0 | 0/0 | 0 | — | PARTIAL |
| `src/Savegame/SerializationHelper.h` | OpenXcom | 30 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Soldier.cpp` | OpenXcom | 2403 | 118 | 20/0 | 7/8 | 0 | — | PARTIAL |
| `src/Savegame/Soldier.h` | OpenXcom | 327 | 7 | 5/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/SoldierAvatar.cpp` | OXCE | 68 | 7 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/SoldierAvatar.h` | OXCE | 53 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/SoldierDeath.cpp` | OpenXcom | 81 | 6 | 0/0 | 1/1 | 0 | — | NOT_REVIEWED |
| `src/Savegame/SoldierDeath.h` | OpenXcom | 52 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/SoldierDiary.cpp` | OpenXcom | 1591 | 67 | 141/4 | 5/3 | 1 | — | NOT_REVIEWED |
| `src/Savegame/SoldierDiary.h` | OpenXcom | 192 | 2 | 3/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Target.cpp` | OpenXcom | 274 | 20 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Target.h` | OpenXcom | 92 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Transfer.cpp` | OpenXcom | 387 | 21 | 50/0 | 2/5 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Transfer.h` | OpenXcom | 117 | 0 | 8/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Ufo.cpp` | OpenXcom | 1372 | 83 | 6/1 | 4/6 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Ufo.h` | OpenXcom | 264 | 12 | 5/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Vehicle.cpp` | OpenXcom | 108 | 8 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Vehicle.h` | OpenXcom | 56 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Waypoint.cpp` | OpenXcom | 58 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/Waypoint.h` | OpenXcom | 42 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/WeightedOptions.cpp` | OpenXcom | 122 | 5 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Savegame/WeightedOptions.h` | OpenXcom | 58 | 4 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Сторонний код в src (этап F)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/fmath.h` | сторонний (через OpenXcom/OXCE) | 154 | 16 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/lodepng.cpp` | сторонний (через OpenXcom/OXCE) | 6245 | 228 | 0/0 | 0/0 | 2 | — | NOT_REVIEWED |
| `src/lodepng.h` | сторонний (через OpenXcom/OXCE) | 1769 | 1 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/md5.cpp` | сторонний (через OpenXcom/OXCE) | 362 | 21 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/md5.h` | сторонний (через OpenXcom/OXCE) | 93 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Тесты (этап A)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `tests/hdgputold_test.cpp` | HD | 132 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `tests/hdworkers_test.cpp` | HD | 354 | 0 | 0/0 | 0/2 | 0 | — | NOT_REVIEWED |
| `tests/shim/alloca.h` | HD | 3 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `tests/stubs.cpp` | HD | 28 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `tests/vertical_trace_test.cpp` | HD | 175 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |

### Уфопедия (этап G)

| Файл | Происх. | Строк | Функц. | Наши +/− | new/delete | Глоб. изм. | Тест | Статус |
|---|---|---|---|---|---|---|---|---|
| `src/Ufopaedia/ArticleState.cpp` | OpenXcom | 299 | 15 | 5/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleState.h` | OpenXcom | 127 | 3 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateArmor.cpp` | OpenXcom | 280 | 4 | 7/1 | 4/1 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateArmor.h` | OpenXcom | 51 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateBaseFacility.cpp` | OpenXcom | 237 | 3 | 83/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateBaseFacility.h` | OpenXcom | 47 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateCraft.cpp` | OpenXcom | 171 | 2 | 0/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateCraft.h` | OpenXcom | 45 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateCraftWeapon.cpp` | OpenXcom | 143 | 2 | 0/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateCraftWeapon.h` | OpenXcom | 45 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateItem.cpp` | OpenXcom | 645 | 6 | 45/11 | 24/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateItem.h` | OpenXcom | 65 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateSoldier.cpp` | OXCE | 141 | 2 | 0/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateSoldier.h` | OXCE | 46 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTD.cpp` | OpenXcom | 192 | 2 | 0/0 | 2/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTD.h` | OpenXcom | 42 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDArmor.cpp` | OpenXcom | 181 | 4 | 0/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDArmor.h` | OpenXcom | 40 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDCraft.cpp` | OpenXcom | 128 | 2 | 0/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDCraft.h` | OpenXcom | 36 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDCraftWeapon.cpp` | OpenXcom | 98 | 2 | 0/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDCraftWeapon.h` | OpenXcom | 36 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDFacility.cpp` | OpenXcom | 85 | 2 | 0/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDFacility.h` | OpenXcom | 36 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDItem.cpp` | OpenXcom | 209 | 4 | 0/0 | 7/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDItem.h` | OpenXcom | 43 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDUso.cpp` | OpenXcom | 67 | 2 | 0/0 | 1/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDUso.h` | OpenXcom | 36 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDVehicle.cpp` | OpenXcom | 136 | 2 | 0/0 | 2/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTFTDVehicle.h` | OpenXcom | 36 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateText.cpp` | OpenXcom | 74 | 2 | 0/0 | 2/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateText.h` | OpenXcom | 43 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTextImage.cpp` | OpenXcom | 96 | 2 | 0/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateTextImage.h` | OpenXcom | 44 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateUfo.cpp` | OpenXcom | 159 | 2 | 49/15 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateUfo.h` | OpenXcom | 47 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateUnit.cpp` | OXCE | 214 | 2 | 0/0 | 5/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateUnit.h` | OXCE | 48 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateVehicle.cpp` | OpenXcom | 163 | 2 | 0/0 | 3/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/ArticleStateVehicle.h` | OpenXcom | 44 | 0 | 0/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/StatsForNerdsState.cpp` | OXCE | 4385 | 95 | 19/0 | 19/1 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/StatsForNerdsState.h` | OXCE | 209 | 2 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/Ufopaedia.cpp` | OpenXcom | 403 | 16 | 23/0 | 24/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/Ufopaedia.h` | OpenXcom | 96 | 0 | 2/0 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/UfopaediaSelectState.cpp` | OpenXcom | 392 | 15 | 85/5 | 6/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/UfopaediaSelectState.h` | OpenXcom | 74 | 0 | 2/1 | 0/0 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/UfopaediaStartState.cpp` | OpenXcom | 282 | 14 | 41/0 | 10/1 | 0 | — | NOT_REVIEWED |
| `src/Ufopaedia/UfopaediaStartState.h` | OpenXcom | 77 | 0 | 5/0 | 0/0 | 0 | — | NOT_REVIEWED |
