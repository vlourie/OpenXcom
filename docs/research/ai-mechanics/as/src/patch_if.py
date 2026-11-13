"""AI ACTION SELECTION / INEFFECTIVE FIRE (GO Vitali 27.10): OXCE_AI_IF in the isolated tree c2/tree (AIModule.cpp/.h,
AiProbe.cpp) on top of the clean al3 sources (exe AL of P0/P1).

  py -3.13 patch_if.py <tree>
1 - the record only: [AIIF] for every strictly useless hostile shot (T2's rule) with what else the unit could do - the other
hand's weapon, the inventory's weapons with the TU to take them, special weapons, melee, the belt grenade, the best reachable
tile for the same weapon - and [AIIFFX] what each hostile attack changed on its target and on the attacker. Decisions as
before. Off (0) - as before."""
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
    "\t/// AI-IF: what else a unit with a useless shot could do, for the record (OXCE_AI_IF).\n\tvoid ifRecord();")
sub(H, "\tint _probeScore = INT_MIN;",
    "\tint _probeScore = INT_MIN;\n"
    "\t/// AI-IF: fireModeEffect asked by the record from another tile (_feFromSet) and with another TU budget (_feTu >= 0).\n"
    "\tbool _feFromSet = false;\n\tPosition _feFrom;\n\tint _feTu = -1;")
sub(C, '#include "../Mod/Mod.h"\n', '#include "../Mod/Mod.h"\n#include "../Mod/RuleInventory.h"\n')
sub(C, "\tif (bestCellBits() & AiProbe::BC_REACHCOST)\n",
    "\t// AI-IF (bench): the record reads the walk costs too (reachCost still answers only under BC_REACHCOST)\n"
    "\tstatic const bool ifOn = AiProbe::param(\"OXCE_AI_IF\", 0) != 0;\n"
    "\tif ((bestCellBits() & AiProbe::BC_REACHCOST) || ifOn)\n")
sub(C, "\tconst int distanceSq = _unit->distance3dToPositionSq(tpos);\n",
    "\t// AI-IF (bench): the record may ask from another tile (_feFromSet) and with another TU budget (_feTu); off - as before\n"
    "\tconst Position feFrom = _feFromSet ? _feFrom : _unit->getPosition();\n"
    "\tconst int feX = feFrom.x - tpos.x, feY = feFrom.y - tpos.y, feZ = feFrom.z - tpos.z;\n"
    "\tconst int distanceSq = _feFromSet ? feX * feX + feY * feY + feZ * feZ : _unit->distance3dToPositionSq(tpos);\n")
sub(C, "\tconst int uses = std::max(1, _unit->getTimeUnits() / tuCost);\n",
    "\tconst int uses = _feTu >= 0 ? _feTu / tuCost : std::max(1, _unit->getTimeUnits() / tuCost);\n")
sub(C, "\t\tconst Position rel = (_unit->getPosition() - tpos) * Position(16, 16, 24);\n",
    "\t\tconst Position rel = (feFrom - tpos) * Position(16, 16, 24);\n")
sub(C, """		if (_rifle)
		{
			const ProbeMark mark = probeMark('x');
			projectileAction();""", """		if (_rifle)
		{
			ifRecord();
			const ProbeMark mark = probeMark('x');
			projectileAction();""")
