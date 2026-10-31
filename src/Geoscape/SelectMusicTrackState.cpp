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
#include "SelectMusicTrackState.h"
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Mod/Mod.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Engine/Music.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextList.h"
#include "../Mod/RuleInterface.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the Select Music Track window.
 * @param origin Where is the dialog called from?
 */
SelectMusicTrackState::SelectMusicTrackState(SelectMusicTrackOrigin origin) : _origin(origin)
{
	_screen = false;

	int x;
	if (_origin == SMT_BATTLESCAPE)
	{
		x = 52;
	}
	else
	{
		x = 20;
	}

	// Create objects
	_window = new Window(this, 216, 160, x, 20, POPUP_BOTH);
	_txtTitle = new Text(206, 17, x + 5, 32);
	// the player's own music (XP-000373): with it on, the button to scan its folder again is next to Cancel
	const bool ownMusic = Options::oxceUserMusic > 0 && !Options::mute;
	_btnRefresh = ownMusic ? new TextButton(86, 16, x + 13, 156) : 0;
	_btnCancel = ownMusic ? new TextButton(86, 16, x + 107, 156) : new TextButton(140, 16, x + 38, 156);
	_lstTracks = new TextList(180, 96, x + 13, 52);

	// Set palette
	setInterface("selectMusicTrack", false, _game->getSavedGame() ? _game->getSavedGame()->getSavedBattle() : 0);

	add(_window, "window", "selectMusicTrack");
	add(_txtTitle, "text", "selectMusicTrack");
	if (_btnRefresh)
	{
		add(_btnRefresh, "button", "selectMusicTrack");
	}
	add(_btnCancel, "button", "selectMusicTrack");
	add(_lstTracks, "list", "selectMusicTrack");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "selectMusicTrack");

	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setBig();
	_txtTitle->setText(tr("STR_SELECT_MUSIC_TRACK"));

	if (_btnRefresh)
	{
		_btnRefresh->setText(tr("STR_USER_MUSIC_REFRESH_UC"));
		_btnRefresh->onMouseClick((ActionHandler)&SelectMusicTrackState::btnRefreshClick);
	}

	_btnCancel->setText(tr("STR_CANCEL_UC"));
	_btnCancel->onMouseClick((ActionHandler)&SelectMusicTrackState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&SelectMusicTrackState::btnCancelClick, Options::keyCancel);

	_lstTracks->setColumns(1, 172);
	_lstTracks->setSelectable(true);
	_lstTracks->setBackground(_window);
	_lstTracks->setMargin(8);
	_lstTracks->setAlign(ALIGN_CENTER);
	_lstTracks->onMouseClick((ActionHandler)&SelectMusicTrackState::lstTrackClick);

	fillList();

	// switch to battlescape theme if called from battlestate
	if (_origin == SMT_BATTLESCAPE)
	{
		applyBattlescapeTheme("selectMusicTrack");
		markCurrentBattle();
	}
}

/**
 * Fills the list with the tracks: the game's of the category, then the player's own (XP-000373, by the file's name).
 * With the option "only own" and own tracks the game's tracks are left out (the one playing now stays).
 */
void SelectMusicTrackState::fillList()
{
	_lstTracks->clearList();
	_tracks.clear();
	_trackNames.clear();
	_currentTrackIndex = -1;

	const std::string search = _origin == SMT_BATTLESCAPE ? "GMTAC" : "GMGEO";
	const std::string category = _origin == SMT_BATTLESCAPE ? "GMTACTIC" : "GMGEO";
	const std::string& currentName = _game->getMod()->getCurrentMusicTrack();
	const bool onlyOwn = _game->getMod()->userMusicOnly(category);
	for (auto& pair : _game->getMod()->getMusicTrackList())
	{
		if (pair.first == currentName || (!onlyOwn && pair.first.find(search) != std::string::npos))
		{
			_lstTracks->addRow(1, tr(pair.first).c_str());
			_tracks.push_back(pair.second);
			_trackNames.push_back(pair.first);
			if (pair.first == currentName)
			{
				_currentTrackIndex = _lstTracks->getLastRowIndex();
				_lstTracks->setRowColor(_currentTrackIndex, _lstTracks->getSecondaryColor());
			}
		}
	}
	for (auto& own : _game->getMod()->getUserMusicList(category))
	{
		_lstTracks->addRow(1, own.second.c_str());
		_tracks.push_back(0);
		_trackNames.push_back(own.first);
		if (own.first == currentName)
		{
			_currentTrackIndex = _lstTracks->getLastRowIndex();
			_lstTracks->setRowColor(_currentTrackIndex, _lstTracks->getSecondaryColor());
		}
	}
}

/**
 * Colours the row of the track playing now in the battlescape theme.
 */
void SelectMusicTrackState::markCurrentBattle()
{
	if (_currentTrackIndex > -1)
	{
		const Element* element = _game->getMod()->getInterface("battlescape")->getElement("optionLists");
		_lstTracks->setRowColor(_currentTrackIndex, element->color2);
	}
}

/**
 * Scans the folder of the player's own music again and shows the new list.
 * @param action Pointer to an action.
 */
void SelectMusicTrackState::btnRefreshClick(Action *)
{
	_game->getMod()->refreshUserMusic();
	fillList();
	if (_origin == SMT_BATTLESCAPE)
	{
		markCurrentBattle();
	}
}

/**
 *
 */
SelectMusicTrackState::~SelectMusicTrackState()
{

}

/**
 * Returns to the previous screen.
 * @param action Pointer to an action.
 */
void SelectMusicTrackState::btnCancelClick(Action *)
{
	_game->popState();
}

/**
 * Starts playing the selected track and returns to the previous screen.
 * @param action Pointer to an action.
 */
void SelectMusicTrackState::lstTrackClick(Action *)
{
	Music *selected = _tracks[_lstTracks->getSelectedRow()];
	if (!selected)
	{
		// the player's own track: opened at its first play; a file that cannot be read goes from the list
		selected = _game->getMod()->getUserMusic(_trackNames[_lstTracks->getSelectedRow()]);
		if (!selected)
		{
			fillList();
			if (_origin == SMT_BATTLESCAPE)
			{
				markCurrentBattle();
			}
			return;
		}
	}
	selected->play();
	_game->getMod()->setCurrentMusicTrack(_trackNames[_lstTracks->getSelectedRow()]);

	_game->popState();
}

}
