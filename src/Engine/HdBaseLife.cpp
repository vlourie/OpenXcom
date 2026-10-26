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
#include "HdBaseLife.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <deque>
#include <utility>
#include "Logger.h"

namespace OpenXcom
{

namespace HdBaseLife
{

namespace
{

const float PI = 3.14159265f;
/// Walking speed, grid cells a second (46 pack pixels of 128, as the preview).
const float SPEED = 46.0f / 128.0f;
/// A walking phase every 5.5 pack pixels, PHASES of them to a stride.
const float STRIDE = 5.5f / 128.0f;
const int DIRS = 16, PHASES = 6;
/// At work (labwork.py, 23.10): the hands at HANDS places each, the body leant at LEANS, facing one of FACES sides.
const int HANDS = 4, LEANS = 3, POSES = HANDS * HANDS * LEANS, FACES = 4;
/// Supersampling of the figures, per side.
const int AA = 4;

enum Role { SCI, ENG, GAL, GAL2, GUARD, NURSE, ROLES };

/// Body and hair of a role, as base_scene_preview.py crew_stamps.
const float LOOKS[ROLES][2][3] = {
	{ { 0.22f, 0.30f, 0.42f }, { 0.35f, 0.22f, 0.15f } },   // scientist in steel blue: white was lost on the labs' light floors
	{ { 1.00f, 0.55f, 0.12f }, { 0.15f, 0.12f, 0.10f } },   // engineer in orange
	{ { 0.75f, 0.15f, 0.30f }, { 0.90f, 0.75f, 0.30f } },   // crew
	{ { 0.20f, 0.55f, 0.60f }, { 0.15f, 0.10f, 0.08f } },   // crew
	{ { 0.18f, 0.20f, 0.26f }, { 0.55f, 0.30f, 0.15f } },   // guard
	{ { 0.55f, 0.90f, 0.75f }, { 0.95f, 0.85f, 0.60f } },   // nurse
};
const float SKIN[3] = { 226 / 255.0f, 180 / 255.0f, 150 / 255.0f };
/// The figure's shadow in screen units, down and right of it: x, y, radii, opacity - a wide faint oval and a
/// denser one inside it for a soft edge
const float SHADOW[2][5] = { { 1.9f, 2.1f, 4.4f, 4.6f, 0.20f }, { 1.6f, 1.8f, 3.4f, 3.8f, 0.32f } };

struct Point
{
	float x, y;                       ///< grid cells
};

struct Agent
{
	Role role = SCI;
	int job = 0;                      ///< Place bits of where it works
	bool nightShift = false;
	int homeX = 0, homeY = 0, cellX = 0, cellY = 0;
	Point pos = { 0, 0 };
	std::vector<Point> path;
	size_t next = 0;
	float wait = 0;
	int dir = 0;
	float step = 0;
	bool asleep = false;
	int face = -1;                    ///< the side of the furniture it goes to work at (0 right, 1 down...), -1 none
	bool atWork = false;              ///< stands there working with its hands
	int spotX = -1, spotY = -1;       ///< the square it works at or goes to
	float hands = 6;                  ///< how fast its hands go
	int craft = -1;                   ///< a hangar hand: the craft (Plan::crafts) it works at
	bool carry = false;               ///< a loader on its way to the craft with a box of ammunition

	bool walking() const { return next < path.size(); }
};

struct Crew
{
	Uint32 key = 0;
	bool made = false;
	std::vector<Agent> agents;
	Uint32 last = 0;
	Uint32 dice = 1;

	/// The crew's own dice, 0..1.
	float roll()
	{
		dice = dice * 1664525u + 1013904223u;
		return (dice >> 8) * (1.0f / 16777216.0f);
	}
};

Crew crew;

/// The figures for one cell size: premultiplied RGBA, [role][dir][phase][size x size].
struct Stamps
{
	int cell = 0, size = 0;
	std::vector<float> rgba;
	std::vector<float> work;          ///< [scientist, engineer][face][pose][size x size]

