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
/*
 * What the weather carries (HdWeather.h, docs/research/battle-weather-2026-11-11.md): tumbleweeds, dust devils, a tornado,
 * lightning bolts and the sound. Everything is a function of the battle's weather seed and the clock; nothing comes from
 * the game's random numbers and nothing of the battle is changed.
 */
#include "HdWeather.h"
#include "HdSprites.h"
#include "HdWorkers.h"
#include "FileMap.h"
#include "Logger.h"
#include "Options.h"
#include "Sound.h"
#include <SDL_mixer.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <tuple>
#include <vector>

namespace OpenXcom
{

namespace HdWeather
{

namespace
{
	const float PI = 3.14159265f;

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
	inline float unit(Uint32 h) { return (h >> 8) * (1.0f / 16777216.0f); }
	inline float clamp01(float x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }
	inline float smooth(float e0, float e1, float x)
	{
		float t = (x - e0) / (e1 - e0);
		t = t < 0 ? 0 : (t > 1 ? 1 : t);
		return t * t * (3 - 2 * t);
	}

	/// A float picture with straight colour and alpha, painted "over" and turned into an HdFrame at the end.
	struct Paint
	{
		int w = 0, h = 0;
		std::vector<float> r, g, b, a;
		Paint(int w_, int h_) : w(w_), h(h_), r((size_t)w_ * h_, 0), g(r), b(r), a(r) {}
		void over(int x, int y, float cr, float cg, float cb, float ca)
		{
			if (x < 0 || y < 0 || x >= w || y >= h || ca <= 0)
				return;
			const size_t i = (size_t)y * w + x;
			const float na = ca + a[i] * (1 - ca);
			if (na <= 0)
				return;
			r[i] = (cr * ca + r[i] * a[i] * (1 - ca)) / na;
			g[i] = (cg * ca + g[i] * a[i] * (1 - ca)) / na;
			b[i] = (cb * ca + b[i] * a[i] * (1 - ca)) / na;
			a[i] = na;
		}
		/// A segment `halfWidth` wide (pixels) with an antialiased edge `soft` pixels wide.
		void segment(float x0, float y0, float x1, float y1, float halfWidth, float soft, float cr, float cg, float cb, float ca)
		{
			const float pad = halfWidth + soft + 1;
			const int bx0 = std::max(0, (int)std::floor(std::min(x0, x1) - pad)), bx1 = std::min(w - 1, (int)std::ceil(std::max(x0, x1) + pad));
			const int by0 = std::max(0, (int)std::floor(std::min(y0, y1) - pad)), by1 = std::min(h - 1, (int)std::ceil(std::max(y0, y1) + pad));
			const float dx = x1 - x0, dy = y1 - y0, len2 = dx * dx + dy * dy;
			// a line thinner than a pixel is drawn a pixel wide and fainter
			const float hw = std::max(halfWidth, 0.5f), thin = std::min(1.0f, halfWidth / 0.5f);
			for (int y = by0; y <= by1; ++y)
			{
				for (int x = bx0; x <= bx1; ++x)
				{
					const float px = x + 0.5f, py = y + 0.5f;
					float t = len2 > 0 ? ((px - x0) * dx + (py - y0) * dy) / len2 : 0;
					t = t < 0 ? 0 : (t > 1 ? 1 : t);
					const float ex = x0 + dx * t - px, ey = y0 + dy * t - py;
					const float d = std::sqrt(ex * ex + ey * ey);
					const float cov = clamp01((hw + soft * 0.5f - d) / std::max(soft, 0.001f)) * thin;
					if (cov > 0.003f)
						over(x, y, cr, cg, cb, ca * cov);
				}
			}
		}
		void toFrame(HdFrame &f) const
		{
			f.width = w;
			f.height = h;
			f.pixels.assign((size_t)w * h, 0);
			for (size_t i = 0; i < f.pixels.size(); ++i)
			{
				if (a[i] > 0.004f)
				{
					auto c8 = [](float v) { return (Uint32)std::lround(std::max(0.0f, std::min(255.0f, v))); };
					f.pixels[i] = (c8(a[i] * 255) << 24) | (c8(r[i]) << 16) | (c8(g[i]) << 8) | c8(b[i]);
				}
			}
			f.generated = true;
			f.buildSpans();
		}
	};

	bool dusty(Biome b) { return b == B_DESERT || b == B_STEPPE || b == B_WASTE; }

