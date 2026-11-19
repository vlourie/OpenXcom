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
#include "Map.h"
#include "MapHd.h"
#include "Camera.h"
#include "CollapsePilot.h"
#include "UnitSprite.h"
#include "ItemSprite.h"
#include "Pathfinding.h"
#include "TileEngine.h"
#include "Projectile.h"
#include "ProjectileFlyBState.h"
#include "Explosion.h"
#include "BattlescapeState.h"
#include "Particle.h"
#include "../Mod/Mod.h"
#include "../Engine/Action.h"
#include "../Engine/SurfaceSet.h"
#include "../Engine/Timer.h"
#include "../Engine/Language.h"
#include "../Engine/Palette.h"
#include "../Engine/Game.h"
#include "../Engine/Screen.h"
#include "../Engine/HdTest.h"
#include "../Engine/HdBattleHud.h"
#include "../Engine/HdBlit.h"
#include "../Engine/HdCanvas.h"
#include "../Engine/HdFx.h"
#include "../Engine/HdGentle.h"
#include "../Engine/HdGpuWorld.h"
#include "../Engine/HdKillCam.h"
#include "../Engine/HdLab.h"
#include "../Engine/HdSmoke.h"
#include "../Engine/HdShots.h"
#include "../Engine/HdFire.h"
#include "../Engine/HdSprites.h"
#include "../Engine/HdTurn.h"
#include "../Engine/HdTurnGroups.h"
#include "../Engine/HdUi.h"
#include "../Engine/HdWorkers.h"
#include <chrono>
#include <climits>
#include <cmath>
#include <map>
#include <sstream>
#include <unordered_set>
#include "../Engine/FileMap.h"
#include "../Engine/ShaderDraw.h"
#include "../Engine/ShaderMove.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/BattleItem.h"
#include "../Ufopaedia/Ufopaedia.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleInterface.h"
#include "../Mod/MapDataSet.h"
#include "../Mod/MapData.h"
#include "../Mod/Armor.h"
#include "../Mod/RuleEnviroEffects.h"
#include "BattlescapeMessage.h"
#include "AiProbe.h"
#include "../Savegame/SavedGame.h"
#include "../Interface/NumberText.h"
#include "../Interface/Text.h"
#include "../fmath.h"

