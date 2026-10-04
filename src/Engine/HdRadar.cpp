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
#include "HdRadar.h"
#include <algorithm>
#include <climits>
#include <cmath>
#include <cstdint>
#include "HdUi.h"
#include "HdWorkers.h"

namespace OpenXcom
{

namespace
{

const double PI = 3.14159265358979323846;
const double TAU = 2 * PI;
/// One wave from the base to the edge of its radar, ms.
const int PULSE_MS = 6000;
/// The next radar's wave of the same base, ms after the previous one.
const int WAVE_GAP_MS = 1100;
/// A base set off less than this many game minutes ago is not set off again.
const long long GUARD_MINUTES = 10;
/// One turn of a craft's beam, ms: a slow analogue radar.
const int SWEEP_MS = 5000;
/// How far behind the beam its trail fades out, radians.
const double TRAIL = 1.3;
/// The width of a wave's bright front, as a part of its radar's range; its tail is four times that.
const double WAVE_WIDTH = 0.07;
/// Distances in the cache are stored in 1/8 world pixel; this is "far outside".
const Sint16 FAR_OUT = -32000;

// colours, 0xAARRGGBB: the alpha is the strongest the part is ever drawn
const Uint32 FILL = 0x1F48D8A8u;   // 12 %: the coverage itself
const Uint32 EDGE = 0x66A8FFE0u;   // 40 %: the line round the joint coverage
const float GLOW = 0.25f;          // the glow just inside the edge, a part of EDGE
const Uint32 WAVE = 0x149CF5D6u;   // 8 %: a pulse on top of the fill
const Uint32 TRAIL_COLOR = 0x1A9CF5D6u; // 10 %: the swept area behind a craft's beam
const Uint32 BEAM = 0x80C8FFE8u;   // 50 %: the beam

struct Vec
{
	double x, y, z;
};

/// The point of the globe in the view's frame: x, y as the orthographic projection (Globe::polarToCart)
/// in radii, z towards the viewer (> 0 on the visible side).
Vec viewVector(const HdRadar::View &view, double lon, double lat)
{
	const double dl = lon - view.cenLon;
	const double sc = std::sin(view.cenLat), cc = std::cos(view.cenLat);
	const double sl = std::sin(lat), cl = std::cos(lat);
	return Vec{ cl * std::sin(dl), cc * sl - sc * cl * std::cos(dl), cc * cl * std::cos(dl) + sc * sl };
}

/// The world unit vector of a point (for the distance between two of them).
Vec worldVector(double lon, double lat)
{
	return Vec{ std::cos(lat) * std::cos(lon), std::cos(lat) * std::sin(lon), std::sin(lat) };
}

double dot(const Vec &a, const Vec &b)
{
	return a.x * b.x + a.y * b.y + a.z * b.z;
}

double arc(const Vec &a, const Vec &b)
{
	return std::acos(std::max(-1.0, std::min(1.0, dot(a, b))));
}

/// A circle on the globe as the screen sees it: its centre in the view's frame and the box of world
/// pixels its visible part takes (with `margin` around).
struct Cap
{
	Vec c;
	double cosR;
	int x0, y0, x1, y1;
	bool visible;
};

Cap makeCap(const HdRadar::View &view, double lon, double lat, double range, int margin)
{
	Cap cap;
	cap.c = viewVector(view, lon, lat);
	cap.cosR = std::cos(range);
	cap.visible = false;
	double minX = 1e30, minY = 1e30, maxX = -1e30, maxY = -1e30;
	auto take = [&](double X, double Y)
	{
		minX = std::min(minX, X); maxX = std::max(maxX, X);
		minY = std::min(minY, Y); maxY = std::max(maxY, Y);
		cap.visible = true;
	};
	if (cap.c.z >= 0)
	{
		take(cap.c.x, cap.c.y);
	}
	// the rim: a pair of directions square to the centre
	const Vec &c = cap.c;
	Vec a = std::fabs(c.z) < 0.9 ? Vec{ 0, 0, 1 } : Vec{ 1, 0, 0 };
	Vec u{ a.y * c.z - a.z * c.y, a.z * c.x - a.x * c.z, a.x * c.y - a.y * c.x };
	const double ul = std::sqrt(dot(u, u));
	u = Vec{ u.x / ul, u.y / ul, u.z / ul };
	const Vec v{ c.y * u.z - c.z * u.y, c.z * u.x - c.x * u.z, c.x * u.y - c.y * u.x };
	const double sr = std::sin(range);
	const int RIM = 128;
	for (int i = 0; i < RIM; ++i)
	{
		const double phi = TAU * i / RIM, cp = std::cos(phi) * sr, sp = std::sin(phi) * sr;
		const double z = cap.cosR * c.z + cp * u.z + sp * v.z;
		if (z >= 0)
		{
			take(cap.cosR * c.x + cp * u.x + sp * v.x, cap.cosR * c.y + cp * u.y + sp * v.y);
		}
	}
	// where the circle runs over the globe's edge, the edge bounds what is seen of it
	const int LIMB = 256;
	for (int i = 0; i < LIMB; ++i)
	{
		const double phi = TAU * i / LIMB, lx = std::cos(phi), ly = std::sin(phi);
		if (lx * c.x + ly * c.y >= cap.cosR)
		{
			take(lx, ly);
		}
	}
	if (cap.visible)
	{
		cap.x0 = (int)std::floor(view.cx + minX * view.radius) - margin;
		cap.x1 = (int)std::ceil(view.cx + maxX * view.radius) + margin;
		cap.y0 = (int)std::floor(view.cy + minY * view.radius) - margin;
		cap.y1 = (int)std::ceil(view.cy + maxY * view.radius) + margin;
	}
	else
	{
		cap.x0 = cap.y0 = cap.x1 = cap.y1 = 0;
	}
	return cap;
}

/// The signed distance of a pixel (X, Y, Z in the view's frame) to the circle's rim on the screen,
/// world pixels, positive inside: the rim's equation over the length of its gradient on the screen.
inline double capDist(const Cap &cap, double X, double Y, double Z, double Zc, double radius)
{
	const double f = X * cap.c.x + Y * cap.c.y + Z * cap.c.z - cap.cosR;
	const double gx = cap.c.x - cap.c.z * X / Zc, gy = cap.c.y - cap.c.z * Y / Zc;
	const double gl = std::max(std::sqrt(gx * gx + gy * gy), 1e-4);
	return f * radius / gl;
}

inline float clamp01(double v)
{
	return v <= 0 ? 0.0f : v >= 1 ? 1.0f : (float)v;
}

/// A wave in flight: the band of the arc it lights now.
struct Wave
{
	Cap cap;          ///< its outer circle
	double cosLo, cosHi;
	double front, width;
	float amp;
};

/// A craft's beam.
struct Sweep
{
	Cap cap;
	double sx, sy;    ///< the craft on the screen, world pixels
	bool front;       ///< the craft is on the visible side
	double angle;     ///< the beam now, radians on the screen
};

}

/**
 * Sets the bases off for this cycle: the first base that may pulse starts now, and every base inside
 * the longest radar of one already set off starts when that wave's front reaches it; a base no wave
 * reaches starts now by itself. A base still pulsing, or set off less than GUARD_MINUTES game minutes
 * ago, is left out.
 */
void HdRadar::schedule(const std::vector<Source> &sources, Uint32 now, long long minute)
{
	std::vector<int> bases;
	for (int i = 0; i < (int)sources.size(); ++i)
	{
		if (sources[i].waves.empty()) continue;
		const auto old = _pulses.find(sources[i].id);
		if (old != _pulses.end() && old->second.any)
		{
			const Pulse &p = old->second;
			if ((int)(now - p.start) < (int)p.length || minute - p.minute < GUARD_MINUTES) continue;
		}
		bases.push_back(i);
	}
	const int n = (int)bases.size();
	std::vector<Vec> at(n);
	for (int i = 0; i < n; ++i)
	{
		at[i] = worldVector(sources[bases[i]].lon, sources[bases[i]].lat);
	}
	const double NOT_YET = 1e30;
	std::vector<double> start(n, NOT_YET);
	std::vector<bool> done(n, false);
	for (int first = 0; first < n; ++first)
	{
		if (start[first] < NOT_YET) continue;
		start[first] = 0;
		// the earliest wave front first, as on a map of roads
		for (;;)
		{
			int a = -1;
			for (int i = 0; i < n; ++i)
			{
				if (!done[i] && start[i] < NOT_YET && (a < 0 || start[i] < start[a])) a = i;
			}
			if (a < 0) break;
			done[a] = true;
			const double reach = sources[bases[a]].waves.front();
			for (int b = 0; b < n; ++b)
			{
				if (done[b]) continue;
				const double d = arc(at[a], at[b]);
				if (d <= reach)
				{
					start[b] = std::min(start[b], start[a] + PULSE_MS * d / reach);
				}
			}
		}
	}
	for (int i = 0; i < n; ++i)
	{
		const Source &s = sources[bases[i]];
		Pulse &p = _pulses[s.id];
		p.any = true;
		p.start = now + (Uint32)std::lround(start[i]);
		p.length = (Uint32)((std::min((int)s.waves.size(), MAX_WAVES) - 1) * WAVE_GAP_MS + PULSE_MS);
		p.minute = minute;
	}
}

/**
 * The bases' joint coverage as a signed distance per world pixel of the globe's widget. It stands
 * while the globe and the bases do, so it is worked out again only when they change, in bands on
 * the render threads.
 */
void HdRadar::updateDist(const View &view, const std::vector<Source> &sources)
{
	std::vector<double> key = { view.cenLon, view.cenLat, view.cx, view.cy, view.radius,
		(double)view.x, (double)view.y, (double)view.w, (double)view.h, (double)view.k };
	for (const Source &s : sources)
	{
		if (s.waves.empty()) continue;
		key.push_back(s.lon);
		key.push_back(s.lat);
		key.push_back(s.range);
	}
	if (key == _distKey) return;
	_distKey.swap(key);

	_distX = view.x; _distY = view.y; _distW = std::max(0, view.w); _distH = std::max(0, view.h);
	_dist.assign((size_t)_distW * _distH, FAR_OUT);
	const int margin = 2 * view.k + 4;
	std::vector<Cap> caps;
	for (const Source &s : sources)
	{
		if (s.waves.empty()) continue;
		Cap cap = makeCap(view, s.lon, s.lat, s.range, margin);
		if (cap.visible) caps.push_back(cap);
	}
	if (caps.empty() || _dist.empty()) return;

	const double radius = view.radius;
	auto rows = [&](int ra, int rb)
	{
		for (int r = ra; r < rb; ++r)
		{
			const int py = _distY + r;
			const double Y = (py + 0.5 - view.cy) / radius;
			if (Y * Y >= 1) continue;
			Sint16 *out = &_dist[(size_t)r * _distW];
			for (const Cap &cap : caps)
			{
				if (py < cap.y0 || py >= cap.y1) continue;
				const int xa = std::max(cap.x0, _distX), xb = std::min(cap.x1, _distX + _distW);
				for (int px = xa; px < xb; ++px)
				{
					const double X = (px + 0.5 - view.cx) / radius;
					const double r2 = X * X + Y * Y;
					if (r2 >= 1) continue;
					const double Z = std::sqrt(1 - r2);
					const double d = capDist(cap, X, Y, Z, std::max(Z, 0.08), radius) * 8;
					const Sint16 q = (Sint16)std::max(-32000.0, std::min(32000.0, d));
					Sint16 &o = out[px - _distX];
					if (q > o) o = q;
				}
			}
		}
	};
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(_distH / 16, pool.threads() * 4));
	pool.run(jobs, [&](int job) { rows((int)((long long)_distH * job / jobs), (int)((long long)_distH * (job + 1) / jobs)); });
}

