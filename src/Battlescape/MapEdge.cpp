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

/**
 * The part of a floor diamond (the bottom 32x16 of the 32x40 frame, k times) that lies within the cell's coordinates
 * a in [aLo, aHi] along the map's x (the diamond's top to its right corner) and b in [bLo, bHi] along the map's y (the
 * top to the left corner), in one colour (XP-000380: the line along the map's edge). The pixels are the diamond's own
 * (the test of fillDiamond), so the band meets the neighbour cell's without a gap or an overlap.
 */
void fillEdgeBand(HdFrame &f, Uint32 rgb, int alpha, int k, double aLo, double aHi, double bLo, double bHi)
{
	f.width = 32 * k;
	f.height = 16 * k;
	f.pixels.assign((size_t)f.width * f.height, 0);
	const Uint32 px = ((Uint32)alpha << 24) | (rgb & 0xFFFFFF);
	for (int y = 0; y < f.height; ++y)
	{
		for (int x = 0; x < f.width; ++x)
		{
			const double s = (x + 0.5 - 16.0 * k) / (16.0 * k), t = (y + 0.5) / (8.0 * k);
			const double a = (s + t) / 2, b = (t - s) / 2;
			if (a > 0 && a < 1 && b > 0 && b < 1 && a >= aLo && a <= aHi && b >= bLo && b <= bHi)
			{
				f.pixels[(size_t)y * f.width + x] = px;
			}
		}
	}
	f.generated = true;
	f.buildSpans();
}

/**
 * One cell's length of a vertical fence one level (24 base pixels) high along a map edge (XP-000382, XP-000420): a frame 16k wide
 * and 32k tall; the foot runs from the left of the frame's row 24k down to its right (`down`, the map's edges that run from the
 * top corner to the right one and from the bottom corner to the left one) or from row 32k up (`!down`). A real fence, not a band:
 * posts on the cell's corners (half a post at each end of the frame, so two neighbours make one whole post and a corner of the
 * map gets one), three pickets between them, two rails along the foot's slope, the gaps only faintly tinted. Posts and pickets
 * have a lighter left edge and a darker right one for volume. Measured in base pixels (u along the cell's 16, v up from the foot)
 * and scaled by k, so every k gives the same fence. `body` is the alpha of the gaps, `edge` the alpha of the posts.
 */
void fillFence(HdFrame &f, bool down, Uint32 rgb, int body, int edge, int k)
{
	f.width = 16 * k;
	f.height = 32 * k;
	f.pixels.assign((size_t)f.width * f.height, 0);
	const int r = (rgb >> 16) & 0xFF, g = (rgb >> 8) & 0xFF, b = rgb & 0xFF;
	auto light = [](int c) { return c + (255 - c) * 45 / 100; };
	auto dark = [](int c) { return c * 58 / 100; };
	const Uint32 cBase = (Uint32)(r << 16 | g << 8 | b);
	const Uint32 cLight = (Uint32)(light(r) << 16 | light(g) << 8 | light(b));
	const Uint32 cDark = (Uint32)(dark(r) << 16 | dark(g) << 8 | dark(b));
	const int aPost = edge, aPicket = edge * 92 / 100, aRail = edge * 78 / 100;
	for (int y = 0; y < f.height; ++y)
	{
		for (int x = 0; x < f.width; ++x)
		{
			const double foot = down ? 24.0 * k + (x + 0.5) / 2 : 32.0 * k - (x + 0.5) / 2;
			const double top = foot - 24.0 * k, at = y + 0.5;
			if (!(at > top && at < foot))
			{
				continue;
			}
			const double u = (x + 0.5) / k, v = (foot - at) / k;
			int alpha = body;
			Uint32 col = cBase;
			if (u < 1.0 || u >= 15.0)
			{
				// a post: [15, 16) of this frame and [0, 1) of the next one; the light edge on the left, the shade on the right
				alpha = aPost;
				col = u >= 15.0 ? (u < 15.5 ? cLight : cBase) : (u < 0.5 ? cBase : cDark);
				if (v > 23.4)
				{
					col = cLight;   // the cut top of the post
				}
			}
			else if (v < 21.0 && ((u >= 3.4 && u < 4.6) || (u >= 7.4 && u < 8.6) || (u >= 11.4 && u < 12.6)))
			{
				const double in = std::fmod(u - 3.4, 4.0) / 1.2;   // 0..1 across the picket
				alpha = aPicket;
				col = in < 0.3 ? cLight : (in > 0.7 ? cDark : cBase);
			}
			else if ((v >= 4.0 && v < 5.5) || (v >= 15.0 && v < 16.5))
			{
				alpha = aRail;
				col = (v < 4.4 || (v >= 15.0 && v < 15.4)) ? cLight : cBase;
			}
			f.pixels[(size_t)y * f.width + x] = ((Uint32)alpha << 24) | (col & 0xFFFFFF);
		}
	}
	f.generated = true;
	f.buildSpans();
}

