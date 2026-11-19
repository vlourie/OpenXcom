# ИИ: аптечка, предметы с земли, оружие бота, carefulGuard, присед, кандидаты, граница «родной ИИ OXCE / правки стенда»

Область карточки:
- `AIModule::medikit_think`, `AIModule::dont_think`, `BattleUnit::think` (вызов аптечки);
- `BattlescapeGame::handleAI` (ветка предметов), `findItem`, `surveyItems`, `worthTaking`, `takeItemFromGround`,
  `takeItem`, `findBotWeapon`, `AIModule::setWeaponPickedUp`, `BattleUnit::getPickUpWeaponsMoreActively`;
- `BattlescapeGame::carefulGuard`, присед (`action->kneel`, `UnitTurnBState`, `BattlescapeGame::kneel`);
- `AiCandidates.cpp/.h`, `OXCE_AI_LOADOUT_FIX` (`NewBattleState.cpp`);
- полная таблица функций AiProbe, которые меняют поведение (раздел 9).

Сравнение «родное — стенд» сделано по `upstream/oxce-plus` (MeridianOXC): `git show upstream/oxce-plus:<файл>`.
В сборке без `OXCE_AI_DEV` все функции AiProbe — заглушки (`src/Battlescape/AiProbe.cpp:73-168`), поэтому в выпуске
работает ветка, помеченная здесь «враг без флагов».

Кто чем играет (00_README): **враг** — родной AIModule (флаги V4 его не включают, кроме тех, что прямо на HOSTILE).
**Бот** — тот же AIModule за сторону игрока: `OXCE_AI_BOT` + `OXCE_AI_CAREFUL=1`. Предикаты:
- `AiProbe::bot()` = `active() && envOn("OXCE_AI_BOT")` (`AiProbe.cpp:185-189`);
- `active()` = `envOn("OXCE_AI_PROBE")` (`:334-338`);
- `careful(unit)` = `bot() && envOn("OXCE_AI_CAREFUL")` **и** `unit->getFaction() == FACTION_PLAYER` (`:367-371`);
- `botTurn(save)` = `bot() && save->getSide() == FACTION_PLAYER` (`:356-359`);
- `envOn` — переменная задана, непустая и не начинается с `'0'` (`:175-179`).

`careful` смотрит на **текущую** фракцию, а не на исходную. Поэтому пришелец под контролем разума бота
(`getFaction()==PLAYER`, `getOriginalFaction()==HOSTILE`) тоже «careful», а солдат бота под контролем врага — нет.

---

## 1. Схема

```
BattlescapeGame::think()                                                      (BattlescapeGame.cpp:217)
  └── _save->getSide() != FACTION_PLAYER || AiProbe::botTurn(_save)           (:230)
        └── handleAI(selectedUnit)                                            (:374)
              ├── TU <= 5 -> dontReselect                                     (:374-377)
              ├── _AIActionCounter >= AiProbe::maxActions(unit) || !reselectAllowed || turnsSinceStunned==0 (:379)
              │     ├── carefulGuard(unit) -> UnitTurnBState(BA_TURN), return  (:381; :307-367)   [бот]
              │     └── следующий юнит / конец хода
              ├── careful -> ai->setTargetFaction(FACTION_HOSTILE)            (:425-430)            [бот]
              ├── AiProbe::beforeThink (запись кандидатов, зонд)              (:446; AiProbe.cpp:1527)
              ├── unit->think(&action)                                        (:447)
              │     └── BattleUnit::think                                     (BattleUnit.cpp:3388-3405)
              │           ├── reloadAmmo()
              │           ├── раз в ход (_aiMedikitUsed):
              │           │     ├── while (medikit_think(BMT_HEAL))           (:3397)  RNG
              │           │     └── while (medikit_think(BMT_STIMULANT))      (:3400)  RNG
              │           └── AIModule::think(action)                         (AIModule.cpp:506)
              │                 ├── [вне V4] revive / flee                    (:551-552)
              │                 ├── isLeeroyJenkins -> dont_think, return     (:598-600; :221-288)
              │                 ├── ... выбор режима (карточки 11-14) ...
              │                 ├── PATROL: evaluate |= RNG::percent(10)      (:682)
              │                 ├── _weaponPickedUp -> evaluate = true        (:695-698)
              │                 ├── tactical (careful у бота) -> tacticalMode (:639, :743-745; :2941-2997)
              │                 └── kneelDefault = careful && "SOLDIER"       (:750) -> action->kneel (:816, :820, :831)
              ├── BA_RETHINK -> think ещё раз                                 (:449-453)
              ├── ветка предметов (!weapon || !weapon->haveAnyAmmo())         (:462-476)
              │     ├── originalFaction != PLAYER: findItem                   (:464-469; :2751)        [враг]
              │     │     ├── surveyItems                                     (:2806)
              │     │     ├── worthTaking                                     (:2870)
              │     │     ├── на клетке: takeItemFromGround -> takeItem       (:2965, :3011)
              │     │     └── иначе action = BA_WALK к предмету, walkToItem   (:2780-2792)
              │     └── [вне V4] botArms (OXCE_AI_ARMS) && не видит врагов: findBotWeapon (:471-475; :3104)
              ├── moreActively && weaponPickedUp -> setWeaponPickedUp, think ещё раз (:477-482)
              ├── BA_WALK: calculate / [V4] blockedStepPlan / [V4 PREFIX] patrolStunReserve (:507-553)
              │     └── путь пуст и walkToItem -> targetTile->setDangerous(true) (:549-552)
              ├── атака -> UnitTurnBState (+ action.kneel) + ProjectileFly/Melee (:556-578)
              │     └── UnitTurnBState: action.kneel -> BA_KNEEL, kneel, FOV, checkReactionFire (UnitTurnBState.cpp:124-136)
              └── BA_NONE -> carefulGuard -> return; иначе следующий юнит     (:580-584)
```

---

## 2. Развилки

### 2.1. Вызов аптечки: раз в ход, до думания

```
УСЛОВИЕ:   if (!_aiMedikitUsed)
ДАННЫЕ:    флаг юнита — ЮНИТ; сбрасывается в prepareNewTurn (BattleUnit.cpp:2871)
RNG:       внутри medikit_think (2.2-2.4)
РЕЗУЛЬТАТ: _aiMedikitUsed = true; while (medikit_think(BMT_HEAL)) {}; while (medikit_think(BMT_STIMULANT)) {};
           затем AIModule::think
ПРЕРЫВАНИЕ: нет
ВОЗВРАТ:   нет (продолжает думать)
СТОРОНЫ:   оба. Родное, совпадает с upstream. Стенд добавил только зонды medikitBefore/After и счётчик used
```
Ссылки: `src/Savegame/BattleUnit.cpp:3388-3405`. Аптечка идёт **до** `AIModule::think` при **первом** думании юнита
в ходу. Значит, решение лечиться принимается до того, как ИИ узнаёт врагов, режим и нужные ОВ на атаку или укрытие.
Повторные думания в том же ходу (второе действие, RETHINK, «Re-Rethink» после подбора оружия) аптечку не зовут.

`AiProbe::medikitBefore/After` (`AiProbe.cpp:4543`, `:4553`) — **чистый зонд**. Он работает только при
`envOn("OXCE_AI_MEDIPROBE") && record()` (`:4538`), только читает, RNG не трогает и пишет строку `[AIMEDI]`.
В выпуске это пустые заглушки (`:167-168`).

### 2.2. medikit_think: быстрые отказы без RNG

```
УСЛОВИЕ:   self->getBaseStats()->stamina <= 0 || self->getBaseStats()->health <= 0      -> return false
           BMT_HEAL:      totalWounds <= 0                                               -> return false
           BMT_STIMULANT: self->getStunlevel() <= 0 && percentEnergyLeft >= 40           -> return false
           иной тип                                                                      -> return false
ДАННЫЕ:    totalWounds = getFatalWounds(); percentHealthLeft = Clamp((getHealth() - getStunlevel()) * 100 /
           getBaseStats()->health, 0, 100); percentEnergyLeft = Clamp(getEnergy() * 100 / getBaseStats()->stamina, 0, 100)
           — всё ЮНИТ (своё состояние)
RNG:       нет
РЕЗУЛЬТАТ: аптечка не применяется
ВОЗВРАТ:   return false (цикл while прекращается)
СТОРОНЫ:   оба
```
Ссылки: `src/Battlescape/AIModule.cpp:295-298`, `:301-303`, `:305-319`. Оглушение вычитается из здоровья
(`getHealth() - getStunlevel()`), поэтому оглушённый юнит считается раненым сильнее.

