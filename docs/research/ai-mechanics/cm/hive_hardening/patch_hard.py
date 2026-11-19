"""HIVE hardening: the new hooks in the isolated tree hive/tree. Each replace must find its place exactly once. Usage: patch_hard.py <tree>"""
import sys
from pathlib import Path

tree = Path(sys.argv[1])


def patch(rel, old, new):
    p = tree / rel
    raw = p.read_bytes()
    crlf = b"\r\n" in raw
    bom = raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8-sig" if bom else "utf-8").replace("\r\n", "\n")
    if t.count(old) != 1:
        sys.exit(f"{rel}: found {t.count(old)} times: {old[:60]!r}")
    t = t.replace(old, new)
    if crlf:
        t = t.replace("\n", "\r\n")
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + t.encode("utf-8"))
    print("patched", rel)


# the battle is set up: the organization before anyone's turn
patch("src/Battlescape/BattlescapeGame.cpp",
      "\tcheckForCasualties(nullptr, BattleActionAttack{ }, true);\n\tcancelCurrentAction();\n}\n",
      "\tcheckForCasualties(nullptr, BattleActionAttack{ }, true);\n\tcancelCurrentAction();\n\tHiveCommand::battleStarts(_save);\n}\n")

# the battle save: one more key, read if it is there
patch("src/Savegame/SavedBattleGame.cpp",
      '#include "../Engine/Language.h"\n',
      '#include "../Engine/Language.h"\n#include "../Battlescape/HiveCommand.h"\n')
patch("src/Savegame/SavedBattleGame.cpp",
      "SavedBattleGame::~SavedBattleGame()\n{\n",
      "SavedBattleGame::~SavedBattleGame()\n{\n\tHiveCommand::forget(this);\n")
patch("src/Savegame/SavedBattleGame.cpp",
      "\t_scriptValues.load(reader, _rule->getScriptGlobal());\n\n\t// Sanity checks\n",
      "\t_scriptValues.load(reader, _rule->getScriptGlobal());\n\tstd::string hive;\n\tconst bool hasHive = reader.tryRead(\"hive\", hive);\n\tHiveCommand::loaded(this, hasHive ? &hive : nullptr);\n\n\t// Sanity checks\n")
patch("src/Savegame/SavedBattleGame.cpp",
      "\t_scriptValues.save(writer, _rule->getScriptGlobal());\n}\n",
      "\t_scriptValues.save(writer, _rule->getScriptGlobal());\n\tstd::string hive;\n\tif (HiveCommand::saveText(this, hive))\n\t{\n\t\twriter.write(\"hive\", hive);\n\t}\n}\n")

# the walkable field of a unit, on the caller's arrays
patch("src/Battlescape/Pathfinding.h",
      "\t/// EXACT_STALE_REACH_V1 (bench): leave the state calculate(unit, ..., BAM_NORMAL) and abortPath() would, when witnessReach\n",
      "\t/// HIVE COMMAND (bench, passive): the time units to each tile the unit can walk to under the cap (-1: not reached), by the step costs of\n"
      "\t/// calculate(unit, ..., BAM_NORMAL), on the caller's arrays: none of the pathfinder's state is touched. Returns the tiles reached; capped says the cap dropped one.\n"
      "\tint hiveFlood(const BattleUnit *unit, int cap, std::vector<int> &cost, std::vector<int> &prev, bool &capped);\n"
      "\t/// EXACT_STALE_REACH_V1 (bench): leave the state calculate(unit, ..., BAM_NORMAL) and abortPath() would, when witnessReach\n")
patch("src/Battlescape/Pathfinding.cpp",
      "/**\n * EXACT_STALE_REACH_V1 (bench, AIModule::setupPatrol's STALE check): the state calculate(unit, ..., BAM_NORMAL) and abortPath()\n",
      """/**
 * HIVE COMMAND (bench, passive): see the header. A step refused or too dear is the same step calculate would meet; what the unit may not
 * know of does not block it here either, as getTUCost asks the same isBlocked.
 */
int Pathfinding::hiveFlood(const BattleUnit *unit, int cap, std::vector<int> &cost, std::vector<int> &prev, bool &capped)
{
	const int hits = _knownOccupantHits;
	cost.assign(_nodes.size(), -1);
	prev.assign(_nodes.size(), -1);
	capped = false;
	typedef std::pair<int, int> Item; // cost, tile index
	std::priority_queue<Item, std::vector<Item>, std::greater<Item>> open;
	const int startIdx = _save->getTileIndex(unit->getPosition());
	cost[startIdx] = 0;
	open.push({0, startIdx});
	int tiles = 0;
	while (!open.empty())
	{
		const Item top = open.top();
		open.pop();
		if (top.first != cost[top.second])
		{
			continue;
		}
		++tiles;
		const Position pos = _nodes[top.second].getPosition();
		for (int direction = 0; direction < 10; direction++)
		{
			PathfindingStep r = getTUCost(pos, direction, unit, 0, BAM_NORMAL);
			if (r.cost.time == INVALID_MOVE_COST)
				continue;
			const int t = top.first + r.cost.time + r.penalty.time;
			if (t > cap)
			{
				capped = true;
				continue;
			}
			const int j = _save->getTileIndex(r.pos);
			if (cost[j] < 0 || t < cost[j])
			{
				cost[j] = t;
				prev[j] = top.second;
				open.push({t, j});
			}
		}
	}
	_knownOccupantHits = hits;
	return tiles;
}

/**
 * EXACT_STALE_REACH_V1 (bench, AIModule::setupPatrol's STALE check): the state calculate(unit, ..., BAM_NORMAL) and abortPath()
""")

# the stand: the battle saved the game's own way at the start of a player's turn, and it goes on
patch("src/Battlescape/AiProbe.cpp",
      "\t\t// Stage 0B: OXCE_AI_FIXTURE_TURN=<t> - the battle at the start of the player's turn t, saved to OXCE_AI_PROBE_SAVE\n",
      """		// HIVE hardening: OXCE_AI_HIVE_SAVE_TURN=<t> - the battle saved the game's own way at the player's turn t, to hive_<t>.asav; it goes on
		static const int hiveSaveTurn = [] { const char *s = getenv("OXCE_AI_HIVE_SAVE_TURN"); return s ? atoi(s) : 0; }();
		static bool hiveSaved = false;
		if (hiveSaveTurn > 0 && !hiveSaved && save->getSide() == FACTION_PLAYER && save->getTurn() == hiveSaveTurn
			&& !state->getBattleGame()->isBusy() && state->allowButtons())
		{
			hiveSaved = true;
			const std::string saveAs = "hive_" + std::to_string(hiveSaveTurn) + ".asav";
			state->getGame()->getSavedGame()->save(saveAs, state->getGame()->getMod());
			Log(LOG_INFO) << "[AIPROBE] hive saved: " << saveAs;
		}
		// Stage 0B: OXCE_AI_FIXTURE_TURN=<t> - the battle at the start of the player's turn t, saved to OXCE_AI_PROBE_SAVE
""")
