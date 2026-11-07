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
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <istream>
#include <iterator>
#include <map>
#include <set>
#include <string>
#include <thread>
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
#include "../Interface/Text.h"
#include "../Menu/LuaScreenState.h"
#include "../Savegame/Base.h"
#include "../Savegame/BattleItem.h"
#include "../Savegame/BattleUnit.h"
#include "../Savegame/Country.h"
#include "../Savegame/Craft.h"
#include "../Savegame/GameTime.h"
#include "../Savegame/ItemContainer.h"
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/SavedGame.h"
#include "../Savegame/Soldier.h"
#include "../Savegame/Tile.h"
#include "MapData.h"
#include "MapDataSet.h"
#include "../Savegame/Transfer.h"
#include "../Savegame/Ufo.h"
#include "../Ufopaedia/StatsForNerdsState.h"
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
const char *const TYPE_RULES = "rules";
const char *const TYPE_RULE_RESEARCH = "ruleResearch";
const char *const TYPE_RULE_INVENTORY = "ruleInventory";
const char *const TYPE_NERDS = "statsForNerds";
const char *const TYPE_UI = "ui";
const char *const TYPE_UI_WIDGET = "uiWidget";
const char *const TYPE_BASE = "base";
const char *const MOD_KEY = "oxce.mod";
const char *const OUT_KEY = "oxce.out";

/// What a slow API call costs a handler, in C loop steps: the counter sees it as one instruction.
const unsigned long long TAG_TICKS = 100, LIST_TICKS = 20, MESSAGE_TICKS = 20000, SPAWN_TICKS = 1000, WIDGET_TICKS = 2000, ROW_TICKS = 200;
/// The ceilings of the queue: the engine's work behind one call is not in the mod's budget.
const int SPAWN_ITEMS_PER_CALL = 32, SPAWN_ITEMS_PER_TURN = 256, SPAWN_UNITS_PER_CALL = 4, SPAWN_UNITS_PER_TURN = 16, MAP_TILES_PER_CALL = 64, MAP_TILES_PER_TURN = 512;
const int SCREENS_PER_CALL = 1, SCREENS_PER_PERIOD = 8;
const int SOLDIERS_PER_CALL = 16, SOLDIERS_PER_DAY = 64;
const lua_Integer ECONOMY_MAX = 1000000000;
const unsigned long long ECONOMY_TICKS = 1000;
const size_t SCREENS_PER_MOD = 64, UI_TEXT_MAX = 2000;
const size_t GLOW_ONE_BY_ONE = 4;
const size_t MESSAGE_MAX = 200, JOURNAL_MAX = 256 * 1024;

