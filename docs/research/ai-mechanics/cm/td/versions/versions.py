"""AI_TACTICAL_DIRECTOR_V1: the four tested versions as sources. Starts from td/tree (v4, the last tested) and undoes the
session's edits step by step (v4 -> v3 -> v2 -> v1), each replacement exactly once; writes AIModule.v<k>.cpp/.h and the diffs
against D0 (td_v<k>.diff) and between versions (td_v<k-1>_v<k>.diff).

  py -3.13 -I versions.py <td dir> <out dir>"""
import difflib
import sys
from pathlib import Path

TD, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
rd = lambda p: p.read_text(encoding="utf-8")
cpp4 = rd(TD / "tree/src/Battlescape/AIModule.cpp")
h = rd(TD / "tree/src/Battlescape/AIModule.h")
d0c, d0h = rd(TD / "../ce/AIModule.d0.cpp"), rd(TD / "../ce/AIModule.d0.h")

# v4 -> v3: the cover role back to the farthest member; no 'stuck'
V4_V3 = [
    ("""		// roles: attack now if two or more can (a strike); otherwise a lone attacker may take its own attack, the rest close in
		// out of sight and, with three or more, the one nearest the target that cannot shoot it now covers them (the ground
		// they cross must be within its sight)
		const int gi = (int)td.groups.size();
		int far = -1;
		if (!g.strike && pool.size() >= 3)
		{
			int best = INT_MAX;
			for (size_t k = 0; k < pool.size(); ++k)
			{
				const int d = Position::distanceSq(pool[k]->bu->getPosition(), target.pos);
				if (!pool[k]->now[i] && d < best)""",
     """		// roles: attack now if two or more can (a strike); otherwise a lone attacker may take its own attack, the rest close in
		// out of sight and, with three or more, the one farthest back covers them
		const int gi = (int)td.groups.size();
		int far = -1;
		if (!g.strike && pool.size() >= 3)
		{
			int best = -1;
			for (size_t k = 0; k < pool.size(); ++k)
			{
				const int d = Position::distanceSq(pool[k]->bu->getPosition(), target.pos);
				if (!pool[k]->now[i] && d > best)"""),
    ("""	std::map<int, Position> parked;   // unit -> the tile it covers or waits on in this turn (held there when it thinks again)
	std::map<int, Position> walked;   // unit -> where it stood when the director last sent it walking in this turn
""", """	std::map<int, Position> parked;   // unit -> the tile it covers or waits on in this turn (held there when it thinks again)
"""),
    ("""	td.parked.clear();
	td.walked.clear();
""", """	td.parked.clear();
"""),
    ("""
	// the director's last walk did not move it (the way was blocked): no more walks of its in this turn (a shot still goes)
	auto was = td.walked.find(_unit->getId());
	const bool stuck = was != td.walked.end() && was->second == _unit->getPosition();""", ""),
    ("""			say(order, "shot");
			return;
		}
		if (stuck)
		{
			say("FREE", "stuck");
			return;
		}""", """			say(order, "shot");
			return;
		}"""),
    ("""	if (stuck)
	{
		say("FREE", "stuck");
		return;
	}
	// cover:""", """	// cover:"""),
    ("""		td.walked[_unit->getId()] = _unit->getPosition();
""", ""),
]
# v3 -> v2: no HOLD
V3_V2 = [
    ("""	std::map<int, Position> parked;   // unit -> the tile it covers or waits on in this turn (held there when it thinks again)
""", ""),
    ("""	td.parked.clear();
""", ""),
    ("""	const bool joined = !g.attacked.empty();
	// it covers or waits where it was put in this turn: it stays (the engine thinks for it again in the second pass); not an
	// order - the loop guard does not count it. A member that closes in still joins once its group has attacked; a tile a
	// contact would see now is no longer held.
	auto park = td.parked.find(_unit->getId());
	if (park != td.parked.end() && park->second == _unit->getPosition() && !(joined && (role == 'M' || role == 'a'))
		&& !tdMask(_save, _unit->getPosition()))
	{
		action->type = BA_NONE;
		if (role == 'S')
			_AIMode = AI_AMBUSH;
		_reserve = BA_NONE;
		_unit->setCharging(0);
		say("HOLD", role == 'S' ? "cover" : "wait");
		return;
	}
""", ""),
    ("""	if (role == 'A' || (joined && (role == 'M' || role == 'a')))""",
     """	const bool joined = !g.attacked.empty();
	if (role == 'A' || (joined && (role == 'M' || role == 'a')))"""),
    ("""			td.parked[_unit->getId()] = best;
""", ""),
    ("""		td.parked[_unit->getId()] = _unit->getPosition();
""", ""),
]
# v2 -> v1: 'now' and the firing point by the terrain masks, no tdFire
V2_V1 = [
    ("""	std::map<long long, char> fire;   // (tile, contact, shooter height) -> a line of fire from there to the contact
""", ""),
    ("""	td.fire.clear();
""", ""),
    ("""/// Could the shooter fire at contact i from the tile: the engine's own test of findFirePoint (canTargetUnit from the weapon's
/// height on that tile to the contact where the side knows it), cached per plan by tile, contact and the shooter's height.
bool tdFire(SavedBattleGame *save, BattleUnit *shooter, Position t, size_t i)
{
	const TdContact &c = td.memory[td.contacts[i]];
	const int height = shooter->getHeight() + shooter->getFloatHeight();
	const long long key = ((long long)save->getTileIndex(t) * 32 + (long long)i) * 256 + height;
	auto it = td.fire.find(key);
	if (it != td.fire.end())
		return it->second != 0;
	Tile *tile = save->getTile(t), *at = save->getTile(c.pos);
	bool ok = false;
	if (tile && at)
	{
		Position origin = t.toVoxel() + Position(8, 8, height - tile->getTerrainLevel() - 4);
		Position scan;
		ok = save->getTileEngine()->canTargetUnit(&origin, at, &scan, shooter, false, at->getUnit() == c.unit ? 0 : c.unit);
	}
	td.fire[key] = ok ? 1 : 0;
	return ok;
}

""", ""),
    ("""		// now: the engine's line of fire from the tile; within two turns: the contact would see the tile (the masks)
		auto scan = [&](const std::vector<int> &tiles, std::vector<char> &out, bool fire)
		{
			for (int idx : tiles)
			{
				const Position t = save->getTileCoords(idx);
				for (size_t i = 0; i < n; ++i)
				{
					if (!out[i] && !rule->isOutOfRange(Position::distanceSq(t, td.memory[td.contacts[i]].pos))
						&& (fire ? tdFire(save, bu, t, i) : (tdMask(save, t) & (1u << i)) != 0))
						out[i] = 1;
				}
			}
		};
		if (shot.Time > 0 && bu->getTimeUnits() >= shot.Time)
		{
			scan(save->getPathfinding()->findReachable(bu, shot), c.now, true);
		}""", """		auto scan = [&](const std::vector<int> &tiles, std::vector<char> &out)
		{
			for (int idx : tiles)
			{
				const Position t = save->getTileCoords(idx);
				for (size_t i = 0; i < n; ++i)
				{
					if (!out[i] && !rule->isOutOfRange(Position::distanceSq(t, td.memory[td.contacts[i]].pos))
						&& (tdMask(save, t) & (1u << i)))
						out[i] = 1;
				}
			}
		};
		if (shot.Time > 0 && bu->getTimeUnits() >= shot.Time)
		{
			scan(save->getPathfinding()->findReachable(bu, shot), c.now);
		}"""),
    ("""		scan(save->getPathfinding()->findReachable(bu, two), c.near, false);""",
     """		scan(save->getPathfinding()->findReachable(bu, two), c.near);"""),
    ("""		// a point it reaches with a shot's time units left with the engine's line of fire to the target, in the weapon's range;
		// the fewest other contacts that would see it, then the nearest""",
     """		// a point it reaches with a shot's time units left that the target would see (a line both ways), in the weapon's range;
		// the fewest other contacts on it, then the nearest"""),
    ("""				if (!tdFire(_save, _unit, t, (size_t)bit))
					continue;
				const unsigned m = tdMask(_save, t);""",
     """				const unsigned m = tdMask(_save, t);
				if (!(m & (1u << bit)))
					continue;"""),
]


