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
#include "HdSprites.h"
#include <cctype>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <sstream>
#include <unordered_map>
#include "CrossPlatform.h"
#include "FileMap.h"
#include "HdWorkers.h"
#include "Logger.h"
#include "Options.h"
#include "SDL2Helpers.h"
#include "Surface.h"
#include "SurfaceSet.h"
#include "../lodepng.h"

namespace OpenXcom
{

void HdFrame::buildSpans()
{
	rows.resize(height);
	solid.resize(height);
	for (int y = 0; y < height; ++y)
	{
		const Uint32 *p = row(y);
		int begin = 0;
		int end = width;
		while (begin < end && (p[begin] >> 24) == 0) ++begin;
		while (end > begin && (p[end - 1] >> 24) == 0) --end;
		rows[y].begin = (Uint16)begin;
		rows[y].end = (Uint16)end;
		// the longest run of opaque pixels
		int bestBegin = begin, bestEnd = begin;
		int runBegin = begin;
		for (int x = begin; x <= end; ++x)
		{
			if (x == end || (p[x] >> 24) != 255)
			{
				if (x - runBegin > bestEnd - bestBegin)
				{
					bestBegin = runBegin;
					bestEnd = x;
				}
				runBegin = x + 1;
			}
		}
		solid[y].begin = (Uint16)bestBegin;
		solid[y].end = (Uint16)bestEnd;
	}
}

namespace HdSprites
{

const char *const ART_ROOT = "hd";
const char *const ART_ROOT_ADULT = "hd_18+";

/**
 * Where to read one HD picture from. The adult tree wins when the player asked
 * for it and actually ships that file; everything it does not hold falls back
 * to the ordinary tree, so it only needs the pictures that differ.
 * @param rest Path below the tree, e.g. "UI/zombie.png" or "TERRAIN/CORP.PCK/7.png".
 */
std::string artPath(const std::string &rest)
{
	if (Options::oxceAdultArt)
	{
		std::string adult = std::string(ART_ROOT_ADULT) + "/" + rest;
		if (FileMap::fileExists(adult))
		{
			return adult;
		}
	}
	return std::string(ART_ROOT) + "/" + rest;
}

/**
 * The contents of a folder of both trees at once, so that a picture shipped
 * only by the adult tree is found too. Names are unique; resolve each of them
 * with artPath to learn which tree it is read from.
 * @param rest Folder below the tree, e.g. "UI".
 */
std::vector<std::string> artFolder(const std::string &rest)
{
	std::vector<std::string> names;
	// the path is kept in a named string: a reference bound to a temporary one
	// looks dangling to gcc, even though the set itself outlives the call
	const std::string plainPath = std::string(ART_ROOT) + "/" + rest;
	const FileMap::NameSet &plain = FileMap::getVFolderContents(plainPath);
	names.assign(plain.begin(), plain.end());
	if (Options::oxceAdultArt)
	{
		const std::string adultPath = std::string(ART_ROOT_ADULT) + "/" + rest;
		const FileMap::NameSet &adult = FileMap::getVFolderContents(adultPath);
		for (const std::string &name : adult)
		{
			if (plain.find(name) == plain.end())
			{
				names.push_back(name);
			}
		}
	}
	return names;
}


namespace
{
	/// A registered frame: read into `frame` from its file when first found (an eager frame has no path).
	struct Entry
	{
		HdFrame frame;
		std::string path;          ///< the PNG, or the pack file (empty: given as pixels, never dropped)
		Uint32 offset = 0, size = 0; ///< the blob within the pack (size 0: the whole file)
		int width = 0, height = 0; ///< the size of the palette frame it replaces
		size_t lru = 0;            ///< when it was last found
		bool failed = false;       ///< the file could not be read (not tried again)
		bool ownColour = false;    ///< color.txt of the set keeps the frame's own colours (HdFrame::ownColour)
		const void *key = nullptr; ///< the key of the frame it belongs to (a variant and a wall slot: the frame's)
		bool recoloured = false;   ///< the loaded picture went through the recolouring (setRecolour)
	};
	std::unordered_map<const void*, Entry> registry;
	/// the variants of a registered frame: slot n - 1 holds variant n (an empty path = no such variant)
	std::unordered_map<const void*, std::vector<Entry>> variants;
	const int MAX_VARIANTS = 15;
	/// An addressed wall frame (address.txt): n pictures, slot N - 1 holds <index>.<slot><N>.png (an empty path = drawn as the frame itself).
	struct WallSlots
	{
		int n = 0;
		std::string label;        ///< "<set> <index>:<slot>" for the log
		std::vector<Entry> slots;
		std::vector<char> warned; ///< the failure of a slot is logged once
	};
	/// [part - 1]: the west and the north wall slot have their own pictures of the same frame
	std::unordered_map<const void*, WallSlots> walls[2];
	std::string addressFile = "address.txt";
	/// Changes only when the addressed wall frames do (the map rebuilds its field then, see HdWallField::update).
	unsigned wallsGeneration = 1;
	/// Frames at most this big are dots, not pictures (makeDots): the bullet tracer is 3x3.
	const int MAX_DOT = 4;
	unsigned registryGeneration = 1;
	void (*beforeChangeHook)() = nullptr;
	/// Lets the canvases run the commands that point at the frames about to change.
	void beforeChange()
	{
		if (beforeChangeHook)
		{
			beforeChangeHook();
		}
	}
	size_t budget = (size_t)384 << 20;
	size_t loadedTotal = 0; ///< bytes of the lazily loaded frames in memory
	size_t clock = 0;

	size_t bytesOf(const HdFrame &frame)
	{
		return frame.pixels.size() * sizeof(Uint32) + (frame.rows.size() + frame.solid.size()) * sizeof(HdFrame::Span);
	}

	/// Measurement: frames read from files and the time it took, since takeLoadStats.
	unsigned loadFrames = 0;
	double loadMs = 0;

	void loadFile(Entry &entry);
	/// Reads a lazy entry's picture from its file (timed: the first show of a set reads its frames on the drawing thread).
	void load(Entry &entry)
	{
		const auto start = std::chrono::steady_clock::now();
		loadFile(entry);
		loadMs += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
		++loadFrames;
	}

	/// Reads the bytes of a lazy entry's picture (the file system is used from one thread only).
	bool readBlob(Entry &entry, std::vector<unsigned char> &data)
	{
		SDL_RWops *rw = FileMap::fileExists(entry.path) ? FileMap::getRWops(entry.path) : nullptr;
		if (!rw)
		{
			entry.failed = true;
			Log(LOG_WARNING) << "HD sprite: cannot open " << entry.path;
			return false;
		}
		bool ok = true;
		if (entry.size > 0)
		{
			data.resize(entry.size);
			ok = SDL_RWseek(rw, entry.offset, RW_SEEK_SET) >= 0 && (long long)SDL_RWread(rw, data.data(), 1, entry.size) == (long long)entry.size;
			SDL_RWclose(rw);
		}
		else
		{
			size_t size = 0;
			void *whole = SDL_LoadFile_RW(rw, &size, SDL_TRUE);
			ok = whole != nullptr;
			if (whole)
			{
				data.assign((const unsigned char*)whole, (const unsigned char*)whole + size);
				SDL_free(whole);
			}
		}
		return ok;
	}

	/// Decodes the bytes of a lazy entry's picture into a frame of the entry's size (any thread).
	bool decodeBlob(const Entry &entry, const std::vector<unsigned char> &data, HdFrame &out)
	{
		HdFrame read;
		if (data.empty() || !decodePng(data.data(), data.size(), read))
		{
			return false;
		}
		if (read.width != entry.width || read.height != entry.height)
		{
			resample(read, entry.width, entry.height, out);
		}
		else
		{
			out = std::move(read);
		}
		out.generated = false;
		out.buildSpans();
		return true;
	}

	/// The recolouring of the pictures read from now on (setRecolour); changed on the main thread only, never during a batch.
	Recolour recolourHook = nullptr;

