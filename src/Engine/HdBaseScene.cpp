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
#include "HdGpuWorld.h"
#include "HdWorkers.h"
#include "Logger.h"

namespace OpenXcom
{

namespace HdBaseScene
{

namespace
{

const float PI = 3.14159265f;
const float BELT_SPEED = 16.0f;      // pack pixels a second a belt carries its parts (ticket 336)
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
	static const char *names[] = { "steady", "blink", "pulse", "screen", "flicker", "tv", "chase", "weld", "night", "burst", "marquee", "swell" };
	for (int i = 0; i < 12; ++i)
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

/// How bright a light is now (with the night's gain), as in base_scene_preview.py. `act` is how much its
/// facility moves: a lamp that blinks, pulses or runs does so by `act`, and at 0 stands at the middle of it.
float strength(const Placed &p, float t, float night, float act)
{
	const Light &L = p.light;
	float gain = 0.28f + 0.72f * night;
	float v = 1.0f;
	// where a lamp stands while its facility rests (its turn is over): the middle of what it does, steady
	float rest = -1.0f;
	switch (L.kind)
	{
	case BLINK:
	{
		// a status lamp (ticket 336, "the light blinks too much"): burns steady with a slow breath, and now and
		// then, every 7-13 s of its own, gives a quick double wink
		const float breath = 0.72f + 0.10f * std::sin((t / (2.5f * std::max(0.1f, L.period)) + L.phase) * 2 * PI);
		const float every = 7.0f + 6.0f * hash1(p.seed, 21, 22);
		const float u = std::fmod(t + L.phase * every + hash1(p.seed, 23, 24) * every, every);
		const float dip = u < 0.9f ? 0.5f - 0.5f * std::cos(u / 0.45f * 2 * PI) : 0.0f;
		v = breath * (1 - 0.8f * dip);
		rest = 0.72f;
		break;
	}
	case PULSE:
		v = 0.6f + 0.4f * std::sin((t / std::max(0.1f, L.period) + L.phase) * 2 * PI);
		rest = 0.6f;
		break;
	case FLICKER:
		// a flame breathes: only the slow sines of the wobble, a narrower swing
		v = 0.86f + 0.14f * wobble(t * 0.55f, (float)(p.seed % 97));
		rest = 0.86f;
		break;
	case SCREEN:
	case TV:
	{
		// a screen whose picture changes: every few seconds a new slide (another brightness) through a short dim,
		// a slow breath on top; a TV changes oftener and deeper
		const bool tv = L.kind == TV;
		const float seg = tv ? 3.0f + 3.0f * hash1(p.seed, 31, 32) : 10.0f + 8.0f * hash1(p.seed, 31, 32);
		const float x = t / seg + hash1(p.seed, 33, 34) * 10.0f;
		const Uint32 n = (Uint32)x;
		const float f = x - (float)n;
		const float lo = tv ? 0.45f : 0.74f;
		const float cur = lo + (1.0f - lo) * hash1(n, 35, p.seed % 53);
		const float prev = lo + (1.0f - lo) * hash1(n - 1, 35, p.seed % 53);
		const float since = f * seg;      // seconds into this slide
		const float k = std::min(1.0f, since / 0.35f);
		float lit = prev + (cur - prev) * smooth(k);
		lit *= 1 - 0.35f * std::sin(k * PI);
		v = lit * (0.94f + 0.06f * std::sin(t * 0.9f + (float)(p.seed % 13)));
		rest = tv ? 0.72f : 0.88f;
		if (!tv)
		{
			gain = 0.4f + 0.5f * night;
		}
		break;
	}
	case CHASE:
	case MARQUEE:
	{
		// a ring runs round once a period. A marquee (casino sign, a machine's lights) keeps the quick tail of 2.5
		// lamps and burns by day nearly as at night; the other rings (the hangar's) swell and fade as one broad
		// slow wave instead
		const int n = std::max(1, L.count);
		const float ph = std::fmod((t / std::max(0.1f, L.period) - L.phase) * n + 1000.0f * n, (float)n);
		if (L.kind == MARQUEE)
		{
			v = ph < 2.5f ? std::max(0.12f, 1 - ph / 2.5f) : 0.12f;
			rest = 0.3f;
			gain = 0.75f + 0.25f * night;
		}
		else
		{
			const float tail = 0.6f * n;
			v = 0.25f + (ph < tail ? 0.75f * smooth(1 - ph / tail) : 0.0f);
			rest = 0.45f;
		}
		break;
	}
	case SWELL:
	{
		// a slow breath of light (the arrows of an empty hangar's pad, ticket 350): from nothing up over 5/7 of the
		// period (5 s at 7), then down over the rest (2 s). The facility's turn does not hold it (rest stays -1): the
		// lamp moves by the display clock all the time, its phase set by the facility's place on the base
		const float per = std::max(0.1f, L.period);
		const float rise = per * 5.0f / 7.0f;
		const float u = std::fmod(t + L.phase * per + 1000.0f * per, per);
		v = 2.0f * (u < rise ? smooth(u / rise) : 1 - smooth((u - rise) / (per - rise)));
		gain = 0.75f + 0.25f * night;
		break;
	}
	case WELD:
	{
		// bursts of flashes a few times a second, dark between them
		const Uint32 tick = (Uint32)(t * 9);
		v = hash1(tick, 77, p.seed % 7) > 0.55f ? 1.6f + 0.6f * hash1((Uint32)(t * 30), 3, p.seed % 7) : 0.0f;
		rest = 0.0f;
		break;
	}
	case DUTY:
		v = night * 0.9f;
		gain = 1.0f;
		break;
	case BURST:
		// only in its facility's fit: the level carries the fit's wave (BaseView::drawHdScene)
		v = 1.6f;
		gain = 0.5f + 0.5f * night;
		break;
	default:
		break;
	}
	if (rest >= 0 && act < 1.0f)
	{
		v = rest + (v - rest) * std::max(0.0f, act);
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

/// The pixel under a blob of weight k: `add` adds light, otherwise the colour is laid over with its alpha
/// (HdGpuWorld's ADD and OVER, the latter with min(1, k)).
inline Uint32 tint(Uint32 px, const float col[3], float k, bool add)
{
	Uint32 out = px & 0xFF000000u;
	for (int c = 0; c < 3; ++c)
	{
		const int shift = 16 - 8 * c;
		const float v = ((px >> shift) & 0xFF) / 255.0f;
		const float o = add ? v + col[c] * k : v + (col[c] - v) * std::min(1.0f, k);
		out |= (Uint32)std::lround(std::min(1.0f, std::max(0.0f, o)) * 255.0f) << shift;
	}
	return out;
}

/// A soft round spot (sigma 0.6 r, as the preview's blobs) or a thin ring of radius `ring`, in the area: its box
/// box[0..3] (x0, y0, x1, y1), then fn(x, y, k) for every pixel it touches. False: nothing to draw.
template <typename F>
bool blobEach(int ax0, int ay0, int ax1, int ay1, float cx, float cy, float r, float ring, float a, int box[4], F fn)
{
	if (a <= 0.004f || r <= 0)
	{
		return false;
	}
	const float sigma = ring > 0 ? 0.7f * r : 0.6f * r;
	const float inv = 1.0f / (2 * sigma * sigma);
	const float reach = ring + 2.8f * sigma;
	const int x0 = std::max(ax0, (int)std::floor(cx - reach)), x1 = std::min(ax1, (int)std::ceil(cx + reach) + 1);
	const int y0 = std::max(ay0, (int)std::floor(cy - reach)), y1 = std::min(ay1, (int)std::ceil(cy + reach) + 1);
	box[0] = x0; box[1] = y0; box[2] = x1; box[3] = y1;
	const float *table = softTable();
	for (int y = y0; y < y1; ++y)
	{
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
			fn(x, y, a * table[(int)q]);
		}
	}
	return x0 < x1 && y0 < y1;
}

/// A rectangle with an edge a pixel soft (a part on a belt, a trolley, a dash of a running line), half sides
/// hx, hy about (cx, cy), in the area: as blobEach.
template <typename F>
bool boxEach(int ax0, int ay0, int ax1, int ay1, float cx, float cy, float hx, float hy, float a, int box[4], F fn)
{
	if (a <= 0.004f || hx <= 0 || hy <= 0)
	{
		return false;
	}
	const int x0 = std::max(ax0, (int)std::floor(cx - hx - 1)), x1 = std::min(ax1, (int)std::ceil(cx + hx + 1));
	const int y0 = std::max(ay0, (int)std::floor(cy - hy - 1)), y1 = std::min(ay1, (int)std::ceil(cy + hy + 1));
	box[0] = x0; box[1] = y0; box[2] = x1; box[3] = y1;
	for (int y = y0; y < y1; ++y)
	{
		const float ky = std::min(1.0f, std::max(0.0f, hy - std::fabs(y + 0.5f - cy) + 0.5f));
		if (ky <= 0)
		{
			continue;
		}
		for (int x = x0; x < x1; ++x)
		{
			const float k = std::min(1.0f, std::max(0.0f, hx - std::fabs(x + 0.5f - cx) + 0.5f)) * ky * a;
			if (k <= 0)
			{
				continue;
			}
			fn(x, y, k);
		}
	}
	return x0 < x1 && y0 < y1;
}

/// blobEach into the world.
void blob(SDL_Surface *world, int ax0, int ay0, int ax1, int ay1, float cx, float cy, float r, float ring,
	const float col[3], float a, bool add)
{
	int box[4];
	blobEach(ax0, ay0, ax1, ay1, cx, cy, r, ring, a, box, [&](int x, int y, float k)
	{
		Uint32 *px = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch) + x;
		*px = tint(*px, col, k, add);
	});
}

/// boxEach into the world.
void boxFill(SDL_Surface *world, int ax0, int ay0, int ax1, int ay1, float cx, float cy, float hx, float hy,
	const float col[3], float a, bool add)
{
	int box[4];
	boxEach(ax0, ay0, ax1, ay1, cx, cy, hx, hy, a, box, [&](int x, int y, float k)
	{
		Uint32 *px = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch) + x;
		*px = tint(*px, col, k, add);
	});
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
				int least = 0;
				if (words >> least && least > 0)
				{
					out.waterLeast = least;
				}
			}
		}
		else if (key == "flow")
		{
			Flow F;
			std::string mode;
			words >> mode >> F.colour[0] >> F.colour[1] >> F.colour[2] >> F.a1 >> F.a2 >> F.core >> F.halo >> F.dark;
			if (words && (mode == "steady" || mode == "fit") && F.a1 > 0 && (mode == "fit" || F.a2 > 0))
			{
				F.mode = mode == "steady" ? Flow::STEADY : Flow::FIT;
				out.flow = F;
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
			static const char *names[] = { "steam", "bubbles", "sparks", "embers", "orbit", "sweep", "ripple", "dust", "flies", "arc", "beam",
				"belt", "beltrev", "roll", "shuttle", "heat", "cart", "ticker" };
			Emit E;
			std::string kind;
			words >> kind >> E.x >> E.y >> E.w >> E.h >> E.r >> E.g >> E.b;
			for (int i = 0; i < 18; ++i)
			{
				if (words && kind == names[i] && E.w >= 0 && E.h >= 0)
				{
					E.kind = (EmitKind)i;
					out.emits.push_back(E);
				}
			}
		}
		else if (key == "cycle")
		{
			float period = 0, length = 0;
			words >> period >> length;
			if (words && period > 0 && length > 0)
			{
				out.cycle = period;
				out.fit = std::min(length, period);
			}
		}
		else if (key == "glow")
		{
			Glow G;
			words >> G.x >> G.y >> G.w >> G.h >> G.hue >> G.tolerance >> G.saturation >> G.peak >> G.pulses >> G.groups;
			if (words && G.w > 0 && G.h > 0 && G.pulses > 0)
			{
				G.groups = std::min(16, std::max(1, G.groups));
				out.glows.push_back(G);
			}
		}
		else if (key == "lid")
		{
			Lid L;
			words >> L.x >> L.y >> L.rx >> L.ry >> L.blinks;
			if (words && L.rx > 0 && L.ry > 0 && L.blinks > 0)
			{
				out.lids.push_back(L);
			}
		}
		else if (key == "sink")
		{
			Sink S;
			words >> S.x >> S.y >> S.w >> S.h >> S.ix >> S.iy >> S.iw >> S.ih >> S.pulses;
			if (words && S.w > 0 && S.h > 0 && S.iw > 0 && S.ih > 0 && S.pulses > 0)
			{
				out.sinks.push_back(S);
			}
		}
		else if (key == "post")
		{
			std::string kind;
			Post P;
			words >> kind >> P.x >> P.y >> P.face >> P.group;
			if (words && P.face >= 0 && P.face < 4 && P.group >= 0 && P.group < 16
				&& (kind == "belt" || kind == "seat" || kind == "dealer"))
			{
				P.kind = kind == "belt" ? Post::BELT : kind == "seat" ? Post::SEAT : Post::DEALER;
				out.posts.push_back(P);
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

bool measuredOff(const char *part)
{
	static const std::string off = std::getenv("OXCE_HD_BASE_OFF") ? std::getenv("OXCE_HD_BASE_OFF") : "";
	return !off.empty() && off.find(part) != std::string::npos;
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

bool moves(const TileScene &scene)
{
	for (const Light &L : scene.lights)
	{
		if (L.kind != STEADY && L.kind != DUTY && L.kind != BURST)
		{
			return true;
		}
	}
	return !scene.emits.empty() || scene.water != 0 || scene.flow.mode == Flow::STEADY || !scene.spins.empty();
}

namespace
{

/// How many facilities of a base move at once.
const int MOVING = 3;
/// Seconds a turn rises and falls over (a short fit - a third of its length).
const float RAMP = 1.3f;

}

void tick(View &view, Uint32 ms)
{
	// a fresh layout, or the base screen left a while ago: deal the first fits over a period from now, the
	// first turns within seconds
	const bool deal = view.fitsAt == 0 || ms - view.fitsAt > 2000;
	const float dt = deal ? 0.0f : std::min(0.25f, (ms - view.fitsAt) / 1000.0f);
	view.fitsAt = ms;
	int running = 0;
	for (Fit &F : view.fits)
	{
		if (deal)
		{
			F.on = false;
			F.next = F.continuous ? ms + 400 + (Uint32)(hash1(F.seed, 1) * 6000)
				: ms + 3000 + (Uint32)(hash1(F.seed, 1) * F.period * 1000);
		}
		if (F.on && F.continuous && !F.wants && (Sint32)(F.end - ms) > (Sint32)(RAMP * 1000))
		{
			F.end = ms + (Uint32)(RAMP * 1000);        // the work is over: the turn falls away now
		}
		if (F.on && (Sint32)(ms - F.end) >= 0)
		{
			F.on = false;
			if (F.continuous)
			{
				// rests 25-45 s, and the facility that has waited longest goes next
				F.next = ms + 25000 + (Uint32)(hash1(F.seed, F.start, 2) * 20000);
			}
			else
			{
				// the next one about a period later, a little more or less, so the facilities do not keep step
				F.next = F.start + (Uint32)(F.period * 1000 * (0.85f + 0.3f * hash1(F.seed, F.start, 2)));
			}
		}
		running += F.on ? 1 : 0;
	}
	// the places go to the due fits first, then to the turns by how long they are overdue
	while (running < MOVING)
	{
		Fit *best = nullptr;
		for (Fit &F : view.fits)
		{
			if (F.on || !F.wants || (Sint32)(ms - F.next) < 0)
			{
				continue;
			}
			if (!best || (!F.continuous && best->continuous) ||
				(F.continuous == best->continuous && (Sint32)(best->next - F.next) > 0))
			{
				best = &F;
			}
		}
		if (!best)
		{
			break;
		}
		best->on = true;
		best->start = ms;
		best->end = ms + (Uint32)(best->length * 1000);
		++running;
	}
	static const char *held = std::getenv("OXCE_HD_BASE_ACT");
	for (Fit &F : view.fits)
	{
		float act = 0;
		if (F.on)
		{
			const float ramp = std::min(RAMP, F.length / 3);
			act = smooth((ms - F.start) / 1000.0f / ramp) * smooth((Sint32)(F.end - ms) / 1000.0f / ramp);
		}
		if (held && *held)
		{
			act = std::atoi(held) != 0 ? 1.0f : 0.0f;
		}
		F.act = act;
		F.turned += act * dt;
	}
}

float actOf(const View &view, int fit)
{
	return fit >= 0 && fit < (int)view.fits.size() ? view.fits[fit].act : 1.0f;
}

float fitTime(const View &view, int fit, Uint32 ms)
{
	if (fit < 0 || fit >= (int)view.fits.size())
	{
		return -1;
	}
	static const char *held = std::getenv("OXCE_HD_BASE_FIT");
	if (held && *held)
	{
		return std::min(view.fits[fit].length, std::max(0.0f, (float)std::atof(held)));
	}
	const Fit &F = view.fits[fit];
	return F.on ? (ms - F.start) / 1000.0f : -1;
}

float fitWave(float t, float length, int pulses)
{
	if (t < 0 || t > length || length <= 0)
	{
		return 0;
	}
	const float s = std::sin(PI * std::max(1, pulses) * t / length);
	return s * s;
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
	// The lamps are linear: a lamp at its resting strength (a steady lamp, a blinking one of a facility that is
	// not moving) goes into a picture of the whole area kept from frame to frame (`cache`, made again only when
	// a resting lamp changes), and what a moving lamp is now over its resting strength is added every frame, so
	// the frame pays for the few lamps that move and not for all of them (ticket 336).
	std::vector<Lit> lit, resting;
	lit.reserve(lights.size());
	static const bool noLight = measuredOff("light"), noFlow = measuredOff("flow");
	const int w = ax1 - ax0;
	const int rows = ay1 - ay0;
	auto makeLit = [&](const Placed &p, float v, Lit &L) -> bool
	{
		const float s = std::max(0.05f, p.scale);
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
		return L.x0 < L.x1 && L.y0 < L.y1;
	};
	for (const Placed &p : lights)
	{
		if (noLight)
		{
			break;
		}
		const float now = strength(p, t, night, p.act);
		// a burst lamp burns only in its facility's fit: nothing at rest; a lamp of the crew moves about
		const float rest = p.light.kind == BURST || p.light.kind == SWELL || p.moving ? 0.0f : strength(p, t, night, 0.0f);
		Lit L;
		if (rest > 0.01f && makeLit(p, rest, L))
		{
			resting.push_back(L);
		}
		if (std::fabs(now - rest) > 0.004f && makeLit(p, now - rest, L))
		{
			lit.push_back(L);
		}
	}
	const unsigned char *curve = toneCurve();
	const int bands = (ay1 - ay0 + BAND - 1) / BAND;
	const bool relief = view && !view->relief.empty();
	// the pipes: where the light runs along them this frame (tools/hdart/base_flow_bake.py emission)
	struct FlowNow
	{
		const PlacedFlow *P;
		float shift, head, fade, act;
	};
	std::vector<FlowNow> flows;
	static const std::vector<PlacedFlow> noFlows;
	for (const PlacedFlow &P : view && !noFlow ? view->flows : noFlows)
	{
		FlowNow N = { &P, 0, 0, 1, 1 };
		if (P.flow.mode == Flow::STEADY)
		{
			// the light runs along the pipes only in the facility's turn; the rest of the time they glow dimly, steady
			N.act = view ? actOf(*view, P.fit) : 1.0f;
			N.shift = P.flow.a1 * t;
		}
		else
		{
			// slugs from the tank in the facility's fit: a1 trains a fit, each fading in and out
			const float ft = P.fit >= 0 ? fitTime(*view, P.fit, ms) : -1;
			if (ft < 0)
			{
				continue;
			}
			const float span = view->fits[P.fit].length / P.flow.a1;
			const float local = std::fmod(ft, span);
			N.fade = std::min(1.0f, std::min(local / 0.6f, std::max(0.0f, (span - local) / 0.8f)));
			N.head = local / (span * 0.75f) * 1.35f - 0.05f;
		}
		flows.push_back(N);
	}
	// the light of one lamp at the pixel x of a row dy below it: m of its colour into the light falling on the
	// pictures (bit 1 of the answer: in its reach), h into its halo (bit 2)
	auto lampAt = [&](const Lit &L, int x, float dy, float dy2, const float *rrow, float &m, float &h) -> int
	{
		const float dx = x + 0.5f - L.x;
		const float d2 = dx * dx + dy2;
		int on = 0;
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
			m = f * f * ndl;
			on |= 1;
		}
		if (d2 < L.halo2)
		{
			h = CORE_GAIN * std::exp(d2 * L.core) + GLOW_GAIN * std::exp(d2 * L.wide);
			on |= 2;
		}
		return on;
	};
	// the light of one lamp on one row: into `acc` (the light falling on the pictures) and `glow` (its halo), the
	// row's first pixel at the area's left edge
	auto lampRow = [&](const Lit &L, int y, float *acc, float *glow, const float *rrow)
	{
		if (y < L.y0 || y >= L.y1)
		{
			return;
		}
		const float py = y + 0.5f;
		const float dy = py - L.y, dy2 = dy * dy;
		for (int x = L.x0; x < L.x1; ++x)
		{
			float m, h;
			const int on = lampAt(L, x, dy, dy2, rrow, m, h);
			if (on & 1)
			{
				float *a = &acc[(x - ax0) * 3];
				a[0] += L.add[0] * m;
				a[1] += L.add[1] * m;
				a[2] += L.add[2] * m;
			}
			if (on & 2)
			{
				float *g = &glow[(x - ax0) * 3];
				g[0] += L.glow[0] * h;
				g[1] += L.glow[1] * h;
				g[2] += L.glow[2] * h;
			}
		}
	};
	// the light running along a pipe at a pixel of its map `q`: k of its colour and `white` into the halo, the
	// light falling on the pipe dimmed by `darken`; false - none there
	auto flowAt = [&](const FlowNow &N, Uint32 q, float &k, float &white, float &darken) -> bool
	{
		const Flow &F = N.P->flow;
		const float core = ((q >> 8) & 0xFF) / 255.0f, about = (q & 0xFF) / 255.0f;
		if (core + about < 0.004f)
		{
			return false;
		}
		const float u = ((q >> 16) & 0xFF) / 255.0f;
		float e;
		white = 0;
		if (F.mode == Flow::STEADY)
		{
			if (N.act < 0.01f)
			{
				e = 0.18f;
			}
			else
			{
				const float p = 0.5f + 0.5f * std::cos(2 * PI * (u - N.shift) / F.a2);
				const float p2 = p * p;
				e = 0.18f + 0.82f * p2 * p2 * p2 * N.act;
			}
			darken = F.dark * core;
		}
		else
		{
			float slug = 0;
			for (int i = 0; i < 3; ++i)
			{
				const float d = (u - (N.head - 0.11f * i)) / 0.045f;
				slug += std::exp(-d * d) * (1 - 0.25f * i);
			}
			const float behind = N.head - u;
			e = (slug + (behind > 0 ? std::exp(-behind / 0.35f) * 0.35f : 0.0f)) * N.fade;
			const float hot = core * slug * N.fade;
			white = hot * hot * 0.6f;
			darken = F.dark * core * N.fade;
		}
		k = e * (core * F.core + about * F.halo);
		return true;
	};
	auto reliefRow = [&](int y) -> const float *
	{
		// the relief of this row (normal and height), where the view covers it
		const bool inView = relief && y >= view->y && y < view->y + view->h;
		return inView ? &view->relief[(size_t)(y - view->y) * view->w * 4] : nullptr;
	};
	// the picture of the resting lamps, made again only when one of them (or the ambient light, the area, the
	// relief) changes
	struct Held
	{
		Uint64 key = 0;
		int w = 0, h = 0;
		std::vector<float> acc, glow;
	};
	static Held held;
	static const bool noCache = measuredOff("cache");     // a test: the same frame the slow way
	const bool cached = !noCache && !resting.empty() && (size_t)w * rows <= 4u * 1024 * 1024;
	bool rebuilt = false;
	if (cached)
	{
		Uint64 key = 1469598103934665603ull;
		auto mix = [&key](const void *data, size_t bytes)
		{
			const unsigned char *b = (const unsigned char*)data;
			for (size_t i = 0; i < bytes; ++i)
			{
				key = (key ^ b[i]) * 1099511628211ull;
			}
		};
		for (const Lit &L : resting)
		{
			mix(&L, sizeof(Lit));
		}
		const int shape[6] = { w, rows, ax0, ay0, view ? view->w : 0, view ? view->x : 0 };
		mix(amb, sizeof(amb));
		mix(shape, sizeof(shape));
		const Uint32 serial = view ? view->serial : 0;
		mix(&serial, sizeof(serial));
		if (key != held.key || held.w != w || held.h != rows)
		{
			held.acc.assign((size_t)w * rows * 3, 0.0f);
			held.glow.assign((size_t)w * rows * 3, 0.0f);
			HdWorkers::instance().run(bands, [&](int band)
			{
				const int y0 = ay0 + band * BAND, y1 = std::min(ay1, y0 + BAND);
				for (int y = y0; y < y1; ++y)
				{
					float *acc = &held.acc[(size_t)(y - ay0) * w * 3], *glow = &held.glow[(size_t)(y - ay0) * w * 3];
					for (int i = 0; i < w; ++i)
					{
						acc[i * 3 + 0] = amb[0];
						acc[i * 3 + 1] = amb[1];
						acc[i * 3 + 2] = amb[2];
					}
					const float *rrow = reliefRow(y);
					for (const Lit &L : resting)
					{
						lampRow(L, y, acc, glow, rrow);
					}
				}
			});
			held.key = key;
			held.w = w;
			held.h = rows;
			rebuilt = true;
		}
	}
	else
	{
		lit.insert(lit.begin(), resting.begin(), resting.end());
	}
	// a frame of the video card: the resting picture is kept on the card, the moving lamps and the pipes go with
	// what they add per pixel (worked out here on all cores); not kept - the processor draws it
	bool handed = false;
	HdGpuWorld &gw = HdGpuWorld::instance();
	if (gw.on(world) && !cached)
	{
		gw.cpu("the light of the base");
	}
	else if (gw.on(world))
	{
		std::vector<HdGpuWorld::Lamp> lamps(lit.size());
		std::vector<HdGpuWorld::Pipe> pipes(flows.size());
		HdWorkers::instance().run((int)(lit.size() + flows.size()), [&](int i)
		{
			if (i < (int)lit.size())
			{
				const Lit &L = lit[i];
				HdGpuWorld::Lamp &out = lamps[i];
				out.x0 = L.x0; out.y0 = L.y0; out.x1 = L.x1; out.y1 = L.y1;
				std::copy(L.add, L.add + 3, out.add);
				std::copy(L.glow, L.glow + 3, out.glow);
				const int bw = L.x1 - L.x0;
				out.mh.assign((size_t)bw * (L.y1 - L.y0) * 2, 0.0f);
				for (int y = L.y0; y < L.y1; ++y)
				{
					const float dy = y + 0.5f - L.y, dy2 = dy * dy;
					const float *rrow = reliefRow(y);
					float *o = &out.mh[(size_t)(y - L.y0) * bw * 2];
					for (int x = L.x0; x < L.x1; ++x, o += 2)
					{
						float m, h;
						const int on = lampAt(L, x, dy, dy2, rrow, m, h);
						o[0] = on & 1 ? m : 0.0f;
						o[1] = on & 2 ? h : 0.0f;
					}
				}
				return;
			}
			const FlowNow &N = flows[i - lit.size()];
			const PlacedFlow &P = *N.P;
			HdGpuWorld::Pipe &out = pipes[i - lit.size()];
			std::copy(P.flow.colour, P.flow.colour + 3, out.colour);
			out.x0 = std::max(ax0, (int)P.box.x);
			out.x1 = std::min(ax1, P.box.x + (int)P.box.w);
			out.y0 = std::max(ay0, (int)P.box.y);
			out.y1 = std::min(ay1, P.box.y + (int)P.box.h);
			if (out.x0 >= out.x1 || out.y0 >= out.y1)
			{
				return;
			}
			const int bw = out.x1 - out.x0;
			out.kwd.assign((size_t)bw * (out.y1 - out.y0) * 3, 0.0f);
			for (int y = out.y0; y < out.y1; ++y)
			{
				const Uint32 *mrow = &P.map[(size_t)(y - P.box.y) * P.box.w];
				float *o = &out.kwd[(size_t)(y - out.y0) * bw * 3];
				for (int x = out.x0; x < out.x1; ++x, o += 3)
				{
					if (!flowAt(N, mrow[x - P.box.x], o[0], o[1], o[2]))
					{
						o[0] = o[1] = o[2] = 0.0f;
					}
				}
			}
		});
		// a pipe out of the area adds nothing
		pipes.erase(std::remove_if(pipes.begin(), pipes.end(), [](const HdGpuWorld::Pipe &P) { return P.kwd.empty(); }), pipes.end());
		handed = gw.light(held.key, held.acc, held.glow, ax0, ay0, w, rows, lamps, pipes, curve, LUT_SIZE, LUT_STEPS) && !gw.verifying();
	}
	HdWorkers::instance().run(handed ? 0 : bands, [&](int band)
	{
		// per row: the light falling on the pictures (ambient + lamps) and the halo over them
		std::vector<float> acc((size_t)w * 3), glow((size_t)w * 3);
		const int y0 = ay0 + band * BAND, y1 = std::min(ay1, y0 + BAND);
		for (int y = y0; y < y1; ++y)
		{
			if (cached)
			{
				std::copy_n(&held.acc[(size_t)(y - ay0) * w * 3], (size_t)w * 3, acc.begin());
				std::copy_n(&held.glow[(size_t)(y - ay0) * w * 3], (size_t)w * 3, glow.begin());
			}
			else
			{
				for (int i = 0; i < w; ++i)
				{
					acc[i * 3 + 0] = amb[0];
					acc[i * 3 + 1] = amb[1];
					acc[i * 3 + 2] = amb[2];
				}
				std::fill(glow.begin(), glow.end(), 0.0f);
			}
			const float *rrow = lit.empty() ? nullptr : reliefRow(y);
			for (const Lit &L : lit)
			{
				lampRow(L, y, acc.data(), glow.data(), rrow);
			}
			// the light running along the pipes: into the halo, so the night does not dim it; the pipe itself
			// darker where it glows, or a white pipe washes out
			for (const FlowNow &N : flows)
			{
				const PlacedFlow &P = *N.P;
				const Flow &F = P.flow;
				if (y < P.box.y || y >= P.box.y + P.box.h)
				{
					continue;
				}
				const Uint32 *mrow = &P.map[(size_t)(y - P.box.y) * P.box.w];
				const int fx0 = std::max(ax0, (int)P.box.x), fx1 = std::min(ax1, P.box.x + (int)P.box.w);
				for (int x = fx0; x < fx1; ++x)
				{
					float k, white, darken;
					if (!flowAt(N, mrow[x - P.box.x], k, white, darken))
					{
						continue;
					}
					float *g = &glow[(x - ax0) * 3];
					float *a = &acc[(x - ax0) * 3];
					g[0] += F.colour[0] * k + white * 0.85f;
					g[1] += F.colour[1] * k + white;
					g[2] += F.colour[2] * k + white * 0.75f;
					a[0] *= 1 - darken;
					a[1] *= 1 - darken;
					a[2] *= 1 - darken;
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
		static int frames = 0, rebuilds = 0;
		rebuilds += rebuilt ? 1 : 0;
		total += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - perfStart).count();
		if (++frames == 60)
		{
			Log(LOG_INFO) << "HD base light: " << total / frames << " ms per frame, " << resting.size() << " resting lamps"
				<< (cached ? " (kept, " : " (not kept, ") << rebuilds << " rebuilds in 60 frames), " << lit.size() - (cached ? 0 : resting.size())
				<< " moving, " << flows.size() << " flows, " << w << "x" << (ay1 - ay0) << " px, " << HdWorkers::instance().threads() << " threads";
			total = 0;
			frames = 0;
			rebuilds = 0;
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
	// the glow of the brightness lum, pow(lum, 1.3) in steps of 1/1023 (the video card reads the same table)
	static const int GLOW_STEPS = 1024;
	static float glowLut[GLOW_STEPS];
	static bool glowMade = false;
	if (!glowMade)
	{
		for (int i = 0; i < GLOW_STEPS; ++i)
		{
			glowLut[i] = std::pow(i / (float)(GLOW_STEPS - 1), 1.3f);
		}
		glowMade = true;
	}
	// what a pixel takes from where it is: reveal, grid, beam, edge, line, lift
	auto params = [&](int x, int y, float *v)
	{
		const float py = (y + 0.5f - rect.y) / s;
		const float px = (x + 0.5f - rect.x) / s;
		// where it is built first: blotches of a big and a small noise
		const float n = (valueNoise(px, py, 24, seed) * 0.7f + valueNoise(px, py, 7, seed + 9) * 0.3f);
		v[0] = std::min(1.0f, std::max(0.0f, (p - n) / 0.05f + 0.5f));
		const float gx = std::fabs(std::fmod(px, 16.0f) - 8.0f), gy = std::fabs(std::fmod(py, 16.0f) - 8.0f);
		v[1] = (gx > 7.4f || gy > 7.4f) ? 0.35f : 0.0f;
		const float bx = std::fabs(std::fmod(px + 16.0f, 32.0f) - 16.0f), by = std::fabs(std::fmod(py + 16.0f, 32.0f) - 16.0f);
		v[2] = (bx < 1.3f || by < 1.3f) ? 0.8f : 0.0f;
		// the hot edge where the building grows
		v[3] = p < 1 ? std::max(0.0f, 1 - std::fabs(n - p) / 0.03f) * weld : 0.0f;
		v[4] = std::max(0.0f, 1 - std::fabs(py - scan) / 3.0f) * 0.5f;
		v[5] = 0.85f + 0.15f * std::sin(t * 2.0f + py * 0.15f);
	};
	// the pixel from them (HdGpuWorld::building does the same)
	auto apply = [&](Uint32 pxl, const float *v)
	{
		const float reveal = v[0], grid = v[1], beam = v[2], edge = v[3], line = v[4], lift = v[5];
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
			const float glow = glowLut[std::min(GLOW_STEPS - 1, (int)(lum * (float)(GLOW_STEPS - 1) + 0.5f))];
			float bp[3] = { 0.05f + glow * 0.25f, 0.12f + glow * 0.55f, 0.20f + glow * 0.85f };
			for (int c = 0; c < 3; ++c)
			{
				const float cyan[3] = { 0.35f, 0.85f, 1.0f };
				const float yellow[3] = { 0.75f, 0.62f, 0.25f };
				float w = bp[c] * lift + cyan[c] * (grid * 0.4f + line);
				w = w * (1 - beam) + yellow[c] * beam;
				out[c] = pic[c] * reveal + w * (1 - reveal);
			}
		}
		const float hot[3] = { 1.0f, 0.55f, 0.15f };
		Uint32 o = pxl & 0xFF000000u;
		for (int c = 0; c < 3; ++c)
		{
			const float w = out[c] + hot[c] * edge * 1.2f;
			o |= (Uint32)std::lround(std::min(1.0f, std::max(0.0f, w)) * 255.0f) << (16 - 8 * c);
		}
		return o;
	};
	const int bands = (y1 - y0 + BAND - 1) / BAND;
	const int bw = x1 - x0;
	HdGpuWorld &gw = HdGpuWorld::instance();
	if (gw.on(world))
	{
		// on the video card: the values of every pixel worked out here, the pixel there
		static std::vector<float> vals;
		vals.resize((size_t)bw * (y1 - y0) * 6);
		HdWorkers::instance().run(bands, [&](int band)
		{
			const int ya = y0 + band * BAND, yb = std::min(y1, ya + BAND);
			for (int y = ya; y < yb; ++y)
			{
				float *v = &vals[(size_t)(y - y0) * bw * 6];
				for (int x = x0; x < x1; ++x, v += 6)
				{
					params(x, y, v);
				}
			}
		});
		const bool verifying = gw.verifying();
		if (gw.building(vals, glowLut, GLOW_STEPS, x0, y0, x1, y1) && !verifying)
		{
			return;
		}
		HdWorkers::instance().run(bands, [&](int band)
		{
			const int ya = y0 + band * BAND, yb = std::min(y1, ya + BAND);
			for (int y = ya; y < yb; ++y)
			{
				Uint32 *row = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch);
				const float *v = &vals[(size_t)(y - y0) * bw * 6];
				for (int x = x0; x < x1; ++x, v += 6)
				{
					row[x] = apply(row[x], v);
				}
			}
		});
		return;
	}
	HdWorkers::instance().run(bands, [&](int band)
	{
		const int ya = y0 + band * BAND, yb = std::min(y1, ya + BAND);
		float v[6];
		for (int y = ya; y < yb; ++y)
		{
			Uint32 *row = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch);
			for (int x = x0; x < x1; ++x)
			{
				params(x, y, v);
				row[x] = apply(row[x], v);
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
/// Pack pixels to a radian of the bottom's caustic net.
const float CAUSTIC = 4.6f;

/// The light of a pool's bottom at (x, y) (pack pixels) as at `t`: five steps of a warped wave make a net of
/// bright threads that tiles every 2 pi (prototype proto.py caustic, 23.10); 0..1.
float caustic(float x, float y, float t, float scale)
{
	const float TAU = 2 * PI, INTEN = 0.005f;
	float px = std::fmod(x / scale, TAU), py = std::fmod(y / scale, TAU);
	px = (px < 0 ? px + TAU : px) - 250;
	py = (py < 0 ? py + TAU : py) - 250;
	float ix = px, iy = py, c = 1;
	for (int n = 0; n < 5; ++n)
	{
		const float tt = t * (1 - 3.5f / (n + 1));
		const float nx = px + std::cos(tt - ix) + std::sin(tt + iy);
		const float ny = py + std::sin(tt - iy) + std::cos(tt + ix);
		ix = nx;
		iy = ny;
		const float a = px / (std::sin(ix + tt) / INTEN), b = py / (std::cos(iy + tt) / INTEN);
		c += 1 / std::sqrt(a * a + b * b);
	}
	c = std::fabs(1.17f - std::pow(c / 5, 1.4f));
	c *= c;
	c *= c;
	return std::min(1.0f, c * c);
}

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

/// The mixes of one part of the motion over its box: on a frame of the video card gathered and handed over at
/// end() as one HdGpuWorld MIX (and drawn by the processor too when verifying or when the card refuses it),
/// otherwise drawn at once. put() from many threads, a pixel once; outside the box - nothing.
struct Mixes
{
	SDL_Surface *world;
	bool card = false;
	int x0 = 0, y0 = 0, x1 = 0, y1 = 0;
	std::vector<float> v;

	explicit Mixes(SDL_Surface *w) : world(w) {}
	void begin(int bx0, int by0, int bx1, int by1)
	{
		x0 = std::max(0, bx0);
		y0 = std::max(0, by0);
		x1 = std::min(world->w, bx1);
		y1 = std::min(world->h, by1);
		card = x0 < x1 && y0 < y1 && HdGpuWorld::instance().on(world);
		if (card)
		{
			v.assign((size_t)(x1 - x0) * (y1 - y0) * 4, 0.0f);
		}
	}
	void put(int x, int y, const float col[3], float m)
	{
		if (x < x0 || y < y0 || x >= x1 || y >= y1)
		{
			return;
		}
		if (card)
		{
			float *o = &v[((size_t)(y - y0) * (x1 - x0) + (x - x0)) * 4];
			o[0] = col[0];
			o[1] = col[1];
			o[2] = col[2];
			o[3] = m;
			return;
		}
		Uint32 *px = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch) + x;
		*px = mix(*px, col, m);
	}
	void end()
	{
		if (!card)
		{
			return;
		}
		card = false;
		HdGpuWorld &gw = HdGpuWorld::instance();
		const bool verify = gw.verifying();
		if (gw.shade(HdGpuWorld::MIX, v, x0, y0, x1, y1, nullptr) && !verify)
		{
			return;
		}
		// m 0 leaves the pixel as it is
		const int w = x1 - x0;
		for (int y = y0; y < y1; ++y)
		{
			Uint32 *row = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch);
			const float *o = &v[(size_t)(y - y0) * w * 4];
			for (int x = x0; x < x1; ++x, o += 4)
			{
				row[x] = mix(row[x], o, o[3]);
			}
		}
	}
};

}

void bake(View &view, const HdFrame *rock, const std::vector<SDL_Rect> &empty, const std::vector<PlacedWater> &waters)
{
	static Uint32 bakes = 0;
	view.serial = ++bakes;
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
		// pools of 200 pack pixels and more (the scene may say less: the metagarden's pond); a glint of colour
		// elsewhere is not water
		const size_t least = (size_t)((W.least > 0 ? W.least : 200) * s * s);
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
			A.fit = W.fit;
			std::copy(W.glint, W.glint + 3, A.glint);
			view.waters.push_back(A);
		}
	}
	// the glows' pixels: of their hue in their box, each pixel once (the shield's boxes may touch), and the
	// groups by the angle round the box's middle
	std::vector<unsigned char> taken(view.albedo.size(), 0);
	for (PlacedGlow &G : view.glows)
	{
		const Glow &L = G.glow;
		const int x0 = std::max(0, (int)(L.x - view.x)), y0 = std::max(0, (int)(L.y - view.y));
		const int x1 = std::min(w, (int)std::ceil(L.x + L.w - view.x)), y1 = std::min(h, (int)std::ceil(L.y + L.h - view.y));
		const float mx = L.x + L.w / 2 - view.x, my = L.y + L.h / 2 - view.y;
		for (int y = y0; y < y1; ++y)
		{
			for (int x = x0; x < x1; ++x)
			{
				const size_t i = (size_t)y * w + x;
				const Uint32 px = view.albedo[i];
				if (taken[i])
				{
					continue;
				}
				const float r = ((px >> 16) & 0xFF) / 255.0f, g = ((px >> 8) & 0xFF) / 255.0f, bl = (px & 0xFF) / 255.0f;
				const float hi = std::max(r, std::max(g, bl)), lo = std::min(r, std::min(g, bl)), d = hi - lo;
				if (hi < 0.3f || d <= 0.0001f || d / hi < L.saturation)
				{
					continue;
				}
				float hue = hi == r ? std::fmod((g - bl) / d + 6, 6.0f) : hi == g ? (bl - r) / d + 2 : (r - g) / d + 4;
				hue *= 60;
				const float off = std::fabs(hue - L.hue);
				if (std::min(off, 360 - off) > L.tolerance)
				{
					continue;
				}
				taken[i] = 1;
				G.pixels.push_back((Uint32)i);
				const float ang = std::atan2(y + 0.5f - my, x + 0.5f - mx) + PI;
				G.group.push_back((unsigned char)std::min(L.groups - 1, (int)(ang / (2 * PI) * L.groups)));
			}
		}
	}
	// a lid is the colour of the picture just above its eye (6 to 10 pack pixels over it, 4 to each side)
	for (PlacedLid &P : view.lids)
	{
		float sum[3] = { 0, 0, 0 };
		int found = 0;
		for (float dy = 6; dy <= 10; dy += 1)
		{
			for (float dx = -4; dx <= 4; dx += 1)
			{
				const int x = (int)(P.lid.x + dx * P.scale - view.x), y = (int)(P.lid.y - P.lid.ry - dy * P.scale - view.y);
				if (x >= 0 && y >= 0 && x < w && y < h)
				{
					const Uint32 px = view.albedo[(size_t)y * w + x];
					sum[0] += (px >> 16) & 0xFF;
					sum[1] += (px >> 8) & 0xFF;
					sum[2] += px & 0xFF;
					++found;
				}
			}
		}
		for (int c = 0; c < 3 && found > 0; ++c)
		{
			P.colour[c] = sum[c] / found;
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
	Mixes mx(world);
	// the water: the picture under it shifted by two slow waves (base_scene_preview.py render), calmer since
	// 23.10, and the light of the bottom running over it - two nets of caustics turned apart, so their cells
	// do not repeat, and a long swell (water A, docs/research/base-living-2026-10-22.md 11)
	const float c1 = std::cos(0.41f), s1 = std::sin(0.41f), c2 = std::cos(-0.93f), s2 = std::sin(-0.93f);
	const float tw = t * 0.7f;
	// OXCE_HD_BASE_PERF: the cost of the water, every 60 frames into the log
	static const bool perf = std::getenv("OXCE_HD_BASE_PERF") != nullptr;
	const auto perfStart = std::chrono::steady_clock::now();
	static const bool noWater = measuredOff("water"), noSpin = measuredOff("spin");
	for (const View::Area &W : view.waters)
	{
		// the pool stands still (the picture as it is) outside its facility's turn, and ripples up to the
		// full strength over the turn's first second
		const float act = actOf(view, W.fit);
		if (noWater || act < 0.01f)
		{
			continue;
		}
		const int x0 = std::max((int)W.box.x, view.x), y0 = std::max((int)W.box.y, view.y);
		const int x1 = std::min(W.box.x + (int)W.box.w, view.x + view.w), y1 = std::min(W.box.y + (int)W.box.h, view.y + view.h);
		if (x0 >= x1 || y0 >= y1)
		{
			continue;
		}
		mx.begin(x0, y0, x1, y1);
		HdWorkers::instance().run(y1 - y0, [&](int row)
		{
			const int y = y0 + row;
			const float vy = (y - W.box.y) / s;
			for (int x = x0; x < x1; ++x)
			{
				const float m = view.water[(size_t)(y - view.y) * view.w + (x - view.x)];
				if (m <= 0.01f || !inWorld(x, y))
				{
					continue;
				}
				const float vx = (x - W.box.x) / s;
				const float dx = 1.8f * std::sin(0.09f * vx + 0.13f * vy + 2.3f * tw) + 1.1f * std::sin(0.17f * vy - 0.05f * vx + 3.4f * tw);
				const float dy = 1.8f * std::sin(0.11f * vx - 0.08f * vy + 2.0f * tw) + 1.1f * std::sin(0.15f * vx + 0.12f * vy - 2.9f * tw);
				float col[3];
				sample(view.albedo, view.w, view.h, x - view.x + dx * 0.8f * s * act, y - view.y + dy * 0.8f * s * act, col);
				const float ca = std::max(caustic(vx * c1 - vy * s1, vx * s1 + vy * c1, t * 0.55f, CAUSTIC),
					0.75f * caustic(vx * c2 - vy * s2 + 17, vx * s2 + vy * c2 + 5, t * 0.43f + 3, CAUSTIC * 1.37f));
				const float swell = 0.5f + 0.5f * std::sin(0.045f * vx + 0.03f * vy - 1.1f * t);
				const float shade = 1 + (0.92f + 0.12f * swell - 1) * act;
				for (int c = 0; c < 3; ++c)
				{
					col[c] = col[c] * shade + W.glint[c] * (0.55f * 255) * ca * act;
				}
				mx.put(x, y, col, m);
			}
		});
		mx.end();
	}
	if (perf)
	{
		static double total = 0;
		static int frames = 0;
		total += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - perfStart).count();
		if (++frames == 60)
		{
			Log(LOG_INFO) << "HD base water: " << total / frames << " ms per frame, " << view.waters.size() << " waters";
			total = 0;
			frames = 0;
		}
	}
	// the spins: a radar dish turning, a turret looking over its sector
	const auto spinStart = std::chrono::steady_clock::now();
	for (const PlacedSpin &P : view.spins)
	{
		if (noSpin)
		{
			break;
		}
		const Spin &S = P.spin;
		float deg = S.rps != 0 ? t * S.rps * 360 + P.phase * 360 : S.middle + S.swing * std::sin(t / S.period * 2 * PI + P.phase * 2 * PI);
		if (P.fit >= 0 && view.fits[P.fit].continuous)
		{
			// a piece of a facility without fits turns while the facility has its turn, and stands where it is
			// between the turns (a swinging one eases to its middle)
			const Fit &F = view.fits[P.fit];
			if (S.rps != 0)
			{
				deg = P.phase * 360 + F.turned * S.rps * 360;
			}
			else
			{
				deg = S.middle + S.swing * F.act * std::sin(F.turned / S.period * 2 * PI + P.phase * 2 * PI);
			}
		}
		else if (P.fit >= 0)
		{
			// a turret of fits looks straight between them and swings from the middle in one (tickets 244, 245),
			// easing back over the last half second if the fit is not whole swings
			const float ft = fitTime(view, P.fit, ms);
			const float left = view.fits[P.fit].length - ft;
			if (S.rps != 0)
			{
				deg = P.phase * 360 + std::max(0.0f, ft) * S.rps * 360;
			}
			else
			{
				deg = ft < 0 ? S.middle : S.middle + S.swing * std::sin(ft / S.period * 2 * PI) * std::min(1.0f, left / 0.5f);
			}
		}
		const float ang = deg * PI / 180, ca = std::cos(ang), sa = std::sin(ang);
		const int r = (int)std::ceil(S.radius);
		const int cx = (int)std::lround(S.x), cy = (int)std::lround(S.y);
		mx.begin(std::max(cx - r, view.x), std::max(cy - r, view.y), std::min(cx + r, view.x + view.w), std::min(cy + r, view.y + view.h));
		for (int y = cy - r; y < cy + r; ++y)
		{
			if (y < view.y || y >= view.y + view.h || y < 0 || y >= world->h)
			{
				continue;
			}
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
					mx.put(x, y, col, 1);
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
				mx.put(x, y, col, m);
			}
		}
		mx.end();
	}
	if (perf)
	{
		static double total = 0;
		static int frames = 0;
		total += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - spinStart).count();
		if (++frames == 60)
		{
			Log(LOG_INFO) << "HD base spins: " << total / frames << " ms per frame, " << view.spins.size() << " spins";
			total = 0;
			frames = 0;
		}
	}
	// the fits (tickets 237-241): only their few thousand pixels, and only while a fit runs
	auto put = [&](int vx, int vy, const float col[3])
	{
		mx.put(view.x + vx, view.y + vy, col, 1);
	};
	auto rgb = [](Uint32 px, float out[3])
	{
		out[0] = (float)((px >> 16) & 0xFF);
		out[1] = (float)((px >> 8) & 0xFF);
		out[2] = (float)(px & 0xFF);
	};
	for (const PlacedGlow &G : view.glows)
	{
		const float ft = fitTime(view, G.fit, ms);
		if (ft < 0)
		{
			continue;
		}
		// the groups go one after another over the first 40% of the fit, each pulsing over the rest
		const float length = view.fits[G.fit].length;
		const float spread = G.glow.groups > 1 ? 0.4f * length : 0.0f;
		float factor[16];
		for (int g = 0; g < G.glow.groups; ++g)
		{
			const float a = fitWave(ft - spread * g / G.glow.groups, length - spread, G.glow.pulses);
			factor[g] = 1 + (G.glow.peak - 1) * a;
		}
		int bx0 = view.w, by0 = view.h, bx1 = 0, by1 = 0;
		for (const auto p : G.pixels)
		{
			bx0 = std::min(bx0, (int)(p % view.w));
			bx1 = std::max(bx1, (int)(p % view.w) + 1);
			by0 = std::min(by0, (int)(p / view.w));
			by1 = std::max(by1, (int)(p / view.w) + 1);
		}
		mx.begin(view.x + bx0, view.y + by0, view.x + bx1, view.y + by1);
		for (size_t i = 0; i < G.pixels.size(); ++i)
		{
			const float f = factor[G.group[i]];
			if (std::fabs(f - 1) < 0.004f)
			{
				continue;
			}
			float col[3];
			rgb(view.albedo[G.pixels[i]], col);
			// going dark the green and blue fall faster: yellow goes to dark orange, violet to dark violet
			const float fg = f < 1 ? std::pow(f, 1.4f) : f;
			col[0] = std::min(255.0f, col[0] * f);
			col[1] = std::min(255.0f, col[1] * fg);
			col[2] = std::min(255.0f, col[2] * fg);
			put((int)(G.pixels[i] % view.w), (int)(G.pixels[i] / view.w), col);
		}
		mx.end();
	}
	for (const PlacedLid &P : view.lids)
	{
		const float ft = fitTime(view, P.fit, ms);
		const float c = fitWave(ft, ft < 0 ? 0 : view.fits[P.fit].length, P.lid.blinks);
		if (c < 0.01f)
		{
			continue;
		}
		// the upper lid comes down the eye's own curve: at full shut it covers it to the lower edge
		const Lid &L = P.lid;
		mx.begin((int)std::floor(L.x - L.rx), (int)std::floor(L.y - L.ry), (int)std::ceil(L.x + L.rx) + 1, (int)std::ceil(L.y + L.ry) + 1);
		for (int y = (int)std::floor(L.y - L.ry); y <= (int)std::ceil(L.y + L.ry); ++y)
		{
			for (int x = (int)std::floor(L.x - L.rx); x <= (int)std::ceil(L.x + L.rx); ++x)
			{
				const float u = (x + 0.5f - L.x) / L.rx;
				if (std::fabs(u) >= 1)
				{
					continue;
				}
				const float half = L.ry * std::sqrt(1 - u * u);
				const float top = L.y - half, edge = top + c * 2 * half, yc = y + 0.5f;
				if (yc < top || yc > edge)
				{
					continue;
				}
				// darker towards its edge, and a dark line of lashes one pack pixel wide there
				const float q = (yc - top) / std::max(0.001f, edge - top);
				const float k = (1 - 0.25f * q) * (edge - yc < P.scale ? 0.45f : 1.0f);
				const float col[3] = { P.colour[0] * k, P.colour[1] * k, P.colour[2] * k };
				put(x - view.x, y - view.y, col);
			}
		}
		mx.end();
	}
	for (const PlacedSink &P : view.sinks)
	{
		const float ft = fitTime(view, P.fit, ms);
		const float a = fitWave(ft, ft < 0 ? 0 : view.fits[P.fit].length, P.sink.pulses);
		if (a < 0.01f)
		{
			continue;
		}
		// the platform shrinks to its middle (it goes down) and darkens, a dark gap opening round it;
		// the hatch grows and reddens (it comes up)
		const Sink &S = P.sink;
		const float cx = S.x + S.w / 2, cy = S.y + S.h / 2, icx = S.ix + S.iw / 2, icy = S.iy + S.ih / 2;
		const float out = 1 / (1 - 0.07f * a), in = 1 - 0.10f * a, dark = 1 - 0.35f * a;
		mx.begin((int)S.x, (int)S.y, (int)(S.x + S.w), (int)(S.y + S.h));
		for (int y = (int)S.y; y < (int)(S.y + S.h); ++y)
		{
			for (int x = (int)S.x; x < (int)(S.x + S.w); ++x)
			{
				const float xc = x + 0.5f, yc = y + 0.5f;
				float col[3];
				if (xc >= S.ix && xc < S.ix + S.iw && yc >= S.iy && yc < S.iy + S.ih)
				{
					sample(view.albedo, view.w, view.h, icx + (xc - icx) * in - 0.5f - view.x, icy + (yc - icy) * in - 0.5f - view.y, col);
					col[0] = std::min(255.0f, col[0] * (1 + 0.6f * a));
					col[1] *= 1 - 0.25f * a;
					col[2] *= 1 - 0.25f * a;
				}
				else
				{
					const float sx = cx + (xc - cx) * out, sy = cy + (yc - cy) * out;
					if (sx < S.x || sx >= S.x + S.w || sy < S.y || sy >= S.y + S.h)
					{
						col[0] = 12;
						col[1] = col[2] = 10;
					}
					else
					{
						sample(view.albedo, view.w, view.h, sx - 0.5f - view.x, sy - 0.5f - view.y, col);
						col[0] *= dark;
						col[1] *= dark;
						col[2] *= dark;
					}
				}
				put(x - view.x, y - view.y, col);
			}
		}
		mx.end();
	}
}

void drawParticles(SDL_Surface *world, const SDL_Rect &area, const std::vector<PlacedEmit> &emits, float night, Uint32 ms)
{
	if (!world || world->format->BytesPerPixel != 4 || emits.empty() || measuredOff("emit"))
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
	struct Blob { float x, y, r, ring, col[3], a; bool add; float hx, hy; };   // hx > 0 - a box of half sides hx, hy
	std::vector<Blob> blobs;
	float actNow = 1.0f;      // how much the emitter's facility moves: its particles fade in and out with it
	auto put = [&](float x, float y, float r, float ring, const float col[3], float a, bool add)
	{
		a *= actNow;
		if (a > 0.004f && r > 0)
		{
			blobs.push_back({ x, y, r, ring, { col[0], col[1], col[2] }, a, add, 0.0f, 0.0f });
		}
	};
	auto putBox = [&](float x, float y, float hx, float hy, const float col[3], float a, bool add)
	{
		a *= actNow;
		if (a > 0.004f && hx > 0 && hy > 0)
		{
			blobs.push_back({ x, y, 0.0f, 0.0f, { col[0], col[1], col[2] }, a, add, hx, hy });
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
		actNow = p.act;
		if (actNow < 0.01f)
		{
			continue;
		}
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
		case BELT:
		case BELTREV:
		{
			// parts ride along the long side of the box, glints of rollers slide over the belt (ticket 336); it
			// runs while the facility works, and the parts are lit as the room is
			if (p.level < 0.5f)
			{
				break;
			}
			const bool horiz = E.w >= E.h, reverse = E.kind == BELTREV;
			const float lenW = horiz ? E.w : E.h, widW = horiz ? E.h : E.w;
			const float Lp = lenW / s, Wp = widW / s;                // pack pixels
			const float gap = std::max(2.6f * Wp, 22.0f);
			const int n = (int)(Lp / gap) + 2;
			const float along = t * BELT_SPEED;
			// the point `pos` pack pixels along the belt (from its end for beltrev), `off` world pixels aside
			auto place = [&](float pos, float off, float &px, float &py)
			{
				const float a = reverse ? Lp - pos : pos;
				px = horiz ? E.x + a * s : E.x + widW / 2 + off;
				py = horiz ? E.y + widW / 2 + off : E.y + a * s;
			};
			static const float white[3] = { 1, 1, 1 }, black[3] = { 0, 0, 0 };
			// the glints of the rollers: a light and a dark bar across the belt, both riding
			const int bars = std::max(1, (int)(Lp / 11));
			const float bx = horiz ? 1.3f * s : widW / 2, by = horiz ? widW / 2 : 1.3f * s;
			for (int j = 0; j <= bars; ++j)
			{
				const float pos = std::fmod(along + j * 11.0f, Lp + 11.0f);
				if (pos > Lp)
				{
					continue;
				}
				float cx, cy;
				place(pos, 0, cx, cy);
				putBox(cx, cy, bx, by, white, 0.07f, true);
				if (pos + 5.5f <= Lp)
				{
					place(pos + 5.5f, 0, cx, cy);
					putBox(cx, cy, bx, by, black, 0.10f, false);
				}
			}
			const float lead = (float)(p.seed % 17);
			for (int i = 0; i < n; ++i)
			{
				const float raw = along + i * gap + lead;
				const Uint32 lap = (Uint32)(raw / (n * gap));
				const float pos = std::fmod(raw, n * gap);
				if (pos > Lp)
				{
					continue;
				}
				const float a = std::min(1.0f, std::min(pos / 5.0f, (Lp - pos) / 5.0f));
				const float ln = (0.44f + 0.26f * hash1(i, lap, p.seed)) * Wp;
				const float wd = (0.42f + 0.20f * hash1(i, lap, p.seed + 1)) * Wp;
				const float tone = 0.82f + 0.36f * hash1(i, lap, p.seed + 2);
				float c[3], edge[3];
				for (int j = 0; j < 3; ++j)
				{
					c[j] = std::min(1.0f, col[j] * tone * amb[j]);
					edge[j] = c[j] * 0.4f;
				}
				float cx, cy;
				place(pos, (hash1(i, lap, p.seed + 3) - 0.5f) * 0.12f * widW, cx, cy);
				const float hx = horiz ? ln / 2 * s : wd / 2 * s, hy = horiz ? wd / 2 * s : ln / 2 * s;
				putBox(cx + 1.2f * s, cy + 1.8f * s, hx, hy, black, 0.40f * a, false);        // the shadow
				putBox(cx, cy, hx + 0.5f * s, hy + 0.5f * s, edge, 0.9f * a, false);          // the dark rim
				putBox(cx, cy, hx, hy, c, 0.96f * a, false);                                  // the body
				putBox(cx, cy - hy * 0.55f, hx * 0.92f, std::max(0.5f, hy * 0.22f), white, 0.22f * a, true);   // the glint
			}
			break;
		}
		case ROLL:
		{
			// a roller turning: glints run across its short side, thinner and paler towards the edges (a cylinder)
			const bool horiz = E.w >= E.h;
			const float lenW = horiz ? E.w : E.h, widW = horiz ? E.h : E.w;
			for (int j = 0; j < 5; ++j)
			{
				const float th = t * 2 * PI / 1.8f + j * 2 * PI / 5;
				const float c = std::cos(th);
				if (c <= 0)
				{
					continue;
				}
				const float off = std::sin(th) * widW / 2 * 0.95f;
				const float thick = (0.8f + 2.2f * c) * s;
				if (horiz)
				{
					putBox(E.x + lenW / 2, E.y + widW / 2 + off, lenW / 2, thick / 2, col, 0.30f * c, true);
				}
				else
				{
					putBox(E.x + widW / 2 + off, E.y + lenW / 2, thick / 2, lenW / 2, col, 0.30f * c, true);
				}
			}
			break;
		}
		case SHUTTLE:
		{
			// a print head goes to and fro along the long side of the box, its nozzle glowing, a cooling trail behind
			const bool horiz = E.w >= E.h;
			const float period = 6.0f + 2.0f * hash1(p.seed, 1, 2);
			const float ph = t / period + hash1(p.seed, 3, 4);
			const float u = 0.5f - 0.5f * std::cos(2 * PI * ph);
			const float dirn = std::sin(2 * PI * ph) >= 0 ? 1.0f : -1.0f;
			static const float white[3] = { 1, 1, 1 }, glint[3] = { 1.0f, 0.85f, 0.6f }, thread[3] = { 1.0f, 0.72f, 0.35f };
			const float dark[3] = { 0.30f * amb[0], 0.19f * amb[1], 0.10f * amb[2] };
			const float metal[3] = { 0.62f * amb[0], 0.40f * amb[1], 0.16f * amb[2] };
			if (horiz)
			{
				const float hx = E.x + u * E.w, hyBody = E.y + 0.30f * E.h, hyTip = E.y + 0.80f * E.h;
				putBox(hx, hyBody, 4.2f * s, 3.0f * s, dark, 0.96f, false);
				putBox(hx, hyBody, 3.5f * s, 2.3f * s, metal, 0.96f, false);
				putBox(hx, hyBody - 1.2f * s, 3.0f * s, 0.6f * s, glint, 0.40f, true);
				for (int j = 1; j < 11; ++j)
				{
					put(hx - dirn * j * 1.4f * s, hyTip, 1.1f * s, 0, thread, 0.55f * (1 - j / 11.0f), true);
				}
				put(hx, hyTip, 7 * s, 0, col, 0.45f, true);
				put(hx, hyTip, 1.6f * s, 0, white, 1.25f, true);
				put(hx, hyTip + 4 * s, 13 * s, 0, col, 0.10f, true);
			}
			else
			{
				const float hy = E.y + u * E.h, hxBody = E.x + 0.30f * E.w, hxTip = E.x + 0.80f * E.w;
				const float body[3] = { 0.50f * amb[0], 0.32f * amb[1], 0.16f * amb[2] };
				putBox(hxBody, hy, 2.6f * s, 3.6f * s, body, 0.95f, false);
				put(hxTip, hy, 7 * s, 0, col, 0.45f, true);
				put(hxTip, hy, 1.6f * s, 0, white, 1.25f, true);
			}
			break;
		}
		case HEAT:
		{
			// hot metal breathing: a soft light swelling and fading, about 3.6 s a breath, each its own phase
			if (p.level < 0.5f)
			{
				break;
			}
			const float v = 0.55f + 0.45f * std::sin((t / 3.6f + hash1(p.seed, 7, 9)) * 2 * PI);
			const float m = std::min(E.w, E.h);
			const float cx = E.x + E.w / 2, cy = E.y + E.h / 2;
			const float hot[3] = { 0.5f + 0.5f * col[0], 0.5f + 0.5f * col[1], 0.5f + 0.5f * col[2] };
			put(cx, cy, 0.62f * m, 0, col, 0.30f * v * p.level, true);
			put(cx, cy, 0.30f * m, 0, hot, 0.18f * v * p.level, true);
			break;
		}
		case CART:
		{
			// a trolley with a load goes along the long side of the box, unloads, comes back empty, waits
			const bool horiz = E.w >= E.h;
			const float lenW = horiz ? E.w : E.h, widW = horiz ? E.h : E.w;
			const float period = 16.0f + 6.0f * hash1(p.seed, 5, 6);
			const float u = std::fmod(t / period + hash1(p.seed, 7, 8), 1.0f);
			float f = 0;
			bool loaded = true;
			if (u < 0.4f)
			{
				f = smooth(u / 0.4f);
			}
			else if (u < 0.5f)
			{
				f = 1;
				loaded = u < 0.45f;
			}
			else if (u < 0.9f)
			{
				f = 1 - smooth((u - 0.5f) / 0.4f);
				loaded = false;
			}
			else
			{
				loaded = false;
			}
			const float half = 3.6f * s, side = 2.2f * s;
			const float along = half + f * std::max(0.0f, lenW - 2 * half);
			const float cx = horiz ? E.x + along : E.x + widW / 2, cy = horiz ? E.y + widW / 2 : E.y + along;
			const float hx = horiz ? half : side, hy = horiz ? side : half;
			float body[3], edge[3], crate[3];
			static const float black[3] = { 0, 0, 0 }, white[3] = { 1, 1, 1 };
			static const float wood[3] = { 0.85f, 0.50f, 0.20f };
			for (int j = 0; j < 3; ++j)
			{
				body[j] = col[j] * amb[j];
				edge[j] = body[j] * 0.45f;
				crate[j] = wood[j] * amb[j];
			}
			putBox(cx + 1.0f * s, cy + 1.5f * s, hx, hy, black, 0.35f, false);
			putBox(cx, cy, hx + 0.4f * s, hy + 0.4f * s, edge, 0.95f, false);
			putBox(cx, cy, hx, hy, body, 0.97f, false);
			// the wheels: dark stubs at the four corners
			for (int cornerX = -1; cornerX <= 1; cornerX += 2)
			{
				for (int cornerY = -1; cornerY <= 1; cornerY += 2)
				{
					putBox(cx + cornerX * (hx - 0.5f * s), cy + cornerY * (hy + 0.3f * s), 0.7f * s, 0.5f * s, black, 0.8f, false);
				}
			}
			if (loaded)
			{
				putBox(cx, cy, hx * 0.6f, hy * 0.62f, crate, 0.97f, false);
				putBox(cx, cy - hy * 0.25f, hx * 0.55f, 0.35f * s, white, 0.18f, true);
			}
			break;
		}
		case TICKER:
		{
			// a running line on a screen: rows of dashes scroll along the long side of the box, fading at its ends
			const bool horiz = E.w >= E.h;
			const float lenP = (horiz ? E.w : E.h) / s, widP = (horiz ? E.h : E.w) / s;
			const int rows = std::max(1, (int)(widP / 3.0f));
			const float span = lenP + 8.0f;
			const int segments = (int)(span / 7.0f) + 1;
			for (int r = 0; r < rows; ++r)
			{
				const float across = (r + 0.5f) * widP / rows;
				const float speed = 5.0f + 3.0f * hash1(r, 11, p.seed);
				const float shift = t * speed + hash1(r, 12, p.seed) * span;
				for (int i = 0; i < segments; ++i)
				{
					const float raw = i * 7.0f + shift;
					const Uint32 lap = (Uint32)(raw / span);
					const float centre = lenP + 4.0f - std::fmod(raw, span);
					const float len = 1.8f + 3.2f * hash1(i, lap, p.seed + r * 7);
					const float a0 = std::max(0.0f, centre - len / 2), a1 = std::min(lenP, centre + len / 2);
					if (a1 <= a0)
					{
						continue;
					}
					const float mid = (a0 + a1) / 2;
					const float fade = smooth(std::min(mid, lenP - mid) / 2.0f);
					const float x = horiz ? E.x + mid * s : E.x + across * s, y = horiz ? E.y + across * s : E.y + mid * s;
					const float halfLen = (a1 - a0) / 2 * s, halfAcross = 0.65f * s;
					putBox(x, y, horiz ? halfLen : halfAcross, horiz ? halfAcross : halfLen, col, 0.85f * fade, true);
				}
			}
			break;
		}
		}
	}
	// a frame of the video card: the weights of every blob on all cores, the blobs handed over in their order
	size_t first = 0;
	HdGpuWorld &gw = HdGpuWorld::instance();
	if (gw.on(world) && !blobs.empty())
	{
		const bool verify = gw.verifying();
		struct Patch { int box[4]; bool any; std::vector<float> k; };
		std::vector<Patch> patches(blobs.size());
		HdWorkers::instance().run((int)blobs.size(), [&](int i)
		{
			const Blob &b = blobs[i];
			Patch &pt = patches[i];
			auto keep = [&](int x, int y, float k)
			{
				const int w = pt.box[2] - pt.box[0];
				if (pt.k.empty())
				{
					pt.k.assign((size_t)w * (pt.box[3] - pt.box[1]), 0.0f);
				}
				pt.k[(size_t)(y - pt.box[1]) * w + (x - pt.box[0])] = b.add ? k : std::min(1.0f, k);
			};
			pt.any = b.hx > 0 ? boxEach(ax0, ay0, ax1, ay1, b.x, b.y, b.hx, b.hy, b.a, pt.box, keep)
				: blobEach(ax0, ay0, ax1, ay1, b.x, b.y, b.r, b.ring, b.a, pt.box, keep);
		});
		for (; first < blobs.size(); ++first)
		{
			const Patch &pt = patches[first];
			// a blob that touches nothing (every weight 0) leaves the pixels as they are
			if (pt.any && !pt.k.empty() && !gw.shade(blobs[first].add ? HdGpuWorld::ADD : HdGpuWorld::OVER, pt.k,
				pt.box[0], pt.box[1], pt.box[2], pt.box[3], blobs[first].col))
			{
				break;
			}
		}
		// with VERIFY the processor draws them all; refused at `first`, the card's world came back with those before
		if (verify)
		{
			first = 0;
		}
	}
	// a band draws the blobs that reach into it, in the same order as every other band (as blob's reach)
	const int bands = first < blobs.size() ? (ay1 - ay0 + BAND - 1) / BAND : 0;
	HdWorkers::instance().run(bands, [&](int band)
	{
		const int y0 = ay0 + band * BAND, y1 = std::min(ay1, y0 + BAND);
		for (size_t i = first; i < blobs.size(); ++i)
		{
			const Blob &b = blobs[i];
			const float reach = b.hx > 0 ? std::max(b.hx, b.hy) + 2 : b.ring + 2.8f * (b.ring > 0 ? 0.7f : 0.6f) * b.r + 1;
			if (b.y + reach >= y0 && b.y - reach < y1)
			{
				if (b.hx > 0)
				{
					boxFill(world, ax0, y0, ax1, y1, b.x, b.y, b.hx, b.hy, b.col, b.a, b.add);
				}
				else
				{
					blob(world, ax0, y0, ax1, y1, b.x, b.y, b.r, b.ring, b.col, b.a, b.add);
				}
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
