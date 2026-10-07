# Разбор Piratez_Factions.rul (X-Piratez)

Файл: `Пиратки/Dioxine_XPiratez/user/mods/Piratez/Ruleset/Piratez_Factions.rul`, 116 601 строка.
Файл читал скрипт, а не человек. Рулсеты Пираток слиты тем же порядком, что и в движке (`tools/rul_map.py`, итог в `.index/mod/Piratez/rul/`). Каждая проверка повторяет то, что делает движок:
- выбор расы боя и развёртывания: `BattlescapeGenerator::deployAliens` (`src/Battlescape/BattlescapeGenerator.cpp:1675-1790`), `ConfirmLandingState.cpp:270-300`;
- выбор члена расы: `AlienRace::getMember` (`src/Mod/AlienRace.cpp:101-119`);
- волны, зоны и объекты миссий: `AlienMission` (`src/Savegame/AlienMission.cpp:196-220`, `1250`, `1436-1455`, `1503`);
- исчезновение точек миссий: `GeoscapeState::processMissionSite` (`src/Geoscape/GeoscapeState.cpp:1807-1830`) и `RuleAlienMission.cpp:81`;
- повторный ключ YAML: `src/Engine/Yaml.cpp:124-160`, `201-230`.

**Файл не правился**: установка Пираток только читается. Все исправления ниже — предложения автору.
Сообщение Dioxine — [piratez-factions-dm.en.txt](piratez-factions-dm.en.txt).

## Что в файле

| Секция | Записей |
|---|---:|
| items | 1 045 |
| units | 405 |
| alienRaces | 129 |
| ufoTrajectories | 50 |
| missionScripts | 447 |
| alienMissions | 345 |
| ufos | 214 |
| alienDeployments | 489 |
| alienItemLevels | 1 |

Файл перекрывает 301 поле мастер-мода (трупы, `costSell` и прочее). Ни одно поле, заданное здесь, не перекрыто файлами, которые грузятся позже.

## Как движок выбирает, кто выйдет на бой

Без этого находки 1 и 2 не понять.

- **Раса боя.**
  - Если у развёртывания задан `race:`, берётся она.
  - Иначе раса миссии: она выбирается по `raceWeights` миссии или скрипта.
  - Миссии, которые порождает база (`genMission`, `huntMissionWeights`), по умолчанию берут расу базы.
  - Ответный удар берёт расу сбитого НЛО. В розыгрыш попадают только миссии с `missionWeights > 0`.
- **Развёртывание.**
  - У боя с НЛО развёртывание называется так же, как НЛО (под водой — с `_UNDERWATER`), если `craftCustomDeploy` / `missionCustomDeploy` из `ufo` или из `raceBonus[раса]` не подменяют его.
  - У точки миссии это `siteType`, волна, у которой `ufo` — развёртывание, или развёртывания текстуры глобуса в зоне региона.
- **Член расы.** Строка `data:` без `customUnitType` берёт юнита `members[alienRank]` расы боя. Если у расы членов не больше `alienRank`, то `getMember` **бросает исключение**, и игра падает при входе в бой. То же с подкреплениями. Предупреждения при загрузке нет: связь «раса — развёртывание» появляется только в бою.

Проверка перебрала все пары «раса — развёртывание», какие может дать игра:
- расы из `raceWeights` миссий и скриптов;
- раса базы для миссий базы;
- расы ответного удара;
- подмены из `raceBonus`;
- развёртывания текстур по зонам регионов;
- оборона базы.

Для каждой пары сверено, что `alienRank` каждой строки меньше числа членов расы.

## Находки

### 1. Чёрный бомбардировщик у BAD_COPS: ранг 13 при 8 членах — вылет

- Миссия `STR_MISSION_HIGHWAYMEN_FLIGHT_1` (строка 38811), `raceWeights`:
  - с 0-го месяца `STR_BAD_COPS: 100`;
  - с 24-го месяца 60 на 40 с `STR_APOCALYPSE_CULT`.
- Волна: `ufo: STR_VESSEL_BLACK_BOMBER`.
- Развёртывание `STR_VESSEL_BLACK_BOMBER` (строка 88431) — одна строка данных `alienRank: 13`, без `customUnitType`.
- У `STR_BAD_COPS` (строка 25728) **8 членов**.
- У НЛО `STR_VESSEL_BLACK_BOMBER` (строка 51056) `raceBonus` задан только для `STR_APOCALYPSE_CULT`, подмены развёртывания нет.
- Итог: любой бой с этим бомбардировщиком у BAD_COPS (место крушения или посадка) — `getMember(13)` на расе из 8, исключение, вылет.
  - До 24-го месяца так кончается каждый такой бой, после — 60 процентов.
  - У APOCALYPSE_CULT 16 членов, у неё всё в порядке.
