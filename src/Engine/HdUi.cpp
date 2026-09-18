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
#include "HdUi.h"
#include <algorithm>
#include <cmath>
#include <chrono>
#include <cstring>
#include "Logger.h"
#include "Font.h"
#include "HdSmooth.h"
#include "HdWorkers.h"
#include "Options.h"
#include "Screen.h"
#include "Surface.h"

namespace OpenXcom
{

namespace
{

const size_t SMOOTH_CACHE_BYTES = 192u << 20;

inline Uint32 packColor(const SDL_Color &c)
{
	return 0xFF000000u | ((Uint32)c.r << 16) | ((Uint32)c.g << 8) | c.b;
}

/// Coverage of the triangle {i + j < legs} (the top-left corner of a k x k block) over the unit pixel (i, j).
inline float cornerCoverage(int i, int j, int legs)
{
	const float s = (float)(legs - i - j);
	if (s <= 0.0f) return 0.0f;
	if (s >= 2.0f) return 1.0f;
	if (s <= 1.0f) return s * s * 0.5f;
	return 1.0f - (2.0f - s) * (2.0f - s) * 0.5f;
}

}

HdUi &HdUi::instance()
{
	static HdUi ui;
	return ui;
}

bool HdUi::active()
{
	Screen *screen = Screen::current();
	return screen && Options::oxceHdUi > 0 && screen->isLayered() && screen->getWorldScale() >= 2;
}

bool HdUi::isScreen(const SDL_Surface *dest)
{
	Screen *screen = Screen::current();
	return screen && dest == screen->getSurface();
}

int HdUi::mode()
{
	return Options::oxceHdUi;
}

bool HdUi::target(SDL_Surface *&dest, int &k, const SDL_Color *&colors) const
{
	Screen *screen = Screen::current();
	if (!screen || !active())
	{
		return false;
	}
	dest = screen->getWorldSurface();
	k = screen->getWorldScale();
	colors = screen->getPalette();
	return dest && dest->format->BytesPerPixel == 4 && colors;
}

SDL_Rect HdUi::worldClip(SDL_Surface *dest, int k) const
{
	SDL_Rect r;
	if (_clipW > 0 && _clipH > 0)
	{
		r.x = (Sint16)std::max(0, _clipX * k);
		r.y = (Sint16)std::max(0, _clipY * k);
		const int x1 = std::min(dest->w, (_clipX + _clipW) * k), y1 = std::min(dest->h, (_clipY + _clipH) * k);
		r.w = (Uint16)std::max(0, x1 - r.x);
		r.h = (Uint16)std::max(0, y1 - r.y);
	}
	else
	{
		r.x = 0; r.y = 0; r.w = (Uint16)dest->w; r.h = (Uint16)dest->h;
	}
	return r;
}

void HdUi::setClip(int x, int y, int w, int h)
{
	_clipX = x; _clipY = y; _clipW = w; _clipH = h;
}

/**
 * Nearest scaling of palette pixels (index 0 transparent) into the world.
 * The rows are split between the render threads for big surfaces.
 */
void HdUi::drawPixels(const Uint8 *pixels, int pitch, int w, int h, int x, int y, const SDL_Color *colors)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || !pixels || w <= 0 || h <= 0)
	{
		return;
	}
	if (colors) pal = colors;
	Uint32 lut[256];
	for (int i = 0; i < 256; ++i) lut[i] = packColor(pal[i]);
	const SDL_Rect clip = worldClip(dest, k);
	const int cx0 = clip.x, cy0 = clip.y, cx1 = clip.x + clip.w, cy1 = clip.y + clip.h;
	// the base rows that land inside the clip
	const int y0 = std::max(0, (cy0 - y * k + k - 1) / k), y1 = std::min(h, (cy1 - y * k + k - 1) / k);
	const int x0 = std::max(0, (cx0 - x * k + k - 1) / k), x1 = std::min(w, (cx1 - x * k + k - 1) / k);
	if (y0 >= y1 || x0 >= x1)
	{
		return;
	}
	Uint8 *dp = (Uint8*)dest->pixels;
	const int dpitch = dest->pitch;
	auto rows = [&](int ra, int rb)
	{
		for (int sy = ra; sy < rb; ++sy)
		{
			const Uint8 *src = pixels + (size_t)sy * pitch;
			for (int ky = 0; ky < k; ++ky)
			{
				const int dy = (y + sy) * k + ky;
				if (dy < cy0 || dy >= cy1) continue;
				Uint32 *drow = (Uint32*)(dp + (size_t)dy * dpitch);
				for (int sx = x0; sx < x1; ++sx)
				{
					const Uint8 idx = src[sx];
					if (!idx) continue;
					const Uint32 v = lut[idx];
					const int dx0 = std::max(cx0, (x + sx) * k), dx1 = std::min(cx1, (x + sx + 1) * k);
					for (int dx = dx0; dx < dx1; ++dx) drow[dx] = v;
				}
			}
		}
	};
	const int n = y1 - y0;
	if (n >= 64)
	{
		HdWorkers &pool = HdWorkers::instance();
		const int jobs = std::max(1, std::min(n / 16, pool.threads() * 2));
		pool.run(jobs, [&](int job)
		{
			rows(y0 + (int)((long long)n * job / jobs), y0 + (int)((long long)n * (job + 1) / jobs));
		});
	}
	else
	{
		rows(y0, y1);
	}
}

