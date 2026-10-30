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
#include "HdSmoke.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <map>
#include <memory>
#include "HdSprites.h"
#include "HdWorkers.h"

namespace OpenXcom
{

namespace HdSmoke
{

namespace
{
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

	/// Value noise 0..1, smooth between the integer lattice points.
	float noise(float x, float y, float z, Uint32 seed)
	{
		const float fx0 = std::floor(x), fy0 = std::floor(y), fz0 = std::floor(z);
		const int ix = (int)fx0, iy = (int)fy0, iz = (int)fz0;
		const float fx = x - fx0, fy = y - fy0, fz = z - fz0;
		const float sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy), sz = fz * fz * (3 - 2 * fz);
		float r = 0;
		for (int dz = 0; dz < 2; ++dz)
		{
			for (int dy = 0; dy < 2; ++dy)
			{
				const float wyz = (dy ? sy : 1 - sy) * (dz ? sz : 1 - sz);
				r += wyz * ((1 - sx) * lattice(ix, iy + dy, iz + dz, seed) + sx * lattice(ix + 1, iy + dy, iz + dz, seed));
			}
		}
		return r;
	}

	/// Three octaves of the noise.
	float fbm(float x, float y, float z, Uint32 seed)
	{
		return noise(x, y, z, seed) * 0.55f + noise(x * 2.03f, y * 2.03f, z * 2.03f, seed + 7) * 0.3f
			+ noise(x * 4.1f, y * 4.1f, z * 4.1f, seed + 13) * 0.15f;
	}

