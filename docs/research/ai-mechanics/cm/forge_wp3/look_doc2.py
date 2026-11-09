"""AI FORGE WP3: what the batch checks actually state, for the document's control table."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
for b in "cpq":
    c = json.loads((HERE / f"check_{b}.json").read_text(encoding="utf-8-sig"))
    print("==", b, "keys", sorted(c))
    for k, v in c.items():
        if k in ("runs", "arms", "per_run"):
            print(k, "n", len(v))
            continue
        print(k, json.dumps(v, ensure_ascii=False)[:700])
    runs = c.get("runs") or c.get("arms") or c.get("per_run")
    if runs:
        first = runs[0] if isinstance(runs, list) else next(iter(runs.values()))
        print("one run", json.dumps(first, ensure_ascii=False)[:1200])
r = json.loads((HERE / "WP3_RESULTS.json").read_text(encoding="utf-8-sig"))
print("log mb", r["log_mb_total"], "ledger", json.dumps(r["ledger"], ensure_ascii=False)[:300], "bootstrap", r["bootstrap"], "flips", r["flips"])
