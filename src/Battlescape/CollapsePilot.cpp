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
#include "../Engine/FileMap.h"
#include "../Engine/SurfaceSet.h"
#include "../Engine/Surface.h"
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

/// The rubble of a collapse (docs/research/building-collapse-rubble-2026-10-20.md, v2:
/// docs/research/collapse-debris-mechanics-2026-10-21.md): low walkable debris. The first rows are the terrains whose
/// own sets have it (any of the building's sets is the key); the rest are lands told by the building's first set, the
/// last one takes every other building. What fell gives the kind, by the material of its dust (HdFx::partMaterial):
/// stone (and the rest), wood (and furniture: its footstep is soft), metal, or a plant (a part that burns and is of
/// grass, earth, snow, sand or water, not a floor: the crown of a tree). A kind a row has no record of takes stone,
/// then wood, then metal. A record of a set the battle has not loaded borrows the set: it joins the battle's sets
/// (saved by name, as the map's own), so a forest gets the broken trees of the mountain sets.
/// Stone has two more tiers, of the set of the collapse's own (COLLAPSE_DEBRIS, tools/collapse_debris_set.py): a heap
/// a unit stands on, and a block that bars the way; a game without the set gets the crumble.
enum RubbleKind { RK_STONE, RK_WOOD, RK_METAL, RK_PLANT, RK_KINDS };
enum RubbleTier { RT_HEAP = RK_KINDS, RT_BLOCK, RT_LISTS };
struct RubbleRow
{
	const char *keys;   // set names; empty - every building
	bool firstSet;      // the key is the building's first set (else any of its sets)
	const char *kind[RK_KINDS];
	const char *heap;   // the stone tiers, none if left out
	const char *block;
};
#define RUBBLE_TREES "MOUNTGRASS:74 MOUNTGRASS:75 MOUNTGRASS:76"
#define RUBBLE_WOOD "URBAN:87 URBAN:88"
#define RUBBLE_METAL "MILBARR:48 MILBARR:49"
#define HEAP_CONCRETE "COLLAPSE_DEBRIS:5 COLLAPSE_DEBRIS:6"
#define HEAP_EARTH "COLLAPSE_DEBRIS:7 COLLAPSE_DEBRIS:8"
#define HEAP_SNOW "COLLAPSE_DEBRIS:9"
#define HEAP_SAND "COLLAPSE_DEBRIS:10"
#define BLOCK_CONCRETE "COLLAPSE_DEBRIS:11 COLLAPSE_DEBRIS:12"
#define BLOCK_STONE "COLLAPSE_DEBRIS:13 COLLAPSE_DEBRIS:14"
#define BLOCK_SNOW "COLLAPSE_DEBRIS:15 COLLAPSE_DEBRIS:16"  // the same blocks; shot, they leave a heap of their land
#define BLOCK_SAND "COLLAPSE_DEBRIS:17 COLLAPSE_DEBRIS:18"
const RubbleRow RUBBLE[] = {
	{ "URBANWAR", false, { "URBANWAR:50 URBANWAR:57", "MADDECOR:80 MADDECOR:83 MADDECOR:84", "", RUBBLE_TREES },
		HEAP_CONCRETE, BLOCK_CONCRETE },
	{ "URBAN", false, { "URBAN:50 URBAN:57", "URBAN:87 URBAN:88 MADDECOR:80 MADDECOR:83 MADDECOR:84", "", RUBBLE_TREES },
		HEAP_CONCRETE, BLOCK_CONCRETE },
	{ "COMMERCE", false, { "COMMERCE:50 COMMERCE:57", "COMDECOR:68 COMDECOR:69", "", RUBBLE_TREES },
		HEAP_CONCRETE, BLOCK_CONCRETE },
	{ "MILBARR", false, { "MILTECHDIO:26", "", "MILBARR:48 MILBARR:49", RUBBLE_TREES }, HEAP_CONCRETE, BLOCK_CONCRETE },
	{ "VILBAN", false, { "", "VILBAN:87 VILBAN:88", "", RUBBLE_TREES }, nullptr, nullptr },
	{ "IDT_FARM", false, { "", "URBAN_GOODS:24 URBAN_GOODS:25", "", RUBBLE_TREES }, nullptr, nullptr },
	{ "URBAN40K", false, { "URBAN40K:57", "", "", RUBBLE_TREES }, HEAP_CONCRETE, BLOCK_CONCRETE },
	{ "BARN_JUNK", false, { "", "FRNITURE:7 CULTIVAT:11", "", RUBBLE_TREES }, nullptr, nullptr },
	{ "BARN", false, { "", "CULTIVAT:11", "", RUBBLE_TREES }, nullptr, nullptr },
	// lands (census/collapse/debris/biomes.tsv, the cards of art/collapse_debris/short.png)
	{ "BARN_PP CULTAREA CULTIVAT FOREST FORESTBITS3 FORESTBITSRED FORESTRED FOREST_NORD MOUNTGRASS", true,
		{ "MOUNTGRASS:8", RUBBLE_WOOD, RUBBLE_METAL, RUBBLE_TREES }, HEAP_EARTH, BLOCK_STONE },  // forest
	{ "BLACKFOREST BLACKJUNGLE MOUNTMUD", true,
		{ "MOUNTMUD:8", RUBBLE_WOOD, RUBBLE_METAL, "MOUNTMUD:74 MOUNTMUD:75 MOUNTMUD:76" }, HEAP_EARTH, BLOCK_STONE },  // dark forest
	{ "FORESTJUNGLESTYX JUNGLE JUNGLEBITS JUNGLESTYX MOUNTTROP NEOJUNGLE", true,
		{ "MUJUNGLE:36 MUJUNGLE:37", RUBBLE_WOOD, RUBBLE_METAL, "MOUNTTROP:74 MOUNTTROP:75 MOUNTTROP:76" }, HEAP_EARTH, BLOCK_STONE },  // jungle
	{ "FORESTBITS_SNOW FOREST_SNOW MOUNTSNOW2", true,
		{ "MOUNTSNOW2:8", RUBBLE_WOOD, RUBBLE_METAL, "MOUNTSNOW2:74 MOUNTSNOW2:75 MOUNTSNOW2:76 FOREST_SNOW:18 FOREST_SNOW:19" },
		HEAP_SNOW, BLOCK_SNOW },  // snow
	{ "FORESTBITSWASTE FORESTSWAMP_WASTE FOREST_WASTE FRNITURE_WASTE MADDECOR_WASTE MOUNTWASTE2 ROADS_WASTE", true,
		{ "MOUNTROCK:8 SIETCH:36 SIETCH:37", RUBBLE_WOOD, RUBBLE_METAL, "MOUNTWASTE2:74 MOUNTWASTE2:75 MOUNTWASTE2:76" },
		HEAP_EARTH, BLOCK_STONE },  // wasteland
	{ "MOUNTROCK", true,
		{ "MOUNTROCK:8", RUBBLE_WOOD, RUBBLE_METAL, "MOUNTROCK:74 MOUNTROCK:75 MOUNTROCK:76" }, HEAP_EARTH, BLOCK_STONE },  // rocks
	{ "DESERT DESERTBITS MOUNTSAND MUMMY_RUINS MUMMY_VILLAGE XOPSDESERT XOPSDESERTRED", true,
		{ "SIETCH:36 SIETCH:37", RUBBLE_WOOD, RUBBLE_METAL, "MOUNT:74 MOUNT:75 MOUNT:76" }, HEAP_SAND, BLOCK_SAND },  // desert
	{ "BRICKBAR FRN_OLD INDUSLUM RUSTSHACKS", true,
		{ "INDUSLUM:56 INDUSLUM:57 INDUSLUM:58 INDUSLUM:59", RUBBLE_WOOD, RUBBLE_METAL, RUBBLE_TREES },
		HEAP_CONCRETE, BLOCK_CONCRETE },  // slums
	{ "CATACDECOR CAVEBLACK U_PLANET_VOID", true,
		{ "SIETCH_DARK:36 MUSTYX:10", RUBBLE_WOOD, RUBBLE_METAL, "MOUNTMUD:74 MOUNTMUD:75 MOUNTMUD:76" },
		HEAP_EARTH, BLOCK_STONE },  // underground
	{ "", true, { "URBAN:50 URBAN:57 COMMERCE:50", RUBBLE_WOOD, RUBBLE_METAL, RUBBLE_TREES },
		HEAP_CONCRETE, BLOCK_CONCRETE },  // town: every other
};
const int RUBBLE_ROWS = sizeof(RUBBLE) / sizeof(RUBBLE[0]);
/// The chance in 100 that a heap of mass 1 (one wall or object, from less than two levels) leaves rubble, by kind:
/// a piece shatters; a crown does not.
const int RUBBLE_CHANCE[RK_KINDS] = { 50, 35, 50, 100 };
/// A heap of a plant of this mass or more is a tree that came down whole: a fallen trunk instead of the broken one,
/// where the cell may take it (mayBlock).
const int RUBBLE_LOG_MASS = 3;
/// A heap of stone of this mass or more is a heap of the collapse's set (walkable, a unit stands on top of it), of
/// RUBBLE_BLOCK_MASS a block (bars the way, where the cell may take it: mayBlock).
const int RUBBLE_HEAP_MASS = 3;
const int RUBBLE_BLOCK_MASS = 5;
/// The chance in 100 that a heap, a block sheds crumble onto each free cell beside it (the spill of lay).
const int RUBBLE_SPILL_HEAP = 40;
const int RUBBLE_SPILL_BLOCK = 75;
/// A heap of stone of RUBBLE_BLOCK_MASS on a floor above the ground of less armor than this breaks it and comes a
/// level down (the pressed floor of lay).
const int RUBBLE_PRESS_ARMOR = 60;
/// The blow of what falls on a unit: this much for a unit of mass and for a level it fell, at most RUBBLE_HIT_MAX
/// (melee, to the head, the front armor); of RUBBLE_HEAP_MASS it pins the unit down, out of energy.
const int RUBBLE_HIT_MASS = 10;
const int RUBBLE_HIT_MAX = 70;
/// The dust of a fall of RUBBLE_HEAP_MASS: the smoke of the game on the cell it came down to, this many turns.
const int RUBBLE_DUST = 3;

