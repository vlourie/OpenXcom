/*
 * SIDE-FIRST COMBAT AI (bench only, OXCE_AI_SCD), see SideCombatDirector.h.
 *
 * What it may read (docs/research/ai-mechanics/TACTICAL_AI_2_0_ARCHITECTURE.md, 4.2): its own units whole; an enemy the side's eyes see now (place, direction,
 * unit type, armor by the ruleset, the weapon in hand); where its eyes last saw one. What it never reads to decide: an enemy's health, stun, morale,
 * current armor, a place nobody of the side saw. The one exception is written in observe(): "this shot visibly hit him", yes or no.
 * No random numbers, no time units, no stats given: everything it does goes through the states the AI's own actions go through.
 */
#include "SideCombatDirector.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <map>
#include <set>
#include <sstream>
#include <tuple>
#include <vector>
#include "AIModule.h"
#include "AiProbe.h"
#include "BattlescapeGame.h"
#include "Pathfinding.h"
#include "TileEngine.h"
#include "../Engine/Logger.h"
#include "../Engine/RNG.h"
#include "../Mod/Armor.h"
#include "../Mod/Mod.h"
#include "../Mod/RuleDamageType.h"
#include "../Mod/RuleItem.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Tile.h"

namespace OpenXcom
{
namespace SideCombatDirector
{
namespace
{

// The planner's scale is expected useful damage of one action. These are the only numbers of its judgement, set before any battle and not tuned on results.
const double USEFUL = 2.5;        // an attack worth this is the unit's job for now: it does not walk away from it
const double MIN_NET = 0.5;       // less than this is no attack at all
const double FF_WEIGHT = 1.0;     // a point of damage on our own against a point on the enemy
const double MOVE_SURE = 0.6;     // a shot after a walk is not a shot yet: reactions, a stop on the way
const double MOVE_TU = 0.03;      // per time unit of the walk
const double EXPOSED = 1.5;       // per other known enemy with a line to the cell
const double IN_WAY = 1.5;        // per comrade's shot the cell stands in
const double CLEAR_SURE = 0.7;    // what stepping aside for a comrade's shot is worth, of what the shot gains
const double CLEAR_MIN = 1.5;     // the gain a step aside must bring
const double APPROACH = 0.4;      // a walk under cover toward a contact: only before the unit is left to itself
const int MIN_HEALTH_PCT = 40;    // below this a unit does not walk toward fire for the side: its own think decides (escape)
const int REMEMBER_TURNS = 2;     // a place seen this long ago is still worth walking to
const int FAILS_BAN = 2;          // actions that changed nothing, then the director leaves the unit alone for the turn
const int LINE_BUDGET = 8000;     // engine line checks per turn: past it no more walks are looked for, attacks go on from the cache and what is left
const int MAX_ACTS_FACTOR = 6;    // director's actions per turn per unit of the side, a guard only

// ---------------------------------------------------------------------------------------------------------------------------------- BattleState

struct Target
{
	BattleUnit *u = 0;
	Position at;
	int dir = 0;
	bool seen = false;   // the side's eyes see it now; otherwise at/dir are where they last did
	int age = 0;         // turns since
	double weight = 1;   // what hurting it is worth: enemy or civilian, the weapon in its hand
	int hits = 0;        // shots of ours seen to hit it this turn
};

struct Memory { Position at; int dir = 0; int turn = 0; };

class BattleState
{
public:
	SavedBattleGame *save = 0;
	int turn = -1;
	std::vector<BattleUnit*> own;    // every unit of the side still in the battle: who can be hit
	std::vector<BattleUnit*> ready;  // those the director may give an action to
	std::vector<Target> targets;     // seen first
	std::map<int, Memory> memory;
	std::map<int, int> hitsTurn;
	std::set<int> banned;
	int version = 0;                 // changes when the set of seen enemies or their places change

	static bool isReady(const BattleUnit *u)
	{
		return u && !u->isOut() && u->getStatus() == STATUS_STANDING && u->getFaction() == FACTION_HOSTILE && u->getOriginalFaction() == FACTION_HOSTILE
			&& u->getTimeUnits() > 0 && u->getTurnsSinceStunned() != 0 && !u->isLeeroyJenkins();
	}

	void refresh()
	{
		own.clear();
		ready.clear();
		std::set<BattleUnit*> eyes;
		for (BattleUnit *u : *save->getUnits())
		{
			if (u->getFaction() != FACTION_HOSTILE || u->isOut())
			{
				continue;
			}
			own.push_back(u);
			if (isReady(u) && !banned.count(u->getId()))
			{
				ready.push_back(u);
			}
			eyes.insert(u->getVisibleUnits()->begin(), u->getVisibleUnits()->end());
		}
		std::ostringstream sign;
		targets.clear();
		const Mod *mod = save->getMod();
		for (BattleUnit *u : *save->getUnits())
		{
			if (u->getFaction() == FACTION_HOSTILE || u->isOut() || (u->getFaction() != FACTION_PLAYER && u->isIgnoredByAI()))
			{
				continue;
			}
			const double kind = u->getFaction() == FACTION_PLAYER ? 1.0 : (u->getAITargetWeightAsHostileCivilians(mod) > AIW_IGNORED ? 0.35 : 0.0);
			if (kind <= 0)
			{
				continue;
			}
			const bool seen = eyes.count(u) != 0;
			if (seen)
			{
				Memory &m = memory[u->getId()];
				m.at = u->getPosition();
				m.dir = u->getDirection();
				m.turn = turn;
				sign << u->getId() << ":" << m.at.x << "," << m.at.y << "," << m.at.z << ";";
			}
			else
			{
				auto it = memory.find(u->getId());
				if (it == memory.end() || turn - it->second.turn > REMEMBER_TURNS)
				{
					continue;
				}
			}
			const Memory &m = memory[u->getId()];
			Target t;
			t.u = u;
			t.at = m.at;
			t.dir = m.dir;
			t.seen = seen;
			t.age = turn - m.turn;
			auto h = hitsTurn.find(u->getId());
			t.hits = h == hitsTurn.end() ? 0 : h->second;
			double threat = 0.8;
			if (seen)
			{
				// the weapon in its hand, as anybody sees it
				const BattleItem *w = u->getMainHandWeapon(false);
				if (w && w->getRules()->getBattleType() == BT_FIREARM)
				{
					const RuleItem *r = w->getRules();
					threat = std::min(1.6, 0.8 + r->getPower() * std::max(1, r->getConfigAuto()->shots) / 150.0);
				}
			}
			t.weight = kind * threat * std::min(1.6, 1.0 + 0.15 * t.hits);
			targets.push_back(t);
		}
		std::stable_sort(targets.begin(), targets.end(), [](const Target &a, const Target &b) { return a.seen > b.seen; });
		const std::string now = sign.str();
		if (now != signature)
		{
			signature = now;
			++version;
		}
	}