- Миссию запускают скрипты `highwaymenOverflights` (около строки 28095) и `highwaymenStrikes` (около 28111).
- Исправить можно одним из трёх способов:
  - дописать BAD_COPS до 14 членов и более;
  - задать в развёртывании `customUnitType`;
  - дать бомбардировщику `raceBonus: STR_BAD_COPS: craftCustomDeploy: <своё развёртывание>`.

### 2. Чёрный вертолёт у BANDIT_VILLAGE: ранг 18 при 15 членах — вылет в половине случаев

- Миссия `STR_MISSION_HARASSMENT_STORMRATS_2` (строка 37214), `raceWeights`: `STR_BANDIT_TOWN: 50`, `STR_BANDIT_VILLAGE: 50`.
- Последняя волна: `ufo: STR_VESSEL_BLACK_HELICOPTER`.
- Развёртывание `STR_VESSEL_BLACK_HELICOPTER` (строка 88393) — `alienRank: 18`.
- У `STR_BANDIT_TOWN` 19 членов, 18-й — `STR_BANDIT_RATMAN_STORMRAT`, то есть сама крыса-штурмовик, ради которой вертолёт и задуман.
- У `STR_BANDIT_VILLAGE` (строка 25697) **15 членов**. Бой с вертолётом у деревни — вылет.
- Бомбардировщики той же миссии (ранг 13) у обеих рас в порядке.
- Сестринская миссия `STR_MISSION_HARASSMENT_STORMRATS` (строка 37194) берёт только `STR_BANDIT_TOWN: 100`, поэтому VILLAGE в `_2` похожа на описку.
- Миссию запускает скрипт `HarassmentStormratsPublicDanger2` (около строки 34129).
- Исправление: `STR_BANDIT_TOWN: 100` (или другая раса, у которой 19 и больше членов и крыса на месте 18).

### 3. AUX_XARQUID_GRAPPLE теряет весь профиль урона

Строка 9625, ключ `damageAlter:` записан дважды подряд (строки 9633 и 9634):

```yaml
    damageType: 6
    damageAlter:
    damageAlter:
      RandomType: 2
      ...
```

- Движок (rapidyaml через `YamlNodeReader`) при повторе ключа берёт **первое** вхождение, а оно пустое.
- Поэтому теряются `RandomType 2`, `ToHealth 0.4`, `ToArmorPre 0.1`, `ToTile 0.3`, `ToTime 1.5`, `FixRadius 0` и `IgnoreDirection false`. Захват бьёт по умолчаниям типа урона 6.
- Исправление: удалить одну строку `damageAlter:`.

### 4. `despawnEvenIfTargeted` у развёртываний не действует

- Поле читает только `RuleAlienMission` (`RuleAlienMission.cpp:81`). У `alienDeployments` его нет, загрузчик молча пропускает.
- Используется оно в `GeoscapeState::processMissionSite`. Если флага у миссии нет, точка с истёкшим сроком не исчезает, пока на неё летит корабль игрока (ветка «CHEEKY EXPLOIT»: `removeSite = noFollowers`).
- Флаг стоит у 16 развёртываний.
  - У пяти он действует всё равно, потому что у одноимённой миссии он тоже есть: CATACOMBS_BUTCHER, CATACOMBS_BUTCHER_ENTRY, HALLS_OF_FEAR, NIGHTOSHPHERE_DELOREAN, NIGHTOSHPHERE_HARVEST.
  - У одиннадцати флаг только на развёртывании, и точка не исчезает, пока её держит корабль:

| Развёртывание | Строка развёртывания | Строка миссии |
|---|---:|---:|
| EUROSYNDICATE_ELIMINATION | 59849 | 34554 |
| THULE_BOSSBATTLE | 61477 | 34416 |
| GATE_OF_FEAR | 70314 | 35925 |
| NECROPOLIS | 70421 | 35937 |
| CITY_OF_THE_DEAD_SCOUTING | 70532 | 35949 |
| CITY_OF_THE_DEAD | 70644 | 35961 |
| FOUNTAIN_OF_YOUTH | 70712 | 35985 |
| FOUNTAIN_OF_YOUTH_G | 70803 | 35997 |
| STYX_BLACK_TOWER_OUTSIDE | 71026 | 34540 |
| EMANSION_MAG | 85243 | 36025 |
| DOOMED_CRYPT | 85819 | 35178 |

