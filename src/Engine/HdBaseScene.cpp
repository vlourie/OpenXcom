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

}

}
