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
/// HD render (oxceHdVolumeSmoke 2): how much of the pack's smoke frame shows through under the puffs (0..1)
const float SMOKE_VEIL_OPACITY = 0.6f;

/**
 * HD render (option oxceHdVolumeSmoke): the puffs of a smoking tile (HdSmoke) over its floor diamond, back to front,
 * each at the light of the field where it floats (bilinear over the nine nodes); without the HD light, at the tile's
 * flat shade. The fire itself is not drawn here.
 */
void drawSmokePuffs(HdCanvas *surface, const Tile *tile, Position screen, int k, int clock, const HdLight *light, int tileShade, float opacity, int crowd)
{
	static std::vector<HdSmoke::Puff> puffs;
	puffs.clear();
	const Position pos = tile->getPosition();
	HdSmoke::puffs(pos.x, pos.y, pos.z, tile->getSmoke(), tile->getFire() > 0, clock, puffs, crowd);
	const int side = HdSmoke::SIDE * k;
	for (const HdSmoke::Puff &p : puffs)
	{
		float shade = (float)tileShade, tint[3] = { 1, 1, 1 };
		if (light)
		{
			const float fu = std::max(0.0f, std::min(2.0f, p.u * 2)), fv = std::max(0.0f, std::min(2.0f, p.v * 2));
			const int i = std::min(1, (int)fu), j = std::min(1, (int)fv);
			const float a = fu - i, b = fv - j;
			const int n = j * 3 + i;
			const auto at = [a, b](float n00, float n01, float n10, float n11)
			{
				return (n00 * (1 - a) + n01 * a) * (1 - b) + (n10 * (1 - a) + n11 * a) * b;
			};
			shade = at(light->shade[n], light->shade[n + 1], light->shade[n + 3], light->shade[n + 4]);
			for (int c = 0; c < 3; ++c)
			{
				tint[c] = at(light->tint[n][c], light->tint[n + 1][c], light->tint[n + 3][c], light->tint[n + 4][c]);
			}
		}
		const int x = screen.x + 16 * k + (int)std::lround((p.u - p.v) * 16 * k) - side / 2;
		const int y = screen.y + 24 * k + (int)std::lround(((p.u + p.v) * 8 - p.h + tile->getTerrainLevel()) * k) - side / 2;
		surface->blitFrameToned(HdSmoke::frame(k, p.kind, p.shape, p.life), x, y, shade, tint, opacity);
	}
}

/**
 * HD render (option oxceHdVolumeFire): the tongues of a burning tile (HdFire) over its floor's ellipse, back to front,
 * at full brightness as the pack's fire; they reach past the tile's sprite, above and to the sides.
 */
void drawFireTongues(HdCanvas *surface, const Tile *tile, Position screen, int k, int clock, float opacity = 1.0f)
{
	static std::vector<HdFire::Tongue> tongues;
	tongues.clear();
	const Position pos = tile->getPosition();
	HdFire::tongues(pos.x, pos.y, pos.z, k, clock, tongues);
	const int y0 = screen.y + tile->getTerrainLevel() * k;
	for (const HdFire::Tongue &g : tongues)
	{
		const HdFire::Sprite s = HdFire::frame(k, g.shape, g.size, g.life, g.mirror);
		const int x = screen.x + (int)std::lround(g.x - HdFire::WIDTH * k / 2.0f) + s.dx;
		const int y = y0 + (int)std::lround(g.y - HdFire::BASE * k) + s.dy;
		if (opacity < 1.0f)
		{
			// next to the battle cursor (XP-000451): see-through, at full brightness (shade 0, white light)
			static const float white[3] = { 1, 1, 1 };
			surface->blitFrameToned(*s.frame, x, y, 0.0f, white, opacity);
		}
		else
		{
			surface->blitFrame(*s.frame, x, y);
		}
	}
}
}

/**
 * The floor of a tile: its frame (turned with the view, with the variant of the ground pattern), the shade of the corners and
 * the weather on it.
 * @param surface The canvas.
 * @param tile The tile.
 * @param tmpSurface The sprite of the floor.
 * @param mapPosition The tile on the map.
 * @param screenPosition The tile on the canvas.
 * @param tileShade The shade of the tile.
 * @param obstacleShade The shade of a part marked as an obstacle.
 * @param turned The view is turned.
 * @param hdFrames The canvas draws the HD frames (not mode 0).
 * @param rot The turn of the view.
 * @param hdWeather The weather is drawn on the ground.
 */
void Map::drawTileFloor(HdCanvas *surface, Tile *tile, SurfaceRaw<const Uint8> tmpSurface, const Position &mapPosition, const Position &screenPosition, int tileShade, int obstacleShade, bool turned, bool hdFrames, int rot, bool hdWeather)
{
	// HD lab: a flat floor turns with the map, unless a view is painted for this turn
	if (turned)
	{
		const SurfaceRaw<const Uint8> view = hdFrames ? _turn->painted(tmpSurface, rot, O_FLOOR) : SurfaceRaw<const Uint8>();
		tmpSurface = view ? view : _turn->floorTurned(tmpSurface, rot, hdFrames);
	}
	// HD render: a floor with pack variants shows the one the ground pattern puts here
	// (turned: the turned frame carries the variants turned too, the pattern stays with the world cell)
	if (_hdGroundVariants)
		surface->setGroundCell(true, mapPosition.x, mapPosition.y, mapPosition.z, rot);
	if (tile->getObstacle(O_FLOOR))
		surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_FLOOR) * _k, obstacleShade, false, _nvColor);
	else
		surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_FLOOR) * _k, tileShade, false, _nvColor);
	if (_hdGroundVariants)
		surface->setGroundCell(false, 0, 0, 0);
	// HD render: the shade of the corners - the floor darkens softly beside the walls and objects on it
	if (Options::oxceHdFloorAo && surface->getHdMode() != HD_MODE_NEAREST && !turned && tile->isDiscovered(O_FLOOR))
	{
		if (const HdFrame *ao = hdFloorAo(tile, mapPosition))
			surface->blitFrame(*ao, screenPosition.x, screenPosition.y + 24 * _k - tile->getYOffset(O_FLOOR) * _k);
	}
	// HD render (Options::oxceHdWeather): the wet, the puddles, the snow and the drops on an open floor
	if (hdWeather && !turned && tile->isDiscovered(O_FLOOR))
	{
		hdWeatherGround(surface, tile, mapPosition, screenPosition, tileShade);
	}
}

