"""HIVE COORDINATED OPERATION V0: one validated operation of two melee fighters on one known big target over two turns, over hive/ci/tree copied to hive/op/tree. The headquarters assigns, the soldier's own think stays: ESCAPE and the dice of the mode are untouched, a blow on an adjacent unit and a charge on anyone else are never held back, nothing after think, no heldOrBack, no PO_HOLD, no ids or coordinates. Run from anywhere."""
from pathlib import Path

B = Path(__file__).parent / "tree" / "src" / "Battlescape"


def patch(name, reps):
    p = B / name
    raw = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", "\n")
    for old, new in reps:
        n = s.count(old)
        if n != 1:
            raise SystemExit(f"{name}: {n} hits for: {old[:80]}")
        s = s.replace(old, new)
    p.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode("utf-8"))


patch("HiveCommand.h", [
    ("""#include <string>

namespace OpenXcom
""", """#include <string>
#include "Position.h"

namespace OpenXcom
"""),
    ("""/// After the unit's think: what it really decided, against its order.
""", """/// HIVE COORDINATED OPERATION V0 (bench, OXCE_AI_HIVE_OP: 0 off, 1 shadow, 2 active, over OXCE_AI_HIVE): two fighters staged on one known big target, the blows on the next turn.
enum OpOrder { OO_NONE, OO_WALK, OO_STAY, OO_ATTACK };
/// Inside setupPatrol and findFirePoint: what the operation wants of this unit now, if it wants anything. The unit's mode is still its own.
OpOrder operationOrder(SavedBattleGame *save, BattleUnit *unit, Position &cell);
/// Inside setupAttack, after meleeAction chose a charge: true - a charge on the operation's target with fewer blows than the planned turn gives waits. Nothing else ever waits.
bool operationDefers(SavedBattleGame *save, BattleUnit *unit, const BattleUnit *target, const Position &to);
/// After the unit's think: what it really decided, against its order.
"""),
])

