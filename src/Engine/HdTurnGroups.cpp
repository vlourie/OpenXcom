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
#include "HdTurnGroups.h"
#include <algorithm>
#include <cctype>
#include <string>
#include <unordered_map>
#include "HdTurn.h"
#include "Logger.h"
#include "../Mod/MapData.h"
#include "../Mod/MapDataSet.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"

namespace OpenXcom
{

namespace
{
#include "HdTurnGroupsTable.inc"
}

void HdTurnGroups::build(SavedBattleGame *save)
{
	_instances.clear();
	const int tiles = save->getMapSizeXYZ();
	_member.assign(tiles, -1);

	// the object of every piece, in the terrain sets of this battle (a set not here: its groups are not)
	const int sets = (int)(sizeof(TURN_GROUP_SETS) / sizeof(TURN_GROUP_SETS[0]));
	std::unordered_map<std::string, int> setIndex;
	for (int i = 0; i < sets; ++i)
		setIndex.emplace(TURN_GROUP_SETS[i], i);
	std::vector<MapDataSet*> setOf(sets, nullptr);
	for (MapDataSet *set : *save->getMapDataSets())
	{
		std::string name = set->getName();
		std::transform(name.begin(), name.end(), name.begin(), [](unsigned char c) { return (char)std::toupper(c); });
		auto it = setIndex.find(name);
		if (it != setIndex.end() && !setOf[it->second])
			setOf[it->second] = set;
	}
	const int defs = (int)(sizeof(TURN_GROUP_DEFS) / sizeof(TURN_GROUP_DEFS[0]));
	std::vector<const MapData*> pieceData(sizeof(TURN_GROUP_PIECES) / sizeof(TURN_GROUP_PIECES[0]), nullptr);
	// the groups by the object of their first piece (the lowest), where the search starts
	std::unordered_map<const MapData*, std::vector<int>> byFirst;
	for (int g = 0; g < defs; ++g)
	{
		const HdTurnGroupDef &def = TURN_GROUP_DEFS[g];
		bool all = true;
		for (int p = def.first; p < def.first + def.count; ++p)
		{
			MapDataSet *set = setOf[TURN_GROUP_PIECES[p].set];
			const int record = TURN_GROUP_PIECES[p].record;
			pieceData[p] = set && record >= 0 && (size_t)record < set->getSize() ? set->getObject(record) : nullptr;
			all = all && pieceData[p];
		}
		if (all)
			byFirst[pieceData[def.first]].push_back(g);
	}

	for (int index = 0; index < tiles && !byFirst.empty(); ++index)
	{
		Tile *tile = save->getTile(index);
		const MapData *data = tile->getMapData(O_OBJECT);
		auto it = data ? byFirst.find(data) : byFirst.end();
		if (it == byFirst.end() || _member[index] >= 0)
			continue;
		for (int g : it->second)
		{
			const HdTurnGroupDef &def = TURN_GROUP_DEFS[g];
			const HdTurnGroupPiece &first = TURN_GROUP_PIECES[def.first];
			Instance found;
			found.corner = tile->getPosition() - Position(first.x, first.y, first.z);
			found.size = Position(def.sizeX, def.sizeY, def.sizeZ);
			found.cell.assign(def.sizeX * def.sizeY * def.sizeZ, -1);
			bool whole = true;
			for (int p = def.first; p < def.first + def.count && whole; ++p)
			{
				const HdTurnGroupPiece &piece = TURN_GROUP_PIECES[p];
				Tile *at = save->getTile(found.corner + Position(piece.x, piece.y, piece.z));
				whole = at && at->getMapData(O_OBJECT) == pieceData[p] && _member[save->getTileIndex(at->getPosition())] < 0;
				if (whole)
				{
					found.cell[(piece.z * def.sizeY + piece.y) * def.sizeX + piece.x] = (int)found.tiles.size();
					found.tiles.push_back(at);
					found.data.push_back(pieceData[p]);
				}
			}
			if (!whole)
				continue;
			for (Tile *at : found.tiles)
				_member[save->getTileIndex(at->getPosition())] = (int)_instances.size();
			_instances.push_back(std::move(found));
			break;
		}
	}

	// the tiles of every box (the box may reach past the map's edge: those cells are left out)
	std::vector<std::pair<int, int>> taken;
	for (int g = 0; g < (int)_instances.size(); ++g)
	{
		const Instance &inst = _instances[g];
		for (int z = 0; z < inst.size.z; ++z)
			for (int y = 0; y < inst.size.y; ++y)
				for (int x = 0; x < inst.size.x; ++x)
					if (save->getTile(inst.corner + Position(x, y, z)))
						taken.push_back(std::make_pair(save->getTileIndex(inst.corner + Position(x, y, z)), g));
	}
	std::sort(taken.begin(), taken.end());
	_coverStart.assign(tiles + 1, 0);
	_cover.clear();
	_cover.reserve(taken.size());
	for (const auto &t : taken)
	{
		++_coverStart[t.first + 1];
		_cover.push_back(t.second);
	}
	for (int i = 0; i < tiles; ++i)
		_coverStart[i + 1] += _coverStart[i];
	Log(LOG_INFO) << "HD turn: " << _instances.size() << " composite object(s) on the map drawn whole when turned";
}

bool HdTurnGroups::intact(const Instance &g) const
{
	for (size_t i = 0; i < g.tiles.size(); ++i)
		if (g.tiles[i]->getMapData(O_OBJECT) != g.data[i])
			return false;
	return true;
}

bool HdTurnGroups::active(int i, int rot, HdTurn *turn, bool hd)
{
	Instance &g = _instances[i];
	if (!intact(g))
		return false;
	if (!hd)
		return true;
	signed char &painted = g.painted[rot & 3];
	if (painted < 0)
	{
		painted = 0;
		for (Tile *t : g.tiles)
		{
			const SurfaceRaw<const Uint8> sprite = t->getSprite(O_OBJECT);
			if (sprite && turn->painted(sprite, rot))
			{
				painted = 1;
				break;
			}
		}
	}
	return painted == 0;
}

const int *HdTurnGroups::covering(int index, int &count) const
{
	if (index < 0 || index + 1 >= (int)_coverStart.size())
	{
		count = 0;
		return nullptr;
	}
	count = _coverStart[index + 1] - _coverStart[index];
	return _cover.data() + _coverStart[index];
}

Tile *HdTurnGroups::piece(int i, const Position &local) const
{
	const Instance &g = _instances[i];
	if (local.x < 0 || local.y < 0 || local.z < 0 || local.x >= g.size.x || local.y >= g.size.y || local.z >= g.size.z)
		return nullptr;
	const int p = g.cell[(local.z * g.size.y + local.y) * g.size.x + local.x];
	return p < 0 ? nullptr : g.tiles[p];
}

}