/**
 * The marks on the floor of a tile, under all that lies and stands there: the shadows of the units hanging above it, the dents
 * in snow, the bloody soles.
 * @param surface The canvas.
 * @param tile The tile.
 * @param mapPosition The tile on the map.
 * @param screenPosition The tile on the canvas.
 * @param turned The view is turned.
 */
void Map::drawFloorMarks(HdCanvas *surface, Tile *tile, const Position &mapPosition, const Position &screenPosition, bool turned)
{
	// HD render: the shadow of a unit hanging above this floor (Map::hdGatherFlierShadows), under all that stands here
	if (!_hdFlierShadows.empty())
	{
		auto shadows = _hdFlierShadows.find(_save->getTileIndex(mapPosition));
		if (shadows != _hdFlierShadows.end())
		{
			for (const HdFrame *piece : shadows->second)
				surface->blitFrame(*piece, screenPosition.x, screenPosition.y + 24 * _k - tile->getYOffset(O_FLOOR) * _k);
		}
	}
	// HD render (Options::oxceHdBloodSteps, XP-000421): a bloody sole on this floor, after the floor, before what lies and stands here;
	// only on a floor the player has discovered, three tiers of opacity by the age in turns (all the prints of the tile, the oldest first);
	// they last Options::oxceHdBloodStepsLife turns (11 = always)
	// XP-000563 (Options::oxceHdSnowTracks): the dents in snow, the same way, under the blood; they last three turns (HD_SNOW_LIFE, age = tier)
	if (!_hdSnowSteps.empty() && !turned && _save->getDepth() == 0)
	{
		auto dent = _hdSnowSteps.find(_save->getTileIndex(mapPosition));
		if (dent != _hdSnowSteps.end() && tile->isDiscovered(O_FLOOR) && !tile->hasNoFloor(_save))
		{
			for (const HdStep &s : dent->second)
			{
				const int age = _save->getTurn() - s.turn;
				if (age >= 0 && age < HD_SNOW_LIFE)
				{
					surface->blitFrame(hdStepFrame(s.dx, s.dy, s.variant, s.kind, s.rgb, std::min(2, age), s.pattern), screenPosition.x,
						screenPosition.y + 24 * _k + tile->getTerrainLevel() * _k);
				}
			}
		}
	}
	if (!_hdSteps.empty() && !turned && _save->getDepth() == 0)
	{
		auto step = _hdSteps.find(_save->getTileIndex(mapPosition));
		if (step != _hdSteps.end() && tile->isDiscovered(O_FLOOR) && !tile->hasNoFloor(_save))
		{
			const int life = hdStepLife();
			for (const HdStep &s : step->second)
			{
				const int age = _save->getTurn() - s.turn;
				if (age >= 0 && (life == 0 || age < life))
				{
					surface->blitFrame(hdStepFrame(s.dx, s.dy, s.variant, s.kind, s.rgb, hdStepTier(age), s.pattern), screenPosition.x,
						screenPosition.y + 24 * _k + tile->getTerrainLevel() * _k);
				}
			}
		}
	}
}

/**
 * The back cursor on its tile: the far half of the box or of the crosshairs, behind what stands on the tile.
 * @param surface The canvas.
 * @param unit The unit of the tile, if any.
 * @param screenPosition The tile on the canvas.
 * @param itZ The level of the tile.
 * @param explosiveReticle A thrown explosive is drawn with the reticle frames (oxceHdReticleExplosive).
 */
void Map::drawCursorBack(HdCanvas *surface, BattleUnit *unit, const Position &screenPosition, int itZ, bool explosiveReticle)
{
	const int halfAnimFrame = (_animFrame / 2) % 4;
	const int halfAnimFrameRest = (_animFrame % 2);
	int frameNumber = 0;
	SurfaceRaw<const Uint8> tmpSurface;
	if (_camera->getViewLevel() == itZ)
	{
		int reticleColor = 0;
		if (_cursorType != CT_AIM && !explosiveReticle)
		{
			if (unit && (unit->getVisible() || _save->getDebugMode()))
				frameNumber = halfAnimFrameRest; // yellow box
			else
				frameNumber = 0; // red box
		}
		else
		{
			if (unit && (unit->getVisible() || _save->getDebugMode()))
			{
				frameNumber = 7 + halfAnimFrame; // yellow animated crosshairs, in the shot's damage colour
				reticleColor = reticleColorGroup(_game->getMod(), _save->getBattleGame()->getCurrentAction(), getPalette());
			}
			else
				frameNumber = 6; // red static crosshairs (no target: keeps its red)
		}
		tmpSurface = _game->getMod()->getHdSurfaceSet("CURSOR.PCK")->getFrame(frameNumber);
		surface->blit(tmpSurface, screenPosition.x, screenPosition.y, 0, false, reticleColor);
	}
	else if (_camera->getViewLevel() > itZ)
	{
		frameNumber = 2; // blue box
		tmpSurface = _game->getMod()->getHdSurfaceSet("CURSOR.PCK")->getFrame(frameNumber);
		surface->blit(tmpSurface, screenPosition.x, screenPosition.y, 0);
	}
}

