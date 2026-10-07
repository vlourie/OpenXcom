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
#include <vector>
#include <SDL.h>

namespace OpenXcom
{

class SurfaceSet;

/**
 * The palette transformation of a battle (enviroEffects paletteTransformations) on the HD packs.
 *
 * The classic frames are indices: swapping the palette recolours them by itself. The HD frames
 * are true colour, so the swap is carried over as a colour shift, the same for every frame of
 * its kind for the whole battle (docs/research/hd-enviro-palette-task-2026-10-07.md, art/paltx/handoff/HANDOFF.md):
 *  - terrain (BR): one 32^3 colour grid of the classic shift P[i] - B[i], gathered from every
 *    picture of the battle's terrain packs (the frames, their .vN variants and the addressed
 *    walls) block by block against the classic index under it, blurred, and blended into M1t
 *    where the samples are few; baked into a 64^3 table before the first frame is shown;
 *  - everything else (soldiers, items): M1t, a 64^3 table of the kernel-weighted mean shift of
 *    the palette entries near each colour.
 * The frames are recoloured once, when they are read (HdSprites::setRecolour).
 */
namespace HdPaletteShift
{
	/// Builds the tables of a battle and recolours its HD frames from now on.
	/// @param shown The palette the battle is drawn with (after the transformation).
	/// @param base The palette it replaced (BACKUP_<name>).
	/// @param terrain The terrain sets of the battle.
	void install(const SDL_Color *shown, const SDL_Color *base, const std::vector<const SurfaceSet*> &terrain);
	/// Back to the frames' own colours (the recoloured ones are dropped and read again when drawn).
	void remove();
	/// Whether a transformation is carried over now.
	bool active();
}

}