/// The fallen trunks of a set for its broken trees: records that turn into one of `windfall` when destroyed, low (6
/// layers at most), not walkable and burning - the whole log of the mountain sets (72 -> 75, 73 -> 76).
std::vector<int> logsOf(MapDataSet *set, const std::vector<int> &windfall)
{
	std::vector<int> logs;
	for (int i = 1; i < (int)set->getSize(); ++i)
	{
		const MapData *md = set->getObject(i);
		if (md->getObjectType() != O_OBJECT || std::find(windfall.begin(), windfall.end(), md->getDieMCD()) == windfall.end())
			continue;
		int layers = 0;
		for (int l = 0; l < 12; ++l)
			layers += md->getLoftID(l) != 0;
		if (layers <= 6 && md->getTUCost(MT_WALK) == 255 && md->getFlammable() < 255 && md->getFuel() > 0 && md->getArmor() < 255)
			logs.push_back(i);
	}
	return logs;
}

/// The records of a row's list that are in one set.
std::vector<int> recordsIn(const std::vector<std::pair<std::string, int> > &list, const std::string &name)
{
	std::vector<int> ids;
	for (const auto &rec : list)
		if (rec.first == name) ids.push_back(rec.second);
	return ids;
}

/// The kind of rubble a fallen part gives.
int rubbleKind(const MapData *md, bool floor)
{
	const std::string m = HdFx::partMaterial(md);
	if (!floor && md->getFlammable() < 255 && md->getFuel() > 0
		&& (m == "grass" || m == "dirt" || m == "snow" || m == "sand" || m == "water"))
		return RK_PLANT;
	return m == "wood" || m == "soft" ? RK_WOOD : m == "metal" ? RK_METAL : RK_STONE;
}

