"""FIRST CONTACT SURVIVAL, stage 2: the shadow probe on the isolated copy fcs/tree of the D0 tree. OXCE_AI_FCS=1 prints one [FCSLOS] line per hostile decision of the first two turns:
which enemies known to the side this turn have a line of fire to the unit's cell and to the chosen cell, how many of the reachable cells have none, and the cheapest of them. It changes nothing.
Byte-faithful: read as LF, written back CRLF."""
import pathlib
import sys

S = pathlib.Path(sys.argv[1])
P = S / "fcs" / "tree" / "src" / "Battlescape" / "AiProbe.cpp"


def sub(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f"{text.count(old)} matches for {old[:70]!r}")
    print("ok", old[:50].replace("\n", " "))
    return text.replace(old, new)


t = P.read_bytes().decode("utf-8").replace("\r\n", "\n")
t = sub(t, '"OXCE_AI_BUILD", "OXCE_AI_KEEP_DECIDE", ', '"OXCE_AI_BUILD", "OXCE_AI_KEEP_DECIDE", "OXCE_AI_FCS", ')
t = sub(t, "\t\treachFallback(save, unit);\n\t\twriteRecord(save, unit, action, hashUnits, hashItems, hashOrder, hashMap, hashRng);\n",
        "\t\treachFallback(save, unit);\n\t\tfcsProbe(save, unit, action);\n\t\twriteRecord(save, unit, action, hashUnits, hashItems, hashOrder, hashMap, hashRng);\n")
probe = r'''/// FIRST_CONTACT_SURVIVAL_V0 (OXCE_AI_FCS): 1 - shadow, one [FCSLOS] line per hostile decision of turns 1-2. Only the enemies the side has
/// laid eyes on this turn count; a cell is "safe" when none of them has a line of fire to it from where it stands now. Reads, changes nothing.
void fcsProbe(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	static const int mode = (int)param("OXCE_AI_FCS", 0);
	if (mode != 1 || unit->getFaction() != FACTION_HOSTILE || save->getSide() != FACTION_HOSTILE || save->getTurn() > 2)
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
	const auto lines = [&](const Position &pos, std::ostringstream *who)
	{
		Tile *tile = save->getTile(pos);
		int n = 0;
		if (!tile)
		{
			return n;
		}
		for (auto *e : known)
		{
			Position origin = te->getSightOriginVoxel(e);
			origin.z -= 2;
			Position scan;
			if (te->canTargetUnit(&origin, tile, &scan, e, false, pos != at ? unit : nullptr))
			{
				++n;
				if (!who)
				{
					break;
				}
				*who << (who->tellp() > 0 ? "," : "") << e->getId();
			}
		}
		return n;
	};
	std::ostringstream now, dest, best;
	lines(at, &now);
	lines(action.target, &dest);
	std::vector<std::pair<int, Position> > safe;
	int cells = 0;
	if (pending.unit == unit->getId() && !pending.wantReach)
	{
		for (const auto &m : pending.set.moves)
		{
			if (m.kind == AiCandidates::MOVE && m.tu >= 0)
			{
				++cells;
				if (lines(m.tile, nullptr) == 0)
				{
					safe.push_back(std::make_pair(m.tu, m.tile));
				}
			}
		}
	}
	std::stable_sort(safe.begin(), safe.end(), [](const std::pair<int, Position> &a, const std::pair<int, Position> &b) { return a.first < b.first; });
	for (size_t i = 0; i < safe.size() && i < 8; ++i)
	{
		best << (i ? ";" : "") << safe[i].second.x << "." << safe[i].second.y << "." << safe[i].second.z << ":" << safe[i].first;
	}
	Log(LOG_INFO) << "[FCSLOS] turn=" << save->getTurn() << " unit=" << unit->getId() << " n=" << action.number
		<< " tu=" << unit->getTimeUnits() << " act=" << (int)action.type << " known=" << known.size()
		<< " now=" << (now.tellp() > 0 ? now.str() : std::string("-")) << " dest=" << (dest.tellp() > 0 ? dest.str() : std::string("-"))
		<< " cells=" << cells << " safe=" << safe.size() << " best=" << (safe.empty() ? std::string("-") : best.str());
}

void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (!active())
'''
t = sub(t, "void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)\n{\n\tif (!active())\n", probe)
P.write_bytes(t.replace("\n", "\r\n").encode("utf-8"))