	/// The test switch OXCE_HD_WEATHER_EXTRA=all: every extra the kind can have, in every battle (screenshots, checks).
	bool forcedExtras()
	{
		const char *e = std::getenv("OXCE_HD_WEATHER_EXTRA");
		return e && std::string(e) == "all";
	}
}

Extras extras(Kind kind, Biome biome, Uint32 seed)
{
	Extras ex;
	const bool all = forcedExtras();
	// the test switch OXCE_HD_WEATHER_EXTRA=none: the weather without its extras (the frames "before" of the page)
	const char *e = std::getenv("OXCE_HD_WEATHER_EXTRA");
	if (e && std::string(e) == "none")
		return ex;
	const float u = unit(hash(seed, 0x7E1A));
	switch (kind)
	{
	case WIND:
		if (dusty(biome) || all)
		{
			ex.tumbleweeds = biome == B_DESERT ? 5 : 4;
			ex.devils = 2;
			ex.tornado = all || u < 0.35f;
			ex.tornadoLook = 0;
		}
		break;
	case SANDSTORM:
		ex.tumbleweeds = 3;
		ex.tornado = all || u < 0.2f;
		ex.tornadoLook = 0;
		break;
	case THUNDER:
		ex.bolts = true;
		if (biome == B_STEPPE || biome == B_WASTE || all)
		{
			ex.tornado = all || u < 0.3f;
			ex.tornadoLook = 1;
		}
		break;
	default:
		break;
	}
	return ex;
}

void windDir(Kind kind, float &du, float &dv)
{
	// the particles' angle (degrees from straight down, positive to the right; HdWeather.cpp lookOf) on the screen, then
	// on the ground: a screen step (dx, dy) is the tile step du - dv = dx / 16, du + dv = dy / 8
	float deg = 100;
	switch (kind)
	{
	case SANDSTORM: deg = 96; break;
	case BLIZZARD: deg = 60; break;
	case WHITEOUT: deg = 78; break;
	case DRIZZLE: case RAIN: case DOWNPOUR: case THUNDER: deg = 70; break;
	default: break;
	}
	const float a = deg * PI / 180;
	const float dx = std::sin(a), dy = std::cos(a);
	du = (dx / 16 + dy / 8) / 2;
	dv = (dy / 8 - dx / 16) / 2;
	const float n = std::sqrt(du * du + dv * dv);
	du /= n;
	dv /= n;
}

// ---- tumbleweeds

namespace
{
	const int SHAPES = 3;
	/// The ball's radius in base pixels of each shape, its hop and the turns of a frame set.
	const float BALL_R[SHAPES] = { 4.6f, 5.4f, 6.3f };
	const float HOP = 3.6f;
	const int TURNS = 24;
	/// The look of the ball: the dense dark one (look B, chosen by Vitali 11.11) unless OXCE_HD_WEATHER_LOOK=a asks for the light
	/// sparse one of the page.
	bool lookB()
	{
		const char *e = std::getenv("OXCE_HD_WEATHER_LOOK");
		return !(e && (e[0] == 'a' || e[0] == 'A'));
	}

	struct Pt { float x, y, z; };
	/// The twigs of a shape: polylines on and inside a ball of radius 1.
	const std::vector<std::vector<Pt>> &twigs(int shape)
	{
		static std::vector<std::vector<Pt>> cache[SHAPES];
		static std::mutex lock;
		std::lock_guard<std::mutex> guard(lock);
		std::vector<std::vector<Pt>> &out = cache[shape];
		if (!out.empty())
			return out;
		const bool dense = lookB();
		const int n = dense ? 46 : 30;
		for (int i = 0; i < n; ++i)
		{
			const Uint32 h = hash(0x7B11u + shape, i);
			// a start on the sphere and a wandering walk near its surface
			float z = unit(hash(h, 1)) * 2 - 1, phi = unit(hash(h, 2)) * 2 * PI;
			const float rr = 0.62f + 0.38f * unit(hash(h, 3));
			Pt p { std::sqrt(1 - z * z) * std::cos(phi) * rr, std::sqrt(1 - z * z) * std::sin(phi) * rr, z * rr };
			std::vector<Pt> line { p };
			Pt d { unit(hash(h, 4)) - 0.5f, unit(hash(h, 5)) - 0.5f, unit(hash(h, 6)) - 0.5f };
			const int steps = 4 + (int)(hash(h, 7) % 4);
			for (int s = 0; s < steps; ++s)
			{
				const Uint32 hs = hash(h, 10 + s);
				d.x += (unit(hash(hs, 1)) - 0.5f) * 0.9f;
				d.y += (unit(hash(hs, 2)) - 0.5f) * 0.9f;
				d.z += (unit(hash(hs, 3)) - 0.5f) * 0.9f;
				const float dl = std::sqrt(d.x * d.x + d.y * d.y + d.z * d.z) + 1e-6f;
				const float step = 0.3f + 0.12f * unit(hash(hs, 4));
				Pt q { p.x + d.x / dl * step, p.y + d.y / dl * step, p.z + d.z / dl * step };
				// keep it near the shell: the ball is hollow-ish, a tangle on its surface
				const float ql = std::sqrt(q.x * q.x + q.y * q.y + q.z * q.z) + 1e-6f;
				const float want = std::min(1.0f, std::max(0.55f, ql));
				q.x *= want / ql; q.y *= want / ql; q.z *= want / ql;
				line.push_back(q);
				p = q;
			}
			out.push_back(line);
		}
		// a few stems through the middle
		for (int i = 0; i < (dense ? 7 : 4); ++i)
		{
			const Uint32 h = hash(0x51E3u + shape, i);
			Pt a { unit(hash(h, 1)) * 2 - 1, unit(hash(h, 2)) * 2 - 1, unit(hash(h, 3)) * 2 - 1 };
			const float al = std::sqrt(a.x * a.x + a.y * a.y + a.z * a.z) + 1e-6f;
			a.x /= al; a.y /= al; a.z /= al;
			out.push_back({ { a.x * 0.85f, a.y * 0.85f, a.z * 0.85f }, { a.x * 0.1f, a.y * 0.1f, a.z * 0.1f }, { -a.x * 0.7f, -a.y * 0.7f, -a.z * 0.7f } });
		}
		return out;
	}

