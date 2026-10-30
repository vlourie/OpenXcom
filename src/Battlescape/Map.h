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
#include "../Engine/Unicode.h"
#include "../Mod/MapData.h"
#include "Position.h"
#include "Particle.h"
#include <array>
#include <vector>
#include <string>
#include <unordered_map>

namespace OpenXcom
{

class SavedBattleGame;
class Surface;
class SurfaceSet;
class BattleUnit;
class BattleItem;
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
class HdTurn;
class HdTurnGroups;

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
	/// The indicators over a body on the floor, each as its animation phases (one when the HD mod ships none).
	std::vector<Surface*> _stunIndicator, _woundIndicator, _burnIndicator, _shockIndicator;
	bool _anyIndicator, _isAltPressed, _isCtrlPressed;
	int _spriteWidth, _spriteHeight;
	/// HD render scale k = _spriteWidth / 32: the map surface and all screen offsets are k times the base resolution.
	int _k;
	/// HD render: the battle view zoom (Ctrl + mouse wheel), an index into the zoom table. The canvas is the
	/// map's size divided by the zoom and reaches the screen scaled: the view takes in more or less of the
	/// map, the tiles and everything the game counts stay as they are. Picture only, 32-bit display only.
	int _zoomStep;
	/// The view the canvas, the camera and every place on the map are counted in, world pixels (the map's
	/// size at the zoom 100 %).
	int _viewWidth, _viewHeight;
	/// The part of the screen above the icons, base pixels: the view's part (_visibleMapHeight) follows it.
	int _visibleBase;
	/// While the view is zoomed, the hidden movement message goes to a canvas of the map's own size (it is
	/// laid out on the screen), so it reaches the screen unscaled.
	HdCanvas *_messageCanvas = nullptr;
	bool _messageApart = false;
	/// Works out the view size for the map's size and the zoom.
	void updateViewSize();
	/// Base-resolution scratch surface used to draw the hidden movement message before scaling it.
	Surface *_messageScratch;
	/// true while the canvas holds the hidden movement message and not the terrain
	bool _messageOnCanvas;
	/// The canvas all battlescape drawing goes to (classic 8-bit surface or the true-color world).
	HdCanvas *_canvas;
	/// HD render: floors with pack variants are drawn by the ground pattern (option oxceHdGroundVariants).
	bool _hdGroundVariants;
	/// The seed of this battle's ground pattern (from the map blocks: the same battle keeps its look after a load).
	Uint32 groundSeed() const;
	/// HD render: addressed wall frames draw the picture of their cell from the SCC field (option oxceHdTerrainAddress).
	bool _hdTerrainAddress;
	HdWallField _wallField;
	/// Test hooks of the addressing (OXCE_HD_ADDRESS_OBSTACLE, OXCE_HD_ADDRESS_RELOAD): frames drawn so far.
	int _addressTestFrames = 0;
	void addressTestReload();
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
	std::unordered_map<int, int> _hoverFade; // unit id -> 1..HOVER_FADE_STEPS, how far the sway of a hanging unit has faded in
	Projectile *_projectile;
	bool _followProjectile;
	bool _projectileInFOV;
	std::list<Explosion *> _explosions;
	/// Loose hits (Options::oxceHdLooseHits): bullet hit sprites no battle state waits for, each with its frame time
	/// and when its next frame is due (picture clock); drawn with the others, animated in think
	struct LooseHit { Explosion *explosion; Uint32 frameMs, next; };
	std::vector<LooseHit> _looseHits;
	std::vector<std::vector<Particle>> _vaporParticlesInit;
	std::vector<std::vector<Particle>> _vaporParticles;
	bool _explosionInFOV, _launch;
	/// Options::oxceHdHiddenMap: the camera offset of the last frame the map was shown with; an unseen enemy's
	/// turn draws the map from there, whatever the camera does meanwhile
	Position _hiddenViewOffset;
	bool _hiddenViewValid = false;
	/// The unseen enemy's turn has drawn its picture: the frames after it keep the canvas as it is (XP-000326).
	bool _hiddenFrozen = false;
	/// Options::oxceHdAnimHidden (XP-000097): what the frozen picture may show again. The signature of what the player has
	/// discovered but does not see, as it was when the picture froze; the picture animates again on every animation tick
	/// at which the signature is still the same. _animTicks counts the ticks of the picture's clock, _hiddenAnimTick
	/// is the tick the signature was last compared at (once a tick, not on every mouse move).
	uint64_t _hiddenSig = 0;
	unsigned _animTicks = 0, _hiddenAnimTick = 0;
	/// What the picture shows of the battle besides its animation (tile contents, smoke, fire, light, doors, items,
	/// visible units, shots in flight), hashed; the same value = a redraw shows nothing new.
	uint64_t hiddenSignature() const;
	/// The frozen picture of an unseen enemy's turn: does the world still match it, so that it can be drawn live again?
	bool hiddenPictureMayAnimate();
	/// The animation of the vapor particles, one tick (a part of animate)
	void animateVapor();
	/// The shake of the drawn map (shake): its start on the picture clock, length and largest offset.
	Uint32 _shakeStart = 0, _shakeMs = 0;
	int _shakeAmp = 0;
	/// The offset of the shake at this moment, (0, 0) when there is none.
	Position shakeOffset(Uint32 now) const;
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
	/// HD interface: the hit chance at the cursor and the numbers over the units seen are not baked into the
	/// canvas (it reaches the screen scaled, and the pixel digits with it) - they are kept here, in canvas
	/// pixels, and drawn with the interface's TrueType font on top of the map in blit(). Picture only.
	struct HdLabel
	{
		UString text;
		int x = 0, y = 0;
		bool tag = false;
		Uint32 face = 0, back = 0, edge = 0;
		float cap = 0.0f;       ///< text only: the capitals' height (0 = the small font's), (x, y) = its top
		bool centre = false;    ///< text only: x is the text's centre
		float weight = 1.0f;    ///< text with a cap, a tag or the small font's text: the strokes' weight against the usual (1 = as the font draws them)
		float scale = 1.0f;     ///< a tag or the small font's text (no cap): the size against the usual (1 = as it was drawn before the option)
	};
	std::vector<HdLabel> _hdLabels;
	bool _hdLabelsOn = false;
	/// Are the labels drawn by the HD interface (its modern skin with the TrueType fonts)?
	bool hdLabelsWanted() const;
	/// The backdrop's middle color 0xRRGGBB from the mod's table hd/backdrop.txt for this battle's terrain or mission, -1: none.
	int hdBackdropRgb();
	int hdBackdropFind();
	int _hdBackdropRgb = -2; ///< hdBackdropRgb once found (-2: not looked yet)
	/// Is the battle's environment in the mod's table hd/vacuum.txt (no backdrop gradient, no hover bob there)?
	bool hdVacuum();
	int _hdVacuum = -1; ///< hdVacuum once looked (-1: not looked yet)
	/// Options::oxceHdBeyondEdge (XP-000263): the ground beyond the map's edge, under the map, at the canvas of HD scale above 1.
	void hdDrawBeyondEdge(HdCanvas *surface, const Position &cameraPos);
	/// The commonest floor of the map's outer band on the ground level, found once a battle: the cells beyond the edge take it
	/// where the cell they mirror is not discovered yet (the mirror shows no floor the player has not seen).
	struct HdGhostFloor { SurfaceRaw<const Uint8> sprite; int yOffset = 0; int count = 0; };
	std::vector<HdGhostFloor> _hdGhostFloors;
	/// The floors of the ground level as the battle began (XP-000263), a cell of the map each, found once with _hdGhostFloors:
	/// kind 0 no floor (a hole), 1 the floor is not known (a damage - the scorched earth, a debris - a room over it, a rare floor
	/// of the band: the ghost floor goes there), 2 the floor is `data`. Memory of the picture only, not saved.
	struct HdSnapFloor { const MapData *data = nullptr; Uint8 kind = 0; };
	std::vector<HdSnapFloor> _hdFloorSnap;
	/// The veils of the backdrop's colour over the far cells (by colour and opacity), kept while the battle's map lives.
	std::unordered_map<unsigned long long, HdFrame> _hdHazeFrames;
	int _hdGhostState = -1;  ///< -1: floors not looked yet, 0: none (no ground level to go on), 1: _hdGhostFloors are there
	/// Options::oxceHdBeyondLook 1: the floor of a palette sprite in greys (made once, kept while the battle's map lives), nullptr if it cannot be made.
	const HdFrame *hdGrayFloor(HdCanvas *surface, SurfaceRaw<const Uint8> sprite);
	std::unordered_map<const void*, HdFrame> _hdGrayFrames;
	/// HD render: the shade of the corners on the floor (option oxceHdFloorAo), see Map::hdFloorAo.
	struct HdAoShape { Uint16 rows[16]; float weight; int count; bool valid; };
	static const int HD_AO_PARTS = 27;
	struct HdAoCell { const MapData *parts[HD_AO_PARTS]; const HdFrame *frame; bool built; };
	const HdFrame *hdFloorAo(Tile *tile, const Position &pos);
	const HdAoShape &hdAoShape(const MapData *part);
	std::unordered_map<const MapData*, HdAoShape> _hdAoShapes;
	std::vector<HdAoCell> _hdAoCells;
	std::unordered_map<std::string, HdFrame> _hdAoFrames;
	int _hdAoK = 0;
	bool _hdAoFull = false;
	/// the time spent making the grids and frames this battle (reported when the map goes)
	double _hdAoBuildMs = 0;
	/// Options::oxceHdMapBorder (XP-000380, XP-000382): the line or the fence along the map's edge. Pass 0 goes under the map's
	/// cells (the line, the two far sides of the fence), pass 1 over them (the two near sides of the fence).
	void hdDrawMapBorder(HdCanvas *surface, const Position &cameraPos, int pass);
	std::unordered_map<unsigned long long, HdFrame> _hdBorderFrames;
	/// The hit chance text as it stands in _txtAccuracy, at canvas (x, y): baked, or kept for the HD interface.
	void drawAccuracy(HdCanvas *canvas, int x, int y);
	SurfaceSet *_projectileSet;
	/// Gentle mode: a reaction shot of this turn, for the arrow at the soldier fired at (picture only).
	/// The arrow tells no more than the shot's trail did: it shows only once the bullet was drawn in view
	/// (seen), and the shooter's number turns only once it was drawn by the shooter (seenOrigin).
	struct GentleShot
	{
		const BattleUnit *shooter;
		Position from, at;
		int height;
		Uint32 ticks, id;
		bool seen, seenOrigin;
	};
	std::vector<GentleShot> _gentleShots;
	std::vector<const BattleUnit*> _gentleShooters;
	int _gentleTurn = -1;
	Uint32 _gentleShotId = 0, _gentleFlying = 0;
	/// Gentle mode: the bullet of the shot in flight was drawn at this voxel, this screen point.
	void noteGentleTrail(const Position &voxel, const Position &screen, int width);
	static const int GENTLE_ARROW_STEPS = 32;
	Surface *_gentleArrow[GENTLE_ARROW_STEPS] = {};
	int _gentleArrowScale = 0;
	/// Notes a reaction shot fired at the player's side (gentle mode).
	void noteGentleShot(const Projectile *projectile);
	/// Draws the arrows from the soldiers fired at towards their shooters (gentle mode).
	void drawGentleArrows(HdCanvas *surface);
	/// The arrow sprite pointing one of GENTLE_ARROW_STEPS ways, in world pixels.
	Surface *gentleArrow(int step);
	/// HD render: the area of the explosion the shot or throw being aimed would make (option oxceHdBlastArea):
	/// the power it would reach each tile with (by tile index, 0 = not reached), the strongest of them,
	/// and the colour of the damage type (0xRRGGBB). Recomputed only when what is aimed changes.
	std::vector<int> _blastPower;
	int _blastMax = 0;
	Uint32 _blastRgb = 0;
	Position _blastCenter = Position(-1, -1, -1);
	int _blastKeyPower = 0, _blastKeyRadius = 0;
	const void *_blastKeyType = nullptr;
	/// The aim hint of the building collapse (option oxceCollapse): the tiles marked "may fall" (by tile index),
	/// a part above the view level marked on the view level, and how many there are.
	std::vector<uint8_t> _blastFall;
	int _blastFallCount = 0;
	/// Works out the area for the current action and cursor (clears it when nothing explosive is aimed).
	void updateBlastArea(HdCanvas *surface);
	/// HD render: the kind of shot aimed, for its reticle style (oxceHdReticleArtillery / oxceHdReticleExplosive).
	enum AimKind { AIM_PLAIN, AIM_ARTILLERY, AIM_EXPLOSIVE };
	AimKind _aimKind = AIM_PLAIN;
	/// HD render: the arc of the aimed throw or arcing shot (option oxceHdAimArc), in voxels from the thrower; whether
	/// it reaches the target, and the colour of its dashes (0xRRGGBB). Worked out again only when the aim moves.
	std::vector<Position> _arcPath;
	bool _arcReaches = false;
	Uint32 _arcRgb = 0;
	const BattleUnit *_arcKeyActor = nullptr;
	const BattleItem *_arcKeyWeapon = nullptr;
	int _arcKeyType = 0, _arcKeyWeight = 0, _arcKeyTurn = 0;
	Position _arcKeyTarget, _arcKeyFrom;
	bool _arcKeyKneeled = false, _arcKeyCtrl = false;
	/// The dashes of the arc: ARC_DASH_ON voxels drawn of every ARC_DASH, running to the target one voxel an animation frame.
	static const int ARC_DASH = 10, ARC_DASH_ON = 6;
	/// Works out the aim kind, swaps its reticle style in and the arc for the current action and cursor.
	void updateAimHints(HdCanvas *surface);
	/// Draws the arc on top of the map.
	void drawAimArc(HdCanvas *surface);
	/// HD render: "+N" under the reticle at canvas (x, y) - the power the shooter's stats add (option oxceHdAimSkillBonus).
	void drawSkillBonus(HdCanvas *surface, int x, int y);
	Text *_txtSkillBonus = nullptr;

