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
#include "HiveCommand.h"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <exception>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "AiProbe.h"
#include "BattlescapeGame.h"
#include "Pathfinding.h"
#include "Position.h"
#include "TileEngine.h"
#include "../Engine/Logger.h"
#include "../Mod/Armor.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/Node.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"

namespace OpenXcom
{
namespace HiveCommand
{
namespace
{

enum Task { T_HOLD, T_SEARCH };
enum OrderState { CREATED, ASSIGNED, VALIDATED, EXECUTING, COMPLETED, BLOCKED, INTERRUPTED, CANCELLED };
const char *const STATE_NAME[] = { "CREATED", "ASSIGNED", "VALIDATED", "EXECUTING", "COMPLETED", "BLOCKED", "INTERRUPTED", "CANCELLED" };
const char *const TASK_NAME[] = { "HOLD", "SEARCH" };
enum Knowledge { KNOWN, LAST_KNOWN, INFERRED };
const char *const KNOW_NAME[] = { "KNOWN", "LAST_KNOWN", "INFERRED" };
enum HoldWhy { HW_NONE, HW_GUARD, HW_NOTHING_KNOWN, HW_NOTHING_REACHABLE };
const char *const HOLD_NAME[] = { "none", "guard_sector", "nothing_known", "nothing_reachable" };
const char *const HOLD_EXITS = "threat_near,not_useful,term_over";

const int SQUAD_TARGET = 5, SQUAD_MAX = 6;
const int LEADER_SPACING = 8;
const int HOLD_RADIUS = 8, POST_RADIUS = 5;
const int ARRIVE_RADIUS = 2, OBJECTIVE_NODE_RADIUS = 10, VISIT_RADIUS = 3, ANY_RADIUS = 100000;
const int CONTACT_REACH = 24, CONTACT_SQUADS = 2;
const int OBJECTIVE_REPLANS_PER_TURN = 3, OBJECTIVE_TURNS = 3, ORDER_TURNS = 3, STUCK_LIMIT = 2, STUCK_TURNS = 2, PATH_TRIES = 5;
const int HOLD_TURNS = 3, HOLD_IDLE = 2, HOLD_EXIT_RADIUS = 12, SEARCH_STALL = 2, RETARGET = 5;
// UNIFIED ARMY CONTROL V0 (bench): the size of a task's place, how long a response lasts past the last sight of the contact and the rest after it, the turns a quiet guard stays
const int SECURE_RADIUS = 8, SEARCH_RADIUS = 10, RESPOND_RADIUS = 8, RESPOND_TURNS = 2, RESPOND_REST = 1, SECURE_IDLE = 4;
// CONTACT_COORDINATION_V0 (bench, OXCE_AI_HIVE_CONTACT=1 over OXCE_AI_HIVE=2): what each squad does about a contact, decided once a side's turn before any unit's think
enum Role { R_NONE, R_ENGAGE, R_REINFORCE, R_MAINTAIN };
const char *const ROLE_NAME[] = { "NONE", "ENGAGE", "REINFORCE", "MAINTAIN" };
const int REINFORCE_MAX = 2, REINFORCE_TURNS = 3, REINFORCE_REST = 3, REINFORCE_ARMED = 2, REINFORCE_STALL = 2, FIRE_REACH = 20;

struct Sector
{
	int id = 0;
	std::vector<Node*> nodes;
	std::set<int> visited;
};

struct Objective
{
	bool valid = false;
	bool contact = false;
	int contactId = -1;
	Position pos, keyPos;
	int since = 0;
	int key = 0;
};

/// What the squad's stand or search came to since the last review: only what really happened counts.
struct Cycle
{
	int shots = 0, reactions = 0, hurt = 0, saw = 0;
};

struct Squad
{
	int id = 0;
	BattleUnit *commander = 0;
	std::vector<BattleUnit*> members;
	Task task = T_HOLD;
	int sector = 0;
	Position anchor;
	Objective objective;
	int replans = 0;
	int replanTurn = -1;
	HoldWhy holdWhy = HW_NONE;
	int holdSince = -1, holdEnd = -1, idle = 0;
	int noProgress = 0, bestDist = 1000000;
	Cycle cycle;
	std::map<int, int> skip; // contact given up -> the turn it was last seen then: seen again, the conditions changed
	Role role = R_NONE;
	int roleContact = -1, roleSince = -1, roleUntil = -1, restUntil = -1, roleShots = 0, roleStall = 0, roleBest = 1000000;
	Position roleAt;
	int roleFar = 0;
};

struct Order
{
	int id = 0;
	int squad = 0;
	BattleUnit *unit = 0;
	Task task = T_HOLD;
	bool stay = false;
	Node *node = 0;
	Position target;
	OrderState state = CREATED;
	std::string why;
	int objectiveKey = 0;
	int turn = 0;
	int overrides = 0;
	int stuck = 0;
	int stuckTurns = 0;
	int pauseTurn = -1;
	Position lastPos, turnStart, startAt;
	int lastTurn = -1;
	int checkTurn = -1, doneTurn = -1, pathTu = -1;
	bool walked = false, moved = false;
};

struct Contact
{
	int id = -1;
	Position pos;
	Knowledge cls = KNOWN;
	int seenTurn = 0;
	int observer = -1;
};

/// All a unit can walk to, by the pathfinder's own step costs and under the time units of ORDER_TURNS turns: nothing more than its search would answer.
struct Field
{
	int turn = -1;
	Position at;
	int tiles = 0;
	bool capped = false;
	std::vector<int> node;
};

/// The unit's last patrol node under its task and how its turn began: for the feedback only, never saved.
struct Choice
{
	Position node;
	bool changed = false;
	int walkTurn = -1;
};

struct TurnStart
{
	Position at;
	int tu = 0;
};

struct Hq
{
	SavedBattleGame *save = 0;
	bool managesBattle = false;
	bool restored = false;
	int turn = -1;
	int firstPlanTurn = -1;
	bool turnOpen = false;
	std::vector<Sector> sectors;
	std::vector<Squad> squads;
	std::map<int, int> squadOf;
	std::map<int, Order> orders;
	std::map<int, Contact> contacts;
	std::map<int, std::map<int, std::pair<int, int> > > blocked; // unit -> node -> the conditions it was refused under
	std::map<int, std::pair<int, int> > ledger; // unit -> time units and health as the side's turn ended
	std::set<int> seenOut;
	std::set<Node*> taken;
	std::map<int, Field> fields;
	std::map<int, Choice> choices;
	std::map<int, TurnStart> starts;
	std::map<int, int> fellBack, dropped; // unit -> the turn
	std::map<std::pair<long long, int>, bool> lines; // this plan: cell and eye height, contact -> a line of fire
	std::vector<int> flood, floodPrev;
	int floodUnit = -1;
	int nextOrder = 1;
	int nextKey = 1;
	long long thinkNs = 0, floodNs = 0;
	int thinks = 0, floods = 0;
	int rejFar = 0, rejUnreachable = 0, rejMemo = 0, rejIllegal = 0;
	int stat[8] = {0, 0, 0, 0, 0, 0, 0, 0};
};
Hq hq;
SavedBattleGame *pendingSave = 0;
const char *pendingOrigin = "spawn";

int dist(const Position &a, const Position &b)
{
	return std::max(std::abs(a.x - b.x), std::abs(a.y - b.y)) + 2 * std::abs(a.z - b.z);
}

bool nearPos(const Position &a, const Position &b, int r)
{
	return a.z == b.z && std::abs(a.x - b.x) <= r && std::abs(a.y - b.y) <= r;
}

std::string pos(const Position &p)
{
	std::ostringstream s;
	s << "(" << p.x << "," << p.y << "," << p.z << ")";
	return s.str();
}

bool isOurs(const BattleUnit *u)
{
	return u->getFaction() == FACTION_HOSTILE && u->getOriginalFaction() == FACTION_HOSTILE;
}

bool available(const BattleUnit *u)
{
	return u && !u->isOut() && isOurs(u);
}

const char *role(const BattleUnit *u)
{
	const BattleItem *w = u->getMainHandWeapon(false);
	if (!w || w->getRules()->getBattleType() != BT_FIREARM) return "M";
	if (!w->getRules()->isTwoHanded()) return "S";
	return w->getRules()->getAccuracyAimed() > 0 ? "L" : "A";
}

/// Out of the system's hands, and counted apart: why, or 0.
const char *unmanaged(const BattleUnit *u)
{
	if (u->isOut()) return "out";
	if (!u->getArmor()->allowsMoving()) return "immobile";
	if (u->isLeeroyJenkins()) return "charger";
	const BattleItem *w = u->getMainHandWeapon(false);
	if (!w) return "unarmed";
	return 0;
}

bool isAttack(int t)
{
	return (t >= BA_THROW && t <= BA_PANIC) || t == BA_CQB;
}

int rankWeight(const std::string &r)
{
	if (r == "STR_LIVE_COMMANDER") return 6;
	if (r == "STR_LIVE_LEADER") return 5;
	if (r == "STR_LIVE_ENGINEER") return 4;
	if (r == "STR_LIVE_MEDIC") return 3;
	if (r == "STR_LIVE_NAVIGATOR") return 2;
	if (r == "STR_LIVE_SOLDIER") return 1;
	return 0;
}

/// A commander by the unit's own fields: rank, then intelligence, health and a weapon; no bonus comes of it.
int leaderScore(const BattleUnit *u)
{
	const int hp = u->getBaseStats()->health > 0 ? 10 * u->getHealth() / u->getBaseStats()->health : 0;
	return 1000 * rankWeight(u->getRankString()) + 100 * u->getIntelligence() + 10 * hp + (u->getMainHandWeapon(false) ? 5 : 0);
}

Node *closestNode(SavedBattleGame *save, const Position &p)
{
	Node *best = 0;
	int bestD = 1000000;
	for (auto *n : *save->getNodes())
	{
		if (n->isDummy()) continue;
		const int d = dist(p, n->getPosition());
		if (d < bestD)
		{
			best = n;
			bestD = d;
		}
	}
	return best;
}

void logOrder(const Order &o, const char *note = "")
{
	Log(LOG_INFO) << "[HIVEORD] turn=" << hq.save->getTurn() << " id=" << o.id << " squad=" << o.squad << " unit=" << o.unit->getId()
		<< " task=" << TASK_NAME[o.task] << " kind=" << (o.stay ? "STAY" : "GO") << " state=" << STATE_NAME[o.state]
		<< " target=" << pos(o.target) << " at=" << pos(o.unit->getPosition()) << " tu=" << o.unit->getTimeUnits()
		<< " why=" << o.why << " overrides=" << o.overrides << " note=" << note;
}

/// One line per closed walking order, the only source of the counts: what it came to, by where the unit really stands.
void logFate(const Order &o, const char *note)
{
	const Position here = o.unit->getPosition();
	const bool moved = o.moved || !(here == o.startAt);
	const int gain = dist(o.startAt, o.target) - dist(here, o.target);
	const char *fate = o.state == COMPLETED ? (moved ? "ARRIVED" : "ARRIVED_NO_STEP") : !moved ? "NOT_MOVED" : gain > 0 ? "MOVED_CLOSER" : "MOVED_NOT_CLOSER";
	std::string reason(note);
	reason = reason.substr(0, reason.find(' '));
	Log(LOG_INFO) << "[HIVEFATE] turn=" << hq.save->getTurn() << " id=" << o.id << " squad=" << o.squad << " unit=" << o.unit->getId() << " task=" << TASK_NAME[o.task]
		<< " issued=" << o.turn << " fate=" << fate << " reason=" << reason << " why=" << o.why << " start=" << pos(o.startAt) << " end=" << pos(here)
		<< " target=" << pos(o.target) << " path_tu=" << o.pathTu << " gain=" << gain << " decided_walk=" << (o.walked ? 1 : 0) << " overrides=" << o.overrides;
}

void setState(Order &o, OrderState s, const char *note = "")
{
	if (o.state == s) return;
	o.state = s;
	hq.stat[s]++;
	if (s == COMPLETED) o.doneTurn = hq.save->getTurn();
	logOrder(o, note);
	if (!o.stay && (s == COMPLETED || s == BLOCKED || s == INTERRUPTED || s == CANCELLED))
	{
		logFate(o, note);
	}
}

bool isTerminal(const Order &o)
{
	return o.state == BLOCKED || o.state == INTERRUPTED || o.state == CANCELLED;
}

/// The unit's field: once a turn from where it stands, or anew when something said the old one was wrong.
const Field &fieldOf(SavedBattleGame *save, BattleUnit *u, bool fresh = false)
{
	Field &f = hq.fields[u->getId()];
	if (!fresh && f.turn == save->getTurn() && f.at == u->getPosition())
	{
		return f;
	}
	const auto t0 = std::chrono::steady_clock::now();
	f.tiles = save->getPathfinding()->hiveFlood(u, ORDER_TURNS * u->getBaseStats()->tu, hq.flood, hq.floodPrev, f.capped);
	hq.floodUnit = u->getId();
	f.turn = save->getTurn();
	f.at = u->getPosition();
	f.node.assign(save->getNodes()->size(), -1);
	for (auto *n : *save->getNodes())
	{
		if (!n->isDummy() && n->getID() >= 0 && n->getID() < (int)f.node.size())
		{
			f.node[n->getID()] = hq.flood[save->getTileIndex(n->getPosition())];
		}
	}
	hq.floods++;
	hq.floodNs += std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t0).count();
	Log(LOG_INFO) << "[HIVEREACH] turn=" << save->getTurn() << " unit=" << u->getId() << " at=" << pos(f.at) << " tiles=" << f.tiles << " capped=" << (f.capped ? 1 : 0) << " tu=" << u->getTimeUnits();
	return f;
}

/// Takes what this unit has in sight: the only way a position of the other side comes in.
void observe(BattleUnit *unit, SavedBattleGame *save)
{
	bool any = false;
	for (auto *v : *unit->getVisibleUnits())
	{
		if (v->isOut() || v->getFaction() != FACTION_PLAYER) continue;
		any = true;
		Contact &c = hq.contacts[v->getId()];
		const bool fresh = c.id == -1 || !(c.pos == v->getPosition()) || c.seenTurn != save->getTurn();
		c.id = v->getId();
		c.pos = v->getPosition();
		c.cls = KNOWN;
		c.seenTurn = save->getTurn();
		c.observer = unit->getId();
		if (fresh)
		{
			Log(LOG_INFO) << "[HIVEFAIR] turn=" << save->getTurn() << " observer=" << unit->getId() << " target=" << v->getId() << " pos=" << pos(c.pos);
		}
	}
	if (any)
	{
		auto f = hq.squadOf.find(unit->getId());
		if (f != hq.squadOf.end())
		{
			hq.squads[f->second].cycle.saw++;
		}
	}
}

int contactTtl(const Squad &sq)
{
	return sq.commander ? sq.commander->getIntelligence() : 1;
}

void changeCommander(Squad &sq, const char *why)
{
	BattleUnit *best = 0;
	for (auto *m : sq.members)
	{
		if (available(m) && !unmanaged(m) && (!best || leaderScore(m) > leaderScore(best) || (leaderScore(m) == leaderScore(best) && m->getId() < best->getId())))
		{
			best = m;
		}
	}
	Log(LOG_INFO) << "[HIVECMD] turn=" << hq.save->getTurn() << " squad=" << sq.id << " old=" << (sq.commander ? sq.commander->getId() : -1)
		<< " new=" << (best ? best->getId() : -1) << " why=" << why << " rank=" << (best ? best->getRankString() : "-")
		<< " int=" << (best ? best->getIntelligence() : 0) << " task=" << TASK_NAME[sq.task] << " kept=" << (best ? 1 : 0);
	sq.commander = best;
}

/// A member of the squad can walk to this node.
bool memberReaches(Squad &sq, SavedBattleGame *save, Node *n)
{
	for (auto *m : sq.members)
	{
		if (!available(m) || unmanaged(m)) continue;
		const Field &f = fieldOf(save, m);
		if (n->getID() < (int)f.node.size() && f.node[n->getID()] > 0) return true;
	}
	return false;
}

/// A member of the squad stands at this place, or can walk to a node near it.
bool squadReaches(Squad &sq, SavedBattleGame *save, const Position &p)
{
	for (auto *m : sq.members)
	{
		if (available(m) && !unmanaged(m) && nearPos(m->getPosition(), p, VISIT_RADIUS)) return true;
	}
	for (auto *n : *save->getNodes())
	{
		if (!n->isDummy() && dist(p, n->getPosition()) <= OBJECTIVE_NODE_RADIUS && memberReaches(sq, save, n)) return true;
	}
	return false;
}

int squadDist(const Squad &sq, const Position &p)
{
	int best = 1000000;
	for (auto *m : sq.members)
	{
		if (available(m) && !unmanaged(m)) best = std::min(best, dist(m->getPosition(), p));
	}
	return best;
}

/// The next node the squad has not been to and can walk to: its own sector's first, then the nearest of the others.
bool sweepObjective(Squad &sq, SavedBattleGame *save, Objective &out)
{
	for (int pass = 0; pass < 2; ++pass)
	{
		Node *best = 0;
		int bestD = 1000000;
		for (auto &s : hq.sectors)
		{
			if ((pass == 0) != (s.id == sq.sector)) continue;
			for (auto *n : s.nodes)
			{
				if (s.visited.count(n->getID())) continue;
				const int d = dist(sq.commander->getPosition(), n->getPosition());
				if (d < bestD && memberReaches(sq, save, n))
				{
					best = n;
					bestD = d;
				}
			}
		}
		if (best)
		{
			out.valid = true;
			out.contact = false;
			out.contactId = -1;
			out.pos = best->getPosition();
			return true;
		}
	}
	return false;
}

/// A hold always has its place, its reason, its term and its way out.
void enterHold(Squad &sq, SavedBattleGame *save, HoldWhy why, const char *from)
{
	const int turn = save->getTurn();
	const bool was = sq.task == T_HOLD;
	sq.task = T_HOLD;
	sq.holdWhy = why;
	sq.holdSince = turn;
	sq.holdEnd = turn + HOLD_TURNS;
	sq.idle = 0;
	Node *n = closestNode(save, sq.commander->getPosition());
	sq.anchor = n ? n->getPosition() : sq.commander->getPosition();
	Log(LOG_INFO) << "[HIVEHOLD] turn=" << turn << " squad=" << sq.id << " commander=" << sq.commander->getId() << " event=" << (was ? "renewed" : "entered") << " from=" << from
		<< " anchor=" << pos(sq.anchor) << " why=" << HOLD_NAME[why] << " since=" << sq.holdSince << " end=" << sq.holdEnd << " exit=" << HOLD_EXITS;
}

/// The fewest time units a shot of the weapon in hand takes; 0: nothing to fire with, or nothing to fire.
int shotCost(BattleUnit *u)
{
	BattleItem *w = u->getMainHandWeapon(false);
	if (!w || !w->haveAnyAmmo()) return 0;
	int best = 0;
	for (BattleActionType t : { BA_SNAPSHOT, BA_AUTOSHOT, BA_AIMEDSHOT })
	{
		const int c = BattleActionCost(t, u, w).Time;
		if (c > 0 && (best == 0 || c < best)) best = c;
	}
	return best;
}

const char *kindName(const Squad &s)
{
	return s.role == R_ENGAGE ? "RESPOND" : s.task == T_HOLD ? "SECURE" : "SEARCH";
}

/// The place of the squad's task; false, it has none just now.
bool areaOf(const Squad &s, Position &center, int &radius)
{
	if (s.role == R_ENGAGE)
	{
		center = s.roleAt;
		radius = RESPOND_RADIUS;
		return true;
	}
	if (s.task == T_HOLD)
	{
		center = s.anchor;
		radius = SECURE_RADIUS;
		return true;
	}
	if (!s.objective.valid) return false;
	center = s.objective.pos;
	radius = SEARCH_RADIUS;
	return true;
}

std::string areaText(const Squad &s)
{
	Position c;
	int r = 0;
	if (!areaOf(s, c, r)) return std::string(kindName(s)) + ":-";
	return std::string(kindName(s)) + ":" + pos(c);
}

void markVisited(const Position &p)
{
	Node *n = closestNode(hq.save, p);
	if (!n) return;
	for (auto &s : hq.sectors)
	{
		if (std::find(s.nodes.begin(), s.nodes.end(), n) != s.nodes.end())
		{
			s.visited.insert(n->getID());
			return;
		}
	}
}

/// The next node of the sweep as the squad's place; the map walked through, the squad secures where it stands.
void nextObjective(Squad &sq, SavedBattleGame *save, const char *why)
{
	const std::string from = areaText(sq);
	Objective out;
	if (sweepObjective(sq, save, out))
	{
		out.keyPos = out.pos;
		out.since = save->getTurn();
		out.key = hq.nextKey++;
		sq.objective = out;
		sq.noProgress = 0;
		sq.bestDist = 1000000;
	}
	else
	{
		sq.objective.valid = false;
		enterHold(sq, save, HW_NOTHING_KNOWN, why);
	}
	Log(LOG_INFO) << "[HIVEUA] event=OBJECTIVE turn=" << save->getTurn() << " squad=" << sq.id << " commander=" << sq.commander->getId() << " from=" << from << " to=" << areaText(sq) << " why=" << why;
}

/// The commander or half the squad at the sweep's node: the search goes on to the next.
void objectiveReached(Squad &sq, SavedBattleGame *save)
{
	if (sq.task != T_SEARCH || sq.role != R_NONE || !sq.objective.valid || !sq.commander) return;
	int alive = 0, there = 0;
	for (auto *m : sq.members)
	{
		if (!available(m) || unmanaged(m)) continue;
		alive++;
		there += nearPos(m->getPosition(), sq.objective.pos, VISIT_RADIUS);
	}
	if (alive == 0 || (there * 2 < alive && !nearPos(sq.commander->getPosition(), sq.objective.pos, VISIT_RADIUS))) return;
	if (sq.replanTurn != save->getTurn())
	{
		sq.replanTurn = save->getTurn();
		sq.replans = 0;
	}
	if (sq.replans >= OBJECTIVE_REPLANS_PER_TURN) return;
	sq.replans++;
	markVisited(sq.objective.pos);
	nextObjective(sq, save, "reached");
}

/// The commander looks at what the task came to since the last plan, by what the squad really did: a fight is no failure of the search, a turn without an inch of progress is.
void reviewTask(Squad &sq, SavedBattleGame *save)
{
	const int turn = save->getTurn();
	const bool first = turn == hq.firstPlanTurn;
	const Cycle ev = sq.cycle;
	sq.cycle = Cycle();
	const bool useful = ev.shots + ev.reactions + ev.hurt + ev.saw > 0;
	if (sq.role == R_NONE)
	{
		if (sq.task == T_HOLD)
		{
			sq.idle = useful || first ? 0 : sq.idle + 1;
			if (sq.idle >= SECURE_IDLE)
			{
				hq.sectors[sq.sector].visited.clear();
				sq.task = T_SEARCH;
				sq.holdWhy = HW_NONE;
				sq.idle = 0;
				sq.objective.valid = false;
				nextObjective(sq, save, "secure_quiet");
			}
		}
		else if (!sq.objective.valid || first)
		{
			nextObjective(sq, save, first ? "first_plan" : "none");
		}
		else
		{
			int best = 1000000;
			for (auto *m : sq.members)
			{
				if (available(m) && !unmanaged(m)) best = std::min(best, dist(m->getPosition(), sq.objective.pos));
			}
			if (best < sq.bestDist)
			{
				sq.bestDist = best;
				sq.noProgress = 0;
			}
			else if (!useful)
			{
				sq.noProgress++;
			}
			const char *why = sq.noProgress >= SEARCH_STALL ? "no_progress" : turn - sq.objective.since > OBJECTIVE_TURNS ? "term_over" : 0;
			if (why)
			{
				markVisited(sq.objective.pos);
				nextObjective(sq, save, why);
			}
		}
	}
	Log(LOG_INFO) << "[HIVEUA] event=REVIEW turn=" << turn << " squad=" << sq.id << " area=" << areaText(sq) << " shots=" << ev.shots << " reactions=" << ev.reactions << " hurt=" << ev.hurt << " saw=" << ev.saw
		<< " idle=" << sq.idle << " noProgress=" << sq.noProgress << " best=" << sq.bestDist;
}

/// Once a side's turn: which contact in sight now gets a squad. Only a searching squad near it goes, one for a contact or a group of them, a third of the squads at most; a squad on guard stays.
void respond(SavedBattleGame *save)
{
	const int turn = save->getTurn();
	std::vector<const Contact*> sight;
	for (const auto &e : hq.contacts)
	{
		if (e.second.cls == KNOWN && e.second.seenTurn == turn) sight.push_back(&e.second);
	}
	int squads = 0, answering = 0;
	for (auto &s : hq.squads)
	{
		if (!s.commander) continue;
		squads++;
		if (s.role != R_ENGAGE) continue;
		const Contact *same = 0;
		for (auto *c : sight)
		{
			if (c->id == s.roleContact) same = c;
		}
		for (auto *c : sight)
		{
			if (!same && dist(c->pos, s.roleAt) <= RETARGET) same = c;
		}
		if (same)
		{
			s.roleContact = same->id;
			s.roleUntil = turn + RESPOND_TURNS;
			if (dist(same->pos, s.roleAt) <= RETARGET)
			{
				s.roleFar = 0;
			}
			else if (++s.roleFar >= 2)
			{
				// the same task, a place moved after the contact: two plans running, so that a step aside moves nobody
				const Position old = s.roleAt;
				s.roleAt = same->pos;
				s.roleFar = 0;
				Log(LOG_INFO) << "[HIVEUA] event=OBJECTIVE turn=" << turn << " squad=" << s.id << " commander=" << s.commander->getId() << " from=RESPOND:" << pos(old) << " to=" << areaText(s) << " why=contact_moved";
			}
		}
		if (turn > s.roleUntil)
		{
			Log(LOG_INFO) << "[HIVEUA] event=RETURN turn=" << turn << " squad=" << s.id << " from=RESPOND:" << pos(s.roleAt) << " contact=" << s.roleContact << " since=" << s.roleSince << " task=" << TASK_NAME[s.task] << " objective=" << (s.objective.valid ? pos(s.objective.pos) : "-");
			s.role = R_NONE;
			s.roleContact = -1;
			s.restUntil = turn + RESPOND_REST;
			s.objective.since = turn;
			s.noProgress = 0;
			s.bestDist = 1000000;
		}
		else
		{
			answering++;
		}
	}
	const int cap = (squads + 2) / 3;
	for (auto *c : sight)
	{
		bool covered = false;
		for (auto &s : hq.squads)
		{
			covered = covered || (s.commander && s.role == R_ENGAGE && dist(c->pos, s.roleAt) <= RETARGET);
		}
		if (covered || answering >= cap) continue;
		Squad *best = 0;
		int bestD = CONTACT_REACH + 1;
		for (auto &s : hq.squads)
		{
			if (!s.commander || s.task != T_SEARCH || s.role != R_NONE || turn <= s.restUntil) continue;
			int armed = 0;
			for (auto *m : s.members)
			{
				armed += available(m) && !unmanaged(m) && (shotCost(m) > 0 || std::string(role(m)) == "M");
			}
			const int d = squadDist(s, c->pos);
			if (armed >= REINFORCE_ARMED && d < bestD)
			{
				best = &s;
				bestD = d;
			}
		}
		if (!best) continue;
		const std::string from = areaText(*best);
		best->role = R_ENGAGE;
		best->roleContact = c->id;
		best->roleAt = c->pos;
		best->roleFar = 0;
		best->roleSince = turn;
		best->roleUntil = turn + RESPOND_TURNS;
		answering++;
		Log(LOG_INFO) << "[HIVEUA] event=OBJECTIVE turn=" << turn << " squad=" << best->id << " commander=" << best->commander->getId() << " from=" << from << " to=" << areaText(*best) << " why=contact contact=" << c->id << " dist=" << bestD << " observer=" << c->observer;
	}
}

/// The side's turn ended: what each soldier and each squad really came to, by where they stand and what they spent.
void logTurnEnd(SavedBattleGame *save)
{
	const int turn = save->getTurn();
	for (auto &s : hq.squads)
	{
		if (!s.commander) continue;
		Position center;
		int radius = 0;
		const bool has = areaOf(s, center, radius);
		int alive = 0, inside = 0;
		for (auto *m : s.members)
		{
			if (!available(m) || unmanaged(m)) continue;
			alive++;
			const Position here = m->getPosition();
			const int d = has ? dist(center, here) : -1;
			inside += has && d <= radius;
			const auto st = hq.starts.find(m->getId());
			if (st == hq.starts.end()) continue;
			const auto ch = hq.choices.find(m->getId());
			const bool walked = ch != hq.choices.end() && ch->second.walkTurn == turn;
			Log(LOG_INFO) << "[HIVEUA] event=RESULT turn=" << turn << " unit=" << m->getId() << " squad=" << s.id << " kind=" << kindName(s) << " center=" << (has ? pos(center) : "-") << " start=" << pos(st->second.at) << " end=" << pos(here)
				<< " spent=" << (st->second.tu - m->getTimeUnits()) << " tu=" << m->getTimeUnits() << " moved=" << (here == st->second.at ? 0 : 1) << " inside=" << (has && d <= radius ? 1 : 0)
				<< " closer=" << (has && d < dist(center, st->second.at) ? 1 : 0) << " walked=" << (walked ? 1 : 0) << " changed=" << (walked && ch->second.changed ? 1 : 0);
		}
		int visited = 0, nodes = 0;
		for (const auto &x : hq.sectors)
		{
			visited += x.visited.size();
			nodes += x.nodes.size();
		}
		Log(LOG_INFO) << "[HIVEUA] event=SQUADTURN turn=" << turn << " squad=" << s.id << " commander=" << s.commander->getId() << " kind=" << kindName(s) << " center=" << (has ? pos(center) : "-") << " alive=" << alive << " inside=" << inside
			<< " own_visited=" << hq.sectors[s.sector].visited.size() << " visited=" << visited << "/" << nodes << " shots=" << s.cycle.shots << " saw=" << s.cycle.saw;
	}
	Log(LOG_INFO) << "[HIVEPERF] turn=" << turn << " phase=turn floods=" << hq.floods << " floodUs=" << hq.floodNs / 1000;
}

void initSectors(SavedBattleGame *save, const std::vector<Squad> &squads)
{
	hq.sectors.clear();
	std::map<int, int> owner;
	std::vector<Node*> frontier;
	for (size_t i = 0; i < squads.size(); ++i)
	{
		Sector s;
		s.id = (int)i;
		hq.sectors.push_back(s);
		Node *n = closestNode(save, squads[i].commander->getPosition());
		if (n && !owner.count(n->getID()))
		{
			owner[n->getID()] = (int)i;
			frontier.push_back(n);
		}
	}
	// over the map's own links (its doors and passages), from each commander in turn; what no link reaches goes to the nearest commander
	auto *nodes = save->getNodes();
	while (!frontier.empty())
	{
		std::vector<Node*> next;
		for (auto *n : frontier)
		{
			for (int l : *n->getNodeLinks())
			{
				if (l < 0 || l >= (int)nodes->size()) continue;
				Node *m = nodes->at(l);
				if (m->isDummy() || owner.count(m->getID())) continue;
				owner[m->getID()] = owner[n->getID()];
				next.push_back(m);
			}
		}
		frontier.swap(next);
	}
	for (auto *n : *nodes)
	{
		if (n->isDummy()) continue;
		auto o = owner.find(n->getID());
		int sector = -1;
		if (o != owner.end())
		{
			sector = o->second;
		}
		else
		{
			int bestD = 1000000;
			for (size_t i = 0; i < squads.size(); ++i)
			{
				const int d = dist(n->getPosition(), squads[i].commander->getPosition());
				if (d < bestD)
				{
					bestD = d;
					sector = (int)i;
				}
			}
		}
		if (sector >= 0)
		{
			hq.sectors[sector].nodes.push_back(n);
		}
	}
}

/// The organization, from the side's own forces only: nothing is done with it and nothing of the other side is known yet.
void initialize(SavedBattleGame *save, const char *origin)
{
	const auto t0 = std::chrono::steady_clock::now();
	hq = Hq();
	hq.save = save;
	hq.managesBattle = save->getMissionType() != "STR_BASE_DEFENSE";

	std::vector<BattleUnit*> managed;
	int ours = 0, apart = 0;
	for (auto *u : *save->getUnits())
	{
		if (!isOurs(u)) continue;
		ours++;
		const char *why = unmanaged(u);
		const BattleItem *w = u->getMainHandWeapon(false);
		Log(LOG_INFO) << "[HIVEUNIT] id=" << u->getId() << " type=" << u->getType() << " pos=" << pos(u->getPosition()) << " status=" << (int)u->getStatus()
			<< " tu=" << u->getTimeUnits() << " energy=" << u->getEnergy() << " hp=" << u->getHealth() << "/" << u->getBaseStats()->health
			<< " rank=" << u->getRankString() << " int=" << u->getIntelligence() << " aggr=" << u->getAggression() << " role=" << role(u)
			<< " weapon=" << (w ? w->getRules()->getType() : "-") << " armor=" << u->getArmor()->getType() << " size=" << u->getArmor()->getSize()
			<< " move=" << (int)u->getMovementType() << " managed=" << (why ? "0" : "1") << " why=" << (why ? why : "-");
		if (why)
		{
			apart++;
		}
		else
		{
			managed.push_back(u);
		}
	}
	int rank0 = 0, usable = 0;
	for (auto *n : *save->getNodes())
	{
		if (n->isDummy()) continue;
		usable++;
		rank0 += n->getRank() == 0;
	}

	if (hq.managesBattle && !managed.empty())
	{
		// commanders: the best by their own fields, spaced apart while there are enough of them
		const int count = std::max(1, ((int)managed.size() + SQUAD_TARGET - 1) / SQUAD_TARGET);
		std::vector<BattleUnit*> byScore(managed);
		std::stable_sort(byScore.begin(), byScore.end(), [](BattleUnit *a, BattleUnit *b)
		{
			const int sa = leaderScore(a), sb = leaderScore(b);
			return sa != sb ? sa > sb : a->getId() < b->getId();
		});
		std::vector<BattleUnit*> leaders;
		for (auto *u : byScore)
		{
			if ((int)leaders.size() >= count) break;
			if (std::string(role(u)) == "M") continue;
			bool spaced = true;
			for (auto *l : leaders)
			{
				spaced = spaced && dist(u->getPosition(), l->getPosition()) >= LEADER_SPACING;
			}
			if (spaced) leaders.push_back(u);
		}
		for (auto *u : byScore)
		{
			if ((int)leaders.size() >= count) break;
			if (std::find(leaders.begin(), leaders.end(), u) == leaders.end()) leaders.push_back(u);
		}
		for (size_t i = 0; i < leaders.size(); ++i)
		{
			Squad s;
			s.id = (int)i;
			s.commander = leaders[i];
			s.sector = (int)i;
			s.members.push_back(leaders[i]);
			hq.squads.push_back(s);
			hq.squadOf[leaders[i]->getId()] = (int)i;
		}
		// the rest: near, but a weapon class the squad lacks is worth tiles, and a squad over its target size costs more
		for (auto *u : managed)
		{
			if (hq.squadOf.count(u->getId())) continue;
			int best = -1, bestCost = 1000000;
			const std::string r = role(u);
			for (auto &s : hq.squads)
			{
				if ((int)s.members.size() >= SQUAD_MAX) continue;
				int same = 0;
				for (auto *m : s.members)
				{
					same += r == role(m);
				}
				const int cost = dist(u->getPosition(), s.commander->getPosition()) + 4 * same + ((int)s.members.size() >= SQUAD_TARGET ? 8 : 0);
				if (cost < bestCost)
				{
					bestCost = cost;
					best = s.id;
				}
			}
			if (best < 0)
			{
				best = 0;
			}
			hq.squads[best].members.push_back(u);
			hq.squadOf[u->getId()] = best;
		}
		initSectors(save, hq.squads);
		// the tasks, no dice: long arms and the squads standing most inside hold, the short arms go looking; a third on guard, one of each from two squads on
		std::vector<std::pair<int, int> > holdScore;
		for (auto &s : hq.squads)
		{
			int score = 0;
			for (auto *m : s.members)
			{
				const std::string r = role(m);
				score += r == "L" ? 2 : r == "S" ? -1 : 0;
			}
			holdScore.push_back(std::make_pair(-score, s.id));
		}
		std::stable_sort(holdScore.begin(), holdScore.end());
		const int holders = hq.squads.size() >= 2 ? ((int)hq.squads.size() + 2) / 3 : 0;
		for (size_t i = 0; i < holdScore.size(); ++i)
		{
			Squad &s = hq.squads[holdScore[i].second];
			s.task = (int)i < holders ? T_HOLD : T_SEARCH;
			Node *n = closestNode(save, s.commander->getPosition());
			s.anchor = n ? n->getPosition() : s.commander->getPosition();
			if (s.task == T_SEARCH)
			{
				s.objective.valid = true;
				s.objective.pos = s.objective.keyPos = s.anchor;
				s.objective.since = save->getTurn();
				s.objective.key = hq.nextKey++;
			}
			if (s.task == T_HOLD)
			{
				s.holdWhy = HW_GUARD;
				s.holdSince = save->getTurn();
				s.holdEnd = save->getTurn() + HOLD_TURNS;
				Log(LOG_INFO) << "[HIVEHOLD] turn=" << save->getTurn() << " squad=" << s.id << " commander=" << s.commander->getId() << " event=entered from=organization"
					<< " anchor=" << pos(s.anchor) << " why=" << HOLD_NAME[s.holdWhy] << " since=" << s.holdSince << " end=" << s.holdEnd << " exit=" << HOLD_EXITS;
			}
		}
		for (auto &s : hq.squads)
		{
			std::ostringstream m;
			for (auto *u : s.members)
			{
				m << (m.tellp() > 0 ? "," : "") << u->getId() << role(u);
			}
			Log(LOG_INFO) << "[HIVESQUAD] id=" << s.id << " commander=" << s.commander->getId() << " rank=" << s.commander->getRankString() << " int=" << s.commander->getIntelligence()
				<< " at=" << pos(s.commander->getPosition()) << " size=" << s.members.size() << " members=" << m.str() << " sector=" << s.sector << " sectorNodes=" << hq.sectors[s.sector].nodes.size()
				<< " task=" << TASK_NAME[s.task] << " anchor=" << pos(s.anchor) << " hold=" << HOLD_NAME[s.holdWhy] << " holdEnd=" << s.holdEnd;
			Log(LOG_INFO) << "[HIVEUA] event=ORG turn=" << save->getTurn() << " squad=" << s.id << " commander=" << s.commander->getId() << " size=" << s.members.size() << " area=" << areaText(s) << " sector=" << s.sector;
		}
	}
	const long long us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - t0).count();
	Log(LOG_INFO) << "[HIVEINIT] origin=" << origin << " turn=" << save->getTurn() << " side=" << (int)save->getSide() << " mission=" << save->getMissionType() << " manages=" << (hq.managesBattle ? 1 : 0) << " hostile=" << ours << " managed=" << managed.size()
		<< " apart=" << apart << " nodes=" << usable << " rank0=" << rank0 << " sectors=" << hq.sectors.size() << " squads=" << hq.squads.size() << " us=" << us;
}

/// Commanders down and units out, seen when the side's turn opens or one of the squad's units thinks.
void checkSquad(Squad &sq, SavedBattleGame *save)
{
	if (sq.commander && (sq.commander->isOut() || !isOurs(sq.commander)))
	{
		const char *why = sq.commander->isOut() ? (sq.commander->getStatus() == STATUS_DEAD ? "dead" : "stunned") : "faction";
		changeCommander(sq, why);
		if (sq.commander)
		{
			if (sq.task == T_SEARCH && sq.objective.valid)
			{
				// the search goes on under the new commander; the task and the squad's other orders stay
				Log(LOG_INFO) << "[HIVETASK] turn=" << save->getTurn() << " squad=" << sq.id << " task=SEARCH commander=" << sq.commander->getId() << " kept=1 key=" << sq.objective.key << " objective=" << pos(sq.objective.pos);
			}
		}
	}
}

/// A side's turn opens: last turn's orders closed by what really happened, the memory aged, the army kept and not rebuilt, each task reviewed.
void planTurn(SavedBattleGame *save)
{
	const auto t0 = std::chrono::steady_clock::now();
	const int turn = save->getTurn();
	hq.turn = turn;
	const bool first = hq.firstPlanTurn < 0;
	if (first)
	{
		hq.firstPlanTurn = turn;
	}
	hq.turnOpen = true;
	hq.taken.clear();
	hq.fields.clear();
	hq.lines.clear();
	hq.floodUnit = -1;
	hq.thinkNs = 0;
	hq.thinks = 0;
	hq.floods = 0;
	hq.floodNs = 0;
	hq.rejFar = hq.rejUnreachable = hq.rejMemo = hq.rejIllegal = 0;
	hq.starts.clear();
	for (auto *u : *save->getUnits())
	{
		if (available(u))
		{
			TurnStart &st = hq.starts[u->getId()];
			st.at = u->getPosition();
			st.tu = u->getTimeUnits();
		}
	}

	if (first)
	{
		int fallen = 0, commanders = 0;
		for (auto &s : hq.squads)
		{
			commanders += s.commander && !available(s.commander);
			for (auto *m : s.members)
			{
				fallen += !available(m);
			}
		}
		Log(LOG_INFO) << "[HIVEFIRST] turn=" << turn << " squads=" << hq.squads.size() << " fallen_since_spawn=" << fallen << " commanders_fallen=" << commanders;
	}
	for (auto *u : *save->getUnits())
	{
		if (isOurs(u) && !u->isOut())
		{
			observe(u, save);
		}
	}
	for (auto i = hq.contacts.begin(); i != hq.contacts.end(); )
	{
		Contact &c = i->second;
		if (c.seenTurn != turn && c.cls == KNOWN)
		{
			c.cls = LAST_KNOWN;
		}
		int ttl = 0;
		for (auto &s : hq.squads)
		{
			ttl = std::max(ttl, contactTtl(s));
		}
		if (turn - c.seenTurn > ttl)
		{
			Log(LOG_INFO) << "[HIVECONTACT] turn=" << turn << " target=" << c.id << " pos=" << pos(c.pos) << " cls=" << KNOW_NAME[c.cls] << " event=expired ttl=" << ttl;
			i = hq.contacts.erase(i);
		}
		else
		{
			Log(LOG_INFO) << "[HIVECONTACT] turn=" << turn << " target=" << c.id << " pos=" << pos(c.pos) << " cls=" << KNOW_NAME[c.cls] << " age=" << (turn - c.seenTurn) << " observer=" << c.observer;
			++i;
		}
	}
	// a unit of ours fell with nobody it could have seen: there is an enemy about that place, no more is known
	int inferredId = -2;
	for (auto *u : *save->getUnits())
	{
		if (u->getOriginalFaction() != FACTION_HOSTILE || !u->isOut() || hq.seenOut.count(u->getId())) continue;
		hq.seenOut.insert(u->getId());
		if (!hq.squadOf.count(u->getId())) continue;
		bool explained = false;
		for (auto &e : hq.contacts)
		{
			explained = explained || (e.second.cls != INFERRED && dist(e.second.pos, u->getPosition()) <= CONTACT_REACH && e.second.seenTurn >= turn - 1);
		}
		if (!explained)
		{
			Contact c;
			c.id = inferredId - u->getId();
			c.pos = u->getPosition();
			c.cls = INFERRED;
			c.seenTurn = turn;
			c.observer = u->getId();
			hq.contacts[c.id] = c;
			Log(LOG_INFO) << "[HIVECONTACT] turn=" << turn << " target=" << c.id << " pos=" << pos(c.pos) << " cls=INFERRED event=own_loss unit=" << u->getId();
		}
	}
	// orders of the fallen; orders left too long
	for (auto &e : hq.orders)
	{
		Order &o = e.second;
		if (!o.unit || isTerminal(o) || o.state == COMPLETED) continue;
		if (!available(o.unit))
		{
			setState(o, INTERRUPTED, "unit_out");
		}
		else if (!o.stay && turn - o.turn >= ORDER_TURNS)
		{
			setState(o, CANCELLED, "too_long");
		}
	}
	// commanders, newcomers, squads too small
	for (auto &s : hq.squads)
	{
		checkSquad(s, save);
	}
	for (auto *u : *save->getUnits())
	{
		if (!isOurs(u) || u->isOut() || unmanaged(u) || hq.squadOf.count(u->getId()) || hq.squads.empty()) continue;
		int best = -1, bestD = 1000000;
		for (auto &s : hq.squads)
		{
			if (!s.commander || (int)s.members.size() >= SQUAD_MAX) continue;
			const int d = dist(u->getPosition(), s.commander->getPosition());
			if (d < bestD)
			{
				best = s.id;
				bestD = d;
			}
		}
		if (best >= 0)
		{
			hq.squads[best].members.push_back(u);
			hq.squadOf[u->getId()] = best;
			Log(LOG_INFO) << "[HIVESQUAD] turn=" << turn << " join=" << u->getId() << " squad=" << best;
		}
	}
	for (auto &s : hq.squads)
	{
		int alive = 0;
		for (auto *m : s.members)
		{
			alive += available(m);
		}
		if (!s.commander || alive >= 3) continue;
		int best = -1, bestD = 1000000;
		for (auto &t : hq.squads)
		{
			if (t.id == s.id || !t.commander) continue;
			int talive = 0;
			for (auto *m : t.members)
			{
				talive += available(m);
			}
			const int d = dist(s.commander->getPosition(), t.commander->getPosition());
			if (talive + alive <= SQUAD_MAX && d < bestD)
			{
				best = t.id;
				bestD = d;
			}
		}
		if (best < 0) continue;
		Squad &t = hq.squads[best];
		for (auto *m : s.members)
		{
			if (!available(m)) continue;
			t.members.push_back(m);
			hq.squadOf[m->getId()] = best;
		}
		Log(LOG_INFO) << "[HIVESQUAD] turn=" << turn << " merged=" << s.id << " into=" << best << " units=" << alive << " task=" << TASK_NAME[t.task];
		s.members.clear();
		s.commander = 0;
	}
	respond(save);
	for (auto &s : hq.squads)
	{
		if (s.commander)
		{
			reviewTask(s, save);
		}
	}
	const long long us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - t0).count();
	Log(LOG_INFO) << "[HIVEPERF] turn=" << turn << " phase=plan us=" << us << " contacts=" << hq.contacts.size() << " floods=" << hq.floods << " floodUs=" << hq.floodNs / 1000
		<< " rejFar=" << hq.rejFar << " rejUnreachable=" << hq.rejUnreachable << " rejMemo=" << hq.rejMemo << " rejIllegal=" << hq.rejIllegal;
}

