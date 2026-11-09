"""REINFORCEMENT INTELLIGENCE V0: the gate over hive/cc/tree in hive/ri/tree. Only HiveCommand.cpp; every path is behind OXCE_AI_HIVE_REINF=1. Each replace must hit exactly once."""
from pathlib import Path

T = Path(__file__).parent / "tree" / "src" / "Battlescape" / "HiveCommand.cpp"
raw = T.read_bytes().decode("utf-8")
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")


def rep(old, new):
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"{n} hits for: {old[:80]}")
    s = s.replace(old, new)


# the flag; a REINFORCE squad under the gate keeps its own search, only its fit units leave it
rep("""bool onContact(const Squad &sq)
{
	return sq.role == R_ENGAGE || sq.role == R_REINFORCE;
}
""", """/// REINFORCEMENT_ELIGIBILITY_GATE (bench): a squad helps only with those of its units that can fire on the contact this turn.
bool gate()
{
	static const bool on = coord() && (int)AiProbe::param("OXCE_AI_HIVE_REINF", 0) == 1;
	return on;
}

bool onContact(const Squad &sq)
{
	return sq.role == R_ENGAGE || (sq.role == R_REINFORCE && !gate());
}
""")

rep("int roleContact = -1, roleSince = -1, roleUntil = -1, restUntil = -1, roleShots = 0, roleStall = 0, roleBest = 1000000;",
    "int roleContact = -1, roleSince = -1, roleUntil = -1, restUntil = -1, roleShots = 0, roleStall = 0, roleBest = 1000000, helpHits = 0;")

# what a unit can do about a contact
rep("""bool seesEnemy(BattleUnit *u)
{""", """/// Is this order a helper's: a place to fire on the contact from?
bool isHelpOrder(const Order &o)
{
	return o.why == "contact_fire" || o.why == "contact_in_place";
}

/// Can this unit fire on this contact this turn, on what its side knows now: a weapon that shoots with ammunition, the contact within its reach, and a line from where it stands
/// or from a node it can walk to with a shot's time units left. A line is the chance to shoot as the unit's own think would ask it, not a promise. Says why; node 0 is from where it stands.
const char *helpCheck(SavedBattleGame *save, BattleUnit *u, const Contact &c, Node *&node)
{
	node = 0;
	if (shotCost(u) == 0) return "no_shot";
	const int reach = std::min(FIRE_REACH, u->getMainHandWeapon(false)->getRules()->getMaxRange());
	const int here = dist(u->getPosition(), c.pos);
	if (here <= reach && lineFrom(save, u, u->getPosition(), c)) return "in_place";
	bool fire = false;
	Node *n = contactNode(save, u, c, fire);
	if (!fire) return n ? "no_fire_node" : "no_node";
	if (dist(n->getPosition(), c.pos) > reach) return "out_of_range";
	node = n;
	return "fire";
}

bool helpFit(const char *why)
{
	return why[0] == 'i' || why[0] == 'f';
}

/// One unit of a helping squad: true if it has got a helper's order. An order of the last help left on anyone else is over.
bool planHelper(Squad &sq, BattleUnit *u, SavedBattleGame *save)
{
	const int turn = save->getTurn();
	const auto c = hq.contacts.find(sq.roleContact);
	auto f = hq.orders.find(u->getId());
	// a fight's orders carry the same name; those end with the fight's objective, by the squad's own plan
	const bool last = f != hq.orders.end() && f->second.unit && !isTerminal(f->second) && isHelpOrder(f->second) && sq.objective.valid && f->second.objectiveKey == sq.objective.key;
	Node *n = 0;
	const char *why = sq.role != R_REINFORCE || c == hq.contacts.end() ? "not_helping" : helpCheck(save, u, c->second, n);
	if (!helpFit(why))
	{
		if (last)
		{
			setState(f->second, CANCELLED, "help_over");
			Log(LOG_INFO) << "[HIVECC] event=HELP_RESULT turn=" << turn << " squad=" << sq.id << " unit=" << u->getId() << " kind=CANCEL why=" << why << " contact=" << sq.roleContact;
		}
		return false;
	}
	int cost = -1;
	if (n)
	{
		cost = fieldOf(save, u).node[n->getID()];
		orderWalk(sq, u, n, "contact_fire", save);
	}
	else
	{
		newOrder(sq, u, true, 0, u->getPosition(), "contact_in_place");
	}
	const Order &o = hq.orders[u->getId()];
	Log(LOG_INFO) << "[HIVECC] event=ORDER turn=" << turn << " squad=" << sq.id << " role=" << ROLE_NAME[sq.role] << " unit=" << u->getId() << " kind=" << why << " order=" << o.id << " contact=" << c->first
		<< " at=" << pos(u->getPosition()) << " target=" << pos(o.target) << " cost=" << cost << " tu=" << u->getTimeUnits() << " shot=" << shotCost(u) << " until=" << sq.roleUntil;
	return true;
}

bool seesEnemy(BattleUnit *u)
{""")

