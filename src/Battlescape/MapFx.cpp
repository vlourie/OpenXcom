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
/// HD render (oxceHdBloodCloud): how long a cloud of blood lives by the clock of real time, ms (it goes at the end of the turn if that comes sooner)
const Uint32 BLOOD_CLOUD_MS = 14000;
/// How many puffs a cloud is made of
const int BLOOD_CLOUD_PUFFS = 5;

unsigned int cloudMix(unsigned int h)
{
	h ^= h >> 16; h *= 0x7feb352dU; h ^= h >> 15; h *= 0x846ca68bU; h ^= h >> 16;
	return h;
}
}

/**
 * HD render (oxceHdBloodCloud, XP-000557): a hit on flesh that is drawn under water (where the blood spray is not, XP-000533) starts
 * a cloud of blood at the voxel of the hit - once for each hit: `now` collects the hits of this frame, `_hdCloudSeen` those of the last.
 * Only a picture: the explosion, the tile and the save are read, not touched; the numbers come from hashes, never from the game's random generator.
 */
void Map::hdNoteBloodCloud(const Explosion *explosion, std::vector<std::pair<const Explosion*, int>> &now)
{
	const int frame = explosion->getCurrentFrame();
	now.push_back({ explosion, frame });
	for (const auto &seen : _hdCloudSeen)
	{
		if (seen.first == explosion && seen.second <= frame)
		{
			return;
		}
	}
	if (_hdBloodClouds.size() >= 64)
	{
		_hdBloodClouds.erase(_hdBloodClouds.begin());
	}
	const Position at = explosion->getPosition();
	HdBloodCloud cloud;
	cloud.voxel = at;
	cloud.rgb = explosion->getHdBlood() >= 0 ? explosion->getHdBlood() : 0xA01818;
	cloud.stamp = _save->getTurn() * 4 + (int)_save->getSide();
	cloud.born = SDL_GetTicks();
	cloud.seed = cloudMix((unsigned int)at.x * 73856093u ^ (unsigned int)at.y * 19349663u ^ (unsigned int)at.z * 83492791u ^ (unsigned int)cloud.stamp * 2654435761u ^ cloud.born);
	_hdBloodClouds.push_back(cloud);
}

/**
 * HD render (oxceHdBloodCloud, XP-000557): draws the clouds of blood over the map - a few puffs of the smoke bank (HdSmoke, thin kind) in the
 * blood's colour, see-through, that spread from the hit and melt away; each is a few blits of a frame, no pass over the screen. Only where the
 * player sees the tile. A cloud goes when its time is up, at the end of the turn (the turn or the side changes), and with the option or under no water.
 */
bool Map::hdTestBloodCloud()
{
	if (!Options::oxceHdBloodCloud || _save->getDepth() == 0 || !_save->getSelectedUnit())
	{
		return false;
	}
	HdBloodCloud cloud;
	cloud.voxel = _save->getSelectedUnit()->getPosition().toVoxel() + Position(8, 8, 12);
	cloud.rgb = 0xA01818;
	cloud.stamp = _save->getTurn() * 4 + (int)_save->getSide();
	cloud.born = SDL_GetTicks();
	cloud.seed = cloudMix((unsigned int)cloud.born);
	_hdBloodClouds.push_back(cloud);
	return true;
}

