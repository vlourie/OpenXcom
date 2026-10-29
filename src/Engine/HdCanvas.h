#pragma once
/*
 * Copyright 2010-2026 OpenXcom Developers.
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
#include <chrono>
#include <cstring>
#include <deque>
#include <list>
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <SDL.h>
#include "Surface.h"
#include "GraphSubset.h"
#include "HdSprites.h"

namespace OpenXcom
{

class ScriptWorkerBlit;

/**
 * Where the drawing of one battle frame went, for the frame log (OXCE_HD_FRAMELOG, Game.cpp):
 * counted only while the log is on, read and cleared by it after every frame. Measurement only.
 */
struct HdDrawStats
{
	/// The frame log is on (read once from the environment).
	static const bool on;
	/// The current frame's counts.
	static HdDrawStats frame;
	/// Map::draw recording the commands (the classic routines, units included), microseconds.
	long long recordUs = 0;
	/// Of the recording: the unit sprites (UnitSprite::draw).
	long long unitsUs = 0;
	/// Of the recording: the units' scripts and their recolour of the HD frames (blitScripted).
	long long scriptUs = 0;
	/// Of the recording: frames smoothed or recoloured on first use, and their number.
	long long smoothUs = 0;
	unsigned smoothNew = 0;
	/// Shaded copies and ground blends made on first use (on the workers, before the commands run),
	/// and the number of shaded copies.
	long long tonedUs = 0;
	unsigned tonedNew = 0;
	/// Running the commands on the workers: wall time, and the longest strip
	/// (a wall much longer than the longest strip means the threads waited for a CPU).
	long long flushUs = 0;
	long long stripMaxUs = 0;
	unsigned cmds = 0;
};

/// Adds the time of its scope to a counter of HdDrawStats while the frame log is on.
class HdDrawTimer
{
	long long *_acc;
	std::chrono::steady_clock::time_point _start;
public:
	explicit HdDrawTimer(long long &acc) : _acc(HdDrawStats::on ? &acc : nullptr)
	{
		if (_acc) _start = std::chrono::steady_clock::now();
	}
	~HdDrawTimer()
	{
		if (_acc) *_acc += std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - _start).count();
	}
	HdDrawTimer(const HdDrawTimer &) = delete;
	HdDrawTimer &operator=(const HdDrawTimer &) = delete;
};

/**
 * The light over one tile for the HD canvas: the shade and the color of the
 * light at the four corners of the tile's floor diamond (N = the top vertex,
 * then E, S, W clockwise), interpolated across every sprite drawn with the
 * tile's own shade. The classic renderer's integer shade is still what the
 * game reasons with; this only changes how the true-color canvas paints it.
 */
struct HdLight
{
	/// The nine nodes of the field over the tile's floor diamond, row by row: (N corner, N-E edge, E corner),
	/// (W-N edge, centre, E-S edge), (W corner, S-W edge, S corner). The centre is the tile's own light, the
	/// edges are shared with the neighbour across them, the corners with the three tiles around them.
	static const int NODES = 9;
	/// The tile's own drawing shade: blits with this shade are lit by the field, others keep their flat shade.
	int center = 0;
	/// Node shades 0..16 (16 = black).
	float shade[NODES] = { 0, 0, 0, 0, 0, 0, 0, 0, 0 };
	/// Node light colors 0..1 (1,1,1 = white light).
	float tint[NODES][3] = { { 1, 1, 1 }, { 1, 1, 1 }, { 1, 1, 1 }, { 1, 1, 1 }, { 1, 1, 1 }, { 1, 1, 1 }, { 1, 1, 1 }, { 1, 1, 1 }, { 1, 1, 1 } };
	/// All nodes equal: the sprite is drawn flat (through the shaded-frame cache).
	bool flat = true;
};

/**
 * SCC wall addressing (option oxceHdTerrainAddress): which picture of an addressed wall frame every map
 * cell shows. One table per (part, n) the loaded packs use, built once for the map's size by a fixed
 * formula of the cell's coordinates, so a cell keeps its picture whatever the camera, the drawing order
 * or a saved game. Along a wall line two neighbours never repeat, nor a cell and the one below it.
 */
