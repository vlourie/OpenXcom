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
const double TRAIL_COS2 = std::cos(TRAIL) * std::cos(TRAIL); // the wedge's edge, squared, for a test without trig
/// The width of a wave's bright front, as a part of its radar's range; its tail is four times that.
const double WAVE_WIDTH = 0.07;

// colours, 0xAARRGGBB: the alpha is the strongest the part is ever drawn
const Uint32 FILL = 0x1F48D8A8u;   // 12 %: the coverage itself
const Uint32 EDGE = 0x66A8FFE0u;   // 40 %: the line round the joint coverage
const float GLOW = 0.25f;          // the glow just inside the edge, a part of EDGE
const Uint32 WAVE = 0x149CF5D6u;   // 8 %: a pulse on top of the fill
const Uint32 TRAIL_COLOR = 0x1A9CF5D6u; // 10 %: the swept area behind a craft's beam
const Uint32 BEAM = 0x80C8FFE8u;   // 50 %: the beam
const Uint32 WAVE_BARE = 0x809CF5D6u; // 50 %: a wave with no wash under it (WAVES), the only sign of the coverage
const Uint32 ENEMY = 0xB3FF4636u;  // 70 %: the line round an enemy radar
const Uint32 ENEMY_SHIP = 0xB3FF7A6Eu; // 70 %: the same round a hunter-killer, a lighter red
const float ENEMY_GLOW = 0.3f;     // the glow just inside it, a part of ENEMY
/// WAVES: a wave ends by this part of the time to the next one, and lasts no less than WAVE_MIN_MS.
/// The most craft a row of the bases' wash is cut for (each works out its own there).
const int MAX_ROW = 64;
/// Every wash picture worked out (HdShadeBase's key): the card keeps the last one it was given.
Uint64 washCount = 0;
const double WAVE_FIT = 0.8;
const int WAVE_MIN_MS = 1000;
/// The most the animation clock moves on between two draws, ms.
const Uint32 MAX_FRAME_MS = 100;

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

/// Blends a colour at its own alpha over pixel x (at a / 256: HdShadeRow::blend256).
inline void blendOwn(HdShadeRow &row, int x, Uint32 color)
{
	const Uint32 a = color >> 24;
	if (a) row.blend256(x, color, a + (a >> 7));
}

/// The wash and the edge at the signed distance `d` (world pixels) to the coverage's edge, with the
/// globe's soft rim `lim`: the fill, and the line and the glow over it, as one colour with its alpha.
/// Without `withFill` only the line and the glow.
Uint32 washColor(double d, float lim, double lineW, double glowLen, bool withFill = true)
{
	const float fill = withFill ? clamp01(d + 0.5) * lim : 0.0f;
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
	bool craft;       ///< a craft's (WAVES): not bounded by the bases' coverage
};

/// A craft's circle, and its beam.
struct Sweep
{
	Cap cap;
	double sx, sy;    ///< the craft on the screen, world pixels
	bool front;       ///< the craft is on the visible side
	double angle;     ///< the beam now, radians on the screen
	double ux, uy;    ///< the beam's direction, cos and sin of the angle
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
		p.wave = PULSE_MS;
	}
}

void HdRadar::note(Uint32 &tick, Uint32 &ms)
{
	// the animation clock as of the last draw: the signals come from the game clock, which runs with it
	ms = tick ? _clock - tick : 0;
	tick = _clock;
}

Uint32 HdRadar::advance()
{
	const Uint32 real = SDL_GetTicks();
	if (_ran && _lastReal)
	{
		// a long gap (the globe was not drawn, under a base screen) is not played as a jump
		_clock += std::min<Uint32>(real - _lastReal, MAX_FRAME_MS);
	}
	_ran = false;
	_lastReal = real;
	return _clock;
}

/**
 * WAVES in turn: in a cycle of `waveHours` hours (6 ten-minute steps an hour) the bases with a radar take
 * their turns evenly, in the order of the list, so that a step sets off one base or a few, never all.
 * A wave lasts PULSE_MS, or less when the clock is fast, so that about three run at once at most.
 */
