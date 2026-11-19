#pragma once
/*
* Copyright 2010-2016 OpenXcom Developers.
*
* This file is part of OpenXcom.
*
* OpenXcom is free software: you can redistribute it and/or modify
* it under the terms of the GNU General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* OpenXcom is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with OpenXcom.  If not, see <http://www.gnu.org/licenses/>.
*/
#include <string>
#include <unordered_map>
#include <utility>
#include <sstream>
#include "../Engine/Yaml.h"
#include "BattleUnit.h"
#include "../Engine/Language.h"

namespace OpenXcom
{

/**
 * A string of a kill record, kept once for all the records that carry it: the tens of thousands of records of a
 * long campaign repeat a few hundred names of units, ranks, races and weapons.
 * The pool belongs to no saved game. A record holds a counted reference and a string leaves the pool with its
 * last record: the pool is empty when no game is loaded, and holds the strings of two games only while one
 * is being loaded over the other. The empty string takes no place in it.
 * The main thread only, as the saved game itself.
 */
class PooledString
{
	typedef std::unordered_map<std::string, size_t> Pool;
	Pool::value_type *_entry;
	static Pool &pool()
	{
		static Pool strings;
		return strings;
	}
	static const std::string &none()
	{
		static const std::string empty;
		return empty;
	}
	static Pool::value_type *take(const std::string &s)
	{
		if (s.empty())
		{
			return nullptr;
		}
		Pool::value_type &entry = *pool().emplace(s, 0).first;
		++entry.second;
		return &entry;
	}
	static void drop(Pool::value_type *entry)
	{
		if (entry && --entry->second == 0)
		{
			pool().erase(pool().find(entry->first));
		}
	}
public:
	PooledString() : _entry(nullptr) {}
	PooledString(const std::string &s) : _entry(take(s)) {}
	PooledString(const char *s) : _entry(take(s)) {}
	PooledString(const PooledString &o) : _entry(o._entry)
	{
		if (_entry) ++_entry->second;
	}
	PooledString(PooledString &&o) noexcept : _entry(o._entry)
	{
		o._entry = nullptr;
	}
	~PooledString()
	{
		drop(_entry);
	}
	PooledString &operator=(const PooledString &o)
	{
		if (o._entry) ++o._entry->second;
		drop(_entry);
		_entry = o._entry;
		return *this;
	}
	PooledString &operator=(PooledString &&o) noexcept
	{
		std::swap(_entry, o._entry);
		return *this;
	}
	PooledString &operator=(const std::string &s)
	{
		Pool::value_type *entry = take(s);
		drop(_entry);
		_entry = entry;
		return *this;
	}
	PooledString &operator=(const char *s)
	{
		return *this = std::string(s);
	}
	operator const std::string &() const { return str(); }
	const std::string &str() const { return _entry ? _entry->first : none(); }
	bool empty() const { return !_entry; }
	const char *c_str() const { return str().c_str(); }
	bool operator==(const PooledString &o) const { return _entry == o._entry; }
	bool operator!=(const PooledString &o) const { return _entry != o._entry; }
	bool operator==(const std::string &o) const { return str() == o; }
	bool operator!=(const std::string &o) const { return str() != o; }
	bool operator==(const char *o) const { return str() == o; }
	bool operator!=(const char *o) const { return str() != o; }
	/// How many different strings the pool holds now.
	static size_t poolSize() { return pool().size(); }
};

/**
 * Container for battle unit kills statistics.
 */
struct BattleUnitKills
{
	// Variables
	PooledString name;
	PooledString type, rank, race, weapon, weaponAmmo;
	UnitFaction faction;
	UnitStatus status;
	int mission, turn, id;
	UnitSide side;
	UnitBodyPart bodypart;

	// Functions
	/// Make turn unique across all kills
	int makeTurnUnique()
	{
		return turn += mission * 300; // Maintains divisibility by 3 as well
	}

	/// Check to see if turn was on HOSTILE side
	bool hostileTurn() const
	{
		if ((turn - 1) % 3 == 0) return true;
		return false;
	}

	/// Make turn unique across mission
	void setTurn(int unitTurn, UnitFaction unitFaction)
	{
		turn = unitTurn * 3 + (int)unitFaction;
	}

	/// Load
	void load(const YAML::YamlNodeReader& reader)
	{
		std::string text;
		if (reader.tryRead("type", text)) type = text; // The ones killed are usually hostiles, so read this first
		if (type.empty() && reader.tryRead("name", text)) name = text; // Can't have both type and name at the same time
		if (reader.tryRead("rank", text)) rank = text;
		if (reader.tryRead("race", text)) race = text;
		if (reader.tryRead("weapon", text)) weapon = text;
		if (reader.tryRead("weaponAmmo", text)) weaponAmmo = text;
		reader.tryRead("status", status);
		reader.tryRead("faction", faction);
		reader.tryRead("mission", mission);
		reader.tryRead("turn", turn);
		reader.tryRead("side", side);
		reader.tryRead("bodypart", bodypart);
		reader.tryRead("id", id);
	}

