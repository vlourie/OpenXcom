"""MISSION_DIRECTOR STAGE 2: on the copy md2/tree of md/tree - the block replaced, the entry points, the hooks in setupPatrol, the terrain-only line in canTargetTile,
the base's state after the battle. Byte-faithful: read as LF, written back CRLF."""
import pathlib
import sys

S = pathlib.Path(sys.argv[1])
B = S / "md2" / "tree" / "src" / "Battlescape"


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
t = sub(t, "int missionOrder(SavedBattleGame *save, BattleUnit *unit, Node *&node, Position &tile);\n",
        "int missionOrder(SavedBattleGame *save, BattleUnit *unit, Position &tile);\n"
        "/// After the battle's last line: the steps of the debriefing on the real base, its state before and after.\n"
        "void missionDebrief(SavedBattleGame *save);\n")
t = sub(t, "/// its order: 1 - shoot the module `tile`, 2 - walk to `node`, 0 - none, the engine's protocol goes on.\n",
        "/// its order: 1 - shoot the module `tile`, 2 - walk to the firing position `tile`, 0 - none, the engine's protocol goes on.\n")
save(h, t)

c = B / "AiProbe.cpp"
t = load(c)
t = sub(t, "int missionOrder(SavedBattleGame *, BattleUnit *, Node *&, Position &) { return 0; }\n",
        "int missionOrder(SavedBattleGame *, BattleUnit *, Position &) { return 0; }\n"
        "void missionDebrief(SavedBattleGame *) {}\n")
start = t.index("\nnamespace\n{\n\n/// MISSION_DIRECTOR_V0 (OXCE_AI_MDIR)")
tail = "\n#endif\n\n}\n"
end = t.rfind(tail)
block = (S / "md2" / "mission_block.cpp").read_text(encoding="utf-8").replace("\r\n", "\n")
t = t[:start] + "\n" + block.lstrip("\n").rstrip("\n") + "\n" + t[end:]
t = sub(t, "\t\t<< \" ms=\" << (SDL_GetTicks() - startTicks) << \" vms=\" << (Timer::probeTicks - startVirtual);\n",
        "\t\t<< \" ms=\" << (SDL_GetTicks() - startTicks) << \" vms=\" << (Timer::probeTicks - startVirtual);\n"
        "\tmissionDebrief(save);\n")
save(c, t)
print("ok block")

a = B / "AIModule.cpp"
t = load(a)
t = sub(t, "\t\t\tNode *orderNode = nullptr;\n\t\t\tPosition orderTile;\n"
        "\t\t\tconst int order = AiProbe::missionOrder(_save, _unit, orderNode, orderTile);\n",
        "\t\t\tPosition orderTile;\n"
        "\t\t\tconst int order = AiProbe::missionOrder(_save, _unit, orderTile);\n")
t = sub(t, "\t\t\t\t_patrolAction.type = BA_SNAPSHOT;\n\t\t\t\t_patrolAction.updateTU();\n"
        "\t\t\t\t_foundBaseModuleToDestroy = _save->getMod()->getAIDestroyBaseFacilities();\n\t\t\t\treturn;\n\t\t\t}\n"
        "\t\t\tif (order == 2)\n\t\t\t{\n\t\t\t\t_toNode = orderNode;\n\t\t\t}\n"
        "\t\t\t// can i shoot an object?\n\t\t\telse if (",
        "\t\t\t\t_patrolAction.type = BA_SNAPSHOT;\n\t\t\t\t_patrolAction.updateTU();\n"
        "\t\t\t\tif (!_patrolAction.haveTU())\n\t\t\t\t{\n\t\t\t\t\t_patrolAction.type = BA_RETHINK;\n\t\t\t\t}\n"
        "\t\t\t\t_foundBaseModuleToDestroy = true;\n\t\t\t\treturn;\n\t\t\t}\n"
        "\t\t\tif (order == 2)\n\t\t\t{\n"
        "\t\t\t\t_patrolAction.actor = _unit;\n\t\t\t\t_patrolAction.target = orderTile;\n\t\t\t\t_patrolAction.type = BA_WALK;\n"
        "\t\t\t\t_foundBaseModuleToDestroy = true;\n\t\t\t\treturn;\n\t\t\t}\n"
        "\t\t\t// can i shoot an object?\n\t\t\tif (")
save(a, t)

th = B / "TileEngine.h"
t = load(th)
t = sub(t, "bool canTargetTile(Position *originVoxel, Tile *tile, int part, Position *scanVoxel, BattleUnit *excludeUnit, bool rememberObstacles);",
        "bool canTargetTile(Position *originVoxel, Tile *tile, int part, Position *scanVoxel, BattleUnit *excludeUnit, bool rememberObstacles, BattleUnit *excludeAllBut = 0);")
save(th, t)

tc = B / "TileEngine.cpp"
t = load(tc)
t = sub(t, "bool TileEngine::canTargetTile(Position *originVoxel, Tile *tile, int part, Position *scanVoxel, BattleUnit *excludeUnit, bool rememberObstacles)\n",
        "bool TileEngine::canTargetTile(Position *originVoxel, Tile *tile, int part, Position *scanVoxel, BattleUnit *excludeUnit, bool rememberObstacles, BattleUnit *excludeAllBut)\n")
# the scan of canTargetTile only: its own test line, the one right after the spiral's x and y
old = ("\t\t\tscanVoxel->y = targetVoxel.y + spiralArray[i*2+1];\n\t\t\t_trajectory.clear();\n"
       "\t\t\tint test = calculateLineVoxel(*originVoxel, *scanVoxel, false, &_trajectory, excludeUnit);\n")
t = sub(t, old, old.replace("&_trajectory, excludeUnit);", "&_trajectory, excludeUnit, excludeAllBut);"))
save(tc, t)
