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
#include "GentleChoiceState.h"
#include "AdultChoiceState.h"
#include "../Engine/Game.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Engine/Screen.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"

namespace OpenXcom
{

/**
 * Do we ask on this start? Until the player has answered once.
 */
bool GentleChoiceState::isNeeded()
{
	return Options::oxceGentleAsk;
}

/**
 * Initializes all the elements in the Gentle Choice screen.
 * @param introPending Is the intro cutscene waiting below us on the stack?
 */
GentleChoiceState::GentleChoiceState(bool introPending) : _introPending(introPending)
{
	// pushed from the loading screen, which still runs at the display's own resolution
	// (see AdultChoiceState): set the menu scale before the widgets are laid out
	Screen::updateScale(Options::geoscapeScale, Options::baseXGeoscape, Options::baseYGeoscape, true);
	_game->getScreen()->resetDisplay(false);

	// Create objects: no popup animation, the warning itself must not flicker
	_window = new Window(this, 300, 190, 10, 5, POPUP_NONE);
	_txtTitle = new Text(280, 17, 20, 14);
	_txtInfo = new Text(280, 100, 20, 36);
	_btnGentle = new TextButton(240, 20, 40, 140);
	_btnUsual = new TextButton(240, 20, 40, 164);

	// Set palette
	setInterface("mainMenu");

	add(_window, "window", "mainMenu");
	add(_txtTitle, "text", "mainMenu");
	add(_txtInfo, "text", "mainMenu");
	add(_btnGentle, "button", "mainMenu");
	add(_btnUsual, "button", "mainMenu");

	centerAllSurfaces();

	// Set up objects. No background picture: the menu art is bright and busy, and the
	// warning must be calm and readable - the window fills itself with a plain colour.

	_txtTitle->setText(tr("STR_GENTLE_CHOICE_TITLE"));
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();

	_txtInfo->setText(tr("STR_GENTLE_CHOICE_INFO"));
	_txtInfo->setWordWrap(true);

	_btnGentle->setText(tr("STR_GENTLE_CHOICE_ON"));
	_btnGentle->onMouseClick((ActionHandler)&GentleChoiceState::btnGentleClick);
	_btnGentle->onKeyboardPress((ActionHandler)&GentleChoiceState::btnGentleClick, Options::keyOk);
	// a stray Esc must not pick the flashing version
	_btnGentle->onKeyboardPress((ActionHandler)&GentleChoiceState::btnGentleClick, Options::keyCancel);

	_btnUsual->setText(tr("STR_GENTLE_CHOICE_OFF"));
	_btnUsual->onMouseClick((ActionHandler)&GentleChoiceState::btnUsualClick);
}

/**
 *
 */
GentleChoiceState::~GentleChoiceState()
{
	// empty
}

/**
 * Applies the answer. Nothing needs a reload: the mode is read where it is used.
 * @param gentle Did the player ask for the gentle mode?
 */
void GentleChoiceState::choose(bool gentle)
{
	Options::oxceGentle = gentle;
	Options::oxceGentleAsk = false;
	Options::save();
	Log(LOG_INFO) << "Gentle mode: " << (gentle ? "on" : "off") << " (asked at start)";

	// the next question builds its texts in its constructor, so it is made only now
	_game->popState();
	if (AdultChoiceState::isNeeded())
	{
		_game->pushState(new AdultChoiceState(_introPending));
	}
}

/**
 * Turns the gentle mode on.
 * @param action Pointer to an action.
 */
void GentleChoiceState::btnGentleClick(Action *)
{
	choose(true);
}

/**
 * Plays as usual.
 * @param action Pointer to an action.
 */
void GentleChoiceState::btnUsualClick(Action *)
{
	choose(false);
}

}
