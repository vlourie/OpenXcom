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
#include <algorithm>
#include <sstream>
#include "TradeConfirmState.h"
#include "../Engine/Game.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Engine/Unicode.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextList.h"

namespace OpenXcom
{

/**
 * Whether the chosen lines are enough to ask (option oxceTradeConfirm: from this many lines, 0 - never).
 * @param rows All rows of the trade screen.
 */
bool TradeConfirmState::wanted(const std::vector<TransferRow> &rows)
{
	if (Options::oxceTradeConfirm <= 0)
		return false;
	auto lines = std::count_if(rows.begin(), rows.end(), [](const TransferRow &row) { return row.amount > 0; });
	return lines >= Options::oxceTradeConfirm;
}

/**
 * Initializes all the elements in the confirmation window.
 * @param rows All rows of the trade screen; the ones with an amount are listed.
 * @param total Money the trade takes or brings.
 * @param title Title string id.
 * @param category Interface category of the trade screen: its palette and colours.
 * @param confirm Does the trade; called after the window closes.
 */
TradeConfirmState::TradeConfirmState(const std::vector<TransferRow> &rows, int64_t total, const std::string &title, const std::string &category, std::function<void()> confirm) : _confirm(std::move(confirm))
{
	_screen = false;

	// Create objects
	_window = new Window(this, 280, 168, 20, 16, POPUP_BOTH);
	_txtTitle = new Text(260, 17, 30, 24);
	_lstItems = new TextList(256, 96, 28, 44);
	_txtTotal = new Text(260, 9, 30, 146);
	_btnOk = new TextButton(120, 16, 34, 160);
	_btnCancel = new TextButton(120, 16, 166, 160);

	// Set palette
	setInterface(category);

	add(_window, "window", category);
	add(_txtTitle, "text", category);
	add(_lstItems, "list", category);
	add(_txtTotal, "text", category);
	add(_btnOk, "button", category);
	add(_btnCancel, "button", category);

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, category);

	_txtTitle->setBig();
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setText(tr(title));

	_lstItems->setColumns(3, 160, 32, 56);
	_lstItems->setAlign(ALIGN_RIGHT, 1);
	_lstItems->setAlign(ALIGN_RIGHT, 2);
	_lstItems->setBackground(_window);
	_lstItems->setMargin(2);
	for (const auto &row : rows)
	{
		if (row.amount <= 0)
			continue;
		std::ostringstream ssAmount;
		ssAmount << row.amount;
		_lstItems->addRow(3, row.name.c_str(), ssAmount.str().c_str(), Unicode::formatFunding(row.cost * row.amount).c_str());
	}

	_txtTotal->setAlign(ALIGN_CENTER);
	_txtTotal->setText(tr("STR_TRADE_CONFIRM_TOTAL").arg(Unicode::formatFunding(total)));

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&TradeConfirmState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&TradeConfirmState::btnOkClick, Options::keyOk);

	_btnCancel->setText(tr("STR_CANCEL_UC"));
	_btnCancel->onMouseClick((ActionHandler)&TradeConfirmState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&TradeConfirmState::btnCancelClick, Options::keyCancel);
}

/**
 *
 */
TradeConfirmState::~TradeConfirmState()
{

}

/**
 * Closes the window and does the trade.
 * @param action Pointer to an action.
 */
void TradeConfirmState::btnOkClick(Action *)
{
	auto confirm = _confirm;
	_game->popState();
	confirm();
}

/**
 * Returns to the trade screen with the choice untouched.
 * @param action Pointer to an action.
 */
void TradeConfirmState::btnCancelClick(Action *)
{
	_game->popState();
}

}
