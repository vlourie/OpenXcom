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
#include "HdCanvas.h"
#include "HdSmooth.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <tuple>
#include <unordered_set>
#include "HdBlit.h"
#include "HdTest.h"
#include "Script.h"
#include "ShaderDraw.h"
#include "ShaderMove.h"
#include "HdWorkers.h"
#include "HdUiArt.h"
#include "Logger.h"

namespace OpenXcom
{

void Canvas8::fill(Uint8 color)
{
	ShaderDrawFunc(
		[](Uint8& dest, Uint8 c)
		{
			dest = c;
		},
		ShaderSurface(_target),
		ShaderScalar<Uint8>(color)
	);
}

void Canvas8::blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, bool half, int newBaseColor)
{
	Surface::blitRaw(_target, src, x, y, shade, half, newBaseColor);
}

void Canvas8::blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, GraphSubset range)
{
	// same as Surface::blitNShade(surface, x, y, shade, range)
	ShaderMove<const Uint8> s(src, x, y);
	SurfaceRaw<Uint8> targetRaw(_target);
	ShaderMove<Uint8> d(targetRaw);
	d.setDomain(range);
	ShaderDraw<helper::StandardShade>(d, s, ShaderScalar(shade));
}

void Canvas8::blitScripted(ScriptWorkerBlit &work, const Surface *src, int x, int y, int shade, GraphSubset range)
{
	work.executeBlit(src, _target, x, y, shade, range);
}

void Canvas8::blitClassic(Surface *src, int x, int y, int scale, int shade, int newBaseColor)
{
	HdBlit::blitScaled(_target, src, x, y, scale, shade, newBaseColor);
}

void Canvas8::drawVapor(SurfaceRaw<int> pattern, int x, int y, int size, const Uint8 *transparencyLUT, SDL_Color)
{
	ShaderDrawFunc(
		[&](Uint8& dest, int threshold)
		{
			if (size <= threshold)
			{
				dest = transparencyLUT[dest];
			}
		},
		ShaderSurface(_target),
		ShaderMove(pattern, x, y)
	);
}

void Canvas8::flash()
{
	// the original loop: every non-transparent pixel to the brightest entry of its color group
	for (int x = 0, y = 0; x < _target->getWidth() && y < _target->getHeight();)
	{
		Uint8 pixel = _target->getPixel(x, y);
		if (pixel)
		{
			pixel = (pixel & 0xF0) + 1; //avoid 0 pixel
			_target->setPixelIterative(&x, &y, pixel);
		}
	}
}

bool Canvas8::saveDump(const std::string &filename)
{
	return HdTest::savePngRgb(filename, _target->getSurface());
}

}

namespace OpenXcom
{

/*
 * Canvas32
 */

namespace
{
	/// Pointer to a row of a raw 8-bit surface.
	inline const Uint8 *rawRow(const SurfaceRaw<const Uint8> &s, int y)
	{
		return (const Uint8*)s.getBuffer() + (size_t)y * s.getPitch();
	}
}

Canvas32::Canvas32(int width, int height, int scale) : _width(width), _height(height), _scale(scale < 1 ? 1 : scale), _hdMode(HD_MODE_NEAREST), _deferred(true), _scriptSrc(1, 1), _scriptDst(1, 1)
{
	std::tie(_buffer, _surface) = Surface::NewPair32Bit(width, height);
	SDL_SetColorKey(_surface.get(), 0, 0);
	_rshift = _surface->format->Rshift;
	_gshift = _surface->format->Gshift;
	_bshift = _surface->format->Bshift;
	_argbLayout = (_rshift == 16 && _gshift == 8 && _bshift == 0);
	for (int i = 0; i < 256; ++i)
	{
		_colors[i].r = _colors[i].g = _colors[i].b = 0;
		_colors[i].unused = 255;
	}
	rebuildTables();
}

void Canvas32::setHdMode(int mode)
{
	if (mode < 0 || mode >= HD_MODE_COUNT)
	{
		mode = HD_MODE_NEAREST;
	}
	flush();
	_hdMode = mode;
}

void Canvas32::setLight(const HdLight *light)
{
	_hasLight = light != nullptr;
	if (light)
	{
		_light = *light;
	}
}

void Canvas32::setDeferred(bool deferred)
{
	flush();
	_deferred = deferred;
}

SDL_Surface *Canvas32::getSdlSurface()
{
	flush();
	return _surface.get();
}

/**
 * Rebuilds the index-to-pixel tables from the palette: plain lookup and one
 * table per shade 0..16 with the StandardShade rules already applied.
 */
void Canvas32::rebuildTables()
{
	for (int i = 0; i < 256; ++i)
	{
		_lut[i] = SDL_MapRGB(_surface->format, _colors[i].r, _colors[i].g, _colors[i].b);
	}
	for (int shade = 0; shade <= 16; ++shade)
	{
		for (int i = 0; i < 256; ++i)
		{
			const Uint8 idx = (Uint8)i;
			const Uint8 newShade = (Uint8)(idx + shade);
			const Uint8 result = ((newShade ^ idx) & 0xF0) ? 0x0F : newShade;
			_shadeLut[shade][i] = _lut[result];
		}
	}
	rebuildToneTables();
	// the smoothed and shaded frames were made with the old palette
	_smooth.clear();
	_smoothScripted.clear();
	clearToned();
}

/**
 * Calibrates the HD shading from the palette. The classic shade s moves a
 * pixel s steps down its 16-entry color ramp (and to black past the end), so
 * the canonical ramp of the palette - the mean brightness of level L relative
 * to level 0 over all bright-to-dark color groups - gives the shading: a pixel
 * is located on the ramp by its brightest channel (a saturated full-brightness
 * color is level 0, like the first entry of a ramp) and each channel is scaled
 * by that channel's mean ramp, rampC(L + s) / rampC(L). Channels have their own
 * ramps so that the drift of the palette towards the dark end (X-COM ramps
 * turn bluish and desaturate as they darken) is kept, and past the end of the
 * ramp the pixel is black exactly where the palette is.
 */
void Canvas32::rebuildToneTables()
{
	double lum[256];
	for (int i = 0; i < 256; ++i)
	{
		lum[i] = (0.299 * _colors[i].r + 0.587 * _colors[i].g + 0.114 * _colors[i].b) / 255.0;
	}
	auto channel = [&](int i, int c) -> double
	{
		return (c == 0 ? _colors[i].r : c == 1 ? _colors[i].g : _colors[i].b) / 255.0;
	};
	double ramp[17] = { 0 };
	double rampC[3][17] = { { 0 } };
	int groupsC[3] = { 0, 0, 0 };
	double top = 0.0; // mean brightest channel of the first entry of the ramps: what "level 0" looks like
	int groups = 0;
	for (int g = 0; g < 16; ++g)
	{
		const double base = lum[g * 16];
		if (base < 0.2 || lum[g * 16 + 15] > base * 0.5)
		{
			continue; // not a bright-to-dark ramp (an empty or UI group)
		}
		for (int level = 0; level < 16; ++level)
		{
			ramp[level] += lum[g * 16 + level] / base;
		}
		top += std::max({ _colors[g * 16].r, _colors[g * 16].g, _colors[g * 16].b }) / 255.0;
		++groups;
		for (int c = 0; c < 3; ++c)
		{
			const double baseC = channel(g * 16, c);
			if (baseC < 0.25)
			{
				continue; // too dark a channel to measure a ratio on
			}
			for (int level = 0; level < 16; ++level)
			{
				rampC[c][level] += channel(g * 16 + level, c) / baseC;
			}
			++groupsC[c];
		}
	}
	if (groups == 0)
	{
		for (int level = 0; level < 16; ++level)
		{
			ramp[level] = (15.0 - level) / 15.0;
		}
		top = 1.0;
	}
	else
	{
		for (int level = 0; level < 16; ++level)
		{
			ramp[level] /= groups;
		}
		top = std::max(0.25, top / groups);
	}
	ramp[0] = 1.0;
	ramp[16] = 0.0; // past the ramp the classic shade gives palette entry 15, black
	for (int level = 1; level <= 16; ++level)
	{
		ramp[level] = std::min(ramp[level], ramp[level - 1]);
	}
	for (int c = 0; c < 3; ++c)
	{
		for (int level = 0; level < 16; ++level)
		{
			rampC[c][level] = groupsC[c] > 0 ? rampC[c][level] / groupsC[c] : ramp[level];
		}
		rampC[c][0] = 1.0;
		rampC[c][16] = 0.0;
		for (int level = 1; level <= 16; ++level)
		{
			rampC[c][level] = std::min(rampC[c][level], rampC[c][level - 1]);
		}
	}
	// value -> continuous level on the brightness ramp
	auto levelOf = [&](double y) -> double
	{
		if (y >= ramp[0])
		{
			return 0.0;
		}
		for (int i = 0; i < 16; ++i)
		{
			if (y <= ramp[i] && y >= ramp[i + 1])
			{
				const double d = ramp[i] - ramp[i + 1];
				return i + (d > 0.0 ? (ramp[i] - y) / d : 0.0);
			}
		}
		return 16.0;
	};
	auto valueOf = [&](const double *r, double level) -> double
	{
		if (level >= 16.0)
		{
			return r[16];
		}
		const int i = (int)level;
		const double t = level - i;
		return r[i] * (1.0 - t) + r[i + 1] * t;
	};
	for (int v = 0; v < 256; ++v)
	{
		const double level = levelOf(std::min(1.0, v / 255.0 / top));
		for (int c = 0; c < 3; ++c)
		{
			const double here = valueOf(rampC[c], level);
			_toneFactor[c][0][v] = 65536u;
			for (int shade = 1; shade <= 16; ++shade)
			{
				const double factor = here > 0.0 ? valueOf(rampC[c], level + shade) / here : 0.0;
				_toneFactor[c][shade][v] = (Uint32)std::max(0.0, std::min(65536.0, std::floor(factor * 65536.0 + 0.5)));
			}
		}
		_level[v] = (Uint8)std::max(0.0, std::min(15.0, std::floor(level + 0.5)));
	}
}

void Canvas32::setPalette(const SDL_Color *colors, int firstcolor, int ncolors)
{
	if (!colors)
	{
		return;
	}
	flush();
	for (int i = 0; i < ncolors; ++i)
	{
		const int c = firstcolor + i;
		if (c >= 0 && c < 256)
		{
			_colors[c] = colors[i];
		}
	}
	rebuildTables();
}

/**
 * Per-frame table of the non-transparent extent of every sprite row, built on
 * first use. Keyed by the pixel buffer; the canvas lives for one battle, and
 * sprite frames are stable for at least that long.
 */
const Canvas32::SpanTable &Canvas32::spansFor(SurfaceRaw<const Uint8> src)
{
	const void *key = src.getBuffer();
	auto it = _spans.find(key);
	if (it != _spans.end() && it->second.width == src.getWidth() && it->second.height == src.getHeight())
	{
		return it->second;
	}
	SpanTable &table = _spans[key];
	table.width = src.getWidth();
	table.height = src.getHeight();
	table.rows.resize(table.height);
	for (int y = 0; y < table.height; ++y)
	{
		const Uint8 *row = rawRow(src, y);
		int begin = 0;
		int end = table.width;
		while (begin < end && row[begin] == 0) ++begin;
		while (end > begin && row[end - 1] == 0) --end;
		table.rows[y].begin = (Uint16)begin;
		table.rows[y].end = (Uint16)end;
	}
	return table;
}

/*
 * Recording
 */

/**
 * Records a command for the next flush, or runs it at once when the canvas
 * is not deferred. Commands whose rows lie outside the canvas are dropped.
 */
void Canvas32::record(Cmd &cmd)
{
	cmd.y0 = std::max(cmd.y0, 0);
	cmd.y1 = std::min(cmd.y1, _height);
	if (cmd.y0 >= cmd.y1)
	{
		return;
	}
	if (_deferred)
	{
		_cmds.push_back(cmd);
	}
	else
	{
		execute(cmd, cmd.y0, cmd.y1);
	}
}

void Canvas32::fill(Uint8 color)
{
	Cmd cmd {};
	cmd.type = Cmd::FILL;
	cmd.color = color;
	cmd.y0 = 0;
	cmd.y1 = _height;
	record(cmd);
}

void Canvas32::blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, bool half, int newBaseColor)
{
	GraphSubset srcDomain(src.getWidth(), src.getHeight());
	if (half)
	{
		srcDomain.beg_x = srcDomain.end_x / 2;
	}
	Cmd cmd {};
	cmd.type = Cmd::BLIT;
	cmd.x = x;
	cmd.y = y;
	cmd.shade = (Sint16)shade;
	cmd.newBaseColor = (Uint8)newBaseColor;
	cmd.src = src;
	cmd.srcDomain = srcDomain;
	cmd.clip = fullArea();
	cmd.y0 = y;
	cmd.y1 = y + src.getHeight();
	if (_hdMode != HD_MODE_NEAREST)
	{
		if (const HdFrame *hd = hdFrameFor(src))
		{
			if (_frameVariant > 0 && !hd->generated)
			{
				const HdFrame *v = HdSprites::findVariant(src.getBuffer(), _frameVariant);
				if (v && v->width == hd->width && v->height == hd->height)
				{
					hd = v;
				}
			}
			else if (_groundOn && !hd->generated)
			{
				hd = groundFrameFor(src, *hd);
			}
			if (!newBaseColor && _hasLight && shade == _light.center)
			{
				recordHdLit(cmd, *hd, shade);
				return;
			}
			cmd.type = Cmd::BLIT_HD;
			cmd.hd = hd;
			if (!newBaseColor && shade > 0)
			{
				// a shaded copy of the frame makes the blit a plain alpha copy
				cmd.hd = tonedFor(*hd, shade);
				cmd.shade = 0;
			}
		}
	}
	// the span table is built on the recording thread, before the strips read it
	if (cmd.type == Cmd::BLIT)
	{
		cmd.spans = &spansFor(src);
	}
	record(cmd);
}

