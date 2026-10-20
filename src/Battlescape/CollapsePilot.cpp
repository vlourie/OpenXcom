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
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <map>
#include <sstream>
#include <string>
#include <vector>
#include <set>
#include <unordered_map>
#include <unordered_set>
#include "BattlescapeGame.h"
#include "BattlescapeState.h"
#include "CollapseCore.h"
#include "CollapsePilotData.h"
#include "Camera.h"
#include "Map.h"
#include "TileEngine.h"
#include "../Engine/Game.h"
#include "../Engine/HdFx.h"
#include "../Engine/Language.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Mod/MapData.h"
#include "../Mod/MapDataSet.h"
#include "../Mod/Mod.h"
#include "../Mod/Unit.h"
#include "../Mod/RuleDamageType.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
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
	std::vector<std::pair<int, int> > dbgCarry;  // debug stand: (unit, item) the placed units carried when placed
	bool fallReported = false;
	bool fallPending = false;  // debug stand: report and save again once the state stack drains (idle)
	bool rubbleReady = false;
	std::vector<std::vector<std::pair<int, int> > > rubble;  // [row of RUBBLE * 3 + kind]: (save set index, record)
	std::map<std::pair<int, int>, int> rubbleKind;  // (save set index, record) of the rubble -> its kind
	std::set<std::pair<int, int> > rubbleOrDead;  // the rubble and what it turns into
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

/// Format of the building list in the battle save (SavedBattleGame "collapsePilot"):
/// 1 - model name and offset, 2 - plus the fingerprint of the model data (sig).
const int FORMAT = 2;

struct Fnv
{
	uint64_t h = 1469598103934665603ULL;
	void add(const void *p, size_t n)
	{
		const unsigned char *c = (const unsigned char*)p;
		for (size_t i = 0; i < n; ++i)
		{
			h ^= c[i];
			h *= 1099511628211ULL;
		}
	}
	void add(int v) { add(&v, sizeof(v)); }
	void add(const char *s) { add(s, strlen(s) + 1); }
};

/// Fingerprint of the model data of block bi: a save made with other data of the same name is not this model.
std::string modelSig(int bi)
{
	const CollapseBlock &b = CollapsePilotData::blocks[bi];
	Fnv f;
	f.add(b.name);
	for (int v : { b.sx, b.sy, b.sz, b.x0, b.x1, b.y0, b.y1, b.nSets, b.nParts })
		f.add(v);
	for (int k = 0; k < b.nSets; ++k)
		f.add(b.sets[k]);
	int nTargets = 0;
	for (int i = 0; i < b.nParts; ++i)
	{
		const CollapsePart &p = b.parts[i];
		for (int v : { p.kind, p.x, p.y, p.z, p.set, p.mcd, p.flags, p.contact, p.limL, p.nEdge, p.e0x, p.e0y, p.e1x, p.e1y, p.mark, p.tOff, p.tCount })
			f.add(v);
		nTargets = std::max(nTargets, p.tOff + p.tCount);
	}
	for (int i = 0; i < nTargets; ++i)
		f.add(b.targets[i]);
	std::ostringstream s;
	s << std::hex;
	s.width(16);
	s.fill('0');
	s << f.h;
	return s.str();
}

/// The rubble of a collapse (docs/research/building-collapse-rubble-2026-10-20.md): low walkable debris of the
/// terrain's own sets. The building's terrain is told by the first of the keys among its sets (a battle map may hold
/// several terrains). What fell gives the kind, by the material of its dust (HdFx::partMaterial): stone (and the
/// rest), wood (and furniture: its footstep is soft) or metal; a kind the terrain has no record of takes stone, then
/// wood, then metal.
enum RubbleKind { RK_STONE, RK_WOOD, RK_METAL, RK_KINDS };
struct RubbleRow
{
	const char *key;
	const char *kind[RK_KINDS];
};
const RubbleRow RUBBLE[] = {
	{ "URBANWAR", { "URBANWAR:50 URBANWAR:57", "MADDECOR:80 MADDECOR:83 MADDECOR:84", "" } },
	{ "URBAN", { "URBAN:50 URBAN:57", "URBAN:87 URBAN:88 MADDECOR:80 MADDECOR:83 MADDECOR:84", "" } },
	{ "COMMERCE", { "COMMERCE:50 COMMERCE:57", "COMDECOR:68 COMDECOR:69", "" } },
	{ "MILBARR", { "MILTECHDIO:26", "", "MILBARR:48 MILBARR:49" } },
	{ "VILBAN", { "", "VILBAN:87 VILBAN:88", "" } },
	{ "IDT_FARM", { "", "URBAN_GOODS:24 URBAN_GOODS:25", "" } },
	{ "URBAN40K", { "URBAN40K:57", "", "" } },
	{ "BARN_JUNK", { "", "FRNITURE:7 CULTIVAT:11", "" } },
	{ "BARN", { "", "CULTIVAT:11", "" } },
};
const int RUBBLE_ROWS = sizeof(RUBBLE) / sizeof(RUBBLE[0]);

/// The kind of rubble a fallen part gives.
int rubbleKind(const MapData *md)
{
	const std::string m = HdFx::partMaterial(md);
	return m == "wood" || m == "soft" ? RK_WOOD : m == "metal" ? RK_METAL : RK_STONE;
}

/// The rubble records of this battle, found once by the set names (a set the battle lacks gives none).
void rubbleOf(SavedBattleGame *save)
{
	if (st.rubbleReady)
		return;
	st.rubbleReady = true;
	st.rubble.assign(RUBBLE_ROWS * RK_KINDS, std::vector<std::pair<int, int> >());
	const std::vector<MapDataSet*> &sets = *save->getMapDataSets();
	auto setIndex = [&sets](const std::string &name) {
		for (size_t i = 0; i < sets.size(); ++i)
			if (upper(sets[i]->getName()) == name) return (int)i;
		return -1;
	};
	for (int r = 0; r < RUBBLE_ROWS; ++r)
	{
		std::ostringstream found;
		size_t any = 0;
		for (int k = 0; k < RK_KINDS; ++k)
		{
			std::istringstream in(RUBBLE[r].kind[k]);
			std::string rec;
			while (in >> rec)
			{
				const size_t colon = rec.find(':');
				const int s = setIndex(rec.substr(0, colon)), id = std::atoi(rec.c_str() + colon + 1);
				if (s < 0 || id < 0 || id >= (int)sets[s]->getSize()) continue;
				st.rubble[r * RK_KINDS + k].push_back(std::make_pair(s, id));
				st.rubbleKind[std::make_pair(s, id)] = k;
				// what the rubble turns into when it is shot or burnt is the collapse's too (foreignParts)
				for (int dead = id; dead > 0 && dead < (int)sets[s]->getSize() && st.rubbleOrDead.insert(std::make_pair(s, dead)).second; )
					dead = sets[s]->getObject(dead)->getDieMCD();
			}
			found << " " << st.rubble[r * RK_KINDS + k].size();
			any += st.rubble[r * RK_KINDS + k].size();
		}
		if (any)
		{
			Log(LOG_INFO) << "[COLLAPSE] rubble of " << RUBBLE[r].key << " (stone wood metal):" << found.str();
		}
	}
}