	const float *at(int role, int dir, int phase) const
	{
		return &rgba[(size_t)((role * DIRS + dir) * PHASES + phase) * size * size * 4];
	}
	const float *atWork(int role, int face, int pose) const
	{
		return &work[(size_t)(((role == ENG ? 1 : 0) * FACES + face) * POSES + pose) * size * size * 4];
	}
};

Stamps stamps;

struct Oval
{
	float x, y, rx, ry;
	float col[3];
	float a;
};

/// Draws the figures seen from above (facing +x before turning): shadow, arms swinging with the step,
/// body, the head's hair and the face forward - the shapes of the preview, rasterised for this size.
void makeStamps(int cell)
{
	if (stamps.cell == cell)
	{
		return;
	}
	stamps.cell = cell;
	// the preview's shapes 1.45 times its size (21 pixels and 1.35 to a unit at 128 to a cell): in the game the
	// base is 768 pixels on a full HD screen, and figures as small as the film's were specks there
	const int S = std::max(7, (int)std::lround(31.0f * cell / 128.0f));
	const float ppu = 1.95f * cell / 128.0f;
	stamps.size = S;
	auto raster = [&](const Oval *ovals, int count, float ang, float *out)
	{
		const float ca = std::cos(ang), sa = std::sin(ang);
		for (int py = 0; py < S; ++py)
		{
			for (int px = 0; px < S; ++px)
			{
				float sum[4] = { 0, 0, 0, 0 };
				for (int sy = 0; sy < AA; ++sy)
				{
					for (int sx = 0; sx < AA; ++sx)
					{
						const float ux = (px + (sx + 0.5f) / AA - S / 2.0f) / ppu;
						const float uy = (py + (sy + 0.5f) / AA - S / 2.0f) / ppu;
						// into the figure's own frame: it faces the direction `ang` on the screen
						const float fx = ux * ca + uy * sa, fy = -ux * sa + uy * ca;
						float c[4] = { 0, 0, 0, 0 };
						// the shadow on the screen, whichever way it faces: light from the top left, a soft edge
						for (const float (&s)[5] : SHADOW)
						{
							const float ex = (ux - s[0]) / s[2], ey = (uy - s[1]) / s[3];
							if (ex * ex + ey * ey <= 1)
							{
								c[3] = s[4] + c[3] * (1 - s[4]);
							}
						}
						for (int n = 0; n < count; ++n)
						{
							const Oval &o = ovals[n];
							const float ex = (fx - o.x) / o.rx, ey = (fy - o.y) / o.ry;
							if (ex * ex + ey * ey <= 1)
							{
								for (int i = 0; i < 3; ++i)
								{
									c[i] = o.col[i] * o.a + c[i] * (1 - o.a);
								}
								c[3] = o.a + c[3] * (1 - o.a);
							}
						}
						for (int i = 0; i < 4; ++i)
						{
							sum[i] += c[i];
						}
					}
				}
				for (int i = 0; i < 4; ++i)
				{
					out[(py * S + px) * 4 + i] = sum[i] / (AA * AA);
				}
			}
		}
	};
	stamps.rgba.assign((size_t)ROLES * DIRS * PHASES * S * S * 4, 0.0f);
	for (int role = 0; role < ROLES; ++role)
	{
		for (int ph = 0; ph < PHASES; ++ph)
		{
			const float swing = std::sin(ph / (float)PHASES * 2 * PI) * 1.6f;
			const Oval ovals[] = {
				{ swing, -3.3f, 1.2f, 1.1f, { SKIN[0], SKIN[1], SKIN[2] }, 1 },
				{ -swing, 3.3f, 1.2f, 1.1f, { SKIN[0], SKIN[1], SKIN[2] }, 1 },
				{ 0, 0, 2.2f, 3.5f, { LOOKS[role][0][0], LOOKS[role][0][1], LOOKS[role][0][2] }, 1 },
				{ 0.7f, 0, 1.6f, 1.6f, { LOOKS[role][1][0], LOOKS[role][1][1], LOOKS[role][1][2] }, 1 },
				{ 1.5f, 0, 0.7f, 0.9f, { SKIN[0], SKIN[1], SKIN[2] }, 1 },
			};
			for (int dir = 0; dir < DIRS; ++dir)
			{
				raster(ovals, 5, dir * 2 * PI / DIRS, const_cast<float*>(stamps.at(role, dir, ph)));
			}
		}
	}
	// at work: the hands forward over the table, each turning something in its own time, the head bent to
	// the work and the body swaying a little (labwork.py work_ovals)
	stamps.work.assign((size_t)2 * FACES * POSES * S * S * 4, 0.0f);
	for (int r = 0; r < 2; ++r)
	{
		const Role role = r ? ENG : SCI;
		for (int pose = 0; pose < POSES; ++pose)
		{
			const float l = (pose % HANDS) * 2.0f / (HANDS - 1) - 1;
			const float h = (pose / HANDS % HANDS) * 2.0f / (HANDS - 1) - 1;
			const float lean = (pose / (HANDS * HANDS) - 1) * 0.25f;
			const Oval ovals[] = {
				{ 2.9f + 0.45f * l, -1.7f + 0.35f * h, 1.15f, 1.05f, { SKIN[0], SKIN[1], SKIN[2] }, 1 },
				{ 2.9f + 0.45f * h, 1.7f - 0.35f * l, 1.15f, 1.05f, { SKIN[0], SKIN[1], SKIN[2] }, 1 },
				{ lean, 0, 2.2f, 3.5f, { LOOKS[role][0][0], LOOKS[role][0][1], LOOKS[role][0][2] }, 1 },
				{ 0.95f + lean, 0, 1.6f, 1.6f, { LOOKS[role][1][0], LOOKS[role][1][1], LOOKS[role][1][2] }, 1 },
				{ 1.75f + lean, 0, 0.7f, 0.9f, { SKIN[0], SKIN[1], SKIN[2] }, 1 },
			};
			for (int face = 0; face < FACES; ++face)
			{
				raster(ovals, 5, face * PI / 2, const_cast<float*>(stamps.atWork(role, face, pose)));
			}
		}
	}
}

typedef std::pair<int, int> Cell;

/// The walking grid, SUB squares to a cell.
const int G = SIZE * SUB;

bool hasFloor(const Plan &plan, int x, int y)
{
	for (int sx = 0; sx < SUB; ++sx)
	{
		for (int sy = 0; sy < SUB; ++sy)
		{
			if (plan.walk[x * SUB + sx][y * SUB + sy])
			{
				return true;
			}
		}
	}
	return false;
}

std::vector<Cell> cellsWith(const Plan &plan, int bits)
{
	std::vector<Cell> out;
	for (int x = 0; x < SIZE; ++x)
	{
		for (int y = 0; y < SIZE; ++y)
		{
			if (plan.facility[x][y] && (plan.place[x][y] & bits) && hasFloor(plan, x, y))
			{
				out.push_back(Cell(x, y));
			}
		}
	}
	return out;
}

int facilityAt(const Plan &plan, int gx, int gy)
{
	return gx < 0 || gy < 0 || gx >= G || gy >= G ? 0 : plan.facility[gx / SUB][gy / SUB];
}

/// The two middle squares of a side where it meets another facility: the doorway the connecting tube
/// comes to, walkable though the picture has its wall there.
bool doorway(const Plan &plan, int gx, int gy)
{
	const int lx = gx % SUB, ly = gy % SUB, mid0 = SUB / 2 - 1, mid1 = SUB / 2;
	const int here = facilityAt(plan, gx, gy);
	if ((ly == mid0 || ly == mid1) && (lx == 0 || lx == SUB - 1))
	{
		const int other = facilityAt(plan, gx + (lx == 0 ? -1 : 1), gy);
		return other && other != here;
	}
	if ((lx == mid0 || lx == mid1) && (ly == 0 || ly == SUB - 1))
	{
		const int other = facilityAt(plan, gx, gy + (ly == 0 ? -1 : 1));
		return other && other != here;
	}
	return false;
}

bool walkable(const Plan &plan, int gx, int gy)
{
	return facilityAt(plan, gx, gy) && (plan.walk[gx][gy] || doorway(plan, gx, gy)) && !plan.hull[gx][gy];
}

/// May the crew step from square a to its neighbour b: over the floor, from one facility to another only
/// straight through a doorway, no corners cut past furniture.
bool canStep(const Plan &plan, int ax, int ay, int bx, int by)
{
	if (!walkable(plan, bx, by))
	{
		return false;
	}
	if (facilityAt(plan, ax, ay) != facilityAt(plan, bx, by))
	{
		return (ax == bx || ay == by) && doorway(plan, ax, ay) && doorway(plan, bx, by);
	}
	return ax == bx || ay == by || (walkable(plan, ax, by) && walkable(plan, bx, ay));
}

/// The squares from a to b over the floor, a and b included; empty when b cannot be reached.
std::vector<Cell> route(const Plan &plan, Cell a, Cell b)
{
	static short prev[G * G];
	static bool seen[G * G];
	std::fill(seen, seen + G * G, false);
	std::deque<Cell> queue;
	queue.push_back(a);
	seen[a.first * G + a.second] = true;
	while (!queue.empty() && !seen[b.first * G + b.second])
	{
		const Cell c = queue.front();
		queue.pop_front();
		for (int dx = -1; dx <= 1; ++dx)
		{
			for (int dy = -1; dy <= 1; ++dy)
			{
				const int x = c.first + dx, y = c.second + dy;
				if ((dx || dy) && x >= 0 && y >= 0 && x < G && y < G && !seen[x * G + y] && canStep(plan, c.first, c.second, x, y))
				{
					seen[x * G + y] = true;
					prev[x * G + y] = (short)(c.first * G + c.second);
					queue.push_back(Cell(x, y));
				}
			}
		}
	}
	std::vector<Cell> out;
	if (!seen[b.first * G + b.second])
	{
		return out;
	}
	out.push_back(b);
	while (out.back() != a)
	{
		const int i = prev[out.back().first * G + out.back().second];
		out.push_back(Cell(i / G, i % G));
	}
	std::reverse(out.begin(), out.end());
	return out;
}

/// The square of the walking grid under a point.
Cell squareOf(Point p)
{
	return Cell(std::min(G - 1, std::max(0, (int)(p.x * SUB))), std::min(G - 1, std::max(0, (int)(p.y * SUB))));
}

/// A place to stand in a cell: one of its floor squares.
Cell spotSquare(const Plan &plan, Cell c)
{
	std::vector<Cell> free;
	for (int sx = 0; sx < SUB; ++sx)
	{
		for (int sy = 0; sy < SUB; ++sy)
		{
			if (plan.walk[c.first * SUB + sx][c.second * SUB + sy] && !plan.hull[c.first * SUB + sx][c.second * SUB + sy])
			{
				free.push_back(Cell(c.first * SUB + sx, c.second * SUB + sy));
			}
		}
	}
	if (free.empty())
	{
		return Cell(c.first * SUB + SUB / 2, c.second * SUB + SUB / 2);
	}
	return free[std::min(free.size() - 1, (size_t)(crew.roll() * free.size()))];
}

Point centre(Cell square)
{
	return { (square.first + 0.5f) / SUB, (square.second + 0.5f) / SUB };
}

Cell pick(const std::vector<Cell> &cells, Cell otherwise)
{
	return cells.empty() ? otherwise : cells[std::min(cells.size() - 1, (size_t)(crew.roll() * cells.size()))];
}

/// Does it work with its hands now: a scientist in a lab while the base researches, an engineer in a workshop
/// while it builds - by day, or on the night shift.
bool works(const Agent &a, const Plan &plan, float night)
{
	if (a.craft >= 0)
	{
		return true;
	}
	if (night > 0.5f && !a.nightShift)
	{
		return false;
	}
	return (a.role == SCI && a.job == LAB && plan.researching) || (a.role == ENG && a.job == WORK && plan.producing);
}

/// A place to work at in cell `c`: a floor square next to furniture (inside the room, not its wall), facing it,
/// and not next to where another of the crew works. With `near`, one of the three nearest to it but not it - a
/// step to the next table.
bool hullSpot(const Plan &plan, const Agent &self, const Cell *near, Cell &square, int &face);

bool workSpot(const Plan &plan, Cell c, const Agent &self, const Cell *near, Cell &square, int &face)
{
	static const int SIDE[FACES][2] = { { 1, 0 }, { 0, 1 }, { -1, 0 }, { 0, -1 } };
	if (self.craft >= 0)
	{
		return hullSpot(plan, self, near, square, face);
	}
	struct Spot
	{
		Cell square;
		int face, dist;
	};
	std::vector<Spot> spots;
	for (int sx = 0; sx < SUB; ++sx)
	{
		for (int sy = 0; sy < SUB; ++sy)
		{
			const int gx = c.first * SUB + sx, gy = c.second * SUB + sy;
			if (!plan.walk[gx][gy])
			{
				continue;
			}
			bool taken = false;
			for (const Agent &o : crew.agents)
			{
				taken = taken || (&o != &self && o.spotX >= 0 && std::abs(o.spotX - gx) <= 1 && std::abs(o.spotY - gy) <= 1);
			}
			const int dist = near ? std::max(std::abs(gx - near->first), std::abs(gy - near->second)) : 0;
			if (taken || (near && dist == 0))
			{
				continue;
			}
			for (int f = 0; f < FACES; ++f)
			{
				const int nx = sx + SIDE[f][0], ny = sy + SIDE[f][1];
				if (nx >= 1 && ny >= 1 && nx <= SUB - 2 && ny <= SUB - 2 && !plan.walk[c.first * SUB + nx][c.second * SUB + ny])
				{
					spots.push_back({ Cell(gx, gy), f, dist });
				}
			}
		}
	}
	if (spots.empty())
	{
		return false;
	}
	size_t choice = spots.size();
	if (near)
	{
		std::stable_sort(spots.begin(), spots.end(), [](const Spot &p, const Spot &q) { return p.dist < q.dist; });
		choice = std::min<size_t>(3, spots.size());
	}
	const Spot &s = spots[std::min(choice - 1, (size_t)(crew.roll() * choice))];
	square = s.square;
	face = s.face;
	return true;
}

/// Sets the agent walking over these squares (from where it stands): turning points only.
/// A place for a hangar hand: on the floor at the edge of its craft, facing the hull - or, for a loader going for
/// the next box, by the hangar's wall away from the craft. With `near`, one of the three nearest to it but not it.
bool hullSpot(const Plan &plan, const Agent &self, const Cell *near, Cell &square, int &face)
{
	static const int SIDE[FACES][2] = { { 1, 0 }, { 0, 1 }, { -1, 0 }, { 0, -1 } };
	const unsigned char mine = (unsigned char)(self.craft + 1);
	const bool pile = plan.crafts[self.craft].status == CRAFT_REARMING && !self.carry;
	float mx = 0, my = 0;
	int count = 0;
	for (int gx = 0; gx < G; ++gx)
	{
		for (int gy = 0; gy < G; ++gy)
		{
			if (plan.hull[gx][gy] == mine)
			{
				mx += gx;
				my += gy;
				++count;
			}
		}
	}
	if (!count)
	{
		return false;
	}
	mx /= count;
	my /= count;
	const int hangar = facilityAt(plan, (int)mx, (int)my);
	struct Spot
	{
		Cell square;
		int face, dist;
	};
	std::vector<Spot> spots;
	for (int gx = 0; gx < G; ++gx)
	{
		for (int gy = 0; gy < G; ++gy)
		{
			if (!walkable(plan, gx, gy) || facilityAt(plan, gx, gy) != hangar)
			{
				continue;
			}
			bool taken = false;
			for (const Agent &o : crew.agents)
			{
				taken = taken || (&o != &self && o.spotX >= 0 && std::abs(o.spotX - gx) <= 1 && std::abs(o.spotY - gy) <= 1);
			}
			const int dist = near ? std::max(std::abs(gx - near->first), std::abs(gy - near->second)) : 0;
			if (taken || (near && dist == 0) || (pile && std::hypot(gx - mx, gy - my) < 5.5f))
			{
				continue;
			}
			for (int f = 0; f < FACES; ++f)
			{
				const int nx = gx + SIDE[f][0], ny = gy + SIDE[f][1];
				if (nx < 0 || ny < 0 || nx >= G || ny >= G)
				{
					continue;
				}
				if (pile ? !plan.walk[nx][ny] && !plan.hull[nx][ny] && facilityAt(plan, nx, ny) == hangar : plan.hull[nx][ny] == mine)
				{
					spots.push_back({ Cell(gx, gy), f, dist });
				}
			}
		}
	}
	if (spots.empty())
	{
		return false;
	}
	size_t choice = spots.size();
	if (near)
	{
		std::stable_sort(spots.begin(), spots.end(), [](const Spot &p, const Spot &q) { return p.dist < q.dist; });
		choice = std::min<size_t>(3, spots.size());
	}
	const Spot &s = spots[std::min(choice - 1, (size_t)(crew.roll() * choice))];
	square = s.square;
	face = s.face;
	return true;
}

void walkOver(Agent &a, const std::vector<Cell> &squares)
{
	a.path.clear();
	a.next = 0;
	for (size_t i = 1; i < squares.size(); ++i)
	{
		const bool last = i + 1 == squares.size();
		if (!last)
		{
			const Cell &p = squares[i - 1], &c = squares[i], &n = squares[i + 1];
			if (c.first - p.first == n.first - c.first && c.second - p.second == n.second - c.second)
			{
				continue;
			}
		}
		a.path.push_back(centre(squares[i]));
	}
}

Uint32 keyOf(const Plan &plan, int sci, int eng, int sol)
{
	Uint32 h = plan.seed * 2654435761u + 1;
	for (int x = 0; x < SIZE; ++x)
	{
		for (int y = 0; y < SIZE; ++y)
		{
			h = (h ^ (Uint32)plan.facility[x][y]) * 16777619u;
			h = (h ^ (Uint32)plan.place[x][y]) * 16777619u;
		}
	}
	for (const Plan::Craft &c : plan.crafts)
	{
		h = (h ^ (Uint32)(c.status + 1)) * 16777619u;
	}
	return ((h ^ (Uint32)sci) * 16777619u ^ (Uint32)eng) * 16777619u ^ (Uint32)sol;
}

/// The crew of this base: how many of each walk about, from the base's own numbers.
void makeCrew(const Plan &plan, Uint32 key, float night)
{
	crew = Crew();
	crew.key = key;
	crew.made = true;
	crew.dice = key | 1;
	const std::vector<Cell> floor = cellsWith(plan, ~0);
	if (floor.empty())
	{
		return;
	}
	std::vector<Cell> homes = cellsWith(plan, HOME);
	if (homes.empty())
	{
		homes = floor;
	}
	auto add = [&](Role role, int job, bool nightShift)
	{
		Agent a;
		a.role = role;
		a.job = job;
		a.nightShift = nightShift;
		const Cell home = homes[crew.agents.size() % homes.size()];
		a.homeX = home.first;
		a.homeY = home.second;
		const bool sleeping = night > 0.6f && !nightShift;
		const Cell start = sleeping ? home : pick(cellsWith(plan, job), home);
		a.cellX = start.first;
		a.cellY = start.second;
		a.pos = centre(spotSquare(plan, start));
		a.wait = crew.roll() * 3;
		a.dir = (int)(crew.roll() * DIRS) % DIRS;
		a.asleep = sleeping;
		a.hands = 5.0f + 2.0f * crew.roll();
		// at work already when the screen opens
		Cell square;
		int face;
		if (!sleeping && works(a, plan, night) && workSpot(plan, start, a, nullptr, square, face))
		{
			a.pos = centre(square);
			a.spotX = square.first;
			a.spotY = square.second;
			a.face = face;
			a.atWork = true;
			a.dir = face * DIRS / FACES;
			a.wait = crew.roll() * 6;
		}
		crew.agents.push_back(a);
	};
	const bool labs = !cellsWith(plan, LAB).empty(), works = !cellsWith(plan, WORK).empty();
	const int sci = labs && plan.scientists > 0 ? std::min(6, std::max(1, (plan.scientists + 9) / 10)) : 0;
	const int eng = works && plan.engineers > 0 ? std::min(5, std::max(1, (plan.engineers + 9) / 10)) : 0;
	const int sol = plan.soldiers > 0 ? std::min(6, std::max(1, (plan.soldiers + 4) / 5)) : 0;
	for (int i = 0; i < sci; ++i)
	{
		add(SCI, LAB, false);
	}
	for (int i = 0; i < eng; ++i)
	{
		add(ENG, WORK, i == 0);
	}
	for (int i = 0; i < sol; ++i)
	{
		add(i % 2 ? GAL2 : GAL, GYM | STORE | HANGAR | OTHER, false);
	}
	if (!cellsWith(plan, PRISON).empty())
	{
		add(GUARD, ~0, true);
	}
	if (!cellsWith(plan, MED).empty())
	{
		add(NURSE, MED, false);
	}
	// two builders on every site, day and night
	const std::vector<Cell> sites = cellsWith(plan, BUILD);
	for (size_t i = 0; i < std::min<size_t>(6, sites.size() * 2); ++i)
	{
		add(ENG, BUILD, true);
	}
	// the hangar hands by the craft's state, day and night: two welders at a craft under repair, two loaders at one
	// rearming, one with the fuel hose at one refuelling
	for (size_t c = 0; c < plan.crafts.size() && !cellsWith(plan, HANGAR).empty(); ++c)
	{
		const int state = plan.crafts[c].status;
		const int hands = state == CRAFT_REPAIRS || state == CRAFT_REARMING ? 2 : state == CRAFT_BUSY ? 1 : 0;
		for (int i = 0; i < hands; ++i)
		{
			Agent a;
			a.role = ENG;
			a.job = HANGAR;
			a.nightShift = true;
			a.craft = (int)c;
			a.carry = state == CRAFT_REARMING && i == 0;
			a.hands = 5.0f + 2.0f * crew.roll();
			a.dir = (int)(crew.roll() * DIRS) % DIRS;
			Cell square;
			int face;
			if (!hullSpot(plan, a, nullptr, square, face))
			{
				continue;
			}
			a.homeX = a.cellX = square.first / SUB;
			a.homeY = a.cellY = square.second / SUB;
			a.pos = centre(square);
			a.spotX = square.first;
			a.spotY = square.second;
			a.face = face;
			a.atWork = true;
			a.dir = face * DIRS / FACES;
			a.wait = crew.roll() * 4;
			crew.agents.push_back(a);
		}
	}
}

/// Where an agent goes next: to work, home at night, about the base when there is no work.
/// Does it carry the ammunition of a rearming craft to and fro?
bool loader(const Agent &a, const Plan &plan)
{
	return a.craft >= 0 && plan.crafts[a.craft].status == CRAFT_REARMING;
}

void choose(Agent &a, const Plan &plan, float night)
{
	const Cell home(a.homeX, a.homeY);
	Cell target = home;
	const bool idle = (a.role == SCI && !plan.researching) || (a.role == ENG && !plan.producing);
	if (night > 0.5f && !a.nightShift)
	{
		target = home;
	}
	else if (a.role == GUARD)
	{
		target = pick(cellsWith(plan, ~0), home);
	}
	else if (idle)
	{
		target = crew.roll() < 0.5f ? home : pick(cellsWith(plan, GYM | STORE | OTHER), home);
	}
	else
	{
		target = pick(cellsWith(plan, a.job), home);
	}
	a.path.clear();
	a.next = 0;
	a.atWork = false;
	a.face = -1;
	a.spotX = a.spotY = -1;
	// over the floor squares to a free square of the target - to work, to a table of it: a few tries, as
	// furniture cuts a room in parts and not every table can be reached from where it stands
	std::vector<Cell> squares;
	if (works(a, plan, night))
	{
		for (int tries = 0; tries < 8 && squares.empty(); ++tries)
		{
			Cell spot;
			int face;
			if (tries > 0)
			{
				target = pick(cellsWith(plan, a.job), home);
			}
			if ((plan.place[target.first][target.second] & a.job) && workSpot(plan, target, a, nullptr, spot, face))
			{
				squares = route(plan, squareOf(a.pos), spot);
				a.face = face;
				a.spotX = spot.first;
				a.spotY = spot.second;
			}
		}
	}
	if (squares.empty())
	{
		a.face = -1;
		a.spotX = a.spotY = -1;
		squares = route(plan, squareOf(a.pos), spotSquare(plan, target));
	}
	if (squares.empty())
	{
		// cut off by furniture: stay and think again later
		a.wait = 2.0f + crew.roll() * 3.0f;
		a.face = -1;
		a.spotX = a.spotY = -1;
		return;
	}
	walkOver(a, squares);
	a.cellX = target.first;
	a.cellY = target.second;
	a.asleep = false;
	if (!a.walking())
	{
		// already there (a room of one floor square): no walk, arrives at once
		a.wait = 2.5f + crew.roll() * 3.5f;
		if (a.face >= 0)
		{
			a.atWork = true;
			a.wait = loader(a, plan) ? 2.0f + crew.roll() : 6.0f + crew.roll() * 4.0f;
			a.dir = a.face * DIRS / FACES;
		}
	}
}

void move(Agent &a, const Plan &plan, float night, float dt)
{
	if (a.walking())
	{
		const Point &to = a.path[a.next];
		const float dx = to.x - a.pos.x, dy = to.y - a.pos.y;
		const float d = std::sqrt(dx * dx + dy * dy), v = SPEED * dt;
		if (d <= v)
		{
			a.pos = to;
			++a.next;
		}
		else
		{
			a.pos.x += dx / d * v;
			a.pos.y += dy / d * v;
			a.dir = ((int)std::lround(std::atan2(dy, dx) / (2 * PI / DIRS)) % DIRS + DIRS) % DIRS;
			a.step += v / STRIDE;
		}
		if (!a.walking())
		{
			a.wait = 2.5f + crew.roll() * 3.5f;
			if (a.face >= 0)
			{
				// at the table: works at it 6-10 s; a loader puts the box down or takes the next in 2-3 s
				a.atWork = true;
				a.wait = loader(a, plan) ? 2.0f + crew.roll() : 6.0f + crew.roll() * 4.0f;
				a.dir = a.face * DIRS / FACES;
			}
		}
		return;
	}
	a.wait -= dt;
	if (a.wait <= 0 && loader(a, plan) && a.atWork)
	{
		// with the box to the craft, without it back to the pile
		a.carry = !a.carry;
		choose(a, plan, night);
	}
	else if (a.wait <= 0)
	{
		// mostly a step to the next table of the room, now and then elsewhere
		Cell square;
		int face;
		const Cell here(a.spotX, a.spotY);
		const bool wasAtWork = a.atWork;
		a.atWork = false;
		if (wasAtWork && works(a, plan, night) && crew.roll() < 0.75f && workSpot(plan, Cell(a.cellX, a.cellY), a, &here, square, face))
		{
			const std::vector<Cell> squares = route(plan, squareOf(a.pos), square);
			if (!squares.empty())
			{
				walkOver(a, squares);
				a.face = face;
				a.spotX = square.first;
				a.spotY = square.second;
				return;
			}
		}
		choose(a, plan, night);
	}
	if (night > 0.6f && !a.nightShift && a.cellX == a.homeX && a.cellY == a.homeY && !a.walking())
	{
		a.asleep = true;
	}
}

}

void draw(SDL_Surface *world, const Plan &plan, int ox, int oy, int cell, float night, Uint32 ms,
	std::vector<HdBaseScene::Placed> &lights)
{
	if (!world || world->format->BytesPerPixel != 4 || cell < 8)
	{
		return;
	}
	// OXCE_HD_BASE_PERF: the cost of the crew and who walks, every 60 frames into the log
	static const bool perf = std::getenv("OXCE_HD_BASE_PERF") != nullptr;
	const auto perfStart = std::chrono::steady_clock::now();
	const int sci = plan.scientists, eng = plan.engineers, sol = plan.soldiers;
	// a new base, a facility built or torn down, more hands: a new crew (counts in tens, so a hire
	// or two does not shuffle everybody)
	const Uint32 key = keyOf(plan, (sci + 9) / 10, (eng + 9) / 10, (sol + 4) / 5);
	float dt = 0;
	if (!crew.made || crew.key != key)
	{
		makeCrew(plan, key, night);
	}
	else if (ms >= crew.last && ms - crew.last < 1000)
	{
		// a long pause (another screen) is not caught up: the crew stands still meanwhile
		dt = std::min(0.1f, (ms - crew.last) / 1000.0f);
	}
	crew.last = ms;
	for (Agent &a : crew.agents)
	{
		move(a, plan, night, dt);
	}
	makeStamps(cell);
	const int S = stamps.size;
	const float s = cell / 128.0f;
	const SDL_Rect clip = world->clip_rect;
	const float t = (float)(ms % 3600000u) / 1000.0f;
	// a dot of `size` world pixels over the layer: mixed in by `a`, or added (sparks)
	auto dot = [&](float fx, float fy, int size, float r, float g, float b, float a, bool add)
	{
		const int x0 = (int)std::lround(fx - size / 2.0f), y0 = (int)std::lround(fy - size / 2.0f);
		const float col[3] = { r, g, b };
		for (int y = std::max(y0, (int)clip.y); y < std::min(y0 + size, clip.y + clip.h); ++y)
		{
			Uint32 *row = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch);
			for (int x = std::max(x0, (int)clip.x); x < std::min(x0 + size, clip.x + clip.w); ++x)
			{
				const Uint32 px = row[x];
				Uint32 out = px & 0xFF000000u;
				for (int c = 0; c < 3; ++c)
				{
					const int shift = 16 - 8 * c;
					const float was = ((px >> shift) & 0xFF) / 255.0f;
					const float v = add ? was + col[c] * a : was + (col[c] - was) * a;
					out |= (Uint32)std::lround(std::min(1.0f, std::max(0.0f, v)) * 255.0f) << shift;
				}
				row[x] = out;
			}
		}
	};
	const int thick = std::max(1, (int)std::lround(cell / 64.0f));
	const float ppu = 1.95f * cell / 128.0f;
	// the fuel hoses under the figures: from the garland of the hangar to whoever refuels, sagging to the floor
	for (const Agent &a : crew.agents)
	{
		if (a.craft < 0 || plan.crafts[a.craft].status != CRAFT_BUSY)
		{
			continue;
		}
		const float x0 = ox + plan.crafts[a.craft].fuelX * cell, y0 = oy + plan.crafts[a.craft].fuelY * cell;
		const float x1 = ox + a.pos.x * cell, y1 = oy + a.pos.y * cell;
		const float mx = (x0 + x1) / 2, my = (y0 + y1) / 2 + 8 * s;
		const int steps = (int)(std::hypot(x1 - x0, y1 - y0) / std::max(1.0f, thick * 0.7f)) + 2;
		for (int i = 0; i <= steps; ++i)
		{
			const float u = i / (float)steps, v = 1 - u;
			dot(v * v * x0 + 2 * u * v * mx + u * u * x1, v * v * y0 + 2 * u * v * my + u * u * y1, thick, 0.13f, 0.13f, 0.15f, 0.95f, false);
		}
	}
	for (size_t n = 0; n < crew.agents.size(); ++n)
	{
		const Agent &a = crew.agents[n];
		if (a.asleep)
		{
			continue;
		}
		float cx = ox + a.pos.x * cell, cy = oy + a.pos.y * cell;
		const int phase = a.walking() ? (int)a.step % PHASES : 0;
		const float *src = stamps.at(a.role, a.dir, phase);
		if (a.atWork && !a.walking())
		{
			// the hands going over the table in their own time, the body swaying (labwork.py work_ovals), a quarter
			// of a square towards the table
			const float seed = (float)(n * 7 + 11);
			auto level = [](float v, int count) { return std::min(count - 1, std::max(0, (int)((v + 1) * 0.5f * count))); };
			const int pose = level(std::sin(t * a.hands + seed), HANDS)
				+ HANDS * level(std::sin(t * a.hands * 0.83f + seed + 1.7f), HANDS)
				+ HANDS * HANDS * level(std::sin(t * 0.9f + seed), LEANS);
			src = stamps.atWork(a.role, a.face, pose);
			const float ang = a.face * PI / 2, ca = std::cos(ang), sa = std::sin(ang);
			cx += ca * 0.25f * cell / SUB;
			cy += sa * 0.25f * cell / SUB;
			// now and then something lights up in the hands: a test tube, a meter's screen, a soldering tip
			Uint32 h = ((Uint32)(t * 1.5f) * 374761393u) ^ ((Uint32)n * 668265263u) ^ crew.key;
			h = (h ^ (h >> 13)) * 1274126177u;
			if (a.craft < 0 && ((h ^ (h >> 16)) & 0xFFFF) > 0.75f * 0xFFFF)
			{
				static const float FLASH[4][3] = { { 0.4f, 1.0f, 0.9f }, { 0.6f, 1.0f, 0.4f }, { 1.0f, 0.7f, 0.3f }, { 1.0f, 0.85f, 0.55f } };
				const float *col = FLASH[a.role == ENG ? 3 : n % 3];
				const float reach = 3.6f * 1.95f * cell / 128.0f;
				HdBaseScene::Placed L;
				L.light.x = cx + ca * reach;
				L.light.y = cy + sa * reach;
				L.light.radius = 9 * s;
				L.light.kind = HdBaseScene::STEADY;
				L.light.r = col[0];
				L.light.g = col[1];
				L.light.b = col[2];
				L.scale = s;
				L.level = 2.0f;
				L.moving = true;
				lights.push_back(L);
			}
		}
		const int x0 = (int)std::lround(cx - S / 2.0f), y0 = (int)std::lround(cy - S / 2.0f);
		for (int y = std::max(0, clip.y - y0); y < S && y0 + y < clip.y + clip.h; ++y)
		{
			Uint32 *row = (Uint32*)((Uint8*)world->pixels + (size_t)(y0 + y) * world->pitch);
			for (int x = std::max(0, clip.x - x0); x < S && x0 + x < clip.x + clip.w; ++x)
			{
				const float *p = src + (y * S + x) * 4;
				if (p[3] <= 0.002f)
				{
					continue;
				}
				const Uint32 px = row[x0 + x];
				Uint32 out = px & 0xFF000000u;
				for (int c = 0; c < 3; ++c)
				{
					const int shift = 16 - 8 * c;
					const float v = p[c] + ((px >> shift) & 0xFF) / 255.0f * (1 - p[3]);
					out |= (Uint32)std::lround(std::min(1.0f, v) * 255.0f) << shift;
				}
				row[x0 + x] = out;
			}
		}
		const float aim = (a.atWork && !a.walking() ? a.face * DIRS / FACES : a.dir) * 2 * PI / DIRS;
		const float hx = cx + std::cos(aim) * 3.4f * ppu, hy = cy + std::sin(aim) * 3.4f * ppu;
		// a loader's box of ammunition in its hands, olive with a dark rim
		if (a.carry && (a.walking() || a.atWork))
		{
			const int side = std::max(3, (int)std::lround(3.8f * ppu));
			dot(hx, hy, side, 0.12f, 0.13f, 0.08f, 1.0f, false);
			dot(hx, hy, std::max(1, side - 2 * thick), 0.44f, 0.47f, 0.25f, 1.0f, false);
		}
		// a welder at a craft under repair: the arc in bursts, flickering, and sparks flying off it
		if (a.craft >= 0 && a.atWork && !a.walking() && plan.crafts[a.craft].status == CRAFT_REPAIRS)
		{
			auto hash = [&](Uint32 v)
			{
				v = (v ^ ((Uint32)n * 668265263u) ^ crew.key) * 2246822519u;
				return ((v ^ (v >> 15)) * 3266489917u >> 8) * (1.0f / 16777216.0f);
			};
			const float burst = hash((Uint32)(t / 1.3f) * 374761393u), flick = hash((Uint32)(t * 25.0f) * 2654435761u + 7);
			if (burst > 0.3f && flick > 0.2f)
			{
				HdBaseScene::Placed L;
				L.light.x = hx;
				L.light.y = hy;
				L.light.radius = 16 * s;
				L.light.kind = HdBaseScene::STEADY;
				L.light.r = 0.75f;
				L.light.g = 0.88f;
				L.light.b = 1.0f;
				L.scale = s;
				L.level = 1.6f + 0.8f * flick;
				L.moving = true;
				lights.push_back(L);
				dot(hx, hy, thick + 1, 0.9f, 0.95f, 1.0f, 1.0f, true);
				for (int i = 0; i < 7; ++i)
				{
					const float k0 = t / 0.45f + i / 7.0f + n * 0.37f, ph = k0 - std::floor(k0);
					const float dir = hash((Uint32)k0 * 2246822519u + (Uint32)i * 97u) * 2 * PI;
					const float reach = (8 + 10 * hash((Uint32)k0 * 3266489917u + (Uint32)i * 131u)) * s * ph;
					const float glow = 1 - ph;
					dot(hx + std::cos(dir) * reach, hy + std::sin(dir) * reach + 10 * s * ph * ph, thick,
						1.0f, 0.55f + 0.4f * glow, 0.2f + 0.5f * glow, glow, true);
				}
			}
		}
		// a lantern a little ahead of whoever walks at night
		if (night > 0.4f && a.walking())
		{
			const float ang = a.dir * 2 * PI / DIRS;
			HdBaseScene::Placed L;
			L.light.x = cx + std::cos(ang) * 10 * s;
			L.light.y = cy + std::sin(ang) * 10 * s;
			L.light.radius = 30 * s;
			L.light.kind = HdBaseScene::STEADY;
			L.light.r = 1.0f;
			L.light.g = 0.85f;
			L.light.b = 0.6f;
			L.scale = s;
			L.level = 0.8f * night;
			L.moving = true;
			lights.push_back(L);
		}
	}
	if (perf)
	{
		static double total = 0;
		static int frames = 0;
		total += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - perfStart).count();
		if (++frames == 60)
		{
			int walking = 0, asleep = 0, working = 0, hangar = 0, roles[ROLES] = {};
			for (const Agent &a : crew.agents)
			{
				walking += a.walking() ? 1 : 0;
				working += a.atWork && !a.walking() ? 1 : 0;
				hangar += a.craft >= 0 ? 1 : 0;
				asleep += a.asleep ? 1 : 0;
				++roles[a.role];
			}
			Log(LOG_INFO) << "HD base crew: " << total / frames << " ms per frame, " << crew.agents.size() << " figures ("
				<< roles[SCI] << " sci, " << roles[ENG] << " eng, " << roles[GAL] + roles[GAL2] << " crew, " << roles[GUARD]
				<< " guard, " << roles[NURSE] << " nurse), " << walking << " walking, " << working << " at work, " << hangar << " in hangars, " << asleep << " asleep; base "
				<< sci << " sci, " << eng << " eng, " << sol << " soldiers, research " << plan.researching
				<< ", production " << plan.producing;
			total = 0;
			frames = 0;
		}
	}
}

}

}
