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

namespace OpenXcom
{

class Surface;

/**
 * Blits for the k-scaled battlescape ("HD render").
 * The map surface is k times the base resolution; classic 8-bit elements that
 * are drawn into it (fonts, number text, hand-made markers, the hidden
 * movement screen) stay at base resolution and are scaled here on the fly.
 */
namespace HdBlit
{
	/// Nearest-neighbour scaled blit of an 8-bit surface into an 8-bit surface with the palette
	/// shading rules of Surface::blitNShade (index 0 transparent, shade within the 16-entry color
	/// group, optional color-group replacement). With scale 1 and shade 0 this is exactly a
	/// color-keyed copy, i.e. what SDL_BlitSurface and blitNShade(shade 0) do.
	void blitScaled(SDL_Surface *dest, const SDL_Surface *src, int x, int y, int scale, int shade = 0, int newBaseColor = 0);
	/// Same, for engine Surface objects (the caller draws the source first, as with blitNShade).
	void blitScaled(Surface *dest, Surface *src, int x, int y, int scale, int shade = 0, int newBaseColor = 0);
	/// Nearest-neighbour upscale of a whole 8-bit frame into an 8-bit frame of scale times its size.
	/// Every index is copied, including 0 (this makes sprite data, it does not draw).
	void upscaleFrame(SDL_Surface *dest, const SDL_Surface *src, int scale);
	/// Makes a scale times bigger nearest-neighbour copy of a sprite frame (palette included).
	Surface upscaledCopy(const Surface &src, int scale);
}

}
