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
#include "../Engine/HdBlit.h"
#include "../Engine/HdCanvas.h"
#include "../Engine/HdFx.h"
#include "../Engine/HdGentle.h"
#include "../Engine/HdKillCam.h"
#include "../Engine/HdLab.h"
#include "../Engine/HdSprites.h"
#include "../Engine/HdTurn.h"
#include "../Engine/HdTurnGroups.h"
#include "../Engine/HdUi.h"
#include <chrono>
#include <climits>
#include <cmath>
#include <map>
#include <sstream>
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


/*
  1) Map origin is top corner.
  2) X axis goes downright. (width of the map)
  3) Y axis goes downleft. (length of the map
  4) Z axis goes up (height of the map)

           0,0
            /\
           /  \
        y+ \  / x+
            \/

  Compass directions

         W  /\  N
           /  \
           \  /
         S  \/  E

  Unit directions

         6  /\  0
           /  \
           \  /
         4  \/  2

  Big units parts

            /\
           /0 \
          /\  /\
         /2 \/1 \
         \  /\  /
          \/3 \/
           \  /
            \/
 */

namespace OpenXcom
{

namespace
{

/// HD render: the battle view zoom steps, percent (Ctrl + mouse wheel goes one step). The view shrinks at most
/// twice, so the bilinear scale of the canvas to the screen still takes every pixel of it in.
const int VIEW_ZOOMS[] = { 50, 59, 71, 84, 100, 119, 141, 168, 200 };
const int VIEW_ZOOM_COUNT = (int)(sizeof(VIEW_ZOOMS) / sizeof(VIEW_ZOOMS[0]));
const int VIEW_ZOOM_ONE = 4;
/// The zoom the player chose last: the next battle of this run of the game starts with it.
int lastViewZoomStep = VIEW_ZOOM_ONE;

/**
 * The palette index the mod writes a damage type in in the Ufopaedia (interface articleItem, ammoColorDT*,
 * drawn with the battlescape palette); 0 = none (vanilla gives none).
 */
int damageTypeColor(const Mod *mod, const RuleDamageType *dt)
{
	static const char *const ids[DAMAGE_TYPES] = { "ammoColorDTNone", "ammoColorDTAP", "ammoColorDTIN", "ammoColorDTHE",
		"ammoColorDTLaser", "ammoColorDTPlasma", "ammoColorDTStun", "ammoColorDTMelee", "ammoColorDTAcid", "ammoColorDTSmoke",
		"ammoColorDT10", "ammoColorDT11", "ammoColorDT12", "ammoColorDT13", "ammoColorDT14",
		"ammoColorDT15", "ammoColorDT16", "ammoColorDT17", "ammoColorDT18", "ammoColorDT19" };
	if (!dt || dt->ResistType < 0 || dt->ResistType >= DAMAGE_TYPES)
	{
		return 0;
	}
	const RuleInterface *ui = mod->getInterface("articleItem", false);
	const Element *e = ui ? ui->getElementOptional(ids[dt->ResistType]) : nullptr;
	return e && e->color > 0 && e->color < 256 ? e->color : 0;
}

/**
 * The fill of the explosion area when the mod gives its damage type no colour (vanilla): fire orange,
 * stun blue, acid green, smoke grey, laser red, plasma green, the rest (HE and modded types) amber.
 */
Uint32 blastFallbackRgb(const RuleDamageType *dt)
{
	switch (dt ? dt->ResistType : DT_HE)
	{
	case DT_IN: return 0xFF5A14;
	case DT_LASER: return 0xFF3C3C;
	case DT_PLASMA: return 0x50FF78;
	case DT_STUN: return 0x5AAAFF;
	case DT_ACID: return 0x96FF28;
	case DT_SMOKE: return 0xC0C0C0;
	default: return 0xFFA030;
	}
}

/// The opacity of the explosion area's fill where the power is the strongest (60% transparent).
const int BLAST_ALPHA_MAX = 102;
/// The weakest fill, as a part of the strongest (where the power has almost run out): the edge stays visible.
const float BLAST_ALPHA_FLOOR = 0.25f;
/// The opacity steps the fill is drawn with (one cached diamond per step and colour).
const int BLAST_ALPHA_STEPS = 32;

/**
 * The floor diamond of a tile (the bottom 32x16 of the 32x40 frame, k times) filled with one colour at one
 * opacity. The diamonds of neighbouring tiles meet with no gap and no overlap: no pixel centre lies on an
 * edge, so every pixel belongs to exactly one tile and a fill of many tiles is even.
 * Kept for the battle (drawn by the strips after this frame records); at most a few colours by 32 steps.
 */
const HdFrame &blastDiamond(Uint32 rgb, int alpha, int k)
{
	static std::map<unsigned long long, HdFrame> cache;
	const unsigned long long key = ((unsigned long long)rgb << 24) | ((unsigned long long)alpha << 8) | (unsigned long long)k;
	auto it = cache.find(key);
	if (it != cache.end())
	{
		return it->second;
	}
	HdFrame &f = cache[key];
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
	return f;
}

/**
 * The collapse hint over the explosion area: the floor diamond of a tile in hazard stripes, yellow and black
 * along the diamond's edge direction. One cached frame per scale.
 */
const HdFrame &fallDiamond(int k)
{
	static std::map<int, HdFrame> cache;
	auto it = cache.find(k);
	if (it != cache.end())
	{
		return it->second;
	}
	HdFrame &f = cache[k];
	f.width = 32 * k;
	f.height = 16 * k;
	f.pixels.assign((size_t)f.width * f.height, 0);
	const double hw = 16.0 * k, hh = 8.0 * k;
	for (int y = 0; y < f.height; ++y)
	{
		for (int x = 0; x < f.width; ++x)
		{
			if (std::fabs(x + 0.5 - hw) / hw + std::fabs(y + 0.5 - hh) / hh < 1.0)
			{
				const bool yellow = ((x + 2 * y) / (6 * k)) % 2 == 0;
				f.pixels[(size_t)y * f.width + x] = yellow ? 0xB4FFC81Eu : 0x8C141414u;
			}
		}
	}
	f.generated = true;
	f.buildSpans();
	return f;
}

/**
 * The palette group (+ 1) whose colour is the nearest to `rgb` at full brightness, for a damage type the mod
 * gives no colour (vanilla): the reticle then takes the explosion area's fallback colour of that type.
 */
int nearestColorGroup(const SDL_Color *pal, Uint32 rgb)
{
	const int r = (rgb >> 16) & 0xFF, g = (rgb >> 8) & 0xFF, b = rgb & 0xFF;
	int best = 0, bestDist = INT_MAX;
	for (int group = 1; group < 16; ++group)
	{
		// the bright end of the ramp, brought to full brightness: the ramps differ by hue, not by how dark they start
		const SDL_Color &c = pal[group * 16 + 2];
		const int peak = std::max((int)c.r, std::max((int)c.g, (int)c.b));
		if (peak < 32)
		{
			continue;
		}
		const int dr = c.r * 255 / peak - r, dg = c.g * 255 / peak - g, db = c.b * 255 / peak - b;
		const int dist = dr * dr + dg * dg + db * db;
		if (dist < bestDist)
		{
			bestDist = dist;
			best = group;
		}
	}
	return best ? best + 1 : 0;
}

/**
 * The damage type the aimed action would hit with, as ExplosionBState::init takes it: a melee hit of an item
 * that is not a melee weapon its melee type, anything else the damage item's own type (the loaded ammo, or the
 * weapon that is its own ammo). nullptr: nothing to hit with (an empty weapon).
 */
const RuleDamageType *aimDamageType(BattleAction *action)
{
	const BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(*action);
	if (!attack.damage_item)
	{
		return nullptr;
	}
	const RuleItem *rule = attack.damage_item->getRules();
	if (action->type == BA_HIT && rule->getBattleType() != BT_MELEE)
	{
		return rule->getMeleeType();
	}
	return rule->getDamageType();
}

/**
 * The colour group of the yellow reticle (+ 1, as blit's newBaseColor wants): the group of the colour
 * the mod gives the shot's damage type in the Ufopaedia (interface articleItem, ammoColorDT*). A loaded
 * weapon shoots its ammo's type, a weapon that is its own ammo its own, a hit the type ExplosionBState hits
 * with (aimDamageType). A mod that gives the type no colour (vanilla gives none) gets the group nearest to the
 * explosion area's fallback colour of that type. 0 = the stock yellow: the option is off or nothing is loaded.
 */
int reticleColorGroup(const Mod *mod, BattleAction *action, const SDL_Color *pal)
{
	if (!Options::oxceHdReticleDamageColor || !action || !action->weapon)
	{
		return 0;
	}
	const RuleDamageType *dt = aimDamageType(action);
	if (!dt)
	{
		return 0;
	}
	const int color = damageTypeColor(mod, dt);
	return color ? color / 16 + 1 : nearestColorGroup(pal, blastFallbackRgb(dt));
}

/**
 * HD render: the arc the aimed throw or arcing shot would fly if it flew true (no deviation rolled), found the
 * way Projectile::calculateThrow and TileEngine::validateThrow find it - the same target points, curvatures and
 * range - but without validateThrow's obstacle marks on the tiles: a preview changes nothing in the battle.
 * Returns whether a curve reaches the target (`path` is that curve); when none does, `path` is the flattest
 * curve to the first target point, up to what stops it (empty when there is nothing to aim at).
 */
bool aimArc(SavedBattleGame *save, BattleAction action, std::vector<Position> &path)
{
	path.clear();
	TileEngine *te = save->getTileEngine();
	Tile *targetTile = save->getTile(action.target);
	if (!targetTile || !action.actor || !action.actor->getTile())
	{
		return false;
	}
	const Position originVoxel = te->getOriginVoxel(action, 0);
	Position targetVoxel = action.target.toVoxel() + Position(8, 8, (1 + -targetTile->getTerrainLevel()));
	std::vector<Position> targets;
	bool forced = false;
	if (action.type == BA_THROW)
	{
		targets.push_back(targetVoxel);
	}
	else
	{
		BattleUnit *tu = targetTile->getOverlappingUnit(save);
		if (Options::forceFire && save->isCtrlPressed(true) && save->getSide() == FACTION_PLAYER)
		{
			targets.push_back(action.target.toVoxel() + Position(0, 0, 12));
			forced = true;
		}
		else if (tu && (action.actor->getFaction() != FACTION_PLAYER || tu->getVisible()))
		{
			targetVoxel.z += tu->getFloatHeight();
			targets.push_back(targetVoxel + Position(0, 0, tu->getHeight() / 2 + 1));
			targets.push_back(targetVoxel + Position(0, 0, 2));
			targets.push_back(targetVoxel + Position(0, 0, tu->getHeight() - 1));
		}
		else if (targetTile->getMapData(O_OBJECT) != 0)
		{
			targetVoxel = action.target.toVoxel() + Position(8, 8, 0);
			targets.push_back(targetVoxel + Position(0, 0, 13));
			targets.push_back(targetVoxel + Position(0, 0, 8));
			targets.push_back(targetVoxel + Position(0, 0, 23));
			targets.push_back(targetVoxel + Position(0, 0, 2));
		}
		else if (targetTile->getMapData(O_NORTHWALL) != 0)
		{
			targetVoxel = action.target.toVoxel() + Position(8, 0, 0);
			targets.push_back(targetVoxel + Position(0, 0, 13));
			targets.push_back(targetVoxel + Position(0, 0, 8));
			targets.push_back(targetVoxel + Position(0, 0, 20));
			targets.push_back(targetVoxel + Position(0, 0, 3));
		}
		else if (targetTile->getMapData(O_WESTWALL) != 0)
		{
			targetVoxel = action.target.toVoxel() + Position(0, 8, 0);
			targets.push_back(targetVoxel + Position(0, 0, 13));
			targets.push_back(targetVoxel + Position(0, 0, 8));
			targets.push_back(targetVoxel + Position(0, 0, 20));
			targets.push_back(targetVoxel + Position(0, 0, 2));
		}
		else if (targetTile->getMapData(O_FLOOR) != 0)
		{
			targets.push_back(targetVoxel);
		}
	}
	if (targets.empty())
	{
		return false;
	}
	// validateThrow: the first curvature, then what refuses the throw before any curve is tried
	double start;
	if (action.type == BA_THROW)
	{
		start = std::max(0.48, 1.73 / sqrt(sqrt((double)(action.actor->getBaseStats()->strength) / (double)(action.weapon->getTotalWeight()))) + (action.actor->isKneeled() ? 0.1 : 0.0));
	}
	else
	{
		start = 1.73 / sqrt(sqrt(70.0 / 10.0)) + (action.actor->isKneeled() ? 0.1 : 0.0);
	}
	const bool blockedTarget = action.type == BA_THROW
		&& targetTile->getMapData(O_OBJECT)
		&& targetTile->getMapData(O_OBJECT)->getTUCost(MT_WALK) == Pathfinding::INVALID_MOVE_COST
		&& !(targetTile->isBigWall()
		&& (targetTile->getMapData(O_OBJECT)->getBigWall() < 1
		|| targetTile->getMapData(O_OBJECT)->getBigWall() > 3));
	std::vector<Position> flattest;
	if (!blockedTarget && ProjectileFlyBState::validThrowRange(&action, originVoxel, targetTile, save->getDepth()))
	{
		for (const Position &target : targets)
		{
			for (double curvature = start; curvature < 5.0; curvature += 0.5)
			{
				path.clear();
				const int test = te->calculateParabolaVoxel(originVoxel, target, true, &path, action.actor, curvature, Position(0, 0, 0));
				if (path.empty())
				{
					break;
				}
				if (forced || (test != V_OUTOFBOUNDS && Projectile::getPositionFromEnd(path, Projectile::ItemDropVoxelOffset).toTile() == target.toTile()))
				{
					return true;
				}
				if (flattest.empty())
				{
					flattest = path;
				}
			}
		}
	}
	if (flattest.empty())
	{
		te->calculateParabolaVoxel(originVoxel, targets.front(), true, &flattest, action.actor, start, Position(0, 0, 0));
	}
	path.swap(flattest);
	return false;
}

/**
 * One dash of the aim arc: a round dot of `rgb` with a dark rim, so that it reads on a light floor and a dark one.
 * Kept for the battle: a few colours by the scale.
 */
const HdFrame &arcDot(Uint32 rgb, int k)
{
	static std::map<unsigned long long, HdFrame> cache;
	const unsigned long long key = ((unsigned long long)rgb << 8) | (unsigned long long)k;
	auto it = cache.find(key);
	if (it != cache.end())
	{
		return it->second;
	}
	HdFrame &f = cache[key];
	const double r = 1.3 * k, rim = 0.6 * k + 0.5;
	f.width = f.height = (int)std::ceil(2 * (r + rim)) + 2;
	f.pixels.assign((size_t)f.width * f.height, 0);
	const double c = f.width / 2.0;
	for (int y = 0; y < f.height; ++y)
	{
		for (int x = 0; x < f.width; ++x)
		{
			const double d = std::hypot(x + 0.5 - c, y + 0.5 - c);
			if (d < r)
			{
				const double edge = std::min(1.0, r - d);       // the soft edge of the dot over its rim
				const int fr = (int)(((rgb >> 16) & 0xFF) * edge + 16 * (1 - edge));
				const int fg = (int)(((rgb >> 8) & 0xFF) * edge + 16 * (1 - edge));
				const int fb = (int)((rgb & 0xFF) * edge + 16 * (1 - edge));
				f.pixels[(size_t)y * f.width + x] = 0xE6000000u | ((Uint32)fr << 16) | ((Uint32)fg << 8) | (Uint32)fb;
			}
			else if (d < r + rim)
			{
				const int a = (int)(150 * std::min(1.0, r + rim - d));
				f.pixels[(size_t)y * f.width + x] = ((Uint32)a << 24) | 0x101010u;
			}
		}
	}
	f.generated = true;
	f.buildSpans();
	return f;
}

/**
 * The end of a blocked aim arc: a red cross where the flight stops, with a dark rim like the dots.
 */
const HdFrame &arcStop(int k)
{
	static std::map<int, HdFrame> cache;
	auto it = cache.find(k);
	if (it != cache.end())
	{
		return it->second;
	}
	HdFrame &f = cache[k];
	const double half = 4.0 * k, hw = 0.9 * k, rim = 0.6 * k + 0.5;
	f.width = f.height = (int)std::ceil(2 * (half + rim)) + 2;
	f.pixels.assign((size_t)f.width * f.height, 0);
	const double c = f.width / 2.0;
	for (int y = 0; y < f.height; ++y)
	{
		for (int x = 0; x < f.width; ++x)
		{
			const double dx = x + 0.5 - c, dy = y + 0.5 - c;
			if (std::max(std::fabs(dx), std::fabs(dy)) > half + rim)
			{
				continue;
			}
			// the distance to the nearer of the two diagonals
			const double d = std::min(std::fabs(dx - dy), std::fabs(dx + dy)) / std::sqrt(2.0);
			if (d < hw && std::max(std::fabs(dx), std::fabs(dy)) <= half)
			{
				f.pixels[(size_t)y * f.width + x] = 0xF0FF3030u;
			}
			else if (d < hw + rim)
			{
				f.pixels[(size_t)y * f.width + x] = 0x96101010u;
			}
		}
	}
	f.generated = true;
	f.buildSpans();
	return f;
}

}

/**
 * Sets up a map with the specified size and position.
 * @param game Pointer to the core game.
 * @param width Width in pixels.
 * @param height Height in pixels.
 * @param x X position in pixels.
 * @param y Y position in pixels.
 * @param visibleMapHeight Current visible map height.
 */
Map::Map(Game *game, int width, int height, int x, int y, int visibleMapHeight) : InteractiveSurface(width * hdScale(game), height * hdScale(game), x, y),
	_game(game), _isTFTD(false), _arrow(0), _anyIndicator(false), _isAltPressed(false), _isCtrlPressed(false),
	_k(hdScale(game)), _zoomStep(VIEW_ZOOM_ONE), _viewWidth(width * hdScale(game)), _viewHeight(height * hdScale(game)), _visibleBase(visibleMapHeight),
	_messageScratch(0), _messageOnCanvas(false), _canvas(0), _hdGroundVariants(Options::oxceHdGroundVariants), _hdTerrainAddress(Options::oxceHdTerrainAddress),
	_selectorX(0), _selectorY(0), _mouseX(0), _mouseY(0), _cursorType(CT_NORMAL), _cursorSize(1), _animFrame(0),
	_projectile(0), _followProjectile(true), _projectileInFOV(false), _explosionInFOV(false), _launch(false), _visibleMapHeight(visibleMapHeight * hdScale(game)),
	_unitDying(false), _smoothingEngaged(false), _flashScreen(false), _bgColor(15), _projectileSet(0), _showObstacles(false), _showInfoOnCursor(false)
{
	// TODO: extract to a better place later
	for (const auto& pair : Options::mods)
	{
		if (pair.second)
		{
			if (pair.first == "xcom2")
			{
				_isTFTD = true;
				break;
			}
		}
	}

	_iconHeight = _game->getMod()->getInterface("battlescape")->getElement("icons")->h;
	_iconWidth = _game->getMod()->getInterface("battlescape")->getElement("icons")->w;
	_messageColor = _game->getMod()->getInterface("battlescape")->getElement("messageWindows")->color;

	auto* itf = _game->getMod()->getInterface("battlescape")->getElement("thinkingProgressBar");
	_hostileBarColor = itf->color;
	_neutralBarColor = itf->color2;
	_borderBarColor = itf->border;

	PathPreview previewSetting = Options::battleNewPreviewPath;
	_smoothCamera = HdGentle::smoothCamera();
	if (Options::traceAI)
	{
		// turn everything on because we want to see the markers.
		previewSetting = PATH_ARROW_TU;
	}
	_previewSettingArrows = previewSetting & PATH_ARROWS;
	_previewSettingTu     = previewSetting & PATH_TU_COST;
	_previewSettingEnergy = previewSetting & PATH_ENERGY_COST;

	_save = _game->getSavedGame()->getSavedBattle();
	if ((int)(_game->getMod()->getLUTs()->size()) > _save->getDepth())
	{
		_transparencies = &_game->getMod()->getLUTs()->at(_save->getDepth());
	}
	else
	{
		const static std::vector<Uint8> dummy;
		_transparencies = &dummy;
	}

	// HD render: tile sprites are k times the original 32x40 (k comes from BLANKS.PCK, see Mod::getHdScale)
	_spriteWidth = BASE_SPRITE_WIDTH * _k;
	_spriteHeight = BASE_SPRITE_HEIGHT * _k;
	// HD render: the map surface, the camera and every screen offset below are in "world" pixels
	// (k times the base resolution); classic UI elements drawn into the map (message, texts,
	// markers) stay at base resolution and are scaled by HdBlit at blit time.
	// the hidden movement message is a classic UI element: base resolution, base coordinates
	_message = new BattlescapeMessage(320, (visibleMapHeight < 200)? visibleMapHeight : 200, 0, 0);
	_message->setX(_game->getScreen()->getDX());
	_message->setY((visibleMapHeight - _message->getHeight()) / 2);
	_message->setTextColor(_messageColor);
	_camera = new Camera(_spriteWidth, _spriteHeight, _save->getMapSizeX(), _save->getMapSizeY(), _save->getMapSizeZ(), this, visibleMapHeight * _k);
	_scrollMouseTimer = new Timer(SCROLL_INTERVAL);
	_scrollMouseTimer->onTimer((SurfaceHandler)&Map::scrollMouse);
	_scrollKeyTimer = new Timer(SCROLL_INTERVAL);
	_scrollKeyTimer->onTimer((SurfaceHandler)&Map::scrollKey);
	_camera->setScrollTimer(_scrollMouseTimer, _scrollKeyTimer);
	_obstacleTimer = new Timer(2500);
	_obstacleTimer->stop();
	_obstacleTimer->onTimer((SurfaceHandler)&Map::disableObstacles);

	_numUnitMarker = 0;
	clearUnitMarkers();

	_showInfoOnCursor = (Options::oxceShowAccuracyOnCrosshair == 1 && Options::battleUFOExtenderAccuracy) || Options::oxceShowAccuracyOnCrosshair == 2;
	_txtAccuracy = new Text(44, 18, 0, 0);
	_txtAccuracy->setSmall();
	_txtAccuracy->setPalette(_game->getScreen()->getPalette());
	_txtAccuracy->setHighContrast(true);
	_txtAccuracy->initText(_game->getMod()->getFont("FONT_BIG"), _game->getMod()->getFont("FONT_SMALL"), _game->getLanguage());
	_txtSkillBonus = new Text(32, 9, 0, 0);
	_txtSkillBonus->setSmall();
	_txtSkillBonus->setPalette(_game->getScreen()->getPalette());
	_txtSkillBonus->setHighContrast(true);
	_txtSkillBonus->initText(_game->getMod()->getFont("FONT_BIG"), _game->getMod()->getFont("FONT_SMALL"), _game->getLanguage());
	_cacheActiveWeaponUfopediaArticleUnlocked = -1;
	_cacheIsCtrlPressed = false;
	_cacheCursorPosition = TileEngine::invalid;
	_cacheHasLOS = -1;

	_nightVisionOn = false;
	if (Options::oxceToggleNightVisionType == 2)
	{
		// persisted per campaign
		_nightVisionOn = _game->getSavedGame()->getToggleNightVision();
	}
	else if (Options::oxceToggleNightVisionType == 1)
	{
		// persisted per battle
		_nightVisionOn = _save->getToggleNightVision();
	}

	_debugVisionMode = 0;
	if (Options::oxceToggleBrightnessType == 2)
	{
		// persisted per campaign
		_debugVisionMode = _game->getSavedGame()->getToggleBrightness();
	}
	else if (Options::oxceToggleBrightnessType == 1)
	{
		// persisted per battle
		_debugVisionMode = _save->getToggleBrightness();
	}

	_save->setToggleNightVisionTemp(false);
	_save->setToggleNightVisionColorTemp(0);
	_save->setToggleBrightnessTemp(_debugVisionMode);

	_fadeShade = 16;
	_nvColor = 0;
	_fadeTimer = new Timer(FADE_INTERVAL);
	_fadeTimer->onTimer((SurfaceHandler)&Map::fadeShade);
	_fadeTimer->start();

	auto* enviro = _save->getEnviroEffects();
	if (enviro)
	{
		_bgColor = enviro->getMapBackgroundColor();
	}

	// the k-times copies: these are drawn into the map canvas like a sprite, so that a mod
	// shipping hd/UI/<name>.png gets a real HD icon instead of a nearest-scaled 16x16 one,
	// and one shipping hd/UI/anim/<name>/<i>.png gets it animated
	_stunIndicator = _game->getMod()->getHdSurfaceFrames("FloorStunIndicator", false);
	_woundIndicator = _game->getMod()->getHdSurfaceFrames("FloorWoundIndicator", false);
	_burnIndicator = _game->getMod()->getHdSurfaceFrames("FloorBurnIndicator", false);
	_shockIndicator = _game->getMod()->getHdSurfaceFrames("FloorShockIndicator", false);
	_anyIndicator = !_stunIndicator.empty() || !_woundIndicator.empty() || !_burnIndicator.empty() || !_shockIndicator.empty();

	if (enviro)
	{
		if (!enviro->getMapShockIndicator().empty())
		{
			_shockIndicator = _game->getMod()->getHdSurfaceFrames(enviro->getMapShockIndicator(), false);
		}
	}

	_vaporParticlesInit.resize(_camera->getMapSizeY() * _camera->getMapSizeX());
	_vaporParticles.resize(_camera->getMapSizeY() * _camera->getMapSizeX());

	// HD render: the battle view zoom the player chose last (OXCE_HD_VIEW_ZOOM=<percent>: the nearest step,
	// for the headless checks); the 8-bit display has none
	if (_game->getScreen()->isLayered())
	{
		_zoomStep = lastViewZoomStep;
		if (const char *zoom = getenv("OXCE_HD_VIEW_ZOOM"))
		{
			const int percent = atoi(zoom);
			for (int i = 0; i < VIEW_ZOOM_COUNT; ++i)
			{
				if (std::abs(VIEW_ZOOMS[i] - percent) < std::abs(VIEW_ZOOMS[_zoomStep] - percent))
				{
					_zoomStep = i;
				}
			}
		}
	}

	// HD render: every drawing call goes through the canvas - the true-color one when the
	// display is 32-bit (the world layer takes it as is), else the classic 8-bit surface
	createCanvas();
	if (_zoomStep != VIEW_ZOOM_ONE)
	{
		_camera->resize();
		Log(LOG_INFO) << "HD view zoom: " << VIEW_ZOOMS[_zoomStep] << "% (view " << _viewWidth << "x" << _viewHeight << ")";
	}
	HdKillCam::clear();
}

/**
 * Name of the canvas type the map draws on.
 */
const char *Map::getCanvasName() const
{
	return _canvas ? _canvas->getName() : "none";
}

/**
 * (Re)creates the drawing canvas for the current map size and display mode.
 */
void Map::createCanvas()
{
	delete _canvas;
	delete _messageCanvas;
	_messageCanvas = nullptr;
	if (_game->getScreen()->isLayered())
	{
		updateViewSize();
		_canvas = new Canvas32(_viewWidth, _viewHeight, _k);
		_canvas->setPalette(getPalette(), 0, 256);
		_canvas->setHdMode(Options::oxceHdMode);
		_canvas->setGroundSeed(groundSeed());
		_canvas->setWallField(_hdTerrainAddress ? &_wallField : nullptr);
	}
	else
	{
		_zoomStep = VIEW_ZOOM_ONE;
		updateViewSize();
		_canvas = new Canvas8(this);
	}
}

/**
 * HD render: the view size for the map's size and the battle view zoom - the map's size divided by
 * the zoom, whole base pixels; at 100 % exactly the map's size.
 */
void Map::updateViewSize()
{
	const int percent = VIEW_ZOOMS[_zoomStep];
	auto view = [&](int world) { return percent == 100 ? world : (int)std::lround(world / _k * 100.0 / percent) * _k; };
	_viewWidth = view(getWidth());
	_viewHeight = view(getHeight());
	_visibleMapHeight = _viewHeight == getHeight() ? _visibleBase * _k : (int)std::lround(_visibleBase * (double)_viewHeight / getHeight()) * _k;
}

/**
 * HD render: changes the battle view zoom by `steps` of the zoom table. The canvas takes the new view
 * size (its caches stay), the camera counts in it, and the map moves so that the place under the mouse
 * stays under it. The game sees nothing of it: the tiles, the units and the turn are as they were.
 * @param steps Steps to go, positive to zoom in.
 * @return false where the zoom is not available (the 8-bit display).
 */
bool Map::zoomView(int steps)
{
	Canvas32 *canvas32 = dynamic_cast<Canvas32*>(_canvas);
	if (!canvas32)
	{
		return false;
	}
	const int step = Clamp(_zoomStep + steps, 0, VIEW_ZOOM_COUNT - 1);
	if (step == _zoomStep)
	{
		return true;
	}
	// the view point under the mouse before and after: the camera moves by their difference
	const int oldX = (int)((long long)_mouseX * _viewWidth / getWidth());
	const int oldY = (int)((long long)_mouseY * _viewHeight / getHeight());
	_zoomStep = step;
	lastViewZoomStep = step;
	updateViewSize();
	canvas32->resize(_viewWidth, _viewHeight);
	delete _messageCanvas;
	_messageCanvas = nullptr;
	_camera->resize();
	const int newX = (int)((long long)_mouseX * _viewWidth / getWidth());
	const int newY = (int)((long long)_mouseY * _viewHeight / getHeight());
	_camera->scrollXY((newX - oldX) / _k * _k, (newY - oldY) / _k * _k, true);
	Log(LOG_INFO) << "HD view zoom: " << VIEW_ZOOMS[_zoomStep] << "% (view " << _viewWidth << "x" << _viewHeight << ")";
	return true;
}

/**
 * HD render: the battle view zoom, percent.
 */
int Map::getViewZoomPercent() const
{
	return VIEW_ZOOMS[_zoomStep];
}

/**
 * HD render: the seed of the ground variant pattern - a hash of the battle's
 * map blocks and size, so a battle keeps its look after a save and a load and
 * another battle on the same terrain gets other patches.
 */
Uint32 Map::groundSeed() const
{
	Uint32 h = 2166136261u;
	auto mix = [&h](const std::string &s)
	{
		for (unsigned char c : s)
		{
			h = (h ^ c) * 16777619u;
		}
		h = (h ^ 0xFF) * 16777619u;
	};
	mix(std::to_string(_save->getMapSizeX()) + "x" + std::to_string(_save->getMapSizeY()) + "x" + std::to_string(_save->getMapSizeZ()));
	for (const auto &column : _save->getFlattenedMapBlockNames())
	{
		for (const auto &name : column)
		{
			mix(name);
		}
	}
	return h;
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

/**
 * Selects how the true-color canvas draws palette sprites (HdMode) and redraws.
 * @param mode HD_MODE_NEAREST, HD_MODE_PACKS or HD_MODE_SMOOTH.
 */
void Map::setHdMode(int mode)
{
	if (_canvas)
	{
		_canvas->setHdMode(mode);
		_redraw = true;
	}
}

/**
 * The mode the canvas draws palette sprites with (HD_MODE_NEAREST on the classic canvas).
 */
int Map::getHdMode() const
{
	return _canvas ? _canvas->getHdMode() : 0;
}

/**
 * HD render scale factor: how many times bigger than the original 32x40 the tile
 * sprites are (read from BLANKS.PCK frame 0). 1 = original resolution.
 * @param game Pointer to the core game.
 * @return k >= 1.
 */
int Map::hdScale(Game *game)
{
	return game->getMod()->getHdScale();
}

/**
 * Speed of the fire or smoke animation at a step of its pace option.
 * @param pace Step of oxceHdFirePace / oxceHdSmokePace, clamped to 0..HD_ENVI_PACES - 1.
 * @return Percent of the stock speed: 0 stock, every next step slower.
 */
int Map::hdEnviPercent(int pace)
{
	static const int Percent[HD_ENVI_PACES] = { 100, 75, 50, 35, 25 };
	return Percent[Clamp(pace, 0, HD_ENVI_PACES - 1)];
}

/**
 * The clock a burning or smoking tile animates by in the HD modes. Every tile starts at its
 * own point of the loop and runs at its own pace (85..115 percent of the option's speed), so
 * neighbouring fires and clouds drift apart and never move in step. The tile's share comes
 * from a hash of its position, not from RNG: the picture only, the rolls of the game stay the same.
 * @param animFrame The battle animation frame (SavedBattleGame::getAnimFrame, 100 ms ticks).
 * @param pos Position of the tile.
 * @param pace Step of the pace option (hdEnviPercent).
 * @return Ticks: the frame of a 4-frame loop is clock / 2 % 4, its in-between picture clock % 2.
 */
int Map::hdEnviClock(int animFrame, Position pos, int pace)
{
	Uint32 h = (Uint32)pos.x * 73856093u ^ (Uint32)pos.y * 19349663u ^ (Uint32)pos.z * 83492791u;
	h ^= h >> 13;
	h *= 0x5bd1e995u;
	h ^= h >> 15;
	const Sint64 rate = (Sint64)hdEnviPercent(pace) * (85 + (int)(h % 31));   // percent of percent
	return (int)((Sint64)animFrame * rate / 10000) + (int)((h >> 8) % 64);
}

/**
 * Deletes the map.
 */
Map::~Map()
{
	delete _scrollMouseTimer;
	delete _scrollKeyTimer;
	delete _fadeTimer;
	delete _obstacleTimer;
	delete _arrow;
	delete _message;
	delete _messageScratch;
	delete _canvas;
	delete _messageCanvas;
	delete _turn;
	delete _turnGroups;
	delete _camera;
	delete _txtAccuracy;
	delete _txtSkillBonus;
	delete _numUnitMarker;
	for (auto *arrow : _gentleArrow)
	{
		delete arrow;
	}
	for (auto &loose : _looseHits)
	{
		delete loose.explosion;
	}
}

/**
 * Initializes the map.
 */
void Map::init()
{
	// load the tiny arrow into a surface
	int f = Palette::blockOffset(1); // yellow
	int b = 15; // black
	int pixels[81] = { 0, 0, b, b, b, b, b, 0, 0,
					   0, 0, b, f, f, f, b, 0, 0,
					   0, 0, b, f, f, f, b, 0, 0,
					   b, b, b, f, f, f, b, b, b,
					   b, f, f, f, f, f, f, f, b,
					   0, b, f, f, f, f, f, b, 0,
					   0, 0, b, f, f, f, b, 0, 0,
					   0, 0, 0, b, f, b, 0, 0, 0,
					   0, 0, 0, 0, b, 0, 0, 0, 0 };

	_arrow = new Surface(9, 9);
	_arrow->setPalette(this->getPalette());
	_arrow->lock();
	for (int y = 0; y < 9;++y)
		for (int x = 0; x < 9; ++x)
			_arrow->setPixel(x, y, pixels[x+(y*9)]);
	_arrow->unlock();

	// number drawn above the units that the selected unit sees directly
	delete _numUnitMarker;
	_numUnitMarker = new NumberText(16, 10, 0, 0);
	_numUnitMarker->setPalette(this->getPalette());
	_numUnitMarker->setBordered(true);

	_projectile = 0;
	if (_save->getDepth() == 0)
	{
		_projectileSet = _game->getMod()->getHdSurfaceSet("Projectiles");
	}
	else
	{
		_projectileSet = _game->getMod()->getHdSurfaceSet("UnderwaterProjectiles");
	}
}

/**
 * Clears all on-map markers of the visible unit indicators.
 */
void Map::clearUnitMarkers()
{
	for (int i = 0; i < UNIT_MARKER_MAX; ++i)
	{
		_unitMarkerUnit[i] = 0;
		_unitMarkerColor[i] = 0;
	}
}

/**
 * Sets an on-map marker for one visible unit indicator.
 * @param index Index of the indicator (0-based); the number drawn is index+1.
 * @param unit Unit to mark, 0 to clear the slot.
 * @param color Color of the number.
 */
void Map::setUnitMarker(int index, const BattleUnit *unit, Uint8 color)
{
	if (index < 0 || index >= UNIT_MARKER_MAX)
	{
		return;
	}
	_unitMarkerUnit[index] = unit;
	_unitMarkerColor[index] = color;
}

/**
 * Keeps the animation timers running.
 */
void Map::think()
{
	_scrollMouseTimer->think(0, this);
	_scrollKeyTimer->think(0, this);
	_fadeTimer->think(0, this);
	_obstacleTimer->think(0, this);
	// HD render: a running muzzle flash needs every frame, not only the game's ticks
	if (Options::oxceHdFx && _canvas->getHdMode() != HD_MODE_NEAREST && HdFx::active(SDL_GetTicks()))
	{
		_redraw = true;
	}
	// a collapse shaking the picture needs every frame until it is still again
	if (_shakeMs && SDL_GetTicks() - _shakeStart <= _shakeMs)
	{
		_redraw = true;
	}
	// loose hits: each sprite goes on at its own frame time, whatever battle state runs now
	if (!_looseHits.empty())
	{
		const Uint32 now = SDL_GetTicks();
		for (auto loose = _looseHits.begin(); loose != _looseHits.end();)
		{
			bool alive = true;
			while (alive && (Sint32)(now - loose->next) >= 0)
			{
				alive = loose->explosion->animate();
				loose->next += loose->frameMs;
				_redraw = true;
			}
			if (alive)
			{
				++loose;
			}
			else
			{
				delete loose->explosion;
				loose = _looseHits.erase(loose);
			}
		}
	}
}

/**
 * Draws the whole map, part by part.
 */
void Map::draw()
{
	if (!_redraw || AiProbe::fast())
	{
		return;
	}

	// normally we'd call for a Surface::draw();
	// but we don't want to clear the background with colour 0, which is transparent (aka black)
	// we use colour 15 because that actually corresponds to the colour we DO want in all variations of the xcom and tftd palettes.
	// Note: un-hardcoded the color from 15 to ruleset value, default 15
	_redraw = false;
	// HD lab: the battle map turned to another side (Engine/HdLab.h), as the options or the keys left it
	_camera->setRotation(HdLab::mapRotation());
	const auto drawStart = std::chrono::steady_clock::now();
	_hdLabels.clear();
	_hdLabelsOn = hdLabelsWanted();
	if (Options::oxceHdBackdrop)
	{
		// the backdrop beyond the map's edge as a gradient around the environment's colour (a palette canvas: flat as ever)
		// (the ground's line of the mod's table hd/backdrop.txt, when there is one, in place of the environment's color)
		_canvas->fillBackdrop(Palette::blockOffset(0) + _bgColor, hdBackdropRgb());
	}
	else
	{
		_canvas->fill(Palette::blockOffset(0) + _bgColor);
	}
	// HD light: smooth colored light only on the true-color canvas in the HD modes
	_hdLightOn = Options::oxceHdLight && _canvas->getHdMode() != HD_MODE_NEAREST;
	if (_hdLightOn)
	{
		_hdShadeCache.assign((size_t)_save->getMapSizeXYZ(), (Sint8)-1);
	}
	_canvas->setLight(nullptr);

	Tile *t;

	_projectileInFOV = _save->getDebugMode();
	if (_projectile)
	{
		t = _save->getTile(_projectile->getPosition(0).toTile());
		if (_save->getSide() == FACTION_PLAYER || (t && t->getVisible()))
		{
			_projectileInFOV = true;
		}
	}
	_explosionInFOV = _save->getDebugMode();

	Explosion* hitExplosion = nullptr;
	const int traceProjectiles = HdGentle::traceProjectiles();
	const bool ignoreAllButAlliesHits = traceProjectiles == 3 || traceProjectiles == 4;
	const bool keepCameraOnShooter = traceProjectiles == 4;
	const bool unitVisible = _save->getSelectedUnit() && _save->getSelectedUnit()->getVisible();
	const bool unitEnemy = _save->getSide() == FACTION_HOSTILE;

	if (!_explosions.empty())
	{
		for (auto* explosion : _explosions)
		{
			if (explosion->isBig())
			{
				_explosionInFOV = true;
				break;
			}
			t = _save->getTile(explosion->getPosition().toTile());
			if (t && t->getVisible())
			{
				_explosionInFOV = true;

				auto* unit = t->getOverlappingUnit(_save);
				if (ignoreAllButAlliesHits && unit && unit->getVisible() && (unit->getFaction() == UnitFaction::FACTION_PLAYER || unit->getFaction() == UnitFaction::FACTION_NEUTRAL))
				{
					hitExplosion = explosion;
					if (!keepCameraOnShooter)
					{
						_camera->centerOnPosition(t->getPosition(), true);
					}
				}

				break;
			}
		}
	}
	// loose hits show wherever they are in view, but do not pull the camera: the next shot is already on its way
	for (const auto &loose : _looseHits)
	{
		t = _save->getTile(loose.explosion->getPosition().toTile());
		if (t && t->getVisible())
		{
			_explosionInFOV = true;
			break;
		}
	}

	if ((_save->getSelectedUnit() && _save->getSelectedUnit()->getVisible())
		|| _unitDying
		|| _save->getSide() == FACTION_PLAYER
		|| _save->getDebugMode()
		|| (_projectileInFOV && (!ignoreAllButAlliesHits || (unitVisible && !unitEnemy)))
		|| (_explosionInFOV && (!ignoreAllButAlliesHits || ((unitVisible && !unitEnemy) || hitExplosion))))
	{
		_camera->beginShown();
		// a collapse shakes the picture: the camera is moved for this frame only, its own moves of the frame are kept
		const Position shook = shakeOffset(SDL_GetTicks());
		if (shook.x || shook.y)
			_camera->setMapOffset(_camera->getMapOffset() + shook);
		drawTerrain(_canvas);
		if (shook.x || shook.y)
			_camera->setMapOffset(_camera->getMapOffset() - shook);
		_hiddenViewOffset = _camera->getMapOffset();
		_hiddenViewValid = true;
		_camera->endShown();
		_messageOnCanvas = false;
		_messageApart = false;
	}
	else if (Options::oxceHdHiddenMap && Options::oxceHdEnemyTurn != 1 && _hiddenViewValid)
	{
		// an unseen enemy's turn: the map from where the player last saw it; the camera's own moves (a walking
		// unit's level, a followed shot, centring on the next unit) are not shown and the camera keeps them
		const Position real = _camera->getMapOffset();
		_camera->setMapOffset(_hiddenViewOffset);
		drawTerrain(_canvas);
		_camera->setMapOffset(real);
		_messageOnCanvas = false;
		_messageApart = false;
	}
	else
	{
		// the message is laid out on the screen: while the view is zoomed it goes to a canvas of the map's own size
		_messageApart = _viewWidth != getWidth() || _viewHeight != getHeight();
		if (_messageApart && !_messageCanvas)
		{
			_messageCanvas = new Canvas32(getWidth(), getHeight(), _k);
			_messageCanvas->setPalette(getPalette(), 0, 256);
			_messageCanvas->setHdMode(_canvas->getHdMode());
		}
		if (_messageApart)
		{
			_messageCanvas->fill(Palette::blockOffset(0) + _bgColor);
		}
		blitMessage(_messageApart ? _messageCanvas : _canvas);
		_messageOnCanvas = true;
	}
	// the true-color canvas records the frame and draws it on all cores now
	_canvas->setLight(nullptr);
	if (HdDrawStats::on)
	{
		HdDrawStats::frame.recordUs += std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - drawStart).count();
	}
	_canvas->flush();
	_lastDrawMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - drawStart).count();
	if (_camera->isGliding())
	{
		_redraw = true; // gentle mode: the picture is on its way, every frame until it is there
	}

