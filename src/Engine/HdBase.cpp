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
#include "HdBase.h"
#include <cstdlib>
#include <map>
#include <vector>
#include "FileMap.h"
#include "Logger.h"

namespace OpenXcom
{

namespace HdBase
{

namespace
{

const char *FOLDER = "hd/BASEBITS.PCK";
const int MAX_PHASES = 16;

struct Tile
{
	std::vector<std::string> paths;                  ///< phase 0 first, then v1, v2, ...
	std::map<int, HdFrame> loaded;                   ///< phase -> picture at the current scale
	std::map<int, size_t> lru;
};

std::map<int, Tile> tiles;
bool scanned = false;
int scanScale = 0;
size_t budget = 64u * 1024u * 1024u;
size_t bytes = 0;
size_t clock_ = 0;
bool anyAnimated = false;

/// Reads the folder once: which tile has which phases.
void scan()
{
	if (scanned)
	{
		return;
	}
	scanned = true;
	const FileMap::NameSet &files = FileMap::getVFolderContents(FOLDER);
	for (const std::string &file : files)
	{
		const size_t dot = file.find('.');
		if (dot == std::string::npos || dot == 0)
		{
			continue;
		}
		int phase = 0;
		const std::string rest = file.substr(dot);
		if (rest != ".png")
		{
			if (rest.size() < 7 || rest.compare(0, 2, ".v") != 0 || rest.compare(rest.size() - 4, 4, ".png") != 0)
			{
				continue;
			}
			const std::string number = rest.substr(2, rest.size() - 6);
			char *vend = nullptr;
			const long v = std::strtol(number.c_str(), &vend, 10);
			if (number.empty() || !vend || *vend != '\0' || v < 1 || v >= MAX_PHASES)
			{
				continue;
			}
			phase = (int)v;
		}
		char *end = nullptr;
		const long index = std::strtol(file.c_str(), &end, 10);
		if (!end || *end != '.' || index < 0)
		{
			continue;
		}
		Tile &tile = tiles[(int)index];
		if ((int)tile.paths.size() <= phase)
		{
			tile.paths.resize(phase + 1);
		}
		tile.paths[phase] = std::string(FOLDER) + "/" + file;
	}
	// a picture of phase 0 is what makes a tile HD; phases stop at the first missing one
	for (auto it = tiles.begin(); it != tiles.end(); )
	{
		std::vector<std::string> &paths = it->second.paths;
		size_t n = 0;
		while (n < paths.size() && !paths[n].empty())
		{
			++n;
		}
		paths.resize(n);
		if (n == 0)
		{
			it = tiles.erase(it);
			continue;
		}
		if (n > 1)
		{
			anyAnimated = true;
		}
		++it;
	}
	if (!tiles.empty())
	{
		Log(LOG_INFO) << "HD base: " << tiles.size() << " tiles with pictures" << (anyAnimated ? " (animated)" : "");
	}
}

/// Drops the pictures found longest ago while the loaded ones exceed the budget.
void trim(const HdFrame *keep)
{
	while (bytes > budget)
	{
		Tile *oldestTile = nullptr;
		int oldestPhase = -1;
		size_t oldest = (size_t)-1;
		for (auto &pair : tiles)
		{
			for (const auto &use : pair.second.lru)
			{
				const HdFrame *f = &pair.second.loaded[use.first];
				if (f == keep || use.second >= oldest)
				{
					continue;
				}
				oldest = use.second;
				oldestTile = &pair.second;
				oldestPhase = use.first;
			}
		}
		if (!oldestTile)
		{
			return;
		}
		HdFrame &f = oldestTile->loaded[oldestPhase];
		bytes -= f.pixels.size() * sizeof(Uint32);
		oldestTile->loaded.erase(oldestPhase);
		oldestTile->lru.erase(oldestPhase);
	}
}

}

int phases(int index)
{
	scan();
	auto it = tiles.find(index);
	return it == tiles.end() ? 0 : (int)it->second.paths.size();
}

const HdFrame *frame(int index, int phase, int scale, int baseWidth, int baseHeight)
{
	scan();
	if (scale < 1 || baseWidth < 1 || baseHeight < 1)
	{
		return nullptr;
	}
	if (scale != scanScale)
	{
		// the display scale changed: the pictures are read again at the new size
		for (auto &pair : tiles)
		{
			pair.second.loaded.clear();
			pair.second.lru.clear();
		}
		bytes = 0;
		scanScale = scale;
	}
	auto it = tiles.find(index);
	if (it == tiles.end() || it->second.paths.empty())
	{
		return nullptr;
	}
	Tile &tile = it->second;
	const int p = tile.paths.empty() ? 0 : (phase % (int)tile.paths.size());
	auto got = tile.loaded.find(p);
	if (got != tile.loaded.end())
	{
		tile.lru[p] = ++clock_;
		return got->second.empty() ? nullptr : &got->second;
	}
	HdFrame frame;
	if (!HdSprites::loadPng(tile.paths[p], frame) || frame.empty())
	{
		Log(LOG_WARNING) << "HD base: cannot read " << tile.paths[p];
		tile.loaded[p] = HdFrame();       // remembered as missing, not read again
		tile.lru[p] = ++clock_;
		return nullptr;
	}
	const int w = baseWidth * scale, h = baseHeight * scale;
	if (frame.width != w || frame.height != h)
	{
		HdFrame scaled;
		HdSprites::resample(frame, w, h, scaled);
		frame = std::move(scaled);
	}
	bytes += frame.pixels.size() * sizeof(Uint32);
	HdFrame &stored = tile.loaded[p];
	stored = std::move(frame);
	tile.lru[p] = ++clock_;
	trim(&stored);
	return &stored;
}

bool animated()
{
	scan();
	return anyAnimated;
}

void clear()
{
	tiles.clear();
	scanned = false;
	scanScale = 0;
	bytes = 0;
	anyAnimated = false;
}

void setBudget(size_t value)
{
	budget = value;
}

}

}
