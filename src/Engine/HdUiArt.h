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
#include <SDL.h>
#include <string>
#include <vector>
#include "HdSprites.h"

namespace OpenXcom
{

class Surface;

/**
 * HD pictures of the interface's images: hd/UI/<name>.png in a mod is the
 * picture of the mod's image <name> (an extraSprites type, or the file name of
 * a single-image sprite), a whole number of times bigger, with an optional
 * <name>.pal.txt (the palette it was made with, for re-tinting to the palette
 * it is shown with).
 *
 * A picture is claimed by name and size, so the same hd mod can hold pictures of several games'
 * images of one name (BACK08.SCR is the ufopaedia's green background in vanilla, another mod's own
 * screen elsewhere): when a picture is first drawn it is shrunk back to the classic size and compared
 * with the image it replaces, and a picture of something else is dropped (see MATCH_LIMIT).
 *
 * The classic interface keeps drawing as it is; when a surface whose pixels are
 * such an image (the image itself, or a state's copy of it) is blitted onto the
 * screen, the picture is drawn into the true-color world layer instead and the
 * classic pixels are left transparent there, so the picture shows through under
 * whatever the state draws on top (texts, buttons).
 */
namespace HdUiArt
{
	struct Art
	{
		std::string name;
		const Surface *baseSurface = nullptr;   ///< the mod's image
		std::string path;                 ///< the picture's file (loaded when first drawn; empty = frame given)
		mutable HdFrame frame;            ///< the picture at `scale` times the classic size (see HdUiArt::frame)
		mutable size_t lru = 0;           ///< when the frame was last used
		int scale = 1;
		int baseWidth = 0, baseHeight = 0;
		Uint64 hash = 0;                  ///< HdUiArt::hashPixels of the classic image
		mutable bool checked = false;     ///< the picture was compared with the image it replaces
		mutable bool bad = false;         ///< it turned out to be a picture of something else (not used)
		std::vector<Uint8> base;          ///< the classic image's pixels (baseWidth * baseHeight)
		std::vector<SDL_Color> palette;   ///< the reference palette (empty: no re-tinting)
	};
	/// FNV hash of palette pixels (the content key of an image).
	Uint64 hashPixels(const Uint8 *pixels, int pitch, int w, int h);
	/// Registers a picture for a classic image (takes the image's pixels now). False if the sizes do not fit.
	bool add(const std::string &name, const Surface *base, HdFrame &&frame, std::vector<SDL_Color> palette);
	/// Registers a picture kept in a file (hd/UI/...) of `width` x `height`, loaded when first drawn; the
	/// loaded pictures are kept within a memory budget (the least recently drawn are dropped).
	bool addLazy(const std::string &name, const Surface *base, const std::string &path, int width, int height, std::vector<SDL_Color> palette);
	/// The picture's pixels, loading them if needed (empty when the file cannot be read).
	const HdFrame &frame(const Art *art);
	/// The memory budget of the loaded pictures (bytes).
	void setBudget(size_t bytes);
	/// The picture of the classic image with these pixels (by content), or nullptr.
	const Art *find(Uint64 hash, int w, int h);
	/// The picture of a mod's image (by the surface it was registered with), or nullptr.
	const Art *find(const Surface *base);
	/// The picture of the image these pixels are a part of (a state's copy of a corner of an image):
	/// the art and the offset of the pixels within its image, or nullptr. Slow (a search): cache the answer.
	const Art *findCrop(const Uint8 *pixels, int pitch, int w, int h, int &offX, int &offY);
	/// Forgets everything (mod reload).
	void clear();
	size_t count();
	/// Bytes of the pictures loaded now (see setBudget).
	size_t bytes();

	/// Are pictures drawn now: the option is on, the screen is layered with a world scale of 2 or more.
	bool active();
	/// The picture of `surface` (if its pixels are a registered image), drawn into the screen's world layer
	/// at the surface's position, re-tinted to the surface's palette. True when drawn: the caller then
	/// leaves the classic pixels out (transparent), so the picture shows through.
	bool drawIfPicture(const Surface *surface, SDL_Surface *dest);
	/// Draws an HD picture into a 32-bit surface (the screen's world layer) at (x, y), clipped to it:
	/// for the pictures a state places itself, such as the base view's facilities (see HdBase).
	void drawFrame(SDL_Surface *dest, const HdFrame &frame, int x, int y);
	/// Drops the prepared (scaled, re-tinted) pictures (palette or scale change).
	void clearPrepared();
}

}
