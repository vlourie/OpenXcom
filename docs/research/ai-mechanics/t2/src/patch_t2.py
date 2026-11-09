"""AI-T2 ATTACK FEASIBILITY (GO Vitali 27.10): OXCE_AI_T2 in the isolated tree c2/tree (AIModule.cpp/.h, AiProbe.cpp) on top
of the clean al3 sources (exe AL of P0/P1).

  py -3.13 patch_t2.py <tree>
1 - the record only ([AIT2] per hostile firearm shot, [AIT2FX] what each hostile attack changed on its target), decisions as
before; 2 - the switch of a useless shot to a useful lawful target ([AIT2SET]). Off (0) - as before."""
import sys
from pathlib import Path

T = Path(sys.argv[1]) / "src" / "Battlescape"


TEXT = {}


def sub(path, old, new):
    """The tree's files are CRLF: matched as they are, all in memory; written only when every match is unique."""
    t = TEXT.setdefault(path, path.read_bytes().decode("utf-8"))
    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    if t.count(old) != 1:
        raise SystemExit(f"{path.name}: {t.count(old)} matches for {old[:60]!r}, nothing written")
    TEXT[path] = t.replace(old, new)


H = T / "AIModule.h"
C = T / "AIModule.cpp"
P = T / "AiProbe.cpp"
sub(H, "\tdouble fireModeEffect(BattleAction *action, BattleUnit *target, const char *&why);",
    "\tdouble fireModeEffect(BattleAction *action, BattleUnit *target, const char *&why);\n"
    "\t/// AI-T2: a useless firearm shot goes at a lawful target it can hurt (OXCE_AI_T2).\n\tvoid t2Retarget();")
sub(H, "\tint _probeScore = INT_MIN;",
    "\tint _probeScore = INT_MIN;\n\t/// AI-T2: the target t2Retarget took the shot away from (OXCE_AI_T2=2), else null.\n\tBattleUnit *_t2From = nullptr;")
sub(C, """		if (_rifle)
		{
			const ProbeMark mark = probeMark('x');
			projectileAction();
			probeSlot('x', "shot", mark);
		}""", """		if (_rifle)
		{
			t2Retarget();
			const ProbeMark mark = probeMark('x');
			projectileAction();
			probeSlot('x', "shot", mark);
			if (_t2From)
			{
				Log(LOG_INFO) << "[AIT2SET] turn=" << _save->getTurn() << " unit=" << _unit->getId() << " from=" << _t2From->getId()
					<< " to=" << _aggroTarget->getId() << " act=" << (int)_attackAction.type;
				_t2From = nullptr;
			}
		}""")
