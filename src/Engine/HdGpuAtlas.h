#pragma once
// The frames of the HD layer on the video card in one texture array (HdGpuCanvas, HdGpuWorld): private to those files.
#ifndef __NO_OPENGL
#include <algorithm>
#include <unordered_map>
#include <vector>
#include "HdGpuGl.h"
namespace OpenXcom
{
namespace hdgl
{

struct Place
{
	int layer, x, y, w, h;
	Uint64 hash;
	/// The last flush that used it.
	Uint32 used;
};

/**
 * The frames the commands read, in the layers of one texture array: shelves in every layer; when nothing fits,
 * the frames no recent flush used give their places to new frames of the same size (the shaded and lit copies
 * come and go in a few sizes), then a whole layer is emptied (the one used by the oldest flush, never one this
 * flush uses), and the array is made bigger (everything uploaded anew) only when every layer is in use.
 */
struct Atlas
{
	struct Shelf { int y, h, x; };
	struct Layer
	{
		std::vector<Shelf> shelves;
		int top = 0;
		Uint32 used = 0;
		std::vector<Uint64> ids;
	};
	struct Slot { int layer, x, y; };
	enum Result { PLACED, GROW, FULL };
	GLuint texture = 0;
	int page = 0, maxLayers = 0;
	std::vector<Layer> layers;
	std::unordered_map<Uint64, Place> places;
	/// The places of frames gone, by size (w << 16 | h).
	std::unordered_map<Uint32, std::vector<Slot>> freeSlots;
	Uint64 nextId = 1;
	/// The number of the flush being prepared.
	Uint32 clock = 0;
	/// The flush of the last sweep of each depth (see sweep).
	Uint32 sweptOld = 0, sweptAll = 0;
	/// Flushes a frame stays after its last use before a sweep gives its place away (about 2 s of a moving view).
	static const Uint32 KEEP = 120;

	bool create(int count)
	{
		if (!texture)
		{
			glGenTextures(1, &texture);
		}
		while (glGetError() != GL_NO_ERROR) {}
		gl.ActiveTexture(GL_TEXTURE0);
		glBindTexture(GL_TEXTURE_2D_ARRAY, texture);
		gl.TexImage3D(GL_TEXTURE_2D_ARRAY, 0, GL_RGBA8, page, page, count, 0, GL_BGRA, GL_UNSIGNED_BYTE, nullptr);
		glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
		glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
		glBindTexture(GL_TEXTURE_2D_ARRAY, 0);
		places.clear();
		freeSlots.clear();
		layers.assign(count, Layer());
		if (glGetError() != GL_NO_ERROR)
		{
			layers.clear();
			return false;
		}
		return true;
	}
	/// Every layer emptied (the array stays).
	void empty()
	{
		places.clear();
		freeSlots.clear();
		layers.assign(layers.size(), Layer());
	}
	bool grow()
	{
		const int count = (int)layers.size();
		return count < maxLayers && create(std::min(maxLayers, count * 2));
	}
	bool fit(Layer &layer, int w, int h, bool tight, int &x, int &y)
	{
		for (Shelf &s : layer.shelves)
		{
			if (h <= s.h && s.x + w <= page && (!tight || s.h <= h + h / 2 + 8))
			{
				x = s.x;
				y = s.y;
				s.x += w;
				return true;
			}
		}
		if (layer.top + h > page)
		{
			return false;
		}
		layer.shelves.push_back(Shelf{ layer.top, h, w });
		x = 0;
		y = layer.top;
		layer.top += h;
		return true;
	}
	/// The place of a frame of this size given up before.
	bool reuse(int w, int h, int &at, int &x, int &y)
	{
		auto it = freeSlots.find(((Uint32)w << 16) | (Uint32)h);
		if (it == freeSlots.end() || it->second.empty())
		{
			return false;
		}
		const Slot s = it->second.back();
		it->second.pop_back();
		at = s.layer;
		x = s.x;
		y = s.y;
		return true;
	}
	/// The frames not used by the last `keep` flushes give up their places (once a flush for each depth).
	void sweep(Uint32 keep)
	{
		Uint32 &swept = keep > 1 ? sweptOld : sweptAll;
		if (swept == clock)
		{
			return;
		}
		swept = clock;
		for (Layer &layer : layers)
		{
			layer.ids.clear();
		}
		for (auto it = places.begin(); it != places.end();)
		{
			const Place &pl = it->second;
			if (clock - pl.used >= keep)
			{
				freeSlots[((Uint32)pl.w << 16) | (Uint32)pl.h].push_back(Slot{ pl.layer, pl.x, pl.y });
				it = places.erase(it);
			}
			else
			{
				layers[pl.layer].ids.push_back(it->first);
				++it;
			}
		}
	}
	/// A frame placed by a flush that did not go to the card: its place goes back.
	void drop(Uint64 id)
	{
		auto it = places.find(id);
		if (it != places.end())
		{
			const Place &pl = it->second;
			freeSlots[((Uint32)pl.w << 16) | (Uint32)pl.h].push_back(Slot{ pl.layer, pl.x, pl.y });
			places.erase(it);
		}
	}
	/// A place for a w x h frame under a new number (w, h <= page).
	Result place(int w, int h, Uint64 &id)
	{
		int at = -1, x = 0, y = 0;
		if (!reuse(w, h, at, x, y))
		{
			for (int pass = 0; pass < 2 && at < 0; ++pass)
			{
				for (int i = 0; i < (int)layers.size(); ++i)
				{
					if (fit(layers[i], w, h, pass == 0, x, y))
					{
						at = i;
						break;
					}
				}
			}
		}
		if (at < 0)
		{
			sweep(KEEP);
			if (!reuse(w, h, at, x, y))
			{
				sweep(1);
				reuse(w, h, at, x, y);
			}
		}
		if (at < 0)
		{
			int oldest = -1;
			for (int i = 0; i < (int)layers.size(); ++i)
			{
				if (layers[i].used != clock && (oldest < 0 || layers[i].used < layers[oldest].used))
				{
					oldest = i;
				}
			}
			if (oldest < 0)
			{
				return (int)layers.size() < maxLayers ? GROW : FULL;
			}
			for (Uint64 gone : layers[oldest].ids)
			{
				auto it = places.find(gone);
				if (it != places.end() && it->second.layer == oldest)
				{
					places.erase(it);
				}
			}
			for (auto &sized : freeSlots)
			{
				std::vector<Slot> &slots = sized.second;
				slots.erase(std::remove_if(slots.begin(), slots.end(), [&](const Slot &s) { return s.layer == oldest; }), slots.end());
			}
			layers[oldest] = Layer();
			fit(layers[oldest], w, h, false, x, y);
			at = oldest;
		}
		id = nextId++;
		places[id] = Place{ at, x, y, w, h, 0, clock };
		layers[at].ids.push_back(id);
		layers[at].used = clock;
		return PLACED;
	}
	/// The place of a frame uploaded before, or nullptr (never uploaded, or emptied since).
	Place *find(Uint64 id)
	{
		if (!id)
		{
			return nullptr;
		}
		auto it = places.find(id);
		if (it == places.end())
		{
			return nullptr;
		}
		layers[it->second.layer].used = clock;
		it->second.used = clock;
		return &it->second;
	}
	void release()
	{
		if (texture)
		{
			glDeleteTextures(1, &texture);
		}
		texture = 0;
		layers.clear();
		places.clear();
		freeSlots.clear();
	}
};
}
}
#endif
