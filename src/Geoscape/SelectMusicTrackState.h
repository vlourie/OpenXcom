#pragma once
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
#include <vector>
#include "../Engine/State.h"

namespace OpenXcom
{

enum SelectMusicTrackOrigin
{
	SMT_GEOSCAPE,
	SMT_BATTLESCAPE
};

class MusicPlayerView;

/**
 * The music player (XP-000575, XP-AMP): the window that was the list of tracks to choose from is now two windows in a
 * column - the player (pause, stop, play, the time and the move in the track, the next and the previous, the volume,
 * shuffle and repeat) and the playlist of the geoscape or of the battle (add, remove, all, clear). All of it is
 * drawn by MusicPlayerView; this state only holds it, closes it and passes the keys.
 */
class SelectMusicTrackState : public State
{
private:
	SelectMusicTrackOrigin _origin;
	MusicPlayerView *_view;
public:
	/// Creates the player.
	SelectMusicTrackState(SelectMusicTrackOrigin origin);
	/// Cleans up the player.
	~SelectMusicTrackState();
	/// Keeps the picture up to date (once a second, not every frame).
	void think() override;
	/// Closes on Esc, on the key that opened it and on a right click outside; passes the rest on.
	void handle(Action *action) override;
};

}
