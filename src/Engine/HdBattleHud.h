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
#include <vector>
#include "InteractiveSurface.h"

namespace OpenXcom
{

/**
 * HD interface, modern skin: the battle's button panel (oxceHdBattleHud).
 *
 * The classic panel is one picture (ICONS.PCK, the bottom 56 rows) with invisible buttons over it;
 * the buttons copy their piece of it, and a pressed one shows that piece with its colours turned.
 * Here, in the world layer only, the picture is replaced: a dark panel, wells for the hands and a
 * card under the unit's name and stats, and each button a tile with a vector pictogram that lights
 * under the mouse and when pressed. The pictograms are rasterized once per scale and cached.
 *
 * Pictures only: the buttons stay where they are, the classic layer keeps the classic panel (what
 * the clicks and the k = 1 frame go by), and nothing the buttons do changes.
 */
class HdBattleHud
{
public:
	/// The pictograms of the panel's buttons.
	enum Icon
	{
		ICON_NONE,
		ICON_UNIT_UP, ICON_UNIT_DOWN, ICON_MAP_UP, ICON_MAP_DOWN, ICON_SHOW_MAP, ICON_KNEEL,
		ICON_INVENTORY, ICON_CENTER, ICON_NEXT_SOLDIER, ICON_NEXT_STOP, ICON_SHOW_LAYERS, ICON_LINKS,
		ICON_OPTIONS, ICON_END_TURN, ICON_ABORT,
		ICON_RESERVE_NONE, ICON_RESERVE_SNAP, ICON_RESERVE_AIMED, ICON_RESERVE_AUTO, ICON_RESERVE_KNEEL,
		ICON_ZERO_TUS,
		ICON_COUNT
	};
	/// Is the panel drawn the modern way (the HD skin is on and so is the option)?
	static bool on();
	/// Draws a button of the panel: a tile at base (x, y, w, h) with the pictogram; `lit` = pressed or
	/// selected. `tint` = the button's own palette colour (the reserve buttons' green and red), 0 = none.
	static void drawButton(int x, int y, int w, int h, Icon icon, bool lit, Uint8 tint, const SDL_Color *pal);
};

/**
 * The battle's button panel (BattlescapeState::_icons): the classic surface, which in the world
 * layer draws the modern panel when HdBattleHud::on(), with the wells and the card under the
 * widgets it is told about.
 */
class HdHudPanel : public InteractiveSurface
{
public:
	/// What is drawn under a widget of the panel.
	enum Part
	{
		PART_HAND,    ///< a well under an item in hand
		PART_CARD,    ///< the card under the unit's name, rank and stats
		PART_RANK,    ///< the frame of the rank badge on the card
		PART_CHIP     ///< a tinted chip under a stat's number
	};
	HdHudPanel(int width, int height, int x = 0, int y = 0) : InteractiveSurface(width, height, x, y) {}
	/// Puts a part under a widget (its rectangle is read at drawing time); `color` = the chip's palette colour.
	void addPart(Part part, const Surface *widget, Uint8 color = 0);
	void hdMirror() override;
private:
	struct Item
	{
		Part part;
		const Surface *widget;
		Uint8 color;
	};
	std::vector<Item> _parts;
};

}
