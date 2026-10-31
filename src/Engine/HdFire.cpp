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
#include "HdFire.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <initializer_list>
#include <map>
#include <memory>
#include "HdSprites.h"
#include "HdWorkers.h"

namespace OpenXcom
{

namespace HdFire
{

namespace
{
	const float PI = 3.14159265358979f;

	inline Uint32 hash3(int x, int y, int z, Uint32 seed)
	{
		Uint32 h = (Uint32)x * 374761393u + (Uint32)y * 668265263u + (Uint32)z * 2147483647u + seed * 144269504u;
		h = (h ^ (h >> 13)) * 1274126177u;
		return h ^ (h >> 16);
	}

	inline float lattice(int x, int y, int z, Uint32 seed)
	{
		return (hash3(x, y, z, seed) & 0xFFFF) / 65535.0f;
	}

	/// Value noise 0..1 over the plane z (an integer: a picture of its own), smooth between the lattice points.
	float noise(float x, float y, int z, Uint32 seed)
	{
		const float fx0 = std::floor(x), fy0 = std::floor(y);
		const int ix = (int)fx0, iy = (int)fy0;
		const float fx = x - fx0, fy = y - fy0;
		const float sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
		const float r0 = (1 - sx) * lattice(ix, iy, z, seed) + sx * lattice(ix + 1, iy, z, seed);
		const float r1 = (1 - sx) * lattice(ix, iy + 1, z, seed) + sx * lattice(ix + 1, iy + 1, z, seed);
		return r0 * (1 - sy) + r1 * sy;
	}

	/// The hash of the schedule of a tile's slots.
	Uint32 h32(std::initializer_list<int> values)
	{
		Uint32 h = 0x9E3779B9u;
		for (int v : values)
		{
			h = (h ^ (Uint32)v) * 0x85EBCA6Bu;
			h ^= h >> 13;
		}
		return h;
	}

	inline float clip(float v)
	{
		return std::max(0.0f, std::min(1.0f, v));
	}

	/// The colour of the depth into a tongue (0 its edge, 1 its heart): the pack's fire measured from the edge,
	/// dark red to bright yellow.
	Uint32 ramp(float c)
	{
		static const float T[6] = { 0.0f, 0.2f, 0.4f, 0.6f, 0.8f, 1.0f };
		static const float C[6][3] = { { 125, 8, 10 }, { 178, 18, 8 }, { 218, 48, 2 }, { 242, 104, 0 }, { 252, 172, 0 }, { 255, 238, 44 } };
		c = clip(c);
		const int i = std::min(4, (int)(c / 0.2f));
		const float a = clip((c - T[i]) / (T[i + 1] - T[i]));
		Uint32 rgb = 0;
		for (int ch = 0; ch < 3; ++ch)
		{
			rgb = rgb << 8 | (Uint32)(C[i][ch] + (C[i + 1][ch] - C[i][ch]) * a);
		}
		return rgb;
	}

	/// Height and width (at the base) of a tongue of each size, pixels at scale 1.
	const float SIZE_H[SIZES] = { 9.0f, 14.0f, 20.0f };
	const float SIZE_W[SIZES] = { 3.0f, 3.8f, 4.6f };
	/// The ellipse of a tile's floor the tongues stand on, pixels at scale 1 from the sprite's top left.
	const float CX = 16.0f, CY = 33.0f, RX = 11.5f, RY = 5.0f;

	struct Bank
	{
		std::vector<HdFrame> frames;
		std::vector<int> dx, dy;
		/// How far a tongue (shape, size, side) reaches left and right of its base over its whole life, pixels.
		std::vector<int> left, right;
		/// How far down a tongue (frame, then shape, size over its life) reaches toward the near edges of the floor's
		/// diamond: max over its pixels of (below the base) + (aside of the middle) / 2, pixels.
		std::vector<float> reachOf, reach;
	};
	std::map<int, std::unique_ptr<Bank>> banks;
	int bakedMs = 0;