/// The saved form: one scalar of records, whole numbers and plain names only, so that it reads back to the same text.
void put(std::ostringstream &s, const Position &p)
{
	s << ',' << p.x << ',' << p.y << ',' << p.z;
}

template <typename T>
void putList(std::ostringstream &s, const T &list)
{
	s << ',';
	bool first = true;
	for (const auto &v : list)
	{
		s << (first ? "" : ".") << v;
		first = false;
	}
}

std::string dump(const Hq &h)
{
	std::ostringstream s;
	s << "HIVE1;H," << h.turn << ',' << h.firstPlanTurn << ',' << (int)h.turnOpen << ',' << h.nextOrder << ',' << h.nextKey << ',' << (int)h.managesBattle;
	for (int v : h.stat)
	{
		s << ',' << v;
	}
	for (const auto &x : h.sectors)
	{
		std::vector<int> ids;
		for (auto *n : x.nodes)
		{
			ids.push_back(n->getID());
		}
		s << ";N," << x.id;
		putList(s, ids);
		putList(s, x.visited);
	}
	for (const auto &q : h.squads)
	{
		std::vector<int> ids;
		for (auto *m : q.members)
		{
			ids.push_back(m->getId());
		}
		s << ";S," << q.id << ',' << (q.commander ? q.commander->getId() : -1) << ',' << (int)q.task << ',' << q.sector;
		put(s, q.anchor);
		s << ',' << (int)q.objective.valid << ',' << (int)q.objective.contact << ',' << q.objective.contactId;
		put(s, q.objective.pos);
		put(s, q.objective.keyPos);
		s << ',' << q.objective.since << ',' << q.objective.key << ',' << q.replans << ',' << q.replanTurn << ',' << (int)q.holdWhy << ',' << q.holdSince << ',' << q.holdEnd << ',' << q.idle
			<< ',' << q.noProgress << ',' << q.bestDist << ',' << q.cycle.shots << ',' << q.cycle.reactions << ',' << q.cycle.hurt << ',' << q.cycle.saw;
		putList(s, ids);
		for (const auto &k : q.skip)
		{
			s << ";K," << q.id << ',' << k.first << ',' << k.second;
		}
		if (q.role != R_NONE || q.restUntil != -1)
		{
			s << ";R," << q.id << ',' << (int)q.role << ',' << q.roleContact << ',' << q.roleSince << ',' << q.roleUntil << ',' << q.restUntil << ',' << q.roleShots << ',' << q.roleStall << ',' << q.roleBest;
			put(s, q.roleAt);
			s << ',' << q.roleFar;
		}
	}
	for (const auto &e : h.orders)
	{
		const Order &o = e.second;
		if (!o.unit) continue;
		s << ";O," << o.id << ',' << o.squad << ',' << o.unit->getId() << ',' << (int)o.task << ',' << (int)o.stay << ',' << (o.node ? o.node->getID() : -1);
		put(s, o.target);
		s << ',' << (int)o.state << ',' << o.why << ',' << o.objectiveKey << ',' << o.turn << ',' << o.overrides << ',' << o.stuck << ',' << o.stuckTurns << ',' << o.pauseTurn;
		put(s, o.lastPos);
		put(s, o.turnStart);
		put(s, o.startAt);
		s << ',' << o.lastTurn << ',' << o.checkTurn << ',' << o.doneTurn << ',' << o.pathTu << ',' << (int)o.walked << ',' << (int)o.moved;
	}
	for (const auto &e : h.contacts)
	{
		const Contact &c = e.second;
		s << ";C," << c.id;
		put(s, c.pos);
		s << ',' << (int)c.cls << ',' << c.seenTurn << ',' << c.observer;
	}
	for (const auto &u : h.blocked)
	{
		for (const auto &n : u.second)
		{
			s << ";B," << u.first << ',' << n.first << ',' << n.second.first << ',' << n.second.second;
		}
	}
	for (const auto &e : h.ledger)
	{
		s << ";L," << e.first << ',' << e.second.first << ',' << e.second.second;
	}
	s << ";X";
	putList(s, h.seenOut);
	return s.str();
}

