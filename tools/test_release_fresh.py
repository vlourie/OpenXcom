"""Выпуск/release.ps1, проверка свежести стейджа перед nobuild (грабли R-044): Get-StaleBuildFiles.

Функции берутся из самого release.ps1 разбором AST и гоняются в Windows PowerShell 5.1 (powershell.exe)
на поддельном дереве во временной папке:
- новый .cpp и .h новее exe - выпуск стоит;
- посторонний файл в src (txt, png) новее exe - ложной ошибки нет;
- CMakeLists.txt (src и корень) и .cmake с неизвестной правкой - выпуск стоит;
- допущенная правка (содержимое с точностью до концов строк и тот же exe) - проходит;
  то же содержимое при другом exe или другое содержимое при том же exe - стоит.
Контроль: прежнее Get-ChildItem -LiteralPath ... -Include *.cpp, *.h на том же дереве -Include не применяет
и берёт посторонние файлы - ложная остановка выпуска; тест это видит.
На настоящем дереве (если стейдж есть): с допусками Get-FreshAllow ничего, без них - ровно src/CMakeLists.txt.

    py -3.13 tools/test_release_fresh.py
"""
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REL = ROOT / "Выпуск" / "release.ps1"
STAGE_EXE = ROOT / "dist" / "_stage" / "openxcom_hd.exe"
ENC_W = "utf-8-sig"

RUNNER = r"""
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
Write-Output ("PSVER " + $PSVersionTable.PSVersion.Major + "." + $PSVersionTable.PSVersion.Minor)
$errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:REL, [ref]$null, [ref]$errs)
if ($errs.Count) { throw ("release.ps1 не разбирается: " + $errs[0].Message) }
foreach ($f in $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    . ([scriptblock]::Create($f.Extent.Text))
}
function Names($root, $items) { (@($items) | Where-Object { $_ } | ForEach-Object { $_.FullName.Substring($root.Length + 1).Replace('\', '/') } | Sort-Object) -join ',' }
foreach ($case in Get-ChildItem -LiteralPath $env:WORK -Directory) {
    $root = $case.FullName
    $exe = Join-Path $root 'stage\game.exe'
    $allow = @()
    $af = Join-Path $root 'allow.txt'
    if (Test-Path -LiteralPath $af) {
        foreach ($l in [IO.File]::ReadAllLines($af)) { $p = $l.Split('|'); $allow += @{ Path = $p[0]; Sha = $p[1]; Exe = $p[2] } }
    }
    Write-Output ("CASE " + $case.Name + " = " + (Names $root (Get-StaleBuildFiles $root $exe $allow)))
    $old = Get-ChildItem -LiteralPath (Join-Path $root 'src') -Recurse -File -Include *.cpp, *.h |
        Where-Object { $_.LastWriteTime -gt (Get-Item -LiteralPath $exe).LastWriteTime }
    Write-Output ("OLD " + $case.Name + " = " + (Names $root $old))
}
if ($env:REAL_EXE) {
    $r = (Resolve-Path $env:REAL_ROOT).Path
    Write-Output ("REAL allow = " + (Names $r (Get-StaleBuildFiles $r $env:REAL_EXE @(Get-FreshAllow))))
    Write-Output ("REAL none = " + (Names $r (Get-StaleBuildFiles $r $env:REAL_EXE @())))
}
"""

ALLOWED = "project ( x )\nset ( a b )\n"          # допущенное содержимое, хэш - с концами LF
EXE_A = b"MZ exe A"
EXE_B = b"MZ exe B"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def put(path, data, t):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    os.utime(path, (t, t))


def norm(names):
    return None if names is None else sorted(n for n in names.split(",") if n)


def make(work, name, exe=EXE_A, newer=(), allow=None):
    """Дерево: всё старше exe на час; newer - (путь, содержимое) новее exe на час."""
    root = work / name
    t0 = time.time() - 86400
    put(root / "stage" / "game.exe", exe, t0)
    for rel, data in [("src/Engine/Game.cpp", "int a;\n"), ("src/Engine/Game.h", "#pragma once\n"),
                      ("src/CMakeLists.txt", "old\n"), ("CMakeLists.txt", "top\n"),
                      ("cmake/modules/BuildType.cmake", "x\n"), ("src/README.txt", "doc\n")]:
        put(root / rel, data, t0 - 3600)
    for rel, data in newer:
        put(root / rel, data, t0 + 3600)
    if allow:
        (root / "allow.txt").write_text("\n".join("|".join(a) for a in allow), encoding="ascii")
    return root


