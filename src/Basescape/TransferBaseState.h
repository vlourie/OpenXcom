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
#include <functional>
#include <string>
#include <vector>

namespace OpenXcom
{

class TextButton;
class Window;
class Text;
class TextList;
class Base;
class DebriefingState;

/**
 * Window that lets the player pick the base
 * to transfer items to.
 */
class TransferBaseState : public State
{
private:
	Base *_base;
	DebriefingState *_debriefingState;
	TextButton *_btnCancel;
	Window *_window;
	Text *_txtTitle, *_txtFunds, *_txtName, *_txtArea;
	TextList *_lstBases;
	std::vector<Base*> _bases;
	// the variant with callbacks (a workshop order's delivery, XP-000256): a click calls back instead of opening the transfer screen
	std::function<void(Base*)> _onPick;
	std::function<std::string()> _header;
	std::function<std::string(Base*)> _detail;
	Text *_txtDetail;
	/// Builds the screen (both ways of creating it).
	void build();
	/// Writes the header and the third column of the callback variant anew.
	void refreshDetail();
public:
	/// Creates the Transfer Base state.
	TransferBaseState(Base *base, DebriefingState *debriefingState);
	/// Creates the variant that calls back on a click: the text of the line under the title, the third column of a base, what to do.
	TransferBaseState(Base *base, const std::function<std::string()> &header, const std::function<std::string(Base*)> &detail, const std::function<void(Base*)> &onPick);
	/// Cleans up the Transfer Base state.
	~TransferBaseState();
	/// Refreshes the callback variant when a screen above it closes.
	void init() override;
	/// Handler for clicking the Cancel button.
	void btnCancelClick(Action *action);
	/// Handler for clicking the Bases list.
	void lstBasesClick(Action *action);
};

}
