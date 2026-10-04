# Граница «C++ логика ИИ + механика из рулсетов = фактическое поведение»

Коммит: 7cd80e284 (ветка hd-render). Только чтение кода и рулсетов, игра не запускалась.
Бот = `AiProbe::careful`, TACTICS выключен. Флаги V4: AMBUSH_MEMO, BLOCKED_STEP,
ESCAPE_REACH_FIRST, FAST, KNOWN_OCCUPANT_PATH_V2, LIGHTSKIP, LOADOUT_FIX, PATROL_STUN_PREFIX,
STALE_EXACT, STALE_PATROL_NODE, WALKFOV_SKIP. Всё прочее помечено «вне V4».

Источник данных X-Piratez: `.index/mod/Piratez/rul/values.tsv` (итог слияния рулсетов, `tools/rul_map.py`),
читался через `csv.reader(..., quoting=QUOTE_NONE)` (R-109). Скрипты разбора — в блокноте сессии
(`pz_ai_stats.py`, `pz_ai_stats2.py`, `pz_tags.py`, `pz_shield.py`), в репозиторий не клались.
«Враг» здесь = юнит, упомянутый в `alienRaces` (`members`, `membersRandom`) или как `customUnitType`
подкреплений `alienDeployments`. Таких 318 из 446 юнитов.

Метки знания (как в `00_README.md`): ИСТИНА — полное состояние боя; СТОРОНА — знание фракции
(TurnsSinceSpotted, пометки для снайперов); ЮНИТ — свои поля и статы; ПАМЯТЬ — что AIModule
запомнил сам; РУЛСЕТ — числа из рулсета и опций, одинаковые для всех.

---

## 0. Схема

```
Фактическое поведение врага/бота
├── C++ решение AIModule (что ИИ ВИДИТ)
│   ├── поля юнита из RuleUnit: aggression, intelligence, sniper, spotter, isLeeroyJenkins,
│   │   meleeWeapon/psiWeapon, ignoredByAI, waitIfOutsideWeaponRange, pickUpWeaponsMoreActively
│   ├── поля брони: allowsMoving/Kneeling/Running, size, movementType, веса целей (ai:), скрипт
│   │   aiCalculateTargetWeight
│   ├── поля предмета: ai.useDelay, battleType, powerBonus+damageType (частично), range, explosionRadius
│   ├── узел ai: Mod (задержки, коэффициенты выбора режима, порог реакции, веса)
│   ├── опции: sneakyAI, traceAI, battleExplosionHeight, oxceReactionFireThreshold
│   └── AlienDeployment.cheatTurn → isCheating
└── Механика, которую AIModule НЕ видит, но которая решает исход
    ├── восстановление брони (recovery: ОВ, энергия, оглушение, здоровье, mana, мораль)
    ├── скрипты Пираток (щиты, блок физическим щитом, наручники, stealth, вампиризм, …)
    ├── реакции защитника: порог, тип (приклад/ближний бой с разворотом, EMR 2), CQB
    ├── типы урона (ToStun, ToHealth, броня цели, RandomStun) при выполнении атаки
    ├── стоимость шага брони (moveCost, округление EMCR 2, бег, нагрузка)
    └── видимость (visibilityAtDark, камуфляж, heatVision, psiVision) — через TileEngine
```

---

## 1. Таблица A: поле рулсета или опция → геттер → где читается → на какое решение влияет

Значение в Пиратках — из `values.tsv` и `Piratez_Globals.rul`; «умолч.» — умолчание движка.

### 1.1 Поля юнита (units)

| Поле | Геттер / место чтения | Где читает ИИ (файл:строка) | Решение | Пиратки (враги, 318) |
|---|---|---|---|---|
| `aggression` | BattleUnit::getAggression, копия из RuleUnit (BattleUnit.cpp:494-512) | AIModule.cpp:1904 (findFirePoint при `_spottingEnemies \|\| aggression < RNG::generate(0,3)`), :3890 (бонус очереди), :4290-4345 (selectMeleeOrRanged), выбор режима :2845 | искать ли точку огня без видимых врагов; очередь; ближний бой | 1:106, 2:82, 0:51, 3:40, 4:17, 8:11, 5:6, 6:3, 7:3 |
| `intelligence` | `_intelligence` (AIModule.cpp:60) | :4217 (шлюз памяти цели), :3883-3884 (шум выбора режима) | помнит ли цель; насколько случаен выбор режима огня | 4:78, 3:47, 6:45, 5:44, 2:40, 1:27, 7:16, 8:12, 10:7, 9:2, 0:1 |
| солдат игрока | BattleUnit.cpp:85-86: `_intelligence = 2; _aggression = 1` | те же места (бот) | бот помнит цель 2 хода, шум режима ±(coeff·8) | — (зашито в C++) |
| `sniper` | getSniperPercentage | AIModule.cpp:1839 (`RNG::percent`), :4218 (обход шлюза памяти) | стрелять по пометке для снайперов | >0 у 132 (33:40, 50:38, 25:33, …) |
| `spotter` | BattleUnit spotter | BattleUnit.cpp:1955-1985 (пометка при попадании), SavedBattleGame | сколько ходов цель помечена для снайперов | ≠0 у 163 |
| `isLeeroyJenkins` | isLeeroyJenkins | AIModule.cpp:598 → dont_think | думать ли вообще | 14 врагов (+2 не враги) |
| `meleeWeapon` | getUtilityWeapon(BT_MELEE) | AIModule.cpp:224 (dont_think), TileEngine.cpp:2711 (реакция) | чем бить | 32 юнита, в основном AUX_FISTO |
| `psiWeapon` | пси-оружие юнита | AIModule.cpp:661 (только после getAIUseDelay), psiAction :4011-4168 | пси-атака | 20 юнитов, в основном AUX_SEDUCTION |
| `ignoredByAI` | isIgnoredByAI | AIModule.cpp:4267 (только для целей не PLAYER) | быть целью | 4 юнита (VIP-кошка, мозг босса, дрон, жертва) |
| `waitIfOutsideWeaponRange` | — | AIModule.cpp:3021, :3528 | ждать вместо сближения | не задан (0) |
| `pickUpWeaponsMoreActively` | BattleUnit.cpp:503-512 | BattlescapeGame.cpp:459-480 | подбирать оружие | у юнитов не задан, глобально `ai:` true |
| `livingWeapon` | — | (оружие встроено) | — | 82 врага |
| `energyRecovery` | только в RuleStatBonus energyRegen | AIModule — не найдено в коде | — | 50:67, 40:57, 30:54, 35:43, 999:17 |
| `canPanic`, `berserkChance`, `avoidsFire` | canPanic (AIModule.cpp:4118), avoidsFire (Pathfinding.cpp:587) | пси (паника), путь | — | не заданы |

