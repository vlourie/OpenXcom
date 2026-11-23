"""STRIKE-V0: put the prototype into the isolated tree sv/tree (a copy of D0)."""
import pathlib
import sys

S = pathlib.Path(sys.argv[1])
B = S / "sv" / "tree" / "src" / "Battlescape"


def sub(path, old, new, count=1):
    text = path.read_text(encoding="utf-8")
    n = text.count(old)
    if n != count:
        raise SystemExit(f"{path.name}: {n} matches for {old[:60]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="")
    print("ok", path.name, old[:50].replace("\n", " "))


h = B / "AiProbe.h"
sub(h, "void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action);\n",
    "void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action);\n"
    "/// TACTICAL AI 2.0 STRIKE-V0 (GO Vitali 30.10, bench only, OXCE_AI_STRIKE): the hostile unit's TU before its think.\n"
    "void strikeBeforeThink(BattleUnit *unit);\n"
    "/// STRIKE-V0: after the unit has thought - the side's known targets and legal useful shots (SideContext), one shared order\n"
    "/// at the target most units can usefully shoot (StrikeCoordinator), and, in place of a patrol walk or an end of action, the\n"
    "/// order's shot checked again just before it is handed out (OrderExecutor). Every check is an [AISTRIKE] line; 1 - shadow\n"
    "/// (nothing changed), 2 - on.\n"
    "void strikeDecide(SavedBattleGame *save, BattleUnit *unit, BattleAction &action);\n")

c = B / "AiProbe.cpp"
sub(c, "void logDecision(SavedBattleGame *, BattleUnit *, const BattleAction &) {}\n",
    "void logDecision(SavedBattleGame *, BattleUnit *, const BattleAction &) {}\n"
    "void strikeBeforeThink(BattleUnit *) {}\n"
    "void strikeDecide(SavedBattleGame *, BattleUnit *, BattleAction &) {}\n")
sub(c, "void beforeThink(SavedBattleGame *save, BattleUnit *unit)\n{\n\tthinkSave = save;\n",
    "void beforeThink(SavedBattleGame *save, BattleUnit *unit)\n{\n\tthinkSave = save;\n\tstrikeBeforeThink(unit);\n")
block = (S / "sv" / "strike_block.cpp").read_text(encoding="utf-8")
text = c.read_text(encoding="utf-8")
tail = "\n#endif\n\n}\n"
i = text.rfind(tail)
if i < 0:
    raise SystemExit("no tail")
text = text[:i] + "\n" + block.rstrip("\n") + "\n" + text[i:]
c.write_text(text, encoding="utf-8", newline="")
print("ok block")

g = B / "BattlescapeGame.cpp"
sub(g, "\tAiProbe::logDecision(_save, unit, action);\n\tAiProbe::blockedStepDecide(_save, unit);\n",
    "\t// TACTICAL AI 2.0 STRIKE-V0 (bench, OXCE_AI_STRIKE): the side's shared order may stand in for a patrol walk or an end\n"
    "\tAiProbe::strikeDecide(_save, unit, action);\n"
    "\tAiProbe::logDecision(_save, unit, action);\n\tAiProbe::blockedStepDecide(_save, unit);\n")
