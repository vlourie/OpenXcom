"""UNIFIED ARMY CONTROL V0: over a pristine copy of hive/ra/tree in hive/ua/tree. No order reaches a soldier any more: PO_STAND, _hiveStand, HiveCommand::patrol, orders and contact roles go; a squad's task becomes a place, a condition on the node the soldier's own setupPatrol chooses, with the free choice behind it. Each replace and cut must hit exactly once."""
from pathlib import Path

ROOT = Path(__file__).parent / "tree" / "src"
BS = ROOT / "Battlescape"
SV = ROOT / "Savegame"


class Text:
    def __init__(self, path):
        self.path = path
        raw = path.read_bytes().decode("utf-8")
        self.crlf = "\r\n" in raw
        self.s = raw.replace("\r\n", "\n")

    def rep(self, old, new):
        n = self.s.count(old)
        if n != 1:
            raise SystemExit(f"{self.path.name}: {n} hits for: {old[:90]}")
        self.s = self.s.replace(old, new)

    def cut(self, a, b, new=""):
        """From a up to b, b stays."""
        if self.s.count(a) != 1:
            raise SystemExit(f"{self.path.name}: {self.s.count(a)} hits for start: {a[:90]}")
        i = self.s.index(a)
        j = self.s.find(b, i + len(a))
        if j < 0:
            raise SystemExit(f"{self.path.name}: no end {b[:90]}")
        self.s = self.s[:i] + new + self.s[j:]

    def done(self):
        self.path.write_bytes((self.s.replace("\n", "\r\n") if self.crlf else self.s).encode("utf-8"))


# ---------- SavedBattleGame: the one new parameter
t = Text(SV / "SavedBattleGame.h")
t.rep("	Node *getPatrolNode(bool scout, BattleUnit *unit, Node *fromNode);",
      "	Node *getPatrolNode(bool scout, BattleUnit *unit, Node *fromNode, const HiveCommand::NodeFit *fit = nullptr);")
t.rep("class Tile;\nclass SavedGame;", "namespace HiveCommand { struct NodeFit; }\nclass Tile;\nclass SavedGame;")
t.done()

t = Text(SV / "SavedBattleGame.cpp")
t.rep(""" * @param fromNode Pointer to the node the unit is at.
 * @return Pointer to the chosen node.
 */
Node *SavedBattleGame::getPatrolNode(bool scout, BattleUnit *unit, Node *fromNode)""", """ * @param fromNode Pointer to the node the unit is at.
 * @param fit UNIFIED ARMY CONTROL V0 (bench): what a squad's task asks of the node, on top of all the tests below; none: the engine's own choice.
 * @return Pointer to the chosen node.
 */
Node *SavedBattleGame::getPatrolNode(bool scout, BattleUnit *unit, Node *fromNode, const HiveCommand::NodeFit *fit)""")
t.rep("		if ( !n->isDummy()																				// don't consider dummy nodes.\n",
      "		if ( !n->isDummy()																				// don't consider dummy nodes.\n			&& (!fit || fit->accepts(n))\n")
t.rep("			return getPatrolNode(true, unit, fromNode); // move dammit", "			return getPatrolNode(true, unit, fromNode, fit); // move dammit")
t.done()

# ---------- AIModule
t = Text(BS / "AIModule.h")
t.rep("	bool _hiveStand = false;\n", "")
t.rep("	void setupPatrol();\n", """	void setupPatrol();
	/// UNIFIED ARMY CONTROL V0 (bench): the patrol's new node; with a squad's task, its node where one fits, the free choice where none does.
	Node *hivePatrolNode(bool scout, int triesLeft);
""")
t.done()

t = Text(BS / "AIModule.cpp")
t.rep("""void AIModule::setupPatrol()
{
	_hiveStand = false;
	_patrolAction.clearTU();""", """void AIModule::setupPatrol()
{
	_patrolAction.clearTU();""")
t.cut("	// HIVE COMMAND CORE V0 (bench): the order of this unit's squad in place of the free choice of a node.", "	int triesLeft = 5;\n",
      """	// UNIFIED ARMY CONTROL V0 (bench): a node kept from before that no longer serves the squad's task goes back to the choice below, once a turn; with nothing else to go to, the unit keeps it
	Node *hiveDropped = 0;
	if (_toNode != 0 && HiveCommand::dropKept(_save, _unit, _toNode))
	{
		hiveDropped = _toNode;
		freePatrolTarget();
		_toNode = 0;
	}
""")
t.rep("""			_toNode = _save->getPatrolNode(scout, _unit, _fromNode);
			if (_toNode == 0)
			{
				_toNode = _save->getPatrolNode(!scout, _unit, _fromNode);
			}
""", """			_toNode = hivePatrolNode(scout, triesLeft);
""")
t.rep("""	for (auto* node : noPathNodes)
	{
		node->freeNode();
	}

	const bool staleCleared""", """	for (auto* node : noPathNodes)
	{
		node->freeNode();
	}
	if (_toNode == 0 && hiveDropped != 0)
	{
		_toNode = hiveDropped;
		Log(LOG_INFO) << "[HIVEUA] event=KEPT_BACK turn=" << _save->getTurn() << " unit=" << _unit->getId();
	}

	const bool staleCleared""")
