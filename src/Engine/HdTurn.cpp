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
#include "HdTurn.h"
#include <cmath>
#include "HdSprites.h"

namespace OpenXcom
{

namespace
{

/**
 * Mirrors or turns one picture: `in` with `pitch` elements a row, into `out` (width a row).
 * kind 0 mirrors left to right. kind 1..3 turns the floor diamond by that many quarters: a pixel keeps
 * whether it is seen (the diamond tiles the map as before, without gaps at its rim) and takes its
 * colour from where the turn brings it from; where that is outside the picture or not seen, from a
 * point nearer the centre.
 */
template <typename P, typename Seen>
void transform(const P *in, int pitch, P *out, int width, int height, int kind, Seen seen)
{
	if (kind == 0)
	{
		for (int y = 0; y < height; ++y)
		{
			for (int x = 0; x < width; ++x)
			{
				out[y * width + x] = in[y * pitch + width - 1 - x];
			}
		}
		return;
	}
	// the diamond of the floor: as wide as the frame, half as high, at its bottom
	const double cx = width / 2.0, cy = height - width / 4.0;
	for (int y = 0; y < height; ++y)
	{
		for (int x = 0; x < width; ++x)
		{
			const P own = in[y * pitch + x];
			out[y * width + x] = own;
			if (!seen(own))
			{
				continue;
			}
			const double dx = x + 0.5 - cx, dy = y + 0.5 - cy;
			// where the turn brings this point from (the inverse of the turn the map makes)
			double sx = dx, sy = dy;
			if (kind == 1)
			{
				sx = 2 * dy;
				sy = -dx / 2;
			}
			else if (kind == 2)
			{
				sx = -dx;
				sy = -dy;
			}
			else
			{
				sx = -2 * dy;
				sy = dx / 2;
			}
			for (double t = 1.0; t > 0.3; t -= 0.15)
			{
				const int px = (int)std::floor(cx + sx * t), py = (int)std::floor(cy + sy * t);
				if (px >= 0 && px < width && py >= 0 && py < height && seen(in[py * pitch + px]))
				{
					out[y * width + x] = in[py * pitch + px];
					break;
				}
			}
		}
	}
}

/// Is the floor flat: at most 3 % of its pixels above its diamond (with an eighth of a margin)?
bool flat(SurfaceRaw<const Uint8> src)
{
	const int width = src.getWidth(), height = src.getHeight();
	const double cx = width / 2.0, cy = height - width / 4.0, hw = width / 2.0, hh = width / 4.0;
	int seen = 0, outside = 0;
	for (int y = 0; y < height; ++y)
	{
		const Uint8 *row = src.getBuffer() + y * src.getPitch();
		for (int x = 0; x < width; ++x)
		{
			if (row[x])
			{
				++seen;
				if (std::abs(x + 0.5 - cx) / hw + std::abs(y + 0.5 - cy) / hh > 1.125)
				{
					++outside;
				}
			}
		}
	}
	return outside * 100 <= seen * 3;
}

}

HdTurn::~HdTurn()
{
	for (auto &frames : _frames)
	{
		for (auto &pair : frames)
		{
			if (pair.second->from)
			{
				HdSprites::remove(pair.second->pixels.data());
			}
		}
	}
}

HdTurn::Entry &HdTurn::entry(SurfaceRaw<const Uint8> src, int kind)
{
	std::unique_ptr<Entry> &slot = _frames[kind][src.getBuffer()];
	if (!slot)
	{
		slot.reset(new Entry());
		Entry &e = *slot;
		e.width = src.getWidth();
		e.height = src.getHeight();
		e.made = kind == 0 || flat(src);
		if (e.made)
		{
			e.pixels.resize((size_t)e.width * e.height);
			transform(src.getBuffer(), src.getPitch(), e.pixels.data(), e.width, e.height, kind, [](Uint8 p) { return p != 0; });
		}
	}
	return *slot;
}

void HdTurn::syncHd(const void *key, Entry &e, int kind)
{
	const HdFrame *hd = HdSprites::find(key);
	if (hd && (hd->width != e.width || hd->height != e.height))
	{
		hd = nullptr;
	}
	if (hd == e.from)
	{
		return;
	}
	if (!hd)
	{
		HdSprites::remove(e.pixels.data());
		e.from = nullptr;
		return;
	}
	HdFrame out;
	out.width = hd->width;
	out.height = hd->height;
	out.generated = hd->generated;
	out.ownColour = hd->ownColour;
	out.pixels.resize(hd->pixels.size());
	transform(hd->pixels.data(), hd->width, out.pixels.data(), hd->width, hd->height, kind, [](Uint32 p) { return (p >> 24) >= 128; });
	out.buildSpans();
	e.from = hd;
	HdSprites::set(e.pixels.data(), std::move(out));
}

SurfaceRaw<const Uint8> HdTurn::mirrored(SurfaceRaw<const Uint8> src, bool hd)
{
	if (!src)
	{
		return src;
	}
	Entry &e = entry(src, 0);
	if (hd)
	{
		syncHd(src.getBuffer(), e, 0);
	}
	return SurfaceRaw<const Uint8>(e.pixels.data(), e.width, e.height, e.width);
}

SurfaceRaw<const Uint8> HdTurn::floorTurned(SurfaceRaw<const Uint8> src, int quarters, bool hd)
{
	quarters = ((quarters % 4) + 4) % 4;
	if (!src || quarters == 0)
	{
		return src;
	}
	Entry &e = entry(src, quarters);
	if (!e.made)
	{
		return src;
	}
	if (hd)
	{
		syncHd(src.getBuffer(), e, quarters);
	}
	return SurfaceRaw<const Uint8>(e.pixels.data(), e.width, e.height, e.width);
}

size_t HdTurn::count() const
{
	size_t n = 0;
	for (const auto &frames : _frames)
	{
		n += frames.size();
	}
	return n;
}

}