	std::mutex rollLock;
	std::map<std::tuple<int, int, int>, HdFrame> rollFrames;
	std::map<std::pair<int, int>, HdFrame> rollShadows;
}

const HdFrame &rollFrame(int k, int shape, float turn)
{
	shape = ((shape % SHAPES) + SHAPES) % SHAPES;
	float t = std::fmod(turn, 2 * PI);
	if (t < 0)
		t += 2 * PI;
	const int step = std::min(TURNS - 1, (int)(t / (2 * PI) * TURNS));
	{
		std::lock_guard<std::mutex> guard(rollLock);
		auto found = rollFrames.find(std::make_tuple(k, shape, step));
		if (found != rollFrames.end())
			return found->second;
	}
	const bool dense = lookB();
	const float R = BALL_R[shape];
	const int side = (int)std::ceil((2 * R + 2) * k);
	Paint p(side, side);
	// the ball turns about the ground's axis across the way it rolls (to the right on the screen): the camera looks down
	// at 30 degrees, so that axis is (0, sin 30, cos 30) in screen coordinates (x right, y down, z to the viewer)
	const float ang = (step + 0.5f) * 2 * PI / TURNS;
	const float ax = 0, ay = 0.5f, az = 0.866f;
	const float c = std::cos(ang), s = std::sin(ang);
	auto rot = [&](const Pt &v)
	{
		const float dot = ax * v.x + ay * v.y + az * v.z;
		const float cx = ay * v.z - az * v.y, cy = az * v.x - ax * v.z, cz = ax * v.y - ay * v.x;
		return Pt { v.x * c + cx * s + ax * dot * (1 - c), v.y * c + cy * s + ay * dot * (1 - c), v.z * c + cz * s + az * dot * (1 - c) };
	};
	struct Seg { Pt a, b; };
	std::vector<Seg> segs;
	for (const auto &line : twigs(shape))
		for (size_t i = 1; i < line.size(); ++i)
			segs.push_back({ rot(line[i - 1]), rot(line[i]) });
	std::sort(segs.begin(), segs.end(), [](const Seg &l, const Seg &r) { return l.a.z + l.b.z < r.a.z + r.b.z; });
	const float cxp = side * 0.5f, cyp = side - (R + 0.6f) * k;
	// dry twigs: dark straw at the back, pale straw in front; the dense look is browner
	const float dark[3] = { dense ? 78.0f : 104.0f, dense ? 58.0f : 80.0f, dense ? 38.0f : 52.0f };
	const float light[3] = { dense ? 168.0f : 205.0f, dense ? 132.0f : 172.0f, dense ? 86.0f : 118.0f };
	for (const Seg &sg : segs)
	{
		const float z = (sg.a.z + sg.b.z) * 0.5f;
		const float lit = clamp01(0.5f + 0.5f * z) * 0.75f + clamp01(0.5f - 0.5f * (sg.a.y + sg.b.y) * 0.5f) * 0.25f;
		const float cr = dark[0] + (light[0] - dark[0]) * lit, cg = dark[1] + (light[1] - dark[1]) * lit, cb = dark[2] + (light[2] - dark[2]) * lit;
		const float alpha = 0.6f + 0.38f * clamp01(0.5f + 0.5f * z);
		p.segment(cxp + sg.a.x * R * k, cyp + sg.a.y * R * k, cxp + sg.b.x * R * k, cyp + sg.b.y * R * k,
			(dense ? 0.42f : 0.36f) * k, 1.0f, cr, cg, cb, alpha);
	}
	HdFrame f;
	p.toFrame(f);
	std::lock_guard<std::mutex> guard(rollLock);
	HdFrame &stored = rollFrames[std::make_tuple(k, shape, step)];
	if (stored.width == 0)
		stored = std::move(f);
	return stored;
}

const HdFrame &rollShadow(int k, int shape)
{
	shape = ((shape % SHAPES) + SHAPES) % SHAPES;
	std::lock_guard<std::mutex> guard(rollLock);
	HdFrame &f = rollShadows[std::make_pair(k, shape)];
	if (f.width)
		return f;
	const float R = BALL_R[shape];
	const int w = (int)std::ceil((2 * R + 3) * k), h = (int)std::ceil((R + 3) * k);
	Paint p(w, h);
	for (int y = 0; y < h; ++y)
	{
		for (int x = 0; x < w; ++x)
		{
			const float dx = ((x + 0.5f) - w * 0.5f) / (R * 0.95f * k), dy = ((y + 0.5f) - h * 0.5f) / (R * 0.45f * k);
			const float d = std::sqrt(dx * dx + dy * dy);
			p.over(x, y, 20, 16, 12, 0.3f * (1 - smooth(0.35f, 1.0f, d)));
		}
	}
	p.toFrame(f);
	return f;
}

namespace
{
	/// Where a run starts: chosen once, near the view of the moment it is first asked (so the run crosses what the player
	/// looks at), then kept to its end - the camera moving later does not move the ball.
	struct Start { Uint32 key = 0; bool set = false, ok = false; float u = 0, v = 0, when = 0; };
	Start rollStart[ROLLS], devilStart[TWISTERS], tornadoStart;
	std::mutex startLock;

	/// The start of run `key`: up to twelve tries of `pick(try, u, v)`, kept when `fits(u, v)`; `now` is kept as the
	/// memo's `when` (the moment of the choice).
	template <typename Pick, typename Fits>
	bool startOf(Start &memo, Uint32 key, Pick pick, Fits fits, float &u, float &v, float now = 0)
	{
		std::lock_guard<std::mutex> guard(startLock);
		if (!memo.set || memo.key != key)
		{
			memo.key = key;
			memo.set = true;
			memo.ok = false;
			memo.when = now;
			for (int t = 0; t < 12 && !memo.ok; ++t)
			{
				pick(t, memo.u, memo.v);
				memo.ok = fits(memo.u, memo.v);
			}
		}
		u = memo.u;
		v = memo.v;
		return memo.ok;
	}

