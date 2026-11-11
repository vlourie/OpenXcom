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
#include "HdWeather.h"
#include "HdSprites.h"
#include "HdWorkers.h"
#include <algorithm>
#include <atomic>
#include <cctype>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <map>
#include <mutex>
#include <tuple>

namespace OpenXcom
{

namespace HdWeather
{

namespace
{
	/// The looks were drawn on frames of scale 4 (docs/research/battle-weather-2026-11-11.md, tools/hdart/weather_mock.py):
	/// sizes and speeds below are pixels of scale 4, times k / 4 on the canvas.
	const float LOOK_K = 4.0f;
	/// The side of a particle texture in pixels of scale 4 (it repeats; the counts are per 1920 x 1080 of scale 4).
	const int TILE4 = 512;
	const float MOCK_AREA = 1920.0f * 1080.0f;
	/// The side of the noise texture and its lattice.
	const int NOISE = 256;
	const int NOISE_CELLS = 16;
	/// The coarse grid of the air: a node every GRID canvas pixels.
	const int GRID = 8;
	/// The ground's noise repeats every PERIOD tiles.
	const int PERIOD = 8;

	inline Uint32 mix(Uint32 h)
	{
		h ^= h >> 16;
		h *= 0x85EBCA6Bu;
		h ^= h >> 13;
		h *= 0xC2B2AE35u;
		h ^= h >> 16;
		return h;
	}
	inline Uint32 hash(Uint32 a, Uint32 b, Uint32 c = 0, Uint32 d = 0)
	{
		return mix(a * 0x9E3779B1u ^ mix(b * 0x85EBCA77u ^ mix(c * 0xC2B2AE3Du ^ mix(d + 0x27D4EB2Fu))));
	}
	/// 0..1 from a hash.
	inline float unit(Uint32 h) { return (h >> 8) * (1.0f / 16777216.0f); }
	inline float smooth(float e0, float e1, float x)
	{
		float t = (x - e0) / (e1 - e0);
		t = t < 0 ? 0 : (t > 1 ? 1 : t);
		return t * t * (3 - 2 * t);
	}
	inline float clamp01(float x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }

	struct Rgb { float r, g, b; };

	/// One layer of particles: strokes (rain) or dots (snow, sand; a streak > 0 draws them as short strokes).
	struct LayerLook
	{
		bool dots;
		int count;
		/// Strokes: length and width; dots: the radii (rmin, rmax) and the streak length.
		float length, width, rmin, rmax, streak;
		/// Degrees from straight down, positive to the right (the mock's angle).
		float angle;
		Rgb color;
		float alpha;
		float blur;
		/// Pixels of scale 4 a second along the angle, and for dots the sway across it (amplitude, period in seconds).
		float speed, sway, swayPeriod;
	};
	/// A band of noise drifting in the wind (blizzard, sand) or wisps of fog.
	struct BandLook
	{
		float alpha;
		Rgb color;
		float scale, sx, sy, lo, hi;
		/// Drift, pixels of scale 4 a second (x, y).
		float vx, vy;
	};
	struct Look
	{
		float sat = 1;
		float mul[3] = { 1, 1, 1 };
		float add[3] = { 0, 0, 0 };
		/// The flat dust in the air over all the map (sand storm).
		float hazeA = 0;
		Rgb haze { 0, 0, 0 };
		/// The veil: threshold in tiles (0 = none), the colour, the strongest alpha, the softness in tiles and how ragged its edge is.
		float veil = 0, veilSoft = 3, veilA = 0, ragged = 0;
		Rgb veilColor { 0, 0, 0 };
		BandLook band {};
		int layers = 0;
		LayerLook layer[3] {};
		bool flash = false;
	};