### 2.3. medikit_think: какие предметы годятся

```
УСЛОВИЕ:   itemRule->getBattleType() == BT_MEDIKIT &&
           (itemRule->getMediKitType() == healOrStim || itemRule->getMediKitType() == BMT_NORMAL) &&
           itemRule->getAllowTargetSelf()
           затем: if (_save->getTurn() < itemRule->getAIUseDelay(_save->getMod())) continue;
           if (usableMedikits.empty()) return false;
ДАННЫЕ:    инвентарь юнита — ЮНИТ; тип, medikitTargetSelf, ai.useDelay / useDelayMedikit — РУЛСЕТ; номер хода — ИСТИНА (общий)
RNG:       нет
РЕЗУЛЬТАТ: список usableMedikits
ВОЗВРАТ:   return false, если список пуст (RNG при этом не тратится)
СТОРОНЫ:   оба
```
Ссылки: `AIModule.cpp:322-342`. Задержка: `RuleItem::getAIUseDelay` (`src/Mod/RuleItem.cpp:2104-2107`) берёт собственное
`ai: useDelay` предмета (`:597-600`), если оно `>= 0`. Иначе берётся глобальное значение по `battleType`; для BT_MEDIKIT
это `useDelayMedikit`.
- Движок по умолчанию: `_aiUseDelayMedikit(999)` (`src/Mod/Mod.cpp:441`), то есть в ванили ИИ аптечками не пользуется.
- Пиратки: `useDelayMedikit: 1` (`Пиратки/.../Ruleset/Piratez_Globals.rul:9161`). Ход начинается с 1
  (`SavedBattleGame.cpp:1242`), поэтому в Пиратках аптечка разрешена с первого хода.
- Собственного `ai:` у предметов Пираток в `.index/mod/Piratez/rul/values.tsv` не найдено.

Аптечки типа `BMT_PAINKILLER` (3) не годятся ни на лечение, ни на стимулятор: тип не равен healOrStim и не BMT_NORMAL
(`src/Mod/RuleItem.h:36`). Множество еды Пираток с типом 3 ИИ не использует никогда.

### 2.4. medikit_think: решение лечиться (здесь «аптечка 30 %»)

```
УСЛОВИЕ:   BMT_HEAL, totalWounds > 0:
             if (self->getStunlevel() + totalWounds >= self->getHealth())   wantsToHeal = true
             else { chanceToHeal = 120 - (percentHealthLeft * 4);
                    if (chanceToHeal <= 0) chanceToHeal = 5;
                    wantsToHeal = RNG::percent(chanceToHeal); }
           if (!wantsToHeal) return false;
ДАННЫЕ:    оглушение, число смертельных ран, здоровье — ЮНИТ
RNG:       RNG HERE: RNG::percent(chanceToHeal) AIModule.cpp:370 — лечиться или нет; вызывается, если есть годная
           аптечка (2.3), есть рана и угроза не «срочная» (stun + раны < здоровья). Одно число на каждый проход цикла while
РЕЗУЛЬТАТ: wantsToHeal
ВОЗВРАТ:   return false при отказе
СТОРОНЫ:   оба, формула родная (совпадает с upstream)
```
Ссылки: `AIModule.cpp:350-378`. Комментарий в коде (`:361-363`): «30% health left = 0% chance to heal (actually 5%
chance because of random heal wish)».

**Откуда «аптечка 30 %».** Отдельного порога бота нет. Это родная формула `120 - 4 * percentHealthLeft`. Она доходит
до 0 при 30 % здоровья (за вычетом оглушения); выше 30 % шанс всегда 5 %, ниже — 120 − 4p (при 20 % это 40 %, при
10 % это 80 %). При «срочном» случае (`stun + раны >= здоровье`) лечение без броска. Бот проходит эту же функцию:
`BattleUnit::think` одинаков для всех, кого ведёт AIModule. В `docs/` строки «аптечка 30» не найдено.

### 2.5. medikit_think: решение колоть стимулятор

```
УСЛОВИЕ:   BMT_STIMULANT:
             (1) if (getStunlevel() > 0):
                   if (getStunlevel() + totalWounds >= getHealth()) wantsToStimStun = true
                   else { chanceToStim1 = 140 - (percentHealthLeft * 7);
                          wantsToStimStun = chanceToStim1 > 0 ? RNG::percent(chanceToStim1) : false; }
             (2) if (percentEnergyLeft < 40) { chanceToStim2 = 120 - (percentEnergyLeft * 3);
                                               wantsToStimEnergy = RNG::percent(chanceToStim2); }
           if (!wantsToStimStun && !wantsToStimEnergy) return false;
ДАННЫЕ:    ЮНИТ
RNG:       RNG HERE: RNG::percent(chanceToStim1) AIModule.cpp:394 — только при stun > 0, не «срочно» и chanceToStim1 > 0
           (то есть percentHealthLeft < 20)
           RNG HERE: RNG::percent(chanceToStim2) AIModule.cpp:404 — только при percentEnergyLeft < 40
РЕЗУЛЬТАТ: wantsToStimStun / wantsToStimEnergy
ВОЗВРАТ:   return false при отказе
СТОРОНЫ:   оба, родное
```
Ссылки: `AIModule.cpp:379-411`.

### 2.6. medikit_think: применение

```
УСЛОВИЕ:   для каждой аптечки из usableMedikits:
           (wantsToHeal && medikit->getHealQuantity() > 0) ||
           (wantsToStimStun && medikit->getStimulantQuantity() > 0 && medikitRule->getStunRecovery() > 0) ||
           (wantsToStimEnergy && medikit->getStimulantQuantity() > 0 && medikitRule->getEnergyRecovery() > 0)
           затем: medikitAction.updateTU(); medikitAction.Time += 4; if (!medikitAction.spendTU()) continue;
ДАННЫЕ:    заряды аптечки — ЮНИТ; tuUse, stunRecovery, energyRecovery — РУЛСЕТ; ОВ — ЮНИТ
RNG:       нет в C++ этой функции и medikitUse (TileEngine.cpp:4952-5073). Скрипт брони HealUnit — не прослежено
РЕЗУЛЬТАТ: HEAL — medikitUse(..., BMA_HEAL, первая часть тела с getFatalWound(i)), medikitRemoveIfEmpty;
           STIM — medikitUse(..., BMA_STIMULANT, BODYPART_TORSO), medikitRemoveIfEmpty; used = true; break
ПРЕРЫВАНИЕ: нет (лечение себя без анимации и без реакции врага)
ВОЗВРАТ:   return used
СТОРОНЫ:   оба, родное
```
Ссылки: `AIModule.cpp:415-502`, `+4` ОВ — `:434` («4TUs for picking up the medikit»), `spendTU` — `:440`, лечение —
`:459`, стимулятор — `:479`; `TileEngine::medikitUse` — `src/Battlescape/TileEngine.cpp:4952-5073`,
`medikitRemoveIfEmpty` — `:4940`. За одно успешное применение лечится одна часть тела. Цикл `while` повторяет вызов,
пока функция возвращает true. Каждый проход заново бросает RNG (2.4) и заново платит `+4` ОВ.

### 2.7. dont_think (берсерк, isLeeroyJenkins)

```
УСЛОВИЕ:   AIModule::think: if (_unit->isLeeroyJenkins()) { dont_think(action); return; }
ДАННЫЕ:    флаг юнита — РУЛСЕТ (leeroyJenkins юнита)
RNG:       внутри selectNearestTargetLeeroy / meleeActionLeeroy / setupPatrol — см. карточки ближнего боя и патруля
РЕЗУЛЬТАТ: ближний бой, если есть оружие ближнего боя и цель; иначе патруль
ВОЗВРАТ:   return из think
СТОРОНЫ:   оба (у кого флаг в рулсете); у солдат бота флага нет — не найдено в коде
```
Ссылки: `AIModule.cpp:598-600` (вызов после revive/flee, `:551-552`), тело — `:221-288`:
- `_melee = false`; `action->weapon = _unit->getUtilityWeapon(BT_MELEE)`. Если это BT_MELEE и
  `_save->canUseWeapon(action->weapon, _unit, false, BA_HIT)`, то `_melee = true`, иначе weapon обнуляется.
