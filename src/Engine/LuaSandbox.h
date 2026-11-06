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
#include <functional>
#include <set>
#include <string>
#include <vector>

struct lua_State;

namespace OpenXcom
{

/**
 * One Lua state for one mod: no files, no network, no running programs, no bytecode, and a limit on
 * instructions, C loops and memory. Knows nothing of the game, so it is tested without loading it
 * (tools/lua_sandbox_test.cpp). The game's objects come in as handles valid for one fire().
 */
class LuaSandbox
{
public:
	struct Limits
	{
		size_t memoryBytes = 32 * 1024 * 1024;
		/// VM instructions for one fire(); the mod's main.lua gets ten times this.
		unsigned long long instructions = 2000000;
		/// Steps of C loops (patterns, string.rep, table.move...) for one fire().
		unsigned long long cTicks = 5000000;
		/// Errors in a row before the mod is switched off.
		int maxErrors = 5;
	};
	using TextFn = std::function<void(const std::string&)>;
	using RandomFn = std::function<int(int, int)>;
	/// Pushes the handler's arguments, returns how many. Runs protected.
	using PushFn = int (*)(lua_State *L, void *data);
	/// Runs protected, may use any of the Lua API.
	using SetupFn = void (*)(lua_State *L, void *data);
	/// Runs after a handler that did not fail, may only read. False: `error` counts as the handler's error.
	using AfterFn = bool (*)(lua_State *L, void *data, std::string &error);
	/// Where the error happened (handler name or main.lua) and its text with the traceback.
	using ErrorFn = std::function<void(const std::string &event, const std::string &text)>;

	LuaSandbox(const Limits &limits, const std::set<std::string> &events, TextFn log, RandomFn random);
	~LuaSandbox();
	LuaSandbox(const LuaSandbox&) = delete;
	LuaSandbox &operator=(const LuaSandbox&) = delete;

	void setErrorFn(ErrorFn fn) { _onError = std::move(fn); }
	/// Registers the game's types and whatever else the host needs. False if it failed.
	bool setup(SetupFn fn, void *data);
	/// Compiles (text only) and runs the mod's code. game.on() works only here.
	bool load(const std::string &chunkName, const std::string &code);
	/// Compiles (text only) in a state of its own and runs nothing: the error text, or empty.
	static std::string compileOnly(const std::string &chunkName, const std::string &code);
	/// Calls the event's handlers, cheap when there are none.
	void fire(const char *event, PushFn push, void *data, AfterFn after = nullptr);

	/// The mod is off: too many errors or it failed to load.
	bool isDisabled() const { return _disabled; }
	bool hasHandlers(const std::string &event) const { return _handled.count(event) != 0; }
	size_t memoryUsed() const { return _used; }
	/// Errors and limit hits since the start, for the tests.
	int errorCount() const { return _totalErrors; }
	int limitCount() const { return _totalLimits; }

	/// Defines a game type: a table of methods, closed to the mod. `regs` as for luaL_setfuncs.
	static void defineType(lua_State *L, const char *type, const void *regs);
	/// Pushes a handle to a game object.
	static void pushObject(lua_State *L, const char *type, void *object);
	/// The object behind a handle, or a Lua error when the handle is from an earlier call.
	static void *checkObject(lua_State *L, int index, const char *type);
	static LuaSandbox *from(lua_State *L);

	/// Used by the patched Lua C loops.
	void cTick(lua_State *L);
	/// Counts work the instruction counter does not see, in C loop steps.
	void charge(lua_State *L, unsigned long long ticks);

private:
	static void *alloc(void *ud, void *ptr, size_t osize, size_t nsize);
	static void countHook(lua_State *L, struct lua_Debug *ar);
	static int openLibs(lua_State *L);
	static int fireProtected(lua_State *L);
	static int messageHandler(lua_State *L);
	static int gameOn(lua_State *L);
	static int gameLog(lua_State *L);
	static int safePcall(lua_State *L);
	static int safeXpcall(lua_State *L);
	static int safeSetmetatable(lua_State *L);
	static int random(lua_State *L);
	static int runSetup(lua_State *L);

	void begin(unsigned long long instructions);
	void hitLimit(lua_State *L, const char *what);
	void noteError(const std::string &text);
	void writeLog(const std::string &text);

	Limits _limits;
	std::set<std::string> _events, _handled;
	TextFn _log;
	RandomFn _random;
	lua_State *_L = nullptr;
	size_t _used = 0;
	unsigned long long _steps = 0, _maxSteps = 0, _ticks = 0, _generation = 1;
	const char *_fireEvent = nullptr;
	PushFn _firePush = nullptr;
	AfterFn _fireAfter = nullptr;
	ErrorFn _onError;
	void *_fireData = nullptr;
	SetupFn _setupFn = nullptr;
	void *_setupData = nullptr;
	int _errorsInRow = 0, _totalErrors = 0, _totalLimits = 0, _logLeft = 1000;
	bool _limitHit = false, _loading = false, _inFire = false, _disabled = false, _anyError = false;
};

}