void Canvas32::blitFrame(const HdFrame &hd, int x, int y)
{
	if (_hdMode == HD_MODE_NEAREST || hd.empty())
	{
		return;
	}
	Cmd cmd {};
	cmd.type = Cmd::BLIT_HD;
	cmd.x = x;
	cmd.y = y;
	cmd.hd = &hd;
	cmd.srcDomain = GraphSubset(hd.width, hd.height);
	cmd.clip = fullArea();
	cmd.y0 = y;
	cmd.y1 = y + hd.height;
	record(cmd);
}

void Canvas32::blit(SurfaceRaw<const Uint8> src, int x, int y, int shade, GraphSubset range)
{
	Cmd cmd {};
	cmd.type = Cmd::BLIT;
	cmd.x = x;
	cmd.y = y;
	cmd.shade = (Sint16)shade;
	cmd.newBaseColor = 0;
	cmd.src = src;
	cmd.srcDomain = GraphSubset(src.getWidth(), src.getHeight());
	cmd.clip = range;
	cmd.y0 = std::max(y, range.beg_y);
	cmd.y1 = std::min(y + src.getHeight(), range.end_y);
	if (_hdMode != HD_MODE_NEAREST)
	{
		if (const HdFrame *hd = hdFrameFor(src))
		{
			if (_frameVariant > 0 && !hd->generated)
			{
				const HdFrame *v = HdSprites::findVariant(src.getBuffer(), _frameVariant);
				if (v && v->width == hd->width && v->height == hd->height)
				{
					hd = v;
				}
			}
			if (_hasLight && shade == _light.center)
			{
				recordHdLit(cmd, *hd, shade);
				return;
			}
			cmd.type = Cmd::BLIT_HD;
			cmd.hd = hd;
			if (shade > 0)
			{
				cmd.hd = tonedFor(*hd, shade);
				cmd.shade = 0;
			}
		}
	}
	if (cmd.type == Cmd::BLIT)
	{
		cmd.spans = &spansFor(src);
	}
	record(cmd);
}

/**
 * Scripted blit: the Y-script runs on the base-resolution sprite (the k-scaled
 * frame is that sprite with every pixel repeated, and the script's result
 * depends on the pixel, not on where it is, so this gives the same picture
 * k times cheaper), into an 8-bit scratch exactly as it would into the
 * classic map; the result is then drawn scaled by k through the palette, or
 * smoothed with xBRZ in the smooth mode. A worker without a script is a
 * plain shaded blit. The script sees 0 as the pixel underneath (there is no
 * palette index under a true-color pixel); no known mod script reads it.
 */