### 1.2 Поля брони (armors)

| Поле | Геттер | Где читает ИИ | Решение | Пиратки (броня врагов) |
|---|---|---|---|---|
| `allowsMoving` | Armor::allowsMoving | AIModule.cpp:804 | двигаться ли вообще | false у 3 |
| `allowsKneeling` | allowsKneeling(kneelDefault) | AIModule.cpp:816, :831; бот :3695 (вне V4) | приседать | false у 2 |
| `allowsRunning` | allowsRunning(small) | AIModule.cpp:245 (dont_think), :1966 (бегство) | бежать | — |
| `size` | isSmallUnit | AIModule.cpp:1966; Pathfinding | бег при бегстве, путь | 2 у 27 |
| `movementType` | getMovementType | Pathfinding.cpp:1134-1148 | путь (полёт) | 1 (летает): 51, 2: 18 |
| `moveCost` | getMoveCost* | Pathfinding.cpp:836-917 | цена шага — косвенно через путь | задан у 1 брони |
| `ai:` веса целей | getAITargetWeightAs* (Armor/Mod) | AIModule.cpp:4214-4240 | вес цели | у брони не задан |
| скрипт `aiCalculateTargetWeight` | ModScript::AiCalculateTargetWeight | AIModule.cpp:4243 | вес цели | в Пиратках хука нет |
| `meleeDodge`, back penalty | getMeleeDodge… | AIModule.cpp:2391 — только трассировка (`_traceAI`) | — (на решение не влияет) | — |
| `createsMeleeThreat` / `ignoresMeleeThreat` | — | ProjectileFlyBState.cpp:173-288 (CQB) — механика | — | false у 13 / true у 11 |
| `recovery` | RuleStatBonus | AIModule — не найдено в коде; AiProbe.cpp:3858-3886 (бот, PATROL_STUN_PREFIX) | — / резерв оглушения бота | у 908 из 969 бронь, 384 варианта |
| `visibilityAtDark`, камуфляж, `heatVision`, `psiVision` | TileEngine visible (:1862-1930), :1739 | только через видимость (СТОРОНА) | что ИИ «видит» | vAD 20:66, 9:57, 16:39, 30:38; heatVision>0: 145; камуфляж ночью ≠0: 89 |
| `painImmune`, `fearImmune` | — | мораль и паника (механика) | — | 30 / 10 |

### 1.3 Предметы (items)

| Поле | Геттер | Где читает ИИ | Решение | Пиратки |
|---|---|---|---|---|
| `ai.useDelay` | RuleItem::getAIUseDelay (RuleItem.cpp:599, :2104-2140) | AIModule.cpp:331 (медикит), :661 (пси) и выбор оружия | с какого хода можно применять | `ai` у предметов не задан → глобальные задержки |
| `battleType` | getBattleType | всюду (выбор оружия, граната, медикит) | категория действия | battleType 3 (ближний бой): 209 |
| `power` + бонусы + `damageType.ResistType` | getPowerBonus, reduceByResistance | AIModule.cpp:4290-4345 (selectMeleeOrRanged); бот evalFire :3764 (вне V4) | ближний или дальний | формулы бонусов: 345+130+6 в Piratez.rul |
| `meleeType`/`meleeAlter` | RuleItem.cpp:445-453, умолч. DT_MELEE (:429) | AIModule — ToStun не читается | — | meleeType 6 с ToHealth 0.2: 63 предмета |
| `explosionRadius` | getExplosionRadius | AIModule.cpp:3927, :4097 | граната, пси-площадь | — |
| `maxRange` | isOutOfRange | AIModule.cpp:3541-3550 при respectMaxRange | исключить режим | respectMaxRange true |
| `meleeHitCount` | RuleItem.cpp:600 (умолч. 25) | AIModule — не найдено | — | — |
| ITEM_STUN_PER_TURN и др. теги | скрипт ITEMS_OF_RECOVERY | AIModule — не найдено | — | 8 предметов (оглушение), энергия 20, мораль 30, mana 6, ОВ 5 |

### 1.4 Узел `ai:` Mod и глобальные константы

| Ключ | Чтение | Геттер → место ИИ | Решение | Умолч. (Mod.cpp:441-449) | Пиратки |
|---|---|---|---|---|---|
| useDelayBlaster / turnAIUseBlaster | Mod.cpp:3896-3922 (старый ключ :3896-3897) | getAIUseDelay | бластер с хода N | 3 | 1 |
| useDelayGrenade / turnAIUseGrenade | там же | getAIUseDelay | граната с хода N | 3 | 1 |
| useDelayFirearm | там же | getAIUseDelay | огнестрел | 0 | 0 |
| aiUseDelayProxy | там же | getAIUseDelay | мины | 999 | 1 |
| useDelayMelee / Psionic | там же | AIModule.cpp:661 (пси) | — | 0 / 0 | 0 / 0 |
| useDelayMedikit | там же | AIModule.cpp:331 | лечиться | 999 (никогда) | 1 |
| fireChoiceIntelCoeff | там же | AIModule.cpp:3883 | шум выбора режима | 5 | 5 (умолч.) |
| fireChoiceAggroCoeff | там же | AIModule.cpp:3890 | бонус очереди | 5 | 5 (умолч.) |
| extendedFireModeChoice | там же | AIModule.cpp:3531-3537 | ветка выбора режима | false | true |
| respectMaxRange | там же | AIModule.cpp:3541-3550 | исключить режим за дальностью | false | true |
| destroyBaseFacilities | там же | AIModule.cpp:1545 | ломать постройки базы | false | true |
| pickUpWeaponsMoreActively(Civ) | там же | BattlescapeGame.cpp:459-480 | подбор оружия | false | true / true |
| reactionFireThreshold(Civ) | там же | getReactionFireThreshold (Mod.cpp:5163) → TileEngine.cpp:2634-2650 | реагировать ли (механика защитника) | 0 | 5 / 5 |
| targetWeight* | там же | AIModule.cpp:4214-4240 | вес цели | Mod.h:247-251: threat 50, hostile 100, hostileCiv 50, friendly −200, neutral −100 | умолч. |
| minReactionAccuracy | — не найдено нигде в src | — | — | — | 5 (молча игнорируется) |
| extendedMeleeReactions | Mod.cpp:3403 | TileEngine.cpp:2711-2806 | тип реакции защитника | 0 | 2 |
| enableCloseQuartersCombat | Mod.cpp:3936 | ProjectileFlyBState.cpp:173-288 | CQB | 0 | 1 (точность 100, ОВ 0, энергия 9) |
| extendedRunningCost | константы | BattlescapeGame.cpp:2141 | бег не прерывается врагом | false | true |
| extendedMovementCostRounding | константы | Pathfinding.cpp:919-929 | округление цены шага | 0 | 2 |
| extendedSpotOnHitForSniping | константы | BattleUnit.cpp:1955-1985 | пометка для снайперов при попадании | 0 | 1 |
| AlienDeployment.cheatTurn | AlienDeployment.cpp:42 (умолч. 20), :170 | SavedBattleGame.cpp:1542 → AIModule.cpp:707, :1505, :2871 | всезнание | 20 | 20 у 489 заданий, 5 у STR_MARS_THE_FINAL_ASSAULT_2 |

