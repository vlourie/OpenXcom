#pragma once
/*
 * Copyright 2010-2016 OpenXcom Developers.
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
#include <cstdint>
#include <vector>
#include <SDL_types.h>
#include "Position.h"
#include "../Mod/MapData.h"

namespace OpenXcom
{

class SavedBattleGame;

/// One voxel of the terrain only - TileEngine::voxelCheck with all units excluded, without its tile cache, so it can run
/// on several threads at once. Reads the tiles, changes nothing. Defined in TileEngine.cpp next to voxelCheck.
VoxelType terrainVoxel(const SavedBattleGame *save, const std::vector<Uint16> *voxelData, Position voxel);
/// A line of the terrain only - TileEngine::calculateLineVoxel's walk (calculateLineHelper) over terrainVoxel.
/// @return what the line meets first: V_FLOOR..V_OBJECT, V_OUTOFBOUNDS or V_EMPTY.
VoxelType terrainLineVoxel(const SavedBattleGame *save, const std::vector<Uint16> *voxelData, Position origin, Position target);

/**
 * The enemy's cover map, docs/research/ai-mechanics/COVER-MAP-DESIGN-2026-10-22.md (direction 2). Per tile a size-1 unit
 * can stand on, per side (8, Pathfinding directions) and per body layer (12, the LOFT step of 2 voxels): how many of 3
 * parallel lines from a virtual shooter on the same level, 3 and 10 tiles away, the terrain stops within 1.5 tiles of the
 * tile (0..3). Per tile: window and door flags. Over the map's nodes: how many shortest paths between nodes go through a
 * node (betweenness) and node-to-node lines of sight within the view distance. Terrain only - no units, no random numbers;
 * reads the map, changes nothing. Built on the first AI decision of a battle (a loaded one too), refreshed around the
 * tiles whose parts changed. Off unless OXCE_AI_COVERMAP is set (2: also the checks - own line against the engine's,
 * one thread against many); not built in the player's base defence (the enemy does not know that map).
 */
class AiCoverMap
{
public:
	static const int SIDES = 8, LAYERS = 12, SHOOTERS = 2, LINES = 3;
	/// Tile flags.
	enum { F_STAND = 1, F_WINDOW = 2, F_DOOR = 4 };

	/// OXCE_AI_COVERMAP: 0 off, 1 on, 2 on with the checks.
	static int mode();
	/// A tile part changed (Tile::setMapData, a UFO door opened or closed): the cover around it is stale.
	static void touch(const Position &pos);
	/// Builds the map of this battle if it is not built yet, refreshes the stale tiles; before each AI decision.
	static void update(SavedBattleGame *save);
	/// The battle is gone (SavedBattleGame's destructor): drops its map.
	static void reset(const SavedBattleGame *save);

	/// Lines stopped (0..3) on side `side`, body layer `layer` (2 voxels each from 2 voxels over the floor), shooter
	/// `far` (0: 3 tiles, 1: 10 tiles); -1 - no map or not a tile to stand on.
	static int cover(const Position &tile, int side, int layer, int far);
	/// F_* of the tile; 0 without a map.
	static int flags(const Position &tile);
	/// Node `from` (eye of a standing unit) sees node `to` (the middle of a standing body) over the terrain.
	static bool nodeSees(int from, int to);
	/// Shortest paths between other nodes through the node; -1 without a map.
	static int choke(int node);
};

}
