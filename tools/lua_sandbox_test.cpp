// Песочница Lua без загрузки игры: побег, зависания, память, ручки, скорость.
// Сборка и запуск: tools/lua_sandbox_test.ps1. Зависание ловит сторож и завершает прогон кодом 2.
#include "../src/Engine/LuaSandbox.h"
#include "../libs/lua/lua.h"
#include "../libs/lua/lauxlib.h"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>

using OpenXcom::LuaSandbox;
using Clock = std::chrono::steady_clock;

static std::atomic<const char*> g_current{ "" };
static std::atomic<long long> g_startMs{ 0 };
static long long nowMs()
{
	return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count();
}

static int g_failed = 0, g_passed = 0;
static std::string g_lastLog;

static LuaSandbox *make(const LuaSandbox::Limits &limits = {})
{
	return new LuaSandbox(limits, { "tick" }, [](const std::string &s) { g_lastLog = s; }, [](int a, int) { return a; });
}

struct Toy { int value = 7; };
static int toyGet(lua_State *L)
{
	lua_pushinteger(L, static_cast<Toy*>(LuaSandbox::checkObject(L, 1, "toy"))->value);
	return 1;
}
static const luaL_Reg TOY[] = { { "get", toyGet }, { nullptr, nullptr } };
static void setupToy(lua_State *L, void *) { LuaSandbox::defineType(L, "toy", TOY); }
static int pushToy(lua_State *L, void *data)
{
	LuaSandbox::pushObject(L, "toy", data);
	return 1;
}

enum Expect { CLEAN, ERROR_IN_HANDLER, LIMIT_HIT, LOAD_FAILS };

static int g_kept[8], g_keptCount = 0;
static int keepIt(lua_State *L)
{
	g_kept[g_keptCount++] = LuaSandbox::keep(L, 1);
	return 0;
}
static void setupKeep(lua_State *L, void *) { lua_register(L, "keepIt", keepIt); }

static void report(const char *name, bool ok, const char *why, long long ms)
{
	printf("%s  %-30s %5lld ms  %s\n", ok ? "PASS" : "FAIL", name, ms, ok ? "" : why);
	(ok ? g_passed : g_failed)++;
}

static void run(const char *name, const char *code, Expect expect)
{
	g_current = name;
	g_startMs = nowMs();
	const auto t0 = nowMs();
	LuaSandbox *s = make();
	Toy toy;
	s->setup(setupToy, nullptr);
	const bool loaded = s->load("main.lua", code);
	bool ok = false;
	const char *why = "";
	if (expect == LOAD_FAILS)
	{
		ok = !loaded;
		why = "загрузилось";
	}
	else if (!loaded)
	{
		why = g_lastLog.c_str();
	}
	else
	{
		s->fire("tick", pushToy, &toy);
		switch (expect)
		{
		case CLEAN:
			ok = s->errorCount() == 0;
			why = g_lastLog.c_str();
			break;
		case ERROR_IN_HANDLER:
			ok = s->errorCount() > 0 && s->limitCount() == 0;
			why = "ждали ошибку без лимита";
			break;
		case LIMIT_HIT:
			ok = s->limitCount() > 0;
			why = "лимит не сработал";
			break;
		default:
			break;
		}
	}
	report(name, ok, why, nowMs() - t0);
	delete s;
	g_current = "";
}

static void h(const char *name, const std::string &body, Expect expect)
{
	const std::string code = "game.on('tick', function(toy)\n" + body + "\nend)";
	run(name, code.c_str(), expect);
}

