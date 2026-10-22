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
#include "OptionsBaseState.h"
#include <vector>
#include "../Engine/OptionInfo.h"

namespace OpenXcom
{

class TextList;
class TextButton;

/**
 * The HD tab of the options: every setting of the HD layer in one place, in six tabs
 * (graphics, battle, interface, geoscape and base, AI and rules, speed), grouped inside
 * each. The settings are the options whose category starts with STR_HD_ (Options.cpp);
 * the art version is one row over two options, oxceHdMode and oxceAdultArt. See docs/HD_MENU.md.
 */
class OptionsHdState : public OptionsBaseState
{
private:
	struct Group
	{
		std::string title;
		std::vector<OptionInfo> settings;
		/// The tab the group is on.
		int tab;
	};
	/// What a row of the list is: a header or a blank (-1), the art version (-2) or a setting.
	struct Row
	{
		int group, index;
	};
	TextList *_lstOptions;
	/// The tabs over the list and the one pressed (TextButton::setGroup moves it).
	std::vector<TextButton*> _btnTabs;
	TextButton *_tab;
	std::vector<Group> _groups;
	std::vector<Row> _rows;
	Uint8 _colorGroup, _greyedOutColor;
	/// Is the adult art tree shipped at all? Without it the art version is only classic or HD.
	bool _adultShipped;
	/// Is there HD art for this game in the active mods (Mod::hasHdArt)? Without it the settings change nothing.
	bool _hdActive;
	/// The BetterAI screen (the first row opens it): the list shows only the AI group, its switch first.
	bool _betterAiView;
	/// The AI group's index in _groups (-1: none); the main list leaves it out.
	int _aiGroup;

	/// The index of the tab pressed last.
	int currentTab() const;
	/// Is this setting grey under the BetterAI switch (an AI row while the switch is off)?
	bool aiLocks(const OptionInfo &info) const;

	void addRow(int group, int index, const std::string &name, const std::string &value);
	std::string valueText(const OptionInfo &info) const;
	Uint8 valueColor(const OptionInfo &info) const;
	/// Is this setting fixed while the tab is open from a battle (the battle saves rule)?
	bool battleLocks(const OptionInfo &info) const;
	/// Opens the row's setting on a window of its own (middle button).
	void showDetail(size_t sel);
	/// Changes the setting of a row as a click on it does.
	void changeSetting(size_t sel, Uint8 button);
	std::string rowDescription(size_t sel) const;
	std::string artText() const;
	void cycleArt(int increment);
public:
	/// Creates the HD Options state.
	OptionsHdState(OptionsOrigin origin);
	/// Cleans up the HD Options state.
	~OptionsHdState();
	/// Fills settings list.
	void init() override;
	/// Fills the settings list.
	void updateList();
	/// Handler for pressing a tab.
	void btnTabPress(Action *action);
	/// Handler for clicking a setting on the list.
	void lstOptionsClick(Action *action);
	/// Handler for moving the mouse over a setting.
	void lstOptionsMouseOver(Action *action);
	/// Handler for moving the mouse outside the settings.
	void lstOptionsMouseOut(Action *action);
};

}
