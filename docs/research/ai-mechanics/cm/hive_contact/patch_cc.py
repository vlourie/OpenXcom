"""CONTACT_COORDINATION_V0: the changes to HiveCommand.cpp of the isolated tree hive/cc/tree. Every replacement must match exactly once. Usage: patch_cc.py <HiveCommand.cpp>"""
import sys

path = sys.argv[1]
raw = open(path, "rb").read().decode("utf-8")
crlf = "\r\n" in raw
text = raw.replace("\r\n", "\n")
if "OXCE_AI_HIVE_CONTACT" in text:
    print("already patched")
    sys.exit(0)


def rep(old, new):
    global text
    assert text.count(old) == 1, (text.count(old), old[:80])
    text = text.replace(old, new)


rep('#include "Position.h"\n', '#include "Position.h"\n#include "TileEngine.h"\n')

rep('''const int HOLD_TURNS = 3, HOLD_IDLE = 2, HOLD_EXIT_RADIUS = 12, SEARCH_STALL = 2, RETARGET = 5;
''', '''const int HOLD_TURNS = 3, HOLD_IDLE = 2, HOLD_EXIT_RADIUS = 12, SEARCH_STALL = 2, RETARGET = 5;
// CONTACT_COORDINATION_V0 (bench, OXCE_AI_HIVE_CONTACT=1 over OXCE_AI_HIVE=2): what each squad does about a contact, decided once a side's turn before any unit's think
enum Role { R_NONE, R_ENGAGE, R_REINFORCE, R_MAINTAIN };
const char *const ROLE_NAME[] = { "NONE", "ENGAGE", "REINFORCE", "MAINTAIN" };
const int REINFORCE_MAX = 2, REINFORCE_TURNS = 3, REINFORCE_REST = 3, REINFORCE_ARMED = 2, REINFORCE_STALL = 2, FIRE_REACH = 20;
''')

rep('''	std::map<int, int> skip; // contact given up -> the turn it was last seen then: seen again, the conditions changed
};
''', '''	std::map<int, int> skip; // contact given up -> the turn it was last seen then: seen again, the conditions changed
	Role role = R_NONE;
	int roleContact = -1, roleSince = -1, roleUntil = -1, restUntil = -1, roleShots = 0, roleStall = 0, roleBest = 1000000;
};
''')

rep('''	std::map<int, Field> fields;
	std::vector<int> flood, floodPrev;
''', '''	std::map<int, Field> fields;
	std::map<std::pair<long long, int>, bool> lines; // this plan: cell and eye height, contact -> a line of fire
	std::vector<int> flood, floodPrev;
''')

rep('''Hq hq;
SavedBattleGame *pendingSave = 0;
const char *pendingOrigin = "spawn";
''', '''Hq hq;
SavedBattleGame *pendingSave = 0;
const char *pendingOrigin = "spawn";

bool coord()
{
	static const bool on = (int)AiProbe::param("OXCE_AI_HIVE", 0) == 2 && (int)AiProbe::param("OXCE_AI_HIVE_CONTACT", 0) == 1;
	return on;
}

bool onContact(const Squad &sq)
{
	return sq.role == R_ENGAGE || sq.role == R_REINFORCE;
}
''')

