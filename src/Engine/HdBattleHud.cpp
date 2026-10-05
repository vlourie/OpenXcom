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
#include "HdBattleHud.h"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include "HdUi.h"
#include "HdWorkers.h"
#include "Options.h"

namespace OpenXcom
{

namespace
{

// the panel's own colours (0xAARRGGBB), the same in every mod: a dark slate with one warm accent, or
// the gold of the original panel (oxceHdBattleHudColor 1, the ramp of the Piratez panel picture)
struct Theme
{
	Uint32 panelTop, panelBottom, panelEdge;
	Uint32 tileTop, tileBottom, tileEdge, hoverTop, hoverBottom, sheenTop, sheenBottom;
	Uint32 accent, litTop, litBottom;
	Uint32 icon, iconHover, iconLit;
	Uint32 wellTop, wellBottom, wellEdge;
	Uint32 cardTop, cardBottom, cardEdge;
	Uint32 rankFill;
	bool plaques;     ///< the keys are the original's plaques in relief, the pictograms struck in (drawPlaque)
};

const Theme SLATE = {
	0xF4171D26u, 0xF40B0E13u, 0x38FFFFFFu,
	0xFF2A323Eu, 0xFF1C222Bu, 0x2EFFFFFFu, 0xFF36414Fu, 0xFF252D38u, 0x14FFFFFFu, 0x02FFFFFFu,
	0xFFE6A23Cu, 0xFFF2B655u, 0xFFC2822Au,
	0xFFCDD6E1u, 0xFFFFFFFFu, 0xFF22180Bu,
	0xFF05070Au, 0xFF0D1015u, 0x36FFFFFFu,
	0xFF0E1218u, 0xFF0A0D11u, 0x22FFFFFFu,
	0xFF151A22u,
	false,
};

const Theme GOLD = {
	0xF4301A0Au, 0xF4120904u, 0xA0F8E57Bu,
	0xFFD8A73Du, 0xFFA36725u, 0x90FFF6AFu, 0xFFE4CA48u, 0xFFB77B2Cu, 0x38FFF6AFu, 0x04FFF6AFu,
	0xFFFFF6AFu, 0xFFFFF6AFu, 0xFFE4CA48u,
	0xFF43210Du, 0xFF221209u, 0xFF341A0Bu,
	0xFF0A0603u, 0xFF1A0F06u, 0xB0C79033u,
	0xFF22140Au, 0xFF150C05u, 0x90B77B2Cu,
	0xFF341A0Bu,
	true,
};

const Theme &theme()
{
	return Options::oxceHdBattleHudColor == 1 ? GOLD : SLATE;
}

inline Uint32 withAlpha(Uint32 c, Uint32 a) { return (c & 0x00FFFFFFu) | (a << 24); }

/// A shape of a pictogram, in the button's base pixels; a cut takes away from what is drawn before it.
struct Shape
{
	enum Type { CIRCLE, ARC, SEGMENT, POLYGON, ROUND_RECT } type;
	bool cut = false;
	float a = 0, b = 0, c = 0, d = 0, e = 0, f = 0, g = 0;
	std::vector<float> pts;
	float x0 = 0, y0 = 0, x1 = 0, y1 = 0;   ///< the bounding box

	bool inside(float x, float y) const
	{
		if (x < x0 || x > x1 || y < y0 || y > y1) return false;
		switch (type)
		{
		case CIRCLE:
		{
			const float dx = x - a, dy = y - b;
			return dx * dx + dy * dy <= c * c;
		}
		case ARC:
		{
			// a ring (centre a b, radius c, width d) from angle e to f (degrees, clockwise from +x on screen)
			const float dx = x - a, dy = y - b;
			const float r = std::sqrt(dx * dx + dy * dy);
			if (std::fabs(r - c) > d * 0.5f) return false;
			if (f - e >= 360.0f) return true;
			float ang = std::atan2(dy, dx) * 57.29578f;
			while (ang < e) ang += 360.0f;
			return ang <= f;
		}
		case SEGMENT:
		{
			// a stroke from (a, b) to (c, d), e wide, round ends
			const float vx = c - a, vy = d - b, wx = x - a, wy = y - b;
			const float l2 = vx * vx + vy * vy;
			const float t = l2 > 0 ? std::min(std::max((wx * vx + wy * vy) / l2, 0.0f), 1.0f) : 0.0f;
			const float px = wx - t * vx, py = wy - t * vy;
			return px * px + py * py <= e * e * 0.25f;
		}
		case POLYGON:
		{
			bool in = false;
			const size_t n = pts.size() / 2;
			for (size_t i = 0, j = n - 1; i < n; j = i++)
			{
				const float xi = pts[2 * i], yi = pts[2 * i + 1], xj = pts[2 * j], yj = pts[2 * j + 1];
				if ((yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) in = !in;
			}
			return in;
		}
		case ROUND_RECT:
		{
			// (a, b) - (c, d), corner radius e
			const float r = e;
			const float cx = std::min(std::max(x, a + r), c - r), cy = std::min(std::max(y, b + r), d - r);
			const float dx = x - cx, dy = y - cy;
			return dx * dx + dy * dy <= r * r;
		}
		}
		return false;
	}
};

/// A pictogram: shapes in drawing order, in a frame moved by (ox, oy).
struct Pic
{
	std::vector<Shape> shapes;
	float ox = 0, oy = 0;
	bool cutting = false;

