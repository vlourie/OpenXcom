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
#include "UnitSprite.h"
#include "ItemSprite.h"
#include "Pathfinding.h"
#include "TileEngine.h"
#include "Projectile.h"
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
#include "../Engine/HdUi.h"
#include <chrono>
#include <cmath>
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
	_k(hdScale(game)), _messageScratch(0), _messageOnCanvas(false), _canvas(0), _hdGroundVariants(Options::oxceHdGroundVariants),
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
	_smoothCamera = Options::battleSmoothCamera;
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
	// shipping hd/UI/<name>.png gets a real HD icon instead of a nearest-scaled 16x16 one
	_stunIndicator = _game->getMod()->getHdSurface("FloorStunIndicator", false);
	_woundIndicator = _game->getMod()->getHdSurface("FloorWoundIndicator", false);
	_burnIndicator = _game->getMod()->getHdSurface("FloorBurnIndicator", false);
	_shockIndicator = _game->getMod()->getHdSurface("FloorShockIndicator", false);
	_anyIndicator = _stunIndicator || _woundIndicator || _burnIndicator || _shockIndicator;

	if (enviro)
	{
		if (!enviro->getMapShockIndicator().empty())
		{
			_shockIndicator = _game->getMod()->getHdSurface(enviro->getMapShockIndicator(), false);
		}
	}

	_vaporParticlesInit.resize(_camera->getMapSizeY() * _camera->getMapSizeX());
	_vaporParticles.resize(_camera->getMapSizeY() * _camera->getMapSizeX());

	// HD render: every drawing call goes through the canvas - the true-color one when the
	// display is 32-bit (the world layer takes it as is), else the classic 8-bit surface
	createCanvas();
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
	if (_game->getScreen()->isLayered())
	{
		_canvas = new Canvas32(getWidth(), getHeight(), _k);
		_canvas->setPalette(getPalette(), 0, 256);
		_canvas->setHdMode(Options::oxceHdMode);
		_canvas->setGroundSeed(groundSeed());
	}
	else
	{
		_canvas = new Canvas8(this);
	}
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
	delete _camera;
	delete _txtAccuracy;
	delete _numUnitMarker;
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
	if (HdFx::active() && _canvas->getHdMode() != HD_MODE_NEAREST)
	{
		_redraw = true;
	}
}

/**
 * Draws the whole map, part by part.
 */
void Map::draw()
{
	if (!_redraw)
	{
		return;
	}

	// normally we'd call for a Surface::draw();
	// but we don't want to clear the background with colour 0, which is transparent (aka black)
	// we use colour 15 because that actually corresponds to the colour we DO want in all variations of the xcom and tftd palettes.
	// Note: un-hardcoded the color from 15 to ruleset value, default 15
	_redraw = false;
	const auto drawStart = std::chrono::steady_clock::now();
	_canvas->fill(Palette::blockOffset(0) + _bgColor);
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
	const bool ignoreAllButAlliesHits = Options::QOL::dontTraceProjectiles == 3 || Options::QOL::dontTraceProjectiles == 4;
	const bool keepCameraOnShooter = Options::QOL::dontTraceProjectiles == 4;
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

	if ((_save->getSelectedUnit() && _save->getSelectedUnit()->getVisible())
		|| _unitDying
		|| _save->getSide() == FACTION_PLAYER
		|| _save->getDebugMode()
		|| (_projectileInFOV && (!ignoreAllButAlliesHits || (unitVisible && !unitEnemy)))
		|| (_explosionInFOV && (!ignoreAllButAlliesHits || ((unitVisible && !unitEnemy) || hitExplosion))))
	{
		drawTerrain(_canvas);
		_messageOnCanvas = false;
	}
	else
	{
		blitMessage();
		_messageOnCanvas = true;
	}
	// the true-color canvas records the frame and draws it on all cores now
	_canvas->setLight(nullptr);
	_canvas->flush();
	_lastDrawMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - drawStart).count();

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
			Tile *t = (dx == 0 && dy == 0) ? tile : _save->getTile(Position(pos.x + dx, pos.y + dy, pos.z));
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
void Map::blitMessage()
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
	_canvas->blitClassic(_messageScratch, 0, 0, _k);
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
		if (_redraw)
		{
			draw();
		}
		SDL_Surface *world = screen->getWorldSurface();
		const int k = screen->getWorldScale();
		// the canvas is already k times the base resolution (see _spriteWidth), so only its origin scales;
		// a true-color canvas copies straight into the world (rows in parallel), a palette one is converted by SDL
		if (Canvas32 *canvas32 = dynamic_cast<Canvas32*>(_canvas))
		{
			canvas32->copyTo(world, getX() * k, getY() * k);
		}
		// the message's two lines are not in the canvas when the HD interface can draw them
		// itself: the canvas reaches the screen scaled, and a smeared line under a sharp one
		// reads worse than either alone. They go on top here, every frame, because the canvas
		// is only redrawn on demand while the HD layer is built anew for each frame
		if (_messageOnCanvas && _message->hdText() && HdUi::active())
		{
			_message->hdDrawAt(getX(), getY());
		}
		else
		{
			SDL_Rect target {};
			target.x = getX() * k;
			target.y = getY() * k;
			SDL_BlitSurface(_canvas->getSdlSurface(), nullptr, world, &target);
		}
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
		int direction = bu->getDirection();
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
			Position leftPos = partCurr + Position(-1, 0, 0);
			Position rightPos = partCurr + Position(0, -1, 0);
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
	unitSprite.draw(bu, part, tileScreenPosition.x + offsets.ScreenOffset.x, tileScreenPosition.y + offsets.ScreenOffset.y, shade, mask, _isAltPressed && !_isCtrlPressed);
}

