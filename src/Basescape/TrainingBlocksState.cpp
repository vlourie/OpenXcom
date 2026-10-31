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
#include "TrainingBlocksState.h"
#include "../Engine/Game.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextList.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the window.
 * @param title Translated name of the transformation.
 * @param blocks Translated names of the paths it closes.
 */
TrainingBlocksState::TrainingBlocksState(const std::string &title, const std::vector<std::string> &blocks)
{
	_screen = false;

	// Create objects
	_window = new Window(this, 256, 168, 32, 16, POPUP_BOTH);
	_txtTitle = new Text(236, 17, 42, 24);
	_txtSubtitle = new Text(236, 9, 42, 42);
	_lstBlocks = new TextList(228, 104, 42, 54);
	_btnOk = new TextButton(120, 16, 100, 162);

	// Set palette
	setInterface("soldierTransformation");

	add(_window, "window", "soldierTransformation");
	add(_txtTitle, "text", "soldierTransformation");
	add(_txtSubtitle, "text", "soldierTransformation");
	add(_lstBlocks, "list1", "soldierTransformation");
	add(_btnOk, "button", "soldierTransformation");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "soldierTransformation");

	_txtTitle->setBig();
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setText(title);

	_txtSubtitle->setAlign(ALIGN_CENTER);
	_txtSubtitle->setText(tr("STR_TRAINING_BLOCKS_TITLE"));

	_lstBlocks->setColumns(1, 228);
	_lstBlocks->setBackground(_window);
	_lstBlocks->setMargin(2);
	for (const auto &name : blocks)
	{
		_lstBlocks->addRow(1, name.c_str());
	}

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&TrainingBlocksState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&TrainingBlocksState::btnOkClick, Options::keyOk);
	_btnOk->onKeyboardPress((ActionHandler)&TrainingBlocksState::btnOkClick, Options::keyCancel);
}

/**
 *
 */
TrainingBlocksState::~TrainingBlocksState()
{

}

/**
 * Returns to the transformation screen.
 * @param action Pointer to an action.
 */
void TrainingBlocksState::btnOkClick(Action *)
{
	_game->popState();
}

}