std::vector<std::string> split(const std::string &text, char by)
{
	std::vector<std::string> out;
	size_t from = 0;
	for (;;)
	{
		const size_t at = text.find(by, from);
		out.push_back(text.substr(from, at == std::string::npos ? std::string::npos : at - from));
		if (at == std::string::npos) return out;
		from = at + 1;
	}
}

struct Rec
{
	std::vector<std::string> f;
	size_t i = 1;
	int num() { return std::stoi(f.at(i++)); }
	bool flag() { return num() != 0; }
	const std::string &str() { return f.at(i++); }
	Position place() { const int x = num(), y = num(), z = num(); return Position(x, y, z); }
	int range(int low, int high)
	{
		const int v = num();
		if (v < low || v > high) throw std::runtime_error("out of range");
		return v;
	}
	std::vector<int> list()
	{
		std::vector<int> out;
		const std::string &text = str();
		if (!text.empty())
		{
			for (const auto &v : split(text, '.'))
			{
				out.push_back(std::stoi(v));
			}
		}
		return out;
	}
};

/// Back from the saved form, with every unit and node found again in this battle; anything that does not fit fails the whole.
bool parse(const std::string &text, SavedBattleGame *save, Hq &h, std::string &error)
{
	try
	{
		std::map<int, BattleUnit*> units;
		for (auto *u : *save->getUnits())
		{
			if (u->getOriginalFaction() == FACTION_HOSTILE) units[u->getId()] = u;
		}
		std::map<int, Node*> nodes;
		for (auto *n : *save->getNodes())
		{
			nodes[n->getID()] = n;
		}
		const auto unitOf = [&units](int id) -> BattleUnit* { return units.at(id); };
		h.save = save;
		const std::vector<std::string> records = split(text, ';');
		if (records.at(0) != "HIVE1") throw std::runtime_error("version");
		for (size_t r = 1; r < records.size(); ++r)
		{
			Rec x;
			x.f = split(records[r], ',');
			const std::string &type = x.f.at(0);
			if (type == "H")
			{
				h.turn = x.num();
				h.firstPlanTurn = x.num();
				h.turnOpen = x.flag();
				h.nextOrder = x.num();
				h.nextKey = x.num();
				h.managesBattle = x.flag();
				for (int &v : h.stat)
				{
					v = x.num();
				}
			}
			else if (type == "N")
			{
				Sector s;
				s.id = x.num();
				if (s.id != (int)h.sectors.size()) throw std::runtime_error("sector order");
				for (int id : x.list())
				{
					s.nodes.push_back(nodes.at(id));
				}
				for (int id : x.list())
				{
					s.visited.insert(id);
				}
				h.sectors.push_back(s);
			}
			else if (type == "S")
			{
				Squad q;
				q.id = x.num();
				if (q.id != (int)h.squads.size()) throw std::runtime_error("squad order");
				const int commander = x.num();
				q.commander = commander == -1 ? 0 : unitOf(commander);
				q.task = (Task)x.range(0, 1);
				q.sector = x.num();
				if (q.sector < 0 || q.sector >= (int)h.sectors.size()) throw std::runtime_error("sector");
				q.anchor = x.place();
				q.objective.valid = x.flag();
				q.objective.contact = x.flag();
				q.objective.contactId = x.num();
				q.objective.pos = x.place();
				q.objective.keyPos = x.place();
				q.objective.since = x.num();
				q.objective.key = x.num();
				q.replans = x.num();
				q.replanTurn = x.num();
				q.holdWhy = (HoldWhy)x.range(0, 3);
				q.holdSince = x.num();
				q.holdEnd = x.num();
				q.idle = x.num();
				q.noProgress = x.num();
				q.bestDist = x.num();
				q.cycle.shots = x.num();
				q.cycle.reactions = x.num();
				q.cycle.hurt = x.num();
				q.cycle.saw = x.num();
				for (int id : x.list())
				{
					if (h.squadOf.count(id)) throw std::runtime_error("unit in two squads");
					q.members.push_back(unitOf(id));
					h.squadOf[id] = q.id;
				}
				if (q.commander && std::find(q.members.begin(), q.members.end(), q.commander) == q.members.end()) throw std::runtime_error("commander outside the squad");
				h.squads.push_back(q);
			}
			else if (type == "K")
			{
				const int squad = x.num();
				const int contact = x.num();
				h.squads.at(squad).skip[contact] = x.num();
			}
			else if (type == "R")
			{
				Squad &q = h.squads.at(x.num());
				q.role = (Role)x.range(0, 3);
				q.roleContact = x.num();
				q.roleSince = x.num();
				q.roleUntil = x.num();
				q.restUntil = x.num();
				q.roleShots = x.num();
				q.roleStall = x.num();
				q.roleBest = x.num();
				q.roleAt = x.place();
				q.roleFar = x.num();
			}
			else if (type == "O")
			{
				Order o;
				o.id = x.num();
				o.squad = x.num();
				if (o.squad < 0 || o.squad >= (int)h.squads.size()) throw std::runtime_error("order's squad");
				o.unit = unitOf(x.num());
				o.task = (Task)x.range(0, 1);
				o.stay = x.flag();
				const int node = x.num();
				o.node = node == -1 ? 0 : nodes.at(node);
				o.target = x.place();
				o.state = (OrderState)x.range(0, 7);
				o.why = x.str();
				o.objectiveKey = x.num();
				o.turn = x.num();
				o.overrides = x.num();
				o.stuck = x.num();
				o.stuckTurns = x.num();
				o.pauseTurn = x.num();
				o.lastPos = x.place();
				o.turnStart = x.place();
				o.startAt = x.place();
				o.lastTurn = x.num();
				o.checkTurn = x.num();
				o.doneTurn = x.num();
				o.pathTu = x.num();
				o.walked = x.flag();
				o.moved = x.flag();
				h.orders[o.unit->getId()] = o;
			}
			else if (type == "C")
			{
				Contact c;
				c.id = x.num();
				c.pos = x.place();
				c.cls = (Knowledge)x.range(0, 2);
				c.seenTurn = x.num();
				c.observer = x.num();
				h.contacts[c.id] = c;
			}
			else if (type == "B")
			{
				const int unit = x.num();
				const int node = x.num();
				const int tile = x.num();
				h.blocked[unit][node] = std::make_pair(tile, x.num());
			}
			else if (type == "L")
			{
				const int unit = x.num();
				const int tu = x.num();
				h.ledger[unit] = std::make_pair(tu, x.num());
			}
			else if (type == "X")
			{
				for (int id : x.list())
				{
					h.seenOut.insert(id);
				}
			}
			else
			{
				throw std::runtime_error("record " + type);
			}
		}
		return true;
	}
	catch (const std::exception &e)
	{
		error = e.what();
		return false;
	}
}