	void newTurn(SavedBattleGame *s)
	{
		if (save != s)
		{
			memory.clear();
		}
		save = s;
		turn = s->getTurn();
		hitsTurn.clear();
		banned.clear();
		signature.clear();
		++version;
	}

private:
	std::string signature;
};

// ---------------------------------------------------------------------------------------------------------------------------------- ActionGenerator

/// One way a unit can attack with what it holds.
struct Mode
{
	BattleActionType type = BA_NONE;
	BattleItem *weapon = 0;
	const RuleItem *rule = 0, *ammo = 0;
	const RuleDamageType *dt = 0;
	int tu = 0, power = 0, shots = 1, pellets = 1, radius = 0, upper = 200, lower = 0, dropoff = 2, maxRange = 200, noLos = -1;
	double acc = 0;
	bool melee = false, canNow = false;
};

/// One attack judged.
struct Shot
{
	const Mode *m = 0;
	const Target *t = 0;
	double acc = 0, pHit = 0, eff = 0, ff = 0, net = -1e9, total = -1e9;
	double d = 0;
	int turnTu = 0, rep = 0;
	bool los = true;
};

/// The line of fire from a place to a place as the engine says it, kept until somebody walks through it.
struct LineRec { bool line = false, los = false; Position from, to; };

class ActionGenerator
{
public:
	BattleState *bs = 0;
	std::map<std::tuple<int, int, int>, LineRec> lines;
	int lineChecks = 0;

	static int pack(const Position &p) { return p.x | (p.y << 10) | (p.z << 20); }

	static double dist(const Position &a, const Position &b)
	{
		const double dx = a.x - b.x, dy = a.y - b.y, dz = (a.z - b.z) * 1.5;
		return std::sqrt(dx * dx + dy * dy + dz * dz);
	}

	/// Is p within w tiles of the segment from a to b?
	static bool nearSegment(const Position &p, const Position &a, const Position &b, double w)
	{
		const double dx = b.x - a.x, dy = b.y - a.y, len2 = dx * dx + dy * dy;
		if (len2 <= 0)
		{
			return dist(p, a) <= w;
		}
		const double k = std::max(0.0, std::min(1.0, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2));
		const double ex = a.x + k * dx - p.x, ey = a.y + k * dy - p.y;
		return ex * ex + ey * ey <= w * w;
	}

	void forgetNear(const Position &p, double w)
	{
		for (auto it = lines.begin(); it != lines.end();)
		{
			if (nearSegment(p, it->second.from, it->second.to, w))
			{
				it = lines.erase(it);
			}
			else
			{
				++it;
			}
		}
	}

	std::vector<Mode> modesOf(BattleUnit *u)
	{
		std::vector<Mode> out;
		std::vector<BattleItem*> guns;
		for (BattleItem *w : { u->getRightHandWeapon(), u->getLeftHandWeapon(), u->getSpecialWeapon(BT_FIREARM) })
		{
			if (w && std::find(guns.begin(), guns.end(), w) == guns.end())
			{
				guns.push_back(w);
			}
		}
		for (BattleItem *w : guns)
		{
			const RuleItem *r = w->getRules();
			// arcing shots and waypoints have rules of their own: the unit's own think keeps them
			if (r->getBattleType() != BT_FIREARM || !w->haveAnyAmmo() || r->getArcingShot() || r->getWaypoints() != 0)
			{
				continue;
			}
			for (BattleActionType type : { BA_AUTOSHOT, BA_SNAPSHOT, BA_AIMEDSHOT })
			{
				addMode(out, u, w, type, false);
			}
		}
		BattleItem *blade = u->getUtilityWeapon(BT_MELEE);
		if (blade)
		{
			addMode(out, u, blade, BA_HIT, true);
		}
		return out;
	}

	void addMode(std::vector<Mode> &out, BattleUnit *u, BattleItem *w, BattleActionType type, bool melee)
	{
		BattleActionCost cost(type, u, w);
		if (cost.Time <= 0)
		{
			return;
		}
		BattleActionAttack attack = BattleActionAttack::GetBeforeShoot(cost);
		if (!attack.damage_item)
		{
			return;
		}
		const RuleItem *r = w->getRules();
		Mode m;
		m.type = type;
		m.weapon = w;
		m.rule = r;
		m.ammo = attack.damage_item->getRules();
		m.dt = m.ammo->getDamageType();
		m.tu = cost.Time;
		m.power = m.ammo->getPowerBonus(attack);
		m.melee = melee;
		m.canNow = cost.haveTU();
		m.acc = BattleUnit::getFiringAccuracy(attack, bs->save->getMod());
		if (!melee)
		{
			m.shots = type == BA_AUTOSHOT ? r->getConfigAuto()->shots : type == BA_SNAPSHOT ? r->getConfigSnap()->shots : r->getConfigAimed()->shots;
			m.pellets = std::max(1, m.ammo->getShotgunPellets());
			m.radius = m.ammo->getExplosionRadius(attack);
			m.dropoff = r->calculateLimits(m.upper, m.lower, bs->save->getDepth(), type);
			m.maxRange = r->getMaxRange();
			m.noLos = r->getNoLOSAccuracyPenalty(const_cast<Mod*>(bs->save->getMod()));
		}
		else
		{
			// MeleeAttackBState: on its own turn the side's blade goes on striking while the time units and the weapon's AI hit count last
			m.shots = std::max(1, std::min(r->getAIMeleeHitCount(), u->getTimeUnits() / cost.Time));
		}
		out.push_back(m);
	}

	/// The engine's line from where the unit stands now; the place of the target as the side sees it.
	LineRec lineNow(BattleUnit *u, const Target &t)
	{
		const auto key = std::make_tuple(u->getId(), pack(u->getPosition()), pack(t.at));
		auto it = lines.find(key);
		if (it != lines.end())
		{
			return it->second;
		}
		TileEngine *te = bs->save->getTileEngine();
		BattleAction a;
		a.actor = u;
		a.target = t.at;
		Position origin = te->getOriginVoxel(a, 0), scan;
		LineRec r;
		r.from = u->getPosition();
		r.to = t.at;
		r.line = te->canTargetUnit(&origin, t.u->getTile(), &scan, u, false);
		r.los = r.line && te->visible(u, t.u->getTile());
		++lineChecks;
		lines[key] = r;
		return r;
	}

	/// The engine's line from a cell of its reach (the origin as Pathfinding's cells give it); the unit stays where it is.
	bool lineFrom(BattleUnit *u, const Position &cell, const Tile *tile, BattleUnit *t)
	{
		Position origin = cell.toVoxel() + Position(8, 8, u->getHeight() + u->getFloatHeight() - tile->getTerrainLevel() - 4), scan;
		++lineChecks;
		return bs->save->getTileEngine()->canTargetUnit(&origin, t->getTile(), &scan, u, false);
	}

