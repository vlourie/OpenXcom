"""RESTORE COMBAT AUTONOMY: HOLD splits into what the squad holds and what the soldier may still do, over hive/cc/tree in hive/ra/tree. HiveCommand.h/.cpp and AIModule.h/.cpp; every path is behind OXCE_AI_HIVE_AUTONOMY=1. Each replace must hit exactly once."""
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
    ("enum PatrolOrder { PO_NONE, PO_HOLD, PO_GO };", "enum PatrolOrder { PO_NONE, PO_HOLD, PO_GO, PO_STAND };"),
    ("/// Inside setupPatrol: the order of this unit. PO_GO gives the node, PO_HOLD ends its selection where it stands, PO_NONE leaves the free choice.",
     "/// Inside setupPatrol: the order of this unit. PO_GO gives the node, PO_HOLD ends its selection where it stands, PO_NONE leaves the free choice, PO_STAND holds the post with no walk and no fall to the escape."),
])

patch("HiveCommand.cpp", [
    ("""bool onContact(const Squad &sq)
{
	return sq.role == R_ENGAGE || sq.role == R_REINFORCE;
}
""", """/// RESTORE COMBAT AUTONOMY (bench): a hold is what the squad keeps, not what its soldier may no longer do.
bool autonomy()
{
	static const bool on = coord() && (int)AiProbe::param("OXCE_AI_HIVE_AUTONOMY", 0) == 1;
	return on;
}

bool onContact(const Squad &sq)
{
	return sq.role == R_ENGAGE || sq.role == R_REINFORCE;
}
"""),
    ("""PatrolOrder patrol(SavedBattleGame *save, BattleUnit *unit, Node *&node)
{
	node = 0;
""", """/// What a hold answers: a guard keeps its post (the squad's objective), anyone else has no useful order and takes its own free choice.
PatrolOrder held(SavedBattleGame *save, const Order &o, const char *from)
{
	if (!autonomy()) return PO_HOLD;
	const auto sf = hq.squadOf.find(o.unit->getId());
	const bool guard = sf != hq.squadOf.end() && o.task == T_HOLD && hq.squads[sf->second].holdWhy == HW_GUARD;
	Log(LOG_INFO) << "[HIVECC] event=AUTONOMY turn=" << save->getTurn() << " unit=" << o.unit->getId() << " answer=" << (guard ? "STAND" : "FREE") << " from=" << from << " why=" << o.why;
	return guard ? PO_STAND : PO_NONE;
}

PatrolOrder patrol(SavedBattleGame *save, BattleUnit *unit, Node *&node)
{
	node = 0;
"""),
    ("""	if (o->stay || o->state == COMPLETED) return PO_HOLD;
	if (nearPos(unit->getPosition(), o->target, ARRIVE_RADIUS))
	{
		setState(*o, COMPLETED, "arrived");
		return PO_HOLD;
	}
	if (o->pauseTurn == save->getTurn())
	{
		return PO_HOLD;
	}
""", """	if (o->stay || o->state == COMPLETED) return held(save, *o, o->stay ? "stay" : "completed");
	if (nearPos(unit->getPosition(), o->target, ARRIVE_RADIUS))
	{
		setState(*o, COMPLETED, "arrived");
		return held(save, *o, "arrived");
	}
	if (o->pauseTurn == save->getTurn())
	{
		return held(save, *o, "pause");
	}
"""),
    ("""			newOrder(sq, unit, true, 0, unit->getPosition(), "no_path_now");
			return PO_HOLD;
""", """			newOrder(sq, unit, true, 0, unit->getPosition(), "no_path_now");
			f = hq.orders.find(unit->getId());
			return f == hq.orders.end() || !f->second.unit ? PO_HOLD : held(save, f->second, "no_path_now");
"""),
    ("""		if (o->stay) return PO_HOLD;
	}
	node = o->node;
""", """		if (o->stay) return held(save, *o, "replan");
	}
	node = o->node;
"""),
])

patch("AIModule.h", [
    ("""	/// This think's action is the patrol's walk to its node.
	bool _patrolWalk = false;
""", """	/// This think's action is the patrol's walk to its node.
	bool _patrolWalk = false;
	/// RESTORE COMBAT AUTONOMY (bench): this think the headquarters has the unit keep its post. Set and read inside one think, never saved.
	bool _hiveStand = false;
"""),
])

patch("AIModule.cpp", [
    ("""void AIModule::setupPatrol()
{
""", """void AIModule::setupPatrol()
{
	_hiveStand = false;
"""),
    ("""	if (hiveOrder == HiveCommand::PO_HOLD)
	{
		freePatrolTarget();
		_toNode = 0;
		_patrolAction.type = BA_NONE;
		return;
	}
""", """	if (hiveOrder == HiveCommand::PO_HOLD || hiveOrder == HiveCommand::PO_STAND)
	{
		freePatrolTarget();
		_toNode = 0;
		_patrolAction.type = BA_NONE;
		_hiveStand = hiveOrder == HiveCommand::PO_STAND;
		return;
	}
"""),
    ("""		if (_ambushTUs != 0)
		{
			return;
		}
		_AIMode = AI_ESCAPE;
	}
}
""", """		if (_ambushTUs != 0)
		{
			return;
		}
		// RESTORE COMBAT AUTONOMY (bench): the unit keeps the post it was told to keep, no place to hide is no reason to run from it
		if (_hiveStand)
		{
			_AIMode = AI_PATROL;
			return;
		}
		_AIMode = AI_ESCAPE;
	}
}
"""),
])
print("patched")
