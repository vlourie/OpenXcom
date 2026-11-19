/*
 * Copyright 2010-2016 OpenXcom Developers.
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
#include "LoadGameState.h"
#include <sstream>
#include "../Engine/Logger.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Engine/Game.h"
#include "../Engine/Exception.h"
#include "../Engine/Options.h"
#include "../Engine/CrossPlatform.h"
#include "../Engine/Screen.h"
#include "../Engine/HdPaletteShift.h"
#include "../Engine/LocalizedText.h"
#include "../Interface/Text.h"
#include "../Geoscape/GeoscapeState.h"
#include "ErrorMessageState.h"
#include "../Battlescape/BattlescapeState.h"
#include "../Mod/Mod.h"
#include "../Engine/Sound.h"
#include "../Engine/Unicode.h"
#include "../Mod/RuleInterface.h"
#include "StatisticsState.h"
#include "MainMenuState.h"
#include "../Engine/RNG.h"
#include <exception>
#include <list>
#include "../Engine/Timer.h"
#include "../Battlescape/BattlescapeGame.h"
#include "../Battlescape/CollapsePilot.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the Load Game screen.
 * @param game Pointer to the core game.
 * @param origin Game section that originated this state.
 * @param filename Name of the save file without extension.
 * @param palette Parent state palette.
 */
LoadGameState::LoadGameState(OptionsOrigin origin, const std::string &filename, SDL_Color *palette) : _firstRun(0), _origin(origin), _filename(filename)
{
	buildUi(palette);
}

/**
 * Initializes all the elements in the Load Game screen.
 * @param game Pointer to the core game.
 * @param origin Game section that originated this state.
 * @param type Type of auto-load being used.
 * @param palette Parent state palette.
 */
LoadGameState::LoadGameState(OptionsOrigin origin, SaveType type, SDL_Color *palette) : _firstRun(0), _origin(origin)
{
	switch (type)
	{
	case SAVE_QUICK:
		_filename = SavedGame::QUICKSAVE;
		break;
	case SAVE_AUTO_GEOSCAPE:
		_filename = SavedGame::AUTOSAVE_GEOSCAPE;
		break;
	case SAVE_AUTO_BATTLESCAPE:
		_filename = SavedGame::AUTOSAVE_BATTLESCAPE;
		break;
	default:
		// can't auto-load ironman games
		break;
	}

	buildUi(palette);
}

/**
 *
 */
LoadGameState::~LoadGameState()
{

}

/**
 * Builds the interface.
 * @param palette Parent state palette.
 */
void LoadGameState::buildUi(SDL_Color *palette)
{
	_screen = false;

	// Create objects
	_txtStatus = new Text(320, 17, 0, 92);

	// Set palette
	setStatePalette(palette);

	if (_origin == OPT_BATTLESCAPE)
	{
		add(_txtStatus, "textLoad", "battlescape");
		_txtStatus->setHighContrast(true);
		if (_game->getSavedGame()->getSavedBattle()->getAmbientSound() != Mod::NO_SOUND)
		{
			_game->getMod()->getSoundByDepth(0, _game->getSavedGame()->getSavedBattle()->getAmbientSound())->stopLoop();
		}
	}
	else
	{
		add(_txtStatus, "textLoad", "geoscape");
	}

	centerAllSurfaces();

	// Set up objects
	_txtStatus->setBig();
	_txtStatus->setAlign(ALIGN_CENTER);
	_txtStatus->setText(tr("STR_LOADING_GAME"));

}

/**
 * Ignore quick loads without a save available.
 */
void LoadGameState::init()
{
	State::init();
	if (_filename == SavedGame::QUICKSAVE && !CrossPlatform::fileExists(Options::getMasterUserFolder() + _filename))
	{
		_game->popState();
		return;
	}
}

/**
 * Builds the screens of a loaded game, which must be the current one: the display takes their size on the way.
 * @param save The loaded game.
 * @param screens The screens are added here, bottom first; on a failure those already built stay in it.
 * @return The battle screen, if the game is in a battle.
 */