- `bool canRun = _melee && _unit->getArmor()->allowsRunning(false) && _unit->getEnergy() >
  _unit->getBaseStats()->stamina * 0.4f;` (`:245`).
- `visibleEnemiesToAttack = selectNearestTargetLeeroy(canRun)` (`AIModule.cpp:2295`). Если `> 0 && _melee` —
  `meleeActionLeeroy` (`:3338`): тип, run, цель, finalFacing и `updateTU`.
- Иначе: `setupPatrol`, `setCharging(0)`, `_reserve = BA_NONE`, тип и цель патруля.
- Затем `endPatrolIfSpent(action, false)` (`:282`). Это правка стенда, но в V4 она ничего не делает: `_patrolSpent`
  ставит только `spendPatrol` при `OXCE_AI_ENERGY_PATROL_END` (вне V4), см. раздел 9.

### 2.8. handleAI: целевая фракция бота

```
УСЛОВИЕ:   if (AiProbe::careful(unit)) ai->setTargetFaction(FACTION_HOSTILE);
ДАННЫЕ:    флаг стенда
RNG:       нет
РЕЗУЛЬТАТ: AIModule бота считает врагами HOSTILE (по умолчанию AIModule целится в игрока)
ВОЗВРАТ:   нет
СТОРОНЫ:   бот (CAREFUL=1, V4); у врага ветки нет
```
Ссылка: `BattlescapeGame.cpp:425-430`. Ставится перед **каждым** думанием юнита бота.

### 2.9. handleAI: ветка предметов

```
УСЛОВИЕ:   const bool botArms = AiProbe::pickUp(unit);
           bool pickUpWeaponsMoreActively = unit->getPickUpWeaponsMoreActively() || botArms;
           if (!weapon || !weapon->haveAnyAmmo()) {
             if (unit->getOriginalFaction() != FACTION_PLAYER) {
               if ((unit->getOriginalFaction() == FACTION_HOSTILE && unit->getVisibleUnits()->empty()) || pickUpWeaponsMoreActively)
                 weaponPickedUp = findItem(&action, pickUpWeaponsMoreActively, walkToItem);
             } else if (botArms && unit->getVisibleUnits()->empty()) {
               weaponPickedUp = findBotWeapon(&action, walkToItem);
             }
           }
           if (pickUpWeaponsMoreActively && weaponPickedUp) { setWeaponPickedUp(); unit->think(&action); }
ДАННЫЕ:    weapon = getMainHandWeapon() — ЮНИТ; getVisibleUnits() — ЮНИТ (видит сейчас);
           pickUpWeaponsMoreActively — РУЛСЕТ (юнит, иначе ai: глобально)
RNG:       нет в ветке; повторный think после подбора — полный проход think со всеми его RNG (PATROL percent(10) и др.)
РЕЗУЛЬТАТ: findItem может ПЕРЕПИСАТЬ решение, уже принятое think: action.type = BA_WALK к предмету (2.11)
ПРЕРЫВАНИЕ: нет
ВОЗВРАТ:   нет
СТОРОНЫ:   враг и нейтралы — findItem; бот в V4 — НИЧЕГО (originalFaction == PLAYER, а botArms ложно: OXCE_AI_ARMS вне V4)
```
Ссылки: `BattlescapeGame.cpp:455-482`. `getPickUpWeaponsMoreActively`: поле юнита, если оно задано
(`BattleUnit.cpp:503-506`); иначе `mod->getAIPickUpWeaponsMoreActively()` для HOSTILE и `...Civ()` для остальных
(`:509-512`). Солдат — false (конструктор солдата, `BattleUnit.cpp:76`). Ключи `ai: pickUpWeaponsMoreActively` /
`pickUpWeaponsMoreActivelyCiv` читаются в `Mod.cpp:3913-3914`. В Пиратках оба `true` (`Piratez_Globals.rul:9158-9159`),
поэтому враги и гражданские Пираток ищут предметы **даже на виду у противника**.

В upstream этой ветки бота нет: стенд добавил `botArms` и `else if` с `findBotWeapon`. Родная часть совпадает.

### 2.10. findItem: исключение «террориста»

```
УСЛОВИЕ:   if (action->actor->getRankString() != "STR_LIVE_TERRORIST" || pickUpWeaponsMoreActively)
ДАННЫЕ:    звание — РУЛСЕТ
RNG:       нет
РЕЗУЛЬТАТ: иначе return false
СТОРОНЫ:   враг
```
Ссылка: `BattlescapeGame.cpp:2754`. В Пиратках moreActively = true, поэтому исключение не работает.

### 2.11. findItem: на клетке — подобрать, иначе идти

```
УСЛОВИЕ:   targetItem = surveyItems(...); if (targetItem && worthTaking(targetItem, ...)) {
             if (targetItem->getTile()->getPosition() == action->actor->getPosition()) {
               if (takeItemFromGround(targetItem, action) == 0) { if (!targetItem->haveAnyAmmo()) reloadAmmo();
                 if (getGlow()) calculateLighting + calculateFOV; return true; }
             } else if (!targetItem->getTile()->getUnit() || targetItem->getTile()->getUnit()->isOut()) {
               action->target = ...; action->type = BA_WALK; walkToItem = true;
               if (pickUpWeaponsMoreActively) { finalAction = false; desperate = false; setHiding(false); }
             } }
           return false;
ДАННЫЕ:    предметы на земле по всей карте — ИСТИНА; занятость клетки предмета (getUnit) — ИСТИНА
RNG:       нет
РЕЗУЛЬТАТ: подбор (true) или замена действия на ходьбу к предмету (false, walkToItem)
ВОЗВРАТ:   true / false
СТОРОНЫ:   враг
```
Ссылки: `BattlescapeGame.cpp:2751-2797`. Если клетка предмета занята живым юнитом (даже невидимым врагу), ходьбы нет:
проверка идёт по `getTile()->getUnit()`, это ИСТИНА. Путь к предмету не найден → клетка помечается опасной до конца хода
(`:549-552`). Флаги опасности сбрасываются в `SavedBattleGame.cpp:2474`.

### 2.12. surveyItems: выбор предмета

```
УСЛОВИЕ:   кандидаты: !bi->isOwnerIgnored() && bi->getRules()->getAttraction() && (bi->getTurnFlag() || pickUpWeaponsMoreActively)
           && bi->getSlot() && bi->getSlot()->getType() == INV_GROUND && bi->getTile() && !bi->getTile()->getDangerous()
           оценка: currentWorth = getAttraction() / ((Position::distance2d(actor, tile) * 2) + 1);
           if (currentWorth > maxWorth) { if (tile->getTUCost(O_OBJECT, movementType) == 255) { setDangerous(true); continue; } ... }
ДАННЫЕ:    все предметы битвы — ИСТИНА; attraction — РУЛСЕТ; turnFlag — ИСТИНА (уронен в ход не-игрока)
RNG:       нет
РЕЗУЛЬТАТ: лучший по worth (строго больше; при равенстве — первый в _save->getItems())
ВОЗВРАТ:   targetItem или 0
СТОРОНЫ:   враг
```
Ссылки: `BattlescapeGame.cpp:2806-2857` (начальный maxWorth = 0 — `:2832`, оценка — `:2842`, 255 — `:2845`). `turnFlag` ставит `TileEngine::itemDrop`,
когда сторона не игрок (`TileEngine.cpp:5211`), и снимает подбор (`:5309`). Видимости предмета для ИИ нет: предмет за
стеной, в тумане, на другом этаже — такой же кандидат. Расстояние — `distance2d` без учёта этажа и пути.

### 2.13. worthTaking: стоит ли брать

```
УСЛОВИЕ:   if (action->actor->getVisibleUnits()->empty() || pickUpWeaponsMoreActively) {
             worthToTake = getAttraction();
             BT_FIREARM без путевых точек: нужен haveAnyAmmo() или BT_AMMO в инвентаре с getSlotForAmmo != -1, иначе return false;
             BT_AMMO: нужен BT_FIREARM в инвентаре, в который он лезет, иначе return false; }
           if (worthToTake) { freeSlots = 25 - сумма (высота * ширина) предметов инвентаря; if (freeSlots < size) return false; }
           if (pickUpWeaponsMoreActively) return worthToTake > 0;
           return (worthToTake - distance2d * 2) > 5;
ДАННЫЕ:    видимые юниты, инвентарь — ЮНИТ; attraction, размеры — РУЛСЕТ
RNG:       нет
РЕЗУЛЬТАТ: bool
СТОРОНЫ:   враг
```
Ссылки: `BattlescapeGame.cpp:2870-2952`. «25 клеток» — грубая оценка, сам код называет её «bad logic» (`:2931`).
С moreActively (Пиратки) функция почти всегда даёт true: проверка расстояния не делается.