/// The records of a row's kind or stone tier (RubbleTier): (set name, record).
const std::vector<std::pair<std::string, int> > &rubbleRecords(int row, int kind)
{
	static std::vector<std::vector<std::pair<std::string, int> > > parsed;
	if (parsed.empty())
	{
		parsed.resize(RUBBLE_ROWS * RT_LISTS);
		for (int r = 0; r < RUBBLE_ROWS; ++r)
			for (int k = 0; k < RT_LISTS; ++k)
			{
				const char *text = k < RK_KINDS ? RUBBLE[r].kind[k] : k == RT_HEAP ? RUBBLE[r].heap : RUBBLE[r].block;
				std::istringstream in(text ? text : "");
				std::string rec;
				while (in >> rec)
				{
					const size_t colon = rec.find(':');
					parsed[r * RT_LISTS + k].push_back(std::make_pair(rec.substr(0, colon), std::atoi(rec.c_str() + colon + 1)));
				}
			}
	}
	return parsed[row * RT_LISTS + kind];
}

/// The index of a set among the battle's sets, or -1.
int setIndexOf(SavedBattleGame *save, const std::string &name)
{
	const std::vector<MapDataSet*> &sets = *save->getMapDataSets();
	for (size_t i = 0; i < sets.size(); ++i)
		if (upper(sets[i]->getName()) == name) return (int)i;
	return -1;
}