unsigned long long fnv(const std::string &text)
{
	unsigned long long h = 1469598103934665603ULL;
	for (unsigned char c : text)
	{
		h = (h ^ c) * 1099511628211ULL;
	}
	return h;
}

/// Every side's turn the state goes through its saved form and back in memory: what a load would get, without a load.
void saveCheck(SavedBattleGame *save)
{
	const auto t0 = std::chrono::steady_clock::now();
	const std::string text = dump(hq);
	Hq back;
	std::string error;
	const bool ok = parse(text, save, back, error);
	const bool same = ok && dump(back) == text;
	const long long us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - t0).count();
	Log(LOG_INFO) << "[HIVESAVECHECK] turn=" << save->getTurn() << " parsed=" << (ok ? 1 : 0) << " same=" << (same ? 1 : 0) << " bytes=" << text.size() << " hash=" << fnv(text) << " us=" << us << " error=" << error;
}

}

bool NodeFit::accepts(const Node *n) const
{
	if (n->getID() < 0 || n->getID() >= (int)reach->size() || (*reach)[n->getID()] <= 0) return false;
	const int d = dist(center, n->getPosition());
	if (closer ? d >= here : d > radius) return false;
	if (skipVisited)
	{
		for (const auto &s : hq.sectors)
		{
			if (s.visited.count(n->getID())) return false;
		}
	}
	accepted++;
	return true;
}