### 2.14. takeItemFromGround / takeItem

```
УСЛОВИЕ:   if (getTimeUnits() < 6) return 1; freeSlots < size -> return 2; takeItem ? 0 : 3
           takeItem: BT_AMMO — зарядить правую, потом левую руку, иначе пояс; BT_GRENADE/PROXIMITY — пояс;
           BT_FIREARM/MELEE — правая рука, только если она пуста; BT_MEDIKIT/SCANNER — рюкзак; BT_MINDPROBE — левая, если пуста
ДАННЫЕ:    ОВ, инвентарь — ЮНИТ; getTULoad, getMoveToCost, слоты — РУЛСЕТ
RNG:       нет
РЕЗУЛЬТАТ: предмет перекладывается; ОВ: getMoveToCost(slot) (+ getTULoad при перезарядке; + цена переноса при
           Mod::EXTENDED_ITEM_RELOAD_COST); cost.haveTU() проверяется перед тратой
СТОРОНЫ:   враг (и бот через findBotWeapon — вне V4)
```
Ссылки: `BattlescapeGame.cpp:2965-3003`, `takeItem` — `:3011-3093` (лямбда зарядки — `:3019-3039`, лямбда размещения — `:3040-3050`,
выбор слота — `:3052-3091`). Порог «6 ОВ» (`:2974`) с настоящей ценой не связан: её считает `takeItem`.

### 2.15. findBotWeapon (вне V4)

```
УСЛОВИЕ:   предметы: !isOwnerIgnored && на земле && tile && !tile->getDangerous();
           dist = distance2d(unit, tile); if (dist >= bestDist(9) || tile->getPosition().z != unit->getPosition().z) continue;
           useful = BT_FIREARM ? !right && bi->haveAnyAmmo() : (BT_AMMO подходит к пустому оружию в руке, fitsHands);
           клетка не занята чужим не выбывшим юнитом
           на своей клетке: takeItem, при неудаче tile->setDangerous(true); иначе BA_WALK, finalAction=false, desperate=false
ДАННЫЕ:    все предметы в радиусе — ИСТИНА; занятость клетки — ИСТИНА
RNG:       нет
РЕЗУЛЬТАТ: подбор / ходьба к предмету
СТОРОНЫ:   бот, только при OXCE_AI_ARMS (вне V4)
```
Ссылки: `BattlescapeGame.cpp:3104-3170`, лучший — ближайший (`:3121`, `:3130`), занятость — `:3137`,
опасность — `:3152`, ходьба — `:3166`. Вызов — только когда бот не видит врагов (`:471`).

### 2.16. Повторное думание после подбора

```
УСЛОВИЕ:   AIModule::think: if (_weaponPickedUp) { evaluate = true; _weaponPickedUp = false; }
ДАННЫЕ:    флаг из setWeaponPickedUp (AIModule.cpp:1363-1366) — ПАМЯТЬ (сохраняется в сейв, :182, :208-209)
RNG:       RNG::percent(10) режима PATROL (:682) всё равно бросается ДО этой проверки, если не короткозамкнут
РЕЗУЛЬТАТ: принудительная переоценка режима
СТОРОНЫ:   враг (с moreActively); бот — только вне V4 (ARMS)
```
Ссылки: `AIModule.cpp:680-698`, `BattlescapeGame.cpp:477-482`.

### 2.17. carefulGuard (бот)

```
УСЛОВИЕ:   if (!AiProbe::careful(unit) || unit->isOut()) return false;
           раз на юнита за ход (_guardedTurn / _guardedUnits);
           threat = ближайший по distanceSq среди bu: getFaction() == FACTION_HOSTILE && !isOut() && getVisible();
           нет threat -> AiProbe::watchPoint(...) (OXCE_AI_WATCH, вне V4) -> в V4 return false;
           diff = |directionTo(target) - getDirection()|; steps = min(diff, 8 - diff);
           if (steps == 0 || getTimeUnits() < steps * getTurnCost()) return false;
ДАННЫЕ:    getVisible() — СТОРОНА (виден стороне игрока = стороне бота); позиция врага — по видимому врагу; ОВ — ЮНИТ
RNG:       нет. UnitTurnBState поворота: RNG внутри поворота не найдено в этой карточке; реакция врага на поворот — не прослежено
РЕЗУЛЬТАТ: statePushBack(UnitTurnBState(BA_TURN к цели)); tally guard
ПРЕРЫВАНИЕ: поворот может открыть новых врагов (FOV в UnitTurnBState)
ВОЗВРАТ:   true -> handleAI делает return, юнит не передаётся следующему (повторный вход в handleAI для того же юнита)
СТОРОНЫ:   только бот (CAREFUL=1). Вызов: при исчерпании действий (BattlescapeGame.cpp:381) и при BA_NONE (:582)
```
Ссылки: `BattlescapeGame.cpp:307-367` (видимость — `:328`, watchPoint — `:345`, шаги — `:352-355`, push — `:362`).
Это правка стенда: в upstream функции нет. Поворот идёт к **ближайшему по прямой** видимому врагу, а не к самому опасному
и не к тому, кто видит бота. ОВ на поворот бот тратит из остатка, который мог бы уйти на присед.

### 2.18. Присед: кто ставит action->kneel

```
УСЛОВИЕ:   const bool kneelDefault = AiProbe::careful(_unit) && _unit->getType() == "SOLDIER";
           COMBAT, BA_AIMEDSHOT || BA_AUTOSHOT: action->kneel = getArmor()->allowsKneeling(kneelDefault);
           COMBAT, _evalChosen && type != BA_WALK: action->kneel = _evalKneel;         (EVAL, вне V4)
           AMBUSH: action->kneel = getArmor()->allowsKneeling(kneelDefault);
ДАННЫЕ:    броня allowsKneeling (useBoolNullable с умолчанием) — РУЛСЕТ; тип юнита — РУЛСЕТ
RNG:       нет
РЕЗУЛЬТАТ: флаг kneel в действии
СТОРОНЫ:   враг: allowsKneeling(false) — сидит, только если броня явно разрешает (как в upstream, :678/:689 там);
           бот (V4): allowsKneeling(true) у солдат — сидит, если броня явно не запрещает
```
Ссылки: `AIModule.cpp:750`, `:814-817`, `:818-821`, `:831`; `Armor::allowsKneeling` — `src/Mod/Armor.cpp:1237`.

**Исполнение.** Флаг `kneel` читает только `UnitTurnBState::think` (`UnitTurnBState.cpp:124-136`; grep `.kneel` по
`src/Battlescape` — других читателей нет): после поворота юнит садится, если `_action.kneel && !isFloating() &&
!isKneeled()`, `spendTU(getKneelChangeCost())`, затем `calculateFOV` и `checkReactionFire(_unit, kneel)`.
`UnitTurnBState` с действием атаки создаёт handleAI (`BattlescapeGame.cpp:568`). Действие засады — это `BA_WALK`, оно
уходит в `UnitWalkBState`, а тот `kneel` не читает. **Флаг kneel засады не исполняется ни у врага, ни у бота** (то же в
upstream).

`BattlescapeGame::kneel` (`:618-641`) ИИ не вызывает. Его зовут игрок (`BattlescapeState.cpp:1251`,
`BattlescapeGame.cpp:2285`) и подъём перед ходьбой (`UnitWalkBState.cpp:105`). Подъём проверяет
`checkReservedTU(bu, tu, 0)` (`:621`) и вызывает `checkReactionFire` (`:633`). Если подъём не удался, ходьба
отменяется (`UnitWalkBState.cpp:109-118`).

### 2.19. tacticalMode: раненый бот отходит, а не лечится