	Look lookOf(Kind kind)
	{
		Look l;
		auto tone = [&](float sat, float r, float g, float b, float ar = 0, float ag = 0, float ab = 0)
		{
			l.sat = sat;
			l.mul[0] = r; l.mul[1] = g; l.mul[2] = b;
			l.add[0] = ar; l.add[1] = ag; l.add[2] = ab;
		};
		auto rain = [&](int n, float len, float wd, float al, float light, float sat)
		{
			tone(sat, light, light * 1.01f, light * 1.06f);
			l.layers = 3;
			l.layer[0] = LayerLook{ false, n, len * 0.6f, wd * 0.7f, 0, 0, 0, 12, { 190, 205, 220 }, al * 0.55f, 0, 900, 0, 0 };
			l.layer[1] = LayerLook{ false, n * 6 / 10, len, wd, 0, 0, 0, 12, { 205, 218, 232 }, al * 0.8f, 0, 1400, 0, 0 };
			l.layer[2] = LayerLook{ false, n * 2 / 10, len * 1.6f, wd * 1.4f, 0, 0, 0, 12, { 220, 230, 240 }, al, 0.5f, 2000, 0, 0 };
		};
		auto streaks = [&](int i, int n, float rmin, float rmax, Rgb c, float al, float streak, float angle, float speed)
		{
			l.layer[i] = LayerLook{ true, n, 0, 0, rmin, rmax, streak, angle, c, al, 0.6f, speed, 0, 0 };
		};
		auto flakes = [&](int i, int n, float rmin, float rmax, Rgb c, float al, float speed, float sway, float period)
		{
			l.layer[i] = LayerLook{ true, n, 0, 0, rmin, rmax, 0, 0, c, al, 0.6f, speed, sway, period };
		};
		switch (kind)
		{
		case DRIZZLE:
			rain(900, 10, 0.8f, 0.18f, 0.88f, 0.93f);
			break;
		case RAIN:
			rain(1500, 22, 1.0f, 0.30f, 0.80f, 0.85f);
			l.veil = 17; l.veilA = 0.55f; l.veilColor = { 150, 160, 172 };
			break;
		case DOWNPOUR:
			rain(2600, 34, 1.3f, 0.38f, 0.68f, 0.85f);
			l.veil = 14; l.veilA = 0.6f; l.veilColor = { 140, 150, 162 };
			break;
		case THUNDER:
			// the downpour, darker and colder (the mock's second tone over the first)
			rain(2600, 34, 1.3f, 0.38f, 0.68f, 0.85f);
			l.sat = 0.765f;
			l.mul[0] = 0.68f * 0.78f; l.mul[1] = 0.6868f * 0.8f; l.mul[2] = 0.7208f * 0.88f;
			l.veil = 14; l.veilA = 0.6f; l.veilColor = { 110, 118, 132 };
			l.flash = true;
			break;
		case FOG:
			tone(0.8f, 0.94f, 0.95f, 0.97f, 8, 9, 11);
			l.veil = 10; l.veilA = 0.85f; l.veilColor = { 170, 176, 182 }; l.ragged = 4;
			l.band = BandLook{ 0.28f, { 180, 186, 192 }, 90, 3.0f, 1.0f, 0.45f, 0.8f, 12, 3 };
			break;
		case FLAKES:
			tone(0.95f, 0.98f, 0.99f, 1.02f);
			l.layers = 2;
			flakes(0, 160, 1.2f, 2.6f, { 245, 248, 255 }, 0.75f, 70, 14, 3.1f);
			flakes(1, 60, 2.5f, 4.5f, { 250, 252, 255 }, 0.85f, 110, 22, 2.3f);
			break;
		case SNOWFALL:
			tone(0.85f, 0.92f, 0.94f, 0.99f, 6, 7, 10);
			l.veil = 17; l.veilA = 0.6f; l.veilColor = { 215, 220, 230 }; l.veilSoft = 4;
			l.layers = 3;
			flakes(0, 1400, 1.0f, 2.2f, { 235, 240, 250 }, 0.55f, 50, 12, 3.1f);
			flakes(1, 700, 1.8f, 3.6f, { 245, 248, 255 }, 0.75f, 80, 18, 2.3f);
			flakes(2, 140, 3.5f, 6.0f, { 250, 252, 255 }, 0.85f, 120, 25, 1.7f);
			break;
		case BLIZZARD:
			tone(0.7f, 0.88f, 0.9f, 0.96f, 18, 20, 26);
			l.veil = 11; l.veilA = 0.8f; l.veilColor = { 210, 216, 226 }; l.ragged = 3; l.veilSoft = 4;
			l.band = BandLook{ 0.25f, { 225, 230, 238 }, 120, 4.0f, 0.7f, 0.4f, 0.85f, 260, 150 };
			l.layers = 2;
			streaks(0, 2200, 1.0f, 2.0f, { 235, 240, 250 }, 0.55f, 10, 60, 700);
			streaks(1, 500, 2.0f, 3.2f, { 245, 248, 255 }, 0.7f, 18, 62, 1000);
			break;
		case WHITEOUT:
			tone(0.55f, 0.8f, 0.82f, 0.88f, 35, 38, 46);
			l.veil = 8; l.veilA = 0.9f; l.veilColor = { 215, 220, 228 }; l.ragged = 3; l.veilSoft = 2.5f;
			l.band = BandLook{ 0.38f, { 228, 232, 238 }, 100, 5.0f, 0.6f, 0.35f, 0.8f, 420, 80 };
			l.layers = 2;
			streaks(0, 3200, 0.9f, 1.8f, { 235, 240, 250 }, 0.6f, 22, 78, 1100);
			streaks(1, 700, 1.8f, 3.0f, { 248, 250, 255 }, 0.75f, 34, 80, 1500);
			break;
		case WIND:
			tone(0.97f, 1, 1, 1);
			// the bands drift with the particles (to the right and a little up: angle 100)
			l.band = BandLook{ 0.12f, { 235, 205, 150 }, 70, 6.0f, 0.5f, 0.55f, 0.9f, 380, -60 };
			l.layers = 1;
			streaks(0, 260, 0.8f, 1.5f, { 210, 170, 110 }, 0.5f, 26, 100, 900);
			break;
		case SANDSTORM:
			// the page's choice B: the dense storm
			tone(0.75f, 0.92f, 0.82f, 0.66f, 30, 18, 4);
			l.hazeA = 0.32f; l.haze = { 195, 145, 85 };
			l.veil = 8; l.veilA = 0.88f; l.veilColor = { 190, 140, 80 }; l.ragged = 3.5f; l.veilSoft = 2.5f;
			l.band = BandLook{ 0.42f, { 200, 150, 90 }, 110, 5.0f, 0.6f, 0.35f, 0.85f, 520, -50 };
			l.layers = 1;
			streaks(0, 2600, 0.8f, 1.6f, { 215, 170, 110 }, 0.55f, 30, 96, 1300);
			break;
		default:
			break;
		}
		return l;
	}

	/// A particle texture: alpha 0..255, side x side, repeating.
	struct Texture
	{
		int side = 0;
		std::vector<Uint8> a;
	};

	/// Draws a soft segment (or a dot when the ends meet) into the repeating texture.
	void paintSegment(Texture &t, float x0, float y0, float x1, float y1, float halfWidth, float soft, float alpha)
	{
		const int n = t.side;
		const float pad = halfWidth + soft + 1;
		const int bx0 = (int)std::floor(std::min(x0, x1) - pad), bx1 = (int)std::ceil(std::max(x0, x1) + pad);
		const int by0 = (int)std::floor(std::min(y0, y1) - pad), by1 = (int)std::ceil(std::max(y0, y1) + pad);
		const float dx = x1 - x0, dy = y1 - y0;
		const float len2 = dx * dx + dy * dy;
		for (int y = by0; y <= by1; ++y)
		{
			for (int x = bx0; x <= bx1; ++x)
			{
				const float px = x + 0.5f - x0, py = y + 0.5f - y0;
				float tt = len2 > 0 ? (px * dx + py * dy) / len2 : 0;
				tt = tt < 0 ? 0 : (tt > 1 ? 1 : tt);
				const float ex = px - tt * dx, ey = py - tt * dy;
				const float d = std::sqrt(ex * ex + ey * ey);
				const float cover = clamp01((halfWidth + soft * 0.5f - d) / soft);
				if (cover <= 0)
				{
					continue;
				}
				Uint8 &dst = t.a[(size_t)(((y % n) + n) % n) * n + (((x % n) + n) % n)];
				const float a = dst / 255.0f;
				const float out = a + cover * alpha * (1 - a);
				dst = (Uint8)std::min(255.0f, out * 255.0f + 0.5f);
			}
		}
	}

