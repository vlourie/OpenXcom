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
#include <functional>
#include <string>
#include <utility>
#include <vector>
#include "../Engine/State.h"

namespace OpenXcom
{

class Base;
class Language;
class Production;
class RuleItem;
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
public:
	/// Items and how many of each.
	typedef std::vector<std::pair<const RuleItem*, int> > Items;
private:
	Production *_production;
	Base *_to;
	int _max, _amount;
	std::function<void(int)> _onOk;
	std::function<Items(int)> _what; ///< what goes for a number of orders (the line under the title)
	/// Builds the window (both ways of creating it).
	ManufactureDeliveryState(Production *production, Base *to, int max, const std::function<void(int)> &onOk, int start, const std::function<Items(int)> &what);
	Window *_window;
	Text *_txtTitle, *_txtAmount, *_txtWhat;
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
	/// Creates the state for the loot of a finished order (XP-000292): no plan, the number goes to the callback; it starts at the most.
	ManufactureDeliveryState(Base *to, int max, const std::function<void(int)> &onOk, const std::function<Items(int)> &what = nullptr);
	/// The text of what goes: the items with their numbers, short (XP-000256); the plan screen uses it too.
	static std::string describe(const Language *lang, const Items &items);
	~ManufactureDeliveryState();
	void think() override;
};

class TextList;

/**
 * OXCE-HD (option oxceManufactureDelivery, XP-000297): the loot of a finished order with several kinds of items - a list of
 * the kinds with how many of each goes to the base, from 0 to what of it is left in the stores. Display and choice only:
 * what is picked goes to the callback, which ships it by the ordinary transfer.
 */
class ManufactureLootPartsState : public State
{
public:
	typedef ManufactureDeliveryState::Items Items;
private:
	Base *_to;
	Items _items;              ///< the kinds and the most of each that can go
	std::vector<int> _amount;  ///< how many of each goes now, by row
	std::function<void(const Items&)> _onOk;
	Window *_window;
	Text *_txtTitle, *_txtTotal;
	TextList *_lstParts;
	TextButton *_btnOk, *_btnCancel;
	/// Writes the row's number and the total.
	void refresh(size_t row);
	/// Changes the selected row's number within 0..most.
	void change(int by);
	void leftArrowClick(Action *action);
	void rightArrowClick(Action *action);
	void btnOkClick(Action *action);
	void btnCancelClick(Action *action);
public:
	/// Creates the state: the base, the kinds with the most of each; the pick goes to `onOk` (the kinds with a number above 0).
	ManufactureLootPartsState(Base *to, const Items &items, const std::function<void(const Items&)> &onOk);
	~ManufactureLootPartsState();
};

}
