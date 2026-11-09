
namespace
{

int strikeTuUnit = -1, strikeTuBefore = -1;

/// STRIKE-V0 (OXCE_AI_STRIKE): 0 - off, 1 - shadow (every check, order and would-be shot written, the action not changed),
/// 2 - on.
int strikeMode()
{
	static const int m = (int)param("OXCE_AI_STRIKE", 0);
	return m;
}

/// SideContext: the shot a hostile unit can make now from where it stands at one target - the type, its TU cost, the expected
/// damage of one attack by the rules (AIModule::fireModeEffect over its uses: hit chance, the armor's rule values and damage
/// modifier, no health, no current armor) - and why there is none ("ok" when there is one worth making).
struct StrikeShot
{
	BattleActionType type = BA_NONE;
	int cost = 0;
	double dmg = 0.0;
	const char *why = "no_weapon";
};

/// SideContext: the player unit is known to the hostile side now - not out, and on a hostile unit's visible list (so its place
/// and facing are what the side sees, nothing remembered or guessed).
bool strikeKnown(const SavedBattleGame *save, const BattleUnit *t)
{
	return t && !t->isOut() && t->getFaction() == FACTION_PLAYER && fairSeenNow(save, FACTION_HOSTILE, t);
}

StrikeShot strikeShot(SavedBattleGame *save, BattleUnit *u, BattleUnit *t)
{
	static const double minDmg = param("OXCE_AI_STRIKE_MIN", 0.5);
	StrikeShot best;
	AIModule *ai = u->getAIModule();
	BattleItem *weapon = u->getMainHandWeapon();
	if (!ai || !weapon || weapon->getRules()->getBattleType() != BT_FIREARM)
	{
		return best;
	}
	// how far the checks got: 1 a fire mode, 2 its TU, 3 its ammo, 4 the line of fire, 5 the rules' estimate
	int got = 0;
	bool lofChecked = false, lof = false;
	// the turn to face the target is paid from the same TU before the shot (UnitTurnBState)
	const int d = std::abs(u->directionTo(t->getPosition()) - u->getDirection());
	const int turnTu = std::min(d, 8 - d) * u->getTurnCost();
	TileEngine *te = save->getTileEngine();
	for (BattleActionType type : {BA_AIMEDSHOT, BA_AUTOSHOT, BA_SNAPSHOT})
	{
		BattleActionCost c(type, u, weapon);
		if (c.Time <= 0)
			continue;
		got = std::max(got, 1);
		if (!c.haveTU() || c.Time + turnTu > u->getTimeUnits())
			continue;
		got = std::max(got, 2);
		if (weapon->needsAmmoForAction(type) && !static_cast<const BattleItem *>(weapon)->getAmmoForAction(type))
			continue;
		got = std::max(got, 3);
		BattleAction shot;
		shot.type = type;
		shot.actor = u;
		shot.weapon = weapon;
		shot.target = t->getPosition();
		if (!lofChecked)
		{
			Position origin = te->getOriginVoxel(shot, nullptr), scan;
			lof = te->canTargetUnit(&origin, t->getTile(), &scan, u, false);
			lofChecked = true;
		}
		if (!lof)
			break;
		got = std::max(got, 4);
		const char *fw = "";
		const double e = ai->fireModeEffect(&shot, t, fw);
		if (e < 0.0)
			continue;
		got = 5;
		const double one = e / std::max(1, u->getTimeUnits() / c.Time);
		if (best.type == BA_NONE || one > best.dmg || (one == best.dmg && c.Time < best.cost))
		{
			best.type = type;
			best.cost = c.Time;
			best.dmg = one;
		}
	}
	static const char *const whys[] = {"no_mode", "no_tu", "no_ammo", "no_lof", "no_estimate", "low_effect"};
	best.why = whys[got];
	if (got == 5 && best.dmg >= minDmg)
		best.why = "ok";
	return best;
}

/// SideContext: a hostile unit that may still act this turn and could take an order.
bool strikeShooter(const BattleUnit *u)
{
	return u && u->getFaction() == FACTION_HOSTILE && !u->isOut() && u->getStatus() == STATUS_STANDING && u->getAIModule()
		&& u->reselectAllowed() && u->getTimeUnits() > 0;
}

/// StrikeCoordinator: the side's one shared order - the target and the units it went to, alive within the side's turn only.
struct StrikeOrder
{
	int turn = -1, target = -1, id = 0, made = 0;
	bool live = false;
	std::set<int> members;
};
StrikeOrder strikeOrder_;
std::map<int, int> strikeUsed; // unit - the turn it last fired by the order (one order shot per unit per turn)

BattleUnit *strikeUnit(SavedBattleGame *save, int id)
{
	for (auto *bu : *save->getUnits())
		if (bu->getId() == id)
			return bu;
	return nullptr;
}

void strikeClose(SavedBattleGame *save, const char *why)
{
	if (strikeOrder_.live)
	{
		Log(LOG_INFO) << "[AISTRIKE] kind=close turn=" << strikeOrder_.turn << " order=" << strikeOrder_.id
			<< " target=" << strikeOrder_.target << " why=" << why << " now=" << save->getTurn();
	}
	strikeOrder_.live = false;
}

/// StrikeCoordinator: the order for this turn - the live one, or a new one when there is none: of the known targets the
/// deciding unit can usefully shoot, the one most of the side's units can usefully shoot now (then the most expected damage,
/// then the lower id); none unless at least OXCE_AI_STRIKE_SHOOTERS (2) can.
bool strikeEnsure(SavedBattleGame *save, BattleUnit *unit)
{
	static const int minShooters = (int)param("OXCE_AI_STRIKE_SHOOTERS", 2);
	static const int maxOrders = (int)param("OXCE_AI_STRIKE_ORDERS", 4);
	const int turn = save->getTurn();
	if (strikeOrder_.live && strikeOrder_.turn != turn)
		strikeClose(save, "turn_over");
	if (strikeOrder_.live)
	{
		BattleUnit *t = strikeUnit(save, strikeOrder_.target);
		if (!t || t->isOut())
			strikeClose(save, "target_out");
		else if (!strikeKnown(save, t))
			strikeClose(save, "target_lost");
	}
	if (strikeOrder_.live)
		return true;
	if (strikeOrder_.turn != turn)
	{
		strikeOrder_.turn = turn;
		strikeOrder_.made = 0;
	}
	if (strikeOrder_.made >= maxOrders)
		return false;
	BattleUnit *pick = nullptr;
	std::vector<std::pair<int, StrikeShot>> pickShooters;
	double pickSum = 0.0;
	for (auto *t : *save->getUnits())
	{
		if (!strikeKnown(save, t) || std::strcmp(strikeShot(save, unit, t).why, "ok") != 0)
			continue;
		std::vector<std::pair<int, StrikeShot>> shooters;
		double sum = 0.0;
		for (auto *u : *save->getUnits())
		{
			if (u != unit && !strikeShooter(u))
				continue;
			StrikeShot s = strikeShot(save, u, t);
			if (std::strcmp(s.why, "ok") == 0)
			{
				shooters.push_back(std::make_pair(u->getId(), s));
				sum += s.dmg;
			}
		}
		if (!pick || shooters.size() > pickShooters.size() || (shooters.size() == pickShooters.size() && sum > pickSum))
		{
			pick = t;
			pickShooters = shooters;
			pickSum = sum;
		}
	}
	if (!pick || (int)pickShooters.size() < minShooters)
	{
		Log(LOG_INFO) << "[AISTRIKE] kind=noorder turn=" << turn << " unit=" << unit->getId()
			<< " target=" << (pick ? pick->getId() : -1) << " shooters=" << pickShooters.size();
		return false;
	}
	static int orderIds = 0;
	strikeOrder_.live = true;
	strikeOrder_.target = pick->getId();
	strikeOrder_.id = ++orderIds;
	++strikeOrder_.made;
	strikeOrder_.members.clear();
	std::ostringstream m;
	for (const auto &p : pickShooters)
	{
		strikeOrder_.members.insert(p.first);
		m << (m.tellp() > 0 ? "," : "") << p.first << ":" << (int)p.second.type << ":" << p.second.cost << ":" << p.second.dmg;
	}
	Log(LOG_INFO) << "[AISTRIKE] kind=order turn=" << turn << " order=" << strikeOrder_.id << " by=" << unit->getId()
		<< " target=" << pick->getId() << " tpos=" << pick->getPosition() << " thp=" << pick->getHealth()
		<< " shooters=" << pickShooters.size() << " sum=" << pickSum << " members=" << m.str();
	return true;
}

}