	/// Bakes a layer's texture at scale k: the jittered grid of the mock (no clumps, no holes).
	void bakeLayer(const LayerLook &L, int k, Uint32 seed, Texture &t)
	{
		const float s = k / LOOK_K;
		t.side = std::max(16, (int)std::lround(TILE4 * s));
		t.a.assign((size_t)t.side * t.side, 0);
		const int n = std::max(1, (int)std::lround(L.count * (TILE4 * TILE4) / MOCK_AREA));
		const int cols = std::max(1, (int)std::sqrt((float)n)), rows = std::max(1, (n + cols - 1) / cols);
		const float ang = L.angle * 3.14159265f / 180.0f;
		const float dx = std::sin(ang), dy = std::cos(ang);
		int i = 0;
		for (int r = 0; r < rows; ++r)
		{
			for (int c = 0; c < cols; ++c, ++i)
			{
				const float x = (c + unit(hash(seed, i, 1))) * t.side / cols;
				const float y = (r + unit(hash(seed, i, 2))) * t.side / rows;
				if (!L.dots)
				{
					const float len = L.length * (0.7f + 0.6f * unit(hash(seed, i, 3))) * s;
					const float a = L.alpha * (0.55f + 0.45f * unit(hash(seed, i, 4)));
					const float hw = std::max(0.5f, L.width * s * 0.5f);
					paintSegment(t, x, y, x + dx * len, y + dy * len, hw, 1.0f + L.blur * 2 * s, a);
				}
				else
				{
					const float q = unit(hash(seed, i, 3));
					const float rad = (L.rmin + (L.rmax - L.rmin) * q * q) * s;
					const float a = L.alpha * (0.5f + 0.5f * unit(hash(seed, i, 4)));
					if (L.streak > 0)
					{
						const float len = L.streak * (0.6f + 0.8f * unit(hash(seed, i, 5))) * s;
						paintSegment(t, x, y, x + dx * len, y + dy * len, std::max(0.5f, rad * 0.7f), 1.0f + L.blur * 2 * s, a);
					}
					else
					{
						paintSegment(t, x, y, x, y, std::max(0.6f, rad), 1.0f + L.blur * 2 * s, a);
					}
				}
			}
		}
	}

	/// Smooth repeating value noise, 0..1, NOISE x NOISE (three octaves).
	std::vector<float> bakeNoise(Uint32 seed)
	{
		std::vector<float> out((size_t)NOISE * NOISE, 0.0f);
		float amp = 1, total = 0;
		for (int o = 0; o < 3; ++o)
		{
			const int cells = NOISE_CELLS << o;
			const float step = (float)NOISE / cells;
			for (int y = 0; y < NOISE; ++y)
			{
				const float fy = y / step;
				const int y0 = (int)fy;
				const float ty = smooth(0, 1, fy - y0);
				for (int x = 0; x < NOISE; ++x)
				{
					const float fx = x / step;
					const int x0 = (int)fx;
					const float tx = smooth(0, 1, fx - x0);
					auto at = [&](int cx, int cy) { return unit(hash(seed, o, cx % cells, cy % cells)); };
					const float v = (at(x0, y0) * (1 - tx) + at(x0 + 1, y0) * tx) * (1 - ty) + (at(x0, y0 + 1) * (1 - tx) + at(x0 + 1, y0 + 1) * tx) * ty;
					out[(size_t)y * NOISE + x] += amp * v;
				}
			}
			total += amp;
			amp *= 0.5f;
		}
		float lo = 1e9f, hi = -1e9f;
		for (float &v : out)
		{
			v /= total;
			lo = std::min(lo, v);
			hi = std::max(hi, v);
		}
		for (float &v : out)
		{
			v = (v - lo) / (hi - lo + 1e-6f);
		}
		return out;
	}

	inline float noiseAt(const std::vector<float> &n, float x, float y)
	{
		x -= std::floor(x / NOISE) * NOISE;
		y -= std::floor(y / NOISE) * NOISE;
		const int x0 = (int)x, y0 = (int)y;
		const float tx = x - x0, ty = y - y0;
		const int x1 = (x0 + 1) & (NOISE - 1), y1 = (y0 + 1) & (NOISE - 1);
		const int xa = x0 & (NOISE - 1), ya = y0 & (NOISE - 1);
		return (n[ya * NOISE + xa] * (1 - tx) + n[ya * NOISE + x1] * tx) * (1 - ty) + (n[y1 * NOISE + xa] * (1 - tx) + n[y1 * NOISE + x1] * tx) * ty;
	}

	/// What the air keeps between frames: the look, the textures of the kind at a scale, the grid of the last prepare.
	struct Air
	{
		std::mutex lock;
		Kind kind = KINDS;
		int k = 0;
		Uint32 seed = 0;
		Look look;
		Texture tex[3];
		std::vector<float> noise;
		/// The grid: per node veil alpha, particles, band alpha, tone weight.
		int gw = 0, gh = 0;
		std::vector<float> grid;
	};
	Air &air()
	{
		static Air a;
		return a;
	}
	std::atomic<long long> bakeUs{ 0 };

	struct BakeTimer
	{
		std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
		~BakeTimer() { bakeUs += std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - start).count(); }
	};