const SDL_Color *HdUi::paletteOf(const Surface *surface)
{
	if (surface)
	{
		// (getSurface is not const; nothing is changed here)
		SDL_Surface *sdl = const_cast<Surface*>(surface)->getSurface();
		if (sdl && sdl->format->palette)
		{
			return sdl->format->palette->colors;
		}
	}
	Screen *screen = Screen::current();
	return screen ? screen->getPalette() : nullptr;
}

void HdUi::fillRect(int x, int y, int w, int h, Uint8 color, const SDL_Color *colors)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || w <= 0 || h <= 0)
	{
		return;
	}
	if (colors) pal = colors;
	const SDL_Rect clip = worldClip(dest, k);
	const int x0 = std::max((int)clip.x, x * k), y0 = std::max((int)clip.y, y * k);
	const int x1 = std::min(clip.x + clip.w, (x + w) * k), y1 = std::min(clip.y + clip.h, (y + h) * k);
	if (x0 >= x1 || y0 >= y1)
	{
		return;
	}
	const Uint32 v = packColor(pal[color]);
	for (int dy = y0; dy < y1; ++dy)
	{
		Uint32 *row = (Uint32*)((Uint8*)dest->pixels + (size_t)dy * dest->pitch);
		for (int dx = x0; dx < x1; ++dx) row[dx] = v;
	}
}

void HdUi::blendFrame(SDL_Surface *dest, const HdFrame &frame, int x, int y, const SDL_Rect *clip)
{
	const int cx0 = clip->x, cy0 = clip->y, cx1 = clip->x + clip->w, cy1 = clip->y + clip->h;
	const int x0 = std::max(cx0, x), y0 = std::max(cy0, y);
	const int x1 = std::min(cx1, x + frame.width), y1 = std::min(cy1, y + frame.height);
	if (x0 >= x1 || y0 >= y1)
	{
		return;
	}
	auto rows = [&](int ra, int rb)
	{
		for (int dy = ra; dy < rb; ++dy)
		{
			const Uint32 *src = frame.row(dy - y);
			Uint32 *drow = (Uint32*)((Uint8*)dest->pixels + (size_t)dy * dest->pitch);
			for (int dx = x0; dx < x1; ++dx)
			{
				const Uint32 s = src[dx - x];
				const Uint32 a = s >> 24;
				if (!a) continue;
				if (a == 255)
				{
					drow[dx] = s | 0xFF000000u;
					continue;
				}
				const Uint32 d = drow[dx];
				const Uint32 ia = 255 - a;
				const Uint32 r = (((s >> 16) & 0xFF) * a + ((d >> 16) & 0xFF) * ia) / 255;
				const Uint32 g = (((s >> 8) & 0xFF) * a + ((d >> 8) & 0xFF) * ia) / 255;
				const Uint32 b = ((s & 0xFF) * a + (d & 0xFF) * ia) / 255;
				drow[dx] = 0xFF000000u | (r << 16) | (g << 8) | b;
			}
		}
	};
	const int n = y1 - y0;
	if (n >= 256)
	{
		HdWorkers &pool = HdWorkers::instance();
		const int jobs = std::max(1, std::min(n / 64, pool.threads() * 2));
		pool.run(jobs, [&](int job)
		{
			rows(y0 + (int)((long long)n * job / jobs), y0 + (int)((long long)n * (job + 1) / jobs));
		});
	}
	else
	{
		rows(y0, y1);
	}
}

