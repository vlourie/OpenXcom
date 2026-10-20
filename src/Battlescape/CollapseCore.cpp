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
#include "CollapseCore.h"
#include <algorithm>

// Port of tools/collapse_pilot_export.py ref_eval (= model M0j4: collapse_v7c.evaluate7c after collapse_v7d.install(),
// i.e. M0j3 plus wall consoles, on the pilot buildings).
// Every set of the model is a byte array: cells of one level or parts of the block.

namespace OpenXcom
{

namespace
{

const int C_CONSOLE = 2;  // console from a support (collapse_v2 C)
const int LINTEL = 4;     // lintel over an opening (collapse_v2 LINTEL)
const int WALL_CONSOLE = 2; // wall console from one side (collapse_v7d WC, model M0j4)
const int NONE = -1;

/// Cell set of one level; anything outside the block is never in a set.
struct Cells
{
	int sx, sy;
	std::vector<uint8_t> v;
	Cells(int x, int y) : sx(x), sy(y), v(x * y, 0) { }
	bool has(int x, int y) const { return x >= 0 && y >= 0 && x < sx && y < sy && v[y * sx + x]; }
	void add(int x, int y) { if (x >= 0 && y >= 0 && x < sx && y < sy) v[y * sx + x] = 1; }
	void del(int x, int y) { if (x >= 0 && y >= 0 && x < sx && y < sy) v[y * sx + x] = 0; }
};

struct Level
{
	int sx, sy;
	std::vector<int> g[4];  // part index or NONE, by kind
	Level(int x, int y) : sx(x), sy(y) { for (auto &k : g) k.assign(x * y, NONE); }
	int at(int k, int x, int y) const { return (x >= 0 && y >= 0 && x < sx && y < sy) ? g[k][y * sx + x] : NONE; }
};

const int DIRS[4][2] = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 } };

/// Distance from xy along d to the first cell of ends, no further than lim, or NONE (collapse_v5.walk).
int walk(int x, int y, int dx, int dy, const Cells &med, const Cells &ends, const Cells &slab, bool bridge, int lim)
{
	int dist = 0;
	while (true)
	{
		x += dx;
		y += dy;
		dist += 1;
		if (dist > lim)
			return NONE;
		if (ends.has(x, y))
			return dist;
		if (med.has(x, y))
			continue;
		if (!bridge)
			return NONE;
		int run = 1;
		int cx = x, cy = y;
		while (true)
		{
			cx += dx;
			cy += dy;
			if (dist + run > lim)
				return NONE;
			if (med.has(cx, cy) || ends.has(cx, cy))
				break;
			run += 1;
		}
		// cover: (x-dx, y-dy), the empty run, (cx, cy); a parallel slab line must be whole over all of it
		const int px = dy, py = dx;
		bool covered = false;
		for (int s = 1; s >= -1 && !covered; s -= 2)
		{
			bool all = true;
			for (int a = -1; a <= run && all; ++a)
			{
				const int ax = x + dx * a, ay = y + dy * a;
				all = slab.has(ax + px * s, ay + py * s);
			}
			covered = all;
		}
		if (!covered)
			return NONE;
		x = cx;
		y = cy;
		dist += run;
		if (ends.has(x, y))
			return dist;
	}
}

int beamLen(int x, int y, const Cells &med, const Cells &ends, const Cells &slab, bool bridge, int lim)
{
	if (ends.has(x, y))
		return 0;
	int best = NONE;
	const int axes[2][2] = { { 1, 0 }, { 0, 1 } };
	for (auto &ax : axes)
	{
		const int a = walk(x, y, ax[0], ax[1], med, ends, slab, bridge, lim);
		if (a == NONE)
			continue;
		const int b = walk(x, y, -ax[0], -ax[1], med, ends, slab, bridge, lim);
		if (b == NONE)
			continue;
		best = (best == NONE) ? a + b : std::min(best, a + b);
	}
	return best;
}