	void ensure(Air &a, Kind kind, int k, Uint32 seed)
	{
		if (a.kind == kind && a.k == k && a.seed == seed)
		{
			return;
		}
		BakeTimer timer;
		a.kind = kind;
		a.k = k;
		a.seed = seed;
		a.look = lookOf(kind);
		HdWorkers::instance().run(a.look.layers, [&](int i)
		{
			bakeLayer(a.look.layer[i], k, hash(seed, 101 + i), a.tex[i]);
		});
		a.noise = bakeNoise(hash(seed, 77));
	}

	/// Bilinear sample of a view field at tile coordinates (u, v); outside the map the edge's value.
	inline float field(const float *f, int w, int l, float u, float v)
	{
		float fx = u - 0.5f, fy = v - 0.5f;
		fx = fx < 0 ? 0 : (fx > w - 1 ? w - 1 : fx);
		fy = fy < 0 ? 0 : (fy > l - 1 ? l - 1 : fy);
		const int x0 = (int)fx, y0 = (int)fy;
		const int x1 = std::min(w - 1, x0 + 1), y1 = std::min(l - 1, y0 + 1);
		const float tx = fx - x0, ty = fy - y0;
		return (f[y0 * w + x0] * (1 - tx) + f[y0 * w + x1] * tx) * (1 - ty) + (f[y1 * w + x0] * (1 - tx) + f[y1 * w + x1] * tx) * ty;
	}

	/// The offset of a layer's texture this frame: it falls along its angle and sways across it, anchored to the map.
	void layerOffset(const LayerLook &L, int k, int side, Uint32 ms, float &ox, float &oy)
	{
		const float s = k / LOOK_K;
		const double t = ms / 1000.0;
		const float ang = L.angle * 3.14159265f / 180.0f;
		const double along = std::fmod(t * L.speed * s, (double)side * 64);
		ox = (float)(std::sin(ang) * along);
		oy = (float)(std::cos(ang) * along);
		if (L.sway > 0)
		{
			ox += (float)(L.sway * s * std::sin(t * 6.2831853 / L.swayPeriod));
		}
	}

	// the ground
	struct GroundKey
	{
		int k, wet, puddles, snow, cx, cy, closed;
		Uint32 seed;
		bool operator<(const GroundKey &o) const
		{
			return std::tie(k, wet, puddles, snow, cx, cy, closed, seed) < std::tie(o.k, o.wet, o.puddles, o.snow, o.cx, o.cy, o.closed, o.seed);
		}
	};
	struct GroundCache
	{
		std::mutex lock;
		int k = 0, wet = -1, puddles = -1, snow = -1;
		Uint32 seed = 0;
		std::map<GroundKey, HdFrame> frames;
		std::map<GroundKey, bool> empty;
	};
	GroundCache &groundCache()
	{
		static GroundCache g;
		return g;
	}