/**
 * The smoothed copy of a surface, kept while its pixels stay the same (a
 * hash of the pixels is compared; surfaces change rarely compared to how
 * often they are blitted). LRU, capped by size.
 */
const HdFrame *HdUi::smoothed(const Surface *surface, int k, const SDL_Color *colors, Uint64 pixelHash)
{
	const int w = surface->getWidth(), h = surface->getHeight();
	const Uint8 *pixels = (const Uint8*)surface->getBuffer();
	const int pitch = surface->getPitch();
	// the palette is part of the content
	Uint64 hash = pixelHash;
	for (int i = 0; i < 256; ++i)
	{
		hash ^= (Uint64)colors[i].r | ((Uint64)colors[i].g << 8) | ((Uint64)colors[i].b << 16);
		hash *= 1099511628211ULL;
	}
	if (SmoothEntry *e = cached(surface, hash, k))
	{
		return &e->frame;
	}
	HdFrame frame;
	// the interface is mirrored on the main thread, so the smoothing may use the whole pool
	if (!HdSmooth::smoothPalette(pixels, w, h, pitch, colors, k, frame, false, true))
	{
		return nullptr;
	}
	return cache(surface, pixelHash, hash, k, std::move(frame));
}

HdUi::SmoothEntry *HdUi::cached(const Surface *key, Uint64 hash, int k)
{
	auto it = _smooth.find(key);
	if (it != _smooth.end() && it->second.hash == hash && it->second.k == k)
	{
		_smoothLru.splice(_smoothLru.begin(), _smoothLru, it->second.lru);
		return &it->second;
	}
	return nullptr;
}

const HdFrame *HdUi::cache(const Surface *key, Uint64 pixelHash, Uint64 hash, int k, HdFrame &&frame, const HdUiArt::Art *art, int artX, int artY)
{
	int misses = 0;
	auto it = _smooth.find(key);
	if (it != _smooth.end())
	{
		misses = it->second.artMisses;
		_smoothBytes -= it->second.frame.pixels.size() * 4;
		_smoothLru.erase(it->second.lru);
		_smooth.erase(it);
	}
	if (!frame.pixels.empty())
	{
		frame.buildSpans();
	}
	SmoothEntry &e = _smooth[key];
	e.hash = hash;
	e.pixelHash = pixelHash;
	e.k = k;
	e.art = art;
	e.artX = artX;
	e.artY = artY;
	e.artMisses = art ? 0 : misses + 1;
	e.frame = std::move(frame);
	_smoothLru.push_front(key);
	e.lru = _smoothLru.begin();
	_smoothBytes += e.frame.pixels.size() * 4;
	while (_smoothBytes > SMOOTH_CACHE_BYTES && _smoothLru.size() > 1)
	{
		const Surface *old = _smoothLru.back();
		auto oit = _smooth.find(old);
		if (oit != _smooth.end())
		{
			_smoothBytes -= oit->second.frame.pixels.size() * 4;
			_smooth.erase(oit);
		}
		_smoothLru.pop_back();
	}
	return &_smooth[key].frame;
}

/**
 * An HD picture made ready for drawing: scaled to the world scale (bilinear
 * when the picture's scale differs) and, when it came with its reference
 * palette, re-tinted for the palette in force: every HD pixel is scaled by
 * the ratio of the current to the reference colour of the classic pixel under
 * it, so that screens that re-tint an image through their palette (the
 * "backpals") re-tint the picture the same way.
 */
