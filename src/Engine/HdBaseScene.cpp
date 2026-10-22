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
	static const char *names[] = { "steady", "blink", "pulse", "screen", "flicker", "tv", "chase", "weld", "night" };
	for (int i = 0; i < 9; ++i)
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

float hash1(Uint32 a, Uint32 b, Uint32 c);

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
	case TV:
		v = 0.55f + 0.45f * std::fabs(wobble(t * 1.7f, 9.0f + (float)(p.seed % 13)));
		break;
	case CHASE:
	{
		// a lamp of a ring that runs round once a period, a tail of 2.5 lamps behind the bright one
		const int n = std::max(1, L.count);
		const float ph = std::fmod((t / std::max(0.1f, L.period) - L.phase) * n + 1000.0f * n, (float)n);
		v = ph < 2.5f ? std::max(0.12f, 1 - ph / 2.5f) : 0.12f;
		break;
	}
	case WELD:
	{
		// bursts of flashes a few times a second, dark between them
		const Uint32 tick = (Uint32)(t * 9);
		v = hash1(tick, 77, p.seed % 7) > 0.55f ? 1.6f + 0.6f * hash1((Uint32)(t * 30), 3, p.seed % 7) : 0.0f;
		break;
	}
	case DUTY:
		v = night * 0.9f;
		gain = 1.0f;
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
				int count = 0;
				if (words >> count)
				{
					L.count = count;
				}
				out.lights.push_back(L);
			}
		}
		else if (key == "water")
		{
			std::string kind;
			float g[3] = { 1, 1, 1 };
			words >> kind >> g[0] >> g[1] >> g[2];
			if (words && (kind == "blue" || kind == "green"))
			{
				out.water = kind == "blue" ? 1 : 2;
				std::copy(g, g + 3, out.glint);
			}
		}
		else if (key == "spin" || key == "swing")
		{
			Spin S;
			words >> S.x >> S.y >> S.radius;
			if (key == "spin")
			{
				words >> S.rps;
			}
			else
			{
				words >> S.swing >> S.period;
			}
			bool ok = (bool)words;
			if (ok && key == "swing" && !(words >> S.middle))
			{
				S.middle = 0;
			}
			if (ok && S.radius > 0 && (S.rps != 0 || (S.swing != 0 && S.period > 0)))
			{
				out.spins.push_back(S);
			}
		}
		else if (key == "emit")
		{
			static const char *names[] = { "steam", "bubbles", "sparks", "embers", "orbit", "sweep", "ripple", "dust", "flies", "arc", "beam" };
			Emit E;
			std::string kind;
			words >> kind >> E.x >> E.y >> E.w >> E.h >> E.r >> E.g >> E.b;
			for (int i = 0; i < 11; ++i)
			{
				if (words && kind == names[i] && E.w >= 0 && E.h >= 0)
				{
					E.kind = (EmitKind)i;
					out.emits.push_back(E);
				}
			}
		}
		else if (key == "walk")
		{
			int n = 0;
			std::string bits;
			words >> n >> bits;
			if (n > 0 && n <= 32 && (int)bits.size() == n * n)
			{
				out.walkSize = n;
				out.walk.resize(n * n);
				for (int i = 0; i < n * n; ++i)
				{
					out.walk[i] = bits[i] == '1' ? 1 : 0;
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

void draw(SDL_Surface *world, const SDL_Rect &area, const std::vector<Placed> &lights, float night, Uint32 ms,
	const View *view)
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
	const bool relief = view && !view->relief.empty();
	// the water glints by day half as much as at night (base_scene_preview.py render)
	const float glintGain = 3.5f * (0.5f + 0.5f * night);
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
			// the relief of this row (normal and height), where the view covers it
			const bool inView = relief && y >= view->y && y < view->y + view->h;
			const float *rrow = inView ? &view->relief[(size_t)(y - view->y) * view->w * 4] : nullptr;
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
						// falls off to the edge of its reach, and by the angle it strikes the surface at: the floor
						// at a slant, a wall or a cupboard lit on the lamp's side and dark on the other
						const float f = 1 - d2 / L.r2;
						float ndl;
						if (rrow && x >= view->x && x < view->x + view->w)
						{
							const float *q = rrow + (size_t)(x - view->x) * 4;
							const float lz = L.lz - q[3];
							ndl = std::max(0.0f, (-dx * q[0] - dy * q[1] + lz * q[2]) / std::sqrt(d2 + lz * lz + 1e-3f));
						}
						else
						{
							ndl = L.lz / std::sqrt(d2 + L.lz2);
						}
						const float m = f * f * ndl;
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
			if (inView)
			{
				// glints dancing on the water: two crossing waves, only their crests (base_scene_preview.py render)
				const float s = view->scale;
				for (const View::Area &W : view->waters)
				{
					if (y < W.box.y || y >= W.box.y + W.box.h)
					{
						continue;
					}
					const float vy = (y - W.box.y) / s;
					const float *mrow = &view->water[(size_t)(y - view->y) * view->w];
					const int wx0 = std::max(ax0, (int)W.box.x), wx1 = std::min(ax1, W.box.x + (int)W.box.w);
					for (int x = wx0; x < wx1; ++x)
					{
						const float m = mrow[x - view->x];
						if (m <= 0.01f)
						{
							continue;
						}
						const float vx = (x - W.box.x) / s;
						const float g = std::sin(0.21f * vx + 0.05f * vy + 3 * t) * std::sin(0.07f * vx - 0.19f * vy + 2.3f * t) - 0.72f;
						if (g > 0)
						{
							float *o = &glow[(x - ax0) * 3];
							const float k = g * glintGain * m;
							o[0] += W.glint[0] * k;
							o[1] += W.glint[1] * k;
							o[2] += W.glint[2] * k;
						}
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

namespace
{

/// Blurs `v` (w x h) by three box passes along the rows and the columns: close to a gaussian of `sigma`.
void blur(std::vector<float> &v, int w, int h, float sigma)
{
	const int r = std::max(1, (int)std::lround((std::sqrt(4 * sigma * sigma + 1) - 1) / 2));
	const float inv = 1.0f / (2 * r + 1);
	auto line = [r, inv](const float *src, float *dst, int n, int stride)
	{
		auto at = [&](int i) { return src[(size_t)std::min(n - 1, std::max(0, i)) * stride]; };
		float sum = 0;
		for (int i = -r; i <= r; ++i)
		{
			sum += at(i);
		}
		for (int i = 0; i < n; ++i)
		{
			dst[i] = sum * inv;
			sum += at(i + r + 1) - at(i - r);
		}
	};
	for (int pass = 0; pass < 3; ++pass)
	{
		HdWorkers::instance().run(h, [&](int y)
		{
			std::vector<float> out(w);
			line(&v[(size_t)y * w], out.data(), w, 1);
			std::copy(out.begin(), out.end(), v.begin() + (size_t)y * w);
		});
		HdWorkers::instance().run(w, [&](int x)
		{
			std::vector<float> out(h);
			line(&v[x], out.data(), h, w);
			for (int y = 0; y < h; ++y)
			{
				v[(size_t)y * w + x] = out[y];
			}
		});
	}
}

/// How far each pixel of `inside` lies from the nearest pixel out of it (0 outside), in pixels (chamfer).
std::vector<float> distanceInside(const std::vector<unsigned char> &inside, int w, int h)
{
	const float BIG = 1e6f, D = 1.4142f;
	std::vector<float> d((size_t)w * h);
	for (size_t i = 0; i < d.size(); ++i)
	{
		d[i] = inside[i] ? BIG : 0.0f;
	}
	auto at = [&](int x, int y) { return x < 0 || y < 0 || x >= w || y >= h ? 0.0f : d[(size_t)y * w + x]; };
	for (int y = 0; y < h; ++y)
	{
		for (int x = 0; x < w; ++x)
		{
			float &v = d[(size_t)y * w + x];
			if (v > 0)
			{
				v = std::min({ v, at(x - 1, y) + 1, at(x, y - 1) + 1, at(x - 1, y - 1) + D, at(x + 1, y - 1) + D });
			}
		}
	}
	for (int y = h - 1; y >= 0; --y)
	{
		for (int x = w - 1; x >= 0; --x)
		{
			float &v = d[(size_t)y * w + x];
			if (v > 0)
			{
				v = std::min({ v, at(x + 1, y) + 1, at(x, y + 1) + 1, at(x + 1, y + 1) + D, at(x - 1, y + 1) + D });
			}
		}
	}
	return d;
}

/// The colour of `albedo` (w x h) at (x, y) between its pixels, clamped to its edge: r, g, b 0..255.
void sample(const std::vector<Uint32> &albedo, int w, int h, float x, float y, float out[3])
{
	x = std::min((float)w - 1.001f, std::max(0.0f, x));
	y = std::min((float)h - 1.001f, std::max(0.0f, y));
	const int x0 = (int)x, y0 = (int)y;
	const float fx = x - x0, fy = y - y0;
	const Uint32 *p = &albedo[(size_t)y0 * w + x0];
	const Uint32 q[4] = { p[0], p[1], p[w], p[w + 1] };
	const float k[4] = { (1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy };
	for (int c = 0; c < 3; ++c)
	{
		const int shift = 16 - 8 * c;
		out[c] = 0;
		for (int i = 0; i < 4; ++i)
		{
			out[c] += ((q[i] >> shift) & 0xFF) * k[i];
		}
	}
}

/// `frame` at (x, y) between its pixels, transparent outside: r, g, b premultiplied 0..255 and alpha 0..1.
void samplePiece(const HdFrame &frame, float x, float y, float out[4])
{
	out[0] = out[1] = out[2] = out[3] = 0;
	const int x0 = (int)std::floor(x), y0 = (int)std::floor(y);
	const float fx = x - x0, fy = y - y0;
	const float k[4] = { (1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy };
	for (int i = 0; i < 4; ++i)
	{
		const int px = x0 + (i & 1), py = y0 + (i >> 1);
		if (px < 0 || py < 0 || px >= frame.width || py >= frame.height)
		{
			continue;
		}
		const Uint32 q = frame.pixels[(size_t)py * frame.width + px];
		const float a = (q >> 24) / 255.0f * k[i];
		for (int c = 0; c < 3; ++c)
		{
			out[c] += ((q >> (16 - 8 * c)) & 0xFF) * a;
		}
		out[3] += a;
	}
}

/// `px` moved towards `col` (0..255) by `m`, alpha kept.
Uint32 mix(Uint32 px, const float col[3], float m)
{
	Uint32 out = px & 0xFF000000u;
	for (int c = 0; c < 3; ++c)
	{
		const int shift = 16 - 8 * c;
		const float v = ((px >> shift) & 0xFF) * (1 - m) + col[c] * m;
		out |= (Uint32)std::min(255L, std::max(0L, std::lround(v))) << shift;
	}
	return out;
}

}

void bake(View &view, const HdFrame *rock, const std::vector<SDL_Rect> &empty, const std::vector<PlacedWater> &waters)
{
	const int w = view.w, h = view.h;
	const size_t n = (size_t)w * h;
	const float s = view.scale;
	if (w <= 0 || h <= 0 || view.albedo.size() != n)
	{
		return;
	}
	// what stands where: the alpha of the pictures and the passages
	std::vector<float> foot(n);
	for (size_t i = 0; i < n; ++i)
	{
		foot[i] = (view.albedo[i] >> 24) / 255.0f;
	}
	// the rock, a whole-base picture stretched over the view, darkened (base_scene_preview.py rock_image)
	std::vector<float> ground(n * 3);
	const bool picture = rock && !rock->empty();
	for (int y = 0; y < h; ++y)
	{
		for (int x = 0; x < w; ++x)
		{
			float *g = &ground[((size_t)y * w + x) * 3];
			if (picture)
			{
				const Uint32 px = rock->pixels[(size_t)(y * rock->height / h) * rock->width + x * rock->width / w];
				for (int c = 0; c < 3; ++c)
				{
					g[c] = ((px >> (16 - 8 * c)) & 0xFF) / 255.0f * 0.62f;
				}
			}
			else
			{
				g[0] = 0.16f;
				g[1] = 0.15f;
				g[2] = 0.15f;
			}
		}
	}
	// the shadow the facilities cast to the bottom right and the darkening close to their walls
	std::vector<float> shadow(n, 0.0f), close = foot;
	const int sx = (int)std::lround(4 * s), sy = (int)std::lround(5 * s);
	for (int y = sy; y < h; ++y)
	{
		for (int x = sx; x < w; ++x)
		{
			shadow[(size_t)y * w + x] = foot[(size_t)(y - sy) * w + (x - sx)];
		}
	}
	blur(shadow, w, h, 7 * s);
	blur(close, w, h, 12 * s);
	for (size_t i = 0; i < n; ++i)
	{
		const float k = (1 - 0.55f * shadow[i]) * (1 - 0.35f * close[i]);
		for (int c = 0; c < 3; ++c)
		{
			ground[i * 3 + c] *= k;
		}
	}
	// the cells where nothing stands: a faint mark of the grid where one may build
	const int a = (int)std::lround(4 * s), b = (int)std::lround(6 * s);
	for (const SDL_Rect &r : empty)
	{
		for (int y = r.y + a; y < r.y + r.h - a; ++y)
		{
			for (int x = r.x + a; x < r.x + r.w - a; ++x)
			{
				if (x >= 0 && y >= 0 && x < w && y < h && (x < r.x + b || y < r.y + b))
				{
					for (int c = 0; c < 3; ++c)
					{
						ground[((size_t)y * w + x) * 3 + c] *= 1.25f;
					}
				}
			}
		}
	}
	view.ground.width = w;
	view.ground.height = h;
	view.ground.pixels.assign(n, 0u);
	std::vector<float> lum(n);
	for (size_t i = 0; i < n; ++i)
	{
		const Uint32 px = view.albedo[i];
		const float al = foot[i];
		Uint32 g = 0xFF000000u, o = 0xFF000000u;
		float rgb[3];
		for (int c = 0; c < 3; ++c)
		{
			const int shift = 16 - 8 * c;
			const float gc = std::min(1.0f, ground[i * 3 + c]);
			g |= (Uint32)std::lround(gc * 255) << shift;
			rgb[c] = ((px >> shift) & 0xFF) / 255.0f * al + gc * (1 - al);
			o |= (Uint32)std::lround(std::min(1.0f, rgb[c]) * 255) << shift;
		}
		view.ground.pixels[i] = g;
		view.albedo[i] = o;
		lum[i] = rgb[0] * 0.3f + rgb[1] * 0.55f + rgb[2] * 0.15f;
	}
	view.ground.buildSpans();
	// the relief: light is high, the rim of a facility higher, the rock low; then its slopes
	std::vector<unsigned char> inside(n);
	for (size_t i = 0; i < n; ++i)
	{
		inside[i] = foot[i] > 0.5f;
	}
	const std::vector<float> dist = distanceInside(inside, w, h);
	std::vector<float> fine = lum, coarse = lum;
	blur(fine, w, h, 1.4f * s);
	blur(coarse, w, h, 2.0f * s);
	std::vector<float> height(n);
	for (size_t i = 0; i < n; ++i)
	{
		const float rim = inside[i] ? std::min(1.0f, std::max(0.0f, 1 - dist[i] / (16 * s))) : 0.0f;
		const float v = inside[i] ? fine[i] * 0.45f + rim * 0.55f : 0.08f + coarse[i] * 0.25f;
		height[i] = v * 14 * s;
	}
	std::vector<float> slope = height;
	blur(slope, w, h, 1.0f * s);
	view.relief.assign(n * 4, 0.0f);
	for (int y = 0; y < h; ++y)
	{
		for (int x = 0; x < w; ++x)
		{
			const size_t i = (size_t)y * w + x;
			const float gx = (slope[(size_t)y * w + std::min(w - 1, x + 1)] - slope[(size_t)y * w + std::max(0, x - 1)]) / 2;
			const float gy = (slope[(size_t)std::min(h - 1, y + 1) * w + x] - slope[(size_t)std::max(0, y - 1) * w + x]) / 2;
			const float len = std::sqrt(gx * gx + gy * gy + 1);
			view.relief[i * 4 + 0] = -gx / len;
			view.relief[i * 4 + 1] = -gy / len;
			view.relief[i * 4 + 2] = 1 / len;
			view.relief[i * 4 + 3] = height[i];
		}
	}
	// the water: the blue (or green) of a picture well inside its walls, in pools of some size
	view.water.assign(n, 0.0f);
	view.waters.clear();
	for (const PlacedWater &W : waters)
	{
		const int x0 = std::max(0, W.box.x - view.x), y0 = std::max(0, W.box.y - view.y);
		const int x1 = std::min(w, W.box.x - view.x + (int)W.box.w), y1 = std::min(h, W.box.y - view.y + (int)W.box.h);
		const int bw = x1 - x0, bh = y1 - y0;
		if (bw <= 0 || bh <= 0)
		{
			continue;
		}
		std::vector<unsigned char> m((size_t)bw * bh);
		for (int y = 0; y < bh; ++y)
		{
			for (int x = 0; x < bw; ++x)
			{
				const size_t i = (size_t)(y + y0) * w + x + x0;
				const Uint32 px = view.albedo[i];
				const float r = ((px >> 16) & 0xFF) / 255.0f, g = ((px >> 8) & 0xFF) / 255.0f, bl = (px & 0xFF) / 255.0f;
				const bool hue = W.kind == 1 ? bl > r + 0.12f && bl > g * 0.95f : g > r + 0.1f && g > bl + 0.12f;
				m[(size_t)y * bw + x] = hue && dist[i] > 14 * s;
			}
		}
		// pools of 200 pack pixels and more; a glint of colour elsewhere is not water
		const size_t least = (size_t)(200 * s * s);
		std::vector<int> label(m.size(), 0);
		std::vector<int> stack;
		std::vector<float> mask(m.size(), 0.0f);
		std::vector<std::vector<int>> pools;
		int next = 0;
		for (size_t start = 0; start < m.size(); ++start)
		{
			if (!m[start] || label[start])
			{
				continue;
			}
			std::vector<int> pool;
			label[start] = ++next;
			stack.push_back((int)start);
			while (!stack.empty())
			{
				const int i = stack.back();
				stack.pop_back();
				pool.push_back(i);
				const int x = i % bw, y = i / bw;
				const int nb[4][2] = { { x - 1, y }, { x + 1, y }, { x, y - 1 }, { x, y + 1 } };
				for (const auto &q : nb)
				{
					if (q[0] >= 0 && q[1] >= 0 && q[0] < bw && q[1] < bh)
					{
						const int j = q[1] * bw + q[0];
						if (m[j] && !label[j])
						{
							label[j] = next;
							stack.push_back(j);
						}
					}
				}
			}
			pools.push_back(std::move(pool));
		}
		// ... and a quarter of the biggest at least: a blue rug by the pool is not water (the vats are alike)
		size_t biggest = 0;
		for (const std::vector<int> &pool : pools)
		{
			biggest = std::max(biggest, pool.size());
		}
		for (const std::vector<int> &pool : pools)
		{
			if (pool.size() >= least && pool.size() * 4 >= biggest)
			{
				for (int i : pool)
				{
					mask[i] = 1.0f;
				}
			}
		}
		blur(mask, bw, bh, 1.5f * s);
		bool any = false;
		for (int y = 0; y < bh; ++y)
		{
			for (int x = 0; x < bw; ++x)
			{
				const float v = mask[(size_t)y * bw + x];
				float &o = view.water[(size_t)(y + y0) * w + x + x0];
				o = std::max(o, v);
				any = any || v > 0.01f;
			}
		}
		if (any)
		{
			View::Area A;
			A.box = W.box;
			std::copy(W.glint, W.glint + 3, A.glint);
			view.waters.push_back(A);
		}
	}
}

void drawMotion(SDL_Surface *world, const View &view, Uint32 ms)
{
	if (!world || world->format->BytesPerPixel != 4 || view.albedo.empty())
	{
		return;
	}
	const float t = (float)(ms % 3600000u) / 1000.0f;
	const float s = view.scale;
	auto inWorld = [&](int x, int y) { return x >= 0 && y >= 0 && x < world->w && y < world->h; };
	// the water: the picture under it shifted by two slow waves (base_scene_preview.py render)
	for (const View::Area &W : view.waters)
	{
		const int x0 = std::max((int)W.box.x, view.x), y0 = std::max((int)W.box.y, view.y);
		const int x1 = std::min(W.box.x + (int)W.box.w, view.x + view.w), y1 = std::min(W.box.y + (int)W.box.h, view.y + view.h);
		if (x0 >= x1 || y0 >= y1)
		{
			continue;
		}
		HdWorkers::instance().run(y1 - y0, [&](int row)
		{
			const int y = y0 + row;
			const float vy = (y - W.box.y) / s;
			Uint32 *line = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch);
			for (int x = x0; x < x1; ++x)
			{
				const float m = view.water[(size_t)(y - view.y) * view.w + (x - view.x)];
				if (m <= 0.01f || !inWorld(x, y))
				{
					continue;
				}
				const float vx = (x - W.box.x) / s;
				const float dx = 1.8f * std::sin(0.09f * vx + 0.13f * vy + 2.3f * t) + 1.1f * std::sin(0.17f * vy - 0.05f * vx + 3.4f * t);
				const float dy = 1.8f * std::sin(0.11f * vx - 0.08f * vy + 2.0f * t) + 1.1f * std::sin(0.15f * vx + 0.12f * vy - 2.9f * t);
				float col[3];
				sample(view.albedo, view.w, view.h, x - view.x + dx * s, y - view.y + dy * s, col);
				line[x] = mix(line[x], col, m);
			}
		});
	}
	// the spins: a radar dish turning, a turret looking over its sector
	for (const PlacedSpin &P : view.spins)
	{
		const Spin &S = P.spin;
		const float deg = S.rps != 0 ? t * S.rps * 360 + P.phase * 360 : S.middle + S.swing * std::sin(t / S.period * 2 * PI + P.phase * 2 * PI);
		const float ang = deg * PI / 180, ca = std::cos(ang), sa = std::sin(ang);
		const int r = (int)std::ceil(S.radius);
		const int cx = (int)std::lround(S.x), cy = (int)std::lround(S.y);
		for (int y = cy - r; y < cy + r; ++y)
		{
			if (y < view.y || y >= view.y + view.h || y < 0 || y >= world->h)
			{
				continue;
			}
			Uint32 *line = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch);
			for (int x = cx - r; x < cx + r; ++x)
			{
				if (x < view.x || x >= view.x + view.w || !inWorld(x, y))
				{
					continue;
				}
				const float dx = x + 0.5f - S.x, dy = y + 0.5f - S.y;
				if (!P.piece.empty())
				{
					// the piece alone over the picture without it (the albedo holds that one)
					if (dx * dx + dy * dy > S.radius * S.radius)
					{
						continue;
					}
					float col[3], pc[4];
					const Uint32 under = view.albedo[(size_t)(y - view.y) * view.w + (x - view.x)];
					samplePiece(P.piece, S.x + ca * dx + sa * dy - 0.5f - P.px, S.y - sa * dx + ca * dy - 0.5f - P.py, pc);
					for (int c = 0; c < 3; ++c)
					{
						col[c] = ((under >> (16 - 8 * c)) & 0xFF) * (1 - pc[3]) + pc[c];
					}
					line[x] = mix(line[x], col, 1);
					continue;
				}
				// a soft edge 3 pack pixels wide, so the turning piece does not show a seam
				const float m = std::min(1.0f, std::max(0.0f, (S.radius - std::sqrt(dx * dx + dy * dy)) / (3 * s)));
				if (m <= 0)
				{
					continue;
				}
				float col[3];
				sample(view.albedo, view.w, view.h, S.x + ca * dx + sa * dy - 0.5f - view.x, S.y - sa * dx + ca * dy - 0.5f - view.y, col);
				line[x] = mix(line[x], col, m);
			}
		}
	}
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
		case SWEEP:
		{
			// a beam from the box's middle to its edge turning once in 6..9 s, a fading trail behind it;
			// a turret's (gate none) and a radar's alike, dimmer where the facility idles
			const float cx = E.x + E.w / 2, cy = E.y + E.h / 2, R = std::min(E.w, E.h) / 2;
			const float turn = 2 * PI / (6.0f + 3.0f * hash1(1, 2, p.seed));
			const float head = t * turn + hash1(3, 4, p.seed) * 2 * PI;
			const int steps = std::max(4, (int)(R / (5 * s)));
			for (int j = 0; j < 6; ++j)
			{
				const float ang = head - j * 0.07f, ca = std::cos(ang), sa = std::sin(ang);
				for (int i = 1; i <= steps; ++i)
				{
					const float d = R * i / steps;
					put(cx + ca * d, cy + sa * d, (2.2f + 1.6f * i / steps) * s, 0, col,
						0.32f * (1 - j / 6.0f) * (1 - 0.5f * i / steps) * std::max(0.3f, p.level), true);
				}
			}
			break;
		}
		case RIPPLE:
		{
			// slow rings spreading on water, a few at a time
			const int n = count(5);
			for (int i = 0; i < n; ++i)
			{
				float age;
				Uint32 k;
				life(i, n, 3.2f, age, k);
				const float x = E.x + hash1(i, k, p.seed) * E.w, y = E.y + hash1(i, k, p.seed + 1) * E.h;
				put(x, y, 1.4f * s, (2 + age / 3.2f * 16) * s, col, (1 - age / 3.2f) * 0.35f, true);
			}
			break;
		}
		case DUST:
		{
			// motes drifting slowly through the light of the room
			const int n = count(14);
			for (int i = 0; i < n; ++i)
			{
				float age;
				Uint32 k;
				life(i, n, 7.0f, age, k);
				const float x = E.x + hash1(i, k, p.seed) * E.w + (age * 2.5f + std::sin(age * 0.9f + i) * 4) * s;
				const float y = E.y + hash1(i, k, p.seed + 1) * E.h + std::sin(age * 0.6f + i * 1.7f) * 3 * s;
				put(x, y, 1.3f * s, 0, col, std::sin(age / 7.0f * PI) * 0.45f * (1 - 0.5f * night), true);
			}
			break;
		}
		case FLIES:
		{
			// dark specks (or bees, by the colour) buzzing about a few spots of the box
			const int n = count(12);
			for (int i = 0; i < n; ++i)
			{
				float age;
				Uint32 k;
				life(i, n, 6.0f, age, k);
				const float hx = E.x + hash1(i % 3, k, p.seed) * E.w, hy = E.y + hash1(i % 3, k, p.seed + 1) * E.h;
				const float w1 = 5 + 3 * hash1(i, 9, p.seed), w2 = 7 + 4 * hash1(i, 10, p.seed);
				const float x = hx + (std::sin(age * w1 + i) * 9 + std::sin(age * 1.3f + i * 2.1f) * 6) * s;
				const float y = hy + (std::cos(age * w2 + i * 0.7f) * 7 + std::sin(age * 0.9f + i) * 5) * s;
				put(x, y, 1.1f * s, 0, col, std::min(1.0f, std::sin(age / 6.0f * PI) * 3) * 0.85f, false);
			}
			break;
		}
		case ARC:
		{
			// a lightning between two poles (transformers) every few seconds: a few flickers of a jagged
			// path, its shape new every 90 ms, a bright core in a coloured glow and a flash about it
			const float period = 3.0f + 2.5f * hash1(5, 6, p.seed);
			const float u = t + hash1(7, 8, p.seed) * period;
			const Uint32 strike = (Uint32)(u / period);
			const float at = std::fmod(u, period), lasts = 0.5f;
			if (at >= lasts || hash1(strike, (Uint32)(at / 0.06f), p.seed + 9) < 0.25f)
			{
				break;
			}
			const float fade = std::sqrt(1 - at / lasts) * std::max(0.4f, p.level);
			const Uint32 shape = strike * 16 + (Uint32)(at / 0.09f);
			const float len = std::sqrt(E.w * E.w + E.h * E.h);
			if (len < 1)
			{
				break;
			}
			const float nx = -E.h / len, ny = E.w / len;
			const float white[3] = { 0.6f + 0.4f * col[0], 0.6f + 0.4f * col[1], 0.6f + 0.4f * col[2] };
			const int knots = 14;
			for (int bolt = 0; bolt < 2; ++bolt)
			{
				// the knots of the path, off the straight line by up to a ninth of its length, none at the poles
				float off[knots + 1];
				for (int j = 0; j <= knots; ++j)
				{
					const float env = std::sin(PI * j / knots);
					off[j] = (hash1(j, shape, p.seed + 11 + bolt * 5) - 0.5f) * 2 * len * (bolt ? 0.16f : 0.11f) * env;
				}
				const int steps = std::max(knots * 2, (int)(len / (1.5f * s)));
				for (int i = 0; i <= steps; ++i)
				{
					const float v = (float)i / steps * knots;
					const int j = std::min(knots - 1, (int)v);
					const float d = off[j] + (off[j + 1] - off[j]) * (v - j);
					const float x = E.x + E.w * i / steps + nx * d, y = E.y + E.h * i / steps + ny * d;
					const float a = fade * (bolt ? 0.5f : 1.0f);
					put(x, y, (bolt ? 2.2f : 3.2f) * s, 0, col, 0.35f * a, true);
					put(x, y, (bolt ? 0.7f : 1.0f) * s, 0, white, 1.2f * a, true);
				}
			}
			// the flash: the poles glow and the air about the arc lights up
			put(E.x, E.y, 7 * s, 0, col, 0.5f * fade, true);
			put(E.x + E.w, E.y + E.h, 7 * s, 0, col, 0.5f * fade, true);
			put(E.x + E.w / 2, E.y + E.h / 2, len * 0.35f, 0, col, 0.10f * fade, true);
			break;
		}
		case BEAM:
		{
			// a plasma gun (Vitali 22.10, art/base_living/turret/plasma_beam_preview.py): violet sparks gather into
			// the orb at the box's corner (x + w, y + h) and it flares, a beam of the colour goes from it to the
			// opposite corner (x, y), then the orb cools till the next shot
			const float period = 5.0f, charge = 1.6f, fire = 0.45f;
			const float u = std::fmod(t + hash1(3, 4, p.seed) * period, period);
			const float cx = E.x + E.w, cy = E.y + E.h, orb = 8 * s;
			static const float violet[3] = { 0.65f, 0.35f, 1.0f }, white[3] = { 0.85f, 0.95f, 1.0f };
			if (u < charge)
			{
				const float k = u / charge;
				for (int i = 0; i < 28; ++i)
				{
					const float ph = std::fmod(i * 0.618f + u * 0.9f, 1.0f);
					const float ang = i * 2.399f + ph * 2.5f, r = orb * 1.9f * (1 - ph);
					put(cx + r * std::cos(ang), cy + r * std::sin(ang), 0.9f * s, 0, violet, 1.2f * k * (0.3f + ph), true);
				}
				put(cx, cy, orb * (0.9f - 0.6f * k) / 0.6f, 0, violet, 0.3f + 1.1f * k * k, true);
				put(cx, cy, (1.7f + 1.7f * k) * s, 0, white, 1.25f * k * k, true);
			}
			else if (u < charge + fire)
			{
				const float k = (u - charge) / fire;
				const float fade = std::pow(1 - k, 0.6f) * (0.85f + 0.15f * hash1((Uint32)(t * 20), 5, p.seed));
				const float len = std::sqrt(E.w * E.w + E.h * E.h), step = 1.5f * s;
				const int n = std::max(2, (int)(len / step));
				// blobs every `step` along the line sum up to the preview's beam: a glow 3.25 and a core 1 pack px wide
				for (int i = 0; i <= n; ++i)
				{
					const float v = (float)i / n, along = 1 - 0.4f * v;
					put(cx - E.w * v, cy - E.h * v, 5.4f * s, 0, col, 0.17f * fade * along, true);
					put(cx - E.w * v, cy - E.h * v, 1.7f * s, 0, white, 0.7f * fade * along, true);
				}
				put(cx, cy, 20 * s, 0, col, 0.8f * fade, true);
				put(cx, cy, 5 * s, 0, white, 1.5f * fade, true);
			}
			else
			{
				const float k = (u - charge - fire) / (period - charge - fire);
				put(cx, cy, orb * 0.8f / 0.6f, 0, violet, 0.15f * (1 - k), true);
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