	/// Save
	void save(YAML::YamlNodeWriter writer) const
	{
		writer.setAsMap();
		writer.setFlowStyle();
		if (!name.empty())
			writer.write("name", name.str());
		if (!type.empty())
			writer.write("type", type.str());
		writer.write("rank", rank.str());
		writer.write("race", race.str());
		writer.write("weapon", weapon.str());
		writer.write("weaponAmmo", weaponAmmo.str());
		writer.write("status", status);
		writer.write("faction", faction);
		writer.write("mission", mission);
		writer.write("turn", turn);
		writer.write("side", side);
		writer.write("bodypart", bodypart);
		writer.write("id", id);
	}

	/// Convert kill Status to string.
	std::string getKillStatusString() const
	{
		switch (status)
		{
		case STATUS_DEAD:           return "STR_KILLED";
		case STATUS_UNCONSCIOUS:    return "STR_STUNNED";
		case STATUS_PANICKING:		return "STR_PANICKED";
		case STATUS_TURNING:		return "STR_MINDCONTROLLED";
		default:                    return "status error";
		}
	}

	/// Convert victim Status to string.
	std::string getUnitStatusString() const
	{
		switch (status)
		{
		case STATUS_DEAD:           return "STATUS_DEAD";
		case STATUS_UNCONSCIOUS:    return "STATUS_UNCONSCIOUS";
		case STATUS_PANICKING:		return "STATUS_PANICKING";
		case STATUS_TURNING:		return "STATUS_TURNING";
		default:                    return "status error";
		}
	}

	/// Convert victim Faction to string.
	std::string getUnitFactionString() const
	{
		switch (faction)
		{
		case FACTION_PLAYER:    return "FACTION_PLAYER";
		case FACTION_HOSTILE:   return "FACTION_HOSTILE";
		case FACTION_NEUTRAL:   return "FACTION_NEUTRAL";
		default:                return "faction error";
		}
	}

	/// Convert victim Side to string.
	std::string getUnitSideString() const
	{
		switch (side)
		{
		case SIDE_FRONT:    return "SIDE_FRONT";
		case SIDE_LEFT:     return "SIDE_LEFT";
		case SIDE_RIGHT:    return "SIDE_RIGHT";
		case SIDE_REAR:     return "SIDE_REAR";
		case SIDE_UNDER:    return "SIDE_UNDER";
		default:            return "side error";
		}
	}

	/// Convert victim Body part to string.
	std::string getUnitBodyPartString() const
	{
		switch (bodypart)
		{
		case BODYPART_HEAD:     return "BODYPART_HEAD";
		case BODYPART_TORSO:    return "BODYPART_TORSO";
		case BODYPART_RIGHTARM: return "BODYPART_RIGHTARM";
		case BODYPART_LEFTARM:  return "BODYPART_LEFTARM";
		case BODYPART_RIGHTLEG: return "BODYPART_RIGHTLEG";
		case BODYPART_LEFTLEG:  return "BODYPART_LEFTLEG";
		default:                return "body part error";
		}
	}

	/// Get human-readable victim name.
	std::string getUnitName(Language *lang) const
	{
		if (!name.empty())
		{
			return name;
		}
		else if (!type.empty())
		{
			return lang->getString(type);
		}
		else
		{
			std::ostringstream ss;
			ss << lang->getString(race) << " " << lang->getString(rank);
			return ss.str();
		}
	}

