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
#include <vector>
#include "../Engine/State.h"

namespace OpenXcom
{

class Base;
class Production;
class SavedGame;
class Window;
class Text;
class TextButton;
class TextList;

/**
 * OXCE-HD (option oxceManufactureDelivery, XP-000256): the deliveries of the workshop orders of a base that are still to be
 * made when the orders are done (what, how many, to which base). A click on a row takes the delivery out of the plan.
 * Only the plan is cleaned: what is already on its way (a Transfer) is not touched.
 */
class ManufactureDeliveryPlanState : public State
{
private:
	/// A row of the list: the order and the base its share goes to.
	struct Row
	{
		Production *production;
		Base *to;
	};
	Base *_base;
	Window *_window;
	TextButton *_btnOk;
	Text *_txtTitle, *_txtHint, *_txtWhat, *_txtWhere;
	TextList *_lstPlan;
	std::vector<Row> _rows;
	/// Fills the list from the plans of the orders.
	void fill();
public:
	/// Is there anything in the plans of the orders of the base to show (and to cancel)?
	static bool hasPlan(const Base *base, const SavedGame *save);
	/// Creates the screen.
	ManufactureDeliveryPlanState(Base *base);
	~ManufactureDeliveryPlanState();
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the list: the delivery leaves the plan.
	void lstPlanClick(Action *action);
};

}