### 1.5 Опции (options.cfg установки Пираток)

| Опция | Где читается | Решение | Значение | fixedUserOptions Пираток |
|---|---|---|---|---|
| sneakyAI | Pathfinding.cpp:254, :1022 | путь врага в обход видимых клеток | false (:412) | нет |
| traceAI | AIModule.cpp:57 | только трассировка | false (:418) | нет |
| oxceReactionFireThreshold | Mod.cpp:5163 (порог для PLAYER) | реакция солдат | 0 (:369) | нет |
| battleExplosionHeight | AIModule.cpp:3198, :3223 | оценка взрыва | 2 | да, 2 |

---

## 2. Развилки на границе ИИ и рулсета

### selectFireMethod : extendedFireModeChoice (AIModule.cpp:3531)
УСЛОВИЕ: `Mod::getAIExtendedFireModeChoice()` истинно (в Пиратках true).
ДАННЫЕ: РУЛСЕТ (extendedFireModeChoice, fireChoiceIntelCoeff, fireChoiceAggroCoeff); ЮНИТ (intelligence, aggression); ИСТИНА (дистанция до цели).
RNG HERE: `RNG::generate(-intelligenceModifier, intelligenceModifier)` AIModule.cpp:3883-3884 — случайная надбавка к оценке; всегда, на КАЖДЫЙ проверяемый режим (число вызовов = числу доступных режимов).
РЕЗУЛЬТАТ: `intelligenceModifier = coeff · max(10 − intelligence, 0)`; очередь получает `(aggression − 1) · AggroCoeff` (:3890). Выбирается режим с наибольшей оценкой.
ПРЕРЫВАНИЕ: нет.
ВОЗВРАТ: режим огня.
СТОРОНЫ: враг и бот. У бота intelligence 2 → шум ±40 (при coeff 5), aggression 1 → бонус очереди 0. В ванильной ветке (false): дистанция < 4 — очередь, без RNG.

### selectFireMethod : respectMaxRange (AIModule.cpp:3541-3550)
УСЛОВИЕ: `getAIRespectMaxRange()` и `isOutOfRange` для режима.
ДАННЫЕ: РУЛСЕТ (maxRange оружия, ключ ai:); ИСТИНА (дистанция).
RNG: нет.
РЕЗУЛЬТАТ: режим за дальностью исключается.
ВОЗВРАТ: режим или «нет режима».
СТОРОНЫ: все. Пиратки — включено.

### selectFireMethod / findFirePoint : waitIfOutsideWeaponRange (AIModule.cpp:3021, :3528)
УСЛОВИЕ: поле юнита истинно.
ДАННЫЕ: ЮНИТ.
RNG: нет.
РЕЗУЛЬТАТ: ждать вместо сближения.
СТОРОНЫ: у солдат false; в Пиратках поле не задано ни у одного юнита → ветка мёртвая.

### medikit_think : задержка медикита (AIModule.cpp:331)
УСЛОВИЕ: номер хода ≥ `getAIUseDelay(medikit)`.
ДАННЫЕ: РУЛСЕТ (useDelayMedikit; умолчание 999 = никогда, в Пиратках 1).
RNG HERE: `RNG::percent` AIModule.cpp:370 (лечение), :394 (стим от оглушения), :404 (стим энергии) — применять ли; только если задержка прошла и есть подходящий предмет.
РЕЗУЛЬТАТ: действие медикита. Сила стима берётся из `getStunRecovery` / `getEnergyRecovery` медикита (:420-421), а не из recovery брони.
СТОРОНЫ: враг. В ванили ветка не срабатывает (999), в Пиратках работает со 2-го хода (ход ≥ 1).
Следствие: изменение useDelayMedikit меняет число вызовов RNG у каждого врага с медикитом.

### think : пси с задержкой (AIModule.cpp:661)
УСЛОВИЕ: у юнита пси-оружие и ход ≥ `getAIUseDelay` пси-оружия.
ДАННЫЕ: РУЛСЕТ, ЮНИТ.
RNG HERE: psiAction AIModule.cpp:4081 `RNG::percent(controlOdds)`, :4092 `RNG::percent(80 − diff·10)`, :4168 `RNG::generate(35,155)` — тип и цель пси; только если ветка пси дошла до них. Плюс механика пси сдвигает глобальный поток: `RNG::globalRandomState().subSequence()` TileEngine.cpp:4721.
РЕЗУЛЬТАТ: пси-действие или обычный ход.
СТОРОНЫ: враги с psiWeapon (20 юнитов).

### SavedBattleGame : cheating (SavedBattleGame.cpp:1542)
УСЛОВИЕ: `(turn > cheatTurn/2 && liveAliens <= 2) || turn > cheatTurn`.
ДАННЫЕ: РУЛСЕТ (cheatTurn задания, умолч. 20); ИСТИНА (число живых врагов).
RNG: нет.
РЕЗУЛЬТАТ: флаг isCheating. AIModule.cpp:707 (вне COMBAT — всезнание о цели), :1505 (патруль к цели), :2871 (режим COMBAT для hostile).
СТОРОНЫ: враг. Бот — не найдено в коде, чтобы isCheating включался для PLAYER.
Пиратки: задание STR_MARS_THE_FINAL_ASSAULT_2 — с 6-го хода (cheatTurn 5), остальные — с 21-го или с 11-го при ≤2 живых.

### getTargetAttackWeight : шлюз памяти (AIModule.cpp:4216-4222)
УСЛОВИЕ: `_intelligence < target->getTurnsSinceSpottedByFaction(своя фракция)` И (`!isSniper()` ИЛИ нет пометки `getTurnsLeftSpottedForSnipersByFaction`).
ДАННЫЕ: ЮНИТ (intelligence, sniper), СТОРОНА (TurnsSinceSpotted, пометки для снайперов).
RNG: нет.
РЕЗУЛЬТАТ: цель AIW_IGNORED. Иначе вес из Mod/Armor (:4224-4240), затем скрипт `aiCalculateTargetWeight` брони (:4243).
ВОЗВРАТ: вес.
СТОРОНЫ: все. Солдатам каждый ход `TurnsSinceSpotted = 0` для игроков (SavedBattleGame.cpp:1558).
Связь с механикой: попадание выстрелом обнуляет TurnsSinceSpotted стрелка для фракции жертвы (BattleUnit.cpp:1955-1985) — канал знания из механики урона; скрипт Пираток SPOTTED_STATUS_REMOVE стирает пометку для снайперов (см. п. 3.9).