	/// Repeating value noise over PERIOD tiles with `cells` lattice cells along it: 0..1 at tile coordinates (x, y).
	float periodic(Uint32 seed, int cells, float x, float y)
	{
		const float fx = x * cells / PERIOD, fy = y * cells / PERIOD;
		const int x0 = (int)std::floor(fx), y0 = (int)std::floor(fy);
		const float tx = smooth(0, 1, fx - x0), ty = smooth(0, 1, fy - y0);
		auto at = [&](int cx, int cy) { return unit(hash(seed, cells, ((cx % cells) + cells) % cells, ((cy % cells) + cells) % cells)); };
		return (at(x0, y0) * (1 - tx) + at(x0 + 1, y0) * tx) * (1 - ty) + (at(x0, y0 + 1) * (1 - tx) + at(x0 + 1, y0 + 1) * tx) * ty;
	}
	float octaves(Uint32 seed, int cells, int count, float x, float y)
	{
		float v = 0, amp = 1, total = 0;
		for (int o = 0; o < count; ++o)
		{
			v += amp * periodic(hash(seed, o), cells << o, x, y);
			total += amp;
			amp *= 0.5f;
		}
		return v / total;
	}
}

Biome biomeOf(const std::string &word, bool &cold)
{
	std::string w = word;
	cold = false;
	const std::string suffix = "_COLD";
	if (w.size() > suffix.size() && w.compare(w.size() - suffix.size(), suffix.size(), suffix) == 0)
	{
		cold = true;
		w.erase(w.size() - suffix.size());
	}
	static const std::pair<const char *, Biome> names[] = {
		{ "CITY", B_CITY }, { "STEPPE", B_STEPPE }, { "SNOW", B_SNOW }, { "SEA", B_SEA }, { "WASTE", B_WASTE },
		{ "DESERT", B_DESERT }, { "JUNGLE", B_JUNGLE }, { "FOREST", B_FOREST }, { "SWAMP", B_SWAMP } };
	for (const auto &n : names)
	{
		if (w == n.first)
		{
			return n.second;
		}
	}
	return B_NONE;
}

const char *kindName(Kind kind)
{
	static const char *names[KINDS] = { "clear", "drizzle", "rain", "downpour", "thunder", "fog", "flakes", "snowfall",
		"blizzard", "whiteout", "wind", "sandstorm" };
	return kind >= 0 && kind < KINDS ? names[kind] : "none";
}

Kind pick(Biome biome, bool cold, Uint32 seed)
{
	struct W { Kind kind; int weight; };
	static const std::vector<W> rainy = { { CLEAR, 50 }, { DRIZZLE, 12 }, { RAIN, 15 }, { DOWNPOUR, 6 }, { THUNDER, 4 }, { FOG, 13 } };
	static const std::vector<W> snowy = { { CLEAR, 45 }, { FLAKES, 20 }, { SNOWFALL, 20 }, { BLIZZARD, 10 }, { WHITEOUT, 5 } };
	static const std::vector<W> coldLand = { { CLEAR, 50 }, { FLAKES, 20 }, { SNOWFALL, 18 }, { BLIZZARD, 7 }, { FOG, 5 } };
	static const std::vector<W> steppe = { { CLEAR, 50 }, { DRIZZLE, 10 }, { RAIN, 12 }, { DOWNPOUR, 4 }, { THUNDER, 4 }, { FOG, 10 }, { WIND, 10 } };
	static const std::vector<W> sea = { { CLEAR, 45 }, { DRIZZLE, 10 }, { RAIN, 15 }, { DOWNPOUR, 10 }, { THUNDER, 8 }, { FOG, 12 } };
	static const std::vector<W> waste = { { CLEAR, 55 }, { WIND, 20 }, { DRIZZLE, 10 }, { RAIN, 8 }, { FOG, 7 } };
	static const std::vector<W> desert = { { CLEAR, 50 }, { WIND, 35 }, { SANDSTORM, 15 } };
	static const std::vector<W> jungle = { { CLEAR, 40 }, { DRIZZLE, 12 }, { RAIN, 20 }, { DOWNPOUR, 12 }, { THUNDER, 8 }, { FOG, 8 } };
	static const std::vector<W> forest = { { CLEAR, 50 }, { DRIZZLE, 12 }, { RAIN, 15 }, { DOWNPOUR, 5 }, { FOG, 18 } };
	static const std::vector<W> swamp = { { CLEAR, 45 }, { DRIZZLE, 20 }, { RAIN, 15 }, { FOG, 20 } };
	const std::vector<W> *table = nullptr;
	switch (biome)
	{
	case B_CITY: table = cold ? &coldLand : &rainy; break;
	case B_STEPPE: table = cold ? &coldLand : &steppe; break;
	case B_SNOW: table = &snowy; break;
	case B_SEA: table = &sea; break;
	case B_WASTE: table = cold ? &coldLand : &waste; break;
	case B_DESERT: table = &desert; break;
	case B_JUNGLE: table = &jungle; break;
	case B_FOREST: table = cold ? &coldLand : &forest; break;
	case B_SWAMP: table = cold ? &coldLand : &swamp; break;
	default: return CLEAR;
	}
	int total = 0;
	for (const W &w : *table)
	{
		total += w.weight;
	}
	int roll = (int)(mix(seed ^ 0x5EA7u) % (Uint32)total);
	for (const W &w : *table)
	{
		if (roll < w.weight)
		{
			return w.kind;
		}
		roll -= w.weight;
	}
	return CLEAR;
}

Kind forced()
{
	const char *env = getenv("OXCE_HD_WEATHER");
	if (!env || !*env)
	{
		return KINDS;
	}
	std::string name = env;
	for (char &c : name)
	{
		c = (char)std::tolower((unsigned char)c);
	}
	for (int i = 0; i < KINDS; ++i)
	{
		if (name == kindName((Kind)i))
		{
			return (Kind)i;
		}
	}
	return KINDS;
}

float power(Uint32 seed, int turn)
{
	// a slow swell with its own phase and period, and a little of the turn's own
	const float phase = unit(hash(seed, 11)) * 6.2831853f;
	const float period = 5 + 4 * unit(hash(seed, 12));
	const float wave = 0.5f + 0.5f * std::sin(phase + turn * 6.2831853f / period);
	const float jitter = unit(hash(seed, 13, turn)) - 0.5f;
	return std::max(0.6f, std::min(1.0f, 0.62f + 0.34f * wave + 0.08f * jitter));
}

float veilTiles(Kind kind)
{
	return lookOf(kind).veil;
}

int strikeAt(Uint32 seed, Uint32 slot)
{
	const Uint32 h = hash(seed, 31, slot);
	return (h & 3) == 0 ? -1 : (int)(500 + (h >> 4) % 5500);
}

float lightning(Kind kind, Uint32 seed, Uint32 ms)
{
	if (kind != THUNDER)
	{
		return 0;
	}
	// one strike a slot of 7 s at a place of its own in the slot: a flash, a short dark, a weaker second flash
	const Uint32 slot = ms / STRIKE_SLOT;
	const int at = strikeAt(seed, slot);
	if (at < 0)
	{
		return 0; // a quiet slot
	}
	const int t = (int)(ms % STRIKE_SLOT) - at;
	if (t < 0 || t >= 420)
	{
		return 0;
	}
	if (t < 90)
	{
		return 1.0f - t / 180.0f;
	}
	if (t < 170)
	{
		return 0;
	}
	if (t < 260)
	{
		return 0.55f * (1.0f - (t - 170) / 90.0f);
	}
	return 0;
}

bool still(Kind kind)
{
	return kind == CLEAR || kind == KINDS;
}

Ground ground(Kind kind, Uint32 seed, int turn)
{
	Ground g;
	const float t = (float)std::max(1, turn);
	switch (kind)
	{
	case RAIN:
		g.wet = 0.25f;
		break;
	case DOWNPOUR:
	case THUNDER:
		// the mock's downpour (its puddles where the noise passes 0.66, a share of 0.34): the floor wet, the puddles
		// a quarter of that share at the 1st turn, nearly all of it by the 3rd
		g.wet = 0.55f;
		g.puddles = 0.34f * (1 - std::exp(-(t + 1) / 1.5f));
		break;
	case FLAKES:
		g.snow = 0.5f * (1 - std::exp(-t / 10.0f));
		break;
	case SNOWFALL:
		// the page's turns: about 0.42 at the 3rd, 0.78 at the 10th
		g.snow = 0.85f * (1 - std::exp(-t / 4.0f));
		break;
	case BLIZZARD:
	case WHITEOUT:
		g.snow = 0.9f * (1 - std::exp(-t / 3.0f));
		break;
	default:
		break;
	}
	(void)seed;
	return g;
}

void prepare(const Scene &s)
{
	Air &a = air();
	std::lock_guard<std::mutex> guard(a.lock);
	ensure(a, s.kind, s.k, s.seed);
	const Look &L = a.look;
	a.gw = s.width / GRID + 2;
	a.gh = s.height / GRID + 2;
	a.grid.assign((size_t)a.gw * a.gh * 4, 0.0f);
	const float sc = s.k / LOOK_K;
	const double t = s.ms / 1000.0;
	const float ragScale = 140 * sc, ragSx = 2.2f;
	const float veilA = L.veilA * s.power;
	const float bandA = L.band.alpha * s.power;
	// the drift of the ragged edge and of the bands, anchored to the map
	const float ragDx = (float)std::fmod(t * 20 * sc, 1.0e6), bandDx = (float)std::fmod(t * L.band.vx * sc, 1.0e6), bandDy = (float)std::fmod(t * L.band.vy * sc, 1.0e6);
	const int rowsPerJob = 8;
	const int jobs = (a.gh + rowsPerJob - 1) / rowsPerJob;
	HdWorkers::instance().run(jobs, [&](int job)
	{
		for (int gy = job * rowsPerJob; gy < std::min(a.gh, (job + 1) * rowsPerJob); ++gy)
		{
			for (int gx = 0; gx < a.gw; ++gx)
			{
				const float px = gx * (float)GRID, py = gy * (float)GRID;
				const float u = s.au * px + s.bu * py + s.cu, v = s.av * px + s.bv * py + s.cv;
				const float inside = std::min(std::min(u, v), std::min(s.mapW - u, s.mapL - v));
				const float m = smooth(-0.5f, 0.5f, inside);
				const float kn = m > 0 && s.known ? field(s.known, s.mapW, s.mapL, u, v) : 0.0f;
				float *node = &a.grid[((size_t)gy * a.gw + gx) * 4];
				const float wx = px - s.originX, wy = py - s.originY;
				float va = 0;
				if (L.veil > 0 && m > 0)
				{
					float d = field(s.dist, s.mapW, s.mapL, u, v);
					if (L.ragged > 0)
					{
						d += (noiseAt(a.noise, (wx - ragDx) / (ragScale * ragSx) * NOISE_CELLS, wy / ragScale * NOISE_CELLS) - 0.5f) * L.ragged;
					}
					va = smooth(L.veil, L.veil + L.veilSoft, d) * veilA * m;
					// a spotted enemy and the cursor keep a window: the veil there is at most a light haze
					const float w = field(s.window, s.mapW, s.mapL, u, v);
					va = std::min(va, 0.45f + 0.55f * smooth(1.2f, 2.5f, w));
				}
				float ba = 0;
				if (bandA > 0 && m > 0)
				{
					const float bs = L.band.scale * sc;
					const float n = noiseAt(a.noise, (wx - bandDx) / (bs * L.band.sx) * NOISE_CELLS + 97, (wy - bandDy) / (bs * L.band.sy) * NOISE_CELLS + 31);
					ba = smooth(L.band.lo, L.band.hi, n) * bandA * m;
				}
				const float sky = m > 0 ? field(s.sky, s.mapW, s.mapL, u, v) : 1.0f;
				node[0] = va * kn;
				node[1] = (0.45f + 0.55f * m) * sky;
				node[2] = ba * kn;
				node[3] = m * kn;
			}
		}
	});
}

void drawRows(const Scene &s, Uint32 *pixels, int pitchBytes, int y0, int y1, int rshift, int gshift, int bshift)
{
	Air &a = air();
	if (a.kind != s.kind || a.k != s.k || a.grid.empty())
	{
		return;
	}
	const Look &L = a.look;
	const float day = std::max(0.0f, std::min(1.0f, s.day));
	const float toneW = 0.5f + 0.5f * s.power;
	const float add[3] = { L.add[0] * day, L.add[1] * day, L.add[2] * day };
	const float veilDim = 0.25f + 0.75f * day, bandDim = 0.3f + 0.7f * day, partDim = 0.35f + 0.65f * day;
	const Rgb veil { L.veilColor.r * veilDim, L.veilColor.g * veilDim, L.veilColor.b * veilDim };
	const Rgb band { L.band.color.r * bandDim, L.band.color.g * bandDim, L.band.color.b * bandDim };
	const Rgb haze { L.haze.r * bandDim, L.haze.g * bandDim, L.haze.b * bandDim };
	const float hazeA = L.hazeA * s.power;
	struct LayerRun { const Uint8 *tex; int side; float ox, oy; Rgb c; float alpha; };
	LayerRun runs[3];
	for (int i = 0; i < L.layers; ++i)
	{
		float ox, oy;
		layerOffset(L.layer[i], s.k, a.tex[i].side, s.ms, ox, oy);
		runs[i] = LayerRun{ a.tex[i].a.data(), a.tex[i].side, ox, oy,
			{ L.layer[i].color.r * partDim, L.layer[i].color.g * partDim, L.layer[i].color.b * partDim }, s.power / 255.0f };
	}
	const float flash = L.flash ? s.flash : 0.0f;
	const int gw = a.gw;
	const float *grid = a.grid.data();
	for (int y = y0; y < y1; ++y)
	{
		Uint32 *row = (Uint32*)((Uint8*)pixels + (size_t)y * pitchBytes);
		const float gyf = (y + 0.5f) / GRID;
		const int gy = std::min(a.gh - 2, (int)gyf);
		const float ty = gyf - gy;
		const float *r0 = grid + (size_t)gy * gw * 4, *r1 = r0 + (size_t)gw * 4;
		// the rows of the layers' textures this row reads
		const Uint8 *texRow[3];
		int texX[3];
		for (int i = 0; i < L.layers; ++i)
		{
			const int side = runs[i].side;
			int ry = (int)std::floor(y - s.originY - runs[i].oy);
			ry = ((ry % side) + side) % side;
			texRow[i] = runs[i].tex + (size_t)ry * side;
			int rx = (int)std::floor(-s.originX - runs[i].ox);
			texX[i] = ((rx % side) + side) % side;
		}
		for (int gx = 0; gx * GRID < s.width; ++gx)
		{
			float left[4], right[4], step[4];
			for (int c = 0; c < 4; ++c)
			{
				left[c] = r0[gx * 4 + c] * (1 - ty) + r1[gx * 4 + c] * ty;
				right[c] = r0[(gx + 1) * 4 + c] * (1 - ty) + r1[(gx + 1) * 4 + c] * ty;
				step[c] = (right[c] - left[c]) / GRID;
				left[c] += step[c] * 0.5f;
			}
			const int xEnd = std::min(s.width, (gx + 1) * GRID);
			for (int x = gx * GRID; x < xEnd; ++x)
			{
				const Uint32 d = row[x];
				float r = (float)((d >> rshift) & 0xFF), g = (float)((d >> gshift) & 0xFF), b = (float)((d >> bshift) & 0xFF);
				const float va = left[0], part = left[1], ba = left[2], m = left[3];
				if (m > 0)
				{
					// the overcast: less colour, a cooler light
					const float gray = (r + g + b) * (1.0f / 3);
					const float w = m * toneW;
					const float tr = (gray + (r - gray) * L.sat) * L.mul[0] + add[0];
					const float tg = (gray + (g - gray) * L.sat) * L.mul[1] + add[1];
					const float tb = (gray + (b - gray) * L.sat) * L.mul[2] + add[2];
					r += (tr - r) * w; g += (tg - g) * w; b += (tb - b) * w;
					if (hazeA > 0)
					{
						const float h = hazeA * m;
						r += (haze.r - r) * h; g += (haze.g - g) * h; b += (haze.b - b) * h;
					}
				}
				if (va > 0)
				{
					r += (veil.r - r) * va; g += (veil.g - g) * va; b += (veil.b - b) * va;
				}
				if (ba > 0)
				{
					r += (band.r - r) * ba; g += (band.g - g) * ba; b += (band.b - b) * ba;
				}
				if (part > 0)
				{
					for (int i = 0; i < L.layers; ++i)
					{
						const Uint8 t = texRow[i][texX[i]];
						if (t)
						{
							const float al = t * runs[i].alpha * part;
							r += (runs[i].c.r - r) * al; g += (runs[i].c.g - g) * al; b += (runs[i].c.b - b) * al;
						}
					}
				}
				if (flash > 0 && m > 0)
				{
					// the strike: all at once lighter and colder, the shadows stay (not a fog)
					const float f = flash * m;
					r += (std::min(255.0f, r * 1.9f + 18) - r) * f;
					g += (std::min(255.0f, g * 1.95f + 18) - g) * f;
					b += (std::min(255.0f, b * 2.15f + 18) - b) * f;
				}
				const int ri = (int)(r < 0 ? 0 : (r > 255 ? 255 : r + 0.5f));
				const int gi = (int)(g < 0 ? 0 : (g > 255 ? 255 : g + 0.5f));
				const int bi = (int)(b < 0 ? 0 : (b > 255 ? 255 : b + 0.5f));
				row[x] = (d & ~((0xFFu << rshift) | (0xFFu << gshift) | (0xFFu << bshift))) | ((Uint32)ri << rshift) | ((Uint32)gi << gshift) | ((Uint32)bi << bshift);
				for (int c = 0; c < 4; ++c)
				{
					left[c] += step[c];
				}
				for (int i = 0; i < L.layers; ++i)
				{
					if (++texX[i] == runs[i].side)
					{
						texX[i] = 0;
					}
				}
			}
		}
	}
}

const HdFrame *groundFrame(int k, const Ground &gr, Uint32 seed, int x, int y, int closed)
{
	if (!gr.any())
	{
		return nullptr;
	}
	GroundCache &c = groundCache();
	const int wet = (int)std::lround(gr.wet * 32), puddles = (int)std::lround(gr.puddles * 64), snow = (int)std::lround(gr.snow * 64);
	std::lock_guard<std::mutex> guard(c.lock);
	if (c.k != k || c.wet != wet || c.puddles != puddles || c.snow != snow || c.seed != seed)
	{
		c.frames.clear();
		c.empty.clear();
		c.k = k; c.wet = wet; c.puddles = puddles; c.snow = snow; c.seed = seed;
	}
	const int cx = ((x % PERIOD) + PERIOD) % PERIOD, cy = ((y % PERIOD) + PERIOD) % PERIOD;
	const GroundKey key{ k, wet, puddles, snow, cx, cy, closed & 15, seed };
	auto found = c.frames.find(key);
	if (found != c.frames.end())
	{
		return &found->second;
	}
	if (c.empty.count(key))
	{
		return nullptr;
	}
	BakeTimer timer;
	HdFrame f;
	f.width = 32 * k;
	f.height = 16 * k;
	f.pixels.assign((size_t)f.width * f.height, 0);
	const float wetA = wet / 32.0f * 0.22f;
	const float share = puddles / 64.0f, amount = snow / 64.0f;
	const float pThr = 1.0f - share;
	bool any = false;
	for (int py = 0; py < f.height; ++py)
	{
		for (int px = 0; px < f.width; ++px)
		{
			// the diamond: a pixel's centre (u, v) from the top corner in base pixels is the voxel (v + u / 2, v - u / 2)
			const float u = (px + 0.5f) / k - 16, v = (py + 0.5f) / k;
			const float vx = v + u / 2, vy = v - u / 2;
			if (vx < 0 || vx >= 16 || vy < 0 || vy >= 16)
			{
				continue;
			}
			const float tx = cx + vx / 16, ty = cy + vy / 16;
			// a side with no open floor beyond: the cover thins out over 5 voxels to nothing on the edge, smoothly at
			// the pixel scale, so the edge is never the diamond's staircase
			float edge = 1;
			const float soft = 5;
			if (closed & SIDE_X0) edge = std::min(edge, vx / soft);
			if (closed & SIDE_X1) edge = std::min(edge, (16 - vx) / soft);
			if (closed & SIDE_Y0) edge = std::min(edge, vy / soft);
			if (closed & SIDE_Y1) edge = std::min(edge, (16 - vy) / soft);
			edge = smooth(0, 1, edge);
			if (edge <= 0)
			{
				continue;
			}
			// straight-alpha "over" of the layers in order: wet, puddle, its rim, snow
			float r = 0, g = 0, b = 0, al = 0;
			auto over = [&](float cr, float cg, float cb, float a)
			{
				if (a <= 0)
				{
					return;
				}
				const float outA = a + al * (1 - a);
				r = (cr * a + r * al * (1 - a)) / outA;
				g = (cg * a + g * al * (1 - a)) / outA;
				b = (cb * a + b * al * (1 - a)) / outA;
				al = outA;
			};
			if (wetA > 0)
			{
				over(0, 0, 0, wetA);
			}
			if (share > 0)
			{
				const float n = octaves(hash(seed, 7), 6, 2, tx, ty);
				const float pm = smooth(pThr, pThr + 0.05f, n);
				const float rim = clamp01(smooth(pThr - 0.06f, pThr - 0.03f, n) - smooth(pThr - 0.03f, pThr, n));
				over(150, 165, 180, rim * 0.25f);
				over(50, 60, 72, pm * 0.5f);
			}
			if (amount > 0)
			{
				const float n = octaves(hash(seed, 13), 5, 4, tx, ty);
				const float cover = smooth(1.0f - amount, 1.0f - amount + 0.08f, n);
				const float lit = 0.85f + 0.15f * n;
				over(236 * lit, 240 * lit, 248 * lit, cover);
			}
			al *= edge;
			if (al > 0.002f)
			{
				const int ai = std::min(255, (int)std::lround(al * 255));
				f.pixels[(size_t)py * f.width + px] = ((Uint32)ai << 24) | ((Uint32)std::lround(std::min(255.0f, r)) << 16)
					| ((Uint32)std::lround(std::min(255.0f, g)) << 8) | (Uint32)std::lround(std::min(255.0f, b));
				any = true;
			}
		}
	}
	if (!any)
	{
		c.empty[key] = true;
		return nullptr;
	}
	f.generated = true;
	f.buildSpans();
	HdFrame &stored = c.frames[key];
	stored = std::move(f);
	return &stored;
}

namespace
{
	/// Frames of a ring's life.
	const int RING_LIFE = 6;
	/// Base pixels: the ring's radius at birth and at its end, the frame's half width.
	const float RING_R0 = 0.8f, RING_R1 = 3.6f;
	const int RING_HALF = 5;
	std::mutex ringLock;
	std::map<int, std::array<HdFrame, RING_LIFE>> rings;

