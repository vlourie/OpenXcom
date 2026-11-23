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
#include "HdShots.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <memory>
#include <sstream>
#include <string>
#include <unordered_map>
#include "FileMap.h"
#include "Logger.h"
#include "Surface.h"
#include "SurfaceSet.h"
#include "../Mod/RuleItem.h"

namespace OpenXcom
{

namespace HdShots
{

namespace
{

const double PI = 3.14159265358979323846;
/// Samples a side of a pixel (the edges are analytic and smooth; this evens out the glow).
const int SS = 2;
/// A piece is this many pixels long at scale 4 (a few voxels of the way).
const int PIECE_BASE = 16;
const int MAX_PIECES = 128;
/// Pictures kept at most; those not asked for in the last IDLE frames go first.
const size_t KEEP = 256, KEEP_MAX = 1024;
const Uint32 IDLE = 240;

// sizes at scale 4 (a base pixel is 4), by Size
const double LASER_WIDTH[3] = { 4.0, 7.0, 11.0 };
const int LASER_VOXELS[3] = { 24, 40, 60 };
const double PLASMA_R[3] = { 7.5, 12.0, 17.0 };
const double GAUSS_LENGTH[3] = { 20.0, 30.0, 44.0 };
const double GAUSS_RADIUS[3] = { 3.2, 4.6, 6.4 };
const double GAUSS_AMP[3] = { 5.0, 7.0, 10.0 };
const double GAUSS_LAMBDA[3] = { 36.0, 50.0, 68.0 };
const double GAUSS_STROKE[3] = { 3.0, 4.0, 5.0 };
/// How far behind the capsule the coils of air reach (scale 4).
const double GAUSS_REACH = 270.0;

struct BeadDef { double off, rad, alpha; };
const BeadDef BEADS[4] = { { 1.95, 0.62, 0.9 }, { 3.2, 0.47, 0.8 }, { 4.3, 0.34, 0.65 }, { 5.2, 0.22, 0.5 } };

std::unordered_map<std::string, Kind> table;
bool tableRead = false;

void readTable()
{
	if (tableRead)
	{
		return;
	}
	tableRead = true;
	const std::string path = HdSprites::artPath("FX/shots.txt");
	if (!FileMap::fileExists(path))
	{
		return;
	}
	std::unique_ptr<std::istream> in = FileMap::getIStream(path);
	if (!in)
	{
		return;
	}
	std::string line;
	int lines = 0;
	while (std::getline(*in, line))
	{
		std::istringstream ss(line);
		std::string what, item, cls, size;
		if (!(ss >> what >> item >> cls >> size) || what != "shot")
		{
			continue;
		}
		Kind kind;
		kind.cls = cls == "laser" ? LASER : cls == "plasma" ? PLASMA : cls == "gauss" ? GAUSS : NONE;
		kind.size = size == "small" ? SMALL : size == "large" ? LARGE : MEDIUM;
		if (kind.cls != NONE)
		{
			table[item] = kind;
			++lines;
		}
	}
	Log(LOG_INFO) << "HD shots: " << lines << " weapons with a class of shot (hd/FX/shots.txt)";
}

struct Rgb { float r, g, b; };
/// Premultiplied colour of a sample.
struct Px { float r = 0, g = 0, b = 0, a = 0; };

inline float clamp01(double x) { return (float)(x < 0 ? 0 : x > 1 ? 1 : x); }
inline double smooth(double e0, double e1, double x)
{
	const double t = std::min(1.0, std::max(0.0, (x - e0) / (e1 - e0)));
	return t * t * (3 - 2 * t);
}
/// Lays colour `c` of coverage `cov` over the sample.
inline void over(Px &p, double cov, const Rgb &c)
{
	if (cov <= 0)
	{
		return;
	}
	const float k = clamp01(cov);
	p.r = p.r * (1 - k) + c.r * k;
	p.g = p.g * (1 - k) + c.g * k;
	p.b = p.b * (1 - k) + c.b * k;
	p.a = p.a * (1 - k) + k;
}
inline Rgb mix(const Rgb &a, const Rgb &b, double t)
{
	return { (float)(a.r + (b.r - a.r) * t), (float)(a.g + (b.g - a.g) * t), (float)(a.b + (b.b - a.b) * t) };
}
inline Rgb scaled(const Rgb &a, double k) { return { (float)(a.r * k), (float)(a.g * k), (float)(a.b * k) }; }

/// Everything a shot's samples need, set once for a picture.
struct Params
{
	int cls = NONE;
	double kf = 1;               ///< scale k / 4
	Rgb vivid, centre, mid, edge, tail, nose, body, rim, vein;
	const Colours *colours = nullptr;
	double w = 0, L = 0;         ///< laser: width and length, pixels
	double r = 0;                ///< plasma: radius
	double ls = 0, rs = 0, amp = 0, lam = 0, sw = 0, reach = 0;   ///< gauss
	double aMin = 0, aMax = 0, nMax = 0;  ///< the extent of the picture: behind the head, and aside from the axis
};

/// The colour of the laser ramp `t` (0 at the head, 1 at the tail).
Rgb rampAt(const Params &p, double t)
{
	const Colours &c = *p.colours;
	if (c.rampCount <= 0)
	{
		return p.vivid;
	}
	const double x = std::min(1.0, std::max(0.0, t)) * (c.rampCount - 1);
	const int i = std::min(c.rampCount - 1, (int)x);
	const int j = std::min(c.rampCount - 1, i + 1);
	const double f = x - i;
	auto at = [&](int n, int ch) { return c.ramp[n][ch] / 255.0; };
	return { (float)(at(i, 0) + (at(j, 0) - at(i, 0)) * f), (float)(at(i, 1) + (at(j, 1) - at(i, 1)) * f), (float)(at(i, 2) + (at(j, 2) - at(i, 2)) * f) };
}

/// The disc of a plasma ball or bead: its centre `ca` behind the head.
void disc(Px &px, const Params &p, double a, double n, double ca, double rad, double alphaMul, double dark)
{
	const double dd = std::hypot(a - ca, n);
	const double cov = std::min(1.0, std::max(0.0, rad - dd + 0.5)) * alphaMul;
	if (cov <= 0)
	{
		return;
	}
	const double tt = std::min(1.0, dd / rad);
	Rgb c = tt < 0.42 ? mix(p.centre, p.mid, tt / 0.42) : mix(p.mid, p.edge, (tt - 0.42) / 0.58);
	c = mix(c, p.tail, dark);
	over(px, cov, c);
}

/// One sample at `a` pixels behind the head and `n` aside from the axis.
Px sample(const Params &p, double a, double n)
{
	Px px;
	if (p.cls == LASER)
	{
		// a flat beam with a round head and a thin light vein; it thins and dims toward its tail
		const double s = p.L - a;
		const double dist = std::hypot(a - std::min(std::max(a, 0.0), p.L), n);
		const double u = std::min(1.0, std::max(0.0, s / p.L));
		const double half = p.w / 2 * (0.62 + 0.38 * smooth(0.0, 0.3, u));
		const double alphaU = 0.12 + 0.88 * smooth(0.0, 0.45, u);
		const Rgb col = rampAt(p, 1 - u);
		over(px, std::min(1.0, std::max(0.0, half - dist + 0.5)) * alphaU, col);
		const double hc = half * 0.34;
		over(px, std::min(1.0, std::max(0.0, hc - dist + 0.5)) * 0.55 * smooth(0.2, 0.7, u), p.vein);
	}
	else if (p.cls == PLASMA)
	{
		// a ball with a halo and a tail of beads that shrink and dim
		const double rr = std::hypot(a, n);
		const double halo = std::max(0.0, 1 - rr / (p.r * 2.3));
		over(px, halo * halo * 0.28, p.mid);
		const double scale = 4.5 / 5.2;
		for (int i = 3; i >= 0; --i)
		{
			disc(px, p, a, n, BEADS[i].off * p.r * scale, p.r * BEADS[i].rad, BEADS[i].alpha, 0.35);
		}
		disc(px, p, a, n, 0, p.r, 1.0, 0.0);
	}
	else if (p.cls == GAUSS)
	{
		// two see-through threads of air coiled around the way, the far half of a turn paler, wider and fainter toward
		// the shooter; over them the capsule
		if (a >= 0 && a <= p.reach)
		{
			const double u = 1 - a / p.reach;                          // 1 at the capsule, 0 at the end of the coils
			const double A = p.amp * (0.55 + 0.95 * (1 - u));
			const double env = smooth(0.0, 0.55, u) * smooth(1.0, 0.93, u);
			if (env > 0)
			{
				const Rgb air = { 214 / 255.f, 234 / 255.f, 255 / 255.f };
				for (int j = 0; j < 2; ++j)
				{
					const double phi = 2 * PI * a / p.lam + j * PI;
					const double nc = A * std::sin(phi);
					const double slope = A * 2 * PI / p.lam * std::cos(phi);
					const double dist = std::fabs(n - nc) / std::sqrt(1 + slope * slope);
					const double depth = 0.30 + 0.70 * (0.5 + 0.5 * std::cos(phi));
					over(px, std::min(1.0, std::max(0.0, p.sw / 2 - dist + 0.5)) * env * depth * 0.5, air);
				}
			}
		}
		const double rad = p.rs;
		const double seg = p.ls - 2 * rad;
		const double proj = (p.ls - rad) - a;                          // from the tail cap's centre toward the nose
		const double dist = std::hypot(proj - std::min(std::max(proj, 0.0), seg), n);
		const double cov = std::min(1.0, std::max(0.0, rad - dist + 0.5));
		if (cov > 0)
		{
			const double sn = std::min(1.0, std::max(-1.0, n / rad));
			const double along = std::min(1.0, std::max(0.0, proj / (seg + rad)));
			const double lit = std::min(1.0, std::max(0.0, 1 - std::fabs(sn + 0.28) * 0.9));
			const double t = std::min(1.0, std::max(0.0, lit * 0.75 + along * 0.35));
			const Rgb c = t < 0.55 ? mix(p.rim, p.body, t / 0.55) : mix(p.body, p.nose, (t - 0.55) / 0.45);
			over(px, cov, c);
			const double hi = std::min(1.0, std::max(0.0, 1 - std::fabs(sn + 0.32) / 0.22)) * std::min(1.0, std::max(0.0, 1 - std::fabs(along - 0.72) / 0.5));
			over(px, cov * hi * 0.75, { 1, 1, 1 });
		}
	}
	return px;
}

struct Key
{
	int cls, size, colours, k, angle, length;
	bool operator==(const Key &o) const
	{
		return cls == o.cls && size == o.size && colours == o.colours && k == o.k && angle == o.angle && length == o.length;
	}
};
struct KeyHash
{
	size_t operator()(const Key &key) const
	{
		uint64_t h = 1469598103934665603ull;
		for (int v : { key.cls, key.size, key.colours, key.k, key.angle, key.length })
		{
			h = (h ^ (uint64_t)(uint32_t)v) * 1099511628211ull;
		}
		return (size_t)h;
	}
};
std::unordered_map<Key, Shot, KeyHash> shots;
Uint32 frameNo = 0;

struct ColourKey
{
	int first;
	Uint32 palette;
	bool operator==(const ColourKey &o) const { return first == o.first && palette == o.palette; }
};
struct ColourKeyHash
{
	size_t operator()(const ColourKey &key) const { return (size_t)key.first * 2654435761u ^ key.palette; }
};
std::unordered_map<ColourKey, Colours, ColourKeyHash> coloursTable;
int coloursIds = 0;

/// Fills the parameters of a picture of `kind`.
Params paramsOf(Kind kind, const Colours &colours, int k, int lengthPieces)
{
	Params p;
	p.cls = kind.cls;
	p.kf = k / 4.0;
	p.colours = &colours;
	const int s = std::min(2, std::max(0, kind.size));
	const double kf = p.kf;
	const Rgb white = { 1, 1, 1 };
	p.vivid = { (float)(colours.vivid[0] / 255), (float)(colours.vivid[1] / 255), (float)(colours.vivid[2] / 255) };
	p.vein = mix(p.vivid, white, 0.85);
	if (kind.cls == LASER)
	{
		p.w = LASER_WIDTH[s] * kf;
		p.L = lengthPieces * (double)(PIECE_BASE * kf);
		p.aMin = -(p.w / 2 + 1);
		p.aMax = p.L + p.w / 2 + 1;
		p.nMax = p.w / 2 + 2;
	}
	else if (kind.cls == PLASMA)
	{
		p.r = PLASMA_R[s] * kf;
		p.centre = mix(p.vivid, white, 0.7);
		p.mid = p.vivid;
		p.edge = scaled(p.vivid, 0.5);
		p.tail = scaled(p.vivid, 0.35);
		p.aMin = -(p.r * 2.3 + 1);
		p.aMax = p.r * 4.8 + 1;
		p.nMax = p.r * 2.3 + 1;
	}
	else
	{
		p.ls = GAUSS_LENGTH[s] * kf;
		p.rs = GAUSS_RADIUS[s] * kf;
		p.amp = GAUSS_AMP[s] * kf;
		p.lam = GAUSS_LAMBDA[s] * kf;
		p.sw = GAUSS_STROKE[s] * kf;
		p.reach = GAUSS_REACH * kf;
		p.nose = mix(p.vivid, white, 0.85);
		p.body = p.vivid;
		p.rim = scaled(p.vivid, 0.45);
		p.aMin = -2;
		p.aMax = p.reach + 2;
		p.nMax = std::max(p.amp * 1.5 + p.sw + 3, p.rs + 2);
	}
	return p;
}

/// Makes every piece of a shot: the whole picture is drawn once, then each pixel goes to the piece its centre lies in.
void build(Shot &shot, Kind kind, const Colours &colours, int k, int angle, int lengthPieces)
{
	const Params p = paramsOf(kind, colours, k, lengthPieces);
	const double seg = PIECE_BASE * p.kf;
	int pieces;
	if (kind.cls == LASER)
	{
		pieces = lengthPieces;
	}
	else
	{
		pieces = std::max(1, (int)std::ceil(p.aMax / seg));
	}
	pieces = std::min(MAX_PIECES, std::max(1, pieces));
	const double th = 2 * PI * angle / ANGLES;
	const double dx = std::cos(th), dy = std::sin(th);          // toward where the shot goes, on the screen
	const double ex = -dy, ey = dx;                             // aside from the axis
	// a point of the picture: -a * d + n * e
	double minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9;
	for (double a : { p.aMin, p.aMax })
	{
		for (double n : { -p.nMax, p.nMax })
		{
			const double x = -a * dx + n * ex, y = -a * dy + n * ey;
			minX = std::min(minX, x); maxX = std::max(maxX, x);
			minY = std::min(minY, y); maxY = std::max(maxY, y);
		}
	}
	const int x0 = (int)std::floor(minX) - 1, y0 = (int)std::floor(minY) - 1;
	const int w = (int)std::ceil(maxX) + 1 - x0, h = (int)std::ceil(maxY) + 1 - y0;
	std::vector<Px> img((size_t)w * h);
	std::vector<int> pieceOf((size_t)w * h, 0);
	for (int iy = 0; iy < h; ++iy)
	{
		for (int ix = 0; ix < w; ++ix)
		{
			const double cx = x0 + ix + 0.5, cy = y0 + iy + 0.5;
			const double ac = -(cx * dx + cy * dy), nc = cx * ex + cy * ey;
			if (ac < p.aMin - 1.5 || ac > p.aMax + 1.5 || std::fabs(nc) > p.nMax + 1.5)
			{
				continue;
			}
			Px sum;
			for (int sy = 0; sy < SS; ++sy)
			{
				for (int sx = 0; sx < SS; ++sx)
				{
					const double x = x0 + ix + (sx + 0.5) / SS, y = y0 + iy + (sy + 0.5) / SS;
					const Px s = sample(p, -(x * dx + y * dy), x * ex + y * ey);
					sum.r += s.r; sum.g += s.g; sum.b += s.b; sum.a += s.a;
				}
			}
			const float inv = 1.0f / (SS * SS);
			Px &out = img[(size_t)iy * w + ix];
			out.r = sum.r * inv; out.g = sum.g * inv; out.b = sum.b * inv; out.a = sum.a * inv;
			pieceOf[(size_t)iy * w + ix] = ac <= 0 ? 0 : std::min(pieces - 1, (int)(ac / seg));
		}
	}
	shot.pieces.assign(pieces, Piece());
	// the tight box of every piece
	std::vector<int> bx0(pieces, w), by0(pieces, h), bx1(pieces, -1), by1(pieces, -1);
	for (int iy = 0; iy < h; ++iy)
	{
		for (int ix = 0; ix < w; ++ix)
		{
			const Px &s = img[(size_t)iy * w + ix];
			if (s.a < 1.0f / 512)
			{
				continue;
			}
			const int j = pieceOf[(size_t)iy * w + ix];
			bx0[j] = std::min(bx0[j], ix); bx1[j] = std::max(bx1[j], ix);
			by0[j] = std::min(by0[j], iy); by1[j] = std::max(by1[j], iy);
		}
	}
	for (int j = 0; j < pieces; ++j)
	{
		if (bx1[j] < 0)
		{
			continue;
		}
		Piece &piece = shot.pieces[j];
		piece.dx = x0 + bx0[j];
		piece.dy = y0 + by0[j];
		piece.frame.width = bx1[j] - bx0[j] + 1;
		piece.frame.height = by1[j] - by0[j] + 1;
		piece.frame.generated = true;
		piece.frame.pixels.assign((size_t)piece.frame.width * piece.frame.height, 0);
		for (int iy = by0[j]; iy <= by1[j]; ++iy)
		{
			for (int ix = bx0[j]; ix <= bx1[j]; ++ix)
			{
				const size_t at = (size_t)iy * w + ix;
				const Px &s = img[at];
				if (s.a < 1.0f / 512 || pieceOf[at] != j)
				{
					continue;
				}
				const auto byte = [](float v) { return (Uint32)(std::min(1.0f, std::max(0.0f, v)) * 255.0f + 0.5f); };
				piece.frame.pixels[(size_t)(iy - by0[j]) * piece.frame.width + (ix - bx0[j])] =
					(byte(s.a) << 24) | (byte(s.r / s.a) << 16) | (byte(s.g / s.a) << 8) | byte(s.b / s.a);
			}
		}
		piece.frame.buildSpans();
	}
}

}

Kind kindOf(const RuleItem *weapon)
{
	readTable();
	if (!weapon)
	{
		return Kind();
	}
	auto i = table.find(weapon->getType());
	return i != table.end() ? i->second : Kind();
}

const Colours &coloursOf(const SurfaceSet *set, int first, const SDL_Color *palette)
{
	Uint32 hash = 2166136261u;
	if (palette)
	{
		for (int c = 0; c < 256; ++c)
		{
			hash = (hash ^ (Uint32)((palette[c].r << 16) | (palette[c].g << 8) | palette[c].b)) * 16777619u;
		}
	}
	const ColourKey key = { first, hash };
	auto found = coloursTable.find(key);
	if (found != coloursTable.end())
	{
		return found->second;
	}
	Colours &out = coloursTable[key];
	out.id = ++coloursIds;
	if (!set || !palette)
	{
		return out;
	}
	// the row's brightest value, then its most vivid colour among the bright ones (as HdSprites::makeDots reads a tracer)
	int maxV = 0;
	for (int pass = 0; pass < 2; ++pass)
	{
		double best = -1.0;
		for (int f = first; f < first + 35; ++f)
		{
			const Surface *s = set->getFrame(f);
			if (!s)
			{
				continue;
			}
			double sum[3] = { 0, 0, 0 };
			int lit = 0;
			for (int y = 0; y < s->getHeight(); ++y)
			{
				for (int x = 0; x < s->getWidth(); ++x)
				{
					const Uint8 index = s->getPixel(x, y);
					if (!index)
					{
						continue;
					}
					const SDL_Color &c = palette[index];
					const int v = std::max({ (int)c.r, (int)c.g, (int)c.b });
					if (pass == 0)
					{
						maxV = std::max(maxV, v);
						sum[0] += c.r; sum[1] += c.g; sum[2] += c.b;
						++lit;
					}
					else if (v * 10 >= maxV * 6 && v > 0)
					{
						const double score = (v - std::min({ (int)c.r, (int)c.g, (int)c.b })) / (double)v * v;
						if (score > best)
						{
							best = score;
							out.vivid[0] = c.r * 255.0 / v; out.vivid[1] = c.g * 255.0 / v; out.vivid[2] = c.b * 255.0 / v;
							out.valid = true;
						}
					}
				}
			}
			if (pass == 0 && lit > 0 && out.rampCount < 35)
			{
				for (int c = 0; c < 3; ++c)
				{
					out.ramp[out.rampCount][c] = sum[c] / lit;
				}
				++out.rampCount;
			}
		}
	}
	return out;
}

int pieceLength(int k)
{
	return std::max(1, PIECE_BASE * k / 4);
}

int laserNominalVoxels(int size)
{
	return LASER_VOXELS[std::min(2, std::max(0, size))];
}

int laserPieces(int pixels, int k)
{
	const int seg = pieceLength(k);
	return std::min(MAX_PIECES, std::max(2, (pixels + seg - 1) / seg));
}

const Shot *shot(Kind kind, const Colours &colours, int k, int angle, int lengthPieces)
{
	if (!kind || !colours.valid)
	{
		return nullptr;
	}
	const Key key = { kind.cls, kind.size, colours.id, k, ((angle % ANGLES) + ANGLES) % ANGLES, kind.cls == LASER ? lengthPieces : 0 };
	auto found = shots.find(key);
	if (found == shots.end())
	{
		found = shots.emplace(key, Shot()).first;
		build(found->second, kind, colours, k, key.angle, lengthPieces);
	}
	found->second.used = frameNo;
	return &found->second;
}

void newFrame()
{
	++frameNo;
	if (shots.size() <= KEEP)
	{
		return;
	}
	for (auto i = shots.begin(); i != shots.end();)
	{
		if (i->second.used + IDLE < frameNo)
		{
			i = shots.erase(i);
		}
		else
		{
			++i;
		}
	}
	// still too many: the oldest go, those used in the last few frames stay (the canvas may still hold their pointers)
	while (shots.size() > KEEP_MAX)
	{
		auto oldest = shots.end();
		for (auto i = shots.begin(); i != shots.end(); ++i)
		{
			if (i->second.used + 3 < frameNo && (oldest == shots.end() || i->second.used < oldest->second.used))
			{
				oldest = i;
			}
		}
		if (oldest == shots.end())
		{
			break;
		}
		shots.erase(oldest);
	}
}

}

}
