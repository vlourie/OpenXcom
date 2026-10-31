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
#include "HdLabPasswordState.h"
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/HdLab.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextEdit.h"
#include "../Interface/Window.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the password window.
 * @param origin Game section that originated this state.
 * @param opened Runs once the lab is open (the HD tab shows its options).
 */
HdLabPasswordState::HdLabPasswordState(OptionsOrigin origin, std::function<void()> opened) : _opened(opened)
{
	_screen = false;

	// Create objects
	_window = new Window(this, 288, 180, 16, 10, POPUP_BOTH);
	_txtTitle = new Text(264, 17, 28, 18);
	_txtPrompt = new Text(248, 64, 36, 42);
	_txtLabel = new Text(60, 10, 36, 114);
	_edtPassword = new TextEdit(this, 180, 10, 100, 114);
	_txtWrong = new Text(248, 20, 36, 134);
	_btnOk = new TextButton(100, 16, 48, 166);
	_btnCancel = new TextButton(100, 16, 172, 166);

	// Set palette
	setInterface("optionsMenu", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	add(_window, "confirmVideo", "optionsMenu");
	add(_txtTitle, "confirmVideo", "optionsMenu");
	add(_txtPrompt, "confirmVideo", "optionsMenu");
	add(_txtLabel, "confirmVideo", "optionsMenu");
	add(_edtPassword, "confirmVideo", "optionsMenu");
	add(_txtWrong, "confirmVideo", "optionsMenu");
	add(_btnOk, "confirmVideo", "optionsMenu");
	add(_btnCancel, "confirmVideo", "optionsMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "optionsMenu");

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText(tr("STR_HD_LAB"));

	_txtPrompt->setWordWrap(true);
	_txtPrompt->setText(tr("STR_HD_LAB_PROMPT"));

	_txtLabel->setText(tr("STR_HD_LAB_PASSWORD"));

	// Enter checks the password; Escape empties the field and closes the window (TextEdit runs the enter handler then)
	_edtPassword->onEnter((ActionHandler)&HdLabPasswordState::edtPasswordEnter);

	_txtWrong->setWordWrap(true);

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&HdLabPasswordState::btnOkClick);

	_btnCancel->setText(tr("STR_CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&HdLabPasswordState::btnCancelClick);

	if (origin == OPT_BATTLESCAPE)
	{
		applyBattlescapeTheme("optionsMenu");
	}
	// the field takes the keys at once, and keeps them: a click on a button still reaches the button
	_edtPassword->setFocus(true, false);
}

/**
 *
 */
HdLabPasswordState::~HdLabPasswordState()
{

}

/**
 * Checks the typed password: the right one opens the lab and closes the window,
 * a wrong one says so and leaves the field for another try.
 */
void HdLabPasswordState::check()
{
	if (HdLab::tryUnlock(_edtPassword->getText()))
	{
		std::function<void()> opened = _opened;
		_game->popState();
		if (opened)
		{
			opened();
		}
		return;
	}
	_txtWrong->setText(tr("STR_HD_LAB_WRONG"));
	_edtPassword->setText("");
	_edtPassword->setFocus(true, false);
}

/**
 * Enter in the field checks the password; an empty field (Escape empties it) closes the window.
 * @param action Pointer to an action.
 */
void HdLabPasswordState::edtPasswordEnter(Action *)
{
	if (_edtPassword->getText().empty())
	{
		_game->popState();
		return;
	}
	check();
}

/**
 * Checks the password.
 * @param action Pointer to an action.
 */
void HdLabPasswordState::btnOkClick(Action *)
{
	check();
}

/**
 * Returns to the options without opening the lab.
 * @param action Pointer to an action.
 */
void HdLabPasswordState::btnCancelClick(Action *)
{
	_game->popState();
}

}
