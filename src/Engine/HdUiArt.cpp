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
#include "HdUiArt.h"
#include <cstring>
#include <cstdlib>
#include <map>
#include <memory>
#include <unordered_map>
#include <algorithm>
#include <cmath>
#include <list>
#include "HdWorkers.h"
#include "Logger.h"
#include "Options.h"
#include "Screen.h"
#include "Surface.h"

namespace OpenXcom
{

namespace HdUiArt
{

namespace
{

struct Key
{
	Uint64 hash;
	int w, h;
	bool operator==(const Key &o) const { return hash == o.hash && w == o.w && h == o.h; }
};
struct KeyHash
{
	size_t operator()(const Key &k) const { return (size_t)(k.hash ^ ((Uint64)k.w << 40) ^ ((Uint64)k.h << 52)); }
};

std::vector<std::unique_ptr<Art>> arts;
std::unordered_map<Key, const Art*, KeyHash> byContent;
std::unordered_map<const Surface*, const Art*> bySurface;

}

Uint64 hashPixels(const Uint8 *pixels, int pitch, int w, int h)
{
	Uint64 hash = 1469598103934665603ULL;
	for (int y = 0; y < h; ++y)
	{
		const Uint8 *row = pixels + (size_t)y * pitch;
		for (int x = 0; x < w; ++x)
		{
			hash ^= row[x];
			hash *= 1099511628211ULL;
		}
	}
	return hash;
}

bool add(const std::string &name, const Surface *base, HdFrame &&frame, std::vector<SDL_Color> palette)
{
	if (!base || base->getWidth() <= 0 || base->getHeight() <= 0 || frame.width <= 0 || frame.height <= 0)
	{
		return false;
	}
	const int bw = base->getWidth(), bh = base->getHeight();
	if (frame.width % bw != 0 || frame.height % bh != 0 || frame.width / bw != frame.height / bh)
	{
		Log(LOG_WARNING) << "HD interface: hd/UI/" << name << ".png is " << frame.width << "x" << frame.height
			<< ", not a whole multiple of the image's " << bw << "x" << bh << " - ignored";
		return false;
	}
	std::unique_ptr<Art> art(new Art());
	art->name = name;
	art->scale = frame.width / bw;
	art->baseWidth = bw;
	art->baseHeight = bh;
	const Uint8 *pixels = (const Uint8*)base->getBuffer();
	const int pitch = base->getPitch();
	art->base.resize((size_t)bw * bh);
	for (int y = 0; y < bh; ++y)
	{
		memcpy(&art->base[(size_t)y * bw], pixels + (size_t)y * pitch, bw);
	}
	art->hash = hashPixels(pixels, pitch, bw, bh);
	art->baseSurface = base;
	art->frame = std::move(frame);
	art->frame.buildSpans();
	art->palette = std::move(palette);
	const Art *p = art.get();
	byContent[Key{ p->hash, bw, bh }] = p;
	bySurface[base] = p;
	arts.push_back(std::move(art));
	return true;
}

bool addLazy(const std::string &name, const Surface *base, const std::string &path, int width, int height, std::vector<SDL_Color> palette)
{
	if (!base || base->getWidth() <= 0 || base->getHeight() <= 0 || width <= 0 || height <= 0)
	{
		return false;
	}
	const int bw = base->getWidth(), bh = base->getHeight();
	if (width % bw != 0 || height % bh != 0 || width / bw != height / bh)
	{
		Log(LOG_WARNING) << "HD interface: " << path << " is " << width << "x" << height
			<< ", not a whole multiple of the image's " << bw << "x" << bh << " - ignored";
		return false;
	}
	std::unique_ptr<Art> art(new Art());
	art->name = name;
	art->path = path;
	art->scale = width / bw;
	art->baseWidth = bw;
	art->baseHeight = bh;
	const Uint8 *pixels = (const Uint8*)base->getBuffer();
	const int pitch = base->getPitch();
	art->base.resize((size_t)bw * bh);
	for (int y = 0; y < bh; ++y)
	{
		memcpy(&art->base[(size_t)y * bw], pixels + (size_t)y * pitch, bw);
	}
	art->hash = hashPixels(pixels, pitch, bw, bh);
	art->baseSurface = base;
	art->palette = std::move(palette);
	const Art *p = art.get();
	byContent[Key{ p->hash, bw, bh }] = p;
	bySurface[base] = p;
	arts.push_back(std::move(art));
	return true;
}

namespace
{
size_t budget = (size_t)768 << 20;
size_t loadedBytes = 0;
size_t clock = 0;

/// How far the picture's colours may be from the image it replaces (mean channel difference of the
/// picture shrunk back to the classic size against the image in its reference palette). A faithful
/// picture of a dithered image is about 13 off (the upscaler melts the dithering); a picture of
/// another image is 80 and more.
const double MATCH_LIMIT = 30.0;
/// ... and how much of its light and shade it must keep when the colours are further off, which is
/// what a repainted picture does (the same picture as a photograph: colours 33 off, but 0.79 of the
/// original's brightness pattern; a picture of another image: 0.23 and less).
const double SHAPE_LIMIT = 0.55;

/// How far the loaded picture (shrunk to the classic size) is from the image it claims to be a
/// picture of: the mean channel difference in `distance` and the correlation of their brightness in
/// `shape`. False when it cannot be told (no reference palette, nothing opaque to compare).
bool pictureMatch(const Art *art, double &distance, double &shape)
{
	const HdFrame &f = art->frame;
	const int s = art->scale, bw = art->baseWidth, bh = art->baseHeight;
	if (art->palette.size() < 256 || f.width != bw * s || f.height != bh * s)
	{
		return false;
	}
	double sum = 0, sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
	size_t n = 0;
	for (int y = 0; y < bh; ++y)
	{
		const Uint8 *baseRow = &art->base[(size_t)y * bw];
		for (int x = 0; x < bw; ++x)
		{
			if (baseRow[x] == 0)
			{
				continue; // transparent in the classic image: the picture has no colour there
			}
			// the block's colour, weighted by its alpha (the picture's own transparent pixels count for nothing)
			Uint32 r = 0, g = 0, b = 0, a = 0;
			for (int j = 0; j < s; ++j)
			{
				const Uint32 *row = f.row(y * s + j) + x * s;
				for (int i = 0; i < s; ++i)
				{
					const Uint32 p = row[i], pa = p >> 24;
					r += ((p >> 16) & 0xFF) * pa;
					g += ((p >> 8) & 0xFF) * pa;
					b += (p & 0xFF) * pa;
					a += pa;
				}
			}
			if (a == 0)
			{
				continue;
			}
			const SDL_Color &c = art->palette[baseRow[x]];
			const double pr = r / a, pg = g / a, pb = b / a;
			sum += std::abs(pr - c.r) + std::abs(pg - c.g) + std::abs(pb - c.b);
			// the brightness of both, for the correlation (the picture's light and shade)
			const double lx = 0.299 * pr + 0.587 * pg + 0.114 * pb;
			const double ly = 0.299 * c.r + 0.587 * c.g + 0.114 * c.b;
			sx += lx; sy += ly; sxx += lx * lx; syy += ly * ly; sxy += lx * ly;
			n += 3;
		}
	}
	if (n < 256 * 3)
	{
		return false;
	}
	const double m = (double)(n / 3);
	distance = sum / n;
	const double vx = sxx - sx * sx / m, vy = syy - sy * sy / m;
	shape = (vx > 1e-6 && vy > 1e-6) ? (sxy - sx * sy / m) / std::sqrt(vx * vy) : 0.0;
	return true;
}

/// Takes a picture out of the registry (it is not drawn again).
void unregister(const Art *art)
{
	auto it = byContent.find(Key{ art->hash, art->baseWidth, art->baseHeight });
	if (it != byContent.end() && it->second == art)
	{
		byContent.erase(it);
	}
	auto is = bySurface.find(art->baseSurface);
	if (is != bySurface.end() && is->second == art)
	{
		bySurface.erase(is);
	}
}
}

void setBudget(size_t bytes)
{
	budget = bytes;
}

const HdFrame &frame(const Art *art)
{
	art->lru = ++clock;
	if (art->bad || !art->frame.pixels.empty() || art->path.empty())
	{
		return art->frame;
	}
	// room for it: drop the pictures drawn longest ago (never the ones given as frames)
	const size_t need = (size_t)art->baseWidth * art->scale * art->baseHeight * art->scale * 4;
	while (loadedBytes + need > budget)
	{
		const Art *oldest = nullptr;
		for (const auto &a : arts)
		{
			if (a.get() != art && !a->path.empty() && !a->frame.pixels.empty() && (!oldest || a->lru < oldest->lru))
			{
				oldest = a.get();
			}
		}
		if (!oldest) break;
		loadedBytes -= oldest->frame.pixels.size() * 4;
		oldest->frame = HdFrame();
	}
	if (HdSprites::loadPng(art->path, art->frame))
	{
		art->frame.buildSpans();
		loadedBytes += art->frame.pixels.size() * 4;
		if (!art->checked)
		{
			// a picture is registered by name and size only, so it can well be a picture of another
			// mod's image of that name (the same hd mod serves several mods): shrink it back and
			// compare it with the image it replaces - a picture of something else is dropped. A
			// repainted picture (the drawing redone as a photograph) keeps the light and shade of
			// the image, so the colours may be further off when the shapes are still there
			art->checked = true;
			double d = 0, shape = 0;
			if (pictureMatch(art, d, shape) && d > MATCH_LIMIT && shape < SHAPE_LIMIT)
			{
				Log(LOG_WARNING) << "HD interface: " << art->path << " is not a picture of " << art->name
					<< " (colours off by " << (int)(d + 0.5) << ", shape " << (int)(shape * 100 + 0.5) << "%) - not used";
				loadedBytes -= art->frame.pixels.size() * 4;
				art->frame = HdFrame();
				art->bad = true;
				unregister(art);
			}
		}
	}
	else
	{
		Log(LOG_WARNING) << "HD interface: cannot load " << art->path;
	}
	return art->frame;
}

const Art *find(Uint64 hash, int w, int h)
{
	auto it = byContent.find(Key{ hash, w, h });
	return it == byContent.end() ? nullptr : it->second;
}

const Art *find(const Surface *base)
{
	auto it = bySurface.find(base);
	return it == bySurface.end() ? nullptr : it->second;
}

void clear()
{
	byContent.clear();
	bySurface.clear();
	arts.clear();
	loadedBytes = 0;
	clearPrepared();
}

size_t count()
{
	return arts.size();
}

// --- drawing: the picture scaled to the world and re-tinted, cached; blended into the world layer ---

namespace
{

struct Prepared
{
	const Art *art = nullptr;
	Uint64 key = 0;                       ///< the palette's hash and the scale
	HdFrame frame;
	size_t lru = 0;
};
std::vector<std::unique_ptr<Prepared>> prepared;
size_t preparedBytes = 0;
const size_t preparedBudget = (size_t)256 << 20;
size_t preparedClock = 0;

Uint64 paletteHash(const SDL_Color *colors, int k)
{
	Uint64 hash = 0x9E3779B97F4A7C15ULL ^ (Uint64)k;
	for (int i = 0; i < 256; ++i)
	{
		hash ^= (Uint64)colors[i].r | ((Uint64)colors[i].g << 8) | ((Uint64)colors[i].b << 16);
		hash *= 1099511628211ULL;
	}
	return hash;
}

/// The picture at the world scale k, re-tinted from its reference palette to `colors` per classic pixel.
const HdFrame *preparedFrame(const Art *art, int k, const SDL_Color *colors)
{
	const Uint64 key = art->palette.empty() ? (Uint64)k : paletteHash(colors, k);
	for (auto &p : prepared)
	{
		if (p->art == art && p->key == key)
		{
			p->lru = ++preparedClock;
			return &p->frame;
		}
	}
	const HdFrame &src = frame(art);
	if (src.pixels.empty())
	{
		return nullptr;
	}
	const int W = art->baseWidth * k, H = art->baseHeight * k;
	const int s = art->scale;
	std::unique_ptr<Prepared> p(new Prepared());
	p->art = art;
	p->key = key;
	p->lru = ++preparedClock;
	HdFrame &out = p->frame;
	out.width = W;
	out.height = H;
	out.pixels.assign((size_t)W * H, 0u);
	out.generated = false;
	// the colour factors of the palette entries (the shown palette against the reference one)
	float factor[256][3];
	bool differs = false;
	if (!art->palette.empty())
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
			Uint32 *dst = &out.pixels[(size_t)y * W];
			const Uint8 *baseRow = &art->base[(size_t)(y / k) * art->baseWidth];
			for (int x = 0; x < W; ++x)
			{
				Uint32 px;
				if (s == k)
				{
					px = src.pixels[(size_t)y * src.width + x];
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
					Uint32 o = 0;
					for (int shift = 0; shift < 32; shift += 8)
					{
						const float c = ((p00 >> shift) & 0xFF) * (1 - tx) * (1 - ty) + ((p10 >> shift) & 0xFF) * tx * (1 - ty)
							+ ((p01 >> shift) & 0xFF) * (1 - tx) * ty + ((p11 >> shift) & 0xFF) * tx * ty;
						o |= (Uint32)std::min(255, (int)(c + 0.5f)) << shift;
					}
					px = o;
				}
				if (differs)
				{
					const Uint8 idx = baseRow[x / k];
					const float *f = factor[idx];
					const int r = std::min(255, (int)(((px >> 16) & 0xFF) * f[0] + 0.5f));
					const int g = std::min(255, (int)(((px >> 8) & 0xFF) * f[1] + 0.5f));
					const int b = std::min(255, (int)((px & 0xFF) * f[2] + 0.5f));
					px = (px & 0xFF000000u) | ((Uint32)r << 16) | ((Uint32)g << 8) | (Uint32)b;
				}
				dst[x] = px;
			}
		}
	};
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(H / 64, pool.threads() * 2));
	pool.run(jobs, [&](int job)
	{
		rows((int)((long long)H * job / jobs), (int)((long long)H * (job + 1) / jobs));
	});
	// room for it
	const size_t bytes = out.pixels.size() * 4;
	while (!prepared.empty() && preparedBytes + bytes > preparedBudget)
	{
		size_t oldest = 0;
		for (size_t i = 1; i < prepared.size(); ++i)
		{
			if (prepared[i]->lru < prepared[oldest]->lru) oldest = i;
		}
		preparedBytes -= prepared[oldest]->frame.pixels.size() * 4;
		prepared.erase(prepared.begin() + oldest);
	}
	preparedBytes += bytes;
	prepared.push_back(std::move(p));
	return &prepared.back()->frame;
}