struct HdWallField
{
	struct Table { int part = 0, n = 0; std::vector<Uint8> v; };
	int sizeX = 0, sizeY = 0, sizeZ = 0;
	/// HdSprites::generation() the tables were checked against.
	unsigned generation = 0;
	std::vector<Table> tables;
	/// The picture (0 .. n - 1, 0 = the frame itself) of cell (x, y, z) for wall `part` with n pictures; 0 without a table.
	int at(int part, int n, int x, int y, int z) const
	{
		if (x < 0 || y < 0 || z < 0 || x >= sizeX || y >= sizeY || z >= sizeZ) return 0;
		for (const Table &t : tables)
			if (t.part == part && t.n == n) return t.v[((size_t)z * sizeY + y) * sizeX + x];
		return 0;
	}
	/// Fills the table of wall `part` (HdSprites::WALL_WEST / WALL_NORTH) with n pictures for a map of X x Y x Z cells.
	static void build(std::vector<Uint8> &f, int part, int n, int X, int Y, int Z);
	/// Brings the tables up to the packs: rebuilt only when the map size or the registry changed and only the
	/// (part, n) pairs that are new. Returns true when anything was built (a log line per table).
	bool update(int X, int Y, int Z);
};

/// How a true-color canvas draws palette sprites (Canvas8 ignores it).
enum HdMode
{
	/// Every sprite nearest-neighbour scaled through the palette: pixel for pixel the classic picture.
	HD_MODE_NEAREST = 0,
	/// HD frames from packs where they exist, nearest for the rest.
	HD_MODE_PACKS = 1,
	/// HD frames from packs where they exist, xBRZ-smoothed sprites for the rest.
	HD_MODE_SMOOTH = 2,
	HD_MODE_COUNT = 3
};

/**
 * The surface the battlescape map draws on ("HD render").
 *
 * Every drawing operation of Map, UnitSprite and ItemSprite goes through this
 * interface, so that the same drawing code can target either the classic
 * 8-bit palette surface (Canvas8, exactly what the game always did) or a
 * true-color surface where palette sprites are converted on the fly and HD
 * sprites are drawn as they are (Canvas32).
 *
 * All coordinates are world pixels (k times the base resolution). Palette
 * sprites keep the original semantics of Surface::blitRaw: index 0 is
 * transparent, `shade` darkens within the 16-entry color group, `newBaseColor`
 * replaces the color group, `half` draws only the right half of the sprite.
 */
class HdCanvas
{
public:
	virtual ~HdCanvas() {}

	/// Width of the canvas in world pixels.
	virtual int getWidth() const = 0;
	/// Height of the canvas in world pixels.
	virtual int getHeight() const = 0;
	/// The whole canvas area as a clip rectangle.
	GraphSubset fullArea() const { return GraphSubset(getWidth(), getHeight()); }