	bool insideMap(float u, float v, int mapW, int mapL)
	{
		return u >= 0.5f && v >= 0.5f && u <= mapW - 0.5f && v <= mapL - 0.5f;
	}
}

int rolls(const Extras &ex, Kind kind, Uint32 seed, Uint32 ms, float power, int mapW, int mapL, float viewU, float viewV,
	ClearFn clear, void *ctx, Roll out[ROLLS])
{
	if (ex.tumbleweeds <= 0 || mapW <= 0 || mapL <= 0)
		return 0;
	float du, dv;
	windDir(kind, du, dv);
	// a tile along the wind is this many base pixels on the screen (the ball turns by the way it goes there)
	const float screenPerTile = std::sqrt((du - dv) * (du - dv) * 256 + (du + dv) * (du + dv) * 64);
	int n = 0;
	const bool all = forcedExtras();
	for (int slot = 0; slot < std::min(ex.tumbleweeds, ROLLS); ++slot)
	{
		const Uint32 hs = hash(seed, 0x70B1u, slot);
		const Uint32 period = 15000 + hs % 11000;
		const Uint32 at = ms + hash(hs, 1) % period;
		const Uint32 cycle = at / period;
		const float tau = (at % period) / 1000.0f;
		const Uint32 hc = hash(hs, cycle);
		// a calmer turn leaves more of the cycles empty
		if (!all && unit(hash(hc, 1)) > 0.45f + 0.5f * power)
			continue;
		// its own way: the wind turned by up to 14 degrees, its own speed and wobble
		const float turnBy = (unit(hash(hc, 4)) - 0.5f) * 0.5f;
		const float wu = du * std::cos(turnBy) - dv * std::sin(turnBy), wv = du * std::sin(turnBy) + dv * std::cos(turnBy);
		const float pu = -wv, pv = wu;
		// it sets off about the middle of the view, mostly upwind of it, to one side or the other - at the moment the run is
		// first asked about (on a loaded battle that is often halfway through it): the run goes from there
		float su, sv;
		auto pick = [&](int t, float &u, float &v)
		{
			const float back = -4 + 14 * unit(hash(hc, 30, t)), lat = (unit(hash(hc, 40, t)) - 0.5f) * 28;
			u = viewU - wu * back + pu * lat;
			v = viewV - wv * back + pv * lat;
		};
		auto fits = [&](float u, float v) { return insideMap(u, v, mapW, mapL) && clear(ctx, u, v, u, v); };
		if (!startOf(rollStart[slot], hc, pick, fits, su, sv, tau))
			continue;
		const float from = rollStart[slot].when;
		if (tau < from)
			continue;
		const float speed = (1.1f + 0.7f * unit(hash(hc, 5))) * (0.75f + 0.25f * power);
		const float phase = unit(hash(hc, 6)) * 6.28f, wobble = 0.1f + 0.15f * unit(hash(hc, 7));
		const float life = period / 1000.0f * 0.8f;
		const int shape = (int)(hash(hc, 8) % SHAPES);
		auto place = [&](float dist, float &u, float &v)
		{
			u = su + wu * dist + pu * wobble * std::sin(dist * 0.9f + phase);
			v = sv + wv * dist + pv * wobble * std::sin(dist * 0.9f + phase);
		};
		if (from > life - 1.5f)
			continue;
		// the gusts: the way gone by the time r of the run, never going back
		const float r = tau - from;
		const float want = speed * r + 0.3f * (std::sin(1.3f * r + phase) - std::sin(phase));
		float gone = 0, u = su, v = sv, stoppedAt = -1;
		const float stepLen = 0.2f;
		while (gone + stepLen <= want)
		{
			float nu, nv;
			place(gone + stepLen, nu, nv);
			if (!clear(ctx, u, v, nu, nv))
			{
				stoppedAt = gone / std::max(0.1f, speed);
				break;
			}
			gone += stepLen;
			u = nu;
			v = nv;
		}
		if (stoppedAt < 0 && want > gone)
		{
			float nu, nv;
			place(want, nu, nv);
			if (clear(ctx, u, v, nu, nv))
			{
				gone = want;
				u = nu;
				v = nv;
			}
		}
		float alpha = smooth(0, 0.5f, r) * (1 - smooth(life - 0.7f, life, tau));
		float hop = 0;
		float turn = gone * screenPerTile / BALL_R[shape];
		if (stoppedAt >= 0)
		{
			// caught by a wall: it shivers in the wind a moment and is gone
			const float since = std::max(0.0f, r - stoppedAt);
			alpha *= 1 - smooth(1.0f, 1.7f, since);
			turn += 0.18f * std::sin(since * 23) * (1 - smooth(0, 1.0f, since));
		}
		else
		{
			const float hopLen = 1.25f;
			const int bounce = (int)(gone / hopLen);
			hop = HOP * (0.35f + 0.65f * unit(hash(hc, 20 + bounce))) * std::fabs(std::sin(PI * gone / hopLen));
		}
		if (alpha <= 0.01f)
			continue;
		out[n++] = Roll { u, v, hop, turn, alpha, shape, hc };
	}
	return n;
}

// ---- twisters

namespace
{
	struct TwisterLook
	{
		/// Base pixels: height, base and top radius, bend; frames of a turn; the strongest alpha.
		float height, rBase, rTop, bend;
		int frames;
		float alphaMax;
		/// The skirt of dust at the base: its radius and height.
		float skirtR, skirtH;
	};
	const TwisterLook DEVIL { 50, 1.6f, 11, 3, 12, 0.62f, 9, 5 };
	const TwisterLook TORNADO { 150, 4.0f, 32, 9, 16, 0.94f, 21, 11 };

	std::mutex twisterLock;
	std::map<std::tuple<int, int, int>, std::vector<HdFrame>> twisterSets;