/// Handlers and their output values, the names of the Y-script. A value in `readOnly` is shown, not taken back.
/// `onlyReads`: the Y-script gets the arguments as const, so what it may not change Lua may not either.
/// `ranges`: the game casts these values to its own enum, a number outside is refused like a non-number.
/// `pure`: called from lists, tooltips and the frame, so the number of calls is not the game's: no random numbers.
struct EventInfo
{
	const char *name;
	std::vector<const char*> outputs;
	std::set<std::string> readOnly;
	bool onlyReads = false;
	std::map<std::string, std::pair<int, int>> ranges = { };
	bool pure = false;
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
	{ "hitUnitAmmo", { "power", "part", "side" }, { } },
	{ "damageUnitAmmo", { "to_health", "to_armor", "to_stun", "to_time", "to_energy", "to_morale", "to_wound", "to_transform", "to_mana" }, { } },
	{ "damageSpecialUnitAmmo", { "transform", "transform_chance", "self_destruct", "self_destruct_chance", "morale_loss", "fire",
		"attacker_turns_since_spotted", "attacker_turns_left_spotted_for_snipers" }, { "transform", "self_destruct" } },
	{ "reactionUnitAction", { "reaction_chance", "distance" }, { "distance" }, true },
	{ "reactionUnitReaction", { "reaction_chance", "distance" }, { "distance" }, true },
	{ "reactionWeaponAction", { "reaction_chance", "distance" }, { "distance" }, true },
	{ "visibilityUnit", { "current_visibility", "default_visibility" }, { "default_visibility" }, true, { }, true },
	{ "aiCalculateTargetWeight", { "current_target_weight", "default_target_weight" }, { "default_target_weight" }, true },
	{ "sellCostItem", { "cost_current", "cost_base" }, { "cost_base" }, true, { }, true },
	{ "buyCostItem", { "cost_current", "cost_base" }, { "cost_base" }, true, { }, true },
	{ "statsForNerdsItem", { }, { }, true, { }, true },
	{ "statsForNerdsArmor", { }, { }, true, { }, true },
	{ "statsForNerdsCraft", { }, { }, true, { }, true },
	{ "statsForNerdsUfo", { }, { }, true, { }, true },
	{ "psiDefenceBonusStats", { "bonus" }, { }, true, { }, true },
	{ "meleeDodgeBonusStats", { "bonus" }, { }, true, { }, true },
	{ "timeRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "energyRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "moraleRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "healthRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "manaRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "stunRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "timeSoldierRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "energySoldierRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "moraleSoldierRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "healthSoldierRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "manaSoldierRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "stunSoldierRecoveryBonusStats", { "bonus" }, { }, true, { }, true },
	{ "damageBonusBonusStats", { "bonus" }, { }, true, { }, true },
	{ "meleeBonusBonusStats", { "bonus" }, { }, true, { }, true },
	{ "accuracyMultiplierBonusStats", { "bonus" }, { }, true, { }, true },
	{ "meleeMultiplierBonusStats", { "bonus" }, { }, true, { }, true },
	{ "throwMultiplierBonusStats", { "bonus" }, { }, true, { }, true },
	{ "closeQuartersMultiplierBonusStats", { "bonus" }, { }, true, { }, true },
	{ "newHour", { }, { } },
	{ "newDay", { }, { } },
	{ "newMonth", { }, { } },
	{ "battleStart", { }, { }, true },
	{ "battleEnd", { }, { }, true },
};

/// Set before main() runs. Not the thread that makes the host: the mods load in a thread of their own (StartState).
const std::thread::id g_mainThread = std::this_thread::get_id();
/// The battle screen may be gone by then: the debriefing runs after it.
bool g_noScreen = false;
/// The running handler is one of EventInfo::onlyReads.
bool g_onlyReads = false;
/// The running handler is one of EventInfo::pure.
bool g_pure = false;
/// The running function builds a screen or is its onClose: it only reads, for another reason than the Y-script's.
bool g_screenReads = false;
/// The running function is one of those whose moment is known: the methods of 'economy' work only there.
bool g_mayEconomy = false;
/// The running handler is battleStart: it only reads, and what it queues runs later, in the battle's own moment.
bool g_battleStart = false;

void checkWritable(lua_State *L)
{
	if (g_onlyReads)
	{
		luaL_error(L, g_screenReads ? "a screen's builder and onClose only read: a screen opened and closed changes nothing"
			: "this handler only reads: the Y-script of the same name gets these objects as const");
	}
}

void checkRandomAllowed(lua_State *L)
{
	if (g_pure)
	{
		luaL_error(L, "no random numbers in this handler: it is called from lists, tooltips and the frame, and would move the game's generator");
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
template<> struct LuaType<Mod> { static const char *name() { return TYPE_RULES; } };
template<> struct LuaType<RuleResearch> { static const char *name() { return TYPE_RULE_RESEARCH; } };
template<> struct LuaType<RuleInventory> { static const char *name() { return TYPE_RULE_INVENTORY; } };
template<> struct LuaType<RuleSkill> { static const char *name() { return TYPE_SKILL; } };
template<> struct LuaType<StatsForNerdsState> { static const char *name() { return TYPE_NERDS; } };
template<> struct LuaType<Base> { static const char *name() { return TYPE_BASE; } };

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
	checkRandomAllowed(L);
	const int low = checkInt(L, 2), high = checkInt(L, 3);
	luaL_argcheck(L, high >= low, 3, "the upper bound is below the lower one");
	lua_pushinteger(L, RNG::generate(low, high));
	return 1;
}

int battleRandomChance(lua_State *L)
{
	checkBattle(L);
	checkRandomAllowed(L);
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

/// The running handler may not change the game, or the battle has no more moments to do it in.
void checkMayQueue(lua_State *L)
{
	if (!g_battleStart)
	{
		checkWritable(L);
	}
	if (g_pure || g_noScreen)
	{
		luaL_error(L, "this handler cannot change the battle: nothing it queues would run in its place");
	}
}

/// What a method of 'economy' asks of the moment. Numbers change on the spot: nothing walks a list at these moments.
SavedGame *checkEconomy(lua_State *L, const char *method)
{
	checkWritable(L);
	auto *host = LuaHost::active();
	auto *sandbox = LuaSandbox::from(L);
	if (!host || !host->hasCap(sandbox, LuaHost::CAP_ECONOMY))
	{
		luaL_error(L, "%s needs 'economy' in luaCaps of metadata.yml", method);
	}
	auto *saved = LuaScreenState::savedGame();
	if (!saved || saved->getSavedBattle())
	{
		luaL_error(L, "%s does not work in a battle: its end takes from the stores and fills them by itself", method);
	}
	if (!g_mayEconomy)
	{
		luaL_error(L, "%s works in newHour, newDay, newMonth, in a click on a screen and in the function of hireSoldier", method);
	}
	sandbox->charge(L, ECONOMY_TICKS);
	return saved;
}

/// What a method of 'spawn' or 'map' asks of the moment.
SavedBattleGame *checkSpawn(lua_State *L, const char *method, LuaHost::Cap cap = LuaHost::CAP_SPAWN, const char *word = "spawn")
{
	checkMayQueue(L);
	auto *host = LuaHost::active();
	if (!host || !host->hasCap(LuaSandbox::from(L), cap))
	{
		luaL_error(L, "%s needs '%s' in luaCaps of metadata.yml", method, word);
	}
	auto *saved = LuaScreenState::savedGame();
	auto *battle = saved ? saved->getSavedBattle() : nullptr;
	if (!battle)
	{
		luaL_error(L, "%s works only in a battle", method);
	}
	if (battle->isPreview())
	{
		luaL_error(L, "%s does not work in the craft's preview", method);
	}
	return battle;
}

/// The function a method of 'spawn' got, LuaSandbox::keep() of it; 0 when there is none.
int keepDone(lua_State *L, int index)
{
	if (lua_isnoneornil(L, index))
	{
		return 0;
	}
	luaL_checktype(L, index, LUA_TFUNCTION);
	return LuaSandbox::keep(L, index);
}

int finishQueued(lua_State *L, int done, const std::string &error)
{
	if (!error.empty())
	{
		if (done)
		{
			LuaSandbox::from(L)->drop(done);
		}
		return luaL_error(L, "%s", error.c_str());
	}
	return 0;
}

/// battle:spawnItem(type, x, y, z[, done]): done(item) runs later, when the item is on the map.
int battleSpawnItem(lua_State *L)
{
	checkSpawn(L, "spawnItem");
	auto *host = LuaHost::active();
	auto *sandbox = LuaSandbox::from(L);
	auto *battle = checkBattle(L);
	const char *type = luaL_checkstring(L, 2);
	const RuleItem *rule = battle->getMod()->getItem(type);
	if (!rule)
	{
		return luaL_error(L, "no item '%s' in the rules", type);
	}
	const int x = checkInt(L, 3), y = checkInt(L, 4), z = checkInt(L, 5);
	// Position keeps short numbers: one past them would wrap into the map
	luaL_argcheck(L, x >= 0 && y >= 0 && z >= 0 && x < battle->getMapSizeX() && y < battle->getMapSizeY() && z < battle->getMapSizeZ(), 3, "outside the map");
	if (!lua_isnoneornil(L, 6))
	{
		luaL_checktype(L, 6, LUA_TFUNCTION);
	}
	sandbox->charge(L, SPAWN_TICKS);
	const int done = lua_isnoneornil(L, 6) ? 0 : LuaSandbox::keep(L, 6);
	return finishQueued(L, done, host->queueSpawnItem(sandbox, battle, rule, x, y, z, done));
}

/// battle:removeItem(item[, done]): done(true) runs later, when the item is gone, or done(nil, reason).
int battleRemoveItem(lua_State *L)
{
	checkSpawn(L, "removeItem");
	auto *sandbox = LuaSandbox::from(L);
	auto *battle = checkBattle(L);
	auto *item = static_cast<BattleItem*>(LuaSandbox::checkObject(L, 2, TYPE_ITEM));
	sandbox->charge(L, SPAWN_TICKS);
	const int done = keepDone(L, 3);
	return finishQueued(L, done, LuaHost::active()->queueRemoveItem(sandbox, battle, item, done));
}

int fieldInt(lua_State *L, const char *name, int low, int high, int fallback, bool required);

/// battle:spawnUnit{ type, x, y, z, faction, direction, done }: done(unit) runs later, or done(nil, reason).
int battleSpawnUnit(lua_State *L)
{
	checkSpawn(L, "spawnUnit");
	auto *sandbox = LuaSandbox::from(L);
	auto *battle = checkBattle(L);
	luaL_checktype(L, 2, LUA_TTABLE);
	lua_pushstring(L, "type");
	lua_rawget(L, 2);
	const char *type = lua_tostring(L, -1);
	if (!type)
	{
		return luaL_error(L, "field 'type' is needed");
	}
	const Unit *rule = battle->getMod()->getUnit(type);
	if (!rule)
	{
		return luaL_error(L, "no unit '%s' in the rules: a soldier cannot be made here", type);
	}
	lua_pop(L, 1);
	// Position keeps short numbers: one past them would wrap into the map
	const int x = fieldInt(L, "x", 0, battle->getMapSizeX() - 1, 0, true);
	const int y = fieldInt(L, "y", 0, battle->getMapSizeY() - 1, 0, true);
	const int z = fieldInt(L, "z", 0, battle->getMapSizeZ() - 1, 0, true);
	const int faction = fieldInt(L, "faction", FACTION_PLAYER, FACTION_NEUTRAL, FACTION_HOSTILE, false);
	const int direction = fieldInt(L, "direction", 0, 7, -1, false);
	lua_pushstring(L, "done");
	lua_rawget(L, 2);
	sandbox->charge(L, SPAWN_TICKS);
	const int done = keepDone(L, lua_gettop(L));
	return finishQueued(L, done, LuaHost::active()->queueSpawnUnit(sandbox, battle, rule, x, y, z, faction, direction, done));
}

/// unit:giveItem(type[, done]): done(item) runs later, when the item is in the inventory, or done(nil, reason).
int unitGiveItem(lua_State *L)
{
	auto *battle = checkSpawn(L, "giveItem");
	auto *sandbox = LuaSandbox::from(L);
	auto *unit = checkUnit(L);
	const char *type = luaL_checkstring(L, 2);
	const RuleItem *rule = battle->getMod()->getItem(type);
	if (!rule)
	{
		return luaL_error(L, "no item '%s' in the rules", type);
	}
	sandbox->charge(L, SPAWN_TICKS);
	const int done = keepDone(L, 3);
	return finishQueued(L, done, LuaHost::active()->queueGiveItem(sandbox, battle, unit, rule, done));
}

/// A part of a tile as a mod names it. R-777: it becomes an index.
TilePart checkPart(lua_State *L, int index)
{
	const int part = checkInt(L, index);
	luaL_argcheck(L, part >= O_FLOOR && part < O_MAX, index, "no such part, see game.PART_*");
	return (TilePart)part;
}

/// tile:getPart(part): the name of the set and the number in it, nil for an empty part.
int tileGetPart(lua_State *L)
{
	const auto *tile = self<Tile>(L);
	const TilePart part = checkPart(L, 2);
	const auto *data = tile->getMapData(part);
	if (!data)
	{
		lua_pushnil(L);
		return 1;
	}
	int id, set;
	tile->getMapData(&id, &set, part);
	lua_pushstring(L, data->getDataset()->getName().c_str());
	lua_pushinteger(L, id);
	return 2;
}

/// The end of every method of 'map': the part, the set and the value mean what `op` needs of them.
int queueMapOp(lua_State *L, const char *method, LuaHost::MapOp op, TilePart part, int id, int set, int value, int doneIndex)
{
	auto *battle = checkSpawn(L, method, LuaHost::CAP_MAP, "map");
	auto *sandbox = LuaSandbox::from(L);
	const Position pos = self<Tile>(L)->getPosition();
	sandbox->charge(L, SPAWN_TICKS);
	const int done = keepDone(L, doneIndex);
	return finishQueued(L, done, LuaHost::active()->queueMapOp(sandbox, battle, method, op, pos.x, pos.y, pos.z, part, id, set, value, done));
}

/// tile:setPart(part, set, id[, done]): done(tile) runs later, or done(nil, reason).
int tileSetPart(lua_State *L)
{
	auto *battle = checkSpawn(L, "setPart", LuaHost::CAP_MAP, "map");
	const TilePart part = checkPart(L, 2);
	const char *name = luaL_checkstring(L, 3);
	auto &sets = *battle->getMapDataSets();
	int set = -1;
	for (size_t i = 0; i < sets.size() && set < 0; ++i)
	{
		if (sets[i]->getName() == name)
		{
			set = (int)i;
		}
	}
	if (set < 0)
	{
		return luaL_error(L, "no set '%s' in this battle, see battle:getMapSets()", name);
	}
	const int id = checkInt(L, 4);
	luaL_argcheck(L, id >= 0 && (size_t)id < sets[set]->getSize(), 4, "no such number in the set");
	luaL_argcheck(L, sets[set]->getObject(id)->getObjectType() == part, 4, "this number of the set is another part of a tile");
	return queueMapOp(L, "setPart", LuaHost::MAP_SET, part, id, set, 0, 5);
}

/// tile:clearPart(part[, done]): the same.
int tileClearPart(lua_State *L)
{
	return queueMapOp(L, "clearPart", LuaHost::MAP_CLEAR, checkPart(L, 2), -1, -1, 0, 3);
}

/// tile:destroyPart(part[, done]): the same, the way of an explosion: the part turns into its wreck.
int tileDestroyPart(lua_State *L)
{
	return queueMapOp(L, "destroyPart", LuaHost::MAP_DESTROY, checkPart(L, 2), -1, -1, 0, 3);
}

/// tile:setFire(turns[, done]): the same. As in the engine's burning, 0 to 255 turns.
int tileSetFire(lua_State *L)
{
	const int turns = checkInt(L, 2);
	luaL_argcheck(L, turns >= 0 && turns <= 255, 2, "from 0 to 255 turns");
	return queueMapOp(L, "setFire", LuaHost::MAP_FIRE, O_FLOOR, -1, -1, turns, 3);
}

/// tile:setSmoke(density[, done]): the same. The engine's smoke has 0 to 15, Map takes a sprite by it.
int tileSetSmoke(lua_State *L)
{
	const int density = checkInt(L, 2);
	luaL_argcheck(L, density >= 0 && density <= 15, 2, "from 0 to 15");
	return queueMapOp(L, "setSmoke", LuaHost::MAP_SMOKE, O_FLOOR, -1, -1, density, 3);
}

/// battle:getMapSets(): what setPart may take in this battle, a list of { name, size }.
int battleGetMapSets(lua_State *L)
{
	const auto &sets = *checkBattle(L)->getMapDataSets();
	LuaSandbox::from(L)->charge(L, LIST_TICKS * sets.size());
	lua_createtable(L, (int)sets.size(), 0);
	for (size_t i = 0; i < sets.size(); ++i)
	{
		lua_createtable(L, 0, 2);
		lua_pushstring(L, sets[i]->getName().c_str());
		lua_setfield(L, -2, "name");
		lua_pushinteger(L, (lua_Integer)sets[i]->getSize());
		lua_setfield(L, -2, "size");
		lua_rawseti(L, -2, (lua_Integer)i + 1);
	}
	return 1;
}

/// A handle of a screen: unlike the game's objects it outlives the call, and dies when the screen closes.
struct UiHandle
{
	unsigned long long screen;
	int widget;
};

void pushUiHandle(lua_State *L, const char *type, unsigned long long screen, int widget)
{
	auto *handle = static_cast<UiHandle*>(lua_newuserdatauv(L, sizeof(UiHandle), 0));
	handle->screen = screen;
	handle->widget = widget;
	luaL_setmetatable(L, type);
}

LuaScreenState *checkUi(lua_State *L)
{
	auto *handle = static_cast<UiHandle*>(luaL_checkudata(L, 1, TYPE_UI));
	auto *screen = LuaScreenState::find(handle->screen);
	if (!screen)
	{
		luaL_error(L, "this screen is closed");
	}
	return screen;
}

LuaScreenState *checkBuilding(lua_State *L)
{
	auto *screen = checkUi(L);
	if (!screen->isBuilding())
	{
		luaL_error(L, "widgets are made only while the screen is being built");
	}
	if (screen->getWidgets() >= LuaScreenState::MAX_WIDGETS)
	{
		luaL_error(L, "more than %d widgets on one screen", (int)LuaScreenState::MAX_WIDGETS);
	}
	LuaSandbox::from(L)->charge(L, WIDGET_TICKS);
	return screen;
}

/// `kinds` is a mask of LuaScreenState::Kind: the error names the method and what it works on.
LuaScreenState *checkWidget(lua_State *L, int &widget, unsigned kinds, const char *what)
{
	auto *handle = static_cast<UiHandle*>(luaL_checkudata(L, 1, TYPE_UI_WIDGET));
	auto *screen = LuaScreenState::find(handle->screen);
	if (!screen)
	{
		luaL_error(L, "this widget's screen is closed");
	}
	widget = handle->widget;
	if (!(kinds & (1u << screen->getKind(widget))))
	{
		luaL_error(L, "%s", what);
	}
	return screen;
}

const char *checkUiText(lua_State *L, int index)
{
	size_t len = 0;
	const char *text = luaL_checklstring(L, index, &len);
	luaL_argcheck(L, len <= UI_TEXT_MAX, index, "too long");
	luaL_argcheck(L, Unicode::isValidUTF8(text), index, "not UTF-8");
	return text;
}

/// A typo in a field would otherwise read as a field not given. `names` has spaces around every name.
void checkFields(lua_State *L, const char *names)
{
	luaL_checktype(L, 2, LUA_TTABLE);
	lua_pushnil(L);
	while (lua_next(L, 2))
	{
		lua_pop(L, 1);
		if (lua_type(L, -1) != LUA_TSTRING || !std::strstr(names, (std::string(" ") + lua_tostring(L, -1) + " ").c_str()))
		{
			luaL_error(L, "unknown field '%s', this widget has:%s", lua_type(L, -1) == LUA_TSTRING ? lua_tostring(L, -1) : luaL_typename(L, -1), names);
		}
	}
}

/// A number of the widget's table, checked both ways: it becomes a size or an index (R-777).
int fieldInt(lua_State *L, const char *name, int low, int high, int fallback, bool required)
{
	lua_pushstring(L, name);
	lua_rawget(L, 2);
	if (lua_isnil(L, -1))
	{
		if (required)
		{
			luaL_error(L, "field '%s' is needed", name);
		}
		lua_pop(L, 1);
		return fallback;
	}
	int isInteger = 0;
	const lua_Integer value = lua_tointegerx(L, -1, &isInteger);
	if (!isInteger || value < low || value > high)
	{
		luaL_error(L, "field '%s' must be a whole number from %d to %d", name, low, high);
	}
	lua_pop(L, 1);
	return (int)value;
}

bool fieldBool(lua_State *L, const char *name)
{
	lua_pushstring(L, name);
	lua_rawget(L, 2);
	const bool value = lua_toboolean(L, -1);
	lua_pop(L, 1);
	return value;
}

/// The string stays alive as long as the table does, and the table is the caller's argument.
const char *fieldText(lua_State *L, const char *name)
{
	lua_pushstring(L, name);
	lua_rawget(L, 2);
	const char *text = "";
	if (!lua_isnil(L, -1))
	{
		if (lua_type(L, -1) != LUA_TSTRING)
		{
			luaL_error(L, "field '%s' must be a string", name);
		}
		size_t len = 0;
		text = lua_tolstring(L, -1, &len);
		if (len > UI_TEXT_MAX || !Unicode::isValidUTF8(text))
		{
			luaL_error(L, "field '%s': too long or not UTF-8", name);
		}
	}
	lua_pop(L, 1);
	return text;
}

/// Kept last of all: an error after this would leave the function in the registry.
int fieldFn(lua_State *L, const char *name)
{
	lua_pushstring(L, name);
	lua_rawget(L, 2);
	int kept = 0;
	if (lua_isfunction(L, -1))
	{
		kept = LuaSandbox::keep(L, -1);
	}
	lua_pop(L, 1);
	return kept;
}

void checkFnField(lua_State *L, const char *name)
{
	lua_pushstring(L, name);
	lua_rawget(L, 2);
	if (!lua_isnil(L, -1) && !lua_isfunction(L, -1))
	{
		luaL_error(L, "field '%s' must be a function", name);
	}
	lua_pop(L, 1);
}

int alignOf(lua_State *L)
{
	const std::string align = fieldText(L, "align");
	return align.empty() || align == "left" ? ALIGN_LEFT : align == "center" ? ALIGN_CENTER : align == "right" ? ALIGN_RIGHT
		: luaL_error(L, "field 'align' must be left, center or right");
}

struct Box { int x, y, w, h, color; };

Box fieldBox(lua_State *L, bool sized = true)
{
	Box box;
	box.x = fieldInt(L, "x", 0, 319, 0, true);
	box.y = fieldInt(L, "y", 0, 199, 0, true);
	box.w = sized ? fieldInt(L, "w", 1, 320, 0, true) : 0;
	box.h = sized ? fieldInt(L, "h", 1, 200, 0, true) : 0;
	box.color = fieldInt(L, "color", 0, 255, -1, false);
	return box;
}

int finishWidget(lua_State *L, LuaScreenState *screen, int widget, const Box &box, bool click, bool change, bool enter)
{
	const int onClick = click ? fieldFn(L, "onClick") : 0;
	const int onChange = change ? fieldFn(L, "onChange") : 0;
	const int onEnter = enter ? fieldFn(L, "onEnter") : 0;
	screen->setHandlers(widget, onClick, onChange, onEnter, box.color);
	pushUiHandle(L, TYPE_UI_WIDGET, screen->getId(), widget);
	return 1;
}

int uiWindow(lua_State *L)
{
	auto *screen = checkBuilding(L);
	checkFields(L, " x y w h background ");
	const Box box = fieldBox(L);
	const char *background = fieldText(L, "background");
	if (*background && !screen->hasSurface(background))
	{
		return luaL_error(L, "no picture '%s' in the game or in the mod's extraSprites", background);
	}
	return finishWidget(L, screen, screen->addWindow(box.x, box.y, box.w, box.h, background), { 0, 0, 0, 0, -1 }, false, false, false);
}

int uiText(lua_State *L)
{
	auto *screen = checkBuilding(L);
	checkFields(L, " x y w h text big align wrap color ");
	const Box box = fieldBox(L);
	const int align = alignOf(L);
	return finishWidget(L, screen, screen->addText(box.x, box.y, box.w, box.h, fieldText(L, "text"), fieldBool(L, "big"), align, fieldBool(L, "wrap")), box, false, false, false);
}

int uiButton(lua_State *L)
{
	auto *screen = checkBuilding(L);
	checkFields(L, " x y w h text color onClick ");
	const Box box = fieldBox(L);
	checkFnField(L, "onClick");
	return finishWidget(L, screen, screen->addButton(box.x, box.y, box.w, box.h, fieldText(L, "text")), box, true, false, false);
}

int uiToggleButton(lua_State *L)
{
	auto *screen = checkBuilding(L);
	checkFields(L, " x y w h text pressed color onClick ");
	const Box box = fieldBox(L);
	checkFnField(L, "onClick");
	return finishWidget(L, screen, screen->addToggle(box.x, box.y, box.w, box.h, fieldText(L, "text"), fieldBool(L, "pressed")), box, true, false, false);
}

void checkNeedsWindow(lua_State *L, const LuaScreenState *screen)
{
	if (!screen->hasWindow())
	{
		luaL_error(L, "this widget takes its background from a window: make ui:window first");
	}
}

int uiList(lua_State *L)
{
	auto *screen = checkBuilding(L);
	checkFields(L, " x y w h columns selectable color onClick ");
	const Box box = fieldBox(L);
	checkFnField(L, "onClick");
	checkNeedsWindow(L, screen);
	lua_pushstring(L, "columns");
	lua_rawget(L, 2);
	luaL_argcheck(L, lua_istable(L, -1), 2, "field 'columns' must be a list of widths");
	const size_t count = lua_rawlen(L, -1);
	luaL_argcheck(L, count >= 1 && count <= LuaScreenState::MAX_COLUMNS, 2, "field 'columns' must have from 1 to 8 widths");
	int widths[LuaScreenState::MAX_COLUMNS] = { };
	for (size_t i = 0; i < count; ++i)
	{
		lua_rawgeti(L, -1, (lua_Integer)i + 1);
		int isInteger = 0;
		const lua_Integer width = lua_tointegerx(L, -1, &isInteger);
		luaL_argcheck(L, isInteger && width >= 1 && width <= 320, 2, "a width of 'columns' must be a whole number from 1 to 320");
		widths[i] = (int)width;
		lua_pop(L, 1);
	}
	lua_pop(L, 1);
	const bool selectable = fieldBool(L, "selectable");
	return finishWidget(L, screen, screen->addList(box.x, box.y, box.w, box.h, std::vector<int>(widths, widths + count), selectable), box, true, false, false);
}

/// The strings of a list at `index`: they stay alive as long as the list does, and it is the caller's argument.
std::vector<std::string> checkOptions(lua_State *L, int index)
{
	std::vector<const char*> checked;
	const size_t count = lua_rawlen(L, index);
	luaL_argcheck(L, count >= 1 && count <= LuaScreenState::MAX_OPTIONS, index, "must have from 1 to 256 options");
	for (size_t i = 0; i < count; ++i)
	{
		lua_rawgeti(L, index, (lua_Integer)i + 1);
		size_t len = 0;
		const char *option = lua_type(L, -1) == LUA_TSTRING ? lua_tolstring(L, -1, &len) : nullptr;
		luaL_argcheck(L, option && len <= UI_TEXT_MAX && Unicode::isValidUTF8(option), index, "an option must be a string of UTF-8");
		checked.push_back(option);
		lua_pop(L, 1);
	}
	return std::vector<std::string>(checked.begin(), checked.end());
}

int uiComboBox(lua_State *L)
{
	auto *screen = checkBuilding(L);
	checkFields(L, " x y w h options selected color onChange ");
	const Box box = fieldBox(L);
	checkFnField(L, "onChange");
	checkNeedsWindow(L, screen);
	lua_pushstring(L, "options");
	lua_rawget(L, 2);
	luaL_argcheck(L, lua_istable(L, -1), 2, "field 'options' must be a list of strings");
	const int options = lua_gettop(L);
	const auto list = checkOptions(L, options);
	const int selected = fieldInt(L, "selected", 1, (int)list.size(), 1, false);
	return finishWidget(L, screen, screen->addCombo(box.x, box.y, box.w, box.h, list, selected - 1), box, false, true, false);
}

int uiEdit(lua_State *L)
{
	auto *screen = checkBuilding(L);
	checkFields(L, " x y w h text focus color onChange onEnter ");
	const Box box = fieldBox(L);
	checkFnField(L, "onChange");
	checkFnField(L, "onEnter");
	return finishWidget(L, screen, screen->addEdit(box.x, box.y, box.w, box.h, fieldText(L, "text"), fieldBool(L, "focus")), box, false, true, true);
}

int uiSlider(lua_State *L)
{
	auto *screen = checkBuilding(L);
	checkFields(L, " x y w h min max value color onChange ");
	const Box box = fieldBox(L);
	checkFnField(L, "onChange");
	const int low = fieldInt(L, "min", -1000000000, 1000000000, 0, true);
	const int high = fieldInt(L, "max", -1000000000, 1000000000, 0, true);
	luaL_argcheck(L, low < high, 2, "field 'min' must be below 'max'");
	const int value = fieldInt(L, "value", low, high, low, false);
	return finishWidget(L, screen, screen->addSlider(box.x, box.y, box.w, box.h, low, high, value), box, false, true, false);
}

int uiImage(lua_State *L)
{
	auto *screen = checkBuilding(L);
	checkFields(L, " x y image onClick ");
	const Box box = fieldBox(L, false);
	checkFnField(L, "onClick");
	const char *image = fieldText(L, "image");
	if (!*image || !screen->hasSurface(image))
	{
		return luaL_error(L, "no picture '%s' in the game or in the mod's extraSprites", image);
	}
	return finishWidget(L, screen, screen->addImage(box.x, box.y, image), box, true, false, false);
}

int uiOnKey(lua_State *L)
{
	auto *screen = checkUi(L);
	luaL_checktype(L, 2, LUA_TFUNCTION);
	screen->setScreenHandlers(LuaSandbox::keep(L, 2), 0);
	return 0;
}

int uiOnClose(lua_State *L)
{
	auto *screen = checkUi(L);
	luaL_checktype(L, 2, LUA_TFUNCTION);
	screen->setScreenHandlers(0, LuaSandbox::keep(L, 2));
	return 0;
}

int uiClose(lua_State *L)
{
	auto *screen = checkUi(L);
	if (screen->isBuilding())
	{
		return luaL_error(L, "a screen being built cannot close: raise an error to not open it");
	}
	if (!screen->isOnTop())
	{
		return luaL_error(L, "only the screen on top can close");
	}
	screen->askClose();
	return 0;
}

const luaL_Reg UI_METHODS[] = {
	{ "window", uiWindow },
	{ "text", uiText },
	{ "button", uiButton },
	{ "toggleButton", uiToggleButton },
	{ "list", uiList },
	{ "comboBox", uiComboBox },
	{ "edit", uiEdit },
	{ "slider", uiSlider },
	{ "image", uiImage },
	{ "onKey", uiOnKey },
	{ "onClose", uiOnClose },
	{ "close", uiClose },
	{ nullptr, nullptr }
};

#define UI_KIND(kind) (1u << LuaScreenState::kind)

int widgetSetVisible(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, ~0u, "");
	screen->setVisible(widget, lua_toboolean(L, 2));
	return 0;
}

int widgetIsVisible(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, ~0u, "");
	lua_pushboolean(L, screen->isVisible(widget));
	return 1;
}

int widgetSetText(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(TEXT) | UI_KIND(BUTTON) | UI_KIND(TOGGLE) | UI_KIND(EDIT), "setText works on text, button, toggleButton and edit");
	LuaSandbox::from(L)->charge(L, MESSAGE_TICKS);
	screen->setText(widget, checkUiText(L, 2));
	return 0;
}

