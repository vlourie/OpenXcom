"""AI FORGE WP3: the oracle's hash after the addendum, beside the first one."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
h = hashlib.sha256((HERE / "AIForgeStochasticOracle.py").read_bytes()).hexdigest()
a = hashlib.sha256((HERE / "WP3_PLAN_ADDENDUM.md").read_bytes()).hexdigest()
p = HERE / "FROZEN.txt"
t = p.read_text(encoding="utf-8")
assert "oracle_after_addendum" not in t
p.write_text(t + f"oracle_after_addendum={h}\naddendum={a}\n", encoding="utf-8")
print(p.read_text(encoding="utf-8"))
