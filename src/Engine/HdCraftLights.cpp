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
#include "HdCraftLights.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>
#include "FileMap.h"
#include "HdSprites.h"
#include "Logger.h"
#include "../Mod/RuleCraft.h"
#include "../Savegame/Base.h"
#include "../Savegame/Craft.h"
#include "../Savegame/Soldier.h"

namespace OpenXcom
{

namespace HdCraftLights
{

namespace
{

const char *FOLDER = "BASEBITS.PCK";
const char *SUFFIX = ".lights.txt";
/// Offset of the master mod's sprites (Mod::loadAll: 1000 x the reserved space of the mods before it;
/// for a master on top of the original game it is 1000). Set by clear().
int masterOffset = 1000;

enum Kind { RED, GREEN, WHITE, STROBE, BEACON, BLINK };

struct Light
{
	float x = 0, y = 0;         ///< classic frame pixels
	Kind kind = RED;
	float period = 1.0f;        ///< seconds (strobe, beacon and blink)
	float offset = 0.0f;        ///< seconds
	bool ownColor = false;      ///< "#rrggbb" given in the file
	float r = 1.0f, g = 1.0f, b = 1.0f;
};

std::map<int, std::vector<Light>> frames;
bool scanned = false;

bool parseKind(const std::string &s, Kind &kind, float &period)
{
	if (s == "red") { kind = RED; return true; }
	if (s == "green") { kind = GREEN; return true; }
	if (s == "white") { kind = WHITE; return true; }
	if (s == "strobe") { kind = STROBE; period = 1.3f; return true; }
	if (s == "beacon") { kind = BEACON; period = 1.0f; return true; }
	if (s == "blink") { kind = BLINK; period = 1.2f; return true; }
	return false;
}

/// "#rrggbb" -> 0..1 channels.
bool parseColor(const std::string &s, float &r, float &g, float &b)
{
	if (s.size() != 7 || s[0] != '#')
	{
		return false;
	}
	char *end = nullptr;
	const unsigned long v = std::strtoul(s.c_str() + 1, &end, 16);
	if (!end || *end != '\0')
	{
		return false;
	}
	r = ((v >> 16) & 0xFF) / 255.0f;
	g = ((v >> 8) & 0xFF) / 255.0f;
	b = (v & 0xFF) / 255.0f;
	return true;
}

/// Reads the folder once: every "<index>.lights.txt".
void scan()
{
	if (scanned)
	{
		return;
	}
	scanned = true;
	const std::string suffix = SUFFIX;
	for (const std::string &file : HdSprites::artFolder(FOLDER))
	{
		if (file.size() <= suffix.size() || file.compare(file.size() - suffix.size(), suffix.size(), suffix) != 0)
		{
			continue;
		}
		char *end = nullptr;
		const long index = std::strtol(file.c_str(), &end, 10);
		if (!end || end != file.c_str() + (file.size() - suffix.size()) || index < 0)
		{
			continue;
		}
		const std::string path = HdSprites::artPath(std::string(FOLDER) + "/" + file);
		std::unique_ptr<std::istream> in = FileMap::getIStream(path);
		if (!in)
		{
			continue;
		}
		std::vector<Light> lights;
		std::string line;
		int number = 0;
		while (std::getline(*in, line))
		{
			++number;
			// a comment is '#' at the start of the line or '#' followed by a space;
			// "#rrggbb" right after the kind is a colour
			for (size_t hash = line.find('#'); hash != std::string::npos; hash = line.find('#', hash + 1))
			{
				const bool first = line.find_first_not_of(" \t") == hash;
				if (first || hash + 1 >= line.size() || line[hash + 1] == ' ' || line[hash + 1] == '\t' || line[hash + 1] == '\r')
				{
					line.erase(hash);
					break;
				}
			}
			std::istringstream ss(line);
			Light light;
			std::string kind;
			if (!(ss >> light.x >> light.y))
			{
				continue;                   // blank or comment
			}
			if (!(ss >> kind) || !parseKind(kind, light.kind, light.period))
			{
				Log(LOG_WARNING) << "HD craft lights: " << file << " line " << number << ": unknown kind '" << kind << "'";
				continue;
			}
			// the rest: an optional "#rrggbb", then period and offset in seconds
			std::string token;
			int numbers = 0;
			while (ss >> token)
			{
				if (token[0] == '#')
				{
					light.ownColor = parseColor(token, light.r, light.g, light.b);
					if (!light.ownColor)
					{
						Log(LOG_WARNING) << "HD craft lights: " << file << " line " << number << ": bad colour '" << token << "'";
					}
					continue;
				}
				const float value = (float)std::atof(token.c_str());
				if (numbers == 0 && value > 0.05f)
				{
					light.period = value;
				}
				else if (numbers == 1)
				{
					light.offset = value;
				}
				++numbers;
			}
			lights.push_back(light);
		}
		if (!lights.empty())
		{
			frames[(int)index] = std::move(lights);
		}
	}
	if (!frames.empty())
	{
		Log(LOG_INFO) << "HD craft lights: " << frames.size() << " craft pictures with lights";
	}
}

/// A soft pulse over one period (phase 0..1): up in the first half, dark in the second.
float pulse(float phase)
{
	const float s = std::sin(phase * 6.2831853f);
	return s > 0.0f ? s * s : 0.0f;
}

/// Brightness 0..1 of a light at time t (seconds). `port`: the light is on the left half of the
/// craft (the sides blink in turn when pilots are missing).
float intensity(const Light &light, Status status, float t, bool port)
{
	if (status != BUSY)
	{
		// every light in one rhythm of the state, the offsets of the file set aside
		const float period = status == READY ? 1.2f : status == REARMING ? 1.4f : 1.0f;
		const float phase = std::fmod(std::fabs(t), period) / period;
		switch (status)
		{
		case REARMING:
		{
			// two short flashes, then a pause
			const float ms = phase * period * 1000.0f;
			return (ms < 120.0f || (ms >= 260.0f && ms < 380.0f)) ? 1.0f : 0.0f;
		}
		case NO_CREW:
			return pulse(port ? phase : std::fmod(phase + 0.5f, 1.0f));
		default:
			return pulse(phase);    // ready, repairs: an even pulse
		}
	}
	// refuelling and the rest: only the beacons, each in its own rhythm
	if (light.kind != BEACON && light.kind != BLINK)
	{
		return 0.0f;
	}
	return pulse(std::fmod(std::fabs(t + light.offset), light.period) / light.period);
}

void colorOf(const Light &light, Status status, float &r, float &g, float &b)
{
	switch (status)
	{
	case READY:
		r = 0.10f; g = 1.00f; b = 0.30f;
		return;
	case REPAIRS:
	case REARMING:
	case NO_CREW:
		r = 1.00f; g = 0.12f; b = 0.08f;
		return;
	default:
		break;
	}
	if (light.ownColor)
	{
		r = light.r; g = light.g; b = light.b;
		return;
	}
	switch (light.kind)
	{
	case RED:    r = 1.00f; g = 0.12f; b = 0.08f; return;
	case GREEN:  r = 0.10f; g = 1.00f; b = 0.30f; return;
	case WHITE:
	case STROBE:
	case BLINK:  r = 1.00f; g = 1.00f; b = 1.00f; return;
	case BEACON: r = 1.00f; g = 0.10f; b = 0.05f; return;
	}
}

/// Adds a soft point of light: a hot white core and a coloured halo, additively.
/// A light painted on the craft (`own`) instead pulls the pixels toward its colour:
/// adding would bleach that colour to white. `size` scales the spot (the garland's bulbs are smaller).
void glow(SDL_Surface *world, float cx, float cy, int k, float r, float g, float b, float amount, bool own, float size = 1.0f)
{
	const float halo = 1.4f * k * size, core = 0.45f * k * size;
	const float reach = halo * 2.6f;
	const int x0 = std::max(0, (int)std::floor(cx - reach)), x1 = std::min(world->w, (int)std::ceil(cx + reach));
	const int y0 = std::max(0, (int)std::floor(cy - reach)), y1 = std::min(world->h, (int)std::ceil(cy + reach));
	for (int y = y0; y < y1; ++y)
	{
		Uint32 *row = (Uint32*)((Uint8*)world->pixels + (size_t)y * world->pitch);
		for (int x = x0; x < x1; ++x)
		{
			const float dx = x + 0.5f - cx, dy = y + 0.5f - cy;
			const float d2 = dx * dx + dy * dy;
			const float h = amount * std::exp(-d2 / (halo * halo));
			const float c = amount * std::exp(-d2 / (core * core));
			if (h < 0.004f)
			{
				continue;
			}
			const Uint32 p = row[x];
			const float pr = (float)((p >> 16) & 0xFF), pg = (float)((p >> 8) & 0xFF), pb = (float)(p & 0xFF);
			float nr, ng, nb;
			if (own)
			{
				const float a = std::min(0.85f * h + c, 1.0f);
				nr = pr * (1.0f - a) + 255.0f * r * a;
				ng = pg * (1.0f - a) + 255.0f * g * a;
				nb = pb * (1.0f - a) + 255.0f * b * a;
			}
			else
			{
				nr = pr + 255.0f * (r * h + c);
				ng = pg + 255.0f * (g * h + c);
				nb = pb + 255.0f * (b * h + c);
			}
			row[x] = 0xFF000000u
				| ((Uint32)std::min(nr, 255.0f) << 16)
				| ((Uint32)std::min(ng, 255.0f) << 8)
				| (Uint32)std::min(nb, 255.0f);
		}
	}
}

/// The lights of a frame of the game's BASEBITS set. The files are named by the frame in the
/// master mod's own numbering (sprite + 33), while the game shifts a mod's craft sprite above 4
/// by the mod's offset (Mod::getOffset): the master's Brig, sprite 26, is frame 1059, not 59.
const std::vector<Light> *lightsOf(int index)
{
	scan();
	auto it = frames.find(index);
	if (it == frames.end() && masterOffset > 0 && index >= masterOffset)
	{
		it = frames.find(index - masterOffset);
	}
	return it == frames.end() ? nullptr : &it->second;
}

}

Status statusOf(const Craft *craft)
{
	const std::string status = craft->getStatus();
	if (status == "STR_REPAIRS")
	{
		return REPAIRS;
	}
	if (status == "STR_REARMING")
	{
		return REARMING;
	}
	if (status != "STR_READY")
	{
		return BUSY;                // refuelling and the rest
	}
	const int needed = craft->getRules()->getPilots();
	const Base *base = craft->getBase();
	if (needed > 0 && base)
	{
		// the soldiers' stats with bonuses are the cache Base::load and the screens keep fresh
		int pilots = 0;
		for (const Soldier *soldier : base->getSoldiers())
		{
			if (soldier->getCraft() == craft && soldier->hasAllPilotingRequirements())
			{
				++pilots;
			}
		}
		if (pilots < needed)
		{
			return NO_CREW;
		}
	}
	return READY;
}

bool has(int index)
{
	return lightsOf(index) != nullptr;
}

void draw(SDL_Surface *world, int index, int x, int y, int k, Status status, Uint32 seed, Uint32 ticks)
{
	const std::vector<Light> *lights = lightsOf(index);
	if (!world || world->format->BytesPerPixel != 4 || k < 1 || !lights)
	{
		return;
	}
	// each hangar keeps its own rhythm
	const float t = (float)ticks / 1000.0f + (float)(seed % 997u) * 0.0371f;
	// the sides of the craft: left and right of the middle of its lights
	float middle = 0.0f;
	for (const Light &light : *lights)
	{
		middle += light.x;
	}
	middle /= (float)lights->size();
	if (SDL_MUSTLOCK(world))
	{
		SDL_LockSurface(world);
	}
	for (const Light &light : *lights)
	{
		const float amount = intensity(light, status, t, light.x < middle);
		if (amount <= 0.0f)
		{
			continue;
		}
		float r = 1.0f, g = 1.0f, b = 1.0f;
		colorOf(light, status, r, g, b);
		glow(world, x + light.x * k, y + light.y * k, k, r, g, b, amount, light.ownColor);
	}
	if (SDL_MUSTLOCK(world))
	{
		SDL_UnlockSurface(world);
	}
}

void drawFuel(SDL_Surface *world, int x, int y, int k, int percent, Uint32 seed, Uint32 ticks)
{
	if (!world || world->format->BytesPerPixel != 4 || k < 1)
	{
		return;
	}
	struct Rgb { float r, g, b; };
	const Rgb red = { 1.00f, 0.12f, 0.08f }, orange = { 1.00f, 0.45f, 0.05f }, yellow = { 1.00f, 0.90f, 0.10f },
		green = { 0.10f, 1.00f, 0.30f }, gold = { 1.00f, 0.72f, 0.12f }, dark = { 0.30f, 0.30f, 0.30f };
	const bool full = percent >= 100;
	const int lit = full ? 5 : percent > 75 ? 4 : percent > 50 ? 3 : percent > 25 ? 2 : 1;
	const Rgb &colour = lit == 1 ? red : lit == 2 ? orange : lit == 3 ? yellow : green;
	// full: the bulbs swap green and gold every half second, neighbours opposite
	const float t = (float)ticks / 1000.0f + (float)(seed % 997u) * 0.0371f;
	const int swap = (int)(t / 0.5f) & 1;
	if (SDL_MUSTLOCK(world))
	{
		SDL_LockSurface(world);
	}
	for (int i = 0; i < 5; ++i)
	{
		const float cx = x + (i - 2) * 5.0f * k;     // 5 classic pixels apart
		if (i >= lit)
		{
			glow(world, cx, (float)y, k, dark.r, dark.g, dark.b, 0.25f, false, 0.6f);
			continue;
		}
		const Rgb &c = full ? (((i + swap) & 1) ? gold : green) : colour;
		glow(world, cx, (float)y, k, c.r, c.g, c.b, 0.9f, false, 0.7f);
	}
	if (SDL_MUSTLOCK(world))
	{
		SDL_UnlockSurface(world);
	}
}

void clear(int offset)
{
	masterOffset = offset;
	frames.clear();
	scanned = false;
}

}

}