void HdRadar::scheduleTurn(const std::vector<Source> &sources, Uint32 now, long long minute, long long step, int waveHours)
{
	const long long period = 6LL * waveHours;
	int n = 0;
	for (const Source &s : sources)
	{
		if (!s.waves.empty()) ++n;
	}
	if (n == 0) return;
	// the steps between two bases' turns, and how many bases share a step
	const double spacing = std::max(1.0, (double)period / n);
	const double together = std::ceil(n / (double)period);
	int wave = PULSE_MS;
	if (_stepMs > 0)
	{
		const double fit = WAVE_FIT * _stepMs * spacing * std::max(1.0, 3.0 / together);
		wave = std::max(WAVE_MIN_MS, std::min(PULSE_MS, (int)fit));
	}
	const long long turn = ((step % period) + period) % period;
	int i = 0;
	for (const Source &s : sources)
	{
		if (s.waves.empty()) continue;
		if ((long long)i * period / n == turn)
		{
			Pulse &p = _pulses[s.id];
			p.any = true;
			p.start = now;
			p.length = (Uint32)wave;
			p.minute = minute;
			p.wave = (Uint32)wave;
		}
		++i;
	}
}

/**
 * WAVES: every base (`bases`) or every craft out sends one wave now; one still running starts again.
 * The wave takes PULSE_MS, or WAVE_FIT of the real time between the last two signals of its kind
 * when that is shorter, so that the clock at 1 minute a step does not lay one wave over the next.
 */
void HdRadar::scheduleAll(const std::vector<Source> &sources, Uint32 now, long long minute, bool bases, Uint32 gapMs)
{
	int wave = PULSE_MS;
	if (gapMs > 0 && gapMs < (Uint32)PULSE_MS * 4)
	{
		wave = std::max(WAVE_MIN_MS, std::min(PULSE_MS, (int)(gapMs * WAVE_FIT)));
	}
	for (const Source &s : sources)
	{
		if (s.waves.empty() == bases) continue;
		Pulse &p = _pulses[s.id];
		p.any = true;
		p.start = now;
		p.length = (Uint32)wave;
		p.minute = minute;
		p.wave = (Uint32)wave;
	}
}

/**
 * The bases' joint coverage: a signed distance per world pixel of the globe's widget, and the colours
 * it gives as runs of each row. It stands while the globe and the bases do, so it is worked out again
 * only when they change, in bands on the render threads. Past a little beyond the glow the distance
 * is not needed: there the wash is plain, so a pixel deep inside or far outside is settled by a bound
 * of the distance, without working it out.
 */
void HdRadar::updateCache(const View &view, const std::vector<Source> &sources, bool fill)
{
	std::vector<double> key = { view.cenLon, view.cenLat, view.cx, view.cy, view.radius,
		(double)view.x, (double)view.y, (double)view.w, (double)view.h, (double)view.k, fill ? 1.0 : 0.0 };
	for (const Source &s : sources)
	{
		if (s.waves.empty()) continue;
		key.push_back(s.lon);
		key.push_back(s.lat);
		key.push_back(s.range);
	}
	if (key == _distKey) return;
	_distKey.swap(key);
	_washKey = ++washCount;
	_colA = _colB = 0;
	_wash.clear();

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
	int capX0 = INT_MAX, capX1 = INT_MIN;
	for (const Cap &cap : caps)
	{
		capX0 = std::min(capX0, cap.x0);
		capX1 = std::max(capX1, cap.x1);
	}
	_colA = std::max(0, capX0 - _distX);
	_colB = std::max(_colA, std::min(_distW, capX1 - _distX));
	_wash.assign((size_t)(_colB - _colA) * (_rowB - _rowA), 0);

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
				if (best >= SAT8 && lim >= 1.0f) cols[px - xa] = fill ? FILL : 0;
				else cols[px - xa] = washColor(d, lim, lineW, glowLen, fill);
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
			// the same as one picture: a run of one colour blends at its alpha even of 0 (the pixel made opaque),
			// a pixel of its own only with an alpha (blendOwn)
			Uint32 *flat = _wash.data() + (size_t)(r - _rowA) * (_colB - _colA);
			const int flatX = _distX + _colA;
			for (const Run &run : row.runs)
			{
				for (int px = run.x0; px < run.x1; ++px)
				{
					const Uint32 c = run.px < 0 ? run.color : row.px[run.px + px - run.x0];
					flat[px - flatX] = run.px < 0 || (c >> 24) ? c : 0;
				}
			}
		}
	};
	const int n = _rowB - _rowA;
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(n / 8, pool.threads() * 4));
	pool.run(jobs, [&](int job) { rows(_rowA + (int)((long long)n * job / jobs), _rowA + (int)((long long)n * (job + 1) / jobs)); });
}

