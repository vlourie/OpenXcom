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
#include "HdSmooth.h"
#include <algorithm>
#include <cstring>
#include <vector>
#include "Scalers/xbrz.h"
#include "HdWorkers.h"

namespace OpenXcom
{

bool HdSmooth::inFloorDiamond(int x, int y, int bw, int bh)
{
	const int r = y - (bh - 16);
	if (r < 1 || r > 15 || bw != 32)
	{
		return false;
	}
	const int hw = r <= 8 ? 2 * r : 2 * (16 - r);
	return x >= 16 - hw && x < 16 + hw;
}

namespace
{

/// The neighbours of a tile on the isometric grid, in base pixels.
const int ISO_NEIGHBOURS[8][2] = { {16, 8}, {-16, 8}, {16, -8}, {-16, -8}, {32, 0}, {-32, 0}, {0, 16}, {0, -16} };

}

/**
 * Smooths a base-resolution palette sprite: converted through the palette to
 * ARGB (index 0 fully transparent) and scaled k times with xBRZ.
 *
 * A battlescape tile gets its floor diamond padded with copies of itself at
 * the neighbouring grid positions before the scaling (xBRZ then sees a field,
 * not a diamond on nothing: it neither rounds the diamond's corners nor
 * blends its edge into transparency, which drew notches at every tile corner
 * and a dotted seam between tiles), and afterwards everything outside the
 * diamond that the sprite did not draw is cut away again, pixel-exact, so
 * that the tiles interlock as they do at base resolution.
 */
bool HdSmooth::smoothPalette(const Uint8 *indices, int bw, int bh, int pitch, const SDL_Color *colors, int k, HdFrame &out, bool isoTile, bool threaded)
{
	if (k < 2 || k > 6 || bw < 1 || bh < 1)
	{
		return false;
	}
	if (isoTile && bw == 32 && bh >= 24)
	{
		// only a sprite that fills its diamond (a floor, water, a road, a floor with debris on it)
		// meets its neighbours along the diamond's edge; walls and objects keep their own edges
		int filled = 0;
		for (int y = bh - 16; y < bh; ++y)
			for (int x = 0; x < bw; ++x)
				if (inFloorDiamond(x, y, bw, bh) && indices[(size_t)y * pitch + x]) ++filled;
		isoTile = filled >= 200;
	}
	else
	{
		isoTile = false;
	}
	if (isoTile)
	{
		// the padded sprite: a margin of 4 base pixels around it (all xBRZ looks at); the copies'
		// diamonds go wherever the sprite itself has nothing, in a band around its own diamond
		// only (up to 3 rows above its top), so that whatever stands on the floor higher up is
		// smoothed as before
		const int M = 4;
		const int pw = bw + 2 * M, ph = bh + 2 * M;
		std::vector<Uint8> padded((size_t)pw * ph, 0), copy((size_t)pw * ph, 0);
		for (int y = 0; y < bh; ++y)
		{
			memcpy(padded.data() + (size_t)(y + M) * pw + M, indices + (size_t)y * pitch, bw);
		}
		for (const int *n : ISO_NEIGHBOURS)
		{
			for (int y = bh - 16; y < bh; ++y)
			{
				const int ty = y + n[1];
				if (ty < bh - 19 || ty >= bh + M) continue;
				for (int x = 0; x < bw; ++x)
				{
					if (!inFloorDiamond(x, y, bw, bh)) continue;
					const int tx = x + n[0];
					if (tx < -M || tx >= bw + M) continue;
					const Uint8 v = indices[(size_t)y * pitch + x];
					const size_t o = (size_t)(ty + M) * pw + (tx + M);
					if (v && !padded[o])
					{
						padded[o] = v;
						copy[o] = 1;
					}
				}
			}
		}
		HdFrame big;
		if (!smoothPalette(padded.data(), pw, ph, pw, colors, k, big, false, threaded))
		{
			return false;
		}
		// a base pixel the sprite did not draw is cut when a copy was pasted on it or next to it
		// (there the smoothing blended towards the copies, not towards nothing)
		std::vector<Uint8> cut((size_t)bw * bh, 0);
		for (int y = 0; y < bh; ++y)
		{
			for (int x = 0; x < bw; ++x)
			{
				if (indices[(size_t)y * pitch + x]) continue;
				bool near = false;
				for (int dy = -1; dy <= 1 && !near; ++dy)
					for (int dx = -1; dx <= 1; ++dx)
						if (copy[(size_t)(y + dy + M) * pw + (x + dx + M)]) { near = true; break; }
				cut[(size_t)y * bw + x] = near;
			}
		}
		const int w = bw * k, h = bh * k;
		out.width = w;
		out.height = h;
		out.pixels.assign((size_t)w * h, 0u);
		out.generated = true;
		for (int y = 0; y < h; ++y)
		{
			const Uint32 *src = &big.pixels[(size_t)(y + M * k) * big.width + M * k];
			Uint32 *dst = &out.pixels[(size_t)y * w];
			const Uint8 *cutRow = &cut[(size_t)(y / k) * bw];
			for (int x = 0; x < w; ++x)
			{
				if (!cutRow[x / k])
				{
					dst[x] = src[x];
				}
			}
		}
		return true;
	}
	const int w = bw * k;
	const int h = bh * k;
	std::vector<Uint8> idx((size_t)bw * bh);
	for (int y = 0; y < bh; ++y)
	{
		memcpy(idx.data() + (size_t)y * bw, indices + (size_t)y * pitch, bw);
	}
	// Pixel art fakes transparency and in-between colors with checkerboards; xBRZ would
	// turn those into diamond lattices, so a checkerboard pixel (all four side neighbours
	// of the other kind, at least three corner neighbours of its own kind) becomes what
	// the pattern stands for: half-transparent, or the mix of the two colors.
	auto at = [&](int x, int y) -> int { return (x < 0 || y < 0 || x >= bw || y >= bh) ? -1 : idx[(size_t)y * bw + x]; };
	auto argb = [&](Uint8 i, Uint32 alpha) -> Uint32 { const SDL_Color &c = colors[i]; return (alpha << 24) | ((Uint32)c.r << 16) | ((Uint32)c.g << 8) | c.b; };
	std::vector<Uint32> base((size_t)bw * bh);
	std::vector<Uint8> dither((size_t)bw * bh, 0); // 1: recognised as part of a checkerboard over nothing
	auto sideMean = [&](const int *side) -> Uint32
	{
		int r = 0, g = 0, b = 0;
		for (int i = 0; i < 4; ++i)
		{
			const SDL_Color &c = colors[side[i]];
			r += c.r; g += c.g; b += c.b;
		}
		return (128u << 24) | ((Uint32)(r / 4) << 16) | ((Uint32)(g / 4) << 8) | (Uint32)(b / 4);
	};
	for (int y = 0; y < bh; ++y)
	{
		for (int x = 0; x < bw; ++x)
		{
			const int self = idx[(size_t)y * bw + x];
			const int side[4] = { at(x - 1, y), at(x + 1, y), at(x, y - 1), at(x, y + 1) };
			const int corner[4] = { at(x - 1, y - 1), at(x + 1, y - 1), at(x - 1, y + 1), at(x + 1, y + 1) };
			Uint32 pixel = self ? argb((Uint8)self, 255) : 0u;
			if (side[0] < 0 || side[1] < 0 || side[2] < 0 || side[3] < 0)
			{
				base[(size_t)y * bw + x] = pixel; // at the border: as it is
				continue;
			}
			if (self == 0)
			{
				// a hole in a dithered patch: all sides drawn, corners mostly holes -> the mean of the sides, half transparent
				int cornersClear = 0;
				for (int i = 0; i < 4; ++i) cornersClear += (corner[i] == 0);
				if (side[0] && side[1] && side[2] && side[3] && cornersClear >= 3)
				{
					pixel = sideMean(side);
					dither[(size_t)y * bw + x] = 1;
				}
			}
			else if (!side[0] && !side[1] && !side[2] && !side[3])
			{
				// a dot of a dithered patch over nothing: corners mostly drawn -> half transparent
				int cornersDrawn = 0;
				for (int i = 0; i < 4; ++i) cornersDrawn += (corner[i] > 0);
				if (cornersDrawn >= 3)
				{
					pixel = argb((Uint8)self, 128);
					dither[(size_t)y * bw + x] = 1;
				}
			}
			else if (side[0] == side[1] && side[1] == side[2] && side[2] == side[3] && side[0] != self)
			{
				// two colors dithered: corners mostly this color, sides all the other -> their mix
				int cornersSame = 0;
				for (int i = 0; i < 4; ++i) cornersSame += (corner[i] == self);
				if (cornersSame >= 3)
				{
					const SDL_Color &a = colors[self];
					const SDL_Color &c = colors[side[0]];
					pixel = 0xFF000000u | ((Uint32)((a.r + c.r) / 2) << 16) | ((Uint32)((a.g + c.g) / 2) << 8) | (Uint32)((a.b + c.b) / 2);
				}
			}
			base[(size_t)y * bw + x] = pixel;
		}
	}
	// the rim of a checkerboard patch: same pattern, but with only two corners of its kind;
	// it belongs to the patch when those corners were recognised as checkerboard (a thin
	// diagonal line has no such neighbours and stays as it is)
	for (int y = 1; y < bh - 1; ++y)
	{
		for (int x = 1; x < bw - 1; ++x)
		{
			if (dither[(size_t)y * bw + x])
			{
				continue;
			}
			const int self = idx[(size_t)y * bw + x];
			const int side[4] = { at(x - 1, y), at(x + 1, y), at(x, y - 1), at(x, y + 1) };
			int cornersDither = 0;
			cornersDither += dither[(size_t)(y - 1) * bw + x - 1] + dither[(size_t)(y - 1) * bw + x + 1];
			cornersDither += dither[(size_t)(y + 1) * bw + x - 1] + dither[(size_t)(y + 1) * bw + x + 1];
			if (cornersDither < 2)
			{
				continue;
			}
			if (self == 0 && side[0] && side[1] && side[2] && side[3])
			{
				base[(size_t)y * bw + x] = sideMean(side);
			}
			else if (self != 0 && !side[0] && !side[1] && !side[2] && !side[3])
			{
				base[(size_t)y * bw + x] = argb((Uint8)self, 128);
			}
		}
	}
	out.width = w;
	out.height = h;
	out.pixels.assign((size_t)w * h, 0u);
	out.generated = true;
	// xBRZ in one thread is the slowest thing the interface does: a 96x96 preview of a base
	// facility at k=4 cost 118 ms, a visible catch on every page of the pedia. Sliced by rows
	// the same way Screen.cpp slices it, the frame comes out the same (see docs/PERF.md)
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = threaded ? std::max(1, std::min(bh / 16, pool.threads() * 2)) : 1;
	if (jobs > 1)
	{
		pool.run(jobs, [&](int job)
		{
			const int ya = (int)((long long)bh * job / jobs);
			const int yb = (int)((long long)bh * (job + 1) / jobs);
			xbrz::scale((size_t)k, base.data(), out.pixels.data(), bw, bh, xbrz::ARGB, xbrz::ScalerCfg(), ya, yb);
		});
	}
	else
	{
		xbrz::scale((size_t)k, base.data(), out.pixels.data(), bw, bh, xbrz::ARGB);
	}
	return true;
}

}
