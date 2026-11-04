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
#include <string>
#include <vector>
#include "../Engine/State.h"
#include "OptionsBaseState.h"

namespace OpenXcom
{

class Window;
class Text;
class TextButton;
class TextList;

/**
 * The window "Themes of the screens" (XP-000484, stage 2; the engine is Engine/HdScreenThemes): the tree of the screens as a
 * list, the groups (menu, geoscape, basescape...) opening to their screens. Each row shows the screen's name and whether it
 * has a theme of its own or takes its parent's. A click on a row opens OptionsScreenThemeEditState for it; the mark at the left
 * of a group opens and closes the group. Opened from the HD options, the interface section.
 */
class OptionsScreenThemesState : public State
{
private:
	struct Row
	{
		std::string screen;
		bool group;   ///< has screens under it (the mark at the left opens them): a group, or a screen with sub-screens
	};
	OptionsOrigin _origin;
	Window *_window;
	Text *_txtTitle, *_txtHint;
	TextList *_lstScreens;
	TextButton *_btnOk;
	std::vector<Row> _rows;
	Uint8 _colorGroup, _greyedOutColor;
	/// The list as the tree and the records stand now.
	void fillList();
	std::string stateText(const std::string &screen) const;
public:
	OptionsScreenThemesState(OptionsOrigin origin);
	~OptionsScreenThemesState();
	/// Fills the list again (after an edit).
	void init() override;
	/// Handler for clicking a row.
	void lstScreensClick(Action *action);
	/// Handler for clicking OK.
	void btnOkClick(Action *action);
};

/**
 * The window of one screen's theme: the colour of the windows' buttons and frames from a list (the last row, the own colour, opens
 * OptionsCustomColorState), the buttons' look (OptionsButtonFaceState) and letters (OptionsButtonInkState), and "As the parent".
 * Those windows work on the options, so for the time of this one the options hold the screen's theme (HdScreenThemes::beginEdit):
 * what is on screen is a sample of it. OK writes the screen's record to hd_screen_themes.yml, Cancel (and anything that closes the
 * window) gives the options back as they were.
 */
class OptionsScreenThemeEditState : public State
{
private:
	OptionsOrigin _origin;
	std::string _name;
	Window *_window;
	Text *_txtTitle, *_txtParent, *_txtState;
	TextList *_lstColor;
	TextButton *_btnCustom, *_btnFace, *_btnInk, *_btnParent, *_btnOk, *_btnCancel;
	Uint8 _colorGroup;
	/// Shows the options on the list and the state line.
	void show();
public:
	OptionsScreenThemeEditState(OptionsOrigin origin, const std::string &screen);
	~OptionsScreenThemeEditState();
	void init() override;
	/// Handler for clicking a colour.
	void lstColorClick(Action *action);
	void btnCustomClick(Action *action);
	void btnFaceClick(Action *action);
	void btnInkClick(Action *action);
	void btnParentClick(Action *action);
	void btnOkClick(Action *action);
	void btnCancelClick(Action *action);
};

}
