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

/// XP-000572: a floor of the sea - animated, no one can walk or fly over it
bool hdSeaFloor(const MapData *data)
{
	return data && data->getObjectType() == O_FLOOR && data->getTUCost(MT_WALK) == 255 && data->getTUCost(MT_FLY) == 255
		&& data->getSprite(0) != data->getSprite(1);
}

/// XP-000572: open water - a sea floor with nothing on it
bool hdOpenSea(const Tile *tile)
{
	return tile && hdSeaFloor(tile->getMapData(O_FLOOR))
		&& !tile->getMapData(O_WESTWALL) && !tile->getMapData(O_NORTHWALL) && !tile->getMapData(O_OBJECT);
}

/// XP-000572: the first floor above this cell is open water - the cell is under the sea
bool hdUnderSea(SavedBattleGame *save, const Position &pos)
{
	for (int z = pos.z + 1; z < save->getMapSizeZ(); ++z)
	{
		const Tile *t = save->getTile(Position(pos.x, pos.y, z));
		if (t && t->getMapData(O_FLOOR))
			return hdOpenSea(t);
	}
	return false;
}

int getArrowBobForFrame(int frame, int scale)
{
	return ArrowBobOffsets[frame % 8] * scale;
}

/**
 * HD render (Options::oxceHdClassicShots): works out the classic shot of this frame - the pieces of the shot in flight and the tiles they stand in.
 * @param classicShot The shot (not active when this frame has none).
 * @param turned The view is turned (HD lab).
 * @param hdFrames The canvas draws HD frames.
 */
void Map::hdFindClassicShot(HdClassicShot &classicShot, bool turned, bool hdFrames)
{
	if (Options::oxceHdClassicShots && _projectile && !_projectile->getItem() && _projectileInFOV && _explosions.empty() &&
		_projectileSet && _k > 1 && hdFrames && _projectile->getParticle(0) != Mod::NO_SURFACE)
	{
		HdShots::newFrame();
		const HdShots::Kind kind = HdShots::kindOf(_projectile->getWeaponRules());
		if (kind)
		{
			const HdShots::Colours &colours = HdShots::coloursOf(_projectileSet, _projectile->getParticle(0), getPalette());
			if (colours.valid)
			{
				classicShot.active = true;
				const int flown = _projectile->getFlown();
				// the way on the screen: its direction and how many pixels a step of it is
				const int ref = std::min(flown + 1, 48);
				Position tail;
				_camera->convertVoxelToScreen(_projectile->getPosition(1), &classicShot.head);
				_camera->convertVoxelToScreen(_projectile->getPosition(1 - ref), &tail);
				const double vx = classicShot.head.x - tail.x, vy = classicShot.head.y - tail.y;
				const double len = std::sqrt(vx * vx + vy * vy);
				if (flown > 0 && len >= 2.0)
				{
					const double perStep = len / ref;
					const int angle = (int)std::lround(std::atan2(vy, vx) / (2 * 3.14159265358979323846) * HdShots::ANGLES);
					int pieces = 0;
					if (kind.cls == HdShots::LASER)
					{
						// as long as the jump of a frame, or the beam's own length: no gap between two frames, no blinking (XP-000310)
						const int steps = std::max(HdShots::laserNominalVoxels(kind.size), _projectile->getSpeed());
						pieces = HdShots::laserPieces((int)std::ceil(steps * perStep), _k);
					}
					classicShot.shot = HdShots::shot(kind, colours, _k, angle, pieces);
					if (classicShot.shot)
					{
						const int count = (int)classicShot.shot->pieces.size();
						classicShot.back.assign(count, -1);
						const double seg = HdShots::pieceLength(_k);
						for (int j = 0; j < count; ++j)
						{
							const int back = (int)std::lround((j + 0.5) * seg / perStep);
							if (back > flown + 1)
							{
								continue;           // before the muzzle
							}
							classicShot.back[j] = back;
							const Position bp = _projectile->getPosition(1 - back);
							classicShot.lowX = std::min(classicShot.lowX, (int)bp.x);
							classicShot.lowY = std::min(classicShot.lowY, (int)bp.y);
							classicShot.highX = std::max(classicShot.highX, (int)bp.x);
							classicShot.highY = std::max(classicShot.highY, (int)bp.y);
						}
						classicShot.lowX /= 16; classicShot.lowY /= 16; classicShot.highX /= 16; classicShot.highY /= 16;
						if (turned)
						{
							const Position a = _camera->worldToView(Position(classicShot.lowX, classicShot.lowY, 0));
							const Position b = _camera->worldToView(Position(classicShot.highX, classicShot.highY, 0));
							classicShot.lowX = std::min(a.x, b.x);
							classicShot.highX = std::max(a.x, b.x);
							classicShot.lowY = std::min(a.y, b.y);
							classicShot.highY = std::max(a.y, b.y);
						}
					}
				}
			}
		}
	}
}