### validTarget : ignoredByAI и порог (AIModule.cpp:4267, :4278)
УСЛОВИЕ: цель не PLAYER и `isIgnoredByAI`; иначе вес > `getAITargetWeightThreatThreshold`.
ДАННЫЕ: РУЛСЕТ (ignoredByAI, threat 50).
RNG: нет.
РЕЗУЛЬТАТ: цель годна или нет.
СТОРОНЫ: все; ignoredByAI у солдата игрока не действует.

### selectMeleeOrRanged : шансы ближнего боя (AIModule.cpp:4290-4345)
УСЛОВИЕ: есть и ближний, и дальний вариант.
ДАННЫЕ: РУЛСЕТ (powerBonus и ResistType предмета ближнего боя); ЮНИТ (aggression, здоровье); СТОРОНА (число видимых врагов); ИСТИНА (броневой коэффициент `reduceByResistance` цели по типу урона).
RNG HERE: `RNG::percent(meleeOdds)` AIModule.cpp:4338 — ближний или дальний; всегда, когда оба варианта есть.
РЕЗУЛЬТАТ: `dmg = target->reduceByResistance(power, ResistType)`; dmg > 50 → +(dmg−50)/2; −20 за каждого видимого врага сверх одного; только при здоровье ≥ 2/3: aggression 0 → −20, >1 → +10·a.
ВОЗВРАТ: выбор атаки.
СТОРОНЫ: враг. Не читает: ToStun/ToHealth типа урона, броню цели (только сопротивление), энергетические щиты, блок физическим щитом, CQB.

### meleeAction : запас на сближение (AIModule.cpp:3300)
УСЛОВИЕ: ближний бой выбран.
ДАННЫЕ: ЮНИТ (ОВ, энергия), РУЛСЕТ (attackCost :3286).
RNG: нет.
РЕЗУЛЬТАТ: `chargeReserve = min(TU − cost.Time, 2·(energy − cost.Energy))` — предполагает энергию шага = ½ ОВ шага; moveCost брони и EMCR не читает.
СТОРОНЫ: враг. Для брони с иной ценой шага (в Пиратках у 1 брони) и для бега (ERC) оценка дальности рывка расходится с Pathfinding.

### explosiveEfficacy : высота взрыва (AIModule.cpp:3185-3223)
УСЛОВИЕ: оценка гранаты/взрыва.
ДАННЫЕ: РУЛСЕТ (getExplosionRadius :3927), опция battleExplosionHeight (:3198, :3223), ЮНИТ (мораль → desperation = (100−morale)/10, :3189), diff (:3185).
RNG: нет.
РЕЗУЛЬТАТ: число задетых врагов и своих; урон и броню не считает.
СТОРОНЫ: враг. Пиратки фиксируют battleExplosionHeight 2.

### TileEngine : порог реакции (TileEngine.cpp:2634-2650)
УСЛОВИЕ: реагирующий фильтруется по порогу `getReactionFireThreshold(фракция)`.
ДАННЫЕ: РУЛСЕТ (reactionFireThreshold 5 у врагов и гражданских в Пиратках), опция (у PLAYER — oxceReactionFireThreshold 0, Mod.cpp:5163).
RNG: нет здесь; дальше `RNG::percent` TileEngine.cpp:2892 (tryReaction).
РЕЗУЛЬТАТ: кто вообще может реагировать.
СТОРОНЫ: защитник. AIModule этот порог при выборе пути не читает — не найдено в коде.

### determineReactionType : ближний бой в реакции (TileEngine.cpp:2711-2806)
УСЛОВИЕ: порядок: оружие для реакций → getUtilityWeapon(BT_MELEE) → основное. При EXTENDED_MELEE_REACTIONS == 2 реагирующий временно разворачивается к цели (:2757-2762). Удар BA_HIT любым оружием, способным на BA_HIT, в зоне ближнего боя (:2797-2806) — значит и прикладом огнестрела; иначе выстрел навскидку.
ДАННЫЕ: РУЛСЕТ (extendedMeleeReactions 2, meleeType/meleeAlter оружия), ИСТИНА (положение).
RNG: нет в выборе типа; RNG в tryReaction (:2892) и в атаке (meleeAttackCalculate — subSequence TileEngine.cpp:4887).
РЕЗУЛЬТАТ: тип реакции.
СТОРОНЫ: защитник любой фракции. ИИ, идущий рядом с солдатом, не учитывает удар прикладом с разворотом: в AIModule поиск ExtendedMeleeReactions / EXTENDED_MELEE_REACTIONS пуст.

### ProjectileFlyBState : ближний бой вплотную, CQB (ProjectileFlyBState.cpp:173-288)
УСЛОВИЕ: `enableCloseQuartersCombat`; стрелок не `ignoresMeleeThreat`; рядом враг с `createsMeleeThreat`, у которого хватает ОВ и энергии и `validMeleeRange`.
ДАННЫЕ: РУЛСЕТ (CQB 1, точность 100, ОВ 0, энергия 9 в Пиратках; поля брони), ИСТИНА (соседи).
RNG HERE: проверка через `TileEngine::meleeAttack` (subSequence) — сорвать ли выстрел; при провале `RNG::generate(0,5)` — куда уйдёт выстрел (пол, вверх, вбок); `RNG::percent` sneakUp. Только когда условие выполнено.
РЕЗУЛЬТАТ: выстрел уходит мимо; у защитника списываются ОВ и энергия.
СТОРОНЫ: все стрелки. В AIModule и AiProbe упоминаний CQB нет — ни враг, ни бот не учитывают риск срыва выстрела вплотную.

### AiProbe::patrolStunReserve : PATROL_STUN_PREFIX (AiProbe.cpp:3888-3967, вызов BattlescapeGame.cpp:535)
УСЛОВИЕ: бот (careful), патрульный шаг, `energy > 0 && after <= 0 && after < full`, где `after` — оглушение после хода с учётом восстановления брони при энергии следующего хода (`stunRecoveryAt`, AiProbe.cpp:3858-3886).
ДАННЫЕ: ЮНИТ (энергия, оглушение), РУЛСЕТ (recovery брони, moveCost пути).
RNG: нет.
РЕЗУЛЬТАТ: V2 (PATROL_STUN_PREFIX ∈ V4) оставляет самый длинный префикс пути, при котором оглушение не перестаёт восстанавливаться; PATROL_STUN_RESERVE (вне V4) — блок целиком.
СТОРОНЫ: только бот. Это ЕДИНСТВЕННОЕ место в V4, где читается recovery брони.

