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
#include <SDL.h>
#include <atomic>
#include <cstring>
#include <cstdlib>
#include <map>
#include <memory>
#include <unordered_map>
#include <unordered_set>
#include <algorithm>
#include <cmath>
#include <list>
#include "FileMap.h"
#include "HdUi.h"
#include "HdWorkers.h"
#include "Logger.h"
#include "Options.h"
#include "Screen.h"
#include "SDL2Helpers.h"
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
/// The base sizes of the pictures (w << 32 | h): a surface of any other size is not hashed at all (R-014).
std::unordered_set<Uint64> sizes;

Uint64 sizeKey(int w, int h)
{
	return ((Uint64)(Uint32)w << 32) | (Uint32)h;
}

}

Uint64 hashPixels(const Uint8 *pixels, int pitch, int w, int h)
{
	// content of the w x h bytes only (not the pitch), kept in memory only: cache keys and the hd/UI lookup,
	// whose pictures are hashed by this same function at load. Four independent xxHash64-style lanes of
	// 8 bytes instead of byte-wise FNV-1a: one multiply chain per byte was 13% of the main thread on the
	// globe (profile 27.10), this is ~10x faster at the same quality of mixing
	const Uint64 P1 = 11400714785074694791ULL, P2 = 14029467366897019727ULL, P3 = 1609587929392839161ULL;
	Uint64 lane[4] = {P1 + P2, P2, 0, 0 - P1};
	auto rotl = [](Uint64 v, int r) { return (v << r) | (v >> (64 - r)); };
	auto round = [&](Uint64 acc, Uint64 word) { return rotl(acc + word * P2, 31) * P1; };
	size_t n = 0;
	for (int y = 0; y < h; ++y)
	{
		const Uint8 *row = pixels + (size_t)y * pitch;
		int x = 0;
		for (; x + 8 <= w; x += 8, ++n)
		{
			Uint64 word;
			memcpy(&word, row + x, 8);
			lane[n & 3] = round(lane[n & 3], word);
		}
		if (x < w)
		{
			Uint64 word = (Uint64)(0x80 | (w - x)) << 56;   // the tail of the row and its length
			memcpy(&word, row + x, w - x);
			lane[n & 3] = round(lane[n & 3], word);
			++n;
		}
	}
	Uint64 hash = rotl(lane[0], 1) + rotl(lane[1], 7) + rotl(lane[2], 12) + rotl(lane[3], 18);
	for (Uint64 l : lane)
	{
		hash = (hash ^ round(0, l)) * P1 + P3;
	}
	hash ^= ((Uint64)(Uint32)w << 32 | (Uint32)h) * P2;
	hash ^= hash >> 33;
	hash *= P2;
	hash ^= hash >> 29;
	hash *= P3;
	return hash ^ (hash >> 32);
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
	sizes.insert(sizeKey(bw, bh));
	arts.push_back(std::move(art));
	return true;
}

