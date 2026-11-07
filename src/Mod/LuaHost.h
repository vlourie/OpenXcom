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
#include <climits>
#include <cstddef>
#include <functional>
#include <initializer_list>
#include <memory>
#include <string>
#include <tuple>
#include <type_traits>
#include <utility>
#include <vector>

namespace OpenXcom
{

class Armor;
class Base;
class BattleItem;
class BattleUnit;
class Country;
class Craft;
class LuaSandbox;
class LuaScreenState;
class Mod;
class RuleCraft;
class RuleItem;
class RuleSkill;
class RuleSoldier;
class RuleSoldierBonus;
class RuleUfo;
class SavedBattleGame;
class SavedGame;
class Soldier;
class State;
class StatsForNerdsState;
class Tile;
class Ufo;
class Unit;

/**
 * The Lua of the active mods: one sandbox per mod, in load order. Exists only with the option
 * oxceLuaMods and at least one mod with Lua: without them the game holds a null pointer and that is all.
 * Runs next to the Y-script of the same name, after it, with its arguments and its output values.
 */
class LuaHost
{
public:
	/// The API version a mod names in metadata.yml as luaApi.
	static const int API_VERSION = 2;
	/// From this version a mod has luaCaps and the methods behind them (docs/portal/LUA_MODS_V2.md).
	static const int API_WITH_CAPS = 2;
	/// What the mod's metadata.yml may name in luaCaps; a method of API 2 needs its word there.
	enum Cap { CAP_SPAWN = 1, CAP_SCREENS = 2, CAP_ECONOMY = 4, CAP_MAP = 8 };
	enum MapOp { MAP_NONE, MAP_SET, MAP_CLEAR, MAP_DESTROY, MAP_FIRE, MAP_SMOKE };

	enum Event
	{
		CREATE_UNIT, NEW_TURN_UNIT, HIT_UNIT, DAMAGE_UNIT, DAMAGE_SPECIAL_UNIT, HEAL_UNIT, SKILL_USE_UNIT,
		RETURN_FROM_MISSION_UNIT, CREATE_ITEM, NEW_TURN_ITEM, AWARD_EXPERIENCE, TRY_PSI_ATTACK_ITEM, TRY_PSI_ATTACK_UNIT,
		TRY_MELEE_ATTACK_ITEM, TRY_MELEE_ATTACK_UNIT, SELECT_MOVE_SOUND_UNIT, NEW_MONTH_COUNTRY, DETECT_UFO_FROM_BASE,
		DETECT_UFO_FROM_CRAFT, APPLY_SOLDIER_BONUSES,
		HIT_UNIT_AMMO, DAMAGE_UNIT_AMMO, DAMAGE_SPECIAL_UNIT_AMMO,
		REACTION_UNIT_ACTION, REACTION_UNIT_REACTION, REACTION_WEAPON_ACTION, VISIBILITY_UNIT, AI_CALCULATE_TARGET_WEIGHT,
		SELL_COST_ITEM, BUY_COST_ITEM,
		STATS_FOR_NERDS_ITEM, STATS_FOR_NERDS_ARMOR, STATS_FOR_NERDS_CRAFT, STATS_FOR_NERDS_UFO,
		PSI_DEFENCE_BONUS, MELEE_DODGE_BONUS,
		TIME_RECOVERY_BONUS, ENERGY_RECOVERY_BONUS, MORALE_RECOVERY_BONUS, HEALTH_RECOVERY_BONUS, MANA_RECOVERY_BONUS, STUN_RECOVERY_BONUS,
		TIME_SOLDIER_RECOVERY_BONUS, ENERGY_SOLDIER_RECOVERY_BONUS, MORALE_SOLDIER_RECOVERY_BONUS, HEALTH_SOLDIER_RECOVERY_BONUS,
		MANA_SOLDIER_RECOVERY_BONUS, STUN_SOLDIER_RECOVERY_BONUS,
		DAMAGE_BONUS_BONUS, MELEE_BONUS_BONUS, ACCURACY_MULTIPLIER_BONUS, MELEE_MULTIPLIER_BONUS, THROW_MULTIPLIER_BONUS, CLOSE_QUARTERS_MULTIPLIER_BONUS,
		// from here on only a mod of API_WITH_CAPS has these, for the rest they stay unknown events
		NEW_HOUR, NEW_DAY, NEW_MONTH, BATTLE_START, BATTLE_END,
		EVENT_COUNT
	};

