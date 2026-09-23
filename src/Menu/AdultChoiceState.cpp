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
#include "AdultChoiceState.h"
#include "StartState.h"
#include "../Engine/FileMap.h"
#include "../Engine/Game.h"
#include "../Engine/HdSprites.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Engine/Screen.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"

namespace OpenXcom
{

/// The mod that carries this screen's strings and the ordinary picture tree.
static const std::string STRINGS_MOD = "hd";

/**
 * Does the adult picture tree ship anything at all? Its folders are probed
 * rather than the tree itself, because the virtual file system lists files,
 * not the folders above them.
 */
bool AdultChoiceState::adultArtShipped()
{
	static const char *const branches[] = { "UI", "TERRAIN", "GLOBE", "BASEBITS.PCK" };
	for (const char *branch : branches)
	{
		const std::string path = std::string(HdSprites::ART_ROOT_ADULT) + "/" + branch;
		if (!FileMap::getVFolderContents(path).empty())
		{
			return true;
		}
	}
	return false;
}

/**
 * Is the mod holding this screen's strings active? Without it the question
 * would be asked in raw STR_ keys (rake R-036).
 */
static bool stringsAvailable()
{
	for (const auto& mod : Options::mods)
	{
		if (mod.first == STRINGS_MOD)
		{
			return mod.second;
		}
	}
	return false;
}

/**
 * Do we ask on this start? Every start, unless the player turned the question
 * off, and only when there is an adult tree to switch to.
 */
bool AdultChoiceState::isNeeded()
{
	return Options::oxceAdultAsk && stringsAvailable() && adultArtShipped();
}

/**
 * Initializes all the elements in the Adult Choice screen.
 * @param introPending Is the intro cutscene waiting below us on the stack?
 */
AdultChoiceState::AdultChoiceState(bool introPending) : _introPending(introPending)
{
	// We are pushed from the loading screen, which still runs at the display's
	// own resolution; the menu scale is only set later, by GoToMainMenuState.
	// Do it here, before the widgets are laid out, or they are placed for a
	// 2560x1440 screen and centered off the visible area.
	Screen::updateScale(Options::geoscapeScale, Options::baseXGeoscape, Options::baseYGeoscape, true);
	_game->getScreen()->resetDisplay(false);

	// Create objects
	_window = new Window(this, 256, 160, 32, 20, POPUP_BOTH);
	_txtTitle = new Text(236, 17, 42, 34);
	_txtInfo = new Text(236, 64, 42, 56);
	_btnAdult = new TextButton(216, 20, 52, 126);
	_btnClassic = new TextButton(216, 20, 52, 152);

	// Set palette
	setInterface("mainMenu");

	add(_window, "window", "mainMenu");
	add(_txtTitle, "text", "mainMenu");
	add(_txtInfo, "text", "mainMenu");
	add(_btnAdult, "button", "mainMenu");
	add(_btnClassic, "button", "mainMenu");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "mainMenu");

	_txtTitle->setText(tr("STR_ADULT_CHOICE_TITLE"));
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();

	_txtInfo->setText(tr("STR_ADULT_CHOICE_INFO"));
	_txtInfo->setAlign(ALIGN_CENTER);
	_txtInfo->setWordWrap(true);

	_btnAdult->setText(tr("STR_ADULT_CHOICE_ADULT"));
	_btnAdult->onMouseClick((ActionHandler)&AdultChoiceState::btnAdultClick);

	_btnClassic->setText(tr("STR_ADULT_CHOICE_CLASSIC"));
	_btnClassic->onMouseClick((ActionHandler)&AdultChoiceState::btnClassicClick);
	_btnClassic->onKeyboardPress((ActionHandler)&AdultChoiceState::btnClassicClick, Options::keyCancel);
}

/**
 *
 */
AdultChoiceState::~AdultChoiceState()
{
	// empty
}

/**
 * Applies the answer. Only which tree is read changes; the pictures themselves
 * are registered while the mods load, so a switch has to load them again.
 * @param adult Did the player ask for the adult art?
 */
void AdultChoiceState::choose(bool adult)
{
	if (Options::oxceAdultArt == adult)
	{
		Log(LOG_INFO) << "Art version: " << (adult ? "adult" : "classic") << " (same as last start)";
		// Nothing to reload; the intro, if any, is the next state down.
		_game->popState();
		return;
	}

	Options::oxceAdultArt = adult;
	Options::save();
	Log(LOG_INFO) << "Art version: " << (adult ? "adult" : "classic") << " (switching, resources reload)";

	// The reload throws away the whole state stack, the intro included,
	// so tell the new loading screen to play it once it is done.
	Options::reload = true;
	StartState::playIntroAfterReload = _introPending;
	_game->setState(new StartState);
}

/**
 * Plays with the adult art.
 * @param action Pointer to an action.
 */
void AdultChoiceState::btnAdultClick(Action *)
{
	choose(true);
}

/**
 * Plays with the classic art.
 * @param action Pointer to an action.
 */
void AdultChoiceState::btnClassicClick(Action *)
{
	choose(false);
}

}