/**
 * XP-000572: looks for the open sea of the map - the level of the water, the tiles the sea beyond the edge is drawn with, the edge's cells it goes on from (XP-000591).
 * Once a battle (_hdSeaZ == -2: not looked for yet).
 */
void Map::hdFindSea()
{
	_hdSeaZ = -1;
	_hdSeaTiles.clear();
	std::vector<int> perZ(_save->getMapSizeZ(), 0);
	std::unordered_map<const MapData*, std::pair<int, Tile*>> kinds;
	for (int i = 0; i < _save->getMapSizeXYZ(); ++i)
	{
		Tile *t = _save->getTile(i);
		if (hdOpenSea(t))
		{
			++perZ[t->getPosition().z];
			auto &k = kinds[t->getMapData(O_FLOOR)];
			if (!k.second)
				k.second = t;
			++k.first;
		}
	}
	for (int z = 0; z < (int)perZ.size(); ++z)
		if (perZ[z] >= 50 && (_hdSeaZ < 0 || perZ[z] > perZ[_hdSeaZ]))
			_hdSeaZ = z;
	std::vector<std::pair<int, Tile*>> order;
	for (auto &k : kinds)
		if (k.second.second->getPosition().z == _hdSeaZ)
			order.push_back(k.second);
	std::sort(order.begin(), order.end(), [](const std::pair<int, Tile*> &a, const std::pair<int, Tile*> &b) { return a.first > b.first; });
	for (size_t i = 0; i < order.size() && i < 8; ++i)
		_hdSeaTiles.push_back(order[i].second);
	// XP-000591: the sea goes on only beyond the edge's cells that are the sea (a harbour has it on one side, a ship all
	// round): an edge cell counts when open sea is within 2 cells of it, so a pier or a boat at the edge leaves no gap
	const int sizeX = _save->getMapSizeX(), sizeY = _save->getMapSizeY();
	_hdSeaEdge.assign((size_t)sizeX * sizeY, 0);
	for (int y = 0; _hdSeaZ >= 0 && y < sizeY; ++y)
	{
		for (int x = 0; x < sizeX; ++x)
		{
			if (x > 2 && x < sizeX - 3 && y > 2 && y < sizeY - 3)
				continue;
			for (int ny = std::max(0, y - 2); ny <= std::min(sizeY - 1, y + 2) && !_hdSeaEdge[(size_t)y * sizeX + x]; ++ny)
				for (int nx = std::max(0, x - 2); nx <= std::min(sizeX - 1, x + 2); ++nx)
					if (hdOpenSea(_save->getTile(Position(nx, ny, _hdSeaZ))))
					{
						_hdSeaEdge[(size_t)y * sizeX + x] = 1;
						break;
					}
		}
	}
}

/**
 * XP-000572: the sea beyond the map's edge on the water's level. The sea behind the map goes under the water's level, before it is drawn; the sea
 * before the map after it - the side of a wave picture under its diamond is black, and the next row of the sea covers it (the map's ring of water too).
 * @param surface The canvas.
 * @param cameraPos The camera's offset on the canvas.
 * @param itZ The level of the water.
 * @param front The part before the map (else the part behind it).
 */
