#pragma once
/*
 * Copyright 2010-2016 OpenXcom Developers.
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
#include "../Engine/TouchState.h"
#include <vector>
#include "SoldierSortUtil.h"
#include "HighlightLowManaSoldiersMixin.h"
#include "SortSoldiersMixin.h"

namespace OpenXcom
{

class TextButton;
class Window;
class Text;
class TextList;
class ComboBox;
class Soldier;
class Craft;
class Target;
class RuleStartingCondition;
struct SortFunctor;

/**
 * Select Squad screen that lets the player
 * pick the soldiers to assign to a craft.
 */
class CraftSoldiersState : public SortSoldiersMixin<HighlightLowManaSoldiersMixin<TouchState>>
{
private:
	TextButton *_btnOk;
	TextButton *_btnPreview;
	TextButton *_btnFit; // OXCE-HD (oxceHdCraftFit): the plate "seats used / seats in all", not pressable
	Window *_window;
	Text *_txtTitle, *_txtName, *_txtRank, *_txtCraft, *_txtAvailable, *_txtUsed;
	ComboBox *_cbxSortBy;
	TextList *_lstSoldiers;

	size_t _craft;
	Uint8 _otherCraftColor;
	std::vector<Soldier *> _origSoldierOrder;
	std::vector<SortFunctor *> _sortFunctors;
	getStatFn_t _dynGetter;
	std::vector<char> _fitGrey; // OXCE-HD (oxceHdCraftFit): the rows now drawn grey, by row of the list
	// OXCE-HD (oxceHdCraftMission): the box "For mission:", the line with the reason; all null with the option off
	ComboBox *_cbxMission = nullptr;
	Text *_txtMissionLabel = nullptr, *_txtMissionInfo = nullptr;
	std::vector<const Target *> _missionTargets; // the targets of the box, from item 1 on (item 0 = none)
	bool _missionActive = false; // a target is chosen
	const RuleStartingCondition *_missionRule = nullptr; // its starting condition (null = none)
	std::string _missionLine; // the line under the list when the mouse is not over a row
	/// OXCE-HD (oxceHdCraftMission): the detected targets (the sources of the UFO tracker) into the box.
	void buildMissionTargets(std::vector<std::string> &names);
	/// OXCE-HD (oxceHdCraftMission): the colour a row has by the craft of the soldier (as initList sets it).
	Uint8 rowBaseColor(const Soldier *s, const Craft *c) const;
	/// OXCE-HD (oxceHdCraftMission): green names of the soldiers who can fly to the chosen target, and the line. Display only.
	void missionRefresh();
	/// OXCE-HD (oxceHdCraftFit): would the click on this soldier meet a craft limit (space, number of units)? Display only.
	bool doesNotFit(const Soldier *s, const Craft *c) const;
	/// OXCE-HD (oxceHdCraftFit): the plate with the seats and the grey rows of those who no longer fit.
	void fitRefresh();
	/// OXCE-HD (oxceHdWoundedRed): the row colours as the base sets them, and the name and the "WOUNDED>days" red for a wounded soldier. Display only.
	void setListRowColor(TextList& list, size_t row, Uint8 color, const Soldier& soldier);
	/// initializes the display list based on the craft soldier's list and the position to display
	void initList(size_t scrl);
public:
	/// Creates the Craft Soldiers state.
	CraftSoldiersState(Base *base, size_t craft);
	/// Cleans up the Craft Soldiers state.
	~CraftSoldiersState();
	/// Handler for changing the sort by combobox.
	void cbxSortByChange(Action *action);
	/// OXCE-HD (oxceHdCraftMission): handler for changing the "For mission:" combobox.
	void cbxMissionChange(Action *action);
	/// OXCE-HD (oxceHdCraftMission): the reason for the soldier under the mouse in the line under the list.
	void lstSoldiersMouseOver(Action *action);
	void lstSoldiersMouseOut(Action *action);
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the Preview button.
	void btnPreviewClick(Action *action);
	/// Updates the soldiers list.
	void init() override;
	/// Handler for clicking the Soldiers reordering button.
	void lstItemsLeftArrowClick(Action *action);
	/// Moves a soldier up.
	void moveSoldierUp(Action *action, unsigned int row, bool max = false);
	/// Handler for clicking the Soldiers reordering button.
	void lstItemsRightArrowClick(Action *action);
	/// Moves a soldier down.
	void moveSoldierDown(Action *action, unsigned int row, bool max = false);
	/// Handler for clicking the Soldiers list.
	void lstSoldiersClick(Action *action);
	/// Handler for pressing-down a mouse-button in the list.
	void lstSoldiersMousePress(Action *action);
	/// Handler for clicking the De-assign All Soldiers button.
	void btnDeassignAllSoldiersClick(Action *action);
	void btnDeassignCraftSoldiersClick(Action *action);
};

}
