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
	/// An entry of a group: kind 0 is an option (index in the group's settings), 1 a row of its own (its marker), 2 a merged row.
	struct Item
	{
		int kind, index;
	};
	struct Group
	{
		std::string title;
		std::vector<OptionInfo> settings;
		/// The rows of the group in their order: what each is (an option, a row of its own, a merged one) and its index.
		std::vector<Item> items;
		/// The tab the group is on (-1: on none, the settings of the BetterAI screen).
		int tab;
		/// Is it the HD lab, behind a password?
		bool lab;
	};
	/// What a row of the list is: a header or a blank (-1), a row of its own or a merged one (other negative), or a setting.
	struct Row
	{
		int group, index;
		/// 0: the value is in the row's second column; 1 and 2: a long value, the label row and the row under it that holds the value.
		int pair = 0;
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
	/// Is the main option of this setting off (the setting does nothing for now: its row is grey)?
	bool dependsOff(const OptionInfo &info) const;

	void addRow(int group, int index, const std::string &name, const std::string &value, int pair = 0);
	/// The rows of a setting: one with its short value beside the label, two with a long one under it.
	void addSettingRow(int group, int index, const std::string &label, bool grey);
	/// The same for a value that is known (a merged row's).
	void addValueRow(int group, int index, const std::string &label, const std::string &value, Uint8 color, bool grey);
	/// The merged rows (several options as one row): a value's name, is it fixed by a mod, grey, the color of its value, a step.
	std::string mergedValue(int m, int v) const;
	bool mergedFixed(int m) const;
	bool mergedGrey(int m) const;
	Uint8 mergedColor(int m) const;
	void changeMerged(int m, int increment);
	/// Is the value too long for the column beside the label (the list puts it under the label then)?
	bool longValue(const std::string &value) const;
	/// Writes a setting's value, and its color, in the row (or the pair of rows) the setting is in.
	void setValueCell(size_t sel, const std::string &value, Uint8 color);
	/// The width of the value column: the widest of the short values.
	int _valueWidth = 0;
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