t.rep("""/**
 * Try to set up an ambush action
""", """/**
 * UNIFIED ARMY CONTROL V0 (bench): the patrol's new node. The soldier chooses as ever, by the engine's own getPatrolNode and its own dice, among the nodes
 * its squad's task allows; none of them will do, and the free choice stands. The free choice is always made first and the dice go on from it, so that the
 * only thing the task changes is the node, and the log can say what the soldier would have done without it. The last two tries of the five carry no condition.
 */
Node *AIModule::hivePatrolNode(bool scout, int triesLeft)
{
	const auto freeChoice = [this, scout]()
	{
		Node *n = _save->getPatrolNode(scout, _unit, _fromNode);
		return n != 0 ? n : _save->getPatrolNode(!scout, _unit, _fromNode);
	};
	HiveCommand::NodeFit fit;
	if (!HiveCommand::patrolIntent(_save, _unit, fit))
	{
		return freeChoice();
	}
	const uint64_t seedBefore = RNG::getSeed();
	Node *freeNode = freeChoice();
	const uint64_t seedAfter = RNG::getSeed();
	Node *chosen = 0;
	int rung = -1;
	if (triesLeft >= 2)
	{
		RNG::setSeed(seedBefore);
		for (int r = 0; r < HiveCommand::FIT_RUNGS && chosen == 0; ++r)
		{
			bool mapWide = false;
			if (HiveCommand::fitRung(fit, r, mapWide))
			{
				chosen = _save->getPatrolNode(mapWide || scout, _unit, _fromNode, &fit);
				rung = r;
			}
		}
		RNG::setSeed(seedAfter);
	}
	HiveCommand::patrolChosen(_save, _unit, fit, rung, 5 - triesLeft, freeNode, chosen);
	return HiveCommand::mode() == 2 && chosen != 0 ? chosen : freeNode;
}

/**
 * Try to set up an ambush action
""")
t.rep("""		// RESTORE COMBAT AUTONOMY (bench): the unit keeps the post it was told to keep, no place to hide is no reason to run from it
		if (_hiveStand)
		{
			_AIMode = AI_PATROL;
			return;
		}
""", "")
t.done()

# ---------- HiveCommand.h
t = Text(BS / "HiveCommand.h")
t.rep("#include <string>\n", "#include <string>\n#include \"Position.h\"\n")
t.rep(""" * squads with real commanders, a memory of contacts between turns and an order for each unit. It only ever answers one question
 * inside the unit's own think: where does a patrol go. Combat, ambush, escape and panic stay the unit's. No dice, no free action,
 * no knowledge of a player unit that no living unit of the side has in sight. See docs/research/ai-mechanics/HIVE_COMMAND_ARCHITECTURE.md
""", """ * squads with real commanders, a memory of contacts between turns and a task for each squad. UNIFIED ARMY CONTROL V0: the task is a place,
 * and the only thing it touches is which nodes the unit's own patrol may choose from, its own dice choosing; none fits, and the free choice stands.
 * Combat, ambush, escape and panic stay the unit's. No dice, no free action, no knowledge of a player unit that no living unit of the side has in sight.
 * See docs/research/ai-mechanics/HIVE_UNIFIED_ARMY_CONTROL_V0_DESIGN.md
""")
t.rep("""enum PatrolOrder { PO_NONE, PO_HOLD, PO_GO, PO_STAND };

""", """/// What a squad's task asks of a patrol's node, for one unit, on top of all the engine's own tests. Knows nothing of the other side beyond the place it was given.
struct NodeFit
{
	int squad = -1;
	const char *kind = "";
	Position center;
	int radius = 0, here = 0;
	bool closer = false, skipVisited = false, hasVisited = false;
	const std::vector<int> *reach = 0;
	mutable int accepted = 0;
	bool accepts(const Node *n) const;
};
/// The steps of the choice, in their order: not yet visited inside the place, by the unit's own kind of search and then all over the map; the same with visited ones; nearer the place than the unit stands, for one outside it.
const int FIT_RUNGS = 5;

""")
t.rep("#include <string>\n", "#include <string>\n#include <vector>\n")
t.rep("""/// Inside setupPatrol: the order of this unit. PO_GO gives the node, PO_HOLD ends its selection where it stands, PO_NONE leaves the free choice, PO_STAND holds the post with no walk and no fall to the escape.
PatrolOrder patrol(SavedBattleGame *save, BattleUnit *unit, Node *&node);
""", """/// Inside setupPatrol, a new node to choose: the place this unit's squad's task asks for; false, none, and the free choice is all there is.
bool patrolIntent(SavedBattleGame *save, BattleUnit *unit, NodeFit &fit);
/// Sets the fit for one step of the choice; false, the step does not apply. mapWide: the search of this step goes over the whole map.
bool fitRung(NodeFit &fit, int rung, bool &mapWide);
/// What came of the choice, for the log and the feedback: free is what the unit would have taken with no task, chosen what the task allowed (0: nothing, the free one stands).
void patrolChosen(SavedBattleGame *save, BattleUnit *unit, const NodeFit &fit, int rung, int tryNo, Node *free, Node *chosen);
/// Inside setupPatrol, a node kept from before: does it go back to the choice? Once a turn for a unit, and not a node the free choice just gave it.
bool dropKept(SavedBattleGame *save, BattleUnit *unit, Node *kept);
""")
t.rep("/// After the unit's think: what it really decided, against its order.", "/// After the unit's think: what it really decided.")
t.done()

