"""FIRST CONTACT SURVIVAL, stage 2: the probe corrected. canTargetUnit gives "no line" for almost any tile where the unit does not stand (a free line has an empty trajectory), so the probe's cells were all "safe".
TileEngine::freeLine: the same scan of the body's place, a line that arrives unhit counts. fcsProbe prints both verdicts: safeOld (the AI's own answer) and safe (the line itself). Turn 1 only. Changes nothing in the game.
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


h = B / "TileEngine.h"
t = load(h)
t = sub(t, "\tbool canTargetUnit(Position *originVoxel, Tile *tile, Position *scanVoxel, BattleUnit *excludeUnit, bool rememberObstacles, BattleUnit *potentialUnit = 0);\n",
        "\tbool canTargetUnit(Position *originVoxel, Tile *tile, Position *scanVoxel, BattleUnit *excludeUnit, bool rememberObstacles, BattleUnit *potentialUnit = 0);\n"
        "\t/// FIRST_CONTACT_SURVIVAL_V0: would a line reach the place of the unit's body on this tile unhit? Pure read, no random numbers.\n"
        "\tbool freeLine(const Position &originVoxel, Tile *tile, BattleUnit *excludeUnit, BattleUnit *body);\n")
save(h, t)

c = B / "TileEngine.cpp"
t = load(c)
t = sub(t, "/**\n * Checks for a tile part available for targeting and what particular voxel.\n",
        r'''/**
 * FIRST_CONTACT_SURVIVAL_V0: the scan of canTargetUnit for a unit that does not stand on the tile: a line that reaches the place of its body unhit.
 */
bool TileEngine::freeLine(const Position &originVoxel, Tile *tile, BattleUnit *excludeUnit, BattleUnit *body)
{
	Position targetVoxel = tile->getPosition().toVoxel() + Position(8, 8, 0);
	const int minHeight = targetVoxel.z - tile->getTerrainLevel() + body->getFloatHeight();
	int heightRange = body->getHeight();
	const int centerHeight = minHeight + heightRange / 2;
	heightRange = std::max(0, std::min(10, heightRange / 2));
	const int unitRadius = body->getArmor()->getSize() > 1 ? 3 : body->getLoftemps();
	const Position relPos = targetVoxel - originVoxel;
	const float len = sqrt((float)(relPos.x * relPos.x + relPos.y * relPos.y));
	const float normal = len > 0 ? unitRadius / len : 0;
	const int relX = floor(((float)relPos.y) * normal + 0.5);
	const int relY = floor(((float)-relPos.x) * normal + 0.5);
	const int sliceTargets[] = {0,0, relX,relY, -relX,-relY, relY,-relX, -relY,relX};
	std::vector<Position> trajectory;
	for (int i = 0; i <= heightRange; ++i)
	{
		for (int j = 0; j < 5; ++j)
		{
			if (i < (heightRange - 1) && j > 2) break;
			Position scan(targetVoxel.x + sliceTargets[j * 2], targetVoxel.y + sliceTargets[j * 2 + 1], centerHeight + heightFromCenter[i]);
			trajectory.clear();
			if (calculateLineVoxel(originVoxel, scan, false, &trajectory, excludeUnit) == V_EMPTY)
			{
				return true;
			}
		}
	}
	return false;
}

/**
 * Checks for a tile part available for targeting and what particular voxel.
''')
save(c, t)

p = B / "AiProbe.cpp"
t = load(p)
t = sub(t, "/// FIRST_CONTACT_SURVIVAL_V0 (OXCE_AI_FCS): 1 - shadow, one [FCSLOS] line per hostile decision of turns 1-2. Only the enemies the side has\n"
           '/// laid eyes on this turn count; a cell is "safe" when none of them has a line of fire to it from where it stands now. Reads, changes nothing.\n',
        "/// FIRST_CONTACT_SURVIVAL_V0 (OXCE_AI_FCS): 1 - shadow, one [FCSLOS] line per hostile decision of turn 1. Only the enemies the side has\n"
        '/// laid eyes on this turn count; a cell is "safe" when none of them has a line of fire to it from where it stands now. safeOld - the same\n'
        "/// by canTargetUnit's answer for a unit not on the tile, the one the AI's own getSpottingUnits gets. Reads, changes nothing.\n")
t = sub(t, "save->getSide() != FACTION_HOSTILE || save->getTurn() > 2)\n", "save->getSide() != FACTION_HOSTILE || save->getTurn() > 1)\n")
t = sub(t, '''	const auto lines = [&](const Position &pos, std::ostringstream *who)
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
''', '''	const auto lines = [&](const Position &pos, std::ostringstream *who, bool old)
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
			if (pos == at ? te->canTargetUnit(&origin, tile, &scan, e, false)
				: old ? te->canTargetUnit(&origin, tile, &scan, e, false, unit) : te->freeLine(origin, tile, e, unit))
			{
				++n;
''')
t = sub(t, "\tlines(at, &now);\n\tlines(action.target, &dest);\n", "\tlines(at, &now, false);\n\tlines(action.target, &dest, false);\n")
t = sub(t, "\tint cells = 0;\n\tif (pending.unit == unit->getId() && !pending.wantReach)\n", "\tint cells = 0, safeOld = 0;\n\tif (pending.unit == unit->getId() && !pending.wantReach)\n")
t = sub(t, "\t\t\t\tif (lines(m.tile, nullptr) == 0)\n", "\t\t\t\tsafeOld += lines(m.tile, nullptr, true) == 0 ? 1 : 0;\n\t\t\t\tif (lines(m.tile, nullptr, false) == 0)\n")
t = sub(t, '<< " cells=" << cells << " safe=" << safe.size() << " best="', '<< " cells=" << cells << " safeOld=" << safeOld << " safe=" << safe.size() << " best="')
save(p, t)
