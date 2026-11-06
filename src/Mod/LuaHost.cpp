/*
 * Copyright 2010-2026 OpenXcom Developers.
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
#include "LuaHost.h"
#include <algorithm>
#include <climits>
#include <cmath>
#include <cstring>
#include <ctime>
#include <istream>
#include <iterator>
#include <map>
#include <set>
#include <string>
#include "Armor.h"
#include "Mod.h"
#include "RuleCountry.h"
#include "RuleCraft.h"
#include "RuleDamageType.h"
#include "RuleInventory.h"
#include "RuleItem.h"
#include "RuleResearch.h"
#include "RuleSkill.h"
#include "RuleSoldier.h"
#include "RuleSoldierBonus.h"
#include "RuleUfo.h"
#include "Unit.h"
#include "../fmath.h"
#include "../Battlescape/BattlescapeGame.h"
#include "../Battlescape/BattlescapeState.h"
#include "../Battlescape/TileEngine.h"
#include "../Engine/CrossPlatform.h"
#include "../Engine/Game.h"
#include "../Engine/Language.h"
#include "../Engine/Logger.h"
#include "../Engine/LuaSandbox.h"
#include "../Engine/ModInfo.h"
#include "../Engine/Options.h"
#include "../Engine/RNG.h"
#include "../Engine/Script.h"
#include "../Engine/Unicode.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/Country.h"
#include "../Savegame/Craft.h"
#include "../Savegame/GameTime.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/Tile.h"
#include "../Savegame/Ufo.h"
#include "../../libs/lua/lua.h"
#include "../../libs/lua/lauxlib.h"

namespace OpenXcom
{

namespace
{

const char *const TYPE_UNIT = "unit";
const char *const TYPE_ITEM = "item";
const char *const TYPE_BATTLE = "battle";
const char *const TYPE_SKILL = "skill";
const char *const TYPE_SOLDIER = "soldier";
const char *const TYPE_RULE_ARMOR = "ruleArmor";
const char *const TYPE_RULE_ITEM = "ruleItem";
const char *const TYPE_RULE_DAMAGE = "ruleDamage";
const char *const TYPE_RULE_UNIT = "ruleUnit";
const char *const TYPE_RULE_SOLDIER = "ruleSoldier";
const char *const TYPE_RULE_BONUS = "ruleSoldierBonus";
const char *const TYPE_RULE_COUNTRY = "ruleCountry";
const char *const TYPE_RULE_UFO = "ruleUfo";
const char *const TYPE_RULE_CRAFT = "ruleCraft";
const char *const TYPE_TILE = "tile";
const char *const TYPE_GEOSCAPE = "geoscape";
const char *const TYPE_COUNTRY = "country";
const char *const TYPE_UFO = "ufo";
const char *const TYPE_CRAFT = "craft";
const char *const MOD_KEY = "oxce.mod";
const char *const OUT_KEY = "oxce.out";

/// What a slow API call costs a handler, in C loop steps: the counter sees it as one instruction.
const unsigned long long TAG_TICKS = 100, LIST_TICKS = 20, MESSAGE_TICKS = 20000;
const size_t MESSAGE_MAX = 200, JOURNAL_MAX = 256 * 1024;

/// Handlers and their output values, the names of the Y-script. A value in `readOnly` is shown, not taken back.
/// `onlyReads`: the Y-script gets the arguments as const, so what it may not change Lua may not either.
/// `ranges`: the game casts these values to its own enum, a number outside is refused like a non-number.
struct EventInfo
{
	const char *name;
	std::vector<const char*> outputs;
	std::set<std::string> readOnly;
	bool onlyReads = false;
	std::map<std::string, std::pair<int, int>> ranges = { };
};

const EventInfo EVENTS[LuaHost::EVENT_COUNT] = {
	{ "createUnit", { }, { } },
	{ "newTurnUnit", { }, { } },
	{ "hitUnit", { "power", "part", "side" }, { } },
	{ "damageUnit", { "to_health", "to_armor", "to_stun", "to_time", "to_energy", "to_morale", "to_wound", "to_transform", "to_mana" }, { } },
	{ "damageSpecialUnit", { "transform", "transform_chance", "self_destruct", "self_destruct_chance", "morale_loss", "fire",
		"attacker_turns_since_spotted", "attacker_turns_left_spotted_for_snipers" }, { "transform", "self_destruct" } },
	{ "healUnit", { "medikit_action_type", "body_part", "wound_recovery", "health_recovery", "energy_recovery", "stun_recovery",
		"mana_recovery", "morale_recovery", "painkiller_recovery" }, { } },
	{ "skillUseUnit", { "continue_action", "spend_tu" }, { } },
	{ "returnFromMissionUnit", { "recovery_time", "mana_loss", "health_loss", "final_mana_loss", "final_health_loss" }, { "mana_loss", "health_loss" } },
	{ "createItem", { }, { } },
	{ "newTurnItem", { }, { } },
	{ "awardExperience", { "experience_multipler", "experience_type" }, { "experience_type" }, true },
	{ "tryPsiAttackItem", { "psi_attack_success" }, { }, true },
	{ "tryPsiAttackUnit", { "psi_attack_success" }, { }, true },
	{ "tryMeleeAttackItem", { "melee_attack_success" }, { }, true },
	{ "tryMeleeAttackUnit", { "melee_attack_success" }, { }, true },
	{ "selectMoveSoundUnit", { "sound_index" }, { }, true },
	{ "newMonthCountry", { "fundingChange", "satisfaction", "formPact", "cancelPact" }, { }, true,
		{ { "satisfaction", { (int)Country::Satisfaction::ALIEN_PACT, (int)Country::Satisfaction::HAPPY } } } },
	{ "detectUfoFromBase", { "detection_type", "detection_chance" }, { }, true, { { "detection_type", { DETECTION_NONE, DETECTION_HYPERWAVE } } } },
	{ "detectUfoFromCraft", { "detection_type", "detection_chance" }, { }, true, { { "detection_type", { DETECTION_NONE, DETECTION_HYPERWAVE } } } },
	{ "applySoldierBonuses", { }, { } },
};

/// The battle screen may be gone by then: the debriefing runs after it.
bool g_noScreen = false;
/// The running handler is one of EventInfo::onlyReads.
bool g_onlyReads = false;

void checkWritable(lua_State *L)
{
	if (g_onlyReads)
	{
		luaL_error(L, "this handler only reads: the Y-script of the same name gets these objects as const");
	}
}

BattleUnit *checkUnit(lua_State *L)
{
	return static_cast<BattleUnit*>(LuaSandbox::checkObject(L, 1, TYPE_UNIT));
}

BattleItem *checkItem(lua_State *L)
{
	return static_cast<BattleItem*>(LuaSandbox::checkObject(L, 1, TYPE_ITEM));
}

int checkInt(lua_State *L, int index)
{
	const lua_Integer value = luaL_checkinteger(L, index);
	luaL_argcheck(L, value >= INT_MIN && value <= INT_MAX, index, "out of range");
	return (int)value;
}

const Mod *gameMod(lua_State *L)
{
	lua_getfield(L, LUA_REGISTRYINDEX, MOD_KEY);
	auto *mod = static_cast<const Mod*>(lua_touserdata(L, -1));
	lua_pop(L, 1);
	return mod;
}

/// An unknown tag is an error both ways: a typo that reads as 0 would never show.
template<typename Tag>
Tag checkTag(lua_State *L)
{
	LuaSandbox::from(L)->charge(L, TAG_TICKS);
	size_t len = 0;
	const char *name = luaL_checklstring(L, 2, &len);
	luaL_argcheck(L, len <= MESSAGE_MAX, 2, "too long");
	const auto tag = gameMod(L)->getScriptGlobal()->getTag<Tag>(std::string("Tag.") + name);
	if (!tag)
	{
		luaL_error(L, "no such tag '%s': declare it in the mod's ruleset, extended: tags", name);
	}
	return tag;
}

void pushOrNil(lua_State *L, const char *type, const void *object)
{
	if (object)
	{
		LuaSandbox::pushObject(L, type, const_cast<void*>(object));
	}
	else
	{
		lua_pushnil(L);
	}
}

/// The Lua type of an engine class.
template<typename T> struct LuaType;
template<> struct LuaType<BattleUnit> { static const char *name() { return TYPE_UNIT; } };
template<> struct LuaType<BattleItem> { static const char *name() { return TYPE_ITEM; } };
template<> struct LuaType<SavedBattleGame> { static const char *name() { return TYPE_BATTLE; } };
template<> struct LuaType<Soldier> { static const char *name() { return TYPE_SOLDIER; } };
template<> struct LuaType<Armor> { static const char *name() { return TYPE_RULE_ARMOR; } };
template<> struct LuaType<RuleItem> { static const char *name() { return TYPE_RULE_ITEM; } };
template<> struct LuaType<RuleDamageType> { static const char *name() { return TYPE_RULE_DAMAGE; } };
template<> struct LuaType<Unit> { static const char *name() { return TYPE_RULE_UNIT; } };
template<> struct LuaType<RuleSoldier> { static const char *name() { return TYPE_RULE_SOLDIER; } };
template<> struct LuaType<RuleSoldierBonus> { static const char *name() { return TYPE_RULE_BONUS; } };
template<> struct LuaType<RuleCountry> { static const char *name() { return TYPE_RULE_COUNTRY; } };
template<> struct LuaType<RuleUfo> { static const char *name() { return TYPE_RULE_UFO; } };
template<> struct LuaType<RuleCraft> { static const char *name() { return TYPE_RULE_CRAFT; } };
template<> struct LuaType<Tile> { static const char *name() { return TYPE_TILE; } };
template<> struct LuaType<SavedGame> { static const char *name() { return TYPE_GEOSCAPE; } };
template<> struct LuaType<Country> { static const char *name() { return TYPE_COUNTRY; } };
template<> struct LuaType<Ufo> { static const char *name() { return TYPE_UFO; } };
template<> struct LuaType<Craft> { static const char *name() { return TYPE_CRAFT; } };

template<typename T>
T *self(lua_State *L)
{
	return static_cast<T*>(LuaSandbox::checkObject(L, 1, LuaType<T>::name()));
}

template<typename M> struct MemberOf;
template<typename C, typename R, typename... A> struct MemberOf<R (C::*)(A...) const> { using Class = C; };
template<typename C, typename R, typename... A> struct MemberOf<R (C::*)(A...)> { using Class = C; };

/// A getter of the engine as a method, the same one the Y-script binds.
template<auto Getter>
int getInt(lua_State *L)
{
	lua_pushinteger(L, (int)(self<typename MemberOf<decltype(Getter)>::Class>(L)->*Getter)());
	return 1;
}

template<auto Getter>
int getBool(lua_State *L)
{
	lua_pushboolean(L, (self<typename MemberOf<decltype(Getter)>::Class>(L)->*Getter)());
	return 1;
}

template<auto Getter>
int getString(lua_State *L)
{
	lua_pushstring(L, (self<typename MemberOf<decltype(Getter)>::Class>(L)->*Getter)().c_str());
	return 1;
}

/// A getter that returns another object: its Lua type comes from the pointer.
template<auto Getter>
int getObject(lua_State *L)
{
	const auto *object = (self<typename MemberOf<decltype(Getter)>::Class>(L)->*Getter)();
	pushOrNil(L, LuaType<std::decay_t<decltype(*object)>>::name(), object);
	return 1;
}

template<auto Setter>
int setInt(lua_State *L)
{
	checkWritable(L);
	auto *object = self<typename MemberOf<decltype(Setter)>::Class>(L);
	(object->*Setter)(checkInt(L, 2));
	return 0;
}

template<typename T>
int getTagOf(lua_State *L)
{
	auto *object = self<T>(L);
	lua_pushinteger(L, object->getScriptValuesRaw().get(checkTag<ScriptTag<T>>(L)));
	return 1;
}

template<typename T>
int setTagOf(lua_State *L)
{
	checkWritable(L);
	auto *object = self<T>(L);
	const auto tag = checkTag<ScriptTag<T>>(L);
	object->luaSetTag(tag, checkInt(L, 3));
	return 0;
}

/// A list of objects as a Lua table. Every element is a new handle, a big battle has thousands of items: each is paid for.
template<typename Range, typename Pred>
int pushList(lua_State *L, const char *type, const Range &range, Pred pred)
{
	auto *sandbox = LuaSandbox::from(L);
	lua_newtable(L);
	lua_Integer count = 0;
	for (auto *object : range)
	{
		sandbox->charge(L, LIST_TICKS);
		if (object && pred(object))
		{
			pushOrNil(L, type, object);
			lua_rawseti(L, -2, ++count);
		}
	}
	return 1;
}

using StatPtr = UnitStats::Ptr;

struct StatName
{
	const char *name;
	StatPtr field;
};

/// The first four are resources: experience has no such stats.
const StatName UNIT_STATS[] = {
	{ "timeUnits", &UnitStats::tu }, { "stamina", &UnitStats::stamina }, { "health", &UnitStats::health }, { "manaPool", &UnitStats::mana },
	{ "bravery", &UnitStats::bravery }, { "reactions", &UnitStats::reactions }, { "firing", &UnitStats::firing }, { "throwing", &UnitStats::throwing },
	{ "strength", &UnitStats::strength }, { "psiStrength", &UnitStats::psiStrength }, { "psiSkill", &UnitStats::psiSkill }, { "melee", &UnitStats::melee },
};

StatPtr checkStat(lua_State *L, int index, bool experience = false)
{
	const char *name = luaL_checkstring(L, index);
	for (size_t i = experience ? 4 : 0; i < std::size(UNIT_STATS); ++i)
	{
		if (!strcmp(name, UNIT_STATS[i].name))
		{
			return UNIT_STATS[i].field;
		}
	}
	luaL_argerror(L, index, "no such stat");
	return nullptr;
}

/// The same limits as UnitStats::setMaxStatScript and addMaxStatScript.
int statAddend(int value)
{
	return std::min(std::max(value, -UnitStats::BaseStatLimit), UnitStats::BaseStatLimit);
}

int statValue(int value)
{
	return std::min(std::max(value, 1), UnitStats::BaseStatLimit);
}

using CraftStatPtr = int RuleCraftStats::*;

struct CraftStatName
{
	const char *name;
	CraftStatPtr field;
};

const CraftStatName CRAFT_STATS[] = {
	{ "fuelMax", &RuleCraftStats::fuelMax }, { "damageMax", &RuleCraftStats::damageMax }, { "speedMax", &RuleCraftStats::speedMax }, { "accel", &RuleCraftStats::accel },
	{ "radarRange", &RuleCraftStats::radarRange }, { "radarChance", &RuleCraftStats::radarChance }, { "sightRange", &RuleCraftStats::sightRange },
	{ "hitBonus", &RuleCraftStats::hitBonus }, { "avoidBonus", &RuleCraftStats::avoidBonus }, { "avoidBonus2", &RuleCraftStats::avoidBonus2 },
	{ "powerBonus", &RuleCraftStats::powerBonus }, { "armor", &RuleCraftStats::armor }, { "shieldCapacity", &RuleCraftStats::shieldCapacity },
	{ "shieldRecharge", &RuleCraftStats::shieldRecharge }, { "shieldRechargeInGeoscape", &RuleCraftStats::shieldRechargeInGeoscape },
	{ "shieldBleedThrough", &RuleCraftStats::shieldBleedThrough }, { "maxUnits", &RuleCraftStats::soldiers },
	{ "maxVehiclesAndLargeSoldiers", &RuleCraftStats::vehicles }, { "maxItems", &RuleCraftStats::maxItems },
};

int pushCraftStat(lua_State *L, const RuleCraftStats &stats)
{
	const char *name = luaL_checkstring(L, 2);
	for (const auto &stat : CRAFT_STATS)
	{
		if (!strcmp(name, stat.name))
		{
			lua_pushinteger(L, stats.*stat.field);
			return 1;
		}
	}
	return luaL_argerror(L, 2, "no such stat");
}

/// Base, fly, normal, climb: the order of BattleUnit::luaMoveCost.
int checkMoveKind(lua_State *L, int index)
{
	static const char *const NAMES[] = { "base", "fly", "normal", "climb", nullptr };
	return luaL_checkoption(L, index, nullptr, NAMES);
}

int checkAction(lua_State *L, int index)
{
	const int action = checkInt(L, index);
	luaL_argcheck(L, action >= BA_NONE && action <= BA_SELF_DESTRUCT, index, "no such action");
	return action;
}

RuleItem *checkRuleItem(lua_State *L, int index)
{
	LuaSandbox::from(L)->charge(L, TAG_TICKS);
	const char *name = luaL_checkstring(L, index);
	auto *rule = gameMod(L)->getItem(name);
	if (!rule)
	{
		luaL_error(L, "no such item '%s'", name);
	}
	return rule;
}

RuleInventory *checkSlot(lua_State *L, int index)
{
	LuaSandbox::from(L)->charge(L, TAG_TICKS);
	const char *name = luaL_checkstring(L, index);
	auto *rule = gameMod(L)->getInventory(name);
	if (!rule)
	{
		luaL_error(L, "no such inventory slot '%s'", name);
	}
	return rule;
}

template<auto Getter>
int unitGet(lua_State *L)
{
	lua_pushinteger(L, (int)(checkUnit(L)->*Getter)());
	return 1;
}

template<auto Getter>
int unitIs(lua_State *L)
{
	lua_pushboolean(L, (checkUnit(L)->*Getter)());
	return 1;
}

template<auto Stat>
int unitGetMax(lua_State *L)
{
	lua_pushinteger(L, (int)(checkUnit(L)->getBaseStats()->*Stat));
	return 1;
}

/// Setters and getters of the Y-script, see BattleUnit::LuaApi: `Field` is a member of that table.
template<auto Field>
int unitSet(lua_State *L)
{
	checkWritable(L);
	auto *unit = checkUnit(L);
	(BattleUnit::luaApi().*Field)(unit, checkInt(L, 2));
	return 0;
}

template<auto Field>
int unitSet2(lua_State *L)
{
	checkWritable(L);
	auto *unit = checkUnit(L);
	const int first = checkInt(L, 2);
	(BattleUnit::luaApi().*Field)(unit, first, checkInt(L, 3));
	return 0;
}

template<auto Field>
int unitScriptGet(lua_State *L)
{
	int value = 0;
	(BattleUnit::luaApi().*Field)(checkUnit(L), value);
	lua_pushinteger(L, value);
	return 1;
}

template<auto Field>
int unitScriptIs(lua_State *L)
{
	int value = 0;
	(BattleUnit::luaApi().*Field)(checkUnit(L), value);
	lua_pushboolean(L, value != 0);
	return 1;
}

template<auto Field>
int unitScriptGet1(lua_State *L)
{
	auto *unit = checkUnit(L);
	int value = 0;
	(BattleUnit::luaApi().*Field)(unit, value, checkInt(L, 2));
	lua_pushinteger(L, value);
	return 1;
}

int unitGetType(lua_State *L)
{
	lua_pushstring(L, checkUnit(L)->getType().c_str());
	return 1;
}

int unitGetPosition(lua_State *L)
{
	const Position pos = checkUnit(L)->getPosition();
	lua_pushinteger(L, pos.x);
	lua_pushinteger(L, pos.y);
	lua_pushinteger(L, pos.z);
	return 3;
}

int unitGetRuleArmor(lua_State *L)
{
	pushOrNil(L, TYPE_RULE_ARMOR, checkUnit(L)->getArmor());
	return 1;
}

int unitGetRightHandWeapon(lua_State *L)
{
	pushOrNil(L, TYPE_ITEM, checkUnit(L)->getRightHandWeapon());
	return 1;
}

int unitGetLeftHandWeapon(lua_State *L)
{
	pushOrNil(L, TYPE_ITEM, checkUnit(L)->getLeftHandWeapon());
	return 1;
}

int unitGetTag(lua_State *L)
{
	auto *unit = checkUnit(L);
	lua_pushinteger(L, unit->getScriptValuesRaw().get(checkTag<ScriptTag<BattleUnit>>(L)));
	return 1;
}

int unitSetTag(lua_State *L)
{
	checkWritable(L);
	auto *unit = checkUnit(L);
	const auto tag = checkTag<ScriptTag<BattleUnit>>(L);
	unit->luaSetTag(tag, checkInt(L, 3));
	return 0;
}

/// `UnitStatus` of the Y-script's isStanding, isWalking and so on.
template<UnitStatus Status>
int unitStatusIs(lua_State *L)
{
	lua_pushboolean(L, checkUnit(L)->getStatus() == Status);
	return 1;
}

int unitGetLook(lua_State *L)
{
	const auto *soldier = checkUnit(L)->getGeoscapeSoldier();
	lua_pushinteger(L, soldier ? (int)soldier->getLook() : 0);
	return 1;
}

int unitGetLookVariant(lua_State *L)
{
	const auto *soldier = checkUnit(L)->getGeoscapeSoldier();
	lua_pushinteger(L, soldier ? soldier->getLookVariant() : 0);
	return 1;
}

int unitDisableIndicators(lua_State *L)
{
	checkWritable(L);
	checkUnit(L)->disableIndicators();
	return 0;
}

int unitMakeVisible(lua_State *L)
{
	checkWritable(L);
	checkUnit(L)->setVisible(true);
	return 0;
}

BattleUnit *checkOtherUnit(lua_State *L)
{
	return static_cast<BattleUnit*>(LuaSandbox::checkObject(L, 2, TYPE_UNIT));
}

int unitGetMaxViewDistanceAtDark(lua_State *L)
{
	auto *unit = checkUnit(L);
	lua_pushinteger(L, unit->getMaxViewDistanceAtDark(checkOtherUnit(L)));
	return 1;
}

int unitGetMaxViewDistanceAtDay(lua_State *L)
{
	auto *unit = checkUnit(L);
	lua_pushinteger(L, unit->getMaxViewDistanceAtDay(checkOtherUnit(L)));
	return 1;
}

int unitGetMaxViewDistance(lua_State *L)
{
	auto *unit = checkUnit(L);
	const int base = checkInt(L, 2), nerf = checkInt(L, 3);
	lua_pushinteger(L, unit->getMaxViewDistance(base, nerf, checkInt(L, 4)));
	return 1;
}

/// A type name, or nil to clear it: the same as the script's setSpawnUnit.
int unitSetSpawnUnit(lua_State *L)
{
	checkWritable(L);
	auto *unit = checkUnit(L);
	const Unit *rule = nullptr;
	if (!lua_isnoneornil(L, 2))
	{
		LuaSandbox::from(L)->charge(L, TAG_TICKS);
		const char *name = luaL_checkstring(L, 2);
		rule = gameMod(L)->getUnit(name);
		if (!rule)
		{
			luaL_error(L, "no such unit '%s'", name);
		}
	}
	BattleUnit::luaApi().setSpawnUnit(unit, rule);
	return 0;
}

int unitGetPreviousOwner(lua_State *L)
{
	pushOrNil(L, TYPE_UNIT, checkUnit(L)->getPreviousOwner());
	return 1;
}

int unitGetMoraleMax(lua_State *L)
{
	checkUnit(L);
	lua_pushinteger(L, 100);
	return 1;
}

int unitGetVisibleUnitsCount(lua_State *L)
{
	lua_pushinteger(L, (int)checkUnit(L)->getVisibleUnits()->size());
	return 1;
}

int unitGetRuleSoldier(lua_State *L)
{
	const auto *soldier = checkUnit(L)->getGeoscapeSoldier();
	pushOrNil(L, TYPE_RULE_SOLDIER, soldier ? soldier->getRules() : nullptr);
	return 1;
}

int unitGetGeoscapeSoldier(lua_State *L)
{
	pushOrNil(L, TYPE_SOLDIER, checkUnit(L)->getGeoscapeSoldier());
	return 1;
}

int unitReduceByBravery(lua_State *L)
{
	auto *unit = checkUnit(L);
	lua_pushinteger(L, unit->reduceByBravery(checkInt(L, 2)));
	return 1;
}

int unitReduceByResistance(lua_State *L)
{
	auto *unit = checkUnit(L);
	const int value = checkInt(L, 2), type = checkInt(L, 3);
	luaL_argcheck(L, type >= 0 && type < DAMAGE_TYPES, 3, "no such damage type");
	lua_pushinteger(L, unit->reduceByResistance(value, (ItemDamageType)type));
	return 1;
}

int checkFaction(lua_State *L, int index)
{
	const int faction = checkInt(L, index);
	luaL_argcheck(L, faction >= FACTION_PLAYER && faction <= FACTION_NEUTRAL, index, "no such faction");
	return faction;
}

int unitGetTurnsSinceSpottedByFaction(lua_State *L)
{
	auto *unit = checkUnit(L);
	lua_pushinteger(L, unit->getTurnsSinceSpottedByFaction((UnitFaction)checkFaction(L, 2)));
	return 1;
}

int unitSetTurnsSinceSpottedByFaction(lua_State *L)
{
	checkWritable(L);
	auto *unit = checkUnit(L);
	const int faction = checkFaction(L, 2);
	unit->setTurnsSinceSpottedByFaction((UnitFaction)faction, checkInt(L, 3));
	return 0;
}

int unitGetTurnsLeftSpottedForSnipersByFaction(lua_State *L)
{
	auto *unit = checkUnit(L);
	lua_pushinteger(L, unit->getTurnsLeftSpottedForSnipersByFaction((UnitFaction)checkFaction(L, 2)));
	return 1;
}

int unitSetTurnsLeftSpottedForSnipersByFaction(lua_State *L)
{
	checkWritable(L);
	auto *unit = checkUnit(L);
	const int faction = checkFaction(L, 2);
	unit->setTurnsLeftSpottedForSnipersByFaction((UnitFaction)faction, checkInt(L, 3));
	return 0;
}

int unitGetTileShade(lua_State *L)
{
	const auto *tile = checkUnit(L)->getTile();
	lua_pushinteger(L, tile ? tile->getShade() : 0);
	return 1;
}

int unitGetStat(lua_State *L)
{
	auto *unit = checkUnit(L);
	lua_pushinteger(L, unit->getBaseStats()->*checkStat(L, 2));
	return 1;
}

int unitSetStat(lua_State *L)
{
	checkWritable(L);
	auto *unit = checkUnit(L);
	const StatPtr stat = checkStat(L, 2);
	unit->luaSetStat(stat, statValue(checkInt(L, 3)));
	return 0;
}

int unitAddStat(lua_State *L)
{
	checkWritable(L);
	auto *unit = checkUnit(L);
	const StatPtr stat = checkStat(L, 2);
	unit->luaSetStat(stat, statValue(statAddend(checkInt(L, 3)) + unit->getBaseStats()->*stat));
	return 0;
}

int unitGetExp(lua_State *L)
{
	auto *unit = checkUnit(L);
	lua_pushinteger(L, unit->getExpStats()->*checkStat(L, 2, true));
	return 1;
}

int unitGetMoveCost(lua_State *L)
{
	auto *unit = checkUnit(L);
	const ArmorMoveCost &cost = unit->luaMoveCost(checkMoveKind(L, 2));
	lua_pushinteger(L, cost.TimePercent);
	lua_pushinteger(L, cost.EnergyPercent);
	return 2;
}

int unitSetMoveCost(lua_State *L)
{
	checkWritable(L);
	auto *unit = checkUnit(L);
	const int kind = checkMoveKind(L, 2), time = checkInt(L, 3), energy = checkInt(L, 4);
	ArmorMoveCost &cost = unit->luaMoveCost(kind);
	cost.TimePercent = time;
	cost.EnergyPercent = energy;
	return 0;
}

int unitGetInventoryItems(lua_State *L)
{
	auto *unit = checkUnit(L);
	const RuleInventory *slot = lua_isnoneornil(L, 2) ? nullptr : checkSlot(L, 2);
	return pushList(L, TYPE_ITEM, *unit->getInventory(), [&](BattleItem *item) { return !slot || item->getSlot() == slot; });
}

/// The first item of a type in the inventory, as the script's getInventoryItem; nil when there is none.
int unitGetInventoryItem(lua_State *L)
{
	auto *unit = checkUnit(L);
	const RuleItem *rule = checkRuleItem(L, 2);
	const RuleInventory *slot = lua_isnoneornil(L, 3) ? nullptr : checkSlot(L, 3);
	for (auto *item : *unit->getInventory())
	{
		LuaSandbox::from(L)->charge(L, LIST_TICKS);
		if (item->getRules() == rule && (!slot || item->getSlot() == slot))
		{
			LuaSandbox::pushObject(L, TYPE_ITEM, item);
			return 1;
		}
	}
	lua_pushnil(L);
	return 1;
}

int unitGetSpecialItems(lua_State *L)
{
	auto *unit = checkUnit(L);
	lua_newtable(L);
	lua_Integer count = 0;
	while (auto *item = unit->luaSpecialItem((int)count))
	{
		LuaSandbox::pushObject(L, TYPE_ITEM, item);
		lua_rawseti(L, -2, ++count);
	}
	return 1;
}

const luaL_Reg UNIT_METHODS[] = {
	{ "getId", unitGet<&BattleUnit::getId> },
	{ "getType", unitGetType },
	{ "getRank", unitGet<&BattleUnit::getRankInt> },
	{ "getFaction", unitScriptGet<&BattleUnit::LuaApi::getFaction> },
	{ "getOriginalFaction", unitScriptGet<&BattleUnit::LuaApi::getOriginalFaction> },
	{ "isKilled", unitScriptIs<&BattleUnit::LuaApi::isKilled> },
	{ "isStunned", unitScriptIs<&BattleUnit::LuaApi::isStunned> },
	{ "isKneeled", unitIs<&BattleUnit::isKneeled> },
	{ "isFloating", unitIs<&BattleUnit::isFloating> },
	{ "getDirection", unitGet<&BattleUnit::getDirection> },
	{ "getPosition", unitGetPosition },
	{ "getTimeUnits", unitGet<&BattleUnit::getTimeUnits> },
	{ "getTimeUnitsMax", unitGetMax<&UnitStats::tu> },
	{ "setTimeUnits", unitSet<&BattleUnit::LuaApi::setTimeUnits> },
	{ "addTimeUnits", unitSet<&BattleUnit::LuaApi::addTimeUnits> },
	{ "getHealth", unitGet<&BattleUnit::getHealth> },
	{ "getHealthMax", unitGetMax<&UnitStats::health> },
	{ "setHealth", unitSet<&BattleUnit::LuaApi::setHealth> },
	{ "addHealth", unitSet<&BattleUnit::LuaApi::addHealth> },
	{ "setHealthWithOverkill", unitSet<&BattleUnit::LuaApi::setHealthWithOverkill> },
	{ "addHealthWithOverkill", unitSet<&BattleUnit::LuaApi::addHealthWithOverkill> },
	{ "getOverKillDamage", unitGet<&BattleUnit::getOverKillDamage> },
	{ "getMana", unitGet<&BattleUnit::getMana> },
	{ "getManaMax", unitGetMax<&UnitStats::mana> },
	{ "setMana", unitSet<&BattleUnit::LuaApi::setMana> },
	{ "addMana", unitSet<&BattleUnit::LuaApi::addMana> },
	{ "getEnergy", unitGet<&BattleUnit::getEnergy> },
	{ "getEnergyMax", unitGetMax<&UnitStats::stamina> },
	{ "setEnergy", unitSet<&BattleUnit::LuaApi::setEnergy> },
	{ "addEnergy", unitSet<&BattleUnit::LuaApi::addEnergy> },
	{ "getStun", unitGet<&BattleUnit::getStunlevel> },
	{ "getStunMax", unitScriptGet<&BattleUnit::LuaApi::getStunMax> },
	{ "setStun", unitSet<&BattleUnit::LuaApi::setStun> },
	{ "addStun", unitSet<&BattleUnit::LuaApi::addStun> },
	{ "getMorale", unitGet<&BattleUnit::getMorale> },
	{ "setMorale", unitSet<&BattleUnit::LuaApi::setMorale> },
	{ "addMorale", unitSet<&BattleUnit::LuaApi::addMorale> },
	{ "getFire", unitGet<&BattleUnit::getFire> },
	{ "setFire", unitSet<&BattleUnit::LuaApi::setFire> },
	{ "getArmor", unitScriptGet1<&BattleUnit::LuaApi::getArmor> },
	{ "getArmorMax", unitScriptGet1<&BattleUnit::LuaApi::getArmorMax> },
	{ "setArmor", unitSet2<&BattleUnit::LuaApi::setArmor> },
	{ "addArmor", unitSet2<&BattleUnit::LuaApi::addArmor> },
	{ "getFatalwoundsTotal", unitGet<&BattleUnit::getFatalWounds> },
	{ "getFatalwounds", unitScriptGet1<&BattleUnit::LuaApi::getFatalwounds> },
	{ "setFatalwounds", unitSet2<&BattleUnit::LuaApi::setFatalwounds> },
	{ "addFatalwounds", unitSet2<&BattleUnit::LuaApi::addFatalwounds> },
	{ "getRightHandWeapon", unitGetRightHandWeapon },
	{ "getLeftHandWeapon", unitGetLeftHandWeapon },
	{ "getRuleArmor", unitGetRuleArmor },
	{ "getTag", unitGetTag },
	{ "setTag", unitSetTag },
	{ "getRankUnified", getInt<&BattleUnit::getRankIntUnified> },
	{ "getGender", getInt<&BattleUnit::getGender> },
	{ "getLook", unitGetLook },
	{ "getLookVariant", unitGetLookVariant },
	{ "isStanding", unitStatusIs<STATUS_STANDING> },
	{ "isWalking", unitStatusIs<STATUS_WALKING> },
	{ "isFlying", unitStatusIs<STATUS_FLYING> },
	{ "isCollapsing", unitStatusIs<STATUS_COLLAPSING> },
	{ "isAiming", unitStatusIs<STATUS_AIMING> },
	{ "isFearable", getBool<&BattleUnit::isFearable> },
	{ "isWoundable", getBool<&BattleUnit::isWoundable> },
	{ "getReactionScore", getInt<&BattleUnit::getReactionScore> },
	{ "getIntelligence", getInt<&BattleUnit::getIntelligence> },
	{ "getAggression", getInt<&BattleUnit::getAggression> },
	{ "getTurretDirection", getInt<&BattleUnit::getTurretDirection> },
	{ "getWalkingPhase", getInt<&BattleUnit::getWalkingPhase> },
	{ "disableIndicators", unitDisableIndicators },
	{ "isVisible", getBool<&BattleUnit::getVisible> },
	{ "makeVisible", unitMakeVisible },
	{ "getMaxViewDistanceAtDark", unitGetMaxViewDistanceAtDark },
	{ "getMaxViewDistanceAtDay", unitGetMaxViewDistanceAtDay },
	{ "getMaxViewDistance", unitGetMaxViewDistance },
	{ "getPsiVision", getInt<&BattleUnit::getPsiVision> },
	{ "getHeatVision", getInt<&BattleUnit::getVisibilityThroughSmoke> },
	{ "getVisibilityThroughFire", getInt<&BattleUnit::getVisibilityThroughFire> },
	{ "setSpawnUnit", unitSetSpawnUnit },
	{ "getSpawnUnit", getObject<&BattleUnit::getSpawnUnit> },
	{ "setSpawnUnitInstantRespawn", unitSet<&BattleUnit::LuaApi::setSpawnUnitInstantRespawn> },
	{ "getSpawnUnitInstantRespawn", getBool<&BattleUnit::getRespawn> },
	{ "setSpawnUnitFaction", unitSet<&BattleUnit::LuaApi::setSpawnUnitFaction> },
	{ "getSpawnUnitFaction", getInt<&BattleUnit::getSpawnUnitFaction> },
	{ "getPreviousOwner", unitGetPreviousOwner },
	{ "getMoraleMax", unitGetMoraleMax },
	{ "setArmorMax", unitSet2<&BattleUnit::LuaApi::setArmorMax> },
	{ "getFatalwoundsMax", unitScriptGet1<&BattleUnit::LuaApi::getFatalwoundsMax> },
	{ "getMovementType", getInt<&BattleUnit::getMovementType> },
	{ "getOriginalMovementType", getInt<&BattleUnit::getOriginalMovementType> },
	{ "setMovementType", unitSet<&BattleUnit::LuaApi::setMovementType> },
	{ "getVisibleUnitsCount", unitGetVisibleUnitsCount },
	{ "getRuleUnit", getObject<&BattleUnit::getUnitRules> },
	{ "getRuleSoldier", unitGetRuleSoldier },
	{ "getGeoscapeSoldier", unitGetGeoscapeSoldier },
	{ "reduceByBravery", unitReduceByBravery },
	{ "reduceByResistance", unitReduceByResistance },
	{ "getTurnsSinceSpotted", getInt<&BattleUnit::getTurnsSinceSpotted> },
	{ "setTurnsSinceSpotted", unitSet<&BattleUnit::LuaApi::setTurnsSinceSpotted> },
	{ "getTurnsSinceSpottedByFaction", unitGetTurnsSinceSpottedByFaction },
	{ "setTurnsSinceSpottedByFaction", unitSetTurnsSinceSpottedByFaction },
	{ "getTurnsLeftSpottedForSnipers", getInt<&BattleUnit::getTurnsLeftSpottedForSnipers> },
	{ "setTurnsLeftSpottedForSnipers", unitSet<&BattleUnit::LuaApi::setTurnsLeftSpottedForSnipers> },
	{ "getTurnsLeftSpottedForSnipersByFaction", unitGetTurnsLeftSpottedForSnipersByFaction },
	{ "setTurnsLeftSpottedForSnipersByFaction", unitSetTurnsLeftSpottedForSnipersByFaction },
	{ "getDisplayShieldHp", getInt<&BattleUnit::getDisplayShieldHp> },
	{ "setDisplayShieldHp", setInt<&BattleUnit::setDisplayShieldHp> },
	{ "getDisplayShieldCapacity", getInt<&BattleUnit::getDisplayShieldCapacity> },
	{ "setDisplayShieldCapacity", setInt<&BattleUnit::setDisplayShieldCapacity> },
	{ "getTurnsSinceStunned", getInt<&BattleUnit::getTurnsSinceStunned> },
	{ "setTurnsSinceStunned", unitSet<&BattleUnit::LuaApi::setTurnsSinceStunned> },
	{ "getTileShade", unitGetTileShade },
	{ "getStat", unitGetStat },
	{ "setStat", unitSetStat },
	{ "addStat", unitAddStat },
	{ "getExp", unitGetExp },
	{ "getMoveCost", unitGetMoveCost },
	{ "setMoveCost", unitSetMoveCost },
	{ "getInventoryItems", unitGetInventoryItems },
	{ "getInventoryItem", unitGetInventoryItem },
	{ "getSpecialItems", unitGetSpecialItems },
	{ nullptr, nullptr }
};

template<auto Getter>
int itemGet(lua_State *L)
{
	lua_pushinteger(L, (int)(checkItem(L)->*Getter)());
	return 1;
}

template<auto Getter>
int itemIs(lua_State *L)
{
	lua_pushboolean(L, (checkItem(L)->*Getter)());
	return 1;
}

template<auto Field>
int itemSet(lua_State *L)
{
	checkWritable(L);
	auto *item = checkItem(L);
	(BattleItem::luaApi().*Field)(item, checkInt(L, 2));
	return 0;
}

int itemGetAmmoQuantityMax(lua_State *L)
{
	lua_pushinteger(L, checkItem(L)->getRules()->getClipSize());
	return 1;
}

int itemGetRuleItem(lua_State *L)
{
	pushOrNil(L, TYPE_RULE_ITEM, checkItem(L)->getRules());
	return 1;
}

int itemGetOwner(lua_State *L)
{
	pushOrNil(L, TYPE_UNIT, checkItem(L)->getOwner());
	return 1;
}

int itemGetTag(lua_State *L)
{
	auto *item = checkItem(L);
	lua_pushinteger(L, item->getScriptValuesRaw().get(checkTag<ScriptTag<BattleItem>>(L)));
	return 1;
}

int itemSetTag(lua_State *L)
{
	checkWritable(L);
	auto *item = checkItem(L);
	const auto tag = checkTag<ScriptTag<BattleItem>>(L);
	item->luaSetTag(tag, checkInt(L, 3));
	return 0;
}

int itemGetUnit(lua_State *L)
{
	pushOrNil(L, TYPE_UNIT, checkItem(L)->getUnit());
	return 1;
}

int itemGetPreviousOwner(lua_State *L)
{
	pushOrNil(L, TYPE_UNIT, checkItem(L)->getPreviousOwner());
	return 1;
}

int itemGetAmmoItem(lua_State *L)
{
	pushOrNil(L, TYPE_ITEM, checkItem(L)->getAmmoForSlot(0));
	return 1;
}

int itemGetAmmoForSlot(lua_State *L)
{
	auto *item = checkItem(L);
	const int slot = checkInt(L, 2);
	luaL_argcheck(L, slot >= 0 && slot < RuleItem::AmmoSlotMax, 2, "no such ammo slot");
	pushOrNil(L, TYPE_ITEM, item->getAmmoForSlot(slot));
	return 1;
}

int itemGetAmmoForAction(lua_State *L)
{
	const BattleItem *item = checkItem(L);
	pushOrNil(L, TYPE_ITEM, item->getAmmoForAction((BattleActionType)checkAction(L, 2)));
	return 1;
}

int itemGetSlot(lua_State *L)
{
	const auto *slot = checkItem(L)->getSlot();
	if (slot)
	{
		lua_pushstring(L, slot->getId().c_str());
	}
	else
	{
		lua_pushnil(L);
	}
	return 1;
}

int itemGetMoveToCost(lua_State *L)
{
	auto *item = checkItem(L);
	const auto *slot = checkSlot(L, 2);
	lua_pushinteger(L, item->getSlot() ? item->getMoveToCost(slot) : 0);
	return 1;
}

int itemGetFuseTimerDefault(lua_State *L)
{
	lua_pushinteger(L, checkItem(L)->getRules()->getFuseTimerDefault());
	return 1;
}

int itemSetFuseEnabled(lua_State *L)
{
	checkWritable(L);
	auto *item = checkItem(L);
	luaL_checktype(L, 2, LUA_TBOOLEAN);
	item->setFuseEnabled(lua_toboolean(L, 2));
	return 0;
}

int itemGetActionCost(lua_State *L)
{
	const BattleItem *item = checkItem(L);
	const auto *unit = checkOtherUnit(L);
	lua_pushinteger(L, unit->getActionTUs((BattleActionType)checkAction(L, 3), item).Time);
	return 1;
}

int itemGetInventoryMoveCost(lua_State *L)
{
	lua_pushinteger(L, checkItem(L)->luaInventoryMoveCost());
	return 1;
}

int itemSetInventoryMoveCost(lua_State *L)
{
	checkWritable(L);
	auto *item = checkItem(L);
	item->luaInventoryMoveCost() = checkInt(L, 2);
	return 0;
}

const luaL_Reg ITEM_METHODS[] = {
	{ "getId", itemGet<&BattleItem::getId> },
	{ "getRuleItem", itemGetRuleItem },
	{ "getOwner", itemGetOwner },
	{ "isAmmo", itemIs<&BattleItem::isAmmo> },
	{ "getAmmoQuantity", itemGet<&BattleItem::getAmmoQuantity> },
	{ "getAmmoQuantityMax", itemGetAmmoQuantityMax },
	{ "setAmmoQuantity", itemSet<&BattleItem::LuaApi::setAmmoQuantity> },
	{ "getFuseTimer", itemGet<&BattleItem::getFuseTimer> },
	{ "setFuseTimer", itemSet<&BattleItem::LuaApi::setFuseTimer> },
	{ "isFuseEnabled", itemIs<&BattleItem::isFuseEnabled> },
	{ "getHealQuantity", itemGet<&BattleItem::getHealQuantity> },
	{ "setHealQuantity", itemSet<&BattleItem::LuaApi::setHealQuantity> },
	{ "getPainKillerQuantity", itemGet<&BattleItem::getPainKillerQuantity> },
	{ "setPainKillerQuantity", itemSet<&BattleItem::LuaApi::setPainKillerQuantity> },
	{ "getStimulantQuantity", itemGet<&BattleItem::getStimulantQuantity> },
	{ "setStimulantQuantity", itemSet<&BattleItem::LuaApi::setStimulantQuantity> },
	{ "getTag", itemGetTag },
	{ "setTag", itemSetTag },
	{ "getBattleUnit", itemGetUnit },
	{ "getAmmoItem", itemGetAmmoItem },
	{ "getAmmoForSlot", itemGetAmmoForSlot },
	{ "getAmmoForAction", itemGetAmmoForAction },
	{ "getSlot", itemGetSlot },
	{ "getPreviousOwner", itemGetPreviousOwner },
	{ "getGlow", getBool<&BattleItem::getGlow> },
	{ "getTotalWeight", getInt<&BattleItem::getTotalWeight> },
	{ "isSpecialWeapon", getBool<&BattleItem::isSpecialWeapon> },
	{ "getFuseTimerDefault", itemGetFuseTimerDefault },
	{ "setFuseEnabled", itemSetFuseEnabled },
	{ "getActionCost", itemGetActionCost },
	{ "getMoveToCost", itemGetMoveToCost },
	{ "getInventoryMoveCost", itemGetInventoryMoveCost },
	{ "setInventoryMoveCost", itemSetInventoryMoveCost },
	{ nullptr, nullptr }
};

SavedBattleGame *checkBattle(lua_State *L)
{
	return static_cast<SavedBattleGame*>(LuaSandbox::checkObject(L, 1, TYPE_BATTLE));
}

int battleGetTurn(lua_State *L)
{
	lua_pushinteger(L, checkBattle(L)->getTurn());
	return 1;
}

int battleGetSize(lua_State *L)
{
	auto *battle = checkBattle(L);
	lua_pushinteger(L, battle->getMapSizeX());
	lua_pushinteger(L, battle->getMapSizeY());
	lua_pushinteger(L, battle->getMapSizeZ());
	return 3;
}

/// As the Y-script's flashMessage: a string id or plain text, then up to three numbers for {0}, {1}, {2}.
template<void (BattlescapeState::*Show)(const std::string&)>
int battleFlashMessage(lua_State *L)
{
	checkWritable(L);
	auto *battle = checkBattle(L);
	LuaSandbox::from(L)->charge(L, MESSAGE_TICKS);
	size_t len = 0;
	const char *text = luaL_checklstring(L, 2, &len);
	luaL_argcheck(L, len <= MESSAGE_MAX, 2, "too long");
	const std::string message(text, len);
	luaL_argcheck(L, Unicode::isValidUTF8(message), 2, "not UTF-8");
	luaL_argcheck(L, lua_gettop(L) <= 5, 6, "at most three numbers");
	int numbers[3] = { };
	const int count = lua_gettop(L) - 2;
	for (int i = 0; i < count; ++i)
	{
		numbers[i] = checkInt(L, 3 + i);
	}
	if (!battle->getBattleState() || g_noScreen)
	{
		return 0;
	}
	LocalizedText translated = battle->getBattleState()->getGame()->getLanguage()->getString(message);
	for (int i = 0; i < count; ++i)
	{
		translated.arg(numbers[i]);
	}
	(battle->getBattleState()->*Show)(translated);
	return 0;
}

int battleGetTile(lua_State *L)
{
	auto *battle = checkBattle(L);
	const int x = checkInt(L, 2), y = checkInt(L, 3), z = checkInt(L, 4);
	// Position keeps short numbers: one past them would wrap into the map
	const bool inMap = x >= 0 && y >= 0 && z >= 0 && x < battle->getMapSizeX() && y < battle->getMapSizeY() && z < battle->getMapSizeZ();
	pushOrNil(L, TYPE_TILE, inMap ? battle->getTile(Position(x, y, z)) : nullptr);
	return 1;
}

int battleGetUnits(lua_State *L)
{
	auto *battle = checkBattle(L);
	const bool all = lua_isnoneornil(L, 2);
	const int faction = all ? 0 : checkFaction(L, 2);
	return pushList(L, TYPE_UNIT, *battle->getUnits(), [&](BattleUnit *unit)
	{
		return !unit->isIgnored() && unit->getStatus() != STATUS_DEAD && (all || unit->getFaction() == faction);
	});
}

int battleGetItems(lua_State *L)
{
	return pushList(L, TYPE_ITEM, *checkBattle(L)->getItems(), [](BattleItem *item) { return !item->isOwnerIgnored(); });
}

int battleGetSelectedUnit(lua_State *L)
{
	pushOrNil(L, TYPE_UNIT, checkBattle(L)->getSelectedUnit());
	return 1;
}

int battleRandomRange(lua_State *L)
{
	checkBattle(L);
	const int low = checkInt(L, 2), high = checkInt(L, 3);
	luaL_argcheck(L, high >= low, 3, "the upper bound is below the lower one");
	lua_pushinteger(L, RNG::generate(low, high));
	return 1;
}

int battleRandomChance(lua_State *L)
{
	checkBattle(L);
	lua_pushboolean(L, RNG::percent(checkInt(L, 2)));
	return 1;
}

int battleDifficultyLevel(lua_State *L)
{
	lua_pushinteger(L, checkBattle(L)->getGeoscapeSave()->getDifficulty());
	return 1;
}

template<void (SavedBattleGame::*Set)(int)>
int battleSetItemLevel(lua_State *L)
{
	checkWritable(L);
	auto *battle = checkBattle(L);
	(battle->*Set)(Clamp(checkInt(L, 2), 0, (int)battle->getMod()->getAlienItemLevels().size()));
	return 0;
}

int battleGetGeoscapeGame(lua_State *L)
{
	pushOrNil(L, TYPE_GEOSCAPE, checkBattle(L)->getGeoscapeSave());
	return 1;
}

int battleTryConcealUnit(lua_State *L)
{
	checkWritable(L);
	auto *battle = checkBattle(L);
	lua_pushboolean(L, battle->getTileEngine()->tryConcealUnit(checkOtherUnit(L)));
	return 1;
}

const luaL_Reg BATTLE_METHODS[] = {
	{ "getTurn", battleGetTurn },
	{ "getSize", battleGetSize },
	{ "flashMessage", battleFlashMessage<&BattlescapeState::warningRaw> },
	{ "flashLongMessage", battleFlashMessage<&BattlescapeState::warningLongRaw> },
	{ "getTile", battleGetTile },
	{ "getUnits", battleGetUnits },
	{ "getItems", battleGetItems },
	{ "getSelectedUnit", battleGetSelectedUnit },
	{ "getTurnSide", getInt<&SavedBattleGame::getSide> },
	{ "randomRange", battleRandomRange },
	{ "randomChance", battleRandomChance },
	{ "difficultyLevel", battleDifficultyLevel },
	{ "getAlienItemLevel", getInt<&SavedBattleGame::getAlienItemLevel> },
	{ "setAlienItemLevel", battleSetItemLevel<&SavedBattleGame::setAlienItemLevel> },
	{ "getReinforcementsItemLevel", getInt<&SavedBattleGame::getReinforcementsItemLevel> },
	{ "setReinforcementsItemLevel", battleSetItemLevel<&SavedBattleGame::setReinforcementsItemLevel> },
	{ "getDepth", getInt<&SavedBattleGame::getDepth> },
	{ "getGlobalShade", getInt<&SavedBattleGame::getGlobalShade> },
	{ "getGeoscapeGame", battleGetGeoscapeGame },
	{ "tryConcealUnit", battleTryConcealUnit },
	{ "getTag", getTagOf<SavedBattleGame> },
	{ "setTag", setTagOf<SavedBattleGame> },
	{ nullptr, nullptr }
};

int tileGetPosition(lua_State *L)
{
	const Position pos = self<Tile>(L)->getPosition();
	lua_pushinteger(L, pos.x);
	lua_pushinteger(L, pos.y);
	lua_pushinteger(L, pos.z);
	return 3;
}

/// Bits: 1 floor, 2 west wall, 4 north wall.
int tileIsDiscovered(lua_State *L)
{
	const auto *tile = self<Tile>(L);
	lua_pushinteger(L, (tile->isDiscovered(O_FLOOR) << 0) | (tile->isDiscovered(O_WESTWALL) << 1) | (tile->isDiscovered(O_NORTHWALL) << 2));
	return 1;
}

int tileMakeDiscovered(lua_State *L)
{
	checkWritable(L);
	auto *tile = self<Tile>(L);
	const int parts = checkInt(L, 2);
	if (parts & 1) tile->setDiscovered(true, O_FLOOR);
	if (parts & 2) tile->setDiscovered(true, O_WESTWALL);
	if (parts & 4) tile->setDiscovered(true, O_NORTHWALL);
	return 0;
}

int tileGetUnit(lua_State *L)
{
	pushOrNil(L, TYPE_UNIT, self<Tile>(L)->getUnit());
	return 1;
}

int tileGetDistanceTile(lua_State *L)
{
	const auto *tile = self<Tile>(L);
	const auto *other = static_cast<Tile*>(LuaSandbox::checkObject(L, 2, TYPE_TILE));
	lua_pushinteger(L, (int)Position::distance(tile->getPosition(), other->getPosition()));
	return 1;
}

int tileGetDistanceVoxel(lua_State *L)
{
	const auto *tile = self<Tile>(L);
	const auto *other = static_cast<Tile*>(LuaSandbox::checkObject(L, 2, TYPE_TILE));
	lua_pushinteger(L, (int)Position::distance(tile->getPosition().toVoxel(), other->getPosition().toVoxel()));
	return 1;
}

const luaL_Reg TILE_METHODS[] = {
	{ "getPosition", tileGetPosition },
	{ "getFire", getInt<&Tile::getFire> },
	{ "getSmoke", getInt<&Tile::getSmoke> },
	{ "getShade", getInt<&Tile::getShade> },
	{ "isDiscovered", tileIsDiscovered },
	{ "makeDiscovered", tileMakeDiscovered },
	{ "getUnit", tileGetUnit },
	{ "getDistanceTile", tileGetDistanceTile },
	{ "getDistanceVoxel", tileGetDistanceVoxel },
	{ "getFloorSpecialTileType", getInt<&Tile::getFloorSpecialTileType> },
	{ "getObjectSpecialTileType", getInt<&Tile::getObjectSpecialTileType> },
	{ nullptr, nullptr }
};

int geoscapeGetTime(lua_State *L)
{
	const auto *time = self<SavedGame>(L)->getTime();
	// the same formula as the script's daysPastEpoch
	std::tm tm = { };
	tm.tm_year = time->getYear() - 1900;
	tm.tm_mon = time->getMonth() - 1;
	tm.tm_mday = time->getDay();
	tm.tm_hour = time->getHour();
	tm.tm_min = time->getMinute();
	tm.tm_sec = time->getSecond();
	const struct { const char *name; int value; } fields[] = {
		{ "second", time->getSecond() }, { "minute", time->getMinute() }, { "hour", time->getHour() }, { "day", time->getDay() },
		{ "month", time->getMonth() }, { "year", time->getYear() }, { "secondsPastMidnight", time->getSecond() + 60 * time->getMinute() + 3600 * time->getHour() },
		{ "daysPastEpoch", (int)(std::mktime(&tm) / (60 * 60 * 24)) },
	};
	lua_createtable(L, 0, (int)std::size(fields));
	for (const auto &field : fields)
	{
		lua_pushinteger(L, field.value);
		lua_setfield(L, -2, field.name);
	}
	return 1;
}

int geoscapeDifficultyLevel(lua_State *L)
{
	lua_pushinteger(L, self<SavedGame>(L)->getDifficulty());
	return 1;
}

int geoscapeGetCountries(lua_State *L)
{
	return pushList(L, TYPE_COUNTRY, *self<SavedGame>(L)->getCountries(), [](Country*) { return true; });
}

int geoscapeIsResearched(lua_State *L)
{
	auto *game = self<SavedGame>(L);
	LuaSandbox::from(L)->charge(L, TAG_TICKS);
	const char *name = luaL_checkstring(L, 2);
	const auto *rule = gameMod(L)->getResearch(name);
	if (!rule)
	{
		luaL_error(L, "no such research '%s'", name);
	}
	lua_pushboolean(L, game->isResearched(rule, false));
	return 1;
}

const luaL_Reg GEOSCAPE_METHODS[] = {
	{ "getTime", geoscapeGetTime },
	{ "difficultyLevel", geoscapeDifficultyLevel },
	{ "getMonthsPassed", getInt<&SavedGame::getMonthsPassed> },
	{ "getDaysPassed", getInt<&SavedGame::getDaysPassed> },
	{ "getCountries", geoscapeGetCountries },
	{ "isResearched", geoscapeIsResearched },
	{ "getTag", getTagOf<SavedGame> },
	{ "setTag", setTagOf<SavedGame> },
	{ nullptr, nullptr }
};

const luaL_Reg COUNTRY_METHODS[] = {
	{ "getRuleCountry", getObject<&Country::getRules> },
	{ "getPact", getBool<&Country::getPact> },
	{ "getCurrentFunding", getInt<&Country::getCurrentFunding> },
	{ "getCurrentActivityAlien", getInt<&Country::getCurrentActivityAlien> },
	{ "getCurrentActivityXcom", getInt<&Country::getCurrentActivityXcom> },
	{ "getTag", getTagOf<Country> },
	{ nullptr, nullptr }
};

/// getId is a member of Target, the base class: the Lua type comes from here.
template<typename T>
int targetGetId(lua_State *L)
{
	lua_pushinteger(L, self<T>(L)->getId());
	return 1;
}

int ufoGetStatus(lua_State *L)
{
	lua_pushinteger(L, (int)self<Ufo>(L)->getStatus());
	return 1;
}

int ufoGetDamageMax(lua_State *L)
{
	lua_pushinteger(L, self<Ufo>(L)->getCraftStats().damageMax);
	return 1;
}

int ufoGetShieldMax(lua_State *L)
{
	lua_pushinteger(L, self<Ufo>(L)->getCraftStats().shieldCapacity);
	return 1;
}

int ufoGetStat(lua_State *L)
{
	return pushCraftStat(L, self<Ufo>(L)->getCraftStats());
}

const luaL_Reg UFO_METHODS[] = {
	{ "getId", targetGetId<Ufo> },
	{ "getAltitude", getInt<&Ufo::getAltitudeInt> },
	{ "getStatus", ufoGetStatus },
	{ "getVisibility", getInt<&Ufo::getVisibility> },
	{ "getDamage", getInt<&Ufo::getDamage> },
	{ "getDamageMax", ufoGetDamageMax },
	{ "getDamagePercentage", getInt<&Ufo::getDamagePercentage> },
	{ "getShield", getInt<&Ufo::getShield> },
	{ "getShieldMax", ufoGetShieldMax },
	{ "getShieldPercentage", getInt<&Ufo::getShieldPercentage> },
	{ "isHunterKiller", getBool<&Ufo::isHunterKiller> },
	{ "isHunting", getBool<&Ufo::isHunting> },
	{ "isEscorting", getBool<&Ufo::isEscorting> },
	{ "getHuntBehavior", getInt<&Ufo::getHuntBehavior> },
	{ "getHuntMode", getInt<&Ufo::getHuntMode> },
	{ "getDetected", getBool<&Ufo::getDetected> },
	{ "getHyperDetected", getBool<&Ufo::getHyperDetected> },
	{ "getRuleUfo", getObject<&Ufo::getRules> },
	{ "getStat", ufoGetStat },
	{ "getTag", getTagOf<Ufo> },
	{ nullptr, nullptr }
};

int craftGetStat(lua_State *L)
{
	return pushCraftStat(L, self<Craft>(L)->getCraftStats());
}

int craftGetShieldMax(lua_State *L)
{
	lua_pushinteger(L, self<Craft>(L)->getCraftStats().shieldCapacity);
	return 1;
}

const luaL_Reg CRAFT_METHODS[] = {
	{ "getId", targetGetId<Craft> },
	{ "getDamage", getInt<&Craft::getDamage> },
	{ "getDamageMax", getInt<&Craft::getDamageMax> },
	{ "getDamagePercentage", getInt<&Craft::getDamagePercentage> },
	{ "getShield", getInt<&Craft::getShield> },
	{ "getShieldMax", craftGetShieldMax },
	{ "getShieldPercentage", getInt<&Craft::getShieldPercentage> },
	{ "getRuleCraft", getObject<&Craft::getRules> },
	{ "getStat", craftGetStat },
	{ "getTag", getTagOf<Craft> },
	{ nullptr, nullptr }
};

template<typename Rule>
int ruleGetType(lua_State *L, const char *type)
{
	lua_pushstring(L, static_cast<Rule*>(LuaSandbox::checkObject(L, 1, type))->getType().c_str());
	return 1;
}

int ruleArmorGetType(lua_State *L) { return ruleGetType<Armor>(L, TYPE_RULE_ARMOR); }
int ruleItemGetType(lua_State *L) { return ruleGetType<RuleItem>(L, TYPE_RULE_ITEM); }
int skillGetType(lua_State *L) { return ruleGetType<RuleSkill>(L, TYPE_SKILL); }

const luaL_Reg SKILL_METHODS[] = { { "getType", skillGetType }, { nullptr, nullptr } };

int ruleArmorGetStat(lua_State *L)
{
	const auto *armor = self<Armor>(L);
	lua_pushinteger(L, armor->getStats()->*checkStat(L, 2));
	return 1;
}

int ruleArmorGetCorpseBattlescape(lua_State *L)
{
	return pushList(L, TYPE_RULE_ITEM, self<Armor>(L)->getCorpseBattlescape(), [](const RuleItem*) { return true; });
}

int ruleArmorGetRequiredResearch(lua_State *L)
{
	const auto *research = self<Armor>(L)->getRequiredResearch();
	if (research)
	{
		lua_pushstring(L, research->getName().c_str());
	}
	else
	{
		lua_pushnil(L);
	}
	return 1;
}

int ruleArmorGetArmor(lua_State *L)
{
	const auto *armor = self<Armor>(L);
	const int side = checkInt(L, 2);
	luaL_argcheck(L, side >= 0 && side < SIDE_MAX, 2, "no such side");
	lua_pushinteger(L, armor->getArmor((UnitSide)side));
	return 1;
}

int ruleArmorGetMoveCost(lua_State *L)
{
	const auto *armor = self<Armor>(L);
	ArmorMoveCost cost = { };
	switch (checkMoveKind(L, 2))
	{
	case 0: cost = armor->getMoveCostBase(); break;
	case 1: cost = armor->getMoveCostBaseFly(); break;
	case 2: cost = armor->getMoveCostBaseNormal(); break;
	default: cost = armor->getMoveCostBaseClimb(); break;
	}
	lua_pushinteger(L, cost.TimePercent);
	lua_pushinteger(L, cost.EnergyPercent);
	return 2;
}

const luaL_Reg RULE_ARMOR_METHODS[] = {
	{ "getType", ruleArmorGetType },
	{ "getStat", ruleArmorGetStat },
	{ "getCorpseGeoscape", getObject<&Armor::getCorpseGeoscape> },
	{ "getCorpseBattlescape", ruleArmorGetCorpseBattlescape },
	{ "getRequiredResearch", ruleArmorGetRequiredResearch },
	{ "getDrawingRoutine", getInt<&Armor::getDrawingRoutine> },
	{ "getDrawBubbles", getBool<&Armor::drawBubbles> },
	{ "getDeathFrames", getInt<&Armor::getDeathFrames> },
	{ "getConstantAnimation", getBool<&Armor::getConstantAnimation> },
	{ "getVisibilityAtDark", getInt<&Armor::getVisibilityAtDark> },
	{ "getVisibilityAtDay", getInt<&Armor::getVisibilityAtDay> },
	{ "getCamouflageAtDark", getInt<&Armor::getCamouflageAtDark> },
	{ "getCamouflageAtDay", getInt<&Armor::getCamouflageAtDay> },
	{ "getAntiCamouflageAtDark", getInt<&Armor::getAntiCamouflageAtDark> },
	{ "getAntiCamouflageAtDay", getInt<&Armor::getAntiCamouflageAtDay> },
	{ "getHeatVision", getInt<&Armor::getVisibilityThroughSmoke> },
	{ "getVisibilityThroughFire", getInt<&Armor::getVisibilityThroughFire> },
	{ "getPersonalLight", getInt<&Armor::getPersonalLightFriend> },
	{ "getPersonalLightHostile", getInt<&Armor::getPersonalLightHostile> },
	{ "getPersonalLightNeutral", getInt<&Armor::getPersonalLightNeutral> },
	{ "getSize", getInt<&Armor::getSize> },
	{ "getArmor", ruleArmorGetArmor },
	{ "getMoveCost", ruleArmorGetMoveCost },
	{ "getTag", getTagOf<Armor> },
	{ nullptr, nullptr }
};

int ruleItemIsSingleTarget(lua_State *L)
{
	const auto *damage = self<RuleItem>(L)->getDamageType();
	lua_pushboolean(L, damage && damage->FixRadius == 0);
	return 1;
}

int ruleItemHasCategory(lua_State *L)
{
	const auto *rule = self<RuleItem>(L);
	LuaSandbox::from(L)->charge(L, TAG_TICKS);
	const std::string name = luaL_checkstring(L, 2);
	const auto &categories = rule->getCategories();
	lua_pushboolean(L, std::find(categories.begin(), categories.end(), name) != categories.end());
	return 1;
}

const luaL_Reg RULE_ITEM_METHODS[] = {
	{ "getType", ruleItemGetType },
	{ "getAccuracyAimed", getInt<&RuleItem::getAccuracyAimed> },
	{ "getAccuracyAuto", getInt<&RuleItem::getAccuracyAuto> },
	{ "getAccuracyMelee", getInt<&RuleItem::getAccuracyMelee> },
	{ "getAccuracyMind", getInt<&RuleItem::getAccuracyMind> },
	{ "getAccuracyPanic", getInt<&RuleItem::getAccuracyPanic> },
	{ "getAccuracySnap", getInt<&RuleItem::getAccuracySnap> },
	{ "getAccuracyThrow", getInt<&RuleItem::getAccuracyThrow> },
	{ "getAccuracyUse", getInt<&RuleItem::getAccuracyUse> },
	{ "getPower", getInt<&RuleItem::getPower> },
	{ "getDamageType", getObject<&RuleItem::getDamageType> },
	{ "getMeleePower", getInt<&RuleItem::getMeleePower> },
	{ "getMeleeDamageType", getObject<&RuleItem::getMeleeType> },
	{ "getArmorValue", getInt<&RuleItem::getArmor> },
	{ "getWeight", getInt<&RuleItem::getWeight> },
	{ "getBattleType", getInt<&RuleItem::getBattleType> },
	{ "getWaypoints", getInt<&RuleItem::getWaypoints> },
	{ "isWaterOnly", getBool<&RuleItem::isWaterOnly> },
	{ "isTwoHanded", getBool<&RuleItem::isTwoHanded> },
	{ "isBlockingBothHands", getBool<&RuleItem::isBlockingBothHands> },
	{ "isSingleTarget", ruleItemIsSingleTarget },
	{ "hasCategory", ruleItemHasCategory },
	{ "getTag", getTagOf<RuleItem> },
	{ nullptr, nullptr }
};

struct DamageField
{
	const char *name;
	float RuleDamageType::*field;
};

const DamageField DAMAGE_FIELDS[] = {
	{ "armorPre", &RuleDamageType::ToArmorPre }, { "armor", &RuleDamageType::ToArmor }, { "energy", &RuleDamageType::ToEnergy },
	{ "health", &RuleDamageType::ToHealth }, { "item", &RuleDamageType::ToItem }, { "mana", &RuleDamageType::ToMana },
	{ "morale", &RuleDamageType::ToMorale }, { "stun", &RuleDamageType::ToStun }, { "tile", &RuleDamageType::ToTile },
	{ "time", &RuleDamageType::ToTime }, { "wound", &RuleDamageType::ToWound },
};

int ruleDamageIsAreaOfEffect(lua_State *L)
{
	lua_pushboolean(L, !self<RuleDamageType>(L)->isDirect());
	return 1;
}

int ruleDamageGetResistType(lua_State *L)
{
	lua_pushinteger(L, (int)self<RuleDamageType>(L)->ResistType);
	return 1;
}

int ruleDamageGetRandomType(lua_State *L)
{
	lua_pushinteger(L, (int)self<RuleDamageType>(L)->RandomType);
	return 1;
}

int ruleDamageGetArmorEffectiveness(lua_State *L)
{
	lua_pushinteger(L, (int)round(self<RuleDamageType>(L)->ArmorEffectiveness * 100));
	return 1;
}

int ruleDamageGetDamageTo(lua_State *L)
{
	const auto *rule = self<RuleDamageType>(L);
	const char *name = luaL_checkstring(L, 2);
	const int value = checkInt(L, 3);
	for (const auto &field : DAMAGE_FIELDS)
	{
		if (!strcmp(name, field.name))
		{
			lua_pushinteger(L, (int)(rule->*field.field * value));
			return 1;
		}
	}
	return luaL_argerror(L, 2, "no such damage kind");
}

int ruleDamageGetRandomDamage(lua_State *L)
{
	const auto *rule = self<RuleDamageType>(L);
	lua_pushinteger(L, rule->getRandomDamage(checkInt(L, 2)));
	return 1;
}

const luaL_Reg RULE_DAMAGE_METHODS[] = {
	{ "isDirect", getBool<&RuleDamageType::isDirect> },
	{ "isAreaOfEffect", ruleDamageIsAreaOfEffect },
	{ "getResistType", ruleDamageGetResistType },
	{ "getRandomType", ruleDamageGetRandomType },
	{ "getArmorEffectiveness", ruleDamageGetArmorEffectiveness },
	{ "getDamageTo", ruleDamageGetDamageTo },
	{ "getRandomDamage", ruleDamageGetRandomDamage },
	{ nullptr, nullptr }
};

const luaL_Reg RULE_UNIT_METHODS[] = {
	{ "getType", getString<&Unit::getType> },
	{ "getSpawnUnit", getObject<&Unit::getSpawnUnit> },
	{ "getCivilianRecoveryItemType", getObject<&Unit::getCivilianRecoveryItemType> },
	{ "getLiveAlienGeoscape", getObject<&Unit::getLiveAlienGeoscape> },
	{ nullptr, nullptr }
};

const luaL_Reg RULE_SOLDIER_METHODS[] = { { "getType", getString<&RuleSoldier::getType> }, { "getTag", getTagOf<RuleSoldier> }, { nullptr, nullptr } };
const luaL_Reg RULE_BONUS_METHODS[] = { { "getType", getString<&RuleSoldierBonus::getName> }, { "getTag", getTagOf<RuleSoldierBonus> }, { nullptr, nullptr } };
const luaL_Reg RULE_COUNTRY_METHODS[] = { { "getType", getString<&RuleCountry::getType> }, { nullptr, nullptr } };
const luaL_Reg RULE_UFO_METHODS[] = { { "getType", getString<&RuleUfo::getType> }, { "getTag", getTagOf<RuleUfo> }, { nullptr, nullptr } };
const luaL_Reg RULE_CRAFT_METHODS[] = { { "getType", getString<&RuleCraft::getType> }, { "getTag", getTagOf<RuleCraft> }, { nullptr, nullptr } };

int soldierGetId(lua_State *L)
{
	lua_pushinteger(L, static_cast<Soldier*>(LuaSandbox::checkObject(L, 1, TYPE_SOLDIER))->getId());
	return 1;
}

int soldierGetRank(lua_State *L)
{
	lua_pushinteger(L, (int)static_cast<Soldier*>(LuaSandbox::checkObject(L, 1, TYPE_SOLDIER))->getRank());
	return 1;
}

int soldierGetStat(lua_State *L)
{
	const auto *soldier = self<Soldier>(L);
	lua_pushinteger(L, soldier->getCurrentStats()->*checkStat(L, 2));
	return 1;
}

int soldierSetStat(lua_State *L)
{
	checkWritable(L);
	auto *soldier = self<Soldier>(L);
	const StatPtr stat = checkStat(L, 2);
	soldier->getCurrentStatsEditable()->*stat = statValue(checkInt(L, 3));
	return 0;
}

int soldierAddStat(lua_State *L)
{
	checkWritable(L);
	auto *soldier = self<Soldier>(L);
	const StatPtr stat = checkStat(L, 2);
	UnitStats::Type &value = soldier->getCurrentStatsEditable()->*stat;
	value = statValue(statAddend(checkInt(L, 3)) + value);
	return 0;
}

const luaL_Reg SOLDIER_METHODS[] = {
	{ "getId", soldierGetId },
	{ "getRank", soldierGetRank },
	{ "getGender", getInt<&Soldier::getGender> },
	{ "getLook", getInt<&Soldier::getLook> },
	{ "getLookVariant", getInt<&Soldier::getLookVariant> },
	{ "getRuleSoldier", getObject<&Soldier::getRules> },
	{ "getWoundRecovery", getInt<&Soldier::getWoundRecoveryInt> },
	{ "setWoundRecovery", setInt<&Soldier::setWoundRecovery> },
	{ "getManaMissing", getInt<&Soldier::getManaMissing> },
	{ "setManaMissing", setInt<&Soldier::setManaMissing> },
	{ "getHealthMissing", getInt<&Soldier::getHealthMissing> },
	{ "setHealthMissing", setInt<&Soldier::setHealthMissing> },
	{ "getStat", soldierGetStat },
	{ "setStat", soldierSetStat },
	{ "addStat", soldierAddStat },
	{ "getTag", getTagOf<Soldier> },
	{ "setTag", setTagOf<Soldier> },
	{ nullptr, nullptr }
};

struct Constant
{
	const char *name;
	int value;
};

const Constant CONSTANTS[] = {
	{ "BODYPART_HEAD", BODYPART_HEAD }, { "BODYPART_TORSO", BODYPART_TORSO }, { "BODYPART_RIGHTARM", BODYPART_RIGHTARM },
	{ "BODYPART_LEFTARM", BODYPART_LEFTARM }, { "BODYPART_RIGHTLEG", BODYPART_RIGHTLEG }, { "BODYPART_LEFTLEG", BODYPART_LEFTLEG },
	{ "SIDE_FRONT", SIDE_FRONT }, { "SIDE_LEFT", SIDE_LEFT }, { "SIDE_RIGHT", SIDE_RIGHT }, { "SIDE_REAR", SIDE_REAR }, { "SIDE_UNDER", SIDE_UNDER },
	{ "FACTION_PLAYER", FACTION_PLAYER }, { "FACTION_HOSTILE", FACTION_HOSTILE }, { "FACTION_NEUTRAL", FACTION_NEUTRAL },
	{ "BA_NONE", BA_NONE }, { "BA_TURN", BA_TURN }, { "BA_WALK", BA_WALK }, { "BA_KNEEL", BA_KNEEL }, { "BA_PRIME", BA_PRIME },
	{ "BA_UNPRIME", BA_UNPRIME }, { "BA_THROW", BA_THROW }, { "BA_AUTOSHOT", BA_AUTOSHOT }, { "BA_SNAPSHOT", BA_SNAPSHOT },
	{ "BA_AIMEDSHOT", BA_AIMEDSHOT }, { "BA_HIT", BA_HIT }, { "BA_USE", BA_USE }, { "BA_LAUNCH", BA_LAUNCH },
	{ "BA_MINDCONTROL", BA_MINDCONTROL }, { "BA_PANIC", BA_PANIC }, { "BA_RETHINK", BA_RETHINK }, { "BA_CQB", BA_CQB },
	{ "DT_NONE", DT_NONE }, { "DT_AP", DT_AP }, { "DT_IN", DT_IN }, { "DT_HE", DT_HE }, { "DT_LASER", DT_LASER }, { "DT_PLASMA", DT_PLASMA },
	{ "DT_STUN", DT_STUN }, { "DT_MELEE", DT_MELEE }, { "DT_ACID", DT_ACID }, { "DT_SMOKE", DT_SMOKE }, { "DT_10", DT_10 }, { "DT_11", DT_11 },
	{ "DT_12", DT_12 }, { "DT_13", DT_13 }, { "DT_14", DT_14 }, { "DT_15", DT_15 }, { "DT_16", DT_16 }, { "DT_17", DT_17 }, { "DT_18", DT_18 }, { "DT_19", DT_19 },
	{ "BA_TRIGGER_TIMED_GRENADE", BA_TRIGGER_TIMED_GRENADE }, { "BA_TRIGGER_PROXY_GRENADE", BA_TRIGGER_PROXY_GRENADE }, { "BA_SELF_DESTRUCT", BA_SELF_DESTRUCT },
	{ "UNIT_RANK_ROOKIE", 0 }, { "UNIT_RANK_SQUADDIE", 1 }, { "UNIT_RANK_SERGEANT", 2 }, { "UNIT_RANK_CAPTAIN", 3 }, { "UNIT_RANK_COLONEL", 4 }, { "UNIT_RANK_COMMANDER", 5 },
	{ "GENDER_MALE", GENDER_MALE }, { "GENDER_FEMALE", GENDER_FEMALE },
	{ "LOOK_BLONDE", LOOK_BLONDE }, { "LOOK_BROWNHAIR", LOOK_BROWNHAIR }, { "LOOK_ORIENTAL", LOOK_ORIENTAL }, { "LOOK_AFRICAN", LOOK_AFRICAN },
	{ "MT_WALK", MT_WALK }, { "MT_FLY", MT_FLY }, { "MT_SLIDE", MT_SLIDE },
	{ "STT_TILE", SpecialTileType::TILE }, { "STT_START_POINT", SpecialTileType::START_POINT }, { "STT_END_POINT", SpecialTileType::END_POINT },
	{ "DIFF_BEGINNER", DIFF_BEGINNER }, { "DIFF_EXPERIENCED", DIFF_EXPERIENCED }, { "DIFF_VETERAN", DIFF_VETERAN }, { "DIFF_GENIUS", DIFF_GENIUS }, { "DIFF_SUPERHUMAN", DIFF_SUPERHUMAN },
	{ "BT_NONE", BT_NONE }, { "BT_FIREARM", BT_FIREARM }, { "BT_AMMO", BT_AMMO }, { "BT_MELEE", BT_MELEE }, { "BT_GRENADE", BT_GRENADE },
	{ "BT_PROXIMITYGRENADE", BT_PROXIMITYGRENADE }, { "BT_MEDIKIT", BT_MEDIKIT }, { "BT_SCANNER", BT_SCANNER }, { "BT_MINDPROBE", BT_MINDPROBE },
	{ "BT_PSIAMP", BT_PSIAMP }, { "BT_FLARE", BT_FLARE }, { "BT_CORPSE", BT_CORPSE },
	{ "BAM_NORMAL", BAM_NORMAL }, { "BAM_RUN", BAM_RUN }, { "BAM_STRAFE", BAM_STRAFE }, { "BAM_SNEAK", BAM_SNEAK },
	{ "BMA_HEAL", BMA_HEAL }, { "BMA_STIMULANT", BMA_STIMULANT }, { "BMA_PAINKILLER", BMA_PAINKILLER },
	{ "SATISFACTION_ALIENPACT", (int)Country::Satisfaction::ALIEN_PACT }, { "SATISFACTION_UNHAPPY", (int)Country::Satisfaction::UNHAPPY },
	{ "SATISFACTION_SATISFIED", (int)Country::Satisfaction::SATISFIED }, { "SATISFACTION_HAPPY", (int)Country::Satisfaction::HAPPY },
	{ "UFO_FLYING", Ufo::FLYING }, { "UFO_LANDED", Ufo::LANDED }, { "UFO_CRASHED", Ufo::CRASHED }, { "UFO_DESTROYED", Ufo::DESTROYED }, { "UFO_IGNORE_ME", Ufo::IGNORE_ME },
	{ "DETECTION_NONE", DETECTION_NONE }, { "DETECTION_RADAR", DETECTION_RADAR }, { "DETECTION_HYPERWAVE", DETECTION_HYPERWAVE },
};

void setupGame(lua_State *L, void *mod)
{
	LuaSandbox::defineType(L, TYPE_UNIT, UNIT_METHODS);
	LuaSandbox::defineType(L, TYPE_ITEM, ITEM_METHODS);
	LuaSandbox::defineType(L, TYPE_BATTLE, BATTLE_METHODS);
	LuaSandbox::defineType(L, TYPE_SKILL, SKILL_METHODS);
	LuaSandbox::defineType(L, TYPE_SOLDIER, SOLDIER_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_ARMOR, RULE_ARMOR_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_ITEM, RULE_ITEM_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_DAMAGE, RULE_DAMAGE_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_UNIT, RULE_UNIT_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_SOLDIER, RULE_SOLDIER_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_BONUS, RULE_BONUS_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_COUNTRY, RULE_COUNTRY_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_UFO, RULE_UFO_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_CRAFT, RULE_CRAFT_METHODS);
	LuaSandbox::defineType(L, TYPE_TILE, TILE_METHODS);
	LuaSandbox::defineType(L, TYPE_GEOSCAPE, GEOSCAPE_METHODS);
	LuaSandbox::defineType(L, TYPE_COUNTRY, COUNTRY_METHODS);
	LuaSandbox::defineType(L, TYPE_UFO, UFO_METHODS);
	LuaSandbox::defineType(L, TYPE_CRAFT, CRAFT_METHODS);
	lua_pushlightuserdata(L, mod);
	lua_setfield(L, LUA_REGISTRYINDEX, MOD_KEY);
	lua_getglobal(L, "game");
	for (const auto &constant : CONSTANTS)
	{
		lua_pushinteger(L, constant.value);
		lua_setfield(L, -2, constant.name);
	}
	lua_pop(L, 1);
}

struct FireData
{
	const EventInfo *info;
	const LuaHost::Arg *args;
	size_t count;
	int *out;
};

int pushArgs(lua_State *L, void *data)
{
	auto *fire = static_cast<FireData*>(data);
	luaL_checkstack(L, (int)fire->count + 8, "handler arguments");
	for (size_t i = 0; i < fire->count; ++i)
	{
		const auto &arg = fire->args[i];
		switch (arg.kind)
		{
		case LuaHost::Arg::UNIT: pushOrNil(L, TYPE_UNIT, arg.object); break;
		case LuaHost::Arg::ITEM: pushOrNil(L, TYPE_ITEM, arg.object); break;
		case LuaHost::Arg::BATTLE: pushOrNil(L, TYPE_BATTLE, arg.object); break;
		case LuaHost::Arg::SKILL: pushOrNil(L, TYPE_SKILL, arg.object); break;
		case LuaHost::Arg::SOLDIER: pushOrNil(L, TYPE_SOLDIER, arg.object); break;
		case LuaHost::Arg::GEOSCAPE: pushOrNil(L, TYPE_GEOSCAPE, arg.object); break;
		case LuaHost::Arg::COUNTRY: pushOrNil(L, TYPE_COUNTRY, arg.object); break;
		case LuaHost::Arg::UFO: pushOrNil(L, TYPE_UFO, arg.object); break;
		case LuaHost::Arg::CRAFT: pushOrNil(L, TYPE_CRAFT, arg.object); break;
		case LuaHost::Arg::BONUS: pushOrNil(L, TYPE_RULE_BONUS, arg.object); break;
		case LuaHost::Arg::INT: lua_pushinteger(L, arg.value); break;
		}
	}
	if (!fire->out)
	{
		return (int)fire->count;
	}
	const auto &names = fire->info->outputs;
	lua_createtable(L, 0, (int)names.size());
	for (size_t i = 0; i < names.size(); ++i)
	{
		lua_pushinteger(L, fire->out[i]);
		lua_setfield(L, -2, names[i]);
	}
	lua_pushvalue(L, -1);
	lua_setfield(L, LUA_REGISTRYINDEX, OUT_KEY);
	return (int)fire->count + 1;
}

/// Takes the output values back, all of them or none. Raw access: the table is the mod's, its metatable too.
bool takeOutputs(lua_State *L, void *data, std::string &error)
{
	auto *fire = static_cast<FireData*>(data);
	const auto &names = fire->info->outputs;
	std::vector<int> values(fire->out, fire->out + names.size());
	lua_getfield(L, LUA_REGISTRYINDEX, OUT_KEY);
	for (size_t i = 0; i < names.size(); ++i)
	{
		if (fire->info->readOnly.count(names[i]))
		{
			continue;
		}
		lua_pushstring(L, names[i]);
		lua_rawget(L, -2);
		int isInteger = 0;
		const lua_Integer value = lua_type(L, -1) == LUA_TNUMBER ? lua_tointegerx(L, -1, &isInteger) : 0;
		lua_pop(L, 1);
		if (!isInteger || value < INT_MIN || value > INT_MAX)
		{
			error = std::string(fire->info->name) + ": output value '" + names[i] + "' must be a whole number, all output values of this call are ignored";
			lua_pop(L, 1);
			return false;
		}
		const auto range = fire->info->ranges.find(names[i]);
		if (range != fire->info->ranges.end() && (value < range->second.first || value > range->second.second))
		{
			error = std::string(fire->info->name) + ": output value '" + names[i] + "' must be from " + std::to_string(range->second.first) + " to " + std::to_string(range->second.second) + ", all output values of this call are ignored";
			lua_pop(L, 1);
			return false;
		}
		values[i] = (int)value;
	}
	lua_pop(L, 1);
	std::copy(values.begin(), values.end(), fire->out);
	return true;
}

}

LuaHost::~LuaHost() = default;

LuaHost *LuaHost::create(Mod *mod)
{
	std::unique_ptr<LuaHost> host;
	int off = 0;
	for (const auto *info : Options::getActiveMods())
	{
		// the mod's own folder, not FileMap: it glues all mods in one tree, and one lua/main.lua would hide another
		const std::string path = info->getPath() + "/lua/main.lua";
		if (info->getLuaApi() == 0 || !CrossPlatform::fileExists(path))
		{
			continue;
		}
		if (!Options::oxceLuaMods)
		{
			++off;
			continue;
		}
		if (!host)
		{
			host = std::make_unique<LuaHost>();
			host->_mod = mod;
		}
		host->_entries.emplace_back();
		auto &entry = host->_entries.back();
		entry.id = info->getId();
		entry.path = path;
		entry.api = info->getLuaApi();
	}
	if (off > 0)
	{
		Log(LOG_INFO) << "[lua] Lua is off (oxceLuaMods), " << off << " mods run without it";
	}
	if (host)
	{
		host->reload();
	}
	return host.release();
}

std::string LuaHost::reload()
{
	int loaded = 0, failed = 0;
	std::fill(std::begin(_handled), std::end(_handled), false);
	std::set<std::string> names;
	for (const auto &event : EVENTS)
	{
		names.insert(event.name);
	}
	for (size_t i = 0; i < _entries.size(); ++i)
	{
		auto &entry = _entries[i];
		entry.sandbox.reset();
		entry.notified = false;
		if (entry.api > API_VERSION)
		{
			++failed;
			noteError(i, "main.lua", "the mod needs Lua API " + std::to_string(entry.api) + ", this game has " + std::to_string(API_VERSION) + ", the mod's Lua is off");
			continue;
		}
		auto file = CrossPlatform::readFile(entry.path);
		if (!file)
		{
			++failed;
			noteError(i, "main.lua", "cannot read " + entry.path);
			continue;
		}
		std::string code{ std::istreambuf_iterator<char>(*file), std::istreambuf_iterator<char>() };
		// a text editor's UTF-8 with BOM: Lua reads the mark as a syntax error on the first line
		if (code.compare(0, 3, "\xEF\xBB\xBF") == 0)
		{
			code.erase(0, 3);
		}
		const std::string id = entry.id;
		entry.sandbox = std::make_unique<LuaSandbox>(LuaSandbox::Limits{}, names,
			[id](const std::string &text) { Log(LOG_INFO) << "[lua] " << id << ": " << text; },
			[](int low, int high) { return RNG::generate(low, high); });
		entry.sandbox->setErrorFn([this, i](const std::string &event, const std::string &text) { noteError(i, event, text); });
		if (!entry.sandbox->setup(setupGame, _mod) || !entry.sandbox->load("main.lua", code))
		{
			++failed;
			Log(LOG_ERROR) << "[lua] " << id << ": main.lua failed, the mod's Lua is off";
			continue;
		}
		++loaded;
		Log(LOG_INFO) << "[lua] " << id << ": loaded, " << entry.sandbox->memoryUsed() / 1024 << " KB";
		for (int e = 0; e < EVENT_COUNT; ++e)
		{
			_handled[e] = _handled[e] || entry.sandbox->hasHandlers(EVENTS[e].name);
		}
	}
	std::string result = "Lua: " + std::to_string(loaded) + " mods loaded";
	if (failed > 0)
	{
		result += ", " + std::to_string(failed) + " failed, see user/lua_errors.log";
	}
	return result;
}

void LuaHost::writeJournal(const std::string &id, const std::string &event, const std::string &text)
{
	_journal += CrossPlatform::now() + " " + id + " " + event + ": " + text + "\n\n";
	if (_journal.size() >= JOURNAL_MAX)
	{
		// the newest errors are the ones an author is looking for, a fixed mod should not stop reporting
		const size_t from = _journal.find("\n\n", _journal.size() - JOURNAL_MAX / 2);
		_journal = "the log was full, older errors are dropped\n\n" + (from == std::string::npos ? std::string() : _journal.substr(from + 2));
	}
	CrossPlatform::writeFile(Options::getUserFolder() + "lua_errors.log", _journal);
}

void LuaHost::noteError(size_t entry, const std::string &event, const std::string &text)
{
	auto &mod = _entries[entry];
	writeJournal(mod.id, event, text);
	const bool off = mod.sandbox && mod.sandbox->isDisabled();
	if (!mod.notified || off)
	{
		mod.notified = true;
		_notice = "Lua " + mod.id + (off ? ": too many errors, the mod's Lua is off" : ": error") + ", see user/lua_errors.log";
	}
}

void LuaHost::fireOutputs(Event event, std::initializer_list<Arg> args, int *out)
{
	if (_handled[event])
	{
		FireData data{ &EVENTS[event], args.begin(), args.size(), out };
		g_noScreen = event == RETURN_FROM_MISSION_UNIT;
		g_onlyReads = EVENTS[event].onlyReads;
		for (auto &entry : _entries)
		{
			if (entry.sandbox)
			{
				entry.sandbox->fire(EVENTS[event].name, pushArgs, &data, out ? takeOutputs : nullptr);
			}
		}
	}
	if (!_notice.empty() && event != RETURN_FROM_MISSION_UNIT)
	{
		for (const auto &arg : args)
		{
			if (arg.kind == Arg::BATTLE && arg.object && static_cast<SavedBattleGame*>(arg.object)->getBattleState())
			{
				static_cast<SavedBattleGame*>(arg.object)->getBattleState()->warningLongRaw(_notice);
				_notice.clear();
				break;
			}
		}
	}
}

}
