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
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Engine/Timer.h"
#include "../Interface/ArrowButton.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Savegame/Base.h"
#include "../Savegame/Production.h"

namespace OpenXcom
{

/**
 * Initializes all the elements of the window.
 * @param production The order the share is taken from.
 * @param to The base the share goes to.
 * @param max The most that can go there: what is not given to the other bases yet plus what is planned for this one.
 */
ManufactureDeliveryState::ManufactureDeliveryState(Production *production, Base *to, int max) : ManufactureDeliveryState(production, to, max, nullptr, 0)
{
}

/**
 * Initializes the window for the loot of a finished order (XP-000292).
 * @param to The base the loot goes to.
 * @param max The most that can go there.
 * @param onOk Called with the number when OK is clicked (after the window is closed).
 */
ManufactureDeliveryState::ManufactureDeliveryState(Base *to, int max, const std::function<void(int)> &onOk) : ManufactureDeliveryState(nullptr, to, max, onOk, max)
{
}

ManufactureDeliveryState::ManufactureDeliveryState(Production *production, Base *to, int max, const std::function<void(int)> &onOk, int start) : _production(production), _to(to), _max(max), _amount(0), _onOk(onOk)
{
	_screen = false;
	_amount = _production ? std::min(_production->getDeliveryShare(_to), _max) : std::max(0, std::min(start, _max));

	// Create objects
	_window = new Window(this, 200, 96, 60, 52, POPUP_BOTH);
	_txtTitle = new Text(184, 24, 68, 60);
	_txtAmount = new Text(60, 16, 130, 94);
	_btnLess = new ArrowButton(ARROW_BIG_DOWN, 13, 14, 108, 94);
	_btnMore = new ArrowButton(ARROW_BIG_UP, 13, 14, 192, 94);
	_btnOk = new TextButton(84, 16, 68, 122);
	_btnCancel = new TextButton(84, 16, 168, 122);
	// the wheel works on the whole window
	_surface = new InteractiveSurface(200, 96, 60, 52);
	_surface->onMouseClick((ActionHandler)&ManufactureDeliveryState::handleWheel, 0);

	// Set palette
	setInterface("manufactureInfo");

	add(_surface);
	add(_window, "window", "manufactureInfo");
	add(_txtTitle, "text", "manufactureInfo");
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

}
