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

/**
 * The window "Buttons' text" (HD interface, modern skin, XP-000399): the letters of the windows' buttons in the battle panel's
 * metal (oxceHdWindowTheme) get a tone (oxceHdButtonInkTone: auto, light or dark - the last two are forced, and the letters are
 * then not kept readable), a hue (oxceHdButtonInkHue), a saturation (oxceHdButtonInkSat) and a brightness (oxceHdButtonInkLight).
 * The keys of the hue and the brightness are those of XP-000411 (they lived in the window "Buttons' look"). Three samples show
 * the letters in each tone. OK keeps what was set, Cancel gives back what the player had, Reset sets the starting look (auto).
 */
class OptionsButtonInkState : public State
{
private:
	Window *_window;
	Text *_txtTitle, *_txtHue, *_txtSat, *_txtLight;
	TextButton *_btnTone[3], *_btnSample[3];
	TextButton *_toneSel;
	Slider *_slrHue, *_slrSat, *_slrLight;
	TextButton *_btnOk, *_btnCancel, *_btnReset;
	/// What the options were when the window opened: the tone, the hue, the saturation, the brightness.
	int _was[4];
	/// Shows the options on the buttons, the sliders and the labels.
	void show();
public:
	/// Creates the window.
	OptionsButtonInkState(OptionsOrigin origin);
	~OptionsButtonInkState();
	/// Handler for picking a tone.
	void btnToneClick(Action *action);
	/// Handler for moving the sliders.
	void slrChange(Action *action);
	/// Handler for clicking OK.
	void btnOkClick(Action *action);
	/// Handler for clicking Cancel.
	void btnCancelClick(Action *action);
	/// Handler for clicking Reset.
	void btnResetClick(Action *action);
};

}
