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
#include "Sound.h"
#include <atomic>
#include "Options.h"
#include "Logger.h"
#include "Unicode.h"
#include "FileMap.h"

namespace OpenXcom
{

namespace
{
/// The channels playShot has faded out (a bit each), the volume Game::setVolume gave the sound channels (-1: not yet)
std::atomic<unsigned long long> g_faded{ 0 };
std::atomic<int> g_channelVolume{ -1 };
bool g_finishedSet = false;

/// Mix_ChannelFinished: a faded channel is back at the slider's volume (SDL_mixer 1.2.12 sets the maximum, R-561).
void channelFinished(int channel)
{
	if (channel < 0 || channel >= 64)
	{
		return;
	}
	const unsigned long long bit = 1ull << channel;
	if (g_faded.fetch_and(~bit) & bit)
	{
		const int volume = g_channelVolume.load();
		if (volume >= 0)
		{
			Mix_Volume(channel, volume);
		}
	}
}
}

/**
 * Deletes the loaded sound content.
 */
void Sound::UniqueSoundDeleter::operator ()(Mix_Chunk* sound)
{
	Mix_FreeChunk(sound);
}

Sound::UniqueSoundPtr Sound::NewSound(Mix_Chunk* sound)
{
	return Sound::UniqueSoundPtr(sound);
}

/**
 * Loads a sound file from a specified filename.
 * @param filename Filename of the sound file.
 */
void Sound::load(const std::string &filename) {
	auto rw = FileMap::getRWops(filename);
	auto s = NewSound(Mix_LoadWAV_RW(rw, SDL_TRUE));
	if (!s)
	{
		Log(LOG_ERROR) << "Sound::load(" << filename << "): mix error=" << Mix_GetError();
	}

	//always overwrite
	_sound = std::move(s);
	_later.clear();
}

/**
 * Remembers a sound file to decode when the sound is first played.
 * @param filename Filename of the sound file.
 */
void Sound::loadLater(const std::string &filename)
{
	//always overwrite
	_sound.reset();
	_later = filename;
}

/**
 * Gets the sound's data, decoding the file of loadLater on the first call.
 * @return The data or nullptr.
 */
Mix_Chunk *Sound::chunk() const
{
	if (!_later.empty())
	{
		_sound = NewSound(Mix_LoadWAV_RW(FileMap::getRWops(_later), SDL_TRUE));
		if (!_sound)
		{
			Log(LOG_ERROR) << "Sound::load(" << _later << "): mix error=" << Mix_GetError();
		}
		_later.clear();
	}
	return _sound.get();
}

/**
 * Loads a sound file from a specified rwops.
 * @param rw SDL_RWops of the sound data.
 */
void Sound::load(SDL_RWops *rw) {
	auto s = NewSound(Mix_LoadWAV_RW(rw, SDL_TRUE));
	if (!s)
	{
		Log(LOG_ERROR) << "Sound::load(data): mix error=" << Mix_GetError();
	}

	//always overwrite
	_sound = std::move(s);
	_later.clear();
}

/**
 * Plays the contained sound effect.
 * @param channel Use specified channel, -1 to use any channel
 */
void Sound::play(int channel, int angle, int distance) const
 {
	if (!Options::mute && chunk())
 	{
		int chan = Mix_PlayChannel(channel, _sound.get(), 0);
		if (chan == -1)
		{
			Log(LOG_WARNING) << Mix_GetError();
		}
		else if (Options::StereoSound)
		{
			if (!Mix_SetPosition(chan, angle, distance))
			{
				Log(LOG_WARNING) << Mix_GetError();
			}
		}
	}
}

/**
 * Plays the sound of a shot (XP-000400): with oxceHdShotCut the same sound of a shot before, still playing (a shotgun's
 * pump), fades out at once, so that it is not heard over this one. The shots keep their time; only the sound is cut.
 * @param angle Stereo position of the shot.
 */
void Sound::playShot(int angle) const
{
	Mix_Chunk *mine = Options::oxceHdShotCut && !Options::mute ? chunk() : nullptr;
	if (mine)
	{
		const int channels = Mix_AllocateChannels(-1);
		for (int c = 0; c < channels; ++c)
		{
			if (Mix_Playing(c) && Mix_GetChunk(c) == mine)
			{
				// SDL_mixer 1.2.12 puts a faded channel's volume at the maximum when the fade ends (R-561):
				// the channel gives its volume back to the slider when it finishes
				if (c >= 5 && c < 64)   // 0-4 are reserved, with volumes of their own (Game::setVolume)
				{
					g_faded |= 1ull << c;
					if (!g_finishedSet)
					{
						g_finishedSet = true;
						Mix_ChannelFinished(channelFinished);
					}
				}
				Mix_FadeOutChannel(c, 40);
			}
		}
	}
	play(-1, angle);
}

/**
 * Remembers the volume of the sound channels, as Game::setVolume has set it.
 * @param volume Volume from 0 to MIX_MAX_VOLUME.
 */
void Sound::setChannelVolume(int volume)
{
	g_channelVolume = volume;
}

/**
 * Stops all sounds playing.
 */
void Sound::stop()
{
	if (!Options::mute)
	{
		Mix_HaltChannel(-1);
	}
}

/**
 * Plays the contained sound effect repeatedly on the reserved ambience channel.
 */
void Sound::loop()
{
	if (!Options::mute && chunk() && Mix_Playing(3) == 0)
	{
		int chan = Mix_PlayChannel(3, _sound.get(), -1);
		if (chan == -1)
		{
			Log(LOG_WARNING) << Mix_GetError();
		}
	}
}

/**
 * Stops the contained sound from looping.
 */
void Sound::stopLoop()
{
	if (!Options::mute)
	{
		Mix_HaltChannel(3);
	}
}

}
