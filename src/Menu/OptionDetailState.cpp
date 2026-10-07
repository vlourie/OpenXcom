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
#include "OptionDetailState.h"
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextList.h"
#include "../Interface/Window.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the Option Detail window.
 * @param origin Game section that originated this state.
 * @param name Translated name of the setting.
 * @param desc Translated description.
 * @param changer Changes the setting and tells its value (see Changer).
 */
OptionDetailState::OptionDetailState(OptionsOrigin origin, const std::string &name, const std::string &desc, Changer changer) : _changer(changer), _valueColor(0)
{
	_screen = false;

	// Create objects
	_window = new Window(this, 288, 180, 16, 10, POPUP_BOTH);
	_txtTitle = new Text(264, 17, 28, 18);
	_btnValue = new TextButton(160, 16, 80, 37);
	_lstDesc = new TextList(248, 100, 28, 58);
	_btnOk = new TextButton(100, 16, 110, 166);

	// Set palette
	setInterface("optionsMenu", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	add(_window, "confirmVideo", "optionsMenu");
	add(_txtTitle, "confirmVideo", "optionsMenu");
	add(_btnValue, "confirmVideo", "optionsMenu");
	add(_btnOk, "confirmVideo", "optionsMenu");
	// the description in the colors of the options list it was opened from
	add(_lstDesc, "optionLists", origin != OPT_BATTLESCAPE ? "advancedMenu" : "battlescape");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "optionsMenu");

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText(name);
	if (_txtTitle->getTextWidth() > _txtTitle->getWidth())
	{
		_txtTitle->setSmall();
	}

	// any button: left steps forward, right back, as on the list
	_btnValue->onMouseClick((ActionHandler)&OptionDetailState::btnValueClick, 0);

	// one row per paragraph; the list wraps them and scrolls with the wheel and the arrows
	_lstDesc->setColumns(1, _lstDesc->getWidth());
	_lstDesc->setWordWrap(true);
	_lstDesc->setBackground(_window);
	size_t start = 0;
	while (start <= desc.size())
	{
		size_t end = desc.find('\n', start);
		if (end == std::string::npos)
		{
			end = desc.size();
		}
		_lstDesc->addRow(1, desc.substr(start, end - start).c_str());
		start = end + 1;
	}
	_lstDesc->scrollTo(0);

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&OptionDetailState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&OptionDetailState::btnOkClick, Options::keyOk);
	_btnOk->onKeyboardPress((ActionHandler)&OptionDetailState::btnOkClick, Options::keyCancel);

	if (origin == OPT_BATTLESCAPE)
	{
		applyBattlescapeTheme("optionsMenu");
	}
	// after the theme, which paints every surface in one color
	_valueColor = _btnValue->getColor();
	showValue(_changer(0));
}

/**
 *
 */
OptionDetailState::~OptionDetailState()
{

}

void OptionDetailState::showValue(const std::pair<std::string, Uint8> &value)
{
	_btnValue->setText(value.first);
	_btnValue->setTextColor(value.second != 0 ? value.second : _valueColor);
}

/**
 * Changes the setting, as a click on its row of the list would.
 * @param action Pointer to an action.
 */
void OptionDetailState::btnValueClick(Action *action)
{
	const Uint8 button = action->getDetails()->button.button;
	if (button == SDL_BUTTON_LEFT || button == SDL_BUTTON_RIGHT)
	{
		showValue(_changer(button));
	}
}

/**
 * Returns to the options list.
 * @param action Pointer to an action.
 */
void OptionDetailState::btnOkClick(Action *)
{
	_game->popState();
}

}