const HdFrame *HdUi::prepared(const HdUiArt::Art *art, const Surface *key, int k, const SDL_Color *colors)
{
	Uint64 hash = art->hash ^ 0x9E3779B97F4A7C15ULL;
	const bool tint = !art->palette.empty();
	if (tint)
	{
		for (int i = 0; i < 256; ++i)
		{
			hash ^= (Uint64)colors[i].r | ((Uint64)colors[i].g << 8) | ((Uint64)colors[i].b << 16);
			hash *= 1099511628211ULL;
		}
	}
	if (SmoothEntry *e = cached(key, hash, k))
	{
		return &e->frame;
	}
	const int W = art->baseWidth * k, H = art->baseHeight * k;
	const int s = art->scale;
	const HdFrame &src = HdUiArt::frame(art);
	if (src.pixels.empty())
	{
		return nullptr;
	}
	HdFrame frame;
	frame.width = W;
	frame.height = H;
	frame.pixels.assign((size_t)W * H, 0u);
	frame.generated = false;
	// the colour factors of the palette entries
	float factor[256][3];
	bool differs = false;
	if (tint)
	{
		for (int i = 0; i < 256; ++i)
		{
			const SDL_Color &ref = art->palette[i], &cur = colors[i];
			factor[i][0] = (cur.r + 1.0f) / (ref.r + 1.0f);
			factor[i][1] = (cur.g + 1.0f) / (ref.g + 1.0f);
			factor[i][2] = (cur.b + 1.0f) / (ref.b + 1.0f);
			if (ref.r != cur.r || ref.g != cur.g || ref.b != cur.b) differs = true;
		}
	}
	auto rows = [&](int ya, int yb)
	{
		for (int y = ya; y < yb; ++y)
		{
			Uint32 *dst = &frame.pixels[(size_t)y * W];
			const Uint8 *baseRow = &art->base[(size_t)(y / k) * art->baseWidth];
			for (int x = 0; x < W; ++x)
			{
				Uint32 p;
				if (s == k)
				{
					p = src.pixels[(size_t)y * src.width + x];
				}
				else
				{
					// bilinear from the picture's own scale
					const float fx = (x + 0.5f) * s / k - 0.5f, fy = (y + 0.5f) * s / k - 0.5f;
					int x0 = (int)std::floor(fx), y0 = (int)std::floor(fy);
					const float tx = fx - x0, ty = fy - y0;
					const int x1 = std::min(x0 + 1, src.width - 1), y1 = std::min(y0 + 1, src.height - 1);
					x0 = std::max(x0, 0); y0 = std::max(y0, 0);
					const Uint32 p00 = src.pixels[(size_t)y0 * src.width + x0], p10 = src.pixels[(size_t)y0 * src.width + x1];
					const Uint32 p01 = src.pixels[(size_t)y1 * src.width + x0], p11 = src.pixels[(size_t)y1 * src.width + x1];
					Uint32 out = 0;
					for (int shift = 0; shift < 32; shift += 8)
					{
						const float c = ((p00 >> shift) & 0xFF) * (1 - tx) * (1 - ty) + ((p10 >> shift) & 0xFF) * tx * (1 - ty)
							+ ((p01 >> shift) & 0xFF) * (1 - tx) * ty + ((p11 >> shift) & 0xFF) * tx * ty;
						out |= (Uint32)std::min(255, (int)(c + 0.5f)) << shift;
					}
					p = out;
				}
				if (differs)
				{
					const Uint8 idx = baseRow[x / k];
					const float *f = factor[idx];
					const int r = std::min(255, (int)(((p >> 16) & 0xFF) * f[0] + 0.5f));
					const int g = std::min(255, (int)(((p >> 8) & 0xFF) * f[1] + 0.5f));
					const int b = std::min(255, (int)((p & 0xFF) * f[2] + 0.5f));
					p = (p & 0xFF000000u) | ((Uint32)r << 16) | ((Uint32)g << 8) | (Uint32)b;
				}
				dst[x] = p;
			}
		}
	};
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(H / 64, pool.threads() * 2));
	pool.run(jobs, [&](int job)
	{
		rows((int)((long long)H * job / jobs), (int)((long long)H * (job + 1) / jobs));
	});
	return cache(key, art->hash, hash, k, std::move(frame));
}

