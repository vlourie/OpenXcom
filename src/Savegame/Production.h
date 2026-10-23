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
#include <map>
#include <string>
#include <utility>
#include <vector>
#include "../Engine/Yaml.h"

namespace OpenXcom
{

class RuleManufacture;
class Base;
class SavedGame;
class Language;
class Mod;
class RuleItem;
enum productionProgress_e { PROGRESS_NOT_COMPLETE, PROGRESS_COMPLETE, PROGRESS_NOT_ENOUGH_MONEY, PROGRESS_NOT_ENOUGH_MATERIALS, PROGRESS_NOT_ENOUGH_LIVING_SPACE, PROGRESS_MAX, PROGRESS_CONSTRUCTION };

/// A share of a finished workshop order that goes to another base (option oxceManufactureDelivery, XP-000256).
/// The base is found by its latitude and longitude (a base has no id, its index shifts and its name changes).
struct DeliveryShare
{
	double lon, lat;
	int amount; ///< in orders (units to produce), not in pieces
};

/// What the delivery of a finished order did (to be told in the Production Complete window; not saved).
struct DeliveryReport
{
	std::vector<std::pair<std::string, int> > sent; ///< base name, pieces on the way
	std::vector<std::string> noSpace; ///< bases whose stores the cargo overfills (sent all the same)
	std::vector<std::pair<std::string, int> > kept; ///< base name, pieces left in the stores: not enough funds for the transfer
	std::vector<std::pair<const RuleItem*, int> > sentParts; ///< what went, by item (XP-000292: the rest of the batch is what is left of it)
	bool empty() const { return sent.empty() && kept.empty(); }
};

class Production
{
public:
	Production (const RuleManufacture * rules, int amount);
	int getAmountTotal() const;
	void setAmountTotal (int);
	bool getInfiniteAmount() const;
	void setInfiniteAmount (bool);
	int getTimeSpent() const;
	void setTimeSpent (int);
	bool isQueuedOnly() const;
	int getAmountProduced() const;
	int getAssignedEngineers() const;
	void setAssignedEngineers (int);
	bool getSellItems() const;
	void setSellItems (bool);
	bool isFallback() const { return _isFallback; }
	void setFallback(bool newValue) { _isFallback = newValue; }
	productionProgress_e step(Base * b, SavedGame * g, const Mod *m, Language *lang);
	const RuleManufacture * getRules() const;
	void startItem(Base * b, SavedGame * g, const Mod *m) const;
	void refundItem(Base * b, SavedGame * g, const Mod *m) const;
	void save(YAML::YamlNodeWriter writer) const;
	void load(const YAML::YamlNodeReader& reader);
	const std::map<std::string, int> &getRandomProductionInfo() const { return _randomProductionInfo; }
	/// Can the rules of this order be delivered to other bases (ordinary items only)?
	bool canDeliver() const;
	/// The plan of the delivery: shares by base.
	const std::vector<DeliveryShare> &getDelivery() const { return _delivery; }
	/// Orders already given to bases in the plan.
	int getDeliveryTotal() const;
	/// Orders planned for this base.
	int getDeliveryShare(const Base *to) const;
	/// Plans this many orders for the base (0 takes it out of the plan).
	void setDeliveryShare(const Base *to, int amount);
	/// Cuts the plan down to the amount ordered.
	void trimDelivery();
	/// Takes out of the plan the bases that are gone.
	void pruneDelivery(const SavedGame *g);
	/// What the delivery at the end of the order did.
	const DeliveryReport &getDeliveryReport() const { return _deliveryReport; }
	/// What one shipment of items between bases did (XP-000292).
	struct ShipOutcome
	{
		int pieces = 0, price = 0, hours = 0;
		bool noSpace = false, noFunds = false;
		std::vector<std::pair<const RuleItem*, int> > parts; ///< what was sent (or, with noFunds, what would have been)
	};
	/// Sends items from the stores of a base to another base by the ordinary transfer (time and price of a transfer between bases).
	static ShipOutcome shipItems(Base *from, Base *to, const std::vector<std::pair<const RuleItem*, int> > &wanted, SavedGame *g, const Mod *m);
private:
	/// Sends the planned shares from the stores of the base by the ordinary transfer (the whole order is ready).
	void deliver(Base * b, SavedGame * g, const Mod *m);
	const RuleManufacture * _rules;
	int _amount;
	bool _infinite;
	int _timeSpent;
	int _engineers;
	bool _sell;
	bool _isFallback;
	std::map<std::string, int> _randomProductionInfo;
	std::vector<DeliveryShare> _delivery;
	DeliveryReport _deliveryReport;
	bool haveEnoughMoneyForOneMoreUnit(SavedGame * g) const;
	bool haveEnoughLivingSpaceForOneMoreUnit(Base * b);
	bool haveEnoughMaterialsForOneMoreUnit(Base * b, const Mod *m) const;
};

}