def undo(src, steps, name):
    for old, new in steps:
        n = src.count(old)
        if n != 1:
            raise SystemExit(f"{name}: a replacement matches {n} times: {old[:80]!r}")
        src = src.replace(old, new)
    return src


def diff(a, b, na, nb):
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), na, nb))


cpp3 = undo(cpp4, V4_V3, "v4->v3")
cpp2 = undo(cpp3, V3_V2, "v3->v2")
cpp1 = undo(cpp2, V2_V1, "v2->v1")
vers = {1: cpp1, 2: cpp2, 3: cpp3, 4: cpp4}
for k, src in vers.items():
    (OUT / f"AIModule.v{k}.cpp").write_text(src, encoding="utf-8", newline="")
    (OUT / f"td_v{k}.diff").write_text(diff(d0c, src, "D0/AIModule.cpp", f"v{k}/AIModule.cpp")
                                       + diff(d0h, h, "D0/AIModule.h", f"v{k}/AIModule.h"), encoding="utf-8", newline="")
    if k > 1:
        (OUT / f"td_v{k - 1}_v{k}.diff").write_text(diff(vers[k - 1], src, f"v{k - 1}/AIModule.cpp", f"v{k}/AIModule.cpp"),
                                                    encoding="utf-8", newline="")
(OUT / "AIModule.h").write_text(h, encoding="utf-8", newline="")
for k in range(1, 5):
    print(f"v{k}: {len(vers[k].splitlines())} lines; tdFire {'tdFire(' in vers[k]}; HOLD {'\"HOLD\"' in vers[k]}; "
          f"stuck {'\"stuck\"' in vers[k]}; S nearest {'d < best' in vers[k]}")