int mode()
{
	static const int m = (int)AiProbe::param("OXCE_AI_HIVE", 0);
	return m;
}

void battleStarts(SavedBattleGame *save)
{
	if (mode() == 0 || save->isPreview()) return;
	if (hq.save == save && hq.restored)
	{
		hq.restored = false;
		Log(LOG_INFO) << "[HIVEINIT] origin=restored turn=" << save->getTurn() << " side=" << (int)save->getSide() << " squads=" << hq.squads.size() << " orders=" << hq.orders.size() << " contacts=" << hq.contacts.size();
		return;
	}
	const char *origin = pendingSave == save ? pendingOrigin : "spawn";
	pendingSave = 0;
	initialize(save, origin);
}

void loaded(SavedBattleGame *save, const std::string *text)
{
	if (mode() == 0) return;
	hq = Hq();
	pendingSave = save;
	pendingOrigin = "load_no_hive";
	if (!text) return;
	Hq back;
	std::string error;
	if (!parse(*text, save, back, error))
	{
		Log(LOG_ERROR) << "[HIVELOAD] parsed=0 error=" << error;
		pendingOrigin = "load_bad_hive";
		return;
	}
	const bool same = dump(back) == *text;
	Log(LOG_INFO) << "[HIVELOAD] parsed=1 same=" << (same ? 1 : 0) << " turn=" << save->getTurn() << " hash=" << fnv(*text) << " bytes=" << text->size() << " text=" << *text;
	hq = back;
	hq.restored = true;
	pendingSave = 0;
	if (hq.turnOpen)
	{
		// saved inside the side's turn: the engine opens that turn again with full time units, so the plan is made again; the army stays
		Log(LOG_INFO) << "[HIVELOAD] mid_side_turn=1 turn=" << hq.turn;
		hq.turn = -1;
		hq.turnOpen = false;
	}
}