	if (_hdTestFrozen)
	{
		// HD render test: this frame was drawn in the frozen state, capture it and thaw
		if (!_hdTestMapDumpPath.empty())
		{
			_canvas->saveDump(_hdTestMapDumpPath);
			_hdTestMapDumpPath.clear();
		}
		_cursorType = _hdTestSavedCursorType;
		_cursorSize = _hdTestSavedCursorSize;
		for (auto& tileParticles : _vaporParticles)
		{
			tileParticles.clear(); // the fixed test cloud is not the game's
		}
		_hdTestFrozen = false;
		_redraw = true;
	}
}

/**
 * The tint (color and opacity) of a vapor particle, for the true-color canvas.
 */
SDL_Color Map::vaporTint(const Particle &p) const
{
	const auto &tints = _game->getMod()->getTransparencies();
	SDL_Color none = { 0, 0, 0, 0 };
	if (p.getColor() < tints.size() && p.getOpacity() < Mod::TransparenciesOpacityLevels)
	{
		return tints[p.getColor()][p.getOpacity()];
	}
	return none;
}

/**
 * The tint of a vapor particle for the HD soft puff: the same tables as vaporTint, but the opacity level is not
 * a step. The classic level L shows for a remaining life of 10L - 7 .. 10L + 2, so the continuous level is
 * (life + 2.5) / 10 and the tint is interpolated between the two tables around it; the last ticks fade into
 * nothing. The particle's life and its tables are the mod's, nothing of the mechanics is touched.
 */
