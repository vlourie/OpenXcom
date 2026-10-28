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
	/// HdUi::drawImage: w x h 0xAARRGGBB (rows `pitch` pixels apart) drawn at (x, y), straight alpha;
	/// `copy` (HdUi::copyRows) - the pixels as they are, alpha too.
	bool image(const Uint32 *argb, int pitch, int w, int h, int x, int y, bool copy = false);
	/// HdUi::blendGlyph: w x h coverages (rows `pitch` apart) at (x, y) in `color`, coverage c blended as lut[c].
	bool glyph(const Uint8 *cov, int pitch, int w, int h, int x, int y, Uint32 color, const float *lut);
	/// HdUi::blendSpan runs of a shape, in their order.
	bool spans(const std::vector<Span> &spans);
	/// A coverage per pixel of [x0, x1) x [y0, y1) in `color` (0: untouched) - the triangles and circles of HdUi.
	bool cover(const std::vector<float> &cov, int x0, int y0, int x1, int y1, Uint32 color);
	/// Canvas32::copyTo: the canvas with its top left at (ox, oy), read from `texture` (the framebuffer the card drew
	/// it into) or, when that is 0, from `pixels` (the processor's picture, uploaded).
	bool canvas(unsigned texture, const SDL_Surface *pixels, int ox, int oy, int x0, int y0, int x1, int y1);
	/// Canvas32::copyZoomed: per column of [x0, x1) the source column and the weight of the next, per row of [y0, y1)
	/// the source row (-1: a black bar) and the weight of the next.
	bool canvasZoomed(unsigned texture, const SDL_Surface *pixels, const std::vector<int> &cols, const std::vector<Uint32> &colWeights,
		const std::vector<int> &rows, const std::vector<Uint32> &rowWeights, Uint32 black, int x0, int y0, int x1, int y1);
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
