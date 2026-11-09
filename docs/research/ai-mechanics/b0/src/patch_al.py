"""Stage 0B stand switches in the isolated tree (DEV section of AiProbe.cpp only):
OXCE_AI_RELEASE_BASE=1 - the clean1 gates O1-O4, O6, O7-O14, O5 follow the release formula (BetterAI && Fixes);
OXCE_AI_FIXTURE_TURN=T - the bot run saves OXCE_AI_PROBE_SAVE at the start of player turn T and quits."""
import sys
from pathlib import Path

p = Path(sys.argv[1])
t = p.read_bytes().decode("utf-8")
assert "\r\n" in t
t = t.replace("\r\n", "\n")

def rep(old, new, count=1):
    global t
    n = t.count(old)
    assert n == count, (old[:60], n)
    t = t.replace(old, new)

rep("""bool active()
{
	static const bool on = harness() || play();
	return on;
}
""", """bool active()
{
	static const bool on = harness() || play();
	return on;
}

/// Stage 0B: OXCE_AI_RELEASE_BASE=1 - the fixes the release gates by BetterAI follow the release formula, not the bench's own
bool releaseBase()
{
	static const bool on = harness() && rawOn("OXCE_AI_RELEASE_BASE");
	return on;
}

bool releaseFixes()
{
	return Options::oxceBetterAi && Options::oxceBetterAiFixes;
}
""")
for name in ("counterFix", "astarCostFix", "escapeSignFix", "staleEscapeFix", "upstreamSpot", "upstreamVis"):
    i = t.index("\nbool " + name + "()\n{\n\tstatic const bool on = active();")
    j = t.index("active();", i)
    t = t[:j] + "releaseBase() ? releaseFixes() : active();" + t[j + len("active();"):]
rep("""	static const bool on = play() || (harness() && envOn("OXCE_AI_OXCE_FIXES"));""",
    """	static const bool on = releaseBase() ? releaseFixes() : play() || (harness() && envOn("OXCE_AI_OXCE_FIXES"));""")
rep("""	static const bool on = active() && envOn("OXCE_AI_STALE_PATROL_NODE");""",
    """	static const bool on = releaseBase() ? releaseFixes() : active() && envOn("OXCE_AI_STALE_PATROL_NODE");""")
rep("""	static const int mode = [] { const int m = stalePatrolNode() ? (int)param("OXCE_AI_STALE_EXACT", 0) : 0; return m >= 0 && m <= 3 ? m : 0; }();""",
    """	static const int mode = [] { const int m = stalePatrolNode() ? (releaseBase() ? 1 : (int)param("OXCE_AI_STALE_EXACT", 0)) : 0; return m >= 0 && m <= 3 ? m : 0; }();""")
rep("""		if (save->getSide() == FACTION_PLAYER && playerStartLogged != save->getTurn() && save->getTurn() > 1)
		{
			playerStartLogged = save->getTurn();
			logState(save, "pstart");
		}
""", """		if (save->getSide() == FACTION_PLAYER && playerStartLogged != save->getTurn() && save->getTurn() > 1)
		{
			playerStartLogged = save->getTurn();
			logState(save, "pstart");
		}
		// Stage 0B: OXCE_AI_FIXTURE_TURN=<t> - the battle at the start of the player's turn t, saved to OXCE_AI_PROBE_SAVE
		static const int fixtureTurn = [] { const char *s = getenv("OXCE_AI_FIXTURE_TURN"); return s ? atoi(s) : 0; }();
		if (fixtureTurn > 0 && save->getSide() == FACTION_PLAYER && save->getTurn() == fixtureTurn
			&& !state->getBattleGame()->isBusy() && state->allowButtons())
		{
			const char *saveAs = getenv("OXCE_AI_PROBE_SAVE");
			if (saveAs && *saveAs)
			{
				state->getGame()->getSavedGame()->save(saveAs, state->getGame()->getMod());
			}
			logResult(save, "fixture");
			phase = FINISHED;
			state->getGame()->quit();
			return;
		}
""")
p.write_bytes(t.replace("\n", "\r\n").encode("utf-8"))
print("patched", p)