void HdRadar::draw(const View &view, const std::vector<Source> &sources, long long minute, Mode mode, int waveHours, bool beam)
{
	if (view.radius <= 1 || view.w <= 0 || view.h <= 0) return;
	const bool sweep = mode == SWEEP, bare = mode == WAVES;
	const bool inTurn = bare && waveHours > 0;
	// a craft's beam: with SWEEP always, with WAVES when asked instead of its waves
	const bool craftBeam = sweep || (bare && beam);
	const Uint32 now = advance();
	if (_cyclePending)
	{
		_cyclePending = false;
		if (sweep) schedule(sources, now, minute);
		else if (bare && !beam) scheduleAll(sources, now, minute, false, _cycleMs);
	}
	if (_hourPending)
	{
		_hourPending = false;
		if (bare && !inTurn) scheduleAll(sources, now, minute, true, _hourMs);
	}
	if (inTurn)
	{
		const long long step = minute / 10;
		if (_step >= 0 && step > _step && step - _step <= 6LL * waveHours)
		{
			_stepMs = (now - _stepAt) / (Uint32)(step - _step);
			// at the slow clock speeds only, as the other pulses
			for (long long s = _step + 1; _slow && s <= step; ++s)
			{
				scheduleTurn(sources, now, minute, s, waveHours);
			}
		}
		if (step != _step)
		{
			// a load or a jump of the date starts the turns from here, without a burst
			_step = step;
			_stepAt = now;
		}
	}
	else
	{
		_step = -1;
	}
	updateCache(view, sources, !bare);

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
		const bool craft = s.waves.empty();
		if (craft)
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
			sw.ux = std::cos(sw.angle);
			sw.uy = std::sin(sw.angle);
			sweeps.push_back(sw);
			grow(sw.cap);
			if (!bare || beam) continue;
		}
		else if (mode == WASH) continue;
		const auto pulse = _pulses.find(s.id);
		if (pulse == _pulses.end() || !pulse->second.any) continue;
		const Pulse &p = pulse->second;
		const int dur = p.wave ? (int)p.wave : PULSE_MS;
		// with WAVES one wave, out to the longest range (the craft: its own)
		const int count = bare ? 1 : std::min((int)s.waves.size(), MAX_WAVES);
		const int first = (int)waves.size();
		double widest = 0;
		for (int j = 0; j < count; ++j)
		{
			const int el = (int)(now - p.start) - j * WAVE_GAP_MS;
			if (el < 0 || el >= dur) continue;
			const double t = (double)el / dur;
			const double range = craft ? s.range : s.waves[j];
			const double front = t * range, width = WAVE_WIDTH * range;
			// the tail fades over four widths; under WAVE's alpha 20 x p^2 its light rounds to nothing past 3.4
			const double lo = std::max(0.0, front - (bare ? 4.0 : 3.4) * width), hi = std::min(range, front + width);
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
				const double fall = x >= 0 ? std::max(0.0, 1 - x) : std::max(0.0, 1 + x * 0.25);
				w.light[i] = (float)(amp * fall * fall);
			}
			widest = std::max(widest, hi);
		}
		if ((int)waves.size() > first)
		{
			groups.push_back({ makeCap(view, s.lon, s.lat, widest, margin), first, (int)waves.size(), craft });
			grow(groups.back().cap);
		}
	}
	if (ux0 >= ux1 || uy0 >= uy1) return;

	const Sint16 *dist = _dist.data();
	const int distX = _distX, distY = _distY, distW = _distW;
	const int rowA = _rowA, rowB = _rowB;
	const double radius = view.radius;
	// with no wash under it a wave would be lost at the wash's own strength
	const Uint32 waveColor = bare ? WAVE_BARE : WAVE;
	const Uint32 waveA = waveColor >> 24;
	// a craft's beam and the fading trail behind it over one pixel, `cov` - how much of it shows there
	auto drawBeam = [&](HdShadeRow &row, const Sweep &sw, float cov, int px, int py)
	{
		const double dx = px + 0.5 - sw.sx, dy = py + 0.5 - sw.sy;
		// the beam shows only in the trail's wedge (behind the beam, within TRAIL) and in the strip along it:
		// that is told without a trig call, with a margin so that the exact test below still decides every pixel
		{
			const double along = dx * sw.ux + dy * sw.uy, cross = sw.ux * dy - sw.uy * dx;
			const double d2 = dx * dx + dy * dy;
			const bool wedge = cross <= 0.01 && (d2 < 4 || (along > 0 && along * along > TRAIL_COS2 * d2 * 0.999));
			const bool strip = along > -0.01 && std::fabs(cross) < beamW * 0.5 + 0.51;
			if (!wedge && !strip) return;
		}
		double delta = std::fmod(sw.angle - std::atan2(dy, dx), TAU);
		if (delta < 0) delta += TAU;
		if (delta < TRAIL)
		{
			const double t = 1 - delta / TRAIL;
			row.blend(px, TRAIL_COLOR, (float)(t * t) * cov);
		}
		const double sd = delta > PI ? delta - TAU : delta;
		if (std::fabs(sd) < PI / 2)
		{
			const double off = std::sqrt(dx * dx + dy * dy) * std::fabs(std::sin(sd));
			const float b = clamp01(beamW * 0.5 + 0.5 - off);
			if (b > 0) row.blend(px, BEAM, b * cov);
		}
	};
	// step 1 below as a picture the video card keeps: the bases' wash, cut where the craft are (but with WAVES)
	HdShadeBase wash;
	const bool washed = _rowA < _rowB && _colA < _colB && (bare || sweeps.size() <= (size_t)MAX_ROW);
	if (washed)
	{
		wash.px = _wash.data();
		wash.x = _distX + _colA;
		wash.y = _distY + _rowA;
		wash.w = _colB - _colA;
		wash.h = _rowB - _rowA;
		wash.key = _washKey;
		for (size_t i = 0; !bare && i < sweeps.size(); ++i)
		{
			const Cap &cap = sweeps[i].cap;
			wash.holes.insert(wash.holes.end(), { cap.x0, cap.y0, cap.x1, cap.y1 });
		}
	}
	HdUi::instance().shadeRows(ux0, uy0, ux1 - ux0, uy1 - uy0, [&](int py, int x0, int x1, HdShadeRow &row)
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

		// 1. the bases' wash as it was worked out, but where the craft are (with WAVES the craft lie apart, on top)
		const int nCut = bare ? 0 : nIv;
		if (drow && !row.baseDrawn())
		{
			const Row &cached = _rows[r];
			for (const Run &run : cached.runs)
			{
				int a = std::max(run.x0, x0);
				const int b = std::min(run.x1, x1);
				int iv = 0;
				while (a < b)
				{
					while (iv < nCut && ivB[iv] <= a) ++iv;
					const int stop = iv < nCut ? std::min(b, ivA[iv]) : b;
					if (a < stop)
					{
						if (run.px < 0)
						{
							const Uint32 c = run.color, al = c >> 24;
							const Uint32 a256 = al + (al >> 7);
							for (int px = a; px < stop; ++px) row.blend256(px, c, a256);
						}
						else
						{
							const Uint32 *src = cached.px.data() + run.px;
							for (int px = a; px < stop; ++px) blendOwn(row, px, src[px - run.x0]);
						}
					}
					a = iv < nCut ? std::max(stop, ivB[iv]) : b;
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
				if (bare)
				{
					// each craft its own edge, not joined with the bases' nor with one another's
					const float lim = limb(r2, radius);
					for (int i = 0; i < nSweep; ++i)
					{
						const Cap &cap = sweeps[rowSweep[i]].cap;
						if (px < cap.x0 || px >= cap.x1) continue;
						const double d = capDist(cap, X, Y, Z, Zc, radius);
						if (d < -lineW - 1) continue;
						if (d <= glowLen + 1) blendOwn(row, px, washColor(d, lim, lineW, glowLen, false));
						const Sweep &sw = sweeps[rowSweep[i]];
						if (craftBeam && sw.front && d > -0.5) drawBeam(row, sw, clamp01(d + 0.5) * lim, px, py);
					}
					continue;
				}
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
				blendOwn(row, px, washColor(d, lim, lineW, glowLen));
				if (!craftBeam) continue;
				const float open = 1 - clamp01(dB + 0.5);
				if (open <= 0.01f) continue;
				for (int i = 0; i < nSweep; ++i)
				{
					const Sweep &sw = sweeps[rowSweep[i]];
					if (!sw.front || dc[i] <= -0.5) continue;
					drawBeam(row, sw, clamp01(dc[i] + 0.5) * open * lim, px, py);
				}
			}
		}

		// 3. the waves: a base's inside the bases' coverage only, a craft's inside its own circle
		for (const WaveGroup &g : groups)
		{
			if (py < g.cap.y0 || py >= g.cap.y1) continue;
			if (!g.craft && !drow) continue;
			const Vec &cen = g.cap.c;
			const int xa = g.craft ? std::max(x0, g.cap.x0) : std::max(x0, std::max(g.cap.x0, distX));
			const int xb = g.craft ? std::min(x1, g.cap.x1) : std::min(x1, std::min(g.cap.x1, distX + distW));
			for (int px = xa; px < xb; ++px)
			{
				// the wave ends at the range, so a craft's needs no bound; a base's fades with the joint edge
				const int v = g.craft ? 8 * 8 : drow[px - distX];
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
				if (a256) row.blend256(px, waveColor, a256);
			}
		}
	}, washed ? &wash : nullptr);
}