	const std::array<HdFrame, RING_LIFE> &ringFrames(int k)
	{
		std::lock_guard<std::mutex> guard(ringLock);
		auto found = rings.find(k);
		if (found != rings.end())
		{
			return found->second;
		}
		BakeTimer timer;
		std::array<HdFrame, RING_LIFE> &set = rings[k];
		for (int i = 0; i < RING_LIFE; ++i)
		{
			HdFrame &f = set[i];
			f.width = 2 * RING_HALF * k;
			f.height = RING_HALF * k;
			f.pixels.assign((size_t)f.width * f.height, 0);
			const float t = (i + 0.5f) / RING_LIFE;
			const float r = RING_R0 + (RING_R1 - RING_R0) * std::sqrt(t);
			const float fade = 0.55f * std::pow(1 - t, 1.2f);
			const float halfWidth = 0.35f, aa = 1.0f / k;
			for (int py = 0; py < f.height; ++py)
			{
				for (int px = 0; px < f.width; ++px)
				{
					// base pixels from the centre; the floor is seen at 2:1, so the ring is an ellipse twice as wide
					const float dx = (px + 0.5f) / k - RING_HALF, dy = ((py + 0.5f) / k - RING_HALF * 0.5f) * 2;
					const float c = std::sqrt(dx * dx + dy * dy);
					const float d = std::fabs(c - r);
					float a = clamp01((halfWidth + aa * 0.5f - d) / aa) * fade;
					if (i == 0)
					{
						// the drop's hit: a bright point in the middle of the first ring
						a = std::max(a, clamp01((0.5f + aa * 0.5f - c) / aa) * 0.6f);
					}
					if (a > 0.004f)
					{
						f.pixels[(size_t)py * f.width + px] = ((Uint32)std::lround(a * 255) << 24) | (205u << 16) | (215u << 8) | 228u;
					}
				}
			}
			f.generated = true;
			f.buildSpans();
		}
		return set;
	}
}

int splashes(Kind kind, int k, Uint32 seed, Uint32 ms, float power, int x, int y, Splash out[SPLASHES])
{
	int slots = 0;
	Uint32 period = 0;
	switch (kind)
	{
	case DRIZZLE: slots = 1; period = 2200; break;
	case RAIN: slots = 2; period = 1300; break;
	case DOWNPOUR: case THUNDER: slots = 3; period = 800; break;
	default: return 0;
	}
	const Uint32 life = 320;
	const std::array<HdFrame, RING_LIFE> &frames = ringFrames(k);
	int n = 0;
	for (int s = 0; s < slots && n < SPLASHES; ++s)
	{
		// every slot of every tile has its own phase; a weaker turn leaves a share of the cycles without a drop
		const Uint32 h = hash(seed, (Uint32)x, (Uint32)y, 0x5917u + s);
		const Uint32 at = ms + (h % period);
		const Uint32 cycle = at / period, inCycle = at % period;
		if (inCycle >= life)
		{
			continue;
		}
		const Uint32 hc = hash(h, cycle);
		if (unit(hc) > power)
		{
			continue;
		}
		const int frame = std::min(RING_LIFE - 1, (int)(inCycle * RING_LIFE / life));
		// a place inside the diamond away from its edges: tile fractions (fu, fv) along x and y
		const float fu = 0.2f + 0.6f * unit(hash(hc, 1)), fv = 0.2f + 0.6f * unit(hash(hc, 2));
		const HdFrame &f = frames[frame];
		out[n].frame = &f;
		out[n].x = (int)std::lround((16 + (fu - fv) * 16) * k) - f.width / 2;
		out[n].y = (int)std::lround(((fu + fv) * 8) * k) - f.height / 2;
		++n;
	}
	return n;
}

int bakeMs()
{
	return (int)(bakeUs.load() / 1000);
}

}

}