	/// The line with comrade a taken off its tile, a back before it returns.
	bool lineWithout(BattleUnit *u, const Target &t, BattleUnit *a)
	{
		Tile *old = a->getTile();
		old->setUnit(0);
		TileEngine *te = bs->save->getTileEngine();
		BattleAction action;
		action.actor = u;
		action.target = t.at;
		Position origin = te->getOriginVoxel(action, 0), scan;
		++lineChecks;
		const bool ok = te->canTargetUnit(&origin, t.u->getTile(), &scan, u, false);
		old->setUnit(a);
		return ok;
	}
};

// ---------------------------------------------------------------------------------------------------------------------------------- SidePlanner

/// What the mean roll leaves past this armor: E[max(0, X - armor)] for X even between the type's least and most, with the type's resistance.
double meanPast(const RuleDamageType *dt, int power, const Armor *armor, double armorValue)
{
	const double modifier = armor->getDamageModifier(dt->ResistType);
	if (power <= 0 || modifier <= 0)
	{
		return 0;
	}
	const double a = armorValue * dt->ArmorEffectiveness;
	const double lo = dt->getRandomDamage(power, 1) * modifier, hi = dt->getRandomDamage(power, 2) * modifier;
	if (hi <= a)
	{
		return 0;
	}
	if (hi - lo < 1e-6)
	{
		return hi - a;
	}
	const double from = std::max(lo, a);
	return (hi - from) * ((hi + from) / 2 - a) / (hi - lo);
}

/// What a point past the armor is worth: health, then what else the type does (a stun gun is no useless gun).
double usefulShare(const RuleDamageType *dt, const Armor *armor)
{
	double v = dt->ToHealth;
	if (dt->IgnorePainImmunity || !armor->getPainImmune())
	{
		v += 0.7 * dt->ToStun;
	}
	return v + 0.1 * (dt->ToEnergy + dt->ToTime + dt->ToMorale + dt->ToArmor);
}

/// The ruleset armor on the side of the target the shot comes from (its direction is as visible as the unit).
double armorFrom(const Armor *armor, const Position &from, const Position &at, int dir)
{
	const double dx = from.x - at.x, dy = from.y - at.y;
	if (dx == 0 && dy == 0)
	{
		return armor->getFrontArmor();
	}
	// engine directions: 0 is -y, clockwise
	const int to = ((int)std::lround(std::atan2(dx, -dy) * 4 / M_PI) + 8) % 8;
	const int rel = (to - dir + 8) % 8;
	if (rel <= 1 || rel == 7)
	{
		return armor->getFrontArmor();
	}
	if (rel >= 3 && rel <= 5)
	{
		return armor->getRearArmor();
	}
	return rel == 2 ? armor->getRightSideArmor() : armor->getLeftSideArmor();
}

/// The miss cloud of Projectile::applyAccuracy: half its width at the target, in tiles, for a mean miss (deviation 50 + what is above the accuracy).
double missSpread(double d, double acc)
{
	return std::max(0.2, 0.005 * d * (50 + (100 - std::min(100.0, std::max(0.0, acc))) / 2));
}

class SidePlanner
{
public:
	BattleState *bs = 0;
	ActionGenerator *gen = 0;

	enum Kind { NONE, ATTACK, MOVE, CLEAR, APPROACH_WALK };

	struct Plan
	{
		Kind kind = NONE;
		BattleUnit *actor = 0;
		Shot shot;
		Mode mode;
		Target target;
		Position cell;
		int cellTu = 0;
		BattleUnit *helps = 0;
		double score = -1e9, gain = 0;
		int exposed = 0;
	};

	struct MoveMemo { int version = -1, tu = -1; Position at; bool any = false; Plan plan; };
	std::map<int, MoveMemo> moves;
	std::set<std::tuple<int, int, int>> triedClear;
	std::set<int> approached;
	std::set<int> claimed;

	void newTurn()
	{
		moves.clear();
		triedClear.clear();
		approached.clear();
		claimed.clear();
	}

	/// Expected damage on the side's own units from what misses, one projectile.
	double ffMiss(const BattleUnit *u, const Position &from, const Position &at, const Mode &m, double acc, double pHit, double d, const BattleUnit *without) const
	{
		if (d < 1 || m.melee)
		{
			return 0;
		}
		const double dx = (at.x - from.x) / std::max(0.01, std::hypot((double)at.x - from.x, (double)at.y - from.y));
		const double dy = (at.y - from.y) / std::max(0.01, std::hypot((double)at.x - from.x, (double)at.y - from.y));
		const double s = missSpread(d, acc);
		double sum = 0;
		for (const BattleUnit *c : bs->own)
		{
			if (c == u || c == without)
			{
				continue;
			}
			const Position cp = c->getPosition();
			const double rx = cp.x - from.x, ry = cp.y - from.y;
			const double proj = rx * dx + ry * dy;
			if (proj < 0.5 || proj > d + 8)
			{
				continue;
			}
			const double f = proj / d;
			if (std::abs(cp.z - (from.z + f * (at.z - from.z))) > 0.75)
			{
				continue;
			}
			const double lat = std::abs(rx * dy - ry * dx), sf = std::max(0.15, s * f);
			if (lat > sf + 0.5)
			{
				continue;
			}
			const double pLat = std::min(1.0, 0.8 / (2 * sf)), pHeight = std::min(1.0, 0.85 / (2 * std::max(0.1, sf * 0.17)));
			const Armor *armor = c->getArmor();
			sum += pLat * pHeight * (f > 1 ? 0.5 : 1.0) * meanPast(m.dt, m.power, armor, armor->getFrontArmor()) * usefulShare(m.dt, armor);
		}
		return (1 - pHit) * sum;
	}

	/// One attack from a place: what it is expected to do, what it risks, what is left of it past the risk.
	Shot judge(BattleUnit *u, const Position &from, const Mode &m, const Target &t, bool los, int tuLeft, const BattleUnit *without) const
	{
		Shot r;
		r.m = &m;
		r.t = &t;
		r.los = los;
		r.d = ActionGenerator::dist(from, t.at);
		if (r.d > m.maxRange)
		{
			return r;
		}
		double acc = m.acc;
		if (!m.melee)
		{
			if (r.d > m.upper)
			{
				acc -= m.dropoff * (r.d - m.upper);
			}
			else if (r.d < m.lower)
			{
				acc -= m.dropoff * (m.lower - r.d);
			}
			if (m.noLos != -1 && !los)
			{
				acc = acc * m.noLos / 100;
			}
		}
		acc = std::max(0.0, acc);
		r.acc = acc;
		const double sure = std::min(1.0, acc / 100);
		const double s = missSpread(r.d, acc);
		const double near = std::min(1.0, 0.8 / (2 * s)) * std::min(1.0, 0.85 / (2 * std::max(0.1, s * 0.17)));
		r.pHit = m.melee ? sure : sure + (1 - sure) * near;
		const Armor *armor = t.u ? t.u->getArmor() : 0; // no unit: a shot at a place, only its risk is known
		const double perHit = armor ? meanPast(m.dt, m.power, armor, armorFrom(armor, from, t.at, t.dir)) * usefulShare(m.dt, armor) : 0;
		const double projectiles = m.shots * (1 + 0.4 * (m.pellets - 1));
		r.eff = r.pHit * projectiles * perHit * t.weight;
		r.ff = m.shots * m.pellets * ffMiss(u, from, t.at, m, acc, r.pHit, r.d, without);
		if (m.radius > 0)
		{
			if (r.d <= m.radius + 1)
			{
				return r; // it would catch the shooter
			}
			const double pBlast = r.pHit + (1 - r.pHit) * std::min(1.0, (m.radius + 0.5) / (s * 1.2));
			r.eff = pBlast * projectiles * perHit * t.weight;
			for (const BattleUnit *c : bs->own)
			{
				const double dc = ActionGenerator::dist(c->getPosition(), t.at);
				if (dc <= m.radius)
				{
					const Armor *ca = c->getArmor();
					const double fall = 1 - dc / (m.radius + 1);
					r.ff += m.shots * pBlast * meanPast(m.dt, (int)(m.power * fall), ca, ca->getFrontArmor()) * usefulShare(m.dt, ca);
				}
			}
			for (const Target &o : bs->targets)
			{
				const double dt2 = ActionGenerator::dist(o.at, t.at);
				if (o.u != t.u && o.seen && dt2 <= m.radius)
				{
					const Armor *oa = o.u->getArmor();
					const double fall = 1 - dt2 / (m.radius + 1);
					r.eff += m.shots * pBlast * meanPast(m.dt, (int)(m.power * fall), oa, oa->getFrontArmor()) * usefulShare(m.dt, oa) * o.weight;
				}
			}
		}
		r.net = r.eff - FF_WEIGHT * r.ff;
		r.rep = m.tu > 0 ? tuLeft / m.tu : 0;
		r.total = m.melee ? r.net : r.net * std::max(1, r.rep); // a blade's strikes are all in its net already
		return r;
	}