/**
 * The west and the north wall of a tile (the turned view draws its walls by the edges of the view cell and passes these by).
 * @param surface The canvas.
 * @param tile The tile.
 * @param mapPosition The tile on the map.
 * @param screenPosition The tile on the canvas.
 * @param turned The view is turned.
 * @param obstacleShade The shade of a part marked as an obstacle.
 * @param addressObstacleEvery The test hook of the SCC addressing: every n-th cell takes the obstacle path (0 - none).
 */
void Map::drawTileWalls(HdCanvas *surface, Tile *tile, const Position &mapPosition, const Position &screenPosition, bool turned, int obstacleShade, int addressObstacleEvery)
{
	SurfaceRaw<const Uint8> tmpSurface;
	// Draw west wall
	// HD render: the wall blits are labelled with their cell for the SCC addressing (paths W1, W2, N1..N4);
	// the obstacle test hook only takes the obstacle path in the drawing, the tile is not touched
	const bool addressObstacle = addressObstacleEvery > 0 && (mapPosition.x * 7 + mapPosition.y * 3 + mapPosition.z) % addressObstacleEvery == 0;
	tmpSurface = turned ? SurfaceRaw<const Uint8>() : tile->getSprite(O_WESTWALL);
	if (tmpSurface)
	{
		int wallShade = getWallShade(O_WESTWALL, tile);
		const bool obstacle = tile->getObstacle(O_WESTWALL) || addressObstacle;
		if (_hdTerrainAddress)
			surface->setCellAddress(HdSprites::WALL_WEST, mapPosition.x, mapPosition.y, mapPosition.z, obstacle ? 2 : 1);
		if (obstacle)
			surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_WESTWALL) * _k, obstacleShade, false, _nvColor);
		else
			surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_WESTWALL) * _k, wallShade, false, _nvColor);
		if (_hdTerrainAddress)
			surface->setCellAddress(0, 0, 0, 0, 0);
	}
	// Draw north wall
	tmpSurface = turned ? SurfaceRaw<const Uint8>() : tile->getSprite(O_NORTHWALL);
	if (tmpSurface)
	{
		int wallShade = getWallShade(O_NORTHWALL, tile);
		const bool obstacle = tile->getObstacle(O_NORTHWALL) || addressObstacle;
		const bool half = bool(tile->getSprite(O_WESTWALL));
		if (_hdTerrainAddress)
			surface->setCellAddress(HdSprites::WALL_NORTH, mapPosition.x, mapPosition.y, mapPosition.z, (obstacle ? 5 : 3) + (half ? 1 : 0));
		if (obstacle)
			surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_NORTHWALL) * _k, obstacleShade, half, _nvColor);
		else
			surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_NORTHWALL) * _k, wallShade, half, _nvColor);
		if (_hdTerrainAddress)
			surface->setCellAddress(0, 0, 0, 0, 0);
	}
}

/**
 * The item on top of the floor of a tile: its shadow, the item, the indicator of an unconscious unit lying there.
 * @param surface The canvas.
 * @param itemSprite The drawer of items of this frame.
 * @param tile The tile.
 * @param item The top item of the tile.
 * @param screenPosition The tile on the canvas.
 * @param tileShade The shade of the tile.
 * @param turned The view is turned.
 */
void Map::drawFloorItem(HdCanvas *surface, ItemSprite &itemSprite, Tile *tile, BattleItem *item, const Position &screenPosition, int tileShade, bool turned)
{
	// HD render: the item's shadow first, at the same place (from its frame's alpha, Map::hdItemShadow); not
	// under a piece of a big unit's body: the piece drawn later would shade the one beside it (Vitali 30.10)
	const BattleUnit *body = item->getUnit();
	if (Options::oxceHdItemShadow && surface->getHdMode() != HD_MODE_NEAREST && !turned
		&& !(body && body->getArmor()->getSize() > 1))
	{
		const Surface *floorSprite = itemSprite.getFloorSprite(item, tileShade);
		if (const HdFrame *shadow = floorSprite ? hdItemShadow(surface, floorSprite) : nullptr)
			surface->blitFrame(*shadow, screenPosition.x - 3 * _k, screenPosition.y + (tile->getTerrainLevel() - 3) * _k);
	}
	itemSprite.draw(item,
		screenPosition.x,
		screenPosition.y + tile->getTerrainLevel() * _k,
		tileShade
	);
	if (_anyIndicator)
	{
		BattleUnit *itemUnit = item->getUnit();
		if (itemUnit && itemUnit->getStatus() == STATUS_UNCONSCIOUS && itemUnit->indicatorsAreEnabled())
		{
			// the same pulse as the indicators on the inventory's ground grid (Inventory::drawItems); mode 0 keeps the classic still shade
			static const int Pulsate[8] = { 0, 1, 2, 3, 4, 3, 2, 1 };
			const bool still = surface->getHdMode() == HD_MODE_NEAREST;
			const int indicatorShade = still ? tileShade : std::min(15, tileShade + Pulsate[_animFrame % 8]);
			// the phases share the classic pixels, so mode 0 would draw the same with any of them
			auto phase = [&](const std::vector<Surface*> &frames) { return frames[still ? 0 : _animFrame % frames.size()]; };
			if (!_burnIndicator.empty() && itemUnit->getFire() > 0)
			{
				surface->blit(phase(_burnIndicator),
					screenPosition.x,
					screenPosition.y + tile->getTerrainLevel() * _k,
					indicatorShade);
			}
			// XP-000533: the HD drops of one who bleeds are not drawn under water (the classic still image stays)
			else if (!_woundIndicator.empty() && itemUnit->getFatalWounds() > 0 && !(_save->getDepth() > 0 && !still))
			{
				surface->blit(phase(_woundIndicator),
					screenPosition.x,
					screenPosition.y + tile->getTerrainLevel() * _k,
					indicatorShade);
			}
			else if (!_shockIndicator.empty() && itemUnit->hasNegativeHealthRegen())
			{
				surface->blit(phase(_shockIndicator),
					screenPosition.x,
					screenPosition.y + tile->getTerrainLevel() * _k,
					indicatorShade);
			}
			else if (!_stunIndicator.empty())
			{
				surface->blit(phase(_stunIndicator),
					screenPosition.x,
					screenPosition.y + tile->getTerrainLevel() * _k,
					indicatorShade);
			}
		}
	}
}

