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
#include "ManufactureDeliveryState.h"
#include <algorithm>
#include <climits>
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/InteractiveSurface.h"
#include "../Engine/Language.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Engine/Timer.h"
#include "../Interface/ArrowButton.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextList.h"
#include "../Interface/Window.h"
#include "../Savegame/Base.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleManufacture.h"
#include "../Savegame/Production.h"

namespace OpenXcom
{

/**
 * Initializes all the elements of the window.
 * @param production The order the share is taken from.
 * @param to The base the share goes to.
 * @param max The most that can go there: what is not given to the other bases yet plus what is planned for this one.
 */
ManufactureDeliveryState::ManufactureDeliveryState(Production *production, Base *to, int max) : ManufactureDeliveryState(production, to, max, nullptr, 0,
	[production](int orders)
	{
		// the whole product of an order times the number of orders (a disassembly gives several kinds)
		Items items;
		for (const auto &i : production->getRules()->getProducedItems())
		{
			items.emplace_back(i.first, orders * i.second);
		}
		return items;
	})
{
}

/**
 * Initializes the window for the loot of a finished order (XP-000292).
 * @param to The base the loot goes to.
 * @param max The most that can go there.
 * @param onOk Called with the number when OK is clicked (after the window is closed).
 * @param what What goes for a number of units: the line under the title.
 */
ManufactureDeliveryState::ManufactureDeliveryState(Base *to, int max, const std::function<void(int)> &onOk, const std::function<Items(int)> &what) : ManufactureDeliveryState(nullptr, to, max, onOk, max, what)
{
}

ManufactureDeliveryState::ManufactureDeliveryState(Production *production, Base *to, int max, const std::function<void(int)> &onOk, int start, const std::function<Items(int)> &what) : _production(production), _to(to), _max(max), _amount(0), _onOk(onOk), _what(what)
{
	_screen = false;
	_amount = _production ? std::min(_production->getDeliveryShare(_to), _max) : std::max(0, std::min(start, _max));

	// Create objects
	// taller than it was: the line of what goes (up to three lines) stands under the title
	_window = new Window(this, 200, 124, 60, 38, POPUP_BOTH);
	_txtTitle = new Text(184, 24, 68, 46);
	_txtWhat = new Text(184, 27, 68, 72);
	_txtAmount = new Text(60, 16, 130, 102);
	_btnLess = new ArrowButton(ARROW_BIG_DOWN, 13, 14, 108, 102);
	_btnMore = new ArrowButton(ARROW_BIG_UP, 13, 14, 192, 102);
	_btnOk = new TextButton(84, 16, 68, 134);
	_btnCancel = new TextButton(84, 16, 168, 134);
	// the wheel works on the whole window
	_surface = new InteractiveSurface(200, 124, 60, 38);
	_surface->onMouseClick((ActionHandler)&ManufactureDeliveryState::handleWheel, 0);

	// Set palette
	setInterface("manufactureInfo");

	add(_surface);
	add(_window, "window", "manufactureInfo");
	add(_txtTitle, "text", "manufactureInfo");
	add(_txtWhat, "text", "manufactureInfo");
	add(_txtAmount, "text", "manufactureInfo");
	add(_btnLess, "button1", "manufactureInfo");
	add(_btnMore, "button1", "manufactureInfo");
	add(_btnOk, "button2", "manufactureInfo");
	add(_btnCancel, "button2", "manufactureInfo");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "manufactureInfo");

	_txtTitle->setBig();
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setWordWrap(true);
	_txtTitle->setText(tr("STR_DELIVERY_AMOUNT").arg(_to->getName()));

	_txtWhat->setAlign(ALIGN_CENTER);
	_txtWhat->setWordWrap(true);

	_txtAmount->setBig();
	_txtAmount->setAlign(ALIGN_CENTER);

