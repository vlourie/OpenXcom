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

namespace OpenXcom
{

class BattleItem;
class BattleUnit;
class RuleDamageType;
class SavedBattleGame;

/**
 * Knowledge armor (option oxceKnowledgeArmor, off by default; Dioxine's proposal, docs/research/knowledge-armor-2026-10-28.md):
 * what the player has researched and how clever the enemy is change how well armor stops a hit. The damage type's
 * armor effectiveness is shifted before BattleUnit::damage subtracts the armor:
 * - the player's side hits an enemy whose armor article (by the armor's name or its ufopediaType) is open: -knownEnemy;
 * - the player's side hits with a weapon, or else its separate ammo, whose article exists, is not hidden
 *   (STR_NOT_AVAILABLE) and is still closed: +unknownWeapon, once;
 * - an enemy hits the player's unit: -intelligenceStep per point of its intelligence, plus the difficulty's shift,
 *   above intelligencePivot (and + below it).
 * The numbers are the ruleset's knowledgeArmor (Mod::getKnowledgeArmor). The AI estimates its hits with the same function.
 */
namespace KnowledgeArmor
{

/// How many hits each case changed (only the calls that pass it count; the AI stand logs them as [AIKNOWARMOR]).
struct Counts
{
	int known = 0, unknown = 0, mirror = 0;
};
extern Counts counts;

/// The armor effectiveness this attack meets: the damage type's own with the option off, for a type that ignores armor
/// (0 or less) or without an attacker; never below 0.
float effectiveness(const RuleDamageType *type, const BattleUnit *attacker, const BattleItem *weapon, const BattleItem *ammo,
	const BattleUnit *target, const SavedBattleGame *save, Counts *count = nullptr);

}

}
