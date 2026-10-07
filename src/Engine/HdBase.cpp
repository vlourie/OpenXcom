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
#include <algorithm>
#include <cstdlib>
#include <map>
#include <memory>
#include <sstream>
#include <vector>
#include "FileMap.h"
#include "HdSprites.h"
#include "HdUiArt.h"
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
const char *ANIM = ".anim.txt";
const int MAX_PHASES = 64;
/// One phase of a loop or a burst (BaseView::blink steps every other tick of its 100 ms timer).
const Uint32 STEP = 200;
const Uint32 NEVER = 0xFFFFFFFFu;
/// Keys of the loaded pictures of a tile: the still one, a piece of the loop, a piece of the burst.
const int STILL = 0, LOOP = 1, BURST = 1000;
/// Files use the master mod's own frame numbers; the game adds the master's offset (set by clear()).
int masterOffset = 1000;

struct Tile
{
	std::string still;                               ///< <N>.png
	std::vector<std::string> loop;                   ///< .v1, .v2 ... in order
	std::vector<std::string> burst;                  ///< .b1, .b2 ... in order
	bool described = false;                          ///< has .anim.txt; else an older pack: <N>.png and .v* are whole phases of a loop
	int width = 0, height = 0;                       ///< size of the picture in the pack
	SDL_Rect loopAt = {}, burstAt = {};              ///< where the pieces lie, in the pack's pixels
	Uint32 cycle = 0;                                ///< ms from one burst to the next (0: no bursts)
	std::map<int, HdFrame> loaded;                   ///< key -> picture at the current scale
	std::map<int, size_t> lru;
};

/// A picture of a tile: its file, its key among the loaded ones, where it lies (w == 0: the whole tile).
struct Piece
{
	const std::string *path;
	int key;
	SDL_Rect at;
};

std::map<int, Tile> tiles;
bool scanned = false;
int scanScale = 0;
size_t budget = 64u * 1024u * 1024u;
size_t bytes = 0;
size_t clock_ = 0;
bool anyAnimated = false;

/// "<index>" followed by `rest`: the index, or -1.
int indexOf(const std::string &file, size_t end)
{
	char *stop = nullptr;
	const long index = std::strtol(file.c_str(), &stop, 10);
	return stop == file.c_str() + end && end > 0 && index >= 0 ? (int)index : -1;
}

/// Reads "<index>.anim.txt": the size, where the pieces lie, how often the burst comes.
void describe(Tile &tile, const std::string &path)
{
	std::unique_ptr<std::istream> in = FileMap::getIStream(path);
	if (!in)
	{
		return;
	}
	tile.described = true;
	int every = 0;
	std::string line;
	while (std::getline(*in, line))
	{
		std::istringstream words(line);
		std::string key;
		words >> key;
		if (key == "size")
		{
			words >> tile.width >> tile.height;
		}
		else if (key == "loop" || key == "burst")
		{
			int x = 0, y = 0, w = 0, h = 0;
			words >> x >> y >> w >> h;
			(key == "loop" ? tile.loopAt : tile.burstAt) = SDL_Rect{ (Sint16)x, (Sint16)y, (Uint16)w, (Uint16)h };
		}
		else if (key == "every")
		{
			words >> every;
		}
	}
	tile.cycle = every > 0 ? (Uint32)every * 1000u : 0;
}

