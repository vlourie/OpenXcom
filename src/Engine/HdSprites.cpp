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
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <cmath>
#include <sstream>
#include <unordered_map>
#include "CrossPlatform.h"
#include "FileMap.h"
#include "Logger.h"
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
	};
	std::unordered_map<const void*, Entry> registry;
	/// the variants of a registered frame: slot n - 1 holds variant n (an empty path = no such variant)
	std::unordered_map<const void*, std::vector<Entry>> variants;
	const int MAX_VARIANTS = 15;
	unsigned registryGeneration = 1;
	size_t budget = (size_t)384 << 20;
	size_t loadedTotal = 0; ///< bytes of the lazily loaded frames in memory
	size_t clock = 0;

	size_t bytesOf(const HdFrame &frame)
	{
		return frame.pixels.size() * sizeof(Uint32) + (frame.rows.size() + frame.solid.size()) * sizeof(HdFrame::Span);
	}

	/// Reads a lazy entry's picture from its file.
	void load(Entry &entry)
	{
		SDL_RWops *rw = FileMap::fileExists(entry.path) ? FileMap::getRWops(entry.path) : nullptr;
		if (!rw)
		{
			entry.failed = true;
			Log(LOG_WARNING) << "HD sprite: cannot open " << entry.path;
			return;
		}
		std::vector<unsigned char> data;
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
		HdFrame read;
		if (!ok || !decodePng(data.data(), data.size(), read))
		{
			entry.failed = true;
			Log(LOG_WARNING) << "HD sprite: cannot read " << entry.path << " at " << entry.offset;
			return;
		}
		if (read.width != entry.width || read.height != entry.height)
		{
			resample(read, entry.width, entry.height, entry.frame);
		}
		else
		{
			entry.frame = std::move(read);
		}
		entry.frame.generated = false;
		entry.frame.buildSpans();
		loadedTotal += bytesOf(entry.frame);
	}
}

void set(const void *key, HdFrame &&frame)
{
	if (!key)
	{
		return;
	}
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
}

void setVariantLazy(const void *key, int variant, const std::string &path, Uint32 offset, Uint32 size, int width, int height)
{
	if (!key || variant < 1 || variant > MAX_VARIANTS || path.empty() || width <= 0 || height <= 0)
	{
		return;
	}
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

void remove(const void *key)
{
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
}

void removeSet(const SurfaceSet *surfaceSet)
{
	if (!surfaceSet || (registry.empty() && variants.empty()))
	{
		return;
	}
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
		}
	}
	++registryGeneration;
}

void clear()
{
	registry.clear();
	variants.clear();
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
	return n;
}

size_t loadedBytes()
{
	return loadedTotal;
}

void setBudget(size_t bytes)
{
	budget = bytes;
}

/**
 * Drops the lazily read frames found longest ago until the loaded ones are
 * a quarter under the budget (so this runs rarely, not every frame).
 */
void trim()
{
	// OXCE_HD_PACK_BUDGET=<MB> overrides the budget (tests of the dropping)
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
	if (loadedTotal <= budget)
	{
		return;
	}
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
	const std::string folder = "hd/" + setName;
	const FileMap::NameSet &files = FileMap::getVFolderContents(folder);
	if (files.empty())
	{
		return 0;
	}
	int loaded = 0;
	if (files.find("pack.hdp") != files.end())
	{
		loaded += registerPackFile(folder + "/pack.hdp", surfaceSet, scale);
	}
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
		const std::string path = folder + "/" + file;
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
			++loaded;
		}
	}
	return loaded;
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