void Canvas32::blitScripted(ScriptWorkerBlit &work, const Surface *src, int x, int y, int shade, GraphSubset range)
{
	if (!src)
	{
		return;
	}
	if (!work.hasScript())
	{
		blit(src, x, y, shade, range);
		return;
	}
	const int w = src->getWidth();
	const int h = src->getHeight();
	int k = _scale;
	if (k < 1 || (w % k) != 0 || (h % k) != 0)
	{
		k = 1;
	}
	const int bw = w / k;
	const int bh = h / k;
	if (_scriptSrc.getWidth() != bw || _scriptSrc.getHeight() != bh)
	{
		_scriptSrc = Surface(bw, bh);
		_scriptDst = Surface(bw, bh);
	}
	// the base sprite: every k-th pixel of the scaled frame
	for (int sy = 0; sy < bh; ++sy)
	{
		const Uint8 *from = src->getRaw(0, sy * k);
		Uint8 *to = _scriptSrc.getRaw(0, sy);
		if (k == 1)
		{
			memcpy(to, from, bw);
		}
		else
		{
			for (int sx = 0; sx < bw; ++sx)
			{
				to[sx] = from[sx * k];
			}
		}
		memset(_scriptDst.getRaw(0, sy), 0, bw);
	}
	work.executeBlit(&_scriptSrc, &_scriptDst, 0, 0, shade, GraphSubset(bw, bh));

	Cmd cmd {};
	cmd.x = x;
	cmd.y = y;
	cmd.shade = 0; // the script applied the shade
	cmd.newBaseColor = 0;
	cmd.clip = range;
	cmd.y0 = std::max(y, range.beg_y);
	cmd.y1 = std::min(y + h, range.end_y);
	// an HD frame of the sprite (a pack): the script's work - the recolour of a face or hair, and the
	// shade - is a change of palette index per base pixel; every HD pixel over a base pixel gets the
	// same change as a change of colour (the ratio of the new colour to the old), so the pack's
	// picture is recoloured and shaded as the classic sprite was. Cached by the script's result.
	if (_hdMode >= HD_MODE_PACKS && k >= 2)
	{
		const HdFrame *pack = HdSprites::find(src->getBuffer());
		if (pack && pack->width == w && pack->height == h)
		{
			Uint64 hash = 0x1234567887654321ULL ^ (Uint64)(uintptr_t)src->getBuffer();
			bool changed = false;
			for (int sy = 0; sy < bh; ++sy)
			{
				const Uint8 *in = _scriptSrc.getRaw(0, sy);
				const Uint8 *out = _scriptDst.getRaw(0, sy);
				for (int sx = 0; sx < bw; ++sx)
				{
					hash = (hash ^ out[sx]) * 1099511628211ULL;
					if (out[sx] != in[sx]) changed = true;
				}
			}
			if (!changed)
			{
				cmd.type = Cmd::BLIT_HD;
				cmd.hd = pack;
				cmd.srcDomain = GraphSubset(w, h);
				record(cmd);
				return;
			}
			auto it = _smoothScripted.find(hash);
			if (it == _smoothScripted.end())
			{
				HdFrame made;
				made.width = w;
				made.height = h;
				made.pixels.resize(pack->pixels.size());
				made.generated = false;
				for (int py = 0; py < h; ++py)
				{
					const Uint8 *in = _scriptSrc.getRaw(0, py / k);
					const Uint8 *out = _scriptDst.getRaw(0, py / k);
					const Uint32 *from = pack->row(py);
					Uint32 *to = &made.pixels[(size_t)py * w];
					for (int px = 0; px < w; ++px)
					{
						const Uint32 p = from[px];
						const Uint8 a = in[px / k], b = out[px / k];
						if (a == b || !(p >> 24))
						{
							to[px] = p;
							continue;
						}
						if (b == 0)
						{
							to[px] = 0; // the script erased the pixel
							continue;
						}
						const SDL_Color &ca = _colors[a], &cb = _colors[b];
						// the new color keeps the brightness the HD pixel had on the old ramp. A
						// per-channel ratio would look the same on paper, but the HD pixel is only
						// close to the palette entry, not equal to it, and where the old color has
						// a near-empty channel the ratio turns that gap into a hue (R-030)
						const float la = 0.299f * ca.r + 0.587f * ca.g + 0.114f * ca.b;
						const float lp = 0.299f * ((p >> 16) & 0xFF) + 0.587f * ((p >> 8) & 0xFF) + 0.114f * (p & 0xFF);
						const float f = (lp + 2.0f) / (la + 2.0f);
						const int r = std::min(255, (int)(cb.r * f + 0.5f));
						const int g = std::min(255, (int)(cb.g * f + 0.5f));
						const int bl = std::min(255, (int)(cb.b * f + 0.5f));
						to[px] = (p & 0xFF000000u) | ((Uint32)r << 16) | ((Uint32)g << 8) | (Uint32)bl;
					}
				}
				made.buildSpans();
				it = _smoothScripted.emplace(hash, std::move(made)).first;
			}
			cmd.type = Cmd::BLIT_HD;
			cmd.hd = &it->second;
			cmd.srcDomain = GraphSubset(w, h);
			record(cmd);
			return;
		}
	}
	if (_hdMode == HD_MODE_SMOOTH && k >= 2 && k <= 6)
	{
		// smooth the script's result; cached by content, as units repeat their recolors
		Uint64 hash = 1469598103934665603ULL ^ (Uint64)(uintptr_t)src->getBuffer();
		for (int sy = 0; sy < bh; ++sy)
		{
			const Uint8 *row = _scriptDst.getRaw(0, sy);
			for (int sx = 0; sx < bw; ++sx)
			{
				hash = (hash ^ row[sx]) * 1099511628211ULL;
			}
		}
		auto it = _smoothScripted.find(hash);
		if (it == _smoothScripted.end())
		{
			HdFrame made;
			if (smoothBase(_scriptDst.getRaw(0, 0), bw, bh, _scriptDst.getPitch(), made))
			{
				made.buildSpans();
				it = _smoothScripted.emplace(hash, std::move(made)).first;
			}
		}
		if (it != _smoothScripted.end())
		{
			cmd.type = Cmd::BLIT_HD;
			cmd.hd = &it->second;
			cmd.srcDomain = GraphSubset(w, h);
			record(cmd);
			return;
		}
	}
	// the script result is rewritten by the next call: keep a copy
	cmd.type = Cmd::BLIT_SCALED;
	cmd.scale = k;
	cmd.srcW = bw;
	cmd.srcH = bh;
	cmd.arena = _arena.size();
	_arena.resize(cmd.arena + (size_t)bw * bh);
	for (int sy = 0; sy < bh; ++sy)
	{
		memcpy(_arena.data() + cmd.arena + (size_t)sy * bw, _scriptDst.getRaw(0, sy), bw);
	}
	record(cmd);
}

void Canvas32::blitClassic(Surface *src, int x, int y, int scale, int shade, int newBaseColor)
{
	if (!src || scale < 1)
	{
		return;
	}
	SDL_Surface *s = src->getSurface();
	Cmd cmd {};
	cmd.type = Cmd::BLIT_SCALED;
	cmd.x = x;
	cmd.y = y;
	cmd.scale = scale;
	cmd.shade = (Sint16)shade;
	cmd.newBaseColor = (Uint8)newBaseColor;
	cmd.srcW = s->w;
	cmd.srcH = s->h;
	cmd.clip = fullArea();
	cmd.y0 = y;
	cmd.y1 = y + s->h * scale;
	// classic elements (texts, markers) are redrawn between calls: keep a copy of the pixels
	cmd.arena = _arena.size();
	_arena.resize(cmd.arena + (size_t)s->w * s->h);
	for (int sy = 0; sy < s->h; ++sy)
	{
		memcpy(_arena.data() + cmd.arena + (size_t)sy * s->w, (const Uint8*)s->pixels + (size_t)sy * s->pitch, s->w);
	}
	record(cmd);
}

void Canvas32::drawVapor(SurfaceRaw<int> pattern, int x, int y, int size, const Uint8 *, SDL_Color tint)
{
	if (tint.unused == 0)
	{
		return; // zero opacity keeps the pixel, as the palette LUT does
	}
	Cmd cmd {};
	cmd.type = Cmd::VAPOR;
	cmd.x = x;
	cmd.y = y;
	cmd.size = size;
	cmd.tint = tint;
	cmd.srcW = pattern.getWidth();
	cmd.srcH = pattern.getHeight();
	cmd.clip = fullArea();
	cmd.y0 = y;
	cmd.y1 = y + pattern.getHeight();
	// the pattern is a temporary of the caller: keep a copy
	cmd.arena = _arenaInt.size();
	_arenaInt.resize(cmd.arena + (size_t)cmd.srcW * cmd.srcH);
	for (int py = 0; py < cmd.srcH; ++py)
	{
		const int *row = (const int*)((const Uint8*)pattern.getBuffer() + (size_t)py * pattern.getPitch());
		memcpy(_arenaInt.data() + cmd.arena + (size_t)py * cmd.srcW, row, sizeof(int) * cmd.srcW);
	}
	record(cmd);
}

void Canvas32::flash()
{
	Cmd cmd {};
	cmd.type = Cmd::FLASH;
	cmd.y0 = 0;
	cmd.y1 = _height;
	record(cmd);
}

bool Canvas32::saveDump(const std::string &filename)
{
	flush();
	return HdTest::savePngRgb(filename, _surface.get());
}

/*
 * Execution
 */

/**
 * Runs the recorded commands: the canvas is cut into horizontal strips, and
 * every strip runs the whole list clipped to its rows on its own thread. The
 * commands only read their sources and the tables, and write their own rows,
 * so the strips are independent and the order within a strip is the order of
 * the calls.
 */
void Canvas32::flush()
{
	if (_cmds.empty())
	{
		return;
	}
	HdWorkers &pool = HdWorkers::instance();
	const int threads = pool.threads();
	const int strips = std::max(1, std::min(_height / 16, threads == 1 ? 1 : threads * 4));
	const std::vector<Cmd> &cmds = _cmds;
	pool.run(strips, [&](int strip)
	{
		const int y0 = (int)((long long)_height * strip / strips);
		const int y1 = (int)((long long)_height * (strip + 1) / strips);
		for (const Cmd &cmd : cmds)
		{
			if (cmd.y1 > y0 && cmd.y0 < y1)
			{
				execute(cmd, std::max(cmd.y0, y0), std::min(cmd.y1, y1));
			}
		}
	});
	_cmds.clear();
	_arena.clear();
	_arenaInt.clear();
	// the pack frames read longest ago go when their memory budget is exceeded (between frames: commands point at them)
	HdSprites::trim();
	if (_tonedStale)
	{
		// the shaded copies made before this frame's packs came (see tonedFor)
		clearToned();
		_tonedTransient.clear();
		_tonedGeneration = HdSprites::generation();
		_tonedStale = false;
	}
	// ground blends of old packs, and the oldest over their cap (commands of this frame pointed at them)
	trimGround();
	// the shaded copies used longest ago go when they exceed their cap (here, not while recording: commands point at them)
	static const size_t tonedCap = 256u * 1024u * 1024u;
	while (_tonedBytes > tonedCap && !_tonedLru.empty())
	{
		auto victim = _toned.find(_tonedLru.back());
		if (victim != _toned.end())
		{
			_tonedBytes -= victim->second.frame.pixels.size() * sizeof(Uint32);
			_toned.erase(victim);
		}
		_tonedLru.pop_back();
	}
	// the smoothed-frame caches are only trimmed between frames: commands point into them;
	// the shaded copies point at the smoothed frames, so they go with them
	if (_smooth.size() > 4096 || _smoothScripted.size() > 2048)
	{
		// measurement: the whole cache goes at once, and the shaded copies with it, so the next
		// frames re-smooth and re-shade everything visible. Invisible in the log otherwise.
		Log(LOG_INFO) << "HD perf: smooth cache dropped, " << _smooth.size() << "+" << _smoothScripted.size()
			<< " frames " << (smoothBytes() >> 20) << " MB, with " << (_tonedBytes >> 20) << " MB of shaded copies";
		if (_smooth.size() > 4096)
		{
			_smooth.clear();
		}
		if (_smoothScripted.size() > 2048)
		{
			_smoothScripted.clear();
		}
		clearToned();
	}
	perfReport();
}