# the units of a squad on a contact go to a place to fire from
rep('''/// The order of one unit, by what it really can do. Nothing it can walk to serves the task: it stands, saying why, and the next plan asks again.
void planUnit(Squad &sq, BattleUnit *u, SavedBattleGame *save)
{
''', '''/// The fewest time units a shot of the weapon in hand takes; 0: nothing to fire with, or nothing to fire.
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

/// A line of fire from this cell to the contact as it stands in sight now, asked as findFirePoint asks it: this unit's eye over that tile; the contact is on its real tile.
bool lineFrom(SavedBattleGame *save, BattleUnit *u, const Position &p, const Contact &c)
{
	const int eye = u->getHeight() + u->getFloatHeight();
	const std::pair<long long, int> key(save->getTileIndex(p) * 256LL + eye, c.id);
	const auto known = hq.lines.find(key);
	if (known != hq.lines.end()) return known->second;
	Tile *from = save->getTile(p);
	Tile *to = save->getTile(c.pos);
	bool line = false;
	if (from && to && to->getUnit())
	{
		Position origin = p.toVoxel() + Position(8, 8, eye - from->getTerrainLevel() - 4);
		Position voxel;
		line = save->getTileEngine()->canTargetUnit(&origin, to, &voxel, u, false);
	}
	hq.lines[key] = line;
	return line;
}

/// Is this cell open to a contact in sight this turn?
bool exposedAt(SavedBattleGame *save, BattleUnit *u, const Position &p)
{
	for (const auto &e : hq.contacts)
	{
		const Contact &c = e.second;
		if (c.seenTurn == save->getTurn() && c.cls == KNOWN && dist(p, c.pos) <= FIRE_REACH && lineFrom(save, u, p, c)) return true;
	}
	return false;
}

/// Where this unit goes this turn about this contact: a node with a line to it and the time units for a shot left there; else a node nearer it and open to no contact in sight, so
/// that nobody comes out under known fire with no shot to give. Only what it can walk to this turn: the next plan looks again. 0 if neither.
Node *contactNode(SavedBattleGame *save, BattleUnit *u, const Contact &c, bool &fire)
{
	const Field &f = fieldOf(save, u);
	const std::pair<int, int> now = conditionsOf(save, u, f);
	const auto memo = hq.blocked.find(u->getId());
	const int shot = shotCost(u), tu = u->getTimeUnits(), here = dist(u->getPosition(), c.pos);
	Node *bestFire = 0, *bestWay = 0;
	int fireScore = 2000000000, wayScore = 2000000000;
	for (auto *n : *save->getNodes())
	{
		if (n->isDummy() || n->getID() >= (int)f.node.size()) continue;
		const int cost = f.node[n->getID()];
		if (cost <= 0 || cost > tu || nearPos(u->getPosition(), n->getPosition(), ARRIVE_RADIUS)) continue;
		if (memo != hq.blocked.end())
		{
			const auto m = memo->second.find(n->getID());
			if (m != memo->second.end() && m->second == now) continue;
		}
		const int d = dist(c.pos, n->getPosition());
		if (shot > 0 && cost + shot <= tu && d <= FIRE_REACH && cost < fireScore && lineFrom(save, u, n->getPosition(), c) && legalNode(save, u, n))
		{
			bestFire = n;
			fireScore = cost;
			continue;
		}
		const int way = 100 * d + cost;
		if (d < here && way < wayScore && !exposedAt(save, u, n->getPosition()) && legalNode(save, u, n))
		{
			bestWay = n;
			wayScore = way;
		}
	}
	fire = bestFire != 0;
	return bestFire ? bestFire : bestWay;
}

bool seesEnemy(BattleUnit *u)
{
	for (auto *v : *u->getVisibleUnits())
	{
		if (!v->isOut() && v->getFaction() == FACTION_PLAYER) return true;
	}
	return false;
}

/// One unit of a squad on a contact. One who sees an enemy gets no order: its fight is its own think's. The rest get the turn's place to help from.
void planContactUnit(Squad &sq, BattleUnit *u, SavedBattleGame *save)
{
	const int turn = save->getTurn();
	if (seesEnemy(u))
	{
		auto f = hq.orders.find(u->getId());
		if (f != hq.orders.end() && f->second.unit && !isTerminal(f->second) && f->second.state != COMPLETED)
		{
			setState(f->second, CANCELLED, "sees_enemy");
		}
		Log(LOG_INFO) << "[HIVECC] event=ORDER turn=" << turn << " squad=" << sq.id << " role=" << ROLE_NAME[sq.role] << " unit=" << u->getId() << " kind=own_fight at=" << pos(u->getPosition());
		return;
	}
	const auto c = hq.contacts.find(sq.roleContact);
	if (c == hq.contacts.end()) return;
	const char *kind = "no_node";
	int cost = -1;
	if (shotCost(u) > 0 && dist(u->getPosition(), c->second.pos) <= FIRE_REACH && lineFrom(save, u, u->getPosition(), c->second))
	{
		kind = "in_place";
		newOrder(sq, u, true, 0, u->getPosition(), "contact_in_place");
	}
	else
	{
		bool fire = false;
		Node *n = contactNode(save, u, c->second, fire);
		if (n)
		{
			kind = fire ? "fire" : "approach";
			cost = fieldOf(save, u).node[n->getID()];
			orderWalk(sq, u, n, fire ? "contact_fire" : "contact_approach", save);
		}
		else
		{
			// nothing serves from where it stands: no order and its own free choice; standing with its time units helps nobody
			auto f = hq.orders.find(u->getId());
			if (f != hq.orders.end() && f->second.unit && !isTerminal(f->second) && f->second.state != COMPLETED)
			{
				setState(f->second, CANCELLED, "contact_no_node");
			}
			Log(LOG_INFO) << "[HIVECC] event=ORDER turn=" << turn << " squad=" << sq.id << " role=" << ROLE_NAME[sq.role] << " unit=" << u->getId() << " kind=" << kind << " contact=" << c->first << " at=" << pos(u->getPosition());
			return;
		}
	}
	const Order &o = hq.orders[u->getId()];
	Log(LOG_INFO) << "[HIVECC] event=ORDER turn=" << turn << " squad=" << sq.id << " role=" << ROLE_NAME[sq.role] << " unit=" << u->getId() << " kind=" << kind << " order=" << o.id << " contact=" << c->first
		<< " at=" << pos(u->getPosition()) << " target=" << pos(o.target) << " cost=" << cost << " tu=" << u->getTimeUnits() << " shot=" << shotCost(u) << " until=" << sq.roleUntil;
}

/// The order of one unit, by what it really can do. Nothing it can walk to serves the task: it stands, saying why, and the next plan asks again.
void planUnit(Squad &sq, BattleUnit *u, SavedBattleGame *save)
{
	if (coord() && onContact(sq))
	{
		planContactUnit(sq, u, save);
		return;
	}
''')