	_btnLess->onMousePress((ActionHandler)&ManufactureDeliveryState::lessPress);
	_btnLess->onMouseRelease((ActionHandler)&ManufactureDeliveryState::lessRelease);
	_btnLess->onMouseClick((ActionHandler)&ManufactureDeliveryState::lessClick, 0);
	_btnMore->onMousePress((ActionHandler)&ManufactureDeliveryState::morePress);
	_btnMore->onMouseRelease((ActionHandler)&ManufactureDeliveryState::moreRelease);
	_btnMore->onMouseClick((ActionHandler)&ManufactureDeliveryState::moreClick, 0);

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&ManufactureDeliveryState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&ManufactureDeliveryState::btnOkClick, Options::keyOk);

	_btnCancel->setText(tr("STR_CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&ManufactureDeliveryState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&ManufactureDeliveryState::btnCancelClick, Options::keyCancel);

	_timerMore = new Timer(250);
	_timerLess = new Timer(250);
	_timerMore->onTimer((StateHandler)&ManufactureDeliveryState::onMore);
	_timerLess->onTimer((StateHandler)&ManufactureDeliveryState::onLess);

	update();
}

/**
 * Frees up memory that's not automatically cleaned on exit.
 */
ManufactureDeliveryState::~ManufactureDeliveryState()
{
	delete _timerMore;
	delete _timerLess;
}

/**
 * Shows the number and how many there can be at most.
 */
void ManufactureDeliveryState::update()
{
	_txtAmount->setText(std::to_string(_amount) + "/" + std::to_string(_max));
	if (_what)
	{
		// "item xN, item xM -> base"; nothing at 0 (the base leaves the plan)
		_txtWhat->setText(_amount > 0 ? tr("STR_DELIVERY_WILL_GO").arg(describe(_game->getLanguage(), _what(_amount))).arg(_to->getName()) : tr("STR_DELIVERY_NONE").arg(_to->getName()));
	}
}

/**
 * Writes what goes: the first three kinds with their numbers, then dots.
 * @param lang The language of the names.
 * @param items The items and the number of each (those with none are left out).
 * @return The text, for example "Medi-kit x4, Stimulant x2".
 */
std::string ManufactureDeliveryState::describe(const Language *lang, const Items &items)
{
	const size_t shown = 3;
	std::string out;
	size_t n = 0;
	for (const auto &i : items)
	{
		if (i.second <= 0)
		{
			continue;
		}
		if (n == shown)
		{
			out += ", ...";
			break;
		}
		if (n > 0)
		{
			out += ", ";
		}
		out += std::string(lang->getString("STR_DELIVERY_ITEM_QTY").arg(lang->getString(i.first->getType())).arg(i.second));
		++n;
	}
	return out;
}

/**
 * Changes the number within 0..max.
 * @param by How much to add (negative: to take).
 */
void ManufactureDeliveryState::change(int by)
{
	const int now = std::max(0, std::min(_max, _amount + by));
	if (now != _amount)
	{
		_amount = now;
		update();
	}
}

void ManufactureDeliveryState::morePress(Action *action)
{
	if (_game->isLeftClick(action, true)) _timerMore->start();
}

void ManufactureDeliveryState::moreRelease(Action *action)
{
	if (_game->isLeftClick(action, true))
	{
		_timerMore->setInterval(250);
		_timerMore->stop();
	}
}

/**
 * Left click: one more (the scroll step); right click: all that is left.
 */
void ManufactureDeliveryState::moreClick(Action *action)
{
	if (_game->isRightClick(action, true)) change(INT_MAX / 2);
	if (_game->isLeftClick(action, true)) change(_game->getScrollStep());
}

void ManufactureDeliveryState::lessPress(Action *action)
{
	if (_game->isLeftClick(action, true)) _timerLess->start();
}

void ManufactureDeliveryState::lessRelease(Action *action)
{
	if (_game->isLeftClick(action, true))
	{
		_timerLess->setInterval(250);
		_timerLess->stop();
	}
}

/**
 * Left click: one less (the scroll step); right click: none.
 */
void ManufactureDeliveryState::lessClick(Action *action)
{
	if (_game->isRightClick(action, true)) change(-INT_MAX / 2);
	if (_game->isLeftClick(action, true)) change(-_game->getScrollStep());
}

void ManufactureDeliveryState::onMore()
{
	_timerMore->setInterval(50);
	change(_game->getScrollStep());
}

void ManufactureDeliveryState::onLess()
{
	_timerLess->setInterval(50);
	change(-_game->getScrollStep());
}

/**
 * The mouse wheel changes the number.
 */
void ManufactureDeliveryState::handleWheel(Action *action)
{
	if (action->getDetails()->button.button == SDL_BUTTON_WHEELUP) change(Options::changeValueByMouseWheel);
	else if (action->getDetails()->button.button == SDL_BUTTON_WHEELDOWN) change(-Options::changeValueByMouseWheel);
}

/**
 * Writes the share into the plan of the order (0 takes the base out of it) and closes the window.
 */
void ManufactureDeliveryState::btnOkClick(Action *)
{
	if (_onOk)
	{
		// closed first: the callback may open a window of its own, which must not be the one popState takes
		const std::function<void(int)> onOk = _onOk;
		const int amount = _amount;
		_game->popState();
		onOk(amount);
		return;
	}
	_production->setDeliveryShare(_to, _amount);
	_game->popState();
}

/**
 * Closes the window, the plan stays as it was.
 */
void ManufactureDeliveryState::btnCancelClick(Action *)
{
	_game->popState();
}

/**
 * Runs the timers of the arrows.
 */
void ManufactureDeliveryState::think()
{
	State::think();
	_timerMore->think(this, 0);
	_timerLess->think(this, 0);
}

/**
 * Initializes the window of the loot by kinds (XP-000297): every kind starts at the most, as the one number of the other window does.
 * @param to The base the loot goes to.
 * @param items The kinds and the most of each that can go (more than 0).
 * @param onOk Called with the kinds picked (a number above 0) when OK is clicked, after the window is closed.
 */
ManufactureLootPartsState::ManufactureLootPartsState(Base *to, const Items &items, const std::function<void(const Items&)> &onOk) : _to(to), _items(items), _onOk(onOk)
{
	_screen = false;
	for (const auto &i : _items)
	{
		_amount.push_back(i.second);
	}

	// Create objects
	_window = new Window(this, 240, 150, 40, 25, POPUP_BOTH);
	_txtTitle = new Text(224, 24, 48, 31);
	_lstParts = new TextList(224, 78, 47, 58);
	_txtTotal = new Text(224, 9, 48, 138);
	_btnOk = new TextButton(104, 16, 48, 153);
	_btnCancel = new TextButton(104, 16, 168, 153);

	// Set palette
	setInterface("manufactureInfo");

	add(_window, "window", "manufactureInfo");
	add(_txtTitle, "text", "manufactureInfo");
	add(_lstParts, "list", "manufactureInfo");
	add(_txtTotal, "text", "manufactureInfo");
	add(_btnOk, "button2", "manufactureInfo");
	add(_btnCancel, "button2", "manufactureInfo");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "manufactureInfo");

	_txtTitle->setBig();
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setWordWrap(true);
	_txtTitle->setText(tr("STR_DELIVERY_AMOUNT").arg(_to->getName()));

	_txtTotal->setAlign(ALIGN_CENTER);

	// the one by one arrows as on the summary list of the finished order: left - less, right - more; the right button goes to the end
	_lstParts->setColumns(2, 150, 36);
	_lstParts->setBackground(_window);
	_lstParts->setSelectable(true);
	_lstParts->setMargin(8);
	_lstParts->setArrowColumn(194, ARROW_HORIZONTAL);
	_lstParts->onLeftArrowClick((ActionHandler)&ManufactureLootPartsState::leftArrowClick);
	_lstParts->onRightArrowClick((ActionHandler)&ManufactureLootPartsState::rightArrowClick);
	for (size_t i = 0; i < _items.size(); ++i)
	{
		_lstParts->addRow(2, tr(_items[i].first->getType()).c_str(), "");
		refresh(i);
	}

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&ManufactureLootPartsState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&ManufactureLootPartsState::btnOkClick, Options::keyOk);

	_btnCancel->setText(tr("STR_CANCEL"));
	_btnCancel->onMouseClick((ActionHandler)&ManufactureLootPartsState::btnCancelClick);
	_btnCancel->onKeyboardPress((ActionHandler)&ManufactureLootPartsState::btnCancelClick, Options::keyCancel);
}