/// The rubble records of this battle, found by the set names (a set the battle lacks gives none, until borrowed).
void rubbleOf(SavedBattleGame *save)
{
	if (st.rubbleReady)
		return;
	st.rubbleReady = true;
	const std::vector<MapDataSet*> &sets = *save->getMapDataSets();
	for (int r = 0; r < RUBBLE_ROWS; ++r)
		for (int k = 0; k < RT_LISTS; ++k)
			for (const auto &rec : rubbleRecords(r, k))
			{
				const int s = setIndexOf(save, rec.first);
				if (s < 0 || rec.second < 0 || rec.second >= (int)sets[s]->getSize()) continue;
				std::vector<int> ids(1, rec.second);
				if (k == RK_PLANT)  // and the fallen trunks of its set (lay)
				{
					const std::vector<int> logs = logsOf(sets[s], recordsIn(rubbleRecords(r, k), rec.first));
					ids.insert(ids.end(), logs.begin(), logs.end());
				}
				for (int id : ids)
				{
					st.rubbleKind[std::make_pair(s, id)] = k < RK_KINDS ? k : RK_STONE;
					// what the rubble turns into when it is shot or burnt is the collapse's too (foreignParts)
					for (int dead = id; dead > 0 && dead < (int)sets[s]->getSize() && st.rubbleOrDead.insert(std::make_pair(s, dead)).second; )
						dead = sets[s]->getObject(dead)->getDieMCD();
				}
			}
}

/// Borrows a set for the rubble: loads it the way the battle generator loads the map's (BattlescapeGenerator) and
/// adds it to the battle's sets; the save keeps it by name. -1 if the game has no such set or the battle no room.
int borrowSet(Mod *mod, SavedBattleGame *save, const std::string &name)
{
	std::vector<MapDataSet*> &sets = *save->getMapDataSets();
	if (sets.size() >= 255 || !FileMap::fileExists("TERRAIN/" + name + ".MCD") || !FileMap::fileExists("TERRAIN/" + name + ".PCK"))
		return -1;
	MapDataSet *mds = mod->getMapDataSet(name);
	mds->loadData(mod->getMCDPatch(name), true, mod->getHdScale());
	// the palette the battle's sets were given (Map::setPalette)
	SurfaceSet *own = sets.empty() ? nullptr : sets[0]->getSurfaceset();
	if (own && own->getTotalFrames() && mds->getSurfaceset())
		mds->getSurfaceset()->setPalette(own->getFrame(0)->getPalette());
	sets.push_back(mds);
	st.rubbleReady = false;
	Log(LOG_INFO) << "[COLLAPSE] rubble: set " << name << " borrowed, battle set " << sets.size() - 1;
	return (int)sets.size() - 1;
}