/**
 * The smoke and the fire of a tile: the pack's frame, or in HD the tongues of flame, the puffs and the veil of the options.
 * @param surface The canvas.
 * @param tile The tile.
 * @param mapPosition The tile on the map.
 * @param screenPosition The tile on the canvas.
 * @param itX, itY, itZ The tile on the map.
 * @param tileShade The shade of the tile.
 * @param cursorFadeOn The volumetric smoke and fire by the cursor are drawn see-through (XP-000451).
 */
void Map::drawSmokeFire(HdCanvas *surface, Tile *tile, const Position &mapPosition, const Position &screenPosition, int itX, int itY, int itZ, int tileShade, bool cursorFadeOn)
{
	const int halfAnimFrame = (_animFrame / 2) % 4;
	const int halfAnimFrameRest = (_animFrame % 2);
	int frameNumber = 0;
	SurfaceRaw<const Uint8> tmpSurface;
	const auto cursorFade = [&](int tx, int ty, int tz)
	{
		if (!cursorFadeOn || (tz != _camera->getViewLevel() && tz != _camera->getViewLevel() + 1))
			return 1.0f;
		if (tx < _selectorX - _cursorSize || tx > _selectorX + 1 || ty < _selectorY - _cursorSize || ty > _selectorY + 1)
			return 1.0f;
		return 0.4f;
	};
	frameNumber = 0;
	int shade = 0;
	if (!tile->getFire())
	{
		if (_save->getDepth() > 0)
		{
			frameNumber += Mod::UNDERWATER_SMOKE_OFFSET;
		}
		else
		{
			frameNumber += Mod::SMOKE_OFFSET;
		}
		if (Mod::EXTENDED_SMOKE_OFFSET == 0)
		{
			frameNumber += int(floor((tile->getSmoke() / 6.0) - 0.1)); // see http://www.ufopaedia.org/images/c/cb/Smoke.gif
		}
		else if (Mod::EXTENDED_SMOKE_OFFSET == 1)
		{
			frameNumber += int(floor((tile->getSmoke() / 6.0) - 0.1)) * 4;
		}
		else // if (Mod::EXTENDED_SMOKE_OFFSET == 2)
		{
			frameNumber += (tile->getSmoke() - 1) / 5 * 4;
		}
		shade = tileShade;
	}

	// HD render: every tile animates by its own clock and at the pace of the options
	// (hdEnviClock); the classic frame of mode 0 stays the stock one
	const bool hdEnvi = surface->getHdMode() != HD_MODE_NEAREST;
	const int enviClock = hdEnvi ? hdEnviClock(_animFrame, tile->getPosition(),
		tile->getFire() ? Options::oxceHdFirePace : Options::oxceHdSmokePace) : 0;
	const int enviHalf = hdEnvi ? (enviClock / 2) % 4 : halfAnimFrame;
	const int enviRest = hdEnvi ? enviClock % 2 : halfAnimFrameRest;
	if (enviHalf + tile->getAnimationOffset() > 3)
	{
		frameNumber += enviHalf + tile->getAnimationOffset() - 4;
	}
	else
	{
		frameNumber += enviHalf + tile->getAnimationOffset();
	}
	tmpSurface = _game->getMod()->getHdSurfaceSet("SMOKE.PCK")->getFrame(frameNumber);
	if (hdEnvi)
	{
		// HD render: the fire burns on the tile's surface (a raised object, a bank), as the
		// items lying there are drawn, not sunk into it; on the odd animation tick the
		// pack's in-between picture of the frame (variant 1), if it has one, doubles the
		// fire's frame rate; a fire style of oxceHdFire takes the pack's variants 2s and 2s + 1
		// instead (a pack without them keeps its own fire)
		// (option oxceHdVolumeSmoke: puffs instead of the pack's smoke, soot over its fire; not under
		// night vision nor water, which keep the pack's frame)
		// (option oxceHdVolumeFire: tongues of flame instead of the pack's fire, under the same limits)
		// (oxceHdVolumeSmoke 2, the veil: the pack's own smoke frame, see-through, under the puffs, in the tile's
		// colours - a smoke without gaps, as under night vision; a burning tile keeps its fire and soot)
		const bool puffs = Options::oxceHdVolumeSmoke > 0 && !_nvColor && _save->getDepth() == 0;
		const bool tongues = tile->getFire() && Options::oxceHdVolumeFire && !_nvColor && _save->getDepth() == 0;
		const int variant = tile->getFire() ? (enviRest ? 1 : 0) + 2 * Options::oxceHdFire : 0;
		if (tongues)
		{
			drawFireTongues(surface, tile, screenPosition, _k, enviClock, cursorFade(itX, itY, itZ));
		}
		else if (!puffs || tile->getFire())
		{
			if (variant)
				surface->setFrameVariant(variant);
			surface->blit(tmpSurface, screenPosition.x, screenPosition.y + (tile->getFire() ? tile->getTerrainLevel() * _k : 0), shade, false, _nvColor);
			if (variant)
				surface->setFrameVariant(0);
		}
		if (puffs)
		{
			if (_hdLightOn)
			{
				updateHdLight(tile, tileShade, mapPosition);
			}
			if (Options::oxceHdVolumeSmoke >= 2 && !tile->getFire())
			{
				if (const HdFrame *veil = surface->frameOf(tmpSurface))
				{
					// one flat light over the tile: the centre node of its light field
					static const float white[3] = { 1, 1, 1 };
					const float *veilTint = _hdLightOn ? _hdLight.tint[4] : white;
					surface->blitFrameToned(*veil, screenPosition.x, screenPosition.y,
						_hdLightOn ? _hdLight.shade[4] : (float)tileShade, veilTint,
						SMOKE_VEIL_OPACITY * cursorFade(itX, itY, itZ));
				}
			}
			int crowd = 0;
			if (!tile->getFire())
			{
				for (int dy = -1; dy <= 1; ++dy)
				{
					for (int dx = -1; dx <= 1; ++dx)
					{
						const Tile *nb = (dx || dy) ? _save->getTile(Position(itX + dx, itY + dy, itZ)) : nullptr;
						if (nb && (nb->getSmoke() > 0 || nb->getFire() > 0))
						{
							++crowd;
						}
					}
				}
			}
			drawSmokePuffs(surface, tile, screenPosition, _k, enviClock, _hdLightOn ? &_hdLight : nullptr, tileShade, cursorFade(itX, itY, itZ), crowd);
		}
	}
	else
	{
		surface->blit(tmpSurface, screenPosition.x, screenPosition.y, shade, false, _nvColor);
	}
}