/// A map cell's index mirrored across the edge of a map `size` cells long (-1 -> 0, size -> size - 1) and folded back and
/// forth within the `band` cells along the edge when the image goes deeper (band 6: -7 -> 5, -8 -> 5, -13 -> 0 ...): the
/// ground beyond the edge goes on with the map's outer band only, not with what stands in the middle of the map.
/// A coordinate inside the map stays as it is (XP-000263).
int bandIndex(int v, int size, int band)
{
	if (v >= 0 && v < size)
	{
		return v;
	}
	band = std::max(1, std::min(band, size));
	const int depth = (v < 0 ? -1 - v : v - size) % (2 * band);
	const int in = depth < band ? depth : 2 * band - 1 - depth;
	return v < 0 ? in : size - 1 - in;
}

}

/**
 * The floor diamond of a tile (the bottom 32x16 of the 32x40 frame, k times) filled with one colour at one
 * opacity. The diamonds of neighbouring tiles meet with no gap and no overlap: no pixel centre lies on an
 * edge, so every pixel belongs to exactly one tile and a fill of many tiles is even.
 * Kept for the battle (drawn by the strips after this frame records); at most a few colours by 32 steps.
 */
void fillDiamond(HdFrame &f, Uint32 rgb, int alpha, int k)
{
	f.width = 32 * k;
	f.height = 16 * k;
	f.pixels.assign((size_t)f.width * f.height, 0);
	const Uint32 px = ((Uint32)alpha << 24) | (rgb & 0xFFFFFF);
	const double hw = 16.0 * k, hh = 8.0 * k;
	for (int y = 0; y < f.height; ++y)
	{
		for (int x = 0; x < f.width; ++x)
		{
			if (std::fabs(x + 0.5 - hw) / hw + std::fabs(y + 0.5 - hh) / hh < 1.0)
			{
				f.pixels[(size_t)y * f.width + x] = px;
			}
		}
	}
	f.generated = true;
	f.buildSpans();
}

/**
 * Options::oxceHdBackdrop: the color of the void by the battle's ground. The mod's table hd/backdrop.txt ("NAME RRGGBB"
 * a line, '#' starts a comment) names a terrain or a mission type; the terrain that most of the map's blocks come from
 * and has a line wins, else the mission type. No file or no line: -1, the environment's own color as it was.
 * The table's line wins over the environment's color (the jungle of Piratez has the heat's dark red).
 * Only a picture: nothing of the battle is read but the names the save already holds.
 */
int Map::hdBackdropRgb()
{
	const int found = hdBackdropFind();
	if (found < 0)
	{
		return -1;
	}
	// the void goes dark with the battle's own darkness (the global shade 0..15): to 15 percent at night
	const int keep = 100 - 85 *std::max(0, std::min(15, _save->getGlobalShade())) / 15;
	return ((((found >> 16) & 255) * keep / 100) << 16) | ((((found >> 8) & 255) * keep / 100) << 8) | ((found & 255) * keep / 100);
}

int Map::hdBackdropFind()
{
	if (_hdBackdropRgb != -2)
	{
		return _hdBackdropRgb;
	}
	_hdBackdropRgb = -1;
	const std::string path = HdSprites::artPath("backdrop.txt");
	std::unique_ptr<std::istream> in = FileMap::fileExists(path) ? FileMap::getIStream(path) : nullptr;
	if (!in)
	{
		return _hdBackdropRgb;
	}
	std::map<std::string, int> table;
	std::string line;
	while (std::getline(*in, line))
	{
		if (line.size() >= 3 && (unsigned char)line[0] == 0xEF && (unsigned char)line[1] == 0xBB && (unsigned char)line[2] == 0xBF)
		{
			line.erase(0, 3);
		}
		std::istringstream fields(line);
		std::string name, hex;
		if (!(fields >> name >> hex) || name[0] == '#')
		{
			continue;
		}
		table[name] = (int)(strtoul(hex.c_str() + (hex[0] == '#' ? 1 : 0), nullptr, 16) & 0xFFFFFF);
	}
	std::map<std::string, int> blocks;
	for (const auto &column : _save->getFlattenedMapTerrainNames())
	{
		for (const std::string &name : column)
		{
			if (table.count(name))
			{
				++blocks[name];
			}
		}
	}
	std::string best = table.count(_save->getMissionType()) ? _save->getMissionType() : "";
	int most = 0;
	for (const auto &b : blocks)
	{
		if (b.second > most)
		{
			most = b.second;
			best = b.first;
		}
	}
	if (!best.empty())
	{
		_hdBackdropRgb = table[best];
	}
	Log(LOG_INFO) << "HD backdrop: " << table.size() << " lines of " << path << ", ground " << (best.empty() ? "-" : best) << " -> " << _hdBackdropRgb << ", shade " << _save->getGlobalShade();
	return _hdBackdropRgb;
}

