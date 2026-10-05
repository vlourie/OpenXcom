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

/// Blends `color` over an opaque pixel at a / 256.
inline void blendInt(Uint32 &d, Uint32 color, Uint32 a)
{
	const Uint32 ia = 256 - a;
	const Uint32 rb = ((d & 0xFF00FFu) * ia + (color & 0xFF00FFu) * a) >> 8;
	const Uint32 g = ((d & 0xFF00u) * ia + (color & 0xFF00u) * a) >> 8;
	d = 0xFF000000u | (rb & 0xFF00FFu) | (g & 0xFF00u);
}

/// Blends a colour at its own alpha.
inline void blendOwn(Uint32 &d, Uint32 color)
{
	const Uint32 a = color >> 24;
	if (a) blendInt(d, color, a + (a >> 7));
}

/// The wash and the edge at the signed distance `d` (world pixels) to the coverage's edge, with the
/// globe's soft rim `lim`: the fill, and the line and the glow over it, as one colour with its alpha.
Uint32 washColor(double d, float lim, double lineW, double glowLen)
{
	const float fill = clamp01(d + 0.5) * lim;
	const float line = clamp01(lineW * 0.5 + 0.5 - std::fabs(d - lineW * 0.5));
	const float glow = d > 0 && d < glowLen ? (float)((1 - d / glowLen) * (1 - d / glowLen)) * GLOW : 0.0f;
	const float aF = (FILL >> 24) / 255.0f * fill;
	const float aE = (EDGE >> 24) / 255.0f * std::max(line, glow) * lim;
	const float a = 1 - (1 - aF) * (1 - aE);
	if (a < 0.002f) return 0;
	const float wf = aF * (1 - aE) / a, we = aE / a;
	auto ch = [&](int s) { return (Uint32)(((FILL >> s) & 0xFF) * wf + ((EDGE >> s) & 0xFF) * we + 0.5f); };
	return (Uint32)(a * 255 + 0.5f) << 24 | ch(16) << 16 | ch(8) << 8 | ch(0);
}

/// The globe's own edge is soft: the cover of a pixel at r2 (radii squared) from the middle.
inline float limb(double r2, double radius)
{
	return r2 > 0.97 ? clamp01((1 - std::sqrt(r2)) * radius) : 1.0f;
}

/// A wave in flight: the band of the arc it lights now, its light by the cosine of the arc.
struct Wave
{
	static const int LUT = 1024;
	Cap cap;          ///< its outer circle
	double lo, hi;    ///< the band, radians of arc from the base
	double cosLo, cosHi, scale;
	float light[LUT + 1];
};

/// One base's waves in flight: they share the centre, so a pixel's distance to it is worked out once.
struct WaveGroup
{
	Cap cap;          ///< the widest of their outer circles
	int a, b;         ///< the waves, [a, b)
};

/// A craft's circle, and its beam.
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
 * The bases' joint coverage: a signed distance per world pixel of the globe's widget, and the colours
 * it gives as runs of each row. It stands while the globe and the bases do, so it is worked out again
 * only when they change, in bands on the render threads. Past a little beyond the glow the distance
 * is not needed: there the wash is plain, so a pixel deep inside or far outside is settled by a bound
 * of the distance, without working it out.
 */
