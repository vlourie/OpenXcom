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

namespace OpenXcom
{

class Mod;
class Surface;

/**
 * The background of a craft's window on the geoscape (GeoscapeCraftState): instead of the
 * interface's one picture for every craft, the picture of the craft's own ufopaedia article,
 * in the colours the window shows its background with - the 16 entries of the background
 * ramp (Palette::backPos, 224..239), ordered by brightness.
 *
 * The whole picture is fitted to the window's height and centred, kept in the darker part of
 * the ramp and darkened towards the window's edges, so the texts and buttons stay readable.
 * The classic image is the ramp's 16 steps; when the picture has an HD version, an HD picture
 * of smooth tones between the ramp's colours is registered for it with HdUiArt. Both are made
 * once per craft type and window palette.
 */
namespace HdCraftBack
{
	/// The background image for a craft of this type shown with this palette, or nullptr
	/// (no ufopaedia article with a picture: the interface's own background stays).
	const Surface *get(Mod *mod, const std::string &craftType, const SDL_Color *palette);
}

}