ManufactureLootPartsState::~ManufactureLootPartsState()
{
}

/**
 * Writes the number of a row ("picked/most") and the total of pieces that go.
 * @param row The row.
 */
void ManufactureLootPartsState::refresh(size_t row)
{
	if (row < _items.size())
	{
		_lstParts->setCellText(row, 1, std::to_string(_amount[row]) + "/" + std::to_string(_items[row].second));
	}
	int total = 0;
	for (int n : _amount)
	{
		total += n;
	}
	_txtTotal->setText(tr("STR_LOOT_PARTS_TOTAL").arg(total));
}

/**
 * Changes the selected row's number within 0..most.
 * @param by How much to add (negative: to take).
 */
void ManufactureLootPartsState::change(int by)
{
	const size_t row = _lstParts->getSelectedRow();
	if (row >= _items.size())
	{
		return;
	}
	_amount[row] = std::max(0, std::min(_items[row].second, _amount[row] + by));
	refresh(row);
}

/**
 * Left arrow: one less (the scroll step); right click: none.
 */
void ManufactureLootPartsState::leftArrowClick(Action *action)
{
	if (_game->isRightClick(action, true)) change(-INT_MAX / 2);
	else if (_game->isLeftClick(action, true)) change(-_game->getScrollStep());
}

/**
 * Right arrow: one more (the scroll step); right click: all that is left.
 */
void ManufactureLootPartsState::rightArrowClick(Action *action)
{
	if (_game->isRightClick(action, true)) change(INT_MAX / 2);
	else if (_game->isLeftClick(action, true)) change(_game->getScrollStep());
}

/**
 * Closes the window and hands the kinds picked to the callback.
 */
void ManufactureLootPartsState::btnOkClick(Action *)
{
	Items picked;
	for (size_t i = 0; i < _items.size(); ++i)
	{
		if (_amount[i] > 0)
		{
			picked.emplace_back(_items[i].first, _amount[i]);
		}
	}
	// closed first: the callback may open a window of its own, which must not be the one popState takes
	const std::function<void(const Items&)> onOk = _onOk;
	_game->popState();
	if (onOk && !picked.empty())
	{
		onOk(picked);
	}
}

/**
 * Closes the window, nothing is sent.
 */
void ManufactureLootPartsState::btnCancelClick(Action *)
{
	_game->popState();
}

}
