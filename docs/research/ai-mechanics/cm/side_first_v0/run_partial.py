"""Runs dig.py, first_cause.py and ff_weapon.py unchanged in their counting on the mixed zips of partial_stats.py, on the missions M3 and L8. args: mix_dir"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
W = Path(__file__).parent
mix = Path(sys.argv[1])
for name in ("dig", "first_cause", "ff_weapon"):
    text = (W / f"{name}.py").read_text(encoding="utf-8")
    new = text.replace('["M3", "M8", "L4", "L8"]', '["M3", "L8"]').replace('("M3", "M8", "L4", "L8")', '("M3", "L8")')
    if new == text:
        raise SystemExit(name + ": no mission list found")
    script = mix / f"{name}_partial.py"
    script.write_text(new, encoding="utf-8")
    for arm in ("v0", "v01"):
        r = subprocess.run([sys.executable, "-I", str(script), str(mix / f"mix_{arm}.zip"), "sfW"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(f"===== {name} {arm}")
        print(r.stdout)
        print(r.stderr[-400:])
