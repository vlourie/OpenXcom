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

namespace
{

/// The opacity of a unit's shadow at its centre (it fades to nothing at the edge).
const int UNIT_SHADOW_ALPHA = 220;

/// How many levels below a hanging unit its shadow still falls (Vitali 30.10); the strength and the spread by level.
const int FLIER_SHADOW_LEVELS = 3;
const double FLIER_SHADOW_FADE[FLIER_SHADOW_LEVELS + 1] = { 1.0, 1.0, 0.7, 0.45 };
const double FLIER_SHADOW_SPREAD[FLIER_SHADOW_LEVELS + 1] = { 1.0, 1.0, 1.15, 1.3 };

/**
 * The shadow of a unit hanging `drop` levels above a floor: the ellipse of unitShadow (weaker and wider the higher the unit,
 * FLIER_SHADOW_FADE/SPREAD) centred (rx, ry) pixels from the top left of a floor diamond (32k x 16k), cut to that diamond.
 * A unit flying between tiles lays its shadow on several floors, each of which draws its own piece after its floor, so
 * the floors drawn later do not cover it (docs/research/hd-shadows-v2-2026-10-30.md §4). Cached by the offset, which a
 * step takes in a few dozen places; Map::hdGatherFlierShadows starts the cache anew, before a frame, past a thousand pieces.
 * @return The piece (empty when the ellipse misses the diamond).
 */
std::map<long long, HdFrame> flierShadowCache;
const HdFrame &flierShadow(int size, int drop, int rx, int ry, int k, int strength)
{
	std::map<long long, HdFrame> &cache = flierShadowCache;
	const long long key = (((((long long)strength * 16 + k) * 8 + size) * 4 + drop) * 4096 + (rx + 2048)) * 4096 + (ry + 2048);
	auto it = cache.find(key);
	if (it != cache.end())
	{
		return it->second;
	}
	HdFrame &f = cache[key];
	const double ax = 7.0 * k * size * FLIER_SHADOW_SPREAD[drop], ay = 3.5 * k * size * FLIER_SHADOW_SPREAD[drop];
	const double peak = UNIT_SHADOW_ALPHA * FLIER_SHADOW_FADE[drop] * strength / UNIT_SHADOW_STEPS;
	const double hw = 16.0 * k, hh = 8.0 * k;
	std::vector<Uint32> pixels((size_t)(32 * k) * (16 * k), 0);
	bool any = false;
	for (int y = 0; y < 16 * k; ++y)
	{
		for (int x = 0; x < 32 * k; ++x)
		{
			if (std::fabs(x + 0.5 - hw) / hw + std::fabs(y + 0.5 - hh) / hh >= 1.0)
			{
				continue;
			}
			const double ex = (x + 0.5 - rx) / ax, ey = (y + 0.5 - ry) / ay;
			const double d = 1.0 - (ex * ex + ey * ey);
			const int alpha = d > 0 ? (int)std::lround(peak * d * d) : 0;
			if (alpha > 0)
			{
				pixels[(size_t)y * 32 * k + x] = (Uint32)alpha << 24;
				any = true;
			}
		}
	}
	if (any)
	{
		f.width = 32 * k;
		f.height = 16 * k;
		f.pixels.swap(pixels);
		f.generated = true;
		f.buildSpans();
	}
	return f;
}

/**
 * The blur of the corner shade: a gaussian 7x7 (sigma 1.5 voxels) with 0.5 in the centre - a wall voxel next to the floor
 * gives about 0.4, three voxels away about 0.05.
 */
const std::array<std::array<double, 7>, 7> &floorAoKernel()
{
	static const std::array<std::array<double, 7>, 7> kernel = []
	{
		std::array<std::array<double, 7>, 7> k {};
		for (int a = -3; a <= 3; ++a)
		{
			for (int b = -3; b <= 3; ++b)
			{
				k[a + 3][b + 3] = 0.5 * std::exp(-(a * a + b * b) / (2 * 1.5 * 1.5));
			}
		}
		return k;
	}();
	return kernel;
}

}

