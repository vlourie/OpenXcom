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
#include <functional>
#include <string>
#include <vector>
#include "../Engine/State.h"
#include "../Savegame/Transfer.h"

namespace OpenXcom
{

class TextButton;
class Window;
class Text;
class TextList;

/**
 * Asks to confirm a purchase or a sale: the chosen lines with their quantity and sum, and the total.
 */
class TradeConfirmState : public State
{
private:
	TextButton *_btnOk, *_btnCancel;
	Window *_window;
	Text *_txtTitle, *_txtTotal;
	TextList *_lstItems;
	std::function<void()> _confirm;
public:
	/// Whether enough lines are chosen to ask (option oxceTradeConfirm).
	static bool wanted(const std::vector<TransferRow> &rows);
	/// Creates the window over the trade screen of the given interface category.
	TradeConfirmState(const std::vector<TransferRow> &rows, int64_t total, const std::string &title, const std::string &category, std::function<void()> confirm);
	/// Cleans up the window.
	~TradeConfirmState();
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the Cancel button.
	void btnCancelClick(Action *action);
};

}