```
УСЛОВИЕ:   tactical = AiProbe::tactics(_unit) || AiProbe::careful(_unit);  if (tactical) tacticalMode();
           в tacticalMode: wounded = careful && (getFatalWounds() > 0 || getHealth() < getBaseStats()->health / 2)
ДАННЫЕ:    ЮНИТ; _spottingEnemies, getSpottingUnits(escape target) — см. карточку режимов
RNG:       нет
РЕЗУЛЬТАТ: раненый бот в контакте уходит в ESCAPE ("pullback") даже из атаки и засады
СТОРОНЫ:   бот (V4); враг — только при TACTICS (вне V4), и у врага wounded всегда false (careful ложно)
```
Ссылки: `AIModule.cpp:639`, `:743-745`, `:2961-2962`, `:2963-2968`, `:2970`, `:2995-2996`. Связь с аптечкой: она
отработала раньше в том же ходу (2.1) с шансом 5 % при здоровье ≥ 30 %. Раненый бот обычно идёт в укрытие с открытой
раной, а лечиться будет в следующем ходу, опять с тем же броском.

---

## 3. Числа

| Значение | Выражение | Файл:строка | На что влияет |
|---|---|---|---|
| порог стимулятора по энергии | `percentEnergyLeft >= 40` → нет | `AIModule.cpp:313` | быстрый отказ без RNG |
| шанс лечения | `120 - percentHealthLeft * 4` | `AIModule.cpp:364` | 0 при 30 %, 40 % при 20 % |
| пол шанса лечения | `chanceToHeal = 5` при `<= 0` | `AIModule.cpp:365-369` | 5 % при здоровье ≥ 30 % |
| срочное лечение | `getStunlevel() + totalWounds >= getHealth()` | `AIModule.cpp:354` | лечение без броска |
| шанс стима от оглушения | `140 - percentHealthLeft * 7`, бросок при `> 0` | `AIModule.cpp:393-394` | > 0 при здоровье < 20 % |
| шанс стима по энергии | `120 - percentEnergyLeft * 3` при энергии `< 40 %` | `AIModule.cpp:403-404` | 3..120 % |
| цена «взять аптечку» | `Time += 4` | `AIModule.cpp:434` | платится при каждом применении |
| задержка аптечки (движок) | `_aiUseDelayMedikit(999)` | `Mod.cpp:441` | в ванили аптечка ИИ выключена |
| задержка аптечки (Пиратки) | `useDelayMedikit: 1` → `getAIUseDelayMedikit` | `Piratez_Globals.rul:9161`, `Mod.cpp:3906` | разрешена с хода 1 |
| задержка мин (Пиратки) | `aiUseDelayProxy: 1` (движок 999) | `Piratez_Globals.rul:9160`, `Mod.cpp:441` | не в этой карточке |
| подбор активнее | `pickUpWeaponsMoreActively(Civ): true` | `Piratez_Globals.rul:9158-9159`, `Mod.cpp:3913-3914` | findItem на виду, без turnFlag |
| ценность предмета | `attraction / (distance2d * 2 + 1)` | `BattlescapeGame.cpp:2842` | выбор в surveyItems |
| порог worthTaking без moreActively | `attraction - distance2d * 2 > 5` | `BattlescapeGame.cpp:2951` | почти никогда (комментарий `:2950`) |
| свободное место | `25 - Σ высота*ширина` | `BattlescapeGame.cpp:2932-2937`, `:2971-2981` | отказ от предмета |
| минимум ОВ на подбор | `getTimeUnits() < 6` → 1 | `BattlescapeGame.cpp:2974` | проверка без связи с ценой |
| непроходимая клетка | `getTUCost(O_OBJECT, ...) == 255` | `BattlescapeGame.cpp:2845` | клетка → опасная |
| радиус оружия бота (вне V4) | `bestDist = 9`, `dist >= bestDist` — отказ, тот же z | `BattlescapeGame.cpp:3121`, `:3130` | findBotWeapon |
| поворот carefulGuard | `steps = min(diff, 8 - diff)`, нужно `steps * getTurnCost()` ОВ | `BattlescapeGame.cpp:351-355` | поворот к врагу |
| порог «не выбирать снова» | `getTimeUnits() <= 5` → dontReselect | `BattlescapeGame.cpp:374-377` | конец действий юнита |
| действий на юнита | `AiProbe::maxActions(unit)`: 2, либо `OXCE_AI_ACTIONS` > 2 у careful (вне V4) | `BattlescapeGame.cpp:379`, `AiProbe.cpp:3826` | число думаний |
| энергия для бега берсерка | `getEnergy() > stamina * 0.4f` | `AIModule.cpp:245` | canRun |
| раненый бот | `getFatalWounds() > 0 || getHealth() < health / 2` | `AIModule.cpp:2961-2962` | отход вместо атаки |
| шанс переоценки патруля | `RNG::percent(10)` | `AIModule.cpp:682` | evaluate |

Аптечки Пираток, которые ИИ может применить к себе (`battleType 6`, `medikitTargetSelf: true`, тип 0/1/2, по
`.index/mod/Piratez/rul/values.tsv`): STR_MEDI_KIT (heal 6, stimulant 6, stunRecovery 12, energyRecovery 25),
STR_STIMM (тип 2: stimulant 1, stun 25, energy 50), STR_VODKA (тип 1, heal 5), STR_HEALING_GEL (heal 3), STR_CANTEEN,
STR_BEER, STR_SAKE, STR_MOONSHINE, STR_OXYGEN_TANK, STR_FROG_POISON, STR_KALTES_KLARES, STR_MEDIPACK_SAVIOUR,
STR_GROG_BARREL, STR_SIVALINGA, STR_ZOMBIGAL_ABILITIES, AUX_SPACE_MEDIPACK, AUX_MEDIPACK_HERBAL, AUX_MEDICAL_SHIELD,
AUX_SUPER_MEDIPACK, SPC_ANKH, SPC_OXYGEN_TANK, AUX_GOOD_TOUCH. Себе нельзя (ИИ их не применит):
STR_MEDIPACK, STR_FIRST_AID_KIT, STR_SMALL_MEDIPACK, STR_SPACE_MEDIPACK, AUX_MEDIPACK, STR_BANDAGE, STR_SUPER_MEDIPACK.
Всего предметов с battleType 6 — 66; много еды с типом 3 (обезболивающее), а его medikit_think не поддерживает.

---

## 4. RNG (в порядке выполнения за одно думание юнита)

| № | Где | Что решает | Когда вызывается |
|---|---|---|---|
| 1 | `AIModule.cpp:370` `RNG::percent(chanceToHeal)` | лечиться | первое думание юнита в ходу; есть годная аптечка (тип 0/1, себе, ход ≥ задержки); `getFatalWounds() > 0`; не «срочно». Повтор на каждом проходе while, пока лечение удаётся |
| 2 | `AIModule.cpp:394` `RNG::percent(chanceToStim1)` | стимулятор от оглушения | первое думание; есть годная аптечка тип 0/2; оглушение > 0, не «срочно», здоровье < 20 % |
| 3 | `AIModule.cpp:404` `RNG::percent(chanceToStim2)` | стимулятор по энергии | первое думание; есть годная аптечка тип 0/2; энергия < 40 % (бросок даже при оглушении 0) |
| 4 | `HealUnit` скрипт брони в `medikitUse` | — | при применении; есть ли RNG в скриптах Пираток — не прослежено |
| 5 | `AIModule.cpp:682` `RNG::percent(10)` | переоценка патруля | PATROL и `!_spottingEnemies && !_visibleEnemies && !_knownEnemies` (короткое замыкание `||`) — при каждом think, в том числе повторном после подбора |
| 6 | внутри `dont_think` → `selectNearestTargetLeeroy`, `meleeActionLeeroy`, `setupPatrol` | цель берсерка / узел патруля | только у isLeeroyJenkins; см. карточки ближнего боя и патруля |
| 7 | `UnitTurnBState.cpp:135` `checkReactionFire` после приседа | реакция врагов на присед | атака с `action.kneel`, юнит сел; RNG реакции — в карточке реакции |
| 8 | `BattlescapeGame.cpp:633` `checkReactionFire` при подъёме перед ходьбой | реакция врагов на подъём | сидящий юнит начинает ходьбу (`UnitWalkBState.cpp:105`) |
| 9 | повторный `unit->think` после подбора (`BattlescapeGame.cpp:481`) | весь think ещё раз | moreActively && weaponPickedUp (враг Пираток) |