	const std::vector<HdFrame> &twisterBank(int k, int big, int look)
	{
		{
			std::lock_guard<std::mutex> guard(twisterLock);
			auto found = twisterSets.find(std::make_tuple(k, big, look));
			if (found != twisterSets.end())
				return found->second;
		}
		const TwisterLook &L = big ? TORNADO : DEVIL;
		// the dust a shade darker than the sand it is lifted from (on a bright desert a pale funnel is lost), the storm grey
		// the dust tornado is denser and darker, with a crisper funnel (Vitali 11.11: «плотнее»); the devils and the grey one stay
		const bool thick = big && !look;
		const float col[3] = { look ? 100.0f : thick ? 136.0f : 158.0f, look ? 103.0f : thick ? 100.0f : 120.0f,
			look ? 112.0f : thick ? 64.0f : 80.0f };
		const float boost = thick ? 1.4f : 1.0f, edge0 = thick ? 0.88f : 0.82f, edge1 = thick ? 1.1f : 1.18f;
		const float wBase = 2 * (std::max(L.rTop * 1.2f, L.skirtR * 1.15f) + L.bend + 3);
		const int W = (int)std::ceil(wBase * k), H = (int)std::ceil((L.height + 8) * k);
		const float baseY = L.height + 3;
		const Uint32 started = SDL_GetTicks();
		std::vector<HdFrame> bank(L.frames);
		HdWorkers::instance().run(L.frames, [&](int f)
		{
			Paint p(W, H);
			const float rho = 2 * PI * f / L.frames;
			const float wob = 0.5f * std::sin(rho);
			for (int py = 0; py < H; ++py)
			{
				const float Y = (py + 0.5f) / k;
				const float s = (baseY - Y) / L.height;
				const float rr = L.rBase + (L.rTop - L.rBase) * std::pow(clamp01(s), 1.7f);
				const float cx = L.bend * std::sin(PI * s * 1.2f + wob) * std::pow(clamp01(s), 0.8f);
				for (int px = 0; px < W; ++px)
				{
					const float X = (px + 0.5f) / k - wBase * 0.5f;
					float af = 0, lf = 1;
					if (s > -0.02f && s < 1.08f)
					{
						const float q = (X - cx) / rr;
						if (std::fabs(q) < 1.2f)
						{
							const float qc = std::max(-1.0f, std::min(1.0f, q));
							const float th = std::asin(qc);
							auto dens = [&](float t)
							{
								return 0.55f + 0.25f * std::sin(3 * (t + rho) + 9 * s) + 0.2f * std::sin(5 * (t + rho) - 13 * s + 1.3f)
									+ 0.12f * std::sin(9 * (t + rho) + 21 * s + 0.4f);
							};
							const float path = std::sqrt(std::max(0.0f, 1 - qc * qc));
							const float d = (dens(th) + 0.7f * dens(PI - th)) * 0.6f * boost * (0.35f + 0.65f * path);
							const float edge = 1 - smooth(edge0, edge1, std::fabs(q));
							const float ends = smooth(-0.02f, 0.05f, s) * (1 - smooth(0.86f, 1.06f, s));
							af = L.alphaMax * clamp01(d) * edge * ends;
							lf = (0.8f - 0.22f * qc + 0.12f * (dens(th) - 0.55f)) * (0.82f + 0.18f * clamp01(s));
						}
					}
					// the skirt: a low dome of dust swirling about the base
					float as = 0, ls = 0.9f;
					{
						const float dx = X / L.skirtR, dyUp = (baseY - Y) / L.skirtH;
						const float dsq = dx * dx + (dyUp > 0 ? dyUp * dyUp : dyUp * dyUp * 9);
						if (dsq < 1.2f)
						{
							const float a = std::atan2(dyUp, dx);
							const float swirl = 0.55f + 0.25f * std::sin(4 * a + 2 * rho) + 0.2f * std::sin(7 * a - 3 * rho + 1.7f);
							as = L.alphaMax * 0.75f * (1 - smooth(0.25f, 1.1f, dsq)) * clamp01(swirl);
							ls = 0.78f + 0.2f * clamp01(dyUp) - 0.1f * dx;
						}
					}
					const float a = 1 - (1 - af) * (1 - as);
					if (a > 0.004f)
					{
						const float l = (af * lf + as * ls) / std::max(1e-4f, af + as);
						p.over(px, py, col[0] * l, col[1] * l, col[2] * l, a);
					}
				}
			}
			p.toFrame(bank[f]);
		});
		Log(LOG_INFO) << "HD weather: " << (big ? "tornado" : "dust devil") << " frames x" << k << " (" << L.frames << ", " << W << "x" << H
			<< ") baked in " << (SDL_GetTicks() - started) << " ms";
		std::lock_guard<std::mutex> guard(twisterLock);
		std::vector<HdFrame> &stored = twisterSets[std::make_tuple(k, big, look)];
		if (stored.empty())
			stored = std::move(bank);
		return stored;
	}
}

int twisters(const Extras &ex, Kind kind, Uint32 seed, Uint32 ms, int mapW, int mapL, float viewU, float viewV, OpenFn open,
	AwayFn away, void *ctx, Twister out[TWISTERS])
{
	int n = 0;
	if (mapW <= 0 || mapL <= 0)
		return 0;
	float du, dv;
	windDir(kind, du, dv);
	const bool all = forcedExtras();
	if (ex.tornado)
	{
		// one tornado going along the wind, slow, past the middle of the view as its pass begins; a quiet stretch between
		// the passes (the test switch: a pass every 90 s, the first a few seconds in)
		const Uint32 ht = hash(seed, 0x70AD);
		const Uint32 period = all ? 90000 : 150000 + ht % 60000;
		const Uint32 at = ms + (all ? period / 2 - 14000 : ht % period);
		const Uint32 cycle = at / period;
		const float tau = (at % period) / 1000.0f, length = period / 1000.0f;
		const Uint32 hc = hash(ht, cycle);
		float cu, cv;
		auto pick = [&](int t, float &u, float &v)
		{
			// three to nine tiles upwind of the view's middle and up to seven aside, so it goes across the view and not out of it
			// (a spread of fifteen tiles each way put it off the screen or off the map most of the time); with the view at the
			// map's edge upwind there is no map, so the later tries look anywhere within six tiles of the middle
			const float back = t < 6 ? 3 + 6 * unit(hash(hc, 50, t)) : (unit(hash(hc, 50, t)) - 0.5f) * 12;
			const float lat = (unit(hash(hc, 60, t)) - 0.5f) * (t < 6 ? 14 : 12);
			u = viewU - du * back - dv * lat;
			v = viewV - dv * back + du * lat;
		};
		// it stands off the units (four tiles from the own ones, the spotted enemies and the cursor) and its way a few tiles on
		// and back keeps three off them - a crowded battle has no wider room; nearer it thins out (Map::hdWeatherOver)
		auto fits = [&](float u, float v)
		{
			if (!insideMap(u, v, mapW, mapL) || away(ctx, u, v) < 4)
				return false;
			for (int s = -4; s <= 4; s += 2)
			{
				const float pu = u + du * s, pv = v + dv * s;
				if (insideMap(pu, pv, mapW, mapL) && away(ctx, pu, pv) < 3)
					return false;
			}
			return true;
		};
		if ((all || unit(hash(hc, 1)) < 0.75f) && startOf(tornadoStart, hc, pick, fits, cu, cv, tau))
		{
			// the chosen point is where it stands at the moment of the choice, and it goes on along the wind from there
			const float along = (tau - tornadoStart.when) * 0.5f;
			const float side = 2.5f * std::sin(tau * 0.09f + unit(hash(hc, 4)) * 6.28f);
			const float u = cu + du * along - dv * side, v = cv + dv * along + du * side;
			// it shows over the map only: it fades in a few tiles before the edge, and at the ends of its pass
			const float inside = std::min(std::min(u, v), std::min(mapW - u, mapL - v));
			const float a = smooth(-4, 2, inside) * smooth(0, 8, tau) * (1 - smooth(length - 8, length, tau));
			if (a > 0.01f)
				out[n++] = Twister { u, v, a, 1, hc };
		}
	}
	for (int slot = 0; slot < ex.devils && n < TWISTERS; ++slot)
	{
		const Uint32 hs = hash(seed, 0xDE71u, slot);
		const Uint32 period = 28000 + hs % 17000;
		const Uint32 at = ms + hash(hs, 1) % period;
		const Uint32 cycle = at / period;
		const float tau = (at % period) / 1000.0f;
		const Uint32 hc = hash(hs, cycle);
		const float life = 8 + 6 * unit(hash(hc, 1));
		if (tau >= life)
			continue;
		float su, sv;
		auto pick = [&](int t, float &u, float &v)
		{
			u = viewU + (unit(hash(hc, 70, t)) - 0.5f) * 20;
			v = viewV + (unit(hash(hc, 80, t)) - 0.5f) * 20;
		};
		auto fits = [&](float u, float v) { return insideMap(u, v, mapW, mapL) && open(ctx, u, v) && away(ctx, u, v) >= 4; };
		if (!startOf(devilStart[std::min(slot, TWISTERS - 1)], hc, pick, fits, su, sv))
			continue;
		const float ph = unit(hash(hc, 4)) * 6.28f;
		const float u = su + du * 0.5f * tau - dv * 0.9f * std::sin(tau * 0.6f + ph);
		const float v = sv + dv * 0.5f * tau + du * 0.9f * std::sin(tau * 0.6f + ph);
		const float a = smooth(0, 1.5f, tau) * (1 - smooth(life - 2, life, tau));
		if (a > 0.01f)
			out[n++] = Twister { u, v, a, 0, hc };
	}
	return n;
}

const HdFrame &twisterFrame(int k, int big, int look, Uint32 ms, int &baseX, int &baseY)
{
	const TwisterLook &L = big ? TORNADO : DEVIL;
	const std::vector<HdFrame> &bank = twisterBank(k, big, look);
	const Uint32 frameMs = big ? 75 : 55;
	const HdFrame &f = bank[(ms / frameMs) % bank.size()];
	baseX = f.width / 2;
	baseY = (int)std::lround((L.height + 3) * k);
	return f;
}

// ---- lightning bolts

namespace
{
	std::mutex boltLock;
	struct BoltKey { Uint32 slot; int k, w, h; Uint32 seed; };
	BoltKey boltKey { 0xFFFFFFFFu, 0, 0, 0, 0 };
	HdFrame boltFrame;
	int boltX = 0, boltY = 0;
	bool boltNone = true;