bool saveText(const SavedBattleGame *save, std::string &text)
{
	if (mode() == 0 || hq.save != save) return false;
	text = dump(hq);
	Log(LOG_INFO) << "[HIVESAVE] turn=" << save->getTurn() << " side=" << (int)save->getSide() << " hash=" << fnv(text) << " bytes=" << text.size() << " text=" << text;
	return true;
}

void forget(const SavedBattleGame *save)
{
	if (hq.save == save)
	{
		hq = Hq();
	}
	if (pendingSave == save)
	{
		pendingSave = 0;
	}
}

void beforeThink(SavedBattleGame *save, BattleUnit *unit)
{
	if (mode() == 0 || save->getSide() != FACTION_HOSTILE || !isOurs(unit)) return;
	const auto t0 = std::chrono::steady_clock::now();
	if (hq.save != save)
	{
		initialize(save, "late");
	}
	if (hq.turn != save->getTurn())
	{
		planTurn(save);
	}
	if (hq.managesBattle)
	{
		observe(unit, save);
		auto f = hq.squadOf.find(unit->getId());
		if (f != hq.squadOf.end())
		{
			Squad &sq = hq.squads[f->second];
			checkSquad(sq, save);
			objectiveReached(sq, save);
			if (sq.task == T_SEARCH && sq.role == R_NONE)
			{
				for (auto &s : hq.sectors)
				{
					for (auto *n : s.nodes)
					{
						if (nearPos(unit->getPosition(), n->getPosition(), VISIT_RADIUS))
						{
							s.visited.insert(n->getID());
						}
					}
				}
			}
		}
	}
	hq.thinkNs += std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - t0).count();
	hq.thinks++;
}