int widgetGetText(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(TEXT) | UI_KIND(EDIT), "getText works on text and edit");
	const std::string text = screen->getText(widget);
	lua_pushlstring(L, text.data(), text.size());
	return 1;
}

int widgetSetPressed(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(TOGGLE), "setPressed works on toggleButton");
	screen->setPressed(widget, lua_toboolean(L, 2));
	return 0;
}

int widgetIsPressed(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(TOGGLE), "isPressed works on toggleButton");
	lua_pushboolean(L, screen->isPressed(widget));
	return 1;
}

int widgetAddRow(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(LIST), "addRow works on list");
	const int cells = lua_gettop(L) - 1;
	luaL_argcheck(L, cells >= 1 && (size_t)cells <= screen->getColumns(widget), 2, "more cells than the list has columns, or none");
	if (screen->getScreenRows() >= LuaScreenState::MAX_ROWS)
	{
		return luaL_error(L, "more than %d rows on one screen", (int)LuaScreenState::MAX_ROWS);
	}
	LuaSandbox::from(L)->charge(L, ROW_TICKS);
	const char *texts[LuaScreenState::MAX_COLUMNS] = { };
	for (int i = 0; i < cells; ++i)
	{
		texts[i] = checkUiText(L, i + 2);
	}
	screen->addRow(widget, std::vector<std::string>(texts, texts + cells));
	return 0;
}

int widgetClearList(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(LIST), "clearList works on list");
	LuaSandbox::from(L)->charge(L, MESSAGE_TICKS);
	screen->clearList(widget);
	return 0;
}