/// Reads the folder once: which tile has which pictures.
void scan()
{
	if (scanned)
	{
		return;
	}
	scanned = true;
	const std::string anim = ANIM;
	std::map<int, std::map<int, std::string>> loops, bursts;
	for (const std::string &file : HdSprites::artFolder(FOLDER))
	{
		const size_t dot = file.find('.');
		if (dot == std::string::npos || dot == 0)
		{
			continue;
		}
		const int index = indexOf(file, dot);
		if (index < 0)
		{
			continue;
		}
		const std::string rest = file.substr(dot);
		const std::string path = HdSprites::artPath(std::string(FOLDER) + "/" + file);
		if (rest == ".png")
		{
			tiles[index].still = path;
			continue;
		}
		if (rest == anim)
		{
			describe(tiles[index], path);
			continue;
		}
		// ".v<n>.png" or ".b<n>.png"
		if (rest.size() < 7 || rest[0] != '.' || (rest[1] != 'v' && rest[1] != 'b') || rest.compare(rest.size() - 4, 4, ".png") != 0)
		{
			continue;
		}
		const std::string number = rest.substr(2, rest.size() - 6);
		char *vend = nullptr;
		const long v = std::strtol(number.c_str(), &vend, 10);
		if (number.empty() || !vend || *vend != '\0' || v < 1 || v > MAX_PHASES)
		{
			continue;
		}
		(rest[1] == 'v' ? loops : bursts)[index][(int)v] = path;
	}
	// the phases run from 1 and stop at the first missing one
	auto collect = [](const std::map<int, std::string> &from, std::vector<std::string> &to)
	{
		for (int n = 1; from.count(n); ++n)
		{
			to.push_back(from.at(n));
		}
	};
	for (auto it = tiles.begin(); it != tiles.end(); )
	{
		Tile &tile = it->second;
		// a picture of the tile itself is what makes it HD
		if (tile.still.empty())
		{
			it = tiles.erase(it);
			continue;
		}
		if (loops.count(it->first))
		{
			collect(loops[it->first], tile.loop);
		}
		if (tile.described && bursts.count(it->first))
		{
			collect(bursts[it->first], tile.burst);
		}
		// pieces need the size of the whole picture to be placed
		if (tile.described && (tile.width < 1 || tile.height < 1))
		{
			Log(LOG_WARNING) << "HD base: no size in the description of " << it->first << ", its animation is left out";
			tile.loop.clear();
			tile.burst.clear();
		}
		if (tile.described && (tile.loopAt.w == 0 || tile.loopAt.h == 0))
		{
			tile.loop.clear();
		}
		if (tile.described && (tile.burstAt.w == 0 || tile.burstAt.h == 0 || tile.cycle == 0))
		{
			tile.burst.clear();
		}
		// a burst starts at the loop's first phase, so the loop goes on through it without a jump,
		// and it comes no more often than every other burst length
		if (!tile.burst.empty())
		{
			const Uint32 unit = STEP * (Uint32)std::max<size_t>(1, tile.loop.size());
			const Uint32 length = STEP * (Uint32)tile.burst.size();
			tile.cycle = std::max(tile.cycle, 2 * length) / unit * unit;
			tile.cycle = std::max(tile.cycle, ((length + unit - 1) / unit + 1) * unit);
		}
		anyAnimated = anyAnimated || !tile.loop.empty() || !tile.burst.empty();
		++it;
	}
	if (!tiles.empty())
	{
		Log(LOG_INFO) << "HD base: " << tiles.size() << " tiles with pictures" << (anyAnimated ? " (animated)" : "")
			<< ", master frames from " << masterOffset;
	}
}

/// The tile of a game frame: by its number, else by the number without the master mod's offset.
std::map<int, Tile>::iterator findTile(int index)
{
	auto it = tiles.find(index);
	if (it == tiles.end() && masterOffset > 0 && index >= masterOffset)
	{
		it = tiles.find(index - masterOffset);
	}
	return it;
}

/// The still picture, phase `n` of the loop, or phase `n` of the burst.
Piece stillPiece(const Tile &tile)
{
	return { &tile.still, STILL, SDL_Rect{} };
}
Piece loopPiece(const Tile &tile, int n)
{
	return { &tile.loop[n], LOOP + n, tile.described ? tile.loopAt : SDL_Rect{} };
}
Piece burstPiece(const Tile &tile, int n)
{
	return { &tile.burst[n], BURST + n, tile.burstAt };
}

/// Where a piece goes on screen, relative to the tile, and its size there.
SDL_Rect placeOf(const Tile &tile, const Piece &piece, int scale, int baseWidth, int baseHeight)
{
	const int w = baseWidth * scale, h = baseHeight * scale;
	if (piece.at.w == 0 || tile.width < 1 || tile.height < 1)
	{
		return SDL_Rect{ 0, 0, (Uint16)w, (Uint16)h };
	}
	// the pack puts pieces on whole classic pixels, so this is exact at any scale
	return SDL_Rect{ (Sint16)(piece.at.x * w / tile.width), (Sint16)(piece.at.y * h / tile.height),
		(Uint16)(piece.at.w * w / tile.width), (Uint16)(piece.at.h * h / tile.height) };
}

/// Drops the pictures found longest ago while the loaded ones exceed the budget.
void trim(const HdFrame *keep)
{
	while (bytes > budget)
	{
		Tile *oldestTile = nullptr;
		int oldestKey = -1;
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
				oldestKey = use.first;
			}
		}
		if (!oldestTile)
		{
			return;
		}
		HdFrame &f = oldestTile->loaded[oldestKey];
		bytes -= f.pixels.size() * sizeof(Uint32);
		oldestTile->loaded.erase(oldestKey);
		oldestTile->lru.erase(oldestKey);
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

/// Keeps a picture (an empty one is remembered as missing, not read again).
HdFrame &store(Tile &tile, int key, HdFrame &&frame)
{
	bytes += frame.pixels.size() * sizeof(Uint32);
	HdFrame &stored = tile.loaded[key];
	stored = std::move(frame);
	tile.lru[key] = ++clock_;
	return stored;
}

/// A piece at its size on screen, read now if it was not.
const HdFrame *get(Tile &tile, const Piece &piece, int scale, int baseWidth, int baseHeight)
{
	auto got = tile.loaded.find(piece.key);
	if (got != tile.loaded.end())
	{
		tile.lru[piece.key] = ++clock_;
		return got->second.empty() ? nullptr : &got->second;
	}
	HdFrame frame;
	if (!HdSprites::loadPng(*piece.path, frame) || frame.empty())
	{
		Log(LOG_WARNING) << "HD base: cannot read " << *piece.path;
		store(tile, piece.key, HdFrame());
		return nullptr;
	}
	const SDL_Rect place = placeOf(tile, piece, scale, baseWidth, baseHeight);
	fit(frame, place.w, place.h);
	HdFrame &stored = store(tile, piece.key, std::move(frame));
	trim(&stored);
	return &stored;
}