int main()
{
	std::thread([] {
		for (;;)
		{
			std::this_thread::sleep_for(std::chrono::milliseconds(200));
			const char *c = g_current;
			if (*c && nowMs() - g_startMs > 15000)
			{
				printf("ЗАВИСАНИЕ: %s\n", c);
				fflush(stdout);
				_Exit(2);
			}
		}
	}).detach();

	// побег
	h("no io/os/require/...", R"(assert(io==nil and os==nil and require==nil and package==nil and debug==nil and coroutine==nil
		and load==nil and loadfile==nil and dofile==nil and collectgarbage==nil and warn==nil
		and loadstring==nil and module==nil))", CLEAN);
	h("no string.dump, randomseed", "assert(string.dump==nil and math.randomseed==nil)", CLEAN);
	h("globals exactly the list", R"(local allow={assert=1,error=1,getmetatable=1,ipairs=1,next=1,pairs=1,pcall=1,print=1,rawequal=1,rawget=1,rawlen=1,
		rawset=1,select=1,setmetatable=1,tonumber=1,tostring=1,type=1,xpcall=1,_G=1,_VERSION=1,table=1,string=1,math=1,utf8=1,game=1}
		for k in pairs(_G) do assert(allow[k], k) end)", CLEAN);
	h("string metatable closed", "assert(getmetatable('')==false)", CLEAN);
	h("handle metatable closed", "assert(getmetatable(toy)==false)", CLEAN);
	h("__gc refused", "setmetatable({}, {__gc=function() end})", ERROR_IN_HANDLER);
	run("bytecode refused", "\x1bLuaT\0\x19\x93\r\n\x1a\n", LOAD_FAILS);
	run("game.on after load", "game.on('tick', function() game.on('tick', print) end)", ERROR_IN_HANDLER);
	h("unknown type of load", "assert(_ENV.load==nil)", CLEAN);
	run("unknown event", "game.on('nope', print)", LOAD_FAILS);
	run("syntax error", "if then", LOAD_FAILS);

	// зависания
	run("endless main.lua", "while true do end", LOAD_FAILS);
	h("while true", "while true do end", LIMIT_HIT);
	h("pcall does not save a loop", "while true do pcall(function() while true do end end) end", LIMIT_HIT);
	h("xpcall does not save a loop", "while true do xpcall(function() while true do end end, function() return 1 end) end", LIMIT_HIT);
	h("endless message handler", "xpcall(error, function() while true do end end)", LIMIT_HIT);
	h("tail recursion", "local function f() return f() end f()", LIMIT_HIT);
	h("exponential pcall", "local function f() pcall(f) pcall(f) end f()", LIMIT_HIT);
	h("metamethod loop", "local t t=setmetatable({}, {__index=function(_,k) while true do end end}) return t.x", LIMIT_HIT);
	h("__close loop", "local x <close> = setmetatable({}, {__close=function() while true do end end})", LIMIT_HIT);
	h("__tostring loop in error", "error(setmetatable({}, {__tostring=function() while true do end end}))", ERROR_IN_HANDLER);
	h("__tostring loop in print", "print(setmetatable({}, {__tostring=function() while true do end end}))", LIMIT_HIT);
	h("pattern backtracking", "string.rep('a',50000):find('.-.-.-.-.-.-.-.-x')", LIMIT_HIT);
	h("gsub backtracking", "string.gsub(string.rep('a',50000), '.-.-.-.-b', '')", LIMIT_HIT);
	h("string.rep of empty", "local s = string.rep('', 1000000000000000)", LIMIT_HIT);
	h("table.move huge", "table.move({}, 1, 1000000000000000, 2)", LIMIT_HIT);
	h("table.remove with __len", "table.remove(setmetatable({}, {__len=function() return 1000000000000000 end}), 1)", LIMIT_HIT);
	h("table.insert with __len", "table.insert(setmetatable({}, {__len=function() return 1000000000000000 end}), 1, 1)", LIMIT_HIT);
	h("table.concat via __index", "table.concat(setmetatable({}, {__index=function() return '' end}), '', 1, 1000000000000000)", LIMIT_HIT);
	h("sparse border table.remove", "local t={} for i=0,50 do t[1<<i]=1 end table.remove(t, 1)", CLEAN);
	// линейная работа за одну инструкцию: строка на 8 МБ, готовая ещё из main.lua