/**
 * The enemy's radars, each circle on its own: a red line just inside the rim and a glow fading inwards,
 * nothing over the rest of the circle. A row works out only the stretches round the points where the rim
 * crosses it and the rows nearby (found exactly, from the circle's plane), so the cost goes with the rims.
 */
void HdRadar::drawRings(const View &view, const std::vector<Ring> &rings)
{
	if (view.radius <= 1 || view.w <= 0 || view.h <= 0 || rings.empty()) return;
	const double k = view.k, radius = view.radius;
	const double lineW = std::max(1.0, 0.75 * k);
	const double glowLen = 4 * k;
	const int margin = 2 * view.k + 4;
	// where a pixel can be lit: from just outside the rim to the end of the glow
	const double lo = -1.0, hi = std::max(lineW, glowLen) + 1.0;
	std::vector<Cap> caps;
	std::vector<Uint32> colors;
	int ux0 = INT_MAX, uy0 = INT_MAX, ux1 = INT_MIN, uy1 = INT_MIN;
	for (const Ring &r : rings)
	{
		const Cap cap = makeCap(view, r.lon, r.lat, r.range, margin);
		if (!cap.visible) continue;
		caps.push_back(cap);
		colors.push_back(r.ship ? ENEMY_SHIP : ENEMY);
		ux0 = std::min(ux0, cap.x0); uy0 = std::min(uy0, cap.y0);
		ux1 = std::max(ux1, cap.x1); uy1 = std::max(uy1, cap.y1);
	}
	if (caps.empty()) return;
	// a lit pixel lies within `band` of a rim point, so in a row no more than `band` away from it
	const int band = (int)std::ceil(hi) + 1;
	// where the rim crosses each row (on the visible side), once a frame: X cx + Z cz = cosR - Y cy with
	// X = s cos t, Z = s sin t, sin t >= 0; the two roots t = phi -+ a run on as two curves down the rows
	struct Rim
	{
		int y0 = 0;                  ///< the row of xs[0]
		bool flat = false;           ///< the rim runs along the rows (a circle round the top or the bottom)
		std::vector<float> xs[2];    ///< world x of each curve in each row; NAN where it has none
	};
	std::vector<Rim> rims(caps.size());
	for (size_t i = 0; i < caps.size(); ++i)
	{
		const Cap &cap = caps[i];
		Rim &rim = rims[i];
		const double A = std::sqrt(cap.c.x * cap.c.x + cap.c.z * cap.c.z);
		if (A < 1e-9)
		{
			rim.flat = true;
			continue;
		}
		const double phi = std::atan2(cap.c.z, cap.c.x);
		rim.y0 = cap.y0 - band;
		const int n = cap.y1 - cap.y0 + 2 * band;
		rim.xs[0].assign(n, NAN);
		rim.xs[1].assign(n, NAN);
		for (int j = 0; j < n; ++j)
		{
			const double Yr = (rim.y0 + j + 0.5 - view.cy) / radius;
			const double s2 = 1 - Yr * Yr;
			if (s2 <= 0) continue;
			const double s = std::sqrt(s2);
			const double q = (cap.cosR - Yr * cap.c.y) / (s * A);
			if (q < -1 || q > 1) continue;
			const double a = std::acos(q);
			for (int side = 0; side < 2; ++side)
			{
				const double t = phi + (side ? a : -a);
				if (std::sin(t) >= 0) rim.xs[side][j] = (float)(view.cx + s * std::cos(t) * radius);
			}
		}
	}
	// a circle a layer, in the rows of its cap: the video card takes it (HdUi::shadeCover)
	std::vector<int> capRows;
	for (const Cap &cap : caps)
	{
		capRows.push_back(cap.y0);
		capRows.push_back(cap.y1);
	}
	HdUi::instance().shadeCover(ux0, uy0, ux1 - ux0, uy1 - uy0, (int)caps.size(), colors.data(), [&](int py, int x0, int x1, float *out)
	{
		const int ox = x0, n = x1 - x0;
		const double Y = (py + 0.5 - view.cy) / radius;
		if (Y * Y >= 1) return;
		const double half = std::sqrt(1 - Y * Y) * radius;
		x0 = std::max(x0, (int)std::floor(view.cx - half));
		x1 = std::min(x1, (int)std::ceil(view.cx + half));
		for (size_t c = 0; c < caps.size(); ++c)
		{
			const Cap &cap = caps[c];
			if (py < cap.y0 || py >= cap.y1) continue;
			const Rim &rim = rims[c];
			// the stretch of this row each curve takes in the rows nearby, widened by the band
			int ivA[2], ivB[2], nIv = 0;
			if (rim.flat)
			{
				ivA[0] = std::max(x0, cap.x0); ivB[0] = std::min(x1, cap.x1); nIv = 1;
			}
			else
			{
				for (int side = 0; side < 2; ++side)
				{
					float lo2 = 1e30f, hi2 = -1e30f;
					const float *xs = rim.xs[side].data() + (py - rim.y0);
					for (int dy = -band; dy <= band; ++dy)
					{
						const float x = xs[dy];
						if (x == x) { lo2 = std::min(lo2, x); hi2 = std::max(hi2, x); }
					}
					if (lo2 > hi2) continue;
					const int a = std::max(x0, (int)std::floor(lo2) - band), b = std::min(x1, (int)std::ceil(hi2) + band + 1);
					if (a < b) { ivA[nIv] = a; ivB[nIv] = b; ++nIv; }
				}
				if (nIv == 2)
				{
					if (ivA[1] < ivA[0]) { std::swap(ivA[0], ivA[1]); std::swap(ivB[0], ivB[1]); }
					if (ivA[1] <= ivB[0]) { ivB[0] = std::max(ivB[0], ivB[1]); nIv = 1; }
				}
			}
			for (int iv = 0; iv < nIv; ++iv)
			{
				for (int px = ivA[iv]; px < ivB[iv]; ++px)
				{
					const double X = (px + 0.5 - view.cx) / radius;
					const double r2 = X * X + Y * Y;
					if (r2 >= 1) continue;
					const double Z = std::sqrt(1 - r2);
					const double d = capDist(cap, X, Y, Z, std::max(Z, 0.08), radius);
					if (d < lo || d > hi) continue;
					const float line = clamp01(lineW * 0.5 + 0.5 - std::fabs(d - lineW * 0.5));
					const float glow = d > 0 && d < glowLen ? (float)((1 - d / glowLen) * (1 - d / glowLen)) * ENEMY_GLOW : 0.0f;
					const float cov = std::max(line, glow) * limb(r2, radius);
					if (cov > 0.004f) out[c * n + (px - ox)] = cov;
				}
			}
		}
	}, capRows.data());
}