/**
 * The shadow under a unit: a soft black ellipse on the floor (2:1, a circle in the isometric view), 7x3.5 pixels
 * of half axes per tile of the unit's size, centred on its footprint and moved a pixel to the right (the light
 * comes from the top left, docs/research/hd-shadows-ao-2026-10-30.md). The frame is the floor diamond of the
 * unit's `part` (the bottom 32x16 of its 32x40 frame, k times) with the piece of the ellipse that lies in it,
 * so the pieces of a big unit meet with no gap and no overlap. One cached frame per size, part and scale.
 */
const HdFrame &unitShadow(int size, int part, int k, int strength)
{
	static std::map<int, HdFrame> cache;
	const int key = (strength << 16) | (k << 8) | (size << 4) | part;
	auto it = cache.find(key);
	if (it != cache.end())
	{
		return it->second;
	}
	HdFrame &f = cache[key];
	f.width = 32 * k;
	f.height = 16 * k;
	f.pixels.assign((size_t)f.width * f.height, 0);
	const int dx = part % 2, dy = part / 2;
	// the footprint's centre in this part's diamond: the top part's diamond centre, half a tile lower per extra tile
	const double cx = 16.0 * k - 16.0 * k * (dx - dy) + 1.0 * k;
	const double cy = 8.0 * k * size - 8.0 * k * (dx + dy);
	const double ax = 7.0 * k * size, ay = 3.5 * k * size;
	const double hw = 16.0 * k, hh = 8.0 * k;
	for (int y = 0; y < f.height; ++y)
	{
		for (int x = 0; x < f.width; ++x)
		{
			if (std::fabs(x + 0.5 - hw) / hw + std::fabs(y + 0.5 - hh) / hh >= 1.0)
			{
				continue;
			}
			const double ex = (x + 0.5 - cx) / ax, ey = (y + 0.5 - cy) / ay;
			const double d = 1.0 - (ex * ex + ey * ey);
			const int alpha = d > 0 ? (int)std::lround(UNIT_SHADOW_ALPHA * strength / UNIT_SHADOW_STEPS * d * d) : 0;
			if (alpha > 0)
			{
				f.pixels[(size_t)y * f.width + x] = (Uint32)alpha << 24;
			}
		}
	}
	f.generated = true;
	f.buildSpans();
	return f;
}

/**
 * Options::oxceHdFloorAo: what of a map part stands low enough to shade the floor beside it - the lower 4 voxels of its
 * LOFT (layers 0 and 1), and how strongly by its height: a flat part (rubble, a plate - nothing above layer 0) shades
 * nothing, a part 12 voxels high or more shades fully. Made once for a part and kept.
 */