/**
 * Bytes held by the smoothed-frame caches (measurement only).
 */
size_t Canvas32::smoothBytes() const
{
	size_t bytes = 0;
	for (const auto &pair : _smooth)
	{
		bytes += pair.second.pixels.size() * sizeof(Uint32);
	}
	for (const auto &pair : _smoothScripted)
	{
		bytes += pair.second.pixels.size() * sizeof(Uint32);
	}
	return bytes;
}

/**
 * Logs what the HD caches hold, every two seconds: what a battle actually costs,
 * and whether a cache is thrashing rather than filling. Draws nothing.
 */
void Canvas32::perfReport()
{
	const Uint32 now = SDL_GetTicks();
	if (now - _perfLast < 2000)
	{
		return;
	}
	_perfLast = now;
	Log(LOG_INFO) << "HD perf: " << _width << "x" << _height << " k=" << _scale << " mode=" << _hdMode
		<< " | smooth " << _smooth.size() << "+" << _smoothScripted.size() << " fr " << (smoothBytes() >> 20) << " MB"
		<< " | toned " << _toned.size() << " fr " << (_tonedBytes >> 20) << " MB"
		<< " | ground " << _ground.size() << " fr " << (_groundBytes >> 20) << " MB"
		<< " | packs " << HdSprites::loaded() << " fr " << (HdSprites::loadedBytes() >> 20) << " MB"
		<< " | pictures " << (HdUiArt::bytes() >> 20) << " MB"
		<< " | spans " << _spans.size();
}

/**
 * Copies the frame into a 32-bit surface of the same pixel format.
 */
void Canvas32::copyTo(SDL_Surface *dest, int x, int y)
{
	flush();
	if (!dest || dest->format->BytesPerPixel != 4)
	{
		return;
	}
	const int x0 = std::max(x, 0), y0 = std::max(y, 0);
	const int x1 = std::min(x + _width, dest->w), y1 = std::min(y + _height, dest->h);
	if (x0 >= x1 || y0 >= y1)
	{
		return;
	}
	const size_t bytes = (size_t)(x1 - x0) * 4;
	HdWorkers &pool = HdWorkers::instance();
	const int rows = y1 - y0;
	const int jobs = std::max(1, std::min(rows / 32, pool.threads() * 2));
	pool.run(jobs, [&](int job)
	{
		const int ya = y0 + (int)((long long)rows * job / jobs);
		const int yb = y0 + (int)((long long)rows * (job + 1) / jobs);
		for (int dy = ya; dy < yb; ++dy)
		{
			memcpy((Uint8*)dest->pixels + (size_t)dy * dest->pitch + (size_t)x0 * 4, rowPtr(dy - y) + (x0 - x), bytes);
		}
	});
}

/**
 * Runs one command on the rows [y0, y1) of the canvas.
 */
void Canvas32::execute(const Cmd &cmd, int y0, int y1)
{
	GraphSubset clip = cmd.clip;
	GraphSubset::intersectionRange(clip.beg_y, clip.end_y, y0, y1);
	switch (cmd.type)
	{
	case Cmd::FILL:
		doFill(cmd.color, y0, y1);
		break;
	case Cmd::BLIT:
		if (cmd.newBaseColor)
		{
			// helper::ColorReplace: shade of the pixel plus shade, color group replaced
			Uint32 table[256];
			const Uint8 newColor = (Uint8)((cmd.newBaseColor - 1) << 4);
			for (int i = 0; i < 256; ++i)
			{
				const Uint8 newShade = (Uint8)((i & 0x0F) + cmd.shade);
				const Uint8 result = (newShade & 0xF0) ? 0x0F : (Uint8)(newColor | newShade);
				table[i] = _lut[result];
			}
			doBlit(cmd.src, *cmd.spans, cmd.srcDomain, cmd.x, cmd.y, table, clip);
		}
		else if (cmd.shade >= 0 && cmd.shade <= 16)
		{
			doBlit(cmd.src, *cmd.spans, cmd.srcDomain, cmd.x, cmd.y, _shadeLut[cmd.shade], clip);
		}
		else
		{
			Uint32 table[256];
			for (int i = 0; i < 256; ++i)
			{
				const Uint8 idx = (Uint8)i;
				const Uint8 newShade = (Uint8)(idx + cmd.shade);
				table[i] = _lut[((newShade ^ idx) & 0xF0) ? 0x0F : newShade];
			}
			doBlit(cmd.src, *cmd.spans, cmd.srcDomain, cmd.x, cmd.y, table, clip);
		}
		break;
	case Cmd::BLIT_HD:
		doBlitHd(*cmd.hd, cmd.x, cmd.y, cmd.shade, cmd.srcDomain, cmd.newBaseColor, clip);
		break;
	case Cmd::BLIT_HD_LIT:
		doBlitHdLit(cmd, clip);
		break;
	case Cmd::BLIT_SCALED:
		doBlitScaled(_arena.data() + cmd.arena, cmd.srcW, cmd.srcH, cmd.x, cmd.y, cmd.scale, cmd.shade, cmd.newBaseColor, clip);
		break;
	case Cmd::VAPOR:
		doVapor(_arenaInt.data() + cmd.arena, cmd.srcW, cmd.srcH, cmd.x, cmd.y, cmd.size, cmd.tint, clip);
		break;
	case Cmd::FLASH:
		doFlash(y0, y1);
		break;
	}
}

void Canvas32::doFill(Uint8 color, int y0, int y1)
{
	const Uint32 value = _lut[color];
	for (int y = y0; y < y1; ++y)
	{
		Uint32 *row = rowPtr(y);
		for (int x = 0; x < _width; ++x)
		{
			row[x] = value;
		}
	}
}

/**
 * The palette sprite blit: dest region = source domain moved to (x, y),
 * clipped to destClip and the canvas; every non-zero index goes through the
 * table (which already encodes the shading rule) into the pixel.
 */
void Canvas32::doBlit(SurfaceRaw<const Uint8> src, const SpanTable &spans, GraphSubset srcDomain, int x, int y, const Uint32 *table, GraphSubset destClip)
{
	const int x0 = std::max({ srcDomain.beg_x + x, destClip.beg_x, 0 });
	const int x1 = std::min({ srcDomain.end_x + x, destClip.end_x, _width });
	const int y0 = std::max({ srcDomain.beg_y + y, destClip.beg_y, 0 });
	const int y1 = std::min({ srcDomain.end_y + y, destClip.end_y, _height });
	if (x0 >= x1 || y0 >= y1)
	{
		return;
	}
	for (int dy = y0; dy < y1; ++dy)
	{
		const int sy = dy - y;
		const Span &span = spans.rows[sy];
		const int sx0 = std::max<int>(span.begin, x0 - x);
		const int sx1 = std::min<int>(span.end, x1 - x);
		if (sx0 >= sx1)
		{
			continue;
		}
		const Uint8 *srcRow = rawRow(src, sy);
		Uint32 *dstRow = rowPtr(dy) + x;
		for (int sx = sx0; sx < sx1; ++sx)
		{
			const Uint8 idx = srcRow[sx];
			if (idx)
			{
				dstRow[sx] = table[idx];
			}
		}
	}
}

/**
 * A base-resolution 8-bit image drawn scaled by an integer factor (classic
 * UI elements in the map, script results): HdBlit::blitScaled semantics.
 */
void Canvas32::doBlitScaled(const Uint8 *src, int srcW, int srcH, int x, int y, int scale, int shade, int newBaseColor, GraphSubset destClip)
{
	const int dstX0 = std::max({ x, destClip.beg_x, 0 });
	const int dstY0 = std::max({ y, destClip.beg_y, 0 });
	const int dstX1 = std::min({ x + srcW * scale, destClip.end_x, _width });
	const int dstY1 = std::min({ y + srcH * scale, destClip.end_y, _height });
	if (dstX0 >= dstX1 || dstY0 >= dstY1)
	{
		return;
	}
	Uint32 table[256];
	if (newBaseColor)
	{
		const Uint8 newColor = (Uint8)((newBaseColor - 1) << 4);
		for (int i = 0; i < 256; ++i)
		{
			const Uint8 newShade = (Uint8)((i & 0x0F) + shade);
			table[i] = _lut[(newShade & 0xF0) ? 0x0F : (Uint8)(newColor | newShade)];
		}
	}
	else
	{
		for (int i = 0; i < 256; ++i)
		{
			const Uint8 idx = (Uint8)i;
			const Uint8 newShade = (Uint8)(idx + shade);
			table[i] = _lut[((newShade ^ idx) & 0xF0) ? 0x0F : newShade];
		}
	}
	for (int dy = dstY0; dy < dstY1; ++dy)
	{
		const Uint8 *srcRow = src + (size_t)((dy - y) / scale) * srcW;
		Uint32 *dstRow = rowPtr(dy);
		if (scale == 1)
		{
			for (int dx = dstX0; dx < dstX1; ++dx)
			{
				const Uint8 idx = srcRow[dx - x];
				if (idx)
				{
					dstRow[dx] = table[idx];
				}
			}
		}
		else
		{
			for (int dx = dstX0; dx < dstX1; ++dx)
			{
				const Uint8 idx = srcRow[(dx - x) / scale];
				if (idx)
				{
					dstRow[dx] = table[idx];
				}
			}
		}
	}
}

