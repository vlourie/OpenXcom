"""AI FORGE WP2: tools and records into docs/research/ai-mechanics/cm/forge_wp2, the frozen exe and raw logs into the battle archive, hashes of all of it."""
import hashlib
import shutil
from pathlib import Path

F = Path(__file__).resolve().parent
S = F.parent
DOC = Path("E:/OpenXCom/docs/research/ai-mechanics/cm/forge_wp2")
ARC = Path("E:/OXCE_AIWorker/battles_archive/forge_wp2")
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
tools += [F / n for n in ("AIForgeCounterfactualRunner.py", "scheduler_integrity_check.py", "test_arena.py", "apply_wp2.py", "build_fw.sh", "pick_branch.py", "look_a1.py", "look_seedless.py", "look_chain.py", "look_bb.py", "look_ab.py",
                          "look_cons.py", "look_map.py", "pack_wp2.py", "WP2_PLAN.md", "WP2_PLAN_ADDENDUM.md", "PICK_R5.json", "WP2_COMPARE.json", "FROZEN.txt", "ledger.tsv")]
tools.append(S / "cm" / "st" / "run_cm.py")
for p in tools:
    shutil.copy2(p, DOC / p.name)
for p in sorted((F / "res").iterdir()):
    shutil.copy2(p, ARC / p.name)
shutil.copy2(F / "b-w" / "bin" / X, ARC / X)
for p in ("FROZEN.txt", "ledger.tsv", "WP2_COMPARE.json", "WP2_PLAN.md", "WP2_PLAN_ADDENDUM.md"):
    shutil.copy2(F / p, ARC / p)
for root in (DOC, ARC):
    lines = [f"{sha(p)}  {p.name}" for p in sorted(root.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"]
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(root, len(lines), "files", sum(p.stat().st_size for p in root.iterdir()) // (1 << 20), "MB")
for name in ("AIForgeCounterfactualRunner.py", "scheduler_integrity_check.py", "SchedulerIntegrityMonitor.cpp", "SchedulerIntegrityMonitor.h", "WP2_PLAN.md", "WP2_PLAN_ADDENDUM.md", "WP2_COMPARE.json"):
    print(sha(DOC / name)[:16], name)
for p in sorted(ARC.glob("res_*.zip")):
    print(sha(p)[:16], p.name)
print(sha(ARC / X))
