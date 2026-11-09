
namespace
{

/// MISSION_DIRECTOR_V0 (OXCE_AI_MDIR): 0 - off, 1 - shadow: [AIMISSION] lines about what a base defense asks of the hostile side and what comes of
/// it, the plan and the orders written, nothing changed; 2 - the orders on.
int missionMode()
{
	static const int m = (int)param("OXCE_AI_MDIR", 0);
	return m;
}

bool missionOn(SavedBattleGame *save)
{
	return missionMode() > 0 && save->getMissionType() == "STR_BASE_DEFENSE";
}

std::string missionXyz(const Position &p)
{
	std::ostringstream s;
	s << p.x << "," << p.y << "," << p.z;
	return s.str();
}

/// MissionContext: the rule's objects. A facility counts as demolished after the battle when the module map's cell of its corner is at 0
/// (DebriefingState), so the objectives are the facilities' cells; the module tiles of each cell at any level (calculateModuleMap counts them all).
/// The side's knowledge is what the engine's own protocol reads for every hostile unit from the first turn: the module map, the tiles' objects, the
/// target nodes. No player unit is looked at.
std::map<std::pair<int, int>, std::vector<Position> > missionTiles_;
std::map<std::pair<int, int>, std::string> missionFacs_;
bool missionKnown_ = false;

void missionKnow(SavedBattleGame *save)
{
	if (missionKnown_)
	{
		return;
	}
	missionKnown_ = true;
	for (int i = 0; i < save->getMapSizeXYZ(); ++i)
	{
		Tile *t = save->getTile(i);
		MapData *md = t ? t->getMapData(O_OBJECT) : nullptr;
		if (md && md->isBaseModule())
		{
			const Position p = t->getPosition();
			missionTiles_[std::make_pair(p.x / 10, p.y / 10)].push_back(p);
		}
	}
	for (auto *base : *save->getGeoscapeSave()->getBases())
	{
		if (base->isInBattlescape())
		{
			for (auto *fac : *base->getFacilities())
			{
				missionFacs_[std::make_pair(fac->getX(), fac->getY())] = fac->getRules()->getType();
			}
		}
	}
}

/// The conditions of the module protocol (AIModule::setupPatrol) and the most one shot of this unit can do to a tile (TileDamageMethod 1: up to
/// 150% of the power, times ToTile); 0 - it is no fighter for this task.
double missionMaxTile(BattleUnit *u)
{
	if (u->isOut() || u->getOriginalFaction() != FACTION_HOSTILE || u->getArmor()->getSize() != 1)
	{
		return 0.0;
	}
	BattleItem *w = u->getMainHandWeapon();
	const BattleItem *ammo = w ? w->getAmmoForAction(BA_SNAPSHOT) : nullptr;
	if (!ammo || !w->getRules()->getAccuracySnap() || w->getRules()->getArcingShot() || ammo->getRules()->getArcingShot())
	{
		return 0.0;
	}
	const RuleDamageType *dt = ammo->getRules()->getDamageType();
	if (!dt->isDirect() || dt->ToTile <= 0.01f)
	{
		return 0.0;
	}
	return 1.5 * ammo->getRules()->getPower() * dt->ToTile;
}

/// The nearest module tile of a cell this unit's snap shot could break from `from` (0 - where it stands): an object still a module, the armor within
/// the shot's reach, and the line of fire ending on that very object, checked the way ProjectileFlyBState aims at a tile.
bool missionAim(SavedBattleGame *save, BattleUnit *u, Tile *from, const std::pair<int, int> &cell, Position &out, int &armor)
{
	const auto it = missionTiles_.find(cell);
	if (it == missionTiles_.end())
	{
		return false;
	}
	const double reach = missionMaxTile(u);
	const Position at = from ? from->getPosition() : u->getPosition();
	std::vector<std::pair<int, Position> > near;
	for (const Position &p : it->second)
	{
		near.push_back(std::make_pair(Position::distanceSq(at, p), p));
	}
	std::stable_sort(near.begin(), near.end(), [](const std::pair<int, Position> &a, const std::pair<int, Position> &b) { return a.first < b.first; });
	TileEngine *te = save->getTileEngine();
	BattleAction a;
	a.actor = u;
	a.type = BA_SNAPSHOT;
	a.weapon = u->getMainHandWeapon();
	for (const auto &n : near)
	{
		Tile *t = save->getTile(n.second);
		MapData *md = t ? t->getMapData(O_OBJECT) : nullptr;
		if (!md || !md->isBaseModule() || md->getArmor() > reach)
		{
			continue;
		}
		a.target = n.second;
		Position origin = te->getOriginVoxel(a, from);
		Position scan;
		if (!te->canTargetTile(&origin, t, O_OBJECT, &scan, u, false))
		{
			continue;
		}
		std::vector<Position> impact;
		const int line = te->calculateLineVoxel(origin, scan, false, &impact, u);
		if (line == V_OBJECT && !impact.empty() && impact.front().toTile() == n.second)
		{
			out = n.second;
			armor = md->getArmor();
			return true;
		}
	}
	return false;
}

std::string missionAlt(SavedBattleGame *save, BattleUnit *u)
{
	missionKnow(save);
	Position alt;
	int armor = 0;
	const Position p = u->getPosition();
	if (missionMaxTile(u) > 0.0 && missionAim(save, u, nullptr, std::make_pair(p.x / 10, p.y / 10), alt, armor))
	{
		std::ostringstream s;
		s << " alt=" << missionXyz(alt) << " altarmor=" << armor;
		return s.str();
	}
	return " alt=-";
}

/// MissionPlanner: one objective at a time - DEMOLISH_OBJECTIVE, one facility - and 2 to 4 fighters for it, each with a target node of that room it
/// has a path to and a module it could break from there.
struct MissionPlan
{
	std::pair<int, int> cell = std::make_pair(-1, -1);
	int turn = -1;
	std::map<int, Node *> fighters;
};
MissionPlan missionPlan_;

void missionMakePlan(SavedBattleGame *save, const char *why)
{
	auto &grid = save->getModuleMap();
	std::vector<BattleUnit *> all;
	for (auto *u : *save->getUnits())
	{
		if (u->getFaction() == FACTION_HOSTILE && missionMaxTile(u) > 0.0)
		{
			all.push_back(u);
		}
	}
	struct Candidate
	{
		double score;
		std::pair<int, int> cell;
		std::vector<Node *> nodes;
	};
	std::vector<Candidate> cands;
	for (const auto &f : missionFacs_)
	{
		const int left = grid[f.first.first][f.first.second].second;
		if (left <= 0)
		{
			continue;
		}
		Candidate c;
		c.cell = f.first;
		for (auto *node : *save->getNodes())
		{
			const Position p = node->getPosition();
			if (!node->isDummy() && node->isTarget() && !node->isAllocated() && p.x / 10 == c.cell.first && p.y / 10 == c.cell.second)
			{
				c.nodes.push_back(node);
			}
		}
		const size_t n = std::min<size_t>(4, std::min(c.nodes.size(), all.size()));
		if (n < 2)
		{
			continue;
		}
		// about the turns it takes: the tiles shared out among the fighters, and the walk of the nearest of them
		std::vector<double> dist;
		for (auto *u : all)
		{
			dist.push_back(std::sqrt((double)Position::distanceSq(u->getPosition(), c.nodes.front()->getPosition())));
		}
		std::sort(dist.begin(), dist.end());
		double sum = 0.0;
		for (size_t i = 0; i < n; ++i)
		{
			sum += dist[i];
		}
		c.score = (double)left / n + sum / n / 10.0;
		cands.push_back(c);
	}
	std::stable_sort(cands.begin(), cands.end(), [](const Candidate &a, const Candidate &b) { return a.score < b.score; });
	Pathfinding *pf = save->getPathfinding();
	missionPlan_.cell = std::make_pair(-1, -1);
	missionPlan_.fighters.clear();
	for (const Candidate &c : cands)
	{
		std::map<int, Node *> chosen;
		std::set<int> used;
		for (auto *node : c.nodes)
		{
			if (chosen.size() >= 4)
			{
				break;
			}
			std::vector<std::pair<int, BattleUnit *> > near;
			for (auto *u : all)
			{
				near.push_back(std::make_pair(Position::distanceSq(u->getPosition(), node->getPosition()), u));
			}
			std::stable_sort(near.begin(), near.end(), [](const std::pair<int, BattleUnit *> &a, const std::pair<int, BattleUnit *> &b) { return a.first < b.first; });
			int tries = 0;
			for (const auto &n : near)
			{
				BattleUnit *u = n.second;
				if (used.count(u->getId()) || ++tries > 6)
				{
					continue;
				}
				Position aim;
				int armor = 0;
				if (!missionAim(save, u, save->getTile(node->getPosition()), c.cell, aim, armor))
				{
					continue;
				}
				bool path = u->getPosition() == node->getPosition();
				if (!path)
				{
					pf->calculate(u, node->getPosition(), BAM_NORMAL);
					path = pf->getStartDirection() != -1;
					pf->abortPath();
				}
				if (path)
				{
					chosen[u->getId()] = node;
					used.insert(u->getId());
					break;
				}
			}
		}
		if (chosen.size() >= 2)
		{
			missionPlan_.cell = c.cell;
			missionPlan_.fighters = chosen;
			std::ostringstream s;
			for (const auto &f : chosen)
			{
				s << (s.tellp() > 0 ? ";" : "") << f.first << ">" << missionXyz(f.second->getPosition());
			}
			const int left = grid[c.cell.first][c.cell.second].second;
			Log(LOG_INFO) << "[AIMISSION] what=objective turn=" << save->getTurn() << " cell=" << c.cell.first << "," << c.cell.second << " fac=" << missionFacs_[c.cell]
				<< " left=" << left << " score=" << c.score << " why=" << why;
			Log(LOG_INFO) << "[AIMISSION] what=plan turn=" << save->getTurn() << " cell=" << c.cell.first << "," << c.cell.second << " fighters=" << s.str();
			return;
		}
	}
	Log(LOG_INFO) << "[AIMISSION] what=noplan turn=" << save->getTurn() << " why=" << why << " candidates=" << cands.size() << " fighters=" << all.size();
}

/// MissionExecutor's check of the plan with each think: a new plan when there is none this turn, its objective is demolished, or under two fighters are left.
void missionRefresh(SavedBattleGame *save)
{
	missionKnow(save);
	const int turn = save->getTurn();
	const char *why = nullptr;
	if (missionPlan_.cell.first < 0)
	{
		if (missionPlan_.turn != turn)
		{
			why = "none";
		}
	}
	else if (save->getModuleMap()[missionPlan_.cell.first][missionPlan_.cell.second].second <= 0)
	{
		Log(LOG_INFO) << "[AIMISSION] what=done turn=" << turn << " cell=" << missionPlan_.cell.first << "," << missionPlan_.cell.second << " fac=" << missionFacs_[missionPlan_.cell];
		why = "done";
	}
	else
	{
		for (auto it = missionPlan_.fighters.begin(); it != missionPlan_.fighters.end();)
		{
			BattleUnit *u = nullptr;
			for (auto *b : *save->getUnits())
			{
				if (b->getId() == it->first)
				{
					u = b;
					break;
				}
			}
			if (!u || missionMaxTile(u) <= 0.0 || u->getFaction() != FACTION_HOSTILE)
			{
				Log(LOG_INFO) << "[AIMISSION] what=release turn=" << turn << " unit=" << it->first << " why=out";
				it = missionPlan_.fighters.erase(it);
			}
			else
			{
				++it;
			}
		}
		if (missionPlan_.fighters.size() < 2)
		{
			why = "few";
		}
	}
	missionPlan_.turn = turn;
	if (why)
	{
		missionMakePlan(save, why);
	}
}

/// One dump per battle: the facilities behind the module map, every module tile, every target node, what each hostile unit carries.
void missionDump(SavedBattleGame *save)
{
	missionKnow(save);
	Log(LOG_INFO) << "[AIMISSION] what=start size=" << save->getMapSizeX() << "," << save->getMapSizeY() << "," << save->getMapSizeZ()
		<< " destroyfac=" << (save->getMod()->getAIDestroyBaseFacilities() ? 1 : 0) << " mode=" << missionMode();
	for (const auto &f : missionFacs_)
	{
		Log(LOG_INFO) << "[AIMISSION] what=fac at=" << f.first.first << "," << f.first.second << " type=" << f.second;
	}
	for (const auto &c : missionTiles_)
	{
		for (const Position &p : c.second)
		{
			Log(LOG_INFO) << "[AIMISSION] what=mtile at=" << missionXyz(p) << " armor=" << save->getTile(p)->getMapData(O_OBJECT)->getArmor();
		}
	}
	auto &grid = save->getModuleMap();
	for (auto *node : *save->getNodes())
	{
		if (!node->isDummy() && node->isTarget())
		{
			const Position p = node->getPosition();
			Log(LOG_INFO) << "[AIMISSION] what=node at=" << missionXyz(p) << " grid=" << p.x / 10 << "," << p.y / 10
				<< " left=" << grid[p.x / 10][p.y / 10].second;
		}
	}
	for (auto *u : *save->getUnits())
	{
		if (u->getOriginalFaction() != FACTION_HOSTILE || u->isOut())
		{
			continue;
		}
		BattleItem *w = u->getMainHandWeapon();
		const BattleItem *ammo = w ? w->getAmmoForAction(BA_SNAPSHOT) : nullptr;
		const RuleDamageType *dt = ammo ? ammo->getRules()->getDamageType() : nullptr;
		Log(LOG_INFO) << "[AIMISSION] what=unit id=" << u->getId() << " at=" << missionXyz(u->getPosition()) << " size=" << u->getArmor()->getSize()
			<< " weapon=" << (w ? w->getRules()->getType() : std::string("-")) << " power=" << (ammo ? ammo->getRules()->getPower() : 0)
			<< " totile=" << (dt ? dt->ToTile : 0.0f) << " method=" << (dt ? dt->TileDamageMethod : 0) << " protocol=" << (missionMaxTile(u) > 0.0 ? 1 : 0);
	}
}

}