	void drawUnit(UnitSprite &unitSprite, Tile *unitTile, Tile *currTile, Position tileScreenPosition, bool topLayer, BattleUnit* movingUnit = nullptr);
	void drawTerrain(HdCanvas *canvas);
	void blitMessage(HdCanvas *target);
	void createCanvas();
	SDL_Color vaporTint(const Particle &p) const;
	SDL_Color vaporTintSoft(const Particle &p) const;
	/// The palette table of a vapor particle (the mod's table of its colour, or the plain grey smoke's own, XP-000301).
	const Uint8 *vaporLut(const Particle &p) const;
	/// The plain grey smoke (Particle::PlainSmokeColor): its four opacity levels, and the palette table built for the battle's palette.
	static const std::array<SDL_Color, 4> &plainSmokeTints(); // 4 = Mod::TransparenciesOpacityLevels
	bool buildPlainSmokeLut();
	std::vector<Uint8> _plainSmokeLut;
	/// HD light: the drawing shade of a tile, cached for the frame (reShade is not cheap in night vision).
	int hdShadeOf(Tile *tile);
	/// HD light: the color of the light on a tile from its light layers (ambient/fire/items/units).
	void hdTintOf(const Tile *tile, float *tint) const;
	/// HD light: computes the light field of a tile from its corners and hands it to the canvas.
	void updateHdLight(Tile *tile, int tileShade, const Position &pos);
	int getTerrainLevel(const Position& pos, int size) const;
	int getWallShade(TilePart part, Tile* tileFrot);
	/// HD lab: the mirrored and turned terrain frames of the turned map (made on first use, kept for the battle).
	HdTurn *_turn = nullptr;
	/// HD lab: the composite objects of the map, drawn whole in the turned view (found when it first turns).
	HdTurnGroups *_turnGroups = nullptr;
	/// HD lab: the wall on a back edge of a cell of the turned view - `left` the edge on the left of the screen
	/// (where the west wall stands unturned), else the right one (the north wall's). Returns the tile that owns
	/// it (nullptr off the map) and its part; its frame is mirrored when that part is the other one.
	Tile *turnedWall(const Position &pos, bool left, TilePart &part) const;
	/// HD lab: how an object stands in the turned view - drawn before the units of its cell (on its back
	/// edges) or after them, mirrored or not, and how far its frame moves on the screen (world pixels):
	/// an object on an edge of its tile goes to where that edge is now.
	struct TurnedObject { bool back; bool mirror; int dx, dy; };
	TurnedObject turnedObject(int bigWall) const;
	/// HD lab: a direction 0..7 as the turned view shows it (other values as they are).
	int turnedDir(int dir) const;
	/// HD interface (oxceHdPathStretch): a path preview's arrow, as many copies one behind another as the step is dear.
	void blitPathArrow(HdCanvas *canvas, SurfaceRaw<const Uint8> frame, int x, int y, int newBaseColor, const Tile *tile, const Position &mapPosition);
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
	/// Is the hidden movement screen on the canvas now (and not the terrain)? (Options::oxceHdEnemyTurn's strip)
	bool isHiddenScreenShown() const { return _messageOnCanvas; }
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
	/// XP-000097: the tick of the picture's animation and nothing else (no ambient sounds, no door mechanics): for the
	/// time a menu is open over the battle; does nothing unless hdAnimWanted
	void animateDrawOnly();
	/// Options::oxceHdAnimHidden and an HD drawing mode (XP-000097): the picture's animation goes on where the classic game
	/// stops it - while a battle state is busy, in a menu over the battle, in an unseen enemy's turn
	bool hdAnimWanted() const;
	/// Sets the battlescape selector position relative to mouse position.
	void setSelectorPosition(int mx, int my);
	/// Gets the currently selected position.
	void getSelectorPosition(Position *pos) const;
	/// Calculates the offset of a soldier, when it is walking in the middle of 2 tiles.
	UnitWalkingOffset calculateWalkingOffset(const BattleUnit *unit) const;
	/// Screen offset of a unit hanging with no floor below: a sway in the air, a slow drift in the water.
	Position hoverBob(const BattleUnit *unit) const;
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
	/// Hands the explosion set over to the loose hits: they play on by themselves, frameMs a frame.
	void loosenExplosions(int frameMs);

