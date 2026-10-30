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

/**
 * The window "Buttons' look" (HD interface, modern skin, XP-000399): the windows' buttons in the battle panel's metal
 * (oxceHdWindowTheme) get a relief (oxceHdButtonFace), a shape (oxceHdButtonShape) and a gloss (oxceHdButtonGloss).
 * The reliefs are a kaleidoscope of buttons, each cast in its own relief; a click picks one, and every button of the
 * window, these included, shows the shape and the gloss at once. OK keeps what was set, Cancel gives back what the
 * player had, Reset sets the starting look (the flat button as before).
 */
class OptionsButtonFaceState : public State
{
private:
	Window *_window;
	Text *_txtTitle, *_txtGloss;
	TextButton *_btnFace[12], *_btnShape[3];
	TextButton *_faceSel, *_shapeSel;
	Slider *_slrGloss;
	TextButton *_btnOk, *_btnCancel, *_btnReset;
	/// What the options were when the window opened: the relief, the shape, the gloss.
	int _was[3];
	/// Shows the options on the buttons, the slider and the label.
	void show();
public:
	/// Creates the window.
	OptionsButtonFaceState(OptionsOrigin origin);
	~OptionsButtonFaceState();
	/// Handler for picking a relief.
	void btnFaceClick(Action *action);
	/// Handler for picking a shape.
	void btnShapeClick(Action *action);
	/// Handler for moving the gloss slider.
	void slrGlossChange(Action *action);
	/// Handler for clicking OK.
	void btnOkClick(Action *action);
	/// Handler for clicking Cancel.
	void btnCancelClick(Action *action);
	/// Handler for clicking Reset.
	void btnResetClick(Action *action);
};

}
