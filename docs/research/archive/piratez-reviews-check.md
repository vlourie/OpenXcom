# Разборы рулсетов Пираток 26.09: сверка выводов с кодом движка

Разборы — `piratez-*-review.md` и `yankes-scripts-review.md`. Здесь не пересказ, а проверка тех выводов,
которые держатся на поведении движка: их можно подтвердить по `src`, не запуская игру. Сверено 2026-09-26 на `hd-render`.

| Разбор | Вывод | Где проверено | Итог |
|---|---|---|---|
| factions 1-2 | ранг развёртывания больше числа членов расы — вылет | `AlienRace::getMember` (`Mod/AlienRace.cpp:101`) бросает `Exception` «does not have a member at position/rank» | верно |
| factions 3 | повторный ключ `damageAlter:` — берётся первое, пустое, вхождение | `YamlNodeReader::findChildNode` ищет с первого ребёнка; индекс строится `emplace` — тоже первое | верно |
| factions 4 | `despawnEvenIfTargeted` у развёртываний не читается | ключ читает только `RuleAlienMission.cpp:81`, проверка в `GeoscapeState.cpp:1817` по правилам миссии | верно |
| events 1 | `interruptResearch` на скрипте событий выбрасывается | ключ читают только `RuleEvent.cpp:70` и `RuleAlienMission.cpp:84`, в `RuleEventScript` его нет | верно |
| globals 4 | `minReactionAccuracy` мёртв и на верхнем уровне, и под `ai:` | в `src` такого ключа нет вовсе | верно |
| resources 1 | подводный лист снарядов обрезан | `Projectiles_DIO.png` 105x162, `UnderwaterProjectiles` объявлен `height: 135` (`Piratez_Resources.rul:9805`) | верно |
| resources 3 | `music: GMTACTIC1` — случайная из 11 | `Mod::getRandomMusic` отбирает по `find(name)`, то есть по подстроке | верно |
| yankes, «что касается нас» | HD-код повторяет схему щитов | `Savegame/BattleUnit.cpp:3048`, `:3065` (зеркала `Tag.UNIT_ENERGY_SHIELD_HP`, `Tag.ARMOR_ENERGY_SHIELD_CAPACITY`) | место есть; при смене схемы у автора сверить |

Файл в разборе yankes назван `BattleUnit.cpp` без папки: это `src/Savegame/BattleUnit.cpp`, не `Battlescape`.

## Что из разборов касается нашего кода

- Подписи слотов инвентаря с ценой ОВ (`":NN"`, `Inventory.cpp:289`) пересекаются уже классическим шрифтом
  (globals, «для Vitali»). С 26.09 эти подписи в HD рисуются TTF (коммит `00af841e5`), а он шире классики
  (R-021) — наложение там вероятнее. В игре не проверено: нужен кадр инвентаря с перетаскиваемым предметом.
- Правки самих рулсетов — это механика Пираток: по правилу проекта мы их не вносим, только сообщаем автору
  (письма `*-dm.en.txt` рядом) или мод-патчем по решению Vitali.
