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
#include "HdControl.h"
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cxxabi.h>
#include <deque>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <typeinfo>
#include <vector>
#include <SDL.h>
#include "Game.h"
#include "Screen.h"
#include "State.h"
#include "Options.h"
#include "OptionInfo.h"
#include "Logger.h"
#include "RNG.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Menu/LoadGameState.h"
#include "../Menu/MainMenuState.h"

namespace OpenXcom
{
namespace HdControl
{

namespace
{

struct Control
{
	std::string dir;
	int nextRun = 1;                  // number of the next batch (cmd.<n>.run, done.<n>)
	int batch = 0;                    // the batch being run, 0 - none
	std::deque<std::string> queue;
	std::vector<std::string> results;
	Uint32 lastPoll = 0, waitUntil = 0;
	int modFrames = 0;                // frames left until a held Ctrl/Shift/Alt is let go
	int sinceInput = 99;              // drawn frames since the last input command: a shot needs the screen to settle
	unsigned frames = 0, seenFrames = 0;   // drawn frames; the commands go one per drawn frame
	bool shotPending = false, loadPending = false, quitAfter = false;
	Uint8 pendingButton = 0;          // a click's button, pushed on the frame after its motion
	int pendingX = 0, pendingY = 0;
	std::string waitState;            // waitstate: the class the top state has to become
	Uint32 waitStateUntil = 0;
	std::string shotPath;
	// record: frames dumped one after another while the display clock steps by the frame, not the wall -
	// a clip without jerks however long a frame takes to write
	std::string recordDir, recordPath, nightBefore;
	int recordLeft = 0, recordIndex = 0;
	double recordStep = 0, nightFrom = -1, nightTo = -1;
	bool recordClock = false, hadNight = false;
	Uint32 recordStart = 0, recordNow = 0;
};

Control &ctl()
{
	static Control c;
	return c;
}

std::string trim(const std::string &s)
{
	const size_t a = s.find_first_not_of(" \t\r\n"), b = s.find_last_not_of(" \t\r\n");
	return a == std::string::npos ? std::string() : s.substr(a, b - a + 1);
}

std::string className(const State *s)
{
	int status = 0;
	char *d = abi::__cxa_demangle(typeid(*s).name(), nullptr, nullptr, &status);
	std::string n = (status == 0 && d) ? d : typeid(*s).name();
	free(d);
	const size_t p = n.rfind("::");
	return p == std::string::npos ? n : n.substr(p + 2);
}

// OXCE_HD_BASE_NIGHT (HdBaseScene::nightAt reads it on every frame): a value, or "" to take it away
void putNight(const std::string &value)
{
#ifdef _WIN32
	_putenv(("OXCE_HD_BASE_NIGHT=" + value).c_str());   // "NAME=" removes it
#else
	if (value.empty()) unsetenv("OXCE_HD_BASE_NIGHT"); else setenv("OXCE_HD_BASE_NIGHT", value.c_str(), 1);
#endif
}

bool fileExists(const std::string &path)
{
	std::ifstream f(path.c_str(), std::ios::binary);
	return f.good();
}

// "ctrl+shift+alt+" before the rest: the modifiers held for the next frames
Uint16 takeMods(std::string &s)
{
	Uint16 mods = KMOD_NONE;
	for (bool again = true; again; )
	{
		again = false;
		if (s.compare(0, 5, "ctrl+") == 0) { mods |= KMOD_LCTRL; s.erase(0, 5); again = true; }
		else if (s.compare(0, 6, "shift+") == 0) { mods |= KMOD_LSHIFT; s.erase(0, 6); again = true; }
		else if (s.compare(0, 4, "alt+") == 0) { mods |= KMOD_LALT; s.erase(0, 4); again = true; }
	}
	return mods;
}

void holdMods(Control &c, Uint16 mods)
{
	if (mods != KMOD_NONE)
	{
		SDL_SetModState((SDLMod)mods);
		c.modFrames = 5;
	}
}

// the same pixel the OXCE_HD_CLICK automation uses (Game.cpp): base screen pixel to display pixel
void toDisplay(Game *g, int bx, int by, Uint16 &dx, Uint16 &dy)
{
	dx = (Uint16)(bx * g->getScreen()->getXScale() + g->getScreen()->getCursorLeftBlackBand());
	dy = (Uint16)(by * g->getScreen()->getYScale() + g->getScreen()->getCursorTopBlackBand());
}

void pushButton(Game *g, int bx, int by, Uint8 button)
{
	SDL_Event ev;
	memset(&ev, 0, sizeof(ev));
	ev.type = SDL_MOUSEBUTTONDOWN;
	ev.button.button = button;
	ev.button.state = SDL_PRESSED;
	toDisplay(g, bx, by, ev.button.x, ev.button.y);
	SDL_PushEvent(&ev);
	ev.type = SDL_MOUSEBUTTONUP;
	ev.button.state = SDL_RELEASED;
	SDL_PushEvent(&ev);
}

// the motion goes now, the button on the next drawn frame: a button of the interface is pressed only when the
// mouse was seen over it a frame before (the motion and the press in one pass of the events missed it)
void pushMouse(Control &c, Game *g, int bx, int by, Uint8 button)
{
	SDL_Event ev;
	memset(&ev, 0, sizeof(ev));
	ev.type = SDL_MOUSEMOTION;
	toDisplay(g, bx, by, ev.motion.x, ev.motion.y);
	SDL_PushEvent(&ev);
	if (button != 0)
	{
		c.pendingButton = button;
		c.pendingX = bx;
		c.pendingY = by;
	}
}

bool parseKey(const std::string &s, SDLKey &key)
{
	static const std::map<std::string, SDLKey> names = {
		{"esc", SDLK_ESCAPE}, {"enter", SDLK_RETURN}, {"tab", SDLK_TAB}, {"space", SDLK_SPACE},
		{"backspace", SDLK_BACKSPACE}, {"up", SDLK_UP}, {"down", SDLK_DOWN}, {"left", SDLK_LEFT},
		{"right", SDLK_RIGHT}, {"pageup", SDLK_PAGEUP}, {"pagedown", SDLK_PAGEDOWN}};
	const auto it = names.find(s);
	if (it != names.end())
	{
		key = it->second;
		return true;
	}
	if (s.size() >= 2 && s[0] == 'f' && isdigit((unsigned char)s[1]))
	{
		const int n = atoi(s.c_str() + 1);
		if (n >= 1 && n <= 12)
		{
			key = (SDLKey)(SDLK_F1 + n - 1);
			return true;
		}
	}
	if (s.empty() || s.find_first_not_of("0123456789") != std::string::npos)
	{
		return false;
	}
	key = (SDLKey)atoi(s.c_str());
	return true;
}

std::string stateLine(Game *g)
{
	const auto &states = g->getStates();
	if (states.empty())
	{
		return "state none";
	}
	std::ostringstream out;
	out << "state " << className(states.back()) << " stack=";
	bool first = true;
	for (const State *s : states)
	{
		out << (first ? "" : ">") << className(s);
		first = false;
	}
	if (g->getSavedGame() && g->getSavedGame()->getSavedBattle())
	{
		static const char *sides[] = {"player", "hostile", "neutral"};
		const SavedBattleGame *sb = g->getSavedGame()->getSavedBattle();
		const int side = (int)sb->getSide();
		out << " side=" << (side >= 0 && side < 3 ? sides[side] : "?") << " turn=" << sb->getTurn();
		// the state of the game's random numbers and the save's animation frame: checks that the picture's animation
		// (XP-000097) does not touch the battle
		out << " seed=" << RNG::getSeed() << " animFrame=" << sb->getAnimFrame();
	}
	return out.str();
}

std::string cmdSet(Game *g, const std::string &args)
{
	std::istringstream in(args);
	std::string pair;
	bool any = false, reset = false;
	std::string errors;
	while (in >> pair)
	{
		const size_t eq = pair.find('=');
		if (eq == std::string::npos || eq == 0)
		{
			errors += " bad pair '" + pair + "';";
			continue;
		}
		const std::string key = pair.substr(0, eq), value = pair.substr(eq + 1);
		any = true;
		if (key == "k")
		{
			// the world layer's scale (Screen::setWorldScale resets the display itself)
			g->getScreen()->setWorldScale(atoi(value.c_str()));
			continue;
		}
		bool found = false;
		for (const OptionInfo &info : Options::getOptionInfo())
		{
			if (info.id() == key)
			{
				std::map<std::string, std::string> m;
				m[key] = value;
				info.load(m, false);
				found = reset = true;
				break;
			}
		}
		if (!found)
		{
			errors += " no option '" + key + "';";
		}
	}
	if (reset)
	{
		g->getScreen()->resetDisplay(false);
	}
	if (!any)
	{
		return "err set: key=value expected";
	}
	return errors.empty() ? "ok" : "err set:" + errors;
}

std::string cmdLoad(Control &c, Game *g, const std::string &name)
{
	if (name.empty())
	{
		return "err load: file name expected";
	}
	// the origin as ListLoadState gets it from where the player stands
	OptionsOrigin origin = OPT_MENU;
	if (g->getSavedGame())
	{
		origin = g->getSavedGame()->getSavedBattle() ? OPT_BATTLESCAPE : OPT_GEOSCAPE;
	}
	g->pushState(new LoadGameState(origin, name, g->getStates().back()->getPalette()));
	c.loadPending = true;   // answered when the loading state is gone
	return "";
}

// "" - not finished (a shot or a load waits for frames); otherwise the result line
std::string run(Control &c, Game *g, const std::string &line)
{
	const size_t sp = line.find(' ');
	const std::string cmd = sp == std::string::npos ? line : line.substr(0, sp);
	std::string args = sp == std::string::npos ? std::string() : trim(line.substr(sp + 1));

	if (g->getStates().empty())
	{
		return "err no state";
	}
	if (cmd == "click" || cmd == "rclick" || cmd == "mclick" || cmd == "hover")
	{
		const Uint16 mods = takeMods(args);
		int x, y;
		if (sscanf(args.c_str(), "%d,%d", &x, &y) != 2)
		{
			return "err " + cmd + ": x,y expected";
		}
		holdMods(c, mods);
		pushMouse(c, g, x, y, cmd == "hover" ? 0 : cmd == "rclick" ? SDL_BUTTON_RIGHT : cmd == "mclick" ? SDL_BUTTON_MIDDLE : SDL_BUTTON_LEFT);
		c.sinceInput = 0;
		return "ok";
	}
	if (cmd == "wheel")
	{
		const Uint16 mods = takeMods(args);
		int x, y;
		const bool up = args.compare(0, 2, "up") == 0, down = args.compare(0, 4, "down") == 0;
		if ((!up && !down) || sscanf(args.c_str() + (up ? 2 : 4), "%d,%d", &x, &y) != 2)
		{
			return "err wheel: [ctrl+]up|down x,y expected";
		}
		holdMods(c, mods);
		pushMouse(c, g, x, y, up ? SDL_BUTTON_WHEELUP : SDL_BUTTON_WHEELDOWN);
		c.sinceInput = 0;
		return "ok";
	}
	if (cmd == "key")
	{
		const Uint16 mods = takeMods(args);
		SDLKey key;
		if (!parseKey(args, key))
		{
			return "err key: SDL key number, name or fN expected";
		}
		holdMods(c, mods);
		SDL_Event ev;
		memset(&ev, 0, sizeof(ev));
		ev.type = SDL_KEYDOWN;
		ev.key.state = SDL_PRESSED;
		ev.key.keysym.sym = key;
		ev.key.keysym.mod = (SDLMod)mods;
		SDL_PushEvent(&ev);
		ev.type = SDL_KEYUP;
		ev.key.state = SDL_RELEASED;
		SDL_PushEvent(&ev);
		c.sinceInput = 0;
		return "ok";
	}
	if (cmd == "type")
	{
		for (const char *p = args.c_str(); *p; ++p)
		{
			SDL_Event ev;
			memset(&ev, 0, sizeof(ev));
			ev.type = SDL_KEYDOWN;
			ev.key.state = SDL_PRESSED;
			ev.key.keysym.sym = (SDLKey)(unsigned char)*p;
			ev.key.keysym.unicode = (Uint16)(unsigned char)*p;
			SDL_PushEvent(&ev);
			ev.type = SDL_KEYUP;
			ev.key.state = SDL_RELEASED;
			SDL_PushEvent(&ev);
		}
		c.sinceInput = 0;
		return "ok";
	}
	if (cmd == "wait")
	{
		c.waitUntil = SDL_GetTicks() + (Uint32)std::max(0, atoi(args.c_str()));
		return "ok";
	}
	if (cmd == "waitstate")
	{
		// waitstate Name [ms]: until the top state is Name (a popup that comes by the game's own timer), 30 s by default
		std::istringstream in(args);
		long ms = 30000;
		in >> c.waitState >> ms;
		if (c.waitState.empty())
		{
			return "err waitstate: class name expected";
		}
		c.waitStateUntil = SDL_GetTicks() + (Uint32)std::max(0L, ms);
		return "";
	}
	if (cmd == "shot")
	{
		if (args.empty())
		{
			return "err shot: file name expected";
		}
		remove(args.c_str());   // so that a stale file of an earlier run is not taken for the new one
		c.shotPath = args;
		c.shotPending = true;
		g->getScreen()->requestHdTestDump(args);
		return "";
	}
	if (cmd == "record")
	{
		// record <folder> <frames> <fps> [night <from> <to>]: f00000.png.. in the folder, the night of the living base
		// going from one value to the other over the clip (without it - the base's own clock)
		std::istringstream in(args);
		std::string night;
		double fps = 0;
		c.recordDir.clear();
		c.recordLeft = 0;
		c.nightFrom = c.nightTo = -1;
		in >> c.recordDir >> c.recordLeft >> fps >> night >> c.nightFrom >> c.nightTo;
		if (c.recordDir.empty() || c.recordLeft <= 0 || fps <= 0 || (!night.empty() && (night != "night" || c.nightFrom < 0 || c.nightTo < 0)))
		{
			c.recordLeft = 0;
			return "err record: <folder> <frames> <fps> [night <from> <to>]";
		}
		const char *had = getenv("OXCE_HD_BASE_NIGHT");
		c.hadNight = had != nullptr;
		c.nightBefore = had ? had : "";
		c.recordIndex = 0;
		c.recordStep = 1000.0 / fps;
		c.recordStart = SDL_GetTicks();
		c.recordClock = true;
		return "";
	}
	if (cmd == "set")
	{
		c.sinceInput = 0;
		return cmdSet(g, args);
	}
	if (cmd == "reinit")
	{
		g->getStates().back()->init();
		c.sinceInput = 0;
		return "ok";
	}
	if (cmd == "state")
	{
		return stateLine(g);
	}
	if (cmd == "load")
	{
		c.sinceInput = 0;
		return cmdLoad(c, g, args);
	}
	if (cmd == "open")
	{
		c.sinceInput = 0;
		return MainMenuState::hdStart(g, args) ? "ok" : "err open: geoscape|base|battle|load|newbattle|options|save|ufopaedia";
	}
	if (cmd == "quit")
	{
		c.quitAfter = true;
		return "ok";
	}
	return "err unknown command '" + cmd + "'";
}

void finish(Control &c, Game *g)
{
	const std::string name = c.dir + "/done." + std::to_string(c.batch);
	const std::string tmp = name + ".tmp";
	{
		std::ofstream out(tmp.c_str(), std::ios::binary);
		for (const std::string &r : c.results)
		{
			out << r << "\n";
		}
		out << "end\n";
	}
	remove(name.c_str());
	if (rename(tmp.c_str(), name.c_str()) != 0)
	{
		Log(LOG_ERROR) << "HdControl: cannot write " << name;
	}
	c.results.clear();
	c.batch = 0;
	if (c.quitAfter)
	{
		g->quit();
	}
}

// a new cmd.txt: renamed to cmd.<n>.run (the client never sees it half read), its lines become the queue
void poll(Control &c)
{
	const std::string cmd = c.dir + "/cmd.txt";
	if (!fileExists(cmd))
	{
		return;
	}
	const std::string runFile = c.dir + "/cmd." + std::to_string(c.nextRun) + ".run";
	remove(runFile.c_str());
	if (rename(cmd.c_str(), runFile.c_str()) != 0)
	{
		return;   // the client still holds it: next time
	}
	std::ifstream in(runFile.c_str(), std::ios::binary);
	std::string line;
	bool first = true;
	while (std::getline(in, line))
	{
		if (first && line.compare(0, 3, "\xEF\xBB\xBF") == 0)
		{
			line.erase(0, 3);
		}
		first = false;
		line = trim(line);
		if (!line.empty() && line[0] != '#')
		{
			c.queue.push_back(line);
		}
	}
	c.batch = c.nextRun++;
	c.results.clear();
}

}

bool enabled()
{
	static const char *dir = getenv("OXCE_HD_CONTROL");
	return dir && *dir;
}

void frameDrawn()
{
	if (enabled())
	{
		++ctl().frames;
	}
}

unsigned ticks()
{
	const Control &c = ctl();
	return c.recordClock ? c.recordNow : SDL_GetTicks();
}

void step(Game *g)
{
	if (!enabled())
	{
		return;
	}
	Control &c = ctl();
	if (c.dir.empty())
	{
		c.dir = getenv("OXCE_HD_CONTROL");
		while (c.dir.size() > 1 && (c.dir.back() == '/' || c.dir.back() == '\\'))
		{
			c.dir.pop_back();
		}
	}
	const Uint32 now = SDL_GetTicks();
	if (c.batch == 0)
	{
		if (now - c.lastPoll >= 100)
		{
			c.lastPoll = now;
			poll(c);
		}
		if (c.batch == 0)
		{
			return;
		}
	}
	if (c.frames == c.seenFrames)
	{
		return;
	}
	c.seenFrames = c.frames;
	if (c.modFrames > 0 && --c.modFrames == 0)
	{
		SDL_SetModState(KMOD_NONE);
	}
	++c.sinceInput;
	if (c.pendingButton != 0)
	{
		pushButton(g, c.pendingX, c.pendingY, c.pendingButton);
		c.pendingButton = 0;
		c.sinceInput = 0;
		return;
	}
	if (!c.waitState.empty())
	{
		const auto &states = g->getStates();
		const std::string top = states.empty() ? "none" : className(states.back());
		if (top == c.waitState)
		{
			c.results.push_back("ok");
		}
		else if (now >= c.waitStateUntil)
		{
			c.results.push_back("err waitstate: top is " + top + ", not " + c.waitState);
		}
		else
		{
			return;
		}
		c.waitState.clear();
		return;
	}
	if (c.loadPending)
	{
		const auto &states = g->getStates();
		if (!states.empty() && className(states.back()) == "LoadGameState")
		{
			return;
		}
		c.loadPending = false;
		c.results.push_back(!states.empty() && className(states.back()) == "ErrorMessageState" ? "err load: the game refused the save (see openxcom.log)" : "ok");
		return;
	}
	if (c.recordClock)
	{
		if (g->getScreen()->hasHdTestDumpRequest())
		{
			return;
		}
		if (c.recordLeft == 0)
		{
			// the last frame is written: back to the wall clock and the night as it was
			c.recordClock = false;
			if (c.nightFrom >= 0)
			{
				putNight(c.hadNight ? c.nightBefore : "");
			}
			c.results.push_back(fileExists(c.recordPath) ? "ok record " + std::to_string(c.recordIndex) + " frames"
				: "err record: frame not written " + c.recordPath);
			return;
		}
		// this turn's frame is drawn at this clock and written after the states are blitted (Screen::writeHdTestDump)
		c.recordNow = c.recordStart + (Uint32)(c.recordIndex * c.recordStep + 0.5);
		if (c.nightFrom >= 0)
		{
			const int last = c.recordIndex + c.recordLeft - 1;
			const double t = last > 0 ? (double)c.recordIndex / last : 0;
			putNight(std::to_string(c.nightFrom + (c.nightTo - c.nightFrom) * t));
		}
		char name[32];
		snprintf(name, sizeof(name), "/f%05d.png", c.recordIndex);
		c.recordPath = c.recordDir + name;
		remove(c.recordPath.c_str());
		g->getScreen()->requestHdTestDump(c.recordPath);
		++c.recordIndex;
		--c.recordLeft;
		return;
	}
	if (c.shotPending)
	{
		if (g->getScreen()->hasHdTestDumpRequest())
		{
			return;
		}
		c.shotPending = false;
		c.results.push_back(fileExists(c.shotPath) ? "ok" : "err shot: file not written " + c.shotPath);
		return;
	}
	if (now < c.waitUntil)
	{
		return;
	}
	if (c.queue.empty())
	{
		finish(c, g);
		return;
	}
	// the frame to shoot has to follow the input by a couple of drawn frames (a state pushed by a click is
	// initialised on the next one) and wait for another dump of the game's own still in flight
	if (c.queue.front().compare(0, 4, "shot") == 0 && (c.sinceInput < 3 || g->getScreen()->hasHdTestDumpRequest()))
	{
		return;
	}
	const std::string line = c.queue.front();
	c.queue.pop_front();
	const std::string r = run(c, g, line);
	if (!r.empty())
	{
		c.results.push_back(r);
	}
}

}
}