def main():
    allow_ok = [("src/CMakeLists.txt", sha(ALLOWED.encode()), sha(EXE_A))]
    crlf = ALLOWED.replace("\n", "\r\n")
    expect = {
        "a_clean": "",
        "b_new_cpp": "src/Engine/New.cpp",
        "c_new_h": "src/Engine/Game.h",
        "d_foreign": "",
        "e_cmake_unknown": "src/CMakeLists.txt",
        "f_cmake_allowed": "",
        "g_allowed_other_exe": "src/CMakeLists.txt",
        "h_allowed_plus_cpp": "src/Engine/New.cpp",
        "i_top_and_module": "CMakeLists.txt,cmake/modules/BuildType.cmake",
        "j_allowed_edited": "src/CMakeLists.txt",
    }
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "w"
        make(work, "a_clean")
        make(work, "b_new_cpp", newer=[("src/Engine/New.cpp", "int b;\n")])
        make(work, "c_new_h", newer=[("src/Engine/Game.h", "#pragma once\nint c;\n")])
        make(work, "d_foreign", newer=[("src/README.txt", "doc2\n"), ("src/Resources/icon.png", b"\x89PNG"),
                                       ("src/notes.md", "x\n")])
        make(work, "e_cmake_unknown", newer=[("src/CMakeLists.txt", "new\n")], allow=allow_ok)
        make(work, "f_cmake_allowed", newer=[("src/CMakeLists.txt", crlf)], allow=allow_ok)
        make(work, "g_allowed_other_exe", exe=EXE_B, newer=[("src/CMakeLists.txt", crlf)], allow=allow_ok)
        make(work, "h_allowed_plus_cpp", newer=[("src/CMakeLists.txt", ALLOWED), ("src/Engine/New.cpp", "int b;\n")],
             allow=allow_ok)
        make(work, "i_top_and_module", newer=[("CMakeLists.txt", "top2\n"), ("cmake/modules/BuildType.cmake", "y\n")],
             allow=allow_ok)
        make(work, "j_allowed_edited", newer=[("src/CMakeLists.txt", ALLOWED + "# more\n")], allow=allow_ok)
        runner = Path(tmp) / "run.ps1"
        runner.write_text(RUNNER, encoding=ENC_W)
        env = {**os.environ, "REL": str(REL), "WORK": str(work)}
        real = STAGE_EXE.exists()
        if real:
            env.update(REAL_EXE=str(STAGE_EXE), REAL_ROOT=str(ROOT))
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(runner)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    out = r.stdout.strip()
    print(out)
    if r.returncode:
        print(r.stderr)
        sys.exit("прогон PowerShell упал")
    got = dict(l.split(" = ", 1) if " = " in l else (l, "") for l in out.splitlines())
    got = {k: v.strip() for k, v in got.items()}
    fails = []
    psver = next((l for l in out.splitlines() if l.startswith("PSVER")), "")
    if psver != "PSVER 5.1":
        fails.append(f"нужен Windows PowerShell 5.1, а запущен {psver or '?'}")
    for name, want in expect.items():
        if norm(got.get("CASE " + name)) != norm(want):
            fails.append(f"{name}: ожидалось [{want}], вышло [{got.get('CASE ' + name)}]")
    # контроль: прежняя проверка (-Include при -LiteralPath) берёт посторонние файлы - ложная остановка
    if got.get("OLD d_foreign") == "":
        fails.append("контроль: прежняя проверка не взяла посторонние файлы - ошибка -Include не воспроизведена")
    if real:
        if got.get("REAL allow") != "":
            fails.append(f"настоящее дерево с допусками: [{got.get('REAL allow')}]")
        if got.get("REAL none") != "src/CMakeLists.txt":
            fails.append(f"настоящее дерево без допусков: [{got.get('REAL none')}], ожидалось src/CMakeLists.txt")
    else:
        print("стейджа нет - проверка настоящего дерева пропущена")
    if fails:
        print("\n".join("FAIL " + f for f in fails))
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