/**
 * Options::oxceHdBeyondEdge (XP-000398): is the map part a low object that the mirror beyond the edge shows (a bush, grass, a
 * stone, a log)? By the part's data only: its type is an object, the topmost non-empty layer of its LOFT is 5 or lower (a layer
 * is 2 voxels: up to 12 voxels, half a cell - a tree's trunk and a wall go to layer 11), it is not the ground's own relief (a
 * part of layer 2 or higher whose layers 0 and 1 fill the cell, FLOOR_AO_HIDDEN: a slope, a hill - they are the ground, the
 * mirror's floor stands for them), and the topmost opaque row of its classic picture is 8 or lower down of 40 (a tall picture
 * of a part without a LOFT is not a low object), and, when it has a LOFT, its set has floor parts (a set without any is a prop set: crates, barrels).
 * Made once for a part and kept.
 * @return 1 low, 2 tall, 3 relief, 4 tall picture, 5 prop (a set without floors).
 */
Uint8 Map::hdLowObject(const MapData *part)
{
	auto it = _hdLowParts.find(part);
	if (it != _hdLowParts.end())
	{
		return it->second;
	}
	Uint8 kind = 1;
	const std::vector<Uint16> *voxels = _game->getMod()->getVoxelData();
	const int lofts = voxels ? (int)(voxels->size() / 16) : 0;
	int top = -1;
	Uint16 rows[16] = { 0 };
	for (int layer = 0; layer < 12; ++layer)
	{
		const int id = part->getLoftID(layer);
		if (!(id > 0 && id < lofts))
		{
			continue;
		}
		for (int y = 0; y < 16; ++y)
		{
			const Uint16 row = voxels->at(id * 16 + y);
			if (layer < 2)
			{
				rows[y] |= row;
			}
			if (row)
			{
				top = layer;
			}
		}
	}
	int count = 0;
	for (int y = 0; y < 16; ++y)
	{
		for (Uint16 row = rows[y]; row; row &= row - 1)
		{
			++count;
		}
	}
	if (top > 5)
	{
		kind = 2;
	}
	else if (top >= 2 && count >= FLOOR_AO_HIDDEN)
	{
		kind = 3;
	}
	else if (part->getDataset() && part->getDataset()->getSurfaceset())
	{
		Surface *frame = part->getDataset()->getSurfaceset()->getFrame(part->getSprite(0));
		if (frame)
		{
			int first = frame->getHeight();
			for (int y = 0; y < frame->getHeight() && first == frame->getHeight(); ++y)
			{
				for (int x = 0; x < frame->getWidth(); ++x)
				{
					if (frame->getPixel(x, y))
					{
						first = y;
						break;
					}
				}
			}
			if (first < 8)
			{
				kind = 4;
			}
		}
	}
	if (kind == 1 && top >= 0)
	{
		// a solid part of a set that has no floor parts at all is a loose prop (a crate, a barrel, a sack: containers, CRATES),
		// not the ground's own cover: a terrain set (FOREST, MOUNTGRASS, the desert's) always has floors next to its bushes and
		// stones. A part without a LOFT (the jungle's vines, a candle) is a picture only and stays as it was
		bool floors = false;
		if (part->getDataset())
		{
			for (const MapData *other : *part->getDataset()->getObjectsRaw())
			{
				if (other->getObjectType() == O_FLOOR && !other->isNoFloor())
				{
					floors = true;
					break;
				}
			}
		}
		if (!floors)
		{
			kind = 5;
		}
	}
	_hdLowParts[part] = kind;
	return kind;
}

/**
 * Options::oxceHdBeyondEdge (XP-000263): the ground goes on beyond the map's edge. Under the map (before its cells are drawn),
 * on the ground level (z = 0, the formula of the map's own cells), over the backdrop, in the cells of the screen that lie off the
 * map: the mirror of the map's edge cells - the floor of the map's cell reflected across the edge (x < 0 -> -1 - x, x >= sizeX ->
 * 2 * sizeX - 1 - x, the same for y; folded back and forth within the outer band of 6 cells, see bandIndex), the ground level - under
 * a veil of the backdrop's colour at its row that thickens with the distance from the edge until the floor is gone into the
 * backdrop (the veil is a floor-diamond frame with alpha, as the explosion area's). A floor of the map the player has not
 * discovered is not shown: the cell takes the commonest floor of the map's outer band instead, under a denser veil. The floors
 * are those of the battle's first frame (a blast leaves no scorched earth beyond the edge), and a floor of under a tenth of the
 * band's open ground (a house, a ship) is the commonest floor too. Options::oxceHdBeyondLook (XP-000263):
 * 1 the floors in greys, 2 a pale fog instead of the backdrop's colour (the floors are gone into it half way, the fog itself
 * thins out to the end). Picture only: no tile is touched, no light, no fog of war, no cache of the battle; the cells are
 * not on the map, so nothing there can be clicked.
 * XP-000398: the low objects of the cells (hdLowObject: bushes, grass, stones, logs; not trees, walls and the ground's slopes)
 * are mirrored too, after the cell's floor, 2 to 12 cells from the edge, thinning out by the cell's hash as the veil would
 * thicken (an object of a cell the player has not discovered is not shown). The ring next to the map on its near sides (the cells
 * the map's cells are drawn over) has none: the map would cut their tops off.
 */
