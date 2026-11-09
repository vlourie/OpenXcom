"""AI FORGE WP1: forgeHash out of the anonymous namespace it landed in: before battleOver, in AiProbe proper. In the tree and in apply_monitor.py, so a re-apply gives the same. args: tree"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
p = Path(sys.argv[1]) / "src/Battlescape/AiProbe.cpp"
b = p.read_bytes().decode("utf-8", errors="surrogateescape").replace("\r\n", "\n")
FN = '''/// AI FORGE WP1: what the stand itself holds between decisions and the next decision can read.
unsigned long long forgeHash()
{
	unsigned long long h = 1469598103934665603ULL;
	for (long long v : { counterUnit, counterTurn, counterSide, passStartTurn, passStartSide, passStartIdx, panicTurn, panicSide, panicValue,
		turnsPlayed, turnAtEnd, aiStartLogged, playerStartLogged, postWalkMeleeUnit })
	{
		h = (h ^ (unsigned long long)v) * 1099511628211ULL;
	}
	return h;
}

'''
assert b.count(FN) == 1
b = b.replace(FN, "")
T = "void battleOver(BattlescapeState *state, SavedBattleGame *save, bool abort)\n{\n	if (!active() || phase == FINISHED)"
assert b.count(T) == 1
b = b.replace(T, FN + T)
p.write_bytes(b.replace("\n", "\r\n").encode("utf-8", errors="surrogateescape"))
a = HERE / "apply_monitor.py"
s = a.read_text(encoding="utf-8")
OLD = """sub(P, '''void logResult(SavedBattleGame *save, const char *how)
{
	SchedulerIntegrityMonitor::finish(save, how);
''', '''""" + FN + """void logResult(SavedBattleGame *save, const char *how)
{
	SchedulerIntegrityMonitor::finish(save, how);
''')
"""
assert s.count(OLD) == 1
NEW = """sub(P, '''void battleOver(BattlescapeState *state, SavedBattleGame *save, bool abort)
{
	if (!active() || phase == FINISHED)''', '''""" + FN + """void battleOver(BattlescapeState *state, SavedBattleGame *save, bool abort)
{
	if (!active() || phase == FINISHED)''')
"""
a.write_text(s.replace(OLD, NEW), encoding="utf-8")
print("moved")