	/// Decide victim name, race and rank.
	void setUnitStats(BattleUnit *unit)
	{
		name = "";
		type = "";
		if (unit->getGeoscapeSoldier())
		{
			name = unit->getGeoscapeSoldier()->getName();
		}
		else
		{
			type = unit->getType();
		}

		if (unit->getOriginalFaction() == FACTION_PLAYER)
		{
			// Soldiers
			if (unit->getGeoscapeSoldier())
			{
				if (!unit->getGeoscapeSoldier()->getRankString().empty())
				{
					rank = unit->getGeoscapeSoldier()->getRankString();
				}
				else
				{
					rank = "STR_SOLDIER";
				}
				if (unit->getUnitRules() != 0 && !unit->getUnitRules()->getRace().empty())
				{
					race = unit->getUnitRules()->getRace();
				}
				else
				{
					race = "STR_FRIENDLY";
				}
			}
			// HWPs
			else
			{
				if (unit->getUnitRules() != 0 && !unit->getUnitRules()->getRank().empty())
				{
					rank = unit->getUnitRules()->getRank();
				}
				else
				{
					rank = "STR_HWPS";
				}
				if (unit->getUnitRules() != 0 && !unit->getUnitRules()->getRace().empty())
				{
					race = unit->getUnitRules()->getRace();
				}
				else
				{
					race = "STR_FRIENDLY";
				}
			}
		}
		// Aliens
		else if (unit->getOriginalFaction() == FACTION_HOSTILE)
		{
			if (unit->getUnitRules() != 0 && !unit->getUnitRules()->getRank().empty())
			{
				rank = unit->getUnitRules()->getRank();
			}
			else
			{
				rank = "STR_LIVE_SOLDIER";
			}
			if (unit->getUnitRules() != 0 && !unit->getUnitRules()->getRace().empty())
			{
				race = unit->getUnitRules()->getRace();
			}
			else
			{
				race = "STR_HOSTILE";
			}
		}
		// Civilians
		else if (unit->getOriginalFaction() == FACTION_NEUTRAL)
		{
			if (unit->getUnitRules() != 0 && !unit->getUnitRules()->getRank().empty())
			{
				rank = unit->getUnitRules()->getRank();
			}
			else
			{
				rank = "STR_CIVILIAN";
			}
			if (unit->getUnitRules() != 0 && !unit->getUnitRules()->getRace().empty())
			{
				race = unit->getUnitRules()->getRace();
			}
			else
			{
				race = "STR_NEUTRAL";
			}
		}
		// Error
		else
		{
			rank = "STR_UNKNOWN";
			race = "STR_UNKNOWN";
		}
	}

	/// The defaults first: load() fills only the keys the save has.
	BattleUnitKills(const YAML::YamlNodeReader& reader) : BattleUnitKills() { load(reader); }
	BattleUnitKills(): faction(FACTION_HOSTILE), status(STATUS_IGNORE_ME), mission(0), turn(0), id(0), side(SIDE_FRONT), bodypart(BODYPART_HEAD) { }
	~BattleUnitKills() { }
};

/**
 * Container for battle unit statistics.
 */
struct BattleUnitStatistics
{
	// Variables
	bool wasUnconcious;                  ///< Tracks if the soldier fell unconscious
	int shotAtCounter;                   ///< Tracks how many times the unit was shot at
	int hitCounter;                      ///< Tracks how many times the unit was hit
	int shotByFriendlyCounter;           ///< Tracks how many times the unit was hit by a friendly
	int shotFriendlyCounter;             ///< Tracks how many times the unit was hit a friendly
	bool loneSurvivor;                   ///< Tracks if the soldier was the only survivor
	bool ironMan;                        ///< Tracks if the soldier was the only soldier on the mission
	int longDistanceHitCounter;          ///< Tracks how many long distance shots were landed
	int lowAccuracyHitCounter;           ///< Tracks how many times the unit landed a low probability shot
	int shotsFiredCounter;               ///< Tracks how many times a unit has shot
	int shotsLandedCounter;              ///< Tracks how many times a unit has hit his target
	std::vector<BattleUnitKills*> kills; ///< Tracks kills
	int daysWounded;                     ///< Tracks how many days the unit was wounded for
	bool KIA;                            ///< Tracks if the soldier was killed in battle
	bool nikeCross;                      ///< Tracks if a soldier killed every alien or killed and stunned every alien
	bool mercyCross;                     ///< Tracks if a soldier stunned every alien
	int woundsHealed;                    ///< Tracks how many times a fatal wound was healed by this unit
	UnitStats delta;                     ///< Tracks the increase in unit stats (is not saved, only used during debriefing)
	int appliedStimulant;                ///< Tracks how many times this soldier applied stimulant
	int appliedPainKill;                 ///< Tracks how many times this soldier applied pain killers
	int revivedSoldier;                  ///< Tracks how many times this soldier revived another soldier
	int revivedHostile;                  ///< Tracks how many times this soldier revived another hostile
	int revivedNeutral;                  ///< Tracks how many times this soldier revived another civilian
	bool MIA;                            ///< Tracks if the soldier was left behind :(
	int martyr;                          ///< Tracks how many kills the soldier landed on the turn of his death
	int slaveKills;                      ///< Tracks how many kills the soldier landed thanks to a mind controlled unit.

	// Functions
	/// Duplicate entry check
	bool duplicateEntry(UnitStatus status, int id) const
	{
		for (const auto* buk : kills)
		{
			if (buk->id == id && buk->status == status)
			{
				return true;
			}
		}
		return false;
	}

	/// Friendly fire check
	bool hasFriendlyFired() const
	{
		for (const auto* buk : kills)
		{
			if (buk->faction == FACTION_PLAYER)
				return true;
		}
		return false;
	}

