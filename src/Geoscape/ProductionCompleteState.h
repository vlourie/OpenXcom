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
#include <string>
#include <map>
#include <vector>
#include "../Engine/State.h"
#include "../Savegame/Production.h"

namespace OpenXcom
{

class TextButton;
class Window;
class Text;
class TextList;
class Base;
class GeoscapeState;
class RuleItem;

/**
 * Window used to notify the player when
 * a production is completed.
 */
class ProductionCompleteState : public State
{
private:
	Base *_base;
	GeoscapeState *_state;

	std::map<std::string, int> _randomProductionInfo;
	std::vector<std::string> _index;
	std::map<std::string, int> _soldOneByOne; ///< sold with the arrows in this window: what the right arrow may take back

	/// Sells one of the selected row's items (change -1) or takes back one sold here (change +1).
	void changeOne(int change);

	/// XP-000292 (option oxceManufactureDelivery): what of the finished batch is still in the stores and may be shipped to other bases.
	struct LootPart
	{
		const RuleItem *item;
		int left; ///< pieces of the batch not shipped yet
		int step; ///< pieces of it in one unit of the dialog (1 for a single kind of item, else per order)
	};
	std::vector<LootPart> _loot;
	std::vector<std::pair<Base*, int> > _lootSent; ///< bases shipped to from this window, pieces
	std::vector<Base*> _lootNoSpace; ///< of them, bases with no room
	std::string _message; ///< the text of the message without the loot lines
	TextButton *_btnLoot;
	/// How many pieces of the part can still go (the batch left, not more than the stores hold).
	int lootAvailable(const LootPart &part) const;
	/// How many units the dialog can offer.
	int lootUnits() const;
	/// How many pieces can still go.
	int lootPieces() const;
	/// Sends this many units of the loot to the base.
	void lootSend(Base *to, int units);
	/// XP-000297: sends the picked pieces of each kind of the loot to the base.
	void lootSendParts(Base *to, const std::vector<std::pair<const RuleItem*, int> > &picked);
	/// The base is picked: asks how much.
	void lootPicked(Base *to);
	/// Writes the message again with the loot shipped so far.
	void refreshMessage();

	TextButton *_btnOk, *_btnGotoBase, *_btnSummary, *_btnKeepWorking;
	Window *_window;
	Text *_txtMessage, *_txtItem, *_txtQuantity, *_txtNext;
	TextList *_lstSummary;
	productionProgress_e _endType;
public:
	/// Creates the Production Complete state.
	ProductionCompleteState(Base *base, const std::string &item, GeoscapeState *state, productionProgress_e endType = PROGRESS_COMPLETE, Production *production = nullptr);
	/// Cleans up the Production Complete state.
	~ProductionCompleteState();
	/// Names the work Keep Working gives the free engineers to.
	void init() override;
	/// Handler for clicking the OK button.
	void btnOkClick(Action *action);
	/// Handler for clicking the Go To Base button.
	void btnGotoBaseClick(Action *action);
	/// Handler for clicking the Summary button.
	void btnSummaryClick(Action *action);
	/// Handler for clicking the Summary list.
	void lstSummaryClick(Action *action);
	/// Handler for the left arrow of the Summary list: one less kept - sells one.
	void lstSummaryLeftArrowClick(Action *action);
	/// Handler for the right arrow of the Summary list: one more kept - takes back one sold here.
	void lstSummaryRightArrowClick(Action *action);
	/// Handler for clicking the Keep Working button.
	void btnKeepWorkingClick(Action *action);
	/// Handler for clicking the Ship the loot button.
	void btnLootClick(Action *action);
};

}