	/// Bakes the bolt of strike `h`; false when it has nowhere to come down (no open ground away from the units in sight).
	bool bakeBolt(Uint32 h, int k, int width, int height, SpotFn spot, void *ctx)
	{
		// from above the top of the map down to a point on it, in the upper part of the view, never on a unit
		float gx = 0, gy = 0;
		bool found = false;
		for (int t = 0; t < 10 && !found; ++t)
		{
			gx = width * (0.08f + 0.84f * unit(hash(h, 2, t)));
			gy = height * (0.12f + 0.4f * unit(hash(h, 3, t)));
			found = spot(ctx, gx, gy);
		}
		if (!found)
		{
			boltFrame = HdFrame();
			return false;
		}
		const float sx = gx + width * 0.16f * (unit(hash(h, 4)) - 0.5f), sy = -10.0f * k;
		struct P2 { float x, y; };
		std::vector<P2> pts { { sx, sy }, { gx, gy } };
		float disp = std::sqrt((gx - sx) * (gx - sx) + (gy - sy) * (gy - sy)) * 0.16f;
		for (int level = 0; level < 6; ++level)
		{
			std::vector<P2> next;
			for (size_t i = 0; i + 1 < pts.size(); ++i)
			{
				const P2 a = pts[i], b = pts[i + 1];
				const float nx = -(b.y - a.y), ny = b.x - a.x, nl = std::sqrt(nx * nx + ny * ny) + 1e-6f;
				const float off = (unit(hash(h, 100 + level, (Uint32)i)) - 0.5f) * 2 * disp;
				next.push_back(a);
				next.push_back({ (a.x + b.x) * 0.5f + nx / nl * off, (a.y + b.y) * 0.5f + ny / nl * off });
			}
			next.push_back(pts.back());
			pts.swap(next);
			disp *= 0.55f;
		}
		// two or three forks off the upper two thirds
		std::vector<std::vector<P2>> forks;
		const int nf = 2 + (int)(hash(h, 5) % 2);
		for (int f = 0; f < nf; ++f)
		{
			const size_t from = (size_t)(pts.size() * (0.15f + 0.5f * unit(hash(h, 200 + f))));
			std::vector<P2> fork { pts[from] };
			const float dir = (unit(hash(h, 210 + f)) < 0.5f ? -1.0f : 1.0f);
			P2 p = pts[from];
			const float len = (gy - sy) * (0.12f + 0.12f * unit(hash(h, 220 + f)));
			for (int s = 0; s < 8; ++s)
			{
				p.x += dir * len / 8 * (0.5f + unit(hash(h, 230 + f, s)));
				p.y += len / 8 * (0.6f + 0.6f * unit(hash(h, 240 + f, s)));
				fork.push_back(p);
			}
			forks.push_back(fork);
		}
		float minX = 1e9f, minY = 1e9f, maxX = -1e9f, maxY = -1e9f;
		auto box = [&](const std::vector<P2> &l) { for (const P2 &p : l) { minX = std::min(minX, p.x); maxX = std::max(maxX, p.x); minY = std::min(minY, p.y); maxY = std::max(maxY, p.y); } };
		box(pts);
		for (auto &f : forks) box(f);
		const float pad = 9.0f * k;
		const int x0 = (int)std::floor(minX - pad), y0 = (int)std::floor(minY - pad);
		Paint p((int)std::ceil(maxX + pad) - x0, (int)std::ceil(maxY + pad) - y0);
		auto stroke = [&](const std::vector<P2> &l, float core, float glow, float strength)
		{
			for (size_t i = 0; i + 1 < l.size(); ++i)
				p.segment(l[i].x - x0, l[i].y - y0, l[i + 1].x - x0, l[i + 1].y - y0, glow * k, 4.0f * k, 150, 170, 255, 0.22f * strength);
			for (size_t i = 0; i + 1 < l.size(); ++i)
				p.segment(l[i].x - x0, l[i].y - y0, l[i + 1].x - x0, l[i + 1].y - y0, core * k, 1.0f, 240, 244, 255, 0.95f * strength);
		};
		for (size_t f = 0; f < forks.size(); ++f)
			stroke(forks[f], 0.35f, 2.2f, 0.65f);
		stroke(pts, 0.6f, 3.2f, 1.0f);
		p.toFrame(boltFrame);
		boltX = x0;
		boltY = y0;
		return true;
	}
}

const HdFrame *bolt(Kind kind, Uint32 seed, Uint32 ms, int k, int width, int height, SpotFn spot, void *ctx, int &x, int &y,
	float &opacity)
{
	if (kind != THUNDER)
		return nullptr;
	// the strike of lightning(), its bolt a little longer than the flash on the ground (that is over in a frame or two of
	// the map): the stroke, a flicker, the return stroke, the channel fading
	const Uint32 slot = ms / STRIKE_SLOT;
	const int at = strikeAt(seed, slot);
	const int t = at < 0 ? -1 : (int)(ms % STRIKE_SLOT) - at;
	if (t < 0 || t >= 460)
		return nullptr;
	const float flash = t < 110 ? 1.0f : t < 170 ? 0.35f : t < 280 ? 0.9f : 0.9f * (1 - (t - 280) / 180.0f);
	// not every strike shows its bolt
	const Uint32 h = hash(seed, 0xB017u, slot);
	if (unit(hash(h, 1)) > 0.65f && !forcedExtras())
		return nullptr;
	std::lock_guard<std::mutex> guard(boltLock);
	if (boltKey.slot != slot || boltKey.k != k || boltKey.w != width || boltKey.h != height || boltKey.seed != seed)
	{
		boltKey = BoltKey { slot, k, width, height, seed };
		boltNone = !bakeBolt(h, k, width, height, spot, ctx) || boltFrame.width == 0;
	}
	if (boltNone)
		return nullptr;
	x = boltX;
	y = boltY;
	opacity = flash;
	return &boltFrame;
}

// ---- the sound

namespace
{
	/// The loop of a kind and its loudness (the files are levelled alike: tools/sfx/weather_sfx_build.py).
	const char *loopOf(Kind kind, float &gain)
	{
		switch (kind)
		{
		case DRIZZLE: gain = 0.30f; return "drizzle";
		case RAIN: gain = 0.42f; return "rain";
		case DOWNPOUR: gain = 0.55f; return "downpour";
		case THUNDER: gain = 0.55f; return "downpour";
		case FOG: gain = 0.22f; return "fog";
		case FLAKES: gain = 0.18f; return "flakes";
		case SNOWFALL: gain = 0.26f; return "snowfall";
		case BLIZZARD: gain = 0.5f; return "blizzard";
		case WHITEOUT: gain = 0.6f; return "whiteout";
		case WIND: gain = 0.4f; return "wind";
		case SANDSTORM: gain = 0.55f; return "sandstorm";
		default: gain = 0; return nullptr;
		}
	}