const Map::HdAoShape &Map::hdAoShape(const MapData *part)
{
	auto it = _hdAoShapes.find(part);
	if (it != _hdAoShapes.end())
	{
		return it->second;
	}
	HdAoShape &shape = _hdAoShapes[part];
	shape = HdAoShape();
	const std::vector<Uint16> *voxels = _game->getMod()->getVoxelData();
	const int lofts = voxels ? (int)(voxels->size() / 16) : 0;
	auto usable = [&](int id) { return id > 0 && id < lofts; };
	int top = -1;
	Uint16 above[16] = {};
	for (int layer = 0; layer < 12; ++layer)
	{
		const int id = part->getLoftID(layer);
		if (!usable(id))
		{
			continue;
		}
		for (int y = 0; y < 16; ++y)
		{
			const Uint16 row = voxels->at(id * 16 + y);
			if (layer < 2)
			{
				shape.rows[y] |= row;
			}
			if (layer == 1)
			{
				above[y] = row;
			}
			if (row)
			{
				top = layer;
			}
		}
	}
	int aboveCount = 0;
	for (int y = 0; y < 16; ++y)
	{
		for (Uint16 row = shape.rows[y]; row; row &= row - 1)
		{
			++shape.count;
		}
		for (Uint16 row = above[y]; row; row &= row - 1)
		{
			++aboveCount;
		}
	}
	// a thin thing on a plate filling the cell (a dead tree on its patch of ground): the plate is ground and shades nothing, as a flat part does (XP-000514)
	if (shape.count >= FLOOR_AO_HIDDEN && aboveCount < FLOOR_AO_THIN && top >= 2)
	{
		std::copy(above, above + 16, shape.rows);
		shape.count = aboveCount;
	}
	// a low part covering the whole cell (tall grass, top layer 1) is a carpet, not a wall: it shades no neighbour (XP-000439)
	shape.valid = shape.count > 0 && top >= 1 && !(shape.count >= FLOOR_AO_HIDDEN && top <= 1);
	// An object's LOFT can be a full block while the picture is round (a well, XP-000528): a voxel stays only where the picture
	// of the object has an opaque pixel at the voxel's foot, within a margin of one base pixel. The picture is the pack frame
	// (the classic frame of a well is a full block), else the classic frame. The foot of the voxel (vx, vy) on the floor diamond
	// (top corner at x 16, row 24 of the frame, raised by the part's Y offset) is x = 16 + vx - vy, y = 24 + (vx + vy + 1) / 2.
	// Made once with the shape and kept with it (one per set:frame for the battle), no per-frame work.
	const int pictureMargin = 1;
	if (shape.valid && part->getObjectType() == O_OBJECT && part->getDataset() && part->getDataset()->getSurfaceset())
	{
		const SurfaceSet *frames = part->getDataset()->getSurfaceset();
		std::vector<const Surface*> pictures;
		for (int f = 0; f < 8; ++f)
		{
			const int index = part->getSprite(f);
			const Surface *pic = index >= 0 ? frames->getFrame(index) : nullptr;
			if (pic && pic->getBuffer() && std::find(pictures.begin(), pictures.end(), pic) == pictures.end())
			{
				pictures.push_back(pic);
			}
		}
		if (!pictures.empty())
		{
			const int lift = part->getYOffset();
			auto opaque = [&](int x, int y)
			{
				// The picture the canvas draws for the frame: its pack frame (the well is a round HD drawing, but a full block in the
				// classic frame), else the classic frame. Terrain frames are scaled in place by k (MapDataSet::loadData): 32k x 40k,
				// a base pixel is a k x k block; opaque = any pixel of the block has alpha of 128 or more.
				if (x < 0 || y < 0 || x >= 32 || y >= 40)
				{
					return false;
				}
				for (const Surface *pic : pictures)
				{
					const int s = std::max(1, pic->getWidth() / 32);
					const HdFrame *hd = HdSprites::find(pic->getBuffer());
					if (hd && !hd->empty() && hd->width == pic->getWidth() && hd->height == pic->getHeight())
					{
						for (int py = y * s; py < (y + 1) * s; ++py)
						{
							for (int px = x * s; px < (x + 1) * s; ++px)
							{
								if ((hd->row(py)[px] >> 24) >= 128)
								{
									return true;
								}
							}
						}
					}
					else if (y * s < pic->getHeight() && pic->getBuffer()[y * s * pic->getPitch() + x * s])
					{
						return true;
					}
				}
				return false;
			};
			Uint16 kept[16] = {};
			shape.count = 0;
			for (int vy = 0; vy < 16; ++vy)
			{
				for (int vx = 0; vx < 16; ++vx)
				{
					if (!(shape.rows[vy] & (1 << (15 - vx))))
					{
						continue;
					}
					const int cx = 16 + vx - vy, cy = 24 + lift + (vx + vy + 1) / 2;
					bool seen = false;
					for (int y = cy - pictureMargin; y <= cy + pictureMargin && !seen; ++y)
					{
						for (int x = cx - 1 - pictureMargin; x <= cx + pictureMargin && !seen; ++x)
						{
							seen = opaque(x, y);
						}
					}
					if (seen)
					{
						kept[vy] |= (Uint16)(1 << (15 - vx));
						++shape.count;
					}
				}
			}
			std::copy(kept, kept + 16, shape.rows);
			shape.valid = shape.count > 0;
		}
	}
	shape.weight = std::min(1.0f, (top + 1) / 6.0f);
	// a raised part a unit walks on (a hill, a ramp) is ground, not a wall: a dark line at its foot reads as a drawn border (XP-000502)
	shape.ground = part->getTerrainLevel() < 0 && part->getTUCost(MT_WALK) < 255;
	return shape;
}