### dont_think : бег Leeroy (AIModule.cpp:224, :245)
УСЛОВИЕ: isLeeroyJenkins.
ДАННЫЕ: ЮНИТ, РУЛСЕТ (allowsRunning брони, stamina).
RNG: нет в выборе бега.
РЕЗУЛЬТАТ: `canRun = _melee && allowsRunning(false) && energy > stamina·0.4f`.
СТОРОНЫ: 14 врагов Пираток.

---

## 3. Что приходит в решения через механику, а не через ИИ

Для каждого пункта: что делает механика, знает ли AIModule, есть ли RNG.

### 3.1 Восстановление ОВ и энергии (recovery.time, recovery.energy)
- Механика: `prepareNewTurn` (BattleUnit.cpp:2858) → `updateUnitStats(true,false)` (:2893): `prepareTimeUnits` (:2730) делает `setValueMax(_tu, tu, 0, base)` — ОВ ПРИБАВЛЯЮТСЯ к остатку, кап базой; затем нагрузка strength/weight и −10% за каждую рану ноги. `prepareEnergy` (:2754) учитывает раны торса.
- Пиратки: типовая формула врага `time = 0.5·tu + 125·manaNormalized`. При полной mana медиана 2.42× базы (min 0.5, max 4.41) — то есть кап; при пустой mana — только половина базы с переносом остатка. Врагов с mana 0 — 19 (у них ОВ = остаток + 0.5·tu). Без поля recovery — 15. ОВ зависят от manaNormalized у 862 бронь.
- Энергия: `10·healthNorm + 10·manaNorm + 0.2·stamina − 0.2·stun`.
- AIModule: не найдено в коде — ход планируется по текущим ОВ, без расчёта, сколько придёт на следующий ход. Перенос остатка ОВ (ход «вполсилы» даёт полный следующий) ИИ не использует.

### 3.2 Восстановление здоровья и оглушения
- Механика: `updateUnitStats(false,true)` (BattleUnit.cpp:2907): `prepareHealth` (:2769) — раны и огонь (RNG::generate по FIRE_DAMAGE_RANGE); `prepareStun` (:2807) → `healStun` (:2062): `_stunlevel -= power`, отрицательное восстановление НАРАЩИВАЕТ оглушение. `hasNegativeHealthRegen` (:2073) — только индикаторы и TileEngine.cpp:3203.
- Нормировка: `normalizedStun = stun / текущее здоровье` (RuleStatBonus.cpp:139-142).
- Округление: RuleStatBonus складывает члены в масштабе ×1000 и один раз округляет к ближайшему (RuleStatBonus.cpp:158-176, :380-407). Значит итог = round(Σ коэфф·стат).
- Пиратки: типовое `health = −0.165·stunNormalized` (у части бронь −0.1, например APOC_ARMOR_P0). С округлением здоровье начинает убывать (−1 за ход) только когда stun ≥ ~3× текущего здоровья (−0.1 — при ≥ 5×); дальше обратная связь: здоровье падает → stunNormalized растёт. При лёгком оглушении потерь нет. У 712 бронь здоровье зависит от stunNormalized. Типовое `stun = −0.05·health + 0.08·healthCurrent + 0.036·stunCurrent`; у врагов при полном здоровье медиана 1.4/ход (min −3, max 2000), ≤1 у 84, ≥10 у 24.
- Синты STR_SYNTH_* (20 бронь, все игроцкие _UC): `stun = 0.03·energyCurrent − 10` — отрицательно при энергии < 333, то есть оглушение растёт каждый ход; `health = 3 − 35·stun/health`; `time = 0.5·tu + 250·manaNorm`.
- AIModule: не найдено в коде. Глубоко оглушённая цель в Пиратках (stun ≥ ~3× здоровья) теряет здоровье каждый ход — ИИ это не оценивает ни как плюс, ни как минус. Бот знает только через patrolStunReserve (свой шаг, не цель).

### 3.3 Mana
- Механика: recovery.mana (типовое `1 − 0.1·health + 0.1·healthCurrent`), mana включена в Пиратках; manaNormalized питает ОВ, энергию и мораль.
- Солдат STR_SOLDIER_SYNTH: mana min 1, max 10, cap 33.
- AIModule: mana не читает — grep нашёл только медикит и self. Трата mana пси/заклинаниями косвенно режет ОВ следующего хода — ИИ не видит.

### 3.4 Мораль
- Пиратки: `morale = 0.08·bravery − 10 + 13·manaNorm − 0.07·morale`.
- AIModule: мораль читается в explosiveEfficacy (desperation, :3189) и через canPanic в пси (:4118). Восстановление морали — не найдено в коде ИИ.

### 3.5 Типы урона
- Механика: DT_STUN по умолчанию ToHealth 0, ToStun 1.0, RandomStun false (Mod.cpp:513-528). Пиратки: battleType 3 по damageType — режущий (7) 71, Daze (6) 39; удар прикладом meleeType 6 с ToHealth 0.2 у 63 предметов.
- Порядок урона: hitUnit (скрипты брони и боеприпаса, BattleUnit.cpp:1738-1746) → расчёт → damageUnit (:1814-1858) → отслеживание попаданий (:1955-1985) → damageSpecialUnit (:1993-2000).
- AIModule: читает только `reduceByResistance(power, ResistType)` в selectMeleeOrRanged (:4290-4345) и (бот, вне V4) в evalFire (:3764). ToStun, ToHealth, ToArmor, RandomStun — не найдено в коде ИИ.

### 3.6 Действия предметов (meleeAlter, battleType, ammo)
- battleType выбирает ветку ИИ (оружие, граната, медикит, пси).
- Боеприпас: bot evalFire пропускает взрывные (:3748, вне V4); у врага выбор режима (scoreFiringMode) мощность боеприпаса не смотрит — см. 50_* (не прослежено здесь подробно).
- meleeAlter: ИИ не читает; механика бьёт прикладом в реакции (TileEngine.cpp:2797-2806).

### 3.7 size и movementType
- AIModule: size — только бег при бегстве `allowsRunning(careful && isSmallUnit)` (:1966); movementType — через Pathfinding (:1134-1148), отдельно ИИ не читает.

