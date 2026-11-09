"""AI FORGE WP2.1: tools and records into docs/research/ai-mechanics/cm/forge_wp21, the frozen exe and raw logs into the battle archive, hashes of all of it."""
import hashlib
import shutil
from pathlib import Path

F = Path(__file__).resolve().parent
S = F.parent
DOC = Path("E:/OpenXCom/docs/research/ai-mechanics/cm/forge_wp21")
ARC = Path("E:/OXCE_AIWorker/battles_archive/forge_wp21")
X = "openxcom" ".exe"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


DOC.mkdir(parents=True, exist_ok=True)
ARC.mkdir(parents=True, exist_ok=True)
tools = [F / "mon" / "SchedulerIntegrityMonitor.h", F / "mon" / "SchedulerIntegrityMonitor.cpp"]
tools += [F / n for n in ("ForgeLegal.h", "test_legal.cpp", "AIForgeCounterfactualRunner.py", "scheduler_integrity_check.py", "test_arena21.py", "apply_wp21.py", "build_fx.sh", "make_plan.py", "make_addendum.py",
                          "make_addendum2.py", "preflight_off.py", "preflight_off2.py", "look_iso.py", "look_iso.txt", "look_tiles.py", "look_end.py", "look_off.py", "look_off2.py", "pack_wp21.py",
                          "WP2_1_PLAN.md", "WP2_1_PLAN_ADDENDUM.md", "WP21_COMPARE.json", "WP21_OFF.json", "OFF_process.txt", "report.txt", "FROZEN.txt", "ledger.tsv")]
tools.append(S / "cm" / "st" / "run_cm.py")
for p in tools:
    shutil.copy2(p, DOC / p.name)
for p in sorted((F / "res").iterdir()):
    shutil.copy2(p, ARC / p.name)
# the stray run has the same file names as the real OFF
for p in sorted((F / "stray").iterdir()):
    shutil.copy2(p, ARC / f"stray_{p.name}")
shutil.copy2(F / "b-x" / "bin" / X, ARC / X)
for p in ("FROZEN.txt", "ledger.tsv", "WP21_COMPARE.json", "WP21_OFF.json", "OFF_process.txt", "WP2_1_PLAN.md", "WP2_1_PLAN_ADDENDUM.md"):
    shutil.copy2(F / p, ARC / p)
for root in (DOC, ARC):
    lines = [f"{sha(p)}  {p.name}" for p in sorted(root.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"]
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(root, len(lines), "files", sum(p.stat().st_size for p in root.iterdir()) // (1 << 20), "MB")
print(sha(ARC / X))
