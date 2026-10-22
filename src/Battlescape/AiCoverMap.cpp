/*
 * Copyright 2010-2016 OpenXcom Developers.
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
#include "AiCoverMap.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <set>
#include <sstream>
#include <thread>
#include "Pathfinding.h"
#include "TileEngine.h"
#include "../Engine/Logger.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleDamageType.h"
#include "../Savegame/Node.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"

namespace OpenXcom
{

namespace
{

const int PER_TILE = AiCoverMap::SIDES * AiCoverMap::SHOOTERS * AiCoverMap::LAYERS; // 192 values of 2 bits
const int BYTES_PER_TILE = PER_TILE / 4;
const int SHOOTER_TILES[AiCoverMap::SHOOTERS] = { 3, 10 };
const int OFFSETS[AiCoverMap::LINES] = { -4, 0, 4 };
/// Only terrain this close to the tile is its cover: 1.5 tiles in voxels.
const int ZONE = 24;
/// The virtual shooter's eye over its floor: TileEngine::getOriginVoxel for a standing unit of height 22 (22 - 4).
const int EYE = 18;
/// A standing body's middle over its floor for the node-to-node lines: half of 22.
const int BODY = 11;
/// Over this many touched tiles a refresh is a rebuild.
const size_t DIRTY_CAP = 4096;

struct CoverState
{
	const SavedBattleGame *save = nullptr;
	bool built = false;
	int sx = 0, sy = 0, sz = 0;
	std::vector<uint8_t> prof;  // per tile BYTES_PER_TILE
	std::vector<uint8_t> flags; // per tile
	int nodes = 0;
	std::vector<uint8_t> sees;  // nodes x nodes bits, row = from
	std::vector<int> choke;
	std::vector<Position> dirty;
	bool overflow = false;
};
CoverState g;

int index(int x, int y, int z) { return (z * g.sy + y) * g.sx + x; }

int valueIndex(int side, int far, int layer) { return (side * AiCoverMap::SHOOTERS + far) * AiCoverMap::LAYERS + layer; }

/// The parallel lines of one side, one shooter, one layer: entry into the zone and the body voxel.
void lineEnds(int x, int y, int z, int bottom, int side, int far, int layer, int off, Position &a, Position &b)
{
	Position d;
	Pathfinding::directionToVector(side, &d);
	const double len = std::sqrt(double(d.x * d.x + d.y * d.y));
	const double ux = d.x / len, uy = d.y / len;
	const double tx = x * 16 + 8 - uy * off, ty = y * 16 + 8 + ux * off;
	const double tz = bottom + 2 + 2 * layer;
	const double r = SHOOTER_TILES[far] * 16.0;
	const double sx = tx + ux * r, sy = ty + uy * r, sz = z * 24 + EYE;
	const double f = ZONE / r;
	a = Position((int)std::lround(tx + (sx - tx) * f), (int)std::lround(ty + (sy - ty) * f), (int)std::lround(tz + (sz - tz) * f));
	b = Position((int)std::lround(tx), (int)std::lround(ty), (int)std::lround(tz));
}

/// A wall on an edge of the tile: own north and west walls, the east neighbour's west wall, the south neighbour's north wall
/// (the sides TileEngine::faceWindow looks at).
template<typename F>
bool anyEdgeWall(const SavedBattleGame *save, const Position &p, F test)
{
	const Tile *t = save->getTile(p);
	const Tile *e = save->getTile(p + Position(1, 0, 0));
	const Tile *s = save->getTile(p + Position(0, 1, 0));
	return (t && t->getMapData(O_NORTHWALL) && test(t->getMapData(O_NORTHWALL)))
		|| (e && e->getMapData(O_WESTWALL) && test(e->getMapData(O_WESTWALL)))
		|| (s && s->getMapData(O_NORTHWALL) && test(s->getMapData(O_NORTHWALL)))
		|| (t && t->getMapData(O_WESTWALL) && test(t->getMapData(O_WESTWALL)));
}

/// One tile: its flags and, if a size-1 unit can stand on it, its cover values. Pure; any thread.
long long computeTile(const SavedBattleGame *save, const std::vector<Uint16> *vox, int x, int y, int z, uint8_t *out, uint8_t &flag)
{
	std::fill(out, out + BYTES_PER_TILE, 0);
	flag = 0;
	const Position p(x, y, z);
	const Tile *tile = save->getTile(p);
	if (!tile)
	{
		return 0;
	}
	if (anyEdgeWall(save, p, [](const MapData *m) { return m->getBlock(DT_NONE) == 0; }))
	{
		flag |= AiCoverMap::F_WINDOW;
	}
	if (anyEdgeWall(save, p, [](const MapData *m) { return m->isDoor() || m->isUFODoor(); }))
	{
		flag |= AiCoverMap::F_DOOR;
	}
	const MapData *obj = tile->getMapData(O_OBJECT);
	if (tile->hasNoFloor(save) || (obj && obj->getTUCost(MT_WALK) == 255))
	{
		return 0;
	}
	flag |= AiCoverMap::F_STAND;
	const int bottom = z * 24 - tile->getTerrainLevel();
	long long rays = 0;
	for (int side = 0; side < AiCoverMap::SIDES; ++side)
	{
		for (int far = 0; far < AiCoverMap::SHOOTERS; ++far)
		{
			for (int layer = 0; layer < AiCoverMap::LAYERS; ++layer)
			{
				int stopped = 0;
				for (int off : OFFSETS)
				{
					Position a, b;
					lineEnds(x, y, z, bottom, side, far, layer, off, a, b);
					// out of the map counts as stopped: no shooter stands beyond the map's edge
					if (terrainLineVoxel(save, vox, a, b) != V_EMPTY)
					{
						++stopped;
					}
					++rays;
				}
				const int vi = valueIndex(side, far, layer);
				out[vi >> 2] |= stopped << ((vi & 3) * 2);
			}
		}
	}
	return rays;
}

int envInt(const char *name, int def)
{
	const char *v = std::getenv(name);
	return v && *v ? std::atoi(v) : def;
}

/// All tiles on `threads` threads: rows (z, y) handed out one by one, each tile written by one thread only.
long long computeAll(const SavedBattleGame *save, std::vector<uint8_t> &prof, std::vector<uint8_t> &flags, int threads)
{
	const std::vector<Uint16> *vox = save->getMod()->getVoxelData();
	std::atomic<int> next(0);
	std::atomic<long long> rays(0);
	const int rows = g.sz * g.sy;
	auto work = [&]()
	{
		long long mine = 0;
		for (int r = next++; r < rows; r = next++)
		{
			const int z = r / g.sy, y = r % g.sy;
			for (int x = 0; x < g.sx; ++x)
			{
				const int i = index(x, y, z);
				mine += computeTile(save, vox, x, y, z, &prof[(size_t)i * BYTES_PER_TILE], flags[i]);
			}
		}
		rays += mine;
	};
	std::vector<std::thread> pool;
	for (int t = 1; t < threads; ++t)
	{
		pool.emplace_back(work);
	}
	work();
	for (auto &t : pool)
	{
		t.join();
	}
	return rays;
}

Position nodeVoxel(const SavedBattleGame *save, const Node *n, int over)
{
	const Position p = n->getPosition();
	const Tile *t = save->getTile(p);
	return Position(p.x * 16 + 8, p.y * 16 + 8, p.z * 24 - (t ? t->getTerrainLevel() : 0) + over);
}

/// Node `i` sees node `j`: within the view distance and no terrain on the line from i's eye to j's body.
bool computeSees(const SavedBattleGame *save, const std::vector<Uint16> *vox, std::vector<Node*> *nodes, int i, int j, long long &rays)
{
	const Position pi = (*nodes)[i]->getPosition(), pj = (*nodes)[j]->getPosition();
	const int dx = pi.x - pj.x, dy = pi.y - pj.y, dz = pi.z - pj.z;
	const int view = save->getMod()->getMaxViewDistance();
	if (dx * dx + dy * dy + dz * dz > view * view)
	{
		return false;
	}
	++rays;
	return terrainLineVoxel(save, vox, nodeVoxel(save, (*nodes)[i], EYE), nodeVoxel(save, (*nodes)[j], BODY)) == V_EMPTY;
}

void setSees(int i, int j, bool v)
{
	const size_t bit = (size_t)i * g.nodes + j;
	if (v)
		g.sees[bit >> 3] |= (uint8_t)(1 << (bit & 7));
	else
		g.sees[bit >> 3] &= (uint8_t)~(1 << (bit & 7));
}

long long computeNodes(const SavedBattleGame *save, std::vector<Node*> *nodes, int threads)
{
	const std::vector<Uint16> *vox = save->getMod()->getVoxelData();
	const int n = g.nodes;
	std::vector<std::vector<uint8_t> > rows(n, std::vector<uint8_t>(n, 0));
	std::atomic<int> next(0);
	std::atomic<long long> rays(0);
	auto work = [&]()
	{
		long long mine = 0;
		for (int i = next++; i < n; i = next++)
		{
			for (int j = 0; j < n; ++j)
			{
				rows[i][j] = i != j && computeSees(save, vox, nodes, i, j, mine);
			}
		}
		rays += mine;
	};
	std::vector<std::thread> pool;
	for (int t = 1; t < threads; ++t)
	{
		pool.emplace_back(work);
	}
	work();
	for (auto &t : pool)
	{
		t.join();
	}
	for (int i = 0; i < n; ++i)
		for (int j = 0; j < n; ++j)
			setSees(i, j, rows[i][j]);

	// betweenness (Brandes, unweighted, links as the route file gives them)
	std::vector<std::vector<int> > adj(n);
	for (int i = 0; i < n; ++i)
	{
		for (int l : *(*nodes)[i]->getNodeLinks())
		{
			if (l >= 0 && l < n && l != i)
				adj[i].push_back(l);
		}
	}
	std::vector<double> cb(n, 0.0);
	for (int s = 0; s < n; ++s)
	{
		std::vector<int> order, dist(n, -1);
		std::vector<double> sigma(n, 0.0), delta(n, 0.0);
		std::vector<std::vector<int> > pred(n);
		std::vector<int> queue(1, s);
		dist[s] = 0;
		sigma[s] = 1.0;
		for (size_t q = 0; q < queue.size(); ++q)
		{
			const int v = queue[q];
			order.push_back(v);
			for (int w : adj[v])
			{
				if (dist[w] < 0)
				{
					dist[w] = dist[v] + 1;
					queue.push_back(w);
				}
				if (dist[w] == dist[v] + 1)
				{
					sigma[w] += sigma[v];
					pred[w].push_back(v);
				}
			}
		}
		for (auto it = order.rbegin(); it != order.rend(); ++it)
		{
			const int w = *it;
			for (int v : pred[w])
				delta[v] += sigma[v] / sigma[w] * (1.0 + delta[w]);
			if (w != s)
				cb[w] += delta[w];
		}
	}
	g.choke.assign(n, 0);
	for (int i = 0; i < n; ++i)
		g.choke[i] = (int)std::lround(cb[i]);
	return rays;
}

unsigned long long hashMap(const std::vector<uint8_t> &prof, const std::vector<uint8_t> &flags)
{
	unsigned long long h = 1469598103934665603ULL;
	for (uint8_t c : prof) { h ^= c; h *= 1099511628211ULL; }
	for (uint8_t c : flags) { h ^= c; h *= 1099511628211ULL; }
	for (uint8_t c : g.sees) { h ^= c; h *= 1099511628211ULL; }
	return h;
}

double msSince(std::chrono::steady_clock::time_point t0)
{
	return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
}

int threadCount()
{
	const int hw = (int)std::thread::hardware_concurrency();
	return std::max(1, envInt("OXCE_AI_COVERMAP_THREADS", hw > 1 ? hw - 1 : 1));
}

/// OXCE_AI_COVERMAP=2: every 16th standing tile's lines once more through the engine's own TileEngine::calculateLineVoxel.
/// A line the engine stops at a unit is not a mismatch (the map is terrain only). Main thread; reads only.
void checkAgainstEngine(SavedBattleGame *save, long long &lines, long long &units, long long &mismatch)
{
	TileEngine *te = save->getTileEngine();
	const std::vector<Uint16> *vox = save->getMod()->getVoxelData();
	int standing = 0;
	for (int z = 0; z < g.sz; ++z)
		for (int y = 0; y < g.sy; ++y)
			for (int x = 0; x < g.sx; ++x)
			{
				if (!(g.flags[index(x, y, z)] & AiCoverMap::F_STAND) || standing++ % 16 != 0)
					continue;
				const int bottom = z * 24 - save->getTile(Position(x, y, z))->getTerrainLevel();
				for (int side = 0; side < AiCoverMap::SIDES; ++side)
					for (int far = 0; far < AiCoverMap::SHOOTERS; ++far)
						for (int layer = 0; layer < AiCoverMap::LAYERS; ++layer)
							for (int off : OFFSETS)
							{
								Position a, b;
								lineEnds(x, y, z, bottom, side, far, layer, off, a, b);
								const VoxelType own = terrainLineVoxel(save, vox, a, b);
								const VoxelType eng = te->calculateLineVoxel(a, b, false, nullptr, nullptr);
								++lines;
								if (eng == V_UNIT)
									++units;
								else if (eng != own)
									++mismatch;
							}
			}
}

void build(SavedBattleGame *save)
{
	g = CoverState();
	g.save = save;
	g.sx = save->getMapSizeX();
	g.sy = save->getMapSizeY();
	g.sz = save->getMapSizeZ();
	const size_t tiles = (size_t)g.sx * g.sy * g.sz;
	g.prof.assign(tiles * BYTES_PER_TILE, 0);
	g.flags.assign(tiles, 0);
	const int threads = threadCount();

	auto t0 = std::chrono::steady_clock::now();
	const long long rays = computeAll(save, g.prof, g.flags, threads);
	const double tilesMs = msSince(t0);
	int standing = 0;
	for (uint8_t f : g.flags)
		standing += (f & AiCoverMap::F_STAND) ? 1 : 0;

	std::vector<Node*> *nodes = save->getNodes();
	g.nodes = (int)nodes->size();
	g.sees.assign(((size_t)g.nodes * g.nodes + 7) / 8, 0);
	t0 = std::chrono::steady_clock::now();
	const long long nodeRays = computeNodes(save, nodes, threads);
	const double nodesMs = msSince(t0);
	g.built = true;
	const unsigned long long hash = hashMap(g.prof, g.flags);

	std::ostringstream extra;
	if (AiCoverMap::mode() >= 2)
	{
		long long lines = 0, units = 0, mismatch = 0;
		checkAgainstEngine(save, lines, units, mismatch);
		std::vector<uint8_t> prof1(g.prof.size(), 0), flags1(g.flags.size(), 0);
		t0 = std::chrono::steady_clock::now();
		computeAll(save, prof1, flags1, 1);
		const double oneMs = msSince(t0);
		extra << ",\"checkLines\":" << lines << ",\"checkUnits\":" << units << ",\"checkMismatch\":" << mismatch
			<< ",\"oneThreadMs\":" << (long long)oneMs << ",\"oneThreadSame\":" << (prof1 == g.prof && flags1 == g.flags ? 1 : 0);
	}
	const size_t bytes = g.prof.size() + g.flags.size() + g.sees.size() + g.choke.size() * sizeof(int);
	Log(LOG_INFO) << "[AICOVER] {\"ev\":\"build\",\"turn\":" << save->getTurn() << ",\"x\":" << g.sx << ",\"y\":" << g.sy << ",\"z\":" << g.sz
		<< ",\"tiles\":" << tiles << ",\"standing\":" << standing << ",\"rays\":" << rays << ",\"ms\":" << (long long)tilesMs
		<< ",\"threads\":" << threads << ",\"nodes\":" << g.nodes << ",\"nodeRays\":" << nodeRays << ",\"nodeMs\":" << (long long)nodesMs
		<< ",\"bytes\":" << bytes << ",\"hash\":\"" << std::hex << hash << std::dec << "\"" << extra.str() << "}";
}

/// The tiles within 2 of a touched tile (one level up and down) and the node pairs whose line's box holds a touched tile.
void refresh(SavedBattleGame *save)
{
	auto t0 = std::chrono::steady_clock::now();
	std::set<int> cells;
	for (const Position &p : g.dirty)
		for (int dz = -1; dz <= 1; ++dz)
			for (int dy = -2; dy <= 2; ++dy)
				for (int dx = -2; dx <= 2; ++dx)
				{
					const int x = p.x + dx, y = p.y + dy, z = p.z + dz;
					if (x >= 0 && y >= 0 && z >= 0 && x < g.sx && y < g.sy && z < g.sz)
						cells.insert(index(x, y, z));
				}
	const std::vector<Uint16> *vox = save->getMod()->getVoxelData();
	long long rays = 0;
	for (int i : cells)
	{
		const int x = i % g.sx, y = (i / g.sx) % g.sy, z = i / (g.sx * g.sy);
		rays += computeTile(save, vox, x, y, z, &g.prof[(size_t)i * BYTES_PER_TILE], g.flags[i]);
	}
	std::vector<Node*> *nodes = save->getNodes();
	long long nodeRays = 0;
	int pairs = 0;
	for (int i = 0; i < g.nodes; ++i)
		for (int j = 0; j < g.nodes; ++j)
		{
			if (i == j)
				continue;
			const Position a = (*nodes)[i]->getPosition(), b = (*nodes)[j]->getPosition();
			bool hit = false;
			for (const Position &p : g.dirty)
			{
				if (p.x >= std::min(a.x, b.x) - 1 && p.x <= std::max(a.x, b.x) + 1 && p.y >= std::min(a.y, b.y) - 1
					&& p.y <= std::max(a.y, b.y) + 1 && p.z >= std::min(a.z, b.z) - 1 && p.z <= std::max(a.z, b.z) + 1)
				{
					hit = true;
					break;
				}
			}
			if (hit)
			{
				setSees(i, j, computeSees(save, vox, nodes, i, j, nodeRays));
				++pairs;
			}
		}
	Log(LOG_INFO) << "[AICOVER] {\"ev\":\"refresh\",\"turn\":" << save->getTurn() << ",\"touched\":" << g.dirty.size()
		<< ",\"cells\":" << cells.size() << ",\"rays\":" << rays << ",\"pairs\":" << pairs << ",\"nodeRays\":" << nodeRays
		<< ",\"ms\":" << (long long)msSince(t0) << "}";
	g.dirty.clear();
}

bool inMap(const Position &p)
{
	return g.built && p.x >= 0 && p.y >= 0 && p.z >= 0 && p.x < g.sx && p.y < g.sy && p.z < g.sz;
}

}

int AiCoverMap::mode()
{
#ifdef OXCE_AI_DEV
	static const int m = envInt("OXCE_AI_COVERMAP", 0);
	return m;
#else
	return 0;
#endif
}

void AiCoverMap::touch(const Position &pos)
{
	if (!g.built || g.overflow)
		return;
	if (g.dirty.size() >= DIRTY_CAP)
	{
		g.overflow = true;
		g.dirty.clear();
		return;
	}
	g.dirty.push_back(pos);
}

void AiCoverMap::update(SavedBattleGame *save)
{
	if (mode() == 0 || save->getMissionType() == "STR_BASE_DEFENSE")
		return;
	// a new battle, a new stage on the same battle (nextStage), or too many touched tiles: built anew
	if (!g.built || g.save != save || g.overflow || g.sx != save->getMapSizeX() || g.sy != save->getMapSizeY()
		|| g.sz != save->getMapSizeZ() || g.nodes != (int)save->getNodes()->size())
	{
		build(save);
		return;
	}
	if (!g.dirty.empty())
		refresh(save);
}

void AiCoverMap::reset(const SavedBattleGame *save)
{
	if (g.save == save)
		g = CoverState();
}

int AiCoverMap::cover(const Position &tile, int side, int layer, int far)
{
	if (!inMap(tile) || side < 0 || side >= SIDES || layer < 0 || layer >= LAYERS || far < 0 || far >= SHOOTERS)
		return -1;
	const int i = index(tile.x, tile.y, tile.z);
	if (!(g.flags[i] & F_STAND))
		return -1;
	const int vi = valueIndex(side, far, layer);
	return (g.prof[(size_t)i * BYTES_PER_TILE + (vi >> 2)] >> ((vi & 3) * 2)) & 3;
}

int AiCoverMap::flags(const Position &tile)
{
	return inMap(tile) ? g.flags[index(tile.x, tile.y, tile.z)] : 0;
}

bool AiCoverMap::nodeSees(int from, int to)
{
	if (!g.built || from < 0 || to < 0 || from >= g.nodes || to >= g.nodes)
		return false;
	const size_t bit = (size_t)from * g.nodes + to;
	return (g.sees[bit >> 3] >> (bit & 7)) & 1;
}

int AiCoverMap::choke(int node)
{
	return g.built && node >= 0 && node < g.nodes ? g.choke[node] : -1;
}

}