/// The opacity of an item's shadow where it is densest (docs/research/hd-shadows-v2-2026-10-30.md, §5).
const int ITEM_SHADOW_ALPHA = 165;

/**
 * Options::oxceHdItemShadow: the shadow of an item lying on the floor, made from the alpha of the picture the canvas draws for
 * its floor sprite - black, blurred, 3k pixels bigger on every side than the frame (drawn at x - 3k, y - 3k): the silhouette
 * moved k right and down (form A of the stage 1 sheet, Vitali 30.10, x1.5). The item is drawn over it, so only the rim around
 * the item shows. Made once for a frame and kept while the battle's map lives. Picture only.
 * @return The shadow, or nullptr when the canvas draws the sprite as a palette one (no alpha to take).
 */
const HdFrame *Map::hdItemShadow(HdCanvas *surface, SurfaceRaw<const Uint8> sprite)
{
	const HdFrame *hd = surface->frameOf(sprite);
	if (!hd || hd->empty())
	{
		return nullptr;
	}
	auto it = _hdItemShadows.find(hd);
	if (it != _hdItemShadows.end())
	{
		return it->second.empty() ? nullptr : &it->second;
	}
	HdFrame &f = _hdItemShadows[hd];
	const int k = _k, pad = 3 * k, w = hd->width + 2 * pad, h = hd->height + 2 * pad;
	auto alphaAt = [&](int x, int y) { return x < 0 || y < 0 || x >= hd->width || y >= hd->height ? 0.0f : (hd->row(y)[x] >> 24) / 255.0f; };
	std::vector<float> a((size_t)w * h, 0.0f), t((size_t)w * h, 0.0f);
	for (int y = 0; y < h; ++y)
	{
		for (int x = 0; x < w; ++x)
		{
			a[(size_t)y * w + x] = alphaAt(x - pad - k, y - pad - k);
		}
	}
	// two box passes each way: close to a gaussian
	const int r = k;
	for (int pass = 0; pass < 4; ++pass)
	{
		const bool across = pass % 2 == 0;
		for (int y = 0; y < h; ++y)
		{
			for (int x = 0; x < w; ++x)
			{
				float sum = 0.0f;
				for (int d = -r; d <= r; ++d)
				{
					const int xx = across ? x + d : x, yy = across ? y : y + d;
					if (xx >= 0 && yy >= 0 && xx < w && yy < h)
					{
						sum += a[(size_t)yy * w + xx];
					}
				}
				t[(size_t)y * w + x] = sum / (2 * r + 1);
			}
		}
		a.swap(t);
	}
	f.width = w;
	f.height = h;
	f.pixels.assign((size_t)w * h, 0);
	for (size_t i = 0; i < a.size(); ++i)
	{
		const int alpha = (int)std::lround(ITEM_SHADOW_ALPHA * std::min(1.0f, a[i]));
		if (alpha > 0)
		{
			f.pixels[i] = (Uint32)alpha << 24;
		}
	}
	f.generated = true;
	f.buildSpans();
	return &f;
}

