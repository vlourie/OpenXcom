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

namespace OpenXcom
{

class TextButton;
class Window;
class Text;

/**
 * The photosensitivity warning of the start-up sequence: after the language,
 * before the art version and before the intro - the intro is the first thing
 * that flashes. It offers the gentle mode (Engine/HdGentle.h).
 *
 * Asked until answered once (Options::oxceGentleAsk); the mode itself is changed
 * later on the HD tab. The screen does not flash itself: no popup animation.
 * Its strings live in Language/OXCE, which the engine always loads, so the
 * question never shows raw keys (rake R-036).
 */
class GentleChoiceState : public State
{
private:
	Window *_window;
	Text *_txtTitle, *_txtInfo;
	TextButton *_btnGentle, *_btnUsual;
	bool _introPending;
	/// Applies the answer and hands over to the next question.
	void choose(bool gentle);
public:
	/// Creates the Gentle Choice state.
	GentleChoiceState(bool introPending);
	/// Cleans up the Gentle Choice state.
	~GentleChoiceState();
	/// Should the question be asked on this start?
	static bool isNeeded();
	/// Handler for clicking the gentle button.
	void btnGentleClick(Action *action);
	/// Handler for clicking the usual button.
	void btnUsualClick(Action *action);
};

}
