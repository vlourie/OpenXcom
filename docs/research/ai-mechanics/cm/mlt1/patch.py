"""MISSION-LEVEL TACTICS: put the log-only probe into the isolated tree md/tree (a copy of D0)."""
import pathlib
import sys

S = pathlib.Path(sys.argv[1])
B = S / "md" / "tree" / "src" / "Battlescape"


def sub(path, old, new, count=1):
    text = path.read_text(encoding="utf-8")
    n = text.count(old)
    if n != count:
        raise SystemExit(f"{path.name}: {n} matches for {old[:60]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    print("ok", path.name, old[:50].replace("\n", " "))


h = B / "AiProbe.h"
sub(h, "void logState(SavedBattleGame *save, const char *when);\n",
    "void logState(SavedBattleGame *save, const char *when);\n"
    "/// MISSION-LEVEL TACTICS (GO Vitali 05.11, bench only, OXCE_AI_MISSION): [AIMISSION] lines about a base defense's task, nothing changed:\n"
    "/// the module map with each side's turn, a shot at a module, no module in the room, the walk to a target node, a tile hit, a module blasted.\n"
    "void missionState(SavedBattleGame *save, const char *when);\n"
    "void missionModuleShot(SavedBattleGame *save, BattleUnit *unit, const BattleAction &patrol);\n"
    "void missionNoModule(SavedBattleGame *save, BattleUnit *unit);\n"
    "void missionWalkTarget(SavedBattleGame *save, BattleUnit *unit, const Node *node);\n"
    "void missionTileHit(SavedBattleGame *save, BattleUnit *attacker, Position center, int part, int tileDamage);\n"
    "void missionBlastModule(SavedBattleGame *save, const Position &p);\n")

c = B / "AiProbe.cpp"
sub(c, "void logState(SavedBattleGame *, const char *) {}\n",
    "void logState(SavedBattleGame *, const char *) {}\n"
    "void missionState(SavedBattleGame *, const char *) {}\n"
    "void missionModuleShot(SavedBattleGame *, BattleUnit *, const BattleAction &) {}\n"
    "void missionNoModule(SavedBattleGame *, BattleUnit *) {}\n"
    "void missionWalkTarget(SavedBattleGame *, BattleUnit *, const Node *) {}\n"
    "void missionTileHit(SavedBattleGame *, BattleUnit *, Position, int, int) {}\n"
    "void missionBlastModule(SavedBattleGame *, const Position &) {}\n")
sub(c, "#include \"../Savegame/BattleUnit.h\"\n",
    "#include \"../Savegame/BattleUnit.h\"\n#include \"../Savegame/Base.h\"\n#include \"../Savegame/BaseFacility.h\"\n"
    "#include \"../Savegame/Node.h\"\n#include \"../Mod/MapData.h\"\n#include \"../Mod/RuleBaseFacility.h\"\n")
sub(c, "void logState(SavedBattleGame *save, const char *when)\n{\n\tif (!active())\n\t{\n\t\treturn;\n\t}\n",
    "void logState(SavedBattleGame *save, const char *when)\n{\n\tif (!active())\n\t{\n\t\treturn;\n\t}\n\tmissionState(save, when);\n")
block = (S / "md" / "mission_block.cpp").read_text(encoding="utf-8")
text = c.read_text(encoding="utf-8")
tail = "\n#endif\n\n}\n"
i = text.rfind(tail)
if i < 0:
    raise SystemExit("no tail")
text = text[:i] + "\n" + block.rstrip("\n") + "\n" + text[i:]
c.write_text(text, encoding="utf-8", newline="")
print("ok block")

a = B / "AIModule.cpp"
sub(a, "\t\t\t\t\t\t_foundBaseModuleToDestroy = _save->getMod()->getAIDestroyBaseFacilities();\n",
    "\t\t\t\t\t\t_foundBaseModuleToDestroy = _save->getMod()->getAIDestroyBaseFacilities();\n"
    "\t\t\t\t\t\tAiProbe::missionModuleShot(_save, _unit, _patrolAction);\n")
sub(a, "\t\t\t\t\t\treturn;\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t\telse\n\t\t\t{\n\t\t\t\t// find closest high value target which is not already allocated\n",
    "\t\t\t\t\t\treturn;\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t\tAiProbe::missionNoModule(_save, _unit);\n\t\t\t}\n\t\t\telse\n\t\t\t{\n\t\t\t\t// find closest high value target which is not already allocated\n")
sub(a, "\t\t\t\t\t\t\t_toNode = node;\n\t\t\t\t\t\t\tclosest = d;\n\t\t\t\t\t\t}\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\n\t\tif (_toNode == 0)\n",
    "\t\t\t\t\t\t\t_toNode = node;\n\t\t\t\t\t\t\tclosest = d;\n\t\t\t\t\t\t}\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t\tAiProbe::missionWalkTarget(_save, _unit, _toNode);\n\t\t\t}\n\t\t}\n\n\t\tif (_toNode == 0)\n")

t = B / "TileEngine.cpp"
sub(t, "\tconst int tileFinalDamage = type->getTileFinalDamage(type->getRandomDamageForTile(power, damage));\n\tif (part >= V_FLOOR && part <= V_OBJECT)\n",
    "\tconst int tileFinalDamage = type->getTileFinalDamage(type->getRandomDamageForTile(power, damage));\n"
    "\tAiProbe::missionTileHit(_save, attack.attacker, center, part, tileFinalDamage);\n\tif (part >= V_FLOOR && part <= V_OBJECT)\n")
sub(t, "\t\t\t\ttiles[i]->getMapData(currentpart)->isBaseModule())\n\t\t\t{\n",
    "\t\t\t\ttiles[i]->getMapData(currentpart)->isBaseModule())\n\t\t\t{\n\t\t\t\tAiProbe::missionBlastModule(_save, tiles[i]->getPosition());\n")