Без RNG: findItem, surveyItems, worthTaking, takeItemFromGround, takeItem, findBotWeapon, carefulGuard, tacticalMode,
setTargetFaction, kneelDefault, `probeFixLoadout` (бросок `getArmorReplacement` делается, но сид сохраняется и
восстанавливается: `NewBattleState.cpp:662-664`), `AiCandidates::generate` (зонд; `beforeThink` сверяет сид до и после,
`pending.rngTouched`, `AiProbe.cpp:1539`, `:1587`).

**Легко сдвинуть поток RNG.** Броски 1-3 зависят от того, есть ли у юнита годная аптечка и сколько у него ран: любая
правка инвентаря (LOADOUT_FIX, подбор, раздача аптечек отряду), ран или оглушения меняет число бросков **до** think.
Бросок 1 повторяется по числу удачных лечений. Повторное думание после подбора (9) добавляет полный набор бросков think.

---

## 5. Знание

| Вход решения | Где | Источник |
|---|---|---|
| свои раны, здоровье, оглушение, энергия | `AIModule.cpp:301-303` | ЮНИТ |
| свой инвентарь, заряды аптечки | `AIModule.cpp:324-338`, `:419-423` | ЮНИТ |
| тип аптечки, medikitTargetSelf, useDelay | `AIModule.cpp:326-331` | РУЛСЕТ |
| номер хода | `AIModule.cpp:331` | ИСТИНА (общий для всех) |
| враги, угроза при лечении | — | не читается (слепое пятно 7.1) |
| предметы на земле по всей карте | `BattlescapeGame.cpp:2811-2826` | ИСТИНА |
| turnFlag предмета (уронен в чужой ход) | `BattlescapeGame.cpp:2820` | ИСТИНА |
| занятость клетки предмета | `BattlescapeGame.cpp:2781`, `:3137` | ИСТИНА (в т. ч. невидимый юнит) |
| видит ли юнит врагов | `getVisibleUnits()->empty()` `:466`, `:471`, `:2876` | ЮНИТ |
| проходимость клетки предмета | `getTUCost(O_OBJECT) == 255` `:2845` | ИСТИНА (карта) |
| attraction, слоты, getTULoad | `:2842`, `:2879`, `takeItem` | РУЛСЕТ |
| враг для carefulGuard | `bu->getVisible()` `:328` | СТОРОНА |
| точка наблюдения без видимых (WATCH, вне V4) | `AiProbe::watchPoint` | ПАМЯТЬ стороны (lastSeen) |
| можно ли сидеть | `allowsKneeling(kneelDefault)` `:816`, `:831` | РУЛСЕТ (+ флаг стенда) |
| раненый бот | `:2961-2962` | ЮНИТ |
| флаг подобранного оружия | `_weaponPickedUp` `:695` | ПАМЯТЬ (сейв) |

---

## 6. Карточка поведения (не режим)

**Аптечка.** Цели нет: только себя (`getAllowTargetSelf`). Кандидаты — годные аптечки инвентаря по порядку
инвентаря, применяется **первая подходящая** (break). Жёсткие отказы: нет ран (лечение), нет оглушения при энергии
≥ 40 % (стим), задержка рулсета, нет зарядов, не хватает `ОВ на применение + 4`. Оценки и штрафов нет, решение — бросок
по своему здоровью. Видимость, врагов, ОВ на атаку и укрытие не учитывает. Лечится одна часть тела за проход, а
проходов сколько угодно, пока броски удачны и хватает ОВ и зарядов.

**Подбор предмета (враг).** Цель — лучший по `attraction / (2·d + 1)` предмет на земле, видимость не нужна. Жёсткие
отказы: клетка опасна (была без пути в этом ходу или непроходима), нет места (25 клеток), огнестрел без патронов и
без подходящих патронов в инвентаре, патроны без подходящего оружия, клетка занята живым юнитом. Штрафа за видимость
клетки предмета нет (комментарий самого кода: «maybe this should check for enemies spotting the tile the item is on?»,
`BattlescapeGame.cpp:2875`). Без moreActively на виду у врага не ищет; с moreActively (Пиратки) — ищет, ходьба не
финальная и не «desperate», юнит не прячется. Путь пропал — клетка опасна до конца хода. Запасной ветки нет.

**Оружие бота.** В V4 отсутствует (2.9). Без ARMS бот без патронов ничего не подбирает. Отдельного «перезарядиться
из рюкзака» в этой ветке нет: `reloadAmmo()` вызывается в `BattleUnit::think` (`BattleUnit.cpp:3390`).

---

## 7. Слепые пятна (доказано кодом)

1. **medikit_think не читает угрозу.** В функции и в `medikitUse` нет обращений к врагам, `getSpottingUnits`,
   видимости или реакции. Лечение выбирается одинаково в укрытии и под огнём (`AIModule.cpp:290-502`).
2. **Аптечка не считает ОВ, нужные после неё.** Проверяется только `spendTU()` самого применения (`:440`); резерва на
   атаку, укрытие или реакцию нет. Каждый проход цикла платит ещё `+4` (`:434`), так что несколько удачных бросков
   подряд могут съесть ОВ хода до того, как think выберет действие.
3. **Аптечка решается до думания и один раз за ход** (`BattleUnit.cpp:3392-3394`). Рана, полученная в том же ходу
   (реакция на шаг), до следующего хода не лечится.
4. **Шанс лечения при здоровье ≥ 30 % — 5 %, сколько бы ран ни было**, пока не наступит «срочно» (`stun + раны ≥
   здоровье`). Число ран входит только в «срочно», не в шанс (`:354`, `:364`). Раненый бот при этом уходит в отход по
   tacticalMode (2.19), а не лечится.
5. **Скорость кровотечения не учитывается.** `getFatalWounds()` суммирует раны, но то, что каждая рана снимает здоровье
   каждый ход, в шанс не входит, кроме порога «срочно».
6. **Подбор предмета не учитывает обзор врага и угрозу ближнего боя.** surveyItems / worthTaking не читают
   `getSpottingUnits`, видимость клетки и врагов рядом (`BattlescapeGame.cpp:2806-2952`). С moreActively юнит Пираток идёт
   за предметом с `finalAction = false`, `desperate = false`, `setHiding(false)` (`:2787-2792`).
7. **findItem переписывает решение think.** Ветка предметов выполняется **после** think (`:462-476`); при ходьбе к
   предмету `action.type`, `target`, `finalAction`, `desperate` заменяются, и выбранные think атака / укрытие / засада
   теряются. Срабатывает у юнита без оружия в главной руке или без патронов (`getMainHandWeapon()`, `:456`, `:462`).
8. **Предмет «знают» сквозь туман.** Кандидаты — все `_save->getItems()` на земле, без видимости (`:2811`); занятость
   клетки — `getTile()->getUnit()` без проверки, видел ли его ИИ (`:2781`).
9. **Расстояние до предмета — по прямой в плоскости**, без этажей и пути (`distance2d`, `:2842`, `:2951`). Предмет
   этажом выше выглядит близким, пока поиск пути не пометит клетку опасной.
10. **Бот в V4 не подбирает ничего.** findItem закрыт для `getOriginalFaction() == FACTION_PLAYER` (`:464`),
    findBotWeapon требует `OXCE_AI_ARMS` (`AiProbe.cpp:379-383`), его нет в V4. Солдат без патронов остаётся без оружия.
11. **carefulGuard: только ближайший видимый, только раз за ход.** Нет оценки, кто бота видит или опаснее (`:325-337`),
    второго поворота за ход нет (`:313-321`). Без видимых врагов в V4 не поворачивается: `watchPoint` вне V4 (`:345`).
12. **Присед бота не входит в расчёт ОВ укрытия.** tacticalMode сравнивает остаток после атаки с `_escapeTUs` без цены
    приседа (`AIModule.cpp:2974-2976`, `:2984`), а присед добавляется после (`:816`) и тратит ОВ в UnitTurnBState
    (`UnitTurnBState.cpp:129-130`). Следующая ходьба сидящего бота стоит ещё и подъёма (`UnitWalkBState.cpp:105`).