#define BIG "local a=string.rep('x',2000000) a=a..a a=a..a local b=string.rep('x',2000000) b=b..b b=b..b local t={[a]=1} "
	run("plain find in a loop", BIG "game.on('tick', function() while true do a:find('y',1,true) end end)", LIMIT_HIT);
	run("upper in a loop", BIG "game.on('tick', function() while true do local s=a:upper() end end)", LIMIT_HIT);
	run("sub in a loop", BIG "game.on('tick', function() while true do local s=a:sub(2) end end)", LIMIT_HIT);
	run("format in a loop", BIG "game.on('tick', function() while true do local s=string.format('%s',a) end end)", LIMIT_HIT);
	run("== in a loop", BIG "game.on('tick', function() while true do local e=a==b end end)", LIMIT_HIT);
	run("< in a loop", BIG "game.on('tick', function() while true do local e=a<b end end)", LIMIT_HIT);
	run("rawequal in a loop", BIG "game.on('tick', function() while true do rawequal(a,b) end end)", LIMIT_HIT);
	run("long key in a loop", BIG "game.on('tick', function() while true do local e=t[b] end end)", LIMIT_HIT);
	run("utf8.len in a loop", BIG "game.on('tick', function() while true do utf8.len(a) end end)", LIMIT_HIT);
	run("utf8.offset in a loop", BIG "game.on('tick', function() while true do utf8.offset(a,-1) end end)", LIMIT_HIT);
	run("tonumber in a loop", "local a=string.rep('1',2000000) a=a..a a=a..a game.on('tick', function() while true do tonumber(a) end end)", LIMIT_HIT);
	run("base tonumber in a loop", "local a=string.rep('1',2000000) a=a..a a=a..a game.on('tick', function() while true do tonumber(a,2) end end)", LIMIT_HIT);
	run("game.log in a loop", BIG "game.on('tick', function() while true do game.log(a) end end)", LIMIT_HIT);
	run("pack format in a loop", "local f=string.rep('b',2000000) f=f..f f=f..f game.on('tick', function() while true do pcall(string.packsize,f) end end)", LIMIT_HIT);
	run("almost fitting pattern", "local a=string.rep('x',1000000) a=a..a a=a..a a=a..a local p=string.rep('x',100000)..'y' game.on('tick', function() a:find(p,1,true) end)", LIMIT_HIT);
	h("a long numeral is not a number", "assert(tonumber(string.rep('1',2000))==nil and tonumber(string.rep('1',20))~=nil)", CLEAN);
	run("%b over a long string", "local a=string.rep('(',2000000) game.on('tick', function() a:find('%b()') end)", LIMIT_HIT);
	run("long set in a pattern", "local s='['..string.rep('a',1000000)..'b]' local a=string.rep('c',1000000) game.on('tick', function() a:find(s) end)", LIMIT_HIT);
	run("long set, greedy", "local s='['..string.rep('a',1000000)..'c]*d' local a=string.rep('c',1000000) game.on('tick', function() a:find(s) end)", LIMIT_HIT);
	run("__index chain in a loop", "local t={} for i=1,1900 do t=setmetatable({}, {__index=t}) end game.on('tick', function() while true do local e=t.x end end)", LIMIT_HIT);
	run("table.sort of a million", "local t={} for i=1,1000000 do t[i]=-i end game.on('tick', function() table.sort(t) end)", LIMIT_HIT);
	h("table.sort of a thousand", "local t={} for i=1,1000 do t[i]=-i end table.sort(t) assert(t[1]==-1000)", CLEAN);
	run("small strings stay free", "game.on('tick', function() for i=1,100000 do local s=('abc'..i):upper() assert(s~='') end end)", CLEAN);
