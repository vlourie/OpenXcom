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
#include <vector>
#include "Position.h"

namespace OpenXcom
{

class SavedBattleGame;
class BattleUnit;
class Node;
struct BattleAction;

/**
 * HIVE COMMAND CORE (bench, OXCE_AI_HIVE: 0 off, 1 shadow, 2 active): one headquarters over the side's units. It keeps sectors,
 * squads with real commanders, a memory of contacts between turns and a task for each squad. UNIFIED ARMY CONTROL V0: the task is a place,
 * and the only thing it touches is which nodes the unit's own patrol may choose from, its own dice choosing; none fits, and the free choice stands.
 * Combat, ambush, escape and panic stay the unit's. No dice, no free action, no knowledge of a player unit that no living unit of the side has in sight.
 * See docs/research/ai-mechanics/HIVE_UNIFIED_ARMY_CONTROL_V0_DESIGN.md
 */
namespace HiveCommand
{

/// What a squad's task asks of a patrol's node, for one unit, on top of all the engine's own tests. Knows nothing of the other side beyond the place it was given.
struct NodeFit
{
	int squad = -1;
	const char *kind = "";
	Position center;
	int radius = 0, here = 0;
	bool closer = false, skipVisited = false, hasVisited = false;
	const std::vector<int> *reach = 0;
	const std::vector<const Node *> *refused = 0; // HIVE D2: offers this think's own search has refused
	mutable int accepted = 0;
	bool accepts(const Node *n) const;
};
/// The steps of the choice, in their order, all by the unit's own kind of search: not yet visited inside the place; visited ones too; nearer the place than the unit stands, for one outside it.
const int FIT_RUNGS = 3;

/// HIVE D2: what one think's tries came to. tries == freeChecked + freeNone + taken: an offer that did not end the choice is not a try.
struct PatrolTally
{
	std::vector<const Node *> refused;
	Node *free = 0;
	bool offer = false, asked = false;
	int tries = 0, freeChecked = 0, freeNone = 0, offers = 0, refusals = 0, taken = 0;
};

/// The flag: 0 off, 1 shadow, 2 active.
int mode();
/// A battle is set up, all its units placed, before anyone's turn: the organization is made, or kept if a save brought it.
void battleStarts(SavedBattleGame *save);
/// The battle save was read: the state it held, or none (an older save). Units and nodes are already there.
void loaded(SavedBattleGame *save, const std::string *text);
/// The state to write into the battle save; false if there is none.
bool saveText(const SavedBattleGame *save, std::string &text);
/// The battle save goes away.
void forget(const SavedBattleGame *save);
/// Before the unit's think: the first of a side's turn plans it, every one takes what this unit sees.
void beforeThink(SavedBattleGame *save, BattleUnit *unit);
/// Inside setupPatrol, a new node to choose: the place this unit's squad's task asks for; false, none, and the free choice is all there is.
bool patrolIntent(SavedBattleGame *save, BattleUnit *unit, NodeFit &fit);
/// Sets the fit for one step of the choice; false, the step does not apply.
bool fitRung(NodeFit &fit, int rung);
/// What came of the choice, for the log and the feedback: free is what the unit would have taken with no task, chosen what the task allowed (0: nothing, the free one stands). scout: the unit's own kind of search.
void patrolChosen(SavedBattleGame *save, BattleUnit *unit, const NodeFit &fit, int rung, int tryNo, Node *free, Node *chosen, bool scout, const Node *fromNode);
/// The time of one choice: the free search and the steps of the condition. Written, nothing more.
void perfSearch(long long freeNs, long long stepsNs);
/// The time of one path check of a patrol's node and whether it failed. Written, nothing more.
void perfPath(long long ns, bool failed);
/// HIVE D2: the soldier's own search has no path to the offered node; the try goes on with the free one.
void offerRefused(SavedBattleGame *save, BattleUnit *unit, const Node *offer, PatrolTally &tally, int tryNo, long long ns, int expanded, bool seedMoved);
/// HIVE D2: the soldier's own search has a path to the offered node.
void offerTaken(PatrolTally &tally, long long ns);
/// HIVE D2: a think's choice is over: writes what its tries came to, and whether the fields it took served an offer.
void patrolEnded(SavedBattleGame *save, BattleUnit *unit, const PatrolTally &tally, const Node *result);
/// Inside setupPatrol, a node kept from before: does it go back to the choice? Once a turn for a unit, and not a node the free choice just gave it.
bool dropKept(SavedBattleGame *save, BattleUnit *unit, Node *kept);
/// After the unit's think: what it really decided.
void decided(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action);
/// At the end of any side's turn: closes the side's turn of orders, or counts what its stand came to over the other side's turn.
void sideEnds(SavedBattleGame *save);

}

}