/// The row of RUBBLE for the building of block bi, or -1.
int rubbleRow(int bi)
{
	const CollapseBlock &b = CollapsePilotData::blocks[bi];
	for (int r = 0; r < RUBBLE_ROWS; ++r)
		for (int s = 0; s < b.nSets; ++s)
			if (upper(b.sets[s]) == RUBBLE[r].key) return r;
	return -1;
}

/// Is the tile's record in the slot rubble (or, with `orDead`, what rubble turns into)?
bool isRubble(SavedBattleGame *save, const Tile *t, TilePart part, bool orDead)
{
	rubbleOf(save);
	int id, setId;
	t->getMapData(&id, &setId, part);
	return orDead ? st.rubbleOrDead.count(std::make_pair(setId, id)) > 0 : st.rubbleKind.count(std::make_pair(setId, id)) > 0;
}

/// A part that fell in settle, for the rubble: where it stood, was it a floor, its kind of rubble.
struct Drop
{
	Position cell;
	bool floor;
	int kind;
};

/// What became of the rubble of one settle.
struct RubbleCount
{
	int laid = 0, merged = 0, unit = 0, object = 0, floor = 0, none = 0, again = 0;
};

/// Lays the rubble of what fell: one record on the floor each part comes down to (the way TileEngine::applyGravity
/// takes items down), of the kind most of what came there was (stone on a tie), the record of its kind by the cell
/// (no random numbers). None where a unit stands or will land, where an object still stands, on a lift or on no floor
/// of its own. The tiles it lies on join `tiles` (gravity, light and sight).
void lay(SavedBattleGame *save, int bi, const std::vector<Drop> &drops, std::vector<Tile*> &tiles, RubbleCount &n)
{
	rubbleOf(save);
	static const std::vector<std::pair<int, int> > nothing;
	const int row = rubbleRow(bi);
	const std::vector<std::pair<int, int> > *list[RK_KINDS] = { &nothing, &nothing, &nothing };
	for (int k = 0; row >= 0 && k < RK_KINDS; ++k)
		list[k] = &st.rubble[row * RK_KINDS + k];
	struct Heap
	{
		Tile *tile;
		int top;
		int kinds[RK_KINDS];
	};
	std::vector<Heap> heaps;
	for (const Drop &d : drops)
	{
		Tile *t = save->getTile(Position(d.cell.x, d.cell.y, std::max(0, d.floor ? d.cell.z - 1 : d.cell.z)));
		while (t && t->getPosition().z > 0 && t->hasNoFloor(save))
			t = save->getBelowTile(t);
		if (!t) continue;
		auto h = std::find_if(heaps.begin(), heaps.end(), [t](const Heap &x) { return x.tile == t; });
		if (h == heaps.end())
		{
			heaps.push_back(Heap{ t, d.cell.z, { 0, 0, 0 } });
			h = heaps.end() - 1;
		}
		else
			++n.merged;
		h->top = std::max<int>(h->top, d.cell.z);
		++h->kinds[d.kind];
	}
	const std::vector<MapDataSet*> &sets = *save->getMapDataSets();
	for (const Heap &h : heaps)
	{
		const Position at = h.tile->getPosition();
		bool unit = false;
		for (int z = at.z; z <= h.top && !unit; ++z)
		{
			const Tile *c = save->getTile(Position(at.x, at.y, z));
			unit = c && c->getUnit();
		}
		const MapData *floor = h.tile->getMapData(O_FLOOR);
		int kind = RK_STONE;
		for (int k = 1; k < RK_KINDS; ++k)
			if (h.kinds[k] > h.kinds[kind]) kind = k;
		for (int k = 0; list[kind]->empty() && k < RK_KINDS; ++k)
			kind = k;
		if (unit) ++n.unit;
		else if (h.tile->getMapData(O_OBJECT)) ++n.object;
		else if ((at.z > 0 && !floor) || (floor && floor->isGravLift())) ++n.floor;
		else if (list[kind]->empty()) ++n.none;
		else
		{
			const auto &rec = (*list[kind])[(at.x * 7 + at.y * 13 + at.z * 5) % list[kind]->size()];
			h.tile->setMapData(sets[rec.first]->getObject(rec.second), rec.second, rec.first, O_OBJECT);
			++n.laid;
			if (std::find(tiles.begin(), tiles.end(), h.tile) == tiles.end())
				tiles.push_back(h.tile);
		}
	}
}

/**
 * Records in the building's place that the building could not have left there: a record of another terrain,
 * or of its own terrain that no part of the template on that tile turns into. A part turns into its die record
 * when destroyed (Tile::destroy, into the slot of the die record) and into its alt record when a door opens
 * (Tile::openDoor, slot of the alt record), along the whole chain; a lost floor at map level 0 becomes
 * scorched earth. Checked are the building's cells (west walls one column east, north walls one row south)
 * on every level of the block. This tells a key moved onto other buildings and onto ground with other records
 * (grass, fences, rocks of the farm); a key moved where the cells hold no records at all (the air above the
 * ground) or onto another copy of the same building passes.
 */
int foreignParts(SavedBattleGame *save, const Instance &in)
{
	const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
	const std::vector<MapDataSet*> &sets = *save->getMapDataSets();
	const auto &setOf = st.setOf[in.bi];
	std::vector<MapDataSet*> modelSet(b.nSets, nullptr);
	for (size_t s = 0; s < setOf.size(); ++s)
		if (setOf[s] >= 0) modelSet[setOf[s]] = sets[s];
	const int w = b.x1 - b.x0 + 2, d = b.y1 - b.y0 + 2;
	auto cell = [&](int x, int y, int z) { return (z * d + (y - b.y0)) * w + (x - b.x0); };
	std::vector<std::set<std::pair<int, int> > > allowed(w * d * b.sz);
	for (int i = 0; i < b.nParts + b.nKeep; ++i)
	{
		const CollapsePart &p = i < b.nParts ? b.parts[i] : b.keep[i - b.nParts];
		if (p.x < b.x0 || p.x > b.x1 + 1 || p.y < b.y0 || p.y > b.y1 + 1) continue;
		auto &ok = allowed[cell(p.x, p.y, p.z)];
		MapDataSet *ds = modelSet[p.set];
		std::vector<int> todo(1, p.mcd);
		while (!todo.empty())
		{
			const int id = todo.back();
			todo.pop_back();
			if (!ok.insert(std::make_pair(p.set, id)).second || !ds || id < 0 || id >= (int)ds->getSize()) continue;
			MapData *md = ds->getObject(id);
			if (md->getDieMCD()) todo.push_back(md->getDieMCD());
			if (md->getAltMCD()) todo.push_back(md->getAltMCD());
		}
	}
	int foreign = 0;
	for (int z = 0; z < b.sz; ++z)
		for (int y = b.y0; y <= b.y1 + 1; ++y)
			for (int x = b.x0; x <= b.x1 + 1; ++x)
			{
				// the column east and the row south of the building: only its own west and north walls, and only
				// inside the block - past the block's edge they are the next block's cells
				const bool east = x > b.x1, south = y > b.y1;
				if ((east && (south || x >= b.sx)) || (south && y >= b.sy)) continue;
				Tile *t = save->getTile(in.off + Position(x, y, z));
				if (!t) continue;
				for (TilePart part : PARTS)
				{
					if ((east && part != O_WESTWALL) || (south && part != O_NORTHWALL)) continue;
					MapData *md = t->getMapData(part);
					if (!md) continue;
					if (part == O_FLOOR && t->getPosition().z == 0 && md == MapDataSet::getScorchedEarthTile()) continue;
					// the rubble of an earlier collapse (and what it turned into) may lie anywhere in the building
					if (isRubble(save, t, part, true)) continue;
					int id, setId;
					t->getMapData(&id, &setId, part);
					const int k = setId >= 0 && setId < (int)setOf.size() ? setOf[setId] : -1;
					if (k < 0 || !allowed[cell(x, y, z)].count(std::make_pair(k, id))) ++foreign;
				}
			}
	return foreign;
}

