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

struct plm_t;

namespace OpenXcom
{

/**
 * HD render: a short silent MPEG-1 clip (the craft launch and landing scenes) decoded with
 * pl_mpeg from a file of the HD mod and drawn over the whole world layer, fitted with black
 * bars. Picture only: nothing of the game reads it.
 */
class HdVideo
{
private:
	std::vector<Uint8> _data;       // the whole file: pl_mpeg reads it from memory (mods may be zipped)
	plm_t *_plm = nullptr;
	std::vector<Uint32> _frame;     // the frame shown now, 0xFFRRGGBB
	int _width = 0, _height = 0;
	double _fps = 25.0;
	double _time = 0.0;             // the clip time played so far
	double _shown = -1.0;           // the time of the frame in _frame
	bool _ended = false;
	/// Decodes the next frame into _frame; false at the end.
	bool decodeNext();
public:
	HdVideo() = default;
	~HdVideo();
	HdVideo(const HdVideo&) = delete;
	HdVideo &operator=(const HdVideo&) = delete;
	/// Opens a clip by its virtual path (FileMap); false if it is missing or not MPEG-1.
	bool open(const std::string &path);
	/// Plays `seconds` on: decodes up to the frame due.
	void advance(double seconds);
	/// The last frame has been shown for its time.
	bool ended() const { return _ended; }
	/// The time played, in seconds.
	double time() const { return _time; }
	/// Draws the frame over the whole of dest (32 bpp), fitted, black around; `bright` of 256.
	void draw(SDL_Surface *dest, int bright = 256) const;
	/// Draws the area (rx, ry, rw, rh) of a w x h 0xAARRGGBB picture over the whole of dest, fitted
	/// with its aspect kept: bilinear, black where the area goes past the picture and around it,
	/// `bright` of 256 (0 black). Rows on the HD workers.
	static void drawFitted(const Uint32 *src, int w, int h, double rx, double ry, double rw, double rh, SDL_Surface *dest, int bright);
};

}