	int turnCost(const BattleUnit *u, const Position &at) const
	{
		if (u->getTurretType() != -1)
		{
			return 0;
		}
		const int d = std::abs(u->directionTo(at) - u->getDirection());
		return std::min(d, 8 - d) * u->getTurnCost();
	}

	/// The unit's best attack from where it stands. blocked: a target it could hurt but for the line.
	bool bestAttack(BattleUnit *u, const std::vector<Mode> &modes, Shot &best, Mode &bestMode, Target &bestTarget, std::vector<std::pair<const Mode*, const Target*>> *blocked)
	{
		bool any = false;
		TileEngine *te = bs->save->getTileEngine();
		for (const Target &t : bs->targets)
		{
			if (!t.seen)
			{
				continue;
			}
			const double d = ActionGenerator::dist(u->getPosition(), t.at);
			for (const Mode &m : modes)
			{
				if (!m.canNow || d > m.maxRange)
				{
					continue;
				}
				const int tc = turnCost(u, t.at);
				if (u->getTimeUnits() < m.tu + tc)
				{
					continue; // the turn is charged before the shot (R-120)
				}
				bool los = true;
				if (m.melee)
				{
					if (d > 2.5 || !te->validMeleeRange(u, t.u, te->getDirectionTo(u->getPosition(), t.at)))
					{
						continue;
					}
				}
				else
				{
					if (m.acc <= 0 || d < 1)
					{
						continue;
					}
					const LineRec line = gen->lineNow(u, t);
					if (!line.line)
					{
						if (blocked)
						{
							blocked->push_back({ &m, &t });
						}
						continue;
					}
					los = line.los;
				}
				Shot s = judge(u, u->getPosition(), m, t, los, u->getTimeUnits() - tc, 0);
				s.turnTu = tc;
				if (s.total > best.total || !any)
				{
					best = s;
					bestMode = m;
					bestTarget = t;
					best.m = &bestMode;
					best.t = &bestTarget;
					any = true;
				}
			}
		}
		return any && best.net > -1e8;
	}

	/// A cell of the unit's reach that gives it an attack worth more than what it has where it stands.
	bool bestCell(BattleUnit *u, const std::vector<Mode> &modes, const std::vector<std::pair<Position, Position>> &shots, Plan &out)
	{
		if (gen->lineChecks > LINE_BUDGET || !u->isSmallUnit() || !u->getArmor()->allowsMoving())
		{
			return false;
		}
		std::vector<const Target*> near;
		for (const Target &t : bs->targets)
		{
			if (t.seen)
			{
				near.push_back(&t);
			}
		}
		if (near.empty())
		{
			return false;
		}
		const Position here = u->getPosition();
		std::stable_sort(near.begin(), near.end(), [&](const Target *a, const Target *b) { return ActionGenerator::dist(here, a->at) < ActionGenerator::dist(here, b->at); });
		if (near.size() > 4)
		{
			near.resize(4);
		}
		Pathfinding *pf = bs->save->getPathfinding();
		const std::vector<int> reach = pf->findReachable(u, BattleActionCost());
		struct Cand { double ub; Position cell; int tu; const Mode *m; const Target *t; };
		std::vector<Cand> cands;
		for (int index : reach)
		{
			const Position c = bs->save->getTileCoords(index);
			Tile *tile = bs->save->getTile(c);
			if (c == here || !tile || tile->getUnit() || tile->getDangerous() || claimed.count(ActionGenerator::pack(c)))
			{
				continue;
			}
			const int tu = pf->reachedTU(c);
			Cand best;
			best.ub = 0;
			for (const Target *t : near)
			{
				const double d = ActionGenerator::dist(c, t->at);
				for (const Mode &m : modes)
				{
					if (m.melee || m.acc <= 0 || d < 1 || d > m.maxRange || u->getTimeUnits() - tu < m.tu)
					{
						continue;
					}
					const double acc = std::max(0.0, m.acc - (d > m.upper ? m.dropoff * (d - m.upper) : d < m.lower ? m.dropoff * (m.lower - d) : 0));
					const Armor *armor = t->u->getArmor();
					const double ub = (std::min(1.0, acc / 100) + 0.1) * m.shots * (1 + 0.4 * (m.pellets - 1)) * meanPast(m.dt, m.power, armor, armor->getRearArmor()) * usefulShare(m.dt, armor) * t->weight;
					if (ub > best.ub)
					{
						best = { ub, c, tu, &m, t };
					}
				}
			}
			if (best.ub > 0)
			{
				cands.push_back(best);
			}
		}
		std::stable_sort(cands.begin(), cands.end(), [](const Cand &a, const Cand &b) { return a.ub - MOVE_TU * a.tu > b.ub - MOVE_TU * b.tu; });
		double bestScore = -1e9;
		int looked = 0;
		for (const Cand &c : cands)
		{
			if (++looked > 12 || MOVE_SURE * c.ub - MOVE_TU * c.tu <= bestScore)
			{
				break;
			}
			const Tile *tile = bs->save->getTile(c.cell);
			if (!gen->lineFrom(u, c.cell, tile, c.t->u))
			{
				continue;
			}
			Shot s = judge(u, c.cell, *c.m, *c.t, true, u->getTimeUnits() - c.tu, 0);
			if (s.net < MIN_NET)
			{
				continue;
			}
			int exposed = 0;
			for (const Target *o : near)
			{
				if (o != c.t && gen->lineFrom(u, c.cell, tile, o->u))
				{
					++exposed;
				}
			}
			int inWay = 0;
			for (const auto &line : shots)
			{
				if (line.first != here && ActionGenerator::nearSegment(c.cell, line.first, line.second, 1.0))
				{
					++inWay;
				}
			}
			const double score = MOVE_SURE * s.net - MOVE_TU * c.tu - EXPOSED * exposed - IN_WAY * std::min(2, inWay);
			if (score > bestScore)
			{
				bestScore = score;
				out = Plan();
				out.kind = MOVE;
				out.actor = u;
				out.cell = c.cell;
				out.cellTu = c.tu;
				out.score = score;
				out.exposed = exposed;
				out.mode = *c.m;
				out.target = *c.t;
				out.shot = s;
				out.shot.m = 0;
				out.shot.t = 0;
			}
		}
		return bestScore > -1e8;
	}