BattlescapeState *LoadGameState::buildScreens(SavedGame *save, std::list<State*> &screens)
{
	if (save->getEnding() != END_NONE)
	{
		Options::baseXResolution = Screen::ORIGINAL_WIDTH;
		Options::baseYResolution = Screen::ORIGINAL_HEIGHT;
		_game->getScreen()->resetDisplay(false);
		screens.push_back(new StatisticsState);
		return 0;
	}
	Options::baseXResolution = Options::baseXGeoscape;
	Options::baseYResolution = Options::baseYGeoscape;
	_game->getScreen()->resetDisplay(false);
	screens.push_back(new GeoscapeState);
	BattlescapeState *bs = 0;
	if (save->getSavedBattle() != 0)
	{
		save->getSavedBattle()->loadMapResources(_game->getMod());
		Options::baseXResolution = Options::baseXBattlescape;
		Options::baseYResolution = Options::baseYBattlescape;
		_game->getScreen()->resetDisplay(false);
		bs = new BattlescapeState;
		screens.push_back(bs);
		save->getSavedBattle()->setBattleState(bs);
	}
	return bs;
}

/**
 * Loads the specified save.
 *
 * A load either gives the player the loaded game or leaves them the game they had. The save is read and its
 * screens are built with the loaded game put in the place of the running one, which is kept whole aside
 * (Game::parkSavedGame): its screens stay in the stack, its Lua, its terrain and its palettes are kept or put back.
 * Only when the screens stand does the game before go (Game::commitSavedGame), and nothing after that fails.
 *
 * A battle loads at the HD scale of the options. When that is not the scale the game before stands at, all that
 * was made for that scale (Mod::parkHdScale) is handed to this load: nothing is copied, the loaded battle gets its
 * own beside it, and the two sets exist together only until the load ends - the parked one is freed when the
 * screens and the game before are gone, or comes back untouched, with nothing read or allocated, when the load fails.
 */
void LoadGameState::think()
{
	State::think();
	// Make sure it gets drawn properly: the work starts after a frame with this screen (Game::shownSince)
	if (_firstRun == 0)
	{
		_firstRun = 1;
		_shownFrame = _game->getFrameCount();
		_shownSince = SDL_GetTicks();
	}
	if (!_game->shownSince(_shownFrame, _shownSince))
	{
		return;
	}
	_game->popState();

	// Remember for later (palette reset)
	SavedGame *before = _game->getSavedGame();
	BattlescapeState *origBattleState = 0;
	if (before != 0 && before->getSavedBattle() != 0)
	{
		origBattleState = before->getSavedBattle()->getBattleState();
	}

	// Reset touch flags
	_game->resetTouchButtonFlags();

	// Load the game
	Mod *mod = _game->getMod();
	SavedGame *s = new SavedGame();
	// SavedGame::load() sets the seed from the file at its very start;
	// a save that is then rejected must not leave its seed to the game that goes on
	const uint64_t seedBefore = RNG::getSeed();
	// what the screens of a loaded game change outside of it, to put back if it is rejected
	const int baseX = Options::baseXResolution, baseY = Options::baseYResolution;
	const int frameSkip = Timer::hdFrameSkip;
	const bool debugPlay = BattlescapeGame::_debugPlay;
	const std::string music = mod->getPlayingMusic();
	std::list<State*> screens;
	Mod::HdScalePark *scalePark = 0;
	bool failed = false, palettes = false;
	std::string failure;
	try
	{
		s->load(_filename, mod, _game->getLanguage());
		_game->parkSavedGame(s);
		CollapsePilot::park();
		if (origBattleState != 0 && s->getEnding() == END_NONE)
		{
			// The colour shift the battle before gave its HD frames is put aside whole, with the frames it recoloured:
			// undone, the load puts it back as it was, without building its tables or reading a frame again
			HdPaletteShift::park();
			// We need to reset palettes here already, can't wait for the destructor
			palettes = origBattleState->resetPalettes();
		}
		if (s->getSavedBattle() != 0 && s->getEnding() == END_NONE && mod->hdScaleStale())
		{
			// The loaded battle takes another HD scale than the game before stands at
			scalePark = mod->parkHdScale();
		}
		_game->getScreen()->parkWorld();
		BattlescapeState *bs = buildScreens(s, screens);
		// the destructor of the battle screen before, on its way out, turns the HD frame skip off
		const int frameSkipNow = Timer::hdFrameSkip;
		// The loaded game stands. The game before goes here; nothing from here on is undone, and nothing fails
		_game->commitSavedGame(screens);
		CollapsePilot::unpark(false);
		// nothing made at the scale before is left to point at what was parked
		mod->dropHdScale(scalePark);
		scalePark = 0;
		HdPaletteShift::unpark(false);
		_game->getScreen()->unparkWorld(false);
		Timer::hdFrameSkip = frameSkipNow;
		if (bs != 0)
		{
			// Try to reactivate the touch buttons
			bs->toggleTouchButtons(false, true);
		}

		// Clear the SDL event queue (i.e. ignore input from impatient users)
		SDL_Event e;
		while (SDL_PollEvent(&e))
		{
			// do nothing
		}
	}
	catch (Exception &e)
	{
		failed = true;
		failure = e.what();
	}
	catch (YAML::Exception &e)
	{
		failed = true;
		failure = e.what();
	}
	catch (std::exception &e)
	{
		// a damaged save can also end in a standard exception (a bad size, a missing key),
		// and so can a lack of memory: that is a save that did not load, not a crash of the game
		failed = true;
		failure = e.what();
	}
	if (failed)
	{
		// the screens built for the game that failed go while it is still the current one
		while (!screens.empty())
		{
			delete screens.back();
			screens.pop_back();
		}
		if (_game->hasParkedGame())
		{
			// Rejected with the game before still whole: it comes back as it was
			if (s->getSavedBattle() != 0)
			{
				// (with the scale before parked the two battles share no terrain: all of this one's goes)
				s->getSavedBattle()->releaseMapData(scalePark == 0 && before != 0 ? before->getSavedBattle() : 0);
				BattlescapeState::restorePalettes(mod);
			}
			mod->unparkHdScale(scalePark);
			scalePark = 0;
			_game->unparkSavedGame();
			CollapsePilot::unpark(true);
			BattlescapeGame::_debugPlay = debugPlay;
			Timer::hdFrameSkip = frameSkip;
			if (origBattleState != 0 && palettes)
			{
				BattlescapeState::restorePalettes(mod);
				// the colour shift of the battle that goes on is in place again before its palettes are:
				// reapplyPalettes finds it carried over and builds nothing
				HdPaletteShift::unpark(true);
				origBattleState->reapplyPalettes();
			}
			HdPaletteShift::unpark(true);
			Options::baseXResolution = baseX;
			Options::baseYResolution = baseY;
			_game->getScreen()->unparkWorld(true);
			try
			{
				_game->getScreen()->resetDisplay(false);
			}
			catch (std::exception &e)
			{
				Log(LOG_ERROR) << "The display did not come back to the size of the game that goes on: " << e.what();
			}
			if (!music.empty() && mod->getPlayingMusic() != music)
			{
				mod->playMusic(music);
			}
		}
		error(failure, s);
		RNG::setSeed(seedBefore);
	}
	CrossPlatform::flashWindow();
}