int widgetSetCell(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(LIST), "setCell works on list");
	const int row = checkInt(L, 2), column = checkInt(L, 3);
	luaL_argcheck(L, row >= 1 && (size_t)row <= screen->getRows(widget), 2, "no such row");
	luaL_argcheck(L, column >= 1 && (size_t)column <= screen->getColumns(widget), 3, "no such column");
	LuaSandbox::from(L)->charge(L, ROW_TICKS);
	screen->setCell(widget, (size_t)row - 1, (size_t)column - 1, checkUiText(L, 4));
	return 0;
}

int widgetGetRowCount(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(LIST), "getRowCount works on list");
	lua_pushinteger(L, (lua_Integer)screen->getRows(widget));
	return 1;
}

int widgetGetSelected(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(LIST) | UI_KIND(COMBO), "getSelected works on list and comboBox");
	lua_pushinteger(L, screen->getSelected(widget) + 1);
	return 1;
}

int widgetSetSelected(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(COMBO), "setSelected works on comboBox");
	const int selected = checkInt(L, 2);
	luaL_argcheck(L, selected >= 1 && (size_t)selected <= screen->getOptions(widget), 2, "no such option");
	screen->setSelected(widget, selected - 1);
	return 0;
}

int widgetSetOptions(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(COMBO), "setOptions works on comboBox");
	luaL_checktype(L, 2, LUA_TTABLE);
	LuaSandbox::from(L)->charge(L, MESSAGE_TICKS);
	screen->setOptions(widget, checkOptions(L, 2));
	return 0;
}

int widgetGetValue(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(SLIDER), "getValue works on slider");
	lua_pushinteger(L, screen->getValue(widget));
	return 1;
}

int widgetSetValue(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(SLIDER), "setValue works on slider");
	screen->setValue(widget, checkInt(L, 2));
	return 0;
}

int widgetSetRange(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(SLIDER), "setRange works on slider");
	const int low = checkInt(L, 2), high = checkInt(L, 3);
	luaL_argcheck(L, low >= -1000000000 && low < high && high <= 1000000000, 2, "the range must go up, within a billion each way");
	screen->setRange(widget, low, high);
	return 0;
}

int widgetSetFocus(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(EDIT), "setFocus works on edit");
	screen->setFocus(widget);
	return 0;
}

int widgetSetImage(lua_State *L)
{
	int widget;
	auto *screen = checkWidget(L, widget, UI_KIND(IMAGE), "setImage works on image");
	const char *image = checkUiText(L, 2);
	if (!screen->hasSurface(image))
	{
		return luaL_error(L, "no picture '%s' in the game or in the mod's extraSprites", image);
	}
	LuaSandbox::from(L)->charge(L, MESSAGE_TICKS);
	screen->setImage(widget, image);
	return 0;
}

const luaL_Reg UI_WIDGET_METHODS[] = {
	{ "setVisible", widgetSetVisible },
	{ "isVisible", widgetIsVisible },
	{ "setText", widgetSetText },
	{ "getText", widgetGetText },
	{ "setPressed", widgetSetPressed },
	{ "isPressed", widgetIsPressed },
	{ "addRow", widgetAddRow },
	{ "clearList", widgetClearList },
	{ "setCell", widgetSetCell },
	{ "getRowCount", widgetGetRowCount },
	{ "getSelected", widgetGetSelected },
	{ "setSelected", widgetSetSelected },
	{ "setOptions", widgetSetOptions },
	{ "getValue", widgetGetValue },
	{ "setValue", widgetSetValue },
	{ "setRange", widgetSetRange },
	{ "setFocus", widgetSetFocus },
	{ "setImage", widgetSetImage },
	{ nullptr, nullptr }
};

/// game.screen(name, fn[, { menu = "STR_NAME", interface = "pauseMenu" }]), only in main.lua.
int gameScreen(lua_State *L)
{
	auto *host = LuaHost::active();
	auto *sandbox = LuaSandbox::from(L);
	if (!host || !host->hasCap(sandbox, LuaHost::CAP_SCREENS))
	{
		return luaL_error(L, "game.screen needs 'screens' in luaCaps of metadata.yml");
	}
	if (!sandbox->isLoading())
	{
		return luaL_error(L, "game.screen works only while main.lua runs");
	}
	const char *name = checkUiText(L, 1);
	luaL_checktype(L, 2, LUA_TFUNCTION);
	lua_settop(L, 3);
	const char *menu = "", *category = "pauseMenu";
	int function = 2;
	if (!lua_isnil(L, 3))
	{
		luaL_checktype(L, 3, LUA_TTABLE);
		// the helpers read the fields from the second place
		lua_rotate(L, 2, 1);
		function = 3;
		checkFields(L, " menu interface ");
		menu = fieldText(L, "menu");
		const char *given = fieldText(L, "interface");
		if (*given)
		{
			category = given;
		}
	}
	const int fn = LuaSandbox::keep(L, function);
	const std::string error = host->declareScreen(sandbox, name, fn, menu, category);
	if (!error.empty())
	{
		sandbox->drop(fn);
		return luaL_error(L, "%s", error.c_str());
	}
	return 0;
}

/// game.openScreen(name): later, from the moment nothing walks the game's lists.
int gameOpenScreen(lua_State *L)
{
	checkWritable(L);
	checkMayQueue(L);
	auto *host = LuaHost::active();
	auto *sandbox = LuaSandbox::from(L);
	if (!host || !host->hasCap(sandbox, LuaHost::CAP_SCREENS))
	{
		return luaL_error(L, "game.openScreen needs 'screens' in luaCaps of metadata.yml");
	}
	if (sandbox->isLoading())
	{
		return luaL_error(L, "game.openScreen works in handlers, main.lua runs before there is a game");
	}
	const std::string error = host->queueScreen(sandbox, checkUiText(L, 1));
	if (!error.empty())
	{
		return luaL_error(L, "%s", error.c_str());
	}
	return 0;
}

int gameGetBattle(lua_State *L)
{
	auto *saved = LuaScreenState::savedGame();
	pushOrNil(L, TYPE_BATTLE, saved ? saved->getSavedBattle() : nullptr);
	return 1;
}

int gameGetGeoscape(lua_State *L)
{
	pushOrNil(L, TYPE_GEOSCAPE, LuaScreenState::savedGame());
	return 1;
}

int gameGetBases(lua_State *L)
{
	auto *saved = LuaScreenState::savedGame();
	if (!saved)
	{
		lua_pushnil(L);
		return 1;
	}
	return pushList(L, TYPE_BASE, *saved->getBases(), [](Base*) { return true; });
}

const luaL_Reg API2_GAME_REGS[] = {
	{ "screen", gameScreen },
	{ "openScreen", gameOpenScreen },
	{ "getBattle", gameGetBattle },
	{ "getGeoscape", gameGetGeoscape },
	{ "getBases", gameGetBases },
	{ nullptr, nullptr }
};

/// spawn is under construction: on top of the table the mod's page is built from, so not on that page.
const luaL_Reg API2_BATTLE_REGS[] = {
	{ "spawnItem", battleSpawnItem },
	{ "removeItem", battleRemoveItem },
	{ "spawnUnit", battleSpawnUnit },
	{ "getMapSets", battleGetMapSets },
	{ nullptr, nullptr }
};

const luaL_Reg API2_TILE_REGS[] = {
	{ "getPart", tileGetPart },
	{ "setPart", tileSetPart },
	{ "clearPart", tileClearPart },
	{ "destroyPart", tileDestroyPart },
	{ "setFire", tileSetFire },
	{ "setSmoke", tileSetSmoke },
	{ nullptr, nullptr }
};

const luaL_Reg API2_UNIT_REGS[] = {
	{ "giveItem", unitGiveItem },
	{ nullptr, nullptr }
};

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

int geoscapeRandomRange(lua_State *L)
{
	self<SavedGame>(L);
	checkRandomAllowed(L);
	const int low = checkInt(L, 2), high = checkInt(L, 3);
	luaL_argcheck(L, high >= low, 3, "the upper bound is below the lower one");
	lua_pushinteger(L, RNG::generate(low, high));
	return 1;
}

int geoscapeRandomRangeSymmetric(lua_State *L)
{
	self<SavedGame>(L);
	checkRandomAllowed(L);
	const int max = checkInt(L, 2);
	luaL_argcheck(L, max >= 0 && max < INT_MAX, 2, "must not be negative");
	lua_pushinteger(L, RNG::generate(-max, max));
	return 1;
}

int geoscapeRandomChance(lua_State *L)
{
	self<SavedGame>(L);
	checkRandomAllowed(L);
	lua_pushboolean(L, RNG::percent(checkInt(L, 2)));
	return 1;
}

const luaL_Reg GEOSCAPE_METHODS[] = {
	{ "getTime", geoscapeGetTime },
	{ "difficultyLevel", geoscapeDifficultyLevel },
	{ "getMonthsPassed", getInt<&SavedGame::getMonthsPassed> },
	{ "getDaysPassed", getInt<&SavedGame::getDaysPassed> },
	{ "getCountries", geoscapeGetCountries },
	{ "isResearched", geoscapeIsResearched },
	{ "randomRange", geoscapeRandomRange },
	{ "randomRangeSymmetric", geoscapeRandomRangeSymmetric },
	{ "randomChance", geoscapeRandomChance },
	{ "getTag", getTagOf<SavedGame> },
	{ "setTag", setTagOf<SavedGame> },
	{ nullptr, nullptr }
};

int geoscapeGetFunds(lua_State *L)
{
	lua_pushinteger(L, self<SavedGame>(L)->getFunds());
	return 1;
}

/// geoscape:addFunds(n): what setFunds does for a purchase, the income and the spending of the month count themselves.
int geoscapeAddFunds(lua_State *L)
{
	auto *saved = self<SavedGame>(L);
	checkEconomy(L, "addFunds");
	const lua_Integer n = luaL_checkinteger(L, 2);
	luaL_argcheck(L, n >= -ECONOMY_MAX && n <= ECONOMY_MAX, 2, "must be from -1000000000 to 1000000000");
	if (n != 0)
	{
		const int64_t funds = saved->getFunds(), income = saved->getIncomes().back(), spent = saved->getExpenditures().back();
		saved->setFunds(funds + n);
		LuaHost::active()->noteEconomy([=]()
		{
			saved->getFundsList().back() = funds;
			saved->getIncomes().back() = income;
			saved->getExpenditures().back() = spent;
		});
	}
	return 0;
}

/// On top of the table the mod's page is built from, like API2_BATTLE_REGS: a mod of API 1 does not have them.
const luaL_Reg API2_GEOSCAPE_REGS[] = {
	{ "getFunds", geoscapeGetFunds },
	{ "addFunds", geoscapeAddFunds },
	{ nullptr, nullptr }
};

int checkCount(lua_State *L, int index)
{
	const lua_Integer n = luaL_optinteger(L, index, 1);
	luaL_argcheck(L, n >= 1 && n <= ECONOMY_MAX, index, "must be from 1 to 1000000000");
	return (int)n;
}

const RuleItem *checkItemRule(lua_State *L, int index)
{
	const char *type = luaL_checkstring(L, index);
	const RuleItem *rule = gameMod(L)->getItem(type);
	if (!rule)
	{
		luaL_error(L, "no item '%s' in the rules", type);
	}
	return rule;
}

int baseGetName(lua_State *L)
{
	lua_pushstring(L, self<Base>(L)->getName().c_str());
	return 1;
}

void pushCapacity(lua_State *L, int capacity)
{
	lua_pushinteger(L, capacity);
	lua_setfield(L, -2, "capacity");
}

int baseGetStores(lua_State *L)
{
	const auto *base = self<Base>(L);
	lua_createtable(L, 0, 2);
	lua_pushnumber(L, base->getUsedStores());
	lua_setfield(L, -2, "used");
	pushCapacity(L, base->getAvailableStores());
	return 1;
}

int baseGetQuarters(lua_State *L)
{
	const auto *base = self<Base>(L);
	lua_createtable(L, 0, 2);
	lua_pushinteger(L, base->getUsedQuarters());
	lua_setfield(L, -2, "used");
	pushCapacity(L, base->getAvailableQuarters());
	return 1;
}

