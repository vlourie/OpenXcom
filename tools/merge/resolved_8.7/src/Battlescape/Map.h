#pragma once
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
#include "../Engine/InteractiveSurface.h"
#include "../Engine/HdCanvas.h"
#include "../Engine/Options.h"
#include "../Engine/Collections.h"
#include "../Mod/MapData.h"
#include "Position.h"
#include "Particle.h"
#include <vector>
#include <string>

namespace OpenXcom
{

class SavedBattleGame;
class Surface;
class SurfaceSet;
class BattleUnit;
class Projectile;
class Explosion;
class BattlescapeMessage;
class Camera;
class Timer;
class Text;
class Tile;
class UnitSprite;
class NumberText;
class HdCanvas;

enum CursorType { CT_NONE, CT_NORMAL, CT_AIM, CT_PSI, CT_WAYPOINT, CT_THROW };
enum TilePart : int;

/**
 * Helper class that returns all important data about the unit movement
 */
struct UnitWalkingOffset
{
	Position ScreenOffset;
	int NormalizedMovePhase;
	int TerrainLevelOffset;
};

/**
 * Interactive map of the battlescape.
 */
class Map : public InteractiveSurface
{
private:
	static const int SCROLL_INTERVAL = 15;
	static const int FADE_INTERVAL = 23;
	static const int NIGHT_VISION_SHADE = 4;
	static const int NIGHT_VISION_MAX_SHADE = 8;
	static const int BULLET_SPRITES = 35;
	static const int UNIT_MARKER_MAX = 10;
	/// Original tile sprite size the map geometry was designed around.
	static const int BASE_SPRITE_WIDTH = 32;
	static const int BASE_SPRITE_HEIGHT = 40;
	Timer *_scrollMouseTimer, *_scrollKeyTimer, *_obstacleTimer;
	Timer *_fadeTimer;
	int _fadeShade;
	bool _nightVisionOn;
	int _debugVisionMode;
	int _nvColor;
	Game *_game;
	SavedBattleGame *_save;
	bool _isTFTD;
	Surface *_arrow;
	Surface *_stunIndicator, *_woundIndicator, *_burnIndicator, *_shockIndicator;
	bool _anyIndicator, _isAltPressed, _isCtrlPressed;
	int _spriteWidth, _spriteHeight;
	/// HD render scale k = _spriteWidth / 32: the map surface and all screen offsets are k times the base resolution.
	int _k;
	/// Base-resolution scratch surface used to draw the hidden movement message before scaling it.
	Surface *_messageScratch;
	/// The canvas all battlescape drawing goes to (classic 8-bit surface or the true-color world).
	HdCanvas *_canvas;
	/// HD render: floors with pack variants are drawn by the ground pattern (option oxceHdGroundVariants).
	bool _hdGroundVariants;
	/// The seed of this battle's ground pattern (from the map blocks: the same battle keeps its look after a load).
	Uint32 groundSeed() const;
	/// HD light: the light field of the tile being drawn, per-frame shade cache, and whether the field is in use this frame.
	HdLight _hdLight;
	std::vector<Sint8> _hdShadeCache;
	bool _hdLightOn = false;
	int _selectorX, _selectorY;
	int _mouseX, _mouseY;
	CursorType _cursorType;
	int _cursorSize;
	int _cacheActiveWeaponUfopediaArticleUnlocked; // -1 = unknown, 0 = locked, 1 = unlocked
	bool _cacheIsCtrlPressed;
	Position _cacheCursorPosition;
	int _cacheHasLOS; // -1 = unknown, 0 = no LOS, 1 = has LOS
	int _animFrame;
	Projectile *_projectile;
	bool _followProjectile;
	bool _projectileInFOV;
	std::list<Explosion *> _explosions;
	std::vector<std::vector<Particle>> _vaporParticlesInit;
	std::vector<std::vector<Particle>> _vaporParticles;
	bool _explosionInFOV, _launch;
	BattlescapeMessage *_message;
	Camera *_camera;
	int _visibleMapHeight;
	std::vector<Position> _waypoints;
	bool _unitDying, _smoothCamera, _smoothingEngaged, _flashScreen;
	int _bgColor;
	bool _previewSettingArrows, _previewSettingTu, _previewSettingEnergy;
	Text *_txtAccuracy;
	NumberText *_numUnitMarker;
	const BattleUnit *_unitMarkerUnit[UNIT_MARKER_MAX];
	Uint8 _unitMarkerColor[UNIT_MARKER_MAX];
	SurfaceSet *_projectileSet;

