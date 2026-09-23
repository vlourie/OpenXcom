#pragma once
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
#include "../Engine/State.h"
#include <string>
#include <vector>

namespace OpenXcom
{

class TextList;
class Window;
class Text;

/**
 * First screen of the start-up sequence: which language to play in.
 *
 * It is drawn before anything else the player can read, so it carries no
 * translated strings of its own - every language is named in itself, the way
 * the options screen names them. The answer IS written down (Options::language),
 * unlike the art version that follows it, so the list opens on last time's
 * choice and Esc keeps it.
 *
 * The screen hands over to AdultChoiceState itself rather than being pushed
 * under it: that screen's texts are built in its constructor, so it may only
 * be created once the language is already loaded.
 */
class LanguageChoiceState : public State
{
private:
	Window *_window;
	Text *_txtTitle;
	TextList *_lstLanguages;
	std::vector<std::string> _ids;
	bool _introPending;
	/// Applies the language and moves on to the art version question.
	void choose(const std::string &id);
public:
	/// Creates the Language Choice state.
	LanguageChoiceState(bool introPending);
	/// Cleans up the Language Choice state.
	~LanguageChoiceState();
	/// Is there anything to choose from?
	static bool isNeeded();
	/// Handler for clicking a language.
	void lstLanguagesClick(Action *action);
	/// Handler for keeping the current language.
	void keepCurrent(Action *action);
};

}