sub(C, """	return hit * shots * perHit * uses;
}
""", r"""	return hit * shots * perHit * uses;
}

namespace
{
/// AI-IF: the expected damage of one hit of this power after the resistance and the armour, as fireModeEffect's.
double ifPerHit(int power, const RuleDamageType *dt, float modifier, double armor)
{
	const float armorCut = dt->ArmorEffectiveness > 0.0f ? (float)armor * dt->ArmorEffectiveness : 0.0f;
	auto afterArmor = [&](int roll)
	{
		int damage = (int)floor(roll * modifier);
		damage -= armorCut;
		return std::max(damage, 0);
	};
	double perHit = 0.0;
	if (dt->RandomType == DRT_UFO_WITH_TWO_DICE)
	{
		const double n = (double)(power + 1) * (power + 1);
		for (int s = 0; s <= 2 * power; ++s)
		{
			perHit += afterArmor(s) * (std::min(s, 2 * power - s) + 1) / n;
		}
	}
	else
	{
		const int lo = dt->getRandomDamage(power, 1);
		const int hi = dt->getRandomDamage(power, 2);
		for (int d = lo; d <= hi; ++d)
		{
			perHit += afterArmor(d);
		}
		perHit /= (hi - lo + 1);
	}
	return perHit;
}
/// AI-IF: the largest roll's damage left after the resistance and the weakest ruleset side (> 0 - it can get through).
int ifThrough(int power, const RuleDamageType *dt, float modifier, int armor)
{
	int d = (int)floor(dt->getRandomDamage(power, 2) * modifier);
	d -= armor * (dt->ArmorEffectiveness > 0.0f ? dt->ArmorEffectiveness : 0.0f);
	return d;
}
int ifRulesetMin(const Armor *a)
{
	return std::max(0, std::min({ a->getFrontArmor(), a->getLeftSideArmor(), a->getRightSideArmor(), a->getRearArmor(), a->getUnderArmor() }));
}
}

/**
 * AI-IF (bench): OXCE_AI_IF >= 1 - the record of a strictly useless hostile shot (AI-T2's rule: the unit has the TU for a fire
 * mode, the honest AI2-A verdict finds nothing besides the damage through the armour for every such mode, and fireModeEffect
 * expects under 0.5 HP) and of everything else the unit could do instead, each valued as fireModeEffect values a shot (the
 * nominal accuracy, the ruleset armour and resistance, the TU it has for it). Only the seen lawful targets the nearest pick
 * takes. Reads only, no RNG, no decision changes; called in setupAttack right before projectileAction.
 *  alt   - the same weapon at another seen target with a line of fire;
 *  hand  - the other hand's firearm (taking it costs no TU, as for the player);
 *  inv   - the firearms and melee items in the inventory: slot, the TU to move it to a hand, a free hand, the best value
 *          with the TU left after the move (TYPE:slot:move:free:ev10:target:why);
 *  spec  - the unit's special firearm (the AI uses it only with both hands empty);
 *  melee - the melee item (getUtilityWeapon) and the firearm's own blow: at an adjacent target now or from a reachable tile
 *          next to it (TYPE:hitTU:target:walk:ev10:through);
 *  gren  - the belt grenade as grenadeAction weighs it: TU needed and had, explosiveEfficacy at the target, a valid throw, the
 *          largest roll left after the ruleset under armour at the centre (TYPE:need:have:eff:valid:through);
 *  pos   - the same weapon from the best reachable tile (_reachableWithAttack, the walk cost from findReachable) at a seen
 *          target with a line of fire from there (ev10:x,y,z:walk:target).
 */
void AIModule::ifRecord()
{
	static const int mode = (int)AiProbe::param("OXCE_AI_IF", 0);
	if (mode <= 0 || !_aggroTarget || !_attackAction.weapon || _unit->getFaction() != FACTION_HOSTILE || !AiProbe::active())
	{
		return;
	}
	TileEngine *te = _save->getTileEngine();
	const Mod *mod = _save->getMod();
	const int tu = _unit->getTimeUnits();
	const int energy = _unit->getEnergy();
	// the best expected damage of weapon w at bu with the TU budget; why: empty - nothing but the damage can act
	auto evAt = [&](BattleItem *w, BattleUnit *bu, int budget, std::string &why, bool verdict)
	{
		why.clear();
		double ev = 0.0;
		BattleAction action;
		action.actor = _unit;
		action.weapon = w;
		action.target = bu->getPosition();
		for (BattleActionType t : { BA_AIMEDSHOT, BA_SNAPSHOT, BA_AUTOSHOT })
		{
			const BattleActionCost cost(t, _unit, w);
			if (cost.Time <= 0 || cost.Time > budget || cost.Energy > energy)
			{
				continue;
			}
			if (verdict)
			{
				std::string terms;
				const int v = zeroEffectVerdictHonest(_save, _unit, t, w, bu, &terms, true);
				const size_t at = terms.find("\"why\":\"");
				const std::string vwhy = at == std::string::npos ? std::string("?") : terms.substr(at + 7, terms.find('"', at + 7) - at - 7);
				if (why.empty() && v != AIZ_ZERO && vwhy != "armor_hidden")
				{
					why = vwhy;
				}
			}
			action.type = t;
			const char *fw = "";
			_feTu = budget;
			const double e = fireModeEffect(&action, bu, fw);
			_feTu = -1;
			if (e < 0.0 && why.empty())
			{
				why = fw;
			}
			ev = std::max(ev, e);
		}
		return ev;
	};
	// the current shot: only a strictly useless one is recorded
	std::string why0;
	const double ev0 = evAt(_attackAction.weapon, _aggroTarget, tu, why0, true);
	bool anyMode = false;
	for (BattleActionType t : { BA_AIMEDSHOT, BA_SNAPSHOT, BA_AUTOSHOT })
	{
		const BattleActionCost cost(t, _unit, _attackAction.weapon);
		anyMode = anyMode || (cost.Time > 0 && cost.Time <= tu && cost.Energy <= energy);
	}
	if (!anyMode || !why0.empty() || ev0 >= 0.5)
	{
		return;
	}
	// the seen lawful targets as the nearest pick takes them, and which have a line of fire from here
	std::vector<BattleUnit*> seen;
	std::vector<bool> lof;
	for (auto* bu : *_save->getUnits())
	{
		if (!validTarget(bu, true, true) || !te->visible(_unit, bu->getTile()))
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
		Position origin = te->getOriginVoxel(action, 0);
		Position at;
		seen.push_back(bu);
		lof.push_back(te->canTargetUnit(&origin, bu->getTile(), &at, _unit, false));
	}
	// the best value of a firearm over the seen targets with a line of fire
	auto bestFire = [&](BattleItem *w, int budget, BattleUnit *skip, int &who, std::string &whyBest)
	{
		double best = 0.0;
		who = -1;
		whyBest = "-";
		for (size_t i = 0; i < seen.size(); ++i)
		{
			if (!lof[i] || seen[i] == skip)
			{
				continue;
			}
			std::string why;
			const double ev = evAt(w, seen[i], budget, why, true);
			if (who < 0 || ev > best)
			{
				best = ev;
				who = seen[i]->getId();
				whyBest = why.empty() ? "-" : why;
			}
		}
		return best;
	};
	std::ostringstream s;
	s << "[AIIF] turn=" << _save->getTurn() << " unit=" << _unit->getId() << " tu=" << tu << " en=" << energy
		<< " weapon=" << _attackAction.weapon->getRules()->getType() << " target=" << _aggroTarget->getId()
		<< " tfac=" << (int)_aggroTarget->getFaction() << " dist=" << Position::distance2d(_unit->getPosition(), _aggroTarget->getPosition())
		<< " ev10=" << (int)std::lround(ev0 * 10) << " seen=" << seen.size();
	{
		int who = -1;
		std::string w;
		const double ev = bestFire(_attackAction.weapon, tu, _aggroTarget, who, w);
		s << " alt=" << (int)std::lround(ev * 10) << ":" << who << ":" << w;
	}
	// the other hand
	s << " hand=";
	{
		BattleItem *other = nullptr;
		for (BattleItem *h : { _unit->getRightHandWeapon(), _unit->getLeftHandWeapon() })
		{
			if (h && h != _attackAction.weapon)
			{
				other = h;
			}
		}
		if (other && other->getRules()->getBattleType() == BT_FIREARM && other->haveAnyAmmo())
		{
			int who = -1;
			std::string w;
			const double ev = bestFire(other, tu, nullptr, who, w);
			s << other->getRules()->getType() << ":" << (int)std::lround(ev * 10) << ":" << who << ":" << w;
		}
		else
		{
			s << (other ? other->getRules()->getType() + ":notfire" : std::string("-"));
		}
	}
	// the inventory
	RuleInventory *rightHand = mod->getInventoryRightHand();
	RuleInventory *leftHand = mod->getInventoryLeftHand();
	const bool freeHand = !_unit->getRightHandWeapon() || !_unit->getLeftHandWeapon();
	RuleInventory *toHand = !_unit->getRightHandWeapon() ? rightHand : leftHand;
	std::vector<BattleItem*> meleeItems;
	if (BattleItem *m = _unit->getUtilityWeapon(BT_MELEE))
	{
		meleeItems.push_back(m);
	}
	if (_attackAction.weapon->getRules()->getCostMelee().Time > 0)
	{
		meleeItems.push_back(_attackAction.weapon);
	}
	s << " inv=";
	int nInv = 0;
	for (BattleItem *it : *_unit->getInventory())
	{
		const RuleInventory *slot = it->getSlot();
		if (!slot || slot->getType() == INV_HAND)
		{
			continue;
		}
		const BattleType bt = it->getRules()->getBattleType();
		if (bt != BT_FIREARM && bt != BT_MELEE)
		{
			continue;
		}
		const int move = slot->getCost(toHand);
		s << (nInv++ ? ";" : "") << it->getRules()->getType() << ":" << slot->getId() << ":" << move << ":" << (freeHand ? 1 : 0);
		if (bt == BT_FIREARM && it->haveAnyAmmo())
		{
			int who = -1;
			std::string w;
			const double ev = bestFire(it, tu - move, nullptr, who, w);
			s << ":" << (int)std::lround(ev * 10) << ":" << who << ":" << w;
		}
		else
		{
			s << ":" << (bt == BT_MELEE ? "melee" : "noammo");
		}
	}
	if (!nInv)
	{
		s << "-";
	}
	// the special firearm
	s << " spec=";
	if (BattleItem *sp = _unit->getSpecialWeapon(BT_FIREARM))
	{
		int who = -1;
		std::string w;
		const double ev = bestFire(sp, tu, nullptr, who, w);
		s << sp->getRules()->getType() << ":" << (int)std::lround(ev * 10) << ":" << who << ":" << w;
	}
	else
	{
		s << "-";
	}
	// melee: an adjacent target now, or the cheapest reachable tile next to one (the walk costs of _reachableWithAttack)
	s << " melee=";
	int nMelee = 0;
	for (BattleItem *m : meleeItems)
	{
		BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(BA_HIT, _unit, m);
		if (!attack.damage_item)
		{
			continue;
		}
		const RuleItem *item = attack.damage_item->getRules();
		const bool bonusPath = item->getBattleType() != BT_MELEE;
		const int power = bonusPath ? item->getMeleeBonus(attack) : item->getPowerBonus(attack);
		const RuleDamageType *dt = bonusPath ? item->getMeleeType() : item->getDamageType();
		const int hitTu = _unit->getActionTUs(BA_HIT, m).Time;
		if (!dt || hitTu <= 0)
		{
			continue;
		}
		const double acc = Clamp(BattleUnit::getFiringAccuracy(attack, mod), 0, 100) / 100.0;
		double best = -1.0;
		int bestWho = -1, bestWalk = -1, bestThrough = 0;
		for (BattleUnit *bu : seen)
		{
			const Position tp = bu->getPosition();
			int walk = -1;
			if (Position::distance2d(_unit->getPosition(), tp) <= 1 && _unit->getPosition().z == tp.z)
			{
				walk = 0;
			}
			else if (!_reachCost.empty())
			{
				for (int dx = -1; dx <= 1; ++dx)
				{
					for (int dy = -1; dy <= 1; ++dy)
					{
						const Position p = tp + Position(dx, dy, 0);
						if ((dx || dy) && _save->getTile(p))
						{
							const int c = _reachCost[_save->getTileIndex(p)];
							if (c >= 0 && (walk < 0 || c < walk))
							{
								walk = c;
							}
						}
					}
				}
			}
			if (walk < 0 || tu - walk < hitTu)
			{
				continue;
			}
			const Armor *a = bu->getArmor();
			const float modifier = a->getDamageModifier(dt->ResistType);
			const double ev = acc * ifPerHit(power, dt, modifier, a->getFrontArmor()) * ((tu - walk) / hitTu);
			if (ev > best)
			{
				best = ev;
				bestWho = bu->getId();
				bestWalk = walk;
				bestThrough = ifThrough(power, dt, modifier, ifRulesetMin(a));
			}
		}
		s << (nMelee++ ? ";" : "") << item->getType() << ":" << hitTu << ":" << bestWho << ":" << bestWalk << ":"
			<< (best < 0 ? -1 : (int)std::lround(best * 10)) << ":" << bestThrough;
	}
	if (!nMelee)
	{
		s << "-";
	}
	// the belt grenade, as grenadeAction weighs it at this target
	s << " gren=";
	if (BattleItem *g = _unit->getGrenadeFromBelt(_save))
	{
		BattleAction action;
		action.weapon = g;
		action.type = BA_THROW;
		action.actor = _unit;
		action.updateTU();
		action.Time += 4;
		action += _unit->getActionTUs(BA_PRIME, g);
		const int radius = g->getRules()->getExplosionRadius(BattleActionAttack::GetBeforeShoot(action));
		const Position at = _aggroTarget->getPosition();
		const int eff = explosiveEfficacy(at, _unit, radius, _attackAction.diff, true);
		Position originVoxel = te->getOriginVoxel(action, 0);
		Position targetVoxel = at.toVoxel() + Position(8, 8, (2 + -_save->getTile(at)->getTerrainLevel()));
		action.target = at;
		const bool valid = te->validateThrow(action, originVoxel, targetVoxel, _save->getDepth());
		BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(action);
		const RuleItem *gr = g->getRules();
		const RuleDamageType *dt = gr->getDamageType();
		const Armor *a = _aggroTarget->getArmor();
		const int through = dt ? ifThrough(gr->getPowerBonus(attack), dt, a->getDamageModifier(dt->ResistType), a->getUnderArmor()) : 0;
		s << gr->getType() << ":" << action.Time << ":" << tu << ":" << eff << ":" << (valid ? 1 : 0) << ":" << through;
	}
	else
	{
		s << "-";
	}
	// the same weapon from the best reachable tile with a line of fire from there
	s << " pos=";
	{
		struct Cand { double ev; Position p; int walk; BattleUnit *bu; };
		std::vector<Cand> cands;
		_feFromSet = true;
		for (int index : _reachableWithAttack)
		{
			const int walk = index >= 0 && index < (int)_reachCost.size() ? _reachCost[index] : -1;
			const Position p = _save->getTileCoords(index);
			if (walk <= 0 || p == _unit->getPosition())
			{
				continue;
			}
			_feFrom = p;
			for (BattleUnit *bu : seen)
			{
				std::string why;
				const double ev = evAt(_attackAction.weapon, bu, tu - walk, why, false);
				if (ev >= 0.5)
				{
					cands.push_back({ ev, p, walk, bu });
				}
			}
		}
		_feFromSet = false;
		std::sort(cands.begin(), cands.end(), [](const Cand &l, const Cand &r) { return l.ev > r.ev || (l.ev == r.ev && l.walk < r.walk); });
		int checked = 0;
		const Cand *found = nullptr;
		for (const Cand &c : cands)
		{
			if (++checked > 15)
			{
				break;
			}
			BattleAction action;
			action.actor = _unit;
			action.weapon = _attackAction.weapon;
			action.target = c.bu->getPosition();
			Position origin = te->getOriginVoxel(action, _save->getTile(c.p));
			Position at;
			if (te->canTargetUnit(&origin, c.bu->getTile(), &at, _unit, false))
			{
				found = &c;
				break;
			}
		}
		if (found)
		{
			s << (int)std::lround(found->ev * 10) << ":" << found->p.x << "," << found->p.y << "," << found->p.z << ":" << found->walk
				<< ":" << found->bu->getId();
		}
		else
		{
			s << "-:" << cands.size();
		}
	}
	s << " tiles=" << _reachableWithAttack.size();
	Log(LOG_INFO) << s.str();
}
""")
sub(P, "void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)\n{\n\tif (!active())\n\t{\n\t\treturn;\n\t}\n",
    """namespace
{
/// AI-IF (bench): OXCE_AI_IF >= 1 - a hostile attack's target and the attacker as they were at the decision; the next decision
/// of anyone (the attack has played out by then) writes what changed as [AIIFFX]. Plain reads for the record only.
struct IfFx
{
	int unit = -1, target = -1, turn = 0, side = 0, act = 0;
	int v[13] = {}, a[5] = {};
};
IfFx ifFx;
void ifState(const BattleUnit *bu, int *v)
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
void ifSelf(const BattleUnit *bu, int *a)
{
	a[0] = bu->getHealth();
	a[1] = bu->getStunlevel();
	a[2] = bu->getFatalWounds();
	a[3] = bu->getMorale();
	a[4] = (int)bu->getStatus();
}
void ifFlush(SavedBattleGame *save)
{
	if (ifFx.unit < 0)
	{
		return;
	}
	const BattleUnit *t = nullptr, *u = nullptr;
	for (const auto *bu : *save->getUnits())
	{
		if (bu->getId() == ifFx.target)
		{
			t = bu;
		}
		if (bu->getId() == ifFx.unit)
		{
			u = bu;
		}
	}
	if (t && u)
	{
		int now[13], self[5];
		ifState(t, now);
		ifSelf(u, self);
		std::ostringstream s;
		s << "[AIIFFX] turn=" << ifFx.turn << " unit=" << ifFx.unit << " act=" << ifFx.act << " target=" << ifFx.target
			<< " later=" << (save->getTurn() != ifFx.turn || (int)save->getSide() != ifFx.side ? 1 : 0)
			<< " st=" << ifFx.v[12] << ">" << now[12] << " d=";
		for (int i = 0; i < 12; ++i)
		{
			s << (i ? "," : "") << now[i] - ifFx.v[i];
		}
		s << " self=" << self[0] - ifFx.a[0] << "," << self[1] - ifFx.a[1] << "," << self[2] - ifFx.a[2] << "," << self[3] - ifFx.a[3]
			<< " sst=" << ifFx.a[4] << ">" << self[4];
		Log(LOG_INFO) << s.str();
	}
	ifFx.unit = -1;
}
}

void logDecision(SavedBattleGame *save, BattleUnit *unit, const BattleAction &action)
{
	if (!active())
	{
		return;
	}
	static const int ifOn = (int)param("OXCE_AI_IF", 0);
	if (ifOn >= 1)
	{
		ifFlush(save);
	}
""")
sub(P, "\tfairDecision(save, unit, action);\n\tif (record())\n", """	if (ifOn >= 1 && target && unit->getFaction() == FACTION_HOSTILE && (action.type == BA_AUTOSHOT || action.type == BA_SNAPSHOT
		|| action.type == BA_AIMEDSHOT || action.type == BA_HIT || action.type == BA_THROW))
	{
		ifFx.unit = unit->getId();
		ifFx.target = target->getId();
		ifFx.turn = save->getTurn();
		ifFx.side = (int)save->getSide();
		ifFx.act = (int)action.type;
		ifState(target, ifFx.v);
		ifSelf(unit, ifFx.a);
	}
	fairDecision(save, unit, action);
	if (record())
""")
for p, t in TEXT.items():
    p.write_bytes(t.encode("utf-8"))
print("patched")