/// The row of RUBBLE for the building of block bi.
int rubbleRow(int bi)
{
	const CollapseBlock &b = CollapsePilotData::blocks[bi];
	for (int r = 0; r < RUBBLE_ROWS; ++r)
	{
		std::istringstream in(RUBBLE[r].keys);
		std::string key;
		bool any = false;
		while (in >> key)
		{
			any = true;
			for (int s = 0; s < (RUBBLE[r].firstSet ? std::min(1, b.nSets) : b.nSets); ++s)
				if (upper(b.sets[s]) == key) return r;
		}
		if (!any) return r;
	}
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
	int laid = 0, merged = 0, unit = 0, object = 0, floor = 0, none = 0, again = 0, light = 0, replaced = 0, log = 0,
		heap = 0, block = 0, spill = 0, pressed = 0, hit = 0, knocked = 0, dust = 0;
};

/// The roll of a heap of mass 1, 0..99: by the cell and the building, not the random numbers of the game, so the
/// same collapse leaves the same rubble after a load.
int rubbleRoll(Position at, int bi)
{
	uint32_t h = (uint32_t)at.x * 73856093u ^ (uint32_t)at.y * 19349663u ^ (uint32_t)at.z * 83492791u ^ (uint32_t)bi * 2654435761u;
	h ^= h >> 13;
	h *= 0x5bd1e995u;
	h ^= h >> 15;
	return (int)(h % 100);
}

/// A low object the rubble may take the place of: walkable, not over half the height (a stump, a tuft, a crate),
/// not a door, a lift, a mark of the map (objective, start, exit), an explosive or what is not to be destroyed.
bool underRubble(const MapData *md)
{
	int layers = 0;
	for (int i = 0; i < 12; ++i)
		layers += md->getLoftID(i) != 0;
	return layers <= 6 && md->getTUCost(MT_WALK) < 255 && !md->isDoor() && !md->isUFODoor() && !md->isGravLift()
		&& md->getSpecialType() == TILE && !md->getExplosive() && md->getArmor() < 255;
}

/// May a cell take a fallen trunk, which bars the way? Not where items lie (a weapon, a body: out of reach under
/// it), by a door, on a mark of the map, nor where it parts the way: the walkable cells of the 8 around must be one
/// run along the ring (each two next on the ring are side by side), so whatever went by the cell still goes round it.
bool mayBlock(SavedBattleGame *save, Tile *t)
{
	if (!t->getInventory()->empty())
		return false;
	const Position at = t->getPosition();
	for (int p = O_FLOOR; p <= O_OBJECT; ++p)
	{
		const MapData *md = t->getMapData((TilePart)p);
		if (md && md->getSpecialType() != TILE) return false;
	}
	const Tile *east = save->getTile(at + Position(1, 0, 0)), *south = save->getTile(at + Position(0, 1, 0));
	const MapData *edges[4] = { t->getMapData(O_WESTWALL), t->getMapData(O_NORTHWALL),
		east ? east->getMapData(O_WESTWALL) : nullptr, south ? south->getMapData(O_NORTHWALL) : nullptr };
	for (const MapData *md : edges)
		if (md && (md->isDoor() || md->isUFODoor())) return false;
	static const int ring[8][2] = { { -1, -1 }, { 0, -1 }, { 1, -1 }, { 1, 0 }, { 1, 1 }, { 0, 1 }, { -1, 1 }, { -1, 0 } };
	bool walk[8];
	for (int i = 0; i < 8; ++i)
	{
		Tile *c = save->getTile(at + Position(ring[i][0], ring[i][1], 0));
		const MapData *object = c ? c->getMapData(O_OBJECT) : nullptr;
		// a block (T_Level -12) is not stepped onto from the ground (Pathfinding: no step up of over 8)
		walk[i] = c && (at.z == 0 || !c->hasNoFloor(save))
			&& (!object || (object->getTUCost(MT_WALK) < 255 && object->getTerrainLevel() > -12));
	}
	int runs = 0;
	for (int i = 0; i < 8; ++i)
		runs += walk[i] && !walk[(i + 7) % 8];
	return runs <= 1;
}

