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

namespace OpenXcom
{

class Window;
class Text;
class TextButton;
class Slider;
class Surface;

/**
 * The window "Own colour" (HD interface, modern skin, XP-000377): the player's own colour of the battle panel
 * (oxceHdBattleHudColor 9) from two colours, the buttons' and the background's, each by hue, saturation and value
 * on three sliders, with a sample of the panel under them that follows the sliders. The colour is the
 * battle panel's, so the windows' buttons take it too when oxceHdWindowTheme is on.
 * Opened from the HD options. While it is open the own colour is the panel's colour, so that everything shows it;
 * OK keeps what was set, Cancel gives back the colours the player had, Reset sets the starting ones.
 */
class OptionsCustomColorState : public State
{
private:
	Window *_window;
	Text *_txtTitle, *_txtKeys, *_txtBack;
	Text *_txtValue[6];
	Slider *_slr[6];
	Surface *_sample;
	TextButton *_btnOk, *_btnCancel, *_btnReset;
	/// What the options were when the window opened: the panel's colour, then the six values of the own colour.
	int _was[7];
	/// Writes the sliders' values to the options and the labels.
	void apply();
	/// Shows the options on the sliders and the labels.
	void show();
public:
	/// Creates the window.
	OptionsCustomColorState(OptionsOrigin origin);
	~OptionsCustomColorState();
	/// Handler for moving a slider.
	void slrChange(Action *action);
	/// Handler for clicking OK.
	void btnOkClick(Action *action);
	/// Handler for clicking Cancel.
	void btnCancelClick(Action *action);
	/// Handler for clicking Reset.
	void btnResetClick(Action *action);
};

}