	/// decodeBlob, then the recolouring (any thread).
	bool decodeShown(const Entry &entry, const std::vector<unsigned char> &data, HdFrame &out)
	{
		if (!decodeBlob(entry, data, out))
		{
			return false;
		}
		if (recolourHook)
		{
			recolourHook(entry.key, out);
		}
		return true;
	}

	/// Puts a decoded picture into its entry (or marks the entry as unreadable).
	void settle(Entry &entry, bool ok, HdFrame &&frame)
	{
		if (!ok)
		{
			entry.failed = true;
			Log(LOG_WARNING) << "HD sprite: cannot read " << entry.path << " at " << entry.offset;
			return;
		}
		entry.frame = std::move(frame);
		entry.frame.ownColour = entry.ownColour;
		entry.recoloured = recolourHook != nullptr;
		loadedTotal += bytesOf(entry.frame);
	}

	void loadFile(Entry &entry)
	{
		std::vector<unsigned char> data;
		if (!readBlob(entry, data))
		{
			if (!entry.failed) // opened, but cut short
			{
				settle(entry, false, HdFrame());
			}
			return;
		}
		HdFrame frame;
		const bool ok = decodeShown(entry, data, frame);
		settle(entry, ok, std::move(frame));
	}
}

void set(const void *key, HdFrame &&frame)
{
	if (!key)
	{
		return;
	}
	beforeChange();
	frame.buildSpans();
	Entry &entry = registry[key];
	if (!entry.path.empty() && !entry.frame.pixels.empty())
	{
		loadedTotal -= bytesOf(entry.frame);
	}
	entry = Entry();
	entry.width = frame.width;
	entry.height = frame.height;
	entry.frame = std::move(frame);
	++registryGeneration;
}

void setLazy(const void *key, const std::string &path, Uint32 offset, Uint32 size, int width, int height)
{
	if (!key || path.empty() || width <= 0 || height <= 0)
	{
		return;
	}
	beforeChange();
	Entry &entry = registry[key];
	if (!entry.path.empty() && !entry.frame.pixels.empty())
	{
		loadedTotal -= bytesOf(entry.frame);
	}
	entry = Entry();
	entry.path = path;
	entry.offset = offset;
	entry.size = size;
	entry.width = width;
	entry.height = height;
	entry.key = key;
	++registryGeneration;
}

namespace
{
	/// The frame of an entry, read from its file if needed, or nullptr.
	const HdFrame *frameOf(Entry &entry)
	{
		entry.lru = ++clock;
		if (entry.frame.pixels.empty())
		{
			if (entry.path.empty() || entry.failed)
			{
				return nullptr;
			}
			load(entry);
			if (entry.frame.pixels.empty())
			{
				return nullptr;
			}
		}
		return &entry.frame;
	}

	/// Forgets the variants of a key (their loaded bytes included).
	void dropVariants(const void *key)
	{
		auto it = variants.find(key);
		if (it == variants.end())
		{
			return;
		}
		for (Entry &entry : it->second)
		{
			if (!entry.path.empty() && !entry.frame.pixels.empty())
			{
				loadedTotal -= bytesOf(entry.frame);
			}
		}
		variants.erase(it);
	}

	/// Forgets the addressed wall pictures of a key (both slots, their loaded bytes included).
	void dropWalls(const void *key)
	{
		for (auto &part : walls)
		{
			auto it = part.find(key);
			if (it == part.end())
			{
				continue;
			}
			for (Entry &entry : it->second.slots)
			{
				if (!entry.path.empty() && !entry.frame.pixels.empty())
				{
					loadedTotal -= bytesOf(entry.frame);
				}
			}
			part.erase(it);
			++wallsGeneration;
		}
	}