namespace
{

/// A picture kept in a file, not registered anywhere yet (nullptr if the sizes do not fit).
std::unique_ptr<Art> lazyArt(const std::string &name, const Surface *base, const std::string &path, int width, int height, std::vector<SDL_Color> palette)
{
	if (!base || base->getWidth() <= 0 || base->getHeight() <= 0 || width <= 0 || height <= 0)
	{
		return nullptr;
	}
	const int bw = base->getWidth(), bh = base->getHeight();
	if (width % bw != 0 || height % bh != 0 || width / bw != height / bh)
	{
		Log(LOG_WARNING) << "HD interface: " << path << " is " << width << "x" << height
			<< ", not a whole multiple of the image's " << bw << "x" << bh << " - ignored";
		return nullptr;
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
	return art;
}

/// The pictures of the paper dolls' layers, by image name, until a doll wearing one is shown.
struct Pending
{
	std::string path;
	int width = 0, height = 0;
	std::vector<SDL_Color> palette;
};
std::unordered_map<std::string, Pending> pending;
/// How many of `arts` are paper dolls' layers and composites (see cropCount).
size_t dollArts = 0;

}

bool addLazy(const std::string &name, const Surface *base, const std::string &path, int width, int height, std::vector<SDL_Color> palette)
{
	std::unique_ptr<Art> art = lazyArt(name, base, path, width, height, std::move(palette));
	if (!art)
	{
		return false;
	}
	const Art *p = art.get();
	byContent[Key{ p->hash, p->baseWidth, p->baseHeight }] = p;
	bySurface[base] = p;
	sizes.insert(sizeKey(p->baseWidth, p->baseHeight));
	arts.push_back(std::move(art));
	return true;
}

void addPending(const std::string &name, const std::string &path, int width, int height, std::vector<SDL_Color> palette)
{
	Pending &p = pending[name];
	p.path = path;
	p.width = width;
	p.height = height;
	p.palette = std::move(palette);
}

void composeLayers(const Surface *composite, const std::vector<std::pair<const Surface*, std::string>> &layers)
{
	if (!composite || layers.empty() || (pending.empty() && dollArts == 0) || !Options::oxceHdPictures)
	{
		return; // no doll pictures in the mods (vanilla, a pack without them)
	}
	const int bw = composite->getWidth(), bh = composite->getHeight();
	const Uint8 *pixels = (const Uint8*)composite->getBuffer();
	const int pitch = composite->getPitch();
	if (bw <= 0 || bh <= 0 || !pixels)
	{
		return;
	}
	const Uint64 hash = hashPixels(pixels, pitch, bw, bh);
	if (find(hash, bw, bh))
	{
		return; // this doll was shown before (or is a picture of its own)
	}
	// the layers' pictures: a mod image's own (the ufopaedia's background), or a layer's, made from its note
	std::vector<const Art*> parts;
	int scale = 0;
	const std::vector<SDL_Color> *palette = nullptr;
	for (const auto &layer : layers)
	{
		const Surface *surface = layer.first;
		if (!surface || surface->getWidth() > bw || surface->getHeight() > bh)
		{
			return;
		}
		const Art *art = find(surface);
		if (!art)
		{
			auto it = pending.find(layer.second);
			if (it == pending.end())
			{
				return; // a layer without a picture: the doll is drawn as it is today
			}
			std::unique_ptr<Art> made = lazyArt(layer.second, surface, it->second.path, it->second.width, it->second.height, std::move(it->second.palette));
			pending.erase(it);
			if (!made)
			{
				return;
			}
			made->doll = true;
			art = made.get();
			// by its image only: a layer is never drawn on its own, and its mostly empty canvas must not
			// be taken for another image's picture
			bySurface[surface] = art;
			arts.push_back(std::move(made));
			++dollArts;
		}
		if (art->bad)
		{
			return;
		}
		scale = std::max(scale, art->scale);
		if (!palette && !art->palette.empty())
		{
			palette = &art->palette;
		}
		parts.push_back(art);
	}
	std::unique_ptr<Art> art(new Art());
	art->name = "doll " + layers.back().second;
	art->scale = scale;
	art->baseWidth = bw;
	art->baseHeight = bh;
	art->base.resize((size_t)bw * bh);
	for (int y = 0; y < bh; ++y)
	{
		memcpy(&art->base[(size_t)y * bw], pixels + (size_t)y * pitch, bw);
	}
	art->hash = hash;
	// the drawing caches key a picture by its image: the composite's surface belongs to a state and goes
	// with it, the first layer's image stays as long as the mods
	art->baseSurface = layers.front().first;
	if (palette)
	{
		art->palette = *palette;
	}
	art->layers = std::move(parts);
	art->doll = true;
	int ox0 = bw, oy0 = bh, ox1 = -1, oy1 = -1;
	for (int y = 0; y < bh; ++y)
	{
		const Uint8 *row = &art->base[(size_t)y * bw];
		for (int x = 0; x < bw; ++x)
		{
			if (row[x])
			{
				ox0 = std::min(ox0, x); ox1 = std::max(ox1, x);
				oy0 = std::min(oy0, y); oy1 = std::max(oy1, y);
			}
		}
	}
	if (ox1 >= 0)
	{
		art->opaque.x = (Sint16)ox0;
		art->opaque.y = (Sint16)oy0;
		art->opaque.w = (Uint16)(ox1 - ox0 + 1);
		art->opaque.h = (Uint16)(oy1 - oy0 + 1);
	}
	art->checked = true;   // made of checked pictures: nothing to compare it with
	const Art *p = art.get();
	byContent[Key{ hash, bw, bh }] = p;
	sizes.insert(sizeKey(bw, bh));
	arts.push_back(std::move(art));
	++dollArts;
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

/// Layers' pictures unpacked ahead by composeFrame, taken by frame() in place of reading the file.
std::unordered_map<const Art*, HdFrame> predecoded;

/// A paper doll's picture: its layers' pictures at its scale, re-tinted to its reference palette, laid one
/// over another in order (straight alpha, as the classic layers are blitted). False when a layer cannot be read.
bool composeFrame(const Art *art)
{
	// the layers' files unpacked side by side: one after another on the main thread a doll of 9 layers took
	// 400-700 ms (lodepng, 1280x800 each). Read here, unpacked on the workers, taken by frame() as if loaded
	std::vector<const Art*> toRead;
	std::vector<std::pair<void*, size_t>> files;
	for (const Art *layer : art->layers)
	{
		if (layer->bad || !layer->frame.pixels.empty() || layer->path.empty() || predecoded.count(layer)
			|| std::find(toRead.begin(), toRead.end(), layer) != toRead.end() || !FileMap::fileExists(layer->path))
		{
			continue;
		}
		size_t size = 0;
		void *data = nullptr;
		if (SDL_RWops *rw = FileMap::getRWops(layer->path))
		{
			data = SDL_LoadFile_RW(rw, &size, SDL_TRUE);
		}
		if (data)
		{
			toRead.push_back(layer);
			files.emplace_back(data, size);
		}
	}
	if (toRead.size() > 1)
	{
		std::vector<HdFrame> frames(toRead.size());
		std::vector<char> ok(toRead.size(), 0);
		HdWorkers::instance().run((int)toRead.size(), [&](int i)
		{
			ok[i] = HdSprites::decodePng((const unsigned char*)files[i].first, files[i].second, frames[i]) ? 1 : 0;
		});
		for (size_t i = 0; i < toRead.size(); ++i)
		{
			if (ok[i])
			{
				predecoded[toRead[i]] = std::move(frames[i]); // a failed one is read again by frame(), which says why
			}
		}
	}
	for (const auto &file : files)
	{
		SDL_free(file.first);
	}
	const int s = art->scale, W = art->baseWidth * s, H = art->baseHeight * s;
	HdFrame out;
	out.width = W;
	out.height = H;
	out.pixels.assign((size_t)W * H, 0u);
	out.generated = false;
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(H / 64, pool.threads() * 2));
	for (const Art *layer : art->layers)
	{
		HdFrame f;
		// the layer in the doll's reference palette (a layer without one, or a doll without one: as it is)
		const SDL_Color *colors = art->palette.empty() ? layer->palette.data() : art->palette.data();
		if (!prepare(layer, s, colors, f))
		{
			return false;
		}
		const int lw = std::min(f.width, W), lh = std::min(f.height, H);
		pool.run(jobs, [&](int job)
		{
			for (int y = (int)((long long)lh * job / jobs), last = (int)((long long)lh * (job + 1) / jobs); y < last; ++y)
			{
				const Uint32 *src = &f.pixels[(size_t)y * f.width];
				Uint32 *dst = &out.pixels[(size_t)y * W];
				for (int x = 0; x < lw; ++x)
				{
					const Uint32 sp = src[x], sa = sp >> 24;
					if (!sa) continue;
					const Uint32 dp = dst[x], da = dp >> 24;
					if (sa == 255 || !da)
					{
						dst[x] = sp;
						continue;
					}
					// over, both straight alpha: the colour weighted by what each one shows
					const Uint32 dw = da * (255 - sa) / 255, oa = sa + dw;
					const Uint32 r = (((sp >> 16) & 0xFF) * sa + ((dp >> 16) & 0xFF) * dw) / oa;
					const Uint32 g = (((sp >> 8) & 0xFF) * sa + ((dp >> 8) & 0xFF) * dw) / oa;
					const Uint32 b = ((sp & 0xFF) * sa + (dp & 0xFF) * dw) / oa;
					dst[x] = (oa << 24) | (r << 16) | (g << 8) | b;
				}
			}
		});
	}
	art->frame = std::move(out);
	return true;
}

}