void missionState(SavedBattleGame *save, const char *when)
{
	if (!missionOn(save) || (std::strcmp(when, "aistart") != 0 && std::strcmp(when, "end") != 0))
	{
		return;
	}
	static bool dumped = false;
	if (!dumped)
	{
		dumped = true;
		missionDump(save);
	}
	std::ostringstream s;
	auto &grid = save->getModuleMap();
	for (size_t x = 0; x < grid.size(); ++x)
	{
		for (size_t y = 0; y < grid[x].size(); ++y)
		{
			if (grid[x][y].first > 0)
			{
				s << (s.tellp() > 0 ? " " : "") << x << "," << y << "=" << grid[x][y].second << "/" << grid[x][y].first;
			}
		}
	}
	Log(LOG_INFO) << "[AIMISSION] what=grid when=" << when << " turn=" << save->getTurn() << " left: " << s.str();
}

bool missionRedirect(SavedBattleGame *save, BattleUnit *unit, const Node *toNode)
{
	if (!missionOn(save))
	{
		return false;
	}
	missionRefresh(save);
	const auto it = missionPlan_.fighters.find(unit->getId());
	if (missionMode() < 2 || it == missionPlan_.fighters.end())
	{
		return false;
	}
	if (it->second != toNode)
	{
		return true;
	}
	// on the way through the objective's room, with a module it can break already in reach
	Position aim;
	int armor = 0;
	const Position p = unit->getPosition();
	return p.x / 10 == missionPlan_.cell.first && p.y / 10 == missionPlan_.cell.second && missionAim(save, unit, nullptr, missionPlan_.cell, aim, armor);
}