SDL_Color Map::vaporTintSoft(const Particle &p) const
{
	const auto &tints = _game->getMod()->getTransparencies();
	SDL_Color none = { 0, 0, 0, 255 };
	if (p.getColor() >= tints.size())
	{
		return none;
	}
	const auto &levels = tints[p.getColor()];
	const int life = p.getOpacityRaw();
	const int u = std::max(0, std::min((Mod::TransparenciesOpacityLevels - 1) * 100, (life * 10 + 25))); // level * 100
	const int lo = u / 100, hi = std::min(lo + 1, Mod::TransparenciesOpacityLevels - 1), frac = u % 100;
	const int fade = std::min(4, life); // 1..4 of 4: the last ticks dissolve
	auto mix = [&](int a, int b) { return (a * (100 - frac) + b * frac) / 100; };
	const SDL_Color &l = levels[lo], &h = levels[hi];
	SDL_Color out;
	out.r = (Uint8)(mix(l.r, h.r) * fade / 4);
	out.g = (Uint8)(mix(l.g, h.g) * fade / 4);
	out.b = (Uint8)(mix(l.b, h.b) * fade / 4);
	out.unused = (Uint8)(255 - (255 - mix(l.unused, h.unused)) * fade / 4);
	return out;
}

/**
 * HD light: the drawing shade of a tile, computed once per frame.
 */
int Map::hdShadeOf(Tile *tile)
{
	const size_t index = (size_t)(tile - _save->getTile(0));
	if (index < _hdShadeCache.size() && _hdShadeCache[index] >= 0)
	{
		return _hdShadeCache[index];
	}
	const int shade = tile->isDiscovered(O_FLOOR) ? reShade(tile) : 16;
	if (index < _hdShadeCache.size())
	{
		_hdShadeCache[index] = (Sint8)shade;
	}
	return shade;
}

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
	float ownTint[3];
	hdTintOf(tile, ownTint);
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
				hdTintOf(t, tintAround[dy + 1][dx + 1]);
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
	_canvas->setLight(&light);
}

/**
 * Draws the hidden movement message into the map surface. The message is a
 * classic base-resolution UI element (window, texts, progress bar blitted at
 * their base coordinates), so it is rendered into a base-resolution scratch
 * surface first and then scaled by k into the map.
 */
void Map::blitMessage(HdCanvas *target)
{
	const int baseW = getWidth() / _k;
	const int baseH = getHeight() / _k;
	if (!_messageScratch || _messageScratch->getWidth() != baseW || _messageScratch->getHeight() != baseH)
	{
		delete _messageScratch;
		_messageScratch = new Surface(baseW, baseH);
		// the message is blitted into the scratch as 8-bit pixels, and SDL translates those by
		// palette: a fresh surface has an all-black one, every colour finds index 0 as its nearest
		// entry, and the whole hidden movement screen comes out transparent - a black screen with
		// no picture, no text and no thinking bar
		if (_message->getPalette())
		{
			_messageScratch->setPalette(_message->getPalette());
		}
	}
	_messageScratch->clear();
	_message->blit(_messageScratch->getSurface());
	target->blitClassic(_messageScratch, 0, 0, _k);
}

/**
 * Blits the map surface. When the screen output is layered (32-bit display),
 * the map is the content of the world layer and never touches the classic
 * 8-bit layer, which keeps UI drawn on top exactly as before; otherwise this
 * is a plain surface blit into the screen buffer.
 * @param surface Screen buffer (used only in the non-layered case).
 */
void Map::blit(SDL_Surface *surface)
{
	Screen *screen = _game->getScreen();
	if (!screen->isLayered())
	{
		Surface::blit(surface);
		return;
	}
	if (_visible && !_hidden)
	{
		// the labels switch between baked and drawn on top with the interface options: the canvas follows
		if (hdLabelsWanted() != _hdLabelsOn)
		{
			_redraw = true;
		}
		if (_redraw)
		{
			draw();
		}
		SDL_Surface *world = screen->getWorldSurface();
		const int k = screen->getWorldScale();
		bool zoomed = false;
		// the hidden movement message of a zoomed view has its own canvas, the map's size
		HdCanvas *shown = _messageOnCanvas && _messageApart && _messageCanvas ? _messageCanvas : _canvas;
		// the battle view zoom: the canvas is the view, the map's size divided by the zoom, and is scaled to the map
		const bool viewScaled = shown == _canvas && (_viewWidth != getWidth() || _viewHeight != getHeight());
		// the canvas is already k times the base resolution (see _spriteWidth), so only its origin scales;
		// a true-color canvas copies straight into the world (rows in parallel), a palette one is converted by SDL
		if (Canvas32 *canvas32 = dynamic_cast<Canvas32*>(shown))
		{
			// the final blow (HdKillCam): the frame goes to the screen enlarged around the victim
			Position voxel, focus;
			double zoom, pull, bars;
			if (HdKillCam::view(voxel, zoom, pull, bars))
			{
				_camera->convertVoxelToScreen(voxel, &focus);
				canvas32->copyZoomed(world, getX() * k, getY() * k, getWidth(), getHeight(), focus.x, focus.y, zoom, pull, bars);
				zoomed = true;
			}
			else if (viewScaled)
			{
				canvas32->copyZoomed(world, getX() * k, getY() * k, getWidth(), getHeight(), 0, 0, 1.0, 0.0, 0.0);
			}
			else
			{
				canvas32->copyTo(world, getX() * k, getY() * k);
			}
		}
		else
		{
			SDL_Rect target {};
			target.x = getX() * k;
			target.y = getY() * k;
			SDL_BlitSurface(shown->getSdlSurface(), nullptr, world, &target);
		}
		// the message's two lines are not in the canvas when the HD interface can draw them
		// itself: the canvas reaches the screen scaled, and a smeared line under a sharp one
		// reads worse than either alone. They go on top here, every frame, because the canvas
		// is only redrawn on demand while the HD layer is built anew for each frame
		if (_messageOnCanvas && _message->hdText() && HdUi::active())
		{
			_message->hdDrawAt(getX(), getY());
		}
		// the hit chance and the unit numbers, kept by the last draw() in canvas pixels (the kill camera's
		// enlarged frame has no cursor of its own to stand by: they wait for the plain one)
		if (_hdLabelsOn && !_hdLabels.empty() && !zoomed && HdUi::active())
		{
			HdUi &ui = HdUi::instance();
			const HdUi::FontMetrics &m = ui.metrics(_game->getMod()->getFont("FONT_SMALL"));
			ui.setClip(getX(), getY(), getWidth(), getHeight());
			for (const HdLabel &label : _hdLabels)
			{
				// canvas pixels are view pixels: the battle view zoom moves the labels with the map, their letters keep their size
				const int wx = getX() * k + label.x * getWidth() / _viewWidth, wy = getY() * k + label.y * getHeight() / _viewHeight;
				if (label.tag)
				{
					if (label.scale != 1.0f || label.weight != 1.0f)
					{
						// the plate keeps its centre: the classic one is 5 rows of digit and 2 of border
						ui.drawMapTag(label.text, wx, wy + (int)std::lround((1.0f - label.scale) * 3.5f * k), label.face, label.back, label.edge, label.scale, label.weight);
					}
					else
					{
						ui.drawMapTag(label.text, wx, wy, label.face, label.back, label.edge);
					}
				}
				else if (label.cap > 0.0f)
				{
					// a line box as tall as the capitals: their tops stand at wy
					const int cx = label.centre ? wx - (int)std::lround(ui.ttfWidth(label.text, true, label.cap) * k / 2) : wx;
					ui.drawMapText(label.text, label.cap, label.cap, cx, wy, label.face, label.edge, label.weight);
				}
				else if (label.scale != 1.0f || label.weight != 1.0f)
				{
					// the small font's text by the player's percent, kept round the middle of the usual box
					const int cx = wx + (int)std::lround((1.0f - label.scale) * ui.ttfWidth(label.text, true, m.cap) * k / 2);
					const int cy = wy + (int)std::lround((1.0f - label.scale) * m.cap * k / 2);
					ui.drawMapText(label.text, m.cap * label.scale, (float)m.lineH * label.scale, cx, cy, label.face, label.edge, label.weight);
				}
				else
				{
					ui.drawMapText(label.text, m.cap, (float)m.lineH, wx, wy, label.face, label.edge);
				}
			}
			ui.clearClip();
		}
	}
}