/// Breadth-first distance over floors from start (collapse_v2.consoles).
std::vector<int> bfs(const Cells &start, const Cells &floors)
{
	const int sx = floors.sx, sy = floors.sy;
	std::vector<int> dist(sx * sy, NONE);
	std::vector<int> q;
	for (int i = 0; i < sx * sy; ++i)
		if (start.v[i]) { dist[i] = 0; q.push_back(i); }
	for (size_t h = 0; h < q.size(); ++h)
	{
		const int x = q[h] % sx, y = q[h] / sx;
		for (auto &d : DIRS)
		{
			const int nx = x + d[0], ny = y + d[1];
			if (floors.has(nx, ny) && dist[ny * sx + nx] == NONE)
			{
				dist[ny * sx + nx] = dist[q[h]] + 1;
				q.push_back(ny * sx + nx);
			}
		}
	}
	return dist;
}

}

void collapseEvaluate(const CollapseBlock &blk, const std::vector<uint8_t> &removed, std::vector<uint8_t> &held)
{
	const int sx = blk.sx, sy = blk.sy, sz = blk.sz, n = blk.nParts;
	const CollapsePart *P = blk.parts;
	auto bearing = [&](int i) { return (P[i].flags & CPF_BEARING) != 0; };
	auto furnOf = [&](int i) { return (P[i].flags & CPF_FURN) != 0; };

	std::vector<Level> lv(sz, Level(sx, sy));
	for (int i = 0; i < n; ++i)
		lv[P[i].z].g[P[i].kind][P[i].y * sx + P[i].x] = i;

	bool anyRemoved = false;
	for (int i = 0; i < n; ++i)
		anyRemoved = anyRemoved || removed[i];
	const bool X = anyRemoved;

	std::vector<uint8_t> sup(n, 0), carry(n, 0), fallenX(n, 0), nobase(n, 0);
	auto in = [&](const std::vector<uint8_t> &s, int i) { return i != NONE && s[i]; };

	for (int z = 0; z < sz; ++z)
	{
		const Level &L = lv[z];
		auto live = [&](int k, int x, int y) { const int i = L.at(k, x, y); return (i != NONE && !removed[i]) ? i : NONE; };
		if (z == 0)
		{
			for (int k = 0; k < 4; ++k)
				for (int c = 0; c < sx * sy; ++c)
				{
					const int i = L.g[k][c];
					if (i != NONE && !removed[i])
					{
						sup[i] = 1;
						if (bearing(i)) carry[i] = 1;
					}
				}
			continue;
		}
		const Level &B = lv[z - 1];
		Cells props(sx, sy), floors(sx, sy), mass(sx, sy), msup(sx, sy), direct(sx, sy), directB(sx, sy);
		for (int y = 0; y < sy; ++y)
			for (int x = 0; x < sx; ++x)
			{
				int i = B.at(1, x, y);
				if (in(carry, i)) { props.add(x, y); props.add(x - 1, y); }
				i = B.at(2, x, y);
				if (in(carry, i)) { props.add(x, y); props.add(x, y - 1); }
				i = B.at(3, x, y);
				if (in(carry, i))
				{
					props.add(x, y);
					if (P[i].nEdge > 0) props.add(x + P[i].e0x, y + P[i].e0y);
					if (P[i].nEdge > 1) props.add(x + P[i].e1x, y + P[i].e1y);
				}
				if (live(0, x, y) != NONE) floors.add(x, y);
				const int o = live(3, x, y);
				if (o != NONE && bearing(o)) mass.add(x, y);
			}
		std::vector<int> q;
		for (int y = 0; y < sy; ++y)
			for (int x = 0; x < sx; ++x)
				if (mass.has(x, y) && (in(carry, B.at(3, x, y)) || (floors.has(x, y) && props.has(x, y))))
				{
					msup.add(x, y);
					q.push_back(y * sx + x);
				}
		for (size_t h = 0; h < q.size(); ++h)
		{
			const int x = q[h] % sx, y = q[h] / sx;
			for (auto &d : DIRS)
			{
				const int nx = x + d[0], ny = y + d[1];
				if (mass.has(nx, ny) && !msup.has(nx, ny)) { msup.add(nx, ny); q.push_back(ny * sx + nx); }
			}
		}
		for (int y = 0; y < sy; ++y)
			for (int x = 0; x < sx; ++x)
				if (floors.has(x, y) && (props.has(x, y) || msup.has(x, y))) { direct.add(x, y); directB.add(x, y); }
		// Q: a floor between direct cells on both axes (one pass over the old set)
		{
			Cells old = directB;
			for (int y = 0; y < sy; ++y)
				for (int x = 0; x < sx; ++x)
					if (floors.has(x, y) && !old.has(x, y) &&
						(old.has(x + 1, y) || old.has(x - 1, y)) && (old.has(x, y + 1) || old.has(x, y - 1)))
						directB.add(x, y);
		}
		// slab (collapse_v6.slab_floors6 without ranch and half consoles)
		Cells slab(sx, sy), held2(sx, sy);
		auto fkey = [&](int x, int y) { return live(0, x, y); };
		for (int y = 0; y < sy; ++y)
			for (int x = 0; x < sx; ++x)
				if (floors.has(x, y) && !(P[fkey(x, y)].flags & CPF_LIGHT)) slab.add(x, y);
		held2 = directB;
		for (int pass = 0; pass < 2; ++pass)
		{
			const Cells base = held2;
			for (int y = 0; y < sy; ++y)
				for (int x = 0; x < sx; ++x)
				{
					if (!floors.has(x, y)) continue;
					const int lim = P[fkey(x, y)].limL;
					const int nl = beamLen(x, y, floors, base, slab, slab.has(x, y), lim);
					if (nl != NONE && nl <= lim) held2.add(x, y);
				}
		}
		Cells okf = held2;
		const std::vector<int> geoHeld = bfs(held2, floors);
		const std::vector<int> geoDir = bfs(directB, floors);
		for (int y = 0; y < sy; ++y)
			for (int x = 0; x < sx; ++x)
			{
				if (!floors.has(x, y) || held2.has(x, y)) continue;
				const int f = fkey(x, y);
				const int c = ((P[f].flags & CPF_CANOPY) && !(P[f].flags & CPF_POSTED)) ? 0 : C_CONSOLE;
				const int cell = y * sx + x;
				if (slab.has(x, y))
				{
					if (geoHeld[cell] != NONE && geoHeld[cell] <= c) { okf.add(x, y); continue; }
					for (auto &d : DIRS)
					{
						const int w = walk(x, y, d[0], d[1], floors, held2, slab, true, c);
						if (w != NONE && w <= c) { okf.add(x, y); break; }
					}
				}
				else if (geoDir[cell] != NONE && geoDir[cell] <= c)
				{
					okf.add(x, y);
				}
			}
		const Cells &strong = held2;
		// X: bearing parts whose part below carried in the intact block but carries no more
		if (X)
		{
			for (int k = 1; k < 4; ++k)
				for (int y = 0; y < sy; ++y)
					for (int x = 0; x < sx; ++x)
					{
						const int i = live(k, x, y);
						if (i == NONE || !bearing(i)) continue;
						const int u = B.at(k, x, y);
						if (u != NONE && (P[u].flags & CPF_CARRY0) && !carry[u]) nobase[i] = 1;
					}
			Cells tier(sx, sy);
			for (int y = 0; y < sy; ++y)
				for (int x = 0; x < sx; ++x)
				{
					if (!okf.has(x, y) || strong.has(x, y)) continue;
					const int o = live(3, x, y);
					const bool xFallO = o != NONE && nobase[o] && !msup.has(x, y) && !strong.has(x, y);
					if (xFallO || in(fallenX, B.at(3, x, y))) tier.add(x, y);
				}
			for (int c = 0; c < sx * sy; ++c)
				if (tier.v[c]) okf.v[c] = 0;
		}
		for (int y = 0; y < sy; ++y)
			for (int x = 0; x < sx; ++x)
				if (floors.has(x, y) && okf.has(x, y)) sup[fkey(x, y)] = 1;
		// lintels with corners (collapse_v6.lintels6)
		std::vector<uint8_t> lint(n, 0), cons(n, 0);
		{
			Cells base[3] = { Cells(sx, sy), Cells(sx, sy), Cells(sx, sy) };
			for (int k = 1; k <= 2; ++k)
				for (int y = 0; y < sy; ++y)
					for (int x = 0; x < sx; ++x)
					{
						const int i = live(k, x, y);
						if (i == NONE || !bearing(i)) continue;
						bool b = in(carry, B.at(k, x, y));
						if (!b)
							b = strong.has(x, y) || (k == 1 ? strong.has(x - 1, y) : strong.has(x, y - 1));
						if (b) base[k].add(x, y);
					}
			auto corner = [&](int k, int px, int py) {
				if (k == 1)
					return base[2].has(px - 1, py) || base[2].has(px, py);
				return base[1].has(px, py - 1) || base[1].has(px, py);
			};
			for (int k = 1; k <= 2; ++k)
			{
				const int dx = (k == 1) ? 0 : 1, dy = (k == 1) ? 1 : 0;
				for (int y = 0; y < sy; ++y)
					for (int x = 0; x < sx; ++x)
					{
						const int i = live(k, x, y);
						if (i == NONE) continue;
						if (in(carry, B.at(k, x, y)) || !bearing(i)) continue;
						int run = 1;
						bool ok = true;
						for (int sgn = 1; sgn >= -1 && ok; sgn -= 2)
						{
							int cx = x, cy = y;
							while (true)
							{
								const int px = sgn > 0 ? cx + dx : cx, py = sgn > 0 ? cy + dy : cy;
								if (corner(k, px, py))
									break;
								cx += dx * sgn;
								cy += dy * sgn;
								const int nk = live(k, cx, cy);
								if (nk == NONE || !bearing(nk)) { ok = false; break; }
								if (base[k].has(cx, cy))
									break;
								run += 1;
							}
						}
						if (ok && run <= LINTEL) lint[i] = 1;
					}
			}
			// wall consoles (collapse_v7d.wall_consoles): a run of up to WALL_CONSOLE bearing walls resting on a
			// base or a corner on at least one side holds, but carries nothing
			for (int k = 1; k <= 2; ++k)
			{
				const int dx = (k == 1) ? 0 : 1, dy = (k == 1) ? 1 : 0;
				for (int y = 0; y < sy; ++y)
					for (int x = 0; x < sx; ++x)
					{
						const int i = live(k, x, y);
						if (i == NONE) continue;
						if (lint[i] || in(carry, B.at(k, x, y)) || !bearing(i)) continue;
						int run = 1, anchored = 0;
						for (int sgn = 1; sgn >= -1; sgn -= 2)
						{
							int cx = x, cy = y;
							while (true)
							{
								const int px = sgn > 0 ? cx + dx : cx, py = sgn > 0 ? cy + dy : cy;
								if (corner(k, px, py)) { anchored += 1; break; }
								cx += dx * sgn;
								cy += dy * sgn;
								const int nk = live(k, cx, cy);
								if (nk == NONE || !bearing(nk)) break;
								if (base[k].has(cx, cy)) { anchored += 1; break; }
								run += 1;
							}
						}
						if (anchored >= 1 && run <= WALL_CONSOLE) cons[i] = 1;
					}
			}
			for (int i = 0; i < n; ++i)
				if (cons[i]) lint[i] = 1;
		}
		// walls (w: sides (x,y) (x-1,y); n: (x,y) (x,y-1))
		for (int k = 1; k <= 2; ++k)
			for (int y = 0; y < sy; ++y)
				for (int x = 0; x < sx; ++x)
				{
					const int i = live(k, x, y);
					if (i == NONE) continue;
					const int sx2 = (k == 1) ? x - 1 : x, sy2 = (k == 1) ? y : y - 1;
					const int u = B.at(k, x, y);
					int onObj = 0;
					if (in(carry, B.at(3, x, y))) onObj = P[i].contact;
					bool h;
					if (nobase[i])
						h = strong.has(x, y) || strong.has(sx2, sy2) || lint[i];
					else
						h = okf.has(x, y) || okf.has(sx2, sy2) || in(carry, u) || lint[i] || onObj > 0;
					// held by a wall console only: stands, but nothing rests on it
					const bool consOnly = cons[i] && !(okf.has(x, y) || okf.has(sx2, sy2) || in(carry, u) || onObj > 0);
					if (h)
					{
						sup[i] = 1;
						if (bearing(i) && !consOnly) carry[i] = 1;
					}
					else if (nobase[i])
					{
						fallenX[i] = 1;
					}
				}
		// objects
		Cells furn(sx, sy), fsup(sx, sy);
		for (int y = 0; y < sy; ++y)
			for (int x = 0; x < sx; ++x)
			{
				const int i = live(3, x, y);
				if (i != NONE && furnOf(i)) furn.add(x, y);
			}
		for (int y = 0; y < sy; ++y)
			for (int x = 0; x < sx; ++x)
			{
				const int i = live(3, x, y);
				if (i == NONE) continue;
				const int u = B.at(3, x, y);
				const int walls[4] = { live(1, x, y), live(1, x + 1, y), live(2, x, y), live(2, x, y + 1) };
				bool byWall = false;
				for (int w : walls)
					byWall = byWall || in(carry, w);
				byWall = byWall && (P[i].flags & CPF_ATTACH);
				bool h;
				if (nobase[i])
					h = msup.has(x, y) || strong.has(x, y);
				else
					h = okf.has(x, y) || msup.has(x, y) || in(carry, u) || (in(sup, u) && furnOf(u)) || byWall;
				if (h)
				{
					sup[i] = 1;
					if (bearing(i)) carry[i] = 1;
					if (furn.has(x, y)) fsup.add(x, y);
				}
				else if (nobase[i])
				{
					fallenX[i] = 1;
				}
			}
		q.clear();
		for (int y = 0; y < sy; ++y)
			for (int x = 0; x < sx; ++x)
			{
				const int i = live(3, x, y);
				if (fsup.has(x, y) || (i != NONE && sup[i] && bearing(i))) q.push_back(y * sx + x);
			}
		for (size_t h = 0; h < q.size(); ++h)
		{
			const int x = q[h] % sx, y = q[h] / sx;
			for (auto &d : DIRS)
			{
				const int nx = x + d[0], ny = y + d[1];
				if (furn.has(nx, ny) && !fsup.has(nx, ny))
				{
					fsup.add(nx, ny);
					sup[live(3, nx, ny)] = 1;
					q.push_back(ny * sx + nx);
				}
			}
		}
	}

	// tree branch D (collapse_v4.tree_hold4, tie all): a column holds as a chain from its base, a crown piece while
	// all its columns hold up to its need level; a part by a carrying wall of its own cell stays with the core
	if (blk.nTreeCols)
	{
		auto onWall = [&](int i) {
			const Level &L = lv[P[i].z];
			const int x = P[i].x, y = P[i].y;
			const int w[4] = { L.at(1, x, y), L.at(1, x + 1, y), L.at(2, x, y), L.at(2, x, y + 1) };
			for (int j : w)
				if (j != NONE && carry[j] && !removed[j]) return true;
			return false;
		};
		std::vector<int> heldTo(blk.nTreeCols);
		std::vector<uint8_t> treeHeld(n, 0), managed(n, 0);
		const int *t = blk.treeCols;
		for (int c = 0; c < blk.nTreeCols; ++c)
		{
			const int len = *t++;
			int top = -1;
			for (int z = 0; z < len; ++z)
			{
				const int i = t[z];
				if (top == z - 1 && !removed[i])
				{
					top = z;
					treeHeld[i] = 1;
				}
				if (z > 0 && !onWall(i)) managed[i] = 1;
			}
			heldTo[c] = top;
			t += len;
		}
		t = blk.crowns;
		for (int k = 0; k < blk.nCrowns; ++k)
		{
			const int i = t[0], need = t[1], nc = t[2];
			const int *cs = t + 3;
			t += 3 + nc;
			if (onWall(i)) continue;
			managed[i] = 1;
			if (removed[i]) continue;
			bool all = true;
			for (int j = 0; j < nc; ++j)
				all = all && heldTo[cs[j]] >= need;
			if (all) treeHeld[i] = 1;
		}
		for (int i = 0; i < n; ++i)
			if (managed[i]) sup[i] = treeHeld[i];
	}

	// marks v2 (collapse_v7c): SURFACE/ATTACHED hold while one of their targets holds
	held.assign(n, 0);
	for (int i = 0; i < n; ++i)
		held[i] = sup[i] && !(P[i].mark && !removed[i]);
	std::vector<int> pending;
	for (int i = 0; i < n; ++i)
	{
		if (!P[i].mark || removed[i]) continue;
		if (P[i].mark == 2)
		{
			if (sup[i]) held[i] = 1;
		}
		else
		{
			pending.push_back(i);
		}
	}
	bool changed = true;
	while (changed)
	{
		changed = false;
		for (int &i : pending)
		{
			if (i == NONE) continue;
			for (int t = 0; t < P[i].tCount; ++t)
			{
				const int tg = blk.targets[P[i].tOff + t];
				if (!removed[tg] && held[tg])
				{
					held[i] = 1;
					i = NONE;
					changed = true;
					break;
				}
			}
		}
	}
}

}
