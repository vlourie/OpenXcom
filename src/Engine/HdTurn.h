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
#include <memory>
#include <unordered_map>
#include <vector>
#include "Surface.h"

namespace OpenXcom
{

struct HdFrame;

/**
 * The terrain frames of the turned battle map (HD lab, Engine/HdLab.h): a wall or an edge object
 * standing on the other diagonal of the screen is its frame mirrored left to right, and a flat
 * floor turns with the map about the centre of its diamond (a quarter turn of the ground is
 * sx' = -2 sy, sy' = sx / 2 on the screen). Each made frame is a palette frame of its own, and the
 * HD frame of the original, mirrored or turned the same way, is registered for it (HdSprites::set),
 * so every drawing mode draws it as it draws the original.
 *
 * A frame with a view painted for the turn (hd/TERRAIN/<set>/<index>.r<R>.png, HdSprites::setView)
 * draws that instead: a copy of the palette frame whose HD frame is the painted one, read lazily
 * within the pack budget like any pack frame. The turned map draws it as it stands, without the
 * mirror and the shift it gives a computed frame (docs/research/map-rotation-2026-10-20.md).
 *
 * The frames are made on first use and kept until the map goes: the canvas keys its caches by the
 * frame buffer (span tables, smoothed frames) for the whole battle, so a buffer may not be freed and
 * its address reused while the battle lasts. Nothing is made while the map is not turned.
 */
class HdTurn
{
	struct Entry
	{
		std::vector<Uint8> pixels;
		int width = 0, height = 0;
		/// The HD frame of the original the registered one was made from (nullptr: none registered).
		const HdFrame *from = nullptr;
		/// The frame differs from the original (a floor with relief is not turned; a frame without a painted view).
		bool made = true;
		/// The painted view of the original is registered for it (HdSprites::setView).
		bool painted = false;
	};
	/// [0] mirrored frames, [1..3] floors turned by that many quarters, [4..6] the painted views of turns 1..3;
	/// by the original's buffer.
	std::unordered_map<const void*, std::unique_ptr<Entry>> _frames[7];
	/// Makes the entry of a frame (kind 0 mirror, 1..3 quarters).
	Entry &entry(SurfaceRaw<const Uint8> src, int kind);
	/// Registers the HD frame of the original changed the same way (or drops it when the original has none).
	void syncHd(const void *key, Entry &e, int kind);
public:
	/// Forgets the HD frames registered for the made ones.
	~HdTurn();
	/// The frame mirrored left to right; with `hd`, its HD frame too.
	SurfaceRaw<const Uint8> mirrored(SurfaceRaw<const Uint8> src, bool hd);
	/// A floor frame turned by `quarters` (1..3) with the map; a frame with relief above its diamond
	/// (grass, rubble) would be squashed, so it is drawn as it is.
	SurfaceRaw<const Uint8> floorTurned(SurfaceRaw<const Uint8> src, int quarters, bool hd);
	/// The frame whose HD frame is the view of `src` painted for turn `quarters` (1..3), or a null frame
	/// when none is painted or its picture cannot be read (then the computed frame is drawn).
	SurfaceRaw<const Uint8> painted(SurfaceRaw<const Uint8> src, int quarters);
	/// How many frames were made (all kinds).
	size_t count() const;
};

}
