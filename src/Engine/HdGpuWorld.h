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
#include <vector>
#include <SDL.h>
#include <SDL_thread.h>

namespace OpenXcom
{

struct HdFrame;

/**
 * The world drawn by the video card (option oxceHdGpu, stage 2 of docs/research/gpu-render-plan-2026-10-27.md).
 *
 * Every write into the world of a frame is a call of the HD layer's leaf routines (HdUiArt's blend, HdUi's
 * pixels, spans, glyphs and pictures, the copy of the battle canvas). On a frame of the card those calls are kept
 * in order instead of drawn, with what they read put into the card (frames and glyphs into a texture array once,
 * coverages and tables into a buffer every frame); at the flip one program draws the whole world into the
 * framebuffer, every pixel running through the calls over its tile in order with the formulas of the processor,
 * so the frame is the processor's byte for byte. The processor neither clears, nor draws, nor uploads that world,
 * and the battle canvas the card drew is copied from its framebuffer without coming back.
 *
 * A writer the card cannot take (a callback per pixel, the light of the base, the globe's earth) calls cpu(): on a
 * frame of the card the world drawn so far comes back into the processor's world at once, and the rest of the
 * frame is drawn there, as before. Whether a frame is the card's is decided at its start: the last frames had
 * no such writer. All calls are made on the thread of the GL context.
 *
 * OXCE_HD_GPU_WORLD=0 the processor draws every world, =probe the lowest bit of blue flipped (the control of the dump
 * comparison); OXCE_HD_GPU_VERIFY=1 the processor draws the card's frames too and they are compared at the flip;
 * OXCE_HD_GPU_STATS=1 a line every 5 s (frames of the card and of the processor, what sent them back, the work).
 */
class HdGpuWorld
{
public:
	/// A run of a row (HdUi::blendSpan): the pixels [ia, ib], the coverage of the first, of the last and of those between.
	struct Span
	{
		int y, ia, ib;
		float first, last, inner;
		Uint32 color;
	};
	/// The process-wide instance.
	static HdGpuWorld &instance();
	/// Screen::clear: a frame of `world` starts. True: the card draws it (the processor's world is left as it is,
	/// unless verifying() - then it is drawn there too).
	bool begin(SDL_Surface *world);
	/// The card is drawing this frame and `dest` is its world: the leaf routines hand their writes over.
	bool on(const SDL_Surface *dest) const { return _on && dest == _world && SDL_ThreadID() == _thread; }
	/// The processor draws the card's frames too (OXCE_HD_GPU_VERIFY): a write handed over is still drawn.
	bool verifying() const { return _on && _verify; }
	/// A write the card does not take: on a frame of the card the world comes back to the processor (`who` in the
	/// statistics); on any frame the next ones stay with the processor for a while.
	void cpu(const char *who);
	/// The same for a write into (or a read of) `dest`, when it is the world.
	void cpu(const SDL_Surface *dest, const char *who) { if (dest && dest == _world) cpu(who); }
	/// Screen::flip: true - the card drew the frame into the world's framebuffer (nothing to upload).
	bool end();
	/// The world drawn so far into a 32-bit surface of its size (the HD test dump); false: not a frame of the card.
	bool readInto(SDL_Surface *out);
	/// The writes. False: not taken - the frame went back to the processor, which draws it.
	/// HdUiArt::blendInto of `f` with its top left at (fx, fy), drawn on [x0, x1) x [y0, y1).
	bool frame(const HdFrame &f, int fx, int fy, int x0, int y0, int x1, int y1);
	/// HdUi::drawPixels: w x h palette pixels with the base pixel (0, 0) at world (ox, oy), k world pixels each,
	/// index 0 transparent, `lut` the 256 colours.
	bool pixels(const Uint8 *pixels, int pitch, int w, int h, int ox, int oy, int k, const Uint32 *lut, int x0, int y0, int x1, int y1);
	/// HdUi::fillRect: the rectangle in one colour.
	bool fill(int x0, int y0, int x1, int y1, Uint32 v);
	/// HdUi::drawImage: w x h 0xAARRGGBB (rows `pitch` pixels apart) drawn at (x, y), straight alpha (BLEND, HdUi's
	/// blendPixel); COPY (HdUi::copyRows) - the pixels as they are, alpha too; OVER_INT - straight alpha in integers
	/// of 255 (HdUiArt's blendInto: HdUi::drawGlyph, Screen::composeSmooth).
	enum Image { BLEND, COPY, OVER_INT };
	bool image(const Uint32 *argb, int pitch, int w, int h, int x, int y, Image how = BLEND);
	/// HdUi::blendGlyph: w x h coverages (rows `pitch` apart) at (x, y) in `color`, coverage c blended as lut[c].
	bool glyph(const Uint8 *cov, int pitch, int w, int h, int x, int y, Uint32 color, const float *lut);
	/// HdUi::blendSpan runs of a shape, in their order.
	bool spans(const std::vector<Span> &spans);
	/// A coverage per pixel in `color` over the rows [y0, y1) inside [x0, x1) (0: untouched) - HdUi::shadeCover. `runs`:
	/// per row the two stretches [a0, b0) and [a1, b1) it has coverages for (none: a == b); `cov` those coverages,
	/// row after row, stretch after stretch.
	bool cover(const std::vector<Sint32> &runs, const std::vector<float> &cov, int x0, int y0, int x1, int y1, Uint32 color);
	/// Canvas32::copyTo: the canvas with its top left at (ox, oy), read from `texture` (the framebuffer the card drew
	/// it into) or, when that is 0, from `pixels` (the processor's picture, uploaded).
	bool canvas(unsigned texture, const SDL_Surface *pixels, int ox, int oy, int x0, int y0, int x1, int y1);
	/// Canvas32::copyZoomed: per column of [x0, x1) the source column and the weight of the next, per row of [y0, y1)
	/// the source row (-1 either: black) and the weight of the next; `bright` below 256 - every pixel then
	/// mixed from black by bright of 256 (HdVideo::drawFitted).
	bool canvasZoomed(unsigned texture, const SDL_Surface *pixels, const std::vector<int> &cols, const std::vector<Uint32> &colWeights,
		const std::vector<int> &rows, const std::vector<Uint32> &rowWeights, Uint32 black, int x0, int y0, int x1, int y1, int bright = 256);
	/// The world drawn so far kept in a texture of the world's size, and the frame going on over a copy of it
	/// (CraftLaunchState enlarges the base's view from there: canvas/canvasZoomed with that texture); 0 - not a
	/// frame of the card.
	unsigned snapshot();
	/// HdUi::shadeRows: the blends of a routine per pixel, worked out by the processor. Per row of [y0, y1) `rows`
	/// holds 4 values: where its pixels start in `table`, the stretch [xa, xb) it blends, where its steps start in
	/// `steps`; `table` per pixel of the stretch and one more the index of the pixel's first step (from the row's
	/// first, the next pixel's: past its last); `steps` 2 values a step - the colour, and STEP_256 | a (HdRadar's
	/// blend of a of 256) or the bits of a coverage (HdUi's blendPixel). Each pixel's steps in their order.
	/// The write is made here and the caller fills its data in place: (y1 - y0) * 4 values of rows, then `table`
	/// values, then `steps` values (filled before the frame goes on); nullptr - not taken.
	static const Uint32 STEP_256 = 0x80000000u;
	Uint32 *steps(size_t table, size_t steps, int x0, int y0, int x1, int y1);
	/// HdBaseScene's drawBuilding: `vals` 6 floats a pixel of [x0, x1) x [y0, y1) (reveal, grid, beam, edge, line,
	/// lift); the glow of the pixel's brightness lum is glowLut[min(lutSize - 1, (int)(lum (lutSize - 1) + 0.5))].
	bool building(const std::vector<float> &vals, const float *glowLut, int lutSize, int x0, int y0, int x1, int y1);
	/// CraftLaunchState's alarm over [x0, x1) x [y0, y1), a value a pixel (row after row): each channel c becomes
	/// that of wash[c], then (bits 24-25: 1 or 2) that of stripe1 / stripe2, then the light of bits 16-23, 8-15 and
	/// 0-7 is added to red, green and blue up to 255; a table holds 256 values, the red of value i in its bits
	/// 16-23, the green in 8-15, the blue in 0-7.
	bool alarm(const std::vector<Uint32> &px, const Uint32 *wash, const Uint32 *stripe1, const Uint32 *stripe2, int x0, int y0, int x1, int y1);
	/// The base's routines per pixel, worked out by the processor up to the write: `vals` holds `stride` floats a pixel
	/// of [x0, x1) x [y0, y1) row after row, `col` the colour (0..1, GLOW 0..1 of 255), the pixel's byte b and v = b / 255:
	/// ADD   k: v + col k, OVER k: v + (col - v) k - clamped to 0..1, rounded of 255 (HdBaseScene's blob, HdBaseLife's dot);
	/// MIX   c0 c1 c2 m: b (1 - m) + c m rounded, 0..255 (HdBaseScene's mix);
	/// STAMP p0 p1 p2 p3: none when p3 <= 0.002, else p + v (1 - p3) up to 1, rounded of 255 (the crew's figures);
	/// GLOW_ADD / GLOW_OWN h c: none when h < 0, else HdCraftLights' glow, opaque.
	enum Shade { ADD, OVER, MIX, STAMP, GLOW_ADD, GLOW_OWN };
	bool shade(Shade kind, const std::vector<float> &vals, int x0, int y0, int x1, int y1, const float col[3]);
	/// HdBaseScene::draw's light. The lamps at rest (`key`: their picture `acc` and `glow`, 3 floats a pixel of the area
	/// (ax0, ay0, w, h)), kept on the card until the key changes; per pixel of the area acc and glow from there, then
	/// a += add m, g += glow h per moving lamp, then per pipe g += colour k + white (0.85, 1, 0.75), a *= 1 - darken;
	/// the pixel's channel: curve[min(lutSize - 1, (int)(v a + g) lutSteps), at least 0].
	struct Lamp
	{
		int x0, y0, x1, y1;
		float add[3], glow[3];
		std::vector<float> mh;     ///< m and h per pixel of the box (0 and 0: out of reach)
	};
	struct Pipe
	{
		int x0, y0, x1, y1;
		float colour[3];
		std::vector<float> kwd;    ///< k, white and darken per pixel of the box (0 0 0: none)
	};
	bool light(unsigned long long key, const std::vector<float> &acc, const std::vector<float> &glow, int ax0, int ay0, int w, int h,
		const std::vector<Lamp> &lamps, const std::vector<Pipe> &pipes, const unsigned char *curve, int lutSize, int lutSteps);
	/// The world surface goes (Screen makes a new one): a frame of the card begun on it is dropped, the processor
	/// draws the rest of the frame.
	void forget();
	/// Drops every GL object (the context goes).
	void release();
private:
	HdGpuWorld() = default;
	struct Impl;
	Impl *_impl = nullptr;
	SDL_Surface *_world = nullptr;
	Uint32 _thread = 0;
	bool _on = false, _verify = false;
	Impl &impl();
	/// The writes so far go back to the processor's world; the rest of the frame is the processor's.
	void fallBack(const char *why);
	/// A write not taken: fallBack, and the pictures' array made bigger when it was too small. Always false.
	bool refuse(const char *why);
};

}
