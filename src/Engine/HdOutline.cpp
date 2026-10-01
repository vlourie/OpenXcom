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
#include "HdOutline.h"
#include <algorithm>
#include <cmath>
#include <map>
#include <memory>
#include <sstream>
#include <tuple>
#include <unordered_map>
#include <vector>
#include "FileMap.h"
#include "HdSprites.h"
#include "HdUi.h"
#include "Logger.h"

namespace OpenXcom
{
namespace HdOutline
{
namespace
{

const char *const FOLDER = "OUTLINE";
const float TAU = 6.2831853f;
/// Headings an outline is cached at: a step of under six degrees, which no outline this small shows.
const int ANGLES = 64;
/// Samples of the mask per world pixel and axis: it is stored much finer than it is drawn.
const int SUPER = 4;

/// The plan as the mod ships it: coverage of the hull, the nose to the right.
struct Mask
{
	int w = 0, h = 0;
	std::vector<Uint8> cov;
	bool tried = false;
};

/// One outline at one length and heading: the hull's coverage, its rim, the dark halo just outside it
/// (the rim reads on sand and on sea alike), and which way round the hull each pixel lies counted
/// from the nose (the light that runs around it, the drawing stroke).
struct Shape
{
	int side = 0;
	std::vector<Uint8> fill, rim, halo, around;
};
/// The halo's colour and strength.
const float HALO_RGB = 16.0f, HALO_ALPHA = 0.6f;

bool indexRead = false;
std::unordered_map<std::string, float> factors;
std::unordered_map<std::string, Mask> masks;
std::map<std::tuple<std::string, int, int>, Shape> shapes;
std::vector<Uint32> scratch;

void readIndex()
{
	if (indexRead)
	{
		return;
	}
	indexRead = true;
	const std::string path = HdSprites::artPath(std::string(FOLDER) + "/index.txt");
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
	while (std::getline(*in, line))
	{
		std::istringstream ss(line);
		std::string type;
		float factor = 1.0f;
		if (!(ss >> type >> factor) || type[0] == '#')
		{
			continue;
		}
		factors[type] = std::min(std::max(factor, 0.3f), 3.0f);
	}
	Log(LOG_INFO) << "HD outlines: " << factors.size() << " craft and UFO types";
}

const Mask *mask(const std::string &type)
{
	Mask &m = masks[type];
	if (!m.tried)
	{
		m.tried = true;
		HdFrame frame;
		if (HdSprites::loadPng(HdSprites::artPath(std::string(FOLDER) + "/" + type + ".png"), frame) && !frame.empty())
		{
			m.w = frame.width;
			m.h = frame.height;
			m.cov.resize(frame.pixels.size());
			for (size_t i = 0; i < frame.pixels.size(); ++i)
			{
				m.cov[i] = (Uint8)(frame.pixels[i] >> 24);
			}
		}
		else
		{
			Log(LOG_WARNING) << "HD outline " << type << " is listed in index.txt but its picture cannot be read";
		}
	}
	return m.cov.empty() ? nullptr : &m;
}

/**
 * The outline `length` world pixels long, turned to heading number `turn`. The same as
 * craft_outline.render, which drew the approval sheet: the mask sampled SUPER x SUPER times
 * per pixel, the rim = the coverage minus its erosion by one pixel.
 */
const Shape &shape(const std::string &type, const Mask &m, int length, int turn)
{
	const auto key = std::make_tuple(type, length, turn);
	auto found = shapes.find(key);
	if (found != shapes.end())
	{
		return found->second;
	}
	if (shapes.size() > 4096)
	{
		// many zooms and headings over a long session: each one is cheap to make again
		shapes.clear();
	}
	Shape &s = shapes[key];
	const int side = (int)std::ceil(length * 1.1f) + 4;
	const size_t n = (size_t)side * side;
	s.side = side;
	const float c = (side - 1) * 0.5f;
	const float scale = (float)length / std::max(m.w, m.h);
	const float a = turn * TAU / ANGLES;
	const float ca = std::cos(a), sa = std::sin(a);
	std::vector<float> cov(n, 0.0f);
	for (int y = 0; y < side; ++y)
	{
		for (int x = 0; x < side; ++x)
		{
			int sum = 0;
			for (int oy = 0; oy < SUPER; ++oy)
			{
				for (int ox = 0; ox < SUPER; ++ox)
				{
					const float dx = x + (ox + 0.5f) / SUPER - 0.5f - c, dy = y + (oy + 0.5f) / SUPER - 0.5f - c;
					// back from the screen to the plan: the nose (+u) points along the heading
					const float u = (ca * dx + sa * dy) / scale + m.w * 0.5f;
					const float v = (-sa * dx + ca * dy) / scale + m.h * 0.5f;
					if (u < 0.0f || v < 0.0f || u >= m.w || v >= m.h)
					{
						continue;
					}
					sum += m.cov[(size_t)(int)v * m.w + (int)u];
				}
			}
			cov[(size_t)y * side + x] = sum / (255.0f * SUPER * SUPER);
		}
	}
	s.fill.resize(n);
	s.rim.resize(n);
	s.halo.resize(n);
	s.around.resize(n);
	for (int y = 0; y < side; ++y)
	{
		for (int x = 0; x < side; ++x)
		{
			const size_t i = (size_t)y * side + x;
			float lowest = cov[i], highest = cov[i];
			for (int dy = -1; dy <= 1; ++dy)
			{
				for (int dx = -1; dx <= 1; ++dx)
				{
					const int yy = y + dy, xx = x + dx;
					const float v = (yy < 0 || xx < 0 || yy >= side || xx >= side) ? 0.0f : cov[(size_t)yy * side + xx];
					lowest = std::min(lowest, v);
					highest = std::max(highest, v);
				}
			}
			s.fill[i] = (Uint8)std::lround(cov[i] * 255.0f);
			s.rim[i] = (Uint8)std::lround(std::min(std::max((cov[i] - lowest) * 1.6f, 0.0f), 1.0f) * 255.0f);
			s.halo[i] = (Uint8)std::lround(std::min(std::max(highest - cov[i], 0.0f), 1.0f) * 255.0f);
			float t = (std::atan2(y - c, x - c) - a) / TAU;
			t -= std::floor(t);
			s.around[i] = (Uint8)std::min(255, (int)(t * 256.0f));
		}
	}
	return s;
}

} // namespace

bool has(const std::string &type, float *factor)
{
	readIndex();
	auto i = factors.find(type);
	if (i == factors.end())
	{
		return false;
	}
	if (factor)
	{
		*factor = i->second;
	}
	return true;
}

void draw(const std::string &type, float cx, float cy, float length, float angle, Uint32 color, float phase, float reveal, float strength)
{
	if (!has(type))
	{
		return;
	}
	const Mask *m = mask(type);
	if (!m)
	{
		return;
	}
	const int len = std::max(4, (int)std::lround(length));
	int turn = (int)std::lround(angle / TAU * ANGLES) % ANGLES;
	if (turn < 0)
	{
		turn += ANGLES;
	}
	const Shape &s = shape(type, *m, len, turn);
	const size_t n = (size_t)s.side * s.side;
	scratch.assign(n, 0);
	const float r0 = (float)((color >> 16) & 0xFF), g0 = (float)((color >> 8) & 0xFF), b0 = (float)(color & 0xFF);
	for (size_t i = 0; i < n; ++i)
	{
		// the rim, and the hull faintly inside it (craft_outline: ring 1, fill 0.22)
		float alpha = std::min(1.0f, s.rim[i] / 255.0f + s.fill[i] / 255.0f * 0.22f) * strength;
		float dark = s.halo[i] / 255.0f * HALO_ALPHA * strength;
		const float t = s.around[i] / 256.0f;
		if (reveal < 1.0f)
		{
			// drawn stroke by stroke from the nose round the hull
			const float drawn = std::min(std::max((reveal * 1.05f - t) / 0.05f, 0.0f), 1.0f);
			alpha *= drawn;
			dark *= drawn;
		}
		// the rim over the halo
		dark *= 1.0f - alpha;
		const float total = alpha + dark;
		if (total <= 0.004f)
		{
			continue;
		}
		const float w = std::max(0.0f, std::cos(t * TAU - phase));
		const float lum = 0.65f + 0.35f * w * w * w;
		const float lift = std::max(0.0f, lum - 0.65f) * 0.8f;
		auto channel = [&](float c0)
		{
			const float lit = std::min(255.0f, c0 * lum + (255.0f - c0) * lift);
			return (Uint32)std::min(255.0f, (lit * alpha + HALO_RGB * dark) / total + 0.5f);
		};
		scratch[i] = ((Uint32)std::lround(total * 255.0f) << 24) | (channel(r0) << 16) | (channel(g0) << 8) | channel(b0);
	}
	const int x0 = (int)std::lround(cx - (s.side - 1) * 0.5f), y0 = (int)std::lround(cy - (s.side - 1) * 0.5f);
	HdUi::instance().drawImage(scratch.data(), s.side, s.side, x0, y0);
}

Uint32 raceColor(const std::string &race)
{
	if (race.empty())
	{
		return 0xFF785A;
	}
	// FNV-1a: the same race is the same colour in every game and on every machine
	Uint32 hash = 2166136261u;
	for (unsigned char ch : race)
	{
		hash = (hash ^ ch) * 16777619u;
	}
	// a hue anywhere but the cyan and blue of the player's own craft (165-225 degrees)
	float hue = (float)(hash % 300u);
	if (hue >= 165.0f)
	{
		hue += 60.0f;
	}
	const float sat = 0.55f + (float)((hash >> 12) % 30u) / 100.0f;
	const float h6 = hue / 60.0f;
	const float x = 1.0f - std::fabs(std::fmod(h6, 2.0f) - 1.0f);
	float r = 0, g = 0, b = 0;
	switch ((int)h6 % 6)
	{
	case 0: r = 1; g = x; break;
	case 1: r = x; g = 1; break;
	case 2: g = 1; b = x; break;
	case 3: g = x; b = 1; break;
	case 4: r = x; b = 1; break;
	default: r = 1; b = x; break;
	}
	auto channel = [&](float v) { return (Uint32)std::lround(255.0f * (1.0f - sat * (1.0f - v))); };
	return (channel(r) << 16) | (channel(g) << 8) | channel(b);
}

void clear()
{
	indexRead = false;
	factors.clear();
	masks.clear();
	shapes.clear();
}

} // namespace HdOutline
} // namespace OpenXcom