	/// Clears the canvas to a palette color.
	virtual void fill(Uint8 color) = 0;
	/// Clears the canvas to a vertical gradient around a palette color (Options::oxceHdBackdrop): darker at the top,
	/// the color itself in the middle, a pale haze at the bottom. A palette canvas has only the flat color.
	/// @param rgb 0xRRGGBB of the middle color when the mod's table names one (hd/backdrop.txt), else -1: the palette color's own.
	virtual void fillBackdrop(Uint8 color, int rgb = -1) { (void)rgb; fill(color); }
	/// The color 0xRRGGBB the last fillBackdrop gives to the row y (the beyond-edge ground fades into it, XP-000263);
	/// -1 when the last fill was flat or the canvas is a palette one.
	virtual int backdropAt(int y) const { (void)y; return -1; }
	/// Draws a palette sprite (Surface::blitRaw semantics).
	virtual void blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, bool half = false, int newBaseColor = 0) = 0;
	/// Draws a palette sprite clipped to a rectangle (Surface::blitNShade(range) semantics).
	virtual void blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, GraphSubset range) = 0;
	/// Draws a unit or item sprite through its Y-script worker, clipped to a rectangle (ScriptWorkerBlit::executeBlit semantics).
	/// `unlit` is the same script filled with shade 0 (the worker holds its shade): it tells the light from
	/// the script's own work for an HD frame in its own colours; nullptr where there is no light.
	virtual void blitScripted(ScriptWorkerBlit &work, const Surface *src, int x, int y, int shade, GraphSubset range, ScriptWorkerBlit *unlit = nullptr) = 0;
	/// Draws a classic base-resolution element scaled by k (HdBlit::blitScaled semantics).
	virtual void blitClassic(Surface *src, int x, int y, int scale, int shade = 0, int newBaseColor = 0) = 0;
	/// Draws one vapor particle: every pixel of the pattern whose threshold is >= size is tinted
	/// (palette canvas: through the transparency lookup table; true-color canvas: dest * tint.alpha + tint.rgb).
	virtual void drawVapor(SurfaceRaw<int> pattern, int x, int y, int size, const Uint8 *transparencyLUT, SDL_Color tint) = 0;
	/// HD modes: one vapor particle as a soft round puff instead of the 2x2 pattern. The centre is in 1/16 of a
	/// screen pixel, `size` is the particle size 0..3 (the classic pattern covers (4 - size) of its 4 cells),
	/// k the HD scale. The tint is already interpolated by the caller. The classic canvas is never asked.
	virtual void drawVaporSoft(int cx16, int cy16, int size, int k, SDL_Color tint) { (void)cx16; (void)cy16; (void)size; (void)k; (void)tint; }
	/// The blast flash: every drawn pixel jumps to the brightest shade of its color group.
	virtual void flash() = 0;

	/// Locks the canvas for direct access (matches Surface::lock, a no-op for software surfaces).
	virtual void lock() {}
	/// Unlocks the canvas.
	virtual void unlock() {}
	/// Writes the canvas content as an RGB PNG (HD render test dumps).
	virtual bool saveDump(const std::string &filename) = 0;
	/// The palette the map draws with (true-color canvases convert indices with it; no-op otherwise).
	virtual void setPalette(const SDL_Color *colors, int firstcolor, int ncolors) {}
	/// The SDL surface holding the canvas (8-bit for Canvas8, 32-bit for Canvas32).
	virtual SDL_Surface *getSdlSurface() = 0;
	/// Name of the canvas type (for the HD render test dumps).
	virtual const char *getName() const = 0;
	/// Finishes any deferred drawing so that the surface holds the frame (no-op for an immediate canvas).
	virtual void flush() {}
	/// The light over the tile the next blits belong to (nullptr: none; no effect on the classic canvas).
	virtual void setLight(const HdLight *light) {}
	/// Selects how palette sprites are drawn (see HdMode; no effect on the classic canvas).
	virtual void setHdMode(int mode) {}
	/// The mode palette sprites are drawn with (always HD_MODE_NEAREST on the classic canvas).
	virtual int getHdMode() const { return HD_MODE_NEAREST; }
	/// HD render: the floor blits that follow are the ground of map cell (x, y, z) (on = false: they are
	/// not). A pack frame with variants (hd/TERRAIN/<set>/<index>.v1.png ...) is then drawn as the variant
	/// of that place, or a blend of two at the edge of a patch (no effect on the classic canvas). The
	/// pattern runs along a scale with the frame itself in the middle, the odd variants on one side of it
	/// (v1 next to it, v3 beyond) and the even ones on the other (v2, v4).
	virtual void setGroundCell(bool on, int x, int y, int z) {}
	/// HD render: the seed of this battle's pattern of ground variants.
	virtual void setGroundSeed(Uint32 seed) {}
	/// HD render: the blits that follow draw variant `variant` of a pack frame when it has one (0 = the
	/// frame itself). The fire uses variant 1 as the picture half a step after the frame.
	virtual void setFrameVariant(int variant) {}
	/// HD render: the map's field of wall pictures (SCC addressing; nullptr: none). It must outlive the canvas use.
	virtual void setWallField(const HdWallField *field) {}
	/// HD render: the wall blits that follow are wall `part` (HdSprites::WALL_WEST / WALL_NORTH, 0 = not a
	/// wall) of map cell (x, y, z), drawn by path `path` of Map::drawTerrain (1..6: W1, W2, N1..N4; test logs
	/// only). An addressed frame then draws the picture the field gives that cell (no effect on the classic canvas).
	virtual void setCellAddress(int part, int x, int y, int z, int path) {}
	/// HD render: draws a true-color frame as it is (combat effects, see HdFx; no effect on the classic
	/// canvas). The frame must stay alive until the canvas is flushed.
	virtual void blitFrame(const HdFrame &hd, int x, int y) {}
};

/**
 * The classic canvas: draws indices into an 8-bit palette surface with the
 * engine's original blitters, byte for byte what the game did before the HD
 * renderer existed.
 */