/**
 * Draw the terrain.
 * Keep this function as optimised as possible. It's big to minimise overhead of function calls.
 * @param surface The surface to draw on.
 */
void Map::drawTerrain(HdCanvas *surface)
{
	_isAltPressed = _game->isAltPressed(true);
	_isCtrlPressed = _game->isCtrlPressed(true);
	// HD render: combat effect clips not drawn for a while go, before this frame records any
	HdFx::trim();
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

	const int halfAnimFrame = (_animFrame / 2) % 4;
	const int halfAnimFrameRest = (_animFrame % 2);

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
	}

	// get corner map coordinates to give rough boundaries in which tiles to redraw are
	_camera->convertScreenToMap(0, 0, &beginX, &dummy);
	_camera->convertScreenToMap(surface->getWidth(), 0, &dummy, &beginY);
	_camera->convertScreenToMap(surface->getWidth() + _spriteWidth, surface->getHeight() + _spriteHeight, &endX, &dummy);
	_camera->convertScreenToMap(0, surface->getHeight() + _spriteHeight, &dummy, &endY);
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

	surface->lock();
	const Position cameraPos = _camera->getMapOffset();
	for (int itZ = beginZ; itZ <= endZ; itZ++)
	{
		bool topLayer = itZ == endZ;
		for (int itY = beginY; itY < endY; itY++)
		{
			mapPosition = Position(beginX, itY, itZ);
			tile = _save->getTile(mapPosition);
			for (int itX = beginX; itX < endX; itX++, mapPosition.x++, tile++)
			{
				_camera->convertMapToScreen(mapPosition, &screenPosition);
				screenPosition += cameraPos;

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
						// HD render: a floor with pack variants shows the one the ground pattern puts here
						if (_hdGroundVariants)
							surface->setGroundCell(true, mapPosition.x, mapPosition.y, mapPosition.z);
						if (tile->getObstacle(O_FLOOR))
							surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_FLOOR) * _k, obstacleShade, false, _nvColor);
						else
							surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_FLOOR) * _k, tileShade, false, _nvColor);
						if (_hdGroundVariants)
							surface->setGroundCell(false, 0, 0, 0);
					}

					auto* unit = tile->getUnit();

					// Draw cursor back
					if (_cursorType != CT_NONE && _selectorX > itX - _cursorSize && _selectorY > itY - _cursorSize && _selectorX < itX+1 && _selectorY < itY+1 && !_save->getBattleState()->getMouseOverIcons())
					{
						if (_camera->getViewLevel() == itZ)
						{
							if (_cursorType != CT_AIM)
							{
								if (unit && (unit->getVisible() || _save->getDebugMode()))
									frameNumber = halfAnimFrameRest; // yellow box
								else
									frameNumber = 0; // red box
							}
							else
							{
								if (unit && (unit->getVisible() || _save->getDebugMode()))
									frameNumber = 7 + halfAnimFrame; // yellow animated crosshairs
								else
									frameNumber = 6; // red static crosshairs
							}
							tmpSurface = _game->getMod()->getHdSurfaceSet("CURSOR.PCK")->getFrame(frameNumber);
							surface->blit(tmpSurface, screenPosition.x, screenPosition.y, 0);
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
							drawUnit(unitSprite, _save->getTile(mapPosition + backPos[b]), tile, screenPosition, topLayer);
						}
					}

					// Draw walls
					{
						// Draw west wall
						tmpSurface = tile->getSprite(O_WESTWALL);
						if (tmpSurface)
						{
							int wallShade = getWallShade(O_WESTWALL, tile);
							if (tile->getObstacle(O_WESTWALL))
								surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_WESTWALL) * _k, obstacleShade, false, _nvColor);
							else
								surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_WESTWALL) * _k, wallShade, false, _nvColor);
						}
						// Draw north wall
						tmpSurface = tile->getSprite(O_NORTHWALL);
						if (tmpSurface)
						{
							int wallShade = getWallShade(O_NORTHWALL, tile);
							if (tile->getObstacle(O_NORTHWALL))
								surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_NORTHWALL) * _k, obstacleShade, bool(tile->getSprite(O_WESTWALL)), _nvColor);
							else
								surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_NORTHWALL) * _k, wallShade, bool(tile->getSprite(O_WESTWALL)), _nvColor);
						}
						// Draw object
						tmpSurface = tile->getSprite(O_OBJECT);
						if (tmpSurface)
						{
							if (tile->isBackTileObject(O_OBJECT))
							{
								if (tile->getObstacle(O_OBJECT))
									surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_OBJECT) * _k, obstacleShade, false, _nvColor);
								else
									surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_OBJECT) * _k, tileShade, false, _nvColor);
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
									// the same pulse as the indicators on the inventory's ground grid (Inventory::drawItems)
									static const int Pulsate[8] = { 0, 1, 2, 3, 4, 3, 2, 1 };
									const int indicatorShade = std::min(15, tileShade + Pulsate[_animFrame % 8]);
									if (_burnIndicator && itemUnit->getFire() > 0)
									{
										surface->blit(_burnIndicator,
											screenPosition.x,
											screenPosition.y + tile->getTerrainLevel() * _k,
											indicatorShade);
									}
									else if (_woundIndicator && itemUnit->getFatalWounds() > 0)
									{
										surface->blit(_woundIndicator,
											screenPosition.x,
											screenPosition.y + tile->getTerrainLevel() * _k,
											indicatorShade);
									}
									else if (_shockIndicator && itemUnit->hasNegativeHealthRegen())
									{
										surface->blit(_shockIndicator,
											screenPosition.x,
											screenPosition.y + tile->getTerrainLevel() * _k,
											indicatorShade);
									}
									else if (_stunIndicator)
									{
										surface->blit(_stunIndicator,
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
							if (voxelPos.x / 16 >= itX &&
								voxelPos.y / 16 >= itY &&
								voxelPos.x / 16 <= itX+1 &&
								voxelPos.y / 16 <= itY+1 &&
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
							if (voxelPos.x / 16 >= itX &&
								voxelPos.y / 16 >= itY &&
								voxelPos.x / 16 <= itX+1 &&
								voxelPos.y / 16 <= itY+1 &&
								voxelPos.z / 24 == itZ &&
								_save->getTileEngine()->isVoxelVisible(voxelPos))
							{
								_camera->convertVoxelToScreen(voxelPos, &bulletPositionScreen);

								itemSprite.draw(item,
									bulletPositionScreen.x - 16 * _k,
									bulletPositionScreen.y - 26 * _k,
									tileShade
								);
							}
						}
						else
						{
							// draw bullet on the correct tile
							if (itX >= bulletLowX && itX <= bulletHighX && itY >= bulletLowY && itY <= bulletHighY)
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
										if (surface->getHdMode() != HD_MODE_NEAREST)
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

					//draw particle clouds behind solder
					for (const Particle& p : getVaporParticle(tile, 0))
					{
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
							drawUnit(unitSprite, _save->getTile(mapPosition + frontPos[f]), tile, screenPosition, topLayer);
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

						if (halfAnimFrame + tile->getAnimationOffset() > 3)
						{
							frameNumber += halfAnimFrame + tile->getAnimationOffset() - 4;
						}
						else
						{
							frameNumber += halfAnimFrame + tile->getAnimationOffset();
						}
						tmpSurface = _game->getMod()->getHdSurfaceSet("SMOKE.PCK")->getFrame(frameNumber);
						if (surface->getHdMode() != HD_MODE_NEAREST)
						{
							// HD render: the fire burns on the tile's surface (a raised object, a bank), as the
							// items lying there are drawn, not sunk into it; on the odd animation tick the
							// pack's in-between picture of the frame (variant 1), if it has one, doubles the
							// fire's frame rate
							const bool tween = tile->getFire() && halfAnimFrameRest;
							if (tween)
								surface->setFrameVariant(1);
							surface->blit(tmpSurface, screenPosition.x, screenPosition.y + (tile->getFire() ? tile->getTerrainLevel() * _k : 0), shade, false, _nvColor);
							if (tween)
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
						tmpSurface = _game->getMod()->getHdSurfaceSet("Pathfinding")->getFrame(tile->getPreview());
						if (tmpSurface)
						{
							surface->blit(tmpSurface, screenPosition.x, screenPosition.y + tile->getTerrainLevel() * _k, 0, false, tileColor);
						}
					}

					{
						// Draw object
						tmpSurface = tile->getSprite(O_OBJECT);
						if (tmpSurface)
						{
							if (!tile->isBackTileObject(O_OBJECT))
							{
								if (tile->getObstacle(O_OBJECT))
									surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_OBJECT) * _k, obstacleShade, false, _nvColor);
								else
									surface->blit(tmpSurface, screenPosition.x, screenPosition.y - tile->getYOffset(O_OBJECT) * _k, tileShade, false, _nvColor);
							}
						}
					}
					// Draw cursor front
					if (_cursorType != CT_NONE && _selectorX > itX - _cursorSize && _selectorY > itY - _cursorSize && _selectorX < itX+1 && _selectorY < itY+1 && !_save->getBattleState()->getMouseOverIcons())
					{
						if (_camera->getViewLevel() == itZ)
						{
							if (_cursorType != CT_AIM)
							{
								if (unit && (unit->getVisible() || _save->getDebugMode()))
									frameNumber = 3 + halfAnimFrameRest; // yellow box
								else
									frameNumber = 3; // red box
							}
							else
							{
								if (unit && (unit->getVisible() || _save->getDebugMode()))
									frameNumber = 7 + halfAnimFrame; // yellow animated crosshairs
								else
									frameNumber = 6; // red static crosshairs
							}
							tmpSurface = _game->getMod()->getHdSurfaceSet("CURSOR.PCK")->getFrame(frameNumber);
							surface->blit(tmpSurface, screenPosition.x, screenPosition.y, 0);

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
								// display additional damage and psi-effectiveness info
								if (_isAltPressed)
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
								_txtAccuracy->draw();
								surface->blitClassic(_txtAccuracy, screenPosition.x, screenPosition.y, _k);
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
									_txtAccuracy->draw();
									surface->blitClassic(_txtAccuracy, screenPosition.x, screenPosition.y, _k);
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
					mapPosition = Position(itX, itY, itZ);
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
							int overlay = tile->getPreview() + 12;
							tmpSurface = _game->getMod()->getHdSurfaceSet("Pathfinding")->getFrame(overlay);
							if (tmpSurface)
							{
								surface->blit(tmpSurface, screenPosition.x, screenPosition.y - adjustment, 0, false, tile->getMarkerColor());
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
							if (_previewSettingTu)
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
			_numUnitMarker->setColor(_unitMarkerColor[i]);
			_numUnitMarker->setValue(i + 1);
			_numUnitMarker->draw();
			surface->blitClassic(
				_numUnitMarker,
				screenPosition.x + markerOffset.x + (_spriteWidth / 2) - (i < 9 ? 3 : 5) * _k,
				screenPosition.y + markerOffset.y - 12 * _k,
				_k);
		}
	}

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
			for (const auto* explosion : _explosions)
			{
				_camera->convertVoxelToScreen(explosion->getPosition(), &bulletPositionScreen);
				// HD render: the combat effect clip in place of the classic frames, frame for frame by progress
				if (surface->getHdMode() != HD_MODE_NEAREST && !explosion->getHdFx().empty())
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
	if (surface->getHdMode() != HD_MODE_NEAREST)
	{
		std::vector<std::pair<const HdFx::Live*, const HdFrame*>> flashes;
		HdFx::running(SDL_GetTicks(), _k, flashes);
		for (const auto &f : flashes)
		{
			_camera->convertVoxelToScreen(f.first->voxel, &bulletPositionScreen);
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

	_camera->convertScreenToMap(mx, my + _spriteHeight/4, &_selectorX, &_selectorY);

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

	// units hanging with no floor below fade their sway in, landed ones fade it out (hoverBob)
	if (Options::oxceHdHoverBob)
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
	int dir = unit->getDirection();
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
		if (phase < midphase)
		{
			result.ScreenOffset.x = phase * 2 * offsetX[dir] * _k;
			result.ScreenOffset.y = - phase * offsetY[dir] * _k;
		}
		else
		{
			result.ScreenOffset.x = (phase - endphase) * 2 * offsetX[dir] * _k;
			result.ScreenOffset.y = - (phase - endphase) * offsetY[dir] * _k;
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
	if (projectile && Options::battleSmoothCamera)
	{
		_launch = true;
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
 * Gets the pointer to the camera.
 * @return Pointer to camera.
 */
Camera *Map::getCamera()
{
	return _camera;
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
	createCanvas();
	const int visibleBase = height - _iconHeight;
	_visibleMapHeight = visibleBase * _k;
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
	int midPoint = getWidth() / 2;
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