int baseGetItemCount(lua_State *L)
{
	const auto *base = self<Base>(L);
	lua_pushinteger(L, base->getStorageItems()->getItem(checkItemRule(L, 2)));
	return 1;
}

int baseAddItem(lua_State *L)
{
	auto *base = self<Base>(L);
	checkEconomy(L, "addItem");
	const RuleItem *rule = checkItemRule(L, 2);
	const int n = checkCount(L, 3), have = base->getStorageItems()->getItem(rule);
	if (have > INT_MAX - n)
	{
		return luaL_error(L, "addItem: %d more of '%s' do not fit a number of the stores, there are %d", n, rule->getType().c_str(), have);
	}
	base->getStorageItems()->addItem(rule, n);
	LuaHost::active()->noteEconomy([=]() { base->getStorageItems()->removeItem(rule, n); });
	return 0;
}

int baseRemoveItem(lua_State *L)
{
	auto *base = self<Base>(L);
	checkEconomy(L, "removeItem");
	const RuleItem *rule = checkItemRule(L, 2);
	const int n = checkCount(L, 3), have = base->getStorageItems()->getItem(rule);
	if (have < n)
	{
		return luaL_error(L, "removeItem: %d of '%s' asked, the stores have %d", n, rule->getType().c_str(), have);
	}
	base->getStorageItems()->removeItem(rule, n);
	LuaHost::active()->noteEconomy([=]() { base->getStorageItems()->addItem(rule, n); });
	return 0;
}

/// getScientists and getEngineers count only those without work: the busy ones cannot be taken.
int changeStaff(lua_State *L, const char *method, int (Base::*get)() const, void (Base::*set)(int), bool add)
{
	auto *base = self<Base>(L);
	checkEconomy(L, method);
	const int n = checkCount(L, 2), have = (base->*get)();
	if (add ? have > INT_MAX - n : have < n)
	{
		return luaL_error(L, add ? "%s: %d more do not fit a number, there are %d" : "%s: %d asked, %d are without work", method, n, have);
	}
	(base->*set)(add ? have + n : have - n);
	LuaHost::active()->noteEconomy([=]() { (base->*set)(have); });
	return 0;
}

int baseAddScientists(lua_State *L) { return changeStaff(L, "addScientists", &Base::getScientists, &Base::setScientists, true); }
int baseRemoveScientists(lua_State *L) { return changeStaff(L, "removeScientists", &Base::getScientists, &Base::setScientists, false); }
int baseAddEngineers(lua_State *L) { return changeStaff(L, "addEngineers", &Base::getEngineers, &Base::setEngineers, true); }
int baseRemoveEngineers(lua_State *L) { return changeStaff(L, "removeEngineers", &Base::getEngineers, &Base::setEngineers, false); }

/// base:hireSoldier(type[, done]): done(soldier) or done(nil, reason) runs later, when the soldier is on the way.
int baseHireSoldier(lua_State *L)
{
	auto *base = self<Base>(L);
	checkEconomy(L, "hireSoldier");
	const char *type = luaL_checkstring(L, 2);
	const RuleSoldier *rule = gameMod(L)->getSoldier(type);
	if (!rule)
	{
		return luaL_error(L, "no soldier '%s' in the rules", type);
	}
	if (!lua_isnoneornil(L, 3))
	{
		luaL_checktype(L, 3, LUA_TFUNCTION);
	}
	auto *sandbox = LuaSandbox::from(L);
	const int done = lua_isnoneornil(L, 3) ? 0 : LuaSandbox::keep(L, 3);
	const std::string error = LuaHost::active()->queueHire(sandbox, base, rule, done);
	if (!error.empty())
	{
		if (done)
		{
			sandbox->drop(done);
		}
		return luaL_error(L, "%s", error.c_str());
	}
	return 0;
}

const luaL_Reg BASE_METHODS[] = {
	{ "getName", baseGetName },
	{ "getStores", baseGetStores },
	{ "getQuarters", baseGetQuarters },
	{ "getItemCount", baseGetItemCount },
	{ "addItem", baseAddItem },
	{ "removeItem", baseRemoveItem },
	{ "getFreeScientists", getInt<&Base::getAvailableScientists> },
	{ "addScientists", baseAddScientists },
	{ "removeScientists", baseRemoveScientists },
	{ "getFreeEngineers", getInt<&Base::getAvailableEngineers> },
	{ "addEngineers", baseAddEngineers },
	{ "removeEngineers", baseRemoveEngineers },
	{ "hireSoldier", baseHireSoldier },
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
const luaL_Reg RULE_COUNTRY_METHODS[] = {
	{ "getType", getString<&RuleCountry::getType> },
	{ "getFundingCap", getInt<&RuleCountry::getFundingCap> },
	{ "getTag", getTagOf<RuleCountry> },
	{ nullptr, nullptr }
};
const luaL_Reg RULE_UFO_METHODS[] = {
	{ "getType", getString<&RuleUfo::getType> },
	{ "getRadius", getInt<&RuleUfo::getRadius> },
	{ "getWeaponRange", getInt<&RuleUfo::getWeaponRange> },
	{ "getWeaponPower", getInt<&RuleUfo::getWeaponPower> },
	{ "getWeaponReload", getInt<&RuleUfo::getWeaponReload> },
	{ "getTag", getTagOf<RuleUfo> },
	{ nullptr, nullptr }
};
const luaL_Reg RULE_CRAFT_METHODS[] = {
	{ "getType", getString<&RuleCraft::getType> },
	{ "getWeaponsMax", getInt<&RuleCraft::getWeapons> },
	{ "getSoldiersMax", getInt<&RuleCraft::getMaxUnits> },
	{ "getVehiclesMax", getInt<&RuleCraft::getMaxVehiclesAndLargeSoldiers> },
	{ "getPilotsMax", getInt<&RuleCraft::getPilots> },
	{ "getTag", getTagOf<RuleCraft> },
	{ nullptr, nullptr }
};
const luaL_Reg RULE_RESEARCH_METHODS[] = {
	{ "getType", getString<&RuleResearch::getName> },
	{ "getCost", getInt<&RuleResearch::getCost> },
	{ "getPoints", getInt<&RuleResearch::getPoints> },
	{ "getLookup", getObject<&RuleResearch::getLookup> },
	{ "getNeededItem", getObject<&RuleResearch::getNeededItem> },
	{ "getTag", getTagOf<RuleResearch> },
	{ nullptr, nullptr }
};

int inventoryGetMoveToCost(lua_State *L)
{
	const auto *inventory = self<RuleInventory>(L);
	const auto *other = static_cast<RuleInventory*>(LuaSandbox::checkObject(L, 2, TYPE_RULE_INVENTORY));
	lua_pushinteger(L, inventory->getCost(other));
	return 1;
}

const luaL_Reg RULE_INVENTORY_METHODS[] = {
	{ "getId", getString<&RuleInventory::getId> },
	{ "getType", getInt<&RuleInventory::getType> },
	{ "isRightHand", getBool<&RuleInventory::isRightHand> },
	{ "isLeftHand", getBool<&RuleInventory::isLeftHand> },
	{ "getMoveToCost", inventoryGetMoveToCost },
	{ nullptr, nullptr }
};

/// By name, as the script's rules.getRuleItem: a rule that is not there is nil, a mod may look for another mod's rule.
template<typename T, T *(Mod::*Find)(const std::string &, bool) const>
int rulesFind(lua_State *L)
{
	LuaSandbox::from(L)->charge(L, TAG_TICKS);
	const auto *mod = self<Mod>(L);
	size_t len = 0;
	const char *name = luaL_checklstring(L, 2, &len);
	luaL_argcheck(L, len <= MESSAGE_MAX, 2, "too long");
	pushOrNil(L, LuaType<T>::name(), (mod->*Find)(name, false));
	return 1;
}

/// The Mod's own getters of these slots throw when the slot is missing, and an exception must not cross Lua.
const char *const SLOT_NAMES[] = { "STR_RIGHT_HAND", "STR_LEFT_HAND", "STR_BACK_PACK", "STR_BELT", "STR_GROUND" };

template<int Slot>
int rulesSlot(lua_State *L)
{
	pushOrNil(L, TYPE_RULE_INVENTORY, self<Mod>(L)->getInventory(SLOT_NAMES[Slot], false));
	return 1;
}

/// The formula of the script's rules.getSmokeReduction.
int rulesGetSmokeReduction(lua_State *L)
{
	const auto *mod = self<Mod>(L);
	lua_pushinteger(L, (lua_Integer)checkInt(L, 2) * mod->getMaxViewDistance() / (3 * 20));
	return 1;
}

const luaL_Reg RULES_METHODS[] = {
	{ "getRuleUnit", rulesFind<Unit, &Mod::getUnit> },
	{ "getRuleItem", rulesFind<RuleItem, &Mod::getItem> },
	{ "getRuleArmor", rulesFind<Armor, &Mod::getArmor> },
	{ "getRuleSkill", rulesFind<RuleSkill, &Mod::getSkill> },
	{ "getRuleResearch", rulesFind<RuleResearch, &Mod::getResearch> },
	{ "getRuleSoldier", rulesFind<RuleSoldier, &Mod::getSoldier> },
	{ "getRuleInventory", rulesFind<RuleInventory, &Mod::getInventory> },
	{ "getRuleInventoryRightHand", rulesSlot<0> },
	{ "getRuleInventoryLeftHand", rulesSlot<1> },
	{ "getRuleInventoryBackpack", rulesSlot<2> },
	{ "getRuleInventoryBelt", rulesSlot<3> },
	{ "getRuleInventoryGround", rulesSlot<4> },
	{ "getMaxDarknessToSeeUnits", getInt<&Mod::getMaxDarknessToSeeUnits> },
	{ "getMaxViewDistance", getInt<&Mod::getMaxViewDistance> },
	{ "getSmokeReduction", rulesGetSmokeReduction },
	{ nullptr, nullptr }
};

int gameGetRules(lua_State *L)
{
	LuaSandbox::pushObject(L, TYPE_RULES, const_cast<Mod*>(gameMod(L)));
	return 1;
}

std::string nerdsText(lua_State *L, int index)
{
	size_t len = 0;
	const char *text = luaL_checklstring(L, index, &len);
	luaL_argcheck(L, len <= MESSAGE_MAX, index, "too long");
	return text;
}

int nerdsAddIntRow(lua_State *L)
{
	self<StatsForNerdsState>(L)->addIntegerScript(nerdsText(L, 2), checkInt(L, 3));
	return 0;
}

int nerdsAddTextRow(lua_State *L)
{
	self<StatsForNerdsState>(L)->addTextScript(nerdsText(L, 2), nerdsText(L, 3));
	return 0;
}

int nerdsAddTextFormatRow(lua_State *L)
{
	auto *nerds = self<StatsForNerdsState>(L);
	const std::string name = nerdsText(L, 2), format = nerdsText(L, 3);
	if (lua_isnoneornil(L, 5))
	{
		nerds->addTextFormat1Script(name, format, checkInt(L, 4));
	}
	else
	{
		nerds->addTextFormat2Script(name, format, checkInt(L, 4), checkInt(L, 5));
	}
	return 0;
}

const luaL_Reg NERDS_METHODS[] = {
	{ "addIntRow", nerdsAddIntRow },
	{ "addTextRow", nerdsAddTextRow },
	{ "addTextFormatRow", nerdsAddTextFormatRow },
	{ nullptr, nullptr }
};

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
	{ "PART_FLOOR", O_FLOOR }, { "PART_WEST", O_WESTWALL }, { "PART_NORTH", O_NORTHWALL }, { "PART_OBJECT", O_OBJECT },
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
	{ "INV_SLOT", INV_SLOT }, { "INV_HAND", INV_HAND }, { "INV_GROUND", INV_GROUND },
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
	LuaSandbox::defineType(L, TYPE_RULES, RULES_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_RESEARCH, RULE_RESEARCH_METHODS);
	LuaSandbox::defineType(L, TYPE_RULE_INVENTORY, RULE_INVENTORY_METHODS);
	LuaSandbox::defineType(L, TYPE_NERDS, NERDS_METHODS);
	lua_pushlightuserdata(L, mod);
	lua_setfield(L, LUA_REGISTRYINDEX, MOD_KEY);
	lua_getglobal(L, "game");
	lua_pushcfunction(L, gameGetRules);
	lua_setfield(L, -2, "getRules");
	for (const auto &constant : CONSTANTS)
	{
		lua_pushinteger(L, constant.value);
		lua_setfield(L, -2, constant.name);
	}
	lua_pop(L, 1);
}

