# Песочница Lua без загрузки игры: собрать tools/lua_sandbox_test.cpp и прогнать. Секунды, а не минуты.
$root = Split-Path $PSScriptRoot -Parent
$env:Path = "C:\msys64\mingw64\bin;$env:Path"
$out = Join-Path $env:TEMP "lua_sandbox_test"
New-Item -ItemType Directory -Force $out | Out-Null
$lua = Join-Path $out "oxce_lua.o"
if (-not (Test-Path $lua) -or (Get-ChildItem "$root\libs\lua" | Where-Object { $_.LastWriteTime -gt (Get-Item $lua).LastWriteTime })) {
    & g++ -std=c++17 -O2 -c "$root\libs\lua\oxce_lua.cpp" -o $lua
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
}
& g++ -std=c++17 -O2 -Wall -Wextra "$root\tools\lua_sandbox_test.cpp" "$root\src\Engine\LuaSandbox.cpp" $lua -static -o "$out\test.exe"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& "$out\test.exe"
exit $LASTEXITCODE