const HdFrame &frame(const Art *art)
{
	art->lru = ++clock;
	if (art->bad || !art->frame.pixels.empty() || (art->path.empty() && art->layers.empty()))
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
			if (a.get() != art && (!a->path.empty() || !a->layers.empty()) && !a->frame.pixels.empty() && (!oldest || a->lru < oldest->lru))
			{
				oldest = a.get();
			}
		}
		if (!oldest) break;
		loadedBytes -= oldest->frame.pixels.size() * 4;
		oldest->frame = HdFrame();
	}
	const Uint32 loadStart = SDL_GetTicks();
	if (!art->layers.empty())
	{
		if (composeFrame(art))
		{
			art->frame.buildSpans();
			loadedBytes += art->frame.pixels.size() * 4;
			// measurement: every layer's picture is read (when not held already) and blended on the main thread
			const Uint32 loadMs = SDL_GetTicks() - loadStart;
			if (loadMs >= 20)
			{
				Log(LOG_INFO) << "HD picture: " << art->name << " composed of " << art->layers.size() << " layers in "
					<< loadMs << " ms, " << (loadedBytes >> 20) << " MB held";
			}
		}
		else
		{
			Log(LOG_WARNING) << "HD interface: cannot compose " << art->name;
			art->bad = true;
			byContent.erase(Key{ art->hash, art->baseWidth, art->baseHeight });
		}
		return art->frame;
	}
	auto decoded = predecoded.find(art);
	const bool ready = decoded != predecoded.end();
	if (ready)
	{
		art->frame = std::move(decoded->second);
		predecoded.erase(decoded);
	}
	if (ready || HdSprites::loadPng(art->path, art->frame))
	{
		art->frame.buildSpans();
		loadedBytes += art->frame.pixels.size() * 4;
		// measurement: a picture is read and unpacked the moment it is first drawn, on the main
		// thread. A big one is a visible freeze, and nothing in the log said so before
		const Uint32 loadMs = SDL_GetTicks() - loadStart;
		const size_t loadBytes = art->frame.pixels.size() * 4;
		if (loadMs >= 20 || loadBytes >= ((size_t)4 << 20))
		{
			Log(LOG_INFO) << "HD picture: " << art->path << " " << (loadBytes >> 20) << " MB in "
				<< loadMs << " ms, " << (loadedBytes >> 20) << " MB held";
		}
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
				// only said, not acted on: measured over the whole X-Piratez pack (tools/hd_match_report.py)
				// 250 pictures of 1702 fall under the limit, and the ones looked at are faithful repaints -
				// Wolverin_Ped is the same mech in the same pose at shape -0.66, MiG the same plane at -0.09.
				// A repaint that turns a pale sky into a night one inverts the brightness of the largest
				// area of the picture, so the correlation cannot tell it from a picture of something else
				Log(LOG_WARNING) << "HD interface: " << art->path << " is far from " << art->name
					<< " (colours off by " << (int)(d + 0.5) << ", shape " << (int)(shape * 100 + 0.5)
					<< "%) - used anyway, check it is the right picture";
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

/**
 * The picture of the image these pixels are a part of (a state's copy of a corner of an image).
 */
const Art *findCrop(const Uint8 *pixels, int pitch, int w, int h, int &offX, int &offY)
{
	if (w < 8 || h < 8)
	{
		return nullptr; // too small to be sure of
	}
	// every picture at every offset: 100 ms against the pack of X-Piratez in one thread, so the pictures are
	// shared out between the workers. The answer is the one the plain loop gives: the first picture in
	// order, at its first offset - a job stops as soon as a picture before its own has been found
	const int count = (int)arts.size();
	std::atomic<int> best(count);
	std::vector<int> foundX(count, 0), foundY(count, 0);
	auto scan = [&](int index)
	{
		const Art &art = *arts[index];
		const int bw = art.baseWidth, bh = art.baseHeight;
		if (art.bad || art.doll || bw < w || bh < h || (bw == w && bh == h))
		{
			return false;
		}
		for (int oy = 0; oy + h <= bh; ++oy)
		{
			const Uint8 *baseRow = &art.base[(size_t)oy * bw];
			const Uint8 *end = baseRow + (bw - w + 1);
			for (const Uint8 *at = baseRow; (at = (const Uint8*)memchr(at, pixels[0], end - at)) != nullptr; ++at)
			{
				if (memcmp(at, pixels, w) != 0)
				{
					continue;
				}
				const int ox = (int)(at - baseRow);
				bool all = true;
				for (int y = 1; y < h && all; ++y)
				{
					all = memcmp(&art.base[(size_t)(oy + y) * bw + ox], pixels + (size_t)y * pitch, w) == 0;
				}
				if (all)
				{
					foundX[index] = ox;
					foundY[index] = oy;
					return true;
				}
			}
		}
		return false;
	};
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(count / 16, pool.threads() * 4));
	pool.run(jobs, [&](int job)
	{
		for (int i = (int)((long long)count * job / jobs), last = (int)((long long)count * (job + 1) / jobs); i < last && i < best.load(); ++i)
		{
			if (scan(i))
			{
				int seen = best.load();
				while (i < seen && !best.compare_exchange_weak(seen, i)) {}
				return;
			}
		}
	});
	const int index = best.load();
	if (index >= count)
	{
		return nullptr;
	}
	offX = foundX[index];
	offY = foundY[index];
	return arts[index].get();
}