void setupApi2(lua_State *L, void *)
{
	luaL_getmetatable(L, TYPE_BATTLE);
	lua_getfield(L, -1, "__index");
	luaL_setfuncs(L, API2_BATTLE_REGS, 0);
	lua_pop(L, 2);
	luaL_getmetatable(L, TYPE_UNIT);
	lua_getfield(L, -1, "__index");
	luaL_setfuncs(L, API2_UNIT_REGS, 0);
	lua_pop(L, 2);
	luaL_getmetatable(L, TYPE_TILE);
	lua_getfield(L, -1, "__index");
	luaL_setfuncs(L, API2_TILE_REGS, 0);
	lua_pop(L, 2);
	luaL_getmetatable(L, TYPE_GEOSCAPE);
	lua_getfield(L, -1, "__index");
	luaL_setfuncs(L, API2_GEOSCAPE_REGS, 0);
	lua_pop(L, 2);
	LuaSandbox::defineType(L, TYPE_UI, UI_METHODS);
	LuaSandbox::defineType(L, TYPE_UI_WIDGET, UI_WIDGET_METHODS);
	LuaSandbox::defineType(L, TYPE_BASE, BASE_METHODS);
	lua_getglobal(L, "game");
	luaL_setfuncs(L, API2_GAME_REGS, 0);
	lua_pop(L, 1);
}

int pushDone(lua_State *L, void *item)
{
	pushOrNil(L, TYPE_ITEM, item);
	return 1;
}

int capOf(const std::string &word)
{
	return word == "spawn" ? LuaHost::CAP_SPAWN : word == "screens" ? LuaHost::CAP_SCREENS : word == "economy" ? LuaHost::CAP_ECONOMY : word == "map" ? LuaHost::CAP_MAP : 0;
}

/// What a method of 'spawn' or 'map' comes to: `done(object)`, `done(true)` for an item taken away, or `done(nil, reason)`.
struct SpawnDone
{
	bool ran = false, removed = false;
	BattleItem *item = nullptr;
	BattleUnit *unit = nullptr;
	Tile *tile = nullptr;
	const char *reason = nullptr;
};

int pushSpawnDone(lua_State *L, void *data)
{
	auto *done = static_cast<SpawnDone*>(data);
	if (done->item)
	{
		pushOrNil(L, TYPE_ITEM, done->item);
		return 1;
	}
	if (done->unit)
	{
		pushOrNil(L, TYPE_UNIT, done->unit);
		return 1;
	}
	if (done->tile)
	{
		pushOrNil(L, TYPE_TILE, done->tile);
		return 1;
	}
	if (done->removed)
	{
		lua_pushboolean(L, 1);
		return 1;
	}
	lua_pushnil(L);
	lua_pushstring(L, done->reason);
	return 2;
}

/// Takes an item out of the battle; why not, or null. What the engine would leave half done is refused or undone first.
/// What a method of 'map' does to the tile, without gravity, light and sight: they run once for the whole moment (R-302).
/// Null, or why not.
const char *changeTile(SavedBattleGame *battle, Tile *tile, LuaHost::MapOp op, TilePart part, int id, int set, int value)
{
	// _baseModules counts the map and the end of a base defense reads it
	if (battle->getMissionType() == "STR_BASE_DEFENSE")
	{
		return "not in a base defense";
	}
	if (op == LuaHost::MAP_SMOKE)
	{
		tile->setSmoke(value);
		return nullptr;
	}
	if (op == LuaHost::MAP_FIRE)
	{
		if (value && !tile->getMapData(O_FLOOR) && !tile->getMapData(O_OBJECT))
		{
			return "nothing to burn on the tile";
		}
		tile->setFire(value);
		// Map draws fire only with smoke, and its density is what burns a unit: the way of an explosion
		if (value && !tile->getSmoke())
		{
			tile->setSmoke(Clamp(15 - (tile->getFlammability() / 10), 1, 12));
		}
		return nullptr;
	}
	const MapData *old = tile->getMapData(part);
	if (!old && op != LuaHost::MAP_SET)
	{
		return "the part is empty";
	}
	if (old && old->isGravLift())
	{
		return "a lift stays";
	}
	if (old && op != LuaHost::MAP_DESTROY && old->getSpecialType() == battle->getObjectiveType())
	{
		return "the mission counts this part, only destroyPart may take it";
	}
	if (op == LuaHost::MAP_SET)
	{
		MapData *data = (*battle->getMapDataSets())[set]->getObject(id);
		if (data->getSpecialType() == battle->getObjectiveType())
		{
			return "the mission would not count this part";
		}
		if (part == O_FLOOR && tile->getPosition().z == 0 && data->isNoFloor())
		{
			return "the lowest level needs a floor";
		}
		const BattleUnit *unit = tile->getUnit();
		if (unit && (part == O_FLOOR || part == O_OBJECT) && (data->getBigWall() != 0 || data->getTUCost(unit->getMovementType()) == 255))
		{
			return "occupied";
		}
		tile->setMapData(data, id, set, part);
		// its frame was the frame of the old part: a UFO door would stand half open, the rest of the frames are one picture
		if (data->isUFODoor())
		{
			tile->closeUfoDoor();
		}
		return nullptr;
	}
	if (op == LuaHost::MAP_DESTROY)
	{
		if (tile->destroy(part, battle->getObjectiveType()))
		{
			battle->addDestroyedObjective();
		}
	}
	else
	{
		tile->setMapData(nullptr, -1, -1, part);
		// the way of Tile::destroy: nothing below the lowest level to fall into
		if (part == O_FLOOR && tile->getPosition().z == 0)
		{
			tile->setMapData(MapDataSet::getScorchedEarthTile(), 1, 0, O_FLOOR);
		}
	}
	// the way of an explosion: the fire is out with what it burned on
	if (tile->getFire() && !tile->getMapData(O_FLOOR) && !tile->getMapData(O_OBJECT))
	{
		tile->setFire(0);
	}
	return nullptr;
}

const char *takeOutOfBattle(SavedBattleGame *battle, BattleItem *item)
{
	auto &items = *battle->getItems();
	if (std::find(items.begin(), items.end(), item) == items.end())
	{
		return "the item is gone";
	}
	if (item->isSpecialWeapon())
	{
		// SavedBattleGame::removeItem leaves it silently: load() would make a new one
		return "a unit's special weapon stays";
	}
	if (item->getUnit())
	{
		// the way back of a stunned unit goes through its body
		return "a body stays";
	}
	if (auto *game = battle->getBattleGame())
	{
		auto *action = game->getCurrentAction();
		while (action->targeting && action->weapon == item && game->cancelCurrentAction(true))
		{
		}
	}
	if (item->isAmmo())
	{
		for (auto *weapon : items)
		{
			for (int slot = 0; weapon != item && slot < RuleItem::AmmoSlotMax; ++slot)
			{
				if (weapon->getAmmoForSlot(slot) == item)
				{
					weapon->setAmmoForSlot(slot, nullptr);
				}
			}
		}
	}
	battle->removeItem(item);
	return nullptr;
}

struct HireDone
{
	Soldier *soldier;
	const char *reason;
};

int pushHireDone(lua_State *L, void *data)
{
	auto *hire = static_cast<HireDone*>(data);
	pushOrNil(L, TYPE_SOLDIER, hire->soldier);
	if (hire->soldier)
	{
		return 1;
	}
	lua_pushstring(L, hire->reason);
	return 2;
}

/// The way of PurchaseState::purchase, the money is the mod's own business.
Soldier *hireSoldier(Mod *mod, SavedGame *save, Base *base, const RuleSoldier *rule)
{
	if (rule->getMonthlyBuyLimit() > 0)
	{
		save->getMonthlyPurchaseLimitLog()[rule->getType()] += 1;
	}
	int time = rule->getTransferTime();
	if (time == 0)
	{
		time = mod->getPersonnelTime();
	}
	auto *transfer = new Transfer(time);
	const int nationality = save->selectSoldierNationalityByLocation(mod, rule, base);
	auto *soldier = mod->genSoldier(save, rule, nationality);
	if (!rule->getSpawnedSoldierTemplate().yaml.empty())
	{
		YAML::YamlRootNodeReader reader(rule->getSpawnedSoldierTemplate(), "(spawned soldier template)");
		const int nationalityOrig = soldier->getNationality();
		soldier->load(reader.toBase(), mod, save, mod->getScriptGlobal(), true);
		if (soldier->getNationality() != nationalityOrig)
		{
			soldier->genName();
		}
	}
	transfer->setSoldier(soldier);
	base->getTransfers()->push_back(transfer);
	return soldier;
}

struct ScreenCall
{
	LuaScreenState *screen;
	int widget, value;
	const std::string *text;
	bool building;
};

int pushScreenCall(lua_State *L, void *data)
{
	auto *call = static_cast<ScreenCall*>(data);
	int count = 0;
	if (call->building)
	{
		pushUiHandle(L, TYPE_UI, call->screen->getId(), -1);
		++count;
	}
	if (call->widget >= 0)
	{
		pushUiHandle(L, TYPE_UI_WIDGET, call->screen->getId(), call->widget);
		++count;
	}
	if (call->value != LuaHost::NO_VALUE)
	{
		lua_pushinteger(L, call->value);
		++count;
	}
	if (call->text)
	{
		lua_pushlstring(L, call->text->data(), call->text->size());
		++count;
	}
	return count;
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
		case LuaHost::Arg::TILE: pushOrNil(L, TYPE_TILE, arg.object); break;
		case LuaHost::Arg::RULE_ITEM: pushOrNil(L, TYPE_RULE_ITEM, arg.object); break;
		case LuaHost::Arg::RULE_ARMOR: pushOrNil(L, TYPE_RULE_ARMOR, arg.object); break;
		case LuaHost::Arg::RULE_UFO: pushOrNil(L, TYPE_RULE_UFO, arg.object); break;
		case LuaHost::Arg::RULE_CRAFT: pushOrNil(L, TYPE_RULE_CRAFT, arg.object); break;
		case LuaHost::Arg::NERDS: pushOrNil(L, TYPE_NERDS, arg.object); break;
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

LuaHost *LuaHost::_active = nullptr;

LuaHost::~LuaHost()
{
	if (_active == this)
	{
		_active = nullptr;
	}
}

int LuaHost::bonusEvent(const std::string &scriptName)
{
	for (int e = PSI_DEFENCE_BONUS; e <= CLOSE_QUARTERS_MULTIPLIER_BONUS; ++e)
	{
		if (scriptName == EVENTS[e].name)
		{
			return e;
		}
	}
	return -1;
}

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
		for (const auto &word : info->getLuaCaps())
		{
			entry.caps |= capOf(word);
			if (!capOf(word))
			{
				entry.capsError = "metadata.yml: luaCaps has an unknown word '" + word + "', the mod's Lua is off";
			}
		}
		if (!info->getLuaCaps().empty() && entry.api < API_WITH_CAPS)
		{
			entry.capsError = "metadata.yml: luaCaps needs luaApi " + std::to_string(API_WITH_CAPS) + ", the mod's Lua is off";
		}
	}
	if (off > 0)
	{
		Log(LOG_INFO) << "[lua] Lua is off (oxceLuaMods), " << off << " mods run without it";
	}
	if (host)
	{
		// main.lua declares its screens through it
		_active = host.get();
		host->reload();
	}
	return host.release();
}

