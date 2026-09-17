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
#include <deque>
#include <list>
#include <string>
#include <vector>
#include <unordered_map>
#include <SDL.h>
#include "Surface.h"
#include "GraphSubset.h"
#include "HdSprites.h"

namespace OpenXcom
{

class ScriptWorkerBlit;

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
	/// Draws a palette sprite (Surface::blitRaw semantics).
	virtual void blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, bool half = false, int newBaseColor = 0) = 0;
	/// Draws a palette sprite clipped to a rectangle (Surface::blitNShade(range) semantics).
	virtual void blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, GraphSubset range) = 0;
	/// Draws a unit or item sprite through its Y-script worker, clipped to a rectangle (ScriptWorkerBlit::executeBlit semantics).
	virtual void blitScripted(ScriptWorkerBlit &work, const Surface *src, int x, int y, int shade, GraphSubset range) = 0;
	/// Draws a classic base-resolution element scaled by k (HdBlit::blitScaled semantics).
	virtual void blitClassic(Surface *src, int x, int y, int scale, int shade = 0, int newBaseColor = 0) = 0;
	/// Draws one vapor particle: every pixel of the pattern whose threshold is >= size is tinted
	/// (palette canvas: through the transparency lookup table; true-color canvas: dest * tint.alpha + tint.rgb).
	virtual void drawVapor(SurfaceRaw<int> pattern, int x, int y, int size, const Uint8 *transparencyLUT, SDL_Color tint) = 0;
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
	void blitScripted(ScriptWorkerBlit &work, const Surface *src, int x, int y, int shade, GraphSubset range) override;
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
private:
	/// Non-transparent extent [begin, end) of one sprite row.
	struct Span { Uint16 begin, end; };
	struct SpanTable { int width, height; std::vector<Span> rows; };
	/// One recorded drawing call.
	struct Cmd
	{
		enum Type : Uint8 { FILL, BLIT, BLIT_HD, BLIT_HD_LIT, BLIT_SCALED, VAPOR, FLASH };
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
		int size;
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
	bool _deferred;
	SDL_Color _colors[256];
	Uint32 _lut[256];
	Uint32 _shadeLut[17][256];
	/// Shading factor (16.16 fixed point) of every channel and shade by the pixel's brightest channel, calibrated from the palette ramps.
	Uint32 _toneFactor[3][17][256];
	/// Luminance -> palette ramp level 0..15 (for the night-vision recolor of HD pixels).
	Uint8 _level[256];
	int _rshift, _gshift, _bshift;
	/// Base-resolution scratch frames the unit/item scripts run on.
	Surface _scriptSrc, _scriptDst;
	std::unordered_map<const void*, SpanTable> _spans;
	/// xBRZ-smoothed frames made on demand (key: frame buffer, or the hash of a scripted result).
	std::unordered_map<const void*, HdFrame> _smooth;
	std::unordered_map<Uint64, HdFrame> _smoothScripted;
	/// HD frames with a shade already applied, so that a shaded HD blit is a plain alpha copy (LRU, capped by size).
	struct TonedKey
	{
		const HdFrame *frame;
		int shade;
		bool operator==(const TonedKey &o) const { return frame == o.frame && shade == o.shade; }
	};
	struct TonedKeyHash
	{
		size_t operator()(const TonedKey &k) const { return std::hash<const void*>()(k.frame) ^ (size_t)k.shade * 0x9E3779B9u; }
	};
	struct TonedEntry
	{
		HdFrame frame;
		std::list<TonedKey>::iterator lru;
	};
	std::unordered_map<TonedKey, TonedEntry, TonedKeyHash> _toned;
	std::list<TonedKey> _tonedLru;
	size_t _tonedBytes = 0;
	unsigned _tonedGeneration = 0;
	/// The registry changed while recording: the cache is cleared at the end of the flush (see tonedFor).
	bool _tonedStale = false;
	/// Shaded copies made while the cache is stale (dropped with it).
	std::deque<HdFrame> _tonedTransient;
	/// True when the canvas pixel layout is 0x00RRGGBB, the layout of HD frames (plain copies possible).
	bool _argbLayout;
	/// The light field of the tile being drawn (HD modes).
	HdLight _light;
	bool _hasLight = false;
	std::unordered_map<Uint32, LightWeights> _lightWeights;
	/// The recorded frame.
	std::vector<Cmd> _cmds;
	std::vector<Uint8> _arena;
	std::vector<int> _arenaInt;

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
	/// A blend of two variants made for one map cell.
	struct GroundEntry
	{
		HdFrame frame;
		const void *src = nullptr;
		int x = 0, y = 0, z = 0;
		unsigned generation = 0;
		size_t lru = 0;
	};
	std::unordered_map<Uint64, GroundEntry> _ground;
	/// Blends that could not go into the cache (a key clash): dropped at the end of the flush.
	std::deque<HdFrame> _groundTransient;
	size_t _groundBytes = 0;
	size_t _groundClock = 0;
	/// The frame to draw for a pack frame on the current ground cell: one of its variants, a blend of
	/// two, or the frame itself (no variants, not ground).
	const HdFrame *groundFrameFor(SurfaceRaw<const Uint8> src, const HdFrame &base);
	/// Drops the blends of an old registry generation and the oldest ones over the cap (end of a flush).
	void trimGround();
	/// Runs one command on the rows [y0, y1).
	void execute(const Cmd &cmd, int y0, int y1);
	void doFill(Uint8 color, int y0, int y1);
	void doBlit(SurfaceRaw<const Uint8> src, const SpanTable &spans, GraphSubset srcDomain, int x, int y, const Uint32 *table, GraphSubset destClip);
	void doBlitHd(const HdFrame &hd, int x, int y, int shade, GraphSubset srcDomain, int newBaseColor, GraphSubset destClip);
	void doBlitScaled(const Uint8 *src, int srcW, int srcH, int x, int y, int scale, int shade, int newBaseColor, GraphSubset destClip);
	void doVapor(const int *pattern, int w, int h, int x, int y, int size, SDL_Color tint, GraphSubset destClip);
	void doFlash(int y0, int y1);
	Uint32 *rowPtr(int y) { return (Uint32*)((Uint8*)_surface->pixels + (size_t)y * _surface->pitch); }
	Uint32 pack(int r, int g, int b) const { return ((Uint32)r << _rshift) | ((Uint32)g << _gshift) | ((Uint32)b << _bshift); }
public:
	/// Creates a true-color canvas of the given size (world pixels) for sprites scaled k times.
	Canvas32(int width, int height, int scale = 1);
	int getWidth() const override { return _width; }
	int getHeight() const override { return _height; }
	void fill(Uint8 color) override;
	void blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, bool half = false, int newBaseColor = 0) override;
	void blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, GraphSubset range) override;
	void blitScripted(ScriptWorkerBlit &work, const Surface *src, int x, int y, int shade, GraphSubset range) override;
	void blitClassic(Surface *src, int x, int y, int scale, int shade = 0, int newBaseColor = 0) override;
	void drawVapor(SurfaceRaw<int> pattern, int x, int y, int size, const Uint8 *transparencyLUT, SDL_Color tint) override;
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
	/// The ground pattern at point (u, v) of level z (tiles; u along the map's x, v along its y) for
	/// `count` variants: 0 .. count - 1, continuous (exposed for tests).
	static float groundLevel(Uint32 seed, float u, float v, int z, int count);
	/// Executes the recorded commands in parallel strips; nothing is pending afterwards.
	void flush() override;
	/// Copies the drawn frame into a same-format 32-bit surface at (x, y), rows in parallel.
	void copyTo(SDL_Surface *dest, int x, int y);
	/// Records commands (default) or draws each call at once (tests, single-threaded use).
	void setDeferred(bool deferred);
	/// The shaded value of a grey pixel (exposed for tests).
	Uint8 toneValue(int shade, int value, int channel = 1) const { return (Uint8)(((Uint32)value * _toneFactor[channel][shade][value] + 32768u) >> 16); }
};

}