void Map::hdDrawBeyondEdge(HdCanvas *surface, const Position &cameraPos)
{
	const int sizeX = _save->getMapSizeX(), sizeY = _save->getMapSizeY(), sizeZ = _save->getMapSizeZ();
	const int BAND = 6; // the outer band of the map that the ground beyond the edge is made of (XP-000263)
	// a cell of the ground level with a floor over it (a base's rooms stand on a bedrock under them, XP-000401): what the
	// player sees there is the room, not the ground, so its ground is not what goes on beyond the edge
	auto covered = [&](int x, int y)
	{
		for (int z = 1; z < sizeZ; ++z)
		{
			const Tile *t = _save->getTile(Position(x, y, z));
			const MapData *data = t ? t->getMapData(O_FLOOR) : nullptr;
			if (data && !data->isNoFloor())
			{
				return true;
			}
		}
		return false;
	};
	if (_hdGhostState < 0)
	{
		_hdGhostState = 0;
		// the floors of the ground level as they are at the battle's first frame (XP-000263): the mirror takes them, not the
		// live tiles, which a blast turns into the scorched earth or debris. A battle loaded from a save has them damaged
		// already: the scorched earth, and the floors that a destroyed part leaves (the die MCD of an object of the set) when
		// they are few, are taken as not known, the ghost floor goes there
		MapData *scorched = MapDataSet::getScorchedEarthTile();
		std::unordered_set<const MapData*> debris;
		std::unordered_set<const MapDataSet*> debrisDone;
		std::unordered_map<const MapData*, int> census; // the cells of each floor over the level
		struct Kind { const MapData *data; int all; int open; };
		std::vector<Kind> kinds;
		int cells = 0, floors = 0, bandAll = 0, bandOpen = 0, damaged = 0, scorchedCells = 0;
		int objectKinds[6] = { 0, 0, 0, 0, 0, 0 }; // the objects of the ground level by hdLowObject's kind (XP-000398)
		_hdFloorSnap.assign((size_t)sizeX * sizeY, HdSnapFloor());
		for (int y = 0; y < sizeY; ++y)
		{
			for (int x = 0; x < sizeX; ++x)
			{
				++cells;
				const Tile *t = _save->getTile(Position(x, y, 0));
				const MapData *data = t ? t->getMapData(O_FLOOR) : nullptr;
				if (!data || data->isNoFloor() || !t->getSprite(O_FLOOR))
				{
					continue;
				}
				++floors;
				HdSnapFloor &snap = _hdFloorSnap[(size_t)y * sizeX + x];
				snap.data = data;
				snap.kind = 2;
				if (const MapData *object = t->getMapData(O_OBJECT))
				{
					if (t->getSprite(O_OBJECT))
					{
						const Uint8 lowKind = hdLowObject(object);
						++objectKinds[lowKind];
						if (lowKind == 1)
						{
							snap.low = object;
						}
					}
				}
				++census[data];
				MapDataSet *set = data->getDataset();
				if (set && debrisDone.insert(set).second)
				{
					for (const MapData *object : *set->getObjectsRaw())
					{
						const int die = object->getDieMCD();
						if (die > 0 && (size_t)die < set->getSize())
						{
							debris.insert(set->getObject(die));
						}
					}
				}
			}
		}
		for (int y = 0; y < sizeY; ++y)
		{
			for (int x = 0; x < sizeX; ++x)
			{
				HdSnapFloor &snap = _hdFloorSnap[(size_t)y * sizeX + x];
				if (snap.kind != 2)
				{
					continue;
				}
				const MapData *data = snap.data;
				// a floor that is a destruction's leaving is damage only when it is a small part of the level: the ground of a
				// whole map (a burnt or snowy plain) is another object's die MCD too
				if (data == scorched || (debris.count(data) && census[data] * 10 < cells))
				{
					snap.kind = 1;
					++damaged;
					scorchedCells += data == scorched ? 1 : 0;
					continue;
				}
				const bool open = !covered(x, y);
				if (!open)
				{
					snap.kind = 1; // a room stands over it: what the player sees there is not the ground
				}
				// the commonest floors are counted where the ground meets the edge: the outer band of the level (a base or a
				// ship in the middle of a desert has its own floors, which the desert beyond the edge does not go on with)
				if (x >= BAND && x < sizeX - BAND && y >= BAND && y < sizeY - BAND)
				{
					continue;
				}
				size_t i = 0;
				while (i < kinds.size() && kinds[i].data != data)
				{
					++i;
				}
				if (i == kinds.size())
				{
					kinds.push_back(Kind{ data, 0, 0 });
				}
				++kinds[i].all;
				++bandAll;
				if (open)
				{
					++kinds[i].open;
					++bandOpen;
				}
			}
		}
		// the open ground of the band (under the sky) when there is any: the grass between a base's rooms, not their bedrock
		const bool useOpen = bandOpen > 0;
		const int bandTotal = useOpen ? bandOpen : bandAll;
		auto share = [&](const Kind &k) { return useOpen ? k.open : k.all; };
		int rare = 0;
		// no ground level to go on (an underground map, a level of air, a level of the scorched earth): at least half of it
		// must have a floor that is not damaged
		if ((floors - damaged) * 2 >= cells && !kinds.empty())
		{
			const Kind *best = &kinds[0];
			for (const Kind &k : kinds)
			{
				if (share(k) > share(*best))
				{
					best = &k;
				}
			}
			HdGhostFloor ghost;
			ghost.sprite = best->data->getDataset()->getSurfaceset()->getFrame(best->data->getSprite(0));
			ghost.yOffset = best->data->getYOffset();
			ghost.count = share(*best);
			_hdGhostFloors.assign(1, ghost); // the commonest one: the floor of the cells whose mirror the player has not discovered
			// a floor of under a tenth of the band's open ground is a house's or a ship's: the cell takes the ghost floor too
			for (int y = 0; y < sizeY; ++y)
			{
				for (int x = 0; x < sizeX; ++x)
				{
					HdSnapFloor &snap = _hdFloorSnap[(size_t)y * sizeX + x];
					if (snap.kind != 2)
					{
						continue;
					}
					for (const Kind &k : kinds)
					{
						if (k.data == snap.data)
						{
							if (share(k) * 10 < bandTotal)
							{
								snap.kind = 1;
								rare += (x < BAND || x >= sizeX - BAND || y < BAND || y >= sizeY - BAND) ? 1 : 0;
							}
							break;
						}
					}
				}
			}
			// XP-000548: a low object of another set than the ground's is not the ground's cover: a craft's ramp, a building's
			// prop stand on the ground's floor too. The mirror takes the objects of the sets the ground itself is made of (the
			// sets of the floors that make a tenth of the band's open ground) and of the set of the cell's own floor
			std::unordered_set<const MapDataSet*> groundSets;
			for (const Kind &k : kinds)
			{
				if (share(k) * 10 >= bandTotal && k.data->getDataset())
				{
					groundSets.insert(k.data->getDataset());
				}
			}
			for (HdSnapFloor &snap : _hdFloorSnap)
			{
				if (snap.low && snap.data && snap.low->getDataset() != snap.data->getDataset() && !groundSets.count(snap.low->getDataset()))
				{
					snap.low = nullptr;
				}
			}
			_hdGhostState = 1;
		}
		else
		{
			_hdFloorSnap.clear();
		}
		Log(LOG_INFO) << "HD beyond edge: " << floors << " floors of " << cells << " cells of the ground level (" << damaged << " damaged, " << scorchedCells << " of them scorched earth) -> " << kinds.size() << " kinds in the band of " << bandTotal << " cells, " << rare << " band cells of rare floors, state " << _hdGhostState
			<< "; objects: " << objectKinds[1] << " low (mirrored), " << objectKinds[2] << " tall, " << objectKinds[3] << " relief, " << objectKinds[4] << " tall picture, " << objectKinds[5] << " props";
	}
	if (_hdGhostState != 1)
	{
		return;
	}
	const int REACH = 36;          // the cells beyond the edge that are drawn: the farthest is all the backdrop's colour
	const double POWER = 1.3;      // the veil grows a little slower than the distance
	const int HAZE_STEPS = 24;     // the veil's opacity steps (a frame of the veil for each step and colour)
	const int look = Options::oxceHdBeyondLook;
	const double FOG_AT = 0.55;    // fog: the floors are under the fog up to this part of the way, beyond it only the fog is drawn
	const double FOG_MAX = 0.92;   // fog: its opacity where the floors end
	const int W = _spriteWidth, H = _spriteHeight;
	const int width = surface->getWidth(), height = surface->getHeight();
	// the cells whose sprite touches the screen (the map's own test), as a box of tiles: u = x - y and v = x + y on the screen
	const double ulo = (-W - cameraPos.x) * 2.0 / W, uhi = (width + W - cameraPos.x) * 2.0 / W;
	const double vlo = (-H - cameraPos.y) * 4.0 / W, vhi = (height + H - cameraPos.y) * 4.0 / W;
	const int x0 = std::max(-REACH, (int)std::floor((ulo + vlo) / 2) - 1), x1 = std::min(sizeX - 1 + REACH, (int)std::ceil((uhi + vhi) / 2) + 1);
	const int y0 = std::max(-REACH, (int)std::floor((vlo - uhi) / 2) - 1), y1 = std::min(sizeY - 1 + REACH, (int)std::ceil((vhi - ulo) / 2) + 1);
	const int baseShade = std::max(0, std::min(15, _save->getGlobalShade()));
	if (_hdLightOn)
	{
		_canvas->setLight(nullptr);
	}
	for (int y = y0; y <= y1; ++y)
	{
		for (int x = x0; x <= x1; ++x)
		{
			const int dx = x < 0 ? -x : (x >= sizeX ? x - sizeX + 1 : 0);
			const int dy = y < 0 ? -y : (y >= sizeY ? y - sizeY + 1 : 0);
			const int distance = std::max(dx, dy);
			if (distance == 0 || distance > REACH)
			{
				continue;
			}
			Position screenPosition;
			_camera->convertMapToScreen(Position(x, y, 0), &screenPosition);
			screenPosition += cameraPos;
			if (!(screenPosition.x > -W && screenPosition.x < width + W && screenPosition.y > -H && screenPosition.y < height + H))
			{
				continue;
			}
			// the cell of the map this one mirrors across the edge, and its floor: the map's own, or - where the player has not
			// discovered it, or a room stands over it - the commonest open one of the map's outer band
			const int mx = bandIndex(x, sizeX, BAND), my = bandIndex(y, sizeY, BAND);
			const Tile *source = _save->getTile(Position(mx, my, 0));
			if (!source)
			{
				continue;
			}
			SurfaceRaw<const Uint8> sprite;
			int yOffset = 0;
			bool unseen = false;
			const HdSnapFloor &snap = _hdFloorSnap[(size_t)my * sizeX + mx];
			if (source->isDiscovered(O_FLOOR))
			{
				if (snap.kind == 0)
				{
					continue;
				}
				if (snap.kind == 2)
				{
					if (source->getMapData(O_FLOOR) == snap.data && source->getSprite(O_FLOOR))
					{
						sprite = source->getSprite(O_FLOOR); // the floor is still there: its animation goes on
						yOffset = source->getYOffset(O_FLOOR);
					}
					else
					{
						// destroyed in the battle: the floor as it was
						sprite = snap.data->getDataset()->getSurfaceset()->getFrame(snap.data->getSprite(0));
						yOffset = snap.data->getYOffset();
					}
				}
			}
			else
			{
				unseen = true;
			}
			if (!sprite)
			{
				sprite = _hdGhostFloors[0].sprite;
				yOffset = _hdGhostFloors[0].yOffset;
			}
			Uint32 h = (Uint32)x * 0x9E3779B1u ^ (Uint32)y * 0x85EBCA77u;
			h ^= h >> 15; h *= 0x2C1B3C6Du; h ^= h >> 12; h *= 0x297A2D39u; h ^= h >> 15;
			// the farther from the edge, the more of the backdrop's colour over the floor, by steps; the hash of the cell (the
			// same every frame) tips a cell to the next step by the part of the way it has gone, so the rings do not show.
			// Fog: the floors sink into it up to FOG_AT of the way and beyond it only the fog is drawn, thinning out to the end
			const double t = (double)(distance - 1) / std::max(1, REACH - 1);
			const double dither = ((h >> 8) & 255) / 256.0;
			bool drawFloor = true;
			double cover = std::pow(t, POWER);
			if (look == 2)
			{
				drawFloor = t <= FOG_AT;
				cover = drawFloor ? FOG_MAX * std::pow(t / FOG_AT, POWER) : FOG_MAX * (1.0 - (t - FOG_AT) / (1.0 - FOG_AT));
			}
			if (unseen)
			{
				// the ghost floor stands where the player has not discovered the cell this one mirrors: under a denser veil
				cover = std::min(0.97, cover * 1.4 + 0.12 * std::min(1.0, cover * 4.0));
			}
			const double hazeAt = cover * HAZE_STEPS;
			const int haze = std::max(0, std::min(HAZE_STEPS, (int)hazeAt + (dither < hazeAt - (int)hazeAt ? 1 : 0)));
			if (drawFloor)
			{
				// look 1: the floor in greys (the kept grey copy of the pack's picture, shaded as the colour one would be)
				const HdFrame *gray = look == 1 ? hdGrayFloor(surface, sprite) : nullptr;
				if (gray)
				{
					surface->blitFrameShaded(*gray, screenPosition.x, screenPosition.y - yOffset * _k, baseShade);
				}
				else
				{
					if (_hdGroundVariants)
					{
						surface->setGroundCell(true, mx, my, 0);
					}
					surface->blit(sprite, screenPosition.x, screenPosition.y - yOffset * _k, baseShade, false, _nvColor);
					if (_hdGroundVariants)
					{
						surface->setGroundCell(false, 0, 0, 0);
					}
				}
			}
			if (haze > 0)
			{
				// the floor's diamond (the bottom 32x16 of its frame) under a veil of the backdrop's colour at its row
				const int cy = screenPosition.y - yOffset * _k + 24 * _k;
				int rgb = surface->backdropAt(cy + 8 * _k);
				if (rgb < 0)
				{
					const SDL_Color &c = getPalette()[Palette::blockOffset(0) + _bgColor];
					rgb = (c.r << 16) | (c.g << 8) | c.b;
				}
				if (look == 2)
				{
					// the fog: the backdrop's colour at the row mixed towards a pale haze, darker the darker the battle's light
					const int pale = 255 * (20 - baseShade) / 20;
					const int fog[3] = { pale * 216 / 255, pale * 224 / 255, pale * 232 / 255 };
					rgb = ((((rgb >> 16) & 255) * 3 + fog[0] * 7) / 10 << 16) | ((((rgb >> 8) & 255) * 3 + fog[1] * 7) / 10 << 8) | (((rgb & 255) * 3 + fog[2] * 7) / 10);
				}
				rgb &= 0xFCFCFC;
				const int alpha = haze * 255 / HAZE_STEPS;
				const unsigned long long key = ((unsigned long long)rgb << 8) | (unsigned long long)alpha;
				auto it = _hdHazeFrames.find(key);
				if (it == _hdHazeFrames.end())
				{
					HdFrame &f = _hdHazeFrames[key];
					fillDiamond(f, rgb, alpha, _k);
					it = _hdHazeFrames.find(key);
					if (_hdHazeFrames.size() % 50 == 0)
					{
						Log(LOG_INFO) << "HD beyond edge: " << _hdHazeFrames.size() << " haze frames";
					}
				}
				surface->blitFrame(it->second, screenPosition.x, cy);
			}
			// XP-000398: the low object of the cell this one mirrors, over its floor and veil: 2 to OBJECT_REACH cells from the
			// edge, fewer of them the denser the veil (the cell's hash against the share left), none where the player has not
			// discovered the mirrored cell, and none in the ring where the map's cells (drawn later) stand over the object's top
			const int OBJECT_REACH = 12;
			const double OBJECT_COVER = 0.30; // the veil's opacity at which no object is left
			if (snap.low && snap.kind == 2 && !unseen && drawFloor && distance >= 2 && distance <= OBJECT_REACH)
			{
				auto inMap = [&](int cx, int cy2) { return cx >= 0 && cx < sizeX && cy2 >= 0 && cy2 < sizeY; };
				const double share = 1.0 - cover / OBJECT_COVER;
				const double roll = ((h >> 18) & 1023) / 1024.0;
				if (share > 0.0 && roll < share && !inMap(x - 1, y) && !inMap(x, y - 1) && !inMap(x - 1, y - 1))
				{
					SurfaceRaw<const Uint8> objectSprite;
					int objectOffset = 0;
					if (source->getMapData(O_OBJECT) == snap.low && source->getSprite(O_OBJECT))
					{
						objectSprite = source->getSprite(O_OBJECT); // still there: its animation goes on
						objectOffset = source->getYOffset(O_OBJECT);
					}
					else if (snap.low->getDataset() && snap.low->getDataset()->getSurfaceset())
					{
						// destroyed in the battle: the object as it was
						objectSprite = snap.low->getDataset()->getSurfaceset()->getFrame(snap.low->getSprite(0));
						objectOffset = snap.low->getYOffset();
					}
					if (objectSprite)
					{
						const HdFrame *gray = look == 1 ? hdGrayFloor(surface, objectSprite) : nullptr;
						if (gray)
						{
							surface->blitFrameShaded(*gray, screenPosition.x, screenPosition.y - objectOffset * _k, baseShade);
						}
						else
						{
							surface->blit(objectSprite, screenPosition.x, screenPosition.y - objectOffset * _k, baseShade, false, _nvColor);
						}
					}
				}
			}
		}
	}
}