/// Hash of every terrain record of the map: the debug stand compares what direct destruction left before the model.
std::string terrainHash(SavedBattleGame *save)
{
	Fnv f;
	const int n = save->getMapSizeXYZ();
	for (int i = 0; i < n; ++i)
	{
		Tile *t = save->getTile(i);
		for (TilePart part : PARTS)
		{
			int id = -1, setId = -1;
			if (t->getMapData(part)) t->getMapData(&id, &setId, part);
			f.add(id);
			f.add(setId);
		}
	}
	std::ostringstream s;
	s << std::hex << f.h;
	return s.str();
}

/// Is a debug stand variable set (tools/collapse_pilot_run.py, collapse_pilot2_run.py)?
bool standEnv()
{
	static const bool on = getenv("OXCE_COLLAPSE_REMOVE") || getenv("OXCE_COLLAPSE_HIT") || getenv("OXCE_COLLAPSE_FIRE")
		|| getenv("OXCE_COLLAPSE_BLAST") || getenv("OXCE_COLLAPSE_MODEL") || getenv("OXCE_COLLAPSE_UNIT") || getenv("OXCE_COLLAPSE_STUN")
		|| getenv("OXCE_COLLAPSE_BIG") || getenv("OXCE_COLLAPSE_FLY") || getenv("OXCE_COLLAPSE_DROP");
	return on;
}

/// The option is off, but the debug stand runs (OXCE_AI_DEV builds only): the same damage, no model -
/// the control for what the collapse changes.
bool standOnly()
{
#ifdef OXCE_AI_DEV
	return !Options::oxceCollapse && standEnv();
#else
	return false;
#endif
}

int dbgAt()
{
	const char *atS = getenv("OXCE_COLLAPSE_AT");
	return atS && *atS ? atoi(atS) : 1;
}

/// Starts the state for this battle map: the save's terrain sets matched to the sets of every block.
void bind(SavedBattleGame *save)
{
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
		for (size_t s = 0; s < sets.size(); ++s)
			for (int k = 0; k < b.nSets; ++k)
				if (upper(sets[s]->getName()) == b.sets[k]) setOf[s] = k;
		st.setOf.push_back(setOf);
	}
}

bool setsOnMap(int bi)
{
	const auto &setOf = st.setOf[bi];
	return std::find_if(setOf.begin(), setOf.end(), [](int k) { return k >= 0; }) != setOf.end();
}

/// Buildings that still fail some of their scenarios stay in the debug stand builds (OXCE_AI_DEV) only.
bool inThisBuild(int bi)
{
#ifdef OXCE_AI_DEV
	return true;
#else
	return !CollapsePilotData::blocks[bi].experimental;
#endif
}

/// Keeps what was found in the battle save, so a loaded battle goes on with the same buildings.
void store(SavedBattleGame *save)
{
	save->setCollapsePilotVersion(FORMAT);
	auto &list = save->getCollapsePilot();
	list.clear();
	for (const Instance &in : st.inst)
		list.push_back({ std::string(CollapsePilotData::blocks[in.bi].name), in.off, modelSig(in.bi) });
}

/// All parts of the block in place, the ones outside the building box too: of two models whose buildings are
/// the same record for record (two templates of one house with different annexes) the block that matches more.
int countAllInPlace(SavedBattleGame *save, const Instance &in)
{
	const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
	int n = 0;
	for (int i = 0; i < b.nParts; ++i)
		if (inPlace(save, in.bi, b.parts[i], in.off)) ++n;
	return n;
}

/// Do the building boxes of two instances share a map cell?
bool overlaps(const Instance &a, const Instance &b)
{
	const CollapseBlock &p = CollapsePilotData::blocks[a.bi], &q = CollapsePilotData::blocks[b.bi];
	return a.off.x + p.x0 <= b.off.x + q.x1 && b.off.x + q.x0 <= a.off.x + p.x1
		&& a.off.y + p.y0 <= b.off.y + q.y1 && b.off.y + q.y0 <= a.off.y + p.y1
		&& a.off.z < b.off.z + q.sz && b.off.z < a.off.z + p.sz;
}

/// Where each terrain record stands on the map: (save set, part kind, record) -> tiles in z, y, x order.
typedef std::unordered_map<uint64_t, std::vector<Position> > Where;

uint64_t whereKey(int setId, int kind, int id)
{
	return ((uint64_t)(uint16_t)setId << 34) | ((uint64_t)kind << 32) | (uint32_t)id;
}

/// One pass over the map instead of one per anchor of every block.
Where mapIndex(SavedBattleGame *save)
{
	Where w;
	for (int z = 0; z < st.mz; ++z)
		for (int y = 0; y < st.my; ++y)
			for (int x = 0; x < st.mx; ++x)
			{
				const Tile *t = save->getTile(Position(x, y, z));
				for (int k = 0; k < 4; ++k)
				{
					if (!t || !t->getMapData(PARTS[k])) continue;
					int id, setId;
					t->getMapData(&id, &setId, PARTS[k]);
					if (setId >= 0) w[whereKey(setId, k, id)].push_back(Position(x, y, z));
				}
			}
	return w;
}

