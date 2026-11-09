"""AI FORGE WP4: tools and records into docs/research/ai-mechanics/cm/forge_wp4, the frozen exe and raw logs into the battle archive, hashes of all of it."""
import hashlib
import shutil
from pathlib import Path

F = Path(__file__).resolve().parent
DOC = Path("E:/OpenXCom/docs/research/ai-mechanics/cm/forge_wp4")
ARC = Path("E:/OXCE_AIWorker/battles_archive/forge_wp4")
X = "openxcom" ".exe"
TOOLS = ["AIForgeOpportunityMiner.py", "scheduler_integrity_check.py", "test_miner.py", "test_miner.log", "ForgeLegal.h", "test_legal.cpp", "apply_wp4.py", "build_f4.sh", "pack_wp4.py", "post_wp4.py", "post2_wp4.py", "post3_wp4.py", "post4_wp4.py",
         "WP4_PLAN.md", "POINTS.json", "SCAN.json", "FROZEN.txt", "ledger.tsv", "GATE.json", "WP4_RUNS.jsonl", "WP4_RESULTS.json", "WP4_TABLES.md", "POST.json", "POST2.json", "POST3.json", "POST4.json", "opportunities.jsonl.gz"]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def hashes(root):
    lines = [f"{sha(p)}  {p.relative_to(root).as_posix()}" for p in sorted(root.rglob("*")) if p.is_file() and p.name != "SHA256SUMS.txt"]
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(lines)


DOC.mkdir(parents=True, exist_ok=True)
(DOC / "mon").mkdir(exist_ok=True)
ARC.mkdir(parents=True, exist_ok=True)
for n in TOOLS:
    shutil.copy2(F / n, DOC / n)
for p in sorted(F.glob("check_*.json")):
    shutil.copy2(p, DOC / p.name)
for p in sorted(F.glob("process_*.txt")):
    shutil.copy2(p, DOC / p.name)
for p in sorted((F / "mon").iterdir()):
    if p.is_file():
        shutil.copy2(p, DOC / "mon" / p.name)
for p in sorted((F / "res").iterdir()):
    shutil.copy2(p, ARC / p.name)
shutil.copy2(F / "b-x" / "bin" / X, ARC / X)
for n in ("FROZEN.txt", "POINTS.json", "ledger.tsv"):
    shutil.copy2(F / n, ARC / n)
print("doc", hashes(DOC), "arc", hashes(ARC))