/**
 * The projectile on a tile: a thrown item with its shadow, the pieces of a classic shot or the stamps of a bullet's trail whose
 * step of the way is in this tile. Called by drawTerrain for every tile while a projectile flies in view.
 * @param surface The canvas.
 * @param itemSprite The drawer of items of this frame.
 * @param classicShot The classic shot of this frame (hdFindClassicShot).
 * @param turned The view is turned.
 * @param viewX, viewY The tile in the view.
 * @param itX, itY, itZ The tile on the map.
 * @param tileShade The shade of the tile.
 * @param bulletLowX, bulletLowY, bulletHighX, bulletHighY The view cells the trail of the bullet covers.
 * @param bulletSpan The voxels of the way the stamps of the trail are spread over.
 */
void Map::drawProjectile(HdCanvas *surface, ItemSprite &itemSprite, const HdClassicShot &classicShot, bool turned, int viewX, int viewY, int itX, int itY, int itZ, int tileShade, int bulletLowX, int bulletLowY, int bulletHighX, int bulletHighY, int bulletSpan)
{
	SurfaceRaw<const Uint8> tmpSurface;
	Position bulletPositionScreen;
	const auto bulletBack = [&](int i) { return i * bulletSpan / BULLET_SPRITES; }; // voxels behind the head of stamp i
	auto viewCellOf = [&](const Position &voxel)
	{
		const Position cell(voxel.x / 16, voxel.y / 16, 0);
		return turned ? _camera->worldToView(cell) : cell;
	};
	tmpSurface = nullptr;
	BattleItem* item = _projectile->getItem();
	if (item)
	{
		Position voxelPos = _projectile->getPosition();
		// draw shadow on the floor
		voxelPos.z = _save->getTileEngine()->castedShade(voxelPos);
		if (viewCellOf(voxelPos).x >= viewX &&
			viewCellOf(voxelPos).y >= viewY &&
			viewCellOf(voxelPos).x <= viewX+1 &&
			viewCellOf(voxelPos).y <= viewY+1 &&
			voxelPos.z / 24 == itZ &&
			_save->getTileEngine()->isVoxelVisible(voxelPos))
		{
			_camera->convertVoxelToScreen(voxelPos, &bulletPositionScreen);

			itemSprite.drawShadow(item,
				bulletPositionScreen.x - 16 * _k,
				bulletPositionScreen.y - 26 * _k
			);
		}

		voxelPos = _projectile->getPosition();
		// draw thrown object
		if (viewCellOf(voxelPos).x >= viewX &&
			viewCellOf(voxelPos).y >= viewY &&
			viewCellOf(voxelPos).x <= viewX+1 &&
			viewCellOf(voxelPos).y <= viewY+1 &&
			voxelPos.z / 24 == itZ &&
			_save->getTileEngine()->isVoxelVisible(voxelPos))
		{
			_camera->convertVoxelToScreen(voxelPos, &bulletPositionScreen);

			itemSprite.draw(item,
				bulletPositionScreen.x - 16 * _k,
				bulletPositionScreen.y - 26 * _k,
				tileShade
			);
			if (_gentleFlying)
			{
				noteGentleTrail(voxelPos, bulletPositionScreen, surface->getWidth());
			}
		}
	}
	else
	{
		// draw bullet on the correct tile
		if (classicShot.active)
		{
			// HD render (XP-000544): the pieces of the shot whose step of the way is in this tile (see above); the order
			// is the stamps' - head first when the shot goes away from the viewer, tail first when it comes
			if (classicShot.shot && viewX >= classicShot.lowX && viewX <= classicShot.highX && viewY >= classicShot.lowY && viewY <= classicShot.highY)
			{
				const int count = (int)classicShot.shot->pieces.size();
				for (int n = 0; n < count; ++n)
				{
					const int j = _projectile->isReversed() ? count - 1 - n : n;
					const HdShots::Piece &piece = classicShot.shot->pieces[j];
					if (classicShot.back[j] < 0 || piece.frame.empty())
					{
						continue;
					}
					const Position voxelPos = _projectile->getPosition(1 - classicShot.back[j]);
					if (voxelPos.x / 16 == itX &&
						voxelPos.y / 16 == itY &&
						voxelPos.z / 24 == itZ &&
						_save->getTileEngine()->isVoxelVisible(voxelPos))
					{
						surface->blitFrame(piece.frame, classicShot.head.x + piece.dx, classicShot.head.y + piece.dy);
						if (_gentleFlying)
						{
							_camera->convertVoxelToScreen(voxelPos, &bulletPositionScreen);
							noteGentleTrail(voxelPos, bulletPositionScreen, surface->getWidth());
						}
					}
				}
			}
		}
		else if (viewX >= bulletLowX && viewX <= bulletHighX && viewY >= bulletLowY && viewY <= bulletHighY)
		{
			int begin = 0;
			int end = BULLET_SPRITES;
			int direction = 1;
			if (_projectile->isReversed())
			{
				begin = BULLET_SPRITES - 1;
				end = -1;
				direction = -1;
			}

			for (int i = begin; i != end; i += direction)
			{
				tmpSurface = _projectileSet->getFrame(_projectile->getParticle(i));
				if (tmpSurface)
				{
					Position voxelPos = _projectile->getPosition(1 - bulletBack(i));
					// HD render: one voxel of the trail is k screen pixels and the tracer sprite is
					// only three base pixels wide, so its thirty-five stamps are a row of separate
					// dots with gaps between them. In HD the step to the next voxel is filled with
					// stamps of the same sprite and the shot reads as one beam; the classic path
					// draws the single stamp it always drew
					Position trail = Position(0, 0, 0);
					int steps = 1;
					// (a tiny frame without a dot is one hd/FX/weapons.txt leaves classic: its bars stay one a voxel)
					if (surface->getHdMode() != HD_MODE_NEAREST && (HdSprites::registered(tmpSurface.getBuffer()) || tmpSurface.getWidth() > 4 * _k || bulletSpan > BULLET_SPRITES))
					{
						Position from, to;
						_camera->convertVoxelToScreen(voxelPos, &from);
						_camera->convertVoxelToScreen(_projectile->getPosition(1 - bulletBack(i + 1)), &to);
						const int gap = std::max(std::abs(to.x - from.x), std::abs(to.y - from.y));
						// a stamp every third of the sprite: closer is wasted work, wider leaves a gap
						const int stride = std::max(1, tmpSurface.getWidth() / 3);
						steps = std::max(1, std::min(4, (gap + stride - 1) / stride));
						trail = to - from;
					}
					// k times the original half size (a 3x3 bullet frame is centred on 1, not on 6 at 4x)
					const int halfX = (tmpSurface.getWidth() / _k / 2) * _k;
					const int halfY = (tmpSurface.getHeight() / _k / 2) * _k;
					// draw shadow on the floor
					voxelPos.z = _save->getTileEngine()->castedShade(voxelPos);
					if (voxelPos.x / 16 == itX &&
						voxelPos.y / 16 == itY &&
						voxelPos.z / 24 == itZ &&
						_save->getTileEngine()->isVoxelVisible(voxelPos))
					{
						_camera->convertVoxelToScreen(voxelPos, &bulletPositionScreen);
						for (int s = 0; s < steps; ++s)
						{
							surface->blit(tmpSurface,
								bulletPositionScreen.x - halfX + trail.x * s / steps,
								bulletPositionScreen.y - halfY + trail.y * s / steps, 16, false, _nvColor);
						}
					}

					// draw bullet itself
					voxelPos = _projectile->getPosition(1 - bulletBack(i));
					if (voxelPos.x / 16 == itX &&
						voxelPos.y / 16 == itY &&
						voxelPos.z / 24 == itZ &&
						_save->getTileEngine()->isVoxelVisible(voxelPos))
					{
						_camera->convertVoxelToScreen(voxelPos, &bulletPositionScreen);
						for (int s = 0; s < steps; ++s)
						{
							surface->blit(tmpSurface,
								bulletPositionScreen.x - halfX + trail.x * s / steps,
								bulletPositionScreen.y - halfY + trail.y * s / steps, 0, false, _nvColor);
						}
						if (_gentleFlying)
						{
							noteGentleTrail(voxelPos, bulletPositionScreen, surface->getWidth());
						}
					}
				}
			}
		}
	}
}