	/// A cell under cover closer to a contact: nothing to fire at this turn, but the next.
	bool bestApproach(BattleUnit *u, const std::vector<Mode> &modes, Plan &out)
	{
		if (gen->lineChecks > LINE_BUDGET || approached.count(u->getId()) || !u->isSmallUnit() || !u->getArmor()->allowsMoving())
		{
			return false;
		}
		int range = 0;
		for (const Mode &m : modes)
		{
			if (!m.melee)
			{
				range = std::max(range, std::min(m.maxRange, std::max(m.upper, 8)));
			}
		}
		if (!range)
		{
			return false; // a blade only: the unit's own think knows how to charge (a walk under cover would take that from it)
		}
		const Position here = u->getPosition();
		const Target *goal = 0;
		double dGoal = 1e9;
		const double stride = u->getBaseStats()->tu / 4.0;
		for (const Target &t : bs->targets)
		{
			const double d = ActionGenerator::dist(here, t.at);
			if (d < dGoal)
			{
				dGoal = d;
				goal = &t;
			}
		}
		if (!goal || dGoal > 2 * stride + range || dGoal <= std::min(range, 6))
		{
			return false;
		}
		Pathfinding *pf = bs->save->getPathfinding();
		const std::vector<int> reach = pf->findReachable(u, BattleActionCost());
		std::vector<std::pair<double, Position>> cells;
		for (int index : reach)
		{
			const Position c = bs->save->getTileCoords(index);
			Tile *tile = bs->save->getTile(c);
			if (c == here || !tile || tile->getUnit() || tile->getDangerous() || claimed.count(ActionGenerator::pack(c)))
			{
				continue;
			}
			const double d = ActionGenerator::dist(c, goal->at);
			if (d >= dGoal - 1)
			{
				continue;
			}
			cells.push_back({ d + 0.02 * pf->reachedTU(c), c });
		}
		std::stable_sort(cells.begin(), cells.end(), [](const std::pair<double, Position> &a, const std::pair<double, Position> &b) { return a.first < b.first; });
		int looked = 0;
		for (const auto &c : cells)
		{
			if (++looked > 6)
			{
				break;
			}
			const Tile *tile = bs->save->getTile(c.second);
			bool hidden = true;
			for (const Target &t : bs->targets)
			{
				if (t.seen && ActionGenerator::dist(c.second, t.at) < 30 && gen->lineFrom(u, c.second, tile, t.u))
				{
					hidden = false;
					break;
				}
			}
			if (hidden)
			{
				out = Plan();
				out.kind = APPROACH_WALK;
				out.actor = u;
				out.cell = c.second;
				out.cellTu = pf->reachedTU(c.second);
				out.score = APPROACH;
				out.target = *goal;
				return true;
			}
		}
		return false;
	}

	/// A comrade with nothing better to do steps out of a shot: a line the engine says only he closes, or a shot he is the risk of. Proved on the real tiles.
	bool bestClear(BattleUnit *b, const Mode &m, const Target &t, const Shot *now, const std::map<int, bool> &busy, Plan &out)
	{
		if (gen->lineChecks > LINE_BUDGET)
		{
			return false;
		}
		bool found = false;
		for (BattleUnit *a : bs->ready)
		{
			auto it = busy.find(a->getId());
			if (a == b || !a->isSmallUnit() || !a->getArmor()->allowsMoving() || (it != busy.end() && it->second) || !ActionGenerator::nearSegment(a->getPosition(), b->getPosition(), t.at, 1.5))
			{
				continue;
			}
			const auto key = std::make_tuple(a->getId(), b->getId(), t.u->getId());
			if (triedClear.count(key))
			{
				continue;
			}
			double before = now ? now->net : 0;
			if (!now)
			{
				if (!gen->lineWithout(b, t, a))
				{
					triedClear.insert(key);
					continue;
				}
			}
			const Shot after = judge(b, b->getPosition(), m, t, true, b->getTimeUnits(), a);
			const double gain = after.net - std::max(0.0, before);
			if (after.net < USEFUL || gain < CLEAR_MIN)
			{
				triedClear.insert(key);
				continue;
			}
			Pathfinding *pf = bs->save->getPathfinding();
			const std::vector<int> reach = pf->findReachable(a, BattleActionCost());
			bool have = false;
			Position cell;
			int cellTu = 1 << 30;
			for (int index : reach)
			{
				const Position c = bs->save->getTileCoords(index);
				Tile *tile = bs->save->getTile(c);
				if (c == a->getPosition() || !tile || tile->getUnit() || tile->getDangerous() || c.z != a->getPosition().z || claimed.count(ActionGenerator::pack(c))
					|| ActionGenerator::nearSegment(c, b->getPosition(), t.at, 1.5))
				{
					continue;
				}
				const int tu = pf->reachedTU(c);
				if (tu < cellTu)
				{
					have = true;
					cell = c;
					cellTu = tu;
				}
			}
			if (!have)
			{
				triedClear.insert(key);
				continue;
			}
			const double score = CLEAR_SURE * gain - MOVE_TU * cellTu;
			if (score > out.score)
			{
				out = Plan();
				out.kind = CLEAR;
				out.actor = a;
				out.cell = cell;
				out.cellTu = cellTu;
				out.helps = b;
				out.score = score;
				out.gain = gain;
				out.target = t;
				out.mode = m;
				found = true;
			}
		}
		return found;
	}

