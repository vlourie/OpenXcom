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
#include "Production.h"
#include <algorithm>
#include <cmath>
#include "../Engine/Collections.h"
#include "../Engine/Logger.h"
#include "../Engine/Options.h"
#include "../Mod/RuleManufacture.h"
#include "../Mod/RuleSoldier.h"
#include "Base.h"
#include "SavedGame.h"
#include "Transfer.h"
#include "ItemContainer.h"
#include "Soldier.h"
#include "Craft.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleItem.h"
#include "../Mod/RuleCraft.h"
#include "../Engine/Language.h"
#include "../Engine/RNG.h"
#include <climits>
#include "BaseFacility.h"

namespace OpenXcom
{
Production::Production(const RuleManufacture * rules, int amount) :
	_rules(rules), _amount(amount), _infinite(false), _timeSpent(0), _engineers(0), _sell(false), _isFallback(false)
{
}

int Production::getAmountTotal() const
{
	return _amount;
}

void Production::setAmountTotal (int amount)
{
	_amount = amount;
}

bool Production::getInfiniteAmount() const
{
	return _infinite;
}

void Production::setInfiniteAmount (bool inf)
{
	_infinite = inf;
}

int Production::getTimeSpent() const
{
	return _timeSpent;
}

void Production::setTimeSpent (int done)
{
	_timeSpent = done;
}

bool Production::isQueuedOnly() const
{
	// no progress made yet and nobody assigned
	return (getTimeSpent() == 0 && getAssignedEngineers() == 0);
}

int Production::getAssignedEngineers() const
{
	return _engineers;
}

void Production::setAssignedEngineers (int engineers)
{
	_engineers = engineers;
}

bool Production::getSellItems() const
{
	return _sell;
}

void Production::setSellItems (bool sell)
{
	_sell = sell;
}

bool Production::haveEnoughMoneyForOneMoreUnit(SavedGame * g) const
{
	return _rules->haveEnoughMoneyForOneMoreUnit(g->getFunds());
}

bool Production::haveEnoughLivingSpaceForOneMoreUnit(Base * b)
{
	if (_rules->getSpawnedPersonType() != "")
	{
		// Note: if the production is running then the space we need is already counted by getUsedQuarters
		if (b->getAvailableQuarters() < b->getUsedQuarters())
		{
			return false;
		}
	}
	return true;
}

bool Production::haveEnoughMaterialsForOneMoreUnit(Base * b, const Mod *m) const
{
	for (const auto& i : _rules->getRequiredItems())
	{
		if (b->getStorageItems()->getItem(i.first) < i.second)
			return false;
	}
	for (const auto& i : _rules->getRequiredCrafts())
	{
		if (b->getCraftCountForProduction(i.first) < i.second)
			return false;
	}
	return true;
}

productionProgress_e Production::step(Base * b, SavedGame * g, const Mod *m, Language *lang)
{
	if (_isFallback)
	{
		int availableEngineer = b->getAvailableEngineers();
		int availableWorkSpace = b->getFreeWorkshops();

		if (isQueuedOnly())
		{
			// start counting the workshop space now
			availableWorkSpace -= _rules->getRequiredSpace();
		}
		if (availableEngineer > 0 && availableWorkSpace > 0)
		{
			int change = std::min(availableEngineer, availableWorkSpace);
			setAssignedEngineers(getAssignedEngineers() + change);
			b->setEngineers(b->getEngineers() - change);
		}
	}

	int done = getAmountProduced();
	_timeSpent += _engineers;

	if (done < getAmountProduced())
	{
		int produced;
		if (!getInfiniteAmount())
		{
			produced = std::min(getAmountProduced(), _amount) - done; // std::min is required because we don't want to overproduce
		}
		else
		{
			produced = getAmountProduced() - done;
		}
		int count = 0;
		do
		{
			auto* ruleCraft = _rules->getProducedCraft();
			if (ruleCraft)
			{
				Craft *craft = new Craft(ruleCraft, b, g->getId(ruleCraft->getType()));
				craft->initFixedWeapons(m);
				craft->checkup();
				int transferTimeCraft = std::max(0, _rules->getTransferTimes().size() < 3 ? 0 : _rules->getTransferTimes().at(2));
				if (transferTimeCraft > 0)
				{
					Transfer* t = new Transfer(transferTimeCraft);
					t->setCraft(craft);
					b->getTransfers()->push_back(t);
				}
				else
				{
					b->getCrafts()->push_back(craft);
				}
			}
			else
			{
				int transferTimeItems = std::max(0, _rules->getTransferTimes().empty() ? 0 : _rules->getTransferTimes().front());
				for (const auto& i : _rules->getProducedItems())
				{
					if (getSellItems())
					{
						int64_t adjustedSellValue = i.first->getSellCostAdjusted(b, g);
						adjustedSellValue *= i.second;
						g->setFunds(g->getFunds() + adjustedSellValue);
					}
					else
					{
						if (transferTimeItems > 0)
						{
							Transfer* t = new Transfer(transferTimeItems);
							t->setItems(i.first, i.second);
							b->getTransfers()->push_back(t);
						}
						else
						{
							b->getStorageItems()->addItem(i.first, i.second);
							if (i.first->getBattleType() == BT_NONE)
							{
								for (auto* c : *b->getCrafts())
								{
									c->reuseItem(i.first);
								}
							}
						}
						if (!_rules->getRandomProducedItems().empty())
						{
							_randomProductionInfo[i.first->getType()] += i.second;
						}
					}
				}
			}
			// Random manufacture
			if (!_rules->getRandomProducedItems().empty())
			{
				int transferTimeItems = std::max(0, _rules->getTransferTimes().empty() ? 0 : _rules->getTransferTimes().front());
				int totalWeight = 0;
				for (const auto& itemSet : _rules->getRandomProducedItems())
				{
					totalWeight += itemSet.first;
				}
				// RNG
				int roll = RNG::generate(1, totalWeight);
				int runningTotal = 0;
				for (const auto& itemSet : _rules->getRandomProducedItems())
				{
					runningTotal += itemSet.first;
					if (runningTotal >= roll)
					{
						for (const auto& i : itemSet.second)
						{
							if (transferTimeItems > 0)
							{
								Transfer* t = new Transfer(transferTimeItems);
								t->setItems(i.first, i.second);
								b->getTransfers()->push_back(t);
							}
							else
							{
								b->getStorageItems()->addItem(i.first, i.second);
								if (i.first->getBattleType() == BT_NONE)
								{
									for (auto* c : *b->getCrafts())
									{
										c->reuseItem(i.first);
									}
								}
							}
							_randomProductionInfo[i.first->getType()] += i.second;
						}
						// break outer loop
						break;
					}
				}
			}
			// Spawn persons (soldiers, engineers, scientists, ...)
			const std::string &spawnedPersonType = _rules->getSpawnedPersonType();
			if (spawnedPersonType != "")
			{
				int transferTimePersonnel = std::max(1, _rules->getTransferTimes().size() < 2 ? 24 : _rules->getTransferTimes().at(1));
				if (spawnedPersonType == "STR_SCIENTIST")
				{
					Transfer *t = new Transfer(transferTimePersonnel);
					t->setScientists(1);
					b->getTransfers()->push_back(t);
				}
				else if (spawnedPersonType == "STR_ENGINEER")
				{
					Transfer *t = new Transfer(transferTimePersonnel);
					t->setEngineers(1);
					b->getTransfers()->push_back(t);
				}
				else
				{
					RuleSoldier *rule = m->getSoldier(spawnedPersonType);
					if (rule != 0)
					{
						Transfer *t = new Transfer(transferTimePersonnel);
						int nationality = g->selectSoldierNationalityByLocation(m, rule, b);
						Soldier *s = m->genSoldier(g, rule, nationality);
						YAML::YamlRootNodeReader reader(_rules->getSpawnedSoldierTemplate(), "(spawned soldier template)");
						s->load(reader, m, g, m->getScriptGlobal(), true); // load from soldier template
						if (_rules->getSpawnedPersonName() != "")
						{
							s->setName(lang->getString(_rules->getSpawnedPersonName()));
						}
						else
						{
							s->genName();
						}
						t->setSoldier(s);
						b->getTransfers()->push_back(t);
					}
				}
			}
			// Generate an event (side effect)
			const std::string choice = _rules->chooseEvent();
			if (!choice.empty())
			{
				RuleEvent* eventToSpawn = m->getEvent(choice, false);
				if (eventToSpawn)
				{
					g->spawnEvent(eventToSpawn);
				}
			}
			if (_rules->getPoints() != 0)
			{
				// yes, negative points are allowed too
				g->addResearchScore(_rules->getPoints());
			}
			count++;
			if (count < produced)
			{
				// We need to ensure that player has enough cash/item to produce a new unit
				if (!haveEnoughMoneyForOneMoreUnit(g)) return PROGRESS_NOT_ENOUGH_MONEY;
				if (!haveEnoughMaterialsForOneMoreUnit(b, m)) return PROGRESS_NOT_ENOUGH_MATERIALS;
				startItem(b, g, m);
			}
		}
		while (count < produced);
	}
	if (getAmountProduced() >= _amount && !getInfiniteAmount())
	{
		// XP-000256: the whole order is ready - the planned shares leave the stores for the other bases (empty plan: nothing happens)
		if (!_delivery.empty())
		{
			deliver(b, g, m);
		}
		return PROGRESS_COMPLETE;
	}
	if (done < getAmountProduced())
	{
		// We need to ensure that player has enough cash/item to produce a new unit
		if (!haveEnoughMoneyForOneMoreUnit(g)) return PROGRESS_NOT_ENOUGH_MONEY;
		if (!haveEnoughLivingSpaceForOneMoreUnit(b)) return PROGRESS_NOT_ENOUGH_LIVING_SPACE;
		if (!haveEnoughMaterialsForOneMoreUnit(b, m)) return PROGRESS_NOT_ENOUGH_MATERIALS;
		startItem(b, g, m);
	}
	return PROGRESS_NOT_COMPLETE;
}

int Production::getAmountProduced() const
{
	if (_rules->getManufactureTime() > 0)
		return _timeSpent / _rules->getManufactureTime();
	else
		return _amount;
}

const RuleManufacture * Production::getRules() const
{
	return _rules;
}

void Production::startItem(Base * b, SavedGame * g, const Mod *m) const
{
	g->setFunds(g->getFunds() - _rules->getManufactureCost());
	for (const auto& i : _rules->getRequiredItems())
	{
		b->getStorageItems()->removeItem(i.first, i.second);
	}
	for (const auto& i : _rules->getRequiredCrafts())
	{
		// Find suitable craft
		for (auto* c : *b->getCrafts())
		{
			if (c->getRules() == i.first)
			{
				Craft *craft = c;
				b->removeCraft(craft, true);
				delete craft;
				break;
			}
		}
	}
}

void Production::refundItem(Base * b, SavedGame * g, const Mod *m) const
{
	g->setFunds(g->getFunds() + _rules->getManufactureCost());
	for (const auto& pair : _rules->getRequiredItems())
	{
		b->getStorageItems()->addItem(pair.first, pair.second);
	}
	//for (const auto& pair : _rules->getRequiredCrafts())
	//{
	//	// not supported
	//}
}

/**
 * Finds the base by its coordinates (a base has no id: the index shifts and the name changes).
 * @return The base or null if there is no such base any more.
 */
static Base *findBaseAt(const SavedGame *g, double lon, double lat)
{
	for (auto *base : *g->getBases())
	{
		if (std::fabs(base->getLongitude() - lon) < 1e-7 && std::fabs(base->getLatitude() - lat) < 1e-7)
		{
			return base;
		}
	}
	return nullptr;
}

/**
 * Can the order be delivered to other bases (XP-000256)? Ordinary items only: not crafts, not random sets, not people.
 * An order whose items reach the stores later (transferTimes of the rules) has nothing in the stores to take at the end.
 * Selling and an infinite order are the player's choice on the screen, not a property of the rules.
 */
bool Production::canDeliver() const
{
	if (_rules->getProducedCraft() || !_rules->getRandomProducedItems().empty() || !_rules->getSpawnedPersonType().empty())
	{
		return false;
	}
	if (_rules->getProducedItems().empty())
	{
		return false;
	}
	if (!_rules->getTransferTimes().empty() && _rules->getTransferTimes().front() > 0)
	{
		return false;
	}
	return true;
}

/**
 * Orders already given to bases in the plan.
 */
int Production::getDeliveryTotal() const
{
	int total = 0;
	for (const auto &share : _delivery)
	{
		total += share.amount;
	}
	return total;
}

/**
 * Orders planned for the base.
 */
int Production::getDeliveryShare(const Base *to) const
{
	for (const auto &share : _delivery)
	{
		if (std::fabs(to->getLongitude() - share.lon) < 1e-7 && std::fabs(to->getLatitude() - share.lat) < 1e-7)
		{
			return share.amount;
		}
	}
	return 0;
}

/**
 * Plans this many orders for the base; 0 (or less) takes the base out of the plan.
 */
void Production::setDeliveryShare(const Base *to, int amount)
{
	for (auto it = _delivery.begin(); it != _delivery.end(); ++it)
	{
		if (std::fabs(to->getLongitude() - it->lon) < 1e-7 && std::fabs(to->getLatitude() - it->lat) < 1e-7)
		{
			if (amount > 0)
			{
				it->amount = amount;
				it->parts.clear(); // whole orders now, not kinds
			}
			else
			{
				_delivery.erase(it);
			}
			return;
		}
	}
	if (amount > 0)
	{
		_delivery.push_back({ to->getLongitude(), to->getLatitude(), amount, {} });
	}
}

/**
 * Cuts the plan down to the amount ordered (the order was made smaller): from the last base of the plan.
 * The shares by kinds (XP-000256) are cut kind by kind to what the order gives now.
 */
void Production::trimDelivery()
{
	int excess = getDeliveryTotal() - _amount;
	for (auto it = _delivery.rbegin(); excess > 0 && it != _delivery.rend(); ++it)
	{
		if (!it->parts.empty())
		{
			continue;
		}
		const int cut = std::min(excess, it->amount);
		it->amount -= cut;
		excess -= cut;
	}
	bool byKinds = false;
	for (const auto &share : _delivery)
	{
		byKinds = byKinds || !share.parts.empty();
	}
	if (byKinds)
	{
		for (const auto &i : _rules->getProducedItems())
		{
			int over = -_amount * i.second;
			for (const auto &share : _delivery)
			{
				for (const auto &p : getShareItems(share))
				{
					if (p.first == i.first)
					{
						over += p.second;
					}
				}
			}
			for (auto it = _delivery.rbegin(); over > 0 && it != _delivery.rend(); ++it)
			{
				auto p = it->parts.find(i.first->getType());
				if (p == it->parts.end())
				{
					continue;
				}
				const int cut = std::min(over, p->second);
				p->second -= cut;
				over -= cut;
				if (p->second <= 0)
				{
					it->parts.erase(p);
				}
			}
		}
	}
	// a share with nothing left (whole orders gone, or all the kinds cut) leaves the plan
	for (auto it = _delivery.begin(); it != _delivery.end();)
	{
		if (it->parts.empty() && it->amount <= 0)
		{
			it = _delivery.erase(it);
		}
		else
		{
			++it;
		}
	}
}

/**
 * Does the recipe give several kinds of items (a disassembly)? The delivery of such an order goes by kinds (XP-000256).
 */
bool Production::hasSeveralKinds() const
{
	return _rules->getProducedItems().size() > 1;
}

/**
 * What a share carries, by kinds, in the order of the recipe (only what is above 0): whole orders times what an order gives,
 * or the pieces of a share by kinds.
 */
std::vector<std::pair<const RuleItem*, int> > Production::getShareItems(const DeliveryShare &share) const
{
	std::vector<std::pair<const RuleItem*, int> > out;
	for (const auto &i : _rules->getProducedItems())
	{
		int n = 0;
		if (share.parts.empty())
		{
			n = share.amount * i.second;
		}
		else
		{
			auto p = share.parts.find(i.first->getType());
			n = (p != share.parts.end()) ? p->second : 0;
		}
		if (n > 0)
		{
			out.emplace_back(i.first, n);
		}
	}
	return out;
}

/**
 * Pieces of one kind of the product that no base has in the plan yet (the order gives `amount * per order`).
 */
int Production::getDeliveryLeft(const RuleItem *item) const
{
	auto produced = _rules->getProducedItems().find(item);
	if (produced == _rules->getProducedItems().end())
	{
		return 0;
	}
	int left = _amount * produced->second;
	for (const auto &share : _delivery)
	{
		for (const auto &p : getShareItems(share))
		{
			if (p.first == item)
			{
				left -= p.second;
			}
		}
	}
	return std::max(0, left);
}

/**
 * Pieces of one kind that the plan sends to the base.
 */
int Production::getDeliveryPieces(const Base *to, const RuleItem *item) const
{
	for (const auto &share : _delivery)
	{
		if (std::fabs(to->getLongitude() - share.lon) < 1e-7 && std::fabs(to->getLatitude() - share.lat) < 1e-7)
		{
			for (const auto &p : getShareItems(share))
			{
				if (p.first == item)
				{
					return p.second;
				}
			}
		}
	}
	return 0;
}

/**
 * All the pieces (of all the kinds) that the plan sends to the base.
 */
int Production::getDeliveryPieces(const Base *to) const
{
	int total = 0;
	for (const auto &share : _delivery)
	{
		if (std::fabs(to->getLongitude() - share.lon) < 1e-7 && std::fabs(to->getLatitude() - share.lat) < 1e-7)
		{
			for (const auto &p : getShareItems(share))
			{
				total += p.second;
			}
		}
	}
	return total;
}

/**
 * Pieces in the plan and pieces the order gives in all.
 */
void Production::getDeliveryPiecesTotal(int &given, int &all) const
{
	all = 0;
	int left = 0;
	for (const auto &i : _rules->getProducedItems())
	{
		all += _amount * i.second;
		left += getDeliveryLeft(i.first);
	}
	given = all - left;
}

/**
 * Plans these pieces (by kinds) for the base instead of what it had in the plan; a kind gets not more than is left of it
 * plus what the base had. Nothing to send - the base leaves the plan.
 */
void Production::setDeliveryParts(const Base *to, const std::vector<std::pair<const RuleItem*, int> > &items)
{
	std::map<std::string, int> parts;
	for (const auto &i : items)
	{
		if (i.second <= 0 || _rules->getProducedItems().find(i.first) == _rules->getProducedItems().end())
		{
			continue;
		}
		const int qty = std::min(i.second, getDeliveryLeft(i.first) + getDeliveryPieces(to, i.first));
		if (qty > 0)
		{
			parts[i.first->getType()] = qty;
		}
	}
	for (auto it = _delivery.begin(); it != _delivery.end(); ++it)
	{
		if (std::fabs(to->getLongitude() - it->lon) < 1e-7 && std::fabs(to->getLatitude() - it->lat) < 1e-7)
		{
			if (parts.empty())
			{
				_delivery.erase(it);
			}
			else
			{
				it->amount = 0;
				it->parts = parts;
			}
			return;
		}
	}
	if (!parts.empty())
	{
		_delivery.push_back({ to->getLongitude(), to->getLatitude(), 0, parts });
	}
}

/**
 * Takes out of the plan the bases that are gone (found by the coordinates).
 */
void Production::pruneDelivery(const SavedGame *g)
{
	for (auto it = _delivery.begin(); it != _delivery.end();)
	{
		if (findBaseAt(g, it->lon, it->lat))
		{
			++it;
		}
		else
		{
			it = _delivery.erase(it);
		}
	}
}

/**
 * Sends items from the stores of a base to another base by the ordinary transfer (XP-000256, XP-000292): the time and the price
 * of TransferItemsState (see Transfer::getBaseDistance), the price is paid at the dispatch. Not more than the stores hold.
 * No money - nothing leaves the stores (noFunds; parts and pieces tell what it would have been).
 * @param from The base whose stores the items leave.
 * @param to The base they go to.
 * @param wanted Item and how many of it.
 */
Production::ShipOutcome Production::shipItems(Base *from, Base *to, const std::vector<std::pair<const RuleItem*, int> > &wanted, SavedGame *g, const Mod *m)
{
	ShipOutcome out;
	double size = 0.0;
	for (const auto &w : wanted)
	{
		const int qty = std::min(w.second, from->getStorageItems()->getItem(w.first));
		if (qty <= 0)
		{
			continue;
		}
		out.parts.emplace_back(w.first, qty);
		out.pieces += qty;
		size += qty * w.first->getSize();
	}
	if (out.pieces <= 0)
	{
		return out;
	}
	const double distance = Transfer::getBaseDistance(from, to);
	out.price = Transfer::getTransferPrice(m, out.pieces * (int)(1 * distance));
	if (g->getFunds() < out.price)
	{
		out.noFunds = true;
		return out;
	}
	g->setFunds(g->getFunds() - out.price);
	if (Options::storageLimitsEnforced && to->storesOverfull(size))
	{
		out.noSpace = true;
	}
	out.hours = Transfer::getTravelHours(distance);
	for (const auto &part : out.parts)
	{
		from->getStorageItems()->removeItem(part.first, part.second);
		Transfer *t = new Transfer(out.hours);
		t->setItems(part.first, part.second);
		to->getTransfers()->push_back(t);
	}
	return out;
}

/**
 * The whole order is ready and in the stores: the planned shares leave them for the other bases by the ordinary transfer
 * (the time and the price of TransferItemsState, see Transfer::getBaseDistance). Not more than the stores hold; a base
 * that is gone from the plan is skipped; no money for a share - it stays in the stores. The result goes to _deliveryReport.
 * Only with the option on and only for ordinary items, not sold and not infinite.
 */
void Production::deliver(Base *b, SavedGame *g, const Mod *m)
{
	_deliveryReport = DeliveryReport();
	if (!Options::oxceManufactureDelivery || !canDeliver() || getSellItems() || getInfiniteAmount())
	{
		return;
	}
	int left = _amount;
	// XP-000256: pieces of each kind the batch still has to give (a share by kinds takes exactly its pieces, not more than that)
	std::map<const RuleItem*, int> capacity;
	for (const auto &i : _rules->getProducedItems())
	{
		capacity[i.first] = _amount * i.second;
	}
	for (const auto &share : _delivery)
	{
		Base *to = findBaseAt(g, share.lon, share.lat);
		std::vector<std::pair<const RuleItem*, int> > wanted;
		if (share.parts.empty())
		{
			const int orders = std::min(share.amount, left);
			if (!to || to == b || orders <= 0)
			{
				continue;
			}
			left -= orders;
			for (const auto &i : _rules->getProducedItems())
			{
				capacity[i.first] -= orders * i.second;
				wanted.emplace_back(i.first, orders * i.second);
			}
		}
		else
		{
			if (!to || to == b)
			{
				continue;
			}
			for (const auto &p : getShareItems(share))
			{
				const int qty = std::min(p.second, std::max(0, capacity[p.first]));
				if (qty > 0)
				{
					capacity[p.first] -= qty;
					wanted.emplace_back(p.first, qty);
				}
			}
			if (wanted.empty())
			{
				continue;
			}
		}
		const ShipOutcome o = shipItems(b, to, wanted, g, m);
		if (o.pieces <= 0)
		{
			continue;
		}
		if (o.noFunds)
		{
			_deliveryReport.kept.emplace_back(to->getName(), o.pieces);
			Log(LOG_INFO) << "Manufacture delivery " << _rules->getName() << " -> " << to->getName() << ": " << o.pieces << " stay, funds " << g->getFunds() << " < " << o.price;
			continue;
		}
		if (o.noSpace)
		{
			_deliveryReport.noSpace.push_back(to->getName());
		}
		for (const auto &part : o.parts)
		{
			_deliveryReport.sentParts.push_back(part);
		}
		_deliveryReport.sent.emplace_back(to->getName(), o.pieces);
		Log(LOG_INFO) << "Manufacture delivery " << _rules->getName() << " -> " << to->getName() << ": " << o.pieces << " pieces, " << o.hours << " h, price " << o.price;
	}
}

void Production::save(YAML::YamlNodeWriter writer) const
{
	writer.setAsMap();
	writer.write("item", getRules()->getName());
	writer.write("assigned", getAssignedEngineers());
	writer.write("spent", getTimeSpent());
	writer.write("amount", getAmountTotal());
	writer.write("infinite", getInfiniteAmount());
	if (getSellItems())
		writer.write("sell", getSellItems());
	if (_isFallback)
		writer.write("isFallback", _isFallback);
	if (!_rules->getRandomProducedItems().empty())
		writer.write("randomProductionInfo", _randomProductionInfo);
	// XP-000256: only a plan that exists (an old build skips the unknown key; no plan - the save is as it was)
	if (!_delivery.empty())
	{
		writer.write("delivery", _delivery,
			[](YAML::YamlNodeWriter& vectorWriter, const DeliveryShare& s)
			{
				auto shareWriter = vectorWriter.write();
				shareWriter.setAsMap();
				shareWriter.write("lon", s.lon);
				shareWriter.write("lat", s.lat);
				shareWriter.write("amount", s.amount);
				// XP-000256: a share by kinds (amount is 0 then: a build without this key drops the share, it does not send whole orders)
				if (!s.parts.empty())
				{
					shareWriter.write("parts", s.parts);
				}
			});
	}
}

void Production::load(const YAML::YamlNodeReader& reader)
{
	setAssignedEngineers(reader["assigned"].readVal(getAssignedEngineers()));
	setTimeSpent(reader["spent"].readVal(getTimeSpent()));
	setAmountTotal(reader["amount"].readVal(getAmountTotal()));
	setInfiniteAmount(reader["infinite"].readVal(getInfiniteAmount()));
	setSellItems(reader["sell"].readVal(getSellItems()));
	reader.tryRead("isFallback", _isFallback);
	if (!_rules->getRandomProducedItems().empty())
	{
		_randomProductionInfo = reader["randomProductionInfo"].readVal(_randomProductionInfo);
	}
	// XP-000256: the delivery plan; a missing, damaged or empty entry is simply not a share (the base is looked up by the
	// coordinates when the order is done, a base that is gone is dropped then)
	_delivery.clear();
	for (const auto& shareReader : reader["delivery"].children())
	{
		try
		{
			DeliveryShare s = { shareReader["lon"].readVal(1000.0), shareReader["lat"].readVal(1000.0), shareReader["amount"].readVal(0), {} };
			// XP-000256: a share by kinds; only the kinds the recipe gives and only pieces above 0 are kept (a missing key: whole orders)
			const std::map<std::string, int> parts = shareReader["parts"].readVal(std::map<std::string, int>());
			for (const auto &i : _rules->getProducedItems())
			{
				auto p = parts.find(i.first->getType());
				if (p != parts.end() && p->second > 0)
				{
					s.parts[p->first] = p->second;
				}
			}
			if (!s.parts.empty())
			{
				s.amount = 0;
			}
			if (std::fabs(s.lon) <= 100.0 && std::fabs(s.lat) <= 100.0 && (s.amount > 0 || !s.parts.empty()))
			{
				_delivery.push_back(s);
			}
		}
		catch (const YAML::Exception&)
		{
			// text instead of a number (R-306): this share is dropped, the rest of the save loads as it was
			Log(LOG_WARNING) << "Manufacture delivery: damaged share of " << _rules->getName() << " in the save is skipped";
		}
	}
	// backwards compatibility
	if (getAmountTotal() == INT_MAX)
	{
		setAmountTotal(999);
		setInfiniteAmount(true);
		setSellItems(true);
	}
}

}
