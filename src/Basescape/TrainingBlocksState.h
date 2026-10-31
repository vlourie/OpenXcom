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
#include <string>
#include <vector>
#include "../Engine/State.h"

namespace OpenXcom
{

class TextButton;
class Window;
class Text;
class TextList;

/**
 * Lists the training paths a transformation closes to the soldier (option oxceHdTrainingBlocks).
 */
class TrainingBlocksState : public State
{
private:
	TextButton *_btnOk;
	Window *_window;
	Text *_txtTitle, *_txtSubtitle;
	TextList *_lstBlocks;
public:
	/// Creates the window over the soldier transformation screen.
	TrainingBlocksState(const std::string &title, const std::vector<std::string> &blocks);
	/// Cleans up the window.
	~TrainingBlocksState();
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
};

}
