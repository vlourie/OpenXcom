"""MISSION_DIRECTOR_V0: on the probe's tree md/tree - the block replaced by the director's, the two new entry points, the hooks in setupPatrol.
Byte-faithful: read as LF, written back CRLF."""
import pathlib
import sys

S = pathlib.Path(sys.argv[1])
B = S / "md" / "tree" / "src" / "Battlescape"


def load(p):
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n")


def save(p, text):
    p.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))


def sub(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f"{text.count(old)} matches for {old[:70]!r}")
    print("ok", old[:50].replace("\n", " "))
    return text.replace(old, new)


h = B / "AiProbe.h"
t = load(h)
t = sub(t, "void missionState(SavedBattleGame *save, const char *when);\n",
        "void missionState(SavedBattleGame *save, const char *when);\n"
        "/// MISSION_DIRECTOR_V0 (OXCE_AI_MDIR, 2 - on), before the unit's choice in setupPatrol: the group's order drops a node kept from an earlier think; then\n"
        "/// its order: 1 - shoot the module `tile`, 2 - walk to `node`, 0 - none, the engine's protocol goes on.\n"
        "bool missionRedirect(SavedBattleGame *save, BattleUnit *unit, const Node *toNode);\n"
        "int missionOrder(SavedBattleGame *save, BattleUnit *unit, Node *&node, Position &tile);\n")
save(h, t)

c = B / "AiProbe.cpp"
t = load(c)
t = sub(t, "void missionState(SavedBattleGame *, const char *) {}\n",
        "void missionState(SavedBattleGame *, const char *) {}\n"
        "bool missionRedirect(SavedBattleGame *, BattleUnit *, const Node *) { return false; }\n"
        "int missionOrder(SavedBattleGame *, BattleUnit *, Node *&, Position &) { return 0; }\n")
start = t.index("\nnamespace\n{\n\n/// MISSION-LEVEL TACTICS (OXCE_AI_MDIR)")
tail = "\n#endif\n\n}\n"
end = t.rfind(tail)
block = (S / "md" / "mission_block.cpp").read_text(encoding="utf-8").replace("\r\n", "\n")
t = t[:start] + "\n" + block.lstrip("\n").rstrip("\n") + "\n" + t[end:]
save(c, t)
print("ok block")

a = B / "AIModule.cpp"
t = load(a)
t = sub(t, "\tint triesLeft = 5;\n\t// PATROL_REUSE_PROBE (bench, passive): the node stored in an earlier think is kept without a new search\n",
        "\t// MISSION_DIRECTOR_V0 (bench, OXCE_AI_MDIR): the group's order comes before a node kept from an earlier think\n"
        "\tif (_toNode != 0 && AiProbe::missionRedirect(_save, _unit, _toNode))\n\t{\n\t\tfreePatrolTarget();\n\t\t_toNode = 0;\n\t}\n"
        "\tint triesLeft = 5;\n\t// PATROL_REUSE_PROBE (bench, passive): the node stored in an earlier think is kept without a new search\n")
t = sub(t, "\t\t\t// can i shoot an object?\n\t\t\tif ((!oxceFixes || _fromNode) && _fromNode->isTarget() &&\n",
        "\t\t\t// MISSION_DIRECTOR_V0 (bench, OXCE_AI_MDIR): the order of the side's shared plan, in the protocol's own shot and walk\n"
        "\t\t\tNode *orderNode = nullptr;\n\t\t\tPosition orderTile;\n"
        "\t\t\tconst int order = AiProbe::missionOrder(_save, _unit, orderNode, orderTile);\n"
        "\t\t\tif (order == 1 && _save->canUseWeapon(_attackAction.weapon, _unit, false, BA_SNAPSHOT))\n\t\t\t{\n"
        "\t\t\t\t_patrolAction.actor = _unit;\n\t\t\t\t_patrolAction.target = orderTile;\n\t\t\t\t_patrolAction.weapon = _attackAction.weapon;\n"
        "\t\t\t\t_patrolAction.type = BA_SNAPSHOT;\n\t\t\t\t_patrolAction.updateTU();\n"
        "\t\t\t\t_foundBaseModuleToDestroy = _save->getMod()->getAIDestroyBaseFacilities();\n\t\t\t\treturn;\n\t\t\t}\n"
        "\t\t\tif (order == 2)\n\t\t\t{\n\t\t\t\t_toNode = orderNode;\n\t\t\t}\n"
        "\t\t\t// can i shoot an object?\n\t\t\telse if ((!oxceFixes || _fromNode) && _fromNode->isTarget() &&\n")
save(a, t)