void Canvas32::doVapor(const int *pattern, int w, int h, int x, int y, int size, SDL_Color tint, GraphSubset destClip)
{
	const int x0 = std::max({ x, destClip.beg_x, 0 });
	const int y0 = std::max({ y, destClip.beg_y, 0 });
	const int x1 = std::min({ x + w, destClip.end_x, _width });
	const int y1 = std::min({ y + h, destClip.end_y, _height });
	for (int dy = y0; dy < y1; ++dy)
	{
		const int *patternRow = pattern + (size_t)(dy - y) * w;
		Uint32 *dstRow = rowPtr(dy);
		for (int dx = x0; dx < x1; ++dx)
		{
			if (size <= patternRow[dx - x])
			{
				const Uint32 d = dstRow[dx];
				int r = (d >> _rshift) & 0xFF, g = (d >> _gshift) & 0xFF, b = (d >> _bshift) & 0xFF;
				// same formula the palette transparency tables were built from
				r = std::min(255, (r * tint.unused / 255) + tint.r);
				g = std::min(255, (g * tint.unused / 255) + tint.g);
				b = std::min(255, (b * tint.unused / 255) + tint.b);
				dstRow[dx] = pack(r, g, b);
			}
		}
	}
}

void Canvas32::doFlash(int y0, int y1)
{
	// the palette version jumps every pixel to the brightest entry of its color group;
	// here: a strong brightening that keeps the hue
	for (int dy = y0; dy < y1; ++dy)
	{
		Uint32 *dstRow = rowPtr(dy);
		for (int dx = 0; dx < _width; ++dx)
		{
			const Uint32 d = dstRow[dx];
			int r = (d >> _rshift) & 0xFF, g = (d >> _gshift) & 0xFF, b = (d >> _bshift) & 0xFF;
			r = 255 - (255 - r) / 4;
			g = 255 - (255 - g) / 4;
			b = 255 - (255 - b) / 4;
			dstRow[dx] = pack(r, g, b);
		}
	}
}

/*
 * Ground variants
 */

namespace
{
	inline Uint32 groundHash(Uint32 seed, int x, int y, int z)
	{
		Uint32 h = seed ^ 0x9E3779B9u;
		h ^= (Uint32)x * 0x85EBCA6Bu;
		h = ((h << 13) | (h >> 19)) * 5u + 0xE6546B64u;
		h ^= (Uint32)y * 0xC2B2AE35u;
		h = ((h << 13) | (h >> 19)) * 5u + 0xE6546B64u;
		h ^= (Uint32)z * 0x27D4EB2Fu;
		h ^= h >> 16;
		h *= 0x85EBCA6Bu;
		h ^= h >> 13;
		h *= 0xC2B2AE35u;
		h ^= h >> 16;
		return h;
	}

	/// Smooth value noise in [0, 1] (quintic fade between lattice values).
	float groundNoise(Uint32 seed, float x, float y, int z)
	{
		const float fx = std::floor(x), fy = std::floor(y);
		const int ix = (int)fx, iy = (int)fy;
		float tx = x - fx, ty = y - fy;
		tx = tx * tx * tx * (tx * (tx * 6.0f - 15.0f) + 10.0f);
		ty = ty * ty * ty * (ty * (ty * 6.0f - 15.0f) + 10.0f);
		auto at = [&](int a, int b) { return (float)(groundHash(seed, a, b, z) & 0xFFFFFF) / 16777215.0f; };
		const float v00 = at(ix, iy), v10 = at(ix + 1, iy), v01 = at(ix, iy + 1), v11 = at(ix + 1, iy + 1);
		const float a = v00 + (v10 - v00) * tx;
		const float b = v01 + (v11 - v01) * tx;
		return a + (b - a) * ty;
	}

	// the pattern: patches about GROUND_WAVE tiles across with smaller ones on them; a blend runs over
	// +-GROUND_EDGE of the pattern around the middle between two variants, and its line is made ragged
	// by fine noise (GROUND_RAGGED), so a patch edge looks grown, not drawn
	const float GROUND_WAVE = 6.0f;
	const float GROUND_WAVE2 = 2.5f;
	const float GROUND_EDGE = 0.16f;
	const float GROUND_RAGGED = 0.22f;

	/// Fine noise (about a fifth and a thirteenth of a tile) for the ragged patch edges.
	inline float groundRagged(Uint32 seed, float u, float v, int z)
	{
		return 0.6f * groundNoise(seed + 7u, u * 5.0f, v * 5.0f, z) + 0.4f * groundNoise(seed + 13u, u * 13.0f, v * 13.0f, z);
	}

	/// The ground point (tiles) of the centre of base pixel (bx, by) of a floor frame of cell (x, y):
	/// the frame's floor diamond is the cell; a pixel above or below the diamond takes the diamond's
	/// edge in its column (what stands on the ground belongs to the ground under it).
	inline void groundPoint(int x, int y, int bw, int bh, int bx, int by, float &u, float &v)
	{
		const float dx = bx + 0.5f - bw * 0.5f;
		const float ext = std::max(0.0f, 8.0f - std::fabs(dx) * 0.5f);
		const float dy = std::max(-ext, std::min(ext, by + 0.5f - (bh - 8.0f)));
		u = x + 0.5f + (dx / 16.0f + dy / 8.0f) * 0.5f;
		v = y + 0.5f + (dy / 8.0f - dx / 16.0f) * 0.5f;
	}

	/// The variant a pattern value shows everywhere around it, or -1 when it may be a blend.
	inline int groundPure(float p, int count)
	{
		const int i = std::max(0, std::min(count - 2, (int)std::floor(p)));
		const float t = p - i;
		const float reach = GROUND_EDGE + GROUND_RAGGED * 0.5f + 0.08f; // + what the pattern moves between samples
		if (t <= 0.5f - reach) return i;
		if (t >= 0.5f + reach) return i + 1;
		return -1;
	}
}

float Canvas32::groundLevel(Uint32 seed, float u, float v, int z, int count)
{
	if (count < 2)
	{
		return 0.0f;
	}
	float n = 0.62f * groundNoise(seed, u / GROUND_WAVE, v / GROUND_WAVE, z)
		+ 0.38f * groundNoise(seed + 101u, u / GROUND_WAVE2 + 0.37f, v / GROUND_WAVE2 + 0.71f, z);
	// value noise crowds around the middle: spread it so the outer variants get their share
	n = std::max(0.0f, std::min(1.0f, (n - 0.5f) * 2.4f + 0.5f));
	return n * (count - 1);
}

void Canvas32::setGroundSeed(Uint32 seed)
{
	if (seed != _groundSeed)
	{
		// the blends of the old pattern go at the next flush (nothing points at them after it)
		for (auto &pair : _ground)
		{
			pair.second.generation = 0;
		}
		_groundSeed = seed;
	}
}

/**
 * The picture of a floor frame on the current map cell. A pack frame with
 * variants shows the variant the ground pattern puts there; along the edge of
 * a patch the two neighbouring variants are blended pixel by pixel (the
 * pattern is continuous over the map, so the cells meet without seams).
 * Cells that show one variant everywhere draw that frame as it is; the
 * blends are cached per cell.
 */
