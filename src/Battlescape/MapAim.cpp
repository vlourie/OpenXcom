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

}
