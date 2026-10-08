/*
 * Copyright 2010-2026 OpenXcom Developers.
 *
 * This file is part of OpenXcom.
 *
 * OpenXcom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * OpenXcom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with OpenXcom.  If not, see <http://www.gnu.org/licenses/>.
 */
#include "CollapsePilot.h"
#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdlib>
#include <map>
#include <sstream>
#include <string>
#include <vector>
#include "BattlescapeGame.h"
#include "CollapseCore.h"
#include "CollapsePilotData.h"
#include "TileEngine.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Mod/MapData.h"
#include "../Mod/MapDataSet.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"

namespace OpenXcom
{

namespace
{

typedef std::chrono::steady_clock Clock;

double msSince(Clock::time_point t0)
{
	return std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
}

/// A pilot building found on this battle map: block bi of CollapsePilotData with its offset.
struct Instance
{
	int bi;
	Position off;
};

/// What was found on the current battle map; rebuilt when the battle changes.
struct State
{
	const SavedBattleGame *owner = nullptr;
	int mx = 0, my = 0, mz = 0;
	std::vector<std::vector<int> > setOf;  // [block][save map data set] -> set index in the block or -1
	std::vector<Instance> inst;
	int runs = 0;
	std::vector<int> dbgUnits, dbgItems;  // debug stand: what it placed, reported around the settle that removes
};

State st;

const TilePart PARTS[4] = { O_FLOOR, O_WESTWALL, O_NORTHWALL, O_OBJECT };

std::string upper(std::string s)
{
	for (auto &c : s)
		c = (char)std::toupper((unsigned char)c);
	return s;
}

/// Is the part's own terrain record still in its tile slot?
bool inPlace(SavedBattleGame *save, int bi, const CollapsePart &p, Position off)
{
	const Tile *t = save->getTile(off + Position(p.x, p.y, p.z));
	if (!t || !t->getMapData(PARTS[p.kind]))
		return false;
	int id, setId;
	t->getMapData(&id, &setId, PARTS[p.kind]);
	const auto &setOf = st.setOf[bi];
	return setId >= 0 && setId < (int)setOf.size() && setOf[setId] == p.set && id == p.mcd;
}

/// Parts of the building (inbox) in place; out of how many.
int countInPlace(SavedBattleGame *save, const Instance &in, int *total)
{
	const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
	int n = 0, all = 0;
	for (int i = 0; i < b.nParts; ++i)
	{
		if (!(b.parts[i].flags & CPF_INBOX)) continue;
		++all;
		if (inPlace(save, in.bi, b.parts[i], in.off)) ++n;
	}
	if (total) *total = all;
	return n;
}

/// Finds the pilot buildings: offsets voted by the rarest parts of each block. Only a whole building counts
/// (every part in place, the whole block inside the map): the model was checked on the intact template, and
/// a partial match is often another building of the same terrain. Found once per battle, kept to its end.
void scan(SavedBattleGame *save)
{
	const auto t0 = Clock::now();
	st = decltype(st)();
	st.owner = save;
	st.mx = save->getMapSizeX();
	st.my = save->getMapSizeY();
	st.mz = save->getMapSizeZ();
	const std::vector<MapDataSet*> &sets = *save->getMapDataSets();
	for (int bi = 0; bi < CollapsePilotData::blockCount; ++bi)
	{
		const CollapseBlock &b = CollapsePilotData::blocks[bi];
		std::vector<int> setOf(sets.size(), -1);
		bool any = false;
		for (size_t s = 0; s < sets.size(); ++s)
			for (int k = 0; k < b.nSets; ++k)
				if (upper(sets[s]->getName()) == b.sets[k]) { setOf[s] = k; any = true; }
		st.setOf.push_back(setOf);
		if (!any) continue;
		// the five rarest records of the building are the anchors
		std::map<std::pair<int, int>, int> freq;
		for (int i = 0; i < b.nParts; ++i)
			++freq[std::make_pair(b.parts[i].set * 1000 + b.parts[i].kind, b.parts[i].mcd)];
		std::vector<std::pair<int, int> > order;
		for (int i = 0; i < b.nParts; ++i)
			if (b.parts[i].flags & CPF_INBOX)
				order.push_back(std::make_pair(freq[std::make_pair(b.parts[i].set * 1000 + b.parts[i].kind, b.parts[i].mcd)], i));
		std::sort(order.begin(), order.end());
		std::vector<Position> cand;
		for (size_t a = 0; a < order.size() && a < 5; ++a)
		{
			const CollapsePart &p = b.parts[order[a].second];
			for (int z = 0; z < st.mz; ++z)
				for (int y = 0; y < st.my; ++y)
					for (int x = 0; x < st.mx; ++x)
					{
						const Position off(x - p.x, y - p.y, z - p.z);
						if (inPlace(save, bi, p, off) && std::find(cand.begin(), cand.end(), off) == cand.end())
							cand.push_back(off);
					}
		}
		for (const Position &off : cand)
		{
			if (off.x < 0 || off.y < 0 || off.z < 0 || off.x + b.sx > st.mx || off.y + b.sy > st.my || off.z + b.sz > st.mz)
				continue;
			Instance in = { bi, off };
			int all = 0;
			const int n = countInPlace(save, in, &all);
			if (all > 0 && n == all)
			{
				st.inst.push_back(in);
				Log(LOG_INFO) << "[COLLAPSE] found " << b.label << " (" << b.name << ") at " << off.x << "," << off.y << "," << off.z
					<< ": " << n << " of " << all << " parts in place";
			}
			else if (all > 0 && n * 2 >= all)
			{
				Log(LOG_INFO) << "[COLLAPSE] not whole " << b.label << " at " << off.x << "," << off.y << "," << off.z
					<< ": " << n << " of " << all << " parts in place - left alone";
			}
		}
	}
	Log(LOG_INFO) << "[COLLAPSE] scan: " << st.inst.size() << " pilot building(s), " << msSince(t0) << " ms";
}

/// Block-relative tiles of a debug variable: "barn:x,y,z;x,y,z|bunker:..." for this block only.
std::vector<Position> debugTiles(const char *env, const char *label)
{
	std::vector<Position> out;
	const char *s = getenv(env);
	if (!s || !*s) return out;
	std::stringstream all(s);
	std::string grp;
	while (std::getline(all, grp, '|'))
	{
		const size_t c = grp.find(':');
		if (c == std::string::npos || grp.substr(0, c) != label) continue;
		std::stringstream ts(grp.substr(c + 1));
		std::string one;
		while (std::getline(ts, one, ';'))
		{
			int x, y, z;
			char a, b;
			std::stringstream ps(one);
			if (ps >> x >> a >> y >> b >> z) out.push_back(Position(x, y, z));
		}
	}
	return out;
}

/// Debug part numbers "barn:1,2,3|bunker:4" for this block only.
std::vector<int> debugParts(const char *env, const char *label)
{
	std::vector<int> out;
	const char *s = getenv(env);
	if (!s || !*s) return out;
	std::stringstream all(s);
	std::string grp;
	while (std::getline(all, grp, '|'))
	{
		const size_t c = grp.find(':');
		if (c == std::string::npos || grp.substr(0, c) != label) continue;
		std::stringstream ps(grp.substr(c + 1));
		std::string one;
		while (std::getline(ps, one, ','))
			if (!one.empty()) out.push_back(atoi(one.c_str()));
	}
	return out;
}

/**
 * Debug stand for the pilot test (tools/collapse_pilot_run.py), all block-relative, first instance of each block:
 * OXCE_COLLAPSE_UNIT / _STUN put the player's units (in their order) on tiles before the first settle, _STUN knocks them out;
 * OXCE_COLLAPSE_DROP moves loose items from the ground there; OXCE_COLLAPSE_REMOVE takes parts away
 * (no debris) at settle number OXCE_COLLAPSE_AT (1 by default).
 */
void debugReport(SavedBattleGame *save, const char *when)
{
	for (int id : st.dbgUnits)
		for (auto *u : *save->getUnits())
			if (u->getId() == id)
			{
				const Position &p = u->getPosition();
				std::ostringstream body;
				for (auto *it : *save->getItems())
					if (it->getUnit() == u && it->getTile())
						body << " body " << it->getId() << " at " << it->getTile()->getPosition().x << "," << it->getTile()->getPosition().y << "," << it->getTile()->getPosition().z;
				Log(LOG_INFO) << "[COLLAPSE] debug: " << when << " unit " << id << " at " << p.x << "," << p.y << "," << p.z
					<< " status " << (int)u->getStatus() << body.str();
			}
	for (int id : st.dbgItems)
	{
		std::ostringstream where;
		where << " gone";
		for (auto *it : *save->getItems())
			if (it->getId() == id)
			{
				where.str("");
				if (it->getTile())
					where << " at " << it->getTile()->getPosition().x << "," << it->getTile()->getPosition().y << "," << it->getTile()->getPosition().z;
				else
					where << " carried";
			}
		Log(LOG_INFO) << "[COLLAPSE] debug: " << when << " item " << id << where.str();
	}
}

void debugStand(BattlescapeGame *battle, SavedBattleGame *save)
{
	std::vector<bool> seen(CollapsePilotData::blockCount, false);
	const char *atS = getenv("OXCE_COLLAPSE_AT");
	const int at = atS && *atS ? atoi(atS) : 1;
	size_t nextUnit = 0;
	std::vector<BattleUnit*> units;
	for (auto *u : *save->getUnits())
		if (u->getFaction() == FACTION_PLAYER && !u->isOut() && u->getArmor()->getSize() == 1)
			units.push_back(u);
	for (const Instance &in : st.inst)
	{
		if (seen[in.bi]) continue;
		seen[in.bi] = true;
		const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
		if (st.runs == 1)
		{
			for (int stun = 0; stun < 2; ++stun)
				for (const Position &p : debugTiles(stun ? "OXCE_COLLAPSE_STUN" : "OXCE_COLLAPSE_UNIT", b.label))
				{
					if (nextUnit >= units.size()) break;
					BattleUnit *u = units[nextUnit++];
					const bool ok = save->setUnitPosition(u, in.off + p);
					if (ok && stun) u->knockOut(battle);
					if (ok) st.dbgUnits.push_back(u->getId());
					Log(LOG_INFO) << "[COLLAPSE] debug: unit " << u->getId() << (stun ? " knocked out" : "") << " at " << b.label << " "
						<< p.x << "," << p.y << "," << p.z << (ok ? "" : " - place refused");
				}
			for (const Position &p : debugTiles("OXCE_COLLAPSE_DROP", b.label))
			{
				Tile *dest = save->getTile(in.off + p);
				BattleItem *pick = nullptr;
				for (auto *it : *save->getItems())
					if (it->getTile() && !it->getOwner() && !it->getUnit() && !it->getRules()->isFixed() && it->getTile() != dest)
					{
						pick = it;
						break;
					}
				if (dest && pick)
				{
					pick->getTile()->removeItem(pick);
					dest->addItem(pick, pick->getSlot());
					st.dbgItems.push_back(pick->getId());
				}
				Log(LOG_INFO) << "[COLLAPSE] debug: item " << (pick ? pick->getId() : -1) << " to " << b.label << " " << p.x << "," << p.y << "," << p.z;
			}
		}
		if (st.runs == at)
		{
			int n = 0;
			std::vector<Tile*> hit;
			for (int i : debugParts("OXCE_COLLAPSE_REMOVE", b.label))
			{
				if (i < 0 || i >= b.nParts) continue;
				const CollapsePart &p = b.parts[i];
				Tile *t = save->getTile(in.off + Position(p.x, p.y, p.z));
				if (t && inPlace(save, in.bi, p, in.off))
				{
					t->setMapData(nullptr, -1, -1, PARTS[p.kind]);
					++n;
					if (std::find(hit.begin(), hit.end(), t) == hit.end())
						hit.push_back(t);
				}
			}
			// as an explosion that took these parts would: gravity on the tile and the tile above
			for (Tile *t : hit)
			{
				save->getTileEngine()->applyGravity(t);
				if (Tile *above = save->getTile(t->getPosition() + Position(0, 0, 1)))
					save->getTileEngine()->applyGravity(above);
			}
			if (n)
			{
				Log(LOG_INFO) << "[COLLAPSE] debug: removed " << n << " part(s) of " << b.label << " at settle " << st.runs;
			}
		}
	}
}

}

namespace CollapsePilot
{

void forget()
{
	st = decltype(st)();
}

bool settle(BattlescapeGame *battle, const char *why)
{
	if (!Options::oxceCollapse)
		return false;
	SavedBattleGame *save = battle->getSave();
	const auto t0 = Clock::now();
	if (st.owner != save || st.mx != save->getMapSizeX() || st.my != save->getMapSizeY() || st.mz != save->getMapSizeZ())
		scan(save);
	if (st.inst.empty())
		return false;
	++st.runs;
	const char *atS = getenv("OXCE_COLLAPSE_AT");
	const int dbgAt = atS && *atS ? atoi(atS) : 1;
	if (st.runs == dbgAt + 1)
		debugReport(save, "next settle");
	debugStand(battle, save);
	const double scanMs = msSince(t0);
	TileEngine *te = save->getTileEngine();
	bool any = false;
	for (const Instance &in : st.inst)
	{
		const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
		std::vector<uint8_t> removed(b.nParts, 0), held;
		int nRemoved = 0;
		for (int i = 0; i < b.nParts; ++i)
			if ((b.parts[i].flags & CPF_INBOX) && !inPlace(save, in.bi, b.parts[i], in.off))
			{
				removed[i] = 1;
				++nRemoved;
			}
		const auto te0 = Clock::now();
		collapseEvaluate(b, removed, held);
		const double evalMs = msSince(te0);
		// debug stand: the exact input and output of the model, for the check against the reference (collapse_pilot_run.py)
		static const bool stand = getenv("OXCE_COLLAPSE_REMOVE") != nullptr;
		if (stand)
		{
			std::ostringstream rm, fl;
			for (int i = 0; i < b.nParts; ++i)
			{
				if (removed[i]) rm << i << ",";
				else if (!held[i] && (b.parts[i].flags & CPF_INBOX)) fl << i << ",";
			}
			Log(LOG_INFO) << "[COLLAPSE] debug: model " << b.label << " at " << in.off.x << "," << in.off.y << "," << in.off.z
				<< " removed=" << rm.str() << " fell=" << fl.str();
		}
		// remove what the model no longer holds: no debris part, as a part that fell apart
		const auto ta0 = Clock::now();
		int fell[4] = { 0, 0, 0, 0 }, outside = 0, objectives = 0, lifts = 0;
		std::vector<Tile*> tiles;
		for (int i = 0; i < b.nParts; ++i)
		{
			if (held[i] || removed[i]) continue;
			const CollapsePart &p = b.parts[i];
			if (!(p.flags & CPF_INBOX))
			{
				++outside;
				continue;
			}
			Tile *t = save->getTile(in.off + Position(p.x, p.y, p.z));
			MapData *md = t ? t->getMapData(PARTS[p.kind]) : nullptr;
			if (!md) continue;
			if (md->isGravLift())
			{
				++lifts;
				continue;
			}
			if (md->getSpecialType() == save->getObjectiveType())
			{
				save->addDestroyedObjective();
				++objectives;
			}
			t->setMapData(nullptr, -1, -1, PARTS[p.kind]);
			if (md->getExplosive())
				t->setExplosive(md->getExplosive(), md->getExplosiveType());
			++fell[p.kind];
			if (std::find(tiles.begin(), tiles.end(), t) == tiles.end())
				tiles.push_back(t);
		}
		const int nFell = fell[0] + fell[1] + fell[2] + fell[3];
		if (nFell == 0)
		{
			if (outside)
			{
				Log(LOG_INFO) << "[COLLAPSE] " << why << " " << b.label << ": nothing fell inside, " << outside << " part(s) outside the building unheld - left as they are";
			}
			continue;
		}
		any = true;
		// gravity after all the geometry, on the tiles and the tiles above (TileEngine::explode)
		for (Tile *t : tiles)
		{
			te->applyGravity(t);
			Tile *above = save->getTile(t->getPosition() + Position(0, 0, 1));
			if (above)
				te->applyGravity(above);
		}
		const double applyMs = msSince(ta0);
		// light and sight once, over the box of what fell
		const auto tl0 = Clock::now();
		Position lo = tiles.front()->getPosition(), hi = lo;
		for (Tile *t : tiles)
		{
			const Position &p = t->getPosition();
			lo = Position(std::min(lo.x, p.x), std::min(lo.y, p.y), std::min(lo.z, p.z));
			hi = Position(std::max(hi.x, p.x), std::max(hi.y, p.y), std::max(hi.z, p.z));
		}
		const Position center((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, (lo.z + hi.z) / 2);
		const int radius = std::max(hi.x - lo.x, hi.y - lo.y) / 2 + 2;
		te->calculateLighting(LL_AMBIENT, center, radius + 1, true);
		te->calculateFOV(center, radius + 1, true, true);
		Log(LOG_INFO) << "[COLLAPSE] " << why << " " << b.label << " at " << in.off.x << "," << in.off.y << "," << in.off.z
			<< ": removed " << nRemoved << ", fell " << nFell << " (f " << fell[0] << " w " << fell[1] << " n " << fell[2] << " o " << fell[3]
			<< "), outside " << outside << ", lifts " << lifts << ", objectives " << objectives << ", tiles " << tiles.size()
			<< ", falling units " << save->getFallingUnits()->size()
			<< "; scan " << scanMs << " ms, eval " << evalMs << " ms, apply " << applyMs << " ms, light+fov " << msSince(tl0) << " ms";
	}
	if (st.runs == dbgAt)
		debugReport(save, "right after");
	return any;
}

}

}
