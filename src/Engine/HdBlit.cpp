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
#include "HdBlit.h"
#include <algorithm>
#include "Surface.h"

namespace OpenXcom
{
namespace HdBlit
{

void blitScaled(SDL_Surface *dest, const SDL_Surface *src, int x, int y, int scale, int shade, int newBaseColor)
{
	if (!dest || !src || scale < 1 || dest->format->BitsPerPixel != 8 || src->format->BitsPerPixel != 8)
	{
		return;
	}
	// destination rectangle of the scaled source, clipped to the destination
	const int dstX0 = std::max(x, 0);
	const int dstY0 = std::max(y, 0);
	const int dstX1 = std::min(x + src->w * scale, dest->w);
	const int dstY1 = std::min(y + src->h * scale, dest->h);
	if (dstX0 >= dstX1 || dstY0 >= dstY1)
	{
		return;
	}
	// same per-pixel rules as helper::StandardShade / helper::ColorReplace in ShaderDraw.h
	const Uint8 ColorGroup = 0xF0;
	const Uint8 ColorShade = 0x0F;
	Uint8 newColor = 0;
	if (newBaseColor)
	{
		newColor = (Uint8)((newBaseColor - 1) << 4);
	}
	const Uint8 *srcPixels = (const Uint8*)src->pixels;
	Uint8 *dstPixels = (Uint8*)dest->pixels;
	for (int dy = dstY0; dy < dstY1; ++dy)
	{
		const Uint8 *srcRow = srcPixels + (size_t)((dy - y) / scale) * src->pitch;
		Uint8 *dstRow = dstPixels + (size_t)dy * dest->pitch;
		for (int dx = dstX0; dx < dstX1; ++dx)
		{
			const Uint8 idx = srcRow[(dx - x) / scale];
			if (!idx)
			{
				continue;
			}
			if (newBaseColor)
			{
				const Uint8 newShade = (Uint8)((idx & ColorShade) + shade);
				dstRow[dx] = (newShade & ColorGroup) ? ColorShade : (Uint8)(newColor | newShade);
			}
			else
			{
				const Uint8 newShade = (Uint8)(idx + shade);
				dstRow[dx] = ((newShade ^ idx) & ColorGroup) ? ColorShade : newShade;
			}
		}
	}
}

void upscaleFrame(SDL_Surface *dest, const SDL_Surface *src, int scale)
{
	if (!dest || !src || scale < 1 || dest->format->BitsPerPixel != 8 || src->format->BitsPerPixel != 8)
	{
		return;
	}
	const int w = std::min(dest->w, src->w * scale);
	const int h = std::min(dest->h, src->h * scale);
	const Uint8 *srcPixels = (const Uint8*)src->pixels;
	Uint8 *dstPixels = (Uint8*)dest->pixels;
	for (int y = 0; y < h; ++y)
	{
		const Uint8 *srcRow = srcPixels + (size_t)(y / scale) * src->pitch;
		Uint8 *dstRow = dstPixels + (size_t)y * dest->pitch;
		for (int x = 0; x < w; ++x)
		{
			dstRow[x] = srcRow[x / scale];
		}
	}
}

Surface upscaledCopy(const Surface &src, int scale)
{
	Surface dest(src.getWidth() * scale, src.getHeight() * scale, src.getX(), src.getY());
	if (src.getPalette())
	{
		dest.setPalette(src.getPalette());
	}
	// Surface::getSurface() is not const; the source is only read
	upscaleFrame(dest.getSurface(), const_cast<Surface&>(src).getSurface(), scale);
	return dest;
}

void blitScaled(Surface *dest, Surface *src, int x, int y, int scale, int shade, int newBaseColor)
{
	if (!dest || !src)
	{
		return;
	}
	blitScaled(dest->getSurface(), src->getSurface(), x, y, scale, shade, newBaseColor);
}

}
}
