"""AI FORGE WP3: tools and records into docs/research/ai-mechanics/cm/forge_wp3, the frozen exe and raw logs into the battle archive, hashes of all of it."""
import hashlib
import shutil
from pathlib import Path

F = Path(__file__).resolve().parent
S = F.parent
DOC = Path("E:/OpenXCom/docs/research/ai-mechanics/cm/forge_wp3")
ARC = Path("E:/OXCE_AIWorker/battles_archive/forge_wp3")
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
tools += [F / n for n in ("ForgeLegal.h", "test_legal.cpp", "AIForgeStochasticOracle.py", "scheduler_integrity_check.py", "test_oracle.py", "apply_wp3.py", "build_f3.sh", "freeze_addendum.py", "look_a1.py", "look_notes.py", "look_final.py", "look_doc.py", "look_doc2.py", "pack_wp3.py",
                          "WP3_PLAN.md", "WP3_PLAN_ADDENDUM.md", "WP3_RESULTS.json", "WP3_RUNS.jsonl", "WP3_TABLES.md", "check_c.json", "check_p.json", "check_q.json", "process_c.txt", "process_p.txt", "process_q.txt", "FROZEN.txt", "ledger.tsv")]
tools.append(S / "cm" / "st" / "run_cm.py")
for p in tools:
    shutil.copy2(p, DOC / p.name)
for p in sorted((F / "res").iterdir()):
    shutil.copy2(p, ARC / p.name)
shutil.copy2(F / "b-x" / "bin" / X, ARC / X)
for p in ("FROZEN.txt", "ledger.tsv", "WP3_RESULTS.json", "WP3_RUNS.jsonl", "WP3_TABLES.md", "WP3_PLAN.md", "WP3_PLAN_ADDENDUM.md", "check_c.json", "check_p.json", "check_q.json"):
    shutil.copy2(F / p, ARC / p)
for root in (DOC, ARC):
    lines = [f"{sha(p)}  {p.name}" for p in sorted(root.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"]
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(root, len(lines), "files", sum(p.stat().st_size for p in root.iterdir()) // (1 << 20), "MB")
print(sha(ARC / X))
