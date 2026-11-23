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
#include "../Engine/State.h"
#include "../Mod/Unit.h"
#include <memory>
#include <string>
#include <vector>

namespace OpenXcom
{

class Mod;
class Soldier;
class Text;
class TextButton;
class Bar;
class Surface;
class InteractiveSurface;

/**
 * Effective stats of one soldier (current stats + soldier bonuses + armor),
 * the same numbers the battlescape Unit Info screen is built from.
 */
struct SoldierStatSnapshot
{
	UnitStats stats;
	int armor[SIDE_MAX] = { 0, 0, 0, 0, 0 };
	std::string rank;

	/// Takes the snapshot. preBattle = use the armor the soldier had before
	/// the mission (starting-condition replacement / enviro transformation undone).
	static SoldierStatSnapshot capture(const Mod *mod, Soldier *soldier, bool preBattle);
};

/**
 * Stat change of one soldier over a mission: before (taken when debriefing starts,
 * i.e. before experience, commendations and promotions are applied) and after.
 */
struct SoldierStatChange
{
	Soldier *soldier = nullptr;
	std::string name;
	SoldierStatSnapshot before, after;
	bool done = false; ///< "after" was taken
};

using SoldierStatChangeList = std::vector<SoldierStatChange>;

/**
 * Post-mission screen in the style of the battlescape Unit Info screen:
 * the soldier's stats after the mission with the difference against the stats
 * before the mission (+N / -N) and the gained part of each bar highlighted.
 */
class SoldierStatChangeState : public State
{
private:
	struct Row
	{
		Text *txt, *diff, *num;
		Bar *bar;
	};
	enum RowId { R_TU, R_ENERGY, R_HEALTH, R_BRAVERY, R_REACTIONS, R_FIRING, R_THROWING, R_MELEE, R_STRENGTH, R_MANA,
		R_PSI_STRENGTH, R_PSI_SKILL, R_ARMOR_FRONT, R_ARMOR_LEFT, R_ARMOR_RIGHT, R_ARMOR_REAR, R_ARMOR_UNDER, R_COUNT };

	std::shared_ptr<SoldierStatChangeList> _list;
	size_t _index;
	bool _manaEnabled;
	Uint8 _colorUp, _colorDown;

	Surface *_bg;
	InteractiveSurface *_exit;
	Text *_txtName, *_txtRank, *_txtRecovery;
	TextButton *_btnPrev, *_btnNext;
	Row _rows[R_COUNT];

	void setRow(RowId id, int before, int after, bool visible = true);
public:
	/// Creates the screen for entry `index` of the list.
	SoldierStatChangeState(std::shared_ptr<SoldierStatChangeList> list, size_t index);
	~SoldierStatChangeState();
	/// Fills the screen for the current soldier.
	void init() override;
	/// Right click / thumb buttons.
	void handle(Action *action) override;
	void btnPrevClick(Action *action);
	void btnNextClick(Action *action);
	void exitClick(Action *action);

	/// Finds the list entry of a soldier, or -1.
	static int findSoldier(const SoldierStatChangeList &list, const Soldier *soldier);
};

}