class Canvas8 : public HdCanvas
{
private:
	Surface *_target;
public:
	/// Wraps an 8-bit surface.
	Canvas8(Surface *target) : _target(target) {}
	int getWidth() const override { return _target->getWidth(); }
	int getHeight() const override { return _target->getHeight(); }
	void fill(Uint8 color) override;
	void blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, bool half = false, int newBaseColor = 0) override;
	void blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, GraphSubset range) override;
	void blitScripted(ScriptWorkerBlit &work, const Surface *src, int x, int y, int shade, GraphSubset range, ScriptWorkerBlit *unlit = nullptr) override;
	void blitClassic(Surface *src, int x, int y, int scale, int shade = 0, int newBaseColor = 0) override;
	void drawVapor(SurfaceRaw<int> pattern, int x, int y, int size, const Uint8 *transparencyLUT, SDL_Color tint) override;
	void flash() override;
	void lock() override { _target->lock(); }
	void unlock() override { _target->unlock(); }
	bool saveDump(const std::string &filename) override;
	SDL_Surface *getSdlSurface() override { return _target->getSurface(); }
	const char *getName() const override { return "Canvas8"; }
};

/**
 * The true-color canvas: palette sprites are converted through the map's
 * palette as they are drawn (same shading rules as Canvas8, so the picture is
 * identical), and the result is a 32-bit surface the world layer takes as is.
 * Transparent margins of palette sprites are skipped with per-frame span
 * tables, which is what makes the k-scaled battlescape fast.
 *
 * In the HD modes a palette frame that has an HD frame (from a mod's pack, or
 * smoothed by the engine with xBRZ) is drawn from that instead: alpha blended,
 * with the tile shade applied as a tone curve calibrated from the palette's
 * own color ramps, and posterized back to a palette color group when the
 * night-vision recolor asks for one.
 *
 * Drawing is deferred: the calls record commands, and flush() (called by the
 * map at the end of a frame, and by anything that reads the pixels) executes
 * them in horizontal strips on all cores. Sources of recorded sprite blits
 * must stay unchanged until the flush (sprite frames do); sources that are
 * rewritten between calls (classic UI elements, script results) are copied.
 */
class Canvas32 : public HdCanvas
{
	/// Draws the recorded commands on the video card (option oxceHdGpu): it reads them and the tables.
	friend class HdGpuCanvas;
private:
	/// Non-transparent extent [begin, end) of one sprite row.
	struct Span { Uint16 begin, end; };
	struct SpanTable { int width, height; std::vector<Span> rows; };
	/// One recorded drawing call.
	struct Cmd
	{
		enum Type : Uint8 { FILL, BLIT, BLIT_HD, BLIT_HD_LIT, BLIT_SCALED, VAPOR, FLASH, FILL_BACKDROP, VAPOR_SOFT };
		Type type;
		Uint8 color;
		Uint8 newBaseColor;
		Sint16 shade;
		int x, y;
		int scale;
		/// BLIT: a stable sprite frame and its span table.
		SurfaceRaw<const Uint8> src;
		const SpanTable *spans;
		/// BLIT_SCALED (8-bit indices, pitch = srcW) and VAPOR (ints): offset into the arena.
		size_t arena;
		int srcW, srcH;
		const HdFrame *hd;
		GraphSubset srcDomain;
		GraphSubset clip;
		SDL_Color tint;
		/// FILL_BACKDROP: the colors of the top, the middle and the bottom row (r, g, b).
		Uint8 backdrop[3][3];
		int size;
		/// VAPOR: the palette transparency table of the classic canvas (exact colors in HD_MODE_NEAREST).
		const Uint8 *transparencyLUT;
		/// Dest rows the command can touch (strip culling).
		int y0, y1;
		/// BLIT_HD_LIT: node shades (8.8 fixed) and tints of the light field; tintFlat: all node tints equal.
		Uint16 lightShade[HdLight::NODES];
		Uint8 lightTint[HdLight::NODES][3];
		bool tintFlat;
	};
	/// Per-pixel weights of a frame size: the quadrant of the diamond the pixel is in and the bilinear
	/// weights of that quadrant's four nodes (sum 256); 5 bytes per pixel.
	struct LightWeights { int width, height; std::vector<Uint8> w; };