void strikeBeforeThink(BattleUnit *unit)
{
	strikeTuUnit = unit->getId();
	strikeTuBefore = unit->getTimeUnits();
}

void strikeDecide(SavedBattleGame *save, BattleUnit *unit, BattleAction &action)
{
	const int mode = strikeMode();
	if (mode <= 0 || unit->getFaction() != FACTION_HOSTILE || save->getSide() != FACTION_HOSTILE)
	{
		return;
	}
	AIModule *ai = unit->getAIModule();
	const int aiMode = ai ? ai->getAIMode() : -1;
	const int tu0 = strikeTuUnit == unit->getId() ? strikeTuBefore : -1;
	const BattleActionType act = action.type;
	// the decision's class: what the unit chose and whether STRIKE may stand in for it
	const char *cls = "allowed";
	switch (act)
	{
	case BA_AUTOSHOT: case BA_SNAPSHOT: case BA_AIMEDSHOT: case BA_THROW: case BA_HIT: case BA_LAUNCH:
	case BA_MINDCONTROL: case BA_PANIC: case BA_USE:
		cls = "attack";
		break;
	default:
		break;
	}
	if (std::strcmp(cls, "attack") == 0) {}
	else if (!ai) cls = "no_ai";
	else if (aiMode == AI_ESCAPE) cls = "escape";
	else if (aiMode == AI_AMBUSH) cls = "ambush";
	else if (unit->getStatus() != STATUS_STANDING) cls = "status";
	else if (unit->getCharging()) cls = "charging";
	else if (tu0 != unit->getTimeUnits()) cls = "tu_changed";
	else if (act == BA_WALK && aiMode == AI_COMBAT) cls = "combat_move";
	else if (act == BA_WALK && save->getMissionType() == "STR_BASE_DEFENSE") cls = "mission";
	else if (act != BA_WALK && act != BA_NONE) cls = "other_act";
	// SideContext for this unit: the best useful shot it has now at a known target
	BattleUnit *best = nullptr;
	StrikeShot bestShot;
	int known = 0;
	for (auto *t : *save->getUnits())
	{
		if (!strikeKnown(save, t))
			continue;
		++known;
		StrikeShot s = strikeShot(save, unit, t);
		const bool ok = std::strcmp(s.why, "ok") == 0, bestOk = std::strcmp(bestShot.why, "ok") == 0;
		if (!best || (ok && !bestOk) || (ok == bestOk && s.dmg > bestShot.dmg))
		{
			best = t;
			bestShot = s;
		}
	}
	const char *shotWhy = known ? bestShot.why : "no_target";
	Log(LOG_INFO) << "[AISTRIKE] kind=opp turn=" << save->getTurn() << " unit=" << unit->getId() << " n=" << action.number
		<< " mode=" << aiMode << " act=" << (int)act << " tu=" << unit->getTimeUnits() << " tu0=" << tu0 << " cls=" << cls
		<< " shot=" << shotWhy << " known=" << known << " target=" << (best ? best->getId() : -1)
		<< " type=" << (int)bestShot.type << " cost=" << bestShot.cost << " dmg=" << bestShot.dmg;
	if (std::strcmp(cls, "allowed") != 0 || std::strcmp(shotWhy, "ok") != 0)
	{
		return;
	}
	// StrikeCoordinator: the shared order, then whether this unit carries it out now
	const int turn = save->getTurn();
	auto used = strikeUsed.find(unit->getId());
	if (used != strikeUsed.end() && used->second == turn)
	{
		Log(LOG_INFO) << "[AISTRIKE] kind=skip turn=" << turn << " unit=" << unit->getId() << " n=" << action.number << " why=used";
		return;
	}
	if (!strikeEnsure(save, unit))
	{
		return;
	}
	BattleUnit *target = strikeUnit(save, strikeOrder_.target);
	// OrderExecutor: the order's shot checked again just before it is handed out - target known, weapon, mode, TU, ammo, line
	// of fire and the rules' estimate from here; any failed check leaves the unit's own decision as it was
	StrikeShot s = strikeShot(save, unit, target);
	const bool member = strikeOrder_.members.count(unit->getId()) != 0;
	if (std::strcmp(s.why, "ok") != 0)
	{
		Log(LOG_INFO) << "[AISTRIKE] kind=skip turn=" << turn << " unit=" << unit->getId() << " n=" << action.number
			<< " order=" << strikeOrder_.id << " why=" << s.why << " member=" << member;
		return;
	}
	if (!member)
	{
		strikeOrder_.members.insert(unit->getId());
		Log(LOG_INFO) << "[AISTRIKE] kind=join turn=" << turn << " unit=" << unit->getId() << " order=" << strikeOrder_.id;
	}
	Log(LOG_INFO) << "[AISTRIKE] kind=exec turn=" << turn << " unit=" << unit->getId() << " n=" << action.number
		<< " order=" << strikeOrder_.id << " status=" << (mode >= 2 ? "shot" : "would") << " target=" << target->getId()
		<< " tpos=" << target->getPosition() << " thp=" << target->getHealth() << " type=" << (int)s.type << " cost=" << s.cost
		<< " dmg=" << s.dmg << " tu=" << unit->getTimeUnits() << " d0act=" << (int)act << " d0to=" << action.target
		<< " mode=" << aiMode;
	strikeUsed[unit->getId()] = turn;
	if (mode < 2)
	{
		return;
	}
	action.type = s.type;
	action.target = target->getPosition();
	action.weapon = unit->getMainHandWeapon();
	action.finalAction = false;
	action.desperate = false;
	action.run = false;
	action.kneel = false;
}