	void drawUnit(UnitSprite &unitSprite, Tile *unitTile, Tile *currTile, Position tileScreenPosition, bool topLayer, BattleUnit* movingUnit = nullptr);
	void drawTerrain(HdCanvas *canvas);
	void blitMessage();
	void createCanvas();
	SDL_Color vaporTint(const Particle &p) const;
	/// HD light: the drawing shade of a tile, cached for the frame (reShade is not cheap in night vision).
	int hdShadeOf(Tile *tile);
	/// HD light: the color of the light on a tile from its light layers (ambient/fire/items/units).
	void hdTintOf(const Tile *tile, float *tint) const;
	/// HD light: computes the light field of a tile from its corners and hands it to the canvas.
	void updateHdLight(Tile *tile, int tileShade, const Position &pos);
	int getTerrainLevel(const Position& pos, int size) const;
	int getWallShade(TilePart part, Tile* tileFrot);
	int _iconHeight, _iconWidth, _messageColor;
	int _hostileBarColor, _neutralBarColor, _borderBarColor;
	const std::vector<Uint8> *_transparencies;
	bool _showObstacles;
	bool _showInfoOnCursor;
	// HD render test (deterministic frame capture), see Engine/HdTest.h
	bool _hdTestFrozen = false;
	std::string _hdTestMapDumpPath;
	CursorType _hdTestSavedCursorType = CT_NORMAL;
	int _hdTestSavedCursorSize = 1;
	double _lastDrawMs = 0.0;
public:
	/// Creates a new map at the specified position and size.
	Map(Game* game, int width, int height, int x, int y, int visibleMapHeight);
	/// Cleans up the map.
	~Map();
	/// Initializes the map.
	void init();
	/// Handles timers.
	void think() override;
	/// Draws the surface.
	void draw() override;
	void refreshAIProgress(int progress);
	/// Sets the palette.
	void setPalette(const SDL_Color *colors, int firstcolor = 0, int ncolors = 256) override;
	void refreshHiddenMovementBackground();
	/// Special handling for mouse press.
	void mousePress(Action *action, State *state) override;
	/// Special handling for mouse release.
	void mouseRelease(Action *action, State *state) override;
	/// Special handling for mouse over
	void mouseOver(Action *action, State *state) override;
	/// Special handling for key presses.
	void keyboardPress(Action *action, State *state) override;
	/// Special handling for key releases.
	void keyboardRelease(Action *action, State *state) override;
	/// Rotates the tile frames 0-7
	void animate(bool redraw);
	/// Sets the battlescape selector position relative to mouse position.
	void setSelectorPosition(int mx, int my);
	/// Gets the currently selected position.
	void getSelectorPosition(Position *pos) const;
	/// Calculates the offset of a soldier, when it is walking in the middle of 2 tiles.
	UnitWalkingOffset calculateWalkingOffset(const BattleUnit *unit) const;
	/// Sets the 3D cursor type.
	void setCursorType(CursorType type, int size = 1);
	/// Gets the 3D cursor type.
	CursorType getCursorType() const;

	/// Sets projectile.
	void setProjectile(Projectile *projectile);
	/// Gets projectile.
	Projectile *getProjectile() const;
	/// Sets follow projectile flag.
	void setFollowProjectile(bool followProjectile) { _followProjectile = followProjectile; }
	/// Gets follow projectile flag.
	bool getFollowProjectile() const { return _followProjectile; }
	/// Gets alt pressed flag.
	bool isAltPressed() const { return _isAltPressed; }
	/// Gets ctrl pressed flag.
	bool isCtrlPressed() const { return _isCtrlPressed; }
	/// Add new vapor particle.
	void addVaporParticle(Position pos, Particle particle);
	/// Get all vapor for tile.
	Collections::Range<const Particle*> getVaporParticle(const Tile* tile, int topLayer) const;
	/// Gets explosion set.
	std::list<Explosion*> *getExplosions();

