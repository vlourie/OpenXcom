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
#include "HdBaseScene.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <sstream>
#include <string>
#include "HdWorkers.h"
#include "Logger.h"

namespace OpenXcom
{

namespace HdBaseScene
{

namespace
{

const float PI = 3.14159265f;
/// Rows of the world layer one job lights.
const int BAND = 8;
/// The height of a lamp over the floor, pack pixels: light falls on the floor at a slant (base_scene_preview.py).
const float LAMP_HEIGHT = 26.0f;
/// The halo of a lamp, pack pixels (sigma): a sharp core and its wide glow.
const float CORE = 1.8f, GLOW = 7.2f;
const float CORE_GAIN = 0.6f, GLOW_GAIN = 0.073f;
/// The ambient light by day and at night (blue moonlight), before the tone curve.
const float DAY[3] = { 0.90f, 0.88f, 0.85f };
const float NIGHT[3] = { 0.20f, 0.25f, 0.38f };
/// The tone curve: x from 0 to LUT_MAX, LUT_STEPS entries per unit.
const int LUT_MAX = 4;
const int LUT_STEPS = 1024;
const int LUT_SIZE = LUT_MAX * LUT_STEPS + 1;

bool kindOf(const std::string &word, Kind &kind)
{
	static const char *names[] = { "steady", "blink", "pulse", "screen", "flicker" };
	for (int i = 0; i < 5; ++i)
	{
		if (word == names[i])
		{
			kind = (Kind)i;
			return true;
		}
	}
	return false;
}

float smooth(float x)
{
	x = std::min(1.0f, std::max(0.0f, x));
	return x * x * (3 - 2 * x);
}

/// The slow wobble of a flame or a screen: a few sines, -1 .. 1.
float wobble(float t, float seed)
{
	return std::sin(t * 7.1f + seed * 1.7f) * 0.5f + std::sin(t * 13.3f + seed * 3.1f) * 0.3f
		+ std::sin(t * 29.7f + seed * 0.7f) * 0.2f;
}

/// The ACES curve over the lit picture (x 1.25, as the preview), so a white lab under its lamps
/// does not burn out to flat white.
const unsigned char *toneCurve()
{
	static unsigned char lut[LUT_SIZE];
	static bool made = false;
	if (!made)
	{
		for (int i = 0; i < LUT_SIZE; ++i)
		{
			const float x = (float)i / LUT_STEPS * 1.25f;
			const float y = x * (2.51f * x + 0.03f) / (x * (2.43f * x + 0.59f) + 0.14f);
			lut[i] = (unsigned char)std::lround(std::min(1.0f, std::max(0.0f, y)) * 255.0f);
		}
		made = true;
	}
	return lut;
}

/// How bright a light is now (with the night's gain), as in base_scene_preview.py.
float strength(const Placed &p, float t, float night)
{
	const Light &L = p.light;
	float gain = 0.28f + 0.72f * night;
	float v = 1.0f;
	switch (L.kind)
	{
	case BLINK:
		v = std::fmod(t / std::max(0.1f, L.period) + L.phase, 1.0f) < 0.5f ? 1.0f : 0.08f;
		break;
	case PULSE:
		v = 0.6f + 0.4f * std::sin((t / std::max(0.1f, L.period) + L.phase) * 2 * PI);
		break;
	case FLICKER:
		v = 0.82f + 0.18f * wobble(t, (float)(p.seed % 97));
		break;
	case SCREEN:
		v = 0.8f + 0.2f * std::fabs(wobble(t * 0.5f, 4.0f + (float)(p.seed % 13)));
		gain = 0.4f + 0.5f * night;
		break;
	default:
		break;
	}
	if (p.home && L.kind == STEADY)
	{
		v *= 1 - 0.85f * night;
	}
	return v * gain * p.level;
}

/// A number 0..1 from a particle's number, its life and a salt - the particles' own dice, never the game's.
float hash1(Uint32 a, Uint32 b, Uint32 c = 0)
{
	Uint32 h = a * 0x9E3779B1u ^ (b + 0x7F4A7C15u) * 0x85EBCA77u ^ (c + 0x165667B1u) * 0xC2B2AE3Du;
	h ^= h >> 15;
	h *= 0x2C1B3C6Du;
	h ^= h >> 12;
	h *= 0x297A2D39u;
	h ^= h >> 15;
	return (h >> 8) * (1.0f / 16777216.0f);
}

/// exp(-q) for q = 0 .. 8 by a table: a soft blob costs a lookup per pixel.
const float *softTable()
{
	static float table[257];
	static bool made = false;
	if (!made)
	{
		for (int i = 0; i <= 256; ++i)
		{
			table[i] = std::exp(-(float)i / 32.0f);
		}
		made = true;
	}
	return table;
}

/// A soft round spot (sigma 0.6 r, as the preview's blobs) or a thin ring of radius `ring`, into the area:
/// `add` adds light, otherwise the colour is laid over with its alpha.
void blob(SDL_Surface *world, int ax0, int ay0, int ax1, int ay1, float cx, float cy, float r, float ring,
	const float col[3], float a, bool add)
{
	if (a <= 0.004f || r <= 0)
	{
		return;
	}
	const float sigma = ring > 0 ? 0.7f * r : 0.6f * r;
	const float inv = 1.0f / (2 * sigma * sigma);
	const float reach = ring + 2.8f * sigma;
	const int x0 = std::max(ax0, (int)std::floor(cx - reach)), x1 = std::min(ax1, (int)std::ceil(cx + reach) + 1);
	const int y0 = std::max(ay0, (int)std::floor(cy - reach)), y1 = std::min(ay1, (int)std::ceil(cy + reach) + 1);
	const float *table = softTable();
	for (int y = y0; y < y1; ++y)
	{
		Uint32 *row = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch);
		const float dy = y + 0.5f - cy;
		for (int x = x0; x < x1; ++x)
		{
			const float dx = x + 0.5f - cx;
			float d = dx * dx + dy * dy;
			if (ring > 0)
			{
				d = std::sqrt(d) - ring;
				d *= d;
			}
			const float q = d * inv * 32.0f;
			if (q >= 256.0f)
			{
				continue;
			}
			const float k = a * table[(int)q];
			const Uint32 px = row[x];
			Uint32 out = px & 0xFF000000u;
			for (int c = 0; c < 3; ++c)
			{
				const int shift = 16 - 8 * c;
				const float v = ((px >> shift) & 0xFF) / 255.0f;
				const float o = add ? v + col[c] * k : v + (col[c] - v) * std::min(1.0f, k);
				out |= (Uint32)std::lround(std::min(1.0f, std::max(0.0f, o)) * 255.0f) << shift;
			}
			row[x] = out;
		}
	}
}

/// A light of this frame, with what does not change from pixel to pixel worked out.
struct Lit
{
	float x, y;
	float r2;                    ///< radius^2 of the light falling on the pictures
	float lz2, lz;               ///< the lamp's height (and squared)
	float add[3];                ///< colour x strength into the light falling on the pictures
	float glow[3];               ///< colour x strength into the halo
	float core, wide;            ///< -1 / (2 sigma^2) of the halo's parts
	float halo2;                 ///< radius^2 of the halo
	int x0, x1, y0, y1;          ///< the box it touches, clipped to the area
};

}

bool parse(std::istream &in, TileScene &out)
{
	out = TileScene();
	std::string line;
	while (std::getline(in, line))
	{
		std::istringstream words(line);
		std::string key;
		words >> key;
		if (key == "size")
		{
			words >> out.width >> out.height;
		}
		else if (key == "gate")
		{
			std::string g;
			words >> g;
			out.gate = g == "lab" ? GATE_LAB : g == "work" ? GATE_WORK : g == "home" ? GATE_HOME : GATE_NONE;
		}
		else if (key == "light")
		{
			Light L;
			std::string kind;
			words >> L.x >> L.y >> L.radius >> kind >> L.r >> L.g >> L.b >> L.period >> L.phase;
			if (words && kindOf(kind, L.kind) && L.radius > 0)
			{
				out.lights.push_back(L);
			}
		}
		else if (key == "emit")
		{
			static const char *names[] = { "steam", "bubbles", "sparks", "embers", "orbit" };
			Emit E;
			std::string kind;
			words >> kind >> E.x >> E.y >> E.w >> E.h >> E.r >> E.g >> E.b;
			for (int i = 0; i < 5; ++i)
			{
				if (words && kind == names[i] && E.w >= 0 && E.h >= 0)
				{
					E.kind = (EmitKind)i;
					out.emits.push_back(E);
				}
			}
		}
	}
	return out.width > 0 && out.height > 0;
}

float nightAt(double longitude, int hour, int minute, int second)
{
	if (const char *env = std::getenv("OXCE_HD_BASE_NIGHT"))
	{
		return std::min(1.0f, std::max(0.0f, (float)std::atof(env)));
	}
	// the sun's height by the local time of day: 1 at noon, -1 at midnight (no seasons); longitude
	// grows to the east, as in Globe::getSunDirection
	const double pi = 3.14159265358979;
	const double hours = hour + minute / 60.0 + second / 3600.0 + longitude * 12.0 / pi;
	const float sun = (float)std::sin((hours - 6.0) / 24.0 * 2 * pi);
	// dusk from the sun just over the horizon to well under it
	return smooth((0.1f - sun) / 0.3f);
}

void draw(SDL_Surface *world, const SDL_Rect &area, const std::vector<Placed> &lights, float night, Uint32 ms)
{
	if (!world || world->format->BytesPerPixel != 4)
	{
		return;
	}
	const int ax0 = std::max(0, (int)area.x), ay0 = std::max(0, (int)area.y);
	const int ax1 = std::min(world->w, area.x + (int)area.w), ay1 = std::min(world->h, area.y + (int)area.h);
	if (ax0 >= ax1 || ay0 >= ay1)
	{
		return;
	}
	// OXCE_HD_BASE_PERF: the cost of the light, an average every 60 frames into the log
	static const bool perf = std::getenv("OXCE_HD_BASE_PERF") != nullptr;
	const auto perfStart = std::chrono::steady_clock::now();
	const float t = (float)(ms % 3600000u) / 1000.0f;
	float amb[3];
	for (int c = 0; c < 3; ++c)
	{
		amb[c] = DAY[c] * (1 - night) + NIGHT[c] * night;
	}
	const float halo = 0.2f + 0.6f * night;
	std::vector<Lit> lit;
	lit.reserve(lights.size());
	for (const Placed &p : lights)
	{
		const float v = strength(p, t, night);
		if (v <= 0.01f)
		{
			continue;
		}
		const float s = std::max(0.05f, p.scale);
		Lit L;
		L.x = p.light.x;
		L.y = p.light.y;
		L.r2 = p.light.radius * p.light.radius;
		L.lz = LAMP_HEIGHT * s;
		L.lz2 = L.lz * L.lz;
		const float cols[3] = { p.light.r, p.light.g, p.light.b };
		for (int c = 0; c < 3; ++c)
		{
			L.add[c] = cols[c] * v * 0.9f;
			L.glow[c] = cols[c] * v * halo;
		}
		L.core = -1.0f / (2 * CORE * CORE * s * s);
		L.wide = -1.0f / (2 * GLOW * GLOW * s * s);
		const float reachHalo = 3 * GLOW * s;
		L.halo2 = reachHalo * reachHalo;
		const float reach = std::max(p.light.radius, reachHalo);
		L.x0 = std::max(ax0, (int)std::floor(L.x - reach));
		L.x1 = std::min(ax1, (int)std::ceil(L.x + reach) + 1);
		L.y0 = std::max(ay0, (int)std::floor(L.y - reach));
		L.y1 = std::min(ay1, (int)std::ceil(L.y + reach) + 1);
		if (L.x0 < L.x1 && L.y0 < L.y1)
		{
			lit.push_back(L);
		}
	}
	const unsigned char *curve = toneCurve();
	const int w = ax1 - ax0;
	const int bands = (ay1 - ay0 + BAND - 1) / BAND;
	HdWorkers::instance().run(bands, [&](int band)
	{
		// per row: the light falling on the pictures (ambient + lamps) and the halo over them
		std::vector<float> acc((size_t)w * 3), glow((size_t)w * 3);
		const int y0 = ay0 + band * BAND, y1 = std::min(ay1, y0 + BAND);
		for (int y = y0; y < y1; ++y)
		{
			for (int i = 0; i < w; ++i)
			{
				acc[i * 3 + 0] = amb[0];
				acc[i * 3 + 1] = amb[1];
				acc[i * 3 + 2] = amb[2];
			}
			std::fill(glow.begin(), glow.end(), 0.0f);
			const float py = y + 0.5f;
			for (const Lit &L : lit)
			{
				if (y < L.y0 || y >= L.y1)
				{
					continue;
				}
				const float dy = py - L.y, dy2 = dy * dy;
				for (int x = L.x0; x < L.x1; ++x)
				{
					const float dx = x + 0.5f - L.x;
					const float d2 = dx * dx + dy2;
					float *a = &acc[(x - ax0) * 3];
					if (d2 < L.r2)
					{
						// falls off to the edge of its reach, and less where it strikes the floor at a slant
						const float f = 1 - d2 / L.r2;
						const float m = f * f * L.lz / std::sqrt(d2 + L.lz2);
						a[0] += L.add[0] * m;
						a[1] += L.add[1] * m;
						a[2] += L.add[2] * m;
					}
					if (d2 < L.halo2)
					{
						const float h = CORE_GAIN * std::exp(d2 * L.core) + GLOW_GAIN * std::exp(d2 * L.wide);
						float *g = &glow[(x - ax0) * 3];
						g[0] += L.glow[0] * h;
						g[1] += L.glow[1] * h;
						g[2] += L.glow[2] * h;
					}
				}
			}
			Uint32 *row = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch) + ax0;
			for (int i = 0; i < w; ++i)
			{
				const Uint32 px = row[i];
				const float *a = &acc[i * 3];
				const float *g = &glow[i * 3];
				Uint32 out = px & 0xFF000000u;
				for (int c = 0; c < 3; ++c)
				{
					const int shift = 16 - 8 * c;
					const float v = ((px >> shift) & 0xFF) / 255.0f * a[c] + g[c];
					const int at = std::min(LUT_SIZE - 1, (int)(v * LUT_STEPS));
					out |= (Uint32)curve[std::max(0, at)] << shift;
				}
				row[i] = out;
			}
		}
	});
	if (perf)
	{
		static double total = 0;
		static int frames = 0;
		total += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - perfStart).count();
		if (++frames == 60)
		{
			Log(LOG_INFO) << "HD base light: " << total / frames << " ms per frame, " << lit.size() << " lights, "
				<< w << "x" << (ay1 - ay0) << " px, " << HdWorkers::instance().threads() << " threads";
			total = 0;
			frames = 0;
		}
	}
}