	const Bank &bankOf(int k);
}

/**
 * One frame of a tongue: a band around its middle line, which leans and curls (a wave running up, stronger to
 * the tip), narrowing to the tip and round under the base; its edge frayed by the noise, which rises with the
 * life. The colour is the depth into the band, brighter low; late in the life a neck pinches the tip off
 * (rounded, no straight gap) and the tip and then the whole tongue redden; it shrinks away, never fades to a
 * see-through olive.
 */
void bake(int k, int shape, int size, int life, Uint32 *out)
{
	const int W = WIDTH * k, H = HEIGHT * k;
	const float K = (float)k;
	auto r = [shape](int j) { return lattice(shape, 0, j, 4242); };
	const float amp = (1.2f + 2.2f * r(0)) * K, freq = 0.5f + 0.8f * r(1), lean = (r(2) - 0.5f) * 2.0f * K;
	const float pinch = 0.9f + 0.5f * r(3);
	const int seed = shape * 13 + 1;
	const float t = life / (float)(LIFE - 1);
	const float grow = std::pow(std::min(1.0f, (t + 0.08f) / 0.3f), 0.7f);
	const float hh = SIZE_H[size] * K * (0.35f + 0.65f * grow) * (1 - 0.25f * std::max(0.0f, t - 0.6f) / 0.4f);
	const float wid = SIZE_W[size] * K * (0.6f + 0.4f * grow) * (1 - 0.7f * std::max(0.0f, t - 0.55f) / 0.45f);
	const float cutAt = 0.62f - 0.1f * std::max(0.0f, t - 0.6f) / 0.4f;
	const float neckSpan = 0.04f + 0.2f * (t - 0.55f) / 0.45f;
	const float redden = 1 - 0.35f * std::max(0.0f, t - 0.7f) / 0.3f;
	const float fade = life < LIFE - 1 ? 1.0f : 0.7f;
	const float base = (float)(BASE * k), cx = W / 2.0f;
	// first the band's field, then the colour: the edge is smoothed over the field's own steepness, so where the
	// fray changes faster than a pixel (the tip, the bottom of the disc) it stays as soft as along the sides
	std::vector<float> field((size_t)W * H);
	std::vector<float> vertOf(H), tipOf(H);
	for (int y = 0; y < H; ++y)
	{
		const float s = (base - y) / hh;
		const float sc = std::max(0.0f, s);
		const float curl = lean * sc + amp * std::pow(sc, 1.4f) * std::sin(2 * PI * (freq * s - 1.3f * t));
		// under the base a half disc as wide as the base
		const float under = std::max(0.0f, y - base) / (0.9f * wid);
		float w = s >= 0 ? wid * std::pow(clip(1 - s), pinch) : wid * std::sqrt(clip(1 - under * under));
		if (t > 0.55f)
		{
			const float neck = std::pow(clip(std::fabs(s - cutAt) / neckSpan), 0.6f);
			w = w * (neck * (1 + 0.4f * (t - 0.55f))) - (1 - neck) * 0.8f * K;
		}
		// past the tip and under the round base the band falls away steeply rather than ends: the frayed edge
		// reaching there stays ragged, never a straight cut
		const float past = s > 1.0f ? (s - 1.0f) * hh * 1.5f : under > 1.0f ? (under - 1.0f) * 0.9f * wid * 1.5f : 0.0f;
		const float tip = t > 0.55f ? clip((s - cutAt) / (1 - cutAt)) : 0.0f;
		const float vert = clip(sc);
		const float fray = (1.2f + 3.5f * vert) * K;
		vertOf[y] = vert;
		tipOf[y] = tip;
		float *row = &field[(size_t)y * W];
		for (int x = 0; x < W; ++x)
		{
			float f = w - std::fabs(x - (cx + curl)) - past;
			if (y > base)
			{
				f = std::min(f, (1 - under) * 0.9f * wid);   // the disc's edge smooth downwards too
			}
			row[x] = f + (noise(x / (2.6f * K), y / (3.5f * K) + t * 3.0f, seed, 31) - 0.5f) * fray;
		}
	}
	for (int y = 0; y < H; ++y)
	{
		const float *row = &field[(size_t)y * W];
		const float *up = &field[(size_t)std::max(0, y - 1) * W], *down = &field[(size_t)std::min(H - 1, y + 1) * W];
		const float dy = (float)(std::min(H - 1, y + 1) - std::max(0, y - 1));
		const float vert = vertOf[y], tip = tipOf[y];
		Uint32 *dst = out + (size_t)y * W;
		for (int x = 0; x < W; ++x)
		{
			const float f = row[x];
			const int xl = std::max(0, x - 1), xr = std::min(W - 1, x + 1);
			const float gx = (row[xr] - row[xl]) / (float)(xr - xl), gy = (down[x] - up[x]) / dy;
			const float steep = std::max(1.0f, std::sqrt(gx * gx + gy * gy));
			const float a = clip(f / steep / (1.1f * K) + 0.45f);
			if (a <= 0)
			{
				dst[x] = 0;
				continue;
			}
			const float depth = std::pow(clip(f / (2.2f * K)), 0.75f);
			float c = depth * (1.1f - 0.55f * vert) + 0.25f * depth * (1 - vert);
			c = c * (1 - 0.6f * tip) * redden;
			c = clip(c + (noise(x / (1.1f * K), y / (6.0f * K) + t * 4.0f, seed + 7, 53) - 0.5f) * 0.22f * depth);
			dst[x] = (Uint32)(a * fade * 255) << 24 | ramp(c);
		}
	}
}

namespace
{
/// The bank of scale k, baked on the HD workers on first use.
const Bank &bankOf(int k)
{
	std::unique_ptr<Bank> &bank = banks[k];
	if (!bank)
	{
		const auto start = std::chrono::steady_clock::now();
		bank.reset(new Bank);
		const int count = SHAPES * SIZES * LIFE, W = WIDTH * k, H = HEIGHT * k;
		bank->frames.resize(count * 2);
		bank->dx.resize(count * 2);
		bank->dy.resize(count * 2);
		bank->reachOf.assign(count, -1e9f);
		HdWorkers::instance().run(count, [&](int i)
		{
			std::vector<Uint32> full((size_t)W * H);
			bake(k, i / (SIZES * LIFE), i / LIFE % SIZES, i % LIFE, full.data());
			// cut to the pixels (a small tongue is a sliver of the frame): the side as baked and mirrored
			int x0 = W, x1 = 0, y0 = H, y1 = 0;
			for (int y = 0; y < H; ++y)
			{
				for (int x = 0; x < W; ++x)
				{
					const Uint32 p = full[(size_t)y * W + x];
					if (p)
					{
						x0 = std::min(x0, x); x1 = std::max(x1, x + 1);
						y0 = std::min(y0, y); y1 = std::max(y1, y + 1);
					}
					if ((p >> 24) > 8)
					{
						// the same for the mirrored side: the middle is the frame's
						const float reach = y + 0.5f - BASE * k + std::fabs(x + 0.5f - W / 2.0f) / 2;
						bank->reachOf[i] = std::max(bank->reachOf[i], reach);
					}
				}
			}
			if (x0 >= x1)
			{
				x0 = y0 = 0;
				x1 = y1 = 1;
			}
			for (int m = 0; m < 2; ++m)
			{
				HdFrame &f = bank->frames[i * 2 + m];
				f.width = x1 - x0;
				f.height = y1 - y0;
				f.generated = true;
				f.pixels.resize((size_t)f.width * f.height);
				for (int y = 0; y < f.height; ++y)
				{
					for (int x = 0; x < f.width; ++x)
					{
						f.pixels[(size_t)y * f.width + x] = full[(size_t)(y0 + y) * W + (m ? x1 - 1 - x : x0 + x)];
					}
				}
				f.buildSpans();
				bank->dx[i * 2 + m] = m ? W - x1 : x0;
				bank->dy[i * 2 + m] = y0;
			}
		});
		bank->left.assign(SHAPES * SIZES * 2, 0);
		bank->right.assign(SHAPES * SIZES * 2, 0);
		for (int i = 0; i < count * 2; ++i)
		{
			const int j = i / (LIFE * 2) * 2 + i % 2;
			bank->left[j] = std::max(bank->left[j], W / 2 - bank->dx[i]);
			bank->right[j] = std::max(bank->right[j], bank->dx[i] + bank->frames[i].width - W / 2);
		}
		bank->reach.assign(SHAPES * SIZES, -1e9f);
		for (int i = 0; i < count; ++i)
		{
			bank->reach[i / LIFE] = std::max(bank->reach[i / LIFE], bank->reachOf[i]);
		}
		bakedMs += (int)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count();
	}
	return *bank;
}
}

Sprite frame(int k, int shape, int size, int life, bool mirror)
{
	const Bank &bank = bankOf(k);
	const int i = ((shape * SIZES + size) * LIFE + life) * 2 + (mirror ? 1 : 0);
	return Sprite{ &bank.frames[i], bank.dx[i], bank.dy[i] };
}

int bakeMs()
{
	return bakedMs;
}

/**
 * A slot's tongue lives LIFE ticks and rests 0..4 more, the slots of a tile out of step; every life (the cycle
 * number) stands somewhere else on the floor's ellipse with another shape, size and side. The sides and the back
 * get the tall tongues, the middle front the small ones: a crown open to the viewer, like the pack's fire.
 */
void tongues(int x, int y, int z, int k, int clock, std::vector<Tongue> &out)
{
	const size_t first = out.size();
	const Bank &bank = bankOf(k);
	for (int s = 0; s < SLOTS; ++s)
	{
		const Uint32 hs = h32({ x, y, z, s, 1 });
		const int period = LIFE + (int)(hs % 5);
		const int t = std::max(0, clock) + (int)((hs >> 8) % 97);
		const int cycle = t / period, phase = t % period;
		if (phase >= LIFE)
		{
			continue;
		}
		const Uint32 hc = h32({ x, y, z, s, cycle, 2 });
		auto rnd = [hc](int i) { return ((hc >> (5 * i)) & 0x1F) / 31.0f; };
		const float ang = 2 * PI * rnd(0), rr = 0.45f + 0.55f * rnd(1);
		const float side = std::fabs(std::cos(ang)) * rr, back = -std::sin(ang) * rr;
		const float score = 0.55f * side + 0.25f * std::max(0.0f, back) + 0.35f * rnd(2);
		Tongue g;
		g.x = (CX + std::cos(ang) * RX * rr) * k;
		g.y = (CY + std::sin(ang) * RY * rr) * k;
		g.shape = (int)(hc % SHAPES);
		g.size = score > 0.62f ? 2 : score > 0.35f ? 1 : 0;
		g.life = phase;
		g.mirror = (hc >> 30) & 1;
		// the whole life within the sides of the tile's sprite: the tile on its left at the same depth is drawn
		// later, and its walls and objects (black, when not yet seen) would cut a tongue reaching there straight
		const int j = (g.shape * SIZES + g.size) * 2 + (g.mirror ? 1 : 0);
		const float lo = bank.left[j] + 1.0f, hi = 32.0f * k - 1 - bank.right[j];
		g.x = lo <= hi ? std::max(lo, std::min(hi, g.x)) : (lo + hi) / 2;
		// and its bottom within the near edges of the floor's diamond (the top face of a floor sprite: rows 24..40,
		// the middle at 16, 32): the floors of the tiles in front are drawn later and would cut it along their edge
		const float low = 40.0f * k - 1 - std::fabs(g.x - 16.0f * k) / 2 - bank.reach[g.shape * SIZES + g.size];
		g.y = std::min(g.y, low);
		out.push_back(g);
	}
	std::sort(out.begin() + first, out.end(), [](const Tongue &a, const Tongue &b) { return a.y < b.y || (a.y == b.y && a.x < b.x); });
}

}

}
