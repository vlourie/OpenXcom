Lua 5.4.9, https://www.lua.org/ftp/lua-5.4.9.tar.gz
373429 bytes, sha256 2335b6c582a52654f94612bf10d2f4672805d05329aa6568b1d8cd9e5c6fb8e6
MIT licence, see the end of lua.h.

Built as one C++ file, oxce_lua.cpp. Left out of this copy: lua.c, luac.c, liolib.c, loslib.c,
loadlib.c, ldblib.c, lcorolib.c, linit.c.

Local changes, all marked OXCE in the source: oxce_c_tick(L) in C loops the VM count hook does not
see. Without them a mod could hang the game inside one call.
  lstrlib.c  match(), str_rep()
  ltablib.c  tinsert(), tremove(), tmove() (two loops), tconcat()
And luaconf.h: LUAI_MAXSTACK is smaller, a stack overflow is the one error slow enough to feel.
