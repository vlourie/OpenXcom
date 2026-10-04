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
#include "HdCraftBack.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <map>
#include <memory>
#include <vector>
#include "HdUiArt.h"
#include "HdWorkers.h"
#include "Logger.h"
#include "Palette.h"
#include "Surface.h"
#include "../Mod/ArticleDefinition.h"
#include "../Mod/Mod.h"

namespace OpenXcom
{

namespace HdCraftBack
{

namespace
{

// GeoscapeCraftState's window: 240x192 at (4, 4) of the 320x200 screen, and a window's background
// shows the image's pixels under it (Window::draw), so the picture goes into that part of the image
const int SW = 320, SH = 200;
const int WX = 4, WY = 4, WW = 240, WH = 192;
// the look picked from two mock-ups on 04.10 (art/_review/geocraft-bg, variant B): the picture's
// brightness stretched over its 0.5..99.5 percentiles, a touch of gamma, the top fifth of the ramp
// left for the texts, and the corners a sixth darker than the middle
const float LOW = 0.005f, HIGH = 0.995f, GAMMA = 0.9f, TOP = 0.80f, VIGNETTE = 0.30f;

struct Entry
{
	std::unique_ptr<Surface> surface;   ///< nullptr: the craft has no article picture
};
// by craft type and palette; the surfaces are the keys of their HD pictures in HdUiArt, so one is
// never freed while HdUiArt can still hold it (only all at once, when HdUiArt is cleared). Never
// destroyed itself: a static's destructor would free the surfaces after SDL has quit
auto &cache = *new std::map<std::pair<std::string, Uint64>, Entry>();
unsigned cacheGeneration = ~0u;

inline float luma(float r, float g, float b)
{
	return r * 0.299f + g * 0.587f + b * 0.114f;
}

/// Where the window's point (wx, wy) takes the picture from, as fractions of its size: the whole
/// picture scaled to the window's height, centred across.
inline void source(float wx, float wy, int w, int h, float &u, float &v)
{
	const float scaledW = w * (float)WH / h;
	u = (wx + (scaledW - WW) * 0.5f) / scaledW;
	v = wy / WH;
}

/// The brightness at the given percentiles of a 256-bin histogram.
void percentiles(const std::vector<size_t> &hist, float &lo, float &hi)
{
	size_t total = 0;
	for (size_t c : hist) total += c;
	size_t acc = 0;
	lo = 0;
	hi = 255;
	bool loSet = false;
	for (int i = 0; i < 256; ++i)
	{
		acc += hist[i];
		if (!loSet && acc > total * LOW) { lo = (float)i; loSet = true; }
		if (acc >= total * HIGH) { hi = (float)i; break; }
	}
	if (hi - lo < 1) hi = lo + 1;
}

/// The ramp level (0 darkest .. 15) of a picture brightness at the window's point.
inline float level(float l, float lo, float hi, float wx, float wy)
{
	float t = std::min(std::max((l - lo) / (hi - lo), 0.0f), 1.0f);
	t = std::pow(t, GAMMA);
	const float nx = (wx - WW * 0.5f) / (WW * 0.5f), ny = (wy - WH * 0.5f) / (WH * 0.5f);
	const float v = std::max(0.0f, 1 - VIGNETTE * (nx * nx + ny * ny) * 0.5f);
	return t * TOP * v * 15;
}

Surface *build(Mod *mod, const std::string &craftType, const SDL_Color *palette)
{
	const ArticleDefinition *article = mod->getUfopaediaArticle(craftType, false);
	if (!article || article->getType() != UFOPAEDIA_TYPE_CRAFT)
	{
		return nullptr;
	}
	const std::string &imageId = static_cast<const ArticleDefinitionCraft*>(article)->image_id;
	Surface *pic = imageId.empty() ? nullptr : mod->getSurface(imageId, false);
	if (!pic || pic->getWidth() <= 0 || pic->getHeight() <= 0)
	{
		return nullptr;
	}
	const Uint32 start = SDL_GetTicks();

	// the ramp's entries from darkest to brightest, in the colours the window shows
	int order[16];
	for (int i = 0; i < 16; ++i) order[i] = Palette::backPos + i;
	std::stable_sort(order, order + 16, [&](int a, int b)
	{
		return luma(palette[a].r, palette[a].g, palette[a].b) < luma(palette[b].r, palette[b].g, palette[b].b);
	});

	// the classic image: the ramp's 16 steps, the darkest outside the window
	const int pw = pic->getWidth(), ph = pic->getHeight();
	// the colours the ufopaedia shows the picture in (ArticleStateCraft): its own only with customPalette,
	// otherwise PAL_UFOPAEDIA - a vanilla SPK's own palette is just whatever it was loaded with
	const SDL_Color *picPal = pic->getPalette();
	if (!article->customPalette)
	{
		if (const Palette *pedia = mod->getPalette("PAL_UFOPAEDIA", false))
		{
			picPal = pedia->getColors();
		}
	}
	const Uint8 *picPx = pic->getBuffer();
	const int picPitch = pic->getPitch();
	std::vector<float> lum((size_t)WW * WH);
	std::vector<size_t> hist(256, 0);
	for (int y = 0; y < WH; ++y)
	{
		for (int x = 0; x < WW; ++x)
		{
			float u, v;
			source(x + 0.5f, y + 0.5f, pw, ph, u, v);
			const int sx = std::min(std::max((int)(u * pw), 0), pw - 1), sy = std::min(std::max((int)(v * ph), 0), ph - 1);
			const SDL_Color &c = picPal[picPx[(size_t)sy * picPitch + sx]];
			const float l = luma(c.r, c.g, c.b);
			lum[(size_t)y * WW + x] = l;
			hist[std::min(255, (int)l)]++;
		}
	}
	float lo, hi;
	percentiles(hist, lo, hi);
	Surface *back = new Surface(SW, SH);
	back->setPalette(palette);
	back->lock();
	Uint8 *px = back->getBuffer();
	const int pitch = back->getPitch();
	for (int y = 0; y < SH; ++y)
	{
		memset(px + (size_t)y * pitch, order[0], SW);
	}
	for (int y = 0; y < WH; ++y)
	{
		for (int x = 0; x < WW; ++x)
		{
			const float f = level(lum[(size_t)y * WW + x], lo, hi, x + 0.5f, y + 0.5f);
			px[(size_t)(WY + y) * pitch + WX + x] = (Uint8)order[std::min(15, (int)(f + 0.5f))];
		}
	}
	back->unlock();

	// the HD picture: smooth tones between the ramp's colours, from the article picture's HD version
	const HdUiArt::Art *art = HdUiArt::find(pic);
	const HdFrame *src = art ? &HdUiArt::frame(art) : nullptr;
	int s = 0;
	if (src && !src->pixels.empty())
	{
		s = std::max(1, art->scale);
		const int fw = src->width, fh = src->height;
		auto lumaAt = [&](float fx, float fy)
		{
			// bilinear over the picture's pixels
			fx = std::min(std::max(fx - 0.5f, 0.0f), (float)(fw - 1));
			fy = std::min(std::max(fy - 0.5f, 0.0f), (float)(fh - 1));
			const int x0 = (int)fx, y0 = (int)fy;
			const int x1 = std::min(x0 + 1, fw - 1), y1 = std::min(y0 + 1, fh - 1);
			const float tx = fx - x0, ty = fy - y0;
			auto l = [&](int x, int y)
			{
				const Uint32 p = src->pixels[(size_t)y * fw + x];
				return luma((float)((p >> 16) & 0xFF), (float)((p >> 8) & 0xFF), (float)(p & 0xFF));
			};
			return (l(x0, y0) * (1 - tx) + l(x1, y0) * tx) * (1 - ty) + (l(x0, y1) * (1 - tx) + l(x1, y1) * tx) * ty;
		};
		// the stretch from the HD picture itself (a repaint need not keep the classic one's light): every 4th pixel
		std::vector<size_t> hdHist(256, 0);
		for (int y = 0; y < WH * s; y += 4)
		{
			for (int x = 0; x < WW * s; x += 4)
			{
				float u, v;
				source((x + 0.5f) / s, (y + 0.5f) / s, fw, fh, u, v);
				hdHist[std::min(255, (int)lumaAt(u * fw, v * fh))]++;
			}
		}
		float hlo, hhi;
		percentiles(hdHist, hlo, hhi);
		Uint32 ramp[16];
		for (int i = 0; i < 16; ++i)
		{
			const SDL_Color &c = palette[order[i]];
			ramp[i] = ((Uint32)c.r << 16) | ((Uint32)c.g << 8) | (Uint32)c.b;
		}
		HdFrame frame;
		frame.width = SW * s;
		frame.height = SH * s;
		frame.pixels.assign((size_t)frame.width * frame.height, 0xFF000000u | ramp[0]);
		auto rows = [&](int ya, int yb)
		{
			for (int y = ya; y < yb; ++y)
			{
				Uint32 *dst = &frame.pixels[(size_t)(WY * s + y) * frame.width + WX * s];
				const float wy = (y + 0.5f) / s;
				for (int x = 0; x < WW * s; ++x)
				{
					const float wx = (x + 0.5f) / s;
					float u, v;
					source(wx, wy, fw, fh, u, v);
					const float f = level(lumaAt(u * fw, v * fh), hlo, hhi, wx, wy);
					const int i0 = std::min(15, (int)f), i1 = std::min(15, i0 + 1);
					const float t = f - i0;
					Uint32 o = 0xFF000000u;
					for (int shift = 0; shift < 24; shift += 8)
					{
						const float c = ((ramp[i0] >> shift) & 0xFF) * (1 - t) + ((ramp[i1] >> shift) & 0xFF) * t;
						o |= (Uint32)std::min(255, (int)(c + 0.5f)) << shift;
					}
					dst[x] = o;
				}
			}
		};
		HdWorkers &pool = HdWorkers::instance();
		const int H = WH * s;
		const int jobs = std::max(1, std::min(H / 32, pool.threads() * 2));
		pool.run(jobs, [&](int job)
		{
			rows(H * job / jobs, H * (job + 1) / jobs);
		});
		std::vector<SDL_Color> ref(palette, palette + 256);
		if (!HdUiArt::add("geocraft_" + craftType, back, std::move(frame), std::move(ref)))
		{
			s = 0;
		}
	}
	Log(LOG_INFO) << "HD craft window background: " << craftType << " from " << imageId
		<< (s ? " (HD x" + std::to_string(s) + ")" : " (classic only)") << " in " << (SDL_GetTicks() - start) << " ms";
	return back;
}

}

const Surface *get(Mod *mod, const std::string &craftType, const SDL_Color *palette)
{
	if (!mod || !palette)
	{
		return nullptr;
	}
	if (cacheGeneration != HdUiArt::generation())
	{
		// HdUiArt forgot its pictures (a mod reload): the images can go with them
		cache.clear();
		cacheGeneration = HdUiArt::generation();
	}
	const auto key = std::make_pair(craftType, HdUiArt::foldPalette(1469598103934665603ULL, palette));
	auto it = cache.find(key);
	if (it == cache.end())
	{
		it = cache.emplace(key, Entry()).first;
		it->second.surface.reset(build(mod, craftType, palette));
	}
	return it->second.surface.get();
}

}

}
