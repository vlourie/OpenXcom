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

/// HD render: the battle view zoom steps, percent (Ctrl + mouse wheel goes one step). The view shrinks at most
/// twice, so the bilinear scale of the canvas to the screen still takes every pixel of it in.
const int VIEW_ZOOMS[] = { 50, 59, 71, 84, 100, 119, 141, 168, 200 };
const int VIEW_ZOOM_COUNT = (int)(sizeof(VIEW_ZOOMS) / sizeof(VIEW_ZOOMS[0]));
const int VIEW_ZOOM_ONE = 4;
/// The zoom the player chose last: the next battle of this run of the game starts with it.
int lastViewZoomStep = VIEW_ZOOM_ONE;

/// The opacity of the explosion area's fill where the power is the strongest (60% transparent).
const int BLAST_ALPHA_MAX = 102;
/// The weakest fill, as a part of the strongest (where the power has almost run out): the edge stays visible.
const float BLAST_ALPHA_FLOOR = 0.25f;
/// The opacity steps the fill is drawn with (one cached diamond per step and colour).
const int BLAST_ALPHA_STEPS = 32;

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
	fillDiamond(f, rgb, alpha, k);
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
	_hiddenFrozen = false;
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
 * Selects how the true-color canvas draws palette sprites (HdMode) and redraws.
 * @param mode HD_MODE_NEAREST, HD_MODE_PACKS or HD_MODE_SMOOTH.
 */