sub(C, """	return hit * shots * perHit * uses;
}
""", """	return hit * shots * perHit * uses;
}

/**
 * AI-T2 (bench): OXCE_AI_T2 - a hostile firearm shot that practically cannot change its target goes at another lawful target
 * it can hurt (1 - the record only, 2 - the switch). Called in setupAttack right before projectileAction, so only for a shot
 * (no grenade, no melee chosen). The shot is useless when the unit has the time units for at least one fire mode and for every
 * such mode the honest AI2-A verdict finds nothing that could act besides the damage through the armour (no area, spawn,
 * transformation, fire, energy shield, script, armour wear, armour-ignoring damage: any of them keeps the shot) and the expected
 * damage over the turn (fireModeEffect: the nominal accuracy with the dropoff, the ruleset armour and resistance of the side it
 * shows) stays below 0.5 HP. Another target takes the shot only under the nearest pick's own checks (validTarget with
 * civilians, seen now, a line of fire) and with at least 3 HP expected from a mode the unit has the TU for; the higher OXCE
 * target weight first (the player's side over civilians, civilians are not barred), then the larger expected damage, then the
 * nearer. Not read: health, current armour, maximum health, the true place of an unseen unit. No RNG; without such a target
 * the shot stays as it was, nothing is cancelled.
 */
void AIModule::t2Retarget()
{
	static const int mode = (int)AiProbe::param("OXCE_AI_T2", 0);
	if (mode <= 0 || !_aggroTarget || !_attackAction.weapon || _unit->getFaction() != FACTION_HOSTILE)
	{
		return;
	}
	const double useless = 0.5, useful = 3.0;
	// the best expected damage over the modes the unit has the TU for; why: empty - nothing but the damage can act, else what can
	auto judge = [&](BattleUnit *bu, double &ev, std::string &why)
	{
		ev = 0.0;
		why.clear();
		int modes = 0;
		BattleAction action;
		action.actor = _unit;
		action.weapon = _attackAction.weapon;
		action.target = bu->getPosition();
		for (BattleActionType t : { BA_AIMEDSHOT, BA_SNAPSHOT, BA_AUTOSHOT })
		{
			BattleActionCost cost(t, _unit, _attackAction.weapon);
			if (!cost.haveTU())
			{
				continue;
			}
			++modes;
			std::string terms;
			const int v = zeroEffectVerdictHonest(_save, _unit, t, _attackAction.weapon, bu, &terms, true);
			const size_t at = terms.find("\\"why\\":\\"");
			const std::string vwhy = at == std::string::npos ? std::string("?") : terms.substr(at + 7, terms.find('"', at + 7) - at - 7);
			if (why.empty() && v != AIZ_ZERO && vwhy != "armor_hidden")
			{
				why = vwhy;
			}
			action.type = t;
			const char *fw = "";
			const double e = fireModeEffect(&action, bu, fw);
			if (e < 0.0 && why.empty())
			{
				why = fw;
			}
			ev = std::max(ev, e);
		}
		return modes;
	};
	double ev0 = 0.0;
	std::string why0;
	const int modes0 = judge(_aggroTarget, ev0, why0);
	const bool isUseless = modes0 > 0 && why0.empty() && ev0 < useless;
	BattleUnit *best = nullptr;
	double bestEv = 0.0;
	int bestWeight = 0, bestDist = 0, n = 0;
	std::ostringstream alts;
	if (isUseless)
	{
		for (auto* bu : *_save->getUnits())
		{
			if (bu == _aggroTarget || !validTarget(bu, true, true) || !_save->getTileEngine()->visible(_unit, bu->getTile()))
			{
				continue;
			}
			if (AiProbe::fairKnowledge() && bu->getFaction() != _unit->getFaction())
			{
				Position mem;
				int dir = 0;
				const int st = AiProbe::fairState(_save, _unit, bu, mem, dir);
				if (st != AiProbe::FAIR_CURRENT && st != AiProbe::FAIR_CHEAT)
				{
					continue;
				}
			}
			BattleAction action;
			action.actor = _unit;
			action.weapon = _attackAction.weapon;
			action.target = bu->getPosition();
			Position origin = _save->getTileEngine()->getOriginVoxel(action, 0);
			Position at;
			if (!_save->getTileEngine()->canTargetUnit(&origin, bu->getTile(), &at, _unit, false))
			{
				continue;
			}
			double ev = 0.0;
			std::string why;
			if (judge(bu, ev, why) == 0)
			{
				continue;
			}
			++n;
			const int weight = (int)getTargetAttackWeight(bu);
			const int dist = Position::distance2d(_unit->getPosition(), bu->getPosition());
			alts << bu->getId() << ":" << (int)bu->getFaction() << ":" << dist << ":" << (int)std::lround(ev * 10) << ":"
				<< (why.empty() ? "-" : why) << ";";
			if (ev >= useful && (!best || weight > bestWeight || (weight == bestWeight && (ev > bestEv || (ev == bestEv && dist < bestDist)))))
			{
				best = bu;
				bestEv = ev;
				bestWeight = weight;
				bestDist = dist;
			}
		}
	}
	const bool doSwitch = mode >= 2 && best;
	if (AiProbe::active())
	{
		Log(LOG_INFO) << "[AIT2] turn=" << _save->getTurn() << " unit=" << _unit->getId() << " tu=" << _unit->getTimeUnits()
			<< " weapon=" << _attackAction.weapon->getRules()->getType() << " target=" << _aggroTarget->getId()
			<< " tfac=" << (int)_aggroTarget->getFaction() << " modes=" << modes0 << " ev10=" << (int)std::lround(ev0 * 10)
			<< " why=" << (why0.empty() ? "-" : why0) << " useless=" << (isUseless ? 1 : 0) << " n=" << n
			<< " best=" << (best ? best->getId() : -1) << " bfac=" << (best ? (int)best->getFaction() : -1)
			<< " bev10=" << (int)std::lround(bestEv * 10) << " switch=" << (doSwitch ? 1 : 0) << " alts=" << alts.str();
	}
	if (doSwitch)
	{
		_t2From = _aggroTarget;
		_aggroTarget = best;
	}
}
""")
sub(P, "void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)\n{\n\tif (!active())\n\t{\n\t\treturn;\n\t}\n",
    """namespace
{
/// AI-T2 (bench): OXCE_AI_T2 >= 1 - the target of a hostile attack as it was at the decision; the next decision of anyone (the
/// attack has played out by then) writes what changed as [AIT2FX]. Plain reads for the record, nothing decides by them.
struct T2Fx
{
	int unit = -1, target = -1, turn = 0, side = 0, act = 0;
	int v[13] = {};
};
T2Fx t2Fx;
void t2State(const BattleUnit *bu, int *v)
{
	v[0] = bu->getHealth();
	v[1] = bu->getStunlevel();
	v[2] = bu->getMorale();
	v[3] = bu->getTimeUnits();
	v[4] = bu->getEnergy();
	v[5] = bu->getFatalWounds();
	v[6] = bu->getFire();
	v[7] = bu->getArmor(SIDE_FRONT);
	v[8] = bu->getArmor(SIDE_LEFT);
	v[9] = bu->getArmor(SIDE_RIGHT);
	v[10] = bu->getArmor(SIDE_REAR);
	v[11] = bu->getArmor(SIDE_UNDER);
	v[12] = (int)bu->getStatus();
}
void t2Flush(SavedBattleGame *save)
{
	if (t2Fx.unit < 0)
	{
		return;
	}
	for (const auto *bu : *save->getUnits())
	{
		if (bu->getId() == t2Fx.target)
		{
			int now[13];
			t2State(bu, now);
			std::ostringstream s;
			s << "[AIT2FX] turn=" << t2Fx.turn << " unit=" << t2Fx.unit << " act=" << t2Fx.act << " target=" << t2Fx.target
				<< " later=" << (save->getTurn() != t2Fx.turn || (int)save->getSide() != t2Fx.side ? 1 : 0)
				<< " st=" << t2Fx.v[12] << ">" << now[12] << " d=";
			for (int i = 0; i < 12; ++i)
			{
				s << (i ? "," : "") << now[i] - t2Fx.v[i];
			}
			Log(LOG_INFO) << s.str();
			break;
		}
	}
	t2Fx.unit = -1;
}
}

void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (!active())
	{
		return;
	}
	static const int t2 = (int)param("OXCE_AI_T2", 0);
	if (t2 >= 1)
	{
		t2Flush(save);
	}
""")
sub(P, "\tfairDecision(save, unit, action);\n\tif (record())\n", """	if (t2 >= 1 && target && unit->getFaction() == FACTION_HOSTILE && (action.type == BA_AUTOSHOT || action.type == BA_SNAPSHOT
		|| action.type == BA_AIMEDSHOT || action.type == BA_HIT))
	{
		t2Fx.unit = unit->getId();
		t2Fx.target = target->getId();
		t2Fx.turn = save->getTurn();
		t2Fx.side = (int)save->getSide();
		t2Fx.act = (int)action.type;
		t2State(target, t2Fx.v);
	}
	fairDecision(save, unit, action);
	if (record())
""")
for p, t in TEXT.items():
    p.write_bytes(t.encode("utf-8"))
print("patched")