	Pic &at(float x, float y) { ox = x; oy = y; return *this; }
	Pic &cut(bool on) { cutting = on; return *this; }
	Shape &add(Shape::Type t)
	{
		shapes.emplace_back();
		Shape &s = shapes.back();
		s.type = t;
		s.cut = cutting;
		return s;
	}
	Pic &circle(float x, float y, float r)
	{
		Shape &s = add(Shape::CIRCLE);
		s.a = x + ox; s.b = y + oy; s.c = r;
		s.x0 = s.a - r; s.x1 = s.a + r; s.y0 = s.b - r; s.y1 = s.b + r;
		return *this;
	}
	Pic &arc(float x, float y, float r, float w, float from = 0, float to = 360)
	{
		Shape &s = add(Shape::ARC);
		s.a = x + ox; s.b = y + oy; s.c = r; s.d = w; s.e = from; s.f = to;
		const float o = r + w * 0.5f;
		s.x0 = s.a - o; s.x1 = s.a + o; s.y0 = s.b - o; s.y1 = s.b + o;
		return *this;
	}
	Pic &line(float xa, float ya, float xb, float yb, float w)
	{
		Shape &s = add(Shape::SEGMENT);
		s.a = xa + ox; s.b = ya + oy; s.c = xb + ox; s.d = yb + oy; s.e = w;
		s.x0 = std::min(s.a, s.c) - w; s.x1 = std::max(s.a, s.c) + w;
		s.y0 = std::min(s.b, s.d) - w; s.y1 = std::max(s.b, s.d) + w;
		return *this;
	}
	Pic &poly(std::initializer_list<float> p)
	{
		Shape &s = add(Shape::POLYGON);
		s.pts.assign(p.begin(), p.end());
		s.x0 = s.y0 = 1e9f; s.x1 = s.y1 = -1e9f;
		for (size_t i = 0; i + 1 < s.pts.size(); i += 2)
		{
			s.pts[i] += ox; s.pts[i + 1] += oy;
			s.x0 = std::min(s.x0, s.pts[i]); s.x1 = std::max(s.x1, s.pts[i]);
			s.y0 = std::min(s.y0, s.pts[i + 1]); s.y1 = std::max(s.y1, s.pts[i + 1]);
		}
		return *this;
	}
	Pic &rect(float xa, float ya, float xb, float yb, float r)
	{
		Shape &s = add(Shape::ROUND_RECT);
		s.a = xa + ox; s.b = ya + oy; s.c = xb + ox; s.d = yb + oy;
		s.e = std::min(r, std::min(xb - xa, yb - ya) * 0.5f);
		s.x0 = s.a; s.x1 = s.c; s.y0 = s.b; s.y1 = s.d;
		return *this;
	}

	// --- the pieces the pictograms are made of (x = the piece's centre line) ---

