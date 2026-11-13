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
#include "HdSprites.h"

namespace OpenXcom
{

class RuleItem;
class SurfaceSet;

/**
 * HD render (option oxceHdClassicShots, XP-000544): the shot of an energy weapon drawn as the classic game drew it, in
 * three families - a flat beam with a round head (laser), a ball with a short tail of beads (plasma), a capsule inside
 * two see-through coils of air (gauss) - each in three sizes by the weapon's class (hd/FX/shots.txt, written by
 * tools/hdart/shots_map.py from the weapon_class table). The colour is the weapon's own: it is read from the row of
 * the bullet sheet the shot flies with, not set here.
 *
 * Only the picture: nothing here reads or changes a trajectory, a hit, a time of flight or a random number. A shot is
 * drawn as a row of pieces (each pixel of the whole picture belongs to exactly one piece, so the pieces do not
 * overlap and show no seams); Map::drawTerrain stamps every piece in the tile its stretch of the way lies in, like the
 * stamps of the classic tracer, so the shot goes behind and in front of walls and units as that does. The pictures
 * are made once per (class, size, colour, angle, length) and kept.
 */
namespace HdShots
{
	enum Class { NONE = 0, LASER = 1, PLASMA = 2, GAUSS = 3 };
	enum Size { SMALL = 0, MEDIUM = 1, LARGE = 2 };
	struct Kind
	{
		int cls = NONE;
		int size = MEDIUM;
		explicit operator bool() const { return cls != NONE; }
	};
	/// How many directions of the screen a shot is drawn at (a step of half a degree).
	const int ANGLES = 720;

	/// The class and the size of `weapon`'s shot by hd/FX/shots.txt ("shot <item> laser|plasma|gauss small|medium|large");
	/// cls == NONE: the file has no line for it, the shot is drawn as before.
	Kind kindOf(const RuleItem *weapon);

	/// The colours of one row of the bullet sheet (its 35 frames from `first`), read from the classic frames.
	struct Colours
	{
		double vivid[3] = { 255, 255, 255 };   ///< the row's most vivid colour at full brightness
		double ramp[35][3] = {};               ///< the colour of every lit frame, from the head backward
		int rampCount = 0;
		bool valid = false;
		int id = 0;                            ///< tells the rows (and palettes) apart
	};
	/// The colours of the row `first` of `set` under `palette`; kept per (row, palette).
	const Colours &coloursOf(const SurfaceSet *set, int first, const SDL_Color *palette);

	/// One piece of a shot: its picture and where its corner lies from the head of the shot (screen pixels).
	struct Piece
	{
		HdFrame frame;
		int dx = 0, dy = 0;
	};
	struct Shot
	{
		std::vector<Piece> pieces;     ///< from the head backward
		Uint32 used = 0;
	};
	/// The length of a piece along the shot, screen pixels at scale k.
	int pieceLength(int k);
	/// The nominal length of a laser beam of this size, in voxels of the way (a faster bullet is drawn as long as its jump).
	int laserNominalVoxels(int size);
	/// How long the shot is, in pieces, for a laser beam `pixels` long at scale k (the other classes have their own).
	int laserPieces(int pixels, int k);
	/// The pieces of a shot of `kind` in `colours`, flying at angle `angle` (0..ANGLES-1, clockwise from the screen's +x),
	/// `lengthPieces` long (laser only). nullptr: the colours are not read. The shot stays valid until a good while
	/// after it was last asked for.
	const Shot *shot(Kind kind, const Colours &colours, int k, int angle, int lengthPieces);
	/// A new map frame: forgets the pictures not asked for lately.
	void newFrame();
}

}