### 3.8 Энергия шагов
- Механика: Pathfinding.cpp:836-917 (moveCost брони по видам шага), :919-929 округление (EMCR 2 в Пиратках), бег (ERC true: бег ставит ignoreSpottedEnemies, BattlescapeGame.cpp:2141).
- AIModule: читает итоговую цену пути (reachableWithAttack хранит `_reachableEnergyMax`, :937-945); meleeAction считает запас по ½ ОВ (:3300). ENERGY_PATROL_END_V2 (spendPatrol / endPatrolIfSpent :1318-1340) — вне V4. FIREPOINT_ENERGY_PATH (AiProbe.cpp:3969+) — вне V4; bresenhamPath энергию не смотрит.

### 3.9 Скрипты X-Piratez (глобальные, Yankes_Scripts.rul и HitFX-basic.rul)
| Хук | Скрипт (строка) | Что делает | RNG | Знает ли ИИ |
|---|---|---|---|---|
| hitUnit | YSCRIPT_ENERGY_SHIELDS_HIT_ITEM (:4429), _ARMOR (:4754) | щит поглощает урон | — | нет |
| hitUnit | ITEMS_OF_RESISTANCE_EFFECT (:4984), блок физическим щитом (:4948) | блок удара ближнего боя | `randomChance` (:4948) | нет |
| hitUnit | _HANDS_CHECK (:4892), CYDONIA_REMOTE_CONTROL (:5047), SHIELD_BREAKER (:5132) | проверки рук, Сидония, пробой щита | не прослежено | нет |
| damageUnit | VAMPIRISM (:2710) | вампиризм | — | нет |
| damageUnit | ATTACKER_LOSES_EXTRA_TU_ON_HIT (:2898) | атакующий теряет ОВ (тег REDUCE_TU_AFTER_HIT, 3 предмета по 40) | — | нет |
| damageUnit | BBRN_EVENT, IGNITE_SPELL, HITFX_DAMAGE_UNIT | события, поджог, теги эффектов | не прослежено | нет |
| damageSpecialUnit | ZOMBIFICATION_FIX_1HP, IXP_CHECK… | зомби, опыт | — | нет |
| createUnit | значения щитов, защита от наручников, SPAWN_UNIT_FULL_TU | старт | — | нет |
| newTurnUnit | ENCUMBRANCE_ENERGY_INSTEAD_OF_TU (:3324) | нагрузка бьёт по энергии, а не по ОВ | — | нет |
| newTurnUnit | HANDCUFFS_BREAKOUT_CHECKS (:3392) | побег из наручников | `randomRange` (:3392) | нет |
| newTurnUnit | SPOTTED_STATUS_REMOVE (:3428) | у брони с STEALTH_CHANCE (4 игроцкие: HOLOSUIT 60, LOKNAR_ASSASSIN 85, NEKO_HOLOSUIT 65, NEKO_UNIPUMA 70) в полуход игрока может обнулить TurnsLeftSpottedForSnipers | `randomRange` (:3440) | влияет на шлюз памяти (:4218) |
| newTurnItem | ITEMS_OF_RECOVERY (:4259) | восстановление от предметов | — | нет |
| createItem | случайный фитиль (Piratez.rul:4582 и др.) | | `randomRange` | нет |

Скриптовый RNG: `battle_game.randomRange` / `randomChance` → `RNG::generate` / `RNG::percent` глобального потока (SavedBattleGame.cpp:3471-3490). Значит, наручники, stealth и фитили сдвигают поток, из которого потом берёт AIModule.
В Пиратках НЕТ хуков reactionUnitAction/Reaction, reactionWeaponAction, visibilityUnit, aiCalculateTargetWeight, tryMeleeAttack/tryPsiAttack.

Теги: ARMOR_ENERGY_SHIELD_CAPACITY у 176 бронь, у 44 из 310 врагов alienRaces; ITEM_ENERGY_SHIELD_CAPACITY — 7 предметов; YTAG_DAMAGE_RETURNED_AS_HP — 10 предметов.

### 3.10 Видимость
- Механика: TileEngine visible (:1862-1930), getVisibleDistanceMaxHelper (:1739), поля брони visibilityAtDark/Day, camouflageAtDark/Day, antiCamouflage, heatVision, psiVision.
- AIModule: видит только итог — список замеченных и TurnsSinceSpotted (СТОРОНА). Темноту, камуфляж цели и свой heatVision в оценке клеток не учитывает (не найдено в коде). LIGHTSKIP (AiProbe.cpp:344, ∈ V4) — у бота: unitLightPower, то есть свет учитывается только в боте.
- getSpottingUnits — фиксированные 20 клеток (см. 20_*/30_*), а не дальность видимости брони.

### 3.11 Реакции
- Порог (п. 2), тип (п. 2), разворот EMR 2, CQB (п. 2). Споттеры реакции TileEngine.cpp:2585-2670, getReactor :2677-2700, validMeleeRange :5368/:5382.
- AIModule: прямой оценки «пройду ли под реакцией» нет; ПРИМЕР — бег при ERC не прерывается, но реакцию не отменяет.

---

## 4. Данные X-Piratez

### 4.1 aggression и intelligence врагов (318)

| aggression | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| врагов | 51 | 106 | 82 | 40 | 17 | 6 | 3 | 3 | 11 |

| intelligence | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| врагов | 1 | 27 | 40 | 47 | 78 | 44 | 45 | 16 | 12 | 2 | 7 |

- aggression ≥ 3 — 80 из 318. intelligence ≤ 2 и aggression ≥ 3 — 32.
- Шум выбора режима при coeff 5: intelligence 10 → 0; 4 → ±30; 2 → ±40; 0 → ±50.
- Память о цели: цель забывается, когда TurnsSinceSpotted > intelligence. У 68 врагов (intelligence ≤ 2) — за 1-3 хода.

### 4.2 Leeroy и ближний бой
- isLeeroyJenkins у врагов — 14: STR_AUR_2, CHUPACABRA_TERRORIST, DEEP_ONE_BERSERKER, DOOM_DEMON_TERRORIST, DOOM_SOUL_TERRORIST, ERIDIAN_FENCER, MAGGOT_TERRORIST, MEGAZOMBIE_TERRORIST, MUTON_HEAVY, SKELETON_TERRORIST, ZOMBIE_BUSTER/GRUBAS/PIMP/STERILE_TERRORIST. Всего 16 с STR_ZOMBIE и ZOMBIE_TROOPER_2.
- meleeWeapon: 32 юнита (AUX_FISTO, LOBSTER_CLAWS, AUX_LAMIA_BITE, AUX_ROBOT_FIST, AUX_TASOTH_WEAPON, STR_UNARMED_GAUNTLET(_PLUS), AUX_DOOM_IMP_CLAWS, STR_GAUNTLET_CLAW, AUX_BOOMOSAURUS_JAWS).
- Поля «только ближний бой» в рулсете нет; Leeroy и meleeWeapon — приближение. Скрипта melee-only в Пиратках не найдено.

