"""AI FORGE WP1: tools and records into docs/research/ai-mechanics/cm/forge_wp1, the frozen exe and raw logs into the battle archive, hashes of all of it. Temporary base_check copies are removed."""
import hashlib
import shutil
from pathlib import Path

F = Path(__file__).resolve().parent
S = F.parent
DOC = Path("E:/OpenXCom/docs/research/ai-mechanics/cm/forge_wp1")
ARC = Path("E:/OXCE_AIWorker/battles_archive/forge_wp1")
X = "openxcom" ".exe"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


for d in F.glob("base_check*"):
    if d.is_dir():
        shutil.rmtree(d)
DOC.mkdir(parents=True, exist_ok=True)
ARC.mkdir(parents=True, exist_ok=True)
tools = [F / "mon" / "SchedulerIntegrityMonitor.h", F / "mon" / "SchedulerIntegrityMonitor.cpp"]
tools += [F / n for n in ("AIForgeReplayRunner.py", "scheduler_integrity_check.py", "test_monitor.py", "test_compare.py", "apply_monitor.py", "make_tree.py", "fix_forgehash.py", "fix_arms.py",
                          "build_fg.sh", "verify_base.sh", "gate1.py", "pick_n.py", "clock_shift.py", "look_div.py", "look_tu.py", "look_tu_class.py", "look_tu_actions.py", "look_tu_hits.py", "look_other.py", "wp1_final_check.py", "check_report.py", "pack_wp1.py",
                          "WP1_PLAN.md", "D0_FINGERPRINT.json", "WP1_COMPARE.json", "WP1_GATE1.json", "WP1_FINAL_CHECK.json", "FROZEN.txt", "ledger.tsv", "ledger_notes.txt")]
tools.append(S / "cm" / "st" / "run_cm.py")
for p in tools:
    shutil.copy2(p, DOC / p.name)
for p in sorted((F / "res").iterdir()):
    shutil.copy2(p, ARC / p.name)
shutil.copy2(F / "b-f" / "bin" / X, ARC / X)
for p in ("FROZEN.txt", "ledger.tsv", "WP1_COMPARE.json", "WP1_GATE1.json", "WP1_FINAL_CHECK.json", "D0_FINGERPRINT.json"):
    shutil.copy2(F / p, ARC / p)
for p in sorted((F / "chains").iterdir()):
    shutil.copy2(p, ARC / p.name)
for root in (DOC, ARC):
    lines = [f"{sha(p)}  {p.name}" for p in sorted(root.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"]
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(root, len(lines), "files", sum(p.stat().st_size for p in root.iterdir()) // (1 << 20), "MB")
for name in ("AIForgeReplayRunner.py", "scheduler_integrity_check.py", "SchedulerIntegrityMonitor.cpp", "SchedulerIntegrityMonitor.h", "WP1_PLAN.md", "WP1_COMPARE.json", "WP1_GATE1.json", "WP1_FINAL_CHECK.json", "D0_FINGERPRINT.json", "test_compare.py", "test_monitor.py"):
    print(sha(DOC / name)[:16], name)
for p in sorted(ARC.glob("res_*.zip")):
    print(sha(p)[:16], p.name)
print(sha(ARC / X))
