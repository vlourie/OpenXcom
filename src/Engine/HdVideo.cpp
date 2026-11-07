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
#include "HdVideo.h"
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "FileMap.h"
#include "HdGpuWorld.h"
#include "HdWorkers.h"
#include "Logger.h"
#include "SDL2Helpers.h"

// the decoder itself, compiled once here (MIT, libs/pl_mpeg/README.md); its own warnings are not ours
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wimplicit-fallthrough"
#elif defined(_MSC_VER)
#pragma warning(push, 0)
#endif
#define PL_MPEG_IMPLEMENTATION
#include "../../libs/pl_mpeg/pl_mpeg.h"
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#elif defined(_MSC_VER)
#pragma warning(pop)
#endif

namespace OpenXcom
{

namespace
{

/// Mixes two 32-bit pixels channel by channel, `w` of 256 of the second one.
inline Uint32 mix2(Uint32 a, Uint32 b, Uint32 w)
{
	const Uint32 rb = (((a & 0x00FF00FFu) * (256 - w) + (b & 0x00FF00FFu) * w) >> 8) & 0x00FF00FFu;
	const Uint32 ag = (((a >> 8) & 0x00FF00FFu) * (256 - w) + ((b >> 8) & 0x00FF00FFu) * w) & 0xFF00FF00u;
	return rb | ag;
}

}

HdVideo::~HdVideo()
{
	if (_plm)
	{
		plm_destroy(_plm);
	}
}

/**
 * Reads the whole clip into memory (a mod may be zipped, so there is no file on disk to hand
 * pl_mpeg) and decodes its first frame.
 */
bool HdVideo::open(const std::string &path)
{
	if (_plm || !FileMap::fileExists(path))
	{
		return false;
	}
	SDL_RWops *rw = FileMap::getRWopsReadAll(path);
	if (!rw)
	{
		return false;
	}
	size_t size = 0;
	void *bytes = SDL_LoadFile_RW(rw, &size, 1);
	if (!bytes)
	{
		return false;
	}
	_data.assign((const Uint8*)bytes, (const Uint8*)bytes + size);
	SDL_free(bytes);
	_plm = plm_create_with_memory(_data.data(), _data.size(), 0);
	if (!_plm || !plm_has_headers(_plm) || plm_get_num_video_streams(_plm) < 1)
	{
		Log(LOG_WARNING) << "HD video: not an MPEG-1 clip: " << path;
		return false;
	}
	plm_set_audio_enabled(_plm, 0);
	plm_set_loop(_plm, 0);
	_width = plm_get_width(_plm);
	_height = plm_get_height(_plm);
	if (_width < 2 || _height < 2)
	{
		return false;
	}
	_fps = plm_get_framerate(_plm) > 1.0 ? plm_get_framerate(_plm) : 25.0;
	// the converter never touches the alpha byte: opaque once and for all
	_frame.assign((size_t)_width * _height, 0xFF000000u);
	return decodeNext();
}

bool HdVideo::decodeNext()
{
	plm_frame_t *frame = plm_decode_video(_plm);
	if (!frame)
	{
		return false;
	}
	plm_frame_to_bgra(frame, (uint8_t*)_frame.data(), _width * 4);
	_shown = frame->time;
	return true;
}

/**
 * Decodes on up to the frame due at the new time; a long stall just skips the frames missed.
 */
void HdVideo::advance(double seconds)
{
	if (!_plm || _ended)
	{
		return;
	}
	_time += std::max(0.0, seconds);
	const double step = 1.0 / _fps;
	while (_shown + step <= _time)
	{
		if (!decodeNext())
		{
			_ended = true;
			return;
		}
	}
}


void HdVideo::draw(SDL_Surface *dest, int bright) const
{
	if (!_frame.empty())
	{
		drawFitted(_frame.data(), _width, _height, 0.0, 0.0, _width, _height, dest, bright);
	}
}

/**
 * The area fitted into dest with its aspect kept, black around and past the picture's edges;
 * bilinear, rows on the workers.
 */
namespace
{

/// drawFitted on the video card: from `texture`, or (0) from `pixels` uploaded, the picture at (tx, ty) there.
bool fitOnCard(unsigned texture, const SDL_Surface *pixels, int tx, int ty, int w, int h, double rx, double ry, double rw, double rh,
	SDL_Surface *dest, int bright)
{
	HdGpuWorld &gw = HdGpuWorld::instance();
	if (!gw.on(dest) || w < 2 || h < 2 || rw <= 0.0 || rh <= 0.0 || dest->format->BytesPerPixel != 4 || dest->format->Rmask != 0x00FF0000u)
	{
		return false;
	}
	// the tables of drawFitted below: per column of the picture's area and per row of dest the source and the
	// weight of the next (-1: black)
	bright = std::min(std::max(bright, 0), 256);
	const double scale = std::min(dest->w / rw, dest->h / rh);
	const int aw = std::min(dest->w, std::max(1, (int)(rw * scale + 0.5))), ah = std::min(dest->h, std::max(1, (int)(rh * scale + 0.5)));
	const int ax = (dest->w - aw) / 2, ay = (dest->h - ah) / 2;
	std::vector<int> cols(aw), rows(dest->h);
	std::vector<Uint32> colWeights(aw), rowWeights(dest->h);
	for (int dx = 0; dx < aw; ++dx)
	{
		const double s = rx + (dx + 0.5) / scale - 0.5;
		if (s < -0.5 || s > w - 0.5)
		{
			cols[dx] = -1;
			colWeights[dx] = 0;
			continue;
		}
		const double c = std::min(std::max(s, 0.0), w - 1.0);
		const int i = std::min((int)c, w - 2);
		cols[dx] = tx + i;
		colWeights[dx] = (Uint32)((c - i) * 256.0 + 0.5);
	}
	for (int dy = 0; dy < dest->h; ++dy)
	{
		const int ly = dy - ay;
		const double s = ry + (ly + 0.5) / scale - 0.5;
		if (ly < 0 || ly >= ah || s < -0.5 || s > h - 0.5 || bright == 0)
		{
			rows[dy] = -1;
			rowWeights[dy] = 0;
			continue;
		}
		const double c = std::min(std::max(s, 0.0), h - 1.0);
		const int j = std::min((int)c, h - 2);
		rows[dy] = ty + j;
		rowWeights[dy] = (Uint32)((c - j) * 256.0 + 0.5);
	}
	const Uint32 black = SDL_MapRGB(dest->format, 0, 0, 0);
	return (ax <= 0 || gw.fill(0, 0, ax, dest->h, black)) && (ax + aw >= dest->w || gw.fill(ax + aw, 0, dest->w, dest->h, black))
		&& gw.canvasZoomed(texture, pixels, cols, colWeights, rows, rowWeights, black, ax, 0, ax + aw, dest->h, bright);
}

}

bool HdVideo::drawFittedCard(unsigned texture, int tx, int ty, int w, int h, double rx, double ry, double rw, double rh, SDL_Surface *dest, int bright)
{
	return texture && fitOnCard(texture, nullptr, tx, ty, w, h, rx, ry, rw, rh, dest, bright);
}

void HdVideo::drawFitted(const Uint32 *src, int w, int h, double rx, double ry, double rw, double rh, SDL_Surface *dest, int bright, bool card)
{
	if (!src || w < 2 || h < 2 || rw <= 0.0 || rh <= 0.0 || !dest || dest->format->BytesPerPixel != 4 || dest->format->Rmask != 0x00FF0000u)
	{
		return;
	}
	HdGpuWorld &gw = HdGpuWorld::instance();
	if (card && gw.on(dest))
	{
		// the picture goes up as the frame's canvas
		SDL_Surface *pixels = SDL_CreateRGBSurfaceFrom((void*)src, w, h, 32, w * 4, 0x00FF0000u, 0x0000FF00u, 0x000000FFu, 0xFF000000u);
		const bool verifying = gw.verifying();
		const bool handed = pixels && fitOnCard(0, pixels, 0, 0, w, h, rx, ry, rw, rh, dest, bright);
		if (pixels)
		{
			SDL_FreeSurface(pixels);
		}
		else
		{
			gw.cpu("a video");
		}
		if (handed && !verifying)
		{
			return;
		}
	}
	bright = std::min(std::max(bright, 0), 256);
	const double scale = std::min(dest->w / rw, dest->h / rh);
	const int aw = std::min(dest->w, std::max(1, (int)(rw * scale + 0.5))), ah = std::min(dest->h, std::max(1, (int)(rh * scale + 0.5)));
	const int ax = (dest->w - aw) / 2, ay = (dest->h - ah) / 2;
	// the source column of each target column (-1: past the picture), and the weight of the next one (of 256)
	std::vector<int> cols(aw);
	std::vector<Uint32> colWeights(aw);
	for (int dx = 0; dx < aw; ++dx)
	{
		const double s = rx + (dx + 0.5) / scale - 0.5;
		if (s < -0.5 || s > w - 0.5)
		{
			cols[dx] = -1;
			colWeights[dx] = 0;
			continue;
		}
		const double c = std::min(std::max(s, 0.0), w - 1.0);
		const int i = std::min((int)c, w - 2);
		cols[dx] = i;
		colWeights[dx] = (Uint32)((c - i) * 256.0 + 0.5);
	}
	const Uint32 black = SDL_MapRGB(dest->format, 0, 0, 0);
	HdWorkers &pool = HdWorkers::instance();
	const int rows = dest->h;
	const int jobs = std::max(1, std::min(rows / 32, pool.threads() * 2));
	pool.run(jobs, [&](int job)
	{
		const int ya = (int)((long long)rows * job / jobs);
		const int yb = (int)((long long)rows * (job + 1) / jobs);
		for (int dy = ya; dy < yb; ++dy)
		{
			Uint32 *out = (Uint32*)((Uint8*)dest->pixels + (size_t)dy * dest->pitch);
			const int ly = dy - ay;
			const double s = ry + (ly + 0.5) / scale - 0.5;
			if (ly < 0 || ly >= ah || s < -0.5 || s > h - 0.5 || bright == 0)
			{
				std::fill(out, out + dest->w, black);
				continue;
			}
			std::fill(out, out + ax, black);
			std::fill(out + ax + aw, out + dest->w, black);
			const double c = std::min(std::max(s, 0.0), h - 1.0);
			const int j = std::min((int)c, h - 2);
			const Uint32 wy = (Uint32)((c - j) * 256.0 + 0.5);
			const Uint32 *r0 = src + (size_t)j * w, *r1 = r0 + w;
			Uint32 *o = out + ax;
			for (int i = 0; i < aw; ++i)
			{
				const int col = cols[i];
				if (col < 0)
				{
					o[i] = black;
					continue;
				}
				const Uint32 wx = colWeights[i];
				const Uint32 px = mix2(mix2(r0[col], r0[col + 1], wx), mix2(r1[col], r1[col + 1], wx), wy);
				o[i] = bright >= 256 ? px : mix2(black, px, (Uint32)bright);
			}
		}
	});
}

}
