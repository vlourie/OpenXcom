/*
 * Copyright 2010-2026 OpenXcom Developers.
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
#include "HdCraftRoute.h"
#include <map>
#include "Logger.h"
#include "Options.h"
#include <string>
#include "../Mod/RuleCraft.h"
#include "../Savegame/AlienBase.h"
#include "../Savegame/Base.h"
#include "../Savegame/Craft.h"
#include "../Savegame/MissionSite.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Target.h"
#include "../Savegame/Ufo.h"
#include "../Savegame/Waypoint.h"

namespace OpenXcom
{

namespace HdCraftRoute
{

namespace
{

const size_t MAX_POINTS = 16; ///< intermediate points in one route

/// One stop of the queue: a place, or (the last stop only) a target that is not a waypoint - a UFO, a base, a site.
struct Stop
{
	Point at;
	Target *target;
};

std::map<const Craft*, std::vector<Stop> > _queues;
std::vector<Craft*> _pendingCrafts;
std::vector<Point> _pendingPoints;

/// A target is looked for in the save by its address: one may have gone while the craft was flying (a shot-down UFO, an expired site).
bool alive(SavedGame *save, Target *t)
{
	for (auto *ufo : *save->getUfos())
		if (ufo == t) return true;
	for (auto *site : *save->getMissionSites())
		if (site == t) return true;
	for (auto *ab : *save->getAlienBases())
		if (ab == t) return true;
	for (auto *base : *save->getBases())
	{
		if (base == t) return true;
		for (auto *craft : *base->getCrafts())
			if (craft == t) return true;
	}
	return false;
}

std::string craftTag(const Craft *craft)
{
	return craft->getRules()->getType() + " " + std::to_string(craft->getId());
}

/// A waypoint as the ordinary click on the globe makes it (Confirm Destination window): a new number, kept by the save while a craft follows it.
Waypoint *newWaypoint(SavedGame *save, const Point &at)
{
	Waypoint *w = new Waypoint();
	w->setLongitude(at.first);
	w->setLatitude(at.second);
	w->setId(save->getId("STR_WAY_POINT"));
	save->getWaypoints()->push_back(w);
	return w;
}

} // namespace

void pendingOpen(const std::vector<Craft*> &crafts)
{
	_pendingCrafts = crafts;
	_pendingPoints.clear();
}

void pendingClose()
{
	_pendingCrafts.clear();
	_pendingPoints.clear();
}

bool pendingAdd(double lon, double lat)
{
	if (_pendingCrafts.empty() || _pendingPoints.size() >= MAX_POINTS)
	{
		return false;
	}
	_pendingPoints.push_back(Point(lon, lat));
	return true;
}

bool pendingFor(const std::vector<Craft*> &crafts)
{
	return !_pendingPoints.empty() && _pendingCrafts == crafts;
}

bool apply(Craft *craft, Target *finalTarget, SavedGame *save)
{
	if (_pendingPoints.empty() || !finalTarget)
	{
		return false;
	}
	std::vector<Stop> queue;
	for (size_t i = 1; i < _pendingPoints.size(); ++i)
	{
		queue.push_back(Stop{ _pendingPoints[i], nullptr });
	}
	// a waypoint without followers is deleted by the geoscape: keep its place, a new waypoint is made on the way
	Target *keep = dynamic_cast<Waypoint*>(finalTarget) ? nullptr : finalTarget;
	queue.push_back(Stop{ Point(finalTarget->getLongitude(), finalTarget->getLatitude()), keep });

	craft->setDestination(newWaypoint(save, _pendingPoints.front())); // an order: the old queue goes
	_queues[craft] = queue;
	Log(LOG_INFO) << "HD route: " << craftTag(craft) << " starts, " << queue.size() << " more stop(s)";
	return true;
}

bool advance(Craft *craft, SavedGame *save)
{
	auto it = _queues.find(craft);
	if (it == _queues.end())
	{
		return false;
	}
	if (!Options::oxceHdCraftRoute || it->second.empty())
	{
		_queues.erase(it);
		return false;
	}
	std::vector<Stop> rest = it->second;
	_queues.erase(it); // taken out first: setDestination() below must not count this as a new order
	const Stop next = rest.front();
	rest.erase(rest.begin());
	if (next.target && !alive(save, next.target))
	{
		return false; // the target is gone: the craft stops at this point as it always did
	}
	craft->setDestination(next.target ? next.target : newWaypoint(save, next.at)); // forget() runs inside
	if (!rest.empty())
	{
		_queues[craft] = rest;
	}
	Log(LOG_INFO) << "HD route: " << craftTag(craft) << " takes the next stop, " << rest.size() << " more";
	return true;
}

void forget(const Craft *craft)
{
	if (!_queues.empty() && _queues.erase(craft) > 0)
	{
		Log(LOG_INFO) << "HD route: the rest of the route is dropped (a new order or the craft is gone)";
	}
}

std::vector<std::vector<Point> > lines(SavedGame *save)
{
	std::vector<std::vector<Point> > out;
	if (!Options::oxceHdCraftRoute)
	{
		return out;
	}
	if (!_pendingPoints.empty() && !_pendingCrafts.empty())
	{
		std::vector<Point> line;
		line.push_back(Point(_pendingCrafts.front()->getLongitude(), _pendingCrafts.front()->getLatitude()));
		line.insert(line.end(), _pendingPoints.begin(), _pendingPoints.end());
		out.push_back(line);
	}
	if (_queues.empty())
	{
		return out;
	}
	for (auto *base : *save->getBases())
	{
		for (auto *craft : *base->getCrafts())
		{
			auto it = _queues.find(craft);
			if (it == _queues.end() || !craft->getDestination() || craft->getStatus() != "STR_OUT")
			{
				continue;
			}
			std::vector<Point> line;
			line.push_back(Point(craft->getLongitude(), craft->getLatitude()));
			line.push_back(Point(craft->getDestination()->getLongitude(), craft->getDestination()->getLatitude()));
			for (const Stop &s : it->second)
			{
				if (s.target && !alive(save, s.target))
				{
					break;
				}
				line.push_back(s.target ? Point(s.target->getLongitude(), s.target->getLatitude()) : s.at);
			}
			out.push_back(line);
		}
	}
	return out;
}

} // namespace HdCraftRoute

} // namespace OpenXcom
