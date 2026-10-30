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
#include "OptionsButtonFaceState.h"
#include <algorithm>
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/HdBattleHud.h"
#include "../Engine/HdUi.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/Slider.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

namespace
{

/// A button of the kaleidoscope: cast in its own relief whatever the option says (0 = the flat button as before).
class FaceTile : public TextButton
{
public:
	FaceTile(int face, int width, int height, int x, int y) : TextButton(width, height, x, y), _face(face) {}
	void hdMirror() override
	{
		HdUi::setFaceOverride(_face);
		TextButton::hdMirror();
		HdUi::setFaceOverride(-1);
	}
private:
	int _face;
};

const char *const FACE[12] = { "STR_HD_FACE_FLAT", "STR_HD_FACE_SMOOTH", "STR_HD_FACE_BRUSHED", "STR_HD_FACE_CAST",
	"STR_HD_FACE_HAMMERED", "STR_HD_FACE_RIVETED", "STR_HD_FACE_SCALES", "STR_HD_FACE_TREAD", "STR_HD_FACE_CARBON",
	"STR_HD_FACE_WOOD", "STR_HD_FACE_LIGHTNING", "STR_HD_FACE_WORN" };
const char *const SHAPE[3] = { "STR_HD_SHAPE_PLATE", "STR_HD_SHAPE_PILLOW", "STR_HD_SHAPE_RECESSED" };
/// What Reset sets: the flat button as before, a plate, a little gloss (the same as the options' defaults, Options.cpp).
const int START[5] = { 0, 0, 40, 0, 50 };

}

/**
 * Initializes all the elements in the Buttons' Look window.
 * @param origin Game section that originated this state.
 */