/**
 * The main base: a compass star of four points, each split along its axis into a light and a dark
 * half (they turn the same way round), on a thin dark outline, with a dark dot in the middle. Worked
 * out again only when the scale or the colour changes, at 4x4 samples a pixel.
 */
void HdRadar::drawMainBase(float cx, float cy, int k, Uint32 color)
{
	if (k <= 0) return;
	const int size = 7 * k + 2;
	if (k != _mainK || color != _mainColor || _mainMark.empty())
	{
		_mainK = k;
		_mainColor = color;
		_mainMark.assign((size_t)size * size, 0);
		const double mid = size * 0.5;
		// the outline's tips end at 3.5 base pixels, as far as a globe marker's edge
		const double line = std::max(0.8, 0.5 * k), R = 3.5 * k - line, r = 1.3 * k, hole = 0.6 * k;
		// a quadrant of the star is the triangles O-(tip,0)-(q,q) and O-(q,q)-(0,tip), q = waist / sqrt 2
		auto inStar = [](double x, double y, double tip, double waist)
		{
			x = std::fabs(x); y = std::fabs(y);
			const double q = waist * 0.70710678;
			// on the centre's side of the edge from (tip,0) to (q,q), or of the one from (q,q) to (0,tip)
			const bool a = y <= x && (q - tip) * y - q * (x - tip) >= 0;
			const bool b = x <= y && (q - tip) * x - q * (y - tip) >= 0;
			return a || b;
		};
		const double lr = ((color >> 16) & 0xFF), lg = ((color >> 8) & 0xFF), lb = (color & 0xFF);
		const int S = 4;
		for (int py = 0; py < size; ++py)
		{
			for (int px = 0; px < size; ++px)
			{
				double cr = 0, cg = 0, cb = 0, ca = 0;
				for (int sy = 0; sy < S; ++sy)
				{
					for (int sx = 0; sx < S; ++sx)
					{
						const double X = px + (sx + 0.5) / S - mid, Y = py + (sy + 0.5) / S - mid;
						double f, sr, sg, sb;
						if (X * X + Y * Y < hole * hole)
						{
							f = 1; sr = sg = sb = 24;
						}
						else if (inStar(X, Y, R, r))
						{
							const bool light = std::fabs(Y) > std::fabs(X) ? X * Y > 0 : X * Y < 0;
							const double m = light ? 1.0 : 0.62;
							f = 1; sr = lr * m; sg = lg * m; sb = lb * m;
						}
						else if (inStar(X, Y, R + line, r + line))
						{
							f = 0.8; sr = sg = sb = 12;
						}
						else continue;
						cr += sr * f; cg += sg * f; cb += sb * f; ca += f;
					}
				}
				if (ca <= 0) continue;
				const double a = ca / (S * S);
				auto ch = [&](double v) { return (Uint32)std::min(255.0, v / ca + 0.5); };
				_mainMark[(size_t)py * size + px] = (Uint32)(a * 255 + 0.5) << 24 | ch(cr) << 16 | ch(cg) << 8 | ch(cb);
			}
		}
	}
	HdUi::instance().drawImage(_mainMark.data(), size, size, (int)std::lround(cx - size * 0.5), (int)std::lround(cy - size * 0.5));
}

}
