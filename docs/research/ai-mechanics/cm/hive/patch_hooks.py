"""HIVE COMMAND CORE V0: the four hooks and the file list in the isolated tree hive/tree (a copy of the D0 tree). Each replace must find its place exactly once. Usage: patch_hooks.py <tree>"""
import sys
from pathlib import Path

tree = Path(sys.argv[1])


def patch(rel, old, new):
    p = tree / rel
    raw = p.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8")
    bom = raw.startswith(b"\xef\xbb\xbf")
    t = text.replace("\r\n", "\n")
    if t.count(old) != 1:
        sys.exit(f"{rel}: found {t.count(old)} times: {old[:60]!r}")
    t = t.replace(old, new)
    if crlf:
        t = t.replace("\n", "\r\n")
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + t.encode("utf-8"))
    print("patched", rel)


patch("src/CMakeLists.txt", "  Battlescape/CollapsePilotData.cpp\n", "  Battlescape/CollapsePilotData.cpp\n  Battlescape/HiveCommand.cpp\n")
patch("src/Battlescape/AIModule.cpp", '#include "AiProbe.h"\n#include "KnowledgeArmor.h"\n', '#include "AiProbe.h"\n#include "HiveCommand.h"\n#include "KnowledgeArmor.h"\n')
patch("src/Battlescape/AIModule.cpp", "\tint triesLeft = 5;\n\t// PATROL_REUSE_PROBE (bench, passive)", """	// HIVE COMMAND CORE V0 (bench): the order of this unit's squad in place of the free choice of a node. Reached only as the
	// patrol's plan: what the unit does is still chosen by its own think below. A hold ends its selection as patrol.spent does
	Node *hiveNode = 0;
	const HiveCommand::PatrolOrder hiveOrder = HiveCommand::patrol(_save, _unit, hiveNode);
	if (hiveOrder == HiveCommand::PO_HOLD)
	{
		freePatrolTarget();
		_toNode = 0;
		_patrolAction.type = BA_NONE;
		return;
	}
	if (hiveOrder == HiveCommand::PO_GO && hiveNode != _toNode)
	{
		freePatrolTarget();
		_toNode = hiveNode;
		_toNodeTurn = _save->getTurn();
	}
	int triesLeft = 5;
	// PATROL_REUSE_PROBE (bench, passive)""")
patch("src/Battlescape/BattlescapeGame.cpp", '#include "../fmath.h"\n', '#include "../fmath.h"\n#include "HiveCommand.h"\n')
patch("src/Battlescape/BattlescapeGame.cpp", "\tAiProbe::beforeThink(_save, unit);\n", "\tAiProbe::beforeThink(_save, unit);\n\tHiveCommand::beforeThink(_save, unit);\n")
patch("src/Battlescape/BattlescapeGame.cpp", "\tAiProbe::logDecision(_save, unit, action);\n\tAiProbe::blockedStepDecide(_save, unit);\n", "\tAiProbe::logDecision(_save, unit, action);\n\tHiveCommand::decided(_save, unit, action);\n\tAiProbe::blockedStepDecide(_save, unit);\n")
patch("src/Battlescape/BattlescapeGame.cpp", "\tAiProbe::sideEnds(_save);\n\t_debugPlay =", "\tAiProbe::sideEnds(_save);\n\tHiveCommand::sideEnds(_save);\n\t_debugPlay =")