void HdRadar::draw(const View &view, const std::vector<Source> &sources, long long minute)
{
	if (view.radius <= 1 || view.w <= 0 || view.h <= 0) return;
	const Uint32 now = SDL_GetTicks();
	if (_cyclePending)
	{
		_cyclePending = false;
		schedule(sources, now, minute);
	}
	updateDist(view, sources);

	const double k = view.k;
	const double lineW = std::max(1.0, 0.75 * k);
	const double glowLen = 3 * k;
	const double beamW = std::max(1.0, 0.8 * k);
	const int margin = 2 * view.k + 4;

	// what is drawn this frame: the box round the bases, the craft and the waves
	int ux0 = INT_MAX, uy0 = INT_MAX, ux1 = INT_MIN, uy1 = INT_MIN;
	auto grow = [&](const Cap &cap)
	{
		ux0 = std::min(ux0, cap.x0); uy0 = std::min(uy0, cap.y0);
		ux1 = std::max(ux1, cap.x1); uy1 = std::max(uy1, cap.y1);
	};
	std::vector<Wave> waves;
	std::vector<Sweep> sweeps;
	for (const Source &s : sources)
	{
		if (s.waves.empty())
		{
			Sweep sw;
			sw.cap = makeCap(view, s.lon, s.lat, s.range, margin);
			if (!sw.cap.visible) continue;
			sw.front = sw.cap.c.z >= 0;
			sw.sx = view.cx + sw.cap.c.x * view.radius;
			sw.sy = view.cy + sw.cap.c.y * view.radius;
			// each craft its own beat, so that a group does not sweep in step
			const Uint32 beat = (Uint32)(((uintptr_t)s.id >> 4) * 2654435761u);
			sw.angle = TAU * ((now + beat) % SWEEP_MS) / SWEEP_MS;
			sweeps.push_back(sw);
			grow(sw.cap);
			continue;
		}
		Cap whole = makeCap(view, s.lon, s.lat, s.range, margin);
		if (!whole.visible) continue;
		grow(whole);
		const auto pulse = _pulses.find(s.id);
		if (pulse == _pulses.end() || !pulse->second.any) continue;
		const int count = std::min((int)s.waves.size(), MAX_WAVES);
		for (int j = 0; j < count; ++j)
		{
			const int el = (int)(now - pulse->second.start) - j * WAVE_GAP_MS;
			if (el < 0 || el >= PULSE_MS) continue;
			const double t = (double)el / PULSE_MS;
			const double range = s.waves[j];
			Wave w;
			w.front = t * range;
			w.width = WAVE_WIDTH * range;
			const double lo = std::max(0.0, w.front - 4 * w.width), hi = std::min(range, w.front + w.width);
			w.cosHi = std::cos(lo);
			w.cosLo = std::cos(hi);
			// it swells as it leaves the base and dies away at the rim
			w.amp = (float)(std::min(1.0, t / 0.05) * std::pow(1 - t, 0.7));
			w.cap = makeCap(view, s.lon, s.lat, hi, margin);
			if (w.cap.visible) waves.push_back(w);
		}
	}
	if (ux0 >= ux1 || uy0 >= uy1) return;

	const Sint16 *dist = _dist.data();
	const int distX = _distX, distY = _distY, distW = _distW, distH = _distH;
	const double radius = view.radius;
	HdUi::instance().shadeRows(ux0, uy0, ux1 - ux0, uy1 - uy0, [&](int py, int x0, int x1, Uint32 *row)
	{
		const double Y = (py + 0.5 - view.cy) / radius;
		if (Y * Y >= 1) return;
		const double half = std::sqrt(1 - Y * Y) * radius;
		x0 = std::max(x0, (int)std::floor(view.cx - half));
		x1 = std::min(x1, (int)std::ceil(view.cx + half));
		// the craft and the waves that touch this row
		const int MAX_ROW = 64;
		int rowSweep[MAX_ROW], nSweep = 0, rowWave[MAX_ROW], nWave = 0;
		for (int i = 0; i < (int)sweeps.size() && nSweep < MAX_ROW; ++i)
		{
			if (py >= sweeps[i].cap.y0 && py < sweeps[i].cap.y1) rowSweep[nSweep++] = i;
		}
		for (int i = 0; i < (int)waves.size() && nWave < MAX_ROW; ++i)
		{
			if (py >= waves[i].cap.y0 && py < waves[i].cap.y1) rowWave[nWave++] = i;
		}
		const Sint16 *drow = py >= distY && py < distY + distH ? dist + (size_t)(py - distY) * distW : nullptr;
		double dc[MAX_ROW];
		for (int px = x0; px < x1; ++px)
		{
			const double X = (px + 0.5 - view.cx) / radius;
			const double r2 = X * X + Y * Y;
			if (r2 >= 1) continue;
			const double Z = std::sqrt(1 - r2);
			const double Zc = std::max(Z, 0.08);
			// the globe's own edge is soft
			const float lim = r2 > 0.97 ? clamp01((1 - std::sqrt(r2)) * radius) : 1.0f;
			const double dB = drow && px >= distX && px < distX + distW ? drow[px - distX] * 0.125 : -4000.0;
			double d = dB;
			for (int i = 0; i < nSweep; ++i)
			{
				const Cap &cap = sweeps[rowSweep[i]].cap;
				dc[i] = px >= cap.x0 && px < cap.x1 ? capDist(cap, X, Y, Z, Zc, radius) : -4000.0;
				d = std::max(d, dc[i]);
			}
			if (d < -lineW - 1) continue;
			Uint32 &pix = row[px];

			// the wash, and the line and the glow round all of it
			const float fill = clamp01(d + 0.5) * lim;
			if (fill > 0) HdUi::blend(pix, FILL, fill);
			const float line = clamp01(lineW * 0.5 + 0.5 - std::fabs(d - lineW * 0.5));
			const float glow = d > 0 && d < glowLen ? (float)((1 - d / glowLen) * (1 - d / glowLen)) * GLOW : 0.0f;
			const float edge = std::max(line, glow) * lim;
			if (edge > 0) HdUi::blend(pix, EDGE, edge);

			// the bases' waves
			if (dB > -0.5 && nWave)
			{
				float a = 0;
				for (int i = 0; i < nWave; ++i)
				{
					const Wave &w = waves[rowWave[i]];
					if (px < w.cap.x0 || px >= w.cap.x1) continue;
					const double c = X * w.cap.c.x + Y * w.cap.c.y + Z * w.cap.c.z;
					if (c < w.cosLo || c > w.cosHi) continue;
					const double x = (std::acos(std::min(1.0, c)) - w.front) / w.width;
					// a sharp front, a long tail behind it
					const double p = x >= 0 ? std::max(0.0, 1 - x) : std::max(0.0, 1 + x * 0.25);
					a += w.amp * (float)(p * p);
				}
				if (a > 0) HdUi::blend(pix, WAVE, std::min(a, 1.5f) * clamp01(dB + 0.5) * lim);
			}

			// the craft's beams, not where a base covers
			if (nSweep)
			{
				const float open = 1 - clamp01(dB + 0.5);
				if (open <= 0.01f) continue;
				for (int i = 0; i < nSweep; ++i)
				{
					const Sweep &sw = sweeps[rowSweep[i]];
					if (!sw.front || dc[i] <= -0.5) continue;
					const float cov = clamp01(dc[i] + 0.5) * open * lim;
					const double dx = px + 0.5 - sw.sx, dy = py + 0.5 - sw.sy;
					double delta = std::fmod(sw.angle - std::atan2(dy, dx), TAU);
					if (delta < 0) delta += TAU;
					if (delta < TRAIL)
					{
						const double t = 1 - delta / TRAIL;
						HdUi::blend(pix, TRAIL_COLOR, (float)(t * t) * cov);
					}
					const double sd = delta > PI ? delta - TAU : delta;
					if (std::fabs(sd) < PI / 2)
					{
						const double off = std::sqrt(dx * dx + dy * dy) * std::fabs(std::sin(sd));
						const float beam = clamp01(beamW * 0.5 + 0.5 - off);
						if (beam > 0) HdUi::blend(pix, BEAM, beam * cov);
					}
				}
			}
		}
	});
}

}