# the helpers over the squad's own orders
rep("""		if (!available(u) || unmanaged(u)) continue;
		auto f = hq.orders.find(u->getId());
		if (!orderHolds(f == hq.orders.end() ? 0 : &f->second, sq))
""", """		if (!available(u) || unmanaged(u)) continue;
		if (gate() && planHelper(sq, u, save)) continue;
		auto f = hq.orders.find(u->getId());
		if (!orderHolds(f == hq.orders.end() ? 0 : &f->second, sq))
""")

# the role: a helping squad's objective stays
rep("""	if (role == R_ENGAGE || role == R_REINFORCE)
	{
		const Contact &c = hq.contacts[contact];
		sq.task = T_SEARCH;""", """	if (gate() && role == R_REINFORCE)
	{
		sq.roleStall = 0;
		sq.helpHits = 0;
		sq.roleSince = turn;
		sq.roleUntil = turn + REINFORCE_TURNS;
		sq.roleShots = 0;
	}
	else if (role == R_ENGAGE || role == R_REINFORCE)
	{
		const Contact &c = hq.contacts[contact];
		sq.task = T_SEARCH;""")

# the review of a helping squad
rep("""			s.roleShots += s.cycle.shots;
			const char *end = 0;
			if (turn > s.roleUntil)
			{
				end = "term_over";
			}
			else if (!known(s.roleContact))
			{""", """			s.roleShots += gate() ? s.helpHits : s.cycle.shots;
			const char *end = 0;
			if (turn > s.roleUntil)
			{
				end = "term_over";
			}
			else if (gate())
			{
				// what counts is an attack on the contact, not a walk toward it. The contact gone, the help is over: another one goes through the same check below, not by itself
				int fit = 0;
				if (known(s.roleContact))
				{
					for (auto *m : s.members)
					{
						Node *n = 0;
						fit += available(m) && !unmanaged(m) && helpFit(helpCheck(save, m, hq.contacts[s.roleContact], n));
					}
				}
				s.roleStall = s.helpHits > 0 ? 0 : s.roleStall + 1;
				if (!known(s.roleContact))
				{
					end = "contact_not_in_sight";
				}
				else if (fit == 0)
				{
					end = "no_eligible";
				}
				else if (s.roleStall >= REINFORCE_STALL)
				{
					end = "no_useful_attack";
				}
				s.helpHits = 0;
			}
			else if (!known(s.roleContact))
			{""")

# the choice: only the fit count
rep("""		if (s.role != R_MAINTAIN || helped.count(p.second)) continue;
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
""", """		if (s.role != R_MAINTAIN || helped.count(p.second)) continue;
		int able = 0, others = 0;
		std::ostringstream whys;
		for (auto *m : s.members)
		{
			if (gate())
			{
				if (!available(m) || unmanaged(m)) continue;
				Node *n = 0;
				const char *why = helpCheck(save, m, hq.contacts[p.second], n);
				whys << m->getId() << ':' << why << ',';
				if (helpFit(why)) able++;
				else others++;
				continue;
			}
			if (!available(m) || unmanaged(m) || shotCost(m) == 0) continue;
			bool fire = false;
			able += contactNode(save, m, hq.contacts[p.second], fire) != 0;
		}
		Log(LOG_INFO) << "[HIVECC] event=REINFORCE_CHECK turn=" << turn << " squad=" << s.id << " contact=" << p.second << " dist=" << p.first.first << " able=" << able;
		if (gate())
		{
			Log(LOG_INFO) << "[HIVECC] event=ELIGIBILITY turn=" << turn << " squad=" << s.id << " contact=" << p.second << " fit=" << able << " stay_on_task=" << others
				<< " objective_dist=" << (s.objective.valid ? dist(s.commander->getPosition(), s.objective.pos) : -1) << " units=" << whys.str();
			checked[p.second]++;
		}
		if (able == 0) continue;
		setRole(s, R_REINFORCE, p.second, gate() ? "fit_to_fire" : "nearest_free_with_route", save);
""")
rep("""	std::stable_sort(pairs.begin(), pairs.end());
	for (auto &p : pairs)
	{
		if (helpers >= cap) break;
""", """	std::stable_sort(pairs.begin(), pairs.end());
	std::map<int, int> checked;
	for (auto &p : pairs)
	{
		if (helpers >= cap) break;
""")
# no helper for a contact
rep("""	// the objective of those on a contact follows it where it is seen
	std::ostringstream parts;""", """	if (gate() && helpers < cap)
	{
		for (auto &e : seers)
		{
			if (!known(e.first) || helped.count(e.first)) continue;
			int fights = 0;
			for (auto &s : hq.squads)
			{
				fights += s.commander && s.role == R_ENGAGE && s.roleContact == e.first;
			}
			Log(LOG_INFO) << "[HIVECC] event=NO_VIABLE_REINFORCEMENT turn=" << turn << " contact=" << e.first << " checked=" << checked[e.first] << " engaged_by=" << fights;
		}
	}
	// the objective of those on a contact follows it where it is seen
	std::ostringstream parts;""")

