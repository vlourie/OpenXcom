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

namespace OpenXcom
{

class TextButton;
class Window;
class Text;

/**
 * Second screen of the start-up sequence: which art version to play, the adult
 * one or the classic one. Asked at every start, before the intro, because the
 * answer is not a property of the installation but of the evening: the same
 * player streams without nudity and plays with it.
 *
 * The answer picks which of the two picture trees of the HD mod is read -
 * hd_18+/ or hd/ (HdSprites::artPath) - and nothing else; the adult tree only
 * has to hold the pictures that differ. Picking what was played last time
 * costs nothing, a switch reloads the resources.
 *
 * Options::oxceAdultArt is the version now loaded, Options::oxceAdultAsk turns
 * the question off for anyone who does not want to be asked.
 */
class AdultChoiceState : public State
{
private:
	Window *_window;
	Text *_txtTitle, *_txtInfo;
	TextButton *_btnAdult, *_btnClassic;
	bool _introPending;
	/// Applies the answer and closes the screen.
	void choose(bool adult);
public:
	/// Creates the Adult Choice state.
	AdultChoiceState(bool introPending);
	/// Cleans up the Adult Choice state.
	~AdultChoiceState();
	/// Should the question be asked on this start?
	static bool isNeeded();
	/// Does any active mod ship the adult picture tree?
	static bool adultArtShipped();
	/// Handler for clicking the adult button.
	void btnAdultClick(Action *action);
	/// Handler for clicking the classic button.
	void btnClassicClick(Action *action);
};

}
