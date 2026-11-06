// Lua 5.4.9 as one translation unit, compiled as C++: errors are exceptions, so they unwind
// through engine code instead of a longjmp past its destructors. Only the libraries the sandbox
// allows are here: io, os, package, debug and coroutine are not even linked (see README.txt).
#include "lprefix.h"

#include <assert.h>
#include <ctype.h>
#include <errno.h>
#include <float.h>
#include <limits.h>
#include <locale.h>
#include <math.h>
#include <setjmp.h>
#include <signal.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// the same string hashes in every run: pairs() over string keys keeps its order
#define luai_makeseed(L) 0x4f584345u

#define LUA_CORE
#define LUA_LIB
#define ltable_c
#define lvm_c
#include "luaconf.h"

#include "lua.h"
#include "lualib.h"
#include "lauxlib.h"

// C loops the VM count hook never sees: defined in src/Engine/LuaSandbox.cpp
void oxce_lua_c_tick(lua_State *L);
#define oxce_c_tick(L) oxce_lua_c_tick(L)
// work in proportion to bytes: added up now, the limit is checked at the next tick or by the VM hook
void oxce_lua_c_bytes(size_t bytes);
#define oxce_c_bytes(n) oxce_lua_c_bytes((size_t)(n))
#define oxce_c_work(L, n) (oxce_c_bytes(n), oxce_c_tick(L))

#include "lzio.c"
#include "lctype.c"
#include "lopcodes.c"
#include "lmem.c"
#include "lundump.c"
#include "ldump.c"
#include "lstate.c"
#include "lgc.c"
#include "llex.c"
#include "lcode.c"
#include "lparser.c"
#include "ldebug.c"
#include "lfunc.c"
#include "lobject.c"
#include "ltm.c"
#include "lstring.c"
#include "ltable.c"
#include "ldo.c"
#include "lvm.c"
#include "lapi.c"
#include "lauxlib.c"
#include "lbaselib.c"
#include "lstrlib.c"
#include "ltablib.c"
#include "lmathlib.c"
#include "lutf8lib.c"
