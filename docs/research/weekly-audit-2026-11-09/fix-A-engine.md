# Fix A: движок, безопасность (аудит 09.11, находки 5 и 12)

## Правка 1: HdWorkers (коммит 10b1c413b)
src/Engine/HdWorkers.cpp: runJob() оборачивает fn(i) в try/catch (std::exception и ...), пишет Log(LOG_ERROR) "HD render: job i failed". Вызывается из takeJobs (пул и вызывающий поток) и из ветки run без пула. Кадр дорисовывается без полосы.

## Правка 2: накопительный лимит Lua на ход
- LuaSandbox::Limits::turnInstructions = 50 * instructions = 100 000 000.
- LuaSandbox: _turnSteps, прибавляется один раз при выходе из runProtected (fire/callKept/callHeld), хук не менялся; resetTurnBudget(). Превышение: _disabled, сообщение через _onError и журнал. main.lua/setup в накопитель не входят (идут через begin(), не через runProtected).
- LuaHost::resetTurnBudgets() сбрасывает все песочницы. Вызовы: SavedBattleGame::newTurnUpdateScripts (начало хода любой стороны и начало боя), BattlescapeGenerator (перед BATTLE_START), DebriefingState (перед BATTLE_END), GeoscapeState (перед NEW_DAY, смена дня). Вызовы стоят за getLuaHost().
- Вызываются явно в местах, а не в fireOutputs: fire() не доходит до fireOutputs, если у события нет обработчиков, и сброса не было бы.
- Тест: tools/lua_sandbox_test.cpp, два новых случая; прогон lua_sandbox_test.ps1: PASS 83, FAIL 0.
- Не делалось: игру не запускали, проверка боем и геоскейпом - в финальном прогоне пачки.