#undef BIG

	// память и стек
	h("memory bomb", "local s='x' while true do s=s..s end", ERROR_IN_HANDLER);
	h("C loop limit on a long rep", "local t={} while true do t[#t+1]=string.rep('x',1000000) end", LIMIT_HIT);
	h("huge string.rep", "local s=string.rep('x',10000000000)", ERROR_IN_HANDLER);
	h("memory caught and looped", "while true do pcall(function() local t={} while true do t[#t+1]=string.rep('x',1000000) end end) end", LIMIT_HIT);
	h("stack overflow", "local function f() return 1+f() end f()", ERROR_IN_HANDLER);
	h("C stack overflow", "local t t=setmetatable({}, {__index=function(_,k) return t[k] end}) return t.x", ERROR_IN_HANDLER);
	h("pcall recursion", "local function f() pcall(f) end f()", CLEAN);
	h("error with a table", "error({})", ERROR_IN_HANDLER);
	h("error with nil", "error()", ERROR_IN_HANDLER);
	h("wrong handle type", "toy.get(1)", ERROR_IN_HANDLER);
	h("new game object forbidden", "local t=setmetatable({}, getmetatable(toy) or {}); assert(not pcall(toy.get, t))", CLEAN);

	// ручки, изоляция, отключение
	{
		g_current = "stale handle"; g_startMs = nowMs();
		LuaSandbox s({}, { "tick" }, [](const std::string &t) { g_lastLog = t; }, [](int a, int) { return a; });
		s.setup(setupToy, nullptr);
		s.load("main.lua", "local saved game.on('tick', function(toy) if saved then saved:get() end saved = toy end)");
		Toy toy;
		s.fire("tick", pushToy, &toy);
		const int first = s.errorCount();
		s.fire("tick", pushToy, &toy);
		report("stale handle gives an error", first == 0 && s.errorCount() == 1, "ждали одну ошибку на втором вызове", 0);
	}
	{
		g_current = "isolation"; g_startMs = nowMs();
		LuaSandbox a({}, { "tick" }, [](const std::string &) {}, [](int x, int) { return x; });
		LuaSandbox b({}, { "tick" }, [](const std::string &) {}, [](int x, int) { return x; });
		a.load("a.lua", "shared = 1; string.len = nil");
		b.load("b.lua", "game.on('tick', function() assert(shared == nil and string.len ~= nil) end)");
		b.fire("tick", nullptr, nullptr);
		report("two mods do not see each other", b.errorCount() == 0, "виден чужой глобал", 0);
	}
	{
		g_current = "next handler"; g_startMs = nowMs();
		LuaSandbox s({}, { "tick" }, [](const std::string &) {}, [](int x, int) { return x; });
		s.load("main.lua", "n=0 game.on('tick', function() error('x') end) game.on('tick', function() n=n+1 end) game.on('tick', function() assert(n==1) end)");
		s.fire("tick", nullptr, nullptr);
		report("error does not stop the next handler", s.errorCount() == 1, "ждали ровно одну ошибку", 0);
	}
	{
		g_current = "disable"; g_startMs = nowMs();
		LuaSandbox s({}, { "tick" }, [](const std::string &) {}, [](int x, int) { return x; });
		s.load("main.lua", "game.on('tick', function() error('x') end)");
		for (int i = 0; i < 20; ++i)
		{
			s.fire("tick", nullptr, nullptr);
		}
		report("off after errors in a row", s.isDisabled() && s.errorCount() == 5, "ждали выключение на пятой", 0);
	}
	{
		g_current = "log flood"; g_startMs = nowMs();
		int lines = 0;
		LuaSandbox s({}, { "tick" }, [&lines](const std::string &) { ++lines; }, [](int x, int) { return x; });
		s.load("main.lua", "game.on('tick', function() for i=1,100000 do print(i) end end)");
		s.fire("tick", nullptr, nullptr);
		report("log flood is cut", lines == 1000, "строк не 1000", 0);
	}
	{
		g_current = "determinism"; g_startMs = nowMs();
		const char *code = "local t={} for i=1,200 do t['k'..i]=i end local o={} for k in pairs(t) do o[#o+1]=k end game.log(table.concat(o,','))";
		std::string one, two;
		LuaSandbox a({}, {}, [&one](const std::string &t) { one = t; }, [](int x, int) { return x; });
		LuaSandbox b({}, {}, [&two](const std::string &t) { two = t; }, [](int x, int) { return x; });
		a.load("a.lua", code);
		b.load("b.lua", code);
		report("pairs order over strings", !one.empty() && one == two, "порядок разный", 0);
	}
	{
		g_current = "random"; g_startMs = nowMs();
		LuaSandbox s({}, { "tick" }, [](const std::string &) {}, [](int low, int) { return low; });
		s.load("main.lua", "game.on('tick', function() assert(math.random(5,9)==5 and math.random(3)==1 and math.random()==0.0); assert(not pcall(math.random,9,5)) end)");
		s.fire("tick", nullptr, nullptr);
		report("math.random goes to the game", !s.isDisabled() && s.errorCount() == 0, "не сошлось", 0);
		LuaSandbox t({}, { "tick" }, [](const std::string &) {}, [](int low, int) { return low; });
		report("math.random is refused while loading", !t.load("main.lua", "local x = math.random(5)"), "загрузка прошла", 0);
	}
	{
		g_current = "error callback"; g_startMs = nowMs();
		std::string where, what;
		LuaSandbox s({}, { "tick" }, [](const std::string &) {}, [](int x, int) { return x; });
		s.setErrorFn([&](const std::string &e, const std::string &t) { where = e; what = t; });
		s.load("main.lua", "game.on('tick', function() error('boom ' .. string.rep('x', 100000)) end)");
		s.fire("tick", nullptr, nullptr);
		report("error callback: handler, line, cut text", where == "tick" && what.find("main.lua:1: boom") == 0 && what.size() < 2100, what.substr(0, 60).c_str(), 0);
	}
	{
		g_current = "after callback"; g_startMs = nowMs();
		static int afterCalls;
		afterCalls = 0;
		LuaSandbox s({}, { "tick" }, [](const std::string &) {}, [](int x, int) { return x; });
		s.load("main.lua", "game.on('tick', function() end) game.on('tick', function() error('x') end) game.on('tick', function() end)");
		s.fire("tick", nullptr, nullptr, [](lua_State *, void *, std::string &e) { e = "bad out"; return ++afterCalls < 2; });
		report("after callback: not after a failed handler, its error counts", afterCalls == 2 && s.errorCount() == 2, "не сошлось", 0);
	}
	g_current = "";

	// скорость: одна и та же машина, числа для отчёта
	{
		auto t0 = nowMs();
		const int states = 100;
		for (int i = 0; i < states; ++i)
		{
			LuaSandbox s({}, { "tick" }, [](const std::string &) {}, [](int x, int) { return x; });
		}
		printf("speed  создание состояния: %.2f мс\n", double(nowMs() - t0) / states);

		LuaSandbox s({}, { "tick" }, [](const std::string &) {}, [](int x, int) { return x; });
		s.setup(setupToy, nullptr);
		printf("speed  память пустого состояния: %zu КБ\n", s.memoryUsed() / 1024);
		s.load("main.lua", "local n=0 game.on('tick', function(toy) n=n+toy:get() end)");
		Toy toy;
		const int calls = 2000000;
		auto t1 = Clock::now();
		for (int i = 0; i < calls; ++i)
		{
			s.fire("tick", pushToy, &toy);
		}
		auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - t1).count();
		printf("speed  вызов обработчика с одной ручкой и одним методом: %.0f нс\n", double(ns) / calls);
		t1 = Clock::now();
		for (int i = 0; i < calls * 10; ++i)
		{
			s.fire("nothing", pushToy, &toy);
		}
		ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - t1).count();
		printf("speed  событие без обработчиков: %.0f нс\n", double(ns) / (calls * 10));

		LuaSandbox w({}, { "tick" }, [](const std::string &) {}, [](int x, int) { return x; });
		w.load("main.lua", "game.on('tick', function() while true do end end)");
		t1 = Clock::now();
		g_current = "limit time"; g_startMs = nowMs();
		w.fire("tick", nullptr, nullptr);
		g_current = "";
		printf("speed  полный бюджет инструкций (%llu): %.2f мс\n", LuaSandbox::Limits{}.instructions,
			std::chrono::duration_cast<std::chrono::microseconds>(Clock::now() - t1).count() / 1000.0);

		LuaSandbox p({}, { "tick" }, [](const std::string &) {}, [](int x, int) { return x; });
		p.load("main.lua", "game.on('tick', function() string.rep('a',50000):find('.-.-.-.-x') end)");
		t1 = Clock::now();
		g_current = "tick time"; g_startMs = nowMs();
		p.fire("tick", nullptr, nullptr);
		g_current = "";
		printf("speed  полный бюджет циклов C (%llu): %.2f мс\n", LuaSandbox::Limits{}.cTicks,
			std::chrono::duration_cast<std::chrono::microseconds>(Clock::now() - t1).count() / 1000.0);
	}

	// функция мода на потом: очередь API 2
	{
		g_current = "kept call"; g_startMs = nowMs();
		const auto t0 = nowMs();
		LuaSandbox *s = make();
		Toy toy;
		s->setup(setupToy, nullptr);
		s->setup(setupKeep, nullptr);
		s->load("main.lua", "game.on('tick', function(toy)\n"
			"  keepIt(function(t) print('kept', t:get()) end)\n"
			"  keepIt(function(t) error('kept failed') end)\n"
			"  keepIt(function(t) while true do end end)\n"
			"  keepIt(function(t) print('dropped') end)\n"
			"end)");
		s->fire("tick", pushToy, &toy);
		s->callKept(g_kept[0], "done", pushToy, &toy);
		report("kept: called with a live handle", g_lastLog == "kept\t7" || g_lastLog == "kept 7", g_lastLog.c_str(), nowMs() - t0);
		const int errors = s->errorCount();
		s->callKept(g_kept[1], "done", pushToy, &toy);
		report("kept: error is the mod's error", s->errorCount() == errors + 1 && !s->isDisabled(), "", nowMs() - t0);
		s->callKept(g_kept[2], "done", pushToy, &toy);
		report("kept: endless loop is stopped", !s->isDisabled() && s->errorCount() >= errors + 1, "", nowMs() - t0);
		s->drop(g_kept[3]);
		delete s;
		g_keptCount = 0;
		s = make();
		s->setup(setupKeep, nullptr);
		s->load("main.lua", "local kept = false\ngame.on('tick', function()\n"
			"  if not kept then kept = true; keepIt(function() print('not called') end) end\n"
			"  error('always')\nend)");
		for (int i = 0; i < 1000 && !s->isDisabled(); ++i)
		{
			s->fire("tick", nullptr, nullptr);
		}
		g_lastLog.clear();
		s->callKept(g_kept[0], "done", nullptr, nullptr);
		report("kept: an off mod is not called", s->isDisabled() && g_lastLog.find("not called") == std::string::npos, g_lastLog.c_str(), nowMs() - t0);
		delete s;
		g_current = "";
	}

	printf("итог: PASS %d, FAIL %d\n", g_passed, g_failed);
	return g_failed ? 1 : 0;
}
