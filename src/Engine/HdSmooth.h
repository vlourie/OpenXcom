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
#include "HdSprites.h"

namespace OpenXcom
{

/**
 * Smoothing of palette pixel art for the HD render (shared by the battlescape
 * canvas and the HD interface).
 */
namespace HdSmooth
{
	/// Scales a base-resolution palette sprite k times (2..6) with xBRZ into a true-color frame:
	/// index 0 transparent, checkerboard dithering turned into alpha / mixed colors first.
	/// `isoTile`: the sprite is a battlescape tile (32 wide, the floor diamond in its bottom 16
	/// rows): the diamond is smoothed as part of a field of its neighbours and keeps a pixel-exact
	/// edge, so that tiles meet without seams or notches.
	bool smoothPalette(const Uint8 *indices, int bw, int bh, int pitch, const SDL_Color *colors, int k, HdFrame &out, bool isoTile = false);
	/// Is (x, y) inside the classic floor diamond of a bw x bh tile (the bottom 16 rows)?
	bool inFloorDiamond(int x, int y, int bw, int bh);
}

}