# ---------- HiveCommand.cpp
t = Text(BS / "HiveCommand.cpp")
t.rep("""const int HOLD_TURNS = 3, HOLD_IDLE = 2, HOLD_EXIT_RADIUS = 12, SEARCH_STALL = 2, RETARGET = 5;
""", """const int HOLD_TURNS = 3, HOLD_IDLE = 2, HOLD_EXIT_RADIUS = 12, SEARCH_STALL = 2, RETARGET = 5;
// UNIFIED ARMY CONTROL V0 (bench): the size of a task's place, how long a response lasts past the last sight of the contact and the rest after it, the turns a quiet guard stays
const int SECURE_RADIUS = 8, SEARCH_RADIUS = 10, RESPOND_RADIUS = 8, RESPOND_TURNS = 2, RESPOND_REST = 1, SECURE_IDLE = 4;
""")
t.rep("""	int roleContact = -1, roleSince = -1, roleUntil = -1, restUntil = -1, roleShots = 0, roleStall = 0, roleBest = 1000000;
};
""", """	int roleContact = -1, roleSince = -1, roleUntil = -1, restUntil = -1, roleShots = 0, roleStall = 0, roleBest = 1000000;
	Position roleAt;
	int roleFar = 0;
};
""")
t.rep("""struct Hq
{
	SavedBattleGame *save = 0;""", """/// The unit's last patrol node under its task and how its turn began: for the feedback only, never saved.
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
	SavedBattleGame *save = 0;""")
t.rep("""	std::map<int, Field> fields;
""", """	std::map<int, Field> fields;
	std::map<int, Choice> choices;
	std::map<int, TurnStart> starts;
	std::map<int, int> fellBack, dropped; // unit -> the turn
""")
t.cut("bool coord()\n", "int dist(const Position &a, const Position &b)")
t.cut("/// The node test of the engine's own patrol choice", "Node *closestNode(")
t.cut("Order &newOrder(Squad &sq", "/// The unit's field: once a turn")
t.cut("/// Where the unit stands and how much it can reach:", "/// Takes what this unit has in sight:")
t.cut("/// The contact the commander's memory still holds", "void changeCommander(")
t.cut("bool isLocked(const BattleUnit *u)", "/// A member of the squad can walk to this node.")
t.cut("/// SEARCH's objective: a remembered contact", "/// A hold always has its place")
t.cut("bool orderHolds(const Order *o, const Squad &sq)", "/// The fewest time units a shot")
t.cut("/// A line of fire from this cell to the contact", "void initSectors(", r'''const char *kindName(const Squad &s)
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

''')
# organization: a third of the squads on guard, and every squad has its place from the start
t.rep("""			const int holders = hq.squads.size() >= 2 ? (int)hq.squads.size() / 2 : 0;
""".replace("			const", "		const"), """		const int holders = hq.squads.size() >= 2 ? ((int)hq.squads.size() + 2) / 3 : 0;
""")
t.rep("""		// the tasks, no dice: long arms and the squads standing most inside hold, the short arms go looking; half and half, one of each from two squads on
""", """		// the tasks, no dice: long arms and the squads standing most inside hold, the short arms go looking; a third on guard, one of each from two squads on
""")
t.rep("""			s.anchor = n ? n->getPosition() : s.commander->getPosition();
			if (s.task == T_HOLD)
			{
				s.holdWhy = HW_GUARD;""", """			s.anchor = n ? n->getPosition() : s.commander->getPosition();
			if (s.task == T_SEARCH)
			{
				s.objective.valid = true;
				s.objective.pos = s.objective.keyPos = s.anchor;
				s.objective.since = save->getTurn();
				s.objective.key = hq.nextKey++;
			}
			if (s.task == T_HOLD)
			{
				s.holdWhy = HW_GUARD;""")