OP = """// HIVE COORDINATED OPERATION V0 (bench): see the header. The target is a big unit a living unit of the side sees now; the fighters are those who could land
// OP_BLOWS blows in a full turn and have nothing to charge now; each gets its own cell on its own way, to which it walks this turn, and strikes the turn after
int opFlag()
{
	static const int on = mode() != 0 ? (int)AiProbe::param("OXCE_AI_HIVE_OP", 0) : 0;
	return on;
}

int opFromTurn()
{
	static const int t = (int)AiProbe::param("OXCE_AI_HIVE_OP_FROM_TURN", 1);
	return t;
}

void opFlood(SavedBattleGame *save, const BattleUnit *u)
{
	bool capped = false;
	save->getPathfinding()->hiveFlood(u, ORDER_TURNS * u->getBaseStats()->tu, hq.opCost, hq.opPrev, capped);
}

/// A living unit of the side has it in sight now.
bool opSeen(SavedBattleGame *save, const BattleUnit *target)
{
	for (auto *m : *save->getUnits())
	{
		if (!available(m)) continue;
		for (auto *v : *m->getVisibleUnits())
		{
			if (v == target) return true;
		}
	}
	return false;
}

/// The cost of its cheapest free cell next to the target where the side knows it to be, -1 if none; the field is left in hq.opCost and hq.opPrev.
int opWay(SavedBattleGame *save, const BattleUnit *u, const BattleUnit *target, const Position &at, int &index)
{
	opFlood(save, u);
	const int size = target->getArmor()->getSize();
	int way = -1;
	index = -1;
	for (int x = -1; x <= size; ++x)
	{
		for (int y = -1; y <= size; ++y)
		{
			if (x >= 0 && x < size && y >= 0 && y < size) continue;
			const Position p = at + Position(x, y, 0);
			Tile *t = save->getTile(p);
			if (!t || (t->getUnit() && t->getUnit() != u)) continue;
			const int i = save->getTileIndex(p);
			const int c = hq.opCost[i];
			if (c >= 0 && (way < 0 || c < way))
			{
				way = c;
				index = i;
			}
		}
	}
	return way;
}

/// Its cell: the free one nearest the target on its own way that it reaches now, no closer than OP_STAND, from which the next turn still gives OP_BLOWS blows.
bool opStagingCell(SavedBattleGame *save, OpFighter &f, const BattleUnit *target, const Position &at, const Position *taken)
{
	int i = -1;
	const int way = opWay(save, f.unit, target, at, i);
	if (way < 0) return false;
	for (; i >= 0; i = hq.opPrev[i])
	{
		const Position p = save->getTileCoords(i);
		const Tile *t = save->getTile(p);
		const bool own = p == f.unit->getPosition();
		if (hq.opCost[i] > f.unit->getTimeUnits() || Position::distance2d(p, at) < OP_STAND || (!own && t->getUnit()) || (taken && p == *taken)) continue;
		f.cell = p;
		f.stageCost = hq.opCost[i];
		f.rest = way - hq.opCost[i];
		f.nextBlows = (f.unit->getBaseStats()->tu - f.rest) / f.blow;
		return f.nextBlows >= OP_BLOWS;
	}
	return false;
}

void opState(SavedBattleGame *save, OpState s, const char *why)
{
	hq.op.state = s;
	Log(LOG_INFO) << "[HIVEOP] event=STATE op=" << hq.op.id << " turn=" << save->getTurn() << " side=" << (int)save->getSide() << " state=" << OP_NAME[s] << " why=" << why;
}

/// What came of it, as the headquarters reads it: who is still there, what each did, whether the target is down. The target's health is for the log only.
void opEnd(SavedBattleGame *save, OpState s, const char *why)
{
	Operation &op = hq.op;
	opState(save, s, why);
	int attacked = 0;
	for (auto &f : op.f)
	{
		attacked += f.attacks > 0;
		Log(LOG_INFO) << "[HIVEOP] event=FEEDBACK op=" << op.id << " turn=" << save->getTurn() << " unit=" << f.unit->getId() << " out=" << (f.unit->isOut() ? 1 : 0) << " at=" << pos(f.unit->getPosition())
			<< " cell=" << pos(f.cell) << " arrived=" << (f.arrived ? 1 : 0) << " tu=" << f.unit->getTimeUnits() << " attacks=" << f.attacks << " deferred=" << f.deferred << " diverted=" << f.diverted
			<< " released=" << (f.released ? 1 : 0) << " hp=" << f.unit->getHealth();
	}
	Log(LOG_INFO) << "[HIVEOP] event=RESULT op=" << op.id << " turn=" << save->getTurn() << " state=" << OP_NAME[s] << " why=" << why << " target=" << op.target->getId() << " target_out=" << (op.target->isOut() ? 1 : 0)
		<< " attacked=" << attacked << " target_hp_log=" << op.target->getHealth() << " stage_turn=" << op.stageTurn << " exec_turn=" << op.execTurn;
}

OpFighter *opFighterOf(const BattleUnit *u)
{
	if (hq.op.state < OP_STAGING || hq.op.state >= OP_COMPLETED) return 0;
	for (auto &f : hq.op.f)
	{
		if (f.unit == u) return &f;
	}
	return 0;
}

/// First think of the side's turn with no operation yet: one is proposed and validated, or none this turn.
void opPropose(SavedBattleGame *save)
{
	std::vector<BattleUnit*> seen;
	for (auto *u : *save->getUnits())
	{
		if (!u->isOut() && u->getFaction() == FACTION_PLAYER && opSeen(save, u)) seen.push_back(u);
	}
	struct Can { BattleUnit *unit; int blow; int way; };
	std::vector<Can> able;
	for (auto *m : *save->getUnits())
	{
		if (!available(m) || m->getArmor()->getSize() != 1 || !m->getArmor()->allowsMoving() || m->isLeeroyJenkins()) continue;
		BattleItem *w = m->getUtilityWeapon(BT_MELEE);
		if (!w) continue;
		const int blow = BattleActionCost(BA_HIT, m, w).Time;
		if (blow <= 0 || m->getBaseStats()->tu < OP_BLOWS * blow) continue;
		bool chargeable = false;
		for (auto *e : seen)
		{
			chargeable = chargeable || Position::distance2d(m->getPosition(), e->getPosition()) <= OP_REACH;
		}
		if (!chargeable) able.push_back({ m, blow, 0 });
	}
	if (seen.empty() || able.size() < 2) return;
	struct Plan { BattleUnit *target; Can a, b; };
	std::vector<Plan> plans;
	for (auto *e : seen)
	{
		if (e->getArmor()->getSize() < 2) continue;
		std::vector<Can> cans;
		for (auto c : able)
		{
			int i = -1;
			c.way = opWay(save, c.unit, e, e->getPosition(), i);
			const int tu = c.unit->getTimeUnits(), full = c.unit->getBaseStats()->tu;
			if (c.way < 0 || c.way + OP_BLOWS * c.blow <= tu || c.way > tu + full - OP_BLOWS * c.blow) continue;
			cans.push_back(c);
		}
		if (cans.size() < 2) continue;
		std::stable_sort(cans.begin(), cans.end(), [](const Can &x, const Can &y) { return x.way < y.way; });
		plans.push_back({ e, cans[0], cans[1] });
	}
	std::stable_sort(plans.begin(), plans.end(), [](const Plan &x, const Plan &y) { return x.a.way + x.b.way < y.a.way + y.b.way; });
	Operation &op = hq.op;
	for (auto &pl : plans)
	{
		const Position at = pl.target->getPosition();
		Log(LOG_INFO) << "[HIVEOP] event=PROPOSED turn=" << save->getTurn() << " target=" << pl.target->getId() << " at=" << pos(at) << " size=" << pl.target->getArmor()->getSize()
			<< " a=" << pl.a.unit->getId() << " a_way=" << pl.a.way << " b=" << pl.b.unit->getId() << " b_way=" << pl.b.way << " plans=" << plans.size() << " able=" << able.size();
		OpFighter a, b;
		a.unit = pl.a.unit;
		a.blow = pl.a.blow;
		b.unit = pl.b.unit;
		b.blow = pl.b.blow;
		if (!opStagingCell(save, a, pl.target, at, 0) || !opStagingCell(save, b, pl.target, at, &a.cell))
		{
			Log(LOG_INFO) << "[HIVEOP] event=REJECTED turn=" << save->getTurn() << " target=" << pl.target->getId() << " why=no_cell";
			continue;
		}
		op.id = 1;
		op.target = pl.target;
		op.known = at;
		op.stageTurn = save->getTurn();
		op.f[0] = a;
		op.f[1] = b;
		opState(save, OP_PROPOSED, "known_big_target");
		opState(save, OP_VALIDATED, "two_cells_time_units");
		for (auto &f : op.f)
		{
			Log(LOG_INFO) << "[HIVEOP] event=ASSIGN op=" << op.id << " turn=" << save->getTurn() << " unit=" << f.unit->getId() << " from=" << pos(f.unit->getPosition()) << " cell=" << pos(f.cell) << " cost=" << f.stageCost
				<< " rest=" << f.rest << " blow=" << f.blow << " next_blows=" << f.nextBlows << " tu=" << f.unit->getTimeUnits() << " hp=" << f.unit->getHealth();
		}
		if (opFlag() == 2)
		{
			opState(save, OP_STAGING, "assigned");
		}
		else
		{
			opState(save, OP_ABORTED, "shadow");
		}
		return;
	}
}

/// Every think of the side: the turn's opening, the fighters and the target as they are now.
void opTick(SavedBattleGame *save)
{
	if (opFlag() == 0 || !hq.managesBattle) return;
	Operation &op = hq.op;
	const int turn = save->getTurn();
	if (op.state == OP_NONE)
	{
		if (op.lastPropose != turn && turn >= opFromTurn())
		{
			op.lastPropose = turn;
			opPropose(save);
		}
		return;
	}
	if (op.state >= OP_COMPLETED) return;
	if (opSeen(save, op.target))
	{
		op.known = op.target->getPosition();
	}
	if (op.target->isOut())
	{
		opEnd(save, op.state == OP_EXECUTING ? OP_COMPLETED : OP_ABORTED, "target_down");
		return;
	}
	for (auto &f : op.f)
	{
		if (!available(f.unit) && !f.outSaid)
		{
			f.outSaid = true;
			Log(LOG_INFO) << "[HIVEOP] event=FIGHTER_OUT op=" << op.id << " turn=" << turn << " unit=" << f.unit->getId() << " attacks=" << f.attacks;
			if (op.state != OP_EXECUTING)
			{
				opEnd(save, OP_ABORTED, "fighter_out");
				return;
			}
		}
		if (f.released && op.state != OP_EXECUTING)
		{
			opEnd(save, OP_ABORTED, "fighter_stuck");
			return;
		}
	}
	if (op.state != OP_EXECUTING && turn > op.stageTurn)
	{
		if (!opSeen(save, op.target))
		{
			opEnd(save, OP_ABORTED, "target_lost");
			return;
		}
		for (auto &f : op.f)
		{
			int i = -1;
			const int way = opWay(save, f.unit, op.target, op.known, i);
			Log(LOG_INFO) << "[HIVEOP] event=TURN_CHECK op=" << op.id << " turn=" << turn << " unit=" << f.unit->getId() << " at=" << pos(f.unit->getPosition()) << " on_cell=" << (f.unit->getPosition() == f.cell ? 1 : 0)
				<< " tu=" << f.unit->getTimeUnits() << " way=" << way << " blow=" << f.blow << " target_at=" << pos(op.known) << " target_dir=" << op.target->getDirection() << " hp=" << f.unit->getHealth();
			if (way < 0 || way + f.blow > f.unit->getTimeUnits())
			{
				opEnd(save, OP_ABORTED, "out_of_reach");
				return;
			}
		}
		op.execTurn = turn;
		opState(save, OP_EXECUTING, "next_turn");
	}
}

OpOrder operationOrder(SavedBattleGame *save, BattleUnit *unit, Position &cell)
{
	if (opFlag() != 2 || hq.save != save || save->getSide() != FACTION_HOSTILE) return OO_NONE;
	Operation &op = hq.op;
	OpFighter *f = opFighterOf(unit);
	if (!f || f->released) return OO_NONE;
	const Position here = unit->getPosition();
	if (op.state == OP_EXECUTING)
	{
		int i = -1;
		const int way = opWay(save, unit, op.target, op.known, i);
		if (way < 0 || way + f->blow > unit->getTimeUnits())
		{
			f->released = true;
			Log(LOG_INFO) << "[HIVEOP] event=RELEASED op=" << op.id << " turn=" << save->getTurn() << " unit=" << unit->getId() << " at=" << pos(here) << " tu=" << unit->getTimeUnits() << " way=" << way << " attacks=" << f->attacks;
			return OO_NONE;
		}
		if (way == 0) return OO_ATTACK;
		cell = save->getTileCoords(i);
		return OO_WALK;
	}
	if (here == f->cell)
	{
		if (!f->arrived)
		{
			f->arrived = true;
			Log(LOG_INFO) << "[HIVEOP] event=ARRIVED op=" << op.id << " turn=" << save->getTurn() << " unit=" << unit->getId() << " at=" << pos(here) << " tu=" << unit->getTimeUnits() << " hp=" << unit->getHealth();
			if (op.state == OP_STAGING && op.f[0].arrived && op.f[1].arrived)
			{
				opState(save, OP_READY, "both_on_cells");
			}
		}
		return OO_STAY;
	}
	if (op.state == OP_READY || f->arrived)
	{
		// it left its cell by its own choice: it does not walk back this turn, next turn's check decides
		return OO_STAY;
	}
	const Tile *t = save->getTile(f->cell);
	if (t->getUnit() && t->getUnit() != unit)
	{
		OpFighter &other = &op.f[0] == f ? op.f[1] : op.f[0];
		if (!opStagingCell(save, *f, op.target, op.known, &other.cell))
		{
			f->released = true;
			Log(LOG_INFO) << "[HIVEOP] event=RELEASED op=" << op.id << " turn=" << save->getTurn() << " unit=" << unit->getId() << " why=cell_taken";
			return OO_NONE;
		}
		Log(LOG_INFO) << "[HIVEOP] event=RECELL op=" << op.id << " turn=" << save->getTurn() << " unit=" << unit->getId() << " cell=" << pos(f->cell) << " next_blows=" << f->nextBlows;
	}
	opFlood(save, unit);
	int i = save->getTileIndex(f->cell);
	while (i >= 0 && (hq.opCost[i] < 0 || hq.opCost[i] > unit->getTimeUnits()))
	{
		i = hq.opPrev[i];
	}
	if (i < 0 || save->getTileCoords(i) == here) return OO_STAY;
	cell = save->getTileCoords(i);
	return OO_WALK;
}

bool operationDefers(SavedBattleGame *save, BattleUnit *unit, const BattleUnit *target, const Position &to)
{
	if (opFlag() != 2 || hq.save != save || save->getSide() != FACTION_HOSTILE) return false;
	Operation &op = hq.op;
	OpFighter *f = opFighterOf(unit);
	if (!f || f->released || op.state == OP_EXECUTING) return false;
	if (target != op.target)
	{
		f->diverted++;
		Log(LOG_INFO) << "[HIVEOP] event=DIVERT op=" << op.id << " turn=" << save->getTurn() << " unit=" << unit->getId() << " at=" << pos(unit->getPosition()) << " on=" << (target ? target->getId() : -1) << " tu=" << unit->getTimeUnits();
		return false;
	}
	opFlood(save, unit);
	const int c = hq.opCost[save->getTileIndex(to)];
	const int now = c < 0 ? -1 : (unit->getTimeUnits() - c) / f->blow;
	const bool wait = now >= 0 && now < OP_BLOWS && now < f->nextBlows;
	if (wait) f->deferred++;
	Log(LOG_INFO) << "[HIVEOP] event=" << (wait ? "DEFER" : "KEEP_CHARGE") << " op=" << op.id << " turn=" << save->getTurn() << " unit=" << unit->getId() << " at=" << pos(unit->getPosition()) << " to=" << pos(to)
		<< " tu=" << unit->getTimeUnits() << " way=" << c << " blows_now=" << now << " blows_next=" << f->nextBlows;
	return wait;
}

void opDecided(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (opFlag() != 2) return;
	Operation &op = hq.op;
	OpFighter *f = opFighterOf(unit);
	if (!f) return;
	const Tile *t = save->getTile(action.target);
	const bool hit = isAttack(action.type) && t && t->getUnit() == op.target;
	const bool charge = action.type == BA_WALK && unit->getCharging() == op.target;
	if ((hit || charge) && op.state == OP_EXECUTING)
	{
		f->attacks++;
	}
	if (action.type == BA_WALK && unit->getPosition() == f->lastAt && action.target == f->lastTo)
	{
		if (++f->same >= OP_STUCK && !f->released)
		{
			f->released = true;
			Log(LOG_INFO) << "[HIVEOP] event=RELEASED op=" << op.id << " turn=" << save->getTurn() << " unit=" << unit->getId() << " why=no_progress";
		}
	}
	else
	{
		f->same = 0;
	}
	f->lastAt = unit->getPosition();
	f->lastTo = action.target;
	Log(LOG_INFO) << "[HIVEOP] event=ACT op=" << op.id << " turn=" << save->getTurn() << " state=" << OP_NAME[op.state] << " unit=" << unit->getId() << " at=" << pos(unit->getPosition()) << " type=" << (int)action.type
		<< " to=" << pos(action.target) << " tu=" << unit->getTimeUnits() << " hit=" << (hit ? 1 : 0) << " charge=" << (charge ? 1 : 0);
}

void opSideEnds(SavedBattleGame *save)
{
	Operation &op = hq.op;
	if (opFlag() != 2 || op.state < OP_STAGING || op.state >= OP_COMPLETED) return;
	for (auto &f : op.f)
	{
		Log(LOG_INFO) << "[HIVEOP] event=SIDE_END op=" << op.id << " turn=" << save->getTurn() << " side=" << (int)save->getSide() << " state=" << OP_NAME[op.state] << " unit=" << f.unit->getId() << " out=" << (f.unit->isOut() ? 1 : 0)
			<< " at=" << pos(f.unit->getPosition()) << " cell=" << pos(f.cell) << " tu=" << f.unit->getTimeUnits() << " hp=" << f.unit->getHealth() << " attacks=" << f.attacks << " deferred=" << f.deferred
			<< " target_at_log=" << pos(op.target->getPosition()) << " target_dir_log=" << op.target->getDirection() << " target_hp_log=" << op.target->getHealth();
	}
	if (save->getSide() == FACTION_HOSTILE && op.state == OP_EXECUTING)
	{
		const int attacked = (op.f[0].attacks > 0) + (op.f[1].attacks > 0);
		opEnd(save, attacked ? OP_COMPLETED : OP_ABORTED, attacked == 2 ? "both_attacked" : attacked == 1 ? "one_attacked" : "no_attack");
	}
}

void beforeThink(SavedBattleGame *save, BattleUnit *unit)
{
"""