	bool anyWalls()
	{
		return !walls[0].empty() || !walls[1].empty();
	}
}

void setVariantLazy(const void *key, int variant, const std::string &path, Uint32 offset, Uint32 size, int width, int height)
{
	if (!key || variant < 1 || variant > MAX_VARIANTS || path.empty() || width <= 0 || height <= 0)
	{
		return;
	}
	beforeChange();
	std::vector<Entry> &slots = variants[key];
	if ((int)slots.size() < variant)
	{
		slots.resize(variant);
	}
	Entry &entry = slots[variant - 1];
	if (!entry.path.empty() && !entry.frame.pixels.empty())
	{
		loadedTotal -= bytesOf(entry.frame);
	}
	entry = Entry();
	entry.path = path;
	entry.offset = offset;
	entry.size = size;
	entry.width = width;
	entry.height = height;
	entry.key = key;
	++registryGeneration;
}

int variantCount(const void *key)
{
	if (variants.empty())
	{
		return 0;
	}
	auto it = variants.find(key);
	return it == variants.end() ? 0 : (int)it->second.size();
}

const HdFrame *findVariant(const void *key, int variant)
{
	if (variant == 0)
	{
		return find(key);
	}
	auto it = variants.find(key);
	if (it == variants.end() || variant < 1 || variant > (int)it->second.size())
	{
		return nullptr;
	}
	return frameOf(it->second[variant - 1]);
}

int wallCount(const void *key, int part)
{
	if (part < WALL_WEST || part > WALL_NORTH || walls[part - 1].empty())
	{
		return 0;
	}
	auto it = walls[part - 1].find(key);
	return it == walls[part - 1].end() ? 0 : it->second.n;
}

const HdFrame *findWallVariant(const void *key, int part, int variant)
{
	if (part < WALL_WEST || part > WALL_NORTH)
	{
		return nullptr;
	}
	auto it = walls[part - 1].find(key);
	if (it == walls[part - 1].end() || variant < 1 || variant >= it->second.n)
	{
		return nullptr;
	}
	WallSlots &wall = it->second;
	Entry &entry = wall.slots[variant - 1];
	const HdFrame *frame = frameOf(entry);
	if (!frame && entry.failed && !wall.warned[variant - 1])
	{
		wall.warned[variant - 1] = 1;
		Log(LOG_WARNING) << "HD address: " << wall.label << " variant " << variant << " decode";
	}
	return frame;
}

std::vector<std::pair<int, int>> wallFields()
{
	std::vector<std::pair<int, int>> out;
	for (int part = WALL_WEST; part <= WALL_NORTH; ++part)
	{
		for (const auto &pair : walls[part - 1])
		{
			const std::pair<int, int> field(part, pair.second.n);
			if (std::find(out.begin(), out.end(), field) == out.end())
			{
				out.push_back(field);
			}
		}
	}
	std::sort(out.begin(), out.end());
	return out;
}

std::string wallLabel(const void *key, int part)
{
	if (part < WALL_WEST || part > WALL_NORTH)
	{
		return std::string();
	}
	auto it = walls[part - 1].find(key);
	return it == walls[part - 1].end() ? std::string() : it->second.label;
}

void setAddressFile(const std::string &name)
{
	addressFile = name.empty() ? std::string("address.txt") : name;
}

const HdFrame *find(const void *key)
{
	if (registry.empty())
	{
		return nullptr;
	}
	auto it = registry.find(key);
	if (it == registry.end())
	{
		return nullptr;
	}
	Entry &entry = it->second;
	entry.lru = ++clock;
	if (entry.frame.pixels.empty())
	{
		if (entry.path.empty() || entry.failed)
		{
			return nullptr;
		}
		load(entry);
		if (entry.frame.pixels.empty())
		{
			return nullptr;
		}
	}
	return &entry.frame;
}

bool registered(const void *key)
{
	return !registry.empty() && registry.find(key) != registry.end();
}

void remove(const void *key)
{
	beforeChange();
	auto it = registry.find(key);
	if (it != registry.end())
	{
		if (!it->second.path.empty() && !it->second.frame.pixels.empty())
		{
			loadedTotal -= bytesOf(it->second.frame);
		}
		registry.erase(it);
		++registryGeneration;
	}
	if (variants.count(key))
	{
		dropVariants(key);
		++registryGeneration;
	}
	if (walls[0].count(key) || walls[1].count(key))
	{
		dropWalls(key);
		++registryGeneration;
	}
}

void removeSet(const SurfaceSet *surfaceSet)
{
	if (!surfaceSet || (registry.empty() && variants.empty() && !anyWalls()))
	{
		return;
	}
	beforeChange();
	for (size_t i = 0; i < surfaceSet->getTotalFrames(); ++i)
	{
		const Surface *frame = surfaceSet->getFrame((int)i);
		if (frame)
		{
			auto it = registry.find(frame->getBuffer());
			if (it != registry.end())
			{
				if (!it->second.path.empty() && !it->second.frame.pixels.empty())
				{
					loadedTotal -= bytesOf(it->second.frame);
				}
				registry.erase(it);
			}
			dropVariants(frame->getBuffer());
			dropWalls(frame->getBuffer());
		}
	}
	++registryGeneration;
}

void clear()
{
	beforeChange();
	registry.clear();
	variants.clear();
	walls[0].clear();
	walls[1].clear();
	++wallsGeneration;
	loadedTotal = 0;
	++registryGeneration;
}

size_t count()
{
	return registry.size();
}

size_t loaded()
{
	size_t n = 0;
	for (const auto &pair : registry)
	{
		if (!pair.second.path.empty() && !pair.second.frame.pixels.empty())
		{
			++n;
		}
	}
	for (const auto &pair : variants)
	{
		for (const Entry &entry : pair.second)
		{
			if (!entry.path.empty() && !entry.frame.pixels.empty())
			{
				++n;
			}
		}
	}
	for (const auto &part : walls)
	{
		for (const auto &pair : part)
		{
			for (const Entry &entry : pair.second.slots)
			{
				if (!entry.path.empty() && !entry.frame.pixels.empty())
				{
					++n;
				}
			}
		}
	}
	return n;
}

size_t loadedBytes()
{
	return loadedTotal;
}

/**
 * Drops the lazily read frames found longest ago until the loaded ones are
 * a quarter under the budget (so this runs rarely, not every frame).
 */
namespace
{
	/// The budget of the loaded frames; OXCE_HD_PACK_BUDGET=<MB> overrides it (tests of the dropping).
	size_t budgetBytes()
	{
		static bool budgetRead = false;
		if (!budgetRead)
		{
			budgetRead = true;
			const char *env = getenv("OXCE_HD_PACK_BUDGET");
			if (env && atoi(env) > 0)
			{
				budget = (size_t)atoi(env) << 20;
			}
		}
		return budget;
	}
}

int preload(const SurfaceSet *surfaceSet)
{
	if (!surfaceSet || registry.empty())
	{
		return 0;
	}
	// the entries of the set not read yet (the frames and their variants), while half the budget is free:
	// what is preloaded must not push out what is on screen
	std::vector<Entry*> todo;
	size_t planned = loadedTotal;
	auto want = [&](Entry &entry)
	{
		if (entry.path.empty() || entry.failed || !entry.frame.pixels.empty())
		{
			return;
		}
		const size_t bytes = (size_t)entry.width * entry.height * sizeof(Uint32);
		if (planned + bytes > budgetBytes() / 2)
		{
			return;
		}
		planned += bytes;
		todo.push_back(&entry);
	};
	for (size_t i = 0; i < surfaceSet->getTotalFrames(); ++i)
	{
		const Surface *frame = surfaceSet->getFrame((int)i);
		if (!frame)
		{
			continue;
		}
		auto it = registry.find(frame->getBuffer());
		if (it != registry.end())
		{
			want(it->second);
		}
		auto vit = variants.find(frame->getBuffer());
		if (vit != variants.end())
		{
			for (Entry &variant : vit->second)
			{
				want(variant);
			}
		}
		for (auto &part : walls)
		{
			auto wit = part.find(frame->getBuffer());
			if (wit != part.end())
			{
				for (Entry &variant : wit->second.slots)
				{
					want(variant);
				}
			}
		}
	}
	if (todo.empty())
	{
		return 0;
	}
	const auto start = std::chrono::steady_clock::now();
	// the bytes here (the file system is not shared between threads), the decoding on all cores
	std::vector<std::vector<unsigned char>> blobs(todo.size());
	for (size_t i = 0; i < todo.size(); ++i)
	{
		if (!readBlob(*todo[i], blobs[i]))
		{
			blobs[i].clear();
		}
	}
	std::vector<HdFrame> frames(todo.size());
	std::vector<char> ok(todo.size(), 0);
	HdWorkers::instance().run((int)todo.size(), [&](int i)
	{
		ok[i] = !todo[i]->failed && decodeShown(*todo[i], blobs[i], frames[i]);
	});
	int loaded = 0;
	for (size_t i = 0; i < todo.size(); ++i)
	{
		if (todo[i]->failed)
		{
			continue; // could not be opened (already told)
		}
		settle(*todo[i], ok[i] != 0, std::move(frames[i]));
		if (ok[i])
		{
			todo[i]->lru = ++clock;
			++loaded;
		}
	}
	Log(LOG_INFO) << "HD sprites: " << loaded << " frame(s) read ahead in "
		<< (int)(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count() + 0.5) << " ms";
	return loaded;
}

void trim()
{
	const size_t budget = budgetBytes();
	if (loadedTotal <= budget)
	{
		return;
	}
	beforeChange();
	std::vector<std::pair<size_t, Entry*>> candidates;
	for (auto &pair : registry)
	{
		Entry &entry = pair.second;
		if (!entry.path.empty() && !entry.frame.pixels.empty())
		{
			candidates.emplace_back(entry.lru, &entry);
		}
	}
	for (auto &pair : variants)
	{
		for (Entry &entry : pair.second)
		{
			if (!entry.path.empty() && !entry.frame.pixels.empty())
			{
				candidates.emplace_back(entry.lru, &entry);
			}
		}
	}
	for (auto &part : walls)
	{
		for (auto &pair : part)
		{
			for (Entry &entry : pair.second.slots)
			{
				if (!entry.path.empty() && !entry.frame.pixels.empty())
				{
					candidates.emplace_back(entry.lru, &entry);
				}
			}
		}
	}
	std::sort(candidates.begin(), candidates.end(), [](const std::pair<size_t, Entry*> &a, const std::pair<size_t, Entry*> &b) { return a.first < b.first; });
	const size_t target = budget - budget / 4;
	size_t dropped = 0;
	for (auto &c : candidates)
	{
		if (loadedTotal <= target)
		{
			break;
		}
		loadedTotal -= bytesOf(c.second->frame);
		c.second->frame = HdFrame();
		++dropped;
	}
	Log(LOG_DEBUG) << "HD sprites: dropped " << dropped << " frame(s) read longest ago, " << (loadedTotal >> 20) << " MB loaded";
}

unsigned generation()
{
	return registryGeneration;
}

unsigned wallGeneration()
{
	return wallsGeneration;
}

void setBeforeChange(void (*hook)())
{
	beforeChangeHook = hook;
}

void takeLoadStats(unsigned &frames, double &ms)
{
	frames = loadFrames;
	ms = loadMs;
	loadFrames = 0;
	loadMs = 0;
}

namespace
{
	/// Every lazy entry (the frames, their variants, the addressed walls).
	template <typename Fn>
	void forEachLazy(Fn fn)
	{
		for (auto &pair : registry)
		{
			fn(pair.second);
		}
		for (auto &pair : variants)
		{
			for (Entry &entry : pair.second)
			{
				fn(entry);
			}
		}
		for (auto &part : walls)
		{
			for (auto &pair : part)
			{
				for (Entry &entry : pair.second.slots)
				{
					fn(entry);
				}
			}
		}
	}
}

void setRecolour(Recolour fn)
{
	if (fn == recolourHook && fn == nullptr)
	{
		return;
	}
	beforeChange();
	// what the previous recolouring made goes: read again from the files when drawn
	size_t dropped = 0;
	forEachLazy([&](Entry &entry)
	{
		if (entry.recoloured && !entry.path.empty() && !entry.frame.pixels.empty())
		{
			loadedTotal -= bytesOf(entry.frame);
			entry.frame = HdFrame();
			++dropped;
		}
		entry.recoloured = false;
	});
	recolourHook = fn;
	size_t recoloured = 0;
	if (fn)
	{
		// the loaded pictures are in their own colours now: each goes through the new one once
		std::vector<Entry*> todo;
		forEachLazy([&](Entry &entry)
		{
			if (!entry.path.empty() && !entry.frame.pixels.empty())
			{
				todo.push_back(&entry);
			}
		});
		HdWorkers::instance().run((int)todo.size(), [&](int i)
		{
			fn(todo[i]->key, todo[i]->frame);
		});
		for (Entry *entry : todo)
		{
			entry->recoloured = true;
		}
		recoloured = todo.size();
	}
	++registryGeneration;
	Log(LOG_INFO) << "HD sprites: recolouring " << (fn ? "on" : "off") << ", " << dropped << " recoloured frame(s) dropped, "
		<< recoloured << " loaded frame(s) recoloured";
}

size_t scanPictures(const std::vector<const SurfaceSet*> &sets, const std::function<void(size_t place, const Surface &classic, const HdFrame &picture)> &fn)
{
	struct Item
	{
		Entry *entry;
		const Surface *classic;
	};
	std::vector<Item> items;
	std::vector<const SurfaceSet*> seen;
	for (const SurfaceSet *surfaceSet : sets)
	{
		if (!surfaceSet || std::find(seen.begin(), seen.end(), surfaceSet) != seen.end())
		{
			continue;
		}
		seen.push_back(surfaceSet);
		for (size_t i = 0; i < surfaceSet->getTotalFrames(); ++i)
		{
			const Surface *frame = surfaceSet->getFrame((int)i);
			if (!frame)
			{
				continue;
			}
			const void *key = frame->getBuffer();
			auto want = [&](Entry &entry)
			{
				if (!entry.path.empty() && !entry.failed)
				{
					items.push_back(Item{ &entry, frame });
				}
			};
			auto it = registry.find(key);
			if (it != registry.end())
			{
				want(it->second);
			}
			auto vit = variants.find(key);
			if (vit != variants.end())
			{
				for (Entry &variant : vit->second)
				{
					want(variant);
				}
			}
			for (auto &part : walls)
			{
				auto wit = part.find(key);
				if (wit != part.end())
				{
					for (Entry &slot : wit->second.slots)
					{
						want(slot);
					}
				}
			}
		}
	}
	// in batches: the bytes here (the file system is not shared between threads), decoding and fn on all cores
	const size_t BATCH = 256;
	std::vector<std::vector<unsigned char>> blobs;
	std::vector<HdFrame> frames;
	for (size_t first = 0; first < items.size(); first += BATCH)
	{
		const size_t n = std::min(BATCH, items.size() - first);
		blobs.assign(n, std::vector<unsigned char>());
		frames.assign(n, HdFrame());
		std::vector<char> own(n, 0); // the loaded picture is in its own colours: given as it is
		for (size_t i = 0; i < n; ++i)
		{
			Entry &entry = *items[first + i].entry;
			if (!entry.frame.pixels.empty() && !entry.recoloured)
			{
				own[i] = 1;
			}
			else
			{
				// a failure to open is told and the entry marked; the picture is left out
				if (!readBlob(entry, blobs[i]))
				{
					blobs[i].clear();
				}
			}
		}
		HdWorkers::instance().run((int)n, [&](int i)
		{
			const Item &item = items[first + i];
			if (own[i])
			{
				fn(first + i, *item.classic, item.entry->frame);
			}
			else if (!blobs[i].empty() && decodeBlob(*item.entry, blobs[i], frames[i]))
			{
				fn(first + i, *item.classic, frames[i]);
			}
		});
	}
	return items.size();
}

/**
 * Decodes an RGBA PNG (any PNG color type, converted to 8-bit RGBA) from the
 * virtual file system into a frame.
 */
bool loadPng(const std::string &path, HdFrame &frame)
{
	if (!FileMap::fileExists(path))
	{
		return false;
	}
	SDL_RWops *rw = FileMap::getRWops(path);
	if (!rw)
	{
		return false;
	}
	size_t size = 0;
	void *data = SDL_LoadFile_RW(rw, &size, SDL_TRUE);
	if (!data)
	{
		return false;
	}
	const bool ok = decodePng((const unsigned char*)data, size, frame);
	SDL_free(data);
	if (!ok)
	{
		Log(LOG_ERROR) << "HD sprite " << path << " cannot be decoded";
	}
	return ok;
}

bool decodePng(const unsigned char *data, size_t size, HdFrame &frame)
{
	std::vector<unsigned char> image;
	unsigned width = 0, height = 0;
	const unsigned error = lodepng::decode(image, width, height, data, size, LCT_RGBA, 8);
	if (error)
	{
		Log(LOG_ERROR) << "HD sprite PNG: " << lodepng_error_text(error);
		return false;
	}
	frame.width = (int)width;
	frame.height = (int)height;
	frame.pixels.resize((size_t)width * height);
	const unsigned char *s = image.data();
	for (size_t i = 0; i < frame.pixels.size(); ++i, s += 4)
	{
		frame.pixels[i] = ((Uint32)s[3] << 24) | ((Uint32)s[0] << 16) | ((Uint32)s[1] << 8) | (Uint32)s[2];
	}
	frame.generated = false;
	return true;
}

namespace
{
	/// One axis of a separable resample: the weights of the source pixels of every destination pixel
	/// (a box over the covered source span when shrinking, a tent between the two nearest when growing).
	struct AxisWeights
	{
		struct Tap { int first; std::vector<float> w; };
		std::vector<Tap> taps;
	};

