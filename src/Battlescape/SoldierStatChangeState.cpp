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
#include "SoldierStatChangeState.h"
#include <algorithm>
#include <sstream>
#include "../Engine/Game.h"
#include "../Engine/Action.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/InteractiveSurface.h"
#include "../Engine/Options.h"
#include "../Engine/Surface.h"
#include "../Engine/SurfaceSet.h"
#include "../Interface/Bar.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Mod/Armor.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleInterface.h"
#include "../Mod/RuleSoldierBonus.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Soldier.h"

namespace OpenXcom
{

/**
 * Same formula as Soldier::prepareStatsWithBonuses() + BattleUnit::updateArmorFromSoldier(),
 * but with an explicit armor and without touching the soldier's cached stats.
 */
SoldierStatSnapshot SoldierStatSnapshot::capture(const Mod *mod, Soldier *soldier, bool preBattle)
{
	SoldierStatSnapshot snap;
	snap.rank = soldier->getRankString();

	const Armor *armor = soldier->getArmor();
	if (preBattle)
	{
		// during the mission the geoscape armor can be temporarily swapped
		// (starting condition replacement / enviro transformation), the originals are kept here
		if (soldier->getReplacedArmor())
			armor = soldier->getReplacedArmor();
		else if (soldier->getTransformedArmor())
			armor = soldier->getTransformedArmor();
	}

	UnitStats tmp = *soldier->getCurrentStats();
	const auto *bonuses = soldier->getBonuses(mod); // rebuilds the bonus cache (commendations included)
	for (const auto *bonus : *bonuses)
	{
		tmp += *bonus->getStats();
	}
	// note: like _tmpStatsWithAllBonuses (what BattleUnit uses), the psi skill lock is not applied here
	if (armor)
	{
		tmp += *armor->getStats();
	}
	snap.stats = UnitStats::obeyFixedMinimum(tmp);

	if (armor)
	{
		snap.armor[SIDE_FRONT] = armor->getFrontArmor();
		snap.armor[SIDE_LEFT]  = armor->getLeftSideArmor();
		snap.armor[SIDE_RIGHT] = armor->getRightSideArmor();
		snap.armor[SIDE_REAR]  = armor->getRearArmor();
		snap.armor[SIDE_UNDER] = armor->getUnderArmor();
	}
	for (const auto *bonus : *bonuses)
	{
		snap.armor[SIDE_FRONT] += bonus->getFrontArmor();
		snap.armor[SIDE_LEFT]  += bonus->getLeftSideArmor();
		snap.armor[SIDE_RIGHT] += bonus->getRightSideArmor();
		snap.armor[SIDE_REAR]  += bonus->getRearArmor();
		snap.armor[SIDE_UNDER] += bonus->getUnderArmor();
	}
	for (int i = 0; i < SIDE_MAX; ++i)
	{
		snap.armor[i] = std::max(0, snap.armor[i]);
	}
	return snap;
}

int SoldierStatChangeState::findSoldier(const SoldierStatChangeList &list, const Soldier *soldier)
{
	for (size_t i = 0; i < list.size(); ++i)
	{
		if (list[i].soldier == soldier && list[i].done)
			return (int)i;
	}
	return -1;
}

/**
 * Initializes all the elements of the screen.
 * @param list Stat changes of all soldiers of the mission.
 * @param index Entry to show first.
 */
SoldierStatChangeState::SoldierStatChangeState(std::shared_ptr<SoldierStatChangeList> list, size_t index) :
	_list(list), _index(index), _manaEnabled(false), _colorUp(0), _colorDown(0)
{
	_manaEnabled = _game->getMod()->isManaFeatureEnabled();
	RuleInterface *ruleStats = _game->getMod()->getInterface("stats");

	_bg = new Surface(320, 200, 0, 0);
	_exit = new InteractiveSurface(320, 180, 0, 20);
	_txtName = new Text(288, 17, 16, 4);
	_txtRank = new Text(150, 9, 8, 21); // left part only: mods draw the bar scale to the right of it
	_btnPrev = new TextButton(14, 18, 2, 2);
	_btnNext = new TextButton(14, 18, 304, 2);

	// same row positions as the battlescape Unit Info screen (mod backgrounds are drawn for them);
	// the battle-only rows are reused: fatal wounds -> wound recovery, morale -> empty
	const int step = 9;
	const int yStart = _manaEnabled ? 30 : 38;
	auto slotOf = [&](int row) -> int
	{
		static const int slots[R_COUNT] = { 0, 1, 2, 4, 6, 7, 8, 9, 10, 11, 11, 12, 13, 14, 15, 16, 17 };
		int slot = slots[row];
		if (_manaEnabled && row > R_MANA) slot += 1;
		return slot;
	};
	for (int i = 0; i < R_COUNT; ++i)
	{
		if (i == R_MANA && !_manaEnabled)
		{
			_rows[i] = Row{ nullptr, nullptr, nullptr, nullptr };
			continue;
		}
		int yPos = yStart + slotOf(i) * step;
		_rows[i].txt = new Text(140, 9, 8, yPos);
		_rows[i].diff = new Text(34, 9, 114, yPos);
		_rows[i].num = new Text(18, 9, 150, yPos);
		_rows[i].bar = new Bar(150, 5, 170, yPos + 1);
	}
	_txtRecovery = new Text(300, 9, 8, yStart + 3 * step);

	setStandardPalette("PAL_BATTLESCAPE");

	add(_bg);
	add(_exit);
	add(_txtName, "textName", "stats", 0);
	add(_txtRank, "textName", "stats", 0);

	static const char *barIds[R_COUNT] = {
		"barTUs", "barEnergy", "barHealth", "barBravery", "barReactions", "barFiring", "barThrowing", "barMelee", "barStrength", "barMana",
		"barPsiStrength", "barPsiSkill", "barFrontArmor", "barLeftArmor", "barRightArmor", "barRearArmor", "barUnderArmor" };
	static const char *labels[R_COUNT] = {
		"STR_TIME_UNITS", "STR_ENERGY", "STR_HEALTH", "STR_BRAVERY", "STR_REACTIONS", "STR_FIRING_ACCURACY", "STR_THROWING_ACCURACY",
		"STR_MELEE_ACCURACY", "STR_STRENGTH", "STR_MANA", "STR_PSIONIC_STRENGTH", "STR_PSIONIC_SKILL",
		"STR_FRONT_ARMOR_UC", "STR_LEFT_ARMOR_UC", "STR_RIGHT_ARMOR_UC", "STR_REAR_ARMOR_UC", "STR_UNDER_ARMOR_UC" };

	for (int i = 0; i < R_COUNT; ++i)
	{
		if (!_rows[i].txt) continue;
		add(_rows[i].txt);
		add(_rows[i].diff);
		add(_rows[i].num);
		add(_rows[i].bar, barIds[i], "stats", 0);
	}
	add(_txtRecovery);
	add(_btnPrev, "button", "stats");
	add(_btnNext, "button", "stats");

	centerAllSurfaces();

	_game->getMod()->getSurface("UNIBORD.PCK")->blitNShade(_bg, 0, 0);

	_exit->onMouseClick((ActionHandler)&SoldierStatChangeState::exitClick);
	_exit->onKeyboardPress((ActionHandler)&SoldierStatChangeState::exitClick, Options::keyCancel);
	_exit->onKeyboardPress((ActionHandler)&SoldierStatChangeState::exitClick, Options::keyOk);
	_exit->onKeyboardPress((ActionHandler)&SoldierStatChangeState::exitClick, Options::keyBattleStats);

	Uint8 color = ruleStats->getElement("text")->color;
	Uint8 color2 = ruleStats->getElement("text")->color2;
	_colorUp = ruleStats->getElement("barTUs")->color;
	_colorDown = ruleStats->getElement("barHealth")->color;

	_txtName->setAlign(ALIGN_CENTER);
	_txtName->setBig();
	_txtName->setHighContrast(true);

	_txtRank->setHighContrast(true);

	_txtRecovery->setColor(_colorDown);
	_txtRecovery->setHighContrast(true);

	for (int i = 0; i < R_COUNT; ++i)
	{
		if (!_rows[i].txt) continue;
		_rows[i].txt->setColor(color);
		_rows[i].txt->setHighContrast(true);
		_rows[i].txt->setText(tr(labels[i]));
		_rows[i].diff->setHighContrast(true);
		_rows[i].diff->setAlign(ALIGN_RIGHT);
		_rows[i].num->setColor(color2);
		_rows[i].num->setHighContrast(true);
		_rows[i].bar->setScale(1.0);
	}

	_btnPrev->setText("<<");
	_btnPrev->onMouseClick((ActionHandler)&SoldierStatChangeState::btnPrevClick);
	_btnPrev->onKeyboardPress((ActionHandler)&SoldierStatChangeState::btnPrevClick, Options::keyBattlePrevUnit);
	_btnPrev->onKeyboardPress((ActionHandler)&SoldierStatChangeState::btnPrevClick, Options::keyGeoLeft);
	_btnNext->setText(">>");
	_btnNext->onMouseClick((ActionHandler)&SoldierStatChangeState::btnNextClick);
	_btnNext->onKeyboardPress((ActionHandler)&SoldierStatChangeState::btnNextClick, Options::keyBattleNextUnit);
	_btnNext->onKeyboardPress((ActionHandler)&SoldierStatChangeState::btnNextClick, Options::keyGeoRight);
	bool several = _list->size() > 1;
	_btnPrev->setVisible(several);
	_btnNext->setVisible(several);
}

SoldierStatChangeState::~SoldierStatChangeState()
{
}

/**
 * One stat row: value after the mission, +N/-N against before,
 * bar with the unchanged part in the usual color and the change highlighted.
 */
void SoldierStatChangeState::setRow(RowId id, int before, int after, bool visible)
{
	Row &r = _rows[id];
	if (!r.txt) return;
	r.txt->setVisible(visible);
	r.diff->setVisible(visible);
	r.num->setVisible(visible);
	r.bar->setVisible(visible);
	if (!visible) return;

	Uint8 numColor = _game->getMod()->getInterface("stats")->getElement("text")->color2;
	int delta = after - before;
	std::ostringstream ss;
	ss << after;
	r.num->setText(ss.str());

	ss.str("");
	if (delta > 0)
	{
		ss << '+' << delta;
		r.diff->setColor(_colorUp);
		r.num->setColor(_colorUp);
	}
	else if (delta < 0)
	{
		ss << delta;
		r.diff->setColor(_colorDown);
		r.num->setColor(_colorDown);
	}
	else
	{
		r.num->setColor(numColor);
	}
	r.diff->setText(ss.str());

	// unchanged part = bar color on top, changed part = second color below it
	Uint8 barColor = _game->getMod()->getInterface("stats")->getElement(
		id == R_TU ? "barTUs" : id == R_ENERGY ? "barEnergy" : id == R_HEALTH ? "barHealth" :
		id == R_BRAVERY ? "barBravery" : id == R_REACTIONS ? "barReactions" : id == R_FIRING ? "barFiring" :
		id == R_THROWING ? "barThrowing" : id == R_MELEE ? "barMelee" : id == R_STRENGTH ? "barStrength" :
		id == R_MANA ? "barMana" : id == R_PSI_STRENGTH ? "barPsiStrength" : id == R_PSI_SKILL ? "barPsiSkill" :
		id == R_ARMOR_FRONT ? "barFrontArmor" : id == R_ARMOR_LEFT ? "barLeftArmor" : id == R_ARMOR_RIGHT ? "barRightArmor" :
		id == R_ARMOR_REAR ? "barRearArmor" : "barUnderArmor")->color;
	if (delta == 0)
	{
		r.bar->setColor(barColor);
		r.bar->setSecondaryColor(barColor);
	}
	else
	{
		// palette ramps go from bright to dark: the part that was there before is drawn
		// a few shades darker, the gained part in the normal (bright) bar color,
		// the lost part in dark red
		r.bar->setColor(barColor + 5);
		r.bar->setSecondaryColor(delta > 0 ? barColor : _colorDown + 5);
	}
	r.bar->setBorderColor(barColor + 4);
	r.bar->setSecondValueOnTop(false);
	r.bar->setMax(std::max(0, std::max(before, after)));
	r.bar->setValue(std::max(0, std::min(before, after)));
	r.bar->setValue2(std::max(0, std::max(before, after)));
}

/**
 * Fills the screen for the current soldier.
 */
void SoldierStatChangeState::init()
{
	State::init();
	if (_list->empty())
	{
		return;
	}
	if (_index >= _list->size())
	{
		_index = 0;
	}
	const SoldierStatChange &e = (*_list)[_index];
	const UnitStats &b = e.before.stats;
	const UnitStats &a = e.after.stats;

	std::ostringstream ss;
	ss << tr(e.after.rank) << " " << e.name;
	_txtName->setText(ss.str());

	ss.str("");
	if (e.before.rank != e.after.rank)
	{
		ss << tr(e.before.rank) << "  >>  " << tr(e.after.rank);
	}
	_txtRank->setText(ss.str());

	setRow(R_TU, b.tu, a.tu);
	setRow(R_ENERGY, b.stamina, a.stamina);
	setRow(R_HEALTH, b.health, a.health);
	ss.str("");
	int days = e.soldier ? e.soldier->getWoundRecovery(0.0f, 0.0f) : 0;
	if (days > 0)
	{
		ss << tr("STR_WOUND_RECOVERY").arg(tr("STR_DAY", days));
	}
	_txtRecovery->setText(ss.str());
	setRow(R_BRAVERY, b.bravery, a.bravery);
	setRow(R_REACTIONS, b.reactions, a.reactions);
	setRow(R_FIRING, b.firing, a.firing);
	setRow(R_THROWING, b.throwing, a.throwing);
	setRow(R_MELEE, b.melee, a.melee);
	setRow(R_STRENGTH, b.strength, a.strength);
	if (_manaEnabled)
	{
		setRow(R_MANA, b.mana, a.mana, _game->getSavedGame()->isManaUnlocked(_game->getMod()));
	}

	// same visibility rules as the battlescape Unit Info screen
	int psiSkillWithoutBonuses = e.soldier ? e.soldier->getCurrentStats()->psiSkill : a.psiSkill;
	bool psiStrVisible = psiSkillWithoutBonuses > 0 ||
		(Options::psiStrengthEval && _game->getSavedGame()->isResearched(_game->getMod()->getPsiRequirements()));
	setRow(R_PSI_STRENGTH, b.psiStrength, a.psiStrength, psiStrVisible);
	setRow(R_PSI_SKILL, b.psiSkill, a.psiSkill, psiSkillWithoutBonuses > 0);

	setRow(R_ARMOR_FRONT, e.before.armor[SIDE_FRONT], e.after.armor[SIDE_FRONT]);
	setRow(R_ARMOR_LEFT, e.before.armor[SIDE_LEFT], e.after.armor[SIDE_LEFT]);
	setRow(R_ARMOR_RIGHT, e.before.armor[SIDE_RIGHT], e.after.armor[SIDE_RIGHT]);
	setRow(R_ARMOR_REAR, e.before.armor[SIDE_REAR], e.after.armor[SIDE_REAR]);
	setRow(R_ARMOR_UNDER, e.before.armor[SIDE_UNDER], e.after.armor[SIDE_UNDER]);
}

/**
 * Right click closes, thumb buttons switch soldiers.
 */
void SoldierStatChangeState::handle(Action *action)
{
	State::handle(action);
	if (action->getDetails()->type == SDL_MOUSEBUTTONDOWN)
	{
		if (_game->isRightClick(action))
		{
			exitClick(action);
			return;
		}
		if (Options::oxceThumbButtons)
		{
			if (action->getDetails()->button.button == SDL_BUTTON_X1)
				btnNextClick(action);
			else if (action->getDetails()->button.button == SDL_BUTTON_X2)
				btnPrevClick(action);
		}
	}
}

void SoldierStatChangeState::btnPrevClick(Action *)
{
	if (_list->size() < 2) return;
	_index = (_index + _list->size() - 1) % _list->size();
	init();
}

void SoldierStatChangeState::btnNextClick(Action *)
{
	if (_list->size() < 2) return;
	_index = (_index + 1) % _list->size();
	init();
}

void SoldierStatChangeState::exitClick(Action *)
{
	_game->popState();
}

}