/// Finds the pilot buildings: offsets voted by the rarest parts of each block. Only a whole building counts
/// (every part in place, the whole block inside the map): the model was checked on the intact template, and
/// a partial match is often another building of the same terrain. One map cell belongs to one building: of
/// whole matches whose boxes overlap only the one with most of its block in place is taken. Found once per
/// battle, kept to its end.
void scan(SavedBattleGame *save)
{
	const auto t0 = Clock::now();
	bind(save);
	// the log file is opened and closed for every Log line (several ms each): the lines of the scan go in one write
	std::ostringstream out;
	auto line = [&out]() -> std::ostringstream& { if (out.tellp() > 0) out << "\n"; return out; };
	std::vector<std::pair<int, Instance> > whole;  // (all parts of the block in place, instance)
	Where where;
	bool indexed = false;
	for (int bi = 0; bi < CollapsePilotData::blockCount; ++bi)
	{
		const CollapseBlock &b = CollapsePilotData::blocks[bi];
		if (!inThisBuild(bi) || !setsOnMap(bi)) continue;
		if (!indexed)
		{
			where = mapIndex(save);
			indexed = true;
		}
		// the five rarest records of the building are the anchors
		std::map<std::pair<int, int>, int> freq;
		for (int i = 0; i < b.nParts; ++i)
			++freq[std::make_pair(b.parts[i].set * 1000 + b.parts[i].kind, b.parts[i].mcd)];
		std::vector<std::pair<int, int> > order;
		for (int i = 0; i < b.nParts; ++i)
			if (b.parts[i].flags & CPF_INBOX)
				order.push_back(std::make_pair(freq[std::make_pair(b.parts[i].set * 1000 + b.parts[i].kind, b.parts[i].mcd)], i));
		std::sort(order.begin(), order.end());
		// candidates in the order of the anchors, each anchor's tiles in z, y, x order
		std::vector<Position> cand;
		std::unordered_set<uint64_t> seen;
		const auto &setOf = st.setOf[bi];
		for (size_t a = 0; a < order.size() && a < 5; ++a)
		{
			const CollapsePart &p = b.parts[order[a].second];
			std::vector<Position> at;
			for (size_t s = 0; s < setOf.size(); ++s)
			{
				if (setOf[s] != p.set) continue;
				const auto f = where.find(whereKey((int)s, p.kind, p.mcd));
				if (f != where.end()) at.insert(at.end(), f->second.begin(), f->second.end());
			}
			std::sort(at.begin(), at.end(), [](const Position &u, const Position &v)
				{ return u.z != v.z ? u.z < v.z : u.y != v.y ? u.y < v.y : u.x < v.x; });
			for (const Position &t : at)
			{
				const Position off(t.x - p.x, t.y - p.y, t.z - p.z);
				const uint64_t key = ((uint64_t)(uint32_t)(off.z + 4096) << 40) | ((uint64_t)(uint32_t)(off.y + 4096) << 20)
					| (uint64_t)(uint32_t)(off.x + 4096);
				if (seen.insert(key).second)
					cand.push_back(off);
			}
		}
		int all = 0;
		for (int i = 0; i < b.nParts; ++i)
			if (b.parts[i].flags & CPF_INBOX) ++all;
		for (const Position &off : cand)
		{
			if (off.x < 0 || off.y < 0 || off.z < 0 || off.x + b.sx > st.mx || off.y + b.sy > st.my || off.z + b.sz > st.mz)
				continue;
			Instance in = { bi, off };
			// counting stops once more than half is missing: then it is neither whole nor worth the line below
			int n = 0, miss = 0;
			for (int i = 0; i < b.nParts && miss * 2 <= all; ++i)
			{
				if (!(b.parts[i].flags & CPF_INBOX)) continue;
				if (inPlace(save, bi, b.parts[i], off)) ++n;
				else ++miss;
			}
			if (all > 0 && miss == 0)
			{
				whole.push_back(std::make_pair(countAllInPlace(save, in), in));
			}
			else if (all > 0 && miss * 2 <= all)
			{
				line() << "[COLLAPSE] not whole " << b.label << " at " << off.x << "," << off.y << "," << off.z
					<< ": " << n << " of " << all << " parts in place - left alone";
			}
		}
	}
	// most of the block first; a tie keeps the order of the blocks in the data, then of the offsets
	std::stable_sort(whole.begin(), whole.end(),
		[](const std::pair<int, Instance> &a, const std::pair<int, Instance> &b) { return a.first > b.first; });
	for (const auto &w : whole)
	{
		const Instance &in = w.second;
		const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
		const Position &off = in.off;
		const Instance *taken = nullptr;
		for (const Instance &had : st.inst)
			if (overlaps(had, in)) taken = &had;
		if (taken)
		{
			const CollapseBlock &tb = CollapsePilotData::blocks[taken->bi];
			line() << "[COLLAPSE] overlaps " << b.label << " at " << off.x << "," << off.y << "," << off.z
				<< ": " << w.first << " of " << b.nParts << " block parts in place, the place is " << tb.label << " at "
				<< taken->off.x << "," << taken->off.y << "," << taken->off.z << " - left alone";
			continue;
		}
		st.inst.push_back(in);
		int all = 0;
		const int n = countInPlace(save, in, &all);
		// self-check of the load test: a whole building has nothing foreign in its place
		line() << "[COLLAPSE] found " << b.label << " (" << b.name << ") at " << off.x << "," << off.y << "," << off.z
			<< ": " << n << " of " << all << " parts in place, " << foreignParts(save, in) << " foreign; block "
			<< w.first << " of " << b.nParts;
	}
	line() << "[COLLAPSE] scan: " << st.inst.size() << " pilot building(s), " << msSince(t0) << " ms";
	Log(LOG_INFO) << out.str();
}

/// Takes the buildings of this battle: the list kept in the save, each entry checked against this build
/// and this map (damage is whatever the saved map lacks); a save without a list - only whole buildings.
void adopt(SavedBattleGame *save)
{
	const int version = save->getCollapsePilotVersion();
	if (version == 0)
	{
		Log(LOG_INFO) << "[COLLAPSE] no building list in the battle: whole buildings only";
		scan(save);
		store(save);
		return;
	}
	bind(save);
	for (const auto &e : save->getCollapsePilot())
	{
		const Position &off = e.at;
		const char *why = nullptr;
		int bi = -1;
		if (version != 1 && version != FORMAT)
			why = "unknown format";
		for (int i = 0; !why && i < CollapsePilotData::blockCount; ++i)
			if (e.model == CollapsePilotData::blocks[i].name && inThisBuild(i)) bi = i;
		if (!why && bi < 0)
			why = "no such model in this build";
		// format 1 kept no fingerprint: its entries are taken on the name alone
		if (!why && version >= 2 && e.sig != modelSig(bi))
			why = "model data changed";
		if (!why)
		{
			const CollapseBlock &b = CollapsePilotData::blocks[bi];
			if (off.x < 0 || off.y < 0 || off.z < 0 || off.x + b.sx > st.mx || off.y + b.sy > st.my || off.z + b.sz > st.mz)
				why = "block outside the map";
			else if (!setsOnMap(bi))
				why = "terrain of the model not on the map";
		}
		Instance in = { bi, off };
		for (const Instance &had : st.inst)
			if (!why && had.bi == bi && had.off == off)
				why = "duplicate entry";
			else if (!why && overlaps(had, in))
				why = "overlaps another building";
		int all = 0, foreign = 0;
		const int n = why ? 0 : countInPlace(save, in, &all);
		// a ruined building is kept however little of it stands; an entry pointing at other buildings
		// is not: something there is no part of this one, nor what its parts turn into
		if (!why && (foreign = foreignParts(save, in)) > 0)
			why = "foreign parts in the building's place";
		if (why)
		{
			Log(LOG_WARNING) << "[COLLAPSE] rejected " << e.model << " at " << off.x << "," << off.y << "," << off.z
				<< " (format " << version << "): " << why << (foreign ? " (" + std::to_string(foreign) + ")" : std::string());
			continue;
		}
		st.inst.push_back(in);
		Log(LOG_INFO) << "[COLLAPSE] kept " << CollapsePilotData::blocks[bi].label << " (" << e.model << ") at "
			<< off.x << "," << off.y << "," << off.z << ": " << n << " of " << all << " parts in place, 0 foreign";
	}
	store(save);
	Log(LOG_INFO) << "[COLLAPSE] from the battle: " << st.inst.size() << " pilot building(s)";
}