bool Map::hdLabelsWanted() const
{
	return HdUi::skin() && HdUi::instance().hasFonts();
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

void Map::drawAccuracy(HdCanvas *canvas, int x, int y)
{
	if (!_hdLabelsOn)
	{
		_txtAccuracy->draw();
		canvas->blitClassic(_txtAccuracy, x, y, _k);
		return;
	}
	// the colour rule of the high-contrast classic text: shade 1 x 3 is the face, shade 5 x 3 the outline;
	// the colours are the map's, as the canvas paints the baked text's indices with them (the text keeps
	// the palette it was made with, and that one is not the battle's)
	const SDL_Color *pal = getPalette();
	const Uint8 c = _txtAccuracy->getColor();
	HdLabel label;
	label.text = Unicode::convUtf8ToUtf32(_txtAccuracy->getText());
	label.x = x;
	label.y = y;
	label.face = HdUi::rgba(pal[(Uint8)(c + 3)]);
	label.edge = HdUi::rgba(pal[(Uint8)(c + 15)]);
	label.scale = std::max(50, std::min(100, Options::oxceHdAimNumSize)) / 100.0f;
	label.weight = std::max(50, std::min(100, Options::oxceHdAimNumWeight)) / 100.0f;
	_hdLabels.push_back(label);
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

void Map::refreshAIProgress(int progress)
{
	if (_save->getSide() == FACTION_NEUTRAL)
	{
		_message->setProgressBarColor(_neutralBarColor, _borderBarColor);
	}
	else
	{
		_message->setProgressBarColor(_hostileBarColor, _borderBarColor);
	}
	_message->setProgressValue(progress);
}

/**
 * Replaces a certain amount of colors in the surface's palette.
 * @param colors Pointer to the set of colors.
 * @param firstcolor Offset of the first color to replace.
 * @param ncolors Amount of colors to replace.
 */
void Map::setPalette(const SDL_Color *colors, int firstcolor, int ncolors)
{
	Surface::setPalette(colors, firstcolor, ncolors);
	if (_canvas)
	{
		_canvas->setPalette(colors, firstcolor, ncolors);
	}
	if (_messageCanvas)
	{
		_messageCanvas->setPalette(colors, firstcolor, ncolors);
	}
	for (auto* mds : *_save->getMapDataSets())
	{
		mds->getSurfaceset()->setPalette(colors, firstcolor, ncolors);
	}
	_message->setPalette(colors, firstcolor, ncolors);
	if (_messageScratch)
	{
		// the scratch the message is drawn into blits index to index only while it carries the same palette
		_messageScratch->setPalette(colors, firstcolor, ncolors);
	}
	refreshHiddenMovementBackground();
	_message->initText(_game->getMod()->getFont("FONT_BIG"), _game->getMod()->getFont("FONT_SMALL"), _game->getLanguage());
	_message->setText(_game->getLanguage()->getString("STR_HIDDEN_MOVEMENT"), _game->getLanguage()->getString("STR_THINKING"));
}

void Map::refreshHiddenMovementBackground()
{
	_message->setBackground(_game->getMod()->getSurface(_save->getHiddenMovementBackground()));
}

/**
 * Get shade of wall.
 * @param part For what wall do calculations.
 * @param tileFrot Tile of wall.
 * @return Current shade of wall.
 */
int Map::getWallShade(TilePart part, Tile* tileFrot)
{
	int shade;
	if (tileFrot->isDiscovered(O_FLOOR))
	{
		shade = reShade(tileFrot);
	}
	else
	{
		shade = 16;
	}
	if (part)
	{
		if ((tileFrot->isDoor(part) || tileFrot->isUfoDoor(part)) && tileFrot->isDiscovered(part))
		{
			Position offset =
				part == O_NORTHWALL ? Position(1,0,0) :
				part == O_WESTWALL ? Position(0,1,0) :
					throw Exception("Unsupported tile part for wall shade");

			Tile *tileBehind = _save->getTile(tileFrot->getPosition() - offset);

			shade = std::min(reShade(tileFrot), tileBehind ? tileBehind->getShade() + 5 : 16);
		}
	}
	return shade;
}

Tile *Map::turnedWall(const Position &pos, bool left, TilePart &part) const
{
	const Position step = _camera->viewStepToWorld(left ? Position(-1, 0, 0) : Position(0, -1, 0));
	// the edge between a tile and its neighbour belongs to the one on its east or south side
	if (step.x != 0)
	{
		part = O_WESTWALL;
		return _save->getTile(step.x < 0 ? pos : pos + Position(1, 0, 0));
	}
	part = O_NORTHWALL;
	return _save->getTile(step.y < 0 ? pos : pos + Position(0, 1, 0));
}

Map::TurnedObject Map::turnedObject(int bigWall) const
{
	TurnedObject result = { bigWall < 6 || bigWall == 9, false, 0, 0 };
	const int rot = _camera->getRotation();
	// the edges of the tile as bits: west 1, north 2, east 4, south 8; a quarter turn moves each to the next
	static const int edges[10] = { 0, 0, 0, 0, 1, 2, 4, 8, 12, 3 };
	if (rot == 0 || bigWall < 4 || bigWall > 9)
	{
		return result;
	}
	const int set = edges[bigWall];
	const int view = ((set << rot) | (set >> (4 - rot))) & 15;
	result.back = (view & 12) == 0;
	result.mirror = (rot & 1) != 0;
	// mirroring the frame swaps west with north and east with south
	const int drawn = result.mirror ? (((set & 5) << 1) | ((set & 10) >> 1)) : set;
	// where a frame shows each edge set (base pixels of the 32x40 frame)
	auto anchor = [](int s, int &x, int &y)
	{
		switch (s)
		{
		case 1: x = 8; y = 28; break;
		case 2: x = 24; y = 28; break;
		case 4: x = 24; y = 36; break;
		case 8: x = 8; y = 36; break;
		case 3: x = 16; y = 24; break;
		case 6: x = 32; y = 32; break;
		case 12: x = 16; y = 40; break;
		default: x = 0; y = 32; break; // 9: south and west
		}
	};
	int vx, vy, dx, dy;
	anchor(view, vx, vy);
	anchor(drawn, dx, dy);
	result.dx = (vx - dx) * _k;
	result.dy = (vy - dy) * _k;
	return result;
}

int Map::turnedDir(int dir) const
{
	return (dir >= 0 && dir < 8) ? (dir + 2 * _camera->getRotation()) % 8 : dir;
}

/**
 * HD interface, oxceHdPathStretch: a path preview's arrow. A step that costs the usual (4 TU straight, 6 diagonal) is
 * the one arrow, as it was; a dearer one (sand, swamp, tall grass) is two or three arrows one behind another along
 * the way, so the hard ground shows at a glance. Picture only: the cost is what the pathfinding already counted.
 */
void Map::blitPathArrow(HdCanvas *canvas, SurfaceRaw<const Uint8> frame, int x, int y, int newBaseColor, const Tile *tile, const Position &mapPosition)
{
	int copies = 1;
	Position along;
	if (Options::oxceHdPathStretch && tile->getPreview() >= 0 && tile->getPreview() < 8)
	{
		static const char *dbgStretch = getenv("OXCE_DBG_STRETCH"); // TEMP-XP284
		const int twelfths = dbgStretch ? (tile->getPreviewStep() ? atoi(dbgStretch) : 0) : tile->getPreviewStep();
		copies = twelfths < 18 ? 1 : (twelfths < 30 ? 2 : 3);
		if (copies > 1)
		{
			Position vec, from, to;
			Pathfinding::directionToVector(tile->getPreview(), &vec);
			_camera->convertMapToScreen(mapPosition, &from);
			_camera->convertMapToScreen(mapPosition + vec, &to);
			along = to - from; // one tile on, in screen pixels
		}
	}
	for (int i = 0; i < copies; ++i)
	{
		// a quarter of a tile apart, the whole row centred on the tile; the head ends on top
		const int at = 2 * i - (copies - 1);
		canvas->blit(frame, x + along.x * at / 8, y + along.y * at / 8, 0, false, newBaseColor);
	}
}

/**
 * Check two positions if have same XY cords
 */
static bool positionHaveSameXY(Position a, Position b)
{
	return a.x == b.x && a.y == b.y;
}

/**
 * Check two positions if have same XY cords
 */
static bool positionInRangeXY(Position a, Position b, int diff)
{
	return std::abs(a.x - b.x) <= diff && std::abs(a.y - b.y) <= diff;
}

namespace
{

static const int ArrowBobOffsets[8] = {0,1,2,1,0,1,2,1};

/// Ticks of the animation timer (100 ms) the sway of a hanging unit takes to fade in or out, so taking off or landing does not jump (Map::hoverBob).
constexpr int HOVER_FADE_STEPS = 4;

static const int ArrowColorsUFO[4]  = { 6,  3, 14, 4 }; // white,    red, blue, green
static const int ArrowColorsTFTD[4] = { 4, 11, 16, 6 }; // white, orange, blue, green

int getArrowBobForFrame(int frame, int scale)
{
	return ArrowBobOffsets[frame % 8] * scale;
}

int getShadePulseForFrame(int shade, int frame)
{
	if (shade > 7) shade = 7;
	if (shade < 2) shade = 2;
	shade += (ArrowBobOffsets[frame % 8] * 2 - 2);
	return shade;
}

}

/**
 * Draw part of unit graphic that overlap current tile.
 * @param surface
 * @param unitTile
 * @param currTile
 * @param currTileScreenPosition
 * @param shade
 * @param obstacleShade
 * @param topLayer
 */
void Map::drawUnit(UnitSprite &unitSprite, Tile *unitTile, Tile *currTile, Position currTileScreenPosition, bool topLayer, BattleUnit* movingUnit)
{
	const int tileFoorWidth = 32 * _k;
	const int tileFoorHeight = 16 * _k;
	const int tileHeight = 40 * _k;

	if (!unitTile)
	{
		return;
	}
	BattleUnit* bu = unitTile->getOverlappingUnit(_save, TUO_ALWAYS);
	Position unitOffset;
	bool unitFromBelow = false;
	bool unitFromAbove = false;
	if (bu)
	{
		if (bu != unitTile->getUnit())
		{
			unitFromBelow = true;
		}
	}
	else if (movingUnit && unitTile == currTile)
	{
		auto* upperTile = _save->getAboveTile(unitTile);
		if (upperTile && upperTile->hasNoFloor(_save))
		{
			bu = upperTile->getUnit();
		}
		if (bu != movingUnit)
		{
			return;
		}
		unitFromAbove = true;
	}
	else
	{
		return;
	}

	if (!(bu->getVisible() || _save->getDebugMode()))
	{
		return;
	}

	unitOffset.x = unitTile->getPosition().x - bu->getPosition().x;
	unitOffset.y = unitTile->getPosition().y - bu->getPosition().y;
	int part = unitOffset.x + unitOffset.y*2;
	const bool turned = _camera->getRotation() != 0;
	if (turned)
	{
		// HD lab: the part of a big unit is its quarter on the screen: the offset in the turned view, from
		// the unit's corner nearest the top of the screen
		const int s = bu->getArmor()->getSize() - 1;
		const Position corner = _camera->worldStepToView(Position(s, s, 0));
		Position viewOffset = _camera->worldStepToView(unitOffset);
		if (corner.x < 0) viewOffset.x += s;
		if (corner.y < 0) viewOffset.y += s;
		part = viewOffset.x + viewOffset.y * 2;
	}

	bool moving = bu->getStatus() == STATUS_WALKING || bu->getStatus() == STATUS_FLYING;
	int bonusWidth = moving ? 0 : tileFoorWidth;
	int topMargin = 0;
	int bottomMargin = 0;

	//if unit is from below then we draw only part that in in tile
	if (unitFromBelow)
	{
		bottomMargin = -tileFoorHeight / 2;
		topMargin = tileFoorHeight;
	}
	else if (topLayer)
	{
		topMargin = 2 * tileFoorHeight;
	}
	else
	{
		const Tile *top = _save->getAboveTile(unitTile);
		if (top && top->getOverlappingUnit(_save, TUO_ALWAYS) == bu)
		{
			topMargin = -tileFoorHeight / 2;
		}
		else
		{
			topMargin = tileFoorHeight;
		}
	}

	GraphSubset mask = GraphSubset(tileFoorWidth + bonusWidth, tileHeight + topMargin + bottomMargin).offset(currTileScreenPosition.x - bonusWidth / 2, currTileScreenPosition.y - topMargin);

	if (moving)
	{
		GraphSubset leftMask = mask.offset(-tileFoorWidth/2, 0);
		GraphSubset rightMask = mask.offset(+tileFoorWidth/2, 0);
		// (the masks are the screen's: the direction as the view shows it)
		int direction = turnedDir(bu->getMoveDirection());
		Position partCurr = currTile->getPosition();
		Position partDest = bu->getDestination() + unitOffset;
		Position partLast = bu->getLastPosition() + unitOffset;
		bool isTileDestPos = positionHaveSameXY(partDest, partCurr);
		bool isTileLastPos = positionHaveSameXY(partLast, partCurr);

		if (unitFromAbove && partLast != unitTile->getPosition())
		{
			//this tile is below moving unit and it do not change levels, nothing to draw
			return;
		}

		//adjusting mask
		if (positionHaveSameXY(partLast, partDest))
		{
			if (currTile == unitTile)
			{
				//no change
			}
			else
			{
				//nothing to draw
				return;
			}
		}
		else if (isTileDestPos)
		{
			//unit is moving to this tile
			switch (direction)
			{
			case 0:
			case 1:
				mask = GraphSubset::intersection(mask, rightMask);
				break;
			case 2:
				//no change
				break;
			case 3:
				//no change
				break;
			case 4:
				//no change
				break;
			case 5:
			case 6:
				mask = GraphSubset::intersection(mask, leftMask);
				break;
			case 7:
				//nothing to draw
				return;
			}
		}
		else if (isTileLastPos)
		{
			//unit is exiting this tile
			switch (direction)
			{
			case 0:
				//no change
				break;
			case 1:
			case 2:
				mask = GraphSubset::intersection(mask, leftMask);
				break;
			case 3:
				//nothing to draw
				return;
			case 4:
			case 5:
				mask = GraphSubset::intersection(mask, rightMask);
				break;
			case 6:
				//no change
				break;
			case 7:
				//no change
				break;
			}
		}
		else
		{
			// (the neighbours on the left and the right of the screen: in a turned view, other ones of the map)
			Position leftPos = partCurr + (turned ? _camera->viewStepToWorld(Position(-1, 0, 0)) : Position(-1, 0, 0));
			Position rightPos = partCurr + (turned ? _camera->viewStepToWorld(Position(0, -1, 0)) : Position(0, -1, 0));
			if (!topLayer && (partDest.z > partCurr.z || partLast.z > partCurr.z))
			{
				//unit change layers, it will be drawn by upper layer not lower.
				return;
			}
			else if (
				(direction == 1 && (partDest == rightPos || partLast == leftPos)) ||
				(direction == 5 && (partDest == leftPos || partLast == rightPos)))
			{
				mask = GraphSubset(tileFoorWidth, tileHeight + 2 * tileFoorHeight).offset(currTileScreenPosition.x, currTileScreenPosition.y - 2 * tileFoorHeight);
			}
			else
			{
				//unit is not moving close to tile
				return;
			}
		}
	}
	else if (unitTile != currTile || unitFromAbove)
	{
		return;
	}

	Position tileScreenPosition;
	_camera->convertMapToScreen(unitTile->getPosition() + Position(0,0, (-unitFromBelow) + (+unitFromAbove)), &tileScreenPosition);
	tileScreenPosition += _camera->getMapOffset();

	//get shade helpers
	auto getTileShade = [&](Tile* tile)
	{
		return tile ? (tile->isDiscovered(O_FLOOR) ? reShade(tile) : 16) : 16;
	};
	auto getMixedTileShade = [&](Tile* tile, int heightOffset, bool below)
	{
		int shadeLower = 0;
		int shadeUpper = 0;
		if (below)
		{
			shadeLower = getTileShade(_save->getBelowTile(tile));
			shadeUpper = getTileShade(tile);
		}
		else
		{
			shadeLower = getTileShade(tile);
			shadeUpper = getTileShade(_save->getAboveTile(tile));
		}

		return Interpolate(shadeLower, shadeUpper, -heightOffset, Position::TileZ);
	};

	// draw unit
	int shade = 0;
	UnitWalkingOffset offsets = calculateWalkingOffset(bu);
	if (moving)
	{
		const Position start = bu->getPosition();
		const Position end = bu->getDestination();
		const auto minLevel = std::min(start.z, end.z); // Sint16
		const int startShade = getMixedTileShade(_save->getTile(start), start.z == minLevel ? offsets.TerrainLevelOffset : 0, false);
		const int endShade = getMixedTileShade(_save->getTile(end), end.z == minLevel ? offsets.TerrainLevelOffset : 0, false);
		shade = Interpolate(startShade, endShade, offsets.NormalizedMovePhase, 16);
	}
	else
	{
		shade = getMixedTileShade(currTile, offsets.TerrainLevelOffset, unitFromBelow);
		if (_showObstacles && unitTile->getObstacle(4))
		{
			shade = getShadePulseForFrame(shade, _animFrame);
		}
	}
	if (_debugVisionMode == 1)
	{
		shade = std::min(+NIGHT_VISION_SHADE, shade);
	}
	HdDrawTimer timer(HdDrawStats::frame.unitsUs);
	// the facing indicator: with Alt held, or always (HD option, only what Alt shows)
	unitSprite.draw(bu, part, tileScreenPosition.x + offsets.ScreenOffset.x, tileScreenPosition.y + offsets.ScreenOffset.y, shade, mask, (_isAltPressed || (Options::oxceHdAltInfo & 1)) && !_isCtrlPressed);
}

/**
 * Draw the terrain.
 * Keep this function as optimised as possible. It's big to minimise overhead of function calls.
 * @param surface The surface to draw on.
 */
/**
 * HD render: the area of the explosion the aimed shot or throw would make if it went off at the cursor
 * tile, with the power it would reach every tile with (TileEngine::explosionArea - explode()'s own rays,
 * nothing rolled or touched). The power is worked out the way ExplosionBState does: the damage item's power
 * with the shooter's bonus, less the range reduction over the distance to the cursor (none for a throw).
 * Only what explodes counts: a damage item with a blast radius, not melee or a psi amp. Picture only:
 * drawn in the HD modes, never in mode 0, and the game reads none of it.
 */
void Map::updateBlastArea(HdCanvas *surface)
{
	Position center(-1, -1, -1);
	const RuleDamageType *type = nullptr;
	int power = 0, radius = 0;
	BattleAction *action = nullptr;
	if (Options::oxceHdBlastArea && surface->getHdMode() != HD_MODE_NEAREST
		&& (_cursorType == CT_AIM || _cursorType == CT_THROW) && _save->getBattleGame()
		&& !_save->getBattleState()->getMouseOverIcons())
	{
		action = _save->getBattleGame()->getCurrentAction();
	}
	const Position target(_selectorX, _selectorY, _camera->getViewLevel());
	if (action && action->weapon && action->actor && action->type != BA_HIT && _save->getTile(target))
	{
		const BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(*action);
		const RuleItem *rule = attack.damage_item ? attack.damage_item->getRules() : nullptr;
		const BattleType battleType = rule ? rule->getBattleType() : BT_NONE;
		const bool explodes = rule && battleType != BT_MELEE && battleType != BT_PSIAMP
			&& (action->type != BA_THROW || battleType == BT_GRENADE || battleType == BT_PROXIMITYGRENADE);
		if (explodes)
		{
			radius = rule->getExplosionRadius(attack);
		}
		if (radius > 0)
		{
			const float range = action->type == BA_THROW ? 0.0f
				: Position::distance(action->actor->getPosition().toVoxel(), target.toVoxel());
			const RuleItem *weaponRule = action->weapon->getRules();
			if (weaponRule->getIgnoreAmmoPower())
			{
				power += weaponRule->getPowerBonus(attack);
				power -= weaponRule->getPowerRangeReduction(range);
			}
			else
			{
				power += rule->getPowerBonus(attack);
				power -= rule->getPowerRangeReduction(range);
			}
			type = rule->getDamageType();
			center = target;
		}
	}
#ifdef OXCE_AI_DEV
	// debug stand OXCE_HD_BLAST_AT "x,y,z" (map cells): the area of an HE terrain explosion there (OXCE_COLLAPSE_BLAST_POWER)
	// with nothing aimed, the camera held on it - for the dumps of the area and the collapse hint
	static const char *blastAt = getenv("OXCE_HD_BLAST_AT");
	if (blastAt && Options::oxceHdBlastArea && surface->getHdMode() != HD_MODE_NEAREST)
	{
		int x = 0, y = 0, z = 0;
		char *end = nullptr;
		x = (int)strtol(blastAt, &end, 10);
		if (*end == ',') y = (int)strtol(end + 1, &end, 10);
		if (*end == ',') z = (int)strtol(end + 1, &end, 10);
		const char *powS = getenv("OXCE_COLLAPSE_BLAST_POWER");
		power = powS && *powS ? atoi(powS) : 60;
		radius = power / 10;
		type = _game->getMod()->getDamageType(DT_HE);
		center = Position(x, y, z);
		if (_camera->getCenterPosition() != center)
		{
			_camera->centerOnPosition(center, true);
		}
		// OXCE_HD_BLAST_REVEAL: the whole map discovered, as the debug mode does - a building seen from inside
		static bool revealed = false;
		if (!revealed && getenv("OXCE_HD_BLAST_REVEAL"))
		{
			revealed = true;
			_save->revealMap();
		}
	}
#endif
	if (power <= 0 || !type)
	{
		_blastMax = 0;
		_blastFallCount = 0;
		_blastCenter = Position(-1, -1, -1);
		return;
	}
	if (center == _blastCenter && power == _blastKeyPower && radius == _blastKeyRadius && type == _blastKeyType
		&& (int)_blastPower.size() == _save->getMapSizeXYZ())
	{
		return;
	}
	_blastCenter = center;
	_blastKeyPower = power;
	_blastKeyRadius = radius;
	_blastKeyType = type;

	const auto t0 = std::chrono::steady_clock::now();
	std::map<Tile*, int> area, strongest;
	_save->getTileEngine()->explosionArea(center.toVoxel() + Position(8, 8, 2), power, type, radius, area, &strongest);
	// the collapse hint: what the building collapse model may let fall after this explosion, marked on its tile -
	// on the view level for a part above it, as that level is the top one drawn
	std::vector<Position> falls;
	CollapsePilot::mayFall(_save, strongest, type, falls);
	_blastFall.assign(_save->getMapSizeXYZ(), 0);
	_blastFallCount = 0;
	for (Position p : falls)
	{
		p.z = std::min(p.z, center.z);
		uint8_t &mark = _blastFall[_save->getTileIndex(p)];
		if (!mark)
		{
			mark = 1;
			++_blastFallCount;
		}
	}
	_blastPower.assign(_save->getMapSizeXYZ(), 0);
	_blastMax = 0;
	for (const auto &p : area)
	{
		if (p.second > 0)
		{
			_blastPower[_save->getTileIndex(p.first->getPosition())] = p.second;
			_blastMax = std::max(_blastMax, p.second);
		}
	}
	const int color = damageTypeColor(_game->getMod(), type);
	const SDL_Color c = color ? getPalette()[color] : SDL_Color();
	const int peak = std::max((int)c.r, std::max((int)c.g, (int)c.b));
	if (peak >= 16)
	{
		// the hue and saturation of the mod's colour at full brightness: the pedia writes on a dark page and
		// often picks a dark shade (Piratez HE is 84,8,0), which over the floor would read as a shadow
		_blastRgb = ((Uint32)(c.r * 255 / peak) << 16) | ((Uint32)(c.g * 255 / peak) << 8) | (Uint32)(c.b * 255 / peak);
	}
	else
	{
		_blastRgb = blastFallbackRgb(type);
	}
	Log(LOG_DEBUG) << "HD blast area: " << area.size() << " tiles at " << center << ", power " << power << ", radius " << radius
		<< ", may fall " << falls.size() << " part(s) on " << _blastFallCount << " tile(s)"
		<< ", type " << type->ResistType << ", colour " << color << ", "
		<< std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count() << " ms";
}

/**
 * HD render: the aim hints that follow what is aimed and where (picture only, the game reads none of it):
 * - the reticle style of the action's kind (oxceHdReticleArtillery for a shot of ammo that explodes,
 *   oxceHdReticleExplosive for a thrown explosive), swapped into CURSOR.PCK 6..10 only when the kind changes;
 * - the arc a throw or an arcing shot would fly (oxceHdAimArc), worked out again only when the aim moves.
 */
void Map::updateAimHints(HdCanvas *surface)
{
	BattleAction *action = nullptr;
	if ((_cursorType == CT_AIM || _cursorType == CT_THROW) && _save->getBattleGame() && _save->getBattleState()
		&& !_save->getBattleState()->getMouseOverIcons())
	{
		action = _save->getBattleGame()->getCurrentAction();
		if (action && (!action->weapon || !action->actor || action->type == BA_NONE))
		{
			action = nullptr;
		}
	}

	// what kind of shot it is: what explodes counts, as updateBlastArea takes it
	_aimKind = AIM_PLAIN;
	if (action && action->type != BA_HIT)
	{
		const BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(*action);
		const RuleItem *rule = attack.damage_item ? attack.damage_item->getRules() : nullptr;
		const BattleType battleType = rule ? rule->getBattleType() : BT_NONE;
		if (rule && battleType != BT_MELEE && battleType != BT_PSIAMP && rule->getExplosionRadius(attack) > 0)
		{
			if (action->type != BA_THROW)
			{
				_aimKind = AIM_ARTILLERY;
			}
			else if (battleType == BT_GRENADE || battleType == BT_PROXIMITYGRENADE)
			{
				_aimKind = AIM_EXPLOSIVE;
			}
		}
	}
	// the reticle of that kind: 0 = as the main one; a thrown explosive with its own style is drawn with the reticle
	// instead of the throw box (see drawTerrain). Only the HD frames change, so k = 1 and mode 0 never see it
	int pick = Options::oxceHdReticle;
	if (_aimKind == AIM_ARTILLERY && Options::oxceHdReticleArtillery > 0)
	{
		pick = Options::oxceHdReticleArtillery - 1;
	}
	else if (_aimKind == AIM_EXPLOSIVE && Options::oxceHdReticleExplosive > 0)
	{
		pick = Options::oxceHdReticleExplosive - 1;
	}
	_game->getMod()->applyHdReticle(pick, false);

	// the arc
	const Position target(_selectorX, _selectorY, _camera->getViewLevel());
	const bool arcing = action && Options::oxceHdAimArc && surface->getHdMode() != HD_MODE_NEAREST
		&& (action->type == BA_THROW || (action->type != BA_HIT && action->weapon->getArcingShot(action->type)))
		&& _save->getTile(target);
	if (!arcing)
	{
		_arcPath.clear();
		_arcKeyActor = nullptr;
		return;
	}
	const bool ctrl = _save->isCtrlPressed(true);
	const Position from = action->actor->getPosition();
	if (action->actor == _arcKeyActor && action->weapon == _arcKeyWeapon && action->type == _arcKeyType && target == _arcKeyTarget
		&& from == _arcKeyFrom && action->actor->isKneeled() == _arcKeyKneeled && ctrl == _arcKeyCtrl
		&& action->weapon->getTotalWeight() == _arcKeyWeight && _save->getTurn() == _arcKeyTurn
		&& _explosions.empty() && !_projectile)
	{
		return;
	}
	_arcKeyActor = action->actor;
	_arcKeyWeapon = action->weapon;
	_arcKeyType = action->type;
	_arcKeyTarget = target;
	_arcKeyFrom = from;
	_arcKeyKneeled = action->actor->isKneeled();
	_arcKeyCtrl = ctrl;
	_arcKeyWeight = action->weapon->getTotalWeight();
	_arcKeyTurn = _save->getTurn();

	BattleAction aimed = *action;
	aimed.target = target;
	_arcReaches = aimArc(_save, aimed, _arcPath);
	// the colour: what the shot carries - the damage type's colour (as the explosion area), white for a plain throw
	const RuleDamageType *type = _aimKind != AIM_PLAIN ? aimDamageType(action) : nullptr;
	_arcRgb = 0xF0F0F0;
	if (type)
	{
		const int color = damageTypeColor(_game->getMod(), type);
		const SDL_Color c = color ? getPalette()[color] : SDL_Color();
		const int peak = std::max((int)c.r, std::max((int)c.g, (int)c.b));
		_arcRgb = peak >= 16 ? ((Uint32)(c.r * 255 / peak) << 16) | ((Uint32)(c.g * 255 / peak) << 8) | (Uint32)(c.b * 255 / peak)
			: blastFallbackRgb(type);
	}
}

/**
 * HD render: the aim arc of a throw or an arcing shot (oxceHdAimArc), dashes running from the thrower to the
 * target: in the colour of what it carries when a curve reaches the target, red with a cross where it stops when
 * none does (the game would then refuse the throw, "unable to throw here", or the shot). On top of the map.
 */
void Map::drawAimArc(HdCanvas *surface)
{
	if (_arcPath.size() < 2)
	{
		return;
	}
	const HdFrame &dot = arcDot(_arcReaches ? _arcRgb : 0xFF3030, _k);
	const int phase = _animFrame % ARC_DASH;
	// the first voxels are in the thrower's own hands: the dashes start a little way out
	for (size_t i = 3; i < _arcPath.size(); ++i)
	{
		if ((int)((i + ARC_DASH - phase) % ARC_DASH) >= ARC_DASH_ON)
		{
			continue;
		}
		Position screen;
		_camera->convertVoxelToScreen(_arcPath[i], &screen);
		surface->blitFrame(dot, screen.x - dot.width / 2, screen.y - dot.height / 2);
	}
	if (!_arcReaches)
	{
		const HdFrame &stop = arcStop(_k);
		Position screen;
		_camera->convertVoxelToScreen(_arcPath.back(), &screen);
		surface->blitFrame(stop, screen.x - stop.width / 2, screen.y - stop.height / 2);
	}
}

/**
 * HD render: the bonus the shooter's stats add to the power of the aimed attack (oxceHdAimSkillBonus), "+N"
 * on a plate in the damage type's colour under the reticle at canvas (x, y) = the cursor tile's top left.
 * The power is taken the way ExplosionBState::init takes it (the weapon's own when it ignores the ammo's, the
 * melee bonus for a hit with an item that is not a melee weapon), less the item's base power: what is left
 * is the shooter's (the stat bonus formula of the item, damageBonus / meleeBonus). Nothing when it is 0 or less.
 */
void Map::drawSkillBonus(HdCanvas *surface, int x, int y)
{
	BattleAction *action = _save->getBattleGame()->getCurrentAction();
	if (!Options::oxceHdAimSkillBonus || surface->getHdMode() == HD_MODE_NEAREST || !action || !action->weapon || !action->actor)
	{
		return;
	}
	const BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(*action);
	if (!attack.damage_item)
	{
		return;
	}
	const RuleItem *rule = attack.damage_item->getRules();
	const RuleItem *weaponRule = action->weapon->getRules();
	if (rule->getBattleType() == BT_PSIAMP || weaponRule->getBattleType() == BT_PSIAMP)
	{
		return;
	}
	int bonus = 0;
	if (action->type == BA_HIT && rule->getBattleType() != BT_MELEE)
	{
		bonus = rule->getMeleeBonus(attack) - rule->getMeleePower();
	}
	else if (weaponRule->getIgnoreAmmoPower())
	{
		bonus = weaponRule->getPowerBonus(attack) - weaponRule->getPower();
	}
	else
	{
		bonus = rule->getPowerBonus(attack) - rule->getPower();
	}
	if (bonus <= 0)
	{
		return;
	}
	const std::string text = "+" + std::to_string(bonus);
	// the plate in the damage type's ramp (the explosion area's fallback in vanilla, which gives none)
	const RuleDamageType *type = aimDamageType(action);
	const SDL_Color *pal = getPalette();
	const int color = damageTypeColor(_game->getMod(), type);
	const int group = color ? color / 16 : nearestColorGroup(pal, blastFallbackRgb(type)) - 1;
	// left of the reticle's centre, its right edge 3 pixels short of it: the mouse arrow runs down and right
	// from its tip and covered a plate centred under the tip
	_txtSkillBonus->setText(text);
	const int textWidth = _txtSkillBonus->getTextWidth();
	if (_hdLabelsOn)
	{
		HdLabel label;
		label.text = Unicode::convUtf8ToUtf32(text);
		// the tag's centre; its plate is the text and 1.5 pixels on each side
		label.x = x + 13 * _k - (textWidth + 3) * _k / 2;
		label.y = y + 30 * _k;
		label.tag = true;
		label.scale = std::max(50, std::min(100, Options::oxceHdAimNumSize)) / 100.0f;
		label.weight = std::max(50, std::min(100, Options::oxceHdAimNumWeight)) / 100.0f;
		if (group > 0)
		{
			label.face = HdUi::rgba(pal[(Uint8)(group * 16 + 1)]);
			label.back = HdUi::rgba(pal[(Uint8)(group * 16 + 11)]);
			label.edge = HdUi::rgba(pal[(Uint8)(group * 16 + 14)]);
		}
		else
		{
			label.face = 0xFFFFE0A0u;
			label.back = 0xFF503010u;
			label.edge = 0xFF201008u;
		}
		_hdLabels.push_back(label);
		return;
	}
	_txtSkillBonus->setColor(group > 0 ? (Uint8)(group * 16) : Palette::blockOffset(Pathfinding::yellow - 1) - 1);
	_txtSkillBonus->draw();
	surface->blitClassic(_txtSkillBonus, x + 13 * _k - textWidth * _k, y + 30 * _k, _k);
}

void Map::drawTerrain(HdCanvas *surface)
{
	_isAltPressed = _game->isAltPressed(true);
	_isCtrlPressed = _game->isCtrlPressed(true);
	updateBlastArea(surface);
	updateAimHints(surface);
	// HD render: the SCC field of addressed walls follows the map size and the packs; on other frames
	// this is a comparison of four numbers
	static const int addressObstacleEvery = [] { const char *p = getenv("OXCE_HD_ADDRESS_OBSTACLE"); return p ? atoi(p) : 0; }();
	if (_hdTerrainAddress)
	{
		addressTestReload();
		_wallField.update(_save->getMapSizeX(), _save->getMapSizeY(), _save->getMapSizeZ());
	}
	// HD render: combat effect clips not drawn for a while go, before this frame records any
	HdFx::trim();
	HdFx::clearTips();
	int frameNumber = 0;
	SurfaceRaw<const Uint8> tmpSurface;
	Tile *tile;
	int beginX = 0, endX = _save->getMapSizeX() - 1;
	int beginY = 0, endY = _save->getMapSizeY() - 1;
	int beginZ = 0, endZ = _save->getMapSizeZ() - 1;
	Position mapPosition, screenPosition, bulletPositionScreen, movingUnitPosition;
	int bulletLowX=16000, bulletLowY=16000, bulletLowZ=16000, bulletHighX=0, bulletHighY=0, bulletHighZ=0;
	int dummy;
	BattleUnit *movingUnit = _save->getTileEngine()->getMovingUnit();
	int tileShade, tileColor, obstacleShade;
	UnitSprite unitSprite(surface, _game->getMod(), _save, _animFrame, _save->getDepth() != 0,
		_isTFTD ? ArrowColorsTFTD[1] : ArrowColorsUFO[1], _isTFTD ? ArrowColorsTFTD[2] : ArrowColorsUFO[2]);
	unitSprite.setScale(_k);
	ItemSprite itemSprite(surface, _game->getMod(), _save, _animFrame);
	// HD lab: the turned view - the cells go in the view's order, each drawing the world tile turned there
	const int rot = _camera->getRotation();
	const bool turned = rot != 0;
	const bool hdFrames = surface->getHdMode() != HD_MODE_NEAREST;
	if (turned && !_turn)
	{
		_turn = new HdTurn();
	}
	if (turned && !_turnGroups)
	{
		_turnGroups = new HdTurnGroups();
		_turnGroups->build(_save);
	}
	unitSprite.setDirectionShift(2 * rot);

	const int halfAnimFrame = (_animFrame / 2) % 4;
	const int halfAnimFrameRest = (_animFrame % 2);
	// HD render: a thrown explosive with a reticle style of its own (oxceHdReticleExplosive) is drawn with the reticle
	// frames instead of the throw box; the throw mark stays over it
	const bool explosiveReticle = _cursorType == CT_THROW && _aimKind == AIM_EXPLOSIVE && Options::oxceHdReticleExplosive > 0
		&& _k > 1 && surface->getHdMode() != HD_MODE_NEAREST;

	NumberText *_numWaypid = 0;

	// if we got bullet, get the highest x and y tiles to draw it on
	if (_projectile && _explosions.empty())
	{
		int part = _projectile->getItem() ? 0 : BULLET_SPRITES-1;
		for (int i = 0; i <= part; ++i)
		{
			if (_projectile->getPosition(1-i).x < bulletLowX)
				bulletLowX = _projectile->getPosition(1-i).x;
			if (_projectile->getPosition(1-i).y < bulletLowY)
				bulletLowY = _projectile->getPosition(1-i).y;
			if (_projectile->getPosition(1-i).z < bulletLowZ)
				bulletLowZ = _projectile->getPosition(1-i).z;
			if (_projectile->getPosition(1-i).x > bulletHighX)
				bulletHighX = _projectile->getPosition(1-i).x;
			if (_projectile->getPosition(1-i).y > bulletHighY)
				bulletHighY = _projectile->getPosition(1-i).y;
			if (_projectile->getPosition(1-i).z > bulletHighZ)
				bulletHighZ = _projectile->getPosition(1-i).z;
		}
		// divide by 16 to go from voxel to tile position
		bulletLowX = bulletLowX / 16;
		bulletLowY = bulletLowY / 16;
		bulletLowZ = bulletLowZ / 24;
		bulletHighX = bulletHighX / 16;
		bulletHighY = bulletHighY / 16;
		bulletHighZ = bulletHighZ / 24;

		// if the projectile is outside the viewport - center it back on it
		_camera->convertVoxelToScreen(_projectile->getPosition(), &bulletPositionScreen);

		if (_projectileInFOV && _followProjectile)
		{
			Position newCam = _camera->getMapOffset();
			if (newCam.z != bulletHighZ) //switch level
			{
				newCam.z = bulletHighZ;
				if (_projectileInFOV)
				{
					_camera->setMapOffset(newCam);
					_camera->convertVoxelToScreen(_projectile->getPosition(), &bulletPositionScreen);
				}
			}
			if (_smoothCamera)
			{
				if (_launch)
				{
					_launch = false;
					if ((bulletPositionScreen.x < 1 || bulletPositionScreen.x > surface->getWidth() - 1 ||
						bulletPositionScreen.y < 1 || bulletPositionScreen.y > _visibleMapHeight - 1))
					{
						_camera->centerOnPosition(Position(bulletLowX, bulletLowY, bulletHighZ), false);
						_camera->convertVoxelToScreen(_projectile->getPosition(), &bulletPositionScreen);
					}
				}
				if (!_smoothingEngaged)
				{
					if (bulletPositionScreen.x < 1 || bulletPositionScreen.x > surface->getWidth() - 1 ||
						bulletPositionScreen.y < 1 || bulletPositionScreen.y > _visibleMapHeight - 1)
					{
						_smoothingEngaged = true;
					}
				}
				else
				{
					_camera->jumpXY((surface->getWidth() / _k / 2) * _k - bulletPositionScreen.x, (_visibleMapHeight / _k / 2) * _k - bulletPositionScreen.y);
				}
			}
			else
			{
				bool enough;
				do
				{
					enough = true;
					if (bulletPositionScreen.x < 0)
					{
						_camera->jumpXY(+surface->getWidth(), 0);
						enough = false;
					}
					else if (bulletPositionScreen.x > surface->getWidth())
					{
						_camera->jumpXY(-surface->getWidth(), 0);
						enough = false;
					}
					else if (bulletPositionScreen.y < 0)
					{
						_camera->jumpXY(0, +_visibleMapHeight);
						enough = false;
					}
					else if (bulletPositionScreen.y > _visibleMapHeight)
					{
						_camera->jumpXY(0, -_visibleMapHeight);
						enough = false;
					}
					_camera->convertVoxelToScreen(_projectile->getPosition(), &bulletPositionScreen);
				}
				while (!enough);
			}
		}
		if (turned)
		{
			// HD lab: the box of the bullet in the view's tiles (its corners go to corners)
			const Position a = _camera->worldToView(Position(bulletLowX, bulletLowY, 0));
			const Position b = _camera->worldToView(Position(bulletHighX, bulletHighY, 0));
			bulletLowX = std::min(a.x, b.x);
			bulletHighX = std::max(a.x, b.x);
			bulletLowY = std::min(a.y, b.y);
			bulletHighY = std::max(a.y, b.y);
		}
	}

	// get corner map coordinates to give rough boundaries in which tiles to redraw are
	_camera->convertScreenToView(0, 0, &beginX, &dummy);
	_camera->convertScreenToView(surface->getWidth(), 0, &dummy, &beginY);
	_camera->convertScreenToView(surface->getWidth() + _spriteWidth, surface->getHeight() + _spriteHeight, &endX, &dummy);
	_camera->convertScreenToView(0, surface->getHeight() + _spriteHeight, &dummy, &endY);
	beginY -= (_camera->getViewLevel() * 2);
	beginX -= (_camera->getViewLevel() * 2);
	if (beginX < 0)
		beginX = 0;
	if (beginY < 0)
		beginY = 0;

	if (!_camera->getShowAllLayers())
	{
		endZ = std::min(endZ, _camera->getViewLevel());
	}
	if (_camera->getShowSingleLayer())
	{
		beginZ = _camera->getViewLevel();
		endZ = _camera->getViewLevel();
	}


	bool pathfinderTurnedOn = _save->getPathfinding()->isPathPreviewed();

	if (!_waypoints.empty() || (pathfinderTurnedOn && (_previewSettingTu || _previewSettingEnergy)))
	{
		_numWaypid = new NumberText(15, 15, 20, 30);
		_numWaypid->setPalette(getPalette());
		_numWaypid->setColor(pathfinderTurnedOn ? _messageColor + 1 : Palette::blockOffset(1));
	}

	if (movingUnit)
	{
		movingUnitPosition = movingUnit->getPosition();
	}

	// HD lab: the place of a tile in the order the cells go here (its index unturned)
	auto cellOrder = [&](const Position &pos)
	{
		if (!turned)
			return _save->getTileIndex(pos);
		const Position view = _camera->worldToView(pos);
		return (view.z * _camera->getViewSizeY() + view.y) * _camera->getViewSizeX() + view.x;
	};
	// HD lab: the view cell of a voxel (its tile unturned)
	auto viewCellOf = [&](const Position &voxel)
	{
		const Position cell(voxel.x / 16, voxel.y / 16, 0);
		return turned ? _camera->worldToView(cell) : cell;
	};
	// HD lab: the walls on the back edges of the view cell at mapPosition / screenPosition - the edge on the
	// left of the screen shows the west wall unturned, the one on the right the north wall; a wall of the other
	// part stands there mirrored. A cell past the map's far edges of the view draws only these (the walls of the
	// last tiles that face away from the view, which no tile of the map draws).
	auto drawTurnedWalls = [&]()
	{
		bool leftDrawn = false;
		for (int side = 0; side < 2; ++side)
		{
			const bool left = side == 0;
			TilePart part;
			Tile *owner = turnedWall(mapPosition, left, part);
			if (!owner)
				continue;
			SurfaceRaw<const Uint8> sprite = owner->getSprite(part);
			if (!sprite)
				continue;
			// a view painted for this turn stands as it is drawn: already on the diagonal of its slot
			const SurfaceRaw<const Uint8> view = hdFrames ? _turn->painted(sprite, rot) : SurfaceRaw<const Uint8>();
			if (view)
				sprite = view;
			else if (left != (part == O_WESTWALL))
				sprite = _turn->mirrored(sprite, hdFrames);
			int shade = getWallShade(part, owner);
			if (owner->getObstacle(part))
				shade = getShadePulseForFrame(shade, _animFrame);
			surface->blit(sprite, screenPosition.x, screenPosition.y - owner->getYOffset(part) * _k, shade, !left && leftDrawn, _nvColor);
			leftDrawn = leftDrawn || left;
		}
	};
	// HD lab: the frame of an object of the turned view - a view painted for this turn stands as it is drawn, in
	// its own place in the cell (no mirror, no shift); else the frame goes with its edge (turnedObject)
	auto objectTurned = [&](TurnedObject &placed, SurfaceRaw<const Uint8> sprite) -> SurfaceRaw<const Uint8>
	{
		const SurfaceRaw<const Uint8> view = hdFrames ? _turn->painted(sprite, rot) : SurfaceRaw<const Uint8>();
		if (view)
		{
			placed.dx = 0;
			placed.dy = 0;
			return view;
		}
		return placed.mirror ? _turn->mirrored(sprite, hdFrames) : sprite;
	};
	// HD lab: a tile whose object is a piece of a composite drawn whole (HdTurnGroups) does not draw it itself
	auto groupDrawn = [&](int tileIndex)
	{
		const int group = _turnGroups->memberOf(tileIndex);
		return group >= 0 && _turnGroups->active(group, rot, _turn, hdFrames);
	};
	// HD lab: the pieces of composites drawn whole that stand in the cell at mapPosition / screenPosition of the
	// turned view, those before its units (`back`) or after them: the cell gets the piece at its place in the
	// group's box as the view sees it - the whole as it is at turns 0 and 2, its mirror at turns 1 and 3
	auto drawGroupPieces = [&](int tileIndex, bool back, int shade, int pulseShade)
	{
		int count = 0;
		const int *groups = _turnGroups->covering(tileIndex, count);
		const bool mirror = (rot & 1) != 0;
		for (int i = 0; i < count; ++i)
		{
			const int group = groups[i];
			if (!_turnGroups->active(group, rot, _turn, hdFrames))
				continue;
			const Position corner = _turnGroups->corner(group), size = _turnGroups->size(group);
			const Position a = _camera->worldToView(corner);
			const Position b = _camera->worldToView(corner + Position(size.x - 1, size.y - 1, 0));
			const Position view = _camera->worldToView(mapPosition);
			const Position at(view.x - std::min(a.x, b.x), view.y - std::min(a.y, b.y), view.z - corner.z);
			Tile *source = _turnGroups->piece(group, mirror ? Position(at.y, at.x, at.z) : at);
			if (!source)
				continue;
			const int bigWall = source->getMapData(O_OBJECT)->getBigWall();
			if ((bigWall < 6 || bigWall == 9) != back)
				continue;
			SurfaceRaw<const Uint8> sprite = source->getSprite(O_OBJECT);
			if (!sprite)
				continue;
			if (mirror)
				sprite = _turn->mirrored(sprite, hdFrames);
			surface->blit(sprite, screenPosition.x, screenPosition.y - source->getYOffset(O_OBJECT) * _k,
				source->getObstacle(O_OBJECT) ? pulseShade : shade, false, _nvColor);
		}
	};
	// HD render: the parts of a collapsed building falling (HdFx::fall), each drawn in its cell's turn, as the
	// cells go here (by tile index)
	std::vector<std::pair<int, std::pair<const HdFx::Piece*, int>>> pieces;
	size_t nextPiece = 0;
	if (Options::oxceHdFx && surface->getHdMode() != HD_MODE_NEAREST)
	{
		std::vector<std::pair<const HdFx::Piece*, int>> falling;
		HdFx::falling(SDL_GetTicks(), falling);
		for (const auto &f : falling)
			if (_save->getTile(f.first->cell))
				pieces.push_back(std::make_pair(cellOrder(f.first->cell), f));
		std::stable_sort(pieces.begin(), pieces.end(), [](const auto &a, const auto &b) { return a.first < b.first; });
	}

	surface->lock();
	const Position cameraPos = _camera->getMapOffset();
	// HD lab: the turned view goes a cell past the map's far edges, for the walls that face away there
	const int rimX = endX + (turned && endX >= _camera->getViewSizeX() ? 1 : 0);
	const int rimY = endY + (turned && endY >= _camera->getViewSizeY() ? 1 : 0);
	for (int itZ = beginZ; itZ <= endZ; itZ++)
	{
		bool topLayer = itZ == endZ;
		for (int viewY = beginY; viewY < rimY; viewY++)
		{
			for (int viewX = beginX; viewX < rimX; viewX++)
			{
				// HD lab: the cell of the view and the world tile turned to it (the same one unturned)
				const Position viewPosition(viewX, viewY, itZ);
				mapPosition = turned ? _camera->viewToWorld(viewPosition) : viewPosition;
				tile = _save->getTile(mapPosition);
				const int itX = mapPosition.x, itY = mapPosition.y;
				_camera->convertMapToScreen(mapPosition, &screenPosition);
				screenPosition += cameraPos;
				if (!tile)
				{
					// HD lab: a cell past the far edge of the view
					if (_hdLightOn)
						_canvas->setLight(nullptr);
					drawTurnedWalls();
					continue;
				}

				// only render cells that are inside the surface
				if (screenPosition.x > -_spriteWidth && screenPosition.x < surface->getWidth() + _spriteWidth &&
					screenPosition.y > -_spriteHeight && screenPosition.y < surface->getHeight() + _spriteHeight )
				{
					bool isUnitMovingNearby = movingUnit && positionInRangeXY(movingUnitPosition, mapPosition, 2);

					if (tile->isDiscovered(O_FLOOR))
					{
						tileShade = reShade(tile);
						obstacleShade = tileShade;
						if (_showObstacles)
						{
							if (tile->isObstacle())
							{
								obstacleShade = getShadePulseForFrame(tileShade, _animFrame);
							}
						}
						if (_hdLightOn)
						{
							updateHdLight(tile, tileShade, mapPosition);
						}
					}
					else
					{
						tileShade = 16;
						obstacleShade = 16;
						if (_hdLightOn)
						{
							_canvas->setLight(nullptr);
						}
					}

					tileColor = tile->getMarkerColor();

					// Draw floor
					tmpSurface = tile->getSprite(O_FLOOR);
					if (tmpSurface)
					{
						// HD lab: a flat floor turns with the map, unless a view is painted for this turn
						if (turned)
						{
							const SurfaceRaw<const Uint8> view = hdFrames ? _turn->painted(tmpSurface, rot) : SurfaceRaw<const Uint8>();
							tmpSurface = view ? view : _turn->floorTurned(tmpSurface, rot, hdFrames);
						}
						// HD render: a floor with pack variants shows the one the ground pattern puts here
						if (_hdGroundVariants && !turned)
							surface->setGroundCell(true, mapPosition.x, mapPosition.y, mapPosition.z);
						if (tile->getObstacle(O_FLOOR))
							surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_FLOOR) * _k, obstacleShade, false, _nvColor);
						else
							surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_FLOOR) * _k, tileShade, false, _nvColor);
						if (_hdGroundVariants && !turned)
							surface->setGroundCell(false, 0, 0, 0);
					}

					// HD render: the explosion area of what is aimed, on the floor of every tile it reaches that the player
					// has seen (not in the air above a level): the colour of the damage type, the stronger the power the denser
					if (_blastMax > 0 && tile->isDiscovered(O_FLOOR) && (itZ == 0 || tile->getMapData(O_FLOOR)))
					{
						const int blastPower = _blastPower[_save->getTileIndex(mapPosition)];
						if (blastPower > 0)
						{
							const float share = std::max(BLAST_ALPHA_FLOOR, std::min(1.0f, (float)blastPower / _blastMax));
							const int step = std::max(1, (int)std::lround(share * BLAST_ALPHA_STEPS));
							const int alpha = BLAST_ALPHA_MAX * step / BLAST_ALPHA_STEPS;
							surface->blitFrame(blastDiamond(_blastRgb, alpha, _k), screenPosition.x,
								screenPosition.y + 24 * _k - tile->getYOffset(O_FLOOR) * _k);
						}
					}
					// HD render: the collapse hint - the tiles whose building parts may fall after the explosion, in hazard stripes
					if (_blastMax > 0 && _blastFallCount > 0 && _blastFall[_save->getTileIndex(mapPosition)])
					{
						surface->blitFrame(fallDiamond(_k), screenPosition.x, screenPosition.y + 24 * _k - tile->getYOffset(O_FLOOR) * _k);
					}

					auto* unit = tile->getUnit();

					// Draw cursor back
					if (_cursorType != CT_NONE && _selectorX > itX - _cursorSize && _selectorY > itY - _cursorSize && _selectorX < itX+1 && _selectorY < itY+1 && !_save->getBattleState()->getMouseOverIcons())
					{
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

					if (isUnitMovingNearby)
					{
						// special handling for a moving unit in background of tile.
						constexpr static Position backPos[] =
						{
							Position(0, -1, 0),
							Position(-1, -1, 0),
							Position(-1, 0, 0),
						};

						for (size_t b = 0; b < std::size(backPos); ++b)
						{
							drawUnit(unitSprite, _save->getTile(mapPosition + (turned ? _camera->viewStepToWorld(backPos[b]) : backPos[b])), tile, screenPosition, topLayer);
						}
					}

					// Draw walls
					{
						// HD lab: the walls on the back edges of the view cell
						if (turned)
						{
							drawTurnedWalls();
						}
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
						// Draw object
						tmpSurface = tile->getSprite(O_OBJECT);
						if (tmpSurface && !(turned && groupDrawn(_save->getTileIndex(mapPosition))))
						{
							// HD lab: an object on an edge of its tile goes with the edge
							TurnedObject placed = turned ? turnedObject(tile->getMapData(O_OBJECT)->getBigWall()) : TurnedObject{ tile->isBackTileObject(O_OBJECT), false, 0, 0 };
							if (placed.back)
							{
								if (turned)
									tmpSurface = objectTurned(placed, tmpSurface);
								if (tile->getObstacle(O_OBJECT))
									surface->blit(tmpSurface, screenPosition.x + placed.dx, screenPosition.y + placed.dy - tile->getYOffset(O_OBJECT) * _k, obstacleShade, false, _nvColor);
								else
									surface->blit(tmpSurface, screenPosition.x + placed.dx, screenPosition.y + placed.dy - tile->getYOffset(O_OBJECT) * _k, tileShade, false, _nvColor);
							}
						}
						if (turned)
							drawGroupPieces(_save->getTileIndex(mapPosition), true, tileShade, obstacleShade);
						// HD render: the collapsed parts that stood in this cell, on their way down
						if (nextPiece < pieces.size())
						{
							const int index = cellOrder(mapPosition);
							while (nextPiece < pieces.size() && pieces[nextPiece].first < index)
								++nextPiece;
							for (; nextPiece < pieces.size() && pieces[nextPiece].first == index; ++nextPiece)
							{
								const HdFx::Piece &piece = *pieces[nextPiece].second.first;
								const int down = pieces[nextPiece].second.second;
								const bool ground = piece.part == O_FLOOR && _hdGroundVariants && !turned;
								if (ground)
									surface->setGroundCell(true, mapPosition.x, mapPosition.y, mapPosition.z);
								surface->blit(piece.sprite, screenPosition.x, screenPosition.y + (down - piece.yOffset) * _k, tileShade, false, _nvColor);
								if (ground)
									surface->setGroundCell(false, 0, 0, 0);
							}
						}
						// draw an item on top of the floor (if any)
						BattleItem* item = tile->getTopItem();
						if (item)
						{
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
									else if (!_woundIndicator.empty() && itemUnit->getFatalWounds() > 0)
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
					}

					// check if we got bullet && it is in Field Of View
					if (_projectile && _projectileInFOV)
					{
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
							if (viewX >= bulletLowX && viewX <= bulletHighX && viewY >= bulletLowY && viewY <= bulletHighY)
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
										Position voxelPos = _projectile->getPosition(1-i);
										// HD render: one voxel of the trail is k screen pixels and the tracer sprite is
										// only three base pixels wide, so its thirty-five stamps are a row of separate
										// dots with gaps between them. In HD the step to the next voxel is filled with
										// stamps of the same sprite and the shot reads as one beam; the classic path
										// draws the single stamp it always drew
										Position trail = Position(0, 0, 0);
										int steps = 1;
										// (a tiny frame without a dot is one hd/FX/weapons.txt leaves classic: its bars stay one a voxel)
										if (surface->getHdMode() != HD_MODE_NEAREST && (HdSprites::registered(tmpSurface.getBuffer()) || tmpSurface.getWidth() > 4 * _k))
										{
											Position from, to;
											_camera->convertVoxelToScreen(voxelPos, &from);
											_camera->convertVoxelToScreen(_projectile->getPosition(-i), &to);
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
										voxelPos = _projectile->getPosition(1-i);
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

					//draw particle clouds
					// a particle is a 2x2 pattern of size thresholds; at HD scale every cell becomes a k x k block
					const int pixelMaskBase[] = { 0, 2, 1, 3 };
					std::vector<int> pixelMaskArray(4 * _k * _k);
					for (int my = 0; my < 2 * _k; ++my)
						for (int mx = 0; mx < 2 * _k; ++mx)
							pixelMaskArray[my * 2 * _k + mx] = pixelMaskBase[(my / _k) * 2 + (mx / _k)];
					SurfaceRaw<int> pixelMask(pixelMaskArray, 2 * _k, 2 * _k);
					const int vaporScreenOriginX = screenPosition.x + _spriteWidth / 2;
					const int vaporScreenOriginY = screenPosition.y + _spriteHeight - _spriteWidth / 2 + tile->getPosition().toVoxel().z * _k;
					const Uint8* const transparetPtr = _transparencies->data();
					const bool softVapor = surface->getHdMode() != HD_MODE_NEAREST;

					//draw particle clouds behind solder
					for (const Particle& p : getVaporParticle(tile, 0))
					{
						if (softVapor)
						{
							// HD: a soft round puff at the particle's own place, fading smoothly (classic mode keeps the 2x2 pattern)
							const Position o = p.getOffset16(_k);
							surface->drawVaporSoft(vaporScreenOriginX * 16 + o.x + _k * 16, vaporScreenOriginY * 16 + o.y + _k * 16, p.getSize(), _k, vaporTintSoft(p));
							continue;
						}
						int vaporX = vaporScreenOriginX + p.getOffsetX() * _k;
						int vaporY = vaporScreenOriginY + p.getOffsetY() * _k;
						auto transparetOffsets = transparetPtr
							+ (p.getColor() * Mod::TransparenciesOpacityLevels * Mod::TransparenciesPaletteColors)
							+ (p.getOpacity() * Mod::TransparenciesPaletteColors);

						surface->drawVapor(pixelMask, vaporX, vaporY, p.getSize(), transparetOffsets, vaporTint(p));
					}

					unit = tile->getUnit();
					// Draw soldier from this tile, below or above
					drawUnit(unitSprite, tile, tile, screenPosition, topLayer, isUnitMovingNearby ? movingUnit : nullptr);

					if (isUnitMovingNearby)
					{
						// special handling for a moving unit in foreground of tile.
						constexpr static Position frontPos[] =
						{
							Position(-1, +1, 0),
							Position(0, +1, 0),
							Position(+1, +1, 0),
							Position(+1, 0, 0),
							Position(+1, -1, 0),
						};

						for (size_t f = 0; f < std::size(frontPos); ++f)
						{
							drawUnit(unitSprite, _save->getTile(mapPosition + (turned ? _camera->viewStepToWorld(frontPos[f]) : frontPos[f])), tile, screenPosition, topLayer);
						}
					}

					// Draw smoke/fire
					if (tile->getSmoke() && tile->isDiscovered(O_FLOOR))
					{
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
							const int variant = tile->getFire() ? (enviRest ? 1 : 0) + 2 * Options::oxceHdFire : 0;
							if (variant)
								surface->setFrameVariant(variant);
							surface->blit(tmpSurface, screenPosition.x, screenPosition.y + (tile->getFire() ? tile->getTerrainLevel() * _k : 0), shade, false, _nvColor);
							if (variant)
								surface->setFrameVariant(0);
						}
						else
						{
							surface->blit(tmpSurface, screenPosition.x, screenPosition.y, shade, false, _nvColor);
						}
					}

					//draw particle clouds on front of solder
					for (const Particle& p : getVaporParticle(tile, topLayer ? 3 : 1))
					{
						if (softVapor)
						{
							// HD: a soft round puff at the particle's own place, fading smoothly (classic mode keeps the 2x2 pattern)
							const Position o = p.getOffset16(_k);
							surface->drawVaporSoft(vaporScreenOriginX * 16 + o.x + _k * 16, vaporScreenOriginY * 16 + o.y + _k * 16, p.getSize(), _k, vaporTintSoft(p));
							continue;
						}
						int vaporX = vaporScreenOriginX + p.getOffsetX() * _k;
						int vaporY = vaporScreenOriginY + p.getOffsetY() * _k;
						auto transparetOffsets = transparetPtr
							+ (p.getColor() * Mod::TransparenciesOpacityLevels * Mod::TransparenciesPaletteColors)
							+ (p.getOpacity() * Mod::TransparenciesPaletteColors);

						surface->drawVapor(pixelMask, vaporX, vaporY, p.getSize(), transparetOffsets, vaporTint(p));
					}

					// Draw Path Preview
					if (_previewSettingArrows && tile->getPreview() != -1 && tile->isDiscovered(O_FLOOR))
					{
						if (itZ > 0 && tile->hasNoFloor(_save))
						{
							tmpSurface = _game->getMod()->getHdSurfaceSet("Pathfinding")->getFrame(11);
							if (tmpSurface)
							{
								surface->blit(tmpSurface, screenPosition.x, screenPosition.y + 2 * _k, 0, false, tile->getMarkerColor());
							}
						}
						tmpSurface = _game->getMod()->getHdSurfaceSet("Pathfinding")->getFrame(turnedDir(tile->getPreview()));
						if (tmpSurface)
						{
							blitPathArrow(surface, tmpSurface, screenPosition.x, screenPosition.y + tile->getTerrainLevel() * _k, tileColor, tile, mapPosition);
						}
					}

					{
						// Draw object
						tmpSurface = tile->getSprite(O_OBJECT);
						if (tmpSurface && !(turned && groupDrawn(_save->getTileIndex(mapPosition))))
						{
							// HD lab: an object on an edge of its tile goes with the edge
							TurnedObject placed = turned ? turnedObject(tile->getMapData(O_OBJECT)->getBigWall()) : TurnedObject{ tile->isBackTileObject(O_OBJECT), false, 0, 0 };
							if (!placed.back)
							{
								if (turned)
									tmpSurface = objectTurned(placed, tmpSurface);
								if (tile->getObstacle(O_OBJECT))
									surface->blit(tmpSurface, screenPosition.x + placed.dx, screenPosition.y + placed.dy - tile->getYOffset(O_OBJECT) * _k, obstacleShade, false, _nvColor);
								else
									surface->blit(tmpSurface, screenPosition.x + placed.dx, screenPosition.y + placed.dy - tile->getYOffset(O_OBJECT) * _k, tileShade, false, _nvColor);
							}
						}
						if (turned)
							drawGroupPieces(_save->getTileIndex(mapPosition), false, tileShade, obstacleShade);
					}
					// Draw cursor front
					if (_cursorType != CT_NONE && _selectorX > itX - _cursorSize && _selectorY > itY - _cursorSize && _selectorX < itX+1 && _selectorY < itY+1 && !_save->getBattleState()->getMouseOverIcons())
					{
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

					// Draw waypoints if any on this tile
					int waypid = 1;
					int waypXOff = 2 * _k;
					int waypYOff = 2 * _k;

					for (const auto& waypoint : _waypoints)
					{
						if (waypoint == mapPosition)
						{
							if (waypXOff == 2 * _k && waypYOff == 2 * _k)
							{
								tmpSurface = _game->getMod()->getHdSurfaceSet("CURSOR.PCK")->getFrame(7);
								surface->blit(tmpSurface, screenPosition.x, screenPosition.y, 0);
							}
							if (_save->getBattleGame()->getCurrentAction()->type == BA_LAUNCH || _save->getBattleGame()->getCurrentAction()->sprayTargeting)
							{
								_numWaypid->setValue(waypid);
								_numWaypid->setBordered(true); // OXCE, not configurable
								_numWaypid->draw();
								surface->blitClassic(_numWaypid, screenPosition.x + waypXOff, screenPosition.y + waypYOff, _k);

								waypXOff += (waypid > 9 ? 10 : 6) * _k; // OXCE
								if (waypXOff >= 26 * _k)
								{
									waypXOff = 2 * _k;
									waypYOff += 8 * _k;
								}
							}
						}
						waypid++;
					}
				}
			}
		}
	}
	if (pathfinderTurnedOn)
	{
		if (_numWaypid)
		{
			_numWaypid->setBordered(true); // give it a border for the pathfinding display, makes it more visible on snow, etc.
		}
		for (int itZ = beginZ; itZ <= endZ; itZ++)
		{
			for (int itX = beginX; itX <= endX; itX++)
			{
				for (int itY = beginY; itY <= endY; itY++)
				{
					// HD lab: itX, itY go over the cells of the view
					mapPosition = turned ? _camera->viewToWorld(Position(itX, itY, itZ)) : Position(itX, itY, itZ);
					_camera->convertMapToScreen(mapPosition, &screenPosition);
					screenPosition += _camera->getMapOffset();

					// only render cells that are inside the surface
					if (screenPosition.x > -_spriteWidth && screenPosition.x < surface->getWidth() + _spriteWidth &&
						screenPosition.y > -_spriteHeight && screenPosition.y < surface->getHeight() + _spriteHeight )
					{
						tile = _save->getTile(mapPosition);
						if (!tile || !tile->isDiscovered(O_FLOOR) || tile->getPreview() == -1)
							continue;
						int adjustment = -tile->getTerrainLevel() * _k;
						if (_previewSettingArrows)
						{
							if (itZ > 0 && tile->hasNoFloor(_save))
							{
								tmpSurface = _game->getMod()->getHdSurfaceSet("Pathfinding")->getFrame(23);
								if (tmpSurface)
								{
									surface->blit(tmpSurface, screenPosition.x, screenPosition.y + 2 * _k, 0, false, tile->getMarkerColor());
								}
							}
							int overlay = turnedDir(tile->getPreview()) + 12;
							tmpSurface = _game->getMod()->getHdSurfaceSet("Pathfinding")->getFrame(overlay);
							if (tmpSurface)
							{
								blitPathArrow(surface, tmpSurface, screenPosition.x, screenPosition.y - adjustment, tile->getMarkerColor(), tile, mapPosition);
							}
						}

						if ((_previewSettingTu || _previewSettingEnergy) && (tile->getTUMarker() > -1 || tile->getEnergyMarker() > -1))
						{
							int off = (tile->getTUMarker() > 9 ? 5 : 3) * _k;
							int offE = (tile->getEnergyMarker() > 9 ? 5 : 3) * _k;
							int mcolor = _previewSettingArrows ? 0 : tile->getMarkerColor();
							if (_previewSettingArrows)
							{
								adjustment += 7 * _k;
							}
							if (_save->getSelectedUnit() && _save->getSelectedUnit()->isBigUnit())
							{
								adjustment += 1 * _k;
								if (!_previewSettingArrows)
								{
									adjustment += 7 * _k;
								}
							}
							if (_hdLabelsOn && Options::oxceHdPathDigits)
							{
								// HD interface: the numbers in the TrueType face, centred where the classic digits stand;
								// the destination (preview 10, the path's last step) larger than the steps on the way.
								// Colours: the bordered digit's face and outer edge, in the ramp blitClassic recolours to
								const bool last = tile->getPreview() == 10;
								const SDL_Color *pal = getPalette();
								const int faceIdx = _numWaypid->getColor() + 1;
								const int ramp = mcolor ? (mcolor - 1) << 4 : faceIdx & 0xF0, shade = faceIdx & 0x0F;
								const bool both = _previewSettingTu && _previewSettingEnergy;
								const int sizePct = std::max(50, std::min(100, Options::oxceHdPathNumSize));
								const int weightPct = std::max(50, std::min(100, Options::oxceHdPathNumWeight));
								auto put = [&](int value, int classicY, int lastLift)
								{
									if (value < 0) return;
									HdLabel label;
									label.text = Unicode::convUtf8ToUtf32(std::to_string(value));
									label.x = screenPosition.x + 16 * _k - _k / 2;
									label.y = screenPosition.y + classicY - adjustment + (last ? -lastLift : 1 * _k);
									label.cap = last ? 7.0f : 5.0f;
									if (sizePct != 100)
									{
										// smaller by the player's percent, the baseline stays where it was
										const float smaller = label.cap * sizePct / 100.0f;
										label.y += (int)std::lround((label.cap - smaller) * _k);
										label.cap = smaller;
									}
									label.weight = weightPct / 100.0f;
									label.centre = true;
									label.face = HdUi::rgba(pal[(Uint8)(ramp + shade)]);
									label.edge = HdUi::rgba(pal[(Uint8)(ramp + std::min(shade + 11, 15))]);
									_hdLabels.push_back(label);
								};
								if (_previewSettingTu)
								{
									put(tile->getTUMarker(), (both ? 22 : 29) * _k, (both ? 2 : 1) * _k);
								}
								if (_previewSettingEnergy)
								{
									put(tile->getEnergyMarker(), 29 * _k, 1 * _k);
								}
							}
							else if (_previewSettingTu)
							{
								_numWaypid->setValue(tile->getTUMarker());
								_numWaypid->draw();
								if (_previewSettingEnergy)
								{
									// TU
									surface->blitClassic(_numWaypid, screenPosition.x + 16 * _k - off, screenPosition.y + (22 * _k - adjustment), _k, 0, mcolor);
									// and Energy
									_numWaypid->setValue(tile->getEnergyMarker());
									_numWaypid->draw();
									surface->blitClassic(_numWaypid, screenPosition.x + 16 * _k - offE, screenPosition.y + (29 * _k - adjustment), _k, 0, mcolor);
								}
								else
								{
									// only TU
									surface->blitClassic(_numWaypid, screenPosition.x + 16 * _k - off, screenPosition.y + (29 * _k - adjustment), _k, 0, mcolor);
								}
							}
							else if (_previewSettingEnergy)
							{
								// only Energy
								_numWaypid->setValue(tile->getEnergyMarker());
								_numWaypid->draw();
								surface->blitClassic(_numWaypid, screenPosition.x + 16 * _k - offE, screenPosition.y + (29 * _k - adjustment), _k, 0, mcolor);
							}
						}
					}
				}
			}
		}
		if (_numWaypid)
		{
			_numWaypid->setBordered(false); // make sure we remove the border in case it's being used for missile waypoints.
		}
	}

	auto* selectedUnit = _save->getSelectedUnit();
	if (selectedUnit && (_save->getSide() == FACTION_PLAYER || _save->getDebugMode()) && selectedUnit->getPosition().z <= _camera->getViewLevel())
	{
		_camera->convertMapToScreen(selectedUnit->getPosition(), &screenPosition);
		screenPosition += _camera->getMapOffset();
		Position offset = calculateWalkingOffset(selectedUnit).ScreenOffset;
		if (selectedUnit->isBigUnit())
		{
			offset.y += 4 * _k;
		}
		offset.y += (Position::TileZ - (selectedUnit->getHeight() + selectedUnit->getFloatHeight())) * _k;
		if (selectedUnit->isKneeled())
		{
			offset.y -= 2 * _k;
		}
		if (this->getCursorType() != CT_NONE)
		{
			surface->blitClassic(_arrow, screenPosition.x + offset.x + (_spriteWidth / 2) - (_arrow->getWidth() / 2) * _k, screenPosition.y + offset.y - _arrow->getHeight() * _k + getArrowBobForFrame(_animFrame, _k), _k);
		}
	}

	// Draw the indicator number above the units seen directly by the selected unit
	if (_numUnitMarker && (_save->getSide() == FACTION_PLAYER || _save->getDebugMode()) && this->getCursorType() != CT_NONE)
	{
		for (int i = 0; i < UNIT_MARKER_MAX; ++i)
		{
			const BattleUnit *markedUnit = _unitMarkerUnit[i];
			if (!markedUnit || markedUnit->isOut() || !(markedUnit->getVisible() || _save->getDebugMode()))
			{
				continue;
			}
			if (markedUnit->getPosition().z > _camera->getViewLevel())
			{
				continue;
			}
			_camera->convertMapToScreen(markedUnit->getPosition(), &screenPosition);
			screenPosition += _camera->getMapOffset();
			Position markerOffset = calculateWalkingOffset(markedUnit).ScreenOffset;
			if (markedUnit->isBigUnit())
			{
				markerOffset.y += 4 * _k;
			}
			markerOffset.y += (Position::TileZ - (markedUnit->getHeight() + markedUnit->getFloatHeight())) * _k;
			if (markedUnit->isKneeled())
			{
				markerOffset.y -= 2 * _k;
			}
			const int markerX = screenPosition.x + markerOffset.x + (_spriteWidth / 2) - (i < 9 ? 3 : 5) * _k;
			const int markerY = screenPosition.y + markerOffset.y - 12 * _k;
			if (_hdLabelsOn)
			{
				// the classic tag is the digit in shade 1 inside a border 8 and 11 shades darker, in the map's
				// colours like the baked tag. The blinking colour runs the digit down its ramp, and the border
				// then goes past the ramp's end into the next one: a thin edge of another colour is not seen,
				// a whole plate of it is. So the plate stays in the digit's ramp: darker under a light digit,
				// lighter under one from shade 6 on (a darker plate under it no longer reads)
				const SDL_Color *pal = getPalette();
				const int ramp = (_unitMarkerColor[i] + 1) & 0xF0, shade = (_unitMarkerColor[i] + 1) & 0x0F;
				const int plate = shade < 6 ? shade + 8 : shade - 6;
				const int edge = std::min(plate + 3, 15);
				HdLabel label;
				label.text = Unicode::convUtf8ToUtf32(std::to_string(i + 1));
				label.x = markerX + (i < 9 ? 5 : 9) * _k / 2;
				label.y = markerY;
				label.tag = true;
				label.face = HdUi::rgba(pal[(Uint8)(ramp + shade)]);
				label.back = HdUi::rgba(pal[(Uint8)(ramp + plate)]);
				label.edge = HdUi::rgba(pal[(Uint8)(ramp + edge)]);
				_hdLabels.push_back(label);
				continue;
			}
			_numUnitMarker->setColor(_unitMarkerColor[i]);
			_numUnitMarker->setValue(i + 1);
			_numUnitMarker->draw();
			surface->blitClassic(_numUnitMarker, markerX, markerY, _k);
		}
	}

	// gentle mode: where the reaction fire came from (drawn while the shot flies too, the cursor is off then)
	// HD render: the flight arc of what is aimed, on top of the map
	drawAimArc(surface);

	drawGentleArrows(surface);

	// Draw motion scanner arrows
	if (_isAltPressed && _save->getSide() == FACTION_PLAYER && this->getCursorType() != CT_NONE)
	{
		for (auto* myUnit : *_save->getUnits())
		{
			bool motionScan = myUnit->getScannedTurn() == _save->getTurn() && myUnit->getFaction() != FACTION_PLAYER && !myUnit->isOut();
			bool customMarker = myUnit->getCustomMarker() > 0 && myUnit->getFaction() == FACTION_PLAYER && !myUnit->isOut();
			if (motionScan || customMarker)
			{
				Position temp = myUnit->getPosition();
				temp.z = _camera->getViewLevel();
				_camera->convertMapToScreen(temp, &screenPosition);
				screenPosition += _camera->getMapOffset();
				Position offset;
				//calculateWalkingOffset(myUnit, &offset);
				if (myUnit->isBigUnit())
				{
					offset.y += 4 * _k;
				}
				if (motionScan)
				{
					offset.y += (Position::TileZ - /*myUnit->getHeight()*/ 21) * _k; // no spoilers
				}
				else if (customMarker)
				{
					offset.y += (Position::TileZ - (myUnit->getHeight() + myUnit->getFloatHeight())) * _k;
				}
				if (myUnit->isKneeled())
				{
					offset.y -= 2 * _k;
				}
				if (motionScan)
				{
					surface->blitClassic(
						_arrow,
						screenPosition.x + offset.x + (_spriteWidth / 2) - (_arrow->getWidth() / 2) * _k,
						screenPosition.y + offset.y - _arrow->getHeight() * _k + getArrowBobForFrame(_animFrame, _k),
						_k);
				}
				else if (customMarker)
				{
					surface->blitClassic(
						_arrow,
						screenPosition.x + offset.x + (_spriteWidth / 2) - (_arrow->getWidth() / 2) * _k,
						screenPosition.y + offset.y - _arrow->getHeight() * _k + getArrowBobForFrame(_animFrame, _k),
						_k,
						0,
						_isTFTD ? ArrowColorsTFTD[myUnit->getCustomMarker() % 4] : ArrowColorsUFO[myUnit->getCustomMarker() % 4]);
				}
			}
		}
	}
	delete _numWaypid;

	// Draw craft deployment preview arrows
	if (_isAltPressed && _save->isPreview() && this->getCursorType() != CT_NONE)
	{
		for (auto& pos : _save->getCraftTiles())
		{
			if (pos.z == _camera->getViewLevel())
			{
				_camera->convertMapToScreen(pos, &screenPosition);
				screenPosition += _camera->getMapOffset();
				screenPosition.y += 2 * _k; // based on vanilla soldier standHeight
				surface->blitClassic(
					_arrow,
					screenPosition.x + (_spriteWidth / 2) - (_arrow->getWidth() / 2) * _k,
					screenPosition.y - _arrow->getHeight() * _k + getArrowBobForFrame(_animFrame, _k),
					_k);
			}
		}
	}

	// check if we got big explosions
	if (_explosionInFOV)
	{
		// big explosions cause the screen to flash as bright as possible before any explosions are actually drawn.
		// this causes everything to look like EGA for a single frame.
		if (_flashScreen)
		{
			surface->flash();
			_flashScreen = false;
		}
		else
		{
			std::vector<const Explosion*> drawn(_explosions.begin(), _explosions.end());
			for (const auto &loose : _looseHits)
			{
				drawn.push_back(loose.explosion);
			}
			for (const auto* explosion : drawn)
			{
				_camera->convertVoxelToScreen(explosion->getPosition(), &bulletPositionScreen);
				// HD render: the combat effect clip in place of the classic frames, frame for frame by progress
				if (Options::oxceHdFx && surface->getHdMode() != HD_MODE_NEAREST && !explosion->getHdFx().empty())
				{
					if (explosion->getCurrentFrame() < 0)
					{
						continue;
					}
					const char *setName = explosion->isBig() ? "X1.PCK" : explosion->isHit() ? "HIT.PCK" : "SMOKE.PCK";
					const std::string clip = HdFx::colour(explosion->getHdFx(), _game->getMod()->getSurfaceSet(setName)->getFrame(explosion->getStartFrame()), getPalette());
					if (const HdFrame *hd = HdFx::frame(clip, explosion->getCurrentFrame() - explosion->getStartFrame(), explosion->getFrameCount(), _k))
					{
						surface->blitFrame(*hd, bulletPositionScreen.x - hd->width / 2, bulletPositionScreen.y - hd->height / 2);
						continue;
					}
				}
				if (explosion->isBig())
				{
					if (explosion->getCurrentFrame() >= 0)
					{
						tmpSurface = _game->getMod()->getHdSurfaceSet("X1.PCK")->getFrame(explosion->getCurrentFrame());
						surface->blit(tmpSurface, bulletPositionScreen.x - (tmpSurface.getWidth() / _k / 2) * _k, bulletPositionScreen.y - (tmpSurface.getHeight() / _k / 2) * _k, 0, false, _nvColor);
					}
				}
				else
				{
					// HD render: a hit on a unit draws the pack's other picture of the frame (blood), if it has one
					const bool onUnit = explosion->isOnUnit() && surface->getHdMode() != HD_MODE_NEAREST;
					if (onUnit)
						surface->setFrameVariant(1);
					if (explosion->isHit())
					{
						tmpSurface = _game->getMod()->getHdSurfaceSet("HIT.PCK")->getFrame(explosion->getCurrentFrame());
						surface->blit(tmpSurface, bulletPositionScreen.x - 15 * _k, bulletPositionScreen.y - 25 * _k, 0, false, _nvColor);
					}
					else
					{
						tmpSurface = _game->getMod()->getHdSurfaceSet("SMOKE.PCK")->getFrame(explosion->getCurrentFrame());
						surface->blit(tmpSurface, bulletPositionScreen.x - 15 * _k, bulletPositionScreen.y - 15 * _k, 0, false, _nvColor);
					}
					if (onUnit)
						surface->setFrameVariant(0);
				}
			}
		}
	}

	// HD render: muzzle flashes, on their own clock (see hdMuzzle)
	if (Options::oxceHdFx && surface->getHdMode() != HD_MODE_NEAREST)
	{
		std::vector<std::pair<const HdFx::Live*, const HdFrame*>> flashes;
		HdFx::running(SDL_GetTicks(), _k, flashes);
		for (const auto &f : flashes)
		{
			// at the muzzle of the weapon as drawn this frame (see UnitSprite::blitItem), else where the shot leaves
			_camera->convertVoxelToScreen(f.first->voxel, &bulletPositionScreen);
			if (f.first->tip)
			{
				bulletPositionScreen.x = f.first->tipX;
				bulletPositionScreen.y = f.first->tipY;
			}
			surface->blitFrame(*f.second, bulletPositionScreen.x - f.second->width / 2, bulletPositionScreen.y - f.second->height / 2);
		}
	}

	surface->unlock();
}

/**
 * Handles mouse presses on the map.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void Map::mousePress(Action *action, State *state)
{
	InteractiveSurface::mousePress(action, state);
	// HD render: Ctrl + mouse wheel zooms the view in and out; the wheel alone goes on changing the level
	const Uint8 button = action->getDetails()->button.button;
	if ((button == SDL_BUTTON_WHEELUP || button == SDL_BUTTON_WHEELDOWN) && Options::oxceHdCtrlZoom && _game->isCtrlPressed() && zoomView(button == SDL_BUTTON_WHEELUP ? 1 : -1))
	{
		return;
	}
	_camera->mousePress(action, state);
}

/**
 * Handles mouse releases on the map.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void Map::mouseRelease(Action *action, State *state)
{
	InteractiveSurface::mouseRelease(action, state);
	_camera->mouseRelease(action, state);
}

/**
 * Handles keyboard presses on the map.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void Map::keyboardPress(Action *action, State *state)
{
	InteractiveSurface::keyboardPress(action, state);
	_camera->keyboardPress(action, state);
}

/**
 * Handles map vision toggle mode.
 */

void Map::enableNightVision()
{
	_nightVisionOn = true;
	_debugVisionMode = 0;
	persistToggles();
}

void Map::toggleNightVision()
{
	_nightVisionOn = !_nightVisionOn;
	_debugVisionMode = 0;
	persistToggles();
}

void Map::toggleDebugVisionMode()
{
	_debugVisionMode = (_debugVisionMode + 1) % 3;
	_nightVisionOn = false;
	persistToggles();
}

void Map::persistToggles()
{
	if (Options::oxceToggleNightVisionType == 2)
	{
		// persisted per campaign
		_game->getSavedGame()->setToggleNightVision(_nightVisionOn);
	}
	else if (Options::oxceToggleNightVisionType == 1)
	{
		// persisted per battle
		_save->setToggleNightVision(_nightVisionOn);
	}

	if (Options::oxceToggleBrightnessType == 2)
	{
		// persisted per campaign
		_game->getSavedGame()->setToggleBrightness(_debugVisionMode);
	}
	else if (Options::oxceToggleBrightnessType == 1)
	{
		// persisted per battle
		_save->setToggleBrightness(_debugVisionMode);
	}

	_save->setToggleBrightnessTemp(_debugVisionMode);
}

/**
 * Handles fade-in and fade-out shade modification
 * @param original tile/item/unit shade
 */

int Map::reShade(Tile *tile) const
{
	// when modders just don't know where to stop...
	if (_debugVisionMode > 0)
	{
		if (_debugVisionMode == 1)
		{
			// Reaver's tests
			return tile->getShade() / 2;
		}
		// Meridian's debug helper
		return 0;
	}

	// no night vision
	if (_nvColor == 0)
	{
		return tile->getShade();
	}

	// already bright enough
	if ((tile->getShade() <= NIGHT_VISION_SHADE))
	{
		return tile->getShade();
	}

	// hybrid night vision (local)
	for (const auto* bu : *_save->getUnits())
	{
		if (bu->getFaction() == FACTION_PLAYER && !bu->isOut())
		{
			if (Position::distance2dSq(tile->getPosition(), bu->getPosition()) <= bu->getMaxViewDistanceAtDarkSquared())
			{
				return tile->getShade() > _fadeShade ? _fadeShade : tile->getShade();
			}
		}
	}

	// hybrid night vision (global)
	return std::min(+NIGHT_VISION_MAX_SHADE, tile->getShade());
}

int Map::reShadeMinimap(int maxShade) const
{
	if (_debugVisionMode > 0)
	{
		if (_debugVisionMode == 1)
		{
			return maxShade / 2;
		}
		return 0;
	}

	if (_nvColor == 0)
	{
		return maxShade;
	}

	return std::min(+NIGHT_VISION_MAX_SHADE / 2, maxShade);
}

/**
 * Handles keyboard releases on the map.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void Map::keyboardRelease(Action *action, State *state)
{
	InteractiveSurface::keyboardRelease(action, state);
	_camera->keyboardRelease(action, state);
}

/**
 * Handles mouse over events on the map.
 * @param action Pointer to an action.
 * @param state State that the action handlers belong to.
 */
void Map::mouseOver(Action *action, State *state)
{
	InteractiveSurface::mouseOver(action, state);
	_camera->mouseOver(action, state);
	// mouse comes in base-resolution coordinates, the map works in world (k times base) pixels
	_mouseX = (int)action->getAbsoluteXMouse() * _k;
	_mouseY = (int)action->getAbsoluteYMouse() * _k;
	setSelectorPosition(_mouseX, _mouseY);
}


/**
 * Sets the selector to a certain tile on the map.
 * @param mx mouse x position (world pixels).
 * @param my mouse y position (world pixels).
 */
void Map::setSelectorPosition(int mx, int my)
{
	int oldX = _selectorX, oldY = _selectorY;

	// the mouse is on the screen, the map is counted in the view (the battle view zoom)
	if (_viewWidth != getWidth() || _viewHeight != getHeight())
	{
		mx = (int)((long long)mx * _viewWidth / getWidth());
		my = (int)((long long)my * _viewHeight / getHeight());
	}
	_camera->convertScreenToMap(mx, my + _spriteHeight/4, &_selectorX, &_selectorY);

	// the aim sticks (ticket XP-000226): a tiny move of the mouse just over a tile's edge keeps the old tile,
	// it changes only once the mouse is STICK base pixels inside the new one
	if (oldX != _selectorX || oldY != _selectorY)
	{
		const int STICK = 2;
		const int d = STICK * _k;
		const int around[4][2] = { { d, 0 }, { -d, 0 }, { 0, d }, { 0, -d } };
		for (const auto &a : around)
		{
			int x, y;
			_camera->convertScreenToMap(mx + a[0], my + a[1] + _spriteHeight/4, &x, &y);
			if (x == oldX && y == oldY)
			{
				_selectorX = oldX;
				_selectorY = oldY;
				break;
			}
		}
	}

	if (oldX != _selectorX || oldY != _selectorY)
	{
		_redraw = true;
	}
}

/**
 * Handles animating tiles. 8 Frames per animation.
 * @param redraw Redraw the battlescape?
 */
void Map::animate(bool redraw)
{
	if (_hdTestFrozen)
	{
		// HD render test: nothing moves until the frozen frame has been drawn
		return;
	}

	_save->nextAnimFrame();
	_animFrame = _save->getAnimFrame();

	if (AiProbe::fast())
	{
		// nobody watches: only UFO doors keep their frames going - a door is open once its animation
		// reaches frame 7 (Tile::openDoor), so that is mechanics, everything else here is the picture
		for (int i = 0; i < _save->getMapSizeXYZ(); ++i)
		{
			Tile *t = _save->getTile(i);
			if (t->isUfoDoor(O_FLOOR) || t->isUfoDoor(O_WESTWALL) || t->isUfoDoor(O_NORTHWALL) || t->isUfoDoor(O_OBJECT))
			{
				t->animate();
			}
		}
		return;
	}

	// units hanging with no floor below fade their sway in, landed ones fade it out (hoverBob); mode 0 draws them still, as the classic game
	if (Options::oxceHdHoverBob && _canvas->getHdMode() != HD_MODE_NEAREST)
	{
		for (const auto* bu : *_save->getUnits())
		{
			const bool hanging = bu->isFloating() && !bu->isOut() && bu->getStatus() != STATUS_COLLAPSING;
			auto it = _hoverFade.find(bu->getId());
			if (hanging)
			{
				if (it == _hoverFade.end())
					_hoverFade[bu->getId()] = 1;
				else if (it->second < HOVER_FADE_STEPS)
					++it->second;
			}
			else if (it != _hoverFade.end() && --it->second <= 0)
			{
				_hoverFade.erase(it);
			}
		}
	}
	else
	{
		_hoverFade.clear();
	}

	// random ambient sounds
	{
		if (!_save->getAmbienceRandom().empty())
		{
			_save->decreaseCurrentAmbienceDelay();
			if (_save->getCurrentAmbienceDelay() <= 0)
			{
				_save->resetCurrentAmbienceDelay();
				_save->playRandomAmbientSound();
			}
		}
	}

	// animate tiles
	for (int i = 0; i < _save->getMapSizeXYZ(); ++i)
	{
		_save->getTile(i)->animate();
	}

	// animate vapor
	for (auto i : Collections::rangeValueLess(_vaporParticles.size()))
	{
		auto& v = _vaporParticles[i];
		int posX = i % _camera->getMapSizeX();
		int posY = i / _camera->getMapSizeX();

		Collections::removeIf(
			v,
			[&](Particle& p)
			{
				if (p.animate())
				{
					Position tileOffset = p.updateScreenPosition();
					if (tileOffset != Position(0,0,0))
					{
						addVaporParticle(Position(posX,posY,0) + tileOffset, p);
						return true;
					}
					return false;
				}
				else
				{
					return true;
				}
			}
		);
	}

	// init vapor vector
	for (auto i : Collections::rangeValueLess(_vaporParticlesInit.size()))
	{
		auto& vi = _vaporParticlesInit[i];
		auto& vDest = _vaporParticles[i];
		if (vi.empty())
		{
			continue;
		}

		if (vDest.empty())
		{
			vi.swap(vDest);
		}
		else
		{
			vDest.insert(std::begin(vDest), std::begin(vi), std::end(vi));
		}


		Collections::removeAll(vi);
	}

	for (auto& tilePar : _vaporParticles)
	{
		if (tilePar.empty())
		{
			Collections::removeAll(tilePar);
		}
		else
		{
			std::sort(std::begin(tilePar), std::end(tilePar), [](const Particle& a, const Particle& b){ return a.getLayerZ() < b.getLayerZ(); });
		}
	}

	// animate certain units (large flying units have a propulsion animation)
	for (auto* bu : *_save->getUnits())
	{
		const Position pos = bu->getPosition();

		// skip units that do not have position
		if (pos == TileEngine::invalid)
		{
			continue;
		}

		if (_save->getDepth() > 0)
		{
			bu->setFloorAbove(false);

			// make sure this unit isn't obscured by the floor above him, otherwise it looks weird.
			if (_camera->getViewLevel() > pos.z)
			{
				for (int z = std::min(_camera->getViewLevel(), _save->getMapSizeZ() - 1); z != pos.z; --z)
				{
					if (!_save->getTile(Position(pos.x, pos.y, z))->hasNoFloor(0))
					{
						bu->setFloorAbove(true);
						break;
					}
				}
			}
		}

		bu->breathe();
	}

	if (redraw) _redraw = true;
	// gentle mode: the reaction arrows go away on the picture clock, also while the battle is busy
	if (!_gentleShots.empty()) _redraw = true;
}

/**
 * Draws the rectangle selector.
 * @param pos Pointer to a position.
 */
void Map::getSelectorPosition(Position *pos) const
{
	pos->x = _selectorX;
	pos->y = _selectorY;
	pos->z = _camera->getViewLevel();
}

/**
 * Calculates the offset of a soldier, when it is walking in the middle of 2 tiles.
 * @param unit Pointer to BattleUnit.
 * @param offset Pointer to the offset to return the calculation.
 */
UnitWalkingOffset Map::calculateWalkingOffset(const BattleUnit *unit) const
{
	UnitWalkingOffset result = { };

	int offsetX[8] = { 1, 1, 1, 0, -1, -1, -1, 0 };
	int offsetY[8] = { 1, 0, -1, -1, -1, 0, 1, 1 };
	int phase = unit->getWalkingPhase() + unit->getDiagonalWalkingPhase();
	int dir = unit->getMoveDirection(); // the step's, not the hull's (a unit backing up)
	int midphase = 4 + 4 * (dir % 2);
	int endphase = 8 + 8 * (dir % 2);
	int size = unit->getArmor()->getSize();

	result.ScreenOffset.x = 0;
	result.ScreenOffset.y = 0;

	if (size > 1)
	{
		if (dir < 1 || dir > 5)
			midphase = endphase;
		else if (dir == 5)
			midphase = 12;
		else if (dir == 1)
			midphase = 5;
		else
			midphase = 1;
	}
	if (unit->getVerticalDirection())
	{
		midphase = 4;
		endphase = 8;
	}
	else if ((unit->getStatus() == STATUS_WALKING || unit->getStatus() == STATUS_FLYING))
	{
		// the phases are the game's (when the unit changes tiles); the step on the screen is the view's (HD lab)
		const int screenDir = turnedDir(dir);
		if (phase < midphase)
		{
			result.ScreenOffset.x = phase * 2 * offsetX[screenDir] * _k;
			result.ScreenOffset.y = - phase * offsetY[screenDir] * _k;
		}
		else
		{
			result.ScreenOffset.x = (phase - endphase) * 2 * offsetX[screenDir] * _k;
			result.ScreenOffset.y = - (phase - endphase) * offsetY[screenDir] * _k;
		}
	}

	result.NormalizedMovePhase = endphase == 16 ? phase : phase * 2;

	// If we are walking in between tiles, interpolate it's terrain level.
	if (unit->getStatus() == STATUS_WALKING || unit->getStatus() == STATUS_FLYING)
	{
		const Position posCurr = unit->getPosition();
		const Position posDest = unit->getDestination();
		const Position posLast = unit->getLastPosition();
		if (phase < midphase)
		{
			int fromLevel = getTerrainLevel(posCurr, size);
			int toLevel = getTerrainLevel(posDest, size);
			if (posCurr.z > posDest.z)
			{
				// going down a level, so toLevel 0 becomes +24, -8 becomes  16
				toLevel += Position::TileZ*(posCurr.z - posDest.z);
			}
			else if (posCurr.z < posDest.z)
			{
				// going up a level, so toLevel 0 becomes -24, -8 becomes -16
				toLevel = -Position::TileZ*(posDest.z - posCurr.z) + abs(toLevel);
			}
			result.TerrainLevelOffset = Interpolate(fromLevel, toLevel, phase, endphase);
		}
		else
		{
			// from phase 4 onwards the unit behind the scenes already is on the destination tile
			// we have to get it's last position to calculate the correct offset
			int fromLevel = getTerrainLevel(posLast, size);
			int toLevel = getTerrainLevel(posDest, size);
			if (posLast.z > posDest.z)
			{
				// going down a level, so fromLevel 0 becomes -24, -8 becomes -32
				fromLevel -= Position::TileZ*(posLast.z - posDest.z);
			}
			else if (posLast.z < posDest.z)
			{
				// going up a level, so fromLevel 0 becomes +24, -8 becomes 16
				fromLevel = Position::TileZ*(posDest.z - posLast.z) - abs(fromLevel);
			}
			result.TerrainLevelOffset = Interpolate(fromLevel, toLevel, phase, endphase);
		}
	}
	else
	{
		result.TerrainLevelOffset = getTerrainLevel(unit->getPosition(), size);
	}
	result.ScreenOffset.y += result.TerrainLevelOffset * _k; // voxels to world pixels
	result.ScreenOffset += hoverBob(unit);
	return result;
}

/**
 * The sway of a unit hanging with no floor below. Drawing only: the unit's position, voxels and
 * line of fire stay where they are. In the air it is a quick shallow hover, in the water
 * (a battle with depth) a slow deep sway with a drift to the side. Each unit has its own phase,
 * so a flock does not bob in step. Measured in world pixels, so at k > 1 it moves by HD pixels.
 * @param unit The unit.
 * @return The offset to add on screen, zero for a unit standing on a floor.
 */
Position Map::hoverBob(const BattleUnit *unit) const
{
	auto it = _hoverFade.find(unit->getId());
	if (it == _hoverFade.end())
	{
		return Position();
	}
	constexpr double Tau = 6.283185307179586;
	const bool water = _save->getDepth() != 0;
	// periods in ticks divide the wrap of the animation frame (705600), so the sway never jumps
	const double period = water ? 24.0 : 8.0;
	const double amplitude = (water ? 2.0 : 1.0) * _k * it->second / HOVER_FADE_STEPS;
	const double t = _animFrame + unit->getId() * 7;
	Position offset;
	offset.y = (int)std::lround(amplitude * std::sin(Tau * t / period));
	if (water)
	{
		offset.x = (int)std::lround(1.0 * _k * it->second / HOVER_FADE_STEPS * std::sin(Tau * t / 48.0));
	}
	return offset;
}


/**
  * Terrainlevel goes from 0 to -24. For a larger sized unit, we need to pick the highest terrain level, which is the lowest number...
  * @param pos Position.
  * @param size Size of the unit we want to get the level from.
  * @return terrainlevel.
  */
int Map::getTerrainLevel(const Position& pos, int size) const
{
	int lowestlevel = 0;

	for (int x = 0; x < size; x++)
	{
		for (int y = 0; y < size; y++)
		{
			int l = _save->getTile(pos + Position(x,y,0))->getTerrainLevel();
			if (l < lowestlevel)
				lowestlevel = l;
		}
	}

	return lowestlevel;
}

/**
 * Sets the 3D cursor to selection/aim mode.
 * @param type Cursor type.
 * @param size Size of cursor.
 */
void Map::setCursorType(CursorType type, int size)
{
	// reset cursor indicator cache
	_cacheActiveWeaponUfopediaArticleUnlocked = -1;
	_cacheIsCtrlPressed = false;
	_cacheCursorPosition = TileEngine::invalid;
	_cacheHasLOS = -1;

	_cursorType = type;
	if (_cursorType == CT_NORMAL)
		_cursorSize = size;
	else
		_cursorSize = 1;
}

/**
 * Gets the cursor type.
 * @return cursor type.
 */
CursorType Map::getCursorType() const
{
	return _cursorType;
}

/**
 * Puts a projectile sprite on the map.
 * @param projectile Projectile to place.
 */
void Map::setProjectile(Projectile *projectile)
{
	_projectile = projectile;
	if (projectile && HdGentle::smoothCamera())
	{
		_launch = true;
	}
	_gentleFlying = 0;
	if (projectile && HdGentle::on())
	{
		noteGentleShot(projectile);
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
 * Gets the current projectile sprite on the map.
 * @return Projectile or 0 if there is no projectile sprite on the map.
 */
Projectile *Map::getProjectile() const
{
	return _projectile;
}

/**
 * Add new vapor particle.
 * @param pos Tile position of particle.
 * @param particle Particle to add.
 */
void Map::addVaporParticle(Position pos, Particle particle)
{
	if ((int)(_transparencies->size()) < (particle.getColor() + 1) * Mod::TransparenciesOpacityLevels * Mod::TransparenciesPaletteColors)
	{
		return;
	}
	if (pos.x >= _camera->getMapSizeX() || pos.y >= _camera->getMapSizeY())
	{
		return;
	}
	if (pos.x < 0 || pos.y < 0)
	{
		return;
	}

	auto& v = _vaporParticlesInit[_camera->getMapSizeX() * pos.y + pos.x];

	// as there will usually be more than one Particle, we prepare more space
	if (v.capacity() < 64)
	{
		v.reserve(64);
	}

	v.push_back(particle);
}

/**
 * Get all vapor for tile.
 * @param tile current tile.
 * @param topLayer if tile is top visible layer, if true then will return particles belongs to upper tiles.
 * @return range of particles that should be drawn.
 */
Collections::Range<const Particle*> Map::getVaporParticle(const Tile* tile, int topLayer) const
{
	Position pos = tile->getPosition();
	auto& v = _vaporParticles[_camera->getMapSizeX() * pos.y + pos.x];
	int startZ = pos.z * Particle::LayerAccuracy + (topLayer & 1);
	int endZ = startZ + Particle::LayerAccuracy / 2;
	auto* s = std::partition_point(v.data(), v.data() + v.size(), [&](const Particle& a){ return a.getLayerZ() < startZ; });
	auto* e = (topLayer & 2) ? v.data() + v.size() : std::partition_point(s, v.data() + v.size(), [&](const Particle& a){ return a.getLayerZ() < endZ; });
	return Collections::Range{ s, e };
}

/**
 * Gets a list of explosion sprites on the map.
 * @return A list of explosion sprites.
 */
std::list<Explosion*> *Map::getExplosions()
{
	return &_explosions;
}

/**
 * Hands the explosion sprites over to the loose hits (Options::oxceHdLooseHits): no battle state waits
 * for them, think plays them on at their own frame time. The fast bench draws nothing, there they just go.
 * @param frameMs Time of one frame, ms.
 */
void Map::loosenExplosions(int frameMs)
{
	const Uint32 now = SDL_GetTicks();
	for (auto *explosion : _explosions)
	{
		if (AiProbe::fast())
		{
			delete explosion;
		}
		else
		{
			// the frame shown now has had its time while the battle state waited a step: the next one is due
			_looseHits.push_back({ explosion, (Uint32)frameMs, now });
		}
	}
	_explosions.clear();
}

/**
 * Gets the pointer to the camera.
 * @return Pointer to camera.
 */
Camera *Map::getCamera()
{
	return _camera;
}

/**
 * Shakes the drawn map: a stronger or longer shake already going on is kept. Picture only - the camera
 * itself does not move, nothing of the battle reads it.
 * @param amp The largest offset, screen pixels.
 * @param ms How long, ms of the picture clock.
 */
void Map::shake(int amp, Uint32 ms)
{
	const Uint32 now = SDL_GetTicks();
	const Uint32 left = _shakeMs && now - _shakeStart < _shakeMs ? _shakeMs - (now - _shakeStart) : 0;
	if (amp <= 0 || (left >= ms && _shakeAmp >= amp))
		return;
	_shakeStart = now;
	_shakeMs = std::max(ms, left);
	_shakeAmp = std::max(amp, left ? _shakeAmp : 0);
	_redraw = true;
}

/**
 * The offset of the shake now: a jolt every 40 ms by a fixed pattern (no random numbers), fading out to the end.
 */
Position Map::shakeOffset(Uint32 now) const
{
	if (!_shakeMs || now - _shakeStart > _shakeMs)
		return Position(0, 0, 0);
	static const int JOLTS[8][2] = { { 1, 0 }, { -1, 1 }, { 0, -1 }, { 1, 1 }, { -1, 0 }, { 0, 1 }, { 1, -1 }, { -1, -1 } };
	const Uint32 t = now - _shakeStart;
	const int amp = (int)std::lround(_shakeAmp * (double)(_shakeMs - t) / _shakeMs);
	const int *j = JOLTS[(t / 40) % 8];
	return Position(j[0] * amp, j[1] * amp, 0);
}

/**
 * Timers only work on surfaces so we have to pass this on to the camera object.
 */
void Map::scrollMouse()
{
	_camera->scrollMouse();
}

/**
 * Timers only work on surfaces so we have to pass this on to the camera object.
 */
void Map::scrollKey()
{
	_camera->scrollKey();
}

/**
 * Modify the fade shade level if fade's in progress.
 */
void Map::fadeShade()
{
	bool hold = SDL_GetKeyState(NULL)[Options::keyNightVisionHold];
	if ((_nightVisionOn && !hold) || (!_nightVisionOn && hold))
	{
		_nvColor = Options::oxceNightVisionColor;
		_save->setToggleNightVisionTemp(true);
		_save->setToggleNightVisionColorTemp(_nvColor);
		if (_fadeShade > NIGHT_VISION_SHADE) // 0 = max brightness
		{
			--_fadeShade;
		}
	}
	else
	{
		if (_nvColor != 0)
		{
			if (_fadeShade < _save->getGlobalShade())
			{
				// gradually fade away
				++_fadeShade;
			}
			else
			{
				// and at the end turn off night vision
				_nvColor = 0;
				_save->setToggleNightVisionTemp(false);
				_save->setToggleNightVisionColorTemp(0);
			}
		}
	}
}

/**
 * Gets a list of waypoints on the map.
 * @return A list of waypoints.
 */
std::vector<Position> *Map::getWaypoints()
{
	return &_waypoints;
}

/**
 * Sets mouse-buttons' pressed state.
 * @param button Index of the button.
 * @param pressed The state of the button.
 */
void Map::setButtonsPressed(Uint8 button, bool pressed)
{
	setButtonPressed(button, pressed);
}

/**
 * Sets the unitDying flag.
 * @param flag True if the unit is dying.
 */
void Map::setUnitDying(bool flag)
{
	_unitDying = flag;
}

/**
 * Updates the selector to the last-known mouse position.
 */
void Map::refreshSelectorPosition()
{
	setSelectorPosition(_mouseX, _mouseY);
}

/**
 * Special handling for setting the height of the map viewport.
 * @param height the new base screen height.
 */
void Map::setHeight(int height)
{
	Surface::setHeight(height * _k);
	const int visibleBase = height - _iconHeight;
	_visibleBase = visibleBase;
	createCanvas(); // the view's visible height (_visibleMapHeight) with it
	_message->setHeight((visibleBase < 200)? visibleBase : 200);
	_message->setY((visibleBase - _message->getHeight()) / 2);
}

/**
 * Special handling for setting the width of the map viewport.
 * @param width the new base screen width.
 */
void Map::setWidth(int width)
{
	int dX = width - getWidth() / _k;
	Surface::setWidth(width * _k);
	createCanvas();
	_message->setX(_message->getX() + dX / 2);
}

/**
 * Get the hidden movement screen's vertical position.
 * @return the vertical position of the hidden movement window.
 */
int Map::getMessageY() const
{
	return _message->getY();
}

/**
 * Get the icon height.
 */
int Map::getIconHeight() const
{
	return _iconHeight;
}

/**
 * Get the icon width.
 */
int Map::getIconWidth() const
{
	return _iconWidth;
}

/**
 * Returns the angle(left/right balance) of a sound effect,
 * based off a map position.
 * @param pos the map position to calculate the sound angle from.
 * @return the angle of the sound (280 to 440).
 */
int Map::getSoundAngle(const Position& pos) const
{
	int midPoint = _viewWidth / 2;
	Position relativePosition;

	_camera->convertMapToScreen(pos, &relativePosition);
	// cap the position to the screen edges relative to the center,
	// negative values indicating a left-shift, and positive values shifting to the right.
	relativePosition.x = Clamp((relativePosition.x + _camera->getMapOffset().x) - midPoint, -midPoint, midPoint);

	// convert the relative distance to a relative increment of an 80 degree angle
	// we use +- 80 instead of +- 90, so as not to go ALL the way left or right
	// which would effectively mute the sound out of one speaker.
	// since Mix_SetPosition uses modulo 360, we can't feed it a negative number, so add 360 instead.
	return 360 + (relativePosition.x / (midPoint / 80.0));
}

/**
 * Reset the camera smoothing bool.
 */
void Map::resetCameraSmoothing()
{
	_smoothingEngaged = false;
}

/**
 * Set the "explosion flash" bool.
 * @param flash should the screen be rendered in EGA this frame?
 */
void Map::setBlastFlash(bool flash)
{
	_flashScreen = flash;

	// Meridian: no frikin flashing!!
	_flashScreen = false;
}

/**
 * Checks if the screen is still being rendered in EGA.
 * @return if we are still in EGA mode.
 */
bool Map::getBlastFlash() const
{
	return _flashScreen;
}

/**
 * Resets obstacle markers.
 */
void Map::resetObstacles(void)
{
	for (int z = 0; z < _save->getMapSizeZ(); z++)
		for (int y = 0; y < _save->getMapSizeY(); y++)
			for (int x = 0; x < _save->getMapSizeX(); x++)
			{
				Tile *tile = _save->getTile(Position(x, y, z));
				if (tile) tile->resetObstacle();
			}
	_showObstacles = false;
}

/**
 * Enables obstacle markers.
 */
void Map::enableObstacles(void)
{
	_showObstacles = true;
	if (_obstacleTimer)
	{
		_obstacleTimer->stop();
		_obstacleTimer->start();
	}
}

/**
 * Disables obstacle markers.
 */
void Map::disableObstacles(void)
{
	_showObstacles = false;
	if (_obstacleTimer)
	{
		_obstacleTimer->stop();
	}
}

}