rep('''void planSquad(Squad &sq, SavedBattleGame *save)
{
	if (!sq.commander) return;
	if (sq.task == T_SEARCH)
''', '''void planSquad(Squad &sq, SavedBattleGame *save)
{
	if (!sq.commander) return;
	if (coord() && onContact(sq))
	{
		// the turn's place: the contact has moved since the last plan, and the time units are new
		for (auto *u : sq.members)
		{
			if (available(u) && !unmanaged(u))
			{
				planContactUnit(sq, u, save);
			}
		}
		return;
	}
	if (sq.task == T_SEARCH)
''')

# no contact is anybody's objective but by the decision of the side
rep('''	std::vector<const Contact*> candidates;
	if (sq.objective.valid && sq.objective.contact)
	{
''', '''	std::vector<const Contact*> candidates;
	if (!coord() && sq.objective.valid && sq.objective.contact)
	{
''')
rep('''	for (auto &e : hq.contacts)
	{
		const Contact &c = e.second;
		if (!usable(c) || onContact[c.id] >= CONTACT_SQUADS) continue;
''', '''	for (auto &e : hq.contacts)
	{
		const Contact &c = e.second;
		if (coord() || !usable(c) || onContact[c.id] >= CONTACT_SQUADS) continue;
''')
rep('''	std::map<int, int> onContact;
	for (auto &o : hq.squads)
	{
		if (o.id != sq.id && o.task == T_SEARCH && o.objective.valid && o.objective.contact)
		{
			onContact[o.objective.contactId]++;
		}
	}
''', '''	std::map<int, int> squadsOn;
	for (auto &o : hq.squads)
	{
		if (o.id != sq.id && o.task == T_SEARCH && o.objective.valid && o.objective.contact)
		{
			squadsOn[o.objective.contactId]++;
		}
	}
''')
rep("if (coord() || !usable(c) || onContact[c.id] >= CONTACT_SQUADS) continue;", "if (coord() || !usable(c) || squadsOn[c.id] >= CONTACT_SQUADS) continue;")