/**
 * Options::oxceHdFloorAo: the shade of the corners on the floor of a tile - beside a wall or an object standing on the floor
 * the floor darkens softly. Made from the LOFT of the walls and objects of the tile and of the eight around it: their low
 * voxels (Map::hdAoShape) on a grid of 22 x 22 voxels - the floor and the three voxels around it the blur reaches -
 * blurred (floorAoKernel), cut to 16 levels and laid onto the floor diamond. Only the parts the player has discovered
 * count, an open UFO door does not. A floor under its own object (FLOOR_AO_HIDDEN of 256 voxels) is not shaded: it is not
 * seen. The rules of tools/ao_census.py (docs/research/hd-shadows-ao-2026-10-30.md §5, §14: the census took one voxel of
 * the four sides, which left a step at the tile's edge); one frame for each grid, kept for the battle; a tile remembers
 * its parts and builds anew only when they change (a door, an explosion, a discovered wall).
 * Picture only: nothing of the map is touched.
 * @return The frame for the floor diamond (32k x 16k, black with alpha), or nullptr when nothing shades this floor.
 */
const HdFrame *Map::hdFloorAo(Tile *tile, const Position &pos)
{
	if (_hdAoK != _k)
	{
		_hdAoCells.clear();
		_hdAoFrames.clear();
		_hdAoFull = false;
		_hdAoK = _k;
	}
	if ((int)_hdAoCells.size() != _save->getMapSizeXYZ())
	{
		_hdAoCells.assign(_save->getMapSizeXYZ(), HdAoCell());
	}
	auto partOf = [&](int dx, int dy, TilePart tp) -> const MapData*
	{
		// an object is seen with its floor: the game never sets the object's own flag
		const Tile *t = (dx || dy) ? _save->getTile(pos + Position(dx, dy, 0)) : tile;
		if (!t || !t->isDiscovered(tp == O_OBJECT ? O_FLOOR : tp) || t->isUfoDoorOpen(tp))
		{
			return nullptr;
		}
		return t->getMapData(tp);
	};
	// the walls and the object of this tile and of the eight around it: [((dy + 1) * 3 + dx + 1) * 3 + west, north, object]
	const TilePart kinds[3] = { O_WESTWALL, O_NORTHWALL, O_OBJECT };
	const MapData *parts[HD_AO_PARTS];
	for (int i = 0; i < HD_AO_PARTS; ++i)
	{
		parts[i] = partOf(i / 3 % 3 - 1, i / 9 - 1, kinds[i % 3]);
	}
	HdAoCell &cell = _hdAoCells[_save->getTileIndex(pos)];
	if (cell.built && std::equal(parts, parts + HD_AO_PARTS, cell.parts))
	{
		return cell.frame;
	}
	std::copy(parts, parts + HD_AO_PARTS, cell.parts);
	cell.built = true;
	cell.frame = nullptr;
	struct Timing
	{
		double &total;
		std::chrono::steady_clock::time_point started;
		~Timing() { total += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count(); }
	} timing { _hdAoBuildMs, std::chrono::steady_clock::now() };

	const HdAoShape *shapes[HD_AO_PARTS];
	bool any = false;
	const HdAoShape *ownObject = nullptr;
	for (int i = 0; i < HD_AO_PARTS; ++i)
	{
		const HdAoShape *shape = parts[i] && hdAoShape(parts[i]).valid ? &hdAoShape(parts[i]) : nullptr;
		if (i == (1 * 3 + 1) * 3 + 2)
		{
			ownObject = shape; // ground too: a floor under a hill is not seen
		}
		shapes[i] = shape && !shape->ground ? shape : nullptr;
		any = any || shapes[i];
	}
	if (!any || (ownObject && ownObject->count >= FLOOR_AO_HIDDEN))
	{
		return nullptr;
	}
	// the grid [y + 3][x + 3]: the floor's voxels and the three the blur reaches beyond each edge, so the shade of two
	// tiles meets at their edge without a step
	double grid[22][22] = {};
	for (int i = 0; i < HD_AO_PARTS; ++i)
	{
		const HdAoShape *s = shapes[i];
		if (!s)
		{
			continue;
		}
		const int ox = (i / 3 % 3 - 1) * 16, oy = (i / 9 - 1) * 16;
		for (int vy = std::max(0, -3 - oy); vy <= std::min(15, 18 - oy); ++vy)
		{
			for (int vx = std::max(0, -3 - ox); vx <= std::min(15, 18 - ox); ++vx)
			{
				if (s->rows[vy] & (1 << (15 - vx)))
				{
					double &g = grid[oy + vy + 3][ox + vx + 3];
					g = std::max(g, (double)s->weight);
				}
			}
		}
	}
	const auto &kernel = floorAoKernel();
	std::string levels(256, '\0');
	bool shaded = false;
	for (int y = 0; y < 16; ++y)
	{
		for (int x = 0; x < 16; ++x)
		{
			double sum = 0;
			for (int a = -3; a <= 3; ++a)
			{
				for (int b = -3; b <= 3; ++b)
				{
					sum += kernel[a + 3][b + 3] * grid[y + a + 3][x + b + 3];
				}
			}
			const int level = std::min(FLOOR_AO_LEVELS - 1, (int)std::nearbyint(std::min(1.0, sum) * (FLOOR_AO_LEVELS - 1)));
			levels[y * 16 + x] = (char)level;
			shaded = shaded || level > 0;
		}
	}
	if (!shaded)
	{
		return nullptr;
	}
	auto found = _hdAoFrames.find(levels);
	if (found != _hdAoFrames.end())
	{
		cell.frame = &found->second;
		return cell.frame;
	}
	if (_hdAoFrames.size() >= FLOOR_AO_MAX_FRAMES)
	{
		if (!_hdAoFull)
		{
			Log(LOG_WARNING) << "HD floor AO: " << FLOOR_AO_MAX_FRAMES << " looks made, the rest of the floors are drawn without the shade";
			_hdAoFull = true;
		}
		return nullptr;
	}
	// the diamond: a pixel's centre (u, v) from the top corner, in base pixels, is the voxel (v + u / 2, v - u / 2)
	HdFrame &f = _hdAoFrames[levels];
	f.width = 32 * _k;
	f.height = 16 * _k;
	f.pixels.assign((size_t)f.width * f.height, 0);
	auto level = [&](int vx, int vy) { return (double)levels[vy * 16 + vx]; };
	for (int y = 0; y < f.height; ++y)
	{
		for (int x = 0; x < f.width; ++x)
		{
			const double u = (x + 0.5) / _k - 16, v = (y + 0.5) / _k;
			const double vx = v + u / 2, vy = v - u / 2;
			if (vx < 0 || vx >= 16 || vy < 0 || vy >= 16)
			{
				continue;
			}
			const double fx = Clamp(vx - 0.5, 0.0, 15.0), fy = Clamp(vy - 0.5, 0.0, 15.0);
			const int x0 = (int)fx, y0 = (int)fy, x1 = std::min(15, x0 + 1), y1 = std::min(15, y0 + 1);
			const double tx = fx - x0, ty = fy - y0;
			const double l = (level(x0, y0) * (1 - tx) + level(x1, y0) * tx) * (1 - ty)
				+ (level(x0, y1) * (1 - tx) + level(x1, y1) * tx) * ty;
			const int alpha = (int)std::lround(FLOOR_AO_ALPHA * l / (FLOOR_AO_LEVELS - 1));
			f.pixels[(size_t)y * f.width + x] = (Uint32)alpha << 24;
		}
	}
	f.generated = true;
	f.buildSpans();
	cell.frame = &f;
	return cell.frame;
}