	/// One argument of a handler; a null pointer reaches Lua as nil.
	struct Arg
	{
		enum Kind { UNIT, ITEM, BATTLE, SKILL, SOLDIER, GEOSCAPE, COUNTRY, UFO, CRAFT, BONUS, TILE, RULE_ITEM, RULE_ARMOR, RULE_UFO, RULE_CRAFT, NERDS, INT } kind;
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
		Arg(const Tile *o) : kind(TILE), object(const_cast<Tile*>(o)), value(0) { }
		Arg(const RuleItem *o) : kind(RULE_ITEM), object(const_cast<RuleItem*>(o)), value(0) { }
		Arg(const Armor *o) : kind(RULE_ARMOR), object(const_cast<Armor*>(o)), value(0) { }
		Arg(const RuleUfo *o) : kind(RULE_UFO), object(const_cast<RuleUfo*>(o)), value(0) { }
		Arg(const RuleCraft *o) : kind(RULE_CRAFT), object(const_cast<RuleCraft*>(o)), value(0) { }
		Arg(StatsForNerdsState *o) : kind(NERDS), object(o), value(0) { }
		Arg(int v) : kind(INT), object(nullptr), value(v) { }
	};

	/// Loads the Lua of the active mods; null when there is nothing to run.
	static LuaHost *create(Mod *mod);
	~LuaHost();