t.rep("""				<< " task=" << TASK_NAME[s.task] << " anchor=" << pos(s.anchor) << " hold=" << HOLD_NAME[s.holdWhy] << " holdEnd=" << s.holdEnd;
""", """				<< " task=" << TASK_NAME[s.task] << " anchor=" << pos(s.anchor) << " hold=" << HOLD_NAME[s.holdWhy] << " holdEnd=" << s.holdEnd;
			Log(LOG_INFO) << "[HIVEUA] event=ORG turn=" << save->getTurn() << " squad=" << s.id << " commander=" << s.commander->getId() << " size=" << s.members.size() << " area=" << areaText(s) << " sector=" << s.sector;
""")
# commanders
t.rep("""void checkSquad(Squad &sq, SavedBattleGame *save, bool plan)
""", """void checkSquad(Squad &sq, SavedBattleGame *save)
""")
t.rep("""			if (plan)
			{
				planSquad(sq, save);
			}
""", "")
t.rep("			checkSquad(s, save, false);\n".replace("			check", "		check"), "		checkSquad(s, save);\n")
t.rep("			checkSquad(sq, save, true);\n", "			checkSquad(sq, save);\n")
# the turn's plan
t.rep("""	hq.rejFar = hq.rejUnreachable = hq.rejMemo = hq.rejIllegal = 0;

	if (first)
""", """	hq.rejFar = hq.rejUnreachable = hq.rejMemo = hq.rejIllegal = 0;
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
""")
t.rep("""	if (coord())
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
""", """	respond(save);
	for (auto &s : hq.squads)
	{
		if (s.commander)
		{
			reviewTask(s, save);
		}
	}
""")
# saved form
t.rep("""		if (q.role != R_NONE)
		{
			s << ";R," << q.id << ',' << (int)q.role << ',' << q.roleContact << ',' << q.roleSince << ',' << q.roleUntil << ',' << q.restUntil << ',' << q.roleShots << ',' << q.roleStall << ',' << q.roleBest;
		}
""", """		if (q.role != R_NONE || q.restUntil != -1)
		{
			s << ";R," << q.id << ',' << (int)q.role << ',' << q.roleContact << ',' << q.roleSince << ',' << q.roleUntil << ',' << q.restUntil << ',' << q.roleShots << ',' << q.roleStall << ',' << q.roleBest;
			put(s, q.roleAt);
			s << ',' << q.roleFar;
		}
""")
t.rep("""				q.roleBest = x.num();
			}
""", """				q.roleBest = x.num();
				q.roleAt = x.place();
				q.roleFar = x.num();
			}
""")
# public functions
t.rep("""int mode()
{
	static const int m = (int)AiProbe::param("OXCE_AI_HIVE", 0);""", """bool NodeFit::accepts(const Node *n) const
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
	static const int m = (int)AiProbe::param("OXCE_AI_HIVE", 0);""")
t.rep("""		if (sq.task == T_SEARCH)
			{
				Sector &s = hq.sectors[sq.sector];
				for (auto *n : s.nodes)
				{
					if (nearPos(unit->getPosition(), n->getPosition(), VISIT_RADIUS))
					{
						s.visited.insert(n->getID());
					}
				}
			}
""".replace("		if (sq.task == T_SEARCH)", "			if (sq.task == T_SEARCH)"), """			if (sq.task == T_SEARCH && sq.role == R_NONE)
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
""")
t.cut("/// What a hold answers:", "void decided(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)", r'''namespace
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

''')
t.cut("void decided(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)", "void sideEnds(SavedBattleGame *save)", r'''void decided(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
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

''')
t.rep("""	if (save->getSide() != FACTION_HOSTILE || !hq.turnOpen) return;
	hq.turnOpen = false;
""", """	if (save->getSide() != FACTION_HOSTILE || !hq.turnOpen) return;
	hq.turnOpen = false;
	logTurnEnd(save);
""")
t.done()
print("patched")
