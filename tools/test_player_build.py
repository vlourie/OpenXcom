"""Сборка игроков без стенда ИИ (грабли R-336): tools/build/build.ps1 и Выпуск/release.ps1.

Функции берутся из самих скриптов разбором AST и гоняются в Windows PowerShell 5.1 (powershell.exe)
на поддельных папках сборки во временной папке; cmake подменён заглушкой, которая пишет в кэш OFF:
- кэш OFF, 0, NO, без строки - сборка идёт, cmake не зовётся;
- кэш ON, 1, TRUE с -NoNinja (чинить нечем) - сборка стоит;
- кэш ON без -NoNinja - cmake зовётся с -DOXCE_AI_DEV=OFF, после него OFF;
- контроль: заглушка cmake кэш не меняет - сборка стоит («по-прежнему»);
- exe со строкой стенда - build.ps1 (Assert-ExeNoBench) и release.ps1 (Get-BenchMark) его ловят, без строки - нет.
На настоящих данных печатает OXCE_AI_DEV из build-release/CMakeCache.txt и строку стенда в exe стейджа.

    py -3.13 tools/test_player_build.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "tools" / "build" / "build.ps1"
REL = ROOT / "Выпуск" / "release.ps1"
ENC_W = "utf-8-sig"
MARK = "[AIPROBE] start"

RUNNER = r"""
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
Write-Output ("PSVER " + $PSVersionTable.PSVersion.Major + "." + $PSVersionTable.PSVersion.Minor)
foreach ($file in @($env:BUILD, $env:REL)) {
    $errs = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($file, [ref]$null, [ref]$errs)
    if ($errs.Count) { throw ("$file не разбирается: " + $errs[0].Message) }
    foreach ($f in $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
        . ([scriptblock]::Create($f.Extent.Text))
    }
    foreach ($a in $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.AssignmentStatementAst] -and
                                  $args[0].Left.Extent.Text -eq '$BenchMarks' }, $false)) {
        . ([scriptblock]::Create($a.Extent.Text))
    }
}
function Write-Ok([string]$t) {}
function Write-Warn([string]$t) {}
function Get-Cfg([string]$name, $default) { return $default }
function Find-Tool($c, $cands, $n) { return 'cmake-stub' }
$script:cmakeArgs = ''
function Invoke-Native([string]$exe, [string[]]$argList) {
    $script:cmakeArgs = $argList -join ' '
    if ($env:STUB_NOOP -ne '1') {
        $cache = Join-Path $argList[-1] 'CMakeCache.txt'
        $t = [IO.File]::ReadAllText($cache) -replace '(?m)^OXCE_AI_DEV:BOOL=.*$', 'OXCE_AI_DEV:BOOL=OFF'
        [IO.File]::WriteAllText($cache, $t)
    }
    return 0
}
foreach ($case in Get-ChildItem -LiteralPath $env:WORK -Directory | Where-Object { $_.Name -like 'c_*' }) {
    $canFix = $case.Name -notlike '*_nofix'
    $script:cmakeArgs = ''
    try { Set-PlayerBuild $case.FullName $canFix; $r = 'go' } catch { $r = 'stop: ' + $_.Exception.Message }
    $after = Get-CacheValue $case.FullName 'OXCE_AI_DEV'
    Write-Output ("CASE " + $case.Name + " | " + $r.Split(' ')[0].TrimEnd(':') + " | cmake=" + $script:cmakeArgs.Split(' ')[0] + " | after=" + $after + " | " + $r)
}
foreach ($exe in Get-ChildItem -LiteralPath (Join-Path $env:WORK 'exe') -File) {
    try { Assert-ExeNoBench $exe.FullName; $b = 'go' } catch { $b = 'stop' }
    Write-Output ("EXE " + $exe.Name + " | build=" + $b + " | release=" + (Get-BenchMark $exe.FullName))
}
if ($env:REAL_EXE) { Write-Output ("REAL exe | release=" + (Get-BenchMark $env:REAL_EXE)) }
Write-Output ("REAL cache | " + (Get-CacheValue $env:REAL_BUILD 'OXCE_AI_DEV'))
"""

CACHES = {  # имя папки: строка в кэше (None - строки нет); _nofix - сборка с -NoNinja
    "c_off": "OXCE_AI_DEV:BOOL=OFF", "c_zero": "OXCE_AI_DEV:BOOL=0", "c_no": "OXCE_AI_DEV:BOOL=NO",
    "c_missing": None,
    "c_on_nofix": "OXCE_AI_DEV:BOOL=ON", "c_one_nofix": "OXCE_AI_DEV:BOOL=1", "c_true_nofix": "OXCE_AI_DEV:BOOL=TRUE",
    "c_on": "OXCE_AI_DEV:BOOL=ON", "c_one": "OXCE_AI_DEV:BOOL=1",
}
# ожидание: (go/stop, позвали ли cmake, значение после)
WANT = {
    "c_off": ("go", "", "OFF"), "c_zero": ("go", "", "0"), "c_no": ("go", "", "NO"), "c_missing": ("go", "", ""),
    "c_on_nofix": ("stop", "", "ON"), "c_one_nofix": ("stop", "", "1"), "c_true_nofix": ("stop", "", "TRUE"),
    "c_on": ("go", "-DOXCE_AI_DEV=OFF", "OFF"), "c_one": ("go", "-DOXCE_AI_DEV=OFF", "OFF"),
}


def run(work, noop=False):
    env = dict(os.environ, BUILD=str(BUILD), REL=str(REL), WORK=str(work), STUB_NOOP="1" if noop else "0",
               REAL_BUILD=str(ROOT / "build-release"))
    stage = ROOT / "dist" / "_stage" / "openxcom_hd.exe"
    if stage.exists():
        env["REAL_EXE"] = str(stage)
    ps1 = Path(work) / "runner.ps1"
    ps1.write_text(RUNNER, encoding=ENC_W)
    p = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
                       capture_output=True, env=env)
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode:
        print(out, p.stderr.decode("utf-8", "replace"))
        raise SystemExit("powershell упал")
    return out


def make(work):
    for name, line in CACHES.items():
        d = Path(work) / name
        d.mkdir()
        body = "# This is the CMakeCache file.\nCMAKE_BUILD_TYPE:STRING=Release\n"
        if line:
            body += line + "\n"
        (d / "CMakeCache.txt").write_text(body + "OXCE_HD:BOOL=ON\n", encoding="utf-8")
    e = Path(work) / "exe"
    e.mkdir()
    pad = bytes(range(256)) * 4096
    (e / "bench.exe").write_bytes(b"MZ" + pad + MARK.encode() + b": turn " + pad)
    (e / "player.exe").write_bytes(b"MZ" + pad + b"[AIPROBE] sta" + pad)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fails = []
    with tempfile.TemporaryDirectory() as work:
        make(work)
        out = run(work)
        print(next(l for l in out.splitlines() if l.startswith("PSVER")))
        got = {}
        for l in out.splitlines():
            if l.startswith("CASE "):
                f = [x.strip() for x in l[5:].split("|")]
                got[f[0]] = (f[1], f[2][len("cmake="):], f[3][len("after="):])
                print(" ", l[:160])
        for k, w in WANT.items():
            if got.get(k) != w:
                fails.append("%s: ждали %s, вышло %s" % (k, w, got.get(k)))
        exe = {l.split()[1]: l for l in out.splitlines() if l.startswith("EXE ")}
        for l in exe.values():
            print(" ", l)
        if "build=stop" not in exe.get("bench.exe", "") or MARK not in exe.get("bench.exe", ""):
            fails.append("exe со строкой стенда не пойман")
        if "build=go" not in exe.get("player.exe", "") or not exe.get("player.exe", "").rstrip().endswith("release="):
            fails.append("exe без строки стенда остановлен")
        for l in out.splitlines():
            if l.startswith("REAL"):
                print("  настоящие данные:", l)
    # контроль: cmake не изменил кэш - сборка обязана стоять
    with tempfile.TemporaryDirectory() as work:
        make(work)
        out = run(work, noop=True)
        ctl = [l for l in out.splitlines() if l.startswith("CASE c_on ")]
        print("  контроль (cmake не меняет кэш):", ctl[0][:120] if ctl else "нет строки")
        if not ctl or "| stop |" not in ctl[0] or "по-прежнему" not in ctl[0]:
            fails.append("контроль: кэш остался ON, а сборка пошла")
    if fails:
        print("ПРОВАЛ:\n  " + "\n  ".join(fails))
        return 1
    print("OK: сборка игроков без стенда ИИ - кэш и exe проверяются")
    return 0


if __name__ == "__main__":
    sys.exit(main())
