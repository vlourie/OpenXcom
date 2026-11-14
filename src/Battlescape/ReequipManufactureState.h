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
#include "../Engine/State.h"
#include <string>
#include <vector>

namespace OpenXcom
{

class TextButton;
class Window;
class Text;
class TextList;
class Base;
class RuleManufacture;
class Production;

/**
 * OXCE-HD (XP-000573): where to manufacture an item missing after a mission - every base with each researched
 * project that makes it, why a base can't (no facility, no materials, little work space) and its free engineers.
 * A click opens the usual production screens of that base: nothing is started here, the player does it there.
 */
class ReequipManufactureState : public State
{
private:
	struct Choice { Base *base; RuleManufacture *rule; Production *running; bool open; };
	std::string _item;
	Base *_home;
	std::vector<Choice> _choices;

	TextButton *_btnCancel;
	Window *_window;
	Text *_txtTitle, *_txtBase, *_txtState, *_txtNone;
	TextList *_lstBases;
public:
	/// Creates the screen for the missing item `item`; `home` is the base the craft is at (it goes first).
	ReequipManufactureState(const std::string &item, Base *home);
	~ReequipManufactureState();
	/// Fills the list again (after coming back from the production screens).
	void init() override;
	/// Returns to the list of missing items.
	void btnCancelClick(Action *action);
	/// Opens the production of the clicked base.
	void lstBasesClick(Action *action);
};

}