13. **Присед засады — мёртвый флаг** у обеих сторон (2.18).
14. **На ходу бота `getPanicHandled()` ложно (с хода 2), а UnitWalkBState ветвится по этому флагу** — вывод по коду,
    прогоном не проверен. Флаг сбрасывают в `false` при `getSide() == FACTION_PLAYER && getTurn() > 1`
    (`BattlescapeGame.cpp:293-297`, вызывается из `BattlescapeState::init`, `BattlescapeState.cpp:816`). Ставится
    флаг только в ветке живого игрока (`BattlescapeGame.cpp:276-281`), в которую ход бота не заходит (`:230`). Это же
    записано в `docs/rakes/aibench.md:88`. Следствия для юнита бота (`getFaction() == FACTION_PLAYER`), за пределами
    этой карточки:
    - `postPathProcedures` не применяет `finalFacing`, «spin 180» эскейпа (`setHiding`) и `dontReselect` при
      `finalAction` — всё это только для `getFaction() != FACTION_PLAYER` (`UnitWalkBState.cpp:481-522`);
    - при ложном флаге `else if (!_parent->getPanicHandled()) _unit->clearTimeUnits();` обнуляет ОВ бота **в конце
      каждой ходьбы** (`UnitWalkBState.cpp:524-527`), то есть после любой ходьбы бот на ходу 2+ больше ничего не делает;
    - остановки по вновь замеченному врагу (`:235`, `:442`) и по резерву (`:338`) у бота не срабатывают.

    Это стоит проверить логом: ОВ бота сразу после ходьбы на ходу ≥ 2. Комментарий у HALF (`AIModule.cpp:841-842`,
    «it ended 77 % of turns with nothing left») с этим согласуется, но довода не даёт.

---

## 8. Не прослежено

- Скрипты брони `HealUnit` и прочие скрипты в `TileEngine::medikitUse` (`:4952-5073`): есть ли в них RNG у Пираток.
- `selectNearestTargetLeeroy` (`AIModule.cpp:2295`), `meleeActionLeeroy` (`:3338`), `setupPatrol` — их RNG и знание
  (карточки ближнего боя и патруля).
- `checkReactionFire` при приседе и подъёме — RNG и условия (карточка реакции).
- `checkReservedTU` для юнита стороны игрока на ходу бота (`BattlescapeGame::kneel`, `:621`): может ли подъём перед
  ходьбой не пройти и молча отменить ходьбу бота.
- Полный список значений по умолчанию в `tools/ai_probe.py` / `ai_arena.py` (что V4 ставит кроме названных флагов) —
  принято по `docs/research/ai-path-audit-2026-10-01.md:4226` и `tools/ai_probe.py:98+`.
- `AiProbe::fast()` (Map, Game, UnitDieBState, CrossPlatform, StartState): по месту вызова — отрисовка и задержки; что
  ни одна из этих веток не влияет на решения, построчно не проверено.
- Пункт 7.14 — вывод по коду, прогоном не проверен (запуск игры запрещён).

---

## 9. Граница «родной ИИ OXCE» и «правки стенда»: функции AiProbe, меняющие поведение

Колонка «V4» — включено ли у бота / врага в наборе AI_BASELINE_V4. «вне V4» — флаг в V4 не задан, функция
возвращает нейтральное значение (false / 0 / 2), поведение родное. Определения — `src/Battlescape/AiProbe.cpp`,
заглушки выпуска — `:73-168`.

### 9.1. Включение стенда и стороны

| Функция | Флаг | V4 | Что меняет | Определение | Вызов |
|---|---|---|---|---|---|
| `active()` | `OXCE_AI_PROBE` | да | разрешает все флаги; автозакрытие экранов | `:334-338` | BriefingState.cpp:270, ConfirmEndMissionState.cpp:126, InfoboxOKState.cpp:101, InventoryState.cpp:2332, NextTurnState.cpp:312 |
| `bot()` / `botTurn()` | `OXCE_AI_BOT` | да | ход игрока играет AIModule | `:185-189`, `:356-359` | BattlescapeGame.cpp:230 |
| `careful(unit)` | `OXCE_AI_CAREFUL` | да (бот) | у юнита стороны игрока: цель HOSTILE, tacticalMode, присед солдата по умолчанию, бег в эскейпе, wounded, carefulGuard; база для EVAL, ARMS, ACTIONS, PATROL_STUN | `:367-371` | BattlescapeGame.cpp:308, :425; AIModule.cpp:639, :750, :1966, :2961, :2983 |
| `tactics(unit)` | `OXCE_AI_TACTICS` | вне V4 (выключен) | tacticalMode у врага (HOSTILE) | `:361-365` | AIModule.cpp:639 |
| `think()` | `OXCE_AI_PROBE`, `OXCE_AI_PROBE_TURNS` | да | ход-лимит боя (бот: 60 ходов по умолчанию) → выход из игры; без бота — сам нажимает конец хода игрока | `:446-...`, `turnsWanted :191-196` | BattlescapeState.cpp:895 |
| `fast()` | `OXCE_AI_FAST` | да | отрисовка и задержки (без кадров) | `:340-343` | Map.cpp:501, :2792; Game.cpp:174, :756, :1089; UnitDieBState.cpp:153; CrossPlatform.cpp:1601; StartState.cpp:176; BattlescapeState.cpp:2607 |
| `probeFixLoadout` | `OXCE_AI_LOADOUT_FIX=1` | да | до боя: солдата, которому условие миссии запрещает броню и даёт неподвижную замену (у Пираток BOXX_ARMOR), переодевает в разрешённую подвижную броню из запаса базы (по умолчанию солдата, иначе первую годную); бросок `getArmorReplacement` делается с сохранением сида | NewBattleState.cpp:620-705 (сид `:662-664`) | NewBattleState.cpp:1023 |
| `probeRandomize` | `OXCE_AI_SEED`, `_CAMPAIGN`, `_CRAFT`, `_SQUAD`, `_MISSION`, `_RACE`, `_DIFF` | настройка боя | отряд, миссия, сложность | NewBattleState.cpp:714+ (env `:719`, `:730`, `:773`, `:824`, `:887`, `:899`) | меню быстрого боя / MainMenuState.cpp:311-313 |

### 9.2. Решения AIModule

| Функция | Флаг | V4 | Что меняет | Определение | Вызов |
|---|---|---|---|---|---|
| `revive` | `OXCE_AI_REVIVE` | вне V4 | стим оглушённому своему / ход к нему, ранний return из think | `:3598` | AIModule.cpp:551 |
| `flee` | `OXCE_AI_FLEE` | вне V4 | безоружный и раненый уходит от врагов, ранний return | `:3741` | AIModule.cpp:552 |
| `knownOccupantPath` (V1) | `OXCE_AI_KNOWN_OCCUPANT_PATH` | вне V4 | известный занятый тайл в пути | `:4066` | AIModule.cpp:540; AiProbe.cpp:1534 |
| `knownOccupantPathV2` | `OXCE_AI_KNOWN_OCCUPANT_PATH_V2` | да, только враг (`FACTION_HOSTILE`) | путь засады / точки огня обходит известного занявшего клетку | `:4111` | AIModule.cpp:1091, :1645, :3010; BattlescapeGame.cpp:514-520 |
| `stalePatrolNode` | `OXCE_AI_STALE_PATROL_NODE` | да | сохранённый узел патруля без пути сбрасывается | `:4185` | AIModule.cpp:1438 |
| `staleExact` | `OXCE_AI_STALE_EXACT` (0-3) | да (=1) | проверка узла по witnessReach, запасной calculate | `:4242` | AIModule.cpp:1446 |
| `ambushMemo` | `OXCE_AI_AMBUSH_MEMO` | да | память отказов поиска засады за вызов | `:1713` | AIModule.cpp:1663 |
| `escapeReachFirst` | `OXCE_AI_ESCAPE_REACH_FIRST` | да | эскейп пропускает клетки вне досягаемости до поиска пути | `:1891` | AIModule.cpp:2053 |
| `closeEnemies` | `OXCE_AI_GAP` | вне V4 | штраф клетки эскейпа за врага в 2 клетках | `:3576` | AIModule.cpp:2088 (и tally `:2139`) |
| `turretsSeeing` | `OXCE_AI_TURRET` | вне V4 | штраф клетки эскейпа за видящие турели | `:3704` | AIModule.cpp:2089 (и tally `:2144`) |
| `halfWalk` | `OXCE_AI_HALF` | вне V4 | патруль бота в контакте идёт на половину ОВ | `:3551` | AIModule.cpp:843 |
| `evalFire` | `OXCE_AI_EVAL` (+ careful) | вне V4 | своя оценка выстрела / приседа бота (`_evalChosen`, `_evalKneel`) | `:373-377` | AIModule.cpp:1849 |
| `firepointTargetCell` | `OXCE_AI_FIREPOINT_TARGET_CELL` | вне V4 | точка огня не на клетке цели | `:4048` | AIModule.cpp:3032 |
| `firepointPathOver` | `OXCE_AI_FIREPOINT_ENERGY_PATH` | вне V4 | точка огня по энергии пути | `:3970` | AIModule.cpp:3075 |
| `firepointBlocked`, `knownRevision`, `firepointBlockedSalt` | `OXCE_AI_FIREPOINT_BLOCKED`, `_SALT` | вне V4 | запрет повторной точки огня, упёршейся в юнита | `:4004`, `:4013`, `:4042` | UnitWalkBState.cpp:381; AIModule.cpp:990-1027 |
| tacticalMode, kneelDefault, run эскейпа, повтор setupEscape | через `careful` / `tactics` | бот — да | см. 2.18, 2.19 | AIModule.cpp:2941, :750, :1966, :640 | — |
| `endPatrolIfSpent` / `spendPatrol` | через `patrolOutOfEnergy` (`OXCE_AI_ENERGY_PATROL_END`) | вне V4 → no-op | конец патруля без энергии | AIModule.cpp:1318, :1331 | AIModule.cpp:282, :788; BattlescapeGame.cpp:543 |