	/// Gets the pointer to the camera.
	Camera *getCamera();
	/// Mouse-scrolls the camera.
	void scrollMouse();
	/// Keyboard-scrolls the camera.
	void scrollKey();
	/// fades in/out
	void fadeShade();
	/// Get waypoints vector.
	std::vector<Position> *getWaypoints();
	/// Clears all on-map markers of the visible unit indicators.
	void clearUnitMarkers();
	/// Sets an on-map marker for one visible unit indicator (0 clears the slot).
	void setUnitMarker(int index, const BattleUnit *unit, Uint8 color);
	/// Set mouse-buttons' pressed state.
	void setButtonsPressed(Uint8 button, bool pressed);
	/// Sets the unitDying flag.
	void setUnitDying(bool flag);
	/// Refreshes the battlescape selector after scrolling.
	void refreshSelectorPosition();
	/// Blits the map: into the screen's world layer when the output is layered, else like any surface.
	void blit(SDL_Surface *surface) override;
	/// Special handling for updating map height.
	void setHeight(int height) override;
	/// Special handling for updating map width.
	void setWidth(int width) override;
	/// Get the vertical position of the hidden movement screen.
	int getMessageY() const;
	/// Get the icon height.
	int getIconHeight() const;
	/// Get the icon width.
	int getIconWidth() const;
	/// Convert a map position to a sound angle.
	int getSoundAngle(const Position& pos) const;
	/// Reset the camera smoothing bool.
	void resetCameraSmoothing();
	/// Set whether the screen should "flash" or not.
	void setBlastFlash(bool flash);
	/// Check if the screen is flashing this.
	bool getBlastFlash() const;
	/// Modify shade for fading
	int reShade(Tile *tile) const;
	int reShadeMinimap(int maxShade) const;
	/// HD render test: freeze all animation for one drawn frame and optionally dump the map surface.
	void hdTestFreeze(const std::string &mapDumpPath);
	/// HD render test: true while the frozen frame has not been drawn yet.
	bool isHdTestFrozen() const { return _hdTestFrozen; }
	/// Is night vision currently on?
	bool isNightVisionOn() const { return _nightVisionOn; }
	/// Gets the debug vision mode (0 = off).
	int getDebugVisionMode() const { return _debugVisionMode; }
	/// Gets the current fade shade (night vision transition).
	int getFadeShade() const { return _fadeShade; }
	/// HD render scale factor read from BLANKS.PCK (1 = original 32x40 tiles).
	static int hdScale(Game *game);
	/// Gets the HD render scale k of this map.
	int getScale() const { return _k; }
	/// Gets the name of the canvas type the map draws on (HD render test dumps).
	const char *getCanvasName() const;
	/// Selects how the canvas draws palette sprites (HdMode) and redraws the map.
	void setHdMode(int mode);
	/// Gets the mode the canvas draws palette sprites with.
	int getHdMode() const;
	/// Time the last full map draw took, milliseconds (HD render profiling).
	double getLastDrawMs() const { return _lastDrawMs; }
	/// Gets the tile sprite width the map geometry is based on (32 in vanilla).
	int getSpriteWidth() const { return _spriteWidth; }
	/// Gets the tile sprite height the map geometry is based on (40 in vanilla).
	int getSpriteHeight() const { return _spriteHeight; }
	/// toggle the night-vision mode
	void enableNightVision();
	void toggleNightVision();
	void toggleDebugVisionMode();
	void persistToggles();
	/// Resets obstacle markers.
	void resetObstacles();
	/// Enables obstacle markers.
	void enableObstacles();
	/// Disables obstacle markers.
	void disableObstacles();
};

}