void HdUi::drawArt(const HdUiArt::Art *art, const Surface *key, int x, int y, const SDL_Color *colors)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || !art || !key)
	{
		return;
	}
	if (colors) pal = colors;
	const HdFrame *frame = prepared(art, key, k, pal);
	if (frame)
	{
		const SDL_Rect clip = worldClip(dest, k);
		blendFrame(dest, *frame, x * k, y * k, &clip);
	}
}

void HdUi::drawSurface(const Surface *surface, int x, int y, bool smooth)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || !surface || surface->getWidth() <= 0 || surface->getHeight() <= 0)
	{
		return;
	}
	const auto t0 = std::chrono::steady_clock::now();
	++_calls;
	++_frameCalls;
	const int w = surface->getWidth(), h = surface->getHeight();
	// the worst call of the frame, with the road it took: "HD UI 160 ms over 2 surfaces" says that the
	// mirror is to blame but not which surface or why, and every road here costs a different amount
	const char *why = "plain";
	struct Timing
	{
		HdUi &ui; std::chrono::steady_clock::time_point t; int w, h; const char *&why;
		~Timing()
		{
			const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t).count();
			ui._frameMs += ms;
			if (ms > ui._worstMs) { ui._worstMs = ms; ui._worstW = w; ui._worstH = h; ui._worstWhy = why; }
		}
	} timing { *this, t0, w, h, why };
	// the surface's own palette: an SDL blit shows a surface with the colours it was given, remapping
	// them to the screen's palette by nearest colour when the two differ (a state's surfaces under a
	// popup with another palette, a text with its own); indexing the screen's palette instead shows
	// wrong colours there (black text, most visibly)
	if (const SDL_Color *own = paletteOf(surface)) pal = own;
	const Uint8 *pixels = (const Uint8*)surface->getBuffer();
	const int pitch = surface->getPitch();
	// a surface far larger than the screen is never a picture and never worth smoothing: hashing it
	// costs megabytes a frame and xBRZ of it costs hundreds (NextTurnState makes its backdrop screen
	// width BY screen width). drawPixels below clips to what is actually seen, so the frame is the
	// same; measured 177 ms -> nothing on the end-of-turn screen
	const bool oversize = (long long)w * h > 4LL * (dest->w / k) * (dest->h / k);
	if (oversize)
	{
		why = "oversize";
		static int said = 0;
		if (said < 4) { ++said; Log(LOG_INFO) << "HD oversize surface: " << w << "x" << h << " drawn plainly"; }
	}
	const bool wantHash = !oversize && k >= 2 && (HdUiArt::count() > 0 || (smooth && k <= 6));
	const Uint64 pixelHash = wantHash ? HdUiArt::hashPixels(pixels, pitch, w, h) : 0;
	// an HD picture of this image (hd/UI): by content, so a state's copy of a mod image (or of a part
	// of it) finds it too; the answer is remembered with the surface's content
	if (!oversize && k >= 2 && HdUiArt::count() > 0)
	{
		const HdUiArt::Art *art = nullptr;
		int artX = 0, artY = 0;
		bool known = false;
		auto it = _smooth.find(surface);
		if (it != _smooth.end() && it->second.k == k && it->second.pixelHash == pixelHash)
		{
			// the same content as last time: the answer is known (a picture, or none)
			art = it->second.art;
			artX = it->second.artX;
			artY = it->second.artY;
			known = true;
		}
		if (!known)
		{
			art = HdUiArt::find(pixelHash, w, h);
			// a part of an image: searched for surfaces of some size, and not for ever for a surface
			// whose content keeps changing (counters, bars: they are never a picture)
			const int misses = it == _smooth.end() ? 0 : it->second.artMisses;
			if (!art && w >= 24 && h >= 16 && misses < 3)
			{
				why = "crop scan";
				art = HdUiArt::findCrop(pixels, pitch, w, h, artX, artY);
			}
			if (art)
			{
				cache(surface, pixelHash, pixelHash ^ 0xA5A5A5A5A5A5A5A5ULL, k, HdFrame(), art, artX, artY);
			}
			else if (!(smooth && k <= 6))
			{
				cache(surface, pixelHash, pixelHash ^ 0x5A5A5A5A5A5A5A5AULL, k, HdFrame());
			}
			// (with smoothing on, the xBRZ entry made next remembers the miss)
		}
		if (art)
		{
			why = "picture";
			const HdFrame *frame = prepared(art, art->baseSurface, k, pal);
			if (frame)
			{
				// the picture placed so that the surface's part of it lands here, clipped to the surface
				const SDL_Rect outer = worldClip(dest, k);
				SDL_Rect clip;
				clip.x = (Sint16)std::max((int)outer.x, x * k);
				clip.y = (Sint16)std::max((int)outer.y, y * k);
				const int x1 = std::min(outer.x + outer.w, (x + w) * k), y1 = std::min(outer.y + outer.h, (y + h) * k);
				clip.w = (Uint16)std::max(0, x1 - clip.x);
				clip.h = (Uint16)std::max(0, y1 - clip.y);
				blendFrame(dest, *frame, (x - artX) * k, (y - artY) * k, &clip);
			}
			return;
		}
	}
	if (!oversize && smooth && k >= 2 && k <= 6)
	{
		why = "xBRZ";
		const HdFrame *frame = smoothed(surface, k, pal, pixelHash);
		if (frame)
		{
			const SDL_Rect clip = worldClip(dest, k);
			blendFrame(dest, *frame, x * k, y * k, &clip);
			return;
		}
	}
	drawPixels(pixels, pitch, w, h, x, y, pal);
}