namespace
{

/// The place of this unit's squad's task, without any search; 0, none: out of the system's hands, or the squad has nothing for it.
Squad *taskOf(SavedBattleGame *save, BattleUnit *unit, NodeFit &fit)
{
	if (mode() == 0 || hq.save != save || !hq.managesBattle || save->getSide() != FACTION_HOSTILE || !isOurs(unit) || unmanaged(unit)) return 0;
	const auto f = hq.squadOf.find(unit->getId());
	if (f == hq.squadOf.end()) return 0;
	Squad &sq = hq.squads[f->second];
	if (!sq.commander || !areaOf(sq, fit.center, fit.radius)) return 0;
	fit.squad = sq.id;
	fit.kind = kindName(sq);
	fit.here = dist(fit.center, unit->getPosition());
	fit.hasVisited = sq.role == R_NONE && sq.task == T_SEARCH;
	return &sq;
}

}

bool patrolIntent(SavedBattleGame *save, BattleUnit *unit, NodeFit &fit)
{
	if (!taskOf(save, unit, fit)) return false;
	fit.reach = &fieldOf(save, unit).node;
	return true;
}

bool fitRung(NodeFit &fit, int rung, bool &mapWide)
{
	fit.accepted = 0;
	fit.closer = rung == 4;
	fit.skipVisited = rung <= 1;
	mapWide = rung == 1 || rung >= 3;
	return rung == 4 ? fit.here > fit.radius : rung <= 1 ? fit.hasVisited : true;
}

