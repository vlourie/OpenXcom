
namespace
{

/// MISSION_DIRECTOR STAGE 2 (OXCE_AI_MDIR): 0 - off, 1 - shadow: [AIMISSION] lines about what a base defense asks of the hostile side and what comes of
/// it, the plan and the orders written, nothing changed; 2 - the orders on.
int missionMode()
{
	static const int m = (int)param("OXCE_AI_MDIR", 0);
	return m;
}

bool missionOn(SavedBattleGame *save)
{
	return missionMode() > 0 && save->getMissionType() == "STR_BASE_DEFENSE" && save->getMod()->getAIDestroyBaseFacilities();
}

std::string missionXyz(const Position &p)
{
	std::ostringstream s;
	s << p.x << "," << p.y << "," << p.z;
	return s.str();
}

/// MissionContext: the rule's objects. A facility counts as demolished after the battle when the module map's cell of its corner is at 0
/// (DebriefingState), so the objectives are the facilities' cells; the module tiles of each cell at their real level, read from the map (the 5-level
/// blocks of the mod hold them at any z, the engine's protocol looks at z=1 only, the top of the 2-level vanilla block).
/// The side's knowledge is what the engine's own protocol reads for every hostile unit from the first turn: the module map, the tiles' objects.
/// Of the player's units only those the side sees now (getTurnsSinceSpottedByFaction 0, the rule of Pathfinding::isBlocked).
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

/// The nearest module tile of a cell this unit's snap shot could break from `from` (0 - where it stands), at most 10 tiles away: an object still a module,
/// the armor within the shot's reach, the line of fire ending on that very object and no unit of its own side on it. The line is terrain only (`u` as both
/// excludeUnit and excludeAllBut leaves no unit in voxelCheck): whether a unseen player's unit stands on it does not enter the choice.
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
		const int d = Position::distanceSq(at, p);
		if (d <= 100)
		{
			near.push_back(std::make_pair(d, p));
		}
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
		if (!te->canTargetTile(&origin, t, O_OBJECT, &scan, u, false, u))
		{
			continue;
		}
		std::vector<Position> line;
		const int hit = te->calculateLineVoxel(origin, scan, true, &line, u, u);
		if (hit != V_OBJECT || line.empty() || line.back().toTile() != n.second)
		{
			continue;
		}
		bool own = false;
		for (const Position &v : line)
		{
			Tile *on = save->getTile(v.toTile());
			BattleUnit *b = on ? on->getUnit() : nullptr;
			own = own || (b && b != u && !b->isOut() && b->getFaction() == FACTION_HOSTILE);
		}
		if (!own)
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

/// The standing tiles from which something of the cell's nearest 6 live modules can be seen along the terrain, within 5 tiles and one level: the real
/// level of the module decides, no z is assumed. A cheap look first: 15 lines per module; the assignment checks the chosen tile with the full missionAim.
std::vector<Position> missionFiringTiles(SavedBattleGame *save, BattleUnit *u, const std::pair<int, int> &cell)
{
	std::vector<Position> found;
	const auto it = missionTiles_.find(cell);
	if (it == missionTiles_.end())
	{
		return found;
	}
	std::vector<Position> mods;
	for (const Position &p : it->second)
	{
		Tile *t = save->getTile(p);
		MapData *md = t ? t->getMapData(O_OBJECT) : nullptr;
		if (md && md->isBaseModule())
		{
			mods.push_back(p);
		}
	}
	const Position at = u->getPosition();
	std::stable_sort(mods.begin(), mods.end(), [&at](const Position &a, const Position &b) { return Position::distanceSq(at, a) < Position::distanceSq(at, b); });
	if (mods.size() > 6)
	{
		mods.resize(6);
	}
	static const int xy[5][2] = { {8, 8}, {4, 8}, {12, 8}, {8, 4}, {8, 12} };
	static const int zs[3] = { 6, 12, 18 };
	TileEngine *te = save->getTileEngine();
	BattleAction a;
	a.actor = u;
	a.type = BA_SNAPSHOT;
	a.weapon = u->getMainHandWeapon();
	std::set<std::tuple<int, int, int> > seen;
	for (const Position &m : mods)
	{
		a.target = m;
		for (int dz = -1; dz <= 1; ++dz)
		for (int dx = -5; dx <= 5; ++dx)
		for (int dy = -5; dy <= 5; ++dy)
		{
			const Position p(m.x + dx, m.y + dy, m.z + dz);
			Tile *t = save->getTile(p);
			if (!t || p == m || !seen.insert(std::make_tuple(p.x, p.y, p.z)).second || t->hasNoFloor(save) || t->getTUCost(O_OBJECT, MT_WALK) >= 255)
			{
				continue;
			}
			BattleUnit *b = t->getUnit();
			if (b && b != u && b->getFaction() == FACTION_HOSTILE)
			{
				continue;
			}
			Position origin = te->getOriginVoxel(a, t);
			bool sees = false;
			for (int i = 0; i < 5 && !sees; ++i)
			{
				for (int j = 0; j < 3 && !sees; ++j)
				{
					std::vector<Position> line;
					const Position scan = m.toVoxel() + Position(xy[i][0], xy[i][1], zs[j]);
					const int hit = te->calculateLineVoxel(origin, scan, false, &line, u, u);
					sees = hit == V_OBJECT && !line.empty() && line.front().toTile() == m;
				}
			}
			if (sees)
			{
				found.push_back(p);
			}
		}
	}
	return found;
}

/// The side's seen enemies within 7 tiles of the route the path calculated last takes from `start`.
int missionRouteDanger(SavedBattleGame *save, const Position &start, const std::vector<Position> &known)
{
	const std::vector<int> &path = save->getPathfinding()->getPath();
	std::set<size_t> near;
	Position cur = start;
	for (size_t s = path.size() + 1; s-- > 0;)
	{
		if (s < path.size())
		{
			Position v;
			Pathfinding::directionToVector(path[s], &v);
			cur += v;
		}
		for (size_t k = 0; k < known.size(); ++k)
		{
			if (Position::distanceSq(cur, known[k]) <= 49)
			{
				near.insert(k);
			}
		}
	}
	return (int)near.size();
}

/// One fighter's firing position for the cell: where it stands if it has a shot from there; else of the 5 nearest tiles the one cheapest to reach within
/// two of its turns, by the engine's own path search; the tile's own shot checked in full.
bool missionAssign(SavedBattleGame *save, BattleUnit *u, const std::pair<int, int> &cell, const std::vector<Position> &tiles, const std::set<std::tuple<int, int, int> > &taken,
	const std::vector<Position> &known, Position &pos, int &cost, int &danger)
{
	Position aim;
	int armor = 0;
	Pathfinding *pf = save->getPathfinding();
	const Position at = u->getPosition();
	if (missionAim(save, u, nullptr, cell, aim, armor))
	{
		pos = at;
		cost = 0;
		danger = 0;
		for (const Position &k : known)
		{
			danger += Position::distanceSq(at, k) <= 49;
		}
		return true;
	}
	std::vector<Position> order = tiles;
	std::stable_sort(order.begin(), order.end(), [&at](const Position &a, const Position &b) { return Position::distanceSq(at, a) < Position::distanceSq(at, b); });
	bool any = false;
	int tries = 0;
	for (const Position &p : order)
	{
		if (taken.count(std::make_tuple(p.x, p.y, p.z)))
		{
			continue;
		}
		if (++tries > 5)
		{
			break;
		}
		if (!missionAim(save, u, save->getTile(p), cell, aim, armor))
		{
			continue;
		}
		pf->calculate(u, p, BAM_NORMAL, nullptr, 2 * u->getBaseStats()->tu);
		if (pf->getStartDirection() != -1)
		{
			const int c = pf->getTotalTUCost();
			if (!any || c < cost)
			{
				any = true;
				pos = p;
				cost = c;
				danger = missionRouteDanger(save, at, known);
			}
		}
		pf->abortPath();
	}
	return any;
}

/// MissionPlanner: one objective at a time - DEMOLISH_OBJECTIVE, one facility - and 2 to 4 fighters for it, each with a firing position it can reach within
/// two turns. The score is about the turns it takes: the walk, the module tiles shared out at two shots a turn, half a turn per enemy the side sees along a route.
struct MissionPlan
{
	std::pair<int, int> cell = std::make_pair(-1, -1);
	int tried = -1;
	std::map<int, Position> fighters;
};
MissionPlan missionPlan_;

void missionMakePlan(SavedBattleGame *save, const char *why, bool sameCell)
{
	auto &grid = save->getModuleMap();
	std::vector<BattleUnit *> all;
	double best = 0.0;
	for (auto *u : *save->getUnits())
	{
		if (u->getFaction() == FACTION_HOSTILE && missionMaxTile(u) > 0.0)
		{
			all.push_back(u);
			best = std::max(best, missionMaxTile(u));
		}
	}
	std::vector<Position> known;
	for (auto *u : *save->getUnits())
	{
		if (!u->isOut() && u->getFaction() == FACTION_PLAYER && u->getTurnsSinceSpottedByFaction(FACTION_HOSTILE) == 0)
		{
			known.push_back(u->getPosition());
		}
	}
	// the buildings by a rough score first, the engine's search for the first 6 of them
	std::vector<std::pair<double, std::pair<int, int> > > rough;
	for (const auto &f : missionFacs_)
	{
		if (sameCell && f.first != missionPlan_.cell)
		{
			continue;
		}
		const int left = grid[f.first.first][f.first.second].second;
		const auto tl = missionTiles_.find(f.first);
		if (left <= 0 || tl == missionTiles_.end())
		{
			continue;
		}
		int hardest = 0;
		for (const Position &p : tl->second)
		{
			MapData *md = save->getTile(p)->getMapData(O_OBJECT);
			hardest = std::max(hardest, md && md->isBaseModule() ? md->getArmor() : 0);
		}
		if (hardest > best)
		{
			continue;
		}
		const Position centre(f.first.first * 10 + 5, f.first.second * 10 + 5, 2);
		std::vector<double> dist;
		for (auto *u : all)
		{
			dist.push_back(std::sqrt((double)Position::distanceSq(u->getPosition(), centre)));
		}
		std::sort(dist.begin(), dist.end());
		if (dist.size() >= 2)
		{
			rough.push_back(std::make_pair(dist[1] / 20.0 + left / 4.0, f.first));
		}
	}
	std::stable_sort(rough.begin(), rough.end(), [](const std::pair<double, std::pair<int, int> > &a, const std::pair<double, std::pair<int, int> > &b) { return a.first < b.first; });
	if (rough.size() > 6)
	{
		rough.resize(6);
	}
	double bestScore = 0.0;
	std::pair<int, int> bestCell(-1, -1);
	std::map<int, Position> bestFighters;
	std::ostringstream detail;
	for (const auto &r : rough)
	{
		const std::pair<int, int> cell = r.second;
		const Position centre(cell.first * 10 + 5, cell.second * 10 + 5, 2);
		std::vector<std::pair<int, BattleUnit *> > near;
		for (auto *u : all)
		{
			near.push_back(std::make_pair(Position::distanceSq(u->getPosition(), centre), u));
		}
		std::stable_sort(near.begin(), near.end(), [](const std::pair<int, BattleUnit *> &a, const std::pair<int, BattleUnit *> &b) { return a.first < b.first; });
		if (near.size() > 8)
		{
			near.resize(8);
		}
		const std::vector<Position> tiles = near.empty() ? std::vector<Position>() : missionFiringTiles(save, near.front().second, cell);
		std::set<std::tuple<int, int, int> > taken;
		std::map<int, Position> chosen;
		double arrive = 0.0, danger = 0.0;
		std::ostringstream one;
		for (const auto &n : near)
		{
			if (chosen.size() >= 4)
			{
				break;
			}
			Position pos;
			int cost = 0, d = 0;
			if (missionAssign(save, n.second, cell, tiles, taken, known, pos, cost, d))
			{
				chosen[n.second->getId()] = pos;
				taken.insert(std::make_tuple(pos.x, pos.y, pos.z));
				arrive += (double)cost / n.second->getBaseStats()->tu;
				danger += d;
				one << " " << n.second->getId() << ":" << missionXyz(pos) << ":tu" << cost << ":d" << d;
			}
		}
		const size_t got = chosen.size();
		const int left = grid[cell.first][cell.second].second;
		const double score = got >= 2 ? arrive / got + (double)left / (2.0 * got) + 0.5 * danger / got : -1.0;
		Log(LOG_INFO) << "[AIMISSION] what=cand turn=" << save->getTurn() << " cell=" << cell.first << "," << cell.second << " fac=" << missionFacs_[cell] << " left=" << left
			<< " tiles=" << tiles.size() << " n=" << got << " score=" << score << " known=" << known.size() << one.str();
		if (got >= 2 && (bestCell.first < 0 || score < bestScore))
		{
			bestScore = score;
			bestCell = cell;
			bestFighters = chosen;
		}
	}
	if (bestCell.first >= 0)
	{
		missionPlan_.cell = bestCell;
		missionPlan_.fighters = bestFighters;
		std::ostringstream s;
		for (const auto &f : bestFighters)
		{
			s << (s.tellp() > 0 ? ";" : "") << f.first << ">" << missionXyz(f.second);
		}
		Log(LOG_INFO) << "[AIMISSION] what=objective turn=" << save->getTurn() << " cell=" << bestCell.first << "," << bestCell.second << " fac=" << missionFacs_[bestCell]
			<< " left=" << grid[bestCell.first][bestCell.second].second << " score=" << bestScore << " why=" << why;
		Log(LOG_INFO) << "[AIMISSION] what=plan turn=" << save->getTurn() << " cell=" << bestCell.first << "," << bestCell.second << " fighters=" << s.str();
		return;
	}
	Log(LOG_INFO) << "[AIMISSION] what=noplan turn=" << save->getTurn() << " why=" << why << " candidates=" << rough.size() << " fighters=" << all.size();
	if (!sameCell || missionPlan_.fighters.empty())
	{
		missionPlan_.cell = std::make_pair(-1, -1);
		missionPlan_.fighters.clear();
	}
}

/// MissionExecutor's check of the plan with each think on the hostile side's own turn. The objective stays until it is demolished: a lost fighter is replaced
/// for the same building, at most once a turn; a new building only when it is done or nobody can go on with it.
void missionRefresh(SavedBattleGame *save)
{
	missionKnow(save);
	const int turn = save->getTurn();
	if (missionPlan_.cell.first >= 0 && save->getModuleMap()[missionPlan_.cell.first][missionPlan_.cell.second].second <= 0)
	{
		Log(LOG_INFO) << "[AIMISSION] what=done turn=" << turn << " cell=" << missionPlan_.cell.first << "," << missionPlan_.cell.second << " fac=" << missionFacs_[missionPlan_.cell];
		missionPlan_.cell = std::make_pair(-1, -1);
		missionPlan_.fighters.clear();
		missionPlan_.tried = turn;
		missionMakePlan(save, "done", false);
		return;
	}
	if (missionPlan_.cell.first < 0)
	{
		if (missionPlan_.tried != turn)
		{
			missionPlan_.tried = turn;
			missionMakePlan(save, "none", false);
		}
		return;
	}
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
	if (missionPlan_.fighters.size() < 2 && missionPlan_.tried != turn)
	{
		missionPlan_.tried = turn;
		missionMakePlan(save, "few", true);
	}
	else if (missionPlan_.fighters.empty())
	{
		missionPlan_.cell = std::make_pair(-1, -1);
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

void missionBaseLine(Base *base, const char *when)
{
	int rubble = 0;
	for (auto *fac : *base->getFacilities())
	{
		rubble += fac->getRules()->getType() == "STR_RUBBLE";
	}
	Log(LOG_INFO) << "[AIMISSION] what=base when=" << when << " facilities=" << base->getFacilities()->size() << " rubble=" << rubble << " labs=" << base->getAvailableLaboratories()
		<< " workshops=" << base->getAvailableWorkshops() << " psilabs=" << base->getAvailablePsiLabs() << " training=" << base->getAvailableTraining()
		<< " stores=" << base->getAvailableStores() << " quarters=" << base->getAvailableQuarters() << " hangars=" << base->getAvailableHangars();
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

bool missionRedirect(SavedBattleGame *save, BattleUnit *unit, const Node *)
{
	if (!missionOn(save) || save->getSide() != FACTION_HOSTILE)
	{
		return false;
	}
	missionRefresh(save);
	return missionMode() >= 2 && missionPlan_.fighters.count(unit->getId()) > 0;
}

int missionOrder(SavedBattleGame *save, BattleUnit *unit, Position &tile)
{
	if (!missionOn(save) || save->getSide() != FACTION_HOSTILE)
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
	if (missionAim(save, unit, nullptr, missionPlan_.cell, aim, armor))
	{
		Log(LOG_INFO) << "[AIMISSION] what=task turn=" << save->getTurn() << " unit=" << unit->getId() << " kind=shoot from=" << missionXyz(p) << " tile=" << missionXyz(aim)
			<< " armor=" << armor << " tu=" << unit->getTimeUnits() << " on=" << on;
		tile = aim;
		return on ? 1 : 0;
	}
	Pathfinding *pf = save->getPathfinding();
	bool path = false;
	if (p != it->second)
	{
		pf->calculate(unit, it->second, BAM_NORMAL);
		path = pf->getStartDirection() != -1;
		pf->abortPath();
	}
	if (!path)
	{
		// this position has no shot left or no way: another of the same building, not the engine's protocol
		std::set<std::tuple<int, int, int> > taken;
		for (const auto &f : missionPlan_.fighters)
		{
			if (f.first != unit->getId())
			{
				taken.insert(std::make_tuple(f.second.x, f.second.y, f.second.z));
			}
		}
		std::vector<Position> known;
		for (auto *u : *save->getUnits())
		{
			if (!u->isOut() && u->getFaction() == FACTION_PLAYER && u->getTurnsSinceSpottedByFaction(FACTION_HOSTILE) == 0)
			{
				known.push_back(u->getPosition());
			}
		}
		Position pos;
		int cost = 0, danger = 0;
		if (!missionAssign(save, unit, missionPlan_.cell, missionFiringTiles(save, unit, missionPlan_.cell), taken, known, pos, cost, danger) || pos == p)
		{
			Log(LOG_INFO) << "[AIMISSION] what=release turn=" << save->getTurn() << " unit=" << unit->getId() << " why=nopos from=" << missionXyz(p);
			missionPlan_.fighters.erase(it);
			return 0;
		}
		Log(LOG_INFO) << "[AIMISSION] what=repos turn=" << save->getTurn() << " unit=" << unit->getId() << " from=" << missionXyz(p) << " to=" << missionXyz(pos) << " tu=" << cost << " danger=" << danger;
		it->second = pos;
	}
	Log(LOG_INFO) << "[AIMISSION] what=task turn=" << save->getTurn() << " unit=" << unit->getId() << " kind=walk from=" << missionXyz(p) << " node=" << missionXyz(it->second)
		<< " tu=" << unit->getTimeUnits() << " on=" << on;
	tile = it->second;
	return on ? 2 : 0;
}

void missionDebrief(SavedBattleGame *save)
{
	static bool done = false;
	if (done || !missionOn(save))
	{
		return;
	}
	done = true;
	auto &grid = save->getModuleMap();
	for (auto *base : *save->getGeoscapeSave()->getBases())
	{
		if (!base->isInBattlescape())
		{
			continue;
		}
		// the steps of DebriefingState, on the real base of this run: the bench quits right after this line and never reaches the debriefing
		missionBaseLine(base, "before");
		std::vector<BaseFacility *> toBeDamaged;
		for (auto *fac : *base->getFacilities())
		{
			if (grid[fac->getX()][fac->getY()].second == 0)
			{
				toBeDamaged.push_back(fac);
				Log(LOG_INFO) << "[AIMISSION] what=demolished at=" << fac->getX() << "," << fac->getY() << " type=" << fac->getRules()->getType()
					<< " modules=" << grid[fac->getX()][fac->getY()].first << " becomes=" << (fac->getRules()->getDestroyedFacility() ? fac->getRules()->getDestroyedFacility()->getType() : std::string("-"));
			}
		}
		for (auto *fac : toBeDamaged)
		{
			base->damageFacility(fac);
		}
		base->destroyDisconnectedFacilities();
		missionBaseLine(base, "after");
	}
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
