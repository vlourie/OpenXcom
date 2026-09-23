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
#include <string>
#include <utility>

namespace OpenXcom
{

class Window;
class Text;
class TextButton;
class TextList;

/**
 * One setting of an options list on a window of its own: the name, the value and the
 * whole description in a scrolling list. Opened with the middle mouse button on a
 * setting, because the tooltip line under the list cuts long descriptions off.
 * The value is a button that changes the setting exactly as a click on the list does.
 */
class OptionDetailState : public State
{
public:
	/// Changes the setting as a click with this mouse button on its list row would
	/// (0: leaves it as it is) and returns its value text and color (0: the default one).
	typedef std::function<std::pair<std::string, Uint8>(Uint8 button)> Changer;
private:
	Window *_window;
	Text *_txtTitle;
	TextButton *_btnValue;
	TextList *_lstDesc;
	TextButton *_btnOk;
	Changer _changer;
	Uint8 _valueColor;
	/// Shows what the changer returns.
	void showValue(const std::pair<std::string, Uint8> &value);
public:
	/// Creates the Option Detail state.
	OptionDetailState(OptionsOrigin origin, const std::string &name, const std::string &desc, Changer changer);
	/// Cleans up the Option Detail state.
	~OptionDetailState();
	/// Handler for clicking the value.
	void btnValueClick(Action *action);
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
};

}
