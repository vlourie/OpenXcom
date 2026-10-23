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
#include <assert.h>
#include <algorithm>
#include "ProductionCompleteState.h"
#include "../Engine/Game.h"
#include "../Engine/Action.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleManufacture.h"
#include "../Engine/LocalizedText.h"
#include "../Interface/TextButton.h"
#include "../Interface/Window.h"
#include "../Interface/Text.h"
#include "../Interface/TextList.h"
#include "GeoscapeState.h"
#include "../Engine/Options.h"
#include "../Engine/Logger.h"
#include "../Basescape/BasescapeState.h"
#include "../Basescape/ManufactureState.h"
#include "../Basescape/ManufactureDeliveryState.h"
#include "../Basescape/TransferBaseState.h"
#include "../Menu/ErrorMessageState.h"
#include "../Mod/RuleInterface.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/Production.h"
#include "../Savegame/Base.h"
#include "../Savegame/ItemContainer.h"
#include "../Savegame/SavedGame.h"

namespace OpenXcom
{

/**
 * Initializes all the elements in a Production Complete window.
 * @param game Pointer to the core game.
 * @param base Pointer to base the production belongs to.
 * @param item Item that finished producing.
 * @param state Pointer to the Geoscape state.
 * @param endType What ended the production.
 * @param production Pointer to the production details.
 */
ProductionCompleteState::ProductionCompleteState(Base *base, const std::string &item, GeoscapeState *state, productionProgress_e endType, Production *production) : _base(base), _state(state), _btnLoot(nullptr), _endType(endType)
{
	_screen = false;

	// XP-000292 (option oxceManufactureDelivery): what of the finished batch can be shipped to the other bases from here:
	// ordinary items, not sold, not an infinite order; what the plan of XP-000256 has sent already is not left
	if (Options::oxceManufactureDelivery && _endType == PROGRESS_COMPLETE && production && production->canDeliver()
		&& !production->getSellItems() && !production->getInfiniteAmount() && _game->getSavedGame()->getBases()->size() > 1)
	{
		std::map<const RuleItem*, int> sent;
		for (const auto &part : production->getDeliveryReport().sentParts)
		{
			sent[part.first] += part.second;
		}
		const auto &produced = production->getRules()->getProducedItems();
		for (const auto &i : produced)
		{
			const int left = production->getAmountTotal() * i.second - sent[i.first];
			if (left > 0)
			{
				_loot.push_back({ i.first, left, produced.size() == 1 ? 1 : i.second });
			}
		}
	}
	const bool loot = lootUnits() > 0;
	// removeProduction() hasn't been called yet at this point, so the completed
	// production is still in getProductions() and its engineers are not freed.
	int effectiveFreeEngineers = base->getAvailableEngineers() + (production ? production->getAssignedEngineers() : 0);
	bool canKeepWorking = (_endType == PROGRESS_COMPLETE || _endType == PROGRESS_NOT_ENOUGH_MONEY || _endType == PROGRESS_NOT_ENOUGH_MATERIALS)
		&& base->getProductions().size() > 1
		&& effectiveFreeEngineers > 0;

	// Create objects
	_window = new Window(this, 320, 200, 0, 0, POPUP_BOTH);
	_btnOk = new TextButton(118, 18, 40, 174);
	_btnGotoBase = new TextButton(118, 18, 162, 174);
	_btnSummary = new TextButton(118, 18, 162, 174);
	// the loot button takes the left half of Keep Working's place (all of it when Keep Working is not shown)
	_btnKeepWorking = new TextButton(loot && canKeepWorking ? 116 : 236, 18, loot && canKeepWorking ? 160 : 40, 152);
	if (loot)
	{
		_btnLoot = new TextButton(canKeepWorking ? 116 : 236, 18, 40, 152);
	}
	_txtMessage = new Text(246, 110, 37, 35);
	_txtNext = new Text(236, 9, 40, 142);
	_txtItem = new Text(160, 9, 47, 35);
	_txtQuantity = new Text(70, 9, 197, 35);
	_lstSummary = new TextList(224, 96, 39, 45);

	// Set palette
	setInterface("geoManufactureComplete");

	add(_window, "window", "geoManufactureComplete");
	add(_btnOk, "button", "geoManufactureComplete");
	add(_btnGotoBase, "button", "geoManufactureComplete");
	add(_btnSummary, "button", "geoManufactureComplete");
	add(_btnKeepWorking, "button", "geoManufactureComplete");
	if (_btnLoot)
	{
		add(_btnLoot, "button", "geoManufactureComplete");
	}
	add(_txtMessage, "text1", "geoManufactureComplete");
	add(_txtNext, "text1", "geoManufactureComplete");
	add(_txtItem, "text1", "geoManufactureComplete");
	add(_txtQuantity, "text1", "geoManufactureComplete");
	add(_lstSummary, "list", "geoManufactureComplete");

	centerAllSurfaces();

	// Set up objects
	setWindowBackground(_window, "geoManufactureComplete");

	_btnOk->setText(tr("STR_OK"));
	_btnOk->onMouseClick((ActionHandler)&ProductionCompleteState::btnOkClick);
	_btnOk->onKeyboardPress((ActionHandler)&ProductionCompleteState::btnOkClick, Options::keyCancel);

	_btnKeepWorking->setText(tr("STR_KEEP_WORKING"));
	_btnKeepWorking->onMouseClick((ActionHandler)&ProductionCompleteState::btnKeepWorkingClick);
	if (_btnLoot)
	{
		_btnLoot->setText(tr("STR_LOOT_SHIP"));
		_btnLoot->onMouseClick((ActionHandler)&ProductionCompleteState::btnLootClick);
	}
	_btnKeepWorking->setVisible(canKeepWorking);
	// named in init(): by the time the window shows, the finished work has left the list
	_txtNext->setAlign(ALIGN_CENTER);
	_txtNext->setVisible(false);
	if (canKeepWorking)
	{
		_txtMessage->setHeight(105);
	}

	if (_endType != PROGRESS_CONSTRUCTION)
	{
		_btnGotoBase->setText(tr("STR_ALLOCATE_MANUFACTURE"));
	}
	else
	{
		_btnGotoBase->setText(tr("STR_GO_TO_BASE"));
	}
	_btnGotoBase->onMouseClick((ActionHandler)&ProductionCompleteState::btnGotoBaseClick);

	_btnSummary->setText(tr("STR_RANDOM_PRODUCTION_SUMMARY"));
	_btnSummary->onMouseClick((ActionHandler)&ProductionCompleteState::btnSummaryClick);

	_txtItem->setText(tr("STR_ITEM"));
	_txtItem->setVisible(false);

	_txtQuantity->setText(tr("STR_QUANTITY_UC"));
	_txtQuantity->setVisible(false);

	// the count column is narrower: one by one arrows after it (ticket XP-000225), right click still sells the row
	_lstSummary->setColumns(2, 150, 36);
	_lstSummary->setBackground(_window);
	_lstSummary->setSelectable(true);
	_lstSummary->setMargin(8);
	_lstSummary->setArrowColumn(194, ARROW_HORIZONTAL);
	_lstSummary->setVisible(false);
	_lstSummary->onMouseClick((ActionHandler)&ProductionCompleteState::lstSummaryClick, SDL_BUTTON_RIGHT);
	_lstSummary->onLeftArrowClick((ActionHandler)&ProductionCompleteState::lstSummaryLeftArrowClick);
	_lstSummary->onRightArrowClick((ActionHandler)&ProductionCompleteState::lstSummaryRightArrowClick);

	if (production && !production->getRules()->getRandomProducedItems().empty())
	{
		_btnGotoBase->setVisible(false);
		_randomProductionInfo = production->getRandomProductionInfo(); // local copy is necessary
		_index.reserve(_randomProductionInfo.size());
		for (auto& each : production->getRandomProductionInfo())
		{
			std::ostringstream ss;
			ss << each.second;
			_lstSummary->addRow(2, tr(each.first).c_str(), ss.str().c_str());
			_index.push_back(each.first);
		}
	}
	else
	{
		_btnSummary->setVisible(false);
	}

	_txtMessage->setAlign(ALIGN_CENTER);
	_txtMessage->setVerticalAlign(ALIGN_MIDDLE);
	_txtMessage->setBig();
	_txtMessage->setWordWrap(true);
	std::string s;
	switch(_endType)
	{
	case PROGRESS_CONSTRUCTION:
		s = tr("STR_CONSTRUCTION_OF_FACILITY_AT_BASE_IS_COMPLETE").arg(item).arg(base->getName());
		break;
	case PROGRESS_COMPLETE:
		s = tr("STR_PRODUCTION_OF_ITEM_AT_BASE_IS_COMPLETE").arg(item).arg(base->getName());
		if (production && !production->getDeliveryReport().empty())
		{
			// XP-000256 (oxceManufactureDelivery): how many went where, then the warnings; the whole text small so it all fits
			const DeliveryReport &report = production->getDeliveryReport();
			auto list = [](const std::vector<std::pair<std::string, int> > &bases)
			{
				std::string out;
				for (const auto &b : bases)
				{
					out += (out.empty() ? "" : ", ") + b.first + " (" + std::to_string(b.second) + ")";
				}
				return out;
			};
			s += "\n\n";
			if (!report.sent.empty())
			{
				s += std::string(tr("STR_DELIVERY_SENT").arg(list(report.sent)));
			}
			if (!report.noSpace.empty())
			{
				std::string names;
				for (const auto &n : report.noSpace)
				{
					names += (names.empty() ? "" : ", ") + n;
				}
				s += "\n" + std::string(tr("STR_DELIVERY_NO_SPACE").arg(names));
			}
			if (!report.kept.empty())
			{
				s += "\n" + std::string(tr("STR_DELIVERY_KEPT").arg(list(report.kept)));
			}
			_txtMessage->setSmall();
		}
		break;
	case PROGRESS_NOT_ENOUGH_MONEY:
		s = tr("STR_NOT_ENOUGH_MONEY_TO_PRODUCE_ITEM_AT_BASE").arg(item).arg(base->getName());
		break;
	case PROGRESS_NOT_ENOUGH_MATERIALS:
		s = tr("STR_NOT_ENOUGH_SPECIAL_MATERIALS_TO_PRODUCE_ITEM_AT_BASE").arg(item).arg(base->getName());
		break;
	case PROGRESS_NOT_ENOUGH_LIVING_SPACE:
		s = tr("STR_NOT_ENOUGH_LIVING_SPACE_AT_BASE").arg(item).arg(base->getName());
		break;
	default:
		assert(false);
	}
	_message = s;
	_txtMessage->setText(s);
}

/**
 *
 */
ProductionCompleteState::~ProductionCompleteState()
{

}

/**
 * Names the work Keep Working gives the free engineers to: the top of the base's list, as
 * btnKeepWorkingClick() takes it.
 */
void ProductionCompleteState::init()
{
	State::init();
	const auto& productions = _base->getProductions();
	const bool show = _btnKeepWorking->getVisible() && !productions.empty();
	if (show)
	{
		_txtNext->setText(tr("STR_KEEP_WORKING_NEXT").arg(tr(productions[0]->getRules()->getName())));
	}
	_txtNext->setVisible(show);
	if (_btnLoot)
	{
		_btnLoot->setVisible(lootUnits() > 0);
	}
}

/**
 * How many pieces of the part can still go: the rest of the batch, but not more than the stores hold now.
 */
int ProductionCompleteState::lootAvailable(const LootPart &part) const
{
	return std::max(0, std::min(part.left, _base->getStorageItems()->getItem(part.item)));
}

/**
 * How many units the dialog can offer: enough to send the most of any kind (for a single kind of item the unit is a piece,
 * else an order, which has the pieces of each kind of the recipe).
 */
int ProductionCompleteState::lootUnits() const
{
	int units = 0;
	for (const auto &part : _loot)
	{
		units = std::max(units, (lootAvailable(part) + part.step - 1) / part.step);
	}
	return units;
}

/**
 * How many pieces can still go.
 */
int ProductionCompleteState::lootPieces() const
{
	int pieces = 0;
	for (const auto &part : _loot)
	{
		pieces += lootAvailable(part);
	}
	return pieces;
}

/**
 * Shows the list of the other bases (the one of the delivery of a workshop order); a click on a base asks how much goes there.
 * The list stays until OK, so the rest can go to another base.
 */
void ProductionCompleteState::btnLootClick(Action *)
{
	_game->pushState(new TransferBaseState(_base,
		[this]() { return std::string(tr("STR_LOOT_LEFT").arg(lootPieces())); },
		[this](Base *to)
		{
			for (const auto &sent : _lootSent)
			{
				if (sent.first == to)
				{
					return std::to_string(sent.second);
				}
			}
			return std::string("-");
		},
		[this](Base *to) { lootPicked(to); },
		"STR_LOOT_TITLE"));
}

/**
 * A base was picked: how much of the loot goes there, from nothing to all that is left.
 */
void ProductionCompleteState::lootPicked(Base *to)
{
	const int units = lootUnits();
	if (units <= 0)
	{
		return;
	}
	_game->pushState(new ManufactureDeliveryState(to, units, [this, to](int n) { lootSend(to, n); },
		[this](int n)
		{
			// what would go for n units: the same arithmetic as lootSend
			ManufactureDeliveryState::Items items;
			for (const auto &part : _loot)
			{
				const int qty = std::min(n * part.step, lootAvailable(part));
				if (qty > 0)
				{
					items.emplace_back(part.item, qty);
				}
			}
			return items;
		}));
}

/**
 * Sends the units of the loot to the base by the ordinary transfer (the time and the price of a transfer between bases,
 * paid now); no money - an error message and nothing leaves the stores.
 */
void ProductionCompleteState::lootSend(Base *to, int units)
{
	if (units <= 0)
	{
		return;
	}
	std::vector<std::pair<const RuleItem*, int> > wanted;
	for (const auto &part : _loot)
	{
		const int qty = std::min(units * part.step, lootAvailable(part));
		if (qty > 0)
		{
			wanted.emplace_back(part.item, qty);
		}
	}
	if (wanted.empty())
	{
		return;
	}
	const Production::ShipOutcome out = Production::shipItems(_base, to, wanted, _game->getSavedGame(), _game->getMod());
	if (out.noFunds)
	{
		RuleInterface *geo = _game->getMod()->getInterface("geoscape");
		_game->pushState(new ErrorMessageState(tr("STR_NOT_ENOUGH_MONEY"), _palette, geo->getElement("errorMessage")->color, "BACK13.SCR", geo->getElement("errorPalette")->color));
		return;
	}
	if (out.pieces <= 0)
	{
		return;
	}
	Log(LOG_INFO) << "Manufacture loot -> " << to->getName() << ": " << out.pieces << " pieces, " << out.hours << " h, price " << out.price << ", funds now " << _game->getSavedGame()->getFunds() << ", " << out.parts.front().first->getType() << " left in the stores " << _base->getStorageItems()->getItem(out.parts.front().first);
	for (const auto &sent : out.parts)
	{
		for (auto &part : _loot)
		{
			if (part.item == sent.first)
			{
				part.left -= sent.second;
			}
		}
	}
	auto it = std::find_if(_lootSent.begin(), _lootSent.end(), [to](const std::pair<Base*, int> &s) { return s.first == to; });
	if (it != _lootSent.end())
	{
		it->second += out.pieces;
	}
	else
	{
		_lootSent.emplace_back(to, out.pieces);
	}
	if (out.noSpace && std::find(_lootNoSpace.begin(), _lootNoSpace.end(), to) == _lootNoSpace.end())
	{
		_lootNoSpace.push_back(to);
	}
	refreshMessage();
}

/**
 * Writes the message again: what it said and then what has been shipped from this window (small, so it all fits).
 */
void ProductionCompleteState::refreshMessage()
{
	std::string s = _message;
	if (!_lootSent.empty())
	{
		std::string list;
		for (const auto &sent : _lootSent)
		{
			list += (list.empty() ? "" : ", ") + sent.first->getName() + " (" + std::to_string(sent.second) + ")";
		}
		s += (_message.find('\n') == std::string::npos ? "\n\n" : "\n") + std::string(tr("STR_LOOT_SENT").arg(list));
		if (!_lootNoSpace.empty())
		{
			std::string names;
			for (const auto *b : _lootNoSpace)
			{
				names += (names.empty() ? "" : ", ") + b->getName();
			}
			s += "\n" + std::string(tr("STR_DELIVERY_NO_SPACE").arg(names));
		}
		_txtMessage->setSmall();
	}
	_txtMessage->setText(s);
}

/**
 * Closes the window.
 * @param action Pointer to an action.
 */
void ProductionCompleteState::btnOkClick(Action *)
{
	_game->popState();
}

/**
 * Goes to the base for the respective production.
 * @param action Pointer to an action.
 */
void ProductionCompleteState::btnGotoBaseClick(Action *)
{
	_state->timerReset();
	_game->popState();
	if (_endType != PROGRESS_CONSTRUCTION)
	{
		_game->pushState(withBaseSwitch(new ManufactureState(_base)));
	}
	else
	{
		_game->pushState(new BasescapeState(_base, _state->getGlobe()));
	}
}

/**
 * Displays the random production info.
 * @param action Pointer to an action.
 */
void ProductionCompleteState::btnSummaryClick(Action *)
{
	_btnSummary->setVisible(false);
	_txtMessage->setVisible(false);

	_btnGotoBase->setVisible(true);
	_txtItem->setVisible(true);
	_txtQuantity->setVisible(true);
	_lstSummary->setVisible(true);
}

/**
 * Assigns all free engineers at this base to the top production item, then closes.
 * @param action Pointer to an action.
 */
void ProductionCompleteState::btnKeepWorkingClick(Action *)
{
	const auto& productions = _base->getProductions();
	if (!productions.empty())
	{
		Production* top = productions[0];
		int freeEngineers = _base->getAvailableEngineers();
		int freeWorkshop = _base->getAvailableWorkshops() - _base->getUsedWorkshops();
		// If top production is queued (0 engineers), its requiredSpace isn't counted
		// in getUsedWorkshops() yet — but assigning engineers activates it, so deduct now.
		if (top->isQueuedOnly())
		{
			freeWorkshop -= top->getRules()->getRequiredSpace();
		}
		int canAssign = std::min(freeEngineers, freeWorkshop);
		if (canAssign > 0)
		{
			top->setAssignedEngineers(top->getAssignedEngineers() + canAssign);
			_base->setEngineers(_base->getEngineers() - canAssign);
		}
	}
	_game->popState();
}

/**
 * Sells the selected item(s)... unless they were sold, transferred or otherwise disposed of earlier already.
 * @param action Pointer to an action.
 */
void ProductionCompleteState::lstSummaryClick(Action *action)
{
	// a click on the one by one arrows is theirs
	if (action->getAbsoluteXMouse() >= _lstSummary->getArrowsLeftEdge() &&
		action->getAbsoluteXMouse() <= _lstSummary->getArrowsRightEdge())
	{
		return;
	}
	// 1. remember stuff
	auto scrollPos = _lstSummary->getScroll();
	unsigned int sel = _lstSummary->getSelectedRow();
	std::string itemName = _index[sel];
	int itemCount = _randomProductionInfo[itemName];

	// 2. deal with it
	auto* itemRule = _game->getMod()->getItem(itemName, false);
	if (itemRule)
	{
		// check if we sold something in the meantime
		if (_base->getStorageItems()->getItem(itemRule) < itemCount)
		{
			itemCount = _base->getStorageItems()->getItem(itemRule);
			_randomProductionInfo[itemName] -= itemCount; // just decrease amount by the maximum we can sell
		}
		else
		{
			// remove completely
			_index.erase(_index.begin() + sel);
		}

		if (itemCount > 0)
		{
			int64_t adjustedSellValue = itemRule->getSellCostAdjusted(_base, _game->getSavedGame());
			adjustedSellValue *= itemCount;
			_game->getSavedGame()->setFunds(_game->getSavedGame()->getFunds() + adjustedSellValue);
			_base->getStorageItems()->removeItem(itemRule, itemCount);
		}
	}

	// 3. refresh UI
	_lstSummary->clearList();
	for (const auto& name : _index)
	{
		std::ostringstream ss;
		ss << _randomProductionInfo[name];
		_lstSummary->addRow(2, tr(name).c_str(), ss.str().c_str());
	}
	_lstSummary->scrollTo(scrollPos);
}

/**
 * Sells one of the selected row's items.
 * @param action Pointer to an action.
 */
void ProductionCompleteState::lstSummaryLeftArrowClick(Action *)
{
	changeOne(-1);
}

/**
 * Takes back one of the selected row's items sold here.
 * @param action Pointer to an action.
 */
void ProductionCompleteState::lstSummaryRightArrowClick(Action *)
{
	changeOne(+1);
}

/**
 * Sells one of the selected row's items at the price the right click sells them for (change -1),
 * or takes back one sold with the arrows in this window at the same price (change +1).
 * @param change -1 or +1, the change of the kept count.
 */
void ProductionCompleteState::changeOne(int change)
{
	const size_t sel = _lstSummary->getSelectedRow();
	if (sel >= _index.size())
	{
		return;
	}
	const std::string &name = _index[sel];
	auto *itemRule = _game->getMod()->getItem(name, false);
	if (!itemRule)
	{
		return;
	}
	SavedGame *save = _game->getSavedGame();
	const int64_t price = itemRule->getSellCostAdjusted(_base, save);
	if (change < 0)
	{
		// nothing left of this row, or sold, transferred or otherwise gone from the stores in the meantime
		if (_randomProductionInfo[name] <= 0 || _base->getStorageItems()->getItem(itemRule) <= 0)
		{
			return;
		}
		save->setFunds(save->getFunds() + price);
		_base->getStorageItems()->removeItem(itemRule, 1);
		_randomProductionInfo[name] -= 1;
		_soldOneByOne[name] += 1;
	}
	else
	{
		if (_soldOneByOne[name] <= 0 || save->getFunds() < price)
		{
			return;
		}
		save->setFunds(save->getFunds() - price);
		_base->getStorageItems()->addItem(itemRule, 1);
		_randomProductionInfo[name] += 1;
		_soldOneByOne[name] -= 1;
	}
	_lstSummary->setCellText(sel, 1, std::to_string(_randomProductionInfo[name]));
}

}
