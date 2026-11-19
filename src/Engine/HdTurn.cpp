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
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include "HdSprites.h"
#include "HdWorkers.h"
#include "Logger.h"

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

/// The memory budget of the HD frames made for the turned views: 384 MB with 16 GB of memory or more, less with
/// less (HdWorkers::cacheBudget); OXCE_HD_TURN_BUDGET=<MB> overrides it (tests of the dropping).
size_t turnBudget()
{
	static const size_t budget = []
	{
		const char *env = getenv("OXCE_HD_TURN_BUDGET");
		return env && atoi(env) > 0 ? (size_t)atoi(env) << 20 : HdWorkers::cacheBudget((size_t)384 << 20);
	}();
	return budget;
}

}

HdTurn::~HdTurn()
{
	Log(LOG_INFO) << "HD turn: " << count() << " frame(s) were made for the turned views, " << (_hdBytes >> 10)
		<< " KB of HD frames registered for them at the end (budget " << (turnBudget() >> 20) << " MB)";
	for (auto &frames : _frames)
	{
		for (auto &pair : frames)
		{
			if (pair.second->from || pair.second->painted)
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
	e.use = _tick;
	Uint64 stamp = 0;
	const HdFrame *hd = HdSprites::find(key, stamp);
	if (hd && (hd->width != e.width || hd->height != e.height))
	{
		hd = nullptr;
	}
	// (the address alone is not enough: a key registered anew keeps its frame where it was, with other pixels)
	if (hd == e.from && (!hd || stamp == e.stamp))
	{
		return;
	}
	if (e.from)
	{
		// with its variants: the original may have fewer now, and the ground pattern would take the former ones
		HdSprites::remove(e.pixels.data());
		e.from = nullptr;
		_hdBytes -= e.hdBytes;
		e.hdBytes = 0;
	}
	if (!hd)
	{
		return;
	}
	e.stamp = stamp;
	HdFrame out;
	out.width = hd->width;
	out.height = hd->height;
	out.generated = hd->generated;
	out.ownColour = hd->ownColour;
	out.pixels.resize(hd->pixels.size());
	transform(hd->pixels.data(), hd->width, out.pixels.data(), hd->width, hd->height, kind, [](Uint32 p) { return (p >> 24) >= 128; });
	out.buildSpans();
	const int width = hd->width, height = hd->height;
	const bool generated = hd->generated, ownColour = hd->ownColour;
	e.from = hd;
	// the two span tables of a frame have a span a row
	const size_t spanBytes = 2 * (size_t)height * sizeof(HdFrame::Span);
	e.hdBytes = out.pixels.size() * sizeof(Uint32) + (out.rows.size() + out.solid.size()) * sizeof(HdFrame::Span);
	HdSprites::set(e.pixels.data(), std::move(out));
	// a floor turned with the map keeps its pack variants (the ground pattern), turned the same way
	if (kind >= 1 && kind <= 3 && !generated)
	{
		const int slots = HdSprites::variantCount(key);
		for (int v = 1; v <= slots; ++v)
		{
			const HdFrame *variant = HdSprites::findVariant(key, v);
			if (!variant || variant->width != width || variant->height != height)
			{
				break; // the pattern takes the variants up to the first gap (Canvas32::groundFrameFor)
			}
			HdFrame turned;
			turned.width = width;
			turned.height = height;
			turned.generated = variant->generated;
			turned.ownColour = ownColour;
			turned.pixels.resize(variant->pixels.size());
			transform(variant->pixels.data(), width, turned.pixels.data(), width, height, kind, [](Uint32 p) { return (p >> 24) >= 128; });
			e.hdBytes += turned.pixels.size() * sizeof(Uint32) + spanBytes;
			HdSprites::setVariant(e.pixels.data(), v, std::move(turned));
		}
	}
	_hdBytes += e.hdBytes;
}

void HdTurn::frame()
{
	const size_t budget = turnBudget();
	if (_hdBytes > budget && _hdBytes > _checkAbove)
	{
		// only what the frame drawn last did not ask for: the view on the screen is never made anew frame after
		// frame, and no command of a frame can point at what goes (the registry runs the waiting ones first anyway)
		std::vector<Entry*> old;
		for (int kind = 0; kind < 4; ++kind)
		{
			for (auto &pair : _frames[kind])
			{
				if (pair.second->from && pair.second->use != _tick)
				{
					old.push_back(pair.second.get());
				}
			}
		}
		std::sort(old.begin(), old.end(), [](const Entry *a, const Entry *b) { return a->use < b->use; });
		const size_t before = _hdBytes, target = budget - budget / 4;
		size_t dropped = 0;
		for (Entry *e : old)
		{
			if (_hdBytes <= target)
			{
				break;
			}
			HdSprites::remove(e->pixels.data());
			e->from = nullptr;
			_hdBytes -= e->hdBytes;
			e->hdBytes = 0;
			++dropped;
		}
		// what is left is on the screen: look again only when more is made
		_checkAbove = _hdBytes > budget ? _hdBytes : 0;
		if (dropped)
		{
			Log(LOG_INFO) << "HD turn: " << (before >> 20) << " MB of turned frames over the budget of " << (budget >> 20)
				<< " MB - " << dropped << " frame(s) of the views not on the screen dropped, " << (_hdBytes >> 20) << " MB kept";
		}
	}
	++_tick;
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

SurfaceRaw<const Uint8> HdTurn::painted(SurfaceRaw<const Uint8> src, int quarters, int part)
{
	if (!src || quarters < 1 || quarters > 3 || part < 0 || part > 3 || !HdSprites::anyViews())
	{
		return SurfaceRaw<const Uint8>();
	}
	std::unique_ptr<Entry> &slot = _frames[4 + (quarters - 1) * 4 + part][src.getBuffer()];
	if (!slot)
	{
		slot.reset(new Entry());
		Entry &e = *slot;
		e.width = src.getWidth();
		e.height = src.getHeight();
		e.pixels.resize((size_t)e.width * e.height);
		e.painted = HdSprites::setView(e.pixels.data(), src.getBuffer(), quarters, part);
		e.made = e.painted;
		if (e.painted)
		{
			// the copy keeps the original's pixels: what the canvas reads from the palette frame stays the same
			for (int y = 0; y < e.height; ++y)
			{
				std::memcpy(e.pixels.data() + (size_t)y * e.width, src.getBuffer() + (size_t)y * src.getPitch(), e.width);
			}
		}
		else
		{
			std::vector<Uint8>().swap(e.pixels);
		}
	}
	Entry &e = *slot;
	if (!e.painted || !HdSprites::find(e.pixels.data()))
	{
		return SurfaceRaw<const Uint8>();
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
