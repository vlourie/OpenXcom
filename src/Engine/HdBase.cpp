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
#include "HdSprites.h"
#include "HdWorkers.h"
#include "Logger.h"
#include "SDL2Helpers.h"

namespace OpenXcom
{

namespace HdBase
{

namespace
{

const char *FOLDER = "BASEBITS.PCK";
const int MAX_PHASES = 16;
/// Files use the master mod's own frame numbers; the game adds the master's offset (see HdCraftLights).
const int MASTER_OFFSET = 1000;

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
	const std::vector<std::string> files = HdSprites::artFolder(FOLDER);
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
		tile.paths[phase] = HdSprites::artPath(std::string(FOLDER) + "/" + file);
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

/// The tile of a game frame: by its number, else by the number without the master mod's offset.
std::map<int, Tile>::iterator findTile(int index)
{
	auto it = tiles.find(index);
	if (it == tiles.end() && index >= MASTER_OFFSET)
	{
		it = tiles.find(index - MASTER_OFFSET);
	}
	return it;
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

/// The display scale changed: the pictures are read again at the new size.
void setScale(int scale)
{
	if (scale == scanScale)
	{
		return;
	}
	for (auto &pair : tiles)
	{
		pair.second.loaded.clear();
		pair.second.lru.clear();
	}
	bytes = 0;
	scanScale = scale;
}

/// Brings a decoded picture to its size on screen.
void fit(HdFrame &frame, int w, int h)
{
	if (!frame.empty() && (frame.width != w || frame.height != h))
	{
		HdFrame scaled;
		HdSprites::resample(frame, w, h, scaled);
		frame = std::move(scaled);
	}
}

/// Keeps a picture of a phase (an empty one is remembered as missing, not read again).
HdFrame &store(Tile &tile, int p, HdFrame &&frame)
{
	bytes += frame.pixels.size() * sizeof(Uint32);
	HdFrame &stored = tile.loaded[p];
	stored = std::move(frame);
	tile.lru[p] = ++clock_;
	return stored;
}

}

int phases(int index)
{
	scan();
	auto it = findTile(index);
	return it == tiles.end() ? 0 : (int)it->second.paths.size();
}

const HdFrame *frame(int index, int phase, int scale, int baseWidth, int baseHeight)
{
	scan();
	if (scale < 1 || baseWidth < 1 || baseHeight < 1)
	{
		return nullptr;
	}
	setScale(scale);
	auto it = findTile(index);
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
		store(tile, p, HdFrame());
		return nullptr;
	}
	fit(frame, baseWidth * scale, baseHeight * scale);
	HdFrame &stored = store(tile, p, std::move(frame));
	trim(&stored);
	return &stored;
}

void preload(const std::vector<Want> &want, int scale)
{
	scan();
	if (scale < 1)
	{
		return;
	}
	setScale(scale);
	struct Job
	{
		Tile *tile;
		int phase, w, h;
		std::string file;   ///< a loose file, read by the worker; empty when `data` is read here
		void *data;
		size_t size;
		HdFrame frame;
		bool ok;
	};
	std::vector<Job> jobs;
	for (const Want &one : want)
	{
		auto it = findTile(one.index);
		if (it == tiles.end() || one.baseWidth < 1 || one.baseHeight < 1)
		{
			continue;
		}
		Tile &tile = it->second;
		for (int p = 0; p < (int)tile.paths.size(); ++p)
		{
			if (tile.loaded.count(p))
			{
				continue;
			}
			bool queued = false;
			for (const Job &job : jobs)
			{
				queued = queued || (job.tile == &tile && job.phase == p);
			}
			if (!queued)
			{
				jobs.push_back({ &tile, p, one.baseWidth * scale, one.baseHeight * scale, std::string(), nullptr, 0, HdFrame(), false });
			}
		}
	}
	if (jobs.empty())
	{
		return;
	}
	const Uint32 start = SDL_GetTicks();
	// FileMap is looked up here; a loose file is then read by the workers (a cold disk costs
	// more than decoding), a file inside a zip here, since the archive is not for threads
	for (Job &job : jobs)
	{
		const std::string &path = job.tile->paths[job.phase];
		const FileMap::FileRecord *rec = FileMap::fileExists(path) ? FileMap::at(path) : nullptr;
		if (rec && !rec->zip)
		{
			job.file = rec->fullpath;
		}
		else if (rec)
		{
			SDL_RWops *rw = rec->getRWops();
			job.data = rw ? SDL_LoadFile_RW(rw, &job.size, SDL_TRUE) : nullptr;
		}
	}
	HdWorkers::instance().run((int)jobs.size(), [&jobs](int i)
	{
		Job &job = jobs[i];
		if (!job.file.empty())
		{
			SDL_RWops *rw = SDL_RWFromFile(job.file.c_str(), "rb");
			job.data = rw ? SDL_LoadFile_RW(rw, &job.size, SDL_TRUE) : nullptr;
		}
		job.ok = job.data && HdSprites::decodePng((const unsigned char*)job.data, job.size, job.frame) && !job.frame.empty();
		if (job.ok)
		{
			fit(job.frame, job.w, job.h);
		}
	});
	size_t read = 0;
	for (Job &job : jobs)
	{
		SDL_free(job.data);
		if (!job.ok)
		{
			Log(LOG_WARNING) << "HD base: cannot read " << job.tile->paths[job.phase];
			job.frame = HdFrame();
		}
		else
		{
			++read;
		}
		store(*job.tile, job.phase, std::move(job.frame));
	}
	trim(nullptr);
	Log(LOG_INFO) << "HD base: preloaded " << read << " of " << jobs.size() << " pictures in "
		<< (SDL_GetTicks() - start) << " ms, " << (bytes >> 20) << " MB of " << (budget >> 20) << " MB";
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