	/// Shakes the drawn map for ms, by up to amp screen pixels fading out (Options::oxceHdCollapseShake; picture only).
	void shake(int amp, Uint32 ms);

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
	/// Gentle mode: has this unit fired a reaction shot at the player's side in this turn?
	bool firedReactionThisTurn(const BattleUnit *unit) const;
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
	/// Steps of oxceHdFirePace and oxceHdSmokePace.
	static const int HD_ENVI_PACES = 5;
	/// Speed of the fire or smoke animation at a step of its pace option, percent of the stock one.
	static int hdEnviPercent(int pace);
	/// The animation clock of a burning or smoking tile in the HD modes, in timer ticks (picture only).
	static int hdEnviClock(int animFrame, Position pos, int pace);
	/// Gets the HD render scale k of this map.
	int getScale() const { return _k; }
	/// Changes the battle view zoom by `steps` (Ctrl + mouse wheel), keeping the place under the mouse where it
	/// is; false where the zoom is not available (the 8-bit display).
	bool zoomView(int steps);
	/// The battle view zoom, percent (100 = the map's own size).
	int getViewZoomPercent() const;
	/// The view's width and height, world pixels (the map's size divided by the zoom).
	int getViewWidth() const { return _viewWidth; }
	int getViewHeight() const { return _viewHeight; }
	/// The view's part above the icons, world pixels.
	int getViewVisibleHeight() const { return _visibleMapHeight; }
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