void HdRadar::updateCache(const View &view, const std::vector<Source> &sources)
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

	const double lineW = std::max(1.0, 0.75 * view.k);
	const double glowLen = 3 * view.k;
	const double sat = glowLen + lineW + 2;
	const Sint16 SAT8 = (Sint16)std::ceil(sat * 8);
	_distX = view.x; _distY = view.y; _distW = std::max(0, view.w); _distH = std::max(0, view.h);
	_dist.assign((size_t)_distW * _distH, (Sint16)-SAT8);
	_rows.resize(_distH);
	for (int r = _rowA; r < _rowB && r < _distH; ++r)
	{
		_rows[r].runs.clear();
		_rows[r].px.clear();
	}
	_rowA = _rowB = 0;
	const int margin = 2 * view.k + 4;
	std::vector<Cap> caps;
	int capY0 = INT_MAX, capY1 = INT_MIN;
	for (const Source &s : sources)
	{
		if (s.waves.empty()) continue;
		Cap cap = makeCap(view, s.lon, s.lat, s.range, margin);
		if (!cap.visible) continue;
		caps.push_back(cap);
		capY0 = std::min(capY0, cap.y0);
		capY1 = std::max(capY1, cap.y1);
	}
	if (caps.empty() || _dist.empty()) return;
	_rowA = std::max(0, capY0 - _distY);
	_rowB = std::min(_distH, capY1 - _distY);
	if (_rowA >= _rowB)
	{
		_rowA = _rowB = 0;
		return;
	}

	const double radius = view.radius;
	auto rows = [&](int ra, int rb)
	{
		std::vector<int> rowCaps;
		std::vector<Uint32> cols;
		for (int r = ra; r < rb; ++r)
		{
			const int py = _distY + r;
			const double Y = (py + 0.5 - view.cy) / radius;
			if (Y * Y >= 1) continue;
			const double half = std::sqrt(1 - Y * Y) * radius;
			const int xa = std::max(_distX, (int)std::floor(view.cx - half));
			const int xb = std::min(_distX + _distW, (int)std::ceil(view.cx + half));
			if (xa >= xb) continue;
			rowCaps.clear();
			for (int i = 0; i < (int)caps.size(); ++i)
			{
				if (py >= caps[i].y0 && py < caps[i].y1) rowCaps.push_back(i);
			}
			if (rowCaps.empty()) continue;
			Sint16 *out = &_dist[(size_t)r * _distW];
			cols.assign(xb - xa, 0);
			for (int px = xa; px < xb; ++px)
			{
				const double X = (px + 0.5 - view.cx) / radius;
				const double r2 = X * X + Y * Y;
				if (r2 >= 1) continue;
				const double Z = std::sqrt(1 - r2);
				const double Zc = std::max(Z, 0.08);
				// the rim's gradient on the screen is never longer than this, so f over it bounds the distance
				const double bound = radius / (1 + 1 / Zc);
				int best = -SAT8;
				for (int i : rowCaps)
				{
					const Cap &cap = caps[i];
					if (px < cap.x0 || px >= cap.x1) continue;
					const double f = X * cap.c.x + Y * cap.c.y + Z * cap.c.z - cap.cosR;
					const double lb = f * bound;
					if (lb >= sat) { best = SAT8; break; }
					if (lb <= -sat) continue;
					const double d = capDist(cap, X, Y, Z, Zc, radius) * 8;
					const int q = (int)std::max(-(double)SAT8, std::min((double)SAT8, d));
					if (q > best) best = q;
					if (best >= SAT8) break;
				}
				out[px - _distX] = (Sint16)best;
				const double d = best * 0.125;
				if (d < -lineW - 1) continue;
				const float lim = limb(r2, radius);
				cols[px - xa] = best >= SAT8 && lim >= 1.0f ? FILL : washColor(d, lim, lineW, glowLen);
			}
			// a long stretch of one colour blends as one, the rest pixel by pixel
			Row &row = _rows[r];
			const int n = xb - xa;
			int open = -1;
			for (int i = 0; i < n; )
			{
				const Uint32 c = cols[i];
				if (!c)
				{
					open = -1;
					++i;
					continue;
				}
				int j = i + 1;
				while (j < n && cols[j] == c) ++j;
				if (j - i >= 4)
				{
					row.runs.push_back(Run{ xa + i, xa + j, c, -1 });
					open = -1;
				}
				else
				{
					if (open < 0)
					{
						open = (int)row.runs.size();
						row.runs.push_back(Run{ xa + i, xa + i, 0, (int)row.px.size() });
					}
					for (int m = i; m < j; ++m) row.px.push_back(cols[m]);
					row.runs[open].x1 = xa + j;
				}
				i = j;
			}
		}
	};
	const int n = _rowB - _rowA;
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(n / 8, pool.threads() * 4));
	pool.run(jobs, [&](int job) { rows(_rowA + (int)((long long)n * job / jobs), _rowA + (int)((long long)n * (job + 1) / jobs)); });
}