patch("HiveCommand.cpp", [
    ("""struct Hq
{
	SavedBattleGame *save = 0;
""", """/// HIVE COORDINATED OPERATION V0: one operation, one target, two fighters, two turns. In the headquarters' memory only: a battle save does not carry it.
enum OpState { OP_NONE, OP_PROPOSED, OP_VALIDATED, OP_STAGING, OP_READY, OP_EXECUTING, OP_COMPLETED, OP_ABORTED };
const char *const OP_NAME[] = { "NONE", "PROPOSED", "VALIDATED", "STAGING", "READY", "EXECUTING", "COMPLETED", "ABORTED" };
const int OP_BLOWS = 6, OP_STAND = 5, OP_REACH = 20, OP_STUCK = 3;
struct OpFighter
{
	BattleUnit *unit = 0;
	Position cell, lastAt, lastTo;
	int blow = 0, stageCost = 0, rest = 0, nextBlows = 0;
	int attacks = 0, deferred = 0, diverted = 0, same = 0;
	bool arrived = false, released = false, outSaid = false;
};
struct Operation
{
	int id = 0;
	OpState state = OP_NONE;
	BattleUnit *target = 0;
	Position known;
	int stageTurn = -1, execTurn = -1, lastPropose = -1;
	OpFighter f[2];
};

struct Hq
{
	Operation op;
	std::vector<int> opCost, opPrev;
	SavedBattleGame *save = 0;
"""),
    ("""void beforeThink(SavedBattleGame *save, BattleUnit *unit)
{
""", OP),
    ("""	if (hq.managesBattle)
	{
		observe(unit, save);
""", """	opTick(save);
	if (hq.managesBattle)
	{
		observe(unit, save);
"""),
    ("""void decided(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (mode() == 0 || hq.save != save || !hq.managesBattle || save->getSide() != FACTION_HOSTILE || !isOurs(unit)) return;
""", """void decided(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (mode() == 0 || hq.save != save || !hq.managesBattle || save->getSide() != FACTION_HOSTILE || !isOurs(unit)) return;
	opDecided(save, unit, action);
"""),
    ("""void sideEnds(SavedBattleGame *save)
{
	if (mode() == 0 || hq.save != save || !hq.managesBattle) return;
""", """void sideEnds(SavedBattleGame *save)
{
	if (mode() == 0 || hq.save != save || !hq.managesBattle) return;
	opSideEnds(save);
"""),
])

