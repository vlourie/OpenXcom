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
#include "HdTest.h"
#include <cstdio>
#include <sstream>
#include <iomanip>
#include "../lodepng.h"
#include "CrossPlatform.h"
#include "Logger.h"
#include "Options.h"

namespace OpenXcom
{
namespace HdTest
{

std::string nextDumpPrefix()
{
	std::ostringstream ss;
	int i = 0;
	do
	{
		ss.str("");
		ss << Options::getMasterUserFolder() << "hdtest" << std::setfill('0') << std::setw(3) << i;
		i++;
	}
	// every part of a dump counts as taken, not just the .json: outside the battlescape only
	// <prefix>_frame.png is written, so counting by .json alone made every such dump overwrite
	// the same file and the player saw nothing new appear
	while (CrossPlatform::fileExists(ss.str() + ".json")
		|| CrossPlatform::fileExists(ss.str() + "_frame.png"));
	return ss.str();
}

bool savePngRgb(const std::string &filename, SDL_Surface *surface)
{
	if (!surface)
	{
		Log(LOG_ERROR) << "HdTest: no surface to dump into " << filename;
		return false;
	}

	const int w = surface->w;
	const int h = surface->h;
	std::vector<unsigned char> rgb;
	rgb.resize((size_t)w * h * 3);

	if (SDL_MUSTLOCK(surface))
	{
		SDL_LockSurface(surface);
	}

	const Uint8 *pixels = (const Uint8*)surface->pixels;
	if (surface->format->BitsPerPixel == 8)
	{
		const SDL_Palette *pal = surface->format->palette;
		for (int y = 0; y < h; ++y)
		{
			const Uint8 *row = pixels + (size_t)y * surface->pitch;
			unsigned char *out = &rgb[(size_t)y * w * 3];
			for (int x = 0; x < w; ++x)
			{
				const Uint8 idx = row[x];
				SDL_Color c = { 0, 0, 0, 0 };
				if (pal && idx < pal->ncolors)
				{
					c = pal->colors[idx];
				}
				out[x * 3 + 0] = c.r;
				out[x * 3 + 1] = c.g;
				out[x * 3 + 2] = c.b;
			}
		}
	}
	else
	{
		const int bpp = surface->format->BytesPerPixel;
		for (int y = 0; y < h; ++y)
		{
			const Uint8 *row = pixels + (size_t)y * surface->pitch;
			unsigned char *out = &rgb[(size_t)y * w * 3];
			for (int x = 0; x < w; ++x)
			{
				Uint32 value = 0;
				const Uint8 *p = row + (size_t)x * bpp;
				switch (bpp)
				{
				case 2: value = *(const Uint16*)p; break;
				case 3: value = p[0] | (p[1] << 8) | (p[2] << 16); break; // little endian only, good enough for a test tool
				default: value = *(const Uint32*)p; break;
				}
				Uint8 r, g, b;
				SDL_GetRGB(value, surface->format, &r, &g, &b);
				out[x * 3 + 0] = r;
				out[x * 3 + 1] = g;
				out[x * 3 + 2] = b;
			}
		}
	}

	if (SDL_MUSTLOCK(surface))
	{
		SDL_UnlockSurface(surface);
	}

	std::vector<unsigned char> png;
	unsigned error = lodepng::encode(png, rgb, (unsigned)w, (unsigned)h, LCT_RGB);
	if (error)
	{
		Log(LOG_ERROR) << "HdTest: PNG encode failed for " << filename << ": " << lodepng_error_text(error);
		return false;
	}
	if (!CrossPlatform::writeFile(filename, png))
	{
		Log(LOG_ERROR) << "HdTest: cannot write " << filename;
		return false;
	}
	Log(LOG_INFO) << "HdTest: wrote " << filename << " (" << w << "x" << h << ")";
	return true;
}

std::string jsonString(const std::string &s)
{
	std::string out = "\"";
	for (char ch : s)
	{
		switch (ch)
		{
		case '"': out += "\\\""; break;
		case '\\': out += "\\\\"; break;
		case '\n': out += "\\n"; break;
		case '\r': out += "\\r"; break;
		case '\t': out += "\\t"; break;
		default:
			if ((unsigned char)ch < 0x20)
			{
				char buf[8];
				snprintf(buf, sizeof(buf), "\\u%04x", (unsigned)(unsigned char)ch);
				out += buf;
			}
			else
			{
				out += ch;
			}
		}
	}
	out += "\"";
	return out;
}

void writeJson(const std::string &filename, const std::vector<std::pair<std::string, std::string> > &fields)
{
	std::ostringstream ss;
	ss << "{\n";
	for (size_t i = 0; i < fields.size(); ++i)
	{
		ss << "  " << jsonString(fields[i].first) << ": " << fields[i].second;
		if (i + 1 < fields.size())
		{
			ss << ",";
		}
		ss << "\n";
	}
	ss << "}\n";
	if (!CrossPlatform::writeFile(filename, ss.str()))
	{
		Log(LOG_ERROR) << "HdTest: cannot write " << filename;
	}
}

}
}
