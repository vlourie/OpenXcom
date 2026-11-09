"""Per battle, side 0 (the bot on the player's side) under the arms: its ff vetoes and the damage its own secondaries did to it.
usage: ff_side0.py <dir> <ff_battles.tsv> <arm> [<arm>...]"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "E:/OpenXCom/census/ai3_2026-10-14/ff")
import ff_ana  # noqa: E402

D = Path(sys.argv[1])
BT = [l.split("\t") for l in Path(sys.argv[2]).read_text(encoding="utf-8-sig").splitlines()[1:] if l.strip()]
ARMS = sys.argv[3:]
K = ["s0_n_sec", "s0_n_secsn", "s0_n_secre", "s0_fsec_dmg", "s0_fsec_ko", "s0_esec_dmg", "s0_edmg", "s1_n_sec", "s1_n_secsn", "s1_n_secre"]
print("battle\tarm\t" + "\t".join(K))
for b in BT:
    for arm in ARMS:
        rec = D / f"ff_{arm}_{b[0]}.rec.gz"
        if not rec.exists():
            continue
        B = ff_ana.scan_file(str(rec))
        C = next(iter(B.values())) if B else {}
        print(f"{b[0]}\t{arm}\t" + "\t".join(str(C.get(k, 0)) for k in K))
