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
#include "OptionsButtonInkState.h"
#include <algorithm>
#include "../Engine/Action.h"
#include "../Engine/Game.h"
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

/// A button of the samples: drawn with the letters in its own tone whatever the option says.
class ToneTile : public TextButton
{
public:
	ToneTile(int tone, int width, int height, int x, int y) : TextButton(width, height, x, y), _tone(tone) {}
	void hdMirror() override
	{
		const int was = Options::oxceHdButtonInkTone;
		Options::oxceHdButtonInkTone = _tone;
		TextButton::hdMirror();
		Options::oxceHdButtonInkTone = was;
	}
private:
	int _tone;
};

const char *const TONE[3] = { "STR_HD_INK_TONE_AUTO", "STR_HD_INK_TONE_LIGHT", "STR_HD_INK_TONE_DARK" };

}

/**
 * Initializes all the elements in the Buttons' Text window.
 * @param origin Game section that originated this state.
 */
OptionsButtonInkState::OptionsButtonInkState(OptionsOrigin origin) : _toneSel(0)
{
	_screen = false;

	_was[0] = Options::oxceHdButtonInkTone;
	_was[1] = Options::oxceHdButtonInkHue;
	_was[2] = Options::oxceHdButtonInkSat;
	_was[3] = Options::oxceHdButtonInkLight;

	// Create objects
	_window = new Window(this, 288, 164, 16, 18, POPUP_BOTH);
	_txtTitle = new Text(264, 17, 28, 26);
	for (int i = 0; i < 3; ++i)
	{
		_btnTone[i] = new TextButton(86, 16, 28 + i * 89, 46);
		_btnSample[i] = new ToneTile(i, 86, 16, 28 + i * 89, 66);
	}
	// three rows, each a label and a slider: the hue, the saturation, the brightness
	_txtHue = new Text(120, 9, 28, 92);
	_slrHue = new Slider(140, 16, 152, 88);
	_txtSat = new Text(120, 9, 28, 109);
	_slrSat = new Slider(140, 16, 152, 105);
	_txtLight = new Text(120, 9, 28, 126);
	_slrLight = new Slider(140, 16, 152, 122);
	_btnOk = new TextButton(80, 16, 28, 148);
	_btnCancel = new TextButton(80, 16, 120, 148);
	_btnReset = new TextButton(80, 16, 212, 148);

	// Set palette
	setInterface("optionsMenu", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	add(_window, "confirmVideo", "optionsMenu");
	add(_txtTitle, "confirmVideo", "optionsMenu");
	for (int i = 0; i < 3; ++i)
	{
		add(_btnTone[i], "button", "optionsMenu");
		add(_btnSample[i], "button", "optionsMenu");
	}
	add(_txtHue, "confirmVideo", "optionsMenu");
	add(_slrHue, "button", "optionsMenu");
	add(_txtSat, "confirmVideo", "optionsMenu");
	add(_slrSat, "button", "optionsMenu");
	add(_txtLight, "confirmVideo", "optionsMenu");
	add(_slrLight, "button", "optionsMenu");
	add(_btnOk, "button", "optionsMenu");
	add(_btnCancel, "button", "optionsMenu");
	add(_btnReset, "button", "optionsMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "optionsMenu");

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText(tr("STR_HD_BUTTON_INK_TITLE"));

	for (int i = 0; i < 3; ++i)
	{
		_btnTone[i]->setText(tr(TONE[i]));
		_btnTone[i]->setGroup(&_toneSel);
		_btnTone[i]->onMouseClick((ActionHandler)&OptionsButtonInkState::btnToneClick);
		_btnSample[i]->setText(tr("STR_HD_BUTTON_INK_SAMPLE"));
	}

	_slrHue->setRange(0, 360);
	_slrHue->onChange((ActionHandler)&OptionsButtonInkState::slrChange);
	_slrSat->setRange(0, 100);
	_slrSat->onChange((ActionHandler)&OptionsButtonInkState::slrChange);
	_slrLight->setRange(0, 100);
	_slrLight->onChange((ActionHandler)&OptionsButtonInkState::slrChange);

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&OptionsButtonInkState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&OptionsButtonInkState::btnOkClick, Options::keyOk);

	_btnCancel->setText(tr("STR_CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&OptionsButtonInkState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&OptionsButtonInkState::btnCancelClick, Options::keyCancel);

	_btnReset->setText(tr("STR_HD_CUSTOM_RESET"));
	_btnReset->onMouseClick((ActionHandler)&OptionsButtonInkState::btnResetClick);

	if (origin == OPT_BATTLESCAPE)
	{
		applyBattlescapeTheme("optionsMenu");
	}

	show();
}

/**
 *
 */
OptionsButtonInkState::~OptionsButtonInkState()
{

}

/**
 * Puts the options on the buttons, the sliders and the labels; the labels say "auto" at the starting values (the theme picks
 * the letters' colour by the cap), and that the theme of the windows' buttons is needed while it is off - the controls then
 * change nothing.
 */
void OptionsButtonInkState::show()
{
	_toneSel = _btnTone[std::min(std::max(Options::oxceHdButtonInkTone, 0), 2)];
	for (int i = 0; i < 3; ++i)
	{
		_btnTone[i]->draw();
	}
	const int hue = std::min(std::max(Options::oxceHdButtonInkHue, 0), 360);
	const int sat = std::min(std::max(Options::oxceHdButtonInkSat, 0), 100);
	const int light = std::min(std::max(Options::oxceHdButtonInkLight, 0), 100);
	_slrHue->setValue(hue);
	_slrSat->setValue(sat);
	_slrLight->setValue(light);
	const std::string needs = Options::oxceHdWindowTheme ? std::string() : " (" + std::string(tr("STR_HD_BUTTON_INK_NEEDS")) + ")";
	_txtHue->setText(std::string(tr("STR_HD_BUTTON_INK_HUE")) + ": " + (hue == 0 ? std::string(tr("STR_HD_BUTTON_INK_AUTO")) : std::to_string(hue)) + needs);
	_txtSat->setText(std::string(tr("STR_HD_BUTTON_INK_SAT")) + ": " + std::to_string(sat) + "%" + needs);
	_txtLight->setText(std::string(tr("STR_HD_BUTTON_INK_LIGHT")) + ": " + (light == 50 ? std::string(tr("STR_HD_BUTTON_INK_AUTO")) : std::to_string(light) + "%") + needs);
}

/**
 * Picks the tone of the button clicked (the buttons follow at the next frame). Without the theme of the windows' buttons it
 * changes nothing.
 * @param action Pointer to an action.
 */
void OptionsButtonInkState::btnToneClick(Action *action)
{
	if (Options::oxceHdWindowTheme)
	{
		for (int i = 0; i < 3; ++i)
		{
			if (action->getSender() == _btnTone[i]) Options::oxceHdButtonInkTone = i;
		}
	}
	show();
}

/**
 * Puts the sliders' values in the letters' hue, saturation and brightness (the buttons follow at the next frame). Without the
 * theme of the windows' buttons they change nothing, and the sliders go back.
 * @param action Pointer to an action.
 */
void OptionsButtonInkState::slrChange(Action *)
{
	if (Options::oxceHdWindowTheme)
	{
		Options::oxceHdButtonInkHue = _slrHue->getValue();
		Options::oxceHdButtonInkSat = _slrSat->getValue();
		Options::oxceHdButtonInkLight = _slrLight->getValue();
	}
	show();
}

/**
 * Keeps the look.
 * @param action Pointer to an action.
 */
void OptionsButtonInkState::btnOkClick(Action *)
{
	_game->popState();
}

/**
 * Gives back the look the player had.
 * @param action Pointer to an action.
 */
void OptionsButtonInkState::btnCancelClick(Action *)
{
	Options::oxceHdButtonInkTone = _was[0];
	Options::oxceHdButtonInkHue = _was[1];
	Options::oxceHdButtonInkSat = _was[2];
	Options::oxceHdButtonInkLight = _was[3];
	_game->popState();
}

/**
 * Sets the starting look (the theme picks the letters).
 * @param action Pointer to an action.
 */
void OptionsButtonInkState::btnResetClick(Action *)
{
	Options::oxceHdButtonInkTone = 0;
	Options::oxceHdButtonInkHue = 0;
	Options::oxceHdButtonInkSat = 75;
	Options::oxceHdButtonInkLight = 50;
	show();
}

}