	typedef std::vector<Sound::UniqueSoundPtr> Clips;
	std::map<std::string, Clips> bank;

	/// hd/SOUND/WEATHER/<name>.ogg, or <name>_1.ogg, <name>_2.ogg ... up to the first missing one.
	const Clips &sounds(const char *word)
	{
		const std::string name = word;
		auto it = bank.find(name);
		if (it != bank.end())
			return it->second;
		Clips &list = bank[name];
		auto add = [&](const std::string &file)
		{
			const std::string path = HdSprites::artPath("SOUND/WEATHER/" + file);
			if (!FileMap::fileExists(path))
				return false;
			Sound::UniqueSoundPtr clip = Sound::NewSound(Mix_LoadWAV_RW(FileMap::getRWops(path), SDL_TRUE));
			if (!clip)
			{
				Log(LOG_ERROR) << "HD weather sound " << path << ": " << Mix_GetError();
				return false;
			}
			list.push_back(std::move(clip));
			return true;
		};
		if (!add(name + ".ogg"))
		{
			for (int i = 1; add(name + "_" + std::to_string(i) + ".ogg"); ++i)
			{
			}
		}
		Log(LOG_INFO) << "HD weather sound: " << name << " - " << list.size() << " file(s)";
		return list;
	}

	/// A loop of ours on a channel, its volume ramped by the chunk's volume (a faded channel would keep the mixer's
	/// maximum volume after the fade, R-561).
	struct Loop
	{
		Mix_Chunk *chunk = nullptr;
		int channel = -1;
		float volume = 0;
		void stop()
		{
			if (chunk && channel >= 0 && Mix_Playing(channel) && Mix_GetChunk(channel) == chunk)
				Mix_HaltChannel(channel);
			chunk = nullptr;
			channel = -1;
			volume = 0;
		}
		/// Plays `c` looping (on `fixed`, or a free channel when -1) towards the volume `target` 0..1, `rate` a second.
		void steer(Mix_Chunk *c, int fixed, float target, float rate, float dt)
		{
			if (c != chunk)
			{
				// a new sound: the old one goes quiet first
				if (chunk && volume > 0.01f)
				{
					volume = std::max(0.0f, volume - rate * 2 * dt);
					Mix_VolumeChunk(chunk, (int)std::lround(volume * MIX_MAX_VOLUME));
					return;
				}
				stop();
				chunk = c;
			}
			if (!chunk)
				return;
			const bool playing = channel >= 0 && Mix_Playing(channel) && Mix_GetChunk(channel) == chunk;
			if (target <= 0.005f && volume <= 0.005f)
			{
				if (playing)
					Mix_HaltChannel(channel);
				channel = -1;
				volume = 0;
				return;
			}
			if (volume < target)
				volume = std::min(target, volume + rate * dt);
			else
				volume = std::max(target, volume - rate * dt);
			Mix_VolumeChunk(chunk, (int)std::lround(volume * MIX_MAX_VOLUME));
			if (!playing)
			{
				channel = Mix_PlayChannel(fixed, chunk, -1);
			}
		}
	};
	Loop air, roar;
	Uint32 lastMs = 0, lastThunderSlot = 0xFFFFFFFFu, lastRoll = 0, lastDevil = 0, pick = 0x2545F491u;