void Map::hdDrawSea(HdCanvas *surface, const Position &cameraPos, int itZ, bool front)
{
	const int sizeX = _save->getMapSizeX(), sizeY = _save->getMapSizeY(), R = 48;
	// the sea of SEAURBAN is one picture cut into 3x3 cells (0..8 of the set): the map lays them by (y % 3, x % 3)
	static const int PIECE[3][3] = { { 0, 2, 5 }, { 1, 4, 7 }, { 3, 6, 8 } };
	Tile *rep0 = _hdSeaTiles[0];
	const MapData *repData = rep0->getMapData(O_FLOOR);
	if (!repData)
		return;
	MapDataSet *seaSet = repData->getDataset();
	SurfaceSet *seaFrames = seaSet ? seaSet->getSurfaceset() : nullptr;
	int seaFrame = 0;
	if (seaFrames)
	{
		const void *cur = rep0->getSprite(O_FLOOR).getBuffer();
		for (int f = 0; f < 8; ++f)
		{
			if (SurfaceRaw<const Uint8>(seaFrames->getFrame(repData->getSprite(f))).getBuffer() == cur)
			{
				seaFrame = f;
				break;
			}
		}
	}
	bool seaPieces = seaFrames && seaSet->getSize() >= 9;
	for (int i = 0; seaPieces && i < 9; ++i)
		seaPieces = hdSeaFloor(seaSet->getObject(i)); // the set's first nine are the sea's 3x3 cells, else one picture everywhere
	for (int y = -R; y < sizeY + R; ++y)
	{
		for (int x = -R; x < sizeX + R; ++x)
		{
			if ((x >= 0 && x < sizeX && y >= 0 && y < sizeY) || (x >= sizeX || y >= sizeY) != front)
				continue;
			// the edge's cell the sea goes on from (XP-000591): the nearest one, past a corner the corner's
			const int ex = std::max(0, std::min(sizeX - 1, x)), ey = std::max(0, std::min(sizeY - 1, y));
			if (!_hdSeaEdge[(size_t)ey * sizeX + ex])
				continue;
			Position screen;
			_camera->convertMapToScreen(Position(x, y, itZ), &screen);
			screen += cameraPos;
			if (screen.x <= -_spriteWidth || screen.x >= surface->getWidth() + _spriteWidth ||
				screen.y <= -_spriteHeight || screen.y >= surface->getHeight() + _spriteHeight)
				continue;
			SurfaceRaw<const Uint8> sprite = rep0->getSprite(O_FLOOR);
			if (seaPieces)
			{
				const MapData *piece = seaSet->getObject(PIECE[((y % 3) + 3) % 3][((x % 3) + 3) % 3]);
				sprite = SurfaceRaw<const Uint8>(seaFrames->getFrame(piece->getSprite(seaFrame)));
			}
			if (sprite)
				surface->blit(sprite, screen.x, screen.y, reShade(rep0), false, _nvColor);
		}
	}
}

/**
 * The path preview over the map: the arrows of the steps and the numbers of time units and energy left.
 * @param surface The canvas.
 * @param _numWaypid The number drawn on the steps (made by drawTerrain for this frame).
 * @param beginX, endX, beginY, endY, beginZ, endZ The cells of the view that are drawn.
 * @param turned The view is turned (HD lab).
 */