### 4.3 Пси
- psiWeapon у 20 юнитов: AUX_SEDUCTION (большинство), HYPNOSIS, ENTROPY_BLAST, BRAINHACK, PYROKINESIS, UNLIMITED_RANGE (STR_ZBOSS), страх и др.
- psiVision > 0 у 66 бронь врагов.

### 4.4 Броня врагов (318 записей)
size 2: 27; movementType 1: 51, 2: 18; heatVision > 0: 145; camouflageAtDark ≠ 0: 89, AtDay ≠ 0: 73; allowsKneeling false: 2; allowsMoving false: 3; createsMeleeThreat false: 13; ignoresMeleeThreat true: 11; painImmune: 30; fearImmune: 10; moveCost задан у одной брони (baseFlyPercent 75/75, flyDown 50/50). `ai` с весами у брони и у предметов — нет.

### 4.5 Опции ИИ мода (Piratez_Globals.rul)
- `ai:` (:9104-9180): minReactionAccuracy 5 (не читается), reactionFireThreshold 5, Civ 5, extendedFireModeChoice true, respectMaxRange true, destroyBaseFacilities true, pickUpWeaponsMoreActively true, Civ true, aiUseDelayProxy 1, useDelayMedikit 1.
- Верхний уровень: turnAIUseGrenade 1, turnAIUseBlaster 1 (:8866-8867).
- Итог задержек: граната 1, бластер 1, огнестрел 0, ближний бой 0, пси 0, мины 1, медикит 1.
- constants: extendedMeleeReactions 2, extendedTerrainMelee 3, extendedRunningCost true, extendedMovementCostRounding 2, extendedSpotOnHitForSniping 1, extendedBerserkWithAimed 2, extendedItemReloadCost true.
- CQB: enableCloseQuartersCombat 1, точность 100, ОВ 0, энергия 9 (:8879-8882).
- fixedUserOptions: battleExplosionHeight 2, strafe, forceFire, alienBleeding, noAlienPanicMessages, allowPsionicCapture.
- aimAndArmorMultipliers [0.75,1,1,1,1].
- cheatTurn: 5 только у STR_MARS_THE_FINAL_ASSAULT_2; остальные 489 заданий — умолчание 20.

---

## 5. Итоговая таблица: величина → читает ли ИИ → влияет ли через механику → пример

| Величина | Читает ли AIModule (V4) | Влияет через механику | Пример в Пиратках |
|---|---|---|---|
| aggression | да (:1904, :3890, :4290-4345, :2845) | нет | aggression 8 у 11 врагов — почти всегда ищет точку огня |
| intelligence | да (:4217, :3883) | нет | intelligence 1 — забывает цель через 2 хода, шум режима ±45 |
| intelligence/aggression бота | да (зашито 2/1, BattleUnit.cpp:85-86) | нет | бот выбирает режим с шумом ±40 |
| sniper / spotter | да (:1839, :4218) | да (пометка при попадании :1955-1985) | sniper 50 у 38 врагов |
| isLeeroyJenkins | да (:598) | нет | 14 врагов бегут в ближний бой без оценки |
| useDelay* (ai:) | да (:331, :661, выбор оружия) | нет | медикит с хода 1 (в ванили никогда) |
| extendedFireModeChoice + коэффициенты | да (:3531-3537, :3883-3890) | нет | число вызовов RNG = числу режимов |
| respectMaxRange | да (:3541-3550) | нет | режим за maxRange исключён |
| cheatTurn | да, через isCheating (:707, :1505, :2871) | нет | Марс: всезнание с 6-го хода |
| веса целей / ignoredByAI | да (:4214-4243, :4267) | нет | VIP-кошка не цель (кроме для PLAYER) |
| powerBonus + ResistType ближнего оружия | да (:4290-4345) | да | шанс ближнего боя растёт при dmg > 50 |
| ToStun / ToHealth типа урона | нет | да (урон) | Daze-удар (39 предметов ближнего боя) копит оглушение; при stun ≥ ~3× hp оно ещё и снимает здоровье через recovery |
| броня цели (числа брони) | нет (бот evalFire — вне V4) | да | выстрел по тяжёлой броне оценён как по голой |
| энергетический щит (теги) | нет | да (скрипт hitUnit) | 44 врага alienRaces со щитом |
| блок физическим щитом | нет | да (`randomChance` :4948) | удар ближнего боя отбит |
| recovery.time (mana → ОВ) | нет | да | без mana враг получает лишь 0.5·tu |
| recovery.stun / health | нет (бот: только PATROL_STUN_PREFIX) | да | здоровье round(−0.165·stun/hp) за ход: −1 при stun ≥ ~3× hp |
| синты: stun от энергии | нет (бот: PATROL_STUN_PREFIX учитывает формулу) | да | синт с энергией < 333 оглушается сильнее каждый ход |
| mana | нет | да (ОВ, энергия, мораль) | трата mana сокращает следующий ход |
| мораль | частично (:3189, :4118) | да | паника, desperation в оценке взрыва |
| moveCost, EMCR, бег | итог пути — да; meleeAction — нет (½ ОВ, :3300) | да | рывок к цели недооценён/переоценён |
| allowsMoving / Kneeling / Running | да (:804, :816, :831, :245, :1966) | да | 3 врага не двигаются |
| size, movementType | частично (:1966; через Pathfinding) | да | 27 врагов 2×2 не бегут при бегстве |
| порог реакции | нет | да (TileEngine.cpp:2634-2650) | врагам нужно ≥5 для реакции |
| тип реакции, EMR 2 | нет | да (TileEngine.cpp:2711-2806) | солдат бьёт прикладом с разворотом |
| CQB | нет | да (ProjectileFlyBState.cpp:173-288) | выстрел вплотную уходит в пол |
| minReactionAccuracy | нет | нет (не читается) | значение 5 игнорируется |
| видимость брони, камуфляж, heatVision | нет (только итог видимости) | да | 145 врагов с тепловым зрением видят дальше в темноте |
| свет на клетке | нет (бот: LIGHTSKIP ∈ V4) | да | — |
| battleExplosionHeight | да (:3198, :3223) | да | зафиксировано 2 |
| sneakyAI | через Pathfinding (:254, :1022) | да | false |
| скрипт aiCalculateTargetWeight | да (:4243) | — | в Пиратках хука нет |
| скриптовый RNG нового хода | нет | да (сдвиг глобального потока) | наручники, stealth, фитили |
| попадание раскрывает стрелка | да, через TurnsSinceSpotted (:4217) | да (BattleUnit.cpp:1955-1985) | ответный огонь по невидимому стрелку |