patch("AIModule.cpp", [
    ("""	// HIVE COMMAND CORE V0 (bench): the order of this unit's squad in place of the free choice of a node. Reached only as the
""", """	// HIVE COORDINATED OPERATION V0 (bench): the patrol of a fighter in an operation goes to its cell or ends there. The mode is still the unit's: a charge and ESCAPE
	// stay what they were
	Position opCell;
	const HiveCommand::OpOrder opOrder = HiveCommand::operationOrder(_save, _unit, opCell);
	if (opOrder != HiveCommand::OO_NONE)
	{
		freePatrolTarget();
		_toNode = 0;
		_hiveStand = true;
		_patrolAction.type = opOrder == HiveCommand::OO_WALK ? BA_WALK : opOrder == HiveCommand::OO_ATTACK ? BA_RETHINK : BA_NONE;
		if (opOrder == HiveCommand::OO_WALK)
		{
			_patrolAction.target = opCell;
		}
		return;
	}
	// HIVE COMMAND CORE V0 (bench): the order of this unit's squad in place of the free choice of a node. Reached only as the
"""),
    ("""			probeSlot('x', "melee", mark);
""", """			// HIVE COORDINATED OPERATION V0 (bench): a charge on the operation's target that gives fewer blows than the next turn waits, undone as above; a blow on an
			// adjacent unit and a charge on anyone else never do
			if (_attackAction.type == BA_WALK && _unit->getCharging() && HiveCommand::operationDefers(_save, _unit, _aggroTarget, _attackAction.target))
			{
				_attackAction = launch;
				_aggroTarget = launchTarget;
				_unit->setCharging(charging);
			}
			probeSlot('x', "melee", mark);
"""),
    ("""	intentFirePoint();
	// AI2-H FAIR KNOWLEDGE: the whole search""", """	intentFirePoint();
	// HIVE COORDINATED OPERATION V0 (bench): the point a fighter in an operation walks to is its cell, or none while it stands on it
	Position opCell;
	const HiveCommand::OpOrder opOrder = HiveCommand::operationOrder(_save, _unit, opCell);
	if (opOrder == HiveCommand::OO_WALK)
	{
		_attackAction.type = BA_WALK;
		_attackAction.target = opCell;
		_attackAction.finalFacing = -1;
		return true;
	}
	if (opOrder != HiveCommand::OO_NONE)
	{
		return false;
	}
	// AI2-H FAIR KNOWLEDGE: the whole search"""),
])
print("patched")