/// Lays the rubble of what fell: one record on the floor each part comes down to (the way TileEngine::applyGravity
/// takes items down), of the kind most of what came there was (stone on a tie), the record of its kind by the cell
/// (no random numbers). The mass of a heap: a floor 2, a wall or an object 1, a fall of two levels or more 1 more;
/// a heap of mass 1 leaves rubble by its roll (RUBBLE_CHANCE), a crown always; a plant of RUBBLE_LOG_MASS is a fallen
/// trunk (logsOf) where the cell may take it (mayBlock); stone of RUBBLE_HEAP_MASS a heap, of RUBBLE_BLOCK_MASS a
/// block where the cell may take it (the tiers of the row; the crumble if the game has not the set). None where a unit stands or will land,
/// on a lift or on no floor of its own; a low object there (underRubble) gives way to it, a higher one keeps the cell.
/// A heap or a block spills the crumble onto each free cell beside it (RUBBLE_SPILL_*, by the cell's roll), not
/// through a wall, onto a unit, an object, a mark of the map or a lift.
/// A block's load breaks a weak floor above the ground (RUBBLE_PRESS_ARMOR) and comes a level down; a unit where it
/// comes down takes its blow (RUBBLE_HIT_*), a fall of a heap's mass raises dust (RUBBLE_DUST); a tree that came
/// down whole knocks the crown of a tree beside it.
/// The tiles it lies on join `tiles` (gravity, light and sight).
void lay(Mod *mod, SavedBattleGame *save, int bi, const std::vector<Drop> &drops, std::vector<Tile*> &tiles, RubbleCount &n)
{
	rubbleOf(save);
	const int row = rubbleRow(bi);
	struct Heap
	{
		Tile *tile;
		int top;
		int mass;
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
			heaps.push_back(Heap{ t, d.cell.z, 0, { 0, 0, 0, 0 } });
			h = heaps.end() - 1;
		}
		else
			++n.merged;
		h->top = std::max<int>(h->top, d.cell.z);
		h->mass += d.floor ? 2 : 1;
		++h->kinds[d.kind];
	}
	// the pressed floor: a block of stone on a weak floor above the ground breaks it and comes a level down with it
	for (Heap &h : heaps)
	{
		const Position at = h.tile->getPosition();
		const MapData *floor = h.tile->getMapData(O_FLOOR);
		bool stone = true;
		for (int k = 1; k < RK_KINDS; ++k)
			stone = stone && h.kinds[k] <= h.kinds[RK_STONE];
		if (at.z == 0 || !floor || !stone || h.mass + (h.top - at.z >= 2 ? 1 : 0) < RUBBLE_BLOCK_MASS
			|| floor->getArmor() >= RUBBLE_PRESS_ARMOR || floor->isGravLift() || floor->getSpecialType() != TILE
			|| h.tile->getUnit() || h.tile->getMapData(O_OBJECT))
			continue;
		if (h.tile->destroy(O_FLOOR, save->getObjectiveType()))
			save->addDestroyedObjective();
		++n.pressed;
		if (std::find(tiles.begin(), tiles.end(), h.tile) == tiles.end())
			tiles.push_back(h.tile);
		Tile *t = h.tile;
		while (t && t->getPosition().z > 0 && t->hasNoFloor(save))
			t = save->getBelowTile(t);
		if (!t || t == h.tile)
			continue;  // the floor broke into a floor of its own (its die record): the block lies on it
		h.tile = t;
		h.mass += 2;
	}
	static const int sides[4][2] = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } };
	static const std::vector<std::pair<std::string, int> > nothing;
	std::vector<std::pair<Tile*, int> > spills;  // a heap or a block laid, the chance of its spill
	for (const Heap &h : heaps)
	{
		const Position at = h.tile->getPosition();
		std::vector<BattleUnit*> under;
		for (int z = at.z; z <= h.top; ++z)
		{
			const Tile *c = save->getTile(Position(at.x, at.y, z));
			BattleUnit *u = c ? c->getUnit() : nullptr;
			if (u && std::find(under.begin(), under.end(), u) == under.end())
				under.push_back(u);
		}
		const bool unit = !under.empty();
		const MapData *floor = h.tile->getMapData(O_FLOOR);
		const MapData *object = h.tile->getMapData(O_OBJECT);
		int kind = RK_STONE;
		for (int k = 1; k < RK_KINDS; ++k)
			if (h.kinds[k] > h.kinds[kind]) kind = k;
		const std::vector<std::pair<std::string, int> > *list = row < 0 ? &nothing : &rubbleRecords(row, kind);
		for (int k = 0; row >= 0 && list->empty() && k < RK_KINDS; ++k)
		{
			kind = k;
			list = &rubbleRecords(row, kind);
		}
		const int mass = h.mass + (h.top - at.z >= 2 ? 1 : 0);
		if (mass >= RUBBLE_HEAP_MASS && !h.tile->getFire() && h.tile->getSmoke() < RUBBLE_DUST)
		{
			h.tile->setSmoke(RUBBLE_DUST);
			++n.dust;
		}
		if (unit)
		{
			// no rubble on a unit: it takes the blow of what fell, of a heap's mass pinned down under it
			++n.unit;
			const int blow = std::min(RUBBLE_HIT_MAX, RUBBLE_HIT_MASS * (mass + h.top - at.z));
			for (BattleUnit *u : under)
			{
				if (u->isOut()) continue;
				u->damage(Position(0, 0, 0), blow, mod->getDamageType(DT_MELEE), save, { }, SIDE_FRONT, BODYPART_HEAD);
				if (mass >= RUBBLE_HEAP_MASS)
					u->spendEnergy(u->getEnergy());
				++n.hit;
			}
		}
		else if (object && !underRubble(object)) ++n.object;
		else if ((at.z > 0 && !floor) || (floor && floor->isGravLift())) ++n.floor;
		else if (list->empty()) ++n.none;
		else if (mass < 2 && rubbleRoll(at, bi) >= RUBBLE_CHANCE[kind]) ++n.light;
		else
		{
			// the record of a list by the cell, its set borrowed if need be; -1 if the game has none
			const std::pair<std::string, int> *rec = nullptr;
			auto pick = [&](const std::vector<std::pair<std::string, int> > &l)
			{
				if (l.empty()) return -1;
				rec = &l[(at.x * 7 + at.y * 13 + at.z * 5) % l.size()];
				int s = setIndexOf(save, rec->first);
				if (s < 0)
					s = borrowSet(mod, save, rec->first);
				return s < 0 || rec->second >= (int)(*save->getMapDataSets())[s]->getSize() ? -1 : s;
			};
			int s = -1;
			if (kind == RK_STONE && mass >= RUBBLE_BLOCK_MASS && mayBlock(save, h.tile) && (s = pick(rubbleRecords(row, RT_BLOCK))) >= 0)
			{
				++n.block;
				spills.push_back(std::make_pair(h.tile, RUBBLE_SPILL_BLOCK));
			}
			else if (kind == RK_STONE && mass >= RUBBLE_HEAP_MASS && (s = pick(rubbleRecords(row, RT_HEAP))) >= 0)
			{
				++n.heap;
				spills.push_back(std::make_pair(h.tile, RUBBLE_SPILL_HEAP));
			}
			else
				s = pick(*list);
			const std::vector<MapDataSet*> &sets = *save->getMapDataSets();
			if (s < 0)
			{
				++n.none;
				continue;
			}
			int id = rec->second;
			if (kind == RK_PLANT && mass >= RUBBLE_LOG_MASS && mayBlock(save, h.tile))
			{
				const std::vector<int> logs = logsOf(sets[s], recordsIn(*list, rec->first));
				if (!logs.empty())
				{
					id = logs[(at.x * 5 + at.y * 3 + at.z) % logs.size()];
					++n.log;
					// the tree came down whole, to a side by the cell: its crown knocks the crown of a tree there
					// (not through a wall), which breaks as a part does (Tile::destroy)
					const int (&d)[2] = sides[rubbleRoll(at, bi + 104729) % 4];
					for (int z = at.z + 1; z <= h.top; ++z)
					{
						Tile *c = save->getTile(Position(at.x + d[0], at.y + d[1], z));
						const MapData *crown = c ? c->getMapData(O_OBJECT) : nullptr;
						if (!crown || rubbleKind(crown, false) != RK_PLANT || isRubble(save, c, O_OBJECT, true)
							|| crown->getSpecialType() != TILE || crown->getArmor() >= 255 || c->getUnit())
							continue;
						const Tile *edge = d[0] + d[1] > 0 ? c : save->getTile(Position(at.x, at.y, z));
						if (!edge || edge->getMapData(d[0] ? O_WESTWALL : O_NORTHWALL))
							continue;
						c->destroy(O_OBJECT, save->getObjectiveType());
						++n.knocked;
						if (std::find(tiles.begin(), tiles.end(), c) == tiles.end())
							tiles.push_back(c);
					}
				}
			}
			if (object)
				++n.replaced;
			h.tile->setMapData(sets[s]->getObject(id), id, s, O_OBJECT);
			++n.laid;
			if (std::find(tiles.begin(), tiles.end(), h.tile) == tiles.end())
				tiles.push_back(h.tile);
		}
	}
	// the spill: a heap or a block sheds the crumble of its row onto the free cells beside it
	const std::vector<std::pair<std::string, int> > &crumble = row < 0 ? nothing : rubbleRecords(row, RK_STONE);
	for (const auto &sp : spills)
		for (const auto &d : sides)
		{
			const Position from = sp.first->getPosition(), at = from + Position(d[0], d[1], 0);
			Tile *t = save->getTile(at);
			if (!t || crumble.empty() || rubbleRoll(at, bi + 7919) >= sp.second
				|| std::find_if(heaps.begin(), heaps.end(), [t](const Heap &x) { return x.tile == t; }) != heaps.end())
				continue;
			// what parts the two cells: the west wall of the east one, the north wall of the south one
			const Tile *edge = d[0] + d[1] > 0 ? t : sp.first;
			if (edge->getMapData(d[0] ? O_WESTWALL : O_NORTHWALL))
				continue;
			const MapData *floor = t->getMapData(O_FLOOR);
			if (t->getMapData(O_OBJECT) || t->getUnit() || (at.z > 0 && t->hasNoFloor(save))
				|| (floor && (floor->isGravLift() || floor->getSpecialType() != TILE)))
				continue;
			const auto &rec = crumble[(at.x * 7 + at.y * 13 + at.z * 5) % crumble.size()];
			int s = setIndexOf(save, rec.first);
			if (s < 0)
				s = borrowSet(mod, save, rec.first);
			if (s < 0 || rec.second >= (int)(*save->getMapDataSets())[s]->getSize())
				continue;
			t->setMapData((*save->getMapDataSets())[s]->getObject(rec.second), rec.second, s, O_OBJECT);
			++n.spill;
			if (std::find(tiles.begin(), tiles.end(), t) == tiles.end())
				tiles.push_back(t);
		}
	rubbleOf(save);
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
	int hits = 0;
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
			drops.push_back(Drop{ t->getPosition(), PARTS[p.kind] == O_FLOOR, rubbleKind(md, PARTS[p.kind] == O_FLOOR) });
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
		lay(battle->getMod(), save, in.bi, drops, tiles, rubble);
		hits += rubble.hit;
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
			<< ", object " << rubble.object << ", no floor " << rubble.floor << ", none " << rubble.none
			<< ", by chance " << rubble.light << "; in place of a low object " << rubble.replaced << ", fallen trunks " << rubble.log
			<< ", heaps " << rubble.heap << ", blocks " << rubble.block << ", spill " << rubble.spill
			<< ", pressed floors " << rubble.pressed << ", units hit " << rubble.hit << ", knocked crowns " << rubble.knocked
			<< ", dust " << rubble.dust << ")"
			<< ", falling units " << save->getFallingUnits()->size()
			<< "; scan " << scanMs << " ms, eval " << evalMs << " ms, apply " << applyMs << " ms, light+fov " << msSince(tl0) << " ms";
	}
	notice(battle, seenCells);
	// the units under what fell: the end of the turn checks the casualties itself (BattlescapeGame::endTurn), right
	// after this settle; twice would count a death twice
	if (hits && std::strcmp(why, "end turn") != 0)
		battle->checkForCasualties(battle->getMod()->getDamageType(DT_MELEE), BattleActionAttack{ }, false, true);
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