const HdFrame *Canvas32::groundFrameFor(SurfaceRaw<const Uint8> src, const HdFrame &base)
{
	const void *key = src.getBuffer();
	const int slots = HdSprites::variantCount(key);
	if (slots <= 0)
	{
		return &base;
	}
	const HdFrame *found[16];
	int count = 0;
	found[count++] = &base;
	for (int v = 1; v <= slots && count < 16; ++v)
	{
		const HdFrame *f = HdSprites::findVariant(key, v);
		if (!f || f->width != base.width || f->height != base.height)
		{
			break; // a variant's side of the scale is set by its number: no gaps
		}
		found[count++] = f;
	}
	if (count < 2)
	{
		return &base;
	}
	// the scale the pattern runs along: the pack's own picture in the middle (the most common look),
	// the odd variants one way from it (v1 next to it, v3 beyond), the even ones the other way (v2, v4):
	// short grass - the grass - tall grass, lighter sand - the sand - darker sand
	const HdFrame *frames[16];
	const int mid = count / 2;
	frames[mid] = found[0];
	for (int j = 1; j < count; ++j)
	{
		frames[(j % 2) ? mid - (j + 1) / 2 : mid + j / 2] = found[j];
	}
	const int k = std::max(1, _scale);
	const int bw = base.width / k, bh = base.height / k;
	if (bw < 2 || bh < 16)
	{
		return &base;
	}
	// one variant all over the cell? (the pattern at the corners, the edge middles and the centre)
	{
		int pure = -2;
		static const float at[9][2] = { {0.02f, 0.02f}, {0.5f, 0.02f}, {0.98f, 0.02f}, {0.02f, 0.5f}, {0.5f, 0.5f}, {0.98f, 0.5f}, {0.02f, 0.98f}, {0.5f, 0.98f}, {0.98f, 0.98f} };
		for (const auto &s : at)
		{
			const int p = groundPure(groundLevel(_groundSeed, _groundX + s[0], _groundY + s[1], _groundZ, count), count);
			if (p < 0 || (pure != -2 && p != pure))
			{
				pure = -1;
				break;
			}
			pure = p;
		}
		if (pure >= 0)
		{
			return frames[pure];
		}
	}
	// a blend, from the cache or made now
	const unsigned generation = HdSprites::generation();
	Uint64 hkey = (Uint64)(uintptr_t)key * 0x9E3779B97F4A7C15ULL;
	hkey ^= ((Uint64)(Uint32)_groundX << 42) ^ ((Uint64)(Uint32)_groundY << 21) ^ (Uint64)(Uint32)_groundZ ^ ((Uint64)generation << 58) ^ ((Uint64)_groundSeed * 0xC2B2AE3D27D4EB4FULL);
	auto it = _ground.find(hkey);
	if (it != _ground.end())
	{
		GroundEntry &e = it->second;
		if (e.src == key && e.x == _groundX && e.y == _groundY && e.z == _groundZ && e.generation == generation)
		{
			e.lru = ++_groundClock;
			return &e.frame;
		}
	}
	HdFrame *out;
	const bool clash = it != _ground.end();
	if (clash)
	{
		_groundTransient.emplace_back();
		out = &_groundTransient.back();
	}
	else
	{
		GroundEntry &e = _ground[hkey];
		e.src = key;
		e.x = _groundX;
		e.y = _groundY;
		e.z = _groundZ;
		e.generation = generation;
		e.lru = ++_groundClock;
		out = &e.frame;
	}
	// the pattern and the ragged edge at every base pixel, then per HD pixel bilinear between them
	std::vector<float> level((size_t)bw * bh), ragged((size_t)bw * bh);
	for (int by = 0; by < bh; ++by)
	{
		for (int bx = 0; bx < bw; ++bx)
		{
			float u, v;
			groundPoint(_groundX, _groundY, bw, bh, bx, by, u, v);
			level[(size_t)by * bw + bx] = groundLevel(_groundSeed, u, v, _groundZ, count);
			ragged[(size_t)by * bw + bx] = groundRagged(_groundSeed, u, v, _groundZ);
		}
	}
	const int w = base.width, h = base.height;
	out->width = w;
	out->height = h;
	out->generated = false;
	out->pixels.assign((size_t)w * h, 0);
	auto sample = [&](const std::vector<float> &grid, float fx, float fy)
	{
		fx = std::max(0.0f, std::min((float)(bw - 1), fx));
		fy = std::max(0.0f, std::min((float)(bh - 1), fy));
		const int x0 = std::min(bw - 2, (int)fx), y0 = std::min(bh - 2, (int)fy);
		const float tx = fx - x0, ty = fy - y0;
		const float a = grid[(size_t)y0 * bw + x0] + (grid[(size_t)y0 * bw + x0 + 1] - grid[(size_t)y0 * bw + x0]) * tx;
		const float b = grid[(size_t)(y0 + 1) * bw + x0] + (grid[(size_t)(y0 + 1) * bw + x0 + 1] - grid[(size_t)(y0 + 1) * bw + x0]) * tx;
		return a + (b - a) * ty;
	};
	for (int py = 0; py < h; ++py)
	{
		const float fy = (py + 0.5f) / k - 0.5f;
		Uint32 *to = &out->pixels[(size_t)py * w];
		for (int px = 0; px < w; ++px)
		{
			const float fx = (px + 0.5f) / k - 0.5f;
			const float p = sample(level, fx, fy);
			const int i = std::max(0, std::min(count - 2, (int)std::floor(p)));
			float t = p - i + GROUND_RAGGED * (sample(ragged, fx, fy) - 0.5f);
			t = std::max(0.0f, std::min(1.0f, (t - (0.5f - GROUND_EDGE)) / (2.0f * GROUND_EDGE)));
			t = t * t * (3.0f - 2.0f * t);
			const Uint32 wb = (Uint32)(t * 255.0f + 0.5f);
			const Uint32 A = frames[i]->pixels[(size_t)py * w + px];
			const Uint32 B = frames[i + 1]->pixels[(size_t)py * w + px];
			if (wb == 0)
			{
				to[px] = A;
				continue;
			}
			if (wb == 255)
			{
				to[px] = B;
				continue;
			}
			const Uint32 fa = (255 - wb) * (A >> 24), fb = wb * (B >> 24);
			const Uint32 sum = fa + fb;
			if (sum == 0)
			{
				to[px] = 0;
				continue;
			}
			const Uint32 r = ((((A >> 16) & 0xFF) * fa + ((B >> 16) & 0xFF) * fb) + sum / 2) / sum;
			const Uint32 g = ((((A >> 8) & 0xFF) * fa + ((B >> 8) & 0xFF) * fb) + sum / 2) / sum;
			const Uint32 b = (((A & 0xFF) * fa + (B & 0xFF) * fb) + sum / 2) / sum;
			const Uint32 a = (sum + 127) / 255;
			to[px] = (a << 24) | (r << 16) | (g << 8) | b;
		}
	}
	out->buildSpans();
	if (!clash)
	{
		_groundBytes += out->pixels.size() * sizeof(Uint32);
	}
	return out;
}

/**
 * The end of a flush: blends of an older pack registry (or pattern) go, and
 * the ones used longest ago while the cache is over its cap; the shaded copies
 * made from the dropped blends go with them.
 */
void Canvas32::trimGround()
{
	// the one-frame blends go (their addresses come back next frame: their shaded copies go too)
	std::unordered_set<const HdFrame*> dropped;
	for (const HdFrame &frame : _groundTransient)
	{
		dropped.insert(&frame);
	}
	_groundTransient.clear();
	static const size_t groundCap = 192u * 1024u * 1024u;
	const unsigned generation = HdSprites::generation();
	std::vector<std::pair<size_t, Uint64>> order;
	bool stale = false;
	for (const auto &pair : _ground)
	{
		if (pair.second.generation != generation)
		{
			stale = true;
		}
		order.emplace_back(pair.second.generation != generation ? 0 : pair.second.lru, pair.first);
	}
	if (stale || _groundBytes > groundCap)
	{
		std::sort(order.begin(), order.end());
		const size_t target = groundCap - groundCap / 4;
		for (const auto &o : order)
		{
			auto it = _ground.find(o.second);
			if (it == _ground.end())
			{
				continue;
			}
			const bool old = it->second.generation != generation;
			if (!old && _groundBytes <= target)
			{
				break;
			}
			_groundBytes -= it->second.frame.pixels.size() * sizeof(Uint32);
			dropped.insert(&it->second.frame);
			_ground.erase(it);
		}
	}
	if (dropped.empty())
	{
		return;
	}
	for (auto it = _toned.begin(); it != _toned.end(); )
	{
		if (dropped.count(it->first.frame))
		{
			_tonedBytes -= it->second.frame.pixels.size() * sizeof(Uint32);
			_tonedLru.erase(it->second.lru);
			it = _toned.erase(it);
		}
		else
		{
			++it;
		}
	}
}

/*
 * HD frames
 */

/**
 * The frame to draw instead of a palette frame: its pack frame when a mod
 * ships one (any HD mode), else its xBRZ-smoothed version (smooth mode), else
 * nullptr for the classic nearest path.
 */
const HdFrame *Canvas32::hdFrameFor(SurfaceRaw<const Uint8> src)
{
	const HdFrame *hd = HdSprites::find(src.getBuffer());
	if (hd && hd->width == src.getWidth() && hd->height == src.getHeight())
	{
		return hd;
	}
	if (_hdMode == HD_MODE_SMOOTH)
	{
		return smoothFor(src);
	}
	return nullptr;
}

/**
 * The xBRZ-smoothed version of a nearest-scaled palette frame, made on first
 * use. Keyed by the frame buffer like the span tables.
 */
const HdFrame *Canvas32::smoothFor(SurfaceRaw<const Uint8> src)
{
	const void *key = src.getBuffer();
	auto it = _smooth.find(key);
	if (it != _smooth.end())
	{
		return it->second.empty() ? nullptr : &it->second;
	}
	HdFrame made;
	if (!smoothFrame(src, made))
	{
		_smooth.emplace(key, HdFrame()); // remember that it cannot be smoothed
		return nullptr;
	}
	made.buildSpans();
	return &_smooth.emplace(key, std::move(made)).first->second;
}

/**
 * Smooths a k-scaled palette frame: the base sprite is recovered by sampling
 * every k-th pixel, then smoothed k times.
 */
bool Canvas32::smoothFrame(SurfaceRaw<const Uint8> src, HdFrame &out)
{
	const int k = _scale;
	const int w = src.getWidth();
	const int h = src.getHeight();
	if (k < 2 || k > 6 || w < k || h < k || (w % k) != 0 || (h % k) != 0)
	{
		return false;
	}
	const int bw = w / k;
	const int bh = h / k;
	std::vector<Uint8> idx((size_t)bw * bh);
	for (int y = 0; y < bh; ++y)
	{
		const Uint8 *row = rawRow(src, y * k);
		for (int x = 0; x < bw; ++x)
		{
			idx[(size_t)y * bw + x] = row[x * k];
		}
	}
	return smoothBase(idx.data(), bw, bh, bw, out);
}