int missionOrder(SavedBattleGame *save, BattleUnit *unit, Node *&node, Position &tile)
{
	if (!missionOn(save))
	{
		return 0;
	}
	missionRefresh(save);
	const auto it = missionPlan_.fighters.find(unit->getId());
	if (it == missionPlan_.fighters.end())
	{
		return 0;
	}
	const int on = missionMode() >= 2;
	const Position p = unit->getPosition();
	Position aim;
	int armor = 0;
	if (p.x / 10 == missionPlan_.cell.first && p.y / 10 == missionPlan_.cell.second && missionAim(save, unit, nullptr, missionPlan_.cell, aim, armor))
	{
		Log(LOG_INFO) << "[AIMISSION] what=task turn=" << save->getTurn() << " unit=" << unit->getId() << " kind=shoot from=" << missionXyz(p) << " tile=" << missionXyz(aim)
			<< " armor=" << armor << " tu=" << unit->getTimeUnits() << " on=" << on;
		tile = aim;
		return on ? 1 : 0;
	}
	if (p == it->second->getPosition())
	{
		Log(LOG_INFO) << "[AIMISSION] what=release turn=" << save->getTurn() << " unit=" << unit->getId() << " why=nomodule from=" << missionXyz(p);
		missionPlan_.fighters.erase(it);
		return 0;
	}
	Pathfinding *pf = save->getPathfinding();
	pf->calculate(unit, it->second->getPosition(), BAM_NORMAL);
	const bool path = pf->getStartDirection() != -1;
	pf->abortPath();
	if (!path)
	{
		Log(LOG_INFO) << "[AIMISSION] what=release turn=" << save->getTurn() << " unit=" << unit->getId() << " why=nopath from=" << missionXyz(p);
		missionPlan_.fighters.erase(it);
		return 0;
	}
	Log(LOG_INFO) << "[AIMISSION] what=task turn=" << save->getTurn() << " unit=" << unit->getId() << " kind=walk from=" << missionXyz(p) << " node=" << missionXyz(it->second->getPosition())
		<< " tu=" << unit->getTimeUnits() << " on=" << on;
	node = it->second;
	return on ? 2 : 0;
}