/// Takes the given parts of the building away (no debris part), then gravity as an explosion would.
int removeParts(SavedBattleGame *save, const Instance &in, const std::vector<int> &parts)
{
	const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
	int n = 0;
	std::vector<Tile*> hit;
	for (int i : parts)
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
	return n;
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
/// Where the things the placed units carried are now: carried by whom, on which tile, or gone.
void reportCarry(SavedBattleGame *save, const char *when)
{
	for (const auto &c : st.dbgCarry)
	{
		std::ostringstream where;
		where << " gone";
		for (auto *it : *save->getItems())
			if (it->getId() == c.second)
			{
				where.str("");
				if (it->getOwner())
					where << " carried by " << it->getOwner()->getId();
				else if (it->getTile())
					where << " on the ground at " << it->getTile()->getPosition().x << "," << it->getTile()->getPosition().y << "," << it->getTile()->getPosition().z;
				else
					where << " nowhere";
				where << " " << it->getRules()->getType();
			}
		Log(LOG_INFO) << "[COLLAPSE] debug: " << when << " carry of unit " << c.first << ": item " << c.second << where.str();
	}
}

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
	reportCarry(save, when);
}

/// A unit the stand placed: reported later together with what it carried when placed.
void placed(SavedBattleGame *save, BattleUnit *u)
{
	st.dbgUnits.push_back(u->getId());
	for (auto *it : *save->getItems())
		if (it->getOwner() == u)
			st.dbgCarry.push_back(std::make_pair(u->getId(), it->getId()));
}