	/// The one next action of the side. Everything is compared on one scale, who acts is part of the answer.
	Plan pick()
	{
		Plan best;
		struct Row { BattleUnit *u; std::vector<Mode> modes; Shot shot; Mode mode; Target target; bool has; std::vector<std::pair<const Mode*, const Target*>> blocked; };
		std::vector<Row> rows;
		rows.reserve(bs->ready.size());
		std::vector<std::pair<Position, Position>> shots;
		std::map<int, bool> busy;
		for (BattleUnit *u : bs->ready)
		{
			rows.emplace_back();
			Row &r = rows.back();
			r.u = u;
			r.modes = gen->modesOf(u);
			r.has = !r.modes.empty() && bestAttack(u, r.modes, r.shot, r.mode, r.target, &r.blocked);
			if (r.has)
			{
				r.shot.m = &r.mode;
				r.shot.t = &r.target;
			}
			const bool useful = r.has && r.shot.net >= USEFUL;
			busy[u->getId()] = useful;
			if (useful)
			{
				shots.push_back({ u->getPosition(), r.target.at });
			}
			if (r.has && r.shot.net >= MIN_NET && r.shot.net > best.score)
			{
				best = Plan();
				best.kind = ATTACK;
				best.actor = u;
				best.shot = r.shot;
				best.mode = r.mode;
				best.target = r.target;
				best.score = r.shot.net;
			}
		}
		// ENABLE: a shot that only a comrade spoils or closes
		for (Row &r : rows)
		{
			if (r.has && r.shot.ff > 0 && r.shot.net >= MIN_NET)
			{
				Plan c;
				if (bestClear(r.u, r.mode, r.target, &r.shot, busy, c) && c.score > best.score)
				{
					best = c;
				}
			}
			else if (!(r.has && r.shot.net >= USEFUL))
			{
				for (const auto &blocked : r.blocked)
				{
					Plan c;
					if (bestClear(r.u, *blocked.first, *blocked.second, 0, busy, c) && c.score > best.score)
					{
						best = c;
					}
				}
			}
		}
		// MOVE FOR PURPOSE: only who has no worthwhile attack where it stands
		for (Row &r : rows)
		{
			if ((r.has && r.shot.net >= USEFUL) || r.modes.empty() || r.u->getHealth() * 100 < MIN_HEALTH_PCT * r.u->getBaseStats()->health)
			{
				continue;
			}
			MoveMemo &memo = moves[r.u->getId()];
			if (memo.version != bs->version || memo.tu != r.u->getTimeUnits() || memo.at != r.u->getPosition())
			{
				memo.version = bs->version;
				memo.tu = r.u->getTimeUnits();
				memo.at = r.u->getPosition();
				memo.plan = Plan();
				memo.any = bestCell(r.u, r.modes, shots, memo.plan);
				if (!memo.any && !(r.has && r.shot.net >= MIN_NET))
				{
					memo.any = bestApproach(r.u, r.modes, memo.plan);
				}
			}
			if (memo.any && memo.plan.score > best.score && (!r.has || memo.plan.score > r.shot.net))
			{
				if (!claimed.count(ActionGenerator::pack(memo.plan.cell)))
				{
					best = memo.plan;
				}
			}
		}
		return best;
	}
};

// ---------------------------------------------------------------------------------------------------------------------------------- ActionExecutor

class ActionExecutor
{
public:
	BattleState bs;
	ActionGenerator gen;
	SidePlanner planner;

	struct Pending
	{
		bool on = false;
		char kind = 0;
		BattleUnit *actor = 0, *target = 0;
		Position at, targetAt;
		int tu = 0, tHealth = 0, tStun = 0, radius = 0, helps = 0;
		std::vector<std::pair<BattleUnit*, int>> ownHp;
		double eff = 0, ff = 0;
	};

	Pending pending;
	SidePlanner::Plan kept;
	bool keptOn = false;
	std::set<int> consulted;
	std::map<int, int> fails;
	std::map<int, Position> lastPos;
	std::set<int> seenLast;
	bool seenKnown = false;
	BattleUnit *cursor = 0; // where the engine's own round stood when the side took over: the selection goes back there (a jump past it would read as a wrap: AiProbe::secondPassWrapped, and the low ids lose their second pass)
	int cursorRounds = 0; // the think rounds the unit at the cursor had used when the side took over: it gets the rest of them back, not two new ones
	bool cursorTaken = false, cursorBack = false;
	int acts = 0, attacks = 0, walks = 0, clears = 0, approaches = 0, thinks = 0, consults = 0, keptSpecial = 0, vetoes = 0, switches = 0, overBudget = 0, backs = 0;
	long long usTurn = 0, usTotal = 0;
	int calls = 0;

	ActionExecutor()
	{
		gen.bs = &bs;
		planner.bs = &bs;
		planner.gen = &gen;
	}

	static std::string pos(const Position &p)
	{
		std::ostringstream s;
		s << "[" << p.x << "," << p.y << "," << p.z << "]";
		return s.str();
	}

	void journal(const std::string &body)
	{
		Log(LOG_INFO) << "[AISCD] {\"turn\":" << bs.turn << "," << body << "}";
	}

	void turnEnd()
	{
		if (bs.turn < 0 || !calls)
		{
			return;
		}
		std::ostringstream s;
		s << "\"ev\":\"turn_end\",\"calls\":" << calls << ",\"us\":" << usTurn << ",\"usTotal\":" << usTotal << ",\"acts\":" << acts << ",\"attacks\":" << attacks << ",\"walks\":" << walks
			<< ",\"clears\":" << clears << ",\"approaches\":" << approaches << ",\"thinks\":" << thinks << ",\"consults\":" << consults << ",\"special\":" << keptSpecial
			<< ",\"vetoes\":" << vetoes << ",\"switches\":" << switches << ",\"lines\":" << gen.lineChecks << ",\"over\":" << overBudget << ",\"banned\":" << bs.banned.size() << ",\"backs\":" << backs;
		journal(s.str());
	}

	void newTurn(SavedBattleGame *save)
	{
		turnEnd();
		bs.newTurn(save);
		planner.newTurn();
		gen.lines.clear();
		gen.lineChecks = 0;
		pending = Pending();
		keptOn = false;
		consulted.clear();
		fails.clear();
		lastPos.clear();
		seenLast.clear();
		seenKnown = false;
		cursor = 0;
		cursorTaken = cursorBack = false;
		acts = attacks = walks = clears = approaches = thinks = consults = keptSpecial = vetoes = switches = overBudget = backs = 0;
		usTurn = 0;
		calls = 0;
	}

	/// What really happened to the last action.
	void observe()
	{
		if (!pending.on)
		{
			return;
		}
		pending.on = false;
		BattleUnit *a = pending.actor;
		const int spent = pending.tu - a->getTimeUnits();
		const bool moved = a->getPosition() != pending.at;
		bool tOut = false, tHit = false;
		if (pending.target)
		{
			tOut = pending.target->isOut();
			// the one look at a target's condition: that this shot visibly hit it, yes or no, and only for this turn's concentration of fire
			tHit = tOut || pending.target->getHealth() < pending.tHealth || pending.target->getStunlevel() > pending.tStun;
			if (tHit)
			{
				++bs.hitsTurn[pending.target->getId()];
			}
		}
		int ownLoss = 0, ownDown = 0;
		for (const auto &h : pending.ownHp)
		{
			const int loss = h.second - h.first->getHealth();
			if (h.first != pending.actor || loss > 0)
			{
				ownLoss += std::max(0, loss);
			}
			if (h.first->isOut())
			{
				++ownDown;
			}
		}
		if (spent <= 0 && !moved && !a->isOut())
		{
			if (++fails[a->getId()] >= FAILS_BAN)
			{
				bs.banned.insert(a->getId());
			}
		}
		if (pending.kind == 'A')
		{
			if (pending.radius > 0)
			{
				gen.lines.clear();
			}
			else if (pending.target)
			{
				gen.forgetNear(pending.targetAt, 2.0);
			}
		}
		std::ostringstream s;
		s << "\"ev\":\"result\",\"kind\":\"" << pending.kind << "\",\"actor\":" << a->getId() << ",\"spent\":" << spent << ",\"moved\":" << (moved ? 1 : 0) << ",\"actorOut\":" << (a->isOut() ? 1 : 0)
			<< ",\"at\":" << pos(a->getPosition());
		if (pending.target)
		{
			// the record only, never read back: what the shot did
			s << ",\"target\":" << pending.target->getId() << ",\"tOut\":" << (tOut ? 1 : 0) << ",\"tHit\":" << (tHit ? 1 : 0) << ",\"tDmg\":" << pending.tHealth - pending.target->getHealth()
				<< ",\"tStun\":" << pending.target->getStunlevel() - pending.tStun;
		}
		s << ",\"ownLoss\":" << ownLoss << ",\"ownDown\":" << ownDown << ",\"eff\":" << pending.eff << ",\"ff\":" << pending.ff;
		journal(s.str());
	}

