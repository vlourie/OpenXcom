"""AI-T1 (target selection, GO Vitali 27.10): OXCE_AI_TARGET_EV in the isolated tree c2/tree (AIModule.cpp/.h).

  py -3.13 patch_t1.py <tree>
1 - the record only ([AITARGET] per attack target pick of a hostile firearm unit), 2 - the pick. Off (0) - as before."""
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
sub(H, "\tint selectNearestTarget(bool escape = false);", "\tint selectNearestTarget(bool escape = false, bool attack = false);")
sub(H, "\tint _probeScore = INT_MIN;", "\tint _probeScore = INT_MIN;\n\t/// AI-T1: the target selectNearestTarget valued clearly better than the nearest (OXCE_AI_TARGET_EV=2), else null.\n\tBattleUnit *_evPick = nullptr;")
sub(C, "\tif (!sniperAttack && selectNearestTarget())\n", "\tif (!sniperAttack && selectNearestTarget(false, true))\n")
sub(C, """		if (_melee && _rifle)
		{
			selectMeleeOrRanged();
		}
		if (_grenade)""", """		if (_melee && _rifle)
		{
			selectMeleeOrRanged();
		}
		// AI-T1 (bench): OXCE_AI_TARGET_EV=2 - a firearm attack (melee not chosen) goes at the target selectNearestTarget valued
		// clearly better than the nearest; the melee choice above still weighs the nearest. Off - _evPick stays null.
		if (_evPick && _rifle && !_melee)
		{
			Log(LOG_INFO) << "[AITARGETSET] turn=" << _save->getTurn() << " unit=" << _unit->getId() << " from=" << _aggroTarget->getId()
				<< " to=" << _evPick->getId();
			_aggroTarget = _evPick;
		}
		if (_grenade)""")
sub(C, "int AIModule::selectNearestTarget(bool escape)\n{", "int AIModule::selectNearestTarget(bool escape, bool attack)\n{")
sub(C, """	const char *cons = escape ? "escape" : "nearest";
	int pickState = AiProbe::FAIR_LEGACY;
	for (auto* bu : *_save->getUnits())
	{
		// AI2-H h8""", """	const char *cons = escape ? "escape" : "nearest";
	int pickState = AiProbe::FAIR_LEGACY;
	// AI-T1 (bench): OXCE_AI_TARGET_EV - the attack's target by its expected effect, not by the distance alone (1 - the record
	// only, 2 - the pick). For a hostile unit with a firearm in setupAttack every seen target with a line of fire is valued by the
	// share of its maximum health the best fire mode it has the time units for is expected to take this turn (fireModeEffect:
	// the hit chance with the range dropoff, the shots, the uses, the ruleset armour and resistance of the side it shows; capped
	// to 1), times its ruleset target weight (a civilian 50, the enemy 100). The pick (2) leaves the nearest only for a target
	// worth more than 1.5 times as much (_evPick, taken by setupAttack for a firearm attack); a weapon the effect cannot model
	// (an area, no ammo) - the nearest. Not read: the target's current health and armour. No RNG; _aggroTarget and _closestDist
	// stay the nearest's here. Off - as before.
	static const int targetEv = (int)AiProbe::param("OXCE_AI_TARGET_EV", 0);
	const bool evOn = attack && targetEv > 0 && _rifle && _unit->getFaction() == FACTION_HOSTILE;
	_evPick = nullptr;
	struct EvCand { BattleUnit *bu; int dist; double ev; double score; int kst; };
	std::vector<EvCand> evCands;
	const char *evWhy = "";
	for (auto* bu : *_save->getUnits())
	{
		// AI2-H h8""")
sub(C, """			tally++;
			int dist = Position::distance2d(_unit->getPosition(), bu->getPosition());
			if (dist < _closestDist)
			{
				bool valid = false;
				if (_rifle || !_melee)""", """			tally++;
			int dist = Position::distance2d(_unit->getPosition(), bu->getPosition());
			if (evOn)
			{
				BattleAction action;
				action.actor = _unit;
				action.weapon = _attackAction.weapon;
				action.target = bu->getPosition();
				Position origin = _save->getTileEngine()->getOriginVoxel(action, 0);
				Position at;
				if (_save->getTileEngine()->canTargetUnit(&origin, bu->getTile(), &at, _unit, false))
				{
					double ev = 0.0;
					for (BattleActionType t : { BA_AIMEDSHOT, BA_SNAPSHOT, BA_AUTOSHOT })
					{
						BattleActionCost cost(t, _unit, _attackAction.weapon);
						if (!cost.haveTU())
						{
							continue;
						}
						action.type = t;
						const char *why = "";
						const double e = fireModeEffect(&action, bu, why);
						if (e < 0.0)
						{
							evWhy = why;
						}
						ev = std::max(ev, e);
					}
					const int hpMax = std::max(1, (int)bu->getBaseStats()->health);
					const double score = std::min(1.0, ev / hpMax) * (int)getTargetAttackWeight(bu) / 100.0;
					evCands.push_back({ bu, dist, ev, score, kst });
				}
			}
			if (dist < _closestDist)
			{
				bool valid = false;
				if (_rifle || !_melee)""")
sub(C, """	if (_aggroTarget)
	{
		AiProbe::fairPick(_unit, _aggroTarget, cons, pickState, pickState == AiProbe::FAIR_LAST_SEEN ? "mem" : "now", tally);
		return tally;
	}

	return 0;
}

/**
 * AI2-H h8 knowledge contract""", """	if (evOn && _aggroTarget && !evCands.empty())
	{
		const EvCand *near = nullptr, *best = nullptr;
		for (const auto &c : evCands)
		{
			if (c.bu == _aggroTarget)
			{
				near = &c;
			}
			if (!best || c.score > best->score || (c.score == best->score && c.dist < best->dist))
			{
				best = &c;
			}
		}
		const bool modelled = !*evWhy;
		const bool better = near && best != near && best->score > 1.5 * near->score;
		const bool pick = targetEv == 2 && modelled && better;
		std::ostringstream s;
		s << "[AITARGET] turn=" << _save->getTurn() << " unit=" << _unit->getId() << " tu=" << _unit->getTimeUnits()
			<< " weapon=" << (_attackAction.weapon ? _attackAction.weapon->getRules()->getType() : std::string("-"))
			<< " melee=" << (_melee ? 1 : 0) << " near=" << _aggroTarget->getId() << " best=" << best->bu->getId()
			<< " model=" << (modelled ? "1" : evWhy) << " better=" << (better ? 1 : 0) << " pick=" << (pick ? 1 : 0) << " cands=";
		for (const auto &c : evCands)
		{
			s << c.bu->getId() << ":" << (int)c.bu->getFaction() << ":" << c.dist << ":" << (int)std::lround(c.ev) << ":"
				<< (int)c.bu->getBaseStats()->health << ":" << (int)std::lround(c.score * 1000) << ";";
		}
		Log(LOG_INFO) << s.str();
		if (pick)
		{
			_evPick = best->bu;
		}
	}
	if (_aggroTarget)
	{
		AiProbe::fairPick(_unit, _aggroTarget, cons, pickState, pickState == AiProbe::FAIR_LAST_SEEN ? "mem" : "now", tally);
		return tally;
	}

	return 0;
}

/**
 * AI2-H h8 knowledge contract""")
for p, t in TEXT.items():
    p.write_bytes(t.encode("utf-8"))
print("patched")