	AxisWeights axisWeights(int from, int to)
	{
		AxisWeights out;
		out.taps.resize(to);
		const float ratio = (float)from / to; // source pixels per destination pixel
		for (int d = 0; d < to; ++d)
		{
			AxisWeights::Tap &tap = out.taps[d];
			if (ratio > 1.0f)
			{
				const float a = d * ratio, b = (d + 1) * ratio;
				tap.first = std::max(0, (int)std::floor(a));
				const int last = std::min(from - 1, (int)std::ceil(b) - 1);
				for (int sx = tap.first; sx <= last; ++sx)
				{
					const float cover = std::min(b, (float)sx + 1) - std::max(a, (float)sx);
					tap.w.push_back(std::max(0.0f, cover) / ratio);
				}
			}
			else
			{
				const float c = (d + 0.5f) * ratio - 0.5f;
				const int s0 = (int)std::floor(c);
				const float t = c - s0;
				tap.first = std::max(0, s0);
				if (s0 < 0)
				{
					tap.w.push_back(1.0f);
				}
				else if (s0 + 1 >= from)
				{
					tap.first = from - 1;
					tap.w.push_back(1.0f);
				}
				else
				{
					tap.w.push_back(1.0f - t);
					tap.w.push_back(t);
				}
			}
		}
		return out;
	}
}

/**
 * Resamples a frame to another size (premultiplied alpha, so edges keep
 * their colour): a box filter where it shrinks, bilinear where it grows.
 */
void resample(const HdFrame &src, int width, int height, HdFrame &dst)
{
	dst = HdFrame();
	dst.width = width;
	dst.height = height;
	if (width <= 0 || height <= 0 || src.width <= 0 || src.height <= 0 || src.pixels.empty())
	{
		return;
	}
	// premultiplied floats, horizontal pass into (width x src.height), then vertical
	const AxisWeights wx = axisWeights(src.width, width), wy = axisWeights(src.height, height);
	std::vector<float> mid((size_t)width * src.height * 4, 0.0f);
	for (int y = 0; y < src.height; ++y)
	{
		const Uint32 *row = src.row(y);
		float *out = &mid[(size_t)y * width * 4];
		for (int x = 0; x < width; ++x, out += 4)
		{
			const AxisWeights::Tap &tap = wx.taps[x];
			for (size_t i = 0; i < tap.w.size(); ++i)
			{
				const Uint32 p = row[tap.first + (int)i];
				const float a = (p >> 24) * tap.w[i];
				out[0] += ((p >> 16) & 0xFF) * a;
				out[1] += ((p >> 8) & 0xFF) * a;
				out[2] += (p & 0xFF) * a;
				out[3] += a;
			}
		}
	}
	dst.pixels.assign((size_t)width * height, 0u);
	std::vector<float> acc((size_t)width * 4);
	for (int y = 0; y < height; ++y)
	{
		std::fill(acc.begin(), acc.end(), 0.0f);
		const AxisWeights::Tap &tap = wy.taps[y];
		for (size_t i = 0; i < tap.w.size(); ++i)
		{
			const float *in = &mid[(size_t)(tap.first + (int)i) * width * 4];
			const float w = tap.w[i];
			for (size_t j = 0; j < acc.size(); ++j)
			{
				acc[j] += in[j] * w;
			}
		}
		Uint32 *out = &dst.pixels[(size_t)y * width];
		for (int x = 0; x < width; ++x)
		{
			const float a = acc[(size_t)x * 4 + 3];
			if (a < 0.5f)
			{
				out[x] = 0;
				continue;
			}
			const int r = std::min(255, (int)(acc[(size_t)x * 4] / a + 0.5f));
			const int g = std::min(255, (int)(acc[(size_t)x * 4 + 1] / a + 0.5f));
			const int b = std::min(255, (int)(acc[(size_t)x * 4 + 2] / a + 0.5f));
			const int al = std::min(255, (int)(a + 0.5f));
			out[x] = ((Uint32)al << 24) | ((Uint32)r << 16) | ((Uint32)g << 8) | (Uint32)b;
		}
	}
	dst.generated = src.generated;
}

bool pngSize(const std::string &path, int &width, int &height)
{
	width = height = 0;
	if (!FileMap::fileExists(path))
	{
		return false;
	}
	SDL_RWops *rw = FileMap::getRWops(path);
	if (!rw)
	{
		return false;
	}
	// signature (8) + IHDR length/type (8) + width (4) + height (4), big-endian
	unsigned char head[24];
	const long long got = SDL_RWread(rw, head, 1, sizeof(head)); // SDL 1.2 returns -1 on error
	SDL_RWclose(rw);
	if (got < (long long)sizeof(head) || memcmp(head + 12, "IHDR", 4) != 0)
	{
		return false;
	}
	width = (head[16] << 24) | (head[17] << 16) | (head[18] << 8) | head[19];
	height = (head[20] << 24) | (head[21] << 16) | (head[22] << 8) | head[23];
	return width > 0 && height > 0;
}

namespace
{
	Uint32 readU32(const unsigned char *p)
	{
		return (Uint32)p[0] | ((Uint32)p[1] << 8) | ((Uint32)p[2] << 16) | ((Uint32)p[3] << 24);
	}
	/// Registers the frames of a pack file (its table only; the pictures are read when drawn).
	int registerPackFile(const std::string &path, SurfaceSet *surfaceSet, int scale)
	{
		SDL_RWops *rw = FileMap::getRWops(path);
		if (!rw)
		{
			return 0;
		}
		unsigned char head[24];
		if (SDL_RWread(rw, head, 1, sizeof(head)) != sizeof(head) || memcmp(head, PACK_MAGIC, 8) != 0)
		{
			SDL_RWclose(rw);
			Log(LOG_WARNING) << "HD sprites: " << path << " is not a pack file - ignored";
			return 0;
		}
		const Uint32 packScale = readU32(head + 8), baseW = readU32(head + 12), baseH = readU32(head + 16), count = readU32(head + 20);
		if (packScale < 1 || packScale > 16 || baseW == 0 || baseH == 0 || count > 1000000)
		{
			SDL_RWclose(rw);
			Log(LOG_WARNING) << "HD sprites: " << path << " has a bad header - ignored";
			return 0;
		}
		const int frameW = surfaceSet->getWidth(), frameH = surfaceSet->getHeight();
		if ((int)baseW * scale != frameW || (int)baseH * scale != frameH)
		{
			SDL_RWclose(rw);
			Log(LOG_WARNING) << "HD sprites: " << path << " holds frames of " << baseW << "x" << baseH
				<< ", the set's frames are " << frameW / scale << "x" << frameH / scale << " - ignored";
			return 0;
		}
		std::vector<unsigned char> table((size_t)count * 12);
		if ((long long)SDL_RWread(rw, table.data(), 1, table.size()) != (long long)table.size())
		{
			SDL_RWclose(rw);
			Log(LOG_WARNING) << "HD sprites: " << path << " is cut short - ignored";
			return 0;
		}
		SDL_RWclose(rw);
		int registered = 0;
		for (Uint32 i = 0; i < count; ++i)
		{
			const unsigned char *e = &table[(size_t)i * 12];
			const Uint32 index = readU32(e), offset = readU32(e + 4), size = readU32(e + 8);
			if (index >= surfaceSet->getTotalFrames() || size == 0)
			{
				continue;
			}
			Surface *frame = surfaceSet->getFrame((int)index);
			if (!frame)
			{
				continue;
			}
			setLazy(frame->getBuffer(), path, offset, size, frame->getWidth(), frame->getHeight());
			++registered;
		}
		if ((int)packScale != scale)
		{
			Log(LOG_INFO) << "HD sprites: " << path << " is a " << packScale << "x pack shown at " << scale << "x (resampled)";
		}
		return registered;
	}