Исправление: перенести `despawnEvenIfTargeted: true` в одноимённую запись `alienMissions`. С развёртывания его можно убрать или оставить: там он ни на что не влияет.

## Проверено и чисто

| Что | Итог |
|---|---|
| Повторы id | Только намеренные `delete` с новым определением: предмет `STR_ETHEREAL_CORPSE`, шесть ванильных `alienMissions` (строки 34266-34271), НЛО `STR_HARVESTER` (39433 / 40808) |
| Битые ссылки из файла | нет |
| Члены рас | каждый член каждой расы — существующий юнит; у самой короткой расы 8 членов |
| Ранги против рас | кроме находок 1 и 2 — ни одной пары «раса — развёртывание», где ранг не помещается |
| Зоны траекторий | 309 миссий × 2 100 пар «миссия — регион», ни одной зоны за пределами `missionZones`. Контроль: при числе зон на 1 меньше скрипт находит 132 нарушения, значит, проверка работает |
| `itemSets` | нет строки без комплекта у юнита, который не является живым оружием (иначе «item set not defined») |
| Живое оружие | у 107 из 109 оружие есть: `builtInWeapons` юнита, брони или `<раса>_WEAPON`. Без оружия только `STR_DANCER_SLAVE` (19626, tu 1) и `STR_VERDUN_SHADE` (19769, `cosmetic`), обе похожи на замысел |
| alienItemLevels | одна строка из 10, значения 0-4, движок сам ограничивает |
| Миссии точек | у каждой миссии объекта 3 есть волна с `objective` или прямое развёртывание точки |
| `nextStage` | все цели существуют, циклов нет |
| Весовые таблицы | ни в одном месяце нет таблицы с нулевой суммой (`raceWeights`, `missionWeights`, `regionWeights`, `alienBaseUpgrades`, `huntMissionWeights`) |
| Вложенные ключи | все известны движку, опечаток нет |

## Мелочи

- `STR_VESSEL_FOOT_PATROL_NECRO` (строка 89411): `alertDescription: STR_VESSEL_FOOT_PATROL_NECRO_BRIEFING.SCR` — имя фоновой картинки, вставленное вместо строки. Вреда нет: развёртывания НЛО тревогу не показывают.
- Строк нет в en-US:
  - имена миссий `STR_EXPLOSION_1_MISSION` (36943) и `STR_BANDIT_ROBBERS_ASSAULT` (39356). Обе с объектом 6. В сведениях об НЛО при гиперволновом декодере покажется сырой ключ;
  - `STR_LOC_SPACE_STATION` (34614);
  - обломок `SENTRY_CORPSE_1` (строка 4191, труп `HWP_SENTRY_LAUNCHER`) называется `STR_SENTRY_CORPSE`, а строки нет: в бою видно сырое имя.
- Ни на что не ссылаются: предметы `STR_SENTRY_CORPSE` (4221), `STR_TANK_MSDF_CORPSE` (4642), развёртывание `STR_VESSEL_PROBE_FOOT_ATTACK_SWARM` (51934).
- Возможно, недостижимые подмены `raceBonus`: раса, для которой они написаны, на этом корабле не летает.
  - COURIER / FRIGATE с `_FLOATER_ELITE` / `_SECTOID_ELITE`;
  - USO `*_TASOTH` (`craftCustomDeploy` на строках 43820-43979).
  - Не проверялось до конца, низкий приоритет.

## Чего нет

- В логах установки (`Пиратки/Dioxine_XPiratez/user/openxcom*.log`) нет строк «does not have a member». Вылеты 1 и 2 предсказаны по данным и коду движка, в игре не пойманы.
- Бой не запускался ни по одной находке.

## Инструменты

Скрипты разового прогона лежат в блокноте сессии, в репозиторий не входят. Логика:
- загрузка файла через `rul_map.compose`;
- слитые значения из `.index/mod/Piratez/rul/values.tsv`;
- модель «раса × развёртывание» с зонами регионов, текстурами глобуса, `raceBonus` и ответным ударом.

Повторить: собрать индекс `python tools/rul_map.py` и пройти те же проверки по разделу «Как движок выбирает».
