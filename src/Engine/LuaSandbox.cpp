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
#include "LuaSandbox.h"
#include <climits>
#include <cstdlib>
#include <cstring>
#include "../../libs/lua/lua.h"
#include "../../libs/lua/lualib.h"
#include "../../libs/lua/lauxlib.h"

void oxce_lua_c_tick(lua_State *L)
{
	OpenXcom::LuaSandbox::from(L)->cTick(L);
}

void oxce_lua_c_bytes(size_t bytes)
{
	OpenXcom::LuaSandbox::chargeBytes(bytes);
}

namespace OpenXcom
{

LuaSandbox *LuaSandbox::_running = nullptr;

namespace
{

const int HOOK_EVERY = 1000;
/// What a C loop step is worth in copied or compared bytes, by measure (tools/lua_sandbox_test.cpp).
const size_t BYTES_PER_TICK = 64;
const char *const HANDLERS_KEY = "oxce.handlers";
/// What a pcall costs, in C loop steps by measure (tools/lua_sandbox_test.cpp): an error unwinds with a C++ exception.
const unsigned long long PCALL_TICKS = 50, PCALL_ERROR_TICKS = 5000;
const size_t ERROR_TEXT_MAX = 2000, LOG_LINE_MAX = 4000;

/// A handle to a game object: valid only inside the fire() that made it.
struct Handle
{
	void *object;
	unsigned long long generation;
};

/// All that is left of the base library. Everything else in it reaches files or the collector.
const char *const BASE_ALLOWED[] = {
	"assert", "error", "getmetatable", "ipairs", "next", "pairs", "pcall", "print", "rawequal", "rawget", "rawlen",
	"rawset", "select", "setmetatable", "tonumber", "tostring", "type", "xpcall", "_G", "_VERSION", nullptr
};

bool isBaseAllowed(const char *name)
{
	for (auto *const *a = BASE_ALLOWED; *a; ++a)
	{
		if (!strcmp(*a, name))
		{
			return true;
		}
	}
	return false;
}

}

LuaSandbox *LuaSandbox::from(lua_State *L)
{
	return *static_cast<LuaSandbox**>(lua_getextraspace(L));
}

void *LuaSandbox::alloc(void *ud, void *ptr, size_t osize, size_t nsize)
{
	auto *self = static_cast<LuaSandbox*>(ud);
	const size_t old = ptr ? osize : 0;
	if (nsize == 0)
	{
		free(ptr);
		self->_used -= old;
		return nullptr;
	}
	if (self->_used - old + nsize > self->_limits.memoryBytes)
	{
		return nullptr; // Lua collects garbage and tries once more, then it is a memory error
	}
	if (nsize > old)
	{
		// the copy behind a new string: one instruction to the counter, an error here is the only way to stop it in time
		self->_ticks += (nsize - old) / BYTES_PER_TICK;
		if (self->_ticks > self->_limits.cTicks)
		{
			if (!self->_limitHit)
			{
				self->_limitHit = true;
				++self->_totalLimits;
			}
			return nullptr;
		}
	}
	void *result = realloc(ptr, nsize);
	if (result)
	{
		self->_used += nsize - old;
	}
	return result;
}

void LuaSandbox::countHook(lua_State *L, lua_Debug *)
{
	auto *self = from(L);
	if (++self->_steps > self->_maxSteps)
	{
		self->hitLimit(L, "instruction limit");
	}
	if (self->_ticks > self->_limits.cTicks)
	{
		self->hitLimit(L, "C loop limit");
	}
}

void LuaSandbox::chargeBytes(size_t bytes)
{
	if (_running)
	{
		_running->_ticks += bytes / BYTES_PER_TICK;
	}
}

void LuaSandbox::cTick(lua_State *L)
{
	if (++_ticks > _limits.cTicks)
	{
		hitLimit(L, "C loop limit");
	}
}

void LuaSandbox::charge(lua_State *L, unsigned long long ticks)
{
	_ticks += ticks;
	if (_ticks > _limits.cTicks)
	{
		hitLimit(L, "C loop limit");
	}
}

void LuaSandbox::hitLimit(lua_State *L, const char *what)
{
	if (!_limitHit)
	{
		_limitHit = true;
		++_totalLimits;
	}
	luaL_error(L, "%s", what);
}

/// pcall that a limit passes through: otherwise `while true do pcall(loop) end` never ends.
int LuaSandbox::safePcall(lua_State *L)
{
	luaL_checkany(L, 1);
	from(L)->charge(L, PCALL_TICKS);
	const int status = lua_pcall(L, lua_gettop(L) - 1, LUA_MULTRET, 0);
	if (from(L)->_limitHit)
	{
		return luaL_error(L, "limit");
	}
	if (status != LUA_OK)
	{
		from(L)->charge(L, PCALL_ERROR_TICKS);
		lua_pushboolean(L, 0);
		lua_insert(L, -2);
		return 2;
	}
	lua_pushboolean(L, 1);
	lua_insert(L, 1);
	return lua_gettop(L);
}

/// xpcall whose handler runs after the unwinding, not as Lua's message handler: an error raised by the
/// count hook leaves the hook off until the pcall catches it, so an endless handler would be out of reach.
int LuaSandbox::safeXpcall(lua_State *L)
{
	luaL_checktype(L, 2, LUA_TFUNCTION);
	from(L)->charge(L, PCALL_TICKS);
	const int args = lua_gettop(L) - 2;
	lua_pushvalue(L, 2);
	lua_insert(L, 1); // handler, function, handler, args
	lua_remove(L, 3);
	const int status = lua_pcall(L, args, LUA_MULTRET, 0);
	if (from(L)->_limitHit)
	{
		return luaL_error(L, "limit");
	}
	if (status == LUA_OK)
	{
		lua_pushboolean(L, 1);
		lua_replace(L, 1);
		return lua_gettop(L);
	}
	from(L)->charge(L, PCALL_ERROR_TICKS);
	lua_pcall(L, 1, 1, 0);
	if (from(L)->_limitHit)
	{
		return luaL_error(L, "limit");
	}
	lua_pushboolean(L, 0);
	lua_insert(L, -2);
	return 2;
}

/// Finalizers run with the count hook off: an endless __gc would be out of reach of any limit.
int LuaSandbox::safeSetmetatable(lua_State *L)
{
	if (lua_istable(L, 2))
	{
		lua_pushliteral(L, "__gc");
		const bool hasGc = lua_rawget(L, 2) != LUA_TNIL;
		lua_pop(L, 1);
		if (hasGc)
		{
			return luaL_error(L, "__gc is not allowed");
		}
	}
	lua_pushvalue(L, lua_upvalueindex(1));
	lua_pushvalue(L, 1);
	lua_pushvalue(L, 2);
	lua_call(L, 2, 1);
	return 1;
}

/// math.random on the game's generator: no clock, and one seed gives one battle.
int LuaSandbox::random(lua_State *L)
{
	auto *self = from(L);
	if (self->_loading)
	{
		// main.lua runs at every load of a save and at Ctrl+F5: it would move the game's random numbers
		return luaL_error(L, "math.random is not available while main.lua loads, call it in a handler");
	}
	if (self->_noRandom)
	{
		return luaL_error(L, "no random numbers in this handler: it is called from lists, tooltips and the frame, and would move the game's generator");
	}
	lua_Integer low = 1, high = 0;
	switch (lua_gettop(L))
	{
	case 0:
		lua_pushnumber(L, self->_random(0, 999999999) / 1e9);
		return 1;
	case 1:
		high = luaL_checkinteger(L, 1);
		break;
	case 2:
		low = luaL_checkinteger(L, 1);
		high = luaL_checkinteger(L, 2);
		break;
	default:
		return luaL_error(L, "wrong number of arguments");
	}
	luaL_argcheck(L, low <= high, lua_gettop(L), "interval is empty");
	luaL_argcheck(L, low >= INT_MIN && high <= INT_MAX, 1, "interval is too wide");
	lua_pushinteger(L, self->_random((int)low, (int)high));
	return 1;
}

int LuaSandbox::gameLog(lua_State *L)
{
	std::string text;
	const int n = lua_gettop(L);
	for (int i = 1; i <= n; ++i)
	{
		size_t len = 0;
		const char *s = luaL_tolstring(L, i, &len);
		from(L)->charge(L, len / BYTES_PER_TICK);
		if (i > 1)
		{
			text += ' ';
		}
		text.append(s, len);
		lua_pop(L, 1);
	}
	from(L)->writeLog(text);
	return 0;
}

int LuaSandbox::gameOn(lua_State *L)
{
	auto *self = from(L);
	const char *event = luaL_checkstring(L, 1);
	luaL_checktype(L, 2, LUA_TFUNCTION);
	if (!self->_loading)
	{
		return luaL_error(L, "game.on works only while main.lua loads");
	}
	if (!self->_events.count(event))
	{
		return luaL_error(L, "unknown event '%s'", event);
	}
	lua_getfield(L, LUA_REGISTRYINDEX, HANDLERS_KEY);
	if (lua_getfield(L, -1, event) == LUA_TNIL)
	{
		lua_pop(L, 1);
		lua_newtable(L);
		lua_pushvalue(L, -1);
		lua_setfield(L, -3, event);
	}
	lua_pushvalue(L, 2);
	lua_rawseti(L, -2, lua_rawlen(L, -2) + 1);
	self->_handled.insert(event);
	return 0;
}

int LuaSandbox::openLibs(lua_State *L)
{
	static const luaL_Reg libs[] = {
		{ LUA_GNAME, luaopen_base },
		{ LUA_TABLIBNAME, luaopen_table },
		{ LUA_STRLIBNAME, luaopen_string },
		{ LUA_MATHLIBNAME, luaopen_math },
		{ LUA_UTF8LIBNAME, luaopen_utf8 },
		{ nullptr, nullptr }
	};
	for (const luaL_Reg *lib = libs; lib->func; ++lib)
	{
		luaL_requiref(L, lib->name, lib->func, 1);
		lua_pop(L, 1);
	}

	// base: only what is on the list
	std::vector<std::string> extra;
	lua_pushglobaltable(L);
	lua_pushnil(L);
	while (lua_next(L, -2))
	{
		lua_pop(L, 1);
		if (lua_type(L, -1) == LUA_TSTRING && !isBaseAllowed(lua_tostring(L, -1)) && strcmp(lua_tostring(L, -1), LUA_TABLIBNAME)
			&& strcmp(lua_tostring(L, -1), LUA_STRLIBNAME) && strcmp(lua_tostring(L, -1), LUA_MATHLIBNAME) && strcmp(lua_tostring(L, -1), LUA_UTF8LIBNAME))
		{
			extra.push_back(lua_tostring(L, -1));
		}
	}
	for (const auto &name : extra)
	{
		lua_pushnil(L);
		lua_setfield(L, -2, name.c_str());
	}
	lua_pushcfunction(L, safePcall);
	lua_setfield(L, -2, "pcall");
	lua_pushcfunction(L, safeXpcall);
	lua_setfield(L, -2, "xpcall");
	lua_pushcfunction(L, gameLog);
	lua_setfield(L, -2, "print");
	lua_getfield(L, -1, "setmetatable");
	lua_pushcclosure(L, safeSetmetatable, 1);
	lua_setfield(L, -2, "setmetatable");

	// the libraries above are registered in package.loaded too: nothing reaches it, the registry is closed
	lua_getfield(L, -1, LUA_STRLIBNAME);
	lua_pushnil(L);
	lua_setfield(L, -2, "dump");
	lua_pop(L, 1);

	lua_getfield(L, -1, LUA_MATHLIBNAME);
	lua_pushnil(L);
	lua_setfield(L, -2, "randomseed");
	lua_pushcfunction(L, random);
	lua_setfield(L, -2, "random");
	lua_pop(L, 1);

	// strings share one metatable: closed, a mod would see it through getmetatable("")
	lua_pushliteral(L, "");
	lua_getmetatable(L, -1);
	lua_pushboolean(L, 0);
	lua_setfield(L, -2, "__metatable");
	lua_pop(L, 2);

	lua_newtable(L);
	lua_setfield(L, LUA_REGISTRYINDEX, HANDLERS_KEY);

	lua_newtable(L);
	lua_pushcfunction(L, gameOn);
	lua_setfield(L, -2, "on");
	lua_pushcfunction(L, gameLog);
	lua_setfield(L, -2, "log");
	lua_setfield(L, -2, "game");

	lua_pop(L, 1);
	return 0;
}

LuaSandbox::LuaSandbox(const Limits &limits, const std::set<std::string> &events, TextFn log, RandomFn random)
	: _limits(limits), _events(events), _log(std::move(log)), _random(std::move(random))
{
	_L = lua_newstate(alloc, this);
	if (!_L)
	{
		_disabled = true;
		return;
	}
	*static_cast<LuaSandbox**>(lua_getextraspace(_L)) = this;
	lua_sethook(_L, reinterpret_cast<lua_Hook>(countHook), LUA_MASKCOUNT, HOOK_EVERY);
	begin(_limits.instructions);
	lua_pushcfunction(_L, openLibs);
	if (lua_pcall(_L, 0, 0, 0) != LUA_OK)
	{
		writeLog(std::string("cannot open the libraries: ") + lua_tostring(_L, -1));
		lua_pop(_L, 1);
		_disabled = true;
	}
}

LuaSandbox::~LuaSandbox()
{
	if (_running == this)
	{
		_running = nullptr;
	}
	if (_L)
	{
		lua_close(_L);
	}
}

void LuaSandbox::begin(unsigned long long instructions)
{
	_running = this;
	_steps = 0;
	_maxSteps = instructions / HOOK_EVERY;
	_ticks = 0;
	_limitHit = false;
	_anyError = false;
}

void LuaSandbox::writeLog(const std::string &text)
{
	if (_logLeft > 0)
	{
		--_logLeft;
		const std::string line = text.size() > LOG_LINE_MAX ? text.substr(0, LOG_LINE_MAX) + "..." : text;
		_log(_logLeft > 0 ? line : line + " (log limit reached, the rest is dropped)");
	}
}

void LuaSandbox::noteError(const std::string &text)
{
	_anyError = true;
	++_totalErrors;
	const std::string cut = text.size() > ERROR_TEXT_MAX ? text.substr(0, ERROR_TEXT_MAX) + "..." : text;
	writeLog("error: " + cut);
	if (_onError)
	{
		_onError(_fireEvent ? _fireEvent : "main.lua", cut);
	}
}

int LuaSandbox::messageHandler(lua_State *L)
{
	const char *text = lua_tostring(L, 1);
	// not luaL_tolstring: a mod's __tostring is more of its code, here in the middle of an error
	luaL_traceback(L, L, text ? text : "(the error is not a string)", 1);
	return 1;
}

int LuaSandbox::runSetup(lua_State *L)
{
	auto *self = from(L);
	self->_setupFn(L, self->_setupData);
	return 0;
}

bool LuaSandbox::setup(SetupFn fn, void *data)
{
	if (_disabled)
	{
		return false;
	}
	_setupFn = fn;
	_setupData = data;
	begin(_limits.instructions);
	lua_pushcfunction(_L, runSetup);
	if (lua_pcall(_L, 0, 0, 0) != LUA_OK)
	{
		writeLog(std::string("cannot set up: ") + lua_tostring(_L, -1));
		lua_pop(_L, 1);
		_disabled = true;
		return false;
	}
	return true;
}

bool LuaSandbox::load(const std::string &chunkName, const std::string &code)
{
	if (_disabled)
	{
		return false;
	}
	begin(_limits.instructions * 10);
	_loading = true;
	lua_pushcfunction(_L, messageHandler);
	// "t": text only, bytecode is the classic way out of a Lua sandbox
	int status = luaL_loadbufferx(_L, code.data(), code.size(), ("@" + chunkName).c_str(), "t");
	if (status == LUA_OK)
	{
		status = lua_pcall(_L, 0, 0, -2);
	}
	_loading = false;
	if (status != LUA_OK)
	{
		const char *text = lua_tostring(_L, -1);
		noteError(text ? text : "unknown error");
		lua_pop(_L, 1);
		_disabled = true;
	}
	lua_pop(_L, 1);
	return !_disabled;
}

std::string LuaSandbox::compileOnly(const std::string &chunkName, const std::string &code)
{
	lua_State *L = luaL_newstate();
	if (!L)
	{
		return "cannot create a Lua state";
	}
	std::string error;
	if (luaL_loadbufferx(L, code.data(), code.size(), ("@" + chunkName).c_str(), "t") != LUA_OK)
	{
		const char *text = lua_tostring(L, -1);
		error = text ? text : "unknown error";
	}
	lua_close(L);
	return error;
}

int LuaSandbox::fireProtected(lua_State *L)
{
	auto *self = from(L);
	lua_getfield(L, LUA_REGISTRYINDEX, HANDLERS_KEY);
	lua_getfield(L, -1, self->_fireEvent);
	const lua_Integer count = lua_rawlen(L, -1);
	for (lua_Integer i = 1; i <= count && !self->_limitHit; ++i)
	{
		lua_pushcfunction(L, messageHandler);
		const int handler = lua_gettop(L);
		lua_rawgeti(L, -2, i);
		const int args = self->_firePush ? self->_firePush(L, self->_fireData) : 0;
		if (lua_pcall(L, args, 0, handler) != LUA_OK)
		{
			const char *text = lua_tostring(L, -1);
			self->noteError(text ? text : "unknown error");
			lua_pop(L, 1);
		}
		else if (self->_fireAfter)
		{
			std::string error;
			if (!self->_fireAfter(L, self->_fireData, error))
			{
				self->noteError(error);
			}
		}
		lua_pop(L, 1);
	}
	return 0;
}

void LuaSandbox::fire(const char *event, PushFn push, void *data, AfterFn after)
{
	if (_disabled || _inFire || !_handled.count(event))
	{
		return;
	}
	_inFire = true;
	// a formula reached from another mod's handler: that one goes on counting after this
	LuaSandbox *const outer = _running;
	begin(_limits.instructions);
	_fireEvent = event;
	_firePush = push;
	_fireData = data;
	_fireAfter = after;
	lua_pushcfunction(_L, fireProtected);
	if (lua_pcall(_L, 0, 0, 0) != LUA_OK)
	{
		const char *text = lua_tostring(_L, -1);
		noteError(text ? text : "unknown error");
		lua_pop(_L, 1);
	}
	++_generation; // every handle given out here is dead now
	_inFire = false;
	_running = outer;
	if (_anyError)
	{
		if (++_errorsInRow >= _limits.maxErrors)
		{
			_disabled = true;
			const std::string text = "too many errors in a row, the mod is off until its Lua is reloaded";
			writeLog(text);
			if (_onError)
			{
				_onError(event, text);
			}
		}
	}
	else
	{
		_errorsInRow = 0;
	}
}

void LuaSandbox::defineType(lua_State *L, const char *type, const void *regs)
{
	luaL_newmetatable(L, type);
	lua_newtable(L);
	luaL_setfuncs(L, static_cast<const luaL_Reg*>(regs), 0);
	lua_setfield(L, -2, "__index");
	lua_pushboolean(L, 0);
	lua_setfield(L, -2, "__metatable");
	lua_pop(L, 1);
}

void LuaSandbox::pushObject(lua_State *L, const char *type, void *object)
{
	auto *handle = static_cast<Handle*>(lua_newuserdatauv(L, sizeof(Handle), 0));
	handle->object = object;
	handle->generation = from(L)->_generation;
	luaL_setmetatable(L, type);
}

void *LuaSandbox::checkObject(lua_State *L, int index, const char *type)
{
	auto *handle = static_cast<Handle*>(luaL_checkudata(L, index, type));
	if (handle->generation != from(L)->_generation)
	{
		luaL_error(L, "%s is valid only inside the handler that received it", type);
	}
	return handle->object;
}

}