/**
 * Smooths a base-resolution palette sprite: converted through the palette to
 * ARGB (index 0 fully transparent) and scaled k times with xBRZ.
 */
bool Canvas32::smoothBase(const Uint8 *indices, int bw, int bh, int pitch, HdFrame &out)
{
	// battlescape sprites: a tile's floor diamond is smoothed as part of a field (see HdSmooth)
	return HdSmooth::smoothPalette(indices, bw, bh, pitch, _colors, _scale, out, bw == 32 && bh >= 24);
}

/**
 * The shaded copy of an HD frame: the tone curve applied to every pixel's
 * color once, so that drawing the frame at that shade is a plain alpha copy.
 * Kept in a size-capped LRU: a frame is normally drawn at the few shades of
 * the light around it, and those repeat frame after frame.
 */
const HdFrame *Canvas32::tonedFor(const HdFrame &hd, int shade, Uint16 tintKey)
{
	shade = std::max(0, std::min(16, shade));
	if (shade == 0 && tintKey == 0x7FFF)
	{
		return &hd;
	}
	// pack frames came or went (a set registered while this frame is recorded): a frame pointer may
	// now mean another picture, so the cache is not trusted until it is cleared - which waits for the
	// end of the flush, as the recorded commands point into it; until then the copies are one-offs
	const bool stale = _tonedGeneration != HdSprites::generation();
	if (stale)
	{
		_tonedStale = true;
	}
	const TonedKey key { &hd, shade | ((int)tintKey << 8) };
	if (!stale)
	{
		auto it = _toned.find(key);
		if (it != _toned.end())
		{
			_tonedLru.splice(_tonedLru.begin(), _tonedLru, it->second.lru);
			return &it->second.frame;
		}
	}
	const size_t bytes = hd.pixels.size() * sizeof(Uint32);
	TonedEntry *entry = nullptr;
	if (stale)
	{
		_tonedTransient.emplace_back();
	}
	else
	{
		entry = &_toned[key];
	}
	HdFrame &out = entry ? entry->frame : _tonedTransient.back();
	out.width = hd.width;
	out.height = hd.height;
	out.rows = hd.rows;
	out.solid = hd.solid;
	out.generated = true;
	out.pixels.resize(hd.pixels.size());
	const Uint32 *toneR = _toneFactor[0][shade];
	const Uint32 *toneG = _toneFactor[1][shade];
	const Uint32 *toneB = _toneFactor[2][shade];
	// the light color, 5 bits per channel in the key (31 = full)
	const Uint32 tr = ((tintKey >> 10) & 31) * 65536u / 31, tg = ((tintKey >> 5) & 31) * 65536u / 31, tb = (tintKey & 31) * 65536u / 31;
	for (size_t i = 0; i < hd.pixels.size(); ++i)
	{
		const Uint32 p = hd.pixels[i];
		if (!(p >> 24))
		{
			out.pixels[i] = 0;
			continue;
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
		out.pixels[i] = (p & 0xFF000000u) | (r << 16) | (g << 8) | b;
	}
	if (entry)
	{
		_tonedLru.push_front(key);
		entry->lru = _tonedLru.begin();
		_tonedBytes += bytes;
	}
	return &out;
}

void Canvas32::clearToned()
{
	_toned.clear();
	_tonedLru.clear();
	_tonedBytes = 0;
}

namespace
{
	/// A light color as the 5-5-5 key of the shaded-frame cache.
	inline Uint16 tintKeyOf(const float *tint)
	{
		auto q = [](float v) -> Uint16 { return (Uint16)std::max(0, std::min(31, (int)(v * 31.0f + 0.5f))); };
		return (Uint16)((q(tint[0]) << 10) | (q(tint[1]) << 5) | q(tint[2]));
	}
}

/**
 * Records an HD blit under the current light field: a flat field is a shaded
 * (and tinted) copy of the frame, a field with a gradient is interpolated per
 * pixel when the command runs.
 */
void Canvas32::recordHdLit(Cmd &cmd, const HdFrame &hd, int shade)
{
	if (_light.flat)
	{
		cmd.type = Cmd::BLIT_HD;
		const int s = std::max(0, std::min(16, (int)std::floor(_light.shade[4] + 0.5f)));
		cmd.hd = tonedFor(hd, s, tintKeyOf(_light.tint[4]));
		cmd.shade = 0;
		record(cmd);
		return;
	}
	cmd.type = Cmd::BLIT_HD_LIT;
	cmd.hd = &hd;
	cmd.shade = 0;
	cmd.tintFlat = true;
	for (int i = 0; i < HdLight::NODES; ++i)
	{
		cmd.lightShade[i] = (Uint16)(std::max(0.0f, std::min(16.0f, _light.shade[i])) * 256.0f + 0.5f);
		for (int c = 0; c < 3; ++c)
		{
			cmd.lightTint[i][c] = (Uint8)std::max(0, std::min(255, (int)(_light.tint[i][c] * 255.0f + 0.5f)));
			if (cmd.lightTint[i][c] != cmd.lightTint[0][c])
			{
				cmd.tintFlat = false;
			}
		}
	}
	lightWeightsFor(hd.width, hd.height); // built on the recording thread
	record(cmd);
}

/**
 * The bilinear corner weights of every pixel of a frame: the pixel is mapped
 * onto the floor diamond at the bottom of the frame (pixels above it, walls
 * and tall objects, take the light of the diamond's upper edge below them).
 */
const Canvas32::LightWeights &Canvas32::lightWeightsFor(int width, int height)
{
	const Uint32 key = ((Uint32)width << 16) | (Uint32)height;
	auto it = _lightWeights.find(key);
	if (it != _lightWeights.end())
	{
		return it->second;
	}
	LightWeights &lw = _lightWeights[key];
	lw.width = width;
	lw.height = height;
	lw.w.resize((size_t)width * height * 5);
	const int k = _scale;
	const float bw = (float)width / k, bh = (float)height / k;
	const float cx = bw / 2.0f, halfW = bw / 2.0f;
	const float dy0 = bh - 16.0f; // the floor diamond: the bottom 16 base rows
	for (int y = 0; y < height; ++y)
	{
		for (int x = 0; x < width; ++x)
		{
			const float px = (x + 0.5f) / k, pyRaw = (y + 0.5f) / k;
			// clamp onto the diamond's upper edges (wall pixels stand on them)
			const float edge = dy0 + std::fabs(px - cx) / halfW * 8.0f;
			const float py = std::max(pyRaw, edge);
			const float a = (px - cx) / halfW;          // -1 .. 1 across
			const float b = (py - dy0) / 8.0f;           // 0 .. 2 down the diamond
			float u = (a + b) / 2.0f, v = (b - a) / 2.0f;
			u = std::max(0.0f, std::min(0.999f, u));
			v = std::max(0.0f, std::min(0.999f, v));
			// the quadrant of the 3x3 node grid and the position inside it
			const int qx = u < 0.5f ? 0 : 1, qy = v < 0.5f ? 0 : 1;
			const float lu = u * 2.0f - qx, lv = v * 2.0f - qy;
			int w0 = (int)((1 - lu) * (1 - lv) * 256.0f + 0.5f);
			int w1 = (int)(lu * (1 - lv) * 256.0f + 0.5f);
			int w2 = (int)(lu * lv * 256.0f + 0.5f);
			int w3 = 256 - w0 - w1 - w2;
			if (w3 < 0) { w0 += w3; w3 = 0; }
			Uint8 *out = &lw.w[((size_t)y * width + x) * 5];
			out[0] = (Uint8)(qy * 2 + qx);
			out[1] = (Uint8)std::min(255, w0);
			out[2] = (Uint8)std::min(255, w1);
			out[3] = (Uint8)std::min(255, w2);
			out[4] = (Uint8)std::min(255, w3);
		}
	}
	return lw;
}

/**
 * Draws an HD frame under a light gradient: every pixel gets the shade and
 * the light color interpolated between the tile's corners, the shade through
 * the palette-calibrated tone curve of the pixel's own brightness.
 */
void Canvas32::doBlitHdLit(const Cmd &cmd, GraphSubset destClip)
{
	const HdFrame &hd = *cmd.hd;
	const int x = cmd.x, y = cmd.y;
	const GraphSubset &srcDomain = cmd.srcDomain;
	const int x0 = std::max({ srcDomain.beg_x + x, destClip.beg_x, 0 });
	const int x1 = std::min({ srcDomain.end_x + x, destClip.end_x, _width, hd.width + x });
	const int y0 = std::max({ srcDomain.beg_y + y, destClip.beg_y, 0 });
	const int y1 = std::min({ srcDomain.end_y + y, destClip.end_y, _height, hd.height + y });
	if (x0 >= x1 || y0 >= y1)
	{
		return;
	}
	auto wit = _lightWeights.find(((Uint32)hd.width << 16) | (Uint32)hd.height);
	if (wit == _lightWeights.end())
	{
		return; // built when recorded
	}
	const Uint8 *weights = wit->second.w.data();
	const int rs = _rshift, gs = _gshift, bs = _bshift;
	const bool tintFlat = cmd.tintFlat;
	const Uint32 flatTint[3] = { cmd.lightTint[4][0] + 1u, cmd.lightTint[4][1] + 1u, cmd.lightTint[4][2] + 1u };
	const bool whiteTint = tintFlat && flatTint[0] == 256 && flatTint[1] == 256 && flatTint[2] == 256;
	for (int dy = y0; dy < y1; ++dy)
	{
		const int sy = dy - y;
		const HdFrame::Span &span = hd.rows[sy];
		const int sx0 = std::max<int>(span.begin, x0 - x);
		const int sx1 = std::min<int>(span.end, x1 - x);
		if (sx0 >= sx1)
		{
			continue;
		}
		const Uint32 *srcRow = hd.row(sy);
		Uint32 *dstRow = rowPtr(dy) + x;
		const Uint8 *wRow = weights + ((size_t)sy * hd.width) * 5;
		for (int sx = sx0; sx < sx1; ++sx)
		{
			const Uint32 p = srcRow[sx];
			const Uint32 a = p >> 24;
			if (!a)
			{
				continue;
			}
			const Uint8 *wq = wRow + sx * 5;
			// the quadrant's four nodes: top-left, top-right, bottom-right, bottom-left of the 3x3 grid
			const int q = wq[0];
			const int n0 = (q >> 1) * 3 + (q & 1), n1 = n0 + 1, n2 = n0 + 4, n3 = n0 + 3;
			const Uint8 *w = wq + 1;
			// interpolated shade (8.8) and light color (0..255)
			const Uint32 shade8 = (w[0] * cmd.lightShade[n0] + w[1] * cmd.lightShade[n1] + w[2] * cmd.lightShade[n2] + w[3] * cmd.lightShade[n3]) >> 8;
			const int s0 = std::min(16, (int)(shade8 >> 8));
			const int s1 = std::min(16, s0 + 1);
			const Uint32 frac = shade8 & 0xFF;
			Uint32 r = (p >> 16) & 0xFF, g = (p >> 8) & 0xFF, b = p & 0xFF;
			const Uint32 m = r > g ? (r > b ? r : b) : (g > b ? g : b);
			Uint32 f[3];
			for (int c = 0; c < 3; ++c)
			{
				const Sint32 fa = (Sint32)_toneFactor[c][s0][m], fb = (Sint32)_toneFactor[c][s1][m];
				f[c] = (Uint32)(fa + (((fb - fa) * (Sint32)frac) >> 8)); // fb <= fa: signed lerp
				if (whiteTint)
				{
					continue;
				}
				if (tintFlat)
				{
					f[c] = (f[c] * flatTint[c]) >> 8;
				}
				else
				{
					const Uint32 t = (w[0] * cmd.lightTint[n0][c] + w[1] * cmd.lightTint[n1][c] + w[2] * cmd.lightTint[n2][c] + w[3] * cmd.lightTint[n3][c]) >> 8;
					f[c] = (f[c] * (t + 1)) >> 8; // t + 1: 255 -> x1
				}
			}
			r = (r * f[0] + 32768u) >> 16;
			g = (g * f[1] + 32768u) >> 16;
			b = (b * f[2] + 32768u) >> 16;
			if (a != 255)
			{
				const Uint32 d = dstRow[sx];
				const Uint32 dr = (d >> rs) & 0xFF, dg = (d >> gs) & 0xFF, db = (d >> bs) & 0xFF;
				const Uint32 ia = 255 - a;
				r = (r * a + dr * ia + 127) / 255;
				g = (g * a + dg * ia + 127) / 255;
				b = (b * a + db * ia + 127) / 255;
			}
			dstRow[sx] = (r << rs) | (g << gs) | (b << bs);
		}
	}
}

namespace
{
	/// The inner loop of the HD blit, specialised per case so that the per-pixel work is only what the case needs.
	/// Frame pixels are 0xAARRGGBB; the canvas pixel layout is given by the shifts.
	template<bool SHADE, bool RECOLOR>
	inline void hdRow(const Uint32 *src, Uint32 *dst, int n, const Uint32 *toneR, const Uint32 *toneG, const Uint32 *toneB,
		const Uint8 *level, const SDL_Color *colors, Uint8 newColor, int shade, int rs, int gs, int bs)
	{
		for (int i = 0; i < n; ++i)
		{
			const Uint32 p = src[i];
			const Uint32 a = p >> 24;
			if (!a)
			{
				continue;
			}
			Uint32 r = (p >> 16) & 0xFF, g = (p >> 8) & 0xFF, b = p & 0xFF;
			if (RECOLOR)
			{
				// the classic recolor keeps the pixel's level on its ramp and moves it to the new group
				const Uint32 lum = (r * 77 + g * 151 + b * 28) >> 8;
				const int newShade = level[lum] + shade;
				const Uint8 idx = newShade > 15 ? (Uint8)0x0F : (Uint8)(newColor | newShade);
				r = colors[idx].r;
				g = colors[idx].g;
				b = colors[idx].b;
			}
			else if (SHADE)
			{
				const Uint32 m = r > g ? (r > b ? r : b) : (g > b ? g : b);
				r = (r * toneR[m] + 32768u) >> 16;
				g = (g * toneG[m] + 32768u) >> 16;
				b = (b * toneB[m] + 32768u) >> 16;
			}
			if (a != 255)
			{
				const Uint32 d = dst[i];
				const Uint32 dr = (d >> rs) & 0xFF, dg = (d >> gs) & 0xFF, db = (d >> bs) & 0xFF;
				const Uint32 ia = 255 - a;
				r = (r * a + dr * ia + 127) / 255;
				g = (g * a + dg * ia + 127) / 255;
				b = (b * a + db * ia + 127) / 255;
			}
			dst[i] = (r << rs) | (g << gs) | (b << bs);
		}
	}
}

/**
 * Draws an HD frame: alpha blended, the shade applied as the palette-calibrated
 * tone curve; with a night-vision color group the pixel is posterized to the
 * palette entry the classic recolor would have produced.
 */
void Canvas32::doBlitHd(const HdFrame &hd, int x, int y, int shade, GraphSubset srcDomain, int newBaseColor, GraphSubset destClip)
{
	const int x0 = std::max({ srcDomain.beg_x + x, destClip.beg_x, 0 });
	const int x1 = std::min({ srcDomain.end_x + x, destClip.end_x, _width, hd.width + x });
	const int y0 = std::max({ srcDomain.beg_y + y, destClip.beg_y, 0 });
	const int y1 = std::min({ srcDomain.end_y + y, destClip.end_y, _height, hd.height + y });
	if (x0 >= x1 || y0 >= y1)
	{
		return;
	}
	shade = std::max(0, std::min(16, shade));
	const Uint32 *toneR = _toneFactor[0][shade];
	const Uint32 *toneG = _toneFactor[1][shade];
	const Uint32 *toneB = _toneFactor[2][shade];
	const Uint8 newColor = newBaseColor ? (Uint8)((newBaseColor - 1) << 4) : 0;
	const int rs = _rshift, gs = _gshift, bs = _bshift;
	for (int dy = y0; dy < y1; ++dy)
	{
		const int sy = dy - y;
		const HdFrame::Span &span = hd.rows[sy];
		const int sx0 = std::max<int>(span.begin, x0 - x);
		const int sx1 = std::min<int>(span.end, x1 - x);
		if (sx0 >= sx1)
		{
			continue;
		}
		const Uint32 *srcRow = hd.row(sy) + sx0;
		Uint32 *dstRow = rowPtr(dy) + x + sx0;
		const int n = sx1 - sx0;
		if (newBaseColor)
		{
			hdRow<true, true>(srcRow, dstRow, n, toneR, toneG, toneB, _level, _colors, newColor, shade, rs, gs, bs);
		}
		else if (shade)
		{
			hdRow<true, false>(srcRow, dstRow, n, toneR, toneG, toneB, _level, _colors, newColor, shade, rs, gs, bs);
		}
		else if (_argbLayout && hd.solid[sy].end > hd.solid[sy].begin)
		{
			// the opaque run of the row is a straight copy (the frame's layout is the canvas's); the soft edges around it blend
			const int s0 = std::max<int>(hd.solid[sy].begin, sx0);
			const int s1 = std::min<int>(hd.solid[sy].end, sx1);
			if (s0 >= s1)
			{
				hdRow<false, false>(srcRow, dstRow, n, toneR, toneG, toneB, _level, _colors, newColor, shade, rs, gs, bs);
				continue;
			}
			hdRow<false, false>(srcRow, dstRow, s0 - sx0, toneR, toneG, toneB, _level, _colors, newColor, shade, rs, gs, bs);
			const Uint32 *sp = hd.row(sy) + s0;
			Uint32 *dp = rowPtr(dy) + x + s0;
			for (int i = 0, m = s1 - s0; i < m; ++i)
			{
				dp[i] = sp[i] & 0x00FFFFFFu;
			}
			hdRow<false, false>(hd.row(sy) + s1, rowPtr(dy) + x + s1, sx1 - s1, toneR, toneG, toneB, _level, _colors, newColor, shade, rs, gs, bs);
		}
		else
		{
			hdRow<false, false>(srcRow, dstRow, n, toneR, toneG, toneB, _level, _colors, newColor, shade, rs, gs, bs);
		}
	}
}

}