	void syncMoves()
	{
		auto note = [&](const BattleUnit *u)
		{
			const Position now = u->getPosition();
			auto it = lastPos.find(u->getId());
			if (it == lastPos.end())
			{
				lastPos[u->getId()] = now;
			}
			else if (it->second != now)
			{
				gen.forgetNear(it->second, 1.2);
				gen.forgetNear(now, 1.2);
				it->second = now;
			}
		};
		for (const BattleUnit *u : bs.own)
		{
			note(u);
		}
		for (const Target &t : bs.targets)
		{
			if (t.seen)
			{
				note(t.u);
			}
		}
	}

	/// Does the unit have something the first generator does not know?
	bool special(SavedBattleGame *save, BattleUnit *u) const
	{
		if (u->getGrenadeFromBelt(save) || u->getSpecialWeapon(BT_PSIAMP))
		{
			return true;
		}
		for (const BattleItem *w : { u->getRightHandWeapon(), u->getLeftHandWeapon() })
		{
			if (w && (w->getRules()->getBattleType() == BT_PSIAMP || w->getRules()->isGrenadeOrProxy() || w->getRules()->getArcingShot() || w->getRules()->getWaypoints() != 0))
			{
				return true;
			}
		}
		return false;
	}

	/// The side has nothing to give out: the round goes on from where the engine stood, or from the next that can act if that one is gone.
	Result handBack(SavedBattleGame *save, BattleUnit *unit, BattleUnit **other)
	{
		BattleUnit *c = cursor;
		cursor = 0;
		if (!c || c == unit)
		{
			return PASS;
		}
		std::vector<BattleUnit*> &units = *save->getUnits();
		for (auto i = std::find(units.begin(), units.end(), c); i != units.end(); ++i)
		{
			if ((*i)->isSelectable(FACTION_HOSTILE, true, false))
			{
				if (*i == unit)
				{
					return PASS;
				}
				*other = *i;
				cursorBack = *i == c;
				++backs;
				return SWITCH;
			}
		}
		return PASS;
	}