void missionModuleShot(SavedBattleGame *save, BattleUnit *unit, const BattleAction &patrol)
{
	if (!missionOn(save))
	{
		return;
	}
	// the same aim as ProjectileFlyBState::init for a tile with an object, before the accuracy
	BattleAction a = patrol;
	TileEngine *te = save->getTileEngine();
	Position origin = te->getOriginVoxel(a, nullptr);
	Position scan;
	const bool lof = te->canTargetTile(&origin, save->getTile(a.target), O_OBJECT, &scan, unit, false);
	if (!lof)
	{
		scan = a.target.toVoxel() + Position(8, 8, 10);
	}
	std::vector<Position> impact;
	const int line = te->calculateLineVoxel(origin, scan, false, &impact, unit);
	Log(LOG_INFO) << "[AIMISSION] what=aim turn=" << save->getTurn() << " unit=" << unit->getId() << " from=" << missionXyz(unit->getPosition())
		<< " target=" << missionXyz(a.target) << " tu=" << unit->getTimeUnits() << " cost=" << a.Time << " lof=" << (lof ? 1 : 0) << " line=" << line
		<< " impact=" << (impact.empty() ? std::string("-") : missionXyz(impact.front().toTile())) << missionAlt(save, unit);
}

void missionNoModule(SavedBattleGame *save, BattleUnit *unit)
{
	if (missionOn(save))
	{
		Log(LOG_INFO) << "[AIMISSION] what=nomodule turn=" << save->getTurn() << " unit=" << unit->getId() << " from=" << missionXyz(unit->getPosition()) << missionAlt(save, unit);
	}
}

