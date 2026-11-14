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
#include "Music.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstring>
#include <vector>
#include "Exception.h"
#include "Options.h"
#include "Logger.h"
#include "Unicode.h"
#include "FileMap.h"
#include "SDL2Helpers.h"
#include "Adlib/adlplayer.h"
#include "AdlibMusic.h"

namespace OpenXcom
{

// XP-000575: what the music player needs to know about the track on. SDL_mixer 1.2 tells neither the time nor the length,
// so the time is our own count from the start (the pause and the moves counted), the length comes from the file's header.
static const Music *s_current = 0;
static Uint32 s_startTicks = 0;
static double s_base = 0.0;
static bool s_paused = false, s_looped = true;
static double s_pausedAt = 0.0;
static std::atomic<bool> s_ended(false), s_ourHalt(false);

/**
 * Called by SDL_mixer when a track ends - in the sound's thread: a flag and nothing else. Halting the music
 * ourselves (stop) calls it too; those are not an end.
 */
static void musicFinishedHook()
{
	if (!s_ourHalt.load())
	{
		s_ended.store(true);
	}
}

/**
 * Initializes a new music track.
 */
Music::Music() : _music(0), _rwops(0), _length(-2)
{
}

void Music::noteStarted(const Music *music, bool loop)
{
	s_current = music;
	s_startTicks = SDL_GetTicks();
	s_base = 0.0;
	s_paused = false;
	s_looped = loop;
	s_ended.store(false);
}

bool Music::isOn()
{
	return s_current != 0;
}

bool Music::isPaused()
{
	return s_current != 0 && s_paused;
}

double Music::currentLength()
{
	return s_current ? s_current->length() : -1.0;
}

double Music::position()
{
	if (!s_current)
	{
		return 0.0;
	}
	double t = s_paused ? s_pausedAt : s_base + (SDL_GetTicks() - s_startTicks) / 1000.0;
	const double len = s_current->length();
	if (len > 0)
	{
		t = s_looped ? fmod(t, len) : std::min(t, len);
	}
	return t;
}

bool Music::canSeek()
{
#ifndef __NO_MUSIC
	if (s_current && !Options::mute)
	{
		switch (Mix_GetMusicType(NULL))
		{
		case MUS_OGG: case MUS_MP3: case MUS_MP3_MAD: case MUS_FLAC: case MUS_MOD: case MUS_MODPLUG:
			return true;
		default:
			break;
		}
	}
#endif
	return false;
}

bool Music::seek(double seconds)
{
#ifndef __NO_MUSIC
	if (!canSeek())
	{
		return false;
	}
	const double len = s_current->length();
	seconds = std::max(0.0, seconds);
	if (len > 1.0)
	{
		seconds = std::min(seconds, len - 0.5);
	}
	if (Mix_SetMusicPosition(seconds) != 0)
	{
		return false;
	}
	s_base = seconds;
	s_startTicks = SDL_GetTicks();
	s_pausedAt = seconds;
	return true;
#else
	return false;
#endif
}

bool Music::takeFinished()
{
	return s_ended.exchange(false);
}

/**
 * The length of the track in seconds, from the header of its file: Ogg Vorbis (the last page's position over the
 * sample rate) and FLAC (the stream info). Other formats do not tell it before they are decoded: -1.
 */
double Music::length() const
{
	if (_length == -2)
	{
		_length = fileLength(_filename, _path);
	}
	return _length;
}

/**
 * The length of a track by the header of its file, without the track being loaded.
 * @param filename A game track's file, relative to the mod's folders (used when path is empty).
 * @param path An own track's full path.
 */
double Music::fileLength(const std::string &filename, const std::string &path)
{
	double result = -1;
	std::string name = path.empty() ? filename : path;
	std::transform(name.begin(), name.end(), name.begin(), ::tolower);
	const bool ogg = name.size() > 4 && name.compare(name.size() - 4, 4, ".ogg") == 0;
	const bool flac = name.size() > 5 && name.compare(name.size() - 5, 5, ".flac") == 0;
	if (!ogg && !flac)
	{
		return result;
	}
	SDL_RWops *rw = 0;
	try
	{
		rw = path.empty() ? FileMap::getRWops(filename) : SDL_RWFromFile(path.c_str(), "rb");
	}
	catch (...)
	{
		rw = 0;
	}
	if (!rw)
	{
		return result;
	}
	unsigned char head[128];
	const int got = (int)SDL_RWread(rw, head, 1, sizeof(head));
	if (flac && got >= 26 && memcmp(head, "fLaC", 4) == 0)
	{
		const unsigned rate = ((unsigned)head[18] << 12) | ((unsigned)head[19] << 4) | (head[20] >> 4);
		const unsigned long long total = ((unsigned long long)(head[21] & 0x0F) << 32) | ((unsigned long long)head[22] << 24) |
			((unsigned long long)head[23] << 16) | ((unsigned long long)head[24] << 8) | head[25];
		if (rate > 0 && total > 0)
		{
			result = (double)total / rate;
		}
	}
	else if (ogg && got >= 40)
	{
		unsigned rate = 0;
		for (int i = 0; i + 16 <= got; ++i)
		{
			if (head[i] == 1 && memcmp(head + i + 1, "vorbis", 6) == 0)
			{
				rate = head[i + 12] | (head[i + 13] << 8) | (head[i + 14] << 16) | ((unsigned)head[i + 15] << 24);
				break;
			}
		}
		const int size = SDL_RWseek(rw, 0, RW_SEEK_END);
		if (rate > 0 && size > 0)
		{
			const int tail = std::min(size, 65536);
			std::vector<unsigned char> buf(tail);
			SDL_RWseek(rw, size - tail, RW_SEEK_SET);
			const int n = (int)SDL_RWread(rw, buf.data(), 1, tail);
			for (int i = n - 27; i >= 0; --i)
			{
				if (buf[i] == 'O' && buf[i + 1] == 'g' && buf[i + 2] == 'g' && buf[i + 3] == 'S' && buf[i + 4] == 0 && buf[i + 5] <= 7)
				{
					unsigned long long granule = 0;
					for (int b = 7; b >= 0; --b)
					{
						granule = (granule << 8) | buf[i + 6 + b];
					}
					if (granule != ~0ULL && granule > 0)
					{
						result = (double)granule / rate;
						break;
					}
				}
			}
		}
	}
	SDL_RWclose(rw);
	return result;
}

/**
 * Deletes the loaded music content.
 */
Music::~Music()
{
#ifndef __NO_MUSIC
	stop();
	if (_music)	Mix_FreeMusic(_music);
	if (_rwops) SDL_RWclose(_rwops);
#endif
}

/**
 * Loads a music file from a specified filename.
 * @param filename Filename of the music file.
 */
void Music::load(const std::string &filename)
{
#ifndef __NO_MUSIC
	_filename = filename;
	load(FileMap::getRWops(filename));
	Log(LOG_VERBOSE)<<"Music::load('" << filename << "')";
#endif
}

/**
 * Loads a music file from a specified rwops.
 * @param filename Filename of the music file.
 */
void Music::load(SDL_RWops *rwops)
{
#ifndef __NO_MUSIC
	_rwops = rwops;
	_music = Mix_LoadMUS_RW(_rwops);

	if (_music == 0)
	{
		throw Exception(Mix_GetError());
	}
#endif
}

/**
 * Plays the contained music track.
 * @param loop Amount of times to loop the track. -1 = infinite
 */
void Music::play(int loop) const
{
#ifndef __NO_MUSIC
	if (!Options::mute)
	{
		if (_music != 0)
		{
			stop();
			if (Mix_PlayMusic(_music, loop) == -1)
			{
				Log(LOG_WARNING) << Mix_GetError();
			}
			else
			{
				Mix_HookMusicFinished(musicFinishedHook);
				noteStarted(this, loop != 0);
			}
		}
	}
#endif
}

/**
 * Stops all music playing.
 */
void Music::stop()
{
#ifndef __NO_MUSIC
	if (!Options::mute)
	{
		func_mute();
		Mix_HookMusic(NULL, NULL);
		s_ourHalt.store(true);
		Mix_HaltMusic();
		s_ourHalt.store(false);
	}
#endif
	s_current = 0;
	s_paused = false;
}

/**
 * Pauses music playback when game loses focus.
 */
void Music::pause()
{
#ifndef __NO_MUSIC
	if (!Options::mute)
	{
		if (s_current && !s_paused)
		{
			s_pausedAt = position();
			s_paused = true;
		}
		Mix_PauseMusic();
		if (Mix_GetMusicType(0) == MUS_NONE)
			Mix_HookMusic(NULL, NULL);
	}
#endif
}

/**
 * Resumes music playback when game gains focus.
 */
void Music::resume()
{
#ifndef __NO_MUSIC
	if (!Options::mute)
	{
		if (s_current && s_paused)
		{
			s_base = s_pausedAt;
			s_startTicks = SDL_GetTicks();
			s_paused = false;
		}
		Mix_ResumeMusic();
		if (Mix_GetMusicType(0) == MUS_NONE)
			Mix_HookMusic(AdlibMusic::player, NULL);
	}
#endif
}

/**
 * Checks if any music is playing.
 */
bool Music::isPlaying()
{
#ifndef __NO_MUSIC
	if (!Options::mute)
	{
		return Mix_Playing(-1) != 0;
	}
#endif
	return false;
}

}
