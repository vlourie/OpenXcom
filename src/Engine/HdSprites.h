#pragma once
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
#include <string>
#include <vector>
#include <SDL.h>

namespace OpenXcom
{

class SurfaceSet;

/**
 * A true-color sprite frame: what the HD renderer draws instead of a palette
 * frame when a mod ships one (or when the engine smoothed one itself).
 * Pixels are 0xAARRGGBB with straight (not premultiplied) alpha; the frame
 * is exactly as big as the palette frame it replaces (k times the original).
 */
struct HdFrame
{
	/// Non-transparent extent [begin, end) of one row.
	struct Span { Uint16 begin, end; };

	int width = 0, height = 0;
	std::vector<Uint32> pixels;
	std::vector<Span> rows;
	/// The longest fully opaque run of every row (drawn as a plain copy).
	std::vector<Span> solid;
	/// Made by the engine (smooth fallback) rather than loaded from a pack.
	bool generated = false;

	/// Pointer to a row of pixels.
	const Uint32 *row(int y) const { return pixels.data() + (size_t)y * width; }
	/// Recomputes the row spans from the alpha channel.
	void buildSpans();
	/// True if the frame has any visible pixel.
	bool empty() const { return pixels.empty(); }
};

/**
 * The registry of HD frames: which true-color frame replaces which palette
 * frame. Keyed by the pixel buffer of the (scaled) palette frame, which is
 * what every drawing call carries, so a lookup costs one hash.
 *
 * Pack format: a mod ships `hd/<set name>/<frame index>.png` (RGBA PNG of the
 * scaled frame size, e.g. hd/SMOKE.PCK/8.png at 128x160 for k = 4;
 * terrain: hd/TERRAIN/<name>.PCK/<index>.png), or `hd/<set name>/pack.hdp`,
 * one file with all the frames of the set (see PACK_MAGIC; tools/hdart/
 * upscale_units.py writes it). Frames without a picture keep drawing as
 * before. A picture made at another whole scale than the game's (a pack of
 * 4x frames shown at 3x) is resampled when loaded.
 *
 * The pictures are read from disk when a frame is first drawn (registering a
 * set costs a directory listing, or the pack's table), and the frames drawn
 * longest ago are dropped when the loaded ones exceed a memory budget, so a
 * mod with thousands of HD unit frames costs the memory of the units on the
 * map, not of the mod.
 */
namespace HdSprites
{
	/// The header of a pack file: magic (8), then little-endian u32 scale, base width, base height, frame
	/// count, and count entries of u32 frame index, offset, size (each blob is an RGBA PNG of the frame).
	const char PACK_MAGIC[9] = "OXHDPCK1";

	/// Registers the HD frame of the palette frame whose pixel buffer is key (replaces an existing one).
	void set(const void *key, HdFrame &&frame);
	/// Registers a frame kept in a file (a PNG, or `size` bytes at `offset` of a pack), read when first
	/// found; `width` x `height` is the size of the palette frame it replaces (the picture is resampled to it).
	void setLazy(const void *key, const std::string &path, Uint32 offset, Uint32 size, int width, int height);
	/// Finds the HD frame of a palette frame (reading it from its file if needed), or nullptr.
	const HdFrame *find(const void *key);
	/// Registers variant `variant` (1, 2, ...) of the HD frame of a palette frame, kept in a file like
	/// setLazy: another painting of the same ground (hd/TERRAIN/<set>/<index>.v1.png). The renderer
	/// picks the variant of a map cell, or blends two, by a smooth pattern over the map.
	void setVariantLazy(const void *key, int variant, const std::string &path, Uint32 offset, Uint32 size, int width, int height);
	/// The number of variant slots of a palette frame's HD frame (0 = no variants; a slot may be empty).
	int variantCount(const void *key);
	/// Finds variant `variant` of a palette frame's HD frame (0 = the frame itself, see find), or nullptr.
	const HdFrame *findVariant(const void *key, int variant);
	/// Forgets the HD frame of a palette frame.
	void remove(const void *key);
	/// Forgets the HD frames of every frame of a set (call before the set is destroyed).
	void removeSet(const SurfaceSet *set);
	/// Forgets everything.
	void clear();
	/// Number of registered frames.
	size_t count();
	/// Number of frames read into memory now.
	size_t loaded();
	/// Bytes of the frames read into memory now.
	size_t loadedBytes();
	/// The memory budget of the frames read from files (bytes; default 384 MB).
	void setBudget(size_t bytes);
	/// Drops the frames found longest ago while the loaded ones exceed the budget. Call between drawn
	/// frames only (drawing commands point at the frames).
	void trim();
	/// A counter that changes whenever the registry does (caches keyed by frame pointers check it).
	unsigned generation();

	/// Registers hd/<setName>/pack.hdp and hd/<setName>/<index>.png for the frames of a set scaled
	/// `scale` times (a loose PNG wins over the pack's frame of the same index), and the variants
	/// hd/<setName>/<index>.v<n>.png (n = 1..15).
	/// @return the number of frames registered.
	int loadPack(const std::string &setName, SurfaceSet *set, int scale);
	/// Decodes an RGBA PNG from the virtual file system into a frame.
	bool loadPng(const std::string &path, HdFrame &frame);
	/// Decodes an RGBA PNG held in memory into a frame.
	bool decodePng(const unsigned char *data, size_t size, HdFrame &frame);
	/// Reads just the size of a PNG in the virtual file system (its header).
	bool pngSize(const std::string &path, int &width, int &height);
	/// The frame resampled to another size (premultiplied bilinear up, box down).
	void resample(const HdFrame &src, int width, int height, HdFrame &dst);

	/// Writes the frames of a palette set as one 8-bit PNG sheet (`cols` frames per row, the given
	/// palette, index 0 transparent) plus <file>.txt with the layout: the input of upscale_units.py.
	/// @return the number of frames written (0 = nothing written).
	int exportSet(const SurfaceSet *set, const SDL_Color *palette, const std::string &pngPath, int cols);
}

}