void Map::hdDrawBloodClouds(HdCanvas *surface)
{
	if (_hdBloodClouds.empty())
	{
		return;
	}
	if (!Options::oxceHdBloodCloud || _k <= 1 || surface->getHdMode() == HD_MODE_NEAREST || _save->getDepth() == 0)
	{
		_hdBloodClouds.clear();
		return;
	}
	const int stamp = _save->getTurn() * 4 + (int)_save->getSide();
	const Uint32 now = SDL_GetTicks();
	_hdBloodClouds.erase(std::remove_if(_hdBloodClouds.begin(), _hdBloodClouds.end(),
		[&](const HdBloodCloud &c) { return c.stamp != stamp || now - c.born >= BLOOD_CLOUD_MS; }), _hdBloodClouds.end());
	const bool debug = _save->getDebugMode();
	for (const HdBloodCloud &c : _hdBloodClouds)
	{
		const Tile *tile = _save->getTile(c.voxel.toTile());
		if (!tile || !(tile->getVisible() || debug))
		{
			continue;
		}
		Position screen;
		_camera->convertVoxelToScreen(c.voxel, &screen);
		const float p = (float)(now - c.born) / (float)BLOOD_CLOUD_MS;
		const float grow = std::sqrt(p);
		// strength B chosen on the decisions page (XP-000557): full opacity at the peak, half as wide again
		const float opacity = 1.0f * std::min(1.0f, (float)(now - c.born) / 500.0f) * (1.0f - p);
		const int mx = std::max(1, std::max((c.rgb >> 16) & 255, std::max((c.rgb >> 8) & 255, c.rgb & 255)));
		const float tint[3] = { ((c.rgb >> 16) & 255) / (float)mx, ((c.rgb >> 8) & 255) / (float)mx, (c.rgb & 255) / (float)mx };
		const float shade = std::min(6.0f, tile->getShade() * 0.5f);
		const int side = HdSmoke::SIDE * _k;
		for (int i = 0; i < BLOOD_CLOUD_PUFFS; ++i)
		{
			const unsigned int h = cloudMix(c.seed + (unsigned int)i * 0x9e3779b9U);
			const float angle = (h & 255) / 256.0f * 6.2831853f;
			const float reach = (0.35f + ((h >> 8) & 127) / 190.0f) * (4.5f + 21.0f * grow) * _k;
			const int x = screen.x + (int)std::lround(std::cos(angle) * reach) - side / 2;
			const int y = screen.y + (int)std::lround(std::sin(angle) * reach * 0.5f - 3.0f * grow * _k) - side / 2;
			const int life = std::min(HdSmoke::LIFE - 1, 2 + (int)(p * 9.0f) + (int)(i & 1));
			surface->blitFrameToned(HdSmoke::frame(_k, HdSmoke::THIN, (int)((h >> 16) % HdSmoke::SHAPES), life), x, y, shade, tint, opacity);
		}
	}
}

/**
 * Gentle mode: the camera stays put on reaction fire (HdGentle::TRACE_PROJECTILES), so the picture
 * tells where it came from instead - an arrow at the soldier fired at, pointing to the shooter,
 * and the shooter's number in the reaction colour for the rest of the turn. Picture only:
 * the rules never read any of it.
 * @param projectile The projectile just launched.
 */
void Map::noteGentleShot(const Projectile *projectile)
{
	const BattleUnit *shooter = projectile->getActor();
	// during the player's turn only the other sides' reaction fire shoots
	if (!shooter || _save->getSide() != FACTION_PLAYER || shooter->getFaction() == FACTION_PLAYER)
	{
		return;
	}
	if (_gentleTurn != _save->getTurn())
	{
		_gentleTurn = _save->getTurn();
		_gentleShooters.clear();
		_gentleShots.clear();
	}
	// the arrow stays where the soldier stood when fired at and points where the shot came from then:
	// it never follows the soldier or the shooter afterwards
	Position at = projectile->getTarget();
	Tile *tile = _save->getTile(at);
	const BattleUnit *target = tile ? tile->getOverlappingUnit(_save) : nullptr;
	int height = 12;
	if (target)
	{
		at = target->getPosition();
		height = target->getHeight() + target->getFloatHeight() + (target->isBigUnit() ? -8 : 0);
	}
	_gentleFlying = ++_gentleShotId;
	_gentleShots.push_back(GentleShot{ shooter, shooter->getPosition(), at, height, SDL_GetTicks(), _gentleFlying, false, false });
}

/**
 * Gentle mode: the bullet of the shot in flight was drawn - the player has seen its trail here.
 * @param voxel Where the bullet was drawn.
 * @param screen Its point on the canvas.
 * @param width The canvas width.
 */
void Map::noteGentleTrail(const Position &voxel, const Position &screen, int width)
{
	if (!_gentleFlying || screen.x < 0 || screen.y < 0 || screen.x >= width || screen.y >= _visibleMapHeight)
	{
		return;
	}
	for (auto &shot : _gentleShots)
	{
		if (shot.id != _gentleFlying)
		{
			continue;
		}
		_redraw = _redraw || !shot.seen;
		shot.seen = true;
		const Position tile = voxel.toTile();
		if (!shot.seenOrigin && std::abs(tile.x - shot.from.x) <= 1 && std::abs(tile.y - shot.from.y) <= 1 && std::abs(tile.z - shot.from.z) <= 1)
		{
			shot.seenOrigin = true;
			if (std::find(_gentleShooters.begin(), _gentleShooters.end(), shot.shooter) == _gentleShooters.end())
			{
				_gentleShooters.push_back(shot.shooter);
			}
		}
	}
}

/**
 * Gentle mode: has this unit fired a reaction shot at the player's side in this turn?
 * @param unit The unit behind a visible unit indicator.
 * @return True to show its number in the reaction colour.
 */