namespace
{

/// Smooth value noise 0..1 on a lattice of `step` pack pixels.
float valueNoise(float x, float y, float step, Uint32 seed)
{
	const float fx = x / step, fy = y / step;
	const int ix = (int)std::floor(fx), iy = (int)std::floor(fy);
	const float u = smooth(fx - ix), v = smooth(fy - iy);
	const float a = hash1((Uint32)ix, (Uint32)iy, seed), b = hash1((Uint32)ix + 1, (Uint32)iy, seed);
	const float c = hash1((Uint32)ix, (Uint32)iy + 1, seed), d = hash1((Uint32)ix + 1, (Uint32)iy + 1, seed);
	return (a + (b - a) * u) * (1 - v) + (c + (d - c) * u) * v;
}

}

void drawBuilding(SDL_Surface *world, const SDL_Rect &rect, float progress, float scale, Uint32 seed, Uint32 ms)
{
	if (!world || world->format->BytesPerPixel != 4)
	{
		return;
	}
	const int x0 = std::max(0, (int)rect.x), y0 = std::max(0, (int)rect.y);
	const int x1 = std::min(world->w, rect.x + (int)rect.w), y1 = std::min(world->h, rect.y + (int)rect.h);
	if (x0 >= x1 || y0 >= y1)
	{
		return;
	}
	const float t = (float)(ms % 3600000u) / 1000.0f;
	const float s = std::max(0.05f, scale);
	const float p = std::min(1.0f, std::max(0.0f, progress));
	const float height = rect.h / s;
	// a scanner line runs down the blueprint over and over
	const float scan = std::fmod(t * 40.0f, height + 40.0f) - 20.0f;
	const float weld = 0.75f + 0.25f * std::sin(t * 9.0f);
	const int bands = (y1 - y0 + BAND - 1) / BAND;
	HdWorkers::instance().run(bands, [&](int band)
	{
		const int ya = y0 + band * BAND, yb = std::min(y1, ya + BAND);
		for (int y = ya; y < yb; ++y)
		{
			Uint32 *row = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch);
			const float py = (y + 0.5f - rect.y) / s;
			for (int x = x0; x < x1; ++x)
			{
				const float px = (x + 0.5f - rect.x) / s;
				// where it is built first: blotches of a big and a small noise
				const float n = (valueNoise(px, py, 24, seed) * 0.7f + valueNoise(px, py, 7, seed + 9) * 0.3f);
				const float reveal = std::min(1.0f, std::max(0.0f, (p - n) / 0.05f + 0.5f));
				const Uint32 pxl = row[x];
				float pic[3];
				for (int c = 0; c < 3; ++c)
				{
					pic[c] = ((pxl >> (16 - 8 * c)) & 0xFF) / 255.0f;
				}
				float out[3] = { pic[0], pic[1], pic[2] };
				if (reveal < 1)
				{
					// the blueprint: the room's own shapes in glowing cyan on dark blue, a fine grid, and the
					// yellow beams of the scaffolding
					const float lum = pic[0] * 0.3f + pic[1] * 0.55f + pic[2] * 0.15f;
					const float glow = std::pow(lum, 1.3f);
					float bp[3] = { 0.05f + glow * 0.25f, 0.12f + glow * 0.55f, 0.20f + glow * 0.85f };
					const float gx = std::fabs(std::fmod(px, 16.0f) - 8.0f), gy = std::fabs(std::fmod(py, 16.0f) - 8.0f);
					const float grid = (gx > 7.4f || gy > 7.4f) ? 0.35f : 0.0f;
					const float bx = std::fabs(std::fmod(px + 16.0f, 32.0f) - 16.0f), by = std::fabs(std::fmod(py + 16.0f, 32.0f) - 16.0f);
					const float beam = (bx < 1.3f || by < 1.3f) ? 0.8f : 0.0f;
					const float line = std::max(0.0f, 1 - std::fabs(py - scan) / 3.0f) * 0.5f;
					const float lift = 0.85f + 0.15f * std::sin(t * 2.0f + py * 0.15f);
					for (int c = 0; c < 3; ++c)
					{
						const float cyan[3] = { 0.35f, 0.85f, 1.0f };
						const float yellow[3] = { 0.75f, 0.62f, 0.25f };
						float v = bp[c] * lift + cyan[c] * (grid * 0.4f + line);
						v = v * (1 - beam) + yellow[c] * beam;
						out[c] = pic[c] * reveal + v * (1 - reveal);
					}
				}
				// the hot edge where the building grows
				const float edge = p < 1 ? std::max(0.0f, 1 - std::fabs(n - p) / 0.03f) * weld : 0.0f;
				const float hot[3] = { 1.0f, 0.55f, 0.15f };
				Uint32 o = pxl & 0xFF000000u;
				for (int c = 0; c < 3; ++c)
				{
					const float v = out[c] + hot[c] * edge * 1.2f;
					o |= (Uint32)std::lround(std::min(1.0f, std::max(0.0f, v)) * 255.0f) << (16 - 8 * c);
				}
				row[x] = o;
			}
		}
	});
}