---

## 6. Числа

| Число | Где | Значение |
|---|---|---|
| умолчания задержек | Mod.cpp:441-444 | бластер 3, огнестрел 0, граната 3, мины 999, ближний 0, пси 0, медикит 999 |
| fireChoice коэффициенты | Mod.cpp:441-444 | 5 / 5 |
| веса целей | Mod.h:247-251 | 50 / 100 / 50 / −200 / −100 |
| cheatTurn | AlienDeployment.cpp:42 | 20 |
| CQB умолчания | Mod.cpp:449 | 0, точность 100, ОВ 12, энергия 8, sneakUp 0 |
| DT_STUN | Mod.cpp:513-528 | ToHealth 0, ToStun 1.0, RandomStun false |
| meleeHitCount | RuleItem.cpp:600 | 25 |
| energy Leeroy для бега | AIModule.cpp:245 | > 0.4·stamina |
| chargeReserve | AIModule.cpp:3300 | min(TU − cost, 2·(energy − cost)) |
| selectMeleeOrRanged | AIModule.cpp:4290-4345 | +(dmg−50)/2, −20 за врага сверх одного, ±по aggression при hp ≥ 2/3 |
| солдат | BattleUnit.cpp:85-86 | intelligence 2, aggression 1 |
| порог реакции Пираток | Piratez_Globals.rul | 5 (игрок 0) |

## 7. RNG (места, где рулсет меняет число вызовов)

| Вызов | Место | Что решает | Когда | Чем рулсет сдвигает |
|---|---|---|---|---|
| `RNG::generate(-m, m)` | AIModule.cpp:3883-3884 | шум режима | на каждый режим при extendedFireModeChoice | число режимов оружия, флаг мода |
| `RNG::percent(meleeOdds)` | AIModule.cpp:4338 | ближний или дальний | если оба есть | meleeWeapon, оружие |
| `RNG::percent` медикит | AIModule.cpp:370, :394, :404 | лечение, стимы | после useDelayMedikit | useDelayMedikit 1 против 999 |
| `RNG::percent(getSniperPercentage)` | AIModule.cpp:1839 | снайперский выстрел | у снайперов | поле sniper |
| `RNG::generate(0,3)` | AIModule.cpp:1904 | искать ли точку огня | без видимых врагов | aggression (вызов идёт после `\|\|`, если `_spottingEnemies` ложно) |
| пси: percent / generate | AIModule.cpp:4081, :4092, :4168 | пси | после useDelay пси | psiWeapon |
| subSequence | TileEngine.cpp:4721 (пси), :4887 (ближний бой) | атака | при атаке | сдвигает ГЛОБАЛЬНЫЙ поток |
| CQB | ProjectileFlyBState.cpp:173-288 | срыв выстрела, направление `RNG::generate(0,5)`, sneakUp | при соседе-враге | enableCloseQuartersCombat 1 |
| tryReaction | TileEngine.cpp:2892 | реакция | после порога | reactionFireThreshold |
| огонь | BattleUnit.cpp:2769 (prepareHealth) | урон огнём | горящий юнит | FIRE_DAMAGE_RANGE |
| скрипты | Yankes_Scripts.rul :3392, :3440, :4948; Piratez.rul:4582 | наручники, stealth, блок щитом, фитиль | новый ход, удар, создание предмета | теги и предметы мода |

## 8. Знание

| Что | Метка | Как ИИ получает |
|---|---|---|
| поля юнита, брони, предмета | ЮНИТ / РУЛСЕТ | прямое чтение |
| ToStun, броня цели, щиты цели | ИСТИНА (в механике) | не получает |
| восстановление цели и своё | ИСТИНА | не получает (бот — своё оглушение, PATROL_STUN_PREFIX) |
| кто стрелял по мне | СТОРОНА | TurnsSinceSpotted = 0 при попадании (BattleUnit.cpp:1955-1985); `ai->setWasHitBy` только у жертвы с ИИ |
| пометки для снайперов | СТОРОНА | spotter, EXTENDED_SPOT_ON_HIT_FOR_SNIPING; стираются скриптом stealth |
| всё о цели | ИСТИНА | при isCheating (cheatTurn) |

---

## 9. Слепые пятна (доказано кодом)

1. AIModule в V4 не читает recovery брони (ОВ, энергия, оглушение, здоровье, mana, мораль): grep по AIModule.cpp не находит Recovery/Regeneration/getStunRecovery кроме медикита (:420-421). Исключение — бот, PATROL_STUN_PREFIX (AiProbe.cpp:3888-3967).
2. selectMeleeOrRanged (AIModule.cpp:4290-4345) не учитывает ToStun, броню цели, энергетические щиты (44 врага) и блок физическим щитом.
3. meleeAction (:3300) считает энергию шага как ½ ОВ, не читая moveCost и EMCR.
4. CQB (ProjectileFlyBState.cpp:173-288) — ни AIModule, ни AiProbe не упоминают; срыв выстрела вплотную не оценивается.
5. Реакция ближнего боя прикладом с разворотом (EMR 2, TileEngine.cpp:2757-2806) — ИИ не учитывает при ходьбе.
6. minReactionAccuracy в src не найден: настройка Пираток (5) молча не действует.
7. Трассировочная оценка уклонения (:2391) на решение не влияет — только при traceAI.
8. Скриптовый RNG нового хода (наручники :3392, stealth :3440) и createItem (фитиль) сдвигает глобальный поток до решений ИИ.
9. waitIfOutsideWeaponRange, canPanic, berserkChance, avoidsFire у юнитов Пираток не заданы — соответствующие ветки ИИ мертвы для этого мода.

## 10. Не прослежено

- Округление RuleStatBonus прослежено (одно округление к ближайшему на всю сумму), но кап и нижние границы у каждого стата после него (prepare*) против реальных чисел в бою не сверялись — проверены формулы, не результат в игре.
- Точная семантика `TileEngine::meleeAttack` внутри CQB (какие статы защитника, точность 100 как множитель).
- Тратят ли враги mana в бою (заклинания, пси) и как часто их ОВ режутся из-за этого.
- Аргументы скрипта CYDONIA_REMOTE_CONTROL и HANDS_CHECK — есть ли в них RNG.
- Влияние ENCUMBRANCE_ENERGY_INSTEAD_OF_TU на ОВ, которые видит ИИ в начале хода (порядок скрипта newTurnUnit относительно prepareNewTurn).
- Выбор боеприпаса и мощности в scoreFiringMode врага — в другом файле спеки (50_*), здесь только граница.
- Ванильная проверка (без мода) — числа в разделах 4-5 только для Пираток.
