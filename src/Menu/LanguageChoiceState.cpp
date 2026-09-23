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
#include "LanguageChoiceState.h"
#include "AdultChoiceState.h"
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/Language.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Engine/Screen.h"
#include "../Interface/Text.h"
#include "../Interface/TextList.h"
#include "../Interface/Window.h"

namespace OpenXcom
{

/**
 * Is there a choice to make? Only on the first start - the answer is kept, and
 * changed later in Options > Video - and only when the mods actually ship more
 * than one language: with a single one the screen would be a dead end.
 */
bool LanguageChoiceState::isNeeded()
{
	if (Options::oxceLanguageChosen)
	{
		return false;
	}
	std::vector<std::string> ids, names;
	Language::getList(ids, names);
	return ids.size() > 1;
}

/**
 * Initializes all the elements in the Language Choice screen.
 * @param introPending Is the intro cutscene waiting below us on the stack?
 */
LanguageChoiceState::LanguageChoiceState(bool introPending) : _introPending(introPending)
{
	// We are pushed from the loading screen, which still runs at the display's
	// own resolution; the menu scale is only set later, by GoToMainMenuState.
	Screen::updateScale(Options::geoscapeScale, Options::baseXGeoscape, Options::baseYGeoscape, true);
	_game->getScreen()->resetDisplay(false);

	// Create objects
	_window = new Window(this, 256, 160, 32, 20, POPUP_BOTH);
	_txtTitle = new Text(236, 17, 42, 34);
	_lstLanguages = new TextList(212, 96, 52, 60);

	// Set palette
	setInterface("mainMenu");

	add(_window, "window", "mainMenu");
	add(_txtTitle, "text", "mainMenu");
	add(_lstLanguages, "list", "mainMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "mainMenu");

	// Not translated on purpose: this screen is read before a language is picked.
	_txtTitle->setText("LANGUAGE");
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();

	std::vector<std::string> names;
	Language::getList(_ids, names);

	_lstLanguages->setColumns(1, 204);
	_lstLanguages->setAlign(ALIGN_CENTER);
	_lstLanguages->setSelectable(true);
	_lstLanguages->setBackground(_window);
	_lstLanguages->onMouseClick((ActionHandler)&LanguageChoiceState::lstLanguagesClick);
	for (const auto& name : names)
	{
		_lstLanguages->addRow(1, name.c_str());
	}

	// Open on the language played last time, and let Esc keep it.
	for (size_t i = 0; i < _ids.size(); ++i)
	{
		if (_ids[i] == Options::language)
		{
			_lstLanguages->scrollTo(i);
			break;
		}
	}
	_lstLanguages->onKeyboardPress((ActionHandler)&LanguageChoiceState::keepCurrent, Options::keyCancel);
	_lstLanguages->onKeyboardPress((ActionHandler)&LanguageChoiceState::keepCurrent, Options::keyOk);
}

/**
 *
 */
LanguageChoiceState::~LanguageChoiceState()
{
	// empty
}

/**
 * Loads the chosen language and hands over to the art version question.
 * @param id Language id, or an empty string to keep the current one.
 */
void LanguageChoiceState::choose(const std::string &id)
{
	if (!id.empty() && id != Options::language)
	{
		Options::language = id;
		_game->loadLanguages();
		Log(LOG_INFO) << "Language chosen: " << id;
	}
	Options::oxceLanguageChosen = true;
	Options::save();

	// Build the next screen only now, with the chosen language loaded: its
	// texts are set in its constructor and would otherwise be the old ones.
	_game->popState();
	if (AdultChoiceState::isNeeded())
	{
		_game->pushState(new AdultChoiceState(_introPending));
	}
}

/**
 * Picks the language that was clicked.
 * @param action Pointer to an action.
 */
void LanguageChoiceState::lstLanguagesClick(Action *)
{
	const size_t row = _lstLanguages->getSelectedRow();
	if (row < _ids.size())
	{
		choose(_ids[row]);
	}
}

/**
 * Keeps the language of the previous start.
 * @param action Pointer to an action.
 */
void LanguageChoiceState::keepCurrent(Action *)
{
	choose("");
}

}
