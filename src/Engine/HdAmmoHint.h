#pragma once
/*
 * Hint: hovering a weapon lights the ammunition that fits it (ticket XP-000257).
 * Interface only: the answer comes from the item rules as they are (RuleItem::getSlotForAmmo covers every
 * ammo slot of a weapon), nothing about the weapon, its ammo or the battle is changed.
 * Option oxceHdAmmoHint, off by default; off = nothing is drawn or recoloured.
 */
#include <SDL.h>
#include "Options.h"
#include "../Mod/RuleItem.h"

namespace OpenXcom
{

namespace HdAmmoHint
{

/// Is the hint switched on?
inline bool enabled()
{
	return Options::oxceHdAmmoHint;
}

/// Does the item `other` fit the weapon `weapon` in any of its ammo slots?
inline bool fits(const RuleItem *weapon, const RuleItem *other)
{
	return weapon && other && weapon != other && weapon->getSlotForAmmo(other) != -1;
}

/// Palette index the matching rows are lit with in the base lists: green of block 3, the one the battle
/// uses for twoHandedGreen (52); 239 showed as black in the Piratez battle palette
const Uint8 COLOR = 52;

}

}