void drawParticles(SDL_Surface *world, const SDL_Rect &area, const std::vector<PlacedEmit> &emits, float night, Uint32 ms)
{
	if (!world || world->format->BytesPerPixel != 4 || emits.empty())
	{
		return;
	}
	const int ax0 = std::max(0, (int)area.x), ay0 = std::max(0, (int)area.y);
	const int ax1 = std::min(world->w, area.x + (int)area.w), ay1 = std::min(world->h, area.y + (int)area.h);
	if (ax0 >= ax1 || ay0 >= ay1)
	{
		return;
	}
	static const bool perf = std::getenv("OXCE_HD_BASE_PERF") != nullptr;
	const auto perfStart = std::chrono::steady_clock::now();
	const float t = (float)(ms % 3600000u) / 1000.0f;
	// the particles are gathered first and laid down in bands on all cores (a site's dust is ~90k pixels)
	struct Blob { float x, y, r, ring, col[3], a; bool add; };
	std::vector<Blob> blobs;
	auto put = [&](float x, float y, float r, float ring, const float col[3], float a, bool add)
	{
		if (a > 0.004f && r > 0)
		{
			blobs.push_back({ x, y, r, ring, { col[0], col[1], col[2] }, a, add });
		}
	};
	// steam is lit as the room is: grey by day, blue at night (it is laid over after the light)
	float amb[3];
	for (int c = 0; c < 3; ++c)
	{
		amb[c] = (DAY[c] * (1 - night) + NIGHT[c] * night) * 1.1f;
	}
	for (const PlacedEmit &p : emits)
	{
		const Emit &E = p.emit;
		const float s = std::max(0.05f, p.scale);
		const float col[3] = { E.r, E.g, E.b };
		// more particles in a bigger box (pack pixels of a 64x64 box make the preview's count)
		const float size = std::max(0.25f, std::min(2.0f, (E.w / s) * (E.h / s) / (64.0f * 64.0f)));
		auto count = [&](int base) { return std::max(3, (int)std::lround(base * size)); };
		// every particle lives `life` seconds over and over, i at its own offset; k counts its lives
		auto life = [&](int i, int n, float span, float &age, Uint32 &k)
		{
			const float u = t + i * span / n + p.seed % 97 * 0.37f;
			age = std::fmod(u, span);
			k = (Uint32)(u / span);
		};
		switch (E.kind)
		{
		case STEAM:
		{
			const int n = count(26);
			const float tint[3] = { col[0] * amb[0], col[1] * amb[1], col[2] * amb[2] };
			for (int i = 0; i < n; ++i)
			{
				float age;
				Uint32 k;
				life(i, n, 4.5f, age, k);
				const float bx = E.x + hash1(i, k, p.seed) * E.w, by = E.y + hash1(i, k, p.seed + 2) * E.h;
				const float x = bx + (-age * 4 + std::sin(age * 1.3f + i) * 3) * s, y = by - age * 7 * s;
				put(x, y, (8 + 2 * std::min(age, 2.0f)) * s, 0, tint,
					std::sin(age / 4.5f * PI) * 0.22f, false);
			}
			break;
		}
		case BUBBLES:
		{
			const int n = count(22);
			for (int i = 0; i < n; ++i)
			{
				float age;
				Uint32 k;
				life(i, n, 1.6f, age, k);
				const float x = E.x + hash1(i, k, p.seed) * E.w, y = E.y + hash1(i, k, p.seed + 1) * E.h;
				put(x, y, 1.0f * s, (1 + age / 1.6f * 5) * s, col, (1 - age / 1.6f) * 0.6f, true);
			}
			for (int i = 0; i < count(10); ++i)
			{
				float age;
				Uint32 k;
				life(i, count(10), 3.5f, age, k);
				const float x = E.x + hash1(i, k, p.seed + 5) * E.w + std::sin(age + i) * 4 * s;
				const float y = E.y + hash1(i, k, p.seed + 6) * E.h - age * 6 * s;
				const float tint[3] = { col[0] * amb[0], col[1] * amb[1], col[2] * amb[2] };
				put(x, y, 12 * s, 0, tint, std::sin(age / 3.5f * PI) * 0.12f, false);
			}
			break;
		}
		case SPARKS:
		{
			// a welder works in bursts, and only while the workshop works
			if (p.level < 0.5f)
			{
				break;
			}
			const int n = count(18);
			for (int i = 0; i < n; ++i)
			{
				float age;
				Uint32 k;
				life(i, n, 0.7f, age, k);
				if (hash1((Uint32)((t - age) * 9), 77, p.seed) <= 0.55f)
				{
					continue;
				}
				// one welding spot in the box for a while, then another
				const Uint32 spot = (Uint32)(t / 3.0f);
				const float wx = E.x + hash1(spot, 3, p.seed) * E.w, wy = E.y + hash1(spot, 4, p.seed) * E.h;
				const float ang = hash1(i, k, p.seed + 1) * 2 * PI;
				const float sp = (30 + 50 * hash1(i, k, p.seed + 2)) * s;
				const float x = wx + std::cos(ang) * sp * age, y = wy + std::sin(ang) * sp * age + 20 * s * age * age;
				put(x, y, 2 * s, 0, col, (1 - age / 0.7f) * 1.4f * p.level, true);
			}
			break;
		}
		case EMBERS:
		{
			const int n = count(12);
			for (int i = 0; i < n; ++i)
			{
				float age;
				Uint32 k;
				life(i, n, 2.5f, age, k);
				const float x = E.x + hash1(i, k, p.seed) * E.w + std::sin(age * 3 + i) * 3 * s;
				const float y = E.y + hash1(i, k, p.seed + 1) * E.h - age * 14 * s;
				put(x, y, 1.6f * s, 0, col, std::sin(age / 2.5f * PI) * 1.1f, true);
			}
			break;
		}
		case ORBIT:
		{
			const int n = count(16);
			const float cx = E.x + E.w / 2, cy = E.y + E.h / 2;
			for (int i = 0; i < n; ++i)
			{
				float age;
				Uint32 k;
				life(i, n, 5.0f, age, k);
				const float ang = hash1(i, k, p.seed) * 2 * PI + age * 0.6f;
				const float rad = (0.25f + 0.45f * hash1(i, k, p.seed + 3)) * E.w / 2 * (1 - age / 5.0f * 0.5f);
				put(cx + std::cos(ang) * rad, cy + std::sin(ang) * rad, 2 * s, 0, col,
					std::sin(age / 5.0f * PI) * 1.2f, true);
			}
			break;
		}
		}
	}
	// a band draws the blobs that reach into it, in the same order as every other band (as blob's reach)
	const int bands = (ay1 - ay0 + BAND - 1) / BAND;
	HdWorkers::instance().run(bands, [&](int band)
	{
		const int y0 = ay0 + band * BAND, y1 = std::min(ay1, y0 + BAND);
		for (const Blob &b : blobs)
		{
			const float reach = b.ring + 2.8f * (b.ring > 0 ? 0.7f : 0.6f) * b.r + 1;
			if (b.y + reach >= y0 && b.y - reach < y1)
			{
				blob(world, ax0, y0, ax1, y1, b.x, b.y, b.r, b.ring, b.col, b.a, b.add);
			}
		}
	});
	if (perf)
	{
		static double total = 0;
		static int frames = 0;
		total += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - perfStart).count();
		if (++frames == 60)
		{
			Log(LOG_INFO) << "HD base particles: " << total / frames << " ms per frame, " << emits.size() << " emitters, "
				<< blobs.size() << " particles";
			total = 0;
			frames = 0;
		}
	}
}

}

}