rep('''void objectiveReached(Squad &sq, SavedBattleGame *save)
{
	if (sq.task != T_SEARCH || !sq.objective.valid || !sq.commander) return;
''', '''void objectiveReached(Squad &sq, SavedBattleGame *save)
{
	if (sq.task != T_SEARCH || !sq.objective.valid || !sq.commander || (coord() && onContact(sq))) return;
''')

rep('''			threat = threat || (contactAlive(e.second, sq, turn) && dist(e.second.pos, sq.anchor) <= HOLD_EXIT_RADIUS);
''', '''			threat = threat || (!coord() && contactAlive(e.second, sq, turn) && dist(e.second.pos, sq.anchor) <= HOLD_EXIT_RADIUS);
''')
rep('''	else if (sq.objective.valid)
	{
		int best = 1000000;
		for (auto *m : sq.members)
		{
			if (available(m) && !unmanaged(m) && !isLocked(m)) best = std::min(best, dist(m->getPosition(), sq.objective.pos));
''', '''	else if (sq.objective.valid && !(coord() && onContact(sq)))
	{
		int best = 1000000;
		for (auto *m : sq.members)
		{
			if (available(m) && !unmanaged(m) && !isLocked(m)) best = std::min(best, dist(m->getPosition(), sq.objective.pos));
''')
rep('''<< " hurt=" << ev.hurt << " saw=" << ev.saw << " idle=" << sq.idle << " noProgress=" << sq.noProgress << " best=" << sq.bestDist << " result=" << result;
}
''', '''<< " hurt=" << ev.hurt << " saw=" << ev.saw << " idle=" << sq.idle << " noProgress=" << sq.noProgress << " best=" << sq.bestDist << " result=" << result;
}

/// One squad's part in the decision. A squad going onto a contact takes it as its SEARCH objective; going off, its own sector's search is what stays.
void setRole(Squad &sq, Role role, int contact, const char *why, SavedBattleGame *save)
{
	const int turn = save->getTurn();
	if (sq.role == role && sq.roleContact == contact) return;
	Log(LOG_INFO) << "[HIVECC] event=ASSIGN turn=" << turn << " squad=" << sq.id << " commander=" << sq.commander->getId() << " from=" << ROLE_NAME[sq.role] << " to=" << ROLE_NAME[role] << " contact=" << contact
		<< " why=" << why << " task=" << TASK_NAME[sq.task] << " hold=" << HOLD_NAME[sq.holdWhy] << " objective=" << (sq.objective.valid ? pos(sq.objective.pos) : "-");
	const bool newStay = sq.role != role;
	if (role == R_ENGAGE || role == R_REINFORCE)
	{
		const Contact &c = hq.contacts[contact];
		sq.task = T_SEARCH;
		sq.holdWhy = HW_NONE;
		sq.objective = Objective();
		sq.objective.valid = true;
		sq.objective.contact = true;
		sq.objective.contactId = contact;
		sq.objective.pos = sq.objective.keyPos = c.pos;
		sq.objective.since = turn;
		sq.objective.key = hq.nextKey++;
		sq.noProgress = 0;
		sq.bestDist = 1000000;
		Log(LOG_INFO) << "[HIVETASK] turn=" << turn << " squad=" << sq.id << " task=SEARCH commander=" << sq.commander->getId() << " key=" << sq.objective.key
			<< " objective=" << pos(sq.objective.pos) << " kind=contact contact=" << contact << " ttl=" << contactTtl(sq) << " role=" << ROLE_NAME[role];
		sq.roleStall = 0;
		sq.roleBest = 1000000;
		if (newStay)
		{
			sq.roleSince = turn;
			sq.roleUntil = role == R_REINFORCE ? turn + REINFORCE_TURNS : -1;
			sq.roleShots = 0;
		}
	}
	else if (onContact(sq))
	{
		sq.objective.valid = false;
		sq.noProgress = 0;
		sq.roleSince = sq.roleUntil = -1;
	}
	sq.role = role;
	sq.roleContact = contact;
}

/// Once a side's turn, before the squads plan: who fights, who helps and who stays on its own task. Only what a living unit of ours has in sight now counts; the actions stay the units'.
void coordinate(SavedBattleGame *save)
{
	const int turn = save->getTurn();
	std::map<int, std::set<int> > sees, seers;
	for (auto &s : hq.squads)
	{
		if (!s.commander) continue;
		for (auto *m : s.members)
		{
			if (!available(m) || unmanaged(m)) continue;
			for (auto *v : *m->getVisibleUnits())
			{
				if (v->isOut() || v->getFaction() != FACTION_PLAYER) continue;
				sees[s.id].insert(v->getId());
				seers[v->getId()].insert(s.id);
			}
		}
	}
	for (auto &e : seers)
	{
		const auto c = hq.contacts.find(e.first);
		if (c == hq.contacts.end()) continue;
		std::ostringstream by;
		for (int q : e.second) by << q << ':';
		Log(LOG_INFO) << "[HIVECC] event=CONTACT turn=" << turn << " target=" << e.first << " pos=" << pos(c->second.pos) << " cls=" << KNOW_NAME[c->second.cls] << " seen_by=" << by.str();
	}
	const auto known = [turn](int id)
	{
		const auto c = hq.contacts.find(id);
		return c != hq.contacts.end() && c->second.cls == KNOWN && c->second.seenTurn == turn;
	};
	for (auto &s : hq.squads)
	{
		if (!s.commander) continue;
		int alive = 0;
		for (auto *m : s.members)
		{
			alive += available(m);
		}
		if (s.role != R_NONE && (s.role != R_MAINTAIN || s.cycle.shots > 0))
		{
			Log(LOG_INFO) << "[HIVECC] event=FEEDBACK turn=" << turn << " squad=" << s.id << " role=" << ROLE_NAME[s.role] << " contact=" << s.roleContact << " shots=" << s.cycle.shots << " reactions=" << s.cycle.reactions
				<< " hurt=" << s.cycle.hurt << " saw=" << s.cycle.saw << " alive=" << alive << " dist=" << (s.roleContact != -1 && hq.contacts.count(s.roleContact) ? squadDist(s, hq.contacts[s.roleContact].pos) : -1);
		}
		// a squad with an enemy in sight is in a fight whatever it was told; a guard's post stands while the enemy is far from it, its units fire by their own think
		int nearest = -1, nearestD = 1000000;
		for (int id : sees[s.id])
		{
			const auto c = hq.contacts.find(id);
			if (c == hq.contacts.end()) continue;
			const int d = dist(s.commander->getPosition(), c->second.pos);
			if (d < nearestD)
			{
				nearest = id;
				nearestD = d;
			}
		}
		if (nearest != -1 && s.task != T_HOLD)
		{
			setRole(s, R_ENGAGE, s.role == R_ENGAGE && sees[s.id].count(s.roleContact) ? s.roleContact : nearest, s.role == R_REINFORCE ? "reinforce_now_sees" : "sees", save);
			continue;
		}
		// a guard reviews its task only for an enemy in sight this turn near its post
		if (s.task == T_HOLD)
		{
			int threat = -1, threatD = 1000000;
			for (auto &e : hq.contacts)
			{
				const int d = dist(e.second.pos, s.anchor);
				if (known(e.first) && d <= HOLD_EXIT_RADIUS && d < threatD)
				{
					threat = e.first;
					threatD = d;
				}
			}
			if (threat != -1)
			{
				setRole(s, R_ENGAGE, threat, "threat_near", save);
				continue;
			}
		}
		if (s.role == R_ENGAGE)
		{
			setRole(s, R_MAINTAIN, -1, "engage_over_nothing_in_sight", save);
		}
		else if (s.role == R_REINFORCE)
		{
			s.roleShots += s.cycle.shots;
			const char *end = 0;
			if (turn > s.roleUntil)
			{
				end = "term_over";
			}
			else if (!known(s.roleContact))
			{
				// out of sight: another in sight within reach that no other helper is on; the term stays
				int next = -1, nextD = CONTACT_REACH + 1;
				for (auto &e : seers)
				{
					bool taken = false;
					for (auto &o : hq.squads)
					{
						taken = taken || (o.id != s.id && o.commander && o.role == R_REINFORCE && o.roleContact == e.first);
					}
					const int d = known(e.first) ? squadDist(s, hq.contacts[e.first].pos) : CONTACT_REACH + 1;
					if (!taken && d < nextD)
					{
						next = e.first;
						nextD = d;
					}
				}
				if (next != -1)
				{
					setRole(s, R_REINFORCE, next, "contact_not_in_sight_next", save);
				}
				else
				{
					end = "contact_not_in_sight";
				}
			}
			else
			{
				const int d = squadDist(s, hq.contacts[s.roleContact].pos);
				if (d < s.roleBest || s.cycle.shots > 0)
				{
					s.roleBest = std::min(s.roleBest, d);
					s.roleStall = 0;
				}
				else if (++s.roleStall >= REINFORCE_STALL)
				{
					end = "no_progress";
				}
			}
			if (end)
			{
				if (s.roleShots == 0)
				{
					s.restUntil = turn + REINFORCE_REST;
				}
				setRole(s, R_MAINTAIN, -1, end, save);
			}
		}
		else if (s.role == R_NONE)
		{
			setRole(s, R_MAINTAIN, -1, "own_task", save);
		}
	}
	// who may help: searching its sector, no enemy in sight, armed; a guard stays a guard. No more than half of those not fighting, one to a contact
	std::set<int> helped;
	int helpers = 0, free = 0, fighting = 0;
	for (auto &s : hq.squads)
	{
		if (!s.commander) continue;
		fighting += s.role == R_ENGAGE;
		free += s.role != R_ENGAGE;
		if (s.role == R_REINFORCE)
		{
			helpers++;
			helped.insert(s.roleContact);
		}
	}
	const int cap = std::min(REINFORCE_MAX, free / 2);
	std::vector<std::pair<std::pair<int, int>, int> > pairs; // (distance, squad), contact
	for (auto &s : hq.squads)
	{
		if (!s.commander || s.role != R_MAINTAIN || s.task != T_SEARCH || s.restUntil > turn) continue;
		int armed = 0;
		for (auto *m : s.members)
		{
			armed += available(m) && !unmanaged(m) && shotCost(m) > 0;
		}
		if (armed < REINFORCE_ARMED) continue;
		for (auto &e : seers)
		{
			if (!known(e.first)) continue;
			const int d = squadDist(s, hq.contacts[e.first].pos);
			if (d <= CONTACT_REACH)
			{
				pairs.push_back(std::make_pair(std::make_pair(d, s.id), e.first));
			}
		}
	}
	std::stable_sort(pairs.begin(), pairs.end());
	for (auto &p : pairs)
	{
		if (helpers >= cap) break;
		Squad &s = hq.squads[p.first.second];
		if (s.role != R_MAINTAIN || helped.count(p.second)) continue;
		int able = 0;
		for (auto *m : s.members)
		{
			if (!available(m) || unmanaged(m) || shotCost(m) == 0) continue;
			bool fire = false;
			able += contactNode(save, m, hq.contacts[p.second], fire) != 0;
		}
		Log(LOG_INFO) << "[HIVECC] event=REINFORCE_CHECK turn=" << turn << " squad=" << s.id << " contact=" << p.second << " dist=" << p.first.first << " able=" << able;
		if (able == 0) continue;
		setRole(s, R_REINFORCE, p.second, "nearest_free_with_route", save);
		helped.insert(p.second);
		helpers++;
	}
	// the objective of those on a contact follows it where it is seen
	std::ostringstream parts;
	for (auto &s : hq.squads)
	{
		if (!s.commander) continue;
		parts << ' ' << s.id << '=' << ROLE_NAME[s.role] << ':' << s.roleContact;
		if (onContact(s) && hq.contacts.count(s.roleContact))
		{
			s.objective.pos = hq.contacts[s.roleContact].pos;
		}
	}
	Log(LOG_INFO) << "[HIVECC] event=DECISION turn=" << turn << " in_sight=" << seers.size() << " fighting=" << fighting << " free=" << free << " cap=" << cap << " helpers=" << helpers << " squads:" << parts.str();
}
''')