bool Map::firedReactionThisTurn(const BattleUnit *unit) const
{
	return _gentleTurn == _save->getTurn() && std::find(_gentleShooters.begin(), _gentleShooters.end(), unit) != _gentleShooters.end();
}

/**
 * The reaction arrow pointing one of GENTLE_ARROW_STEPS ways (step 0 to the right, clockwise on
 * the screen), built in world pixels from its outline so its edges stay straight at any scale (R-042).
 * @param step Direction step.
 * @return The arrow sprite, kept until the scale changes.
 */
Surface *Map::gentleArrow(int step)
{
	if (_gentleArrowScale != _k)
	{
		for (auto *&arrow : _gentleArrow)
		{
			delete arrow;
			arrow = nullptr;
		}
		_gentleArrowScale = _k;
	}
	if (_gentleArrow[step])
	{
		return _gentleArrow[step];
	}
	const int size = 24 * _k;
	auto *arrow = new Surface(size, size);
	arrow->clear();
	const double angle = step * 2.0 * M_PI / GENTLE_ARROW_STEPS;
	const double c = std::cos(angle), s = std::sin(angle), k = _k;
	// along the arrow u (tail -9, head tip +10), across it v; m widens the shape by the outline
	auto inside = [&](double u, double v, double m)
	{
		const double av = std::abs(v);
		if (u >= -9 * k - m && u <= 3 * k + m && av <= 1.5 * k + m)
			return true;
		return u >= 3 * k - m && u <= 10 * k + m && av <= (10 * k - u) * 5.0 / 7.0 + m * 1.25;
	};
	arrow->lock();
	for (int y = 0; y < size; ++y)
	{
		for (int x = 0; x < size; ++x)
		{
			const double px = x + 0.5 - size / 2.0, py = y + 0.5 - size / 2.0;
			const double u = px * c + py * s, v = -px * s + py * c;
			if (inside(u, v, 0))
				arrow->setPixel(x, y, HdGentle::REACTION_COLOR);
			else if (inside(u, v, k))
				arrow->setPixel(x, y, 15); // dark rim, readable on any floor
		}
	}
	arrow->unlock();
	_gentleArrow[step] = arrow;
	return arrow;
}

/**
 * Draws the arrows from the soldiers fired at by reaction shots towards the shooters.
 * Steady, no blinking; each goes after HdGentle::REACTION_ARROW_MS.
 * @param surface The canvas.
 */
void Map::drawGentleArrows(HdCanvas *surface)
{
	if (_gentleShots.empty())
	{
		return;
	}
	const Uint32 now = SDL_GetTicks();
	_gentleShots.erase(std::remove_if(_gentleShots.begin(), _gentleShots.end(), [&](const GentleShot &s)
	{
		return _gentleTurn != _save->getTurn() || now - s.ticks > HdGentle::REACTION_ARROW_MS;
	}), _gentleShots.end());
	for (const auto &shot : _gentleShots)
	{
		const Position &at = shot.at;
		if (!shot.seen || at.z > _camera->getViewLevel())
		{
			continue;
		}
		Position here, there;
		_camera->convertMapToScreen(at, &here);
		_camera->convertMapToScreen(shot.from, &there);
		const double dx = there.x - here.x, dy = there.y - here.y;
		if (dx == 0 && dy == 0)
		{
			continue;
		}
		const double angle = std::atan2(dy, dx);
		const int step = ((int)std::lround(angle * GENTLE_ARROW_STEPS / (2.0 * M_PI)) % GENTLE_ARROW_STEPS + GENTLE_ARROW_STEPS) % GENTLE_ARROW_STEPS;
		Surface *arrow = gentleArrow(step);

		// the middle of the body as it stood when fired at (see the visible unit indicators)
		const int cx = here.x + _camera->getMapOffset().x + _spriteWidth / 2 + (int)std::lround(std::cos(angle) * 16 * _k);
		const int cy = here.y + _camera->getMapOffset().y + (Position::TileZ - shot.height / 2) * _k + (int)std::lround(std::sin(angle) * 16 * _k);
		surface->blitClassic(arrow, cx - arrow->getWidth() / 2, cy - arrow->getHeight() / 2, 1);
	}
}

/**
 * HD render test: freezes every animated element of the map at phase 0 and hides
 * the 3D cursor, so that the next draw() is a pure function of the save file and
 * the camera position. The freeze lasts for exactly one drawn frame.
 * @param mapDumpPath Where to write the map surface after that frame (empty = don't).
 */