### 9.3. handleAI и исполнение

| Функция | Флаг | V4 | Что меняет | Определение | Вызов |
|---|---|---|---|---|---|
| `carefulGuard` (BattlescapeGame) | через `careful` | да (бот) | поворот к ближайшему видимому врагу в конце действий | BattlescapeGame.cpp:307-367 | :381, :582 |
| `watchPoint` | `OXCE_AI_WATCH` | вне V4 | поворот к последнему месту врага, если никого не видно | `:3514` | BattlescapeGame.cpp:345 |
| `maxActions` | `OXCE_AI_ACTIONS` (+ careful) | вне V4 → 2 | число думаний юнита бота | `:3826` | BattlescapeGame.cpp:379 |
| `pickUp` → `findBotWeapon` | `OXCE_AI_ARMS` (+ careful) | вне V4 | подбор оружия ботом | `:379-383`; BattlescapeGame.cpp:3104 | BattlescapeGame.cpp:458, :473 |
| `blockedStepDecide` / `Plan` / `Stop` | `OXCE_AI_BLOCKED_STEP` | да | запрет первого шага, где уже упирался в юнита; перерасчёт пути | `:4372`, `:4403`, `:4346` (вкл. `:4285`) | BattlescapeGame.cpp:494, :523; UnitWalkBState.cpp:382 |
| `patrolStunReserve` | `OXCE_AI_PATROL_STUN_RESERVE` (V1) / `OXCE_AI_PATROL_STUN_PREFIX` (V2) | PREFIX — да, только careful | путь патруля бота режется до безопасного префикса; abortPath, если шагов нет | `:3888` | BattlescapeGame.cpp:535 |
| `patrolOutOfEnergy` | `OXCE_AI_ENERGY_PATROL_END` | вне V4 | обрыв патруля без энергии | `:3834` | BattlescapeGame.cpp:541 |
| `setTargetFaction(FACTION_HOSTILE)` | через `careful` | да (бот) | врагами бота считаются HOSTILE | — | BattlescapeGame.cpp:429 |
| `walkFovKeep` | `OXCE_AI_WALKFOV_SKIP` (1) | да | пропуск пересчёта обзора экрана для шагающего бота (FOV шага остаётся) | `:2345` (режим `:2028`, условие `:2036`) | UnitWalkBState.cpp:204 |
| `lightSkip` | `OXCE_AI_LIGHTSKIP` | да | пропуск пересчёта света юнита, который света не даёт (`unitLightPower == 0`) | `:344-354` | UnitWalkBState.cpp:228, :531 |

### 9.4. Только запись (не меняют поведение)

Это `tally`, `note`, `chosen`, `propose`, `logDecision`, `walkStop`, `walkFovBefore/After/Confirm`, `walkPlanned`,
`turnStage` (SavedBattleGame.cpp:1484, :1526, :1618, :1621), `event` (TileEngine.cpp:2895, ExplosionBState.cpp:211),
`sideEnds` / `logCasualty` (BattlescapeGame.cpp:649, :943), `modeOdds`, `ambush*`, `escape*`, `traceTile`, `pathAsk`,
`pathProf` (Pathfinding.cpp:175-217, :1848-1912), `OXCE_AI_TRACE_PATH`, `OXCE_AI_TRACE_MELEE` (AIModule.cpp:2410).

Отдельно — зонды, которые выполняют работу, но, по коду, решение не меняют:
- `medikitBefore/After` (`OXCE_AI_MEDIPROBE`, `:4543`, `:4553`).
- `beforeThink` (`:1527`) с `AiCandidates::generate` (`OXCE_AI_RECORD`). Генерация зовёт `findReachable`,
  `getFiringAccuracy`, `canTargetUnit`; RNG проверяется сверкой сида (`:1539`, `:1587`). Сброс узлов поиска пути
  перед думанием — побочный эффект, влияние не прослежено.
- `reachWanted/reachTaken` (`OXCE_AI_RECORD_REUSE`, Pathfinding.cpp:1914-1924): только копирует ответ `findReachable` в запись.
- `staleShadow` (`OXCE_AI_STALE_SHADOW`, AIModule.cpp:1463).
- `patrolReuseProbe` (`:1432`).
- `patrolNoPathProbe` (`:1268`): лишние `probeReach` и повтор `calculate`, затем `abortPath`, «so the node flags and
  the expanded count are those it left».
- `escapeAlt` (`OXCE_AI_ESCAPE_ALT_PROBE`, `:2129`, «read only»).
- Пути с `OXCE_AI_ATTRIB_PROBE`, `OXCE_AI_EXPOSURE_PROBE`, `OXCE_AI_PATHPROF`, `OXCE_AI_AMBUSHPROF`, `OXCE_AI_ESCAPEPROF`,
  `OXCE_AI_WALKFOVPROF`, `OXCE_AI_TRACE_DECISION`.

### 9.5. AiCandidates

`src/Battlescape/AiCandidates.cpp/.h` — список кандидатов действий для записи решения: виды MOVE, ATTACK, KNEEL, TURN,
END, RETHINK, MOVE_TO_AI_POINT, OTHER (`AiCandidates.h`). Как строится (`generate`, `AiCandidates.cpp:148`):
- враги — видимые юниту или с `getTurnsSinceSpottedByFaction <= getIntelligence()`;
- оружие — руки, особое оружие и по одной гранате каждого типа;
- атаки — snap/auto/aimed, HIT, THROW и пси, у каждой шанс `getFiringAccuracy` и проверка линии;
- дальше присед, 7 поворотов, END, RETHINK, «дальние» точки (узлы и враги) и ходы из `findReachable`.

Вызывается **только** из AiProbe (`AiProbe.cpp:668`, `:851`, `:1574`, `:1579`, `:1608`, `:2806-2856`), то есть при
`OXCE_AI_RECORD`. На решения AIModule не влияет: ни AIModule, ни BattlescapeGame его не вызывают (grep `AiCandidates::`).

### 9.6. Итог границы для бота в V4

Родное OXCE у бота: `medikit_think` (аптечка с шансом 5 % при здоровье ≥ 30 %), выбор режимов, оценки засады, эскейпа и
точки огня, реакция, `dont_think`.

Правки стенда, работающие у бота в V4:
- цель HOSTILE;
- tacticalMode (scoot / pullback / cover), повтор setupEscape при `tactical`;
- присед солдата по умолчанию, бег в эскейпе у малого юнита;
- carefulGuard (поворот к видимому врагу);
- PATROL_STUN_PREFIX, BLOCKED_STEP, STALE_PATROL_NODE / STALE_EXACT, AMBUSH_MEMO, ESCAPE_REACH_FIRST;
- WALKFOV_SKIP, LIGHTSKIP, FAST, LOADOUT_FIX (до боя).

KNOWN_OCCUPANT_PATH_V2 — только у врага. Подбора предметов у бота в V4 нет.