/**
 * A glyph k times bigger with smooth edges: every source pixel becomes a
 * k x k block, and at the corners where the classic Scale2x rule applies
 * (the two neighbours across the corner agree with each other and disagree
 * with the two opposite ones) the block's corner is chamfered along the
 * diagonal, with the exact coverage of the cut as anti-aliasing; a concave
 * corner gets the triangle filled instead. Straight edges stay straight,
 * dots and line ends stay square, staircases become 45-degree edges. The
 * shape decisions use the silhouette; the palette offset of a pixel (the
 * font's shading) is copied to its block.
 */
void HdUi::scaleShape(const Uint8 *src, int w, int h, int k, std::vector<Uint8> &value, std::vector<Uint8> &cov,
                       std::vector<Uint8> *value2, std::vector<Uint8> *mix)
{
	const int W = w * k, H = h * k;
	value.assign((size_t)W * H, 0);
	cov.assign((size_t)W * H, 0);
	if (value2) value2->assign((size_t)W * H, 0);
	if (mix) mix->assign((size_t)W * H, 0);
	if (k < 1 || k > 64)
	{
		return;
	}
	auto at = [&](int x, int y) -> int { return (x < 0 || y < 0 || x >= w || y >= h) ? 0 : src[(size_t)y * w + x]; };
	std::vector<float> blockCov((size_t)k * k), blockMix((size_t)k * k);
	std::vector<Uint8> blockVal((size_t)k * k), blockVal2((size_t)k * k);
	for (int y = 0; y < h; ++y)
	{
		for (int x = 0; x < w; ++x)
		{
			const int e = at(x, y);
			const int b = at(x, y - 1), d = at(x - 1, y), f = at(x + 1, y), hh = at(x, y + 1);
			// per corner: the two neighbours across it and their opposites (the Scale2x rule compares
			// the values: a corner is chamfered when the two neighbours across it agree and each
			// differs from its opposite), flips of the coverage function
			struct Corner { int s1, s2, o1, o2; bool flipX, flipY; };
			const Corner corners[4] = {
				{ b, d, hh, f, false, false },   // top-left: up & left
				{ b, f, hh, d, true, false },    // top-right: up & right
				{ hh, d, b, f, false, true },    // bottom-left: down & left
				{ hh, f, b, d, true, true },     // bottom-right: down & right
			};
			for (int j = 0; j < k; ++j)
				for (int i = 0; i < k; ++i)
				{
					blockCov[(size_t)j * k + i] = e ? 1.0f : 0.0f;
					blockVal[(size_t)j * k + i] = (Uint8)e;
					blockVal2[(size_t)j * k + i] = 0;
					blockMix[(size_t)j * k + i] = 0.0f;
				}
			for (const Corner &cn : corners)
			{
				// the decisions use the silhouette (drawn or not): the shades inside a glyph (its bevel)
				// keep their pixel boundaries, chamfering those cuts wedges into the letters
				const bool S1 = cn.s1 != 0, S2 = cn.s2 != 0, O1 = cn.o1 != 0, O2 = cn.o2 != 0, E = e != 0;
				if (S1 != S2 || S1 == O1 || S2 == O2 || S1 == E)
				{
					continue;
				}
				// the shade a filled corner gets: the main one (the lower offset) of the two neighbours
				const int n = std::min(cn.s1, cn.s2);
				// a cut takes the block's whole corner half (a staircase becomes a straight diagonal);
				// a fill only half of that, as Scale2x does: a thin stroke's corner gets a small bridge,
				// not a spike (its own pixels are line ends and are never cut)
				const int legs = E ? k : (k + 1) / 2;
				for (int j = 0; j < k; ++j)
					for (int i = 0; i < k; ++i)
					{
						const float t = cornerCoverage(cn.flipX ? k - 1 - i : i, cn.flipY ? k - 1 - j : j, legs);
						if (t <= 0.0f) continue;
						const size_t o = (size_t)j * k + i;
						if (E)
						{
							// convex corner of the shape: cut
							blockCov[o] *= 1.0f - t;
						}
						else if (t > blockCov[o])
						{
							// concave corner: fill the triangle
							blockCov[o] = t;
							blockVal[o] = (Uint8)n;
						}
					}
			}
			for (int j = 0; j < k; ++j)
				for (int i = 0; i < k; ++i)
				{
					const size_t o = (size_t)(y * k + j) * W + (x * k + i);
					const size_t bo = (size_t)j * k + i;
					const float cv = blockCov[bo];
					if (cv > 0.002f)
					{
						cov[o] = (Uint8)std::min(255.0f, cv * 255.0f + 0.5f);
						value[o] = blockVal[bo];
						if (value2 && mix && blockMix[bo] > 0.002f)
						{
							(*value2)[o] = blockVal2[bo];
							(*mix)[o] = (Uint8)std::min(255.0f, blockMix[bo] * 255.0f + 0.5f);
						}
					}
				}
		}
	}
}

