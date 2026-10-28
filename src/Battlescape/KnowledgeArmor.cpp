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
#include "KnowledgeArmor.h"
#include <algorithm>
#include "../Engine/Options.h"
#include "../Mod/Armor.h"
#include "../Mod/ArticleDefinition.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleDamageType.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "../Ufopaedia/Ufopaedia.h"

namespace OpenXcom
{

namespace KnowledgeArmor
{

Counts counts;

namespace
{

/// The article of this name is there and open to the player.
bool isOpen(const Mod *mod, SavedGame *geo, const std::string &name)
{
	ArticleDefinition *article = mod->getUfopaediaArticle(name, false);
	return article && Ufopaedia::isArticleAvailable(geo, article);
}

/// The item has an article the player can ever read (not in the hidden section), and it is still closed. An item with
/// no article at all (built-in weapons, ammo described by its weapon) is never unknown: it cannot be researched.
bool isUnknown(const Mod *mod, SavedGame *geo, const BattleItem *item)
{
	ArticleDefinition *article = mod->getUfopaediaArticle(item->getRules()->getUfopediaType(), false);
	return article && article->section != UFOPAEDIA_NOT_AVAILABLE && !Ufopaedia::isArticleAvailable(geo, article);
}

}

float effectiveness(const RuleDamageType *type, const BattleUnit *attacker, const BattleItem *weapon, const BattleItem *ammo,
	const BattleUnit *target, const SavedBattleGame *save, Counts *count)
{
	const float base = type->ArmorEffectiveness;
	if (!Options::oxceKnowledgeArmor || base <= 0.0f || !attacker || !target || !save || !save->getGeoscapeSave())
	{
		return base;
	}
	const Mod *mod = save->getMod();
	SavedGame *geo = save->getGeoscapeSave();
	const KnowledgeArmorRules &rules = mod->getKnowledgeArmor();
	float shift = 0.0f;
	if (attacker->getFaction() == FACTION_PLAYER)
	{
		if (target->getOriginalFaction() == FACTION_HOSTILE)
		{
			const Armor *armor = target->getArmor();
			if (isOpen(mod, geo, armor->getType()) || isOpen(mod, geo, armor->getUfopediaType()))
			{
				shift -= rules.knownEnemy;
				if (count)
					++count->known;
			}
		}
		// the weapon and its ammo give one penalty between them
		if ((weapon && isUnknown(mod, geo, weapon)) || (ammo && ammo != weapon && isUnknown(mod, geo, ammo)))
		{
			shift += rules.unknownWeapon;
			if (count)
				++count->unknown;
		}
	}
	else if (attacker->getFaction() == FACTION_HOSTILE && attacker->getOriginalFaction() == FACTION_HOSTILE
		&& target->getOriginalFaction() == FACTION_PLAYER)
	{
		const std::vector<int> &byDifficulty = rules.difficultyIntelligence;
		const int difficulty = (int)geo->getDifficulty();
		const int intelligence = attacker->getIntelligence()
			+ (difficulty >= 0 && difficulty < (int)byDifficulty.size() ? byDifficulty[difficulty] : 0);
		const int above = intelligence - rules.intelligencePivot;
		if (above != 0)
		{
			shift -= rules.intelligenceStep * above;
			if (count)
				++count->mirror;
		}
	}
	if (shift == 0.0f)
	{
		return base;
	}
	return std::max(0.0f, base + shift);
}

}

}