	Surface::UniqueBufferPtr _buffer;
	Surface::UniqueSurfacePtr _surface;
	int _width, _height;
	/// HD scale k the palette sprites were upscaled by (sprite width / 32).
	int _scale;
	int _hdMode;
	SDL_Color _colors[256];
	Uint32 _lut[256];
	/// Pixel -> palette index, for the ops the classic canvas does on indices (vapor, flash):
	/// sorted (pixel << 8 | index) of the entries 1..255, first index of a repeated color.
	std::vector<Uint64> _paletteIndexOf;
	Uint32 _shadeLut[17][256];
	/// The same with the color group replaced (helper::ColorReplace): [newBaseColor - 1][shade].
	Uint32 _recolorLut[16][17][256];
	/// Shading factor (16.16 fixed point) of every channel and shade by the pixel's brightest channel, calibrated from the palette ramps.
	Uint32 _toneFactor[3][17][256];
	/// Luminance -> palette ramp level 0..15 (for the night-vision recolor of HD pixels).
	Uint8 _level[256];
	int _rshift, _gshift, _bshift;
	/// Base-resolution scratch frames the unit/item scripts run on (_scriptLit: the same script
	/// without the light, for a pack frame in its own colours).
	Surface _scriptSrc, _scriptDst, _scriptLit;
	std::unordered_map<const void*, SpanTable> _spans;
	/// xBRZ-smoothed frames made on demand (key: frame buffer, or the hash of a scripted result).
	/// Trimmed by the flushes that used them longest ago once they hold more than their cap (see trimSmooth).
	struct SmoothEntry
	{
		HdFrame frame;
		Uint32 used = 0;
	};
	std::unordered_map<const void*, SmoothEntry> _smooth;
	std::unordered_map<Uint64, SmoothEntry> _smoothScripted;
	/// The number of the flush being recorded (the `used` of the smoothed frames), and their bytes.
	Uint32 _smoothClock = 1;
	size_t _smoothBytes = 0;
	/// The end of a flush: the smoothed frames used longest ago go while the caches are over their cap.
	void trimSmooth();
	void clearSmooth();
	/// HD frames with a shade already applied, so that a shaded HD blit is a plain alpha copy (LRU, capped by size).
	/// The shade of a copy lit by a light field with a gradient (see litFor): the field is in the key.
	static const int TONED_LIT = -1;
	struct TonedKey
	{
		const HdFrame *frame;
		int shade;
		/// TONED_LIT: the node shades and tints of the light field (as in Cmd), zero otherwise.
		Uint16 lightShade[HdLight::NODES];
		Uint8 lightTint[HdLight::NODES][3];
		bool operator==(const TonedKey &o) const
		{
			return frame == o.frame && shade == o.shade && (shade != TONED_LIT ||
				(!memcmp(lightShade, o.lightShade, sizeof(lightShade)) && !memcmp(lightTint, o.lightTint, sizeof(lightTint))));
		}
	};
	struct TonedKeyHash
	{
		size_t operator()(const TonedKey &k) const
		{
			size_t h = std::hash<const void*>()(k.frame) ^ (size_t)k.shade * 0x9E3779B9u;
			if (k.shade == TONED_LIT)
			{
				const Uint8 *b = (const Uint8*)k.lightShade;
				for (size_t i = 0; i < sizeof(k.lightShade); ++i)
				{
					h = (h ^ b[i]) * 1099511628211ull;
				}
				b = &k.lightTint[0][0];
				for (size_t i = 0; i < sizeof(k.lightTint); ++i)
				{
					h = (h ^ b[i]) * 1099511628211ull;
				}
			}
			return h;
		}
	};
	struct TonedEntry
	{
		HdFrame frame;
		std::list<TonedKey>::iterator lru;
		/// _tonedFrame of the last frame that drew this copy.
		unsigned used = 0;
	};
	std::unordered_map<TonedKey, TonedEntry, TonedKeyHash> _toned;
	std::list<TonedKey> _tonedLru;
	size_t _tonedBytes = 0;
	/// Counts the flushes: the copies the frame being recorded uses are not trimmed after it.
	unsigned _tonedFrame = 1;
	/// HdSprites::generation() the shaded copies and the ground blends were checked against (see forgetChanged).
	unsigned _tonedGeneration = 0;
	/// The registry changed while recording: what changed is dropped at the end of the flush (see tonedFor).
	bool _tonedStale = false;
	/// The generation the changes below were taken at (_tonedGeneration while there are none): the frames
	/// and keys that changed - their copies and blends are one-offs until the end of the flush - or everything.
	unsigned _changedGeneration = 0;
	std::unordered_set<const void*> _changedFrames, _changedKeys;
	bool _changedAll = false;
	/// Takes the changes of the registry since _tonedGeneration (when the caches hold anything).
	void noticeChanges();
	/// The end of a flush: the shaded copies and the ground blends of what changed go, the rest is checked against the new generation.
	void forgetChanged();
	/// Shaded copies made while the cache is stale (dropped with it).
	std::deque<HdFrame> _tonedTransient;
	/// A shaded copy the recording reserved: the workers fill it before the commands run (makeJobs).
	struct TonedJob
	{
		const HdFrame *src;
		HdFrame *out;
		int shade;
		Uint16 tintKey;
		/// In the cache under `key` (not a one-off copy of a stale cache).
		bool cached;
		TonedKey key;
		/// TONED_LIT: the corner weights of the frame's size (see lightWeightsFor).
		const Uint8 *weights;
	};
	std::vector<TonedJob> _tonedJobs;
	/// Fills a reserved shaded copy (on a worker).
	void makeToned(const TonedJob &job) const;
	/// One pixel of a shaded copy: the tone curve by its brightest channel, then the light color (5 bits per channel, 31 = full).
	struct ToneOf
	{
		const Uint32 *toneR, *toneG, *toneB;
		Uint16 tintKey;
		Uint32 tr, tg, tb;
		ToneOf(const Canvas32 &canvas, int shade, Uint16 tint);
		Uint32 operator()(Uint32 p) const
		{
			if (!(p >> 24))
			{
				return 0;
			}
			Uint32 r = (p >> 16) & 0xFF, g = (p >> 8) & 0xFF, b = p & 0xFF;
			const Uint32 m = r > g ? (r > b ? r : b) : (g > b ? g : b);
			r = (r * toneR[m] + 32768u) >> 16;
			g = (g * toneG[m] + 32768u) >> 16;
			b = (b * toneB[m] + 32768u) >> 16;
			if (tintKey != 0x7FFF)
			{
				r = (r * tr + 32768u) >> 16;
				g = (g * tg + 32768u) >> 16;
				b = (b * tb + 32768u) >> 16;
			}
			return (p & 0xFF000000u) | (r << 16) | (g << 8) | b;
		}
	};
	/// One pixel under a light field with a gradient: the shade and the light color interpolated from the four
	/// nodes of the pixel's quadrant (its 5 weight bytes, see LightWeights), alpha kept - the same for the blit
	/// and for the lit copy it is drawn from.
	struct LitOf
	{
		const Uint32 (*toneFactor)[17][256];
		const Uint16 *shade;
		const Uint8 (*tint)[3];
		bool tintFlat, whiteTint;
		Uint32 flatTint[3];
		LitOf(const Canvas32 &canvas, const Uint16 *lightShade, const Uint8 (*lightTint)[3], bool tintFlat);
		inline Uint32 operator()(Uint32 p, const Uint8 *wq) const;
	};
	/// True when the canvas pixel layout is 0x00RRGGBB, the layout of HD frames (plain copies possible).
	bool _argbLayout;
	/// The light field of the tile being drawn (HD modes).
	HdLight _light;
	bool _hasLight = false;
	std::unordered_map<Uint32, LightWeights> _lightWeights;
	/// The recorded frame.
	std::vector<Cmd> _cmds;
	/// HdSprites::generation() when the first of _cmds was recorded (see flush).
	unsigned _cmdsGeneration = 0;
	/// The stops of the last fillBackdrop (top, middle, bottom), for backdropAt; _backdropOn is false after a flat fill.
	Uint8 _backdropStops[3][3] = {};
	bool _backdropOn = false;
	std::vector<Uint8> _arena;
	std::vector<int> _arenaInt;

