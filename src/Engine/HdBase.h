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
#include <string>
#include <vector>
#include "HdSprites.h"

namespace OpenXcom
{

/**
 * HD pictures of the base view's facilities, with animation.
 *
 * A mod ships `hd/BASEBITS.PCK/<frame index>.png` - the picture of that tile of
 * the base screen (the facility's shape and graphic together), a whole number of
 * times bigger than the classic 32x40 tile - and, for an animated facility, the
 * further phases `<frame index>.v1.png`, `.v2.png` ... (the same names the HD
 * sprite packs use for ground variants, see HdSprites).
 *
 * A tile with such a picture is not drawn on the classic layer at all: the
 * picture goes into the true-color world layer instead, so it is shown in the
 * display's resolution, and everything the base view draws on top (connectors,
 * craft, the selector, numbers) keeps drawing classically over it.
 *
 * The pictures are read when first drawn and kept within a memory budget.
 */
namespace HdBase
{
	/// Number of animation phases of a base tile (0 = no picture, 1 = a still picture).
	int phases(int index);
	/// The picture of a base tile at `scale` times the classic `baseWidth` x `baseHeight`, or nullptr.
	const HdFrame *frame(int index, int phase, int scale, int baseWidth, int baseHeight);
	/// A tile a base screen is about to draw.
	struct Want
	{
		int index, baseWidth, baseHeight;
	};
	/// Reads every phase of these tiles not read yet, decoding across HdWorkers: a base opens
	/// with one short pause instead of a stall on each phase met for the first time.
	void preload(const std::vector<Want> &want, int scale);
	/// Are animated tiles in use (something drawn since the last clear has more than one phase)?
	bool animated();
	/// Forgets everything (mod reload).
	void clear();
	/// The memory budget of the loaded pictures (bytes, default 64 MB).
	void setBudget(size_t bytes);
}

}