/// Draws a piece of the tile whose top left corner is at (x, y).
void put(SDL_Surface *dest, Tile &tile, const Piece &piece, int x, int y, int scale, int baseWidth, int baseHeight)
{
	if (const HdFrame *f = get(tile, piece, scale, baseWidth, baseHeight))
	{
		const SDL_Rect place = placeOf(tile, piece, scale, baseWidth, baseHeight);
		HdUiArt::drawFrame(dest, *f, x + place.x, y + place.y);
	}
}

/// Where in its cycle a facility's burst starts: spread over the cycle by the facility's seed.
Uint32 offsetOf(Uint32 seed, Uint32 cycle)
{
	Uint32 h = seed * 2654435761u;
	h ^= h >> 15;
	return (h % (cycle / STEP)) * STEP;
}

}

int phases(int index)
{
	scan();
	auto it = findTile(index);
	return it == tiles.end() ? 0 : 1 + (int)it->second.loop.size() + (int)it->second.burst.size();
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
	if (it == tiles.end())
	{
		return nullptr;
	}
	Tile &tile = it->second;
	const int n = tile.described ? 1 : 1 + (int)tile.loop.size();
	const int p = phase % n;
	return get(tile, p == 0 ? stillPiece(tile) : loopPiece(tile, p - 1), scale, baseWidth, baseHeight);
}

Uint32 draw(SDL_Surface *dest, int index, int x, int y, int scale, int baseWidth, int baseHeight,
	bool animate, Uint32 ms, Uint32 seed)
{
	scan();
	if (!dest || scale < 1 || baseWidth < 1 || baseHeight < 1)
	{
		return NEVER;
	}
	setScale(scale);
	auto it = findTile(index);
	if (it == tiles.end())
	{
		return NEVER;
	}
	Tile &tile = it->second;
	if (!tile.described)
	{
		// an older pack: the still picture is the loop's first phase
		const Uint32 n = 1 + (Uint32)tile.loop.size();
		const Uint32 p = animate ? (ms / STEP) % n : 0;
		put(dest, tile, p == 0 ? stillPiece(tile) : loopPiece(tile, (int)p - 1), x, y, scale, baseWidth, baseHeight);
		return animate && n > 1 ? ms + STEP - ms % STEP : NEVER;
	}
	put(dest, tile, stillPiece(tile), x, y, scale, baseWidth, baseHeight);
	if (!animate)
	{
		return NEVER;
	}
	const Uint32 t = ms + (tile.cycle ? offsetOf(seed, tile.cycle) : 0);
	const Uint32 nextStep = ms + STEP - t % STEP;
	Uint32 next = NEVER;
	if (!tile.loop.empty())
	{
		put(dest, tile, loopPiece(tile, (int)((t / STEP) % tile.loop.size())), x, y, scale, baseWidth, baseHeight);
		next = nextStep;
	}
	if (!tile.burst.empty())
	{
		// the burst holds the loop inside its piece, at the same phase (the cycle is whole loops)
		const Uint32 at = t % tile.cycle;
		if (at < STEP * (Uint32)tile.burst.size())
		{
			put(dest, tile, burstPiece(tile, (int)(at / STEP)), x, y, scale, baseWidth, baseHeight);
			next = nextStep;
		}
		else
		{
			next = std::min(next, ms + (tile.cycle - at));
		}
	}
	return next;
}

void preload(const std::vector<Want> &want, int scale, bool allPhases)
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
		Piece piece;
		int w, h;
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
		std::vector<Piece> pieces = { stillPiece(tile) };
		for (int n = 0; allPhases && n < (int)tile.loop.size(); ++n)
		{
			pieces.push_back(loopPiece(tile, n));
		}
		for (int n = 0; allPhases && n < (int)tile.burst.size(); ++n)
		{
			pieces.push_back(burstPiece(tile, n));
		}
		for (const Piece &piece : pieces)
		{
			if (tile.loaded.count(piece.key))
			{
				continue;
			}
			bool queued = false;
			for (const Job &job : jobs)
			{
				queued = queued || (job.tile == &tile && job.piece.key == piece.key);
			}
			if (!queued)
			{
				const SDL_Rect place = placeOf(tile, piece, scale, one.baseWidth, one.baseHeight);
				jobs.push_back({ &tile, piece, place.w, place.h, std::string(), nullptr, 0, HdFrame(), false });
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
		const std::string &path = *job.piece.path;
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
			Log(LOG_WARNING) << "HD base: cannot read " << *job.piece.path;
			job.frame = HdFrame();
		}
		else
		{
			++read;
		}
		store(*job.tile, job.piece.key, std::move(job.frame));
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

void clear(int offset)
{
	masterOffset = offset;
	tiles.clear();
	scanned = false;
	scanScale = 0;
	bytes = 0;
	anyAnimated = false;
}

}

}