	struct Bank
	{
		std::vector<HdFrame> frames;
	};
	std::map<int, std::unique_ptr<Bank>> banks;
	int bakedMs = 0;
}

/**
 * One frame of a puff: rays from the viewer through a cube of side 2 around the puff, sampled at half the
 * frame's resolution (the smoke is soft) and scaled up. The density is a ball growing over the puff's life,
 * frayed by the noise, which boils as the life goes on; it appears over the first 18 % of the life and melts
 * over the last 45 %. The light inside is what reaches a point from the top through the density above it.
 */
void bake(int k, int kind, int shape, int life, Uint32 *out)
{
	const int S = SIDE * k;
	const int R = std::max(SIDE, S / 2);
	const int N = 32;
	const float t = life / (float)(LIFE - 1);
	const float radius = 0.58f + 0.36f * t;
	const float env = std::min(1.0f, t / 0.18f) * (1.0f - std::pow(std::max(0.0f, (t - 0.55f) / 0.45f), 1.5f));
	const float thick = kind == THIN ? 0.5f : kind == SOOT ? 0.9f : 1.0f;
	const float drift = t * 1.3f;
	const Uint32 seed = (Uint32)(shape * 31 + 5 + kind * 101);
	const float freq = 1.7f;
	// density [y][x][z], z from the far side to the viewer
	std::vector<float> dens((size_t)R * R * N), light((size_t)R * R * N);
	for (int y = 0; y < R; ++y)
	{
		const float Y = (y + 0.5f) / R * 2 - 1;
		for (int x = 0; x < R; ++x)
		{
			const float X = (x + 0.5f) / R * 2 - 1;
			float *d = &dens[((size_t)y * R + x) * N];
			for (int z = 0; z < N; ++z)
			{
				const float Z = (z + 0.5f) / N * 2 - 1;
				const float r = std::sqrt(X * X + (Y * 1.4f) * (Y * 1.4f) + Z * Z) / radius;
				const float n = fbm(X * freq + 11.3f * shape, Y * freq - drift, Z * freq + drift * 0.5f, seed);
				const float e = std::max(0.0f, std::min(1.0f, (1.0f - r) * 1.3f + (n - 0.5f) * 1.1f));
				d[z] = e * e * (3 - 2 * e) * 1.8f * env * thick;
			}
		}
	}
	const float stepY = 2.0f / R * 1.2f;
	for (int x = 0; x < R; ++x)
	{
		for (int z = 0; z < N; ++z)
		{
			float tau = 0;
			for (int y = 0; y < R; ++y)
			{
				const size_t i = ((size_t)y * R + x) * N + z;
				tau += dens[i] * stepY;
				light[i] = 0.38f + 0.62f * std::exp(-tau);
			}
		}
	}
	std::vector<float> lum((size_t)R * R), alpha((size_t)R * R);
	const float dz = 2.0f / N;
	for (size_t p = 0; p < (size_t)R * R; ++p)
	{
		const float *d = &dens[p * N];
		const float *l = &light[p * N];
		float T = 1, col = 0;
		for (int z = 0; z < N; ++z)
		{
			const float a = 1 - std::exp(-d[z] * dz);
			col += T * a * l[z];
			T *= 1 - a;
		}
		alpha[p] = 1 - T;
		lum[p] = alpha[p] > 1e-4f ? col / alpha[p] : 0;
	}
	const float base[KINDS][3] = { { 205, 205, 210 }, { 205, 205, 210 }, { 92, 87, 82 } };
	for (int y = 0; y < S; ++y)
	{
		const float sy = std::max(0.0f, std::min((float)(R - 1), (y + 0.5f) * R / S - 0.5f));
		const int y0 = std::min(R - 2, (int)sy);
		const float fy = sy - y0;
		for (int x = 0; x < S; ++x)
		{
			const float sx = std::max(0.0f, std::min((float)(R - 1), (x + 0.5f) * R / S - 0.5f));
			const int x0 = std::min(R - 2, (int)sx);
			const float fx = sx - x0;
			auto bil = [&](const std::vector<float> &v)
			{
				const size_t i = (size_t)y0 * R + x0;
				return (v[i] * (1 - fx) + v[i + 1] * fx) * (1 - fy) + (v[i + R] * (1 - fx) + v[i + R + 1] * fx) * fy;
			};
			const float a = bil(alpha);
			const int a8 = std::max(0, std::min(255, (int)(a * 255 + 0.5f)));
			if (!a8)
			{
				out[(size_t)y * S + x] = 0;
				continue;
			}
			const float l = bil(lum);
			Uint32 px = (Uint32)a8 << 24;
			for (int c = 0; c < 3; ++c)
			{
				px |= (Uint32)std::max(0, std::min(255, (int)(base[kind][c] * l + 0.5f))) << (16 - 8 * c);
			}
			out[(size_t)y * S + x] = px;
		}
	}
}

const HdFrame &frame(int k, int kind, int shape, int life)
{
	std::unique_ptr<Bank> &bank = banks[k];
	if (!bank)
	{
		const auto start = std::chrono::steady_clock::now();
		bank.reset(new Bank);
		const int count = KINDS * SHAPES * LIFE, S = SIDE * k;
		bank->frames.resize(count);
		HdWorkers::instance().run(count, [&](int i)
		{
			HdFrame &f = bank->frames[i];
			f.width = S;
			f.height = S;
			f.generated = true;
			f.pixels.assign((size_t)S * S, 0);
			bake(k, i / (SHAPES * LIFE), i / LIFE % SHAPES, i % LIFE, f.pixels.data());
			f.buildSpans();
		});
		bakedMs += (int)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count();
	}
	return bank->frames[(kind * SHAPES + shape) * LIFE + life];
}

int bakeMs()
{
	return bakedMs;
}

/**
 * A tile has a few slots; a slot's puff lives a period of 36..52 ticks of its own, the slots of a tile spread
 * over it. Every life (the cycle number) has its own place of birth, rise and drift, so a cloud never repeats.
 */
void puffs(int x, int y, int z, int smoke, bool fire, int clock, std::vector<Puff> &out)
{
	const size_t first = out.size();
	const int slots = fire ? 3 : std::min(5, 2 + smoke / 4);
	const int kind = fire ? SOOT : smoke < 6 ? THIN : THICK;
	for (int s = 0; s < slots; ++s)
	{
		const Uint32 hs = hash3(x, y, z * 8 + s, 0x5EEDu);
		const int period = 36 + (int)(hs % 17);
		const int t = std::max(0, clock) + s * period / slots + (int)((hs >> 8) % 7);
		const int cycle = t / period;
		const float ph = (t % period) / (float)period;
		const Uint32 hc = hash3(x * 64 + s, y, z, (Uint32)cycle * 2654435761u);
		auto rnd = [hc](int i) { return lattice(i, 0, 0, hc); };
		Puff p;
		const float ease = 1 - (1 - ph) * (1 - ph);
		p.u = 0.2f + 0.6f * rnd(1) + (rnd(3) - 0.5f) * 0.3f * ph;
		p.v = 0.2f + 0.6f * rnd(2) + (rnd(4) - 0.5f) * 0.3f * ph;
		p.h = (fire ? 10 + 4 * rnd(6) : 2 + 6 * rnd(6)) + (fire ? 12 + 6 * rnd(5) : 8 + 6 * rnd(5)) * ease;
		p.kind = kind;
		p.shape = (int)(hc % SHAPES);
		p.life = std::min(LIFE - 1, (int)(ph * LIFE));
		out.push_back(p);
	}
	std::sort(out.begin() + first, out.end(), [](const Puff &a, const Puff &b) { return a.u + a.v < b.u + b.v; });
}

}

}
