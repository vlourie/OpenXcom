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
#include "OptionsBaseState.h"
#include <functional>

namespace OpenXcom
{

class Window;
class Text;
class TextButton;
class TextEdit;

/**
 * The password window of the HD lab (Engine/HdLab.h): a word to the captain, a field for the
 * password, OK and Cancel. The right password opens the lab and closes the window; a wrong one
 * says so and leaves the field for another try.
 */
class HdLabPasswordState : public State
{
private:
	Window *_window;
	Text *_txtTitle, *_txtPrompt, *_txtLabel, *_txtWrong;
	TextEdit *_edtPassword;
	TextButton *_btnOk, *_btnCancel;
	std::function<void()> _opened;
	/// Checks the typed password.
	void check();
public:
	/// Creates the password window; `opened` runs once the lab is open.
	HdLabPasswordState(OptionsOrigin origin, std::function<void()> opened);
	/// Cleans up the password window.
	~HdLabPasswordState();
	/// Enter in the field: checks the password (an empty field, Escape too, closes the window).
	void edtPasswordEnter(Action *action);
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the Cancel button.
	void btnCancelClick(Action *action);
};

}