void debugStand(BattlescapeGame *battle, SavedBattleGame *save)
{
	std::vector<bool> seen(CollapsePilotData::blockCount, false);
	const int at = dbgAt();
	size_t nextUnit = 0;
	// the player's units first, then the others: a tile with no way out needs more bodies than the squad
	std::vector<BattleUnit*> units, big, fly;
	for (int pass = 0; pass < 2; ++pass)
		for (auto *u : *save->getUnits())
			if (!u->isOut() && (u->getFaction() == FACTION_PLAYER) == (pass == 0))
			{
				if (u->getArmor()->getSize() > 1) big.push_back(u);
				else units.push_back(u);
				if (u->getArmor()->getSize() == 1 && u->getMovementType() == MT_FLY) fly.push_back(u);
			}
	size_t nextBig = 0, nextFly = 0;
	for (const Instance &in : st.inst)
	{
		if (seen[in.bi]) continue;
		seen[in.bi] = true;
		const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
		if (st.runs == 1)
		{
			// OXCE_COLLAPSE_BIG / _FLY: a large unit (its corner tile) and a flying one, of any side
			for (int kind = 0; kind < 2; ++kind)
				for (const Position &p : debugTiles(kind ? "OXCE_COLLAPSE_FLY" : "OXCE_COLLAPSE_BIG", b.label))
				{
					std::vector<BattleUnit*> &from = kind ? fly : big;
					size_t &next = kind ? nextFly : nextBig;
					if (next >= from.size())
					{
						Log(LOG_INFO) << "[COLLAPSE] debug: no " << (kind ? "flying" : "large") << " unit left for " << b.label;
						break;
					}
					BattleUnit *u = from[next++];
					const bool ok = save->setUnitPosition(u, in.off + p);
					if (ok) placed(save, u);
					Log(LOG_INFO) << "[COLLAPSE] debug: " << (kind ? "flying" : "large") << " unit " << u->getId() << " " << u->getType()
						<< " size " << u->getArmor()->getSize() << " at " << b.label << " " << p.x << "," << p.y << "," << p.z << (ok ? "" : " - place refused");
				}
			for (int stun = 0; stun < 2; ++stun)
				for (const Position &p : debugTiles(stun ? "OXCE_COLLAPSE_STUN" : "OXCE_COLLAPSE_UNIT", b.label))
				{
					if (nextUnit >= units.size()) break;
					BattleUnit *u = units[nextUnit++];
					const bool ok = save->setUnitPosition(u, in.off + p);
					if (ok && stun) u->knockOut(battle);
					if (ok) placed(save, u);
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
			const int n = removeParts(save, in, debugParts("OXCE_COLLAPSE_REMOVE", b.label));
			// OXCE_COLLAPSE_FIRE: the tiles burn their last turn - they burn out in the next SavedBattleGame::endTurn
			for (const Position &p : debugTiles("OXCE_COLLAPSE_FIRE", b.label))
				if (Tile *t = save->getTile(in.off + p))
				{
					t->setFire(1);
					Log(LOG_INFO) << "[COLLAPSE] debug: fire at " << b.label << " " << p.x << "," << p.y << "," << p.z
						<< " flammable floor " << (t->getMapData(O_FLOOR) ? t->getMapData(O_FLOOR)->getFlammable() : -1)
						<< " object " << (t->getMapData(O_OBJECT) ? t->getMapData(O_OBJECT)->getFlammable() : -1);
				}
			// OXCE_COLLAPSE_BLAST: terrain explosions there, set off by checkForTerrainExplosions after this settle
			const char *powS = getenv("OXCE_COLLAPSE_BLAST_POWER");
			const int power = powS && *powS ? atoi(powS) : 60;
			for (const Position &p : debugTiles("OXCE_COLLAPSE_BLAST", b.label))
				if (Tile *t = save->getTile(in.off + p))
				{
					t->setExplosive(power, 0, true); // MCD explosive type: 0 is HE (ExplosionBState), DT_HE would read as smoke
					Log(LOG_INFO) << "[COLLAPSE] debug: blast " << power << " at " << b.label << " " << p.x << "," << p.y << "," << p.z;
				}
			if (n)
			{
				Log(LOG_INFO) << "[COLLAPSE] debug: removed " << n << " part(s) of " << b.label << " at settle " << st.runs;
			}
		}
	}
}

/// A part that fell in settle, as it was last drawn (HD render, HdFx::fall).
struct Fallen
{
	SurfaceRaw<const Uint8> sprite;
	Position cell;
	TilePart part;
	int yOffset;
	const MapData *what;
	bool seen;              ///< the player has seen it
};

/// The rumble of a collapse: X-Piratez' wall_destroy.wav (its BATTLE.CAT 315), taken from the stone gargoyle that
/// dies with it - the unit holds the index with the mod's offset already added. Without that unit (other masters)
/// collapses stay silent.
int rumble(const Mod *mod)
{
	const Unit *gargoyle = mod->getUnit("STR_STYGIAN_GARGOYLE");
	return gargoyle && !gargoyle->getDeathSounds().empty() ? gargoyle->getDeathSounds().front() : Mod::NO_SOUND;
}
/// A big collapse raises dust on this many landing cells at most, the first ones.
const size_t MAX_DUST = 24;

/// Shows what fell in settle, after the geometry, gravity, light and sight: the building rumbles once, and each part
/// the player has seen goes down to the floor below it (its own floor, for a wall or an object that still has one)
/// and raises dust there (HdFx - pictures only: no smoke, no random numbers, nothing of the battle changes).
void showFall(BattlescapeGame *battle, const std::vector<Fallen> &fallen, Position center)
{
	battle->playSound(rumble(battle->getMod()), center);
	SavedBattleGame *save = battle->getSave();
	struct Landing
	{
		Position cell;
		int parts;
		bool floor;
		int levels;
		Uint32 ms;
		const MapData *what;
	};
	std::vector<Landing> landings;
	for (const Fallen &f : fallen)
	{
		if (!f.seen || !f.sprite)
			continue;
		int z = f.part == O_FLOOR ? f.cell.z - 1 : f.cell.z;
		for (; z > 0; --z)
		{
			Tile *t = save->getTile(Position(f.cell.x, f.cell.y, z));
			if (t && t->getMapData(O_FLOOR))
				break;
		}
		z = std::max(0, z);
		const int levels = f.cell.z - z;
		const Uint32 ms = HdFx::fall(f.sprite, f.cell, f.part, f.yOffset, levels);
		const Position at(f.cell.x, f.cell.y, z);
		auto l = std::find_if(landings.begin(), landings.end(), [&at](const Landing &x) { return x.cell == at; });
		if (l == landings.end())
		{
			landings.push_back(Landing{ at, 1, f.part == O_FLOOR, levels, ms, f.what });
			continue;
		}
		++l->parts;
		l->floor = l->floor || f.part == O_FLOOR;
		l->levels = std::max(l->levels, levels);
		l->ms = std::max(l->ms, ms);
	}
	// headless checks: the pieces at the start, halfway and nearly down (first: the test dumps go in the order asked)
	if (!landings.empty())
		for (Uint32 at : { 0u, landings.front().ms / 2, landings.front().ms * 9 / 10 })
			HdFx::noteForTest("collapse_fall", at);
	// A: a part crumbled where it stood; B: a floor or several parts came down; C: one part fell from above
	for (size_t i = 0; i < landings.size() && i < MAX_DUST; ++i)
	{
		const Landing &l = landings[i];
		HdFx::dust(l.levels == 0 ? 'A' : (l.floor || l.parts > 1) ? 'B' : 'C', l.cell, l.what, l.ms);
	}
}

/// The tile damage an explosion reaching a tile with this power does at most: RuleDamageType::getTileFinalDamage
/// with its roll at the top (RandomTile rolls 0..damage). Keep the two in step; the roll itself must not be made
/// here - the hint runs while aiming, and a roll would move the battle's random numbers.
int tileDamageMax(const RuleDamageType *type, int power)
{
	if (power <= 0)
		return 0;
	const int d = (int)std::round(power * type->ToTile);
	return type->TileDamageLimit >= 0 && d > type->TileDamageLimit ? type->TileDamageLimit : d;
}

/// What an explosion may bring down in each building: per instance (index in st.inst), the parts its tile damage
/// at the top could destroy (TileEngine::detonate: the part's armor against the strongest damage of the tiles that
/// touch it) and the parts the model then no longer holds that it holds now. strongest: the strongest power the
/// explosion reaches each tile with (TileEngine::explosionArea). Reads the map, changes nothing.
void mayFallParts(SavedBattleGame *save, const std::map<Tile*, int> &strongest, const RuleDamageType *type,
	std::vector<std::vector<uint8_t> > &hit, std::vector<std::vector<int> > &falls)
{
	hit.assign(st.inst.size(), std::vector<uint8_t>());
	falls.assign(st.inst.size(), std::vector<int>());
	if (!type || type->ToTile <= 0.0f || st.owner != save || st.mx != save->getMapSizeX() || st.my != save->getMapSizeY()
		|| st.mz != save->getMapSizeZ())
		return;
	std::unordered_map<int, int> damage;  // tile index -> tile damage at the top
	for (const auto &p : strongest)
	{
		const int d = tileDamageMax(type, p.second);
		if (d > 0)
			damage[save->getTileIndex(p.first->getPosition())] = d;
	}
	if (damage.empty())
		return;
	auto at = [&](Position p)
	{
		if (!save->getTile(p))
			return 0;
		auto it = damage.find(save->getTileIndex(p));
		return it == damage.end() ? 0 : it->second;
	};
	for (size_t ii = 0; ii < st.inst.size(); ++ii)
	{
		const Instance &in = st.inst[ii];
		const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
		std::vector<uint8_t> removed(b.nParts, 0), blasted(b.nParts, 0);
		bool any = false;
		for (int i = 0; i < b.nParts; ++i)
		{
			const CollapsePart &p = b.parts[i];
			if (!(p.flags & CPF_INBOX))
				continue;
			if (!inPlace(save, in.bi, p, in.off))
			{
				removed[i] = 1;
				continue;
			}
			const Position pos = in.off + Position(p.x, p.y, p.z);
			const MapData *md = save->getTile(pos)->getMapData(PARTS[p.kind]);
			if (md->getArmor() == 255)
				continue;
			// detonate() of a tile reaches its own parts, the floor above it (ceiling), the west wall of the tile east
			// of it and the north wall of the tile south of it, and the big walls of the tiles north and west of it
			int d = at(pos);
			if (p.kind == 0)
				d = std::max(d, at(pos - Position(0, 0, 1)));
			else if (p.kind == 1)
				d = std::max(d, at(pos - Position(1, 0, 0)));
			else if (p.kind == 2)
				d = std::max(d, at(pos - Position(0, 1, 0)));
			else
			{
				const int bw = md->getBigWall();
				if (bw == 1 || bw == 7 || bw == 8)
					d = std::max(d, at(pos + Position(0, 1, 0)));
				if (bw == 1 || bw == 6 || bw == 8)
					d = std::max(d, at(pos + Position(1, 0, 0)));
			}
			if (d > 0 && md->getArmor() <= d)
			{
				blasted[i] = 1;
				any = true;
			}
		}
		if (!any)
			continue;
		std::vector<uint8_t> heldNow, heldAfter, after(removed);
		collapseEvaluate(b, removed, heldNow);
		for (int i = 0; i < b.nParts; ++i)
			if (blasted[i])
				after[i] = 1;
		collapseEvaluate(b, after, heldAfter);
		for (int i = 0; i < b.nParts; ++i)
			if ((b.parts[i].flags & CPF_INBOX) && !after[i] && heldNow[i] && !heldAfter[i])
				falls[ii].push_back(i);
		hit[ii] = blasted;
	}
}

/// The player saw parts fall, all of them off the screen: one line in the warning bar says to which side (the camera
/// stays: moving it is the battle's). What fell unseen tells nothing - the fog keeps it.
void notice(BattlescapeGame *battle, const std::vector<Position> &seen)
{
	BattlescapeState *state = battle->getSave()->getBattleState();
	if (seen.empty() || !state)
		return;
	Camera *camera = battle->getMap()->getCamera();
	Position sum;
	for (const Position &p : seen)
	{
		if (camera->isOnScreen(p, false, 0, false))
			return;
		sum += p;
	}
	const int n = (int)seen.size();
	Position at, mid;
	camera->convertMapToScreen(Position(sum.x / n, sum.y / n, sum.z / n), &at);
	camera->convertMapToScreen(camera->getCenterPosition(), &mid);
	// eight sides of the screen: a side alone while the other is under half of it
	const int dx = at.x - mid.x, dy = at.y - mid.y;
	const int h = 2 * std::abs(dx) > std::abs(dy) ? (dx > 0 ? 2 : 1) : 0, v = 2 * std::abs(dy) > std::abs(dx) ? (dy > 0 ? 2 : 1) : 0;
	static const char *const SIDE[3][3] = {
		{ "", "STR_HD_COLLAPSE_SIDE_UP", "STR_HD_COLLAPSE_SIDE_DOWN" },
		{ "STR_HD_COLLAPSE_SIDE_LEFT", "STR_HD_COLLAPSE_SIDE_UP_LEFT", "STR_HD_COLLAPSE_SIDE_DOWN_LEFT" },
		{ "STR_HD_COLLAPSE_SIDE_RIGHT", "STR_HD_COLLAPSE_SIDE_UP_RIGHT", "STR_HD_COLLAPSE_SIDE_DOWN_RIGHT" },
	};
	if (!h && !v)
		return;
	Language *lang = state->getGame()->getLanguage();
	state->warningRaw(lang->getString("STR_HD_COLLAPSE_NOTICE").arg(lang->getString(SIDE[h][v])));
	HdFx::noteForTest("collapse_notice", 300);
	Log(LOG_INFO) << "[COLLAPSE] notice: " << SIDE[h][v] << " (" << n << " seen part(s) off the screen)";
}

}