/**
 * Options::oxceHdBeyondLook 1 (XP-000263): the floor of a palette sprite in greys. The picture the canvas draws for the
 * sprite (the pack's, or the smoothed one) with the luminance of its colours in all three channels and its alpha kept; made
 * once for a sprite and kept for the battle (the ground variants' blends are not made for it: one plain picture).
 * @return The grey frame, or nullptr when the canvas draws the sprite as a palette one (nothing to take the colours from).
 */
const HdFrame *Map::hdGrayFloor(HdCanvas *surface, SurfaceRaw<const Uint8> sprite)
{
	const void *key = sprite.getBuffer();
	auto it = _hdGrayFrames.find(key);
	if (it != _hdGrayFrames.end())
	{
		return it->second.empty() ? nullptr : &it->second;
	}
	HdFrame &gray = _hdGrayFrames[key];
	const HdFrame *color = surface->frameOf(sprite);
	if (!color || color->empty())
	{
		return nullptr;
	}
	gray.width = color->width;
	gray.height = color->height;
	gray.pixels.resize(color->pixels.size());
	for (size_t i = 0; i < color->pixels.size(); ++i)
	{
		const Uint32 p = color->pixels[i];
		const Uint32 l = (77 * ((p >> 16) & 255) + 151 * ((p >> 8) & 255) + 28 * (p & 255) + 128) >> 8;
		gray.pixels[i] = (p & 0xFF000000u) | (l << 16) | (l << 8) | l;
	}
	gray.generated = true;
	gray.buildSpans();
	return &gray;
}