	Result stepInner(int level, SavedBattleGame *save, BattleUnit *unit, BattleAction *action, BattleUnit **other)
	{
		const int lastActor = pending.on ? pending.actor->getId() : -1;
		observe();
		bs.refresh();
		syncMoves();
		// the record only: who of the enemy came into the side's sight since the last call, and through whose action
		std::set<int> seenNow;
		std::ostringstream fresh;
		for (const Target &t : bs.targets)
		{
			if (t.seen)
			{
				seenNow.insert(t.u->getId());
				if (!seenLast.count(t.u->getId()))
				{
					fresh << (fresh.tellp() > 0 ? "," : "") << t.u->getId();
				}
			}
		}
		if (seenKnown && fresh.tellp() > 0)
		{
			std::ostringstream s;
			s << "\"ev\":\"revealed\",\"by\":" << lastActor << ",\"ids\":[" << fresh.str() << "]";
			journal(s.str());
		}
		seenLast.swap(seenNow);
		seenKnown = true;
		if (gen.lineChecks > LINE_BUDGET)
		{
			overBudget = 1;
		}
		bool anySeen = false;
		for (const Target &t : bs.targets)
		{
			anySeen = anySeen || t.seen;
		}
		if (bs.targets.empty() || acts > MAX_ACTS_FACTOR * (int)bs.own.size())
		{
			keptOn = false;
			return handBack(save, unit, other);
		}
		SidePlanner::Plan plan;
		if (keptOn && kept.actor == unit)
		{
			plan = kept;
		}
		else
		{
			plan = planner.pick();
		}
		keptOn = false;
		if (plan.kind == SidePlanner::NONE)
		{
			return handBack(save, unit, other);
		}
		if (plan.kind == SidePlanner::ATTACK)
		{
			plan.shot.m = &plan.mode;
			plan.shot.t = &plan.target;
		}
		if (level == 1)
		{
			std::ostringstream s;
			s << "\"ev\":\"would\",\"kind\":" << (int)plan.kind << ",\"actor\":" << plan.actor->getId() << ",\"score\":" << plan.score;
			journal(s.str());
			return PASS;
		}
		if (plan.actor != unit)
		{
			if (!cursor)
			{
				cursor = unit;
				cursorTaken = true;
			}
			kept = plan;
			keptOn = true;
			++switches;
			*other = plan.actor;
			return SWITCH;
		}
		pending = Pending();
		pending.on = true;
		pending.actor = unit;
		pending.at = unit->getPosition();
		pending.tu = unit->getTimeUnits();
		for (BattleUnit *u : bs.own)
		{
			pending.ownHp.push_back({ u, u->getHealth() });
		}
		action->actor = unit;
		std::ostringstream s;
		if (plan.kind == SidePlanner::ATTACK)
		{
			// the real state decides, not the plan: the line once more from the engine
			gen.lines.erase(std::make_tuple(unit->getId(), ActionGenerator::pack(unit->getPosition()), ActionGenerator::pack(plan.target.at)));
			if (!plan.mode.melee && !gen.lineNow(unit, plan.target).line)
			{
				pending.on = false;
				return handBack(save, unit, other);
			}
			action->type = plan.mode.type;
			action->weapon = plan.mode.weapon;
			action->target = plan.target.u->getPosition();
			pending.kind = 'A';
			pending.target = plan.target.u;
			pending.targetAt = plan.target.at;
			pending.tHealth = plan.target.u->getHealth();
			pending.tStun = plan.target.u->getStunlevel();
			pending.radius = plan.mode.radius;
			pending.eff = plan.shot.eff;
			pending.ff = plan.shot.ff;
			++attacks;
			s << "\"ev\":\"act\",\"kind\":\"A\",\"actor\":" << unit->getId() << ",\"pos\":" << pos(unit->getPosition()) << ",\"tu\":" << unit->getTimeUnits() << ",\"target\":" << plan.target.u->getId()
				<< ",\"tAt\":" << pos(plan.target.at) << ",\"t\":" << (int)plan.mode.type << ",\"w\":\"" << plan.mode.rule->getType() << "\",\"cost\":" << plan.mode.tu << ",\"turnTu\":" << plan.shot.turnTu
				<< ",\"d\":" << plan.shot.d << ",\"acc\":" << plan.shot.acc << ",\"pHit\":" << plan.shot.pHit << ",\"eff\":" << plan.shot.eff << ",\"ff\":" << plan.shot.ff << ",\"net\":" << plan.shot.net
				<< ",\"rep\":" << plan.shot.rep << ",\"los\":" << (plan.shot.los ? 1 : 0) << ",\"radius\":" << plan.mode.radius << ",\"hits\":" << plan.target.hits;
		}
		else
		{
			action->type = BA_WALK;
			action->target = plan.cell;
			planner.claimed.insert(ActionGenerator::pack(plan.cell));
			pending.kind = plan.kind == SidePlanner::MOVE ? 'M' : plan.kind == SidePlanner::CLEAR ? 'C' : 'P';
			if (plan.kind == SidePlanner::MOVE)
			{
				++walks;
			}
			else if (plan.kind == SidePlanner::CLEAR)
			{
				++clears;
				pending.helps = plan.helps->getId();
				planner.triedClear.insert(std::make_tuple(unit->getId(), plan.helps->getId(), plan.target.u->getId()));
			}
			else
			{
				++approaches;
				planner.approached.insert(unit->getId());
			}
			s << "\"ev\":\"act\",\"kind\":\"" << pending.kind << "\",\"actor\":" << unit->getId() << ",\"pos\":" << pos(unit->getPosition()) << ",\"tu\":" << unit->getTimeUnits() << ",\"to\":" << pos(plan.cell)
				<< ",\"walkTu\":" << plan.cellTu << ",\"score\":" << plan.score << ",\"goal\":" << plan.target.u->getId() << ",\"seen\":" << (plan.target.seen ? 1 : 0);
			if (plan.kind == SidePlanner::MOVE)
			{
				s << ",\"net\":" << plan.shot.net << ",\"eff\":" << plan.shot.eff << ",\"ff\":" << plan.shot.ff << ",\"exposed\":" << plan.exposed << ",\"t\":" << (int)plan.mode.type;
			}
			if (plan.kind == SidePlanner::CLEAR)
			{
				s << ",\"helps\":" << plan.helps->getId() << ",\"gain\":" << plan.gain << ",\"helpsAt\":" << pos(plan.helps->getPosition());
			}
		}
		++acts;
		journal(s.str());
		if (special(save, unit) && !consulted.count(unit->getId())) // before any plan: a walk would spend the time units psi and throws need
		{
			consulted.insert(unit->getId());
			++consults;
			return CONSULT;
		}
		return ACT;
	}
};

ActionExecutor ex;

int levelNow()
{
	static const int level = (int)AiProbe::param("OXCE_AI_SCD", 0);
	return level;
}

} // namespace

Result step(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, BattleUnit **other)
{
	const int level = levelNow();
	if (level == 0 || save->getSide() != FACTION_HOSTILE || unit->getFaction() != FACTION_HOSTILE)
	{
		return PASS;
	}
	const auto t0 = std::chrono::steady_clock::now();
	if (ex.bs.save != save || ex.bs.turn != save->getTurn())
	{
		ex.newTurn(save);
	}
	const uint64_t rng = RNG::getSeed();
	const Result r = ex.stepInner(level, save, unit, action, other);
	if (RNG::getSeed() != rng)
	{
		ex.journal("\"ev\":\"rng_touched\""); // must never be written: the director rolls no dice
	}
	const long long us = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - t0).count();
	ex.usTurn += us;
	ex.usTotal += us;
	++ex.calls;
	return r;
}

int roundsAfterSwitch(int rounds)
{
	if (ex.cursorTaken)
	{
		ex.cursorTaken = false;
		ex.cursorRounds = rounds;
		return 0;
	}
	if (ex.cursorBack)
	{
		ex.cursorBack = false;
		return ex.cursorRounds;
	}
	return 0;
}

bool afterThink(SavedBattleGame *save, BattleUnit *unit, BattleAction *action, Result result, const BattleAction &planned)
{
	const int level = levelNow();
	if (level < 2 || save->getSide() != FACTION_HOSTILE || unit->getFaction() != FACTION_HOSTILE)
	{
		return false;
	}
	if (result == CONSULT)
	{
		// the unit's own special action goes first: it knows throws and psi, the first generator does not
		if (action->type == BA_THROW || action->type == BA_PANIC || action->type == BA_MINDCONTROL || action->type == BA_USE || action->type == BA_LAUNCH)
		{
			++ex.keptSpecial;
			ex.consulted.erase(unit->getId()); // it may have another one left
			ex.pending.kind = 'T';
			ex.pending.target = 0;
			std::ostringstream s;
			s << "\"ev\":\"special\",\"actor\":" << unit->getId() << ",\"t\":" << (int)action->type;
			ex.journal(s.str());
			return false;
		}
		const int number = action->number;
		*action = planned;
		action->number = number;
		return true;
	}
	++ex.thinks;
	if (action->type != BA_SNAPSHOT && action->type != BA_AUTOSHOT && action->type != BA_AIMEDSHOT)
	{
		return false;
	}
	// a shot of its own that the side's scale says hurts us more than them does not go out
	Tile *tile = save->getTile(action->target);
	BattleUnit *on = tile ? tile->getUnit() : 0;
	if ((on && on->getFaction() == FACTION_HOSTILE) || !action->weapon)
	{
		return false;
	}
	ex.bs.refresh();
	// only a unit the side sees is judged as a unit; anything else is a shot at a place whatever stands there, and only its risk counts
	Target t;
	t.at = action->target;
	for (const Target &known : ex.bs.targets)
	{
		if (known.seen && known.u == on)
		{
			t = known;
			break;
		}
	}
	const std::vector<Mode> modes = ex.gen.modesOf(unit);
	for (const Mode &m : modes)
	{
		if (m.type == action->type && m.weapon == action->weapon)
		{
			const Shot s = ex.planner.judge(unit, unit->getPosition(), m, t, true, unit->getTimeUnits(), 0);
			if (s.net > -1e8 && (t.u ? s.net <= 0 : s.net <= -MIN_NET))
			{
				++ex.vetoes;
				std::ostringstream o;
				o << "\"ev\":\"veto\",\"actor\":" << unit->getId() << ",\"target\":" << (t.u ? t.u->getId() : -1) << ",\"t\":" << (int)m.type << ",\"w\":\"" << m.rule->getType() << "\",\"d\":" << s.d << ",\"acc\":" << s.acc
					<< ",\"eff\":" << s.eff << ",\"ff\":" << s.ff;
				ex.journal(o.str());
				action->type = BA_NONE;
			}
			break;
		}
	}
	return false;
}

}
}