	/// A standing figure, its head's top at y = top; s = 1 is 11.2 base pixels tall (feet at top + 11.2).
	Pic &person(float x, float top = 2.45f, float s = 1.0f)
	{
		auto Y = [&](float v) { return top + (v - 2.45f) * s; };
		circle(x, Y(4.2f), 1.75f * s);
		rect(x - 1.75f * s, Y(6.4f), x + 1.75f * s, Y(10.3f), 0.9f * s);
		line(x - 2.15f * s, Y(7.0f), x - 2.7f * s, Y(10.0f), 1.0f * s);
		line(x + 2.15f * s, Y(7.0f), x + 2.7f * s, Y(10.0f), 1.0f * s);
		line(x - 0.85f * s, Y(10.0f), x - 1.05f * s, Y(13.3f), 1.4f * s);
		line(x + 0.85f * s, Y(10.0f), x + 1.05f * s, Y(13.3f), 1.4f * s);
		return *this;
	}
	/// A figure shooting to the right, for the 17 x 11 reserve buttons: the gun at the hip (snap and
	/// auto) or raised to the eye (aimed), as the mod draws them.
	Pic &shooter(float x, bool aimed)
	{
		circle(x, 2.6f, 1.3f);
		rect(x - 1.05f, 3.9f, x + 1.05f, 6.8f, 0.5f);
		line(x - 0.45f, 6.5f, x - 1.7f, 9.2f, 1.15f);
		line(x + 0.45f, 6.5f, x + 1.5f, 9.2f, 1.15f);
		if (aimed)
		{
			line(x + 0.6f, 4.3f, x + 2.4f, 3.3f, 1.0f);
			rect(x + 1.6f, 2.75f, x + 7.0f, 3.75f, 0.3f);
		}
		else
		{
			line(x + 0.6f, 4.6f, x + 2.6f, 4.9f, 1.0f);
			rect(x + 2.0f, 4.35f, x + 7.0f, 5.35f, 0.3f);
		}
		return *this;
	}
	/// The levels of the map: a narrow column of three storeys.
	Pic &storeys(float x)
	{
		rect(x - 2.4f, 3.0f, x + 2.4f, 13.0f, 0.5f);
		cut(true);
		for (int i = 0; i < 3; ++i)
		{
			rect(x - 1.25f, 4.15f + 2.95f * i, x + 1.25f, 6.05f + 2.95f * i, 0.2f);
		}
		return cut(false);
	}
	/// A kneeling figure, the same feet line.
	Pic &kneeling(float x)
	{
		// upright, one knee on the ground, the other leg bent forward
		circle(x, 5.3f, 1.75f);
		rect(x - 1.65f, 7.5f, x + 1.65f, 10.9f, 0.9f);
		line(x - 2.05f, 8.1f, x - 2.5f, 10.6f, 1.0f);
		line(x + 2.05f, 8.1f, x + 2.5f, 10.6f, 1.0f);
		line(x + 0.6f, 10.5f, x + 3.4f, 10.8f, 1.4f);
		line(x + 3.4f, 10.8f, x + 3.6f, 13.4f, 1.4f);
		line(x - 0.8f, 10.5f, x - 1.0f, 13.1f, 1.4f);
		line(x - 1.0f, 13.3f, x - 3.6f, 13.4f, 1.3f);
		return *this;
	}
	/// A triangle pointing up or down, centred at (x, y).
	Pic &arrow(float x, float y, bool up)
	{
		const float s = up ? 1.0f : -1.0f;
		return poly({ x - 3.2f, y + 2.0f * s, x + 3.2f, y + 2.0f * s, x, y - 2.6f * s });
	}
	/// A triangle pointing right, centred at (x, y).
	Pic &arrowRight(float x, float y)
	{
		return poly({ x - 2.0f, y - 2.8f, x + 2.4f, y, x - 2.0f, y + 2.8f });
	}
};

/// The pictograms follow the mod's own picture of the panel (the same sign on the same button), drawn
/// again as clean shapes: what the player knows a button by stays.
Pic makeIcon(HdBattleHud::Icon icon)
{
	Pic p;
	switch (icon)
	{
	case HdBattleHud::ICON_UNIT_UP: p.arrow(10.5f, 8.2f, true).person(20.5f); break;
	case HdBattleHud::ICON_UNIT_DOWN: p.arrow(10.5f, 7.8f, false).person(20.5f); break;
	case HdBattleHud::ICON_MAP_UP: p.arrow(10.5f, 8.2f, true).storeys(20.5f); break;
	case HdBattleHud::ICON_MAP_DOWN: p.arrow(10.5f, 7.8f, false).storeys(20.5f); break;
	case HdBattleHud::ICON_SHOW_MAP:
		// a map sheet with a tab, its left part a grid of squares
		p.rect(8.6f, 4.2f, 23.4f, 13.0f, 0.9f).rect(17.0f, 2.6f, 23.4f, 5.2f, 0.7f);
		p.cut(true).rect(9.8f, 5.4f, 22.2f, 11.8f, 0.3f).cut(false);
		for (int i = 0; i < 9; ++i)
		{
			const float x = 10.5f + (i % 3) * 1.85f, y = 6.1f + (i / 3) * 1.85f;
			p.rect(x, y, x + 1.3f, y + 1.3f, 0.15f);
		}
		break;
	case HdBattleHud::ICON_KNEEL:
		// stand / kneel
		p.person(8.6f).line(13.6f, 12.8f, 18.4f, 3.2f, 1.0f).kneeling(22.8f);
		break;
	case HdBattleHud::ICON_INVENTORY:
		p.person(16.0f);
		break;
	case HdBattleHud::ICON_CENTER:
		// the unit in the middle of the view: a small figure in four ticks
		p.person(16.0f, 4.3f, 0.66f);
		p.line(10.6f, 6.2f, 10.6f, 9.8f, 1.1f).line(21.4f, 6.2f, 21.4f, 9.8f, 1.1f);
		p.line(14.2f, 2.6f, 17.8f, 2.6f, 1.1f).line(14.2f, 13.4f, 17.8f, 13.4f, 1.1f);
		break;
	case HdBattleHud::ICON_NEXT_SOLDIER: p.person(9.0f).arrowRight(16.3f, 8.2f).person(23.0f); break;
	case HdBattleHud::ICON_NEXT_STOP:
		// done with this one (struck through), on to the next
		p.person(8.4f).cut(true).line(4.6f, 13.4f, 12.2f, 2.8f, 2.6f).cut(false).line(4.6f, 13.4f, 12.2f, 2.8f, 1.0f);
		p.line(13.6f, 8.2f, 17.2f, 8.2f, 1.1f).poly({ 16.4f, 6.0f, 19.2f, 8.2f, 16.4f, 10.4f });
		p.person(23.6f);
		break;
	case HdBattleHud::ICON_SHOW_LAYERS:
	{
		// three stacked diamonds, each lower one cut where the upper lies over it
		auto diamond = [&](float y, float grow) { p.poly({ 16.0f, y - 2.7f - grow, 22.2f + grow * 2.0f, y, 16.0f, y + 2.7f + grow, 9.8f - grow * 2.0f, y }); };
		diamond(11.2f, 0.0f);
		p.cut(true); diamond(8.0f, 0.75f); p.cut(false);
		diamond(8.0f, 0.0f);
		p.cut(true); diamond(4.8f, 0.75f); p.cut(false);
		diamond(4.8f, 0.0f);
		break;
	}
	case HdBattleHud::ICON_LINKS:
		p.rect(10.4f, 3.9f, 21.6f, 5.6f, 0.8f).rect(10.4f, 7.15f, 21.6f, 8.85f, 0.8f).rect(10.4f, 10.4f, 21.6f, 12.1f, 0.8f);
		break;
	case HdBattleHud::ICON_OPTIONS:
		// a question mark
		p.arc(16.0f, 5.9f, 2.7f, 1.7f, 180.0f, 405.0f);
		p.line(17.9f, 7.8f, 16.0f, 9.2f, 1.7f).line(16.0f, 9.2f, 16.0f, 10.1f, 1.7f);
		p.circle(16.0f, 12.6f, 1.05f);
		break;
	case HdBattleHud::ICON_END_TURN:
		// a struck circle
		p.arc(16.0f, 8.0f, 4.1f, 1.4f).line(13.3f, 10.7f, 18.7f, 5.3f, 1.4f);
		break;
	case HdBattleHud::ICON_ABORT:
		// back on board: the craft, an arrow up to it
		p.poly({ 8.6f, 6.6f, 10.0f, 5.2f, 20.4f, 4.7f, 22.4f, 2.0f, 24.0f, 2.0f, 23.4f, 5.4f, 22.2f, 6.9f, 10.2f, 7.5f });
		p.poly({ 14.4f, 6.8f, 18.6f, 6.8f, 16.6f, 8.0f, 13.8f, 8.0f });
		p.poly({ 13.4f, 11.8f, 18.6f, 11.8f, 16.0f, 9.2f }).line(16.0f, 11.4f, 16.0f, 13.8f, 1.3f);
		break;
	case HdBattleHud::ICON_RESERVE_NONE:
		p.line(2.6f, 5.5f, 11.6f, 5.5f, 1.3f).poly({ 10.8f, 2.7f, 14.6f, 5.5f, 10.8f, 8.3f });
		break;
	case HdBattleHud::ICON_RESERVE_SNAP:
		p.shooter(4.4f, false).line(12.6f, 4.85f, 14.4f, 4.85f, 1.0f);
		break;
	case HdBattleHud::ICON_RESERVE_AIMED:
		p.shooter(4.4f, true).line(12.6f, 3.25f, 14.4f, 3.25f, 1.0f);
		break;
	case HdBattleHud::ICON_RESERVE_AUTO:
		p.shooter(4.4f, false).line(10.4f, 4.85f, 11.0f, 4.85f, 1.0f).line(12.2f, 4.85f, 12.8f, 4.85f, 1.0f).line(14.0f, 4.85f, 14.6f, 4.85f, 1.0f);
		break;
	case HdBattleHud::ICON_RESERVE_KNEEL:
		// down to the knee: an arrow over a kneeling figure
		p.line(5.0f, 2.4f, 5.0f, 6.6f, 1.2f).poly({ 2.6f, 5.6f, 7.4f, 5.6f, 5.0f, 8.6f });
		p.at(1.8f, 6.2f).kneeling(3.2f);
		break;
	case HdBattleHud::ICON_ZERO_TUS:
		// the unit's time units to nought: a figure over a struck zero
		p.person(5.0f, 2.4f, 0.66f).rect(2.2f, 10.5f, 7.8f, 11.5f, 0.3f);
		p.rect(2.9f, 13.0f, 7.1f, 19.6f, 2.1f).cut(true).rect(4.1f, 14.2f, 5.9f, 18.4f, 0.9f).cut(false);
		p.line(4.2f, 17.9f, 5.8f, 14.7f, 0.8f);
		break;
	default:
		break;
	}
	return p;
}

/// A pictogram's coverage at a scale (one byte per world pixel), and its colourings.
struct Raster
{
	int w = 0, h = 0;
	std::vector<Uint8> cov;
	std::unordered_map<Uint32, std::vector<Uint32>> colored;
};

int cacheScale = 0;
std::unordered_map<Uint64, Raster> cache;

const Raster &raster(HdBattleHud::Icon icon, int w, int h, int k, bool small = false)
{
	if (k != cacheScale)
	{
		cache.clear();
		cacheScale = k;
	}
	const Uint64 key = ((Uint64)small << 40) | ((Uint64)icon << 32) | ((Uint64)(w & 0xFFFF) << 16) | (Uint64)(h & 0xFFFF);
	auto found = cache.find(key);
	if (found != cache.end()) return found->second;
	Raster &r = cache[key];
	r.w = w * k;
	r.h = h * k;
	r.cov.assign((size_t)r.w * r.h, 0);
	const Pic pic = makeIcon(icon);
	// 4 x 4 samples a pixel; the rows are shared out to the render threads (a hand of pictograms a scale)
	const int S = 4;
	// small: shrunk about the button's centre, to sit inside a plaque's sunken field
	const float grow = small ? 1.0f / 0.8f : 1.0f;
	const float inv = grow / (float)k, cx = w * 0.5f * (1.0f - grow), cy = h * 0.5f * (1.0f - grow);
	auto rows = [&](int ra, int rb)
	{
		for (int py = ra; py < rb; ++py)
		{
			for (int px = 0; px < r.w; ++px)
			{
				int hits = 0;
				for (int sy = 0; sy < S; ++sy)
				{
					const float y = (py + (sy + 0.5f) / S) * inv + cy;
					for (int sx = 0; sx < S; ++sx)
					{
						const float x = (px + (sx + 0.5f) / S) * inv + cx;
						bool in = false;
						for (const Shape &s : pic.shapes)
						{
							if (s.cut ? in : !in)
							{
								if (s.inside(x, y)) in = !s.cut;
							}
						}
						hits += in;
					}
				}
				r.cov[(size_t)py * r.w + px] = (Uint8)((hits * 255 + S * S / 2) / (S * S));
			}
		}
	};
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(r.h / 8, pool.threads() * 2));
	pool.run(jobs, [&](int job) { rows((int)((long long)r.h * job / jobs), (int)((long long)r.h * (job + 1) / jobs)); });
	return r;
}

/// The pictogram in a colour: straight alpha 0xAARRGGBB, cached per colour.
const std::vector<Uint32> &colored(const Raster &r, Uint32 color)
{
	Raster &rw = const_cast<Raster&>(r);
	auto found = rw.colored.find(color);
	if (found != rw.colored.end()) return found->second;
	std::vector<Uint32> &out = rw.colored[color];
	out.resize(r.cov.size());
	const Uint32 a = color >> 24;
	for (size_t i = 0; i < r.cov.size(); ++i)
	{
		out[i] = withAlpha(color, (r.cov[i] * a + 127) / 255);
	}
	return out;
}

/// The colour of a palette entry, or the accent for none.
Uint32 tintOf(Uint8 tint, const SDL_Color *pal)
{
	return tint && pal ? HdUi::rgba(pal[tint]) : theme().accent;
}

/// The ramp the mod's panel picture is drawn with, dark to light.
const Uint32 GOLD_RAMP[] = {
	0xFF120B07u, 0xFF221209u, 0xFF341A0Bu, 0xFF43210Du, 0xFF52280Fu, 0xFF6C3B16u, 0xFF86511Eu, 0xFFA36725u,
	0xFFB77B2Cu, 0xFFC79033u, 0xFFD8A73Du, 0xFFE4CA48u, 0xFFF8E57Bu, 0xFFFDF19Bu, 0xFFFFF6AFu, 0xFFFFFFD0u,
};

Uint32 mix(Uint32 a, Uint32 b, float t)
{
	auto ch = [&](int sh) { return (Uint32)((float)((a >> sh) & 0xFF) * (1.0f - t) + (float)((b >> sh) & 0xFF) * t + 0.5f) << sh; };
	return 0xFF000000u | ch(16) | ch(8) | ch(0);
}

/// A shade 0..1 of the metal: the gold ramp, or a key's own colour from nearly black to nearly white.
Uint32 rampColor(float s, Uint32 tint)
{
	s = std::min(std::max(s, 0.0f), 1.0f);
	if (!tint)
	{
		const float f = s * 15.0f;
		const int i = std::min((int)f, 14);
		return mix(GOLD_RAMP[i], GOLD_RAMP[i + 1], f - (float)i);
	}
	if (s < 0.6f) return mix(0xFF000000u, tint | 0xFF000000u, 0.12f + 0.88f * s / 0.6f);
	return mix(tint | 0xFF000000u, 0xFFFFFFE0u, (s - 0.6f) / 0.4f * 0.5f);
}

/// A key's own colour made as deep as the original's plaques: more saturated, its strongest channel at D8.
Uint32 vivid(Uint32 c)
{
	float ch[3] = { (float)((c >> 16) & 0xFF), (float)((c >> 8) & 0xFF), (float)(c & 0xFF) };
	const float grey = (ch[0] + ch[1] + ch[2]) / 3.0f;
	float top = 1.0f;
	for (float &v : ch)
	{
		v = std::max(grey + 1.8f * (v - grey), 0.0f);
		top = std::max(top, v);
	}
	Uint32 out = 0xFF000000u;
	for (int i = 0; i < 3; ++i)
	{
		out |= (Uint32)std::min(ch[i] * 216.0f / top + 0.5f, 255.0f) << (16 - 8 * i);
	}
	return out;
}

/// Distance inside a rounded box (negative outside), at a pixel's centre.
float insideBox(float x, float y, float x0, float y0, float x1, float y1, float r)
{
	const float qx = std::fabs(x - (x0 + x1) * 0.5f) - ((x1 - x0) * 0.5f - r);
	const float qy = std::fabs(y - (y0 + y1) * 0.5f) - ((y1 - y0) * 0.5f - r);
	const float ox = std::max(qx, 0.0f), oy = std::max(qy, 0.0f);
	return r - std::sqrt(ox * ox + oy * oy) - std::min(std::max(qx, qy), 0.0f);
}

inline float ease(float t) { t = std::min(std::max(t, 0.0f), 1.0f); return t * (2.0f - t); }

/// Metal in relief, lit from the upper left as the original picture is: a height a pixel (1 = the top of a
/// plaque), a darkening (the bottom of a cut, the foot of a rim) and a coverage; the slopes catch or lose
/// the light, the steepest ones facing it glint. The rows go to the render threads.
std::vector<Uint32> shadeMetal(const std::vector<float> &height, const std::vector<float> &dark, const std::vector<float> &cover, int W, int H, float k, float lift, Uint32 tint)
{
	std::vector<Uint32> out((size_t)W * H, 0);
	const float lx = -0.5f, ly = -0.6f, lz = 0.62f;
	auto rows = [&](int ra, int rb)
	{
		for (int y = ra; y < rb; ++y)
		{
			const int yu = std::max(y - 1, 0), yd = std::min(y + 1, H - 1);
			for (int x = 0; x < W; ++x)
			{
				const size_t i = (size_t)y * W + x;
				const float a = cover[i];
				if (a <= 0.0f) continue;
				const int xl = std::max(x - 1, 0), xr = std::min(x + 1, W - 1);
				const float gx = (height[(size_t)y * W + xr] - height[(size_t)y * W + xl]) * 0.5f * k;
				const float gy = (height[(size_t)yd * W + x] - height[(size_t)yu * W + x]) * 0.5f * k;
				const float d = (-gx * lx - gy * ly + lz) / std::sqrt(gx * gx + gy * gy + 1.0f);
				const float glint = 0.32f * std::pow(std::max(d, 0.0f), 10.0f);
				const float s = 0.6f + 0.9f * (d - lz) + glint - dark[i] + lift;
				out[i] = withAlpha(rampColor(s, tint), (Uint32)(std::min(a, 1.0f) * 255.0f + 0.5f));
			}
		}
	};
	HdWorkers &pool = HdWorkers::instance();
	const int jobs = std::max(1, std::min(H / 8, pool.threads() * 2));
	pool.run(jobs, [&](int job) { rows((int)((long long)H * job / jobs), (int)((long long)H * (job + 1) / jobs)); });
	return out;
}

/// A pictogram's coverage softened by two box passes of radius rb: the walls of the cut.
std::vector<float> softCover(const Raster &pic, int rb)
{
	const int W = pic.w, H = pic.h;
	std::vector<float> a(pic.cov.size()), b(pic.cov.size());
	for (size_t i = 0; i < a.size(); ++i) a[i] = pic.cov[i] / 255.0f;
	const float n = 1.0f / (float)(2 * rb + 1);
	for (int pass = 0; pass < 2; ++pass)
	{
		for (int y = 0; y < H; ++y)
			for (int x = 0; x < W; ++x)
			{
				float sum = 0;
				for (int d = -rb; d <= rb; ++d) sum += a[(size_t)y * W + std::min(std::max(x + d, 0), W - 1)];
				b[(size_t)y * W + x] = sum * n;
			}
		for (int y = 0; y < H; ++y)
			for (int x = 0; x < W; ++x)
			{
				float sum = 0;
				for (int d = -rb; d <= rb; ++d) sum += b[(size_t)std::min(std::max(y + d, 0), H - 1) * W + x];
				a[(size_t)y * W + x] = sum * n;
			}
	}
	return a;
}

int metalScale = 0;
std::unordered_map<Uint64, std::vector<Uint32>> metalCache;

std::vector<Uint32> *metalCached(Uint64 key, int k)
{
	if (k != metalScale)
	{
		metalCache.clear();
		metalScale = k;
	}
	auto found = metalCache.find(key);
	return found != metalCache.end() ? &found->second : nullptr;
}

/// The original panel's key cast in metal: a plaque with rounded bevels, a sunken field, the pictogram
/// struck into it (its own colour keys - the reserves - with the figure standing out unless lit).
/// state 0 still, 1 under the mouse, 2 lit.
const std::vector<Uint32> &plaque(HdBattleHud::Icon icon, int w, int h, int k, int state, Uint32 tint)
{
	const Uint64 key = ((Uint64)(tint & 0xFFFFFF) << 32) | ((Uint64)state << 30) | ((Uint64)(icon & 0x3F) << 24) | ((Uint64)(w & 0xFFF) << 12) | (Uint64)(h & 0xFFF);
	if (std::vector<Uint32> *hit = metalCached(key, k)) return *hit;
	const int W = w * k, H = h * k;
	const float g = 0.6f * k, R = 2.0f * k, b1 = 1.2f * k, b2 = 0.7f * k;
	const float m = (h >= 14 ? 2.3f : 1.6f) * k;
	const bool struck = !tint || state == 2;
	// the cut's walls from the softened pictogram, its colour from the sharp one: thin strokes stay legible
	std::vector<float> cut;
	const Raster *sharp = nullptr;
	if (icon != HdBattleHud::ICON_NONE && icon < HdBattleHud::ICON_COUNT)
	{
		sharp = &raster(icon, w, h, k, true);
		cut = softCover(*sharp, std::max(1, (int)std::lround(0.3f * k)));
	}
	std::vector<float> height((size_t)W * H), dark((size_t)W * H), cover((size_t)W * H);
	for (int y = 0; y < H; ++y)
	{
		for (int x = 0; x < W; ++x)
		{
			const size_t i = (size_t)y * W + x;
			const float sd = insideBox(x + 0.5f, y + 0.5f, g, g, W - g, H - g, R);
			cover[i] = std::min(std::max(sd + 0.5f, 0.0f), 1.0f);
			const float rim = ease(sd / b1), sunk = ease((sd - m) / b2);
			float hgt = rim - 0.6f * sunk;
			// the field darker at the foot of the rim, the rim's top a little brighter than the field
			float dk = 0.18f * sunk * (1.0f - std::min(std::max((sd - m) / (2.5f * k), 0.0f), 1.0f)) - 0.06f * (rim - sunk);
			if (!cut.empty())
			{
				const float c = cut[i], ink = sharp->cov[i] / 255.0f;
				if (struck) { hgt -= 0.5f * c; dk += 0.15f * c + 0.3f * ink; }
				else { hgt += 0.45f * c; dk -= 0.1f * c + 0.32f * ink; }
			}
			height[i] = hgt;
			dark[i] = dk;
		}
	}
	// a key's own colour sits a step lower, so its plaque keeps the colour instead of washing out
	const float lift = (state == 2 ? 0.1f : (state == 1 ? 0.05f : 0.0f)) - (tint && state != 2 ? 0.1f : 0.0f);
	return metalCache[key] = shadeMetal(height, dark, cover, W, H, (float)k, lift, tint ? vivid(tint) : 0);
}

/// A gold frame cast round a box (the wells under the items in hand): a rounded tube f wide, w x h world
/// pixels inside it.
const std::vector<Uint32> &metalFrame(int w, int h, int k, float f)
{
	const Uint64 key = (1ull << 63) | ((Uint64)(w & 0xFFFF) << 16) | (Uint64)(h & 0xFFFF);
	if (std::vector<Uint32> *hit = metalCached(key, k)) return *hit;
	const int fw = (int)std::ceil(f);
	const int W = w + 2 * fw, H = h + 2 * fw;
	std::vector<float> height((size_t)W * H), dark((size_t)W * H, 0.0f), cover((size_t)W * H);
	const float R = 2.5f * k, half = f * 0.5f;
	for (int y = 0; y < H; ++y)
	{
		for (int x = 0; x < W; ++x)
		{
			const size_t i = (size_t)y * W + x;
			const float sd = insideBox(x + 0.5f, y + 0.5f, 0.0f, 0.0f, (float)W, (float)H, R);
			// a round profile across the tube, open inside
			const float t = (sd - half) / half;
			height[i] = std::sqrt(std::max(1.0f - t * t, 0.0f));
			cover[i] = std::min(std::max(sd + 0.5f, 0.0f), 1.0f) * std::min(std::max(f - sd + 0.5f, 0.0f), 1.0f);
		}
	}
	return metalCache[key] = shadeMetal(height, dark, cover, W, H, (float)k * 0.6f, 0.0f, 0);
}

/// The original panel's key in metal (see plaque), drawn into its cell.
void drawPlaque(int x, int y, int w, int h, HdBattleHud::Icon icon, bool lit, bool over, Uint32 tint)
{
	const int k = HdUi::scale();
	const std::vector<Uint32> &img = plaque(icon, w, h, k, lit ? 2 : (over ? 1 : 0), tint);
	HdUi::instance().drawImage(img.data(), w * k, h * k, x * k, y * k);
}

}

bool HdBattleHud::on()
{
	return Options::oxceHdBattleHud && HdUi::skin();
}

void HdBattleHud::drawButton(int x, int y, int w, int h, Icon icon, bool lit, Uint8 tint, const SDL_Color *pal)
{
	const int k = HdUi::scale();
	if (k <= 0 || w <= 0 || h <= 0) return;
	HdUi &ui = HdUi::instance();
	ui.notePanel(x, y, w, h);
	const bool over = ui.hover(x, y, w, h);
	// a gap of about a base pixel between neighbours: the tiles read as separate keys
	const float in = 0.6f * k;
	const float x0 = (float)x * k + in, y0 = (float)y * k + in, x1 = (float)(x + w) * k - in, y1 = (float)(y + h) * k - in;
	const float r = 2.2f * k, edge = std::max(1.0f, 0.5f * k);
	const Theme &t = theme();
	const Uint32 accent = tintOf(tint, pal);
	if (t.plaques)
	{
		drawPlaque(x, y, w, h, icon, lit, over, tint ? accent : 0);
		return;
	}
	Uint32 face;
	if (lit)
	{
		// lit: the accent (the reserve buttons' own colour) filling the tile, the pictogram dark on it
		const Uint32 top = tint ? HdUi::scaled(accent, 1.15f) : t.litTop, bottom = tint ? HdUi::scaled(accent, 0.78f) : t.litBottom;
		ui.fillRoundRect(x0, y0, x1, y1, r, top, bottom);
		ui.strokeRoundRect(x0, y0, x1, y1, r, edge, withAlpha(HdUi::scaled(top, 1.2f), 0xE0));
		face = tint ? HdUi::scaled(accent, 0.22f) : t.iconLit;
	}
	else
	{
		ui.fillRoundRect(x0, y0, x1, y1, r, over ? t.hoverTop : t.tileTop, over ? t.hoverBottom : t.tileBottom);
		// a sheen on the upper half, a light top edge; under the mouse the edge takes the accent
		ui.fillRoundRect(x0 + edge, y0 + edge, x1 - edge, (y0 + y1) * 0.5f, std::max(r - edge, 0.0f), t.sheenTop, t.sheenBottom);
		ui.strokeRoundRect(x0, y0, x1, y1, r, edge, over ? withAlpha(accent, 0xD0) : (tint ? withAlpha(accent, 0x60) : t.tileEdge));
		face = tint ? HdUi::scaled(accent, over ? 1.25f : 1.1f) : (over ? t.iconHover : t.icon);
	}
	if (icon == ICON_NONE || icon >= ICON_COUNT) return;
	const Raster &pic = raster(icon, w, h, k);
	ui.drawImage(colored(pic, face).data(), pic.w, pic.h, x * k, y * k);
}

void HdHudPanel::addPart(Part part, const Surface *widget, Uint8 color)
{
	_parts.push_back(Item{ part, widget, color });
}

void HdHudPanel::hdMirror()
{
	if (!HdBattleHud::on())
	{
		InteractiveSurface::hdMirror();
		return;
	}
	const int k = HdUi::scale();
	if (k <= 0) return;
	HdUi &ui = HdUi::instance();
	const SDL_Color *pal = HdUi::paletteOf(this);
	const Theme &t = theme();
	const float x0 = (float)getX() * k, y0 = (float)getY() * k;
	const float x1 = (float)(getX() + getWidth()) * k, y1 = (float)(getY() + getHeight()) * k;
	const float edge = std::max(1.0f, 0.5f * k);
	// the map fades into the panel instead of ending at a hard line
	ui.fillRoundRect(x0, y0 - 4.0f * k, x1, y0, 0.0f, 0x00000000u, 0x70000000u);
	// the panel: rounded at the top, a fine light edge along it
	ui.fillRoundRect(x0, y0, x1, y1 + 3.0f * k, 3.0f * k, t.panelTop, t.panelBottom);
	ui.fillRoundRect(x0 + 2.0f * k, y0, x1 - 2.0f * k, y0 + edge, 0.0f, t.panelEdge, t.panelEdge);
	ui.notePanel(getX(), getY(), getWidth(), getHeight());
	for (const Item &item : _parts)
	{
		const Surface *s = item.widget;
		const float wx0 = (float)s->getX() * k, wy0 = (float)s->getY() * k;
		const float wx1 = (float)(s->getX() + s->getWidth()) * k, wy1 = (float)(s->getY() + s->getHeight()) * k;
		switch (item.part)
		{
		case HdHudPanel::PART_HAND:
		{
			const float m = 1.5f * k;
			ui.fillRoundRect(wx0 - m, wy0 - m, wx1 + m, wy1 + m, 2.5f * k, t.wellTop, t.wellBottom);
			if (t.plaques)
			{
				// the original's gold frame round the hand, cast in the same metal as the keys
				const float f = 2.2f * k;
				const int fw = (int)std::ceil(f);
				const int ix = (int)std::lround(wx0 - m), iy = (int)std::lround(wy0 - m);
				const int iw = (int)std::lround(wx1 + m) - ix, ih = (int)std::lround(wy1 + m) - iy;
				const std::vector<Uint32> &frame = metalFrame(iw, ih, k, f);
				ui.drawImage(frame.data(), iw + 2 * fw, ih + 2 * fw, ix - fw, iy - fw);
			}
			else
			{
				ui.strokeRoundRect(wx0 - m, wy0 - m, wx1 + m, wy1 + m, 2.5f * k, edge, t.wellEdge);
			}
			break;
		}
		case HdHudPanel::PART_CARD:
		{
			const float m = 1.0f * k;
			ui.fillRoundRect(wx0 - m, wy0 - m, wx1 + m, std::min(wy1 + m, y1 - 0.5f * k), 2.2f * k, t.cardTop, t.cardBottom);
			ui.strokeRoundRect(wx0 - m, wy0 - m, wx1 + m, std::min(wy1 + m, y1 - 0.5f * k), 2.2f * k, edge, t.cardEdge);
			break;
		}
		case HdHudPanel::PART_RANK:
			ui.fillRoundRect(wx0, wy0, wx1, wy1 - 0.5f * k, 1.6f * k, t.rankFill, t.rankFill);
			break;
		case HdHudPanel::PART_CHIP:
		{
			const Uint32 c = pal ? HdUi::rgba(pal[item.color]) : t.accent;
			ui.fillRoundRect(wx0 - 1.5f * k, wy0 - 1.0f * k, wx1 + 1.0f * k, wy1 + 1.0f * k, 1.4f * k, withAlpha(c, 0x40), withAlpha(c, 0x28));
			break;
		}
		}
	}
}

}
