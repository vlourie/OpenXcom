#pragma once
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
#include <cstddef>
#include <initializer_list>
#include <memory>
#include <string>
#include <tuple>
#include <type_traits>
#include <vector>

namespace OpenXcom
{

class BattleItem;
class BattleUnit;
class Country;
class Craft;
class LuaSandbox;
class Mod;
class RuleSkill;
class RuleSoldierBonus;
class SavedBattleGame;
class SavedGame;
class Soldier;
class Ufo;

/**
 * The Lua of the active mods: one sandbox per mod, in load order. Exists only with the option
 * oxceLuaMods and at least one mod with Lua: without them the game holds a null pointer and that is all.
 * Runs next to the Y-script of the same name, after it, with its arguments and its output values.
 */
class LuaHost
{
public:
	/// The API version a mod names in metadata.yml as luaApi.
	static const int API_VERSION = 1;

	enum Event
	{
		CREATE_UNIT, NEW_TURN_UNIT, HIT_UNIT, DAMAGE_UNIT, DAMAGE_SPECIAL_UNIT, HEAL_UNIT, SKILL_USE_UNIT,
		RETURN_FROM_MISSION_UNIT, CREATE_ITEM, NEW_TURN_ITEM, AWARD_EXPERIENCE, TRY_PSI_ATTACK_ITEM, TRY_PSI_ATTACK_UNIT,
		TRY_MELEE_ATTACK_ITEM, TRY_MELEE_ATTACK_UNIT, SELECT_MOVE_SOUND_UNIT, NEW_MONTH_COUNTRY, DETECT_UFO_FROM_BASE,
		DETECT_UFO_FROM_CRAFT, APPLY_SOLDIER_BONUSES, EVENT_COUNT
	};

	/// One argument of a handler; a null pointer reaches Lua as nil.
	struct Arg
	{
		enum Kind { UNIT, ITEM, BATTLE, SKILL, SOLDIER, GEOSCAPE, COUNTRY, UFO, CRAFT, BONUS, INT } kind;
		void *object;
		int value;

		// const: the handlers that only read, the setters refuse there
		Arg(const BattleUnit *o) : kind(UNIT), object(const_cast<BattleUnit*>(o)), value(0) { }
		Arg(const BattleItem *o) : kind(ITEM), object(const_cast<BattleItem*>(o)), value(0) { }
		Arg(SavedBattleGame *o) : kind(BATTLE), object(o), value(0) { }
		Arg(const RuleSkill *o) : kind(SKILL), object(const_cast<RuleSkill*>(o)), value(0) { }
		Arg(Soldier *o) : kind(SOLDIER), object(o), value(0) { }
		Arg(const SavedGame *o) : kind(GEOSCAPE), object(const_cast<SavedGame*>(o)), value(0) { }
		Arg(const Country *o) : kind(COUNTRY), object(const_cast<Country*>(o)), value(0) { }
		Arg(const Ufo *o) : kind(UFO), object(const_cast<Ufo*>(o)), value(0) { }
		Arg(const Craft *o) : kind(CRAFT), object(const_cast<Craft*>(o)), value(0) { }
		Arg(const RuleSoldierBonus *o) : kind(BONUS), object(const_cast<RuleSoldierBonus*>(o)), value(0) { }
		Arg(int v) : kind(INT), object(nullptr), value(v) { }
	};

	/// Loads the Lua of the active mods; null when there is nothing to run.
	static LuaHost *create(Mod *mod);
	~LuaHost();

	/// Calls the handlers of an event without output values.
	void fire(Event event, std::initializer_list<Arg> args) { fireOutputs(event, args, nullptr); }
	/// Calls the handlers of an event, `outputs` is the data of the script's ScriptOutputArgs.
	template<typename Tuple>
	void fire(Event event, Tuple &outputs, std::initializer_list<Arg> args)
	{
		if (!_handled[event] && _notice.empty())
		{
			return;
		}
		std::apply([&](auto&... values)
		{
			int out[] = { static_cast<int>(values)... };
			fireOutputs(event, args, out);
			int i = 0;
			((values = static_cast<std::decay_t<decltype(values)>>(out[i++])), ...);
		}, outputs);
	}

	/// Reads every mod's main.lua again: Lua variables are gone, a switched off mod is back. What happened, in a line.
	std::string reload();
	/// A mod handles hitUnit, damageUnit or damageSpecialUnit: the AI's forecast of a shot does not know the result.
	bool hasDamageHandlers() const { return _handled[HIT_UNIT] || _handled[DAMAGE_UNIT] || _handled[DAMAGE_SPECIAL_UNIT]; }

private:
	struct Entry
	{
		std::string id, path;
		int api = 0;
		std::unique_ptr<LuaSandbox> sandbox;
		bool notified = false;
	};

	void fireOutputs(Event event, std::initializer_list<Arg> args, int *out);
	void noteError(size_t entry, const std::string &event, const std::string &text);
	void writeJournal(const std::string &id, const std::string &event, const std::string &text);

	Mod *_mod = nullptr;
	std::vector<Entry> _entries;
	bool _handled[EVENT_COUNT] = { };
	std::string _notice, _journal;
};

}