/**
 * A glyph k times bigger with smooth edges: every source pixel becomes a
 * k x k block, and at the corners where the classic Scale2x rule applies
 * (the two neighbours across the corner agree with each other and disagree
 * with the two opposite ones) the block's corner is chamfered along the
 * diagonal, with the exact coverage of the cut as anti-aliasing; a concave
 * corner gets the triangle filled instead. Straight edges stay straight,
 * dots and line ends stay square, staircases become 45-degree edges. The
 * shape decisions use the silhouette; the palette offset of a pixel (the
 * font's shading) is copied to its block.
 */
/**
 * A glyph k times bigger with smooth edges: every source pixel becomes a
 * k x k block, and at the corners where the classic Scale2x rule applies
 * (the two neighbours across the corner agree with each other and disagree
 * with the two opposite ones) the block's corner is chamfered along the
 * diagonal, with the exact coverage of the cut as anti-aliasing; a concave
 * corner gets the triangle filled instead. Straight edges stay straight,
 * dots and line ends stay square, staircases become 45-degree edges. The
 * shape decisions use the silhouette; the palette offset of a pixel (the
 * font's shading) is copied to its block.
 */
const HdUi::Glyph &HdUi::glyph(const Font *font, UCode c, int k)
{
	GlyphKey key = { font, c, k };
	auto it = _glyphs.find(key);
	if (it != _glyphs.end())
	{
		return it->second;
	}
	Glyph &g = _glyphs[key];
	SurfaceCrop crop = font->getChar(c);
	const Surface *sheet = crop.getSurface();
	const SDL_Rect *r = crop.getCrop();
	const int w = r->w, h = r->h;
	if (!sheet || w <= 0 || h <= 0)
	{
		return g;
	}
	std::vector<Uint8> src((size_t)w * h);
	for (int y = 0; y < h; ++y)
		for (int x = 0; x < w; ++x)
			src[(size_t)y * w + x] = sheet->getPixel(r->x + x, r->y + y);
	g.w = w * k;
	g.h = h * k;
	scaleShape(src.data(), w, h, k, g.value, g.cov, &g.value2, &g.mix);
	return g;
}