/**
 * The front cursor on its tile: the box or the crosshairs (in the colour of the shot's damage), the accuracy and the damage of the aimed
 * attack by the crosshairs, the cursors of the special actions. Called by drawTerrain for the tiles under the cursor.
 * @param surface The canvas.
 * @param tile The tile.
 * @param unit The unit of the tile (or the one drawn there), if any.
 * @param screenPosition The tile on the canvas.
 * @param itX, itY, itZ The tile on the map.
 * @param explosiveReticle A thrown explosive is drawn with the reticle frames (oxceHdReticleExplosive).
 */
void Map::drawCursorFront(HdCanvas *surface, Tile *tile, BattleUnit *unit, const Position &screenPosition, int itX, int itY, int itZ, bool explosiveReticle)
{
	const int halfAnimFrame = (_animFrame / 2) % 4;
	const int halfAnimFrameRest = (_animFrame % 2);
	int frameNumber = 0;
	SurfaceRaw<const Uint8> tmpSurface;
	if (_camera->getViewLevel() == itZ)
	{
		int reticleColor = 0;
		if (_cursorType != CT_AIM && !explosiveReticle)
		{
			if (unit && (unit->getVisible() || _save->getDebugMode()))
				frameNumber = 3 + halfAnimFrameRest; // yellow box
			else
				frameNumber = 3; // red box
		}
		else
		{
			if (unit && (unit->getVisible() || _save->getDebugMode()))
			{
				frameNumber = 7 + halfAnimFrame; // yellow animated crosshairs, in the shot's damage colour
				reticleColor = reticleColorGroup(_game->getMod(), _save->getBattleGame()->getCurrentAction(), getPalette());
			}
			else
				frameNumber = 6; // red static crosshairs (no target: keeps its red)
		}
		tmpSurface = _game->getMod()->getHdSurfaceSet("CURSOR.PCK")->getFrame(frameNumber);
		surface->blit(tmpSurface, screenPosition.x, screenPosition.y, 0, false, reticleColor);

		// UFO extender accuracy: display adjusted accuracy value on crosshair in real-time.
		if (_cursorType >= CT_AIM && _showInfoOnCursor && (_cursorType != CT_THROW || !Options::oxceDisableInfoOnThrowCursor))
		{
			BattleAction *action = _save->getBattleGame()->getCurrentAction();
			const RuleItem *weapon = action->weapon->getRules();
			std::ostringstream ss;
			BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(*action);
			int distanceSq = action->actor->distance3dToPositionSq(Position(itX, itY,itZ));
			int distance = (int)std::ceil(sqrt(float(distanceSq)));

			if (_cursorType == CT_AIM || _cursorType == CT_THROW)
			{
				int accuracy = BattleUnit::getFiringAccuracy(attack, _game->getMod());

				{
					int upperLimit, lowerLimit;
					int dropoff = weapon->calculateLimits(upperLimit, lowerLimit, _save->getDepth(), action->type);

					// at this point, let's assume the shot is adjusted and set the text amber.
					_txtAccuracy->setColor(Palette::blockOffset(Pathfinding::yellow - 1) - 1);

					if (distance > upperLimit)
					{
						accuracy -= (distance - upperLimit) * dropoff;
					}
					else if (distance < lowerLimit)
					{
						accuracy -= (lowerLimit - distance) * dropoff;
					}
					else
					{
						// no adjustment made? set it to green.
						_txtAccuracy->setColor(Palette::blockOffset(Pathfinding::green - 1) - 1);
					}
				}

				// Include LOS penalty for tiles in the unit's current view range
				// Don't recalculate LOS for outside of the current FOV
				int noLOSAccuracyPenalty = action->weapon->getRules()->getNoLOSAccuracyPenalty(_game->getMod());
				if (noLOSAccuracyPenalty != -1)
				{
					bool hasLOS = false;
					if (Position(itX, itY, itZ) == _cacheCursorPosition && _isCtrlPressed == _cacheIsCtrlPressed && _cacheHasLOS != -1)
					{
						// use cached result
						hasLOS = (_cacheHasLOS == 1);
					}
					else
					{
						// recalculate
						if (unit && (unit->getVisible() || _save->getDebugMode()))
						{
							hasLOS = _save->getTileEngine()->visible(action->actor, tile);
						}
						else
						{
							hasLOS = _save->getTileEngine()->isTileInLOS(action, tile, true);
						}
						// remember
						_cacheIsCtrlPressed = _isCtrlPressed;
						_cacheCursorPosition = Position(itX, itY, itZ);
						_cacheHasLOS = hasLOS ? 1 : 0;
					}

					if (!hasLOS)
					{
						accuracy = accuracy * noLOSAccuracyPenalty / 100;
						_txtAccuracy->setColor(Palette::blockOffset(Pathfinding::yellow - 1) - 1);
					}
				}

				bool outOfRange = action->type == BA_THROW
					? weapon->isOutOfThrowRange(distanceSq, _save->getDepth())
					: weapon->isOutOfRange(distanceSq);

				// zero accuracy or out of range: set it red.
				if (accuracy <= 0 || outOfRange)
				{
					accuracy = 0;
					_txtAccuracy->setColor(Palette::blockOffset(Pathfinding::red - 1) - 1);
				}
				ss << accuracy;
				ss << "%";
			}

			//TODO: merge this code with `InventoryState::calculateCurrentDamageTooltip` as 90% is same or should be same
			// display additional damage and psi-effectiveness info (Alt held, or always: HD option)
			if (_isAltPressed || (Options::oxceHdAltInfo & 2))
			{
				// step 1: determine rule
				const RuleItem *rule;
				if (weapon->getBattleType() == BT_PSIAMP)
				{
					rule = weapon;
				}
				else if (action->weapon->needsAmmoForAction(action->type))
				{
					auto* ammo = attack.damage_item;
					if (ammo != nullptr)
					{
						rule = ammo->getRules();
					}
					else
					{
						rule = 0; // empty weapon = no rule
					}
				}
				else
				{
					rule = weapon;
				}

				// step 2: check if unlocked
				if (_cacheActiveWeaponUfopediaArticleUnlocked == -1)
				{
					_cacheActiveWeaponUfopediaArticleUnlocked = 0;
					if (_game->getSavedGame()->getMonthsPassed() == -1)
					{
						_cacheActiveWeaponUfopediaArticleUnlocked = 1; // new battle mode
					}
					else if (rule)
					{
						_cacheActiveWeaponUfopediaArticleUnlocked = 1; // assume unlocked
						ArticleDefinition *article = _game->getMod()->getUfopaediaArticle(rule->getType(), false);
						if (article && !Ufopaedia::isArticleAvailable(_game->getSavedGame(), article))
						{
							_cacheActiveWeaponUfopediaArticleUnlocked = 0; // ammo/weapon locked
						}
						if (rule->getType() != weapon->getType())
						{
							article = _game->getMod()->getUfopaediaArticle(weapon->getType(), false);
							if (article && !Ufopaedia::isArticleAvailable(_game->getSavedGame(), article))
							{
								_cacheActiveWeaponUfopediaArticleUnlocked = 0; // weapon locked
							}
						}
					}
				}

				// step 3: calculate and draw
				if (rule && _cacheActiveWeaponUfopediaArticleUnlocked == 1)
				{
					if (rule->getBattleType() == BT_PSIAMP)
					{
						float attackStrength = BattleUnit::getPsiAccuracy(attack);
						float defenseStrength = 30.0f; // indicator ignores: +victim->getArmor()->getPsiDefence(victim);

						float dis = Position::distance(action->actor->getPosition().toVoxel(), Position(itX, itY, itZ).toVoxel());
						int min = attackStrength - defenseStrength - rule->getPsiAccuracyRangeReduction(dis);
						int max = min + 55;
						if (max <= 0)
						{
							ss << "0%";
						}
						else
						{
							ss << min << "-" << max << "%";
						}
					}
					if (rule->getBattleType() != BT_PSIAMP || action->type == BA_USE)
					{
						int totalDamage = 0;
						if (weapon->getIgnoreAmmoPower())
						{
							totalDamage += weapon->getPowerBonus(attack);
							totalDamage -= weapon->getPowerRangeReduction(distance * 16);
						}
						else
						{
							totalDamage += rule->getPowerBonus(attack);
							totalDamage -= rule->getPowerRangeReduction(distance * 16);
						}
						if (totalDamage < 0) totalDamage = 0;
						if (_cursorType != CT_WAYPOINT)
							ss << "\n";
						ss << rule->getDamageType()->getRandomDamage(totalDamage, 1);
						ss << "-";
						ss << rule->getDamageType()->getRandomDamage(totalDamage, 2);
						if (rule->getDamageType()->RandomType == DRT_UFO_WITH_TWO_DICE)
							ss << "*";
					}
				}
				else
				{
					ss << "\n?-?";
				}
			}

			_txtAccuracy->setText(ss.str());
			drawAccuracy(surface, screenPosition.x, screenPosition.y);
		}
		// HD render: what the shooter's stats add to the power of the aimed attack
		if (_cursorType == CT_AIM || _cursorType == CT_THROW)
		{
			drawSkillBonus(surface, screenPosition.x, screenPosition.y);
		}
	}
	else if (_camera->getViewLevel() > itZ)
	{
		frameNumber = 5; // blue box
		tmpSurface = _game->getMod()->getHdSurfaceSet("CURSOR.PCK")->getFrame(frameNumber);
		surface->blit(tmpSurface, screenPosition.x, screenPosition.y, 0);
	}
	if (!_isAltPressed && _cursorType > CT_AIM && _camera->getViewLevel() == itZ)
	{
		bool ignore = false;
		if (_cursorType == CT_PSI || _cursorType == CT_WAYPOINT)
		{
			BattleAction* action = _save->getBattleGame()->getCurrentAction();
			int distanceSq = action->actor->distance3dToPositionSq(Position(itX, itY, itZ));
			if (action->weapon->getRules()->isOutOfRange(distanceSq))
			{
				// weapon doesn't work at this distance, just draw a normal cursor with a red 0% hint text
				ignore = true;
				_txtAccuracy->setColor(Palette::blockOffset(Pathfinding::red - 1) - 1);
				_txtAccuracy->setText("0%");
				drawAccuracy(surface, screenPosition.x, screenPosition.y);
			}
		}
		if (!ignore)
		{
			int frame[6] = { 0, 0, 0, 11, 13, 15 };
			tmpSurface = _game->getMod()->getHdSurfaceSet("CURSOR.PCK")->getFrame(frame[_cursorType] + (_animFrame / 4) % 2);
			surface->blit(tmpSurface, screenPosition.x, screenPosition.y, 0);
		}
	}
}

}