# the save
rep("""<< q.roleShots << ',' << q.roleStall << ',' << q.roleBest;
""", """<< q.roleShots << ',' << q.roleStall << ',' << q.roleBest;
			if (gate()) s << ',' << q.helpHits;
""")
rep("""				q.roleBest = x.num();
""", """				q.roleBest = x.num();
				if (gate()) q.helpHits = x.num();
""")

# the order in the unit's think: done or not possible, the unit is its own think's again; it never stops on a hold
rep("""	Order *o = &f->second;
	if (o->stay || o->state == COMPLETED) return PO_HOLD;
	if (nearPos(unit->getPosition(), o->target, ARRIVE_RADIUS))
	{
		setState(*o, COMPLETED, "arrived");
		return PO_HOLD;
	}
	if (o->pauseTurn == save->getTurn())
	{
		return PO_HOLD;
	}
""", """	Order *o = &f->second;
	const auto hs = hq.squadOf.find(unit->getId());
	const bool help = gate() && isHelpOrder(*o) && hs != hq.squadOf.end() && hq.squads[hs->second].role == R_REINFORCE;
	if (help && (o->stay || o->state == COMPLETED)) return PO_NONE;
	if (o->stay || o->state == COMPLETED) return PO_HOLD;
	if (nearPos(unit->getPosition(), o->target, ARRIVE_RADIUS))
	{
		setState(*o, COMPLETED, "arrived");
		if (help)
		{
			const auto c = hq.contacts.find(hq.squads[hs->second].roleContact);
			Log(LOG_INFO) << "[HIVECC] event=HELP_RESULT turn=" << save->getTurn() << " squad=" << o->squad << " unit=" << unit->getId() << " kind=POSITION contact=" << (c == hq.contacts.end() ? -1 : c->first)
				<< " line=" << (c != hq.contacts.end() && lineFrom(save, unit, unit->getPosition(), c->second) ? 1 : 0) << " tu=" << unit->getTimeUnits() << " shot=" << shotCost(unit);
			return PO_NONE;
		}
		return PO_HOLD;
	}
	if (o->pauseTurn == save->getTurn())
	{
		return help ? PO_NONE : PO_HOLD;
	}
""")
rep("""			note << "path_now=" << cost << " plan=" << o->pathTu;
			logOrder(*o, note.str().c_str());
			break;
""", """			note << "path_now=" << cost << " plan=" << o->pathTu;
			logOrder(*o, note.str().c_str());
			if (help && isHelpOrder(*o) && cost + shotCost(unit) > unit->getTimeUnits())
			{
				// the way has grown since the plan: no shot at the end of it, and the walk would only take the unit off
				setState(*o, CANCELLED, "help_path_over_tu");
				Log(LOG_INFO) << "[HIVECC] event=HELP_RESULT turn=" << save->getTurn() << " squad=" << o->squad << " unit=" << unit->getId() << " kind=CANCEL why=path_over_tu path=" << cost << " plan=" << o->pathTu << " tu=" << unit->getTimeUnits();
				return PO_NONE;
			}
			break;
""")

# an attack on the contact
rep("""	if (sf != hq.squadOf.end() && isAttack(action.type))
	{
		hq.squads[sf->second].cycle.shots++;
	}
""", """	if (sf != hq.squadOf.end() && isAttack(action.type))
	{
		hq.squads[sf->second].cycle.shots++;
		Squad &hs = hq.squads[sf->second];
		if (gate() && hs.role == R_REINFORCE)
		{
			Tile *ht = save->getTile(action.target);
			if (ht && ht->getUnit() && ht->getUnit()->getId() == hs.roleContact)
			{
				hs.helpHits++;
				Log(LOG_INFO) << "[HIVECC] event=HELP_RESULT turn=" << save->getTurn() << " squad=" << hs.id << " unit=" << unit->getId() << " kind=ATTACK contact=" << hs.roleContact << " at=" << pos(unit->getPosition()) << " act=" << (int)action.type;
			}
		}
	}
""")

T.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode("utf-8"))
print("patched", T)