void HdUi::drawGlyph(const Font *font, UCode c, int x, int y, int color, int mul, int mid, const SDL_Color *colors)
{
	SDL_Surface *dest;
	int k;
	const SDL_Color *pal;
	if (!target(dest, k, pal) || !font || k > 64)
	{
		return;
	}
	if (colors) pal = colors;
	const Glyph &g = glyph(font, c, k);
	if (g.w <= 0)
	{
		return;
	}
	const SDL_Rect clip = worldClip(dest, k);
	const int cx0 = clip.x, cy0 = clip.y, cx1 = clip.x + clip.w, cy1 = clip.y + clip.h;
	const int ox = x * k, oy = y * k;
	const int x0 = std::max(cx0, ox), y0 = std::max(cy0, oy), x1 = std::min(cx1, ox + g.w), y1 = std::min(cy1, oy + g.h);
	// the colours of the glyph's shades (font palettes use offsets 1-5); the index wraps like the
	// classic byte arithmetic (Text::draw's PaletteShift)
	Uint32 lut[8] = {0, 0, 0, 0, 0, 0, 0, 0};
	for (int v = 1; v < 8; ++v)
	{
		const int inverse = mid ? 2 * (mid - v) : 0;
		const Uint8 idx = (Uint8)(color + v * mul + inverse);
		lut[v] = packColor(pal[idx]);
	}
	for (int dy = y0; dy < y1; ++dy)
	{
		Uint32 *drow = (Uint32*)((Uint8*)dest->pixels + (size_t)dy * dest->pitch);
		const size_t go = (size_t)(dy - oy) * g.w;
		for (int dx = x0; dx < x1; ++dx)
		{
			const size_t gi = go + (dx - ox);
			const Uint8 cv = g.cov[gi];
			if (!cv) continue;
			Uint32 s = lut[g.value[gi] & 7];
			const Uint8 m = g.mix[gi];
			if (m)
			{
				const Uint32 s2 = lut[g.value2[gi] & 7];
				const Uint32 im = 255 - m;
				s = 0xFF000000u | (((((s >> 16) & 0xFF) * im + ((s2 >> 16) & 0xFF) * m) / 255) << 16)
					| (((((s >> 8) & 0xFF) * im + ((s2 >> 8) & 0xFF) * m) / 255) << 8) | (((s & 0xFF) * im + (s2 & 0xFF) * m) / 255);
			}
			if (cv == 255)
			{
				drow[dx] = s;
				continue;
			}
			const Uint32 d = drow[dx];
			const Uint32 a = cv, ia = 255 - cv;
			const Uint32 r = (((s >> 16) & 0xFF) * a + ((d >> 16) & 0xFF) * ia) / 255;
			const Uint32 gg = (((s >> 8) & 0xFF) * a + ((d >> 8) & 0xFF) * ia) / 255;
			const Uint32 b = ((s & 0xFF) * a + (d & 0xFF) * ia) / 255;
			drow[dx] = 0xFF000000u | (r << 16) | (gg << 8) | b;
		}
	}
}

void HdUi::frameDone()
{
	if (!active())
	{
		return;
	}
	_totalMs += _frameMs;
	_lastFrameMs = _frameMs;
	_lastCalls = _frameCalls;
	_lastWorstMs = _worstMs;
	_lastWorstW = _worstW;
	_lastWorstH = _worstH;
	_lastWorstWhy = _worstWhy;
	_frameMs = 0;
	_frameCalls = 0;
	_worstMs = 0;
	if (++_frames % 600 == 0)
	{
		Log(LOG_VERBOSE) << "HD interface: " << _totalMs / 600 << " ms/frame, " << _calls / 600 << " surfaces/frame, "
			<< _smooth.size() << " smoothed surfaces cached (" << (_smoothBytes >> 20) << " MB), " << _glyphs.size() << " glyphs";
		_totalMs = 0;
		_calls = 0;
	}
}

void HdUi::clearCaches()
{
	_smooth.clear();
	_smoothLru.clear();
	_smoothBytes = 0;
	_glyphs.clear();
}

}