namespace CollapsePilot
{

void scanNew(SavedBattleGame *save)
{
	if (!Options::oxceCollapse)
		return;
	scan(save);
	store(save);
}

void begin(SavedBattleGame *save)
{
	st = decltype(st)();
	if (save->isPreview())
		return;
	if (Options::oxceCollapse)
		adopt(save);
	else if (standOnly())
	{
		scan(save);
		Log(LOG_INFO) << "[COLLAPSE] debug: option off - stand only, no model";
	}
	else
		return;
	// debug stand OXCE_COLLAPSE_HIT: parts taken away before the first settle, as a hit that left the building standing
	std::vector<bool> seen(CollapsePilotData::blockCount, false);
	for (const Instance &in : st.inst)
	{
		if (seen[in.bi]) continue;
		seen[in.bi] = true;
		const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
		const int n = removeParts(save, in, debugParts("OXCE_COLLAPSE_HIT", b.label));
		if (n)
		{
			Log(LOG_INFO) << "[COLLAPSE] debug: hit " << n << " part(s) of " << b.label << " before the first settle";
		}
	}
}

bool settle(BattlescapeGame *battle, const char *why)
{
	const bool model = Options::oxceCollapse;
	if (!model && !standOnly())
		return false;
	SavedBattleGame *save = battle->getSave();
	const auto t0 = Clock::now();
	if (st.owner != save || st.mx != save->getMapSizeX() || st.my != save->getMapSizeY() || st.mz != save->getMapSizeZ())
	{
		if (model) adopt(save);
		else scan(save);
	}
	if (st.inst.empty())
		return false;
	++st.runs;
	const int atRun = dbgAt();
	if (st.runs == atRun + 1)
		debugReport(save, "next settle");
	debugStand(battle, save);
	const double scanMs = msSince(t0);
	if (standEnv())
	{
		// the map as the damage left it, before the model: with the option on and off it must be the same
		Log(LOG_INFO) << "[COLLAPSE] debug: before model settle " << st.runs << " (" << why << "): terrain " << terrainHash(save);
		for (const Instance &in : st.inst)
		{
			const CollapseBlock &b = CollapsePilotData::blocks[in.bi];
			std::ostringstream rm;
			for (int i = 0; i < b.nParts; ++i)
				if ((b.parts[i].flags & CPF_INBOX) && !inPlace(save, in.bi, b.parts[i], in.off))
					rm << i << ",";
			Log(LOG_INFO) << "[COLLAPSE] debug: before model " << b.label << " at " << in.off.x << "," << in.off.y << "," << in.off.z
				<< " removed=" << rm.str();
		}
	}
	if (!model)
	{
		if (st.runs == atRun)
			debugReport(save, "right after");
		return false;
	}
	TileEngine *te = save->getTileEngine();
	bool any = false;
	std::vector<Position> seenCells;
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
		if (standEnv())
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
		std::vector<Fallen> fallen;
		std::vector<Drop> drops;
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
			const TilePart part = PARTS[p.kind];
			const bool seen = t->isDiscovered(O_FLOOR) || (part != O_OBJECT && t->isDiscovered(part));
			if (seen)
				seenCells.push_back(t->getPosition());
			if (Options::oxceHdFx)
				fallen.push_back(Fallen{ t->getSprite(part), t->getPosition(), part, t->getYOffset(part), md, seen });
			drops.push_back(Drop{ t->getPosition(), PARTS[p.kind] == O_FLOOR, rubbleKind(md) });
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
		// the rubble of an earlier collapse on a floor that fell now goes down with it
		RubbleCount rubble;
		for (size_t i = 0, n = tiles.size(); i < n; ++i)
		{
			Tile *t = tiles[i];
			if (t->getMapData(O_FLOOR) || !t->getMapData(O_OBJECT) || !isRubble(save, t, O_OBJECT, false))
				continue;
			int id, setId;
			t->getMapData(&id, &setId, O_OBJECT);
			drops.push_back(Drop{ t->getPosition(), false, st.rubbleKind[std::make_pair(setId, id)] });
			t->setMapData(nullptr, -1, -1, O_OBJECT);
			++rubble.again;
		}
		lay(save, in.bi, drops, tiles, rubble);
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
#ifdef OXCE_AI_DEV
		// debug stand: the camera on what fell, for the HD dumps of the fall (OXCE_HD_DUMP_FX)
		if (getenv("OXCE_COLLAPSE_CAMERA"))
		{
			// the top level in view, the middle of the height in the middle of the screen (a level is 1.5 cells x and y)
			const int d = 3 * (hi.z - lo.z) / 4;
			battle->getMap()->getCamera()->centerOnPosition(Position(center.x + d, center.y + d, hi.z), true);
		}
		// debug stand: the camera away from what fell by "dx,dy" cells, for the off-screen notice
		if (const char *away = getenv("OXCE_COLLAPSE_CAMERA_AWAY"))
		{
			char *end = nullptr;
			const int dx = (int)strtol(away, &end, 10), dy = *end == ',' ? (int)strtol(end + 1, nullptr, 10) : 0;
			battle->getMap()->getCamera()->centerOnPosition(Position(center.x + dx, center.y + dy, center.z), true);
		}
#endif
		showFall(battle, fallen, center);
		Log(LOG_INFO) << "[COLLAPSE] " << why << " " << b.label << " at " << in.off.x << "," << in.off.y << "," << in.off.z
			<< ": removed " << nRemoved << ", fell " << nFell << " (f " << fell[0] << " w " << fell[1] << " n " << fell[2] << " o " << fell[3]
			<< "), outside " << outside << ", lifts " << lifts << ", objectives " << objectives << ", tiles " << tiles.size()
			<< ", rubble " << rubble.laid << " (merged " << rubble.merged << ", again " << rubble.again << "; skipped: unit " << rubble.unit
			<< ", object " << rubble.object << ", no floor " << rubble.floor << ", none " << rubble.none << ")"
			<< ", falling units " << save->getFallingUnits()->size()
			<< "; scan " << scanMs << " ms, eval " << evalMs << " ms, apply " << applyMs << " ms, light+fov " << msSince(tl0) << " ms";
	}
	notice(battle, seenCells);
	if (st.runs == atRun)
		debugReport(save, "right after");
	return any;
}