std::string LuaHost::reload()
{
	int loaded = 0, failed = 0;
	dropQueue();
	_menuScreens = false;
	std::fill(std::begin(_handled), std::end(_handled), false);
	std::set<std::string> names, namesApi1;
	for (int e = 0; e < EVENT_COUNT; ++e)
	{
		names.insert(EVENTS[e].name);
		if (e < NEW_HOUR)
		{
			namesApi1.insert(EVENTS[e].name);
		}
	}
	for (size_t i = 0; i < _entries.size(); ++i)
	{
		auto &entry = _entries[i];
		entry.sandbox.reset();
		entry.notified = false;
		entry.turn = -1;
		entry.screenPeriod = -1;
		entry.screens.clear();
		if (entry.api > API_VERSION)
		{
			++failed;
			noteError(i, "main.lua", "the mod needs Lua API " + std::to_string(entry.api) + ", this game has " + std::to_string(API_VERSION) + ", the mod's Lua is off");
			continue;
		}
		if (!entry.capsError.empty())
		{
			++failed;
			noteError(i, "main.lua", entry.capsError);
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
		entry.sandbox = std::make_unique<LuaSandbox>(LuaSandbox::Limits{}, entry.api >= API_WITH_CAPS ? names : namesApi1,
			[id](const std::string &text) { Log(LOG_INFO) << "[lua] " << id << ": " << text; },
			[](int low, int high) { return RNG::generate(low, high); });
		entry.sandbox->setErrorFn([this, i](const std::string &event, const std::string &text) { noteError(i, event, text); });
		if (!entry.sandbox->setup(setupGame, _mod) || (entry.api >= API_WITH_CAPS && !entry.sandbox->setup(setupApi2, nullptr)) || !entry.sandbox->load("main.lua", code))
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
	// the formulas reach the workers of the frame and the AI's map: Lua is one thread, there the script's value stands
	if (std::this_thread::get_id() != g_mainThread)
	{
		return;
	}
	if (_handled[event])
	{
		FireData data{ &EVENTS[event], args.begin(), args.size(), out };
		// a method of a handler can reach a formula, and with it another mod's handler: the outer one goes on after it
		const bool noScreen = g_noScreen, onlyReads = g_onlyReads, pure = g_pure, mayEconomy = g_mayEconomy, battleStart = g_battleStart;
		g_battleStart = event == BATTLE_START;
		g_noScreen = event == RETURN_FROM_MISSION_UNIT || event == BATTLE_END;
		g_mayEconomy = event == NEW_HOUR || event == NEW_DAY || event == NEW_MONTH;
		g_onlyReads = EVENTS[event].onlyReads;
		g_pure = EVENTS[event].pure;
		for (auto &entry : _entries)
		{
			if (entry.sandbox)
			{
				const bool noRandom = entry.sandbox->setNoRandom(EVENTS[event].pure);
				const size_t queued = _queue.size(), undo = _undo.size();
				const int errors = entry.sandbox->errorCount();
				entry.callItems = 0;
				entry.callUnits = 0;
				entry.callTiles = 0;
				entry.callScreens = 0;
				entry.callHires = 0;
				entry.sandbox->fire(EVENTS[event].name, pushArgs, &data, out ? takeOutputs : nullptr);
				// like the output values: a call that failed changes nothing
				const bool failed = entry.sandbox->errorCount() != errors;
				if (failed)
				{
					dropQueued(queued);
				}
				if (_undo.size() > undo)
				{
					endEconomy(entry, undo, failed);
				}
				entry.sandbox->setNoRandom(noRandom);
			}
		}
		g_noScreen = noScreen;
		g_onlyReads = onlyReads;
		g_pure = pure;
		g_mayEconomy = mayEconomy;
		g_battleStart = battleStart;
	}
	if (!_notice.empty() && event != RETURN_FROM_MISSION_UNIT && event != BATTLE_END)
	{
		for (const auto &arg : args)
		{
			if (arg.kind == Arg::BATTLE && arg.object)
			{
				showNotice(static_cast<SavedBattleGame*>(arg.object));
				break;
			}
		}
	}
}

void LuaHost::showNotice(SavedBattleGame *battle)
{
	if (!_notice.empty() && battle->getBattleState())
	{
		battle->getBattleState()->warningLongRaw(_notice);
		_notice.clear();
	}
}

bool LuaHost::hasCap(const LuaSandbox *sandbox, Cap cap) const
{
	for (const auto &entry : _entries)
	{
		if (entry.sandbox.get() == sandbox)
		{
			return entry.caps & cap;
		}
	}
	return false;
}

std::string LuaHost::queueBattleOp(const LuaSandbox *sandbox, const SavedBattleGame *battle, Pending op, const char *method)
{
	for (size_t i = 0; i < _entries.size(); ++i)
	{
		auto &entry = _entries[i];
		if (entry.sandbox.get() != sandbox)
		{
			continue;
		}
		if (entry.turn != battle->getTurn())
		{
			entry.turn = battle->getTurn();
			entry.turnItems = 0;
			entry.turnUnits = 0;
			entry.turnTiles = 0;
		}
		const bool isUnit = op.unitRule != nullptr, isTile = op.mapOp != MAP_NONE;
		int &inCall = isTile ? entry.callTiles : isUnit ? entry.callUnits : entry.callItems;
		int &inTurn = isTile ? entry.turnTiles : isUnit ? entry.turnUnits : entry.turnItems;
		const int perCall = isTile ? MAP_TILES_PER_CALL : isUnit ? SPAWN_UNITS_PER_CALL : SPAWN_ITEMS_PER_CALL;
		const int perTurn = isTile ? MAP_TILES_PER_TURN : isUnit ? SPAWN_UNITS_PER_TURN : SPAWN_ITEMS_PER_TURN;
		const char *what = isTile ? " changes of tiles" : isUnit ? " units" : " items";
		if (inCall >= perCall)
		{
			return std::string(method) + ": more than " + std::to_string(perCall) + what + " in one call";
		}
		if (inTurn >= perTurn)
		{
			return std::string(method) + ": more than " + std::to_string(perTurn) + what + " in one turn of the battle";
		}
		++inCall;
		++inTurn;
		op.entry = i;
		_queue.push_back(op);
		return std::string();
	}
	return std::string(method) + ": not a running mod";
}

std::string LuaHost::queueSpawnItem(const LuaSandbox *sandbox, const SavedBattleGame *battle, const RuleItem *rule, int x, int y, int z, int done)
{
	return queueBattleOp(sandbox, battle, { 0, rule, x, y, z, done }, "spawnItem");
}

std::string LuaHost::queueGiveItem(const LuaSandbox *sandbox, const SavedBattleGame *battle, BattleUnit *unit, const RuleItem *rule, int done)
{
	Pending op{ 0, rule, 0, 0, 0, done };
	op.unit = unit;
	return queueBattleOp(sandbox, battle, op, "giveItem");
}

std::string LuaHost::queueRemoveItem(const LuaSandbox *sandbox, const SavedBattleGame *battle, BattleItem *item, int done)
{
	Pending op{ 0, nullptr, 0, 0, 0, done };
	op.item = item;
	return queueBattleOp(sandbox, battle, op, "removeItem");
}

std::string LuaHost::queueSpawnUnit(const LuaSandbox *sandbox, const SavedBattleGame *battle, const Unit *rule, int x, int y, int z, int faction, int direction, int done)
{
	Pending op{ 0, nullptr, x, y, z, done };
	op.unitRule = rule;
	op.faction = faction;
	op.direction = direction;
	return queueBattleOp(sandbox, battle, op, "spawnUnit");
}

std::string LuaHost::queueMapOp(const LuaSandbox *sandbox, const SavedBattleGame *battle, const char *method, MapOp mapOp, int x, int y, int z, int part, int id, int set, int value, int done)
{
	Pending op{ 0, nullptr, x, y, z, done };
	op.mapOp = mapOp;
	op.part = part;
	op.mapId = id;
	op.mapSet = set;
	op.mapValue = value;
	return queueBattleOp(sandbox, battle, op, method);
}

std::string LuaHost::queueHire(const LuaSandbox *sandbox, Base *base, const RuleSoldier *rule, int done)
{
	for (size_t i = 0; i < _entries.size(); ++i)
	{
		auto &entry = _entries[i];
		if (entry.sandbox.get() != sandbox)
		{
			continue;
		}
		const auto *saved = LuaScreenState::savedGame();
		const int period = saved ? saved->getDaysPassed() : 0;
		if (entry.hirePeriod != period)
		{
			entry.hirePeriod = period;
			entry.periodHires = 0;
		}
		if (entry.callHires >= SOLDIERS_PER_CALL)
		{
			return "hireSoldier: more than " + std::to_string(SOLDIERS_PER_CALL) + " soldiers in one call";
		}
		if (entry.periodHires >= SOLDIERS_PER_DAY)
		{
			return "hireSoldier: more than " + std::to_string(SOLDIERS_PER_DAY) + " soldiers in one day";
		}
		++entry.callHires;
		++entry.periodHires;
		_queue.push_back({ i, nullptr, 0, 0, 0, done, base, rule });
		return std::string();
	}
	return "hireSoldier: not a running mod";
}

void LuaHost::endEconomy(const Entry &entry, size_t undo, bool failed)
{
	if (failed)
	{
		for (size_t i = _undo.size(); i > undo; --i)
		{
			_undo[i - 1]();
		}
	}
	else if (auto *saved = LuaScreenState::savedGame())
	{
		saved->luaTouch(entry.id, "economy");
	}
	_undo.erase(_undo.begin() + undo, _undo.end());
}

void LuaHost::dropQueued(size_t from)
{
	for (size_t i = from; i < _queue.size(); ++i)
	{
		if (_queue[i].done && _entries[_queue[i].entry].sandbox)
		{
			_entries[_queue[i].entry].sandbox->drop(_queue[i].done);
		}
	}
	_queue.resize(from);
}

void LuaHost::dropQueue()
{
	_screens.clear();
	if (!_queue.empty())
	{
		writeJournal("lua", "queue", std::to_string(_queue.size()) + " queued changes are dropped: the battle they were for is gone");
		dropQueued(0);
	}
}

bool LuaHost::isRunning(const LuaSandbox *sandbox) const
{
	for (const auto &entry : _entries)
	{
		if (entry.sandbox.get() == sandbox)
		{
			return true;
		}
	}
	return false;
}

std::string LuaHost::declareScreen(const LuaSandbox *sandbox, const std::string &name, int fn, const std::string &menu, const std::string &category)
{
	for (auto &entry : _entries)
	{
		if (entry.sandbox.get() != sandbox)
		{
			continue;
		}
		if (entry.screens.size() >= SCREENS_PER_MOD)
		{
			return "game.screen: more than " + std::to_string(SCREENS_PER_MOD) + " screens in one mod";
		}
		for (const auto &screen : entry.screens)
		{
			if (screen.name == name)
			{
				return "game.screen: the mod already has a screen '" + name + "'";
			}
		}
		entry.screens.push_back({ name, menu, category, fn });
		_menuScreens = _menuScreens || !menu.empty();
		return std::string();
	}
	return "game.screen: not a running mod";
}

std::string LuaHost::queueScreen(const LuaSandbox *sandbox, const std::string &name)
{
	for (size_t i = 0; i < _entries.size(); ++i)
	{
		auto &entry = _entries[i];
		if (entry.sandbox.get() != sandbox)
		{
			continue;
		}
		for (size_t s = 0; s < entry.screens.size(); ++s)
		{
			if (entry.screens[s].name != name)
			{
				continue;
			}
			auto *saved = LuaScreenState::savedGame();
			const auto *battle = saved ? saved->getSavedBattle() : nullptr;
			const int period = battle ? battle->getTurn() : saved ? saved->getDaysPassed() : 0;
			if (entry.screenPeriod != period)
			{
				entry.screenPeriod = period;
				entry.periodScreens = 0;
			}
			if (entry.callScreens >= SCREENS_PER_CALL)
			{
				return "game.openScreen: more than " + std::to_string(SCREENS_PER_CALL) + " screen in one call";
			}
			if (entry.periodScreens >= SCREENS_PER_PERIOD)
			{
				return "game.openScreen: more than " + std::to_string(SCREENS_PER_PERIOD) + " screens in one turn or day";
			}
			if (LuaScreenState::openCount() + _screens.size() >= LuaScreenState::MAX_OPEN)
			{
				return "game.openScreen: more than " + std::to_string(LuaScreenState::MAX_OPEN) + " screens one on another";
			}
			++entry.callScreens;
			++entry.periodScreens;
			_screens.emplace_back(i, s);
			return std::string();
		}
		return "game.openScreen: the mod has no screen '" + name + "', declare it with game.screen in main.lua";
	}
	return "game.openScreen: not a running mod";
}

State *LuaHost::nextScreenNow()
{
	while (!_screens.empty())
	{
		const auto next = _screens.front();
		_screens.erase(_screens.begin());
		const auto &entry = _entries[next.first];
		if (entry.sandbox && next.second < entry.screens.size())
		{
			if (auto *state = buildScreen(next.first, entry.screens[next.second]))
			{
				return state;
			}
		}
	}
	return nullptr;
}

std::vector<std::pair<std::string, std::string>> LuaHost::menuScreens() const
{
	std::vector<std::pair<std::string, std::string>> list;
	for (const auto &entry : _entries)
	{
		if (entry.sandbox && !entry.sandbox->isDisabled())
		{
			for (const auto &screen : entry.screens)
			{
				if (!screen.menu.empty())
				{
					list.emplace_back(screen.menu, entry.id);
				}
			}
		}
	}
	return list;
}

State *LuaHost::openMenuScreen(size_t index)
{
	for (size_t i = 0; i < _entries.size(); ++i)
	{
		const auto &entry = _entries[i];
		if (entry.sandbox && !entry.sandbox->isDisabled())
		{
			for (const auto &screen : entry.screens)
			{
				if (!screen.menu.empty() && index-- == 0)
				{
					return buildScreen(i, screen);
				}
			}
		}
	}
	return nullptr;
}

State *LuaHost::buildScreen(size_t entry, const ScreenInfo &screen)
{
	auto &mod = _entries[entry];
	if (mod.sandbox->isDisabled())
	{
		return nullptr;
	}
	if (!_mod->getInterface(screen.category, false))
	{
		noteError(entry, screen.name, "game.screen: no interface '" + screen.category + "' in the rules, the screen does not open");
		return nullptr;
	}
	auto state = std::make_unique<LuaScreenState>(mod.sandbox.get(), screen.category);
	const int errors = mod.sandbox->errorCount();
	ScreenCall call{ state.get(), -1, NO_VALUE, nullptr, true };
	callScreenFn(mod, screen.fn, screen.name.c_str(), true, &call);
	if (mod.sandbox->errorCount() != errors)
	{
		return nullptr;
	}
	state->finish();
	return state.release();
}

void LuaHost::callScreen(LuaScreenState *screen, int fn, const char *what, bool pure, int widget, int value, const std::string *text)
{
	for (auto &entry : _entries)
	{
		if (entry.sandbox.get() == screen->getSandbox())
		{
			ScreenCall call{ screen, widget, value, text, false };
			callScreenFn(entry, fn, what, pure, &call);
			// a click outside a battle has its moment right here, the screen is on top until it closes
			auto *saved = LuaScreenState::savedGame();
			if (!pure && saved && !saved->getSavedBattle())
			{
				runQueue(saved);
			}
			return;
		}
	}
}

void LuaHost::callScreenFn(Entry &entry, int fn, const char *what, bool pure, void *call)
{
	const bool noScreen = g_noScreen, onlyReads = g_onlyReads, wasPure = g_pure, screenReads = g_screenReads, mayEconomy = g_mayEconomy;
	const bool noRandom = entry.sandbox->setNoRandom(pure);
	g_noScreen = false;
	g_onlyReads = pure;
	g_pure = pure;
	g_screenReads = pure;
	g_mayEconomy = !pure;
	entry.callUnits = 0;
	const size_t queued = _queue.size(), screens = _screens.size(), undo = _undo.size();
	const int errors = entry.sandbox->errorCount();
	entry.callItems = 0;
	entry.callTiles = 0;
	entry.callScreens = 0;
	entry.callHires = 0;
	entry.sandbox->callHeld(fn, what, pushScreenCall, call);
	// like the handlers: a call that failed changes nothing
	const bool failed = entry.sandbox->errorCount() != errors;
	if (failed)
	{
		dropQueued(queued);
		_screens.resize(screens);
	}
	if (_undo.size() > undo)
	{
		endEconomy(entry, undo, failed);
	}
	entry.sandbox->setNoRandom(noRandom);
	g_noScreen = noScreen;
	g_onlyReads = onlyReads;
	g_pure = wasPure;
	g_screenReads = screenReads;
	g_mayEconomy = mayEconomy;
}

void LuaHost::runGeoscapeQueueNow(SavedGame *save)
{
	// what the functions called here add waits for the next moment
	std::vector<Pending> now;
	now.swap(_queue);
	int battleOps = 0;
	for (const auto &op : now)
	{
		auto &entry = _entries[op.entry];
		if (!entry.sandbox)
		{
			continue;
		}
		if (!op.base || entry.sandbox->isDisabled())
		{
			battleOps += op.base ? 0 : 1;
			if (op.done)
			{
				entry.sandbox->drop(op.done);
			}
			continue;
		}
		HireDone hire{ nullptr, nullptr };
		const auto &bases = *save->getBases();
		const int limit = op.soldier->getMonthlyBuyLimit();
		if (std::find(bases.begin(), bases.end(), op.base) == bases.end())
		{
			hire.reason = "the base is gone";
		}
		else if (op.base->getAvailableQuarters() - op.base->getUsedQuarters() < 1)
		{
			hire.reason = "no free quarters";
		}
		else if (limit > 0 && save->getMonthlyPurchaseLimitLog()[op.soldier->getType()] >= limit)
		{
			hire.reason = "the monthly limit of this soldier";
		}
		else
		{
			hire.soldier = hireSoldier(_mod, save, op.base, op.soldier);
			save->luaTouch(entry.id, "economy");
		}
		if (op.done)
		{
			const bool mayEconomy = g_mayEconomy;
			g_mayEconomy = true;
			const size_t queued = _queue.size(), undo = _undo.size();
			const int errors = entry.sandbox->errorCount();
			entry.callHires = 0;
			entry.callScreens = 0;
			entry.sandbox->callKept(op.done, "hireSoldier done", pushHireDone, &hire);
			const bool failed = entry.sandbox->errorCount() != errors;
			if (failed)
			{
				dropQueued(queued);
			}
			if (_undo.size() > undo)
			{
				endEconomy(entry, undo, failed);
			}
			g_mayEconomy = mayEconomy;
		}
	}
	if (battleOps > 0)
	{
		writeJournal("lua", "queue", std::to_string(battleOps) + " queued changes are dropped: the battle they were for is gone");
	}
}

void LuaHost::runQueueNow(SavedBattleGame *battle, bool all)
{
	// what the functions called here add waits for the next moment: a chain is stopped by the ceiling of the turn
	std::vector<Pending> now;
	now.swap(_queue);
	// a unit is 11-14 ms (LUA_MODS_V2_STAGE0.md): one a moment, what stands after the first one waits in its order
	size_t count = now.size();
	if (!all)
	{
		bool unit = false;
		for (size_t i = 0; i < now.size(); ++i)
		{
			if (now[i].unitRule)
			{
				if (unit)
				{
					count = i;
					break;
				}
				unit = true;
			}
		}
	}
	std::vector<SpawnDone> results(count);
	std::vector<std::pair<Position, int>> glowing;
	std::vector<Tile*> tiles;
	auto *tileEngine = battle->getTileEngine();
	bool newUnits = false, newParts = false;
	for (size_t i = 0; i < count; ++i)
	{
		const auto &op = now[i];
		auto &entry = _entries[op.entry];
		auto &result = results[i];
		if (!entry.sandbox)
		{
			continue;
		}
		if (entry.sandbox->isDisabled() || op.base)
		{
			if (op.done)
			{
				entry.sandbox->drop(op.done);
			}
			continue;
		}
		result.ran = true;
		if (op.mapOp != MAP_NONE)
		{
			auto *tile = battle->getTile(Position(op.x, op.y, op.z));
			result.reason = changeTile(battle, tile, op.mapOp, (TilePart)op.part, op.mapId, op.mapSet, op.mapValue);
			if (!result.reason)
			{
				result.tile = tile;
				tiles.push_back(tile);
				newParts = newParts || (op.mapOp != MAP_FIRE && op.mapOp != MAP_SMOKE);
				battle->getGeoscapeSave()->luaTouch(entry.id, "map");
			}
		}
		else if (op.unitRule)
		{
			result.unit = battle->placeNewUnit(op.unitRule, (UnitFaction)op.faction, Position(op.x, op.y, op.z), 0, op.direction, nullptr);
			result.reason = "no room for the unit";
			newUnits = newUnits || result.unit;
		}
		else if (op.item)
		{
			const bool glow = op.item->getGlow();
			const Position pos = op.item->getOwner() ? op.item->getOwner()->getPosition() : op.item->getTile() ? op.item->getTile()->getPosition() : TileEngine::invalid;
			const int range = op.item->getVisibilityUpdateRange();
			result.reason = takeOutOfBattle(battle, op.item);
			result.removed = !result.reason;
			if (glow && result.removed && pos != TileEngine::invalid)
			{
				glowing.push_back({ pos, range });
			}
		}
		else if (op.unit)
		{
			const auto &units = *battle->getUnits();
			if (std::find(units.begin(), units.end(), op.unit) == units.end() || op.unit->isOut())
			{
				result.reason = "the unit is gone";
			}
			else
			{
				// `true`, the way of a unit's fixed weapons: a soldier takes nothing without it, addItem leaves a soldier's kit to the player
				result.item = battle->createItemForUnit(op.rule, op.unit, true);
				result.reason = "the unit does not take it: no slot, too heavy or it has one already";
				if (result.item && result.item->getGlow())
				{
					glowing.push_back({ op.unit->getPosition(), result.item->getVisibilityUpdateRange() });
				}
			}
		}
		else
		{
			// the way of BattlescapeGame::spawnNewItem
			result.item = battle->createItemForTile(op.rule, battle->getTile(Position(op.x, op.y, op.z)));
			tileEngine->applyGravity(result.item->getTile());
			if (result.item->getGlow())
			{
				glowing.push_back({ result.item->getTile()->getPosition(), result.item->getVisibilityUpdateRange() });
			}
		}
		if (result.item || result.unit || result.removed)
		{
			battle->getGeoscapeSave()->luaTouch(entry.id, "spawn");
		}
	}
	// the order of an explosion (R-302): all the parts, gravity on each tile and the one above, light and sight once
	if (!tiles.empty())
	{
		for (auto *tile : tiles)
		{
			tileEngine->applyGravity(tile);
			tileEngine->applyGravity(battle->getAboveTile(tile));
		}
		tileEngine->calculateLighting(newParts ? LL_AMBIENT : LL_FIRE, TileEngine::invalid, 0, true);
		tileEngine->recalculateFOV();
	}
	// the light of many items at once: one pass over the map costs what a few of them do one by one (LUA_MODS_V2_STAGE0.md)
	if (glowing.size() > GLOW_ONE_BY_ONE)
	{
		tileEngine->calculateLighting(LL_ITEMS);
		tileEngine->recalculateFOV();
	}
	else
	{
		for (const auto &glow : glowing)
		{
			tileEngine->calculateLighting(LL_ITEMS, glow.first);
			tileEngine->calculateFOV(glow.first, glow.second, false);
		}
	}
	if ((newUnits || !tiles.empty()) && battle->getBattleState())
	{
		battle->getBattleState()->updateSoldierInfo(false);
	}
	for (size_t i = 0; i < count; ++i)
	{
		if (results[i].ran && now[i].done)
		{
			auto &entry = _entries[now[i].entry];
			entry.callItems = 0;
			entry.callUnits = 0;
			entry.callTiles = 0;
			entry.callScreens = 0;
			const size_t queued = _queue.size();
			const int errors = entry.sandbox->errorCount();
			entry.sandbox->callKept(now[i].done, now[i].mapOp != MAP_NONE ? "map done" : now[i].unitRule ? "spawnUnit done" : now[i].unit ? "giveItem done" : now[i].item ? "removeItem done" : "spawnItem done", pushSpawnDone, &results[i]);
			// like a handler: a call that failed asked for nothing
			if (entry.sandbox->errorCount() != errors)
			{
				dropQueued(queued);
			}
		}
	}
	_queue.insert(_queue.begin(), now.begin() + count, now.end());
	showNotice(battle);
}

}
