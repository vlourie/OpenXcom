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
#include "../Engine/State.h"
#include <atomic>
#include <string>
#include <sstream>

namespace OpenXcom
{

class Text;
class Font;
class Timer;
class Language;

enum LoadingPhase { LOADING_STARTED, LOADING_FAILED, LOADING_SUCCESSFUL, LOADING_DONE };

/**
 * Initializes the game and loads all required content.
 */
class StartState : public State
{
private:
	Text *_text, *_cursor;
	Font *_font;
	Timer *_timer;
	Language *_lang;
	int _anim;
	std::string _oldMaster;

	/// The data loading thread while it may still run (0 once it has been waited for).
	static SDL_Thread *_thread;
	std::ostringstream _output;
public:
	/// Waits for the data loading thread if it still runs; safe to call again (main thread only).
	static void waitLoading();
	/// The loading thread's verdict. The thread stores it as its very last step, after `error` and after the mod
	/// and the language are complete; the main thread reads those only after it has seen the verdict here.
	static std::atomic<LoadingPhase> loading;
	static std::string error;
	/// Play the intro once the next load is done? Set when a reload throws away a pending cutscene.
	static bool playIntroAfterReload;

	/// Creates the Start state.
	StartState();
	/// Cleans up the Start state.
	~StartState();
	/// Reset everything.
	void init() override;
	/// Displays messages.
	void think() override;
	/// Handles key clicks.
	void handle(Action *action) override;
	/// Animates the terminal.
	void animate();
	/// Adds a line of text.
	void addLine(const std::string &str);
	/// Loads the game resources.
	static int load(void *game_ptr);
};

}