namespace OpenXcom
{

/**
 * HD light: the color of the light falling on a tile. Every light layer has
 * a color (the ambient light is white by day and turns cool at night, fire is
 * warm, flares and lamps are yellowish, personal lights are cool white) and
 * the tile's color is their mix weighted by how much each contributes; it is
 * normalised so that a color only ever takes brightness away from channels.
 */
void Map::hdTintOf(const Tile *tile, float *tint) const
{
	static const float fire[3] = { 1.0f, 0.70f, 0.40f };
	static const float items[3] = { 1.0f, 0.94f, 0.80f };
	static const float units[3] = { 0.92f, 0.96f, 1.0f };
	const float night = std::max(0.0f, std::min(1.0f, _save->getGlobalShade() / 15.0f));
	const float ambient[3] = { 1.0f - 0.28f * night, 1.0f - 0.18f * night, 1.0f };
	const float *colors[LL_MAX] = { ambient, fire, items, units };
	float sum[3] = { 0, 0, 0 };
	float total = 0;
	for (int layer = 0; layer < LL_MAX; ++layer)
	{
		const float l = (float)tile->getLight((LightLayers)layer);
		const float w = l * l;
		if (w <= 0)
		{
			continue;
		}
		for (int c = 0; c < 3; ++c)
		{
			sum[c] += colors[layer][c] * w;
		}
		total += w;
	}
	if (total <= 0)
	{
		tint[0] = ambient[0]; tint[1] = ambient[1]; tint[2] = ambient[2];
		return;
	}
	const float maxc = std::max({ sum[0], sum[1], sum[2] });
	for (int c = 0; c < 3; ++c)
	{
		tint[c] = sum[c] / maxc;
	}
}

/**
 * HD light: the light field of a tile. Every corner of the tile's floor
 * diamond takes the mean shade and light color of the discovered tiles that
 * share it, so that neighbouring tiles blend into each other instead of
 * stepping. The tile's own drawing shade is the field's centre: only sprites
 * drawn with it (floor, walls, objects, smoke) are lit by the field.
 */
void Map::updateHdLight(Tile *tile, int tileShade, const Position &pos)
{
	HdLight &light = _hdLight;
	light.center = tileShade;
	// the light color of a tile is the same for the nine tiles around it: computed once a frame (like hdShadeOf)
	auto tintOf = [&](const Tile *t, float *tint)
	{
		const size_t index = (size_t)(t - _save->getTile(0)) * 3;
		if (index + 2 < _hdTintCache.size())
		{
			float *c = &_hdTintCache[index];
			if (c[0] < 0)
			{
				hdTintOf(t, c);
			}
			tint[0] = c[0]; tint[1] = c[1]; tint[2] = c[2];
			return;
		}
		hdTintOf(t, tint);
	};
	float ownTint[3];
	tintOf(tile, ownTint);
	// the tiles around: [dy + 1][dx + 1], nullptr where undiscovered or black
	Tile *around[3][3];
	int shadeAround[3][3];
	float tintAround[3][3][3];
	for (int dy = -1; dy <= 1; ++dy)
	{
		for (int dx = -1; dx <= 1; ++dx)
		{
			// (the grid is the view's: in a turned view (HD lab) its columns and rows are other directions of the map)
			const Position step = _camera->getRotation() ? _camera->viewStepToWorld(Position(dx, dy, 0)) : Position(dx, dy, 0);
			Tile *t = (dx == 0 && dy == 0) ? tile : _save->getTile(Position(pos.x + step.x, pos.y + step.y, pos.z));
			int shade = 16;
			if (t && t->isDiscovered(O_FLOOR))
			{
				shade = (t == tile) ? tileShade : hdShadeOf(t);
			}
			if (!t || shade >= 16)
			{
				around[dy + 1][dx + 1] = nullptr;
				continue;
			}
			around[dy + 1][dx + 1] = t;
			shadeAround[dy + 1][dx + 1] = shade;
			if (t == tile)
			{
				for (int c = 0; c < 3; ++c) tintAround[dy + 1][dx + 1][c] = ownTint[c];
			}
			else
			{
				tintOf(t, tintAround[dy + 1][dx + 1]);
			}
		}
	}
	// every node averages the tiles that share it: the centre is the tile alone, an edge the two tiles
	// across it, a corner the four around it (grid column = x direction, row = y direction)
	bool flat = true;
	for (int row = 0; row < 3; ++row)
	{
		for (int col = 0; col < 3; ++col)
		{
			const int node = row * 3 + col;
			float sumShade = 0, sumTint[3] = { 0, 0, 0 };
			int n = 0;
			// which of the 3x3 tiles touch this node: col 0 -> x-1 and x, col 1 -> x, col 2 -> x and x+1 (same for rows)
			const int xs[3][2] = { { 0, 1 }, { 1, 1 }, { 1, 2 } };
			const int ys[3][2] = { { 0, 1 }, { 1, 1 }, { 1, 2 } };
			for (int yy = ys[row][0]; yy <= ys[row][1]; ++yy)
			{
				for (int xx = xs[col][0]; xx <= xs[col][1]; ++xx)
				{
					if (!around[yy][xx])
					{
						continue;
					}
					sumShade += shadeAround[yy][xx];
					for (int c = 0; c < 3; ++c) sumTint[c] += tintAround[yy][xx][c];
					++n;
				}
			}
			if (n == 0)
			{
				light.shade[node] = (float)tileShade;
				for (int c = 0; c < 3; ++c) light.tint[node][c] = ownTint[c];
			}
			else
			{
				light.shade[node] = sumShade / n;
				for (int c = 0; c < 3; ++c) light.tint[node][c] = sumTint[c] / n;
			}
			if (node > 0)
			{
				if (std::fabs(light.shade[node] - light.shade[0]) > 0.01f) flat = false;
				for (int c = 0; c < 3; ++c)
				{
					if (std::fabs(light.tint[node][c] - light.tint[0][c]) > 0.01f) flat = false;
				}
			}
		}
	}
	light.flat = flat;
	light.dynamic = false;
	if (!_hdFlashes.empty())
	{
		hdAddFlashLight(pos, light);
	}
	_canvas->setLight(&light);
}

namespace
{
/// Options::oxceHdFlashLight: OXCE_HD_FLASH_GAIN and OXCE_HD_FLASH_REACH scale the strength and the reach of the flashes
/// (tests and the comparison sheet only; 1 without them).
float flashScale(const char *name)
{
	const char *v = getenv(name);
	return v && *v ? std::max(0.0f, (float)atof(v)) : 1.0f;
}
}

/**
 * HD render (option oxceHdFlashLight): the combat effects drawn this frame that light the map - the explosions and hits
 * while explosions show (the frame of the clip the drawing picks) and the muzzle flashes - and what each sees from its
 * voxel. Pictures only: the effects' own state, the tiles' parts and their LOFT are read, nothing is written.
 */
void Map::hdGatherFlashLights()
{
	_hdFlashes.clear();
	if (!_hdLightOn || !Options::oxceHdFlashLight || !Options::oxceHdFx)
	{
		_hdFlashSight.clear();
		return;
	}
	for (auto &s : _hdFlashSight)
	{
		s.second.used = false;
	}
	if (_explosionInFOV && !_flashScreen)
	{
		std::vector<const Explosion*> drawn(_explosions.begin(), _explosions.end());
		for (const auto &loose : _looseHits)
		{
			drawn.push_back(loose.explosion);
		}
		for (const auto *explosion : drawn)
		{
			// XP-000533: under water (depth > 0) no HD blood, so no flash of it either
			if (explosion->getHdFx().empty() || explosion->getCurrentFrame() < 0 || (_save->getDepth() > 0 && HdFx::isBloodClip(explosion->getHdFx())))
			{
				continue;
			}
			// the clip as drawTerrain picks it (the blood over a hit on flesh is dark and gives no light anyway)
			const char *setName = explosion->isBig() ? "X1.PCK" : explosion->isHit() ? "HIT.PCK" : "SMOKE.PCK";
			const std::string clip = HdFx::colour(explosion->getHdFx(), _game->getMod()->getSurfaceSet(setName)->getFrame(explosion->getStartFrame()), getPalette());
			const int clipStep = explosion->getCurrentFrame() - explosion->getStartFrame();
			if (const HdFrame *hd = HdFx::frame(HdFx::tinted(clip, explosion->getHdBlood()), clipStep, explosion->getFrameCount(), _k))
			{
				hdAddFlash(explosion->getPosition(), *hd);
			}
		}
	}
	std::vector<std::pair<const HdFx::Live*, const HdFrame*>> flashes;
	HdFx::running(SDL_GetTicks(), _k, flashes);
	for (const auto &f : flashes)
	{
		if (f.first->ms == 0) // a muzzle flash, not the dust of a collapse
		{
			hdAddFlash(f.first->voxel, *f.second);
		}
	}
	// tests and the comparison sheet: OXCE_HD_FLASH_AT="x,y,z,area" is a steady orange flash of `area` classic pixels
	// over the floor of cell x,y,z
	static const char *at = getenv("OXCE_HD_FLASH_AT");
	int ax, ay, az, area;
	if (at && sscanf(at, "%d,%d,%d,%d", &ax, &ay, &az, &area) == 4 && _save->getTile(Position(ax, ay, az)))
	{
		const double orange[3] = { 255, 190, 110 };
		hdAddFlashLit(Position(ax * 16 + 8, ay * 16 + 8, az * 24 - _save->getTile(Position(ax, ay, az))->getTerrainLevel() + 8), area, orange);
	}
	for (auto s = _hdFlashSight.begin(); s != _hdFlashSight.end();)
	{
		s = s->second.used ? std::next(s) : _hdFlashSight.erase(s);
	}
}

/**
 * HD render (option oxceHdFlashLight): a flash of the clip frame `frame` at `voxel`. Only what is bright gives light -
 * alpha times how far the brightest channel is past 0.55 (tools/flash_light_census.py), every other pixel - so blood,
 * dust and smoke stay dark; the sum in classic pixels gives the reach and the strength, the mean the colour.
 */
void Map::hdAddFlash(const Position &voxel, const HdFrame &frame)
{
	double sum = 0, rgb[3] = { 0, 0, 0 };
	for (int y = 0; y < frame.height; y += 2)
	{
		const Uint32 *row = frame.pixels.data() + (size_t)y * frame.width;
		for (int x = 0; x < frame.width; x += 2)
		{
			const Uint32 p = row[x];
			const int r = (p >> 16) & 0xFF, g = (p >> 8) & 0xFF, b = p & 0xFF;
			const int m = std::max({ r, g, b });
			if ((p >> 24) == 0 || m <= 140)
			{
				continue;
			}
			const double w = (p >> 24) / 255.0 * (m - 140.25) / 114.75;
			sum += w;
			rgb[0] += w * r;
			rgb[1] += w * g;
			rgb[2] += w * b;
		}
	}
	if (sum * 4 / ((double)_k * _k) >= 2)
	{
		hdAddFlashLit(voxel, sum * 4 / ((double)_k * _k), rgb);
	}
}

/**
 * HD render (option oxceHdFlashLight): a flash that lights `area` classic pixels at `voxel` in colour `rgb` (any scale):
 * its reach, strength and colour, and its sight on the workers when it is at a new voxel or reaches further than before.
 */
void Map::hdAddFlashLit(const Position &voxel, double area, const double rgb[3])
{
	static const float gain = flashScale("OXCE_HD_FLASH_GAIN"), reach = flashScale("OXCE_HD_FLASH_REACH");
	HdFlash flash;
	flash.voxel = voxel;
	flash.radius = 16.0f * std::max(1.0f, std::min(7.0f, 0.25f * (float)std::sqrt(area) * reach));
	flash.strength = std::min(1.0f, std::min(1.0f, (float)area / 150.0f) * gain);
	const double maxc = std::max({ rgb[0], rgb[1], rgb[2] });
	for (int c = 0; c < 3; ++c)
	{
		flash.rgb[c] = 0.3f + 0.7f * (float)(rgb[c] / maxc); // a little towards white
	}

	// the box of cells the flash may reach: its level and the ones its reach gets to, two at most each way
	const int reachXY = (int)std::ceil(flash.radius / 16.0f), reachZ = std::min(2, (int)std::ceil(flash.radius / 24.0f));
	const Position cell = voxel.toTile();
	const Position lo(std::max(0, cell.x - reachXY), std::max(0, cell.y - reachXY), std::max(0, cell.z - reachZ));
	const Position hi(std::min(_save->getMapSizeX() - 1, cell.x + reachXY), std::min(_save->getMapSizeY() - 1, cell.y + reachXY),
		std::min(_save->getMapSizeZ() - 1, cell.z + reachZ));
	if (hi.x < lo.x || hi.y < lo.y || hi.z < lo.z)
	{
		return; // a flash beyond the map's edge reaches no cell of it (XP-000444: the box came out negative)
	}
	_hdFlashes.push_back(flash);
	HdFlashSight &sight = _hdFlashSight[std::make_tuple(voxel.x, voxel.y, voxel.z)];
	sight.used = true;
	if (!sight.bits.empty() && lo.x >= sight.origin.x && lo.y >= sight.origin.y && lo.z >= sight.origin.z
		&& hi.x < sight.origin.x + sight.size.x && hi.y < sight.origin.y + sight.size.y && hi.z < sight.origin.z + sight.size.z)
	{
		return;
	}
	sight.origin = lo;
	sight.size = Position(hi.x - lo.x + 1, hi.y - lo.y + 1, hi.z - lo.z + 1);
	sight.bits.assign((size_t)sight.size.x * sight.size.y * sight.size.z, 0);
	const int cells = (int)sight.bits.size();
	if (!HdWorkers::instance().run(cells, [&](int i)
	{
		const Position at(lo.x + i % sight.size.x, lo.y + (i / sight.size.x) % sight.size.y, lo.z + i / (sight.size.x * sight.size.y));
		sight.bits[i] = hdFlashNodes(voxel, at);
	}))
	{
		// not whole: forgotten (the flash lights nothing this frame) and counted anew at the next one
		_hdFlashSight.erase(std::make_tuple(voxel.x, voxel.y, voxel.z));
	}
}

/**
 * HD render (option oxceHdFlashLight): the line of a flash's light through the map's voxels, a step per voxel along
 * its longest axis (so it cannot slip through a wall: every coordinate changes by one at most), tested the way
 * TileEngine::voxelCheck tests the terrain, but read only (voxelCheck keeps a cache) and without units.
 */
bool Map::hdLoftBlocked(const Position &from, const Position &to, int skip, const Position &target) const
{
	const std::vector<Uint16> *voxels = _game->getMod()->getVoxelData();
	if (!voxels)
	{
		return false;
	}
	const int lofts = (int)(voxels->size() / 16);
	const int dx = to.x - from.x, dy = to.y - from.y, dz = to.z - from.z;
	const int n = std::max({ std::abs(dx), std::abs(dy), std::abs(dz) });
	auto along = [n](int start, int d, int i) { return start + (d * i + (d >= 0 ? n / 2 : -(n / 2))) / n; };
	for (int i = skip; i < n; ++i)
	{
		const int x = along(from.x, dx, i), y = along(from.y, dy, i), z = along(from.z, dz, i);
		if (x < 0 || y < 0 || z < 0)
		{
			continue;
		}
		const Position cell(x / 16, y / 16, z / 24);
		const Tile *tile = _save->getTile(cell);
		if (!tile)
		{
			continue;
		}
		const int bit = 1 << (15 - x % 16), row = y % 16, layer = (z % 24) / 2;
		for (int part = O_FLOOR; part <= O_OBJECT; ++part)
		{
			const TilePart tp = (TilePart)part;
			if ((tp == O_OBJECT && cell == target) || ((tp == O_WESTWALL || tp == O_NORTHWALL) && tile->isUfoDoorOpen(tp)))
			{
				continue;
			}
			const MapData *data = tile->getMapData(tp);
			if (!data)
			{
				continue;
			}
			const int id = data->getLoftID(layer);
			if (id >= 0 && id < lofts && ((*voxels)[(size_t)id * 16 + row] & bit))
			{
				return true;
			}
		}
	}
	return false;
}

/**
 * HD render (option oxceHdFlashLight): which light nodes of cell `pos` (HdLight order: rows of the view's grid) the flash
 * at `voxel` sees. A node is tested at its point pulled 3 voxels into the cell and 6 above its floor: the two cells on
 * either side of an edge test it apart, so a wall between them splits the light, and an open edge lights both alike.
 */
Uint16 Map::hdFlashNodes(const Position &voxel, const Position &pos) const
{
	const Tile *tile = _save->getTile(pos);
	if (!tile)
	{
		return 0;
	}
	const int z = std::min(pos.z * 24 + 22, pos.z * 24 - tile->getTerrainLevel() + 6);
	Uint16 bits = 0;
	for (int node = 0; node < HdLight::NODES; ++node)
	{
		const Position w = _camera->viewStepToWorld(Position(node % 3 - 1, node / 3 - 1, 0));
		const Position at(pos.x * 16 + 8 + 5 * w.x, pos.y * 16 + 8 + 5 * w.y, z);
		if (!hdLoftBlocked(voxel, at, 2, pos))
		{
			bits |= 1 << node;
		}
	}
	return bits;
}

/**
 * HD render (option oxceHdFlashLight): the light of the flashes added into the field of a tile. Every node it sees takes
 * s = strength x (1 - (d / reach)^2)^2 by its distance d from the flash (from the node's own point, shared with the
 * neighbours, so an open floor has no seam); flashes add up as 1 - (1 - s1)(1 - s2)... The node's shade goes down by that
 * part and its colour towards the flashes'. A field so lit is drawn per pixel (HdLight::dynamic).
 */
void Map::hdAddFlashLight(const Position &pos, HdLight &light)
{
	Position step[HdLight::NODES];
	for (int node = 0; node < HdLight::NODES; ++node)
	{
		step[node] = _camera->viewStepToWorld(Position(node % 3 - 1, node / 3 - 1, 0));
	}
	const float cx = pos.x * 16 + 8.0f, cy = pos.y * 16 + 8.0f, cz = pos.z * 24 + 2.0f;
	float keep[HdLight::NODES], weight[HdLight::NODES] = {}, color[HdLight::NODES][3] = {};
	std::fill(keep, keep + HdLight::NODES, 1.0f);
	bool any = false;
	for (const HdFlash &f : _hdFlashes)
	{
		const float fx = cx - f.voxel.x, fy = cy - f.voxel.y, fz = cz - f.voxel.z;
		const float reachNear = f.radius + 12.0f;
		if (fx * fx + fy * fy + fz * fz > reachNear * reachNear)
		{
			continue;
		}
		auto s = _hdFlashSight.find(std::make_tuple(f.voxel.x, f.voxel.y, f.voxel.z));
		if (s == _hdFlashSight.end())
		{
			continue;
		}
		const HdFlashSight &sight = s->second;
		const Position in = pos - sight.origin;
		if (in.x < 0 || in.y < 0 || in.z < 0 || in.x >= sight.size.x || in.y >= sight.size.y || in.z >= sight.size.z)
		{
			continue;
		}
		const Uint16 bits = sight.bits[((size_t)in.z * sight.size.y + in.y) * sight.size.x + in.x];
		const float r2 = f.radius * f.radius;
		for (int node = 0; node < HdLight::NODES; ++node)
		{
			if (!(bits & (1 << node)))
			{
				continue;
			}
			const float dx = fx + 8.0f * step[node].x, dy = fy + 8.0f * step[node].y;
			const float d2 = dx * dx + dy * dy + fz * fz;
			if (d2 >= r2)
			{
				continue;
			}
			const float t = 1.0f - d2 / r2;
			const float v = f.strength * t * t;
			keep[node] *= 1.0f - v;
			weight[node] += v;
			for (int c = 0; c < 3; ++c)
			{
				color[node][c] += v * f.rgb[c];
			}
			any = true;
		}
	}
	if (!any)
	{
		return;
	}
	for (int node = 0; node < HdLight::NODES; ++node)
	{
		const float part = 1.0f - keep[node];
		if (part <= 0.002f)
		{
			continue;
		}
		light.shade[node] *= 1.0f - part;
		for (int c = 0; c < 3; ++c)
		{
			light.tint[node][c] += (color[node][c] / weight[node] - light.tint[node][c]) * part;
		}
	}
	light.flat = false;
	light.dynamic = true;
}

}