namespace { unsigned cleared = 0; }

void clear()
{
	byContent.clear();
	bySurface.clear();
	sizes.clear();
	arts.clear();
	pending.clear();
	predecoded.clear();
	dollArts = 0;
	loadedBytes = 0;
	++cleared;
	clearPrepared();
}

size_t count()
{
	return arts.size();
}

size_t cropCount()
{
	return arts.size() - dollArts;
}

SDL_Rect pictureArea(const Art *art, int x, int y, int w, int h)
{
	SDL_Rect r;
	if (art && !art->layers.empty())
	{
		// (with the ufopaedia's background among its layers that is the whole page again)
		x += art->opaque.x;
		y += art->opaque.y;
		w = art->opaque.w;
		h = art->opaque.h;
	}
	r.x = (Sint16)x;
	r.y = (Sint16)y;
	r.w = (Uint16)std::max(0, w);
	r.h = (Uint16)std::max(0, h);
	return r;
}

unsigned generation()
{
	return cleared;
}

size_t bytes()
{
	return loadedBytes;
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

/// The picture at the world scale k, re-tinted from its reference palette to `colors` per classic pixel.
const HdFrame *preparedFrame(const Art *art, int k, const SDL_Color *colors)
{
	const Uint64 key = art->palette.empty() ? (Uint64)k : foldPalette(0x9E3779B97F4A7C15ULL ^ (Uint64)k, colors);
	for (auto &p : prepared)
	{
		if (p->art == art && p->key == key)
		{
			p->lru = ++preparedClock;
			return &p->frame;
		}
	}
	std::unique_ptr<Prepared> p(new Prepared());
	p->art = art;
	p->key = key;
	p->lru = ++preparedClock;
	if (!prepare(art, k, colors, p->frame))
	{
		return nullptr;
	}
	// room for it
	const size_t bytes = p->frame.pixels.size() * 4;
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

}

Uint64 foldPalette(Uint64 seed, const SDL_Color *colors)
{
	Uint64 hash = seed;
	for (int i = 0; i < 256; ++i)
	{
		hash ^= (Uint64)colors[i].r | ((Uint64)colors[i].g << 8) | ((Uint64)colors[i].b << 16);
		hash *= 1099511628211ULL;
	}
	return hash;
}

bool prepare(const Art *art, int k, const SDL_Color *colors, HdFrame &out)
{
	const HdFrame &src = frame(art);
	if (src.pixels.empty())
	{
		return false;
	}
	const int W = art->baseWidth * k, H = art->baseHeight * k;
	const int s = art->scale;
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
	return true;
}

namespace
{

/// Alpha-blends a frame into a 32-bit surface at (x, y), clipped to `clip` and to the surface.
void blendInto(SDL_Surface *dest, const HdFrame &f, int x, int y, const SDL_Rect *clip)
{
	int cx0 = 0, cy0 = 0, cx1 = dest->w, cy1 = dest->h;
	if (clip)
	{
		cx0 = std::max(cx0, (int)clip->x);
		cy0 = std::max(cy0, (int)clip->y);
		cx1 = std::min(cx1, clip->x + clip->w);
		cy1 = std::min(cy1, clip->y + clip->h);
	}
	const int x0 = std::max(cx0, x), y0 = std::max(cy0, y);
	const int x1 = std::min(cx1, x + f.width), y1 = std::min(cy1, y + f.height);
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
	if (n < 256)
	{
		rows(y0, y1); // a button's worth: the pool would cost more than the rows
		return;
	}
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(n / 64, pool.threads() * 2));
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

/**
 * Draws a picture into a 32-bit surface at (x, y) (the screen's world layer): what a state
 * draws itself, such as the base view's HD facilities.
 */
void drawFrame(SDL_Surface *dest, const HdFrame &frame, int x, int y, const SDL_Rect *clip)
{
	if (dest && dest->format->BytesPerPixel == 4 && !frame.pixels.empty())
	{
		blendInto(dest, frame, x, y, clip);
	}
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
	if (!art && sizes.count(sizeKey(w, h)))
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
	blendInto(world, *f, surface->getX() * k, surface->getY() * k, nullptr);
	if (SDL_MUSTLOCK(world)) SDL_UnlockSurface(world);
	const SDL_Rect area = pictureArea(art, surface->getX(), surface->getY(), w, h);
	HdUi::instance().notePicture(area.x, area.y, area.w, area.h);
	return true;
}

void clearPrepared()
{
	prepared.clear();
	preparedBytes = 0;
}

}

}