	/**
	 * Reads `hd/<setName>/color.txt`: which frames of the set the pack painted in
	 * their own colours. "colorAuthority: pack" marks them, "frames: 2 10 18-20"
	 * names them (no list - the whole set). The old upscales have no such file:
	 * their sheet palette is off the battle one (R-030), they keep the ramp's hue.
	 */
	void readColour(const std::string &setName, SurfaceSet *surfaceSet)
	{
		const std::string path = artPath(setName + "/color.txt");
		if (!FileMap::fileExists(path))
		{
			return;
		}
		std::unique_ptr<std::istream> in = FileMap::getIStream(path);
		if (!in)
		{
			return;
		}
		bool pack = false, listed = false;
		std::vector<int> frames;
		std::string line;
		while (std::getline(*in, line))
		{
			if (line.size() >= 3 && (unsigned char)line[0] == 0xEF && (unsigned char)line[1] == 0xBB && (unsigned char)line[2] == 0xBF)
			{
				line.erase(0, 3);
			}
			line.erase(std::find_if(line.rbegin(), line.rend(), [](unsigned char c) { return !std::isspace(c); }).base(), line.end());
			const size_t start = line.find_first_not_of(" \t");
			if (start == std::string::npos || line[start] == '#')
			{
				continue;
			}
			line.erase(0, start);
			if (line == "colorAuthority: pack")
			{
				pack = true;
			}
			else if (line.compare(0, 7, "frames:") == 0)
			{
				listed = true;
				std::istringstream words(line.substr(7));
				std::string word;
				while (words >> word)
				{
					char *end = nullptr;
					const long from = std::strtol(word.c_str(), &end, 10);
					long to = from;
					if (end && *end == '-')
					{
						to = std::strtol(end + 1, &end, 10);
					}
					if (!end || *end != '\0' || from < 0 || to < from || to - from > 100000)
					{
						Log(LOG_WARNING) << "HD sprites: " << path << ": '" << word << "' is not a frame - ignored";
						continue;
					}
					for (long i = from; i <= to; ++i)
					{
						frames.push_back((int)i);
					}
				}
			}
			else
			{
				Log(LOG_WARNING) << "HD sprites: " << path << ": '" << line << "' is not understood - ignored";
			}
		}
		if (!pack)
		{
			return;
		}
		if (!listed)
		{
			for (int i = 0; i < (int)surfaceSet->getTotalFrames(); ++i)
			{
				frames.push_back(i);
			}
		}
		beforeChange();
		int marked = 0;
		for (int index : frames)
		{
			Surface *frame = index < (int)surfaceSet->getTotalFrames() ? surfaceSet->getFrame(index) : nullptr;
			auto found = frame ? registry.find(frame->getBuffer()) : registry.end();
			if (found == registry.end())
			{
				continue;
			}
			found->second.ownColour = true;
			found->second.frame.ownColour = true;
			auto alt = variants.find(frame->getBuffer());
			if (alt != variants.end())
			{
				for (Entry &entry : alt->second)
				{
					entry.ownColour = true;
					entry.frame.ownColour = true;
				}
			}
			++marked;
		}
		++registryGeneration;
		Log(LOG_INFO) << "HD sprites: " << setName << ": " << marked << " frame(s) keep their own colours (color.txt)";
	}