	/// Measurement: bytes held by the smoothed-frame caches, and the periodic cache report.
	size_t smoothBytes() const;
	void perfReport();
	Uint32 _perfLast = 0;

	void rebuildTables();
	void rebuildToneTables();
	const SpanTable &spansFor(SurfaceRaw<const Uint8> src);
	/// The HD frame to draw for a palette frame in the current mode, or nullptr for the nearest path.
	const HdFrame *hdFrameFor(SurfaceRaw<const Uint8> src);
	/// The xBRZ-smoothed frame of a nearest-scaled palette frame (cached).
	const HdFrame *smoothFor(SurfaceRaw<const Uint8> src);
	/// Smooths a k-scaled palette frame with xBRZ; false when it cannot be (k outside 2..6).
	bool smoothFrame(SurfaceRaw<const Uint8> src, HdFrame &out);
	/// Smooths a base-resolution palette sprite k times with xBRZ (checkerboards become alpha first).
	bool smoothBase(const Uint8 *idx, int bw, int bh, int pitch, HdFrame &out);
	/// The frame with the shade (and a light color) applied to its colors (cached), or the frame itself at shade 0 and white light.
	const HdFrame *tonedFor(const HdFrame &hd, int shade, Uint16 tintKey = 0x7FFF);
	/// The frame lit by the light field of the command (cached with the shaded copies), or nullptr: drawn lit per pixel.
	const HdFrame *litFor(const HdFrame &hd, const Cmd &cmd, const LightWeights &weights);
	/// A lit copy did not fit the cap this frame: the trim at the end of the flush makes room (see flush).
	bool _litRefused = false;
	/// The corner weights of every pixel of a frame of this size (built once per size).
	const LightWeights &lightWeightsFor(int width, int height);
	/// Records an HD blit lit by the current light field (or a flat/tinted one when the field is flat).
	void recordHdLit(Cmd &cmd, const HdFrame &hd, int shade);
	void doBlitHdLit(const Cmd &cmd, GraphSubset destClip);
	/// Forgets the shaded copies (the frames they were made from are gone or the palette changed).
	void clearToned();
	/// Records a command (or runs it at once when not deferred).
	void record(Cmd &cmd);
	/// Ground variants: the map cell the next floor blits belong to (see setGroundCell).
	bool _groundOn = false;
	int _groundX = 0, _groundY = 0, _groundZ = 0;
	Uint32 _groundSeed = 0;
	/// The variant the next blits draw (setFrameVariant).
	int _frameVariant = 0;
	/// SCC wall addressing: the map's field and the wall cell the next blits belong to (setCellAddress).
	const HdWallField *_wallField = nullptr;
	int _cellPart = 0, _cellX = 0, _cellY = 0, _cellZ = 0, _cellPath = 0;
	/// The picture of an addressed wall frame for the current wall cell, or the frame itself.
	const HdFrame *wallFrameFor(SurfaceRaw<const Uint8> src, const HdFrame *hd, bool half);
	/// Test log (OXCE_HD_ADDRESS_TRACE): a blit made under a wall cell label by another branch than the wall one.
	void traceForeign(const void *key, const char *branch);
	/// A blend of two variants made for one map cell.
	struct GroundEntry
	{
		HdFrame frame;
		const void *src = nullptr;
		int x = 0, y = 0, z = 0;
		/// _tonedGeneration it is good for (0: to drop - a changed frame or an old pattern).
		unsigned generation = 0;
		size_t lru = 0;
		/// The shade made into the blend (a TonedKey shade, GROUND_RAW: none).
		int tone = 0;
	};
	/// The tone of a ground blend drawn as it is (gradient light, a recolour, shade 0 in white light).
	static const int GROUND_RAW = 0x7FFF << 8;
	/// The tone the next floor blit draws its blend at: shaded blends are made shaded, not kept beside a shaded copy.
	int groundToneFor(int shade, int newBaseColor) const;
	std::unordered_map<Uint64, GroundEntry> _ground;
	/// Blends that could not go into the cache (a key clash): dropped at the end of the flush.
	std::deque<HdFrame> _groundTransient;
	size_t _groundBytes = 0;
	size_t _groundClock = 0;
	/// _groundClock when the frame being recorded began: blends stamped after it are in view.
	size_t _groundFrameFrom = 0;
	/// The frame to draw for a pack frame on the current ground cell: one of its variants, a blend of
	/// two, or the frame itself (no variants, not ground). A blend is made at `tone` (`toned` is set):
	/// the rest are the caller's to shade.
	const HdFrame *groundFrameFor(SurfaceRaw<const Uint8> src, const HdFrame &base, int tone, bool &toned);
	/// A ground blend the recording reserved: the workers fill it before the commands run (makeJobs).
	struct GroundJob
	{
		HdFrame *out;
		/// The variants along the pattern's scale.
		const HdFrame *frames[16];
		int count;
		int x, y, z;
		Uint32 seed;
		/// The shade made into the blend (GROUND_RAW: none).
		int tone;
		/// In the cache under `key` (not a one-off blend of a key clash).
		bool cached;
		Uint64 key;
	};
	std::vector<GroundJob> _groundJobs;
	/// HdSprites::generation() when the first waiting job was reserved: the frames they read belong to it.
	unsigned _jobsGeneration = 0;
	/// Fills a reserved ground blend (on a worker).
	void makeGround(const GroundJob &job) const;
	/// Fills the reserved blends, then the shaded copies (some are copies of the blends), on the workers.
	void makeJobs();
	/// Drops the reserved frames unfilled (the registry changed under them: their sources may be gone).
	void dropJobs();
	/// Drops the blends of changed frames and the oldest ones over the cap (end of a flush).
	void trimGround();
	/// Runs one command on the rows [y0, y1).
	void execute(const Cmd &cmd, int y0, int y1);
	void doFill(Uint8 color, int y0, int y1);
	void doFillBackdrop(const Cmd &cmd, int y0, int y1);
	void doBlit(SurfaceRaw<const Uint8> src, const SpanTable &spans, GraphSubset srcDomain, int x, int y, const Uint32 *table, GraphSubset destClip);
	void doBlitHd(const HdFrame &hd, int x, int y, int shade, GraphSubset srcDomain, int newBaseColor, GraphSubset destClip);
	void doBlitScaled(const Uint8 *src, int srcW, int srcH, int x, int y, int scale, int shade, int newBaseColor, GraphSubset destClip);
	/// Index -> pixel table of a classic blit: a prepared one, or built into `scratch` for a rare shade.
	const Uint32 *classicTable(int shade, int newBaseColor, Uint32 *scratch) const;
	void doVapor(const int *pattern, int w, int h, int x, int y, int size, SDL_Color tint, const Uint8 *transparencyLUT, GraphSubset destClip);
	void doVaporSoft(int cx16, int cy16, int size, int k, SDL_Color tint, GraphSubset destClip);
	/// Radius of a soft vapor puff in 1/16 of a screen pixel.
	static int vaporSoftRadius16(int size, int k);
	void doFlash(int y0, int y1);
	/// The palette index 1..255 whose color the pixel is, or -1.
	int paletteIndexOf(Uint32 pixel) const;
	Uint32 *rowPtr(int y) { return (Uint32*)((Uint8*)_surface->pixels + (size_t)y * _surface->pitch); }
	Uint32 pack(int r, int g, int b) const { return ((Uint32)r << _rshift) | ((Uint32)g << _gshift) | ((Uint32)b << _bshift); }
public:
	/// Creates a true-color canvas of the given size (world pixels) for sprites scaled k times.
	Canvas32(int width, int height, int scale = 1);
	~Canvas32() override;
	int getWidth() const override { return _width; }
	int getHeight() const override { return _height; }
	void fill(Uint8 color) override;
	void fillBackdrop(Uint8 color, int rgb = -1) override;
	int backdropAt(int y) const override;
	void blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, bool half = false, int newBaseColor = 0) override;
	void blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, GraphSubset range) override;
	void blitScripted(ScriptWorkerBlit &work, const Surface *src, int x, int y, int shade, GraphSubset range, ScriptWorkerBlit *unlit = nullptr) override;
	void blitClassic(Surface *src, int x, int y, int scale, int shade = 0, int newBaseColor = 0) override;
	void drawVapor(SurfaceRaw<int> pattern, int x, int y, int size, const Uint8 *transparencyLUT, SDL_Color tint) override;
	void drawVaporSoft(int cx16, int cy16, int size, int k, SDL_Color tint) override;
	void flash() override;
	bool saveDump(const std::string &filename) override;
	void setPalette(const SDL_Color *colors, int firstcolor, int ncolors) override;
	/// The surface with the drawn frame (executes pending commands first).
	SDL_Surface *getSdlSurface() override;
	const char *getName() const override { return "Canvas32"; }
	void setHdMode(int mode) override;
	int getHdMode() const override { return _hdMode; }
	void setLight(const HdLight *light) override;
	void setGroundCell(bool on, int x, int y, int z) override { _groundOn = on; _groundX = x; _groundY = y; _groundZ = z; }
	void setGroundSeed(Uint32 seed) override;
	void setFrameVariant(int variant) override { _frameVariant = variant; }
	void setWallField(const HdWallField *field) override { _wallField = field; }
	void setCellAddress(int part, int x, int y, int z, int path) override { _cellPart = part; _cellX = x; _cellY = y; _cellZ = z; _cellPath = path; }
	void blitFrame(const HdFrame &hd, int x, int y) override;
	/// The ground pattern at point (u, v) of level z (tiles; u along the map's x, v along its y) for
	/// `count` variants: 0 .. count - 1, continuous (exposed for tests).
	static float groundLevel(Uint32 seed, float u, float v, int z, int count);
	/// Executes the recorded commands in parallel strips; nothing is pending afterwards.
	void flush() override;
	/// Copies the drawn frame into a same-format 32-bit surface at (x, y), rows in parallel.
	void copyTo(SDL_Surface *dest, int x, int y);
	/// The same into a w x h area (bilinear: the battle view zoom), enlarged `zoom` times more with `pull`
	/// of the way to the point (fx, fy) in the middle and black bars `bars` of the height at the top and
	/// the bottom (see HdKillCam).
	void copyZoomed(SDL_Surface *dest, int x, int y, int w, int h, double fx, double fy, double zoom, double pull, double bars);
	/// Gives the canvas another size, keeping its tables and caches (the battle view zoom); the pixels are not kept.
	void resize(int width, int height);
};

}