/**
 * Options::oxceHdUnitShadow for the units hanging with no floor (the shadow drawUnit leaves out): the pieces of their shadows
 * on the first floor below, up to FLIER_SHADOW_LEVELS down, for the floor pass of drawTerrain. Only a unit drawn (visible or
 * debug mode, not above the levels shown) gives one, and only onto a floor the player has discovered. The shadow stands
 * where the unit's feet are on the screen with its step, without the sway and the climb of a level (it stays on the floor).
 * Picture only: reads the units and tiles.
 */
void Map::hdGatherFlierShadows(const Position &cameraPos, int endZ)
{
	_hdFlierShadows.clear();
	// not under water (depth > 0: no sun there) nor on an orbital map (ticket XP-000446)
	if (!Options::oxceHdUnitShadow || _canvas->getHdMode() == HD_MODE_NEAREST || _camera->getRotation() != 0 || _save->getDepth() > 0 || hdOrbitalMap(_save))
	{
		return;
	}
	// weaker in the dusk, none at night (ticket XP-000447)
	const int strength = unitShadowStrength(_save->getGlobalShade());
	if (strength <= 0)
	{
		return;
	}
	if (flierShadowCache.size() > 1000)
	{
		flierShadowCache.clear();
	}
	for (const BattleUnit *bu : *_save->getUnits())
	{
		const Position pos = bu->getPosition();
		if (!bu->isFloating() || bu->isOut() || bu->getStatus() == STATUS_COLLAPSING || pos.x < 0 || pos.z > endZ
			|| !(bu->getVisible() || _save->getDebugMode()))
		{
			continue;
		}
		// the first floor down from the unit's own level (a unit just lifting off still has its own), as Tile::hasNoFloor sees it
		int drop = -1;
		for (int d = 0; d <= FLIER_SHADOW_LEVELS && pos.z - d >= 0; ++d)
		{
			const Tile *t = _save->getTile(Position(pos.x, pos.y, pos.z - d));
			if (t && !t->hasNoFloor(_save))
			{
				drop = d;
				break;
			}
		}
		if (drop < 0)
		{
			continue;
		}
		const int size = bu->getArmor()->getSize();
		const int z = pos.z - drop;
		const UnitWalkingOffset offsets = calculateWalkingOffset(bu);
		const Position bob = hoverBob(bu);
		Position screen;
		_camera->convertMapToScreen(Position(pos.x, pos.y, z), &screen);
		screen += cameraPos;
		// the centre of the footprint, as unitShadow has it: a pixel right of the middle of the floor diamond(s)
		const int cx = screen.x + offsets.ScreenOffset.x - bob.x + 17 * _k;
		const int cy = screen.y + offsets.ScreenOffset.y - offsets.TerrainLevelOffset * _k - bob.y + 24 * _k + 8 * _k * size;
		const double ax = 7.0 * _k * size * FLIER_SHADOW_SPREAD[drop], ay = 3.5 * _k * size * FLIER_SHADOW_SPREAD[drop];
		const Position dest = bu->getDestination();
		const int x0 = std::min(pos.x, dest.x) - 1, x1 = std::max(pos.x, dest.x) + size;
		const int y0 = std::min(pos.y, dest.y) - 1, y1 = std::max(pos.y, dest.y) + size;
		for (int y = y0; y <= y1; ++y)
		{
			for (int x = x0; x <= x1; ++x)
			{
				const Position at(x, y, z);
				Tile *t = _save->getTile(at);
				if (!t || t->hasNoFloor(_save) || !t->isDiscovered(O_FLOOR))
				{
					continue;
				}
				Position tileScreen;
				_camera->convertMapToScreen(at, &tileScreen);
				tileScreen += cameraPos;
				const int rx = cx - tileScreen.x, ry = cy - (tileScreen.y + 24 * _k - t->getYOffset(O_FLOOR) * _k);
				if (std::abs(rx - 16 * _k) >= 16 * _k + ax || std::abs(ry - 8 * _k) >= 8 * _k + ay)
				{
					continue;
				}
				const HdFrame &piece = flierShadow(size, drop, rx, ry, _k, strength);
				if (!piece.empty())
				{
					_hdFlierShadows[_save->getTileIndex(at)].push_back(&piece);
				}
			}
		}
	}
}

}