void missionWalkTarget(SavedBattleGame *save, BattleUnit *unit, const Node *node)
{
	if (missionOn(save))
	{
		Log(LOG_INFO) << "[AIMISSION] what=walk turn=" << save->getTurn() << " unit=" << unit->getId() << " from=" << missionXyz(unit->getPosition())
			<< " node=" << (node ? missionXyz(node->getPosition()) : std::string("-"));
	}
}

void missionTileHit(SavedBattleGame *save, BattleUnit *attacker, Position center, int part, int tileDamage)
{
	if (!missionOn(save))
	{
		return;
	}
	const Position p = center.toTile();
	Tile *tile = save->getTile(p);
	MapData *obj = tile ? tile->getMapData(O_OBJECT) : nullptr;
	MapData *hit = tile && part >= V_FLOOR && part <= V_OBJECT ? tile->getMapData(static_cast<TilePart>(part)) : nullptr;
	Log(LOG_INFO) << "[AIMISSION] what=hit turn=" << save->getTurn() << " unit=" << (attacker ? attacker->getId() : -1)
		<< " side=" << (attacker ? (int)attacker->getOriginalFaction() : -1) << " tile=" << missionXyz(p) << " part=" << part << " tdmg=" << tileDamage
		<< " partarmor=" << (hit ? hit->getArmor() : -1) << " module=" << (obj && obj->isBaseModule() ? 1 : 0)
		<< " left=" << save->getModuleMap()[p.x / 10][p.y / 10].second;
}

void missionBlastModule(SavedBattleGame *save, const Position &p)
{
	if (missionOn(save))
	{
		Log(LOG_INFO) << "[AIMISSION] what=blast turn=" << save->getTurn() << " tile=" << missionXyz(p) << " left=" << save->getModuleMap()[p.x / 10][p.y / 10].second;
	}
}
