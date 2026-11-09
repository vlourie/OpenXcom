"""P0 vs P1 (GO Vitali 27.10, REAL AI COMPARISON), isolated tree only: under OXCE_AI_RELEASE_BASE the fixes inside the AI's
own decisions (O1 escapeSign, O3 counter, O4 staleEscape, O5 stalePatrolNode/staleExact, O7-O14 oxceFixes) follow the release
formula for the AI sides and stay off on the bot's (player's) turn: the bot stands in for the player, whom BetterAI never
changes. The engine ones (O2 astarCost - Pathfinding, O6 upstreamSpot/Vis - TileEngine/Pathfinding/UI) stay the formula for
everybody, as in the game. Without the bot (one AI turn, stage 0B) nothing changes."""
import sys
from pathlib import Path

p = Path(sys.argv[1])
t = p.read_bytes().decode("utf-8")
assert "\r\n" in t
t = t.replace("\r\n", "\n")


def rep(old, new, count=1):
    global t
    n = t.count(old)
    assert n == count, (old[:70], n)
    t = t.replace(old, new)


rep("""bool releaseFixes()
{
	return Options::oxceBetterAi && Options::oxceBetterAiFixes;
}
""", """bool releaseFixes()
{
	return Options::oxceBetterAi && Options::oxceBetterAiFixes;
}

/// P0 vs P1: the battle the frame hook last saw (think), for releaseAi
static const SavedBattleGame *releaseSave = nullptr;

/// P0 vs P1: under RELEASE_BASE the fixes inside the AI's own decisions follow the release formula for the AI sides only; on
/// the bot's turn (it plays the player's side, which BetterAI never changes) they stay off. The engine ones stay releaseFixes
bool releaseAi()
{
	return releaseFixes() && !(bot() && releaseSave && releaseSave->getSide() == FACTION_PLAYER);
}
""")

rep("""void think(BattlescapeState *state, SavedBattleGame *save)
{
	if (!active() || phase == FINISHED)""", """void think(BattlescapeState *state, SavedBattleGame *save)
{
	releaseSave = save;
	if (!active() || phase == FINISHED)""")

for old_tail in ("active(); // clean1: P0-C always in the bench",
                 "active(); // clean1: U2 always in the bench",
                 "active(); // clean1: U3-A and U3-B always in the bench",
                 "play() || (harness() && envOn(\"OXCE_AI_OXCE_FIXES\"));",
                 "active() && envOn(\"OXCE_AI_STALE_PATROL_NODE\");"):
    rep(f"""	static const bool on = releaseBase() ? releaseFixes() : {old_tail}
	return on;""", f"""	static const bool on = {old_tail}
	return releaseBase() ? releaseAi() : on;""")

rep("""	static const int mode = [] { const int m = stalePatrolNode() ? (releaseBase() ? 1 : (int)param("OXCE_AI_STALE_EXACT", 0)) : 0; return m >= 0 && m <= 3 ? m : 0; }();
	return mode;""", """	static const int mode = [] { const int m = releaseBase() ? (releaseFixes() ? 1 : 0) : stalePatrolNode() ? (int)param("OXCE_AI_STALE_EXACT", 0) : 0; return m >= 0 && m <= 3 ? m : 0; }();
	return releaseBase() && !releaseAi() ? 0 : mode;""")

p.write_bytes(t.replace("\n", "\r\n").encode("utf-8"))
print("patched", p)
