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

/**
 * The HD tab of the options: every setting of the HD layer in one place, grouped
 * (art version, battlescape, interface, speed). The settings are the options whose
 * category starts with STR_HD_ (Options.cpp); the art version is one row over two
 * options, oxceHdMode and oxceAdultArt. See docs/HD_MENU.md.
 */
class OptionsHdState : public OptionsBaseState
{
private:
	struct Group
	{
		std::string title;
		std::vector<OptionInfo> settings;
	};
	/// What a row of the list is: a header or a blank (-1), the art version (-2) or a setting.
	struct Row
	{
		int group, index;
	};
	TextList *_lstOptions;
	std::vector<Group> _groups;
	std::vector<Row> _rows;
	Uint8 _colorGroup, _greyedOutColor;
	/// Is the adult art tree shipped at all? Without it the art version is only classic or HD.
	bool _adultShipped;
	/// Is the hd mod active? Without it the settings change nothing.
	bool _hdActive;

	void addRow(int group, int index, const std::string &name, const std::string &value);
	std::string valueText(const OptionInfo &info) const;
	Uint8 valueColor(const OptionInfo &info) const;
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
	/// Handler for clicking a setting on the list.
	void lstOptionsClick(Action *action);
	/// Handler for moving the mouse over a setting.
	void lstOptionsMouseOver(Action *action);
	/// Handler for moving the mouse outside the settings.
	void lstOptionsMouseOut(Action *action);
};

}