	/// For the rules, which hold no pointer to the game: null without Lua, the only cost of the calls they make.
	static LuaHost *active() { return _active; }
	/// The event of a bonus script by the name of its parser, -1 when Lua has no such event.
	static int bonusEvent(const std::string &scriptName);

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
	/// Puts a new item on the battle's map, later: a handler may be called from a walk over the game's lists.
	/// `done` is LuaSandbox::keep() of the mod's function or 0. An error text, or empty.
	std::string queueSpawnItem(const LuaSandbox *sandbox, const SavedBattleGame *battle, const RuleItem *rule, int x, int y, int z, int done);
	/// The same for an item into a unit's inventory.
	std::string queueGiveItem(const LuaSandbox *sandbox, const SavedBattleGame *battle, BattleUnit *unit, const RuleItem *rule, int done);
	/// The same for taking an item out of the battle.
	std::string queueRemoveItem(const LuaSandbox *sandbox, const SavedBattleGame *battle, BattleItem *item, int done);
	/// The same for a new unit. `direction` below 0 is a random one.
	std::string queueSpawnUnit(const LuaSandbox *sandbox, const SavedBattleGame *battle, const Unit *rule, int x, int y, int z, int faction, int direction, int done);
	/// The same for a change of a tile: the tile's x, y, z; `part`, `id` of the set and `set` as Tile::setMapData has them, `value` of fire and smoke.
	std::string queueMapOp(const LuaSandbox *sandbox, const SavedBattleGame *battle, const char *method, MapOp mapOp, int x, int y, int z, int part, int id, int set, int value, int done);
	/// Does the mod declare this in luaCaps?
	bool hasCap(const LuaSandbox *sandbox, Cap cap) const;
	/// Does what the handlers asked for. Only where nothing walks the lists: the battle's idle moment, before a save.
	/// `all`: new units too, at once; else one a moment, a unit is a step of the frame.
	void runQueue(SavedBattleGame *battle, bool all = false)
	{
		if (!_queue.empty())
		{
			runQueueNow(battle, all);
		}
	}
	/// The same outside a battle: the geoscape's think, a click on a screen, before a save.
	void runQueue(SavedGame *save)
	{
		if (!_queue.empty())
		{
			runGeoscapeQueueNow(save);
		}
	}
	/// Hires a soldier for the base, later: the new soldier takes numbers from the game's generator. `done` as in queueSpawnItem.
	std::string queueHire(const LuaSandbox *sandbox, Base *base, const RuleSoldier *rule, int done);
	/// The running call changed money or stock: how to take it back if the call fails.
	void noteEconomy(std::function<void()> undo) { _undo.push_back(std::move(undo)); }
	/// The battle ended or goes on another map: what was asked for has no place to happen. The next battle's reload() and the next stage call this.
	void dropQueue();
	/// A screen declared in main.lua: game.screen(name, fn, options). `fn` is LuaSandbox::keep(). An error text, or empty.
	std::string declareScreen(const LuaSandbox *sandbox, const std::string &name, int fn, const std::string &menu, const std::string &category);
	/// game.openScreen(name): the screen is built later, where nothing runs under it. An error text, or empty.
	std::string queueScreen(const LuaSandbox *sandbox, const std::string &name);
	/// The next screen asked for, built, for the caller to show; null when there is none or building it failed.
	State *nextScreen() { return _screens.empty() ? nullptr : nextScreenNow(); }
	/// Is there anything for the player's own way in: the button of the pause menu and the key?
	bool hasMenuScreens() const { return _menuScreens; }
	/// What the list of the player's way in shows: the title and the mod.
	std::vector<std::pair<std::string, std::string>> menuScreens() const;
	/// Builds a screen of that list for the caller to show; null when building it failed.
	State *openMenuScreen(size_t index);
	/// Calls a function of an open screen. `pure`: it only reads, a screen opened and closed changes nothing.
	/// `widget` -1: no widget among the arguments; `value` NO_VALUE: no number; `text` null: no text.
	static const int NO_VALUE = INT_MIN;
	void callScreen(LuaScreenState *screen, int fn, const char *what, bool pure, int widget, int value, const std::string *text);
	/// Is this the sandbox of a loaded mod? A screen may outlive its Lua only in the eyes of its destructor.
	bool isRunning(const LuaSandbox *sandbox) const;
	/// A mod handles the damage or the power of a shot: the AI's forecast of it does not know the result.
	bool hasDamageHandlers() const
	{
		return _handled[HIT_UNIT] || _handled[DAMAGE_UNIT] || _handled[DAMAGE_SPECIAL_UNIT]
			|| _handled[HIT_UNIT_AMMO] || _handled[DAMAGE_UNIT_AMMO] || _handled[DAMAGE_SPECIAL_UNIT_AMMO]
			|| _handled[DAMAGE_BONUS_BONUS] || _handled[MELEE_BONUS_BONUS];
	}

private:
	struct ScreenInfo
	{
		std::string name, menu, category;
		int fn;
	};
	struct Entry
	{
		std::string id, path, capsError;
		int api = 0;
		int caps = 0;
		std::unique_ptr<LuaSandbox> sandbox;
		bool notified = false;
		/// Queued by the running call, and by this turn of the battle: the budget of Lua does not see the engine's work.
		int callItems = 0, turnItems = 0, callUnits = 0, turnUnits = 0, callTiles = 0, turnTiles = 0, turn = -1;
		/// The same for screens: in a battle by its turn, outside it by the day.
		int callScreens = 0, periodScreens = 0, screenPeriod = -1;
		/// The same for soldiers, by the day.
		int callHires = 0, periodHires = 0, hirePeriod = -1;
		std::vector<ScreenInfo> screens;
	};
	struct Pending
	{
		size_t entry;
		const RuleItem *rule;
		int x, y, z, done;
		/// A hire instead of an item: it waits for a moment outside a battle.
		Base *base = nullptr;
		const RuleSoldier *soldier = nullptr;
		/// An item into this unit's inventory instead of the map.
		BattleUnit *unit = nullptr;
		/// This item out of the battle.
		BattleItem *item = nullptr;
		/// A new unit instead of an item, at x, y, z.
		const Unit *unitRule = nullptr;
		int faction = 0, direction = -1;
		/// A change of the tile at x, y, z instead of an item.
		MapOp mapOp = MAP_NONE;
		int part = 0, mapId = -1, mapSet = -1, mapValue = 0;
	};

	void fireOutputs(Event event, std::initializer_list<Arg> args, int *out);
	std::string queueBattleOp(const LuaSandbox *sandbox, const SavedBattleGame *battle, Pending op, const char *method);
	void runQueueNow(SavedBattleGame *battle, bool all);
	void runGeoscapeQueueNow(SavedGame *save);
	void endEconomy(const Entry &entry, size_t undo, bool failed);
	void dropQueued(size_t from);
	State *nextScreenNow();
	State *buildScreen(size_t entry, const ScreenInfo &screen);
	void callScreenFn(Entry &entry, int fn, const char *what, bool pure, void *call);
	void showNotice(SavedBattleGame *battle);
	void noteError(size_t entry, const std::string &event, const std::string &text);
	void writeJournal(const std::string &id, const std::string &event, const std::string &text);

	static LuaHost *_active;

	Mod *_mod = nullptr;
	std::vector<Entry> _entries;
	std::vector<Pending> _queue;
	std::vector<std::function<void()>> _undo;
	/// The screens asked for: the mod and the place in its Entry::screens.
	std::vector<std::pair<size_t, size_t>> _screens;
	bool _menuScreens = false;
	bool _handled[EVENT_COUNT] = { };
	std::string _notice, _journal;
};

}
