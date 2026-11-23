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
#include "MapHd.h"

namespace OpenXcom
{

/**
 * HD render (Options::oxceHdWeather): picks the weather of the battle once. The ground is the terrain most of the map's
 * blocks come from (or the mission type) looked up in the mod's table hd/weather.txt; the seed is made of what the save
 * holds already (mission, terrains, map size, shade), so a loaded battle has the same weather. Nothing on the
 * underwater, orbital or vacuum maps. The test switch OXCE_HD_WEATHER names a kind for any ground.
 */
void Map::hdWeatherPick()
{
	if (_hdWeatherPicked)
	{
		return;
	}
	_hdWeatherPicked = true;
	_hdWeatherKind = HdWeather::CLEAR;
	Uint32 h = 2166136261u;
	auto feed = [&h](const std::string &s)
	{
		for (unsigned char c : s)
		{
			h = (h ^ c) * 16777619u;
		}
		h = (h ^ 0xFFu) * 16777619u;
	};
	feed(_save->getMissionType());
	std::map<std::string, int> blocks;
	for (const auto &column : _save->getFlattenedMapTerrainNames())
	{
		for (const std::string &name : column)
		{
			++blocks[name];
		}
	}
	for (const auto &b : blocks)
	{
		feed(b.first);
	}
	feed(std::to_string(_save->getMapSizeX() * 10000 + _save->getMapSizeY() * 100 + _save->getMapSizeZ()));
	feed(std::to_string(_save->getGlobalShade()));
	// a battle of its own (Vitali 11.11: the same mission on the same ground was clear every time): where the blocks,
	// the UFO and the craft lie, and the geoscape's time, which stands still while the battle lasts - after a load the
	// weather is the same; nothing here draws on the game's random numbers
	for (const auto &column : _save->getFlattenedMapTerrainNames())
	{
		for (const std::string &name : column)
		{
			feed(name);
		}
	}
	if (const SavedGame *geo = _game->getSavedGame())
	{
		if (const GameTime *t = geo->getTime())
		{
			feed(std::to_string(((((t->getYear() * 13LL + t->getMonth()) * 32 + t->getDay()) * 24 + t->getHour()) * 60 + t->getMinute()) * 60 + t->getSecond()));
		}
	}
	_hdWeatherSeed = h;

	const RuleEnviroEffects *enviro = _save->getEnviroEffects();
	const std::string enviroType = enviro ? enviro->getType() : "";
	std::string ground = "-";
	HdWeather::Biome biome = HdWeather::B_NONE;
	bool cold = enviroType.find("COLD") != std::string::npos;
	if (_save->getDepth() == 0 && !hdVacuum() && !hdOrbitalMap(_save))
	{
		std::map<std::string, std::string> table;
		const std::string path = HdSprites::artPath("weather.txt");
		std::unique_ptr<std::istream> in = FileMap::fileExists(path) ? FileMap::getIStream(path) : nullptr;
		std::string line;
		while (in && std::getline(*in, line))
		{
			if (line.size() >= 3 && (unsigned char)line[0] == 0xEF && (unsigned char)line[1] == 0xBB && (unsigned char)line[2] == 0xBF)
			{
				line.erase(0, 3);
			}
			std::istringstream fields(line);
			std::string name, word;
			if (fields >> name >> word && name[0] != '#')
			{
				table[name] = word;
			}
		}
		std::string best = table.count(_save->getMissionType()) ? _save->getMissionType() : "";
		int most = 0;
		for (const auto &b : blocks)
		{
			if (table.count(b.first) && b.second > most)
			{
				most = b.second;
				best = b.first;
			}
		}
		if (!best.empty())
		{
			ground = best;
			bool coldWord = false;
			biome = HdWeather::biomeOf(table[best], coldWord);
			cold = cold || coldWord;
		}
		if (biome != HdWeather::B_NONE)
		{
			_hdWeatherKind = HdWeather::pick(biome, cold, _hdWeatherSeed);
			// the map's own weather wins: its dust storm and acid rain are the sand and the rain of the picture
			if (enviroType.find("DUST_STORM") != std::string::npos)
				_hdWeatherKind = HdWeather::SANDSTORM;
			else if (enviroType.find("ACID_RAIN") != std::string::npos)
				_hdWeatherKind = HdWeather::RAIN;
		}
		const HdWeather::Kind test = HdWeather::forced();
		if (test != HdWeather::KINDS)
		{
			_hdWeatherKind = test;
		}
	}
	_hdWeatherBiome = biome;
	_hdWeatherExtras = HdWeather::extras(_hdWeatherKind, biome, _hdWeatherSeed);
	Log(LOG_INFO) << "HD weather: ground " << ground << ", biome " << (int)biome << (cold ? " cold" : "") << ", enviro "
		<< (enviroType.empty() ? "-" : enviroType) << " -> " << HdWeather::kindName(_hdWeatherKind) << ", seed " << _hdWeatherSeed
		<< "; tumbleweeds " << _hdWeatherExtras.tumbleweeds << ", dust devils " << _hdWeatherExtras.devils << ", tornado "
		<< (_hdWeatherExtras.tornado ? (_hdWeatherExtras.tornadoLook ? "grey" : "dust") : "no") << ", bolts " << (_hdWeatherExtras.bolts ? "yes" : "no");
}

/**
 * HD render (Options::oxceHdWeather): readies the weather of this frame - the strength and the ground of the turn, the
 * open sky of every column (once a turn) and the fields of the veil. False when the frame has no weather.
 */
bool Map::hdWeatherOn(HdCanvas *surface)
{
	_hdWeatherFrameOn = false;
	if (!Options::oxceHdWeather || surface->getHdMode() == HD_MODE_NEAREST || _camera->getShowSingleLayer())
	{
		return false;
	}
	hdWeatherPick();
	if (_hdWeatherKind == HdWeather::CLEAR)
	{
		return false;
	}
	const int turn = _save->getTurn();
	const int sx = _save->getMapSizeX(), sy = _save->getMapSizeY(), sz = _save->getMapSizeZ();
	const bool newTurn = turn != _hdWeatherTurn || (int)_hdWeatherTop.size() != sx * sy;
	if (newTurn)
	{
		_hdWeatherTurn = turn;
		_hdWeatherPower = HdWeather::power(_hdWeatherSeed, turn);
		_hdWeatherGround = HdWeather::ground(_hdWeatherKind, _hdWeatherSeed, turn);
		// the open sky: the highest level of a column with a floor; what is lower stands under it
		_hdWeatherTop.assign((size_t)sx * sy, 0);
		for (int y = 0; y < sy; ++y)
		{
			for (int x = 0; x < sx; ++x)
			{
				for (int z = sz - 1; z > 0; --z)
				{
					Tile *t = _save->getTile(Position(x, y, z));
					if (t && t->getMapData(O_FLOOR))
					{
						_hdWeatherTop[(size_t)y * sx + x] = z;
						break;
					}
				}
			}
		}
	}
	hdWeatherFields();
	if (newTurn)
	{
		// how much of the view the veil may cover: the discovered columns and the farthest of them from the own units
		int known = 0;
		float farthest = 0;
		for (size_t i = 0; i < _hdWeatherSeen.size(); ++i)
		{
			if (_hdWeatherSeen[i] > 0)
			{
				++known;
				farthest = std::max(farthest, _hdWeatherDist[i]);
			}
		}
		Log(LOG_INFO) << "HD weather: turn " << turn << ", power " << _hdWeatherPower << ", wet " << _hdWeatherGround.wet << ", puddles "
			<< _hdWeatherGround.puddles << ", snow " << _hdWeatherGround.snow << "; discovered " << known << " of " << _hdWeatherSeen.size()
			<< " columns, the farthest " << farthest << " tiles from the own units, the veil from " << HdWeather::veilTiles(_hdWeatherKind);
	}
	// the clock of the fall and the drops; the frame of the render test (hdTestFreeze) is the one at 0, as its animations
	_hdWeatherScene.ms = _hdTestFrozen ? 0 : SDL_GetTicks();
	_hdWeatherFrameOn = true;
	return true;
}

/**
 * HD render (Options::oxceHdWeather): the fields of the view's tiles for the veil - the distance from the nearest own unit,
 * the open sky over the level the camera shows, the distance from the nearest spotted enemy or the cursor.
 */
void Map::hdWeatherFields()
{
	const int w = _camera->getViewSizeX(), l = _camera->getViewSizeY();
	const int sx = _save->getMapSizeX();
	const int level = _camera->getViewLevel();
	const bool turned = _camera->getRotation() != 0;
	const size_t n = (size_t)w * l;
	_hdWeatherDist.assign(n, 1e6f);
	_hdWeatherWindow.assign(n, 1e6f);
	_hdWeatherSky.assign(n, 1.0f);
	_hdWeatherSeen.assign(n, 0.0f);
	// the discovered columns: only the ones not yet known are looked at again
	const int sy = _save->getMapSizeY(), sz = _save->getMapSizeZ();
	if ((int)_hdWeatherKnown.size() != sx * sy)
	{
		_hdWeatherKnown.assign((size_t)sx * sy, 0);
	}
	for (int y = 0; y < sy; ++y)
	{
		for (int x = 0; x < sx; ++x)
		{
			Uint8 &known = _hdWeatherKnown[(size_t)y * sx + x];
			for (int z = 0; z < sz && !known; ++z)
			{
				Tile *t = _save->getTile(Position(x, y, z));
				if (t && t->isDiscovered(O_FLOOR))
				{
					known = 1;
				}
			}
		}
	}
	std::vector<std::pair<float, float>> own, windows;
	for (BattleUnit *unit : *_save->getUnits())
	{
		if (unit->isOut() || unit->getTile() == nullptr)
		{
			continue;
		}
		const Position p = turned ? _camera->worldToView(unit->getPosition()) : unit->getPosition();
		const float cx = p.x + unit->getArmor()->getSize() * 0.5f, cy = p.y + unit->getArmor()->getSize() * 0.5f;
		if (unit->getFaction() == FACTION_PLAYER)
			own.push_back({ cx, cy });
		else if (unit->getVisible())
			windows.push_back({ cx, cy });
	}
	if (_cursorType != CT_NONE && _selectorX >= 0 && _selectorY >= 0)
	{
		windows.push_back({ _selectorX + 0.5f, _selectorY + 0.5f });
	}
	for (int y = 0; y < l; ++y)
	{
		for (int x = 0; x < w; ++x)
		{
			const size_t i = (size_t)y * w + x;
			const float cx = x + 0.5f, cy = y + 0.5f;
			float best = 1e12f;
			for (const auto &p : own)
				best = std::min(best, (p.first - cx) * (p.first - cx) + (p.second - cy) * (p.second - cy));
			_hdWeatherDist[i] = std::sqrt(best);
			best = 1e12f;
			for (const auto &p : windows)
				best = std::min(best, (p.first - cx) * (p.first - cx) + (p.second - cy) * (p.second - cy));
			_hdWeatherWindow[i] = std::sqrt(best);
			const Position world = turned ? _camera->viewToWorld(Position(x, y, 0)) : Position(x, y, 0);
			_hdWeatherSky[i] = _hdWeatherTop[(size_t)world.y * sx + world.x] <= level ? 1.0f : 0.0f;
			_hdWeatherSeen[i] = _hdWeatherKnown[(size_t)world.y * sx + world.x] ? 1.0f : 0.0f;
		}
	}
}

/**
 * HD render (Options::oxceHdWeather): what the weather leaves on an open floor (wet, puddles, snow) and the rings of the
 * drops, right after the floor; lit as the floor is.
 */
void Map::hdWeatherGround(HdCanvas *surface, Tile *tile, const Position &mapPos, const Position &screenPos, int shade)
{
	const int sx = _save->getMapSizeX(), sy = _save->getMapSizeY();
	const int z = mapPos.z;
	if (_hdWeatherTop[(size_t)mapPos.y * sx + mapPos.x] > z || tile->hasNoFloor(_save))
	{
		return;
	}
	// the sides with no open floor of this level beyond: the cover thins out there
	auto open = [&](int x, int y)
	{
		if (x < 0 || y < 0 || x >= sx || y >= sy || _hdWeatherTop[(size_t)y * sx + x] > z)
			return false;
		Tile *t = _save->getTile(Position(x, y, z));
		return t && !t->hasNoFloor(_save);
	};
	int closed = 0;
	if (!open(mapPos.x - 1, mapPos.y)) closed |= HdWeather::SIDE_X0;
	if (!open(mapPos.x + 1, mapPos.y)) closed |= HdWeather::SIDE_X1;
	if (!open(mapPos.x, mapPos.y - 1)) closed |= HdWeather::SIDE_Y0;
	if (!open(mapPos.x, mapPos.y + 1)) closed |= HdWeather::SIDE_Y1;
	const int x = screenPos.x, y = screenPos.y + 24 * _k - tile->getYOffset(O_FLOOR) * _k;
	static const float white[3] = { 1, 1, 1 };
	if (const HdFrame *g = HdWeather::groundFrame(_k, _hdWeatherGround, _hdWeatherSeed, mapPos.x, mapPos.y, closed))
	{
		surface->blitFrameToned(*g, x, y, (float)shade, white);
	}
	HdWeather::Splash rings[HdWeather::SPLASHES];
	const int count = HdWeather::splashes(_hdWeatherKind, _k, _hdWeatherSeed, _hdWeatherScene.ms, _hdWeatherPower, mapPos.x, mapPos.y, rings);
	for (int i = 0; i < count; ++i)
	{
		surface->blitFrameToned(*rings[i].frame, x + rings[i].x, y + rings[i].y, (float)shade, white);
	}
}

/**
 * HD render (Options::oxceHdWeather): the air of the frame - the fall, the tone, the veil, the lightning - over the whole
 * map, as one command of the canvas drawn on the HD workers.
 */
void Map::hdWeatherAir(HdCanvas *surface)
{
	HdWeather::Scene &s = _hdWeatherScene;
	const Position offset = _camera->getMapOffset();
	const float k = (float)_k;
	s.kind = _hdWeatherKind;
	s.k = _k;
	s.seed = _hdWeatherSeed;
	s.power = _hdWeatherPower;
	s.day = 1.0f - std::max(0, std::min(15, _save->getGlobalShade())) / 15.0f;
	s.width = surface->getWidth();
	s.height = surface->getHeight();
	// a canvas pixel in view tiles on the ground (level 0, whatever level the camera shows: the columns stand on it):
	// the inverse of Camera::viewToScreen at the floor's diamond
	s.au = 1 / (32 * k);
	s.bu = 1 / (16 * k);
	s.cu = -offset.x / (32 * k) - offset.y / (16 * k) - 2;
	s.av = -1 / (32 * k);
	s.bv = 1 / (16 * k);
	s.cv = offset.x / (32 * k) - offset.y / (16 * k) - 1;
	s.mapW = _camera->getViewSizeX();
	s.mapL = _camera->getViewSizeY();
	s.dist = _hdWeatherDist.data();
	s.sky = _hdWeatherSky.data();
	s.window = _hdWeatherWindow.data();
	s.known = _hdWeatherSeen.data();
	s.originX = offset.x;
	s.originY = offset.y;
	s.flash = HdWeather::lightning(_hdWeatherKind, _hdWeatherSeed, s.ms);
	HdWeather::prepare(s);
	surface->drawWeather(&s);
	// the snowflakes one by one over the air: each its own size, fall, sway and turn (HdWeather::flakes)
	static std::vector<HdWeather::Flake> flakes;
	HdWeather::flakes(s, flakes);
	for (const HdWeather::Flake &f : flakes)
	{
		surface->blitFrameToned(*f.frame, f.x, f.y, 0.0f, f.tint, f.opacity);
	}
	hdWeatherOver(surface);
	_hdWeatherLastDraw = SDL_GetTicks();
}

/**
 * HD render (Options::oxceHdWeather): can the floor of the ground level at (x, y) bear a tumbleweed - open sky over it, a
 * floor, nothing standing on it, no unit the player sees (a unit the player does not see is never asked about).
 */
bool Map::hdWeatherFree(int x, int y)
{
	const int sx = _save->getMapSizeX(), sy = _save->getMapSizeY();
	if (x < 0 || y < 0 || x >= sx || y >= sy || (int)_hdWeatherTop.size() != sx * sy || _hdWeatherTop[(size_t)y * sx + x] > 0)
		return false;
	Tile *t = _save->getTile(Position(x, y, 0));
	if (!t || t->hasNoFloor(_save) || t->getMapData(O_OBJECT))
		return false;
	BattleUnit *u = t->getUnit();
	return !(u && (u->getFaction() == FACTION_PLAYER || u->getVisible()));
}

/**
 * HD render: a tumbleweed can go from (fromU, fromV) to (u, v) of the ground level: the way crosses no wall, and the ball
 * there keeps clear of what stands around it (a margin to every side and to the front, where it is drawn).
 */
bool Map::hdWeatherClear(void *ctx, float fromU, float fromV, float u, float v)
{
	Map *map = static_cast<Map*>(ctx);
	auto wallX = [map](int x, int y) { Tile *t = map->_save->getTile(Position(x, y, 0)); return t && t->getMapData(O_WESTWALL); };
	auto wallY = [map](int x, int y) { Tile *t = map->_save->getTile(Position(x, y, 0)); return t && t->getMapData(O_NORTHWALL); };
	// one step to a tile next to this one (or this one), the walls on the way
	std::function<bool(int, int, int, int)> step = [&](int ax, int ay, int bx, int by) -> bool
	{
		if (!map->hdWeatherFree(bx, by))
			return false;
		const int dx = bx - ax, dy = by - ay;
		if (dx == 0 && dy == 0)
			return true;
		if (std::abs(dx) > 1 || std::abs(dy) > 1)
			return false;
		if (dx != 0 && dy != 0)
			return (step(ax, ay, bx, ay) && step(bx, ay, bx, by)) || (step(ax, ay, ax, by) && step(ax, by, bx, by));
		if (dx == 1) return !wallX(bx, by);
		if (dx == -1) return !wallX(ax, ay);
		if (dy == 1) return !wallY(bx, by);
		return !wallY(ax, ay);
	};
	const int fx = (int)std::floor(fromU), fy = (int)std::floor(fromV);
	const int cx = (int)std::floor(u), cy = (int)std::floor(v);
	if (!step(fx, fy, cx, cy))
		return false;
	const float M = 0.3f;
	const float around[5][2] = { { M, 0 }, { -M, 0 }, { 0, M }, { 0, -M }, { M, M } };
	for (const auto &a : around)
	{
		if (!step(cx, cy, (int)std::floor(u + a[0]), (int)std::floor(v + a[1])))
			return false;
	}
	return true;
}

/**
 * HD render: a dust devil may rise at (u, v): open sky over the ground there, nothing standing, a column the player knows.
 */
bool Map::hdWeatherOpen(void *ctx, float u, float v)
{
	Map *map = static_cast<Map*>(ctx);
	const int x = (int)std::floor(u), y = (int)std::floor(v);
	const int sx = map->_save->getMapSizeX();
	if (!map->hdWeatherFree(x, y) || (int)map->_hdWeatherKnown.size() != sx * map->_save->getMapSizeY())
		return false;
	return map->_hdWeatherKnown[(size_t)y * sx + x] != 0;
}

/**
 * HD render: a bolt may come down at the canvas point (px, py): the ground there is open and known, five tiles and more from
 * the own units and three from the spotted enemies and the cursor (a strike on the squad would read as a hit).
 */
bool Map::hdWeatherSpot(void *ctx, float px, float py)
{
	Map *map = static_cast<Map*>(ctx);
	const HdWeather::Scene &s = map->_hdWeatherScene;
	const float u = s.au * px + s.bu * py + s.cu, v = s.av * px + s.bv * py + s.cv;
	if (!hdWeatherOpen(ctx, u, v))
		return false;
	const int x = (int)std::floor(u), y = (int)std::floor(v);
	if (!s.dist || !s.window || x >= s.mapW || y >= s.mapL)
		return false;
	const size_t i = (size_t)y * s.mapW + x;
	return s.dist[i] >= 5 && s.window[i] >= 3;
}

/**
 * HD render: tiles from the ground point (u, v) to the nearest own unit, spotted enemy or the cursor (the veil's fields);
 * far off the map or before the fields are made - far.
 */
float Map::hdWeatherAway(void *ctx, float u, float v)
{
	Map *map = static_cast<Map*>(ctx);
	const HdWeather::Scene &s = map->_hdWeatherScene;
	const int x = (int)std::floor(u), y = (int)std::floor(v);
	if (!s.dist || !s.window || x < 0 || y < 0 || x >= s.mapW || y >= s.mapL)
		return 1e6f;
	const size_t i = (size_t)y * s.mapW + x;
	return std::min(s.dist[i], s.window[i]);
}

/**
 * HD render (Options::oxceHdWeather): the tumbleweeds of this frame and the tiles they are drawn in; notes new ones the
 * player can see for the sound.
 */
void Map::hdWeatherRolls()
{
	_hdWeatherRollCount = 0;
	if (_hdWeatherExtras.tumbleweeds <= 0 || _camera->getRotation() != 0)
		return;
	const int sx = _save->getMapSizeX(), sy = _save->getMapSizeY();
	const Position offset = _camera->getMapOffset();
	// the ground in the middle of the view (hdWeatherAir's mapping): a run starting now sets off upwind of it
	const float k = (float)_k, mx = getWidth() * 0.5f, my = getHeight() * 0.5f;
	const float midU = mx / (32 * k) + my / (16 * k) - offset.x / (32 * k) - offset.y / (16 * k) - 2;
	const float midV = -mx / (32 * k) + my / (16 * k) + offset.x / (32 * k) - offset.y / (16 * k) - 1;
	_hdWeatherRollCount = HdWeather::rolls(_hdWeatherExtras, _hdWeatherKind, _hdWeatherSeed, _hdWeatherScene.ms, _hdWeatherPower,
		sx, sy, midU, midV, &Map::hdWeatherClear, this, _hdWeatherRoll);
	for (int i = 0; i < _hdWeatherRollCount; ++i)
	{
		const HdWeather::Roll &r = _hdWeatherRoll[i];
		// the front-most tile the ball reaches: drawn there, after the floors it overlaps (hdWeatherClear keeps it free)
		const int x = std::min(sx - 1, (int)std::floor(r.u + 0.3f)), y = std::min(sy - 1, (int)std::floor(r.v + 0.3f));
		_hdWeatherRollTile[i] = _save->getTileIndex(Position(x, y, 0));
		if (std::find(_hdWeatherSeenIds.begin(), _hdWeatherSeenIds.end(), r.id) == _hdWeatherSeenIds.end())
		{
			Tile *t = _save->getTile(Position(x, y, 0));
			Position screen;
			_camera->convertMapToScreen(Position(x, y, 0), &screen);
			screen += offset;
			if (t && t->isDiscovered(O_FLOOR) && screen.x > -32 * _k && screen.x < getWidth() && screen.y > -40 * _k && screen.y < getHeight())
			{
				_hdWeatherSeenIds.push_back(r.id);
				++_hdWeatherNewRolls;
				_hdWeatherRollPan = (screen.x + 16 * _k) * 2.0f / std::max(1, getWidth()) - 1;
			}
		}
	}
	if (_hdWeatherSeenIds.size() > 64)
		_hdWeatherSeenIds.erase(_hdWeatherSeenIds.begin(), _hdWeatherSeenIds.begin() + 32);
}

/**
 * HD render (Options::oxceHdWeather): the tumbleweeds drawn in this tile - the shadow on the ground, the ball over it -
 * lit as the tile is.
 */
void Map::hdWeatherRollsAt(HdCanvas *surface, const Position &mapPos, const Position &screenPos, int shade)
{
	const int index = _save->getTileIndex(mapPos);
	static const float white[3] = { 1, 1, 1 };
	for (int i = 0; i < _hdWeatherRollCount; ++i)
	{
		if (_hdWeatherRollTile[i] != index)
			continue;
		const HdWeather::Roll &r = _hdWeatherRoll[i];
		const float fu = r.u - mapPos.x, fv = r.v - mapPos.y;
		const int cx = screenPos.x + (int)std::lround((16 + (fu - fv) * 16) * _k);
		const int cy = screenPos.y + (int)std::lround((24 + (fu + fv) * 8) * _k);
		const HdFrame &shadow = HdWeather::rollShadow(_k, r.shape);
		surface->blitFrameToned(shadow, cx - shadow.width / 2, cy - shadow.height / 2, (float)shade, white, r.alpha * (1 - std::min(0.6f, r.hop * 0.12f)));
		const HdFrame &ball = HdWeather::rollFrame(_k, r.shape, r.turn);
		surface->blitFrameToned(ball, cx - ball.width / 2, cy - ball.height - (int)std::lround(r.hop * _k), (float)shade, white, r.alpha);
	}
}

/**
 * HD render: where a whirl at the ground point (u, v) stands (ticket XP-000578, a tornado went through ships and houses):
 * on the top of what the column holds up to the drawn level - a roof, a rock, a hull - in base pixels over the ground;
 * between the tiles the heights blend, so it climbs a roof over a tile of its way and does not jump. Returns how much of
 * it shows: 1 in the open and on the tops, 0 indoors, under a roof the view does not draw (Vitali 16.11, variant A).
 */
float Map::hdWeatherStand(float u, float v, float &lift)
{
	lift = 0;
	const int sx = _save->getMapSizeX(), sy = _save->getMapSizeY(), sz = _save->getMapSizeZ();
	int topZ = sz - 1;
	if (!_camera->getShowAllLayers())
		topZ = std::min(topZ, _camera->getViewLevel());
	// one layer alone on the screen: only that level is drawn, the whirl stands on it
	const int lowZ = _camera->getShowSingleLayer() ? std::max(0, std::min(topZ, _camera->getViewLevel())) : 0;
	if (_camera->getShowSingleLayer())
		topZ = lowZ;
	// one column: the top of the highest drawn thing in it, a floor (its level) or an object (the top of its shape);
	// under a roof the view does not draw (a room seen from its floor) it is indoors, -1
	auto column = [&](int x, int y) -> float
	{
		if (x < 0 || y < 0 || x >= sx || y >= sy)
			return 0;
		if ((int)_hdWeatherTop.size() == sx * sy && _hdWeatherTop[(size_t)y * sx + x] > topZ)
			return -1;
		for (int z = topZ; z >= lowZ; --z)
		{
			Tile *t = _save->getTile(Position(x, y, z));
			if (!t)
				continue;
			int top = -1;
			if (MapData *o = t->getMapData(O_OBJECT))
			{
				for (int layer = 11; layer >= 0; --layer)
				{
					if (o->getLoftID(layer) != 0)
					{
						top = (layer + 1) * 2;
						break;
					}
				}
			}
			if (top < 0 && z > 0 && t->getMapData(O_FLOOR))
				top = 0;
			if (top >= 0)
				return (float)(z * 24 + top);
		}
		return 0;
	};
	const float fu = u - 0.5f, fv = v - 0.5f;
	const int x0 = (int)std::floor(fu), y0 = (int)std::floor(fv);
	const float wu = fu - x0, wv = fv - y0;
	const float h00 = column(x0, y0), h10 = column(x0 + 1, y0), h01 = column(x0, y0 + 1), h11 = column(x0 + 1, y0 + 1);
	auto blend = [&](float a, float b, float c, float d) { return (a * (1 - wu) + b * wu) * (1 - wv) + (c * (1 - wu) + d * wu) * wv; };
	// indoors it is gone; anywhere else it stands on the top
	auto open = [](float h) { return h < 0 ? 0.0f : 1.0f; };
	auto top = [](float h) { return std::max(0.0f, h); };
	lift = blend(top(h00), top(h10), top(h01), top(h11));
	return blend(open(h00), open(h10), open(h01), open(h11));
}

/**
 * HD render (Options::oxceHdWeather): over the air - the dust devils and the tornado on the ground they stand on, the bolt
 * of a strike; notes for the sound how much of the tornado shows and the new dust devils.
 */
void Map::hdWeatherOver(HdCanvas *surface)
{
	_hdWeatherTornadoSeen = 0;
	if (_camera->getRotation() != 0)
		return;
	const HdWeather::Scene &s = _hdWeatherScene;
	const float k = (float)_k;
	const int sx = _save->getMapSizeX(), sy = _save->getMapSizeY();
	static const float white[3] = { 1, 1, 1 };
	const float shade = (float)std::max(0, std::min(15, _save->getGlobalShade()));
	HdWeather::Twister tw[HdWeather::TWISTERS];
	// the ground in the middle of the view: a pass starting now goes by there
	const float midU = s.au * s.width * 0.5f + s.bu * s.height * 0.5f + s.cu, midV = s.av * s.width * 0.5f + s.bv * s.height * 0.5f + s.cv;
	const int n = HdWeather::twisters(_hdWeatherExtras, _hdWeatherKind, _hdWeatherSeed, s.ms, sx, sy, midU, midV, &Map::hdWeatherOpen,
		&Map::hdWeatherAway, this, tw);
	for (int i = 0; i < n; ++i)
	{
		const HdWeather::Twister &t = tw[i];
		// the ground point on the canvas (the inverse of the air's mapping)
		const float A = t.u - s.cu, B = t.v - s.cv;
		float lift = 0;
		const float stand = hdWeatherStand(t.u, t.v, lift);
		const int px = (int)std::lround((A - B) * 16 * k), py = (int)std::lround(((A + B) * 8 - lift) * k);
		// over the ground the player knows; the tornado thins out over the units, the spotted enemies and the cursor
		const int bx = (int)std::floor(t.u), by = (int)std::floor(t.v);
		int known = 0;
		for (int dy = -1; dy <= 1; ++dy)
			for (int dx = -1; dx <= 1; ++dx)
			{
				const int x = bx + dx, y = by + dy;
				if (x >= 0 && y >= 0 && x < sx && y < sy && (int)_hdWeatherKnown.size() == sx * sy && _hdWeatherKnown[(size_t)y * sx + x])
					++known;
			}
		float alpha = t.alpha * known / 9.0f * stand;
		if (t.big)
		{
			alpha *= 0.8f + 0.2f * _hdWeatherPower;
			const int vx = std::max(0, std::min(s.mapW - 1, bx)), vy = std::max(0, std::min(s.mapL - 1, by));
			if (bx >= 0 && by >= 0 && bx < s.mapW && by < s.mapL && s.dist && s.window)
			{
				const float closest = std::min(s.dist[(size_t)vy * s.mapW + vx], s.window[(size_t)vy * s.mapW + vx]);
				alpha *= 0.5f + 0.5f * std::max(0.0f, std::min(1.0f, (closest - 1.5f) / 2.5f));
			}
		}
		if (alpha <= 0.01f)
			continue;
		int baseX = 0, baseY = 0;
		const HdFrame &f = HdWeather::twisterFrame(_k, t.big, _hdWeatherExtras.tornadoLook, s.ms, baseX, baseY);
		const int x = px - baseX, y = py - baseY;
		surface->blitFrameToned(f, x, y, shade, white, alpha);
		const bool onScreen = x + f.width > 0 && x < s.width && y + f.height > 0 && y < s.height;
		if (t.big && onScreen)
		{
			_hdWeatherTornadoSeen = std::max(_hdWeatherTornadoSeen, alpha);
		}
		else if (!t.big && onScreen && std::find(_hdWeatherSeenIds.begin(), _hdWeatherSeenIds.end(), t.id) == _hdWeatherSeenIds.end())
		{
			_hdWeatherSeenIds.push_back(t.id);
			++_hdWeatherNewDevils;
			_hdWeatherDevilPan = px * 2.0f / std::max(1, s.width) - 1;
		}
	}
	if (_hdWeatherExtras.bolts)
	{
		int x = 0, y = 0;
		float opacity = 0;
		if (const HdFrame *b = HdWeather::bolt(_hdWeatherKind, _hdWeatherSeed, s.ms, _k, s.width, s.height, &Map::hdWeatherSpot, this,
			x, y, opacity))
		{
			surface->blitFrameToned(*b, x, y, 0, white, opacity);
		}
	}
}

/**
 * HD render (Options::oxceHdWeatherSound): the weather's sound of this moment, on every tick of the map (the hidden turn of
 * the other side too: the picture stands, the rain goes on).
 */
void Map::hdWeatherHear()
{
	HdWeather::Hearing h;
	if (_hdWeatherFrameOn && Options::oxceHdWeather)
	{
		h.kind = _hdWeatherKind;
		h.seed = _hdWeatherSeed;
		h.power = _hdWeatherPower;
		h.tornado = _hdWeatherTornadoSeen;
		h.newRolls = _hdWeatherNewRolls;
		h.newDevils = _hdWeatherNewDevils;
		h.rollPan = _hdWeatherRollPan;
		h.devilPan = _hdWeatherDevilPan;
	}
	_hdWeatherNewRolls = 0;
	_hdWeatherNewDevils = 0;
	HdWeather::hear(h, SDL_GetTicks());
}

}
