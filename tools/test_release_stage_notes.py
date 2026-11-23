"""Выпуск/release.ps1, режим «Что нового» готового стейджа (notes/stage.ru.txt, stage.en.txt).

Функции берутся из самого release.ps1 разбором AST и гоняются на копиях во временной папке:
- русское «Что нового» - ровно пункты stage.ru.txt;
- CHANGELOG: раздел выпуска - текст stage.ru.txt, из «[Не выпущено]» уходят только совпавшие пункты,
  чужие строки и пункт, переписанный для выпуска, остаются, опустевший заголовок ### уходит,
  прежние разделы не меняются до байта;
- next.en.txt: уходят только выпущенные пункты, без спецификации остаётся без неё.
Контроль: прежний Close-Changelog на той же копии переносит в раздел выпуска все пункты - тест это видит.

    py -3.13 tools/test_release_stage_notes.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REL = ROOT / "Выпуск" / "release.ps1"
ENC_W = "utf-8-sig"

OLD = "## 2026.10.07-3 — 7 октября 2026\n### Исправлено\n- Старый пункт прошлого выпуска.\n"
CHANGELOG = ("# Changelog\n\nНовое — сверху.\n\n## [Не выпущено]\n### Добавлено\n- Предметы A.\n"
             "### Исправлено\n- Окраска B.\n- Лес C.\n- Песок всех пустынь D.\n- Джунгли E (чужая строка).\n"
             "- Полы F (чужая строка).\n\n" + OLD)
STAGE_RU = "### Добавлено\n- Предметы A.\n### Исправлено\n- Окраска B.\n- Лес C.\n- Песок только X-ops D2.\n"
STAGE_EN = "- Objects A.\n- Colouring B.\n- Forest C.\n- X-ops sand only D2.\n"
NEXT_EN = ("- Objects A.\n- Colouring B.\n- Forest C.\n- Sand of all deserts D.\n- Jungle E.\n"
           "- Floors F.\n")

RUNNER = r"""
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$errs = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:REL, [ref]$null, [ref]$errs)
if ($errs.Count) { throw ("release.ps1 не разбирается: " + $errs[0].Message) }
foreach ($f in $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    . ([scriptblock]::Create($f.Extent.Text))
}
$w = $env:WORK
$stRu = Join-Path $w 'stage.ru.txt'
$stEn = Join-Path $w 'stage.en.txt'
function Guard([string] $name, [string] $ru, [string] $en, [bool] $nb) {
    try { $r = Test-StageNotes $ru $en $nb; Write-Output "GUARD $name = $r" } catch { Write-Output "GUARD $name = throw" }
}
Guard 'none' (Join-Path $w 'no.ru.txt') (Join-Path $w 'no.en.txt') $false
Guard 'nobuild' $stRu $stEn $true
Guard 'build' $stRu $stEn $false
Guard 'one_lang' $stRu (Join-Path $w 'no.en.txt') $true
Guard 'unequal' $stRu (Join-Path $w 'short.en.txt') $true
[IO.File]::WriteAllText((Join-Path $w 'out.ru.txt'), (Format-Notes ([IO.File]::ReadAllText($stRu, [Text.Encoding]::UTF8))), (New-Object Text.UTF8Encoding $true))
Close-StageChangelog (Join-Path $w 'CHANGELOG.md') '2026.10.08' ([datetime]'2026-10-08') $stRu
Remove-NextItems (Join-Path $w 'next.en.txt') @(Get-NoteItems $stEn)
Remove-NextItems (Join-Path $w 'next.ru.txt') @(Get-NoteItems $stRu)
Close-Changelog (Join-Path $w 'CHANGELOG_ctl.md') '2026.10.08' ([datetime]'2026-10-08')
"""


def section(text, title):
    at = text.index(title)
    nxt = text.find("\n## ", at + len(title))
    return text[at:nxt if nxt >= 0 else len(text)]


def items(text):
    return [l[2:] for l in text.splitlines() if l.startswith("- ")]


def main():
    fails = []
    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        (w / "CHANGELOG.md").write_text(CHANGELOG, encoding=ENC_W)
        (w / "CHANGELOG_ctl.md").write_text(CHANGELOG, encoding=ENC_W)
        (w / "stage.ru.txt").write_text(STAGE_RU, encoding=ENC_W)
        (w / "stage.en.txt").write_text(STAGE_EN, encoding=ENC_W)
        (w / "next.en.txt").write_text(NEXT_EN, encoding="utf-8")
        (w / "short.en.txt").write_text("- Objects A.\n", encoding=ENC_W)
        runner = w / "run.ps1"
        runner.write_text(RUNNER, encoding=ENC_W)
        env = {**os.environ, "REL": str(REL), "WORK": str(w)}
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(runner)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        print(r.stdout.strip())
        if r.returncode:
            print(r.stderr)
            sys.exit("ОШИБКА: прогон функций release.ps1 упал")

        guards = dict(l[6:].split(" = ") for l in r.stdout.splitlines() if l.startswith("GUARD "))
        want_g = {"none": "False", "nobuild": "True", "build": "throw", "one_lang": "throw", "unequal": "throw"}
        if guards != want_g:
            fails.append(f"проверка notes/stage.*: {guards}, нужно {want_g}")

        ru = (w / "out.ru.txt").read_text(encoding=ENC_W).splitlines()
        want = ["— Предметы A.", "— Окраска B.", "— Лес C.", "— Песок только X-ops D2."]
        if ru != want:
            fails.append(f"русское «Что нового»: {ru}")

        cl = (w / "CHANGELOG.md").read_text(encoding=ENC_W)
        unrel = section(cl, "## [Не выпущено]")
        if items(unrel) != ["Песок всех пустынь D.", "Джунгли E (чужая строка).", "Полы F (чужая строка)."]:
            fails.append(f"[Не выпущено] после выпуска: {items(unrel)}")
        if "### Добавлено" in unrel:
            fails.append("опустевший заголовок ### Добавлено остался в [Не выпущено]")
        rel = section(cl, "## 2026.10.08 — 8 октября 2026")
        if items(rel) != ["Предметы A.", "Окраска B.", "Лес C.", "Песок только X-ops D2."]:
            fails.append(f"раздел выпуска: {items(rel)}")
        if not cl.endswith(OLD):
            fails.append("прежний раздел выпуска изменён")

        en = (w / "next.en.txt").read_bytes()
        if en.startswith(b"\xef\xbb\xbf"):
            fails.append("next.en.txt получил спецификацию")
        if items(en.decode("utf-8")) != ["Sand of all deserts D.", "Jungle E.", "Floors F."]:
            fails.append(f"next.en.txt после выпуска: {items(en.decode('utf-8'))}")
        if (w / "next.ru.txt").exists():
            fails.append("next.ru.txt появился, хотя его не было")

        # контроль: прежнее закрытие уносит в раздел выпуска все шесть пунктов, включая чужие
        ctl = (w / "CHANGELOG_ctl.md").read_text(encoding=ENC_W)
        ctl_rel = items(section(ctl, "## 2026.10.08 — 8 октября 2026"))
        if len(ctl_rel) != 6 or items(section(ctl, "## [Не выпущено]")):
            fails.append(f"контроль: прежний Close-Changelog дал {ctl_rel} - тест не отличает режимы")
        else:
            print("контроль: прежний Close-Changelog уносит в выпуск все 6 пунктов, включая чужие")

    if fails:
        print("\n".join("FAIL " + f for f in fails))
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
