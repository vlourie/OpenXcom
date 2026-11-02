#pragma once
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
#include <utility>
#include <vector>

namespace OpenXcom
{

class Craft;
class SavedGame;
class Target;

/**
 * A craft's flight route of several points on the globe (oxceHdCraftRoute, XP-000470).
 * With the option off nothing here is ever filled in, and every call is a no-op.
 *
 * A route lives in memory only (never in the save): the craft flies to the first point as to an
 * ordinary waypoint, and the points after it wait in a queue kept here. When the craft arrives at
 * a waypoint that has a queue, the next stop is taken at once with Craft::setDestination (no
 * "reached the point" window); the window shows on the last stop only, as it always did.
 * Any other order to the craft (Craft::setDestination called from elsewhere: a new target, home,
 * patrol, fuel, the target gone) throws the queue away, and so does the craft's destruction.
 */
namespace HdCraftRoute
{

typedef std::pair<double, double> Point; ///< longitude, latitude

/// A route opened on the globe for the crafts (Select Destination window): Shift+click adds points. Closed with the window.
void pendingOpen(const std::vector<Craft*> &crafts);
void pendingClose();
/// Adds a point; false when the route is too long already.
bool pendingAdd(double lon, double lat);
/// Are these the crafts the route is being made for, and is there a point in it?
bool pendingFor(const std::vector<Craft*> &crafts);

/// The order is confirmed: the craft flies to the first point of the pending route, the rest waits in the queue
/// together with the final target. `finalTarget` is the target of the order (a waypoint is kept as a place only).
bool apply(Craft *craft, Target *finalTarget, SavedGame *save);
/// The craft arrived at a waypoint: takes the next stop of the queue; false = no queue (or it is cancelled), do as always.
bool advance(Craft *craft, SavedGame *save);
/// Drops the craft's queue (a new order, the craft is gone).
void forget(const Craft *craft);

/// What to draw: each line starts at a craft, goes through the points to the final one (the pending route too).
std::vector<std::vector<Point> > lines(SavedGame *save);

}

}