/**
 * Pops up a window with an error message
 * and cleans up afterwards.
 * @param msg Error message.
 * @param save Pending save.
 */
void LoadGameState::error(const std::string &msg, SavedGame *save)
{

	Log(LOG_ERROR) << msg;
	std::ostringstream error;
	error << tr("STR_LOAD_UNSUCCESSFUL") << Unicode::TOK_NL_SMALL << msg;
	if (_game->getSavedGame() == save)
	{
		// The failure came after the game was switched to this save (the map resources, the battle screen):
		// the game before it is gone and the screens put up for this one must not stay without a save.
		// Back to the main menu, as after abandoning a game; the message goes on top of it.
		Screen::updateScale(Options::geoscapeScale, Options::baseXGeoscape, Options::baseYGeoscape, true);
		_game->getScreen()->resetDisplay(false);
		// the screens of the game that failed go before it does (error() runs from a screen that is not in the stack)
		std::list<State*> menu;
		menu.push_back(new MainMenuState);
		_game->replaceStates(menu);
	}
	if (_origin != OPT_BATTLESCAPE)
		_game->pushState(new ErrorMessageState(error.str(), _palette, _game->getMod()->getInterface("errorMessages")->getElement("geoscapeColor")->color, "BACK01.SCR", _game->getMod()->getInterface("errorMessages")->getElement("geoscapePalette")->color));
	else
		_game->pushState(new ErrorMessageState(error.str(), _palette, _game->getMod()->getInterface("errorMessages")->getElement("battlescapeColor")->color, "TAC00.SCR", _game->getMod()->getInterface("errorMessages")->getElement("battlescapePalette")->color));

	if (_game->getSavedGame() == save)
		_game->setSavedGame(0);
	else
		delete save;
}

}
