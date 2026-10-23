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
#include "TransferBaseState.h"
#include <sstream>
#include "../Engine/Game.h"
#include "../Mod/Mod.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Engine/Unicode.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextList.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Base.h"
#include "../Savegame/Region.h"
#include "../Mod/RuleRegion.h"
#include "TransferItemsState.h"
#include "../Battlescape/DebriefingState.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in the Select Destination Base window.
 * @param game Pointer to the core game.
 * @param base Pointer to the base to get info from.
 */
TransferBaseState::TransferBaseState(Base *base, DebriefingState *debriefingState) : _base(base), _debriefingState(debriefingState), _txtDetail(nullptr)
{
	build();
}

/**
 * Initializes the Select Destination Base window of a workshop order's delivery (option oxceManufactureDelivery): the same list
 * of the other bases, but a click calls back (the caller asks how many to send there) and the window stays.
 * @param base Pointer to the base the order is made at.
 * @param header The text of the line under the title (what is left to give out).
 * @param detail The text of the third column for a base (what is planned for it).
 * @param onPick What to do when a base is clicked.
 */
TransferBaseState::TransferBaseState(Base *base, const std::function<std::string()> &header, const std::function<std::string(Base*)> &detail, const std::function<void(Base*)> &onPick) :
	_base(base), _debriefingState(nullptr), _onPick(onPick), _header(header), _detail(detail), _txtDetail(nullptr)
{
	build();
}

/**
 * Builds the window: the ordinary transfer's list of bases, or the callback variant's one.
 */
void TransferBaseState::build()
{
	const bool callback = (bool)_onPick;
	// Create objects
	_window = new Window(this, 280, 140, 20, 30);
	_btnCancel = new TextButton(264, 16, 28, 146);
	_txtTitle = new Text(270, 17, 25, 38);
	_txtFunds = new Text(250, 9, 30, 54);
	_txtName = new Text(130, 17, 28, 64);
	_txtArea = new Text(130, 17, callback ? 140 : 160, 64);
	_lstBases = new TextList(248, 64, 28, 80);
	if (callback)
	{
		_txtDetail = new Text(60, 17, 228, 64);
	}

	// Set palette
	setInterface("transferBaseSelect");

	add(_window, "window", "transferBaseSelect");
	add(_btnCancel, "button", "transferBaseSelect");
	add(_txtTitle, "text", "transferBaseSelect");
	add(_txtFunds, "text", "transferBaseSelect");
	add(_txtName, "text", "transferBaseSelect");
	add(_txtArea, "text", "transferBaseSelect");
	if (callback)
	{
		add(_txtDetail, "text", "transferBaseSelect");
	}
	add(_lstBases, "list", "transferBaseSelect");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "transferBaseSelect");

	_btnCancel->setText(callback ? tr("STR_OK") : tr("STR_CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&TransferBaseState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&TransferBaseState::btnCancelClick, Options::keyCancel);
	if (callback)
	{
		_btnCancel->onKeyboardPress((ActionHandler)&TransferBaseState::btnCancelClick, Options::keyOk);
	}

	_txtTitle->setBig();
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setText(tr(callback ? "STR_DELIVERY_TITLE" : "STR_SELECT_DESTINATION_BASE"));

	_txtFunds->setText(tr("STR_CURRENT_FUNDS").arg(Unicode::formatFunding(_game->getSavedGame()->getFunds())));

	_txtName->setText(tr("STR_NAME"));
	_txtName->setBig();

	_txtArea->setText(tr("STR_AREA"));
	_txtArea->setBig();

	if (callback)
	{
		_txtDetail->setText(tr("STR_QUANTITY_UC"));
		_txtDetail->setBig();
		_lstBases->setColumns(3, 112, 88, 48);
	}
	else
	{
		_lstBases->setColumns(2, 130, 116);
	}
	_lstBases->setSelectable(true);
	_lstBases->setBackground(_window);
	_lstBases->setMargin(2);
	_lstBases->onMouseClick((ActionHandler)&TransferBaseState::lstBasesClick);

	int row = 0;
	for (auto* xbase : *_game->getSavedGame()->getBases())
	{
		if (xbase != _base)
		{
			// Get area
			std::string area;
			for (const auto* region : *_game->getSavedGame()->getRegions())
			{
				if (region->getRules()->insideRegion(xbase->getLongitude(), xbase->getLatitude()))
				{
					area = tr(region->getRules()->getType());
					break;
				}
			}
			std::ostringstream ss;
			ss << Unicode::TOK_COLOR_FLIP << area;
			if (callback)
			{
				_lstBases->addRow(3, xbase->getName().c_str(), ss.str().c_str(), "");
			}
			else
			{
				_lstBases->addRow(2, xbase->getName().c_str(), ss.str().c_str());
			}
			_bases.push_back(xbase);
			row++;
		}
	}
	if (callback)
	{
		refreshDetail();
	}
}

/**
 * Writes the line under the title and the third column anew (the callback variant).
 */
void TransferBaseState::refreshDetail()
{
	if (_header)
	{
		_txtFunds->setText(_header());
	}
	if (_detail)
	{
		for (size_t i = 0; i < _bases.size(); ++i)
		{
			_lstBases->setCellText(i, 2, _detail(_bases[i]));
		}
	}
}

/**
 * Refreshes the callback variant when the screen above it (the amount) closes.
 */
void TransferBaseState::init()
{
	State::init();
	if (_onPick)
	{
		refreshDetail();
	}
}

/**
 *
 */
TransferBaseState::~TransferBaseState()
{
}

/**
 * Returns to the previous screen.
 * @param action Pointer to an action.
 */
void TransferBaseState::btnCancelClick(Action *)
{
	_game->popState();
}

/**
 * Shows the Transfer screen for the selected base.
 * @param action Pointer to an action.
 */
void TransferBaseState::lstBasesClick(Action *)
{
	if (_onPick)
	{
		_onPick(_bases[_lstBases->getSelectedRow()]);
		return;
	}
	_game->pushState(new TransferItemsState(_base, _bases[_lstBases->getSelectedRow()], _debriefingState));
}

}