void Map::hdTestFreeze(const std::string &mapDumpPath)
{
	if (!_hdTestFrozen)
	{
		_hdTestSavedCursorType = _cursorType;
		_hdTestSavedCursorSize = _cursorSize;
	}
	_hdTestFrozen = true;
	_hdTestMapDumpPath = mapDumpPath;

	_save->setAnimFrame(0);
	_animFrame = 0;
	_menuTicks = 0;
	for (int i = 0; i < _save->getMapSizeXYZ(); ++i)
	{
		_save->getTile(i)->hdTestResetAnimation();
	}
	for (auto& tileParticles : _vaporParticles)
	{
		tileParticles.clear();
	}
	for (auto& tileParticles : _vaporParticlesInit)
	{
		tileParticles.clear();
	}
	// the sway of hanging units depends on when the key was pressed: the dump draws them still
	_hoverFade.clear();
	// the live vapor is random, so a fixed cloud takes its place: the dump still covers the vapor
	// path, and two dumps of one save match (every third tile of the view level: a 4x4 patch of
	// puffs of every size and opacity level, the vapor color cycling over the tiles)
	// only the colors whose table changes something: the mod offsets leave most of the slots empty (identity)
	const int vaporSlots = (int)(_transparencies->size() / (Mod::TransparenciesOpacityLevels * Mod::TransparenciesPaletteColors));
	std::vector<Uint8> liveColors;
	for (int c = 0; c < vaporSlots; ++c)
	{
		const Uint8 *lut = _transparencies->data() + c * Mod::TransparenciesOpacityLevels * Mod::TransparenciesPaletteColors;
		for (int i = 0; i < Mod::TransparenciesOpacityLevels * Mod::TransparenciesPaletteColors; ++i)
		{
			if (lut[i] != i % Mod::TransparenciesPaletteColors)
			{
				liveColors.push_back((Uint8)c);
				break;
			}
		}
	}
	const int vaporColors = (int)liveColors.size();
	int puffs = 0;
	if (vaporColors > 0)
	{
		const int z = _camera->getViewLevel();
		for (int y = 0; y < _camera->getMapSizeY(); ++y)
		{
			for (int x = 0; x < _camera->getMapSizeX(); ++x)
			{
				if ((x + 2 * y) % 3 != 0)
				{
					continue;
				}
				auto &tileParticles = _vaporParticles[_camera->getMapSizeX() * y + x];
				for (int n = 0; n < 16; ++n)
				{
					const Position voxel = Position(x, y, z).toVoxel() + Position(2 + 4 * (n % 4), 2 + 4 * (n / 4), 4 + 6 * (n % 3));
					Particle p(voxel, Position(0, 0, 0), Position(0, 0, 0), Position(0, 0, 0), 0,
						liveColors[(x + y) % vaporColors], (Uint8)(3 + 10 * (n % 4)), (Uint8)(n / 4));
					p.updateScreenPosition();
					tileParticles.push_back(p);
				}
				std::sort(tileParticles.begin(), tileParticles.end(), [](const Particle& a, const Particle& b){ return a.getLayerZ() < b.getLayerZ(); });
				puffs += 16;
			}
		}
	}
	Log(LOG_INFO) << "HD test: frozen, " << puffs << " vapor puffs of " << vaporColors << " of " << vaporSlots << " color(s) at level " << _camera->getViewLevel();
	_cursorType = CT_NONE;
	_cursorSize = 1;
	_redraw = true;
}

/**
 * Test hook of the SCC wall addressing (OXCE_HD_ADDRESS_RELOAD=<frame>:<file>): on that drawn frame the HD packs
 * of the battle's terrain sets are registered again, reading <file> instead of address.txt - the field must
 * follow before the frame is drawn. Off unless the variable is set.
 */
void Map::addressTestReload()
{
	static const char *env = getenv("OXCE_HD_ADDRESS_RELOAD");
	if (!env || !*env)
	{
		return;
	}
	++_addressTestFrames;
	const std::string spec = env;
	const size_t colon = spec.find(':');
	if (colon == std::string::npos || atoi(spec.substr(0, colon).c_str()) != _addressTestFrames)
	{
		return;
	}
	const std::string file = spec.substr(colon + 1);
	Log(LOG_INFO) << "HD address: test reload of the terrain packs with " << file << " on frame " << _addressTestFrames;
	HdSprites::setAddressFile(file);
	for (MapDataSet *set : *_save->getMapDataSets())
	{
		SurfaceSet *frames = set->getSurfaceset();
		if (!frames)
		{
			continue;
		}
		HdSprites::removeSet(frames);
		HdSprites::loadPack("TERRAIN/" + set->getName() + ".PCK", frames, _k);
		HdSprites::preload(frames);
	}
}

}