	void once(const char *name, float volume, float pan)
	{
		const Clips &list = sounds(name);
		if (list.empty())
			return;
		pick = mix(pick + 0x9E3779B9u);
		Mix_Chunk *clip = list[pick % list.size()].get();
		Mix_VolumeChunk(clip, (int)std::lround(clamp01(volume) * MIX_MAX_VOLUME));
		const int channel = Mix_PlayChannel(-1, clip, 0);
		if (channel >= 0 && Options::StereoSound)
		{
			int angle = (int)std::lround(std::max(-1.0f, std::min(1.0f, pan)) * 70);
			if (angle < 0)
				angle += 360;
			Mix_SetPosition(channel, angle, 0);
		}
	}

	bool canHear()
	{
		return Options::oxceHdWeatherSound && !Options::mute && Mix_QuerySpec(nullptr, nullptr, nullptr) != 0;
	}
}

void hear(const Hearing &h, Uint32 ms)
{
	if (!canHear())
	{
		silence();
		return;
	}
	const float dt = lastMs && ms > lastMs ? std::min(0.25f, (ms - lastMs) / 1000.0f) : 0.0f;
	lastMs = ms;
	float gain = 0;
	const char *loop = loopOf(h.kind, gain);
	const Clips *list = loop ? &sounds(loop) : nullptr;
	Mix_Chunk *chunk = list && !list->empty() ? (*list)[0].get() : nullptr;
	// channel 0 is reserved and the game plays nothing on it (Game::initAudio)
	air.steer(chunk, 0, gain * (0.55f + 0.45f * h.power), 0.35f, dt);

	// the tornado's roar while it is seen
	const Clips &roarList = sounds("tornado");
	roar.steer(roarList.empty() ? nullptr : roarList[0].get(), -1, 0.6f * clamp01(h.tornado), 0.25f, dt);

	// the thunder of a strike, late by its distance
	if (h.kind == THUNDER)
	{
		const Uint32 slot = ms / STRIKE_SLOT;
		const Uint32 hs = hash(h.seed, 0x7D0Du, slot);
		// the strike of lightning() in this slot; a quiet slot has none
		const int strike = strikeAt(h.seed, slot);
		if (strike >= 0 && slot != lastThunderSlot)
		{
			const int delay = 250 + (int)(hs % 2600);
			const int since = (int)(ms % STRIKE_SLOT) - strike - delay;
			if (since >= 0)
			{
				lastThunderSlot = slot;
				if (since < 600)
				{
					const bool close = delay < 1000;
					once(close ? "thunder_near" : "thunder_far", (close ? 0.85f : 0.6f) * (0.7f + 0.3f * h.power),
						unit(hash(hs, 9)) * 2 - 1);
				}
			}
		}
	}
	if (h.newRolls > 0 && ms - lastRoll > 3500)
	{
		lastRoll = ms;
		once("tumbleweed", 0.35f, h.rollPan);
	}
	if (h.newDevils > 0 && ms - lastDevil > 6000)
	{
		lastDevil = ms;
		once("dustdevil", 0.45f, h.devilPan);
	}
}

void silence()
{
	if (Mix_QuerySpec(nullptr, nullptr, nullptr) != 0)
	{
		air.stop();
		roar.stop();
	}
	else
	{
		air = Loop();
		roar = Loop();
	}
	lastMs = 0;
	lastThunderSlot = 0xFFFFFFFFu;
}

}

}