rep('''	hq.fields.clear();
	hq.floodUnit = -1;
	hq.thinkNs = 0;
''', '''	hq.fields.clear();
	hq.lines.clear();
	hq.floodUnit = -1;
	hq.thinkNs = 0;
''')
rep('''	for (auto &s : hq.squads)
	{
		if (s.commander)
		{
			reviewSquad(s, save);
			planSquad(s, save);
		}
	}
	const long long us =''', '''	if (coord())
	{
		coordinate(save);
	}
	for (auto &s : hq.squads)
	{
		if (s.commander)
		{
			reviewSquad(s, save);
			planSquad(s, save);
		}
	}
	const long long us =''')

# the save
rep('''			s << ";K," << q.id << ',' << k.first << ',' << k.second;
		}
''', '''			s << ";K," << q.id << ',' << k.first << ',' << k.second;
		}
		if (q.role != R_NONE)
		{
			s << ";R," << q.id << ',' << (int)q.role << ',' << q.roleContact << ',' << q.roleSince << ',' << q.roleUntil << ',' << q.restUntil << ',' << q.roleShots << ',' << q.roleStall << ',' << q.roleBest;
		}
''')
rep('''			else if (type == "O")
			{
				Order o;
''', '''			else if (type == "R")
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
			}
			else if (type == "O")
			{
				Order o;
''')

