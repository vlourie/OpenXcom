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
#include <functional>
#include <memory>
#include <string>
#include "HdSprites.h"

namespace OpenXcom
{

class RuleItem;
class BattleItem;
class Surface;
class SurfaceSet;
class SavedBattleGame;

/**
 * HD pictures of the inventory sprites (BIGOBS), chosen per item, not per frame.
 *
 * A mod ships, in hd/BIGOBS.PCK/ (the frame number is the one in the game, after the mod offset):
 *
 *     <frame>.<ITEM TYPE>.png        the picture of that item (two items sharing a frame keep their own)
 *     <frame>.<ITEM TYPE>.hand.png   its version for the 32x48 hand frame (optional)
 *     <frame>.png, <frame>.hand.png  the picture of every item of that frame, shipped only when the
 *                                    pack's builder allowed it (no other user, or the users agreed)
 *
 * The choice goes in two steps. First the picture: the item's own when any file of its own exists, else
 * the frame's common one, else classic; an item with a file of its own never falls back to the common
 * one. Then the version of that picture for where it is shown: the grid takes <picture>.png (only a .hand
 * of its own - classic there); the hand frame takes <picture>.hand.png, else for an item up to 2x3 the
 * grid picture with the usual hand offset, else (3x2, 3x3) classic. Each classic fallback logs one line
 * per type. A picture is a whole number of times bigger than the classic frame (32x48, or the frame's
 * own size) and is scaled to the interface's k. It is drawn clipped to the item's cells (the GRID
 * context: grid, ground) or, in the hand frame (the HAND context: hands, the dragged item, the ammo
 * preview, the battle's hand buttons, Ufopaedia, the alien inventory's hands), to the item's cells after
 * the usual hand offset inside the frame's lines - a .hand picture too; only a 3x2 or 3x3 item, bigger
 * than the frame, gets the whole frame inside its lines.
 *
 * Items whose sprite a script recolours stay classic: the interface has no brightness transfer yet. A mod's
 * recolour scripts can be global (X-Piratez runs its shield script on every item), so what counts is
 * whether the scripts change the frame's pixels now, not whether there are any.
 * Everything is read when first drawn and kept within a memory budget; docs/research/inventory-items-hd.md §9.
 */
namespace HdItems
{
	enum Context { GRID, HAND };

	/// A picture ready to draw: `frame` at k, its top left `dx`, `dy` base pixels from where the classic
	/// sprite goes (GRID: the item's first cell; HAND: the hand frame's top left), clipped to the base
	/// rectangle (`clipX`, `clipY`, `clipW`, `clipH`) relative to the same point.
	struct Pick
	{
		std::shared_ptr<const HdFrame> frame;   ///< kept alive while drawn, even if the cache drops it
		int dx = 0, dy = 0;
		int clipX = 0, clipY = 0, clipW = 0, clipH = 0;
	};

	/// Is the HD interface drawing and has any mod pictures for the inventory sprites?
	bool enabled();
	/// The frame number of a frame of a set (what BattleItem::getBigSprite chose), -1 when it is not one.
	int indexOf(const SurfaceSet *set, const Surface *frame);
	/// The picture of an item in a context at the interface's scale k, or false: draw it classically - also
	/// while a script recolours its sprite (`item` given: the scripts are run on the frame and compared).
	bool pick(const RuleItem *rule, const BattleItem *item, const SavedBattleGame *save, int animFrame,
		int frame, const SurfaceSet *set, Context context, int k, Pick &out);
	/// Draws a picked picture into the world layer: `x`, `y` is where the classic sprite goes (base pixels,
	/// screen coordinates); also clipped to the base rectangle `outer` when its w > 0 (the widget, the window).
	void draw(const Pick &pick, int x, int y, const SDL_Rect &outer);
	/// Draws `pick` with a surface from now on: Surface::blit puts it over the surface's own HD version,
	/// `x`, `y` base pixels from the surface's top left, clipped to the surface. For widgets that keep a
	/// sprite drawn (the ammo preview, the battle's hand buttons, Ufopaedia, the alien inventory).
	void attach(const Surface *surface, const Pick &pick, int x = 0, int y = 0);
	/// Forgets what was attached to a surface: its owner cleared it.
	void detach(const Surface *surface);
	/// Keeps a surface's item sprite right while it lives: when the HD pictures are switched on or off or
	/// change k (enabled(), HdUi::scale()), `redraw` runs just before the surface is next blitted - the owner
	/// draws the sprite again, its HD picture or the classic one. For widgets drawn once (Ufopaedia, the
	/// battle's hand buttons); a picked HD picture leaves the surface's classic pixels out, so without it the
	/// sprite would be missing when HD goes off, or stay at the old k.
	void watch(const Surface *surface, std::function<void()> redraw);
	/// Surface::blit calls it first: runs the surface's `redraw` when the HD state changed since.
	void refresh(const Surface *surface);
	/// Forgets everything about a surface that is going away.
	void forget(const Surface *surface);
	/// Draws what is attached to a surface just blitted onto the screen at its x, y.
	void drawAttached(const Surface *surface);
	/// RuleItem::drawHandSprite's HD version: the item's picture for the hand frame attached to `surface`
	/// (whatever was attached before is dropped), or false: draw it classically. `item` may be null
	/// (Ufopaedia: the rule's own frame).
	bool attachHand(const RuleItem *rule, const BattleItem *item, const SavedBattleGame *save, int animFrame,
		const SurfaceSet *set, const Surface *surface);
	/// A rule's hand sprite on a surface of its own (Ufopaedia): the surface cleared, then the HD picture
	/// attached or the classic sprite drawn, and watched - drawn again when the HD state changes.
	void drawRuleHand(const RuleItem *rule, const SurfaceSet *set, Surface *surface);
	/// Forgets everything (mod reload).
	void clear();
}

}
