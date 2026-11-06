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
#include <climits>
#include <istream>
#include <iterator>
#include <set>
#include <string>
#include "Armor.h"
#include "Mod.h"
#include "RuleDamageType.h"
#include "RuleItem.h"
#include "RuleSkill.h"
#include "Unit.h"
#include "../Battlescape/BattlescapeState.h"
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
#include "../Savegame/SavedBattleGame.h"
#include "../Savegame/Soldier.h"
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
const char *const MOD_KEY = "oxce.mod";
const char *const OUT_KEY = "oxce.out";

/// What a slow API call costs a handler, in C loop steps: the counter sees it as one instruction.
const unsigned long long TAG_TICKS = 100, MESSAGE_TICKS = 20000;
const size_t MESSAGE_MAX = 200, JOURNAL_MAX = 256 * 1024;

/// Handlers and their output values, the names of the Y-script. A value in `readOnly` is shown, not taken back.
struct EventInfo
{
	const char *name;
	std::vector<const char*> outputs;
	std::set<std::string> readOnly;
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
};

/// The battle screen may be gone by then: the debriefing runs after it.
bool g_noScreen = false;

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
	const char *name = luaL_checkstring(L, 2);
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
	auto *unit = checkUnit(L);
	(BattleUnit::luaApi().*Field)(unit, checkInt(L, 2));
	return 0;
}

template<auto Field>
int unitSet2(lua_State *L)
{
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
	auto *unit = checkUnit(L);
	const auto tag = checkTag<ScriptTag<BattleUnit>>(L);
	unit->luaSetTag(tag, checkInt(L, 3));
	return 0;
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
	auto *item = checkItem(L);
	const auto tag = checkTag<ScriptTag<BattleItem>>(L);
	item->luaSetTag(tag, checkInt(L, 3));
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
int battleFlashMessage(lua_State *L)
{
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
	battle->getBattleState()->warningRaw(translated);
	return 0;
}

const luaL_Reg BATTLE_METHODS[] = {
	{ "getTurn", battleGetTurn },
	{ "getSize", battleGetSize },
	{ "flashMessage", battleFlashMessage },
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

const luaL_Reg RULE_ARMOR_METHODS[] = { { "getType", ruleArmorGetType }, { nullptr, nullptr } };
const luaL_Reg RULE_ITEM_METHODS[] = { { "getType", ruleItemGetType }, { nullptr, nullptr } };
const luaL_Reg SKILL_METHODS[] = { { "getType", skillGetType }, { nullptr, nullptr } };

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

const luaL_Reg SOLDIER_METHODS[] = { { "getId", soldierGetId }, { "getRank", soldierGetRank }, { nullptr, nullptr } };

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
		const std::string code{ std::istreambuf_iterator<char>(*file), std::istreambuf_iterator<char>() };
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
	if (_journal.size() >= JOURNAL_MAX)
	{
		return;
	}
	_journal += CrossPlatform::now() + " " + id + " " + event + ": " + text + "\n\n";
	if (_journal.size() >= JOURNAL_MAX)
	{
		_journal += "the log is full, the rest is dropped\n";
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