void Map::setHdMode(int mode)
{
	if (_canvas)
	{
		_canvas->setHdMode(mode);
		_hiddenFrozen = false;
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
	HdWeather::silence();
	if (!_hdAoFrames.empty())
	{
		Log(LOG_INFO) << "HD floor AO: " << _hdAoFrames.size() << " looks for this battle, grids and frames made in " << _hdAoBuildMs << " ms";
	}
	if (HdSmoke::bakeMs())
	{
		Log(LOG_INFO) << "HD volume smoke: puff banks baked in " << HdSmoke::bakeMs() << " ms (this run)";
	}
	if (HdFire::bakeMs())
	{
		Log(LOG_INFO) << "HD fire tongues: tongue banks baked in " << HdFire::bakeMs() << " ms (this run)";
	}
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
	// HD render (Options::oxceHdWeather): the falling weather moves at about 30 frames a second; when a frame with it costs
	// more than 10 ms (a slow processor), fewer, down to 15 a second, so that it keeps to a third of the time
	const Uint32 weatherStep = (Uint32)std::max(33.0, std::min(66.0, _hdWeatherCostMs / 0.3));
	{
		static Uint32 toldStep = 33;
		if (_hdWeatherFrameOn && (weatherStep >= toldStep + 8 || weatherStep + 8 <= toldStep))
		{
			toldStep = weatherStep;
			Log(LOG_INFO) << "HD weather: moves every " << weatherStep << " ms (a frame with it " << (int)std::lround(_hdWeatherCostMs) << " ms)";
		}
	}
	if (_hdWeatherFrameOn && !HdWeather::still(_hdWeatherKind) && SDL_GetTicks() - _hdWeatherLastDraw >= weatherStep)
	{
		_redraw = true;
	}
	// HD render (Options::oxceHdWeatherSound): the weather's sound goes on whether the picture is drawn or not
	hdWeatherHear();
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
	// HD light: smooth colored light only on the true-color canvas in the HD modes
	_hdLightOn = Options::oxceHdLight && _canvas->getHdMode() != HD_MODE_NEAREST;
	if (_hdLightOn)
	{
		_hdShadeCache.assign((size_t)_save->getMapSizeXYZ(), (Sint8)-1);
		_hdTintCache.assign((size_t)_save->getMapSizeXYZ() * 3, -1.0f);
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

	const bool shown = (_save->getSelectedUnit() && _save->getSelectedUnit()->getVisible())
		|| _unitDying
		|| ownShotShown()
		|| _save->getSide() == FACTION_PLAYER
		|| _save->getDebugMode()
		|| (_projectileInFOV && (!ignoreAllButAlliesHits || (unitVisible && !unitEnemy)))
		|| (_explosionInFOV && (!ignoreAllButAlliesHits || ((unitVisible && !unitEnemy) || hitExplosion)));
	const bool hiddenMap = !shown && Options::oxceHdHiddenMap && Options::oxceHdEnemyTurn != 1 && _hiddenViewValid;
	if (hiddenMap && _hiddenFrozen && !_hdTestFrozen && !hiddenPictureMayAnimate())
	{
		// XP-000326: an unseen enemy's turn keeps the one picture drawn when it began: a door opened or smoke blown
		// on a tile the player discovered but does not see is not shown before the player sees it again
		// (XP-000097: while nothing of that kind has changed, the picture goes on animating: smoke, fire, lamps)
		return;
	}
	_hdLabels.clear();
	_hdLabelsOn = hdLabelsWanted();
	if (Options::oxceHdBackdrop && !hdVacuum())
	{
		// the backdrop beyond the map's edge as a gradient around the environment's colour (a palette canvas: flat as ever)
		// (the ground's line of the mod's table hd/backdrop.txt, when there is one, in place of the environment's color);
		// in vacuum the void stays the flat color of the environment: no haze where there is no air (XP-000317)
		_canvas->fillBackdrop(Palette::blockOffset(0) + _bgColor, hdBackdropRgb());
	}
	else
	{
		_canvas->fill(Palette::blockOffset(0) + _bgColor);
	}
	if (shown)
	{
		_hiddenFrozen = false;
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
	else if (hiddenMap)
	{
		// an unseen enemy's turn: the map from where the player last saw it; the camera's own moves (a walking
		// unit's level, a followed shot, centring on the next unit) are not shown and the camera keeps them;
		// no tile cursor, the mouse points at nothing the player can act on
		if (!_hiddenFrozen && hdAnimWanted())
		{
			// the picture freezes now: what it shows is the reference the animating frames are compared with
			_hiddenSig = hiddenSignature();
			_hiddenAnimTick = _animTicks;
		}
		const Position real = _camera->getMapOffset();
		const CursorType cursor = _cursorType;
		_camera->setMapOffset(_hiddenViewOffset);
		_cursorType = CT_NONE;
		drawTerrain(_canvas);
		_cursorType = cursor;
		_camera->setMapOffset(real);
		_hiddenFrozen = true;
		_messageOnCanvas = false;
		_messageApart = false;
	}
	else
	{
		_hiddenFrozen = false;
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
	if (_hdWeatherFrameOn)
	{
		// one slow frame (the twisters baked, a level changed) moves the mean a little, a slow machine moves it for good
		_hdWeatherCostMs = _hdWeatherCostMs > 0 ? 0.85 * _hdWeatherCostMs + 0.15 * _lastDrawMs : _lastDrawMs;
	}
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
	if (p.getColor() == Particle::PlainSmokeColor)
	{
		return p.getOpacity() < Mod::TransparenciesOpacityLevels ? plainSmokeTints()[p.getOpacity()] : none;
	}
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
	const bool plain = p.getColor() == Particle::PlainSmokeColor;
	if (!plain && p.getColor() >= tints.size())
	{
		return none;
	}
	const auto &levels = plain ? plainSmokeTints() : tints[p.getColor()];
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
 * The plain grey smoke of a bullet or a rocket with no vapor in the ruleset (Options::oxceHdPlainSmoke, XP-000301): the four
 * opacity levels, made by the rule the mod's own "R, G, B, opacity" tints follow (Mod.cpp, transparencyLUTs) for the grey
 * 7, 7, 7 with opacity 8 - the neutral cousin of the smoke tint of the Piratez table. A mod's table numbers differ from mod
 * to mod, this one is the engine's own, so it works in any mod and in the original game.
 */
const std::array<SDL_Color, 4> &Map::plainSmokeTints()
{
	static_assert(Mod::TransparenciesOpacityLevels == 4, "the plain smoke has four opacity levels");
	static const std::array<SDL_Color, 4> tints = []
	{
		std::array<SDL_Color, 4> t;
		for (int level = 0; level < 4; ++level)
		{
			const int op = std::min((level + 1) * 8, 64);
			const float co = 1.0f - (op / 64.0f) * (op / 64.0f);
			SDL_Color c;
			c.r = c.g = c.b = (Uint8)std::min(255, 7 * op);
			c.unused = (Uint8)(255 * co);
			t[level] = c;
		}
		return t;
	}();
	return tints;
}

/**
 * Builds the palette table of the plain grey smoke (4 levels x 256 colours) from the palette the map shows, the way
 * Mod::createTransparencyLUT does it for the mod's tints: the nearest palette colour to the tinted one.
 * @return false if the map has no palette yet.
 */
bool Map::buildPlainSmokeLut()
{
	if (!_plainSmokeLut.empty())
	{
		return true;
	}
	const SDL_Color *pal = getPalette();
	if (!pal)
	{
		return false;
	}
	std::vector<Uint8> lut;
	lut.reserve(4 * Mod::TransparenciesPaletteColors);
	for (const SDL_Color &tint : plainSmokeTints())
	{
		for (int current = 0; current < Mod::TransparenciesPaletteColors; ++current)
		{
			const int r = std::min(255, (pal[current].r * tint.unused / 255) + tint.r);
			const int g = std::min(255, (pal[current].g * tint.unused / 255) + tint.g);
			const int b = std::min(255, (pal[current].b * tint.unused / 255) + tint.b);
			Uint8 closest = current;
			int lowest = INT_MAX;
			if (current != 0)
			{
				for (int comparator = 1; comparator < Mod::TransparenciesPaletteColors; ++comparator)
				{
					const int d = (r - pal[comparator].r) * (r - pal[comparator].r) + (g - pal[comparator].g) * (g - pal[comparator].g)
						+ (b - pal[comparator].b) * (b - pal[comparator].b);
					if (d < lowest)
					{
						closest = comparator;
						lowest = d;
					}
				}
			}
			lut.push_back(closest);
		}
	}
	_plainSmokeLut = std::move(lut);
	return true;
}

/**
 * The palette table (256 entries) of a vapor particle at its opacity level: the mod's table of its colour, or the plain
 * grey smoke's own.
 */
const Uint8 *Map::vaporLut(const Particle &p) const
{
	if (p.getColor() == Particle::PlainSmokeColor)
	{
		return _plainSmokeLut.data() + p.getOpacity() * Mod::TransparenciesPaletteColors;
	}
	return _transparencies->data()
		+ (p.getColor() * Mod::TransparenciesOpacityLevels * Mod::TransparenciesPaletteColors)
		+ (p.getOpacity() * Mod::TransparenciesPaletteColors);
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
			// an HD test dump compares the frame drawn now: the video card's canvas comes back at once, not a frame late
			if (screen->hasHdTestDumpRequest())
			{
				canvas32->getSdlSurface();
			}
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
			// on the video card: the bytes in the colours SDL's blit maps them to, its colour key 0 left out
			SDL_Surface *src = shown->getSdlSurface();
			HdGpuWorld &gpuWorld = HdGpuWorld::instance();
			bool handed = false;
			if (gpuWorld.on(world))
			{
				const SDL_Palette *pal = src->format->palette;
				if (src->format->BitsPerPixel == 8 && pal && (src->flags & SDL_SRCCOLORKEY) && src->format->colorkey == 0
					&& !(src->flags & SDL_SRCALPHA) && src->format->alpha == 255 && world->clip_rect.x == 0 && world->clip_rect.y == 0
					&& world->clip_rect.w == world->w && world->clip_rect.h == world->h)
				{
					Uint32 lut[256] = {};
					for (int i = 0; i < pal->ncolors && i < 256; ++i)
					{
						lut[i] = SDL_MapRGB(world->format, pal->colors[i].r, pal->colors[i].g, pal->colors[i].b);
					}
					handed = gpuWorld.pixels((const Uint8*)src->pixels, src->pitch, src->w, src->h, target.x, target.y, 1, lut,
						target.x, target.y, target.x + src->w, target.y + src->h) && !gpuWorld.verifying();
				}
				else
				{
					gpuWorld.cpu("a palette canvas");
				}
			}
			if (!handed)
			{
				SDL_BlitSurface(src, nullptr, world, &target);
			}
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
 * Is this battle in vacuum? The mod's table hd/vacuum.txt names the environments (enviroEffects types, one a line,
 * # comments), so the engine knows no mod's names. Looked up once a battle; only the picture asks it.
 * @return True when the battle's environment is in the table.
 */
bool Map::hdVacuum()
{
	if (_hdVacuum >= 0)
	{
		return _hdVacuum == 1;
	}
	_hdVacuum = 0;
	const RuleEnviroEffects *enviro = _save->getEnviroEffects();
	const std::string path = HdSprites::artPath("vacuum.txt");
	std::unique_ptr<std::istream> in = enviro && FileMap::fileExists(path) ? FileMap::getIStream(path) : nullptr;
	std::string line;
	while (in && std::getline(*in, line))
	{
		if (line.size() >= 3 && (unsigned char)line[0] == 0xEF && (unsigned char)line[1] == 0xBB && (unsigned char)line[2] == 0xBF)
		{
			line.erase(0, 3);
		}
		std::istringstream fields(line);
		std::string name;
		if (fields >> name && name[0] != '#' && name == enviro->getType())
		{
			_hdVacuum = 1;
			break;
		}
	}
	Log(LOG_INFO) << "HD vacuum: environment " << (enviro ? enviro->getType() : "-") << " -> " << _hdVacuum;
	return _hdVacuum == 1;
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
		const int twelfths = tile->getPreviewStep();
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
 * HD: true when the battle is on an orbital map (enviro effects STR_ENVIRO_SPACE, the ORBIT_* terrains of Piratez): no sun
 * lights the ground there, so units cast no HD shadow (ticket XP-000446). Not STR_ENVIRO_MOON, not the freighter.
 * The string compare runs only when the battle's enviro effects change (a new battle or stage), not per unit per frame.
 */
bool hdOrbitalMap(const SavedBattleGame *save)
{
	static const RuleEnviroEffects *seen = nullptr;
	static bool known = false, orbital = false;
	const RuleEnviroEffects *env = save->getEnviroEffects();
	if (!known || env != seen)
	{
		seen = env;
		known = true;
		orbital = env && env->getType() == "STR_ENVIRO_SPACE";
	}
	return orbital;
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
	// HD: the shadow on the floor, under the piece drawn here and cut by its mask; not under a unit hanging with no
	// floor, nor under the top of one reaching up from the level below (its floor is there); not in the turned view;
	// not under water (depth > 0: no sun there) nor on an orbital map (ticket XP-000446); weaker in the dusk, none at night
	// (the strength of the global shade, ticket XP-000447)
	const int shadowStrength = Options::oxceHdUnitShadow ? unitShadowStrength(_save->getGlobalShade()) : 0;
	if (shadowStrength > 0 && _canvas->getHdMode() != HD_MODE_NEAREST && _save->getDepth() <= 0 && !hdOrbitalMap(_save) && !unitFromBelow && !unitFromAbove && !turned
		&& !bu->isFloating() && !bu->isOut() && part < bu->getArmor()->getSize() * bu->getArmor()->getSize())
	{
		const Position bob = hoverBob(bu);
		_canvas->blitFrame(unitShadow(bu->getArmor()->getSize(), part, _k, shadowStrength), tileScreenPosition.x + offsets.ScreenOffset.x - bob.x,
			tileScreenPosition.y + offsets.ScreenOffset.y - bob.y + 24 * _k, mask);
	}
	// the facing indicator: with Alt held, or always (HD option, only what Alt shows)
	unitSprite.draw(bu, part, tileScreenPosition.x + offsets.ScreenOffset.x, tileScreenPosition.y + offsets.ScreenOffset.y, shade, mask, (_isAltPressed || (Options::oxceHdAltInfo & 1)) && !_isCtrlPressed);
}

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

// HD render (XP-000544, Options::oxceHdClassicShots): the shot of a laser, plasma or gauss weapon as the classic game drew it - a flat
// beam, a ball with a tail of beads, a capsule in coils of air - instead of the 35 stamps of its tracer. Picture only: nothing below
// reads the shot's way any other way than the stamps did (the positions of its steps), the camera above has already moved.
// The shot is a row of pieces that do not overlap (HdShots); piece j stands where the way is `back[j]` steps behind the head
// and is stamped in the tile of that step, like a stamp of the tracer, so walls and units cover it the same way.
// `active`: this shot is drawn so, and the classic stamps are not (even when nothing is to be seen yet: the first step)
struct HdClassicShot
{
	bool active = false;
	const HdShots::Shot *shot = nullptr;
	Position head;                  // the head on the map surface
	std::vector<int> back;          // steps behind the head of every piece, -1: before the muzzle, not drawn
	int lowX = 16000, lowY = 16000, highX = 0, highY = 0;   // the tiles of the pieces, in the view's tiles
};

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
	// HD render (XP-000310): a fast bullet flies more voxels a frame than its tracer has stamps, so between two frames part
	// of the way was never drawn and the bullet blinked. In HD the stamps of the trail are spread over the whole jump of a
	// frame (the gaps between them are filled below); the classic path and the slow bullets keep a stamp a voxel
	const int bulletSpan = (_projectile && !_projectile->getItem() && _k > 1 && surface->getHdMode() != HD_MODE_NEAREST) ?
		std::max((int)BULLET_SPRITES, _projectile->getSpeed()) : (int)BULLET_SPRITES;
	const auto bulletBack = [&](int i) { return i * bulletSpan / BULLET_SPRITES; }; // voxels behind the head of stamp i
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
			const Position bp = _projectile->getPosition(1 - bulletBack(i));
			if (bp.x < bulletLowX)
				bulletLowX = bp.x;
			if (bp.y < bulletLowY)
				bulletLowY = bp.y;
			if (bp.z < bulletLowZ)
				bulletLowZ = bp.z;
			if (bp.x > bulletHighX)
				bulletHighX = bp.x;
			if (bp.y > bulletHighY)
				bulletHighY = bp.y;
			if (bp.z > bulletHighZ)
				bulletHighZ = bp.z;
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

	HdClassicShot classicShot;
	hdFindClassicShot(classicShot, turned, hdFrames);

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

	// HD render (XP-000451): the cursor frame is drawn in the pass of its own tile and the volumetric smoke and fire of the
	// tiles in front of it come later and bury it; within one tile of the cursor (its floor and the one above) they are drawn
	// see-through, so the frame shows. Walls, units and items in front still cover it, as in the classic frame.
	// Only while the battle cursor is shown (not in a projectile's flight, the enemy's turn, nor over the icons).
	const bool cursorFadeOn = hdFrames && _cursorType != CT_NONE && !_save->getBattleState()->getMouseOverIcons();
	const auto cursorFade = [&](int tx, int ty, int tz)
	{
		if (!cursorFadeOn || (tz != _camera->getViewLevel() && tz != _camera->getViewLevel() + 1))
			return 1.0f;
		if (tx < _selectorX - _cursorSize || tx > _selectorX + 1 || ty < _selectorY - _cursorSize || ty > _selectorY + 1)
			return 1.0f;
		return 0.4f;
	};

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
			const SurfaceRaw<const Uint8> view = hdFrames ? _turn->painted(sprite, rot, part) : SurfaceRaw<const Uint8>();
			if (view)
				sprite = view;
			else if (left != (part == O_WESTWALL))
				sprite = _turn->mirrored(sprite, hdFrames);
			int shade = getWallShade(part, owner);
			// a wall standing on the far tile of its edge is seen from this cell: known (the sight of this cell
			// discovers it) while its own tile is not, it is lit as this cell is, not black
			if (!owner->isDiscovered(O_FLOOR) && owner->isDiscovered(part))
			{
				Tile *front = _save->getTile(mapPosition);
				if (front && front != owner && front->isDiscovered(O_FLOOR))
					shade = reShade(front);
			}
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
		const SurfaceRaw<const Uint8> view = hdFrames ? _turn->painted(sprite, rot, O_OBJECT) : SurfaceRaw<const Uint8>();
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

	// a particle is a 2x2 pattern of size thresholds; at HD scale every cell becomes a k x k block (built once per frame, not per tile)
	const int pixelMaskBase[] = { 0, 2, 1, 3 };
	std::vector<int> pixelMaskArray(4 * _k * _k);
	for (int my = 0; my < 2 * _k; ++my)
		for (int mx = 0; mx < 2 * _k; ++mx)
			pixelMaskArray[my * 2 * _k + mx] = pixelMaskBase[(my / _k) * 2 + (mx / _k)];
	SurfaceRaw<int> pixelMask(pixelMaskArray, 2 * _k, 2 * _k);

	surface->lock();
	const Position cameraPos = _camera->getMapOffset();
	// XP-000263: the ground beyond the map's edge, under the map: only at HD scale above 1, not turned, not in vacuum
	if (Options::oxceHdBeyondEdge && _k > 1 && !turned && !_camera->getShowSingleLayer() && !hdVacuum())
	{
		hdDrawBeyondEdge(surface, cameraPos);
	}
	// XP-000380, XP-000382: the border of the field along the map's edge (HD scale above 1, not turned); without the ground beyond too
	const bool hdBorder = Options::oxceHdMapBorder > 0 && _k > 1 && !turned;
	if (hdBorder)
	{
		hdDrawMapBorder(surface, cameraPos, 0);
	}
	// HD lab: the turned view goes a cell past the map's far edges, for the walls that face away there
	const int rimX = endX + (turned && endX >= _camera->getViewSizeX() ? 1 : 0);
	const int rimY = endY + (turned && endY >= _camera->getViewSizeY() ? 1 : 0);
	hdGatherFlierShadows(cameraPos, endZ);
	hdGatherFlashLights();
	hdObserveSteps();
	// HD render (Options::oxceHdWeather): the weather of the battle - the ground goes with the floors, the air at the end
	const bool hdWeather = hdWeatherOn(surface);
	if (hdWeather)
	{
		hdWeatherRolls();
	}
	// XP-000572: a map with open sea (a ship) - the sea goes on beyond the map's edge on the water's level, HD scale above 1;
	// looked for once: the map lives for one battle
	if (_hdSeaZ == -2)
	{
		hdFindSea();
	}
	const bool hdSea = _k > 1 && !turned && _hdSeaZ >= beginZ && _hdSeaZ <= endZ && !_hdSeaTiles.empty();
	for (int itZ = beginZ; itZ <= endZ; itZ++)
	{
		bool topLayer = itZ == endZ;
		if (hdSea && itZ == _hdSeaZ)
			hdDrawSea(surface, cameraPos, itZ, false);
		if (hdSea && itZ == _hdSeaZ + 1)
			hdDrawSea(surface, cameraPos, _hdSeaZ, true);
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

					// XP-000572: what lies under the sea and is not seen yet stays under the water, not black
					if (hdSea && !tile->isDiscovered(O_FLOOR) && !tile->isDiscovered(O_WESTWALL) && !tile->isDiscovered(O_NORTHWALL)
						&& hdUnderSea(_save, mapPosition))
					{
						continue;
					}

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
					else if (hdSea && hdOpenSea(tile))
					{
						// XP-000572: open water (an animated floor no one can walk or fly over, nothing on it) shows before it is seen
						tileShade = reShade(tile);
						obstacleShade = tileShade;
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

					// HD render: the explosion area of what is aimed, on the floor of every tile it reaches that the player
					// has seen (not in the air above a level): the colour of the damage type, the stronger the power the denser;
					// and the collapse hint - the tiles whose building parts may fall after the explosion, in hazard stripes.
					// A hill is an object on a flat floor (terrain level below 0): the object would cover a diamond on the floor,
					// so on such a tile the diamonds go right after the object, lifted by the terrain level like the path marks.
					// Only where a unit can stand: crates, racks and tables are impassable (TU walk 255) and keep the diamond
					// under them, hills are walkable (XP-000346)
					const bool blastOnHill = _blastMax > 0 && tile->getTerrainLevel() < 0 && tile->getSprite(O_OBJECT)
						&& tile->getMapData(O_OBJECT)->getTUCost(MT_WALK) < 255
						&& (turned ? turnedObject(tile->getMapData(O_OBJECT)->getBigWall()).back : tile->isBackTileObject(O_OBJECT));
					auto drawBlastHint = [&](int lift)
					{
						if (_blastMax > 0 && tile->isDiscovered(O_FLOOR) && (itZ == 0 || tile->getMapData(O_FLOOR)))
						{
							const int blastPower = _blastPower[_save->getTileIndex(mapPosition)];
							if (blastPower > 0)
							{
								const float share = std::max(BLAST_ALPHA_FLOOR, std::min(1.0f, (float)blastPower / _blastMax));
								const int step = std::max(1, (int)std::lround(share * BLAST_ALPHA_STEPS));
								const int alpha = BLAST_ALPHA_MAX * step / BLAST_ALPHA_STEPS;
								surface->blitFrame(blastDiamond(_blastRgb, alpha, _k), screenPosition.x,
									screenPosition.y + 24 * _k - tile->getYOffset(O_FLOOR) * _k + lift);
							}
						}
						if (_blastMax > 0 && _blastFallCount > 0 && _blastFall[_save->getTileIndex(mapPosition)])
						{
							surface->blitFrame(fallDiamond(_k), screenPosition.x, screenPosition.y + 24 * _k - tile->getYOffset(O_FLOOR) * _k + lift);
						}
					};
					if (!blastOnHill)
					{
						drawBlastHint(0);
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
						if (blastOnHill)
						{
							drawBlastHint(tile->getTerrainLevel() * _k);
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

					//draw particle clouds
					// a particle is a 2x2 pattern of size thresholds; at HD scale every cell becomes a k x k block
					const int vaporScreenOriginX = screenPosition.x + _spriteWidth / 2;
					const int vaporScreenOriginY = screenPosition.y + _spriteHeight - _spriteWidth / 2 + tile->getPosition().toVoxel().z * _k;
					const bool softVapor = surface->getHdMode() != HD_MODE_NEAREST;

					//draw particle clouds behind solder
					for (const Particle& p : getVaporParticle(tile, 0))
					{
						if (_k > 1 && p.isHdShot())
						{
							continue; // HD: the vapor of an energy shot with the classic shots (XP-000555)
						}
						if (softVapor)
						{
							// HD: a soft round puff at the particle's own place, fading smoothly (classic mode keeps the 2x2 pattern)
							const Position o = p.getOffset16(_k);
							surface->drawVaporSoft(vaporScreenOriginX * 16 + o.x + _k * 16, vaporScreenOriginY * 16 + o.y + _k * 16, p.getSize(), _k, vaporTintSoft(p));
							continue;
						}
						int vaporX = vaporScreenOriginX + p.getOffsetX() * _k;
						int vaporY = vaporScreenOriginY + p.getOffsetY() * _k;
						auto transparetOffsets = vaporLut(p);

						surface->drawVapor(pixelMask, vaporX, vaporY, p.getSize(), transparetOffsets, vaporTint(p));
					}

					// HD render (Options::oxceHdWeather): a tumbleweed whose front-most tile this is, before the units of the tile
					if (hdWeather && _hdWeatherRollCount > 0 && !turned && itZ == 0 && tile->isDiscovered(O_FLOOR))
					{
						hdWeatherRollsAt(surface, mapPosition, screenPosition, tileShade);
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

					//draw particle clouds on front of solder
					for (const Particle& p : getVaporParticle(tile, topLayer ? 3 : 1))
					{
						if (_k > 1 && p.isHdShot())
						{
							continue; // HD: the vapor of an energy shot with the classic shots (XP-000555)
						}
						if (softVapor)
						{
							// HD: a soft round puff at the particle's own place, fading smoothly (classic mode keeps the 2x2 pattern)
							const Position o = p.getOffset16(_k);
							surface->drawVaporSoft(vaporScreenOriginX * 16 + o.x + _k * 16, vaporScreenOriginY * 16 + o.y + _k * 16, p.getSize(), _k, vaporTintSoft(p));
							continue;
						}
						int vaporX = vaporScreenOriginX + p.getOffsetX() * _k;
						int vaporY = vaporScreenOriginY + p.getOffsetY() * _k;
						auto transparetOffsets = vaporLut(p);

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
						drawCursorFront(surface, tile, unit, screenPosition, itX, itY, itZ, explosiveReticle);
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
	if (hdSea && _hdSeaZ == endZ)
		hdDrawSea(surface, cameraPos, _hdSeaZ, true);
	// XP-000382: the near sides of the fence stand before the map's cells
	if (hdBorder && Options::oxceHdMapBorder == 2)
	{
		hdDrawMapBorder(surface, cameraPos, 1);
	}
	if (pathfinderTurnedOn)
	{
		drawPathPreview(surface, _numWaypid, beginX, endX, beginY, endY, beginZ, endZ, turned);
	}

	drawSelectedArrow(surface);

	// Draw the indicator number above the units seen directly by the selected unit
	drawUnitMarkers(surface);

	// gentle mode: where the reaction fire came from (drawn while the shot flies too, the cursor is off then)
	// HD render: the flight arc of what is aimed, on top of the map
	drawAimArc(surface);

	drawGentleArrows(surface);

	// Draw motion scanner arrows
	drawScannerArrows(surface);
	delete _numWaypid;

	// Draw craft deployment preview arrows
	drawDeployArrows(surface);

	// HD render (oxceHdBloodCloud, XP-000557): the clouds of blood under water, under the hits' own pictures
	hdDrawBloodClouds(surface);
	drawExplosions(surface);

	// HD render (Options::oxceHdWeather): the air of the weather over the whole map; the muzzle flashes shine through it
	if (hdWeather)
	{
		hdWeatherAir(surface);
	}

	// HD render: muzzle flashes, on their own clock (see hdMuzzle)
	drawMuzzleFlashes(surface);

	surface->unlock();
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
 * Is a shot of the player's own soldier on the picture (XP-000462)? In an unseen enemy's turn the picture is frozen unless
 * something the player sees happens; the reaction burst of his soldier is such a thing, but it lost its right to the live
 * picture after the first round: once the enemy it fired at is dead or out of view and the bullets fly over tiles that
 * are not seen, the flashes, the tracers and the soldier's aim froze and only the sound of the other rounds went on.
 */
bool Map::ownShotShown() const
{
	return _ownShot || (Sint32)(SDL_GetTicks() - _ownShotUntil) < 0;
}

/**
 * The picture's animation where the classic game stops it (XP-000097): needs the option and an HD drawing mode; the
 * classic drawing (mode 0) stays as it always was.
 */
bool Map::hdAnimWanted() const
{
	return Options::oxceHdAnimHidden && _canvas && _canvas->getHdMode() != HD_MODE_NEAREST;
}

/**
 * Hashes everything the picture draws from the battle except its animation (XP-000097): the tiles up to the level of the
 * frozen view (what is discovered and seen, the parts, smoke, fire, light, UFO doors open or shut, the items), the units
 * the player sees, the effects that could show an unseen place. Two equal values mean that a redraw shows nothing the frozen
 * picture does not show; only the frame of the animation (and the frames of the parts) differs.
 */
uint64_t Map::hiddenSignature() const
{
	uint64_t h = 1469598103934665603ULL;
	const auto mix = [&h](uint64_t v) { h = (h ^ v) * 1099511628211ULL; };
	const int sizeX = _save->getMapSizeX(), sizeY = _save->getMapSizeY(), sizeZ = _save->getMapSizeZ();
	const int topZ = _camera->getShowAllLayers() ? sizeZ - 1 : std::min(sizeZ - 1, (int)_hiddenViewOffset.z);
	mix(sizeX); mix(sizeY); mix(topZ);
	for (int z = 0; z <= topZ; ++z)
	{
		for (int y = 0; y < sizeY; ++y)
		{
			for (int x = 0; x < sizeX; ++x)
			{
				Tile *tile = _save->getTile(Position(x, y, z));
				const uint64_t seen = (tile->isDiscovered(O_FLOOR) ? 1 : 0) | (tile->isDiscovered(O_WESTWALL) ? 2 : 0)
					| (tile->isDiscovered(O_NORTHWALL) ? 4 : 0) | (tile->getVisible() ? 8 : 0);
				mix(seen);
				if (!seen)
				{
					continue; // a black tile: nothing of it is drawn
				}
				mix((uint64_t)tile->getSmoke() | ((uint64_t)tile->getFire() << 8));
				for (int part = 0; part < O_MAX; ++part)
				{
					mix((uint64_t)(uintptr_t)tile->getMapData((TilePart)part));
					mix(tile->isUfoDoorOpen((TilePart)part) ? 1 : 0);
				}
				for (int layer = 0; layer < LL_MAX; ++layer)
				{
					mix((uint64_t)tile->getLight((LightLayers)layer));
				}
				const auto *items = tile->getInventory();
				mix(items->size());
				for (const BattleItem *item : *items)
				{
					mix((uint64_t)(uintptr_t)item);
					mix((uint64_t)item->getFuseTimer());
				}
			}
		}
	}
	for (const BattleUnit *bu : *_save->getUnits())
	{
		mix(bu->getVisible() ? 1 : 0);
		if (!bu->getVisible())
		{
			continue; // not drawn: where it is and what it does is not shown
		}
		const Position pos = bu->getPosition();
		mix(bu->getId()); mix(pos.x); mix(pos.y); mix(pos.z);
		mix(bu->getDirection()); mix(bu->getStatus()); mix(bu->isKneeled() ? 1 : 0); mix(bu->getFire());
	}
	// a shot in flight is drawn only where the tile it flies over is seen (_projectileInFOV) and a hit on a seen tile is
	// seen: neither shows what the frozen picture hides, so they no longer stop the animation (XP-000097, the tracer of an
	// unseen enemy's shot froze the smoke and the fire for its flight). What the picture could draw from an unseen
	// place is counted: a big explosion (it is drawn wherever it is) and one on a tile that is not seen (it is drawn
	// along with another that is in view); explosions are drawn at all only when one of them is in view (Map::draw)
	size_t unseenExplosions = 0, unseenLooseHits = 0;
	if (_explosionInFOV)
	{
		const auto unseen = [this](const Explosion *explosion)
		{
			if (explosion->isBig())
			{
				return true;
			}
			const Tile *at = _save->getTile(explosion->getPosition().toTile());
			return !at || !at->getVisible();
		};
		for (const Explosion *explosion : _explosions)
		{
			unseenExplosions += unseen(explosion) ? 1 : 0;
		}
		for (const auto &loose : _looseHits)
		{
			unseenLooseHits += unseen(loose.explosion) ? 1 : 0;
		}
	}
	mix(unseenExplosions);
	mix(unseenLooseHits);
	mix(_gentleShots.size());
	mix(HdFx::active(SDL_GetTicks()) ? 1 : 0);
	return h;
}

/**
 * The picture of an unseen enemy's turn is frozen (XP-000326): may this redraw draw the world live? Yes while the
 * signature of what the player has discovered is the one the picture froze with: the redraw then differs from the
 * frozen picture only in the animation (smoke, fire, lamps, doors that were opening). Looked at once a tick of the
 * picture's clock, not on every mouse move (but on every frame a shot, a hit or a flash is moving: the tracer would
 * go in steps of 100 ms); a change that is later undone lets the animation go on again.
 */
bool Map::hiddenPictureMayAnimate()
{
	const bool moving = _projectile || !_explosions.empty() || !_looseHits.empty() || HdFx::active(SDL_GetTicks());
	if (!hdAnimWanted() || (_hiddenAnimTick == _animTicks && !moving))
	{
		return false;
	}
	_hiddenAnimTick = _animTicks;
	return hiddenSignature() == _hiddenSig;
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
	_animFrame = (_save->getAnimFrame() + _menuTicks) % 705600; // plus the frames the menus ran: the picture's clock does not go back
	++_animTicks;

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

	// units hanging with no floor below fade their sway in, landed ones fade it out (hoverBob); mode 0 draws them still, as the classic game,
	// and so does vacuum: nothing to float in (XP-000318)
	if (Options::oxceHdHoverBob && _canvas->getHdMode() != HD_MODE_NEAREST && !hdVacuum())
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

	animateVapor();

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
 * The tick of the picture's animation and nothing else (XP-000097), for the time a menu is open over the battle: the
 * frame of the smoke, the fire, the lamps and the vapor, and a redraw. The ambient sounds, the UFO doors (their frames
 * are the game's: a door is open once its animation reaches frame 7) and the units are left to animate.
 */
void Map::animateDrawOnly()
{
	if (_hdTestFrozen || AiProbe::fast() || !hdAnimWanted())
	{
		return;
	}
	_animFrame = (_animFrame + 1) % 705600; // the span of SavedBattleGame::nextAnimFrame; the save's own frame is not touched
	_menuTicks = (_menuTicks + 1) % 705600;
	++_animTicks;
	for (int i = 0; i < _save->getMapSizeXYZ(); ++i)
	{
		_save->getTile(i)->animateDrawOnly();
	}
	animateVapor();
	_redraw = true;
}

/**
 * Animates the vapor particles of the map, one tick.
 */
void Map::animateVapor()
{
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
	// XP-000462: the shot of the player's own soldier in an enemy's turn (reaction fire) stays on the picture for the rest
	// of the burst, whether or not the enemy is still seen and the bullet flies over a seen tile (picture only)
	const bool own = projectile && projectile->getActor() && projectile->getActor()->getFaction() == FACTION_PLAYER;
	if (_ownShot || own)
	{
		_ownShotUntil = SDL_GetTicks() + OWN_SHOT_HOLD_MS;
	}
	_ownShot = own;
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
	if (particle.getColor() == Particle::PlainSmokeColor)
	{
		// the plain grey smoke (XP-000301) has its own tint and table, no mod's table is needed
		if (!buildPlainSmokeLut())
		{
			return;
		}
	}
	else if ((int)(_transparencies->size()) < (particle.getColor() + 1) * Mod::TransparenciesOpacityLevels * Mod::TransparenciesPaletteColors)
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
