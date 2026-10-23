#pragma once
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
#include "../Engine/State.h"

namespace OpenXcom
{

class Base;
class Production;
class Window;
class Text;
class TextButton;
class ArrowButton;
class Timer;
class InteractiveSurface;

/**
 * OXCE-HD (option oxceManufactureDelivery, XP-000256): how many orders of a workshop order go to another base when it is done.
 * From 0 (the base leaves the plan) to what is not yet given to the other bases.
 */
class ManufactureDeliveryState : public State
{
private:
	Production *_production;
	Base *_to;
	int _max, _amount;
	Window *_window;
	Text *_txtTitle, *_txtAmount;
	TextButton *_btnOk, *_btnCancel;
	ArrowButton *_btnMore, *_btnLess;
	Timer *_timerMore, *_timerLess;
	InteractiveSurface *_surface;
	/// Shows the number.
	void update();
	/// Changes the number within 0..max.
	void change(int by);
	void moreClick(Action *action);
	void moreRelease(Action *action);
	void morePress(Action *action);
	void lessClick(Action *action);
	void lessRelease(Action *action);
	void lessPress(Action *action);
	void onMore();
	void onLess();
	void handleWheel(Action *action);
	void btnOkClick(Action *action);
	void btnCancelClick(Action *action);
public:
	/// Creates the state: the order, the base the share goes to and the most that can go there.
	ManufactureDeliveryState(Production *production, Base *to, int max);
	~ManufactureDeliveryState();
	void think() override;
};

}
