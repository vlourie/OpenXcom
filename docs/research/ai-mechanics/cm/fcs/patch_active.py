"""FIRST CONTACT SURVIVAL V0, stage 3: the one rule on fcs/tree. OXCE_AI_FCS=2: a hostile unit that has decided to flee, whose cell and whose chosen cell both have a free line from an enemy the side has seen this turn,
goes to the cheapest reachable cell without such a line, if there is one. Same TU, same mode, the walk is still the unit's last action; no random numbers.
Byte-faithful: read as LF, written back CRLF."""
import pathlib
import sys

S = pathlib.Path(sys.argv[1])
B = S / "fcs" / "tree" / "src" / "Battlescape"


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
t = sub(t, "void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action);\n",
        "void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action);\n"
        "/// FIRST_CONTACT_SURVIVAL_V0 (OXCE_AI_FCS=2): the flight's cell, moved off the known lines of fire when there is such a cell in reach.\n"
        "void fcsEscape(SavedBattleGame *save, BattleUnit *unit, const std::vector<int> &reachable, Position &target);\n")
save(h, t)

a = B / "AIModule.cpp"
t = load(a)
t = sub(t, "\t\taction->type = _escapeAction.type;\n\t\taction->target = _escapeAction.target;\n\t\t// end this unit's turn.\n",
        "\t\taction->type = _escapeAction.type;\n\t\taction->target = _escapeAction.target;\n"
        "\t\tif (action->type == BA_WALK)\n\t\t{\n\t\t\tAiProbe::fcsEscape(_save, _unit, _reachable, action->target);\n\t\t}\n"
        "\t\t// end this unit's turn.\n")
save(a, t)

p = B / "AiProbe.cpp"
t = load(p)
t = sub(t, "void logDecision(SavedBattleGame *, BattleUnit *, const BattleAction &) {}\n",
        "void logDecision(SavedBattleGame *, BattleUnit *, const BattleAction &) {}\nvoid fcsEscape(SavedBattleGame *, BattleUnit *, const std::vector<int> &, Position &) {}\n")
rule = r'''/// FIRST_CONTACT_SURVIVAL_V0 (OXCE_AI_FCS=2): only the enemies the side has laid eyes on this turn count, from where they stand. Nothing when the unit's
/// own cell or the chosen one has no such line; else the first of the reachable cells (they are sorted by cost) with none. No random numbers, no TU, no other change.
void fcsEscape(SavedBattleGame *save, BattleUnit *unit, const std::vector<int> &reachable, Position &target)
{
	static const int mode = (int)param("OXCE_AI_FCS", 0);
	if (mode != 2 || unit->getFaction() != FACTION_HOSTILE || save->getSide() != FACTION_HOSTILE)
	{
		return;
	}
	std::vector<BattleUnit *> known;
	for (auto *bu : *save->getUnits())
	{
		if (!bu->isOut() && bu->getFaction() == FACTION_PLAYER && bu->getTurnsSinceSpottedByFaction(FACTION_HOSTILE) == 0)
		{
			known.push_back(bu);
		}
	}
	TileEngine *te = save->getTileEngine();
	const Position at = unit->getPosition();
	const auto lines = [&](const Position &pos)
	{
		Tile *tile = save->getTile(pos);
		int n = 0;
		for (auto *e : known)
		{
			Position origin = te->getSightOriginVoxel(e);
			origin.z -= 2;
			Position scan;
			if (tile && (pos == at ? te->canTargetUnit(&origin, tile, &scan, e, false) : te->freeLine(origin, tile, e, unit)))
			{
				++n;
			}
		}
		return n;
	};
	const int here = lines(at);
	const int there = target == at ? here : lines(target);
	if (here == 0 || there == 0)
	{
		return;
	}
	int checked = 0;
	for (int index : reachable)
	{
		const Position pos = save->getTileCoords(index);
		Tile *tile = save->getTile(pos);
		if (pos == at || !tile || tile->getFire() || tile->getDangerous())
		{
			continue;
		}
		++checked;
		if (lines(pos) == 0)
		{
			Log(LOG_INFO) << "[FCSACT] turn=" << save->getTurn() << " unit=" << unit->getId() << " tu=" << unit->getTimeUnits() << " from=" << at << " dest=" << target
				<< " here=" << here << " there=" << there << " known=" << known.size() << " new=" << pos << " checked=" << checked;
			target = pos;
			return;
		}
	}
	Log(LOG_INFO) << "[FCSACT] turn=" << save->getTurn() << " unit=" << unit->getId() << " tu=" << unit->getTimeUnits() << " from=" << at << " dest=" << target
		<< " here=" << here << " there=" << there << " known=" << known.size() << " new=- checked=" << checked;
}

/// FIRST_CONTACT_SURVIVAL_V0 (OXCE_AI_FCS): 1 - shadow, one [FCSLOS] line per hostile decision of turn 1.'''
t = sub(t, "/// FIRST_CONTACT_SURVIVAL_V0 (OXCE_AI_FCS): 1 - shadow, one [FCSLOS] line per hostile decision of turn 1.", rule)
save(p, t)
