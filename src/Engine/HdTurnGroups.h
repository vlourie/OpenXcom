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
#include "../Battlescape/Position.h"

namespace OpenXcom
{

class SavedBattleGame;
class Tile;
class MapData;
class HdTurn;

/// A piece of a composite object: the object record `record` of terrain set `set` (index into the set names)
/// at (x, y, z) from the low corner of the group's box, z up.
struct HdTurnGroupPiece { int set, record, x, y, z; };
/// A composite object: `count` pieces from `first`, in a box of sizeX x sizeY x sizeZ tiles.
struct HdTurnGroupDef { int first, count, sizeX, sizeY, sizeZ; };

/**
 * The composite objects of the turned battle map (HD lab, Engine/HdLab.h): a tree, a dome or a tank drawn by
 * the objects of several tiles (the table HdTurnGroupsTable.inc, made by tools/rotation_groups_inc.py from the
 * .MAP blocks of both games). The turned map draws each object facing the view, mirrored at an odd turn;
 * drawn tile by tile, the pieces of such a whole would each turn in its own tile and fall apart. The table
 * holds only wholes that look the same from every side (plants, wholes equal to their mirror): one that does
 * not (a car, a ship's cockpit) mirrored as a whole would come off the pieces around it.
 *
 * The groups standing whole on the map are found once (build): the pieces of a group in their places, the
 * same object records. The turned view then draws a group as one: a cell of the view inside its box gets the
 * piece that stands at that place of the box in the whole - the whole as it is at turns 0 and 2, its mirror
 * (x and y of the box swapped, each piece mirrored) at turns 1 and 3 - and a tile of the group does not draw
 * its own piece. Only the picture moves: the tiles keep their objects for every rule of the game.
 *
 * A group that lost a piece (destroyed, changed) is drawn tile by tile again, as is one whose piece has a
 * view painted for the turn (HdTurn::painted, which stands in its own tile).
 */
class HdTurnGroups
{
	struct Instance
	{
		/// The low corner of the box on the map and its size in tiles.
		Position corner, size;
		/// The tiles of the pieces and the object each held when the group was found.
		std::vector<Tile*> tiles;
		std::vector<const MapData*> data;
		/// By the cell of the box (x fastest, then y, then z): the piece standing there, -1 none.
		std::vector<int> cell;
		/// By turn: some piece has a view painted for it (-1 not looked yet).
		signed char painted[4] = { -1, -1, -1, -1 };
	};
	std::vector<Instance> _instances;
	/// By tile index: the group whose piece the tile holds, -1 none.
	std::vector<int> _member;
	/// By tile index: the groups whose box takes the tile, _cover[_coverStart[i] .. _coverStart[i + 1]).
	std::vector<int> _coverStart, _cover;
	/// Whether every tile of the group still holds its piece.
	bool intact(const Instance &g) const;
public:
	/// Finds the composite objects standing whole on the map.
	void build(SavedBattleGame *save);
	/// How many were found.
	size_t count() const { return _instances.size(); }
	/// Whether group `i` is drawn as one at turn `rot` (1..3): whole, and no piece with a view painted for
	/// the turn when `hd` (the painted views are looked at with `turn`).
	bool active(int i, int rot, HdTurn *turn, bool hd);
	/// The group whose piece tile `index` holds, -1 none.
	int memberOf(int index) const { return index >= 0 && index < (int)_member.size() ? _member[index] : -1; }
	/// The groups whose box takes tile `index`: `count` of them from the pointer returned.
	const int *covering(int index, int &count) const;
	/// The low corner and the size of the box of group `i`.
	const Position &corner(int i) const { return _instances[i].corner; }
	const Position &size(int i) const { return _instances[i].size; }
	/// The tile of the piece at `local` in the box of group `i`, nullptr none (or outside the box).
	Tile *piece(int i, const Position &local) const;
};

}