void patrolChosen(SavedBattleGame *save, BattleUnit *unit, const NodeFit &fit, int rung, int tryNo, Node *free, Node *chosen)
{
	const int turn = save->getTurn();
	const bool changed = chosen != 0 && chosen != free;
	Node *done = mode() == 2 && chosen != 0 ? chosen : free;
	const auto nodePos = [](Node *n) { return n ? pos(n->getPosition()) : std::string("(-1,-1,-1)"); };
	const auto inside = [&fit](Node *n) { return n && dist(fit.center, n->getPosition()) <= fit.radius; };
	const auto closer = [&fit](Node *n) { return n && dist(fit.center, n->getPosition()) < fit.here; };
	Log(LOG_INFO) << "[HIVEUA] event=CHOICE turn=" << turn << " unit=" << unit->getId() << " squad=" << fit.squad << " kind=" << fit.kind << " try=" << tryNo << " at=" << pos(unit->getPosition()) << " center=" << pos(fit.center) << " radius=" << fit.radius
		<< " free=" << nodePos(free) << " chosen=" << nodePos(chosen) << " changed=" << (changed ? 1 : 0) << " fit=" << fit.accepted << " rung=" << rung << " inside=" << (inside(chosen) ? 1 : 0) << " closer=" << (closer(chosen) ? 1 : 0)
		<< " free_inside=" << (inside(free) ? 1 : 0) << " free_closer=" << (closer(free) ? 1 : 0) << " fallback=" << (chosen ? 0 : 1) << " tu=" << unit->getTimeUnits();
	if (!chosen)
	{
		hq.fellBack[unit->getId()] = turn;
	}
	if (done)
	{
		Choice &c = hq.choices[unit->getId()];
		c.node = done->getPosition();
		c.changed = changed;
	}
	else
	{
		hq.choices.erase(unit->getId());
	}
}

bool dropKept(SavedBattleGame *save, BattleUnit *unit, Node *kept)
{
	NodeFit fit;
	if (!taskOf(save, unit, fit)) return false;
	const int turn = save->getTurn(), id = unit->getId();
	const auto back = hq.fellBack.find(id);
	const auto was = hq.dropped.find(id);
	if ((back != hq.fellBack.end() && back->second == turn) || (was != hq.dropped.end() && was->second == turn)) return false;
	const int d = dist(fit.center, kept->getPosition());
	if (d <= fit.radius || (fit.here > fit.radius && d < fit.here)) return false;
	hq.dropped[id] = turn;
	Log(LOG_INFO) << "[HIVEUA] event=KEPT_DROP turn=" << turn << " unit=" << id << " squad=" << fit.squad << " kind=" << fit.kind << " at=" << pos(unit->getPosition()) << " center=" << pos(fit.center) << " radius=" << fit.radius << " node=" << pos(kept->getPosition()) << " real=" << (mode() == 2 ? 1 : 0);
	return mode() == 2;
}

void decided(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (mode() == 0 || hq.save != save || !hq.managesBattle || save->getSide() != FACTION_HOSTILE || !isOurs(unit)) return;
	const auto sf = hq.squadOf.find(unit->getId());
	if (sf == hq.squadOf.end()) return;
	Squad &sq = hq.squads[sf->second];
	if (isAttack(action.type))
	{
		sq.cycle.shots++;
	}
	if (action.type == BA_NONE) return;
	const auto ch = hq.choices.find(unit->getId());
	const bool onChoice = action.type == BA_WALK && ch != hq.choices.end() && ch->second.node == action.target;
	if (onChoice)
	{
		ch->second.walkTurn = save->getTurn();
	}
	Log(LOG_INFO) << "[HIVEUA] event=DECIDED turn=" << save->getTurn() << " unit=" << unit->getId() << " squad=" << sq.id << " kind=" << kindName(sq) << " act=" << (int)action.type << " at=" << pos(unit->getPosition()) << " to=" << pos(action.target)
		<< " on_choice=" << (onChoice ? 1 : 0) << " changed=" << (onChoice && ch->second.changed ? 1 : 0) << " tu=" << unit->getTimeUnits();
}

void sideEnds(SavedBattleGame *save)
{
	if (mode() == 0 || hq.save != save || !hq.managesBattle) return;
	if (save->getSide() == FACTION_PLAYER)
	{
		// what came of the side's stand over the other side's turn: time units spent there can only be reactions, health lost is health lost. Counted, nothing more
		for (auto &e : hq.ledger)
		{
			auto sf = hq.squadOf.find(e.first);
			if (sf == hq.squadOf.end()) continue;
			for (auto *m : hq.squads[sf->second].members)
			{
				if (m->getId() != e.first || m->isOut()) continue;
				if (m->getTimeUnits() < e.second.first)
				{
					hq.squads[sf->second].cycle.reactions++;
					Log(LOG_INFO) << "[HIVEREACT] turn=" << save->getTurn() << " unit=" << e.first << " squad=" << sf->second << " task=" << TASK_NAME[hq.squads[sf->second].task] << " tu_spent=" << (e.second.first - m->getTimeUnits());
				}
				if (m->getHealth() < e.second.second)
				{
					hq.squads[sf->second].cycle.hurt++;
				}
			}
		}
		return;
	}
	if (save->getSide() != FACTION_HOSTILE || !hq.turnOpen) return;
	hq.turnOpen = false;
	logTurnEnd(save);
	int alive = 0, holdUnits = 0, searchUnits = 0, holdTu = 0, searchTu = 0, squads = 0, hold = 0, search = 0;
	hq.ledger.clear();
	for (auto &s : hq.squads)
	{
		if (!s.commander) continue;
		squads++;
		(s.task == T_SEARCH ? search : hold)++;
		int squadTu = 0, squadAlive = 0;
		for (auto *m : s.members)
		{
			if (!available(m)) continue;
			alive++;
			squadAlive++;
			hq.ledger[m->getId()] = std::make_pair(m->getTimeUnits(), m->getHealth());
			const int pc = m->getBaseStats()->tu > 0 ? 100 * m->getTimeUnits() / m->getBaseStats()->tu : 0;
			squadTu += pc;
			if (s.task == T_SEARCH)
			{
				searchUnits++;
				searchTu += pc;
			}
			else
			{
				holdUnits++;
				holdTu += pc;
			}
		}
		Log(LOG_INFO) << "[HIVESQUADTURN] turn=" << save->getTurn() << " squad=" << s.id << " commander=" << s.commander->getId() << " task=" << TASK_NAME[s.task] << " hold=" << HOLD_NAME[s.task == T_HOLD ? s.holdWhy : HW_NONE]
			<< " since=" << s.holdSince << " end=" << s.holdEnd << " idle=" << s.idle << " alive=" << squadAlive << " tuPct=" << (squadAlive ? squadTu / squadAlive : 0)
			<< " shots=" << s.cycle.shots << " saw=" << s.cycle.saw << " key=" << s.objective.key << " objective=" << (s.task == T_SEARCH && s.objective.valid ? pos(s.objective.pos) : "-");
	}
	for (auto &e : hq.orders)
	{
		Order &o = e.second;
		if (!o.unit || isTerminal(o) || o.state == COMPLETED) continue;
		o.moved = o.moved || !(o.unit->getPosition() == o.startAt);
		if (!available(o.unit))
		{
			setState(o, INTERRUPTED, "unit_out");
		}
		else if (o.stay && mode() == 2)
		{
			if (dist(o.unit->getPosition(), o.target) <= (o.task == T_HOLD ? HOLD_RADIUS : VISIT_RADIUS))
			{
				setState(o, COMPLETED, "held_turn");
			}
			else
			{
				setState(o, INTERRUPTED, "left_post");
			}
		}
		else if (mode() == 2 && nearPos(o.unit->getPosition(), o.target, ARRIVE_RADIUS))
		{
			setState(o, COMPLETED, "arrived");
		}
	}
	Log(LOG_INFO) << "[HIVETURN] turn=" << save->getTurn() << " alive=" << alive << " squads=" << squads << " hold=" << hold << " search=" << search
		<< " holdUnits=" << holdUnits << " holdTuPct=" << (holdUnits ? holdTu / holdUnits : 0) << " searchUnits=" << searchUnits << " searchTuPct=" << (searchUnits ? searchTu / searchUnits : 0)
		<< " created=" << hq.stat[CREATED] << " validated=" << hq.stat[VALIDATED] << " executing=" << hq.stat[EXECUTING] << " completed=" << hq.stat[COMPLETED]
		<< " blocked=" << hq.stat[BLOCKED] << " interrupted=" << hq.stat[INTERRUPTED] << " cancelled=" << hq.stat[CANCELLED]
		<< " thinks=" << hq.thinks << " thinkUs=" << hq.thinkNs / 1000;
	saveCheck(save);
}

}
}
