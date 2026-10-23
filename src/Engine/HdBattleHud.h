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
#include <string>
#include "InteractiveSurface.h"

namespace OpenXcom
{

/**
 * HD interface, modern skin: the battle's button panel (oxceHdBattleHud).
 *
 * The classic panel is one picture (ICONS.PCK, the bottom 56 rows) with invisible buttons over it;
 * the buttons copy their piece of it, and a pressed one shows that piece with its colours turned.
 * Here, in the world layer only, the picture is replaced: a dark panel, wells for the hands and a
 * card under the unit's name and stats, and each button a key: a cap in a socket that goes down when
 * pressed (by the mouse or by its hotkey) and springs back, stays down while it is on (the reserve
 * chosen, the unit kneeling), its pictogram lit in a window of glass (or cut into the brass). The caps
 * are built once per scale and step of the way down and cached; the motion is kept per key.
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
	/// Draws a button of the panel, `key` (its motion is kept under it), at base (x, y, w, h) with the pictogram;
	/// `lit` = on (the reserve chosen, the unit kneeling), `held` = a mouse button is down on it. `tint` = the
	/// button's own palette colour (the reserve buttons' green and red), 0 = none; `hotkey` = its key's name or null.
	static void drawButton(const void *key, int x, int y, int w, int h, Icon icon, bool lit, bool held, Uint8 tint, const SDL_Color *pal, const char *hotkey);
	/// A button was pressed (clicked or its hotkey): its key goes down, even for a click quicker than a frame.
	static void notePress(const void *key);
	/// Is this bar laid in a groove of the brass panel's card (Bar::hdMirror draws it as a tube in it)?
	static bool grooved(const Surface *bar);
	/// The colours of such a groove in the panel's metal: its floor top and bottom, the light on its lower lip (0xRRGGBB).
	static void grooveColors(Uint32 &top, Uint32 &bottom, Uint32 &lip);
	/// Is this number a counter lying on a hand's well of the painted panel (NumberText::hdMirror draws it on a dark
	/// tab, HdUi::drawCounter)? `plate` and `edge` get the tab's colours (0xAARRGGBB).
	static bool counter(const Surface *number, Uint32 &plate, Uint32 &edge);
	/// A shade 0..1 (dark to light) of the panel's metal for the option's look (brass, hull steel, silver...):
	/// the windows' metal frames (HdScreens) are cast in it.
	static Uint32 metalShade(float s);
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
		PART_CHIP,    ///< a tinted chip under a stat's number
		PART_BAR,     ///< a stat's bar, laid in a groove (HdBattleHud::grooved)
		PART_COUNT    ///< a number on a hand's well: the rounds left, the medikit's doses (HdBattleHud::counter)
	};
	HdHudPanel(int width, int height, int x = 0, int y = 0) : InteractiveSurface(width, height, x, y) {}
	~HdHudPanel() override;
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

/**
 * The arrow on a small tab at the top of the battle's panel (oxceHdPanelHide): a click slides the panel down off
 * the screen, and the tab, gone down with it to the screen's edge, then points up to bring it back. Drawn in the
 * world layer only (the classic surface stays empty) and only while the panel is the modern one.
 */
class HdPanelToggle : public InteractiveSurface
{
public:
	HdPanelToggle(int width, int height, int x = 0, int y = 0) : InteractiveSurface(width, height, x, y) {}
	/// The panel is down: the arrow points up.
	void setDown(bool down) { _down = down; }
	void hdMirror() override;
private:
	bool _down = false;
};

/**
 * The mark of the enemy's and the neutrals' turn (oxceHdEnemyTurn), as big as the screen and drawn in the world
 * layer only (its classic surface stays empty, nothing under it takes the mouse): a plate with a line of text at
 * the top, over the hidden movement screen (mode 1), or a soft frame along the screen's edge, red for the enemy
 * and yellow for the neutrals, drawn by code (mode 2). Picture only.
 */
class HdTurnMark : public Surface
{
public:
	enum Kind { NONE, STRIP, FRAME_ENEMY, FRAME_NEUTRAL };
	HdTurnMark(int width, int height) : Surface(width, height, 0, 0) {}
	void setKind(Kind kind) { _kind = kind; }
	Kind getKind() const { return _kind; }
	void setText(const std::string &text) { _text = text; }
	void hdMirror() override;
private:
	Kind _kind = NONE;
	std::string _text;
};

}