void HdRadar::draw(const View &view, const std::vector<Source> &sources, long long minute, bool sweep)
{
	if (view.radius <= 1 || view.w <= 0 || view.h <= 0) return;
	const Uint32 now = SDL_GetTicks();
	if (_cyclePending)
	{
		_cyclePending = false;
		if (sweep) schedule(sources, now, minute);
	}
	updateCache(view, sources);

	const double k = view.k;
	const double lineW = std::max(1.0, 0.75 * k);
	const double glowLen = 3 * k;
	const double beamW = std::max(1.0, 0.8 * k);
	const int margin = 2 * view.k + 4;

	// what is drawn this frame: the bases' rows, the craft and the waves
	int ux0 = INT_MAX, uy0 = INT_MAX, ux1 = INT_MIN, uy1 = INT_MIN;
	if (_rowA < _rowB)
	{
		ux0 = _distX; ux1 = _distX + _distW;
		uy0 = _distY + _rowA; uy1 = _distY + _rowB;
	}
	auto grow = [&](const Cap &cap)
	{
		ux0 = std::min(ux0, cap.x0); uy0 = std::min(uy0, cap.y0);
		ux1 = std::max(ux1, cap.x1); uy1 = std::max(uy1, cap.y1);
	};
	std::vector<Wave> waves;
	std::vector<WaveGroup> groups;
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
		if (!sweep) continue;
		const auto pulse = _pulses.find(s.id);
		if (pulse == _pulses.end() || !pulse->second.any) continue;
		const int count = std::min((int)s.waves.size(), MAX_WAVES);
		const int first = (int)waves.size();
		double widest = 0;
		for (int j = 0; j < count; ++j)
		{
			const int el = (int)(now - pulse->second.start) - j * WAVE_GAP_MS;
			if (el < 0 || el >= PULSE_MS) continue;
			const double t = (double)el / PULSE_MS;
			const double range = s.waves[j];
			const double front = t * range, width = WAVE_WIDTH * range;
			// the tail fades over four widths, but past 3.4 its light rounds to nothing (WAVE's alpha 20 x p^2)
			const double lo = std::max(0.0, front - 3.4 * width), hi = std::min(range, front + width);
			waves.emplace_back();
			Wave &w = waves.back();
			w.cap = makeCap(view, s.lon, s.lat, hi, margin);
			if (!w.cap.visible || hi <= lo)
			{
				waves.pop_back();
				continue;
			}
			w.lo = lo;
			w.hi = hi;
			w.cosHi = std::cos(lo);
			w.cosLo = std::cos(hi);
			w.scale = Wave::LUT / std::max(1e-12, w.cosHi - w.cosLo);
			// it swells as it leaves the base and dies away at the rim; a sharp front, a long tail behind it
			const double amp = std::min(1.0, t / 0.05) * std::pow(1 - t, 0.7);
			for (int i = 0; i <= Wave::LUT; ++i)
			{
				const double c = w.cosLo + (i + 0.5) / w.scale;
				const double x = (std::acos(std::min(1.0, c)) - front) / width;
				const double p = x >= 0 ? std::max(0.0, 1 - x) : std::max(0.0, 1 + x * 0.25);
				w.light[i] = (float)(amp * p * p);
			}
			widest = std::max(widest, hi);
		}
		if ((int)waves.size() > first)
		{
			groups.push_back({ makeCap(view, s.lon, s.lat, widest, margin), first, (int)waves.size() });
			grow(groups.back().cap);
		}
	}
	if (ux0 >= ux1 || uy0 >= uy1) return;

	const Sint16 *dist = _dist.data();
	const int distX = _distX, distY = _distY, distW = _distW;
	const int rowA = _rowA, rowB = _rowB;
	const double radius = view.radius;
	const Uint32 waveA = WAVE >> 24;
	HdUi::instance().shadeRows(ux0, uy0, ux1 - ux0, uy1 - uy0, [&](int py, int x0, int x1, Uint32 *row)
	{
		const double Y = (py + 0.5 - view.cy) / radius;
		if (Y * Y >= 1) return;
		const double half = std::sqrt(1 - Y * Y) * radius;
		x0 = std::max(x0, (int)std::floor(view.cx - half));
		x1 = std::min(x1, (int)std::ceil(view.cx + half));
		if (x0 >= x1) return;
		const int r = py - distY;
		const Sint16 *drow = r >= rowA && r < rowB ? dist + (size_t)r * distW : nullptr;

		// the craft in this row, and the stretches of it they take: those are worked out per pixel
		const int MAX_ROW = 64;
		int rowSweep[MAX_ROW], nSweep = 0;
		int ivA[MAX_ROW], ivB[MAX_ROW], nIv = 0;
		for (int i = 0; i < (int)sweeps.size() && nSweep < MAX_ROW; ++i)
		{
			const Cap &cap = sweeps[i].cap;
			if (py < cap.y0 || py >= cap.y1) continue;
			rowSweep[nSweep++] = i;
			int a = std::max(x0, cap.x0), b = std::min(x1, cap.x1);
			if (a >= b) continue;
			// kept in order and apart
			int at = 0;
			while (at < nIv && ivA[at] < a) ++at;
			for (int m = nIv; m > at; --m) { ivA[m] = ivA[m - 1]; ivB[m] = ivB[m - 1]; }
			ivA[at] = a; ivB[at] = b; ++nIv;
		}
		int merged = 0;
		for (int i = 0; i < nIv; ++i)
		{
			if (merged && ivA[i] <= ivB[merged - 1]) ivB[merged - 1] = std::max(ivB[merged - 1], ivB[i]);
			else { ivA[merged] = ivA[i]; ivB[merged] = ivB[i]; ++merged; }
		}
		nIv = merged;

		// 1. the bases' wash as it was worked out, but where the craft are
		if (drow)
		{
			const Row &cached = _rows[r];
			for (const Run &run : cached.runs)
			{
				int a = std::max(run.x0, x0);
				const int b = std::min(run.x1, x1);
				int iv = 0;
				while (a < b)
				{
					while (iv < nIv && ivB[iv] <= a) ++iv;
					const int stop = iv < nIv ? std::min(b, ivA[iv]) : b;
					if (a < stop)
					{
						if (run.px < 0)
						{
							const Uint32 c = run.color, al = c >> 24;
							const Uint32 a256 = al + (al >> 7);
							for (int px = a; px < stop; ++px) blendInt(row[px], c, a256);
						}
						else
						{
							const Uint32 *src = cached.px.data() + run.px;
							for (int px = a; px < stop; ++px) blendOwn(row[px], src[px - run.x0]);
						}
					}
					a = iv < nIv ? std::max(stop, ivB[iv]) : b;
				}
			}
		}

		// 2. the craft: their circles join the bases' wash; a beam turns where no base covers
		double dc[MAX_ROW];
		for (int iv = 0; iv < nIv; ++iv)
		{
			for (int px = ivA[iv]; px < ivB[iv]; ++px)
			{
				const double X = (px + 0.5 - view.cx) / radius;
				const double r2 = X * X + Y * Y;
				if (r2 >= 1) continue;
				const double Z = std::sqrt(1 - r2);
				const double Zc = std::max(Z, 0.08);
				const double dB = drow && px >= distX && px < distX + distW ? drow[px - distX] * 0.125 : -4000.0;
				double d = dB;
				for (int i = 0; i < nSweep; ++i)
				{
					const Cap &cap = sweeps[rowSweep[i]].cap;
					dc[i] = px >= cap.x0 && px < cap.x1 ? capDist(cap, X, Y, Z, Zc, radius) : -4000.0;
					d = std::max(d, dc[i]);
				}
				if (d < -lineW - 1) continue;
				const float lim = limb(r2, radius);
				Uint32 &pix = row[px];
				blendOwn(pix, washColor(d, lim, lineW, glowLen));
				if (!sweep) continue;
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

		// 3. the bases' waves, inside the bases' coverage only
		if (!drow) return;
		for (const WaveGroup &g : groups)
		{
			if (py < g.cap.y0 || py >= g.cap.y1) continue;
			const Vec &cen = g.cap.c;
			const int xa = std::max(x0, std::max(g.cap.x0, distX)), xb = std::min(x1, std::min(g.cap.x1, distX + distW));
			for (int px = xa; px < xb; ++px)
			{
				const int v = drow[px - distX];
				if (v <= -4) continue;
				const double X = (px + 0.5 - view.cx) / radius;
				const double r2 = X * X + Y * Y;
				if (r2 >= 1) continue;
				const double Z = std::sqrt(1 - r2);
				const double c = X * cen.x + Y * cen.y + Z * cen.z;
				// the waves over this pixel: the same colour blended twice is one blend of 1-(1-a1)(1-a2)
				float light = 0;
				bool in = false;
				for (int i = g.a; i < g.b; ++i)
				{
					const Wave &w = waves[i];
					if (c < w.cosLo || c > w.cosHi) continue;
					in = true;
					const float l = w.light[std::min(Wave::LUT, (int)((c - w.cosLo) * w.scale))];
					light = 1 - (1 - light) * (1 - l);
				}
				if (!in)
				{
					// out of every band: a pixel moves the point on the globe at most 1/(Z radius) radians,
					// so its arc from the base by no more, and Z along a row is least at an end of the
					// stretch: the next `skip` pixels are out of the bands too
					const double arc = std::acos(std::max(-1.0, std::min(1.0, c)));
					double off = PI;
					for (int i = g.a; i < g.b; ++i)
					{
						off = std::min(off, arc < waves[i].lo ? waves[i].lo - arc : arc - waves[i].hi);
					}
					int skip = (int)(off * Z * radius);
					if (skip > 1)
					{
						const double Xs = X + skip / radius, r2s = Xs * Xs + Y * Y;
						skip = r2s < 1 ? (int)(off * std::min(Z, std::sqrt(1 - r2s)) * radius) : 0;
						if (skip > 1) px += skip - 1;
					}
					continue;
				}
				if (light <= 0) continue;
				const float a = light * clamp01(v * 0.125 + 0.5) * limb(r2, radius);
				const Uint32 a256 = (Uint32)(a * waveA * (256.0f / 255.0f) + 0.5f);
				if (a256) blendInt(row[px], WAVE, a256);
			}
		}
	});
}

}