/// Alpha-blends a frame into a 32-bit surface at (x, y), clipped to it.
void blendInto(SDL_Surface *dest, const HdFrame &f, int x, int y)
{
	const int x0 = std::max(0, x), y0 = std::max(0, y);
	const int x1 = std::min(dest->w, x + f.width), y1 = std::min(dest->h, y + f.height);
	if (x0 >= x1 || y0 >= y1)
	{
		return;
	}
	auto rows = [&](int ra, int rb)
	{
		for (int dy = ra; dy < rb; ++dy)
		{
			const Uint32 *src = f.row(dy - y);
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
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(n / 32, pool.threads() * 2));
	pool.run(jobs, [&](int job)
	{
		rows(y0 + (int)((long long)n * job / jobs), y0 + (int)((long long)n * (job + 1) / jobs));
	});
}

}

bool active()
{
	if (!Options::oxceHdPictures || arts.empty())
	{
		return false;
	}
	Screen *screen = Screen::current();
	return screen && screen->isLayered() && screen->getWorldScale() >= 2;
}

bool drawIfPicture(const Surface *surface, SDL_Surface *dest)
{
	Screen *screen = Screen::current();
	if (!screen || !surface || dest != screen->getSurface())
	{
		return false;
	}
	const int w = surface->getWidth(), h = surface->getHeight();
	SDL_Surface *sdl = const_cast<Surface*>(surface)->getSurface();
	if (w < 32 || h < 32 || !sdl || sdl->format->BitsPerPixel != 8)
	{
		return false; // small things (icons, glyphs) are never pictures
	}
	// the picture by the surface itself (a mod's image) or by its content (a state's copy of one)
	const Art *art = find(surface);
	if (!art)
	{
		const Uint64 hash = hashPixels((const Uint8*)surface->getBuffer(), surface->getPitch(), w, h);
		art = find(hash, w, h);
	}
	if (!art)
	{
		return false;
	}
	const int k = screen->getWorldScale();
	SDL_Surface *world = screen->getWorldSurface();
	if (!world)
	{
		return false;
	}
	// the palette the surface is shown with: its own, or the screen's when it has none
	const SDL_Palette *pal = sdl->format->palette;
	const SDL_Color *colors = pal && pal->ncolors >= 256 ? pal->colors : screen->getPalette();
	const HdFrame *f = preparedFrame(art, k, colors);
	if (!f)
	{
		return false;
	}
	if (SDL_MUSTLOCK(world)) SDL_LockSurface(world);
	blendInto(world, *f, surface->getX() * k, surface->getY() * k);
	if (SDL_MUSTLOCK(world)) SDL_UnlockSurface(world);
	return true;
}

void clearPrepared()
{
	prepared.clear();
	preparedBytes = 0;
}

}

}