OptionsButtonFaceState::OptionsButtonFaceState(OptionsOrigin origin) : _faceSel(0), _shapeSel(0)
{
	_screen = false;

	_was[0] = Options::oxceHdButtonFace;
	_was[1] = Options::oxceHdButtonShape;
	_was[2] = Options::oxceHdButtonGloss;
	_was[3] = Options::oxceHdButtonInkHue;
	_was[4] = Options::oxceHdButtonInkLight;

	// Create objects
	_window = new Window(this, 288, 180, 16, 10, POPUP_BOTH);
	_txtTitle = new Text(264, 17, 28, 18);
	for (int i = 0; i < 12; ++i)
	{
		_btnFace[i] = new FaceTile(i, 63, 16, 28 + (i % 4) * 67, 38 + (i / 4) * 19);
	}
	for (int i = 0; i < 3; ++i)
	{
		_btnShape[i] = new TextButton(86, 16, 28 + i * 89, 96);
	}
	// three rows, each a label and a slider: the gloss, the letters' hue and brightness (XP-000411)
	_txtGloss = new Text(120, 9, 28, 119);
	_slrGloss = new Slider(140, 16, 152, 115);
	_txtInkHue = new Text(120, 9, 28, 136);
	_slrInkHue = new Slider(140, 16, 152, 132);
	_txtInkLight = new Text(120, 9, 28, 153);
	_slrInkLight = new Slider(140, 16, 152, 149);
	_btnOk = new TextButton(80, 16, 28, 170);
	_btnCancel = new TextButton(80, 16, 120, 170);
	_btnReset = new TextButton(80, 16, 212, 170);

	// Set palette
	setInterface("optionsMenu", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	add(_window, "confirmVideo", "optionsMenu");
	add(_txtTitle, "confirmVideo", "optionsMenu");
	for (int i = 0; i < 12; ++i)
	{
		add(_btnFace[i], "button", "optionsMenu");
	}
	for (int i = 0; i < 3; ++i)
	{
		add(_btnShape[i], "button", "optionsMenu");
	}
	add(_txtGloss, "confirmVideo", "optionsMenu");
	add(_slrGloss, "button", "optionsMenu");
	add(_txtInkHue, "confirmVideo", "optionsMenu");
	add(_slrInkHue, "button", "optionsMenu");
	add(_txtInkLight, "confirmVideo", "optionsMenu");
	add(_slrInkLight, "button", "optionsMenu");
	add(_btnOk, "button", "optionsMenu");
	add(_btnCancel, "button", "optionsMenu");
	add(_btnReset, "button", "optionsMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "optionsMenu");

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText(tr("STR_HD_BUTTON_FACE_TITLE"));

	for (int i = 0; i < 12; ++i)
	{
		_btnFace[i]->setText(tr(FACE[i]));
		_btnFace[i]->setGroup(&_faceSel);
		_btnFace[i]->onMouseClick((ActionHandler)&OptionsButtonFaceState::btnFaceClick);
	}
	for (int i = 0; i < 3; ++i)
	{
		_btnShape[i]->setText(tr(SHAPE[i]));
		_btnShape[i]->setGroup(&_shapeSel);
		_btnShape[i]->onMouseClick((ActionHandler)&OptionsButtonFaceState::btnShapeClick);
	}

	_slrGloss->setRange(0, 100);
	_slrGloss->onChange((ActionHandler)&OptionsButtonFaceState::slrGlossChange);

	_slrInkHue->setRange(0, 360);
	_slrInkHue->onChange((ActionHandler)&OptionsButtonFaceState::slrInkChange);
	_slrInkLight->setRange(0, 100);
	_slrInkLight->onChange((ActionHandler)&OptionsButtonFaceState::slrInkChange);

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&OptionsButtonFaceState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&OptionsButtonFaceState::btnOkClick, Options::keyOk);

	_btnCancel->setText(tr("STR_CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&OptionsButtonFaceState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&OptionsButtonFaceState::btnCancelClick, Options::keyCancel);

	_btnReset->setText(tr("STR_HD_CUSTOM_RESET"));
	_btnReset->onMouseClick((ActionHandler)&OptionsButtonFaceState::btnResetClick);

	if (origin == OPT_BATTLESCAPE)
	{
		applyBattlescapeTheme("optionsMenu");
	}

	show();
}

/**
 *
 */
OptionsButtonFaceState::~OptionsButtonFaceState()
{

}

/**
 * Puts the options on the buttons, the slider and the label.
 */
void OptionsButtonFaceState::show()
{
	_faceSel = _btnFace[std::min(std::max(Options::oxceHdButtonFace, 0), 11)];
	_shapeSel = _btnShape[std::min(std::max(Options::oxceHdButtonShape, 0), 2)];
	for (int i = 0; i < 12; ++i)
	{
		_btnFace[i]->draw();
	}
	for (int i = 0; i < 3; ++i)
	{
		_btnShape[i]->draw();
	}
	const int gloss = std::min(std::max(Options::oxceHdButtonGloss, 0), 100);
	_slrGloss->setValue(gloss);
	_txtGloss->setText(std::string(tr("STR_HD_BUTTON_GLOSS")) + ": " + std::to_string(gloss) + "%");
	showInk();
}

/**
 * Puts the options of the letters on their sliders and labels; the labels say "auto" at the starting values (the theme picks
 * the letters' colour by the cap), and that the theme of the windows' buttons is needed while it is off - the sliders then
 * keep still.
 */
void OptionsButtonFaceState::showInk()
{
	const int hue = std::min(std::max(Options::oxceHdButtonInkHue, 0), 360);
	const int light = std::min(std::max(Options::oxceHdButtonInkLight, 0), 100);
	_slrInkHue->setValue(hue);
	_slrInkLight->setValue(light);
	const std::string needs = Options::oxceHdWindowTheme ? std::string() : " (" + std::string(tr("STR_HD_BUTTON_INK_NEEDS")) + ")";
	_txtInkHue->setText(std::string(tr("STR_HD_BUTTON_INK_HUE")) + ": " + (hue == 0 ? std::string(tr("STR_HD_BUTTON_INK_AUTO")) : std::to_string(hue)) + needs);
	_txtInkLight->setText(std::string(tr("STR_HD_BUTTON_INK_LIGHT")) + ": " + (light == 50 ? std::string(tr("STR_HD_BUTTON_INK_AUTO")) : std::to_string(light) + "%") + needs);
}

/**
 * Puts the sliders' values in the letters' hue and brightness (the buttons follow at the next frame). Without the theme of
 * the windows' buttons they change nothing, and the sliders go back.
 * @param action Pointer to an action.
 */
void OptionsButtonFaceState::slrInkChange(Action *)
{
	if (Options::oxceHdWindowTheme)
	{
		Options::oxceHdButtonInkHue = _slrInkHue->getValue();
		Options::oxceHdButtonInkLight = _slrInkLight->getValue();
	}
	showInk();
}

/**
 * Picks the relief of the button clicked.
 * @param action Pointer to an action.
 */
void OptionsButtonFaceState::btnFaceClick(Action *action)
{
	for (int i = 0; i < 12; ++i)
	{
		if (action->getSender() == _btnFace[i]) Options::oxceHdButtonFace = i;
	}
	show();
}

/**
 * Picks the shape of the button clicked.
 * @param action Pointer to an action.
 */
void OptionsButtonFaceState::btnShapeClick(Action *action)
{
	for (int i = 0; i < 3; ++i)
	{
		if (action->getSender() == _btnShape[i]) Options::oxceHdButtonShape = i;
	}
	show();
}

/**
 * Puts the slider's value in the gloss (the buttons follow at the next frame) and the label.
 * @param action Pointer to an action.
 */
void OptionsButtonFaceState::slrGlossChange(Action *)
{
	Options::oxceHdButtonGloss = _slrGloss->getValue();
	_txtGloss->setText(std::string(tr("STR_HD_BUTTON_GLOSS")) + ": " + std::to_string(Options::oxceHdButtonGloss) + "%");
}

/**
 * Keeps the look.
 * @param action Pointer to an action.
 */
void OptionsButtonFaceState::btnOkClick(Action *)
{
	_game->popState();
}

/**
 * Gives back the look the player had.
 * @param action Pointer to an action.
 */
void OptionsButtonFaceState::btnCancelClick(Action *)
{
	Options::oxceHdButtonFace = _was[0];
	Options::oxceHdButtonShape = _was[1];
	Options::oxceHdButtonGloss = _was[2];
	Options::oxceHdButtonInkHue = _was[3];
	Options::oxceHdButtonInkLight = _was[4];
	_game->popState();
}

/**
 * Sets the starting look (the flat button as before).
 * @param action Pointer to an action.
 */
void OptionsButtonFaceState::btnResetClick(Action *)
{
	Options::oxceHdButtonFace = START[0];
	Options::oxceHdButtonShape = START[1];
	Options::oxceHdButtonGloss = START[2];
	Options::oxceHdButtonInkHue = START[3];
	Options::oxceHdButtonInkLight = START[4];
	show();
}

}