/**
 * Options::oxceHdMapBorder (XP-000380, XP-000382): the border of the battle field along the whole perimeter of the map, on the
 * ground level (z = 0), made of true-colour frames with alpha, one cell's length each (the floor diamond's band for the line, a
 * 16k x 32k frame for the fence). 1: a line about 3 base pixels thick on the outside of the edge, in the metal of the battle
 * panel's theme when the HD interface is on, else warm yellow; 2: a red fence one level high (posts, pickets and rails
 * with gaps between, XP-000420), standing on the edge. Pass 0 goes under the map's cells (the line, and the two far sides of the fence - the map's cells stand before them),
 * pass 1 over them (the two near sides of the fence - they stand before the map's cells). Picture only: nothing of the map is
 * touched, nothing can be clicked, no light.
 */
void Map::hdDrawMapBorder(HdCanvas *surface, const Position &cameraPos, int pass)
{
	const int mode = Options::oxceHdMapBorder;
	if ((mode != 1 && mode != 2) || (mode == 1 && pass != 0))
	{
		return;
	}
	const int sizeX = _save->getMapSizeX(), sizeY = _save->getMapSizeY();
	const int k = _k;
	const int width = surface->getWidth(), height = surface->getHeight();
	if (_hdLightOn)
	{
		_canvas->setLight(nullptr);
	}
	// where the floor diamond of a cell of the ground level starts (its top-left corner)
	auto diamondAt = [&](int x, int y, int &dx, int &dy)
	{
		Position p;
		_camera->convertMapToScreen(Position(x, y, 0), &p);
		p += cameraPos;
		dx = p.x;
		dy = p.y + 24 * k;
	};
	auto frameFor = [&](unsigned long long key, auto &&fill) -> const HdFrame&
	{
		auto it = _hdBorderFrames.find(key);
		if (it == _hdBorderFrames.end())
		{
			HdFrame &made = _hdBorderFrames[key];
			fill(made);
			return made;
		}
		return it->second;
	};
	if (mode == 1)
	{
		// the line's colour: the battle panel's metal (the theme of the windows) when the HD interface is on, else warm yellow
		const Uint32 rgb = (HdUi::active() ? HdBattleHud::metalShade(0.8f) : 0xF0C040u) & 0xFFFFFF;
		const int alpha = 235;
		const double F = 0.2;      // the band is this part of the outer cell's depth (about 3 base pixels)
		const double G = 1.0 - F;
		// kinds: 0 north-east side, 1 south-east, 2 south-west, 3 north-west; 4 top corner, 5 right, 6 bottom, 7 left
		static const double LIM[8][4] = {
			{ 0, 1, G, 1 }, { 0, F, 0, 1 }, { 0, 1, 0, F }, { G, 1, 0, 1 },
			{ G, 1, G, 1 }, { 0, F, G, 1 }, { 0, F, 0, F }, { G, 1, 0, F } };
		auto put = [&](int kind, int x, int y)
		{
			int dx, dy;
			diamondAt(x, y, dx, dy);
			if (!(dx > -32 * k && dx < width && dy > -16 * k && dy < height))
			{
				return;
			}
			const HdFrame &f = frameFor(((unsigned long long)rgb << 8) | (unsigned long long)kind, [&](HdFrame &out)
			{
				fillEdgeBand(out, rgb, alpha, k, LIM[kind][0], LIM[kind][1], LIM[kind][2], LIM[kind][3]);
			});
			surface->blitFrame(f, dx, dy);
		};
		for (int x = 0; x < sizeX; ++x)
		{
			put(0, x, -1);
			put(2, x, sizeY);
		}
		for (int y = 0; y < sizeY; ++y)
		{
			put(3, -1, y);
			put(1, sizeX, y);
		}
		put(4, -1, -1);
		put(5, sizeX, -1);
		put(6, sizeX, sizeY);
		put(7, -1, sizeY);
		return;
	}
	// the fence: one cell's length is a frame 16k wide, 32k tall; the bottom edge of the cell's side runs along the foot
	const Uint32 rgb = 0xE02828;
	const int body = 24, edge = 235;   // the gaps between the pickets barely tinted, the posts almost solid
	auto put = [&](bool down, int x, int y, int offX, int offY)
	{
		int dx, dy;
		diamondAt(x, y, dx, dy);
		dx += offX;
		dy += offY;
		if (!(dx > -16 * k && dx < width && dy > -32 * k && dy < height))
		{
			return;
		}
		const HdFrame &f = frameFor(0x100000000ULL | ((unsigned long long)k << 4) | (unsigned long long)(down ? 1 : 0), [&](HdFrame &out)
		{
			fillFence(out, down, rgb, body, edge, k);
		});
		surface->blitFrame(f, dx, dy);
	};
	if (pass == 0)
	{
		for (int x = 0; x < sizeX; ++x)
		{
			put(true, x, 0, 16 * k, -24 * k);            // north-east side: from the top corner of cell (x, 0) to its right one
		}
		for (int y = 0; y < sizeY; ++y)
		{
			put(false, 0, y, 0, -24 * k);                // north-west side: from the left corner of cell (0, y) to its top one
		}
	}
	else
	{
		for (int y = 0; y < sizeY; ++y)
		{
			put(false, sizeX - 1, y, 16 * k, -16 * k);   // south-east side: from the right corner of cell (sizeX - 1, y) to its bottom one
		}
		for (int x = 0; x < sizeX; ++x)
		{
			put(true, x, sizeY - 1, 0, -16 * k);         // south-west side: from the left corner of cell (x, sizeY - 1) to its bottom one
		}
	}
}

}
