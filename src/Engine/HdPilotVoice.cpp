/*
 * Pilot voices on the geoscape (ticket XP-000246); see HdPilotVoice.h.
 */
#include "HdPilotVoice.h"
#include <map>
#include <memory>
#include <random>
#include <string>
#include <utility>
#include <vector>
#include <SDL.h>
#include <SDL_mixer.h>
#include "FileMap.h"
#include "HdSprites.h"
#include "Logger.h"
#include "Options.h"
#include "Sound.h"
#include "../Mod/RuleCraft.h"
#include "../Savegame/Craft.h"

namespace OpenXcom
{

namespace HdPilotVoice
{

namespace
{

const char *const NAMES[EVENT_COUNT] = { "select", "order", "attack", "escort", "return", "rebase", "wing", "cancel", "damaged", "noammo" };
/// Unit responses (Game::setVolume: the voice slider).
const int CHANNEL = 4;
/// A craft repeats the same report no sooner than this, in ms of real time.
const Uint32 REPORT_PAUSE = 20000;

/// The lines of one event in one language, loaded on first use.
struct Lines
{
	std::vector<std::unique_ptr<Sound> > sounds;
	int last = -1;
};

std::map<std::string, Lines> _lines;
std::map<std::pair<const Craft*, int>, Uint32> _reported;

std::mt19937 &gen()
{
	static std::mt19937 g(SDL_GetTicks() ^ 0x9E3779B9u);
	return g;
}

bool ready()
{
	return Options::oxceHdPilotVoice && !Options::mute && Mix_QuerySpec(nullptr, nullptr, nullptr) != 0;
}

/// hd/PILOT/<kind>/<event>/<lang>_<N>.ogg for N = 1, 2, ... up to the first missing file.
Lines &load(const std::string &kind, Event ev, const std::string &lang)
{
	const std::string dir = "PILOT/" + kind + "/" + NAMES[ev] + "/" + lang + "_";
	auto it = _lines.find(dir);
	if (it != _lines.end())
	{
		return it->second;
	}
	Lines &lines = _lines[dir];
	for (int n = 1; ; ++n)
	{
		const std::string path = HdSprites::artPath(dir + std::to_string(n) + ".ogg");
		if (!FileMap::fileExists(path))
		{
			break;
		}
		lines.sounds.emplace_back(new Sound());
		lines.sounds.back()->load(path);
	}
	return lines;
}

/// Plays a line of the craft's speaker; false when there is none.
bool say(const Craft *craft, Event ev)
{
	if (!craft || ev < 0 || ev >= EVENT_COUNT || !ready())
	{
		return false;
	}
	const int alt = craft->getRules()->getMaxAltitude();
	const std::string kind = (alt >= 0 && alt <= 1) ? "ground" : "air";
	Lines *lines = &load(kind, ev, Options::language.compare(0, 2, "ru") == 0 ? "ru" : "en");
	if (lines->sounds.empty())
	{
		lines = &load(kind, ev, "en");
		if (lines->sounds.empty())
		{
			return false;
		}
	}
	const int count = (int)lines->sounds.size();
	int pick = 0;
	if (count > 1)
	{
		// never the same line twice in a row
		pick = std::uniform_int_distribution<int>(0, count - 2)(gen());
		if (lines->last >= 0 && pick >= lines->last)
		{
			++pick;
		}
	}
	lines->last = pick;
	lines->sounds[pick]->play(CHANNEL);
	Log(LOG_INFO) << "HD pilot voice: " << kind << " " << NAMES[ev] << " " << (pick + 1) << "/" << count;
	return true;
}

}

void order(const Craft *craft, Event ev)
{
	say(craft, ev);
}

void report(const Craft *craft, Event ev)
{
	if (!ready() || Mix_Playing(CHANNEL))
	{
		return;
	}
	const Uint32 now = SDL_GetTicks();
	auto key = std::make_pair(craft, (int)ev);
	auto it = _reported.find(key);
	if (it != _reported.end() && now - it->second < REPORT_PAUSE)
	{
		return;
	}
	if (say(craft, ev))
	{
		_reported[key] = now;
	}
}

}

}
