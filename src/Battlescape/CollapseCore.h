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
#include <cstdint>

namespace OpenXcom
{

/// Part flags of the collapse pilot data (tools/collapse_pilot_export.py).
enum CollapsePartFlag
{
	CPF_BEARING = 1,   ///< bearing class (wall, block, column...)
	CPF_FURN = 2,      ///< furniture class
	CPF_ATTACH = 4,    ///< may be held by a bearing wall of its own cell (rule a)
	CPF_CARRY0 = 8,    ///< carries load in the intact block
	CPF_CANOPY = 16,   ///< floor: roof over the street
	CPF_POSTED = 32,   ///< floor: canopy with posts in the intact block
	CPF_LIGHT = 64,    ///< floor: light deck (not in any 3x3 square of the intact block)
	CPF_INBOX = 128,   ///< part of the pilot building (only these may collapse in battle)
};

/// One map part of a collapse template block. Everything here depends only on the intact block.
struct CollapsePart
{
	int kind;          ///< 0 floor, 1 west wall, 2 north wall, 3 object (TilePart order)
	int x, y, z;
	int set, mcd;      ///< index into the block set names, MCD index in that set
	int flags;         ///< CollapsePartFlag
	int contact;       ///< wall: shared LOFT voxels with the object below in its cell (rule b)
	int limL;          ///< floor: longest beam span
	int nEdge;         ///< object: bigWall edge neighbours
	int e0x, e0y, e1x, e1y;
	int mark;          ///< 0 none, 1 SURFACE/ATTACHED with targets, 2 marked but no target in the block
	int tOff, tCount;  ///< targets of the mark in the block targets array
};

/// A collapse template block.
struct CollapseBlock
{
	const char *label;
	const char *name;
	int sx, sy, sz;
	int x0, x1, y0, y1; ///< pilot building cells
	const char *const *sets;
	int nSets;
	const CollapsePart *parts;
	int nParts;
	const int *targets;
	int experimental; ///< still fails some of its scenarios: only in the debug stand builds (OXCE_AI_DEV)
};

/**
 * Which parts of the block hold after the given parts are removed (model M0j4 with marks v2,
 * the branches alive on the pilot buildings). removed and held are indexed by part.
 */
void collapseEvaluate(const CollapseBlock &blk, const std::vector<uint8_t> &removed, std::vector<uint8_t> &held);

}
