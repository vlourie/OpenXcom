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
#include "OptionsCustomColorState.h"
#include <algorithm>
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/HdBattleHud.h"
#include "../Engine/HdUi.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Engine/Surface.h"
#include "../Interface/Slider.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

namespace
{

/// A sample of the panel: a piece of its steel with three keys, drawn in the world layer only (the classic layer has
/// nothing of the modern panel to show).
class HdCustomSample : public Surface
{
public:
	HdCustomSample(int width, int height, int x, int y) : Surface(width, height, x, y) {}
	void hdMirror() override
	{
		if (HdUi::skin())
		{
			HdBattleHud::drawSample(getX(), getY(), getWidth(), getHeight());
		}
	}
};

/// The options the sliders stand for, in the order of the sliders: the keys' hue, saturation, value, the background's.
int *const VALUE[6] = { &Options::oxceHdCustomKeyHue, &Options::oxceHdCustomKeySat, &Options::oxceHdCustomKeyVal,
	&Options::oxceHdCustomBackHue, &Options::oxceHdCustomBackSat, &Options::oxceHdCustomBackVal };
const int HIGH[6] = { 359, 100, 100, 359, 100, 100 };
/// What Reset sets: the Cruiser hull's colours (the same as the options' defaults, Options.cpp).
const int START[6] = { 256, 25, 49, 255, 25, 38 };
const char *const LABEL[3] = { "STR_HD_CUSTOM_HUE", "STR_HD_CUSTOM_SAT", "STR_HD_CUSTOM_VAL" };

}

/**
 * Initializes all the elements in the Own Colour window.
 * @param origin Game section that originated this state.
 */
OptionsCustomColorState::OptionsCustomColorState(OptionsOrigin origin)
{
	_screen = false;

	// remember what the player had; from now on the own colour is the panel's colour, so that the whole interface shows it
	_was[0] = Options::oxceHdBattleHudColor;
	for (int i = 0; i < 6; ++i)
	{
		_was[1 + i] = *VALUE[i];
	}
	Options::oxceHdBattleHudColor = HdBattleHud::COLOR_CUSTOM;

	// Create objects
	_window = new Window(this, 288, 180, 16, 10, POPUP_BOTH);
	_txtTitle = new Text(264, 17, 28, 18);
	_txtKeys = new Text(120, 9, 28, 38);
	_txtBack = new Text(120, 9, 172, 38);
	for (int i = 0; i < 6; ++i)
	{
		const int col = i / 3, row = i % 3;
		_txtValue[i] = new Text(120, 9, 28 + col * 144, 52 + row * 26);
		_slr[i] = new Slider(120, 16, 28 + col * 144, 62 + row * 26);
	}
	_sample = new HdCustomSample(264, 28, 28, 136);
	_btnOk = new TextButton(80, 16, 28, 168);
	_btnCancel = new TextButton(80, 16, 120, 168);
	_btnReset = new TextButton(80, 16, 212, 168);

	// Set palette
	setInterface("optionsMenu", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	add(_window, "confirmVideo", "optionsMenu");
	add(_txtTitle, "confirmVideo", "optionsMenu");
	add(_txtKeys, "confirmVideo", "optionsMenu");
	add(_txtBack, "confirmVideo", "optionsMenu");
	for (int i = 0; i < 6; ++i)
	{
		add(_txtValue[i], "confirmVideo", "optionsMenu");
		add(_slr[i], "button", "optionsMenu");
	}
	add(_sample);
	add(_btnOk, "button", "optionsMenu");
	add(_btnCancel, "button", "optionsMenu");
	add(_btnReset, "button", "optionsMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "optionsMenu");

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText(tr("STR_HD_CUSTOM_COLOR_TITLE"));

	_txtKeys->setAlign(ALIGN_CENTER);
	_txtKeys->setText(tr("STR_HD_CUSTOM_KEYS"));
	_txtBack->setAlign(ALIGN_CENTER);
	_txtBack->setText(tr("STR_HD_CUSTOM_BACK"));

	for (int i = 0; i < 6; ++i)
	{
		_slr[i]->setRange(0, HIGH[i]);
		_slr[i]->onChange((ActionHandler)&OptionsCustomColorState::slrChange);
	}

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&OptionsCustomColorState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&OptionsCustomColorState::btnOkClick, Options::keyOk);

	_btnCancel->setText(tr("STR_CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&OptionsCustomColorState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&OptionsCustomColorState::btnCancelClick, Options::keyCancel);

	_btnReset->setText(tr("STR_HD_CUSTOM_RESET"));
	_btnReset->onMouseClick((ActionHandler)&OptionsCustomColorState::btnResetClick);

	if (origin == OPT_BATTLESCAPE)
	{
		applyBattlescapeTheme("optionsMenu");
	}

	show();
}

/**
 *
 */
OptionsCustomColorState::~OptionsCustomColorState()
{

}

/**
 * Puts the options on the sliders and the labels.
 */
void OptionsCustomColorState::show()
{
	for (int i = 0; i < 6; ++i)
	{
		const int v = std::min(std::max(*VALUE[i], 0), HIGH[i]);
		_slr[i]->setValue(v);
		_txtValue[i]->setText(std::string(tr(LABEL[i % 3])) + ": " + std::to_string(v));
	}
}

/**
 * Puts the sliders' values in the options (the sample, the panel and the buttons follow at the next frame) and the labels.
 */
void OptionsCustomColorState::apply()
{
	for (int i = 0; i < 6; ++i)
	{
		*VALUE[i] = _slr[i]->getValue();
		_txtValue[i]->setText(std::string(tr(LABEL[i % 3])) + ": " + std::to_string(*VALUE[i]));
	}
}

/**
 * Handler for moving a slider.
 * @param action Pointer to an action.
 */
void OptionsCustomColorState::slrChange(Action *)
{
	apply();
}

/**
 * Keeps the colours: the panel's colour stays the own one.
 * @param action Pointer to an action.
 */
void OptionsCustomColorState::btnOkClick(Action *)
{
	_game->popState();
}

/**
 * Gives back the colours the player had.
 * @param action Pointer to an action.
 */
void OptionsCustomColorState::btnCancelClick(Action *)
{
	Options::oxceHdBattleHudColor = _was[0];
	for (int i = 0; i < 6; ++i)
	{
		*VALUE[i] = _was[1 + i];
	}
	_game->popState();
}

/**
 * Sets the starting colours (the Cruiser hull's).
 * @param action Pointer to an action.
 */
void OptionsCustomColorState::btnResetClick(Action *)
{
	for (int i = 0; i < 6; ++i)
	{
		*VALUE[i] = START[i];
	}
	show();
}

}
