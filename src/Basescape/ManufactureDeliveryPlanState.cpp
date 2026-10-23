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
#include "ManufactureDeliveryPlanState.h"
#include <algorithm>
#include <cmath>
#include <string>
#include "ManufactureDeliveryState.h"
#include "../Engine/Action.h"
#include "../Engine/Game.h"
#include "../Engine/Language.h"
#include "../Engine/LocalizedText.h"
#include "../Engine/Options.h"
#include "../Interface/Text.h"
#include "../Interface/TextButton.h"
#include "../Interface/TextList.h"
#include "../Interface/Window.h"
#include "../Mod/RuleManufacture.h"
#include "../Savegame/Base.h"
#include "../Savegame/Production.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

namespace
{

/**
 * Finds the base by the coordinates of a share of the plan (a base has no id); null if it is gone.
 */
Base *baseAt(const SavedGame *save, const DeliveryShare &share)
{
	for (auto *base : *save->getBases())
	{
		if (std::fabs(base->getLongitude() - share.lon) < 1e-7 && std::fabs(base->getLatitude() - share.lat) < 1e-7)
		{
			return base;
		}
	}
	return nullptr;
}

/**
 * Is the plan of the order going to be carried out at its end? Not for a sale, an infinite order or one that cannot be delivered.
 */
bool planActive(const Production *production)
{
	return production->canDeliver() && !production->getSellItems() && !production->getInfiniteAmount();
}

}

/**
 * Is there a share in the plan of any order of the base that is still to be made?
 * @param base The base whose workshop it is.
 * @param save The game (to find the bases of the shares).
 */
bool ManufactureDeliveryPlanState::hasPlan(const Base *base, const SavedGame *save)
{
	for (const auto *production : base->getProductions())
	{
		if (!planActive(production))
		{
			continue;
		}
		for (const auto &share : production->getDelivery())
		{
			if (share.amount > 0 && baseAt(save, share))
			{
				return true;
			}
		}
	}
	return false;
}

/**
 * Initializes all the elements of the screen (the look is that of the list of bases of the delivery).
 * @param base The base whose orders are shown.
 */
ManufactureDeliveryPlanState::ManufactureDeliveryPlanState(Base *base) : _base(base)
{
	// Create objects
	_window = new Window(this, 280, 140, 20, 30);
	_btnOk = new TextButton(264, 16, 28, 146);
	_txtTitle = new Text(270, 17, 25, 38);
	_txtHint = new Text(250, 9, 30, 54);
	_txtWhat = new Text(160, 9, 28, 68);
	_txtWhere = new Text(80, 9, 190, 68);
	_lstPlan = new TextList(248, 64, 28, 80);

	// Set palette
	setInterface("transferBaseSelect");

	add(_window, "window", "transferBaseSelect");
	add(_btnOk, "button", "transferBaseSelect");
	add(_txtTitle, "text", "transferBaseSelect");
	add(_txtHint, "text", "transferBaseSelect");
	add(_txtWhat, "text", "transferBaseSelect");
	add(_txtWhere, "text", "transferBaseSelect");
	add(_lstPlan, "list", "transferBaseSelect");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "transferBaseSelect");

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&ManufactureDeliveryPlanState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&ManufactureDeliveryPlanState::btnOkClick, Options::keyOk);
	_btnOk->onKeyboardPress((ActionHandler)&ManufactureDeliveryPlanState::btnOkClick, Options::keyCancel);

	_txtTitle->setBig();
	_txtTitle->setAlign(ALIGN_CENTER);
	_txtTitle->setText(tr("STR_DELIVERY_PLAN_TITLE"));

	_txtHint->setText(tr("STR_DELIVERY_PLAN_HINT"));

	_txtWhat->setText(tr("STR_DELIVERY_PLAN_WHAT"));
	_txtWhere->setText(tr("STR_DELIVERY_PLAN_WHERE"));

	_lstPlan->setColumns(2, 162, 86);
	_lstPlan->setSelectable(true);
	_lstPlan->setBackground(_window);
	_lstPlan->setMargin(2);
	_lstPlan->setWordWrap(true);
	_lstPlan->onMouseClick((ActionHandler)&ManufactureDeliveryPlanState::lstPlanClick);

	fill();
}

/**
 *
 */
ManufactureDeliveryPlanState::~ManufactureDeliveryPlanState()
{
}

/**
 * Fills the list: one row for each share of each order that is still to be delivered (what, how many, to which base).
 */
void ManufactureDeliveryPlanState::fill()
{
	_lstPlan->clearList();
	_rows.clear();
	const SavedGame *save = _game->getSavedGame();
	for (auto *production : _base->getProductions())
	{
		if (!planActive(production))
		{
			continue;
		}
		for (const auto &share : production->getDelivery())
		{
			Base *to = baseAt(save, share);
			if (share.amount <= 0 || !to || to == _base)
			{
				continue;
			}
			ManufactureDeliveryState::Items items;
			for (const auto &i : production->getRules()->getProducedItems())
			{
				items.emplace_back(i.first, share.amount * i.second);
			}
			_lstPlan->addRow(2, ManufactureDeliveryState::describe(_game->getLanguage(), items).c_str(), to->getName().c_str());
			_rows.push_back({ production, to });
		}
	}
	if (_rows.empty())
	{
		_txtHint->setText(tr("STR_DELIVERY_PLAN_EMPTY"));
	}
}

/**
 * Returns to the order.
 */
void ManufactureDeliveryPlanState::btnOkClick(Action *)
{
	_game->popState();
}

/**
 * Takes the delivery of the row out of the plan of its order (what is already on its way is not touched).
 */
void ManufactureDeliveryPlanState::lstPlanClick(Action *)
{
	const size_t row = _lstPlan->getSelectedRow();
	if (row >= _rows.size())
	{
		return;
	}
	_rows[row].production->setDeliveryShare(_rows[row].to, 0);
	fill();
}

}