	/// Load function
	void load(const YAML::YamlNodeReader& node)
	{
		const auto& reader = node.useIndex();
		reader.tryRead("wasUnconcious", wasUnconcious);
		for (const auto& kill : reader["kills"].children())
			kills.push_back(new BattleUnitKills(kill));
		reader.tryRead("shotAtCounter", shotAtCounter);
		reader.tryRead("hitCounter", hitCounter);
		reader.tryRead("shotByFriendlyCounter", shotByFriendlyCounter);
		reader.tryRead("shotFriendlyCounter", shotFriendlyCounter);
		reader.tryRead("loneSurvivor", loneSurvivor);
		reader.tryRead("ironMan", ironMan);
		reader.tryRead("longDistanceHitCounter", longDistanceHitCounter);
		reader.tryRead("lowAccuracyHitCounter", lowAccuracyHitCounter);
		reader.tryRead("shotsFiredCounter", shotsFiredCounter);
		reader.tryRead("shotsLandedCounter", shotsLandedCounter);
		reader.tryRead("nikeCross", nikeCross);
		reader.tryRead("mercyCross", mercyCross);
		reader.tryRead("woundsHealed", woundsHealed);
		reader.tryRead("appliedStimulant", appliedStimulant);
		reader.tryRead("appliedPainKill", appliedPainKill);
		reader.tryRead("revivedSoldier", revivedSoldier);
		reader.tryRead("revivedHostile", revivedHostile);
		reader.tryRead("revivedNeutral", revivedNeutral);
		reader.tryRead("martyr", martyr);
		reader.tryRead("slaveKills", slaveKills);
	}

	/// Save function
	void save(YAML::YamlNodeWriter writer) const
	{
		writer.setAsMap();
		if (wasUnconcious) writer.write("wasUnconcious", wasUnconcious);
		writer.write("kills", kills,
			[](YAML::YamlNodeWriter& w, BattleUnitKills* k)
			{ k->save(w.write()); });
		if (shotAtCounter) writer.write("shotAtCounter", shotAtCounter);
		if (hitCounter) writer.write("hitCounter", hitCounter);
		if (shotByFriendlyCounter) writer.write("shotByFriendlyCounter", shotByFriendlyCounter);
		if (shotFriendlyCounter) writer.write("shotFriendlyCounter", shotFriendlyCounter);
		if (loneSurvivor) writer.write("loneSurvivor", loneSurvivor);
		if (ironMan) writer.write("ironMan", ironMan);
		if (longDistanceHitCounter) writer.write("longDistanceHitCounter", longDistanceHitCounter);
		if (lowAccuracyHitCounter) writer.write("lowAccuracyHitCounter", lowAccuracyHitCounter);
		if (shotsFiredCounter) writer.write("shotsFiredCounter", shotsFiredCounter);
		if (shotsLandedCounter) writer.write("shotsLandedCounter", shotsLandedCounter);
		if (nikeCross) writer.write("nikeCross", nikeCross);
		if (mercyCross) writer.write("mercyCross", mercyCross);
		if (woundsHealed) writer.write("woundsHealed", woundsHealed);
		if (appliedStimulant) writer.write("appliedStimulant", appliedStimulant);
		if (appliedPainKill) writer.write("appliedPainKill", appliedPainKill);
		if (revivedSoldier) writer.write("revivedSoldier", revivedSoldier);
		if (revivedHostile) writer.write("revivedHostile", revivedHostile);
		if (revivedNeutral) writer.write("revivedNeutral", revivedNeutral);
		if (martyr) writer.write("martyr", martyr);
		if (slaveKills) writer.write("slaveKills", slaveKills);
		// for backwards compatibility, we output empty map as null
		if (!writer.toReader()[0])
		{
			writer.unsetAsMap();
			writer.setValueNull();
		}
	}

	/// The defaults first: load() fills only the keys the save has.
	BattleUnitStatistics(const YAML::YamlNodeReader& reader) : BattleUnitStatistics() { load(reader); }
	BattleUnitStatistics() : wasUnconcious(false), shotAtCounter(0), hitCounter(0), shotByFriendlyCounter(0), shotFriendlyCounter(0), loneSurvivor(false), ironMan(false), longDistanceHitCounter(0), lowAccuracyHitCounter(0), shotsFiredCounter(0), shotsLandedCounter(0), kills(), daysWounded(0), KIA(false), nikeCross(false), mercyCross(false), woundsHealed(0), appliedStimulant(0), appliedPainKill(0), revivedSoldier(0), revivedHostile(0), revivedNeutral(0), MIA(false), martyr(0), slaveKills(0) { }
	~BattleUnitStatistics() { }
};

}