	/// A whole decimal number (nothing else in the string).
	bool parseWhole(const std::string &text, int &value)
	{
		if (text.empty() || text.size() > 6 || !std::all_of(text.begin(), text.end(), [](char c) { return c >= '0' && c <= '9'; }))
		{
			return false;
		}
		value = std::atoi(text.c_str());
		return true;
	}

	/// The size of the pictures in a pack file (from its header), or false.
	bool packPictureSize(const std::string &path, int &width, int &height)
	{
		SDL_RWops *rw = FileMap::getRWops(path);
		if (!rw)
		{
			return false;
		}
		unsigned char head[24];
		const bool ok = SDL_RWread(rw, head, 1, sizeof(head)) == sizeof(head) && memcmp(head, PACK_MAGIC, 8) == 0;
		SDL_RWclose(rw);
		if (!ok)
		{
			return false;
		}
		width = (int)(readU32(head + 8) * readU32(head + 12));
		height = (int)(readU32(head + 8) * readU32(head + 16));
		return width > 0 && height > 0;
	}

	/**
	 * SCC wall addressing (option oxceHdTerrainAddress; docs/research/map-addressing-scc-contract-2026-10-06.md):
	 * reads `hd/<setName>/address.txt` - the version of the formula and the pairs "<index>:<slot>:<n>" - and
	 * registers the pictures `<index>.<slot><N>.png`, N = 1 .. n - 1. An unknown version turns the whole set
	 * off, a bad pair only itself; a missing or ill-sized picture is drawn as the frame itself (its cell
	 * alone - the numbers of the others do not move). Pictures no pair asks for are not used.
	 * @param mainSize The size of each `<index>.png` of the folder (the pictures of pack.hdp are read from its header).
	 */
	void registerWalls(const std::string &setName, SurfaceSet *surfaceSet, int scale, const std::vector<std::string> &files,
		const std::unordered_map<int, std::pair<int, int>> &mainSize)
	{
		// the wall pictures of the folder, to name those no pair uses
		std::vector<std::string> wallFiles;
		for (const std::string &file : files)
		{
			const size_t dot = file.find('.');
			if (dot != std::string::npos && (file.compare(dot, 6, ".north") == 0 || file.compare(dot, 5, ".west") == 0))
			{
				wallFiles.push_back(file);
			}
		}
		std::vector<std::string> used;
		const std::string path = artPath(setName + "/" + addressFile);
		std::unique_ptr<std::istream> in;
		if (FileMap::fileExists(path))
		{
			in = FileMap::getIStream(path);
		}
		std::string version = "none";
		std::vector<std::string> elements;
		if (in)
		{
			std::string line;
			while (std::getline(*in, line))
			{
				if (!line.empty() && line.back() == '\r')
				{
					line.pop_back();
				}
				const size_t first = line.find_first_not_of(" \t");
				if (first == std::string::npos || line[first] == '#')
				{
					continue;
				}
				const size_t colon = line.find(':');
				if (colon == std::string::npos)
				{
					continue;
				}
				std::string key = line.substr(first, colon - first);
				key.erase(key.find_last_not_of(" \t") + 1);
				std::istringstream value(line.substr(colon + 1));
				if (key == "version")
				{
					value >> version;
				}
				else if (key == "frames")
				{
					std::string element;
					while (value >> element)
					{
						elements.push_back(element);
					}
				}
			}
		}
		struct Pair { int frame = -1, part = 0, n = 0; std::string token, bad; };
		std::vector<Pair> pairs;
		if (!in)
		{
			// no declaration: nothing is addressed
		}
		else if (version != "1")
		{
			Log(LOG_WARNING) << "HD address: " << setName << " version " << version << " unknown, off";
		}
		else
		{
			for (const std::string &token : elements)
			{
				Pair pair;
				pair.token = token;
				const size_t a = token.find(':'), b = a == std::string::npos ? a : token.find(':', a + 1);
				int n = 0;
				if (b == std::string::npos || token.find(':', b + 1) != std::string::npos
					|| !parseWhole(token.substr(0, a), pair.frame) || !parseWhole(token.substr(b + 1), n))
				{
					pair.bad = "syntax";
				}
				else if (pair.frame >= (int)surfaceSet->getTotalFrames() || !surfaceSet->getFrame(pair.frame))
				{
					pair.bad = "frame";
				}
				else
				{
					const std::string slot = token.substr(a + 1, b - a - 1);
					pair.part = slot == "west" ? WALL_WEST : slot == "north" ? WALL_NORTH : 0;
					pair.n = n;
					if (!pair.part)
					{
						pair.bad = "slot";
					}
				}
				pairs.push_back(pair);
			}
			// a pair given twice: which n is meant is unknown - both go
			for (Pair &pair : pairs)
			{
				if (pair.bad.empty() && std::count_if(pairs.begin(), pairs.end(),
					[&pair](const Pair &other) { return other.part && other.frame == pair.frame && other.part == pair.part; }) > 1)
				{
					pair.bad = "duplicate";
				}
			}
			for (Pair &pair : pairs)
			{
				if (pair.bad.empty() && pair.n < 4)
				{
					pair.bad = "n<4";
				}
				else if (pair.bad.empty() && pair.n > 16)
				{
					pair.bad = "n>16";
				}
			}
		}
		int on = 0, off = 0;
		if (!pairs.empty())
		{
			beforeChange();
		}
		for (Pair &pair : pairs)
		{
			Surface *frame = pair.bad.empty() ? surfaceSet->getFrame(pair.frame) : nullptr;
			auto main = frame ? registry.find(frame->getBuffer()) : registry.end();
			if (pair.bad.empty() && main == registry.end())
			{
				pair.bad = "main";
			}
			if (!pair.bad.empty())
			{
				Log(LOG_WARNING) << "HD address: " << setName << " " << pair.token << " off: " << pair.bad;
				++off;
				continue;
			}
			// the size of the frame's own picture: every variant must have it
			int mainW = 0, mainH = 0;
			auto size = mainSize.find(pair.frame);
			if (size != mainSize.end())
			{
				mainW = size->second.first;
				mainH = size->second.second;
			}
			else if (!packPictureSize(main->second.path, mainW, mainH))
			{
				mainW = mainH = -1;
			}
			const std::string slot = pair.part == WALL_WEST ? "west" : "north";
			const void *key = frame->getBuffer();
			dropWalls(key);
			WallSlots &wall = walls[pair.part - 1][key];
			wall.n = pair.n;
			wall.label = setName + " " + std::to_string(pair.frame) + ":" + slot;
			wall.slots.resize(pair.n - 1);
			wall.warned.assign(pair.n - 1, 0);
			const int fw = frame->getWidth(), fh = frame->getHeight();
			const int bw = fw / scale, bh = fh / scale;
			for (int v = 1; v < pair.n; ++v)
			{
				const std::string file = std::to_string(pair.frame) + "." + slot + std::to_string(v) + ".png";
				if (std::find(files.begin(), files.end(), file) == files.end())
				{
					Log(LOG_WARNING) << "HD address: " << wall.label << " variant " << v << " missing";
					continue;
				}
				used.push_back(file);
				const std::string picture = artPath(setName + "/" + file);
				int width = 0, height = 0;
				if (!pngSize(picture, width, height))
				{
					Log(LOG_WARNING) << "HD address: " << wall.label << " variant " << v << " decode";
					continue;
				}
				const bool fits = (width == fw && height == fh) || (bw > 0 && bh > 0 && width % bw == 0 && height % bh == 0 && width / bw == height / bh);
				if (!fits || width != mainW || height != mainH)
				{
					Log(LOG_WARNING) << "HD address: " << wall.label << " variant " << v << " size";
					continue;
				}
				Entry &entry = wall.slots[v - 1];
				entry.path = picture;
				entry.width = fw;
				entry.height = fh;
				entry.key = key;
			}
			++on;
		}
		for (const std::string &file : wallFiles)
		{
			if (std::find(used.begin(), used.end(), file) == used.end())
			{
				Log(LOG_WARNING) << "HD address: " << setName << " " << file << " unused (no pair of " << addressFile << " asks for it)";
			}
		}
		if (!pairs.empty())
		{
			++registryGeneration;
			++wallsGeneration;
		}
		if (in)
		{
			Log(LOG_INFO) << "HD address: " << setName << " " << on << " pair(s) on, " << off << " off";
		}
	}
}

/**
 * Registers the HD pack of a set: `hd/<setName>/pack.hdp` and every
 * `hd/<setName>/<index>.png` in the virtual file system. The pictures
 * themselves are read when their frames are first drawn.
 */
int loadPack(const std::string &setName, SurfaceSet *surfaceSet, int scale)
{
	if (!surfaceSet || scale < 1)
	{
		return 0;
	}
	const std::vector<std::string> files = artFolder(setName);
	if (files.empty())
	{
		return 0;
	}
	int loaded = 0;
	if (std::find(files.begin(), files.end(), std::string("pack.hdp")) != files.end())
	{
		loaded += registerPackFile(artPath(setName + "/pack.hdp"), surfaceSet, scale);
	}
	std::unordered_map<int, std::pair<int, int>> mainSize; // the size of each <index>.png (address.txt)
	for (const std::string &file : files)
	{
		// "<index>.png", or "<index>.v<n>.png" (variant n of the frame)
		const size_t dot = file.find('.');
		if (dot == std::string::npos || dot == 0)
		{
			continue;
		}
		int variant = 0;
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
			if (number.empty() || !vend || *vend != '\0' || v < 1 || v > MAX_VARIANTS)
			{
				continue;
			}
			variant = (int)v;
		}
		char *end = nullptr;
		const long index = std::strtol(file.c_str(), &end, 10);
		if (!end || *end != '.' || index < 0 || (size_t)index >= surfaceSet->getTotalFrames())
		{
			continue;
		}
		Surface *frame = surfaceSet->getFrame((int)index);
		if (!frame)
		{
			continue;
		}
		const std::string path = artPath(setName + "/" + file);
		int width = 0, height = 0;
		if (!pngSize(path, width, height))
		{
			continue;
		}
		const int fw = frame->getWidth(), fh = frame->getHeight();
		const int bw = fw / scale, bh = fh / scale;
		const bool fits = (width == fw && height == fh) || (bw > 0 && bh > 0 && width % bw == 0 && height % bh == 0 && width / bw == height / bh);
		if (!fits)
		{
			Log(LOG_WARNING) << "HD sprite " << path << " is " << width << "x" << height
				<< ", the frame it replaces is " << fw << "x" << fh << " - ignored";
			continue;
		}
		if (variant > 0)
		{
			setVariantLazy(frame->getBuffer(), variant, path, 0, 0, fw, fh);
		}
		else
		{
			setLazy(frame->getBuffer(), path, 0, 0, fw, fh);
			mainSize[(int)index] = std::make_pair(width, height);
			++loaded;
		}
	}
	if (Options::oxceHdTerrainAddress && loaded > 0)
	{
		registerWalls(setName, surfaceSet, scale, files, mainSize);
	}
	if (loaded > 0 && std::find(files.begin(), files.end(), std::string("color.txt")) != files.end())
	{
		readColour(setName, surfaceSet);
	}
	return loaded;
}

/**
 * Round HD frames for a set of tiny sprites, where no pack covers them.
 *
 * Why the engine draws these itself instead of a mod shipping pictures: the bullet
 * tracer is 35 stamps of one 3x3 sprite, a voxel apart, and every mod has its own
 * sheet of them (X-Piratez has 54 tracers, vanilla 11, and frame 7 means a different
 * bullet in each). Scaled by nearest the shot becomes a staircase of hard squares,
 * and smoothing a single 3x3 frame cannot fix a staircase - what fixes it is a rim
 * that fades out, because then the stamps overlap into one beam.
 *
 * The dot keeps the colours of the frame it replaces: the mean of its lit pixels for
 * the body and the brightest of them for the middle, so nothing is invented. Its
 * radius follows how much of the frame was lit - the head of a tracer fills all nine
 * pixels and stays fat, its tail is one pixel and stays thin - and the fuller the
 * frame, the hotter its middle, which is what makes the head read as the bullet.
 * @param classic Set at base resolution: the colours and the palette are read from it.
 * @param scaled The k-times set the game draws; its frames are the keys of the registry.
 * @param scale k.
 * @return How many frames were made.
 */
int makeDots(const std::string &setName, const SurfaceSet *classic, SurfaceSet *scaled, int scale, const std::vector<const DotStyle*> *styles)
{
	if (!classic || !scaled || scale < 2)
	{
		return 0;
	}
	const int bw = classic->getWidth(), bh = classic->getHeight();
	// a sprite this small has no shape to keep - it is a dot, and it is drawn as a dot
	if (bw < 2 || bh < 2 || bw > MAX_DOT || bh > MAX_DOT)
	{
		return 0;
	}
	const int w = bw * scale, h = bh * scale;
	const double half = std::min(bw, bh) / 2.0;
	int made = 0, kept = 0, blank = 0, noPalette = 0, styled = 0, leftClassic = 0;
	// a styled tracer, read as a whole: its brightest pixel and its most vivid colour at full brightness
	struct Row { int maxLum = 1; double vivid[3] = { 255, 255, 255 }; };
	std::unordered_map<const DotStyle*, Row> rows;
	auto rowOf = [&](const DotStyle *st) -> const Row&
	{
		auto found = rows.find(st);
		if (found != rows.end())
		{
			return found->second;
		}
		Row &row = rows[st];
		int maxV = 0;
		for (int pass = 0; pass < 2; ++pass)
		{
			double best = -1.0;
			for (int f = st->first; f < st->first + 35; ++f)
			{
				const Surface *s = classic->getFrame(f);
				const SDL_Color *p = s ? s->getPalette() : nullptr;
				if (!p) continue;
				for (int y = 0; y < bh; ++y)
				{
					for (int x = 0; x < bw; ++x)
					{
						const Uint8 index = s->getPixel(x, y);
						if (!index) continue;
						const SDL_Color &c = p[index];
						const int v = std::max({ c.r, c.g, c.b });
						if (pass == 0)
						{
							maxV = std::max(maxV, v);
							row.maxLum = std::max(row.maxLum, c.r * 2 + c.g * 5 + c.b);
						}
						else if (v * 10 >= maxV * 6 && v > 0)
						{
							const double score = (v - std::min({ c.r, c.g, c.b })) / (double)v * v;
							if (score > best)
							{
								best = score;
								row.vivid[0] = c.r * 255.0 / v; row.vivid[1] = c.g * 255.0 / v; row.vivid[2] = c.b * 255.0 / v;
							}
						}
					}
				}
			}
		}
		return row;
	};
	for (size_t i = 0; i < scaled->getTotalFrames(); ++i)
	{
		const DotStyle *style = styles && i < styles->size() ? (*styles)[i] : nullptr;
		if (style && style->classic)
		{
			++leftClassic;
			continue;
		}
		const Surface *src = classic->getFrame((int)i);
		Surface *dst = scaled->getFrame((int)i);
		if (!src || !dst || dst->getWidth() != w || dst->getHeight() != h)
		{
			++blank;
			continue;
		}
		if (registered(dst->getBuffer()))
		{
			++kept;
			continue;
		}
		const SDL_Color *pal = src->getPalette();
		if (!pal)
		{
			++noPalette;
			continue;
		}
		int lit = 0, litEven = 0, peak = 0, peakLum = -1, sumR = 0, sumG = 0, sumB = 0, sumLum = 0;
		for (int y = 0; y < bh; ++y)
		{
			for (int x = 0; x < bw; ++x)
			{
				const Uint8 index = src->getPixel(x, y);
				if (!index)
				{
					continue;
				}
				const SDL_Color &c = pal[index];
				++lit;
				litEven += ((x + y) & 1) ? 0 : 1;
				sumR += c.r; sumG += c.g; sumB += c.b;
				const int lum = c.r * 2 + c.g * 5 + c.b;
				sumLum += lum;
				if (lum > peakLum)
				{
					peakLum = lum;
					peak = index;
				}
			}
		}
		if (!lit)
		{
			++blank;
			continue;
		}
		const double fill = lit / (double)(bw * bh);
		// half the cells lit and all of one parity: that is the classic way of drawing
		// half-transparency (the smoke of a vanilla bullet), so it becomes a puff over the
		// whole frame at half alpha, not a solid dot of half the pixels
		const bool dithered = lit * 2 >= bw * bh && (litEven == 0 || litEven == lit);
		const double cover = dithered ? 1.0 : fill;
		double fade = dithered ? 0.5 : 1.0;
		double radius = (0.37 + 0.63 * std::sqrt(cover)) * half;
		double body[3] = { sumR / (double)lit, sumG / (double)lit, sumB / (double)lit };
		const double white = 0.35 * fill;
		double core[3] = {
			pal[peak].r + (255.0 - pal[peak].r) * white,
			pal[peak].g + (255.0 - pal[peak].g) * white,
			pal[peak].b + (255.0 - pal[peak].b) * white };
		if (style)
		{
			// the projectile is a frame lit over half and bright for its tracer; the rest is its trail
			const Row &row = rowOf(style);
			const double rel = sumLum / (double)lit / row.maxLum;
			const bool projectile = !dithered && lit * 2 >= bw * bh && rel >= 0.55;
			radius *= style->width;
			const double *to = nullptr;
			double tint[3] = { (double)style->headR, (double)style->headG, (double)style->headB };
			if (projectile && style->headR >= 0)
			{
				to = tint;
			}
			else if (projectile && style->bright)
			{
				to = row.vivid;
			}
			if (to)
			{
				for (int c = 0; c < 3; ++c)
				{
					body[c] = to[c];
					core[c] = to[c] + (255.0 - to[c]) * 0.55;
				}
			}
			else if (!projectile && style->fade < 1.0)
			{
				// a dark trail drawn opaque reads as the smoke of a rocket: it glows faintly instead
				for (int c = 0; c < 3; ++c)
				{
					body[c] = row.vivid[c];
					core[c] = row.vivid[c] + (255.0 - row.vivid[c]) * 0.3;
				}
				fade *= style->fade * std::min(1.0, rel);
			}
			++styled;
		}
		// a dot thinner than the step between stamps: a denser rim, or the beam breaks into beads
		const double rim = 1.6 * (style ? std::min(1.0, style->width) : 1.0);
		HdFrame frame;
		frame.width = w;
		frame.height = h;
		frame.generated = true;
		frame.pixels.assign((size_t)w * h, 0);
		for (int y = 0; y < h; ++y)
		{
			for (int x = 0; x < w; ++x)
			{
				const double dx = (x + 0.5) / scale - bw / 2.0;
				const double dy = (y + 0.5) / scale - bh / 2.0;
				const double t = std::sqrt(dx * dx + dy * dy) / radius;
				const double fall = 1.0 - t * t;
				if (fall <= 0.0)
				{
					continue;
				}
				const double hot = std::max(0.0, 1.0 - (t / 0.55) * (t / 0.55));
				const Uint32 a = (Uint32)(std::pow(fall, rim) * 255.0 * fade + 0.5);
				const Uint32 r = (Uint32)(body[0] + (core[0] - body[0]) * hot + 0.5);
				const Uint32 g = (Uint32)(body[1] + (core[1] - body[1]) * hot + 0.5);
				const Uint32 b = (Uint32)(body[2] + (core[2] - body[2]) * hot + 0.5);
				frame.pixels[(size_t)y * w + x] = (a << 24) | (r << 16) | (g << 8) | b;
			}
		}
		set(dst->getBuffer(), std::move(frame));
		++made;
	}
	// said out loud even when nothing was made: a set of this size is meant to become dots, so
	// "0 made" is the answer to "why does the tracer still look the way it did"
	Log(LOG_INFO) << "HD render: round dots for " << setName << " (" << bw << "x" << bh
		<< " frames, k=" << scale << "): " << made << " made, " << kept << " left to a pack, "
		<< blank << " empty, " << noPalette << " without a palette; " << styled << " styled, "
		<< leftClassic << " left classic by hd/FX/weapons.txt";
	return made;
}

/**
 * Writes a palette set as an 8-bit PNG sheet plus a text file with its
 * layout, for the art tools.
 */
int exportSet(const SurfaceSet *surfaceSet, const SDL_Color *palette, const std::string &pngPath, int cols)
{
	if (!surfaceSet || !palette || cols < 1)
	{
		return 0;
	}
	const int fw = surfaceSet->getWidth(), fh = surfaceSet->getHeight();
	const int total = (int)surfaceSet->getTotalFrames();
	if (fw <= 0 || fh <= 0 || total <= 0)
	{
		return 0;
	}
	const int rows = (total + cols - 1) / cols;
	const unsigned width = (unsigned)(cols * fw), height = (unsigned)(rows * fh);
	std::vector<unsigned char> sheet((size_t)width * height, 0);
	int written = 0;
	for (int i = 0; i < total; ++i)
	{
		const Surface *frame = surfaceSet->getFrame(i);
		if (!frame || frame->getWidth() != fw || frame->getHeight() != fh)
		{
			continue;
		}
		const int ox = (i % cols) * fw, oy = (i / cols) * fh;
		bool any = false;
		for (int y = 0; y < fh; ++y)
		{
			const Uint8 *src = frame->getRaw(0, y);
			unsigned char *dst = &sheet[(size_t)(oy + y) * width + ox];
			memcpy(dst, src, fw);
			for (int x = 0; x < fw && !any; ++x)
			{
				any = src[x] != 0;
			}
		}
		if (any)
		{
			++written;
		}
	}
	if (written == 0)
	{
		return 0;
	}
	lodepng::State state;
	state.info_png.color.colortype = LCT_PALETTE;
	state.info_png.color.bitdepth = 8;
	state.info_raw.colortype = LCT_PALETTE;
	state.info_raw.bitdepth = 8;
	for (int i = 0; i < 256; ++i)
	{
		lodepng_palette_add(&state.info_png.color, palette[i].r, palette[i].g, palette[i].b, i == 0 ? 0 : 255);
		lodepng_palette_add(&state.info_raw, palette[i].r, palette[i].g, palette[i].b, i == 0 ? 0 : 255);
	}
	state.encoder.auto_convert = 0;
	std::vector<unsigned char> png;
	const unsigned error = lodepng::encode(png, sheet, width, height, state);
	if (error)
	{
		Log(LOG_ERROR) << "HD export " << pngPath << ": " << lodepng_error_text(error);
		return 0;
	}
	if (!CrossPlatform::writeFile(pngPath, png))
	{
		Log(LOG_ERROR) << "HD export: cannot write " << pngPath;
		return 0;
	}
	std::ostringstream info;
	info << "frames " << total << "\n" << "width " << fw << "\n" << "height " << fh << "\n" << "cols " << cols << "\n";
	CrossPlatform::writeFile(pngPath + ".txt", info.str());
	return written;
}

}

}
