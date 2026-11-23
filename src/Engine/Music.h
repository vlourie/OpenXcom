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
#include <string>
#include <SDL_mixer.h>

namespace OpenXcom
{

/**
 * Container for music tracks.
 * Handles loading and playing various formats through SDL_mixer.
 */
class Music
{
private:
	Mix_Music *_music;
	SDL_RWops *_rwops;
	/// Where the file lies (a game track: relative to the mod's folders; an own one: a full path), for its length.
	std::string _filename, _path;
	/// The length in seconds: -2 not looked at yet, -1 not known (only OGG and FLAC tell it from their headers).
	mutable double _length;
public:
	/// Creates a blank music track.
	Music();
	/// Cleans up the music track.
	virtual ~Music();
	/// Loads music from the specified file.
	virtual void load(const std::string &filename);
	/// Loads music from the specified rwops.
	virtual void load(SDL_RWops *rwops);
	/// Plays the music.
	virtual void play(int loop = -1) const;
	/// Stops all music.
	static void stop();
	/// Pauses all music.
	static void pause();
	/// Resumes all music.
	static void resume();
	/// Checks if music is playing.
	static bool isPlaying();
	/// XP-000575, the music player: a track was started (play() calls it; a music with its own play() too).
	static void noteStarted(const Music *music, bool loop);
	/// Is a track on (playing or paused)? False after stop() and before the first play.
	static bool isOn();
	/// Is the music paused now?
	static bool isPaused();
	/// Seconds the track has played (our own count: SDL_mixer 1.2 does not tell), the pause not counted; a looped track wraps at its length.
	static double position();
	/// The length of the track on, seconds; -1 when not known.
	static double currentLength();
	/// Can the track on be moved to another time (OGG, FLAC, MP3, MOD)?
	static bool canSeek();
	/// Moves the track on to a time in seconds; false when it cannot be.
	static bool seek(double seconds);
	/// True once after a track played without a loop reached its end (a flag set by the sound thread, read by the main one).
	static bool takeFinished();
	/// The length of this track in seconds (read from the file's header once), -1 when not known.
	double length() const;
	/// The length by the header of a file (OGG, FLAC), -1 when not known: a game track's file, or an own track's full path.
	static double fileLength(const std::string &filename, const std::string &path);
	/// Where an own track's file lies, for its length.
	void setSourcePath(const std::string &path) { _path = path; }
};

}