#ifdef OXCE_AI_DEV
static void reportFall(SavedBattleGame *save, const char *what)
{
	for (int id : st.dbgUnits)
		for (auto *u : *save->getUnits())
			if (u->getId() == id)
			{
				const Position &p = u->getPosition();
				const Tile *t = save->getTile(p);
				Log(LOG_INFO) << "[COLLAPSE] debug: " << what << " unit " << id << " at " << p.x << "," << p.y << "," << p.z
					<< " status " << (int)u->getStatus() << " out " << u->isOut() << " health " << u->getHealth()
					<< " stun " << u->getStunlevel() << " wounds " << u->getFatalWounds()
					<< " tile unit " << (t && t->getUnit() ? t->getUnit()->getId() : -1);
			}
	reportCarry(save, what);
}
#endif

void afterFall(BattlescapeGame *battle)
{
#ifdef OXCE_AI_DEV
	SavedBattleGame *save = battle->getSave();
	if (st.fallReported || st.dbgUnits.empty() || st.runs < dbgAt() || st.owner != save)
		return;
	st.fallReported = true;
	st.fallPending = true;
	Log(LOG_INFO) << "[COLLAPSE] debug: fall over at turn " << save->getTurn() << ", side " << (int)save->getSide();
	reportFall(save, "fall over");
#else
	(void)battle;
#endif
}

void mayFall(SavedBattleGame *save, const std::map<Tile*, int> &strongest, const RuleDamageType *type, std::vector<Position> &cells)
{
	cells.clear();
	if (!Options::oxceCollapse || st.inst.empty())
		return;
	std::vector<std::vector<uint8_t> > hit;
	std::vector<std::vector<int> > falls;
	mayFallParts(save, strongest, type, hit, falls);
	for (size_t ii = 0; ii < st.inst.size(); ++ii)
		for (int i : falls[ii])
		{
			const CollapsePart &p = CollapsePilotData::blocks[st.inst[ii].bi].parts[i];
			const Position pos = st.inst[ii].off + Position(p.x, p.y, p.z);
			const Tile *t = save->getTile(pos);
			// only what the player has seen: the hint must not draw the building through the fog
			if (t && (t->isDiscovered(O_FLOOR) || (PARTS[p.kind] != O_OBJECT && t->isDiscovered(PARTS[p.kind]))))
				cells.push_back(pos);
#ifdef OXCE_AI_DEV
			if (getenv("OXCE_HD_BLAST_AT") && t)
			{
				Log(LOG_INFO) << "[COLLAPSE] debug: may fall " << pos << " kind " << p.kind << " discovered " << t->isDiscovered(O_FLOOR)
					<< t->isDiscovered(O_WESTWALL) << t->isDiscovered(O_NORTHWALL) << t->isDiscovered(O_OBJECT);
			}
#endif
		}
}

void idle(SavedBattleGame *save)
{
#ifdef OXCE_AI_DEV
	// debug stand OXCE_COLLAPSE_SHOW: the parts of OXCE_COLLAPSE_REMOVE taken away in the player's turn, with the map
	// on screen (3 s after the first idle moment: the battle has put its camera on the soldier by then), and settled
	// at once - for the HD dumps of the fall (OXCE_HD_DUMP_FX)
	static bool shown = false;
	static Clock::time_point firstIdle;
	if (!shown && getenv("OXCE_COLLAPSE_SHOW") && st.owner == save && save->getSide() == FACTION_PLAYER && save->getBattleGame()
		&& (firstIdle == Clock::time_point() ? (firstIdle = Clock::now(), false) : msSince(firstIdle) >= 3000))
	{
		shown = true;
		for (const Instance &in : st.inst)
			removeParts(save, in, debugParts("OXCE_COLLAPSE_REMOVE", CollapsePilotData::blocks[in.bi].label));
		// OXCE_COLLAPSE_HINT_BLAST "x,y,z" (map cells): the aim hint of an HE explosion there (OXCE_COLLAPSE_BLAST_POWER,
		// the radius of a terrain explosion), then the explosion itself - the hint against what the model brings down
		if (const char *hb = getenv("OXCE_COLLAPSE_HINT_BLAST"))
		{
			Position c;
			std::stringstream ps(hb);
			char a, b;
			ps >> c.x >> a >> c.y >> b >> c.z;
			const char *powS = getenv("OXCE_COLLAPSE_BLAST_POWER");
			const int power = powS && *powS ? atoi(powS) : 60;
			const RuleDamageType *type = save->getBattleGame()->getMod()->getDamageType(DT_HE);
			const Position center = c.toVoxel() + Position(8, 8, 2);
			std::map<Tile*, int> area, strongest;
			save->getTileEngine()->explosionArea(center, power, type, power / 10, area, &strongest);
			std::vector<std::vector<uint8_t> > hit;
			std::vector<std::vector<int> > falls;
			const auto th = Clock::now();
			mayFallParts(save, strongest, type, hit, falls);
			const double hintMs = msSince(th);
			for (size_t ii = 0; ii < st.inst.size(); ++ii)
			{
				if (hit[ii].empty()) continue;
				const Instance &in = st.inst[ii];
				std::ostringstream hs, fs;
				for (size_t i = 0; i < hit[ii].size(); ++i)
					if (hit[ii][i]) hs << i << ",";
				for (int i : falls[ii])
					fs << i << ",";
				Log(LOG_INFO) << "[COLLAPSE] debug: hint " << CollapsePilotData::blocks[in.bi].label << " at " << in.off.x << "," << in.off.y
					<< "," << in.off.z << " hit=" << hs.str() << " fell=" << fs.str();
			}
			Log(LOG_INFO) << "[COLLAPSE] debug: hint blast " << power << " at " << c << ", " << area.size() << " tile(s), " << hintMs << " ms";
			save->getTileEngine()->explode(BattleActionAttack{ }, center, power, type, power / 10);
		}
		settle(save->getBattleGame(), "show");
	}
	if (!st.fallPending || st.owner != save)
		return;
	st.fallPending = false;
	// the states the fall pushed (UnitDieBState of a unit knocked out below) are done: what a player's save would hold
	Log(LOG_INFO) << "[COLLAPSE] debug: fall settled at turn " << save->getTurn() << ", side " << (int)save->getSide();
	reportFall(save, "fall settled");
	const char *saveAs = getenv("OXCE_COLLAPSE_FALL_SAVE");
	if (saveAs && *saveAs && save->getBattleState())
	{
		Game *game = save->getBattleState()->getGame();
		game->getSavedGame()->save(saveAs, game->getMod());
		Log(LOG_INFO) << "[COLLAPSE] debug: fall settled saved " << saveAs;
	}
#else
	(void)save;
#endif
}

}

}