void Map::drawPathPreview(HdCanvas *surface, NumberText *_numWaypid, int beginX, int endX, int beginY, int endY, int beginZ, int endZ, bool turned)
{
	Position mapPosition, screenPosition;
	Tile *tile;
	SurfaceRaw<const Uint8> tmpSurface;
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

/**
 * The arrow over the selected unit.
 * @param surface The canvas.
 */
void Map::drawSelectedArrow(HdCanvas *surface)
{
	Position screenPosition;
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
}

/**
 * The numbers above the units the selected unit sees.
 * @param surface The canvas.
 */
void Map::drawUnitMarkers(HdCanvas *surface)
{
	Position screenPosition;
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
}

/**
 * The arrows over the units found by the motion scanner and over the player's units with a marker (Alt held).
 * @param surface The canvas.
 */
void Map::drawScannerArrows(HdCanvas *surface)
{
	Position screenPosition;
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
}

/**
 * The arrows over the craft's tiles in the deployment preview (Alt held).
 * @param surface The canvas.
 */
void Map::drawDeployArrows(HdCanvas *surface)
{
	Position screenPosition;
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
}

/**
 * The explosions and hits in view: the screen's flash of a big one, the HD clips of the combat effects or the classic frames.
 * @param surface The canvas.
 */
void Map::drawExplosions(HdCanvas *surface)
{
	Position bulletPositionScreen;
	SurfaceRaw<const Uint8> tmpSurface;
	std::vector<std::pair<const Explosion*, int>> cloudHits;

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
				// XP-000533: under water (depth > 0) no HD blood: the hit on flesh keeps the classic animation, no spray flies on
				const bool hdBloodless = _save->getDepth() > 0;
				if (hdBloodless && Options::oxceHdBloodCloud && Options::oxceHdFx && _k > 1 && surface->getHdMode() != HD_MODE_NEAREST
					&& explosion->getCurrentFrame() >= 0 && HdFx::isBloodClip(explosion->getHdFx()))
				{
					hdNoteBloodCloud(explosion, cloudHits);
				}
				if (Options::oxceHdFx && surface->getHdMode() != HD_MODE_NEAREST && !explosion->getHdFx().empty()
					&& !(hdBloodless && HdFx::isBloodClip(explosion->getHdFx())))
				{
					if (explosion->getCurrentFrame() < 0)
					{
						continue;
					}
					const char *setName = explosion->isBig() ? "X1.PCK" : explosion->isHit() ? "HIT.PCK" : "SMOKE.PCK";
					std::string clip = HdFx::colour(explosion->getHdFx(), _game->getMod()->getSurfaceSet(setName)->getFrame(explosion->getStartFrame()), getPalette());
					const int clipStep = explosion->getCurrentFrame() - explosion->getStartFrame();
					const HdFrame *hd = nullptr, *stabHd = nullptr;
					if (Options::oxceHdBloodSpray && explosion->getHdLoss() > 0 && !hdBloodless)
					{
						// XP-000298: the blood of a bullet that took health flies on along its way (the bullet's way on the screen,
						// from a voxel back to the hit); a mod without these clips keeps the hit's own blood
						Position from;
						_camera->convertVoxelToScreen(explosion->getHdFrom(), &from);
						const int wayX = bulletPositionScreen.x - from.x, wayY = bulletPositionScreen.y - from.y;
						if (std::abs(wayX) + std::abs(wayY) >= _k)
						{
							const std::string spray = HdFx::sprayClip(clip, wayX, wayY, explosion->getHdLoss(), explosion->getHdSeed());
							if (!spray.empty() && (hd = HdFx::frame(HdFx::tinted(spray, explosion->getHdBlood()), clipStep, explosion->getFrameCount(), _k)))
							{
								clip = spray;
							}
							else
							{
								// a blow in melee: the blood goes over the swing, from the attacker's side
								const std::string stab = HdFx::stabClip(explosion->getHdFx(), wayX, wayY, explosion->getHdLoss(), explosion->getHdSeed());
								if (!stab.empty())
								{
									stabHd = HdFx::frame(HdFx::tinted(stab, explosion->getHdBlood()), clipStep, explosion->getFrameCount(), _k);
								}
							}
						}
					}
					if (hd || (hd = HdFx::frame(HdFx::tinted(clip, explosion->getHdBlood()), clipStep, explosion->getFrameCount(), _k)))
					{
						surface->blitFrame(*hd, bulletPositionScreen.x - hd->width / 2, bulletPositionScreen.y - hd->height / 2);
						if (stabHd)
						{
							surface->blitFrame(*stabHd, bulletPositionScreen.x - stabHd->width / 2, bulletPositionScreen.y - stabHd->height / 2);
						}
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
			_hdCloudSeen.swap(cloudHits);
		}
	}
	else
	{
		_hdCloudSeen.clear();
	}
}

/**
 * HD render: the muzzle flashes, on their own clock (see hdMuzzle).
 * @param surface The canvas.
 */
void Map::drawMuzzleFlashes(HdCanvas *surface)
{
	Position bulletPositionScreen;
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
}

}