# what the units did
rep('''	auto sf = hq.squadOf.find(unit->getId());
	if (sf != hq.squadOf.end() && isAttack(action.type))
	{
		hq.squads[sf->second].cycle.shots++;
	}
''', '''	auto sf = hq.squadOf.find(unit->getId());
	if (sf != hq.squadOf.end() && isAttack(action.type))
	{
		hq.squads[sf->second].cycle.shots++;
	}
	if (coord() && sf != hq.squadOf.end() && action.type != BA_NONE)
	{
		const auto of = hq.orders.find(unit->getId());
		const bool onOrder = of != hq.orders.end() && of->second.unit && !of->second.stay && action.target == of->second.target;
		if (isAttack(action.type) || onOrder)
		{
			Tile *t = save->getTile(action.target);
			Log(LOG_INFO) << "[HIVECC] event=EXEC turn=" << save->getTurn() << " squad=" << sf->second << " role=" << ROLE_NAME[hq.squads[sf->second].role] << " unit=" << unit->getId() << " act=" << (int)action.type
				<< " at=" << pos(unit->getPosition()) << " to=" << pos(action.target) << " aim=" << (t && t->getUnit() ? t->getUnit()->getId() : -1) << " on_order=" << (onOrder ? of->second.id : -1)
				<< " why=" << (onOrder ? of->second.why : "own") << " tu=" << unit->getTimeUnits();
		}
	}
''')

out = text.replace("\n", "\r\n") if crlf else text
open(path, "wb").write(out.encode("utf-8"))
print("patched")
