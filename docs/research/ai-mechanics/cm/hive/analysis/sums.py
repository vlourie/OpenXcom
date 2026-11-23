"""HIVE COMMAND CORE V0: recounts the report's totals from the saved analysis output, so the tables are checked against the journals' own numbers (read only)."""
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
out = Path(sys.argv[1])
B = ["6_M6_s1", "8_M6_s2", "9_L6_s1", "10_L6_s2", "11_L7_s1"]
go = ref = ex = done = 0
sc = st = hc = ht = 0
walk_same = walk_other = 0
modes = {}
fair = [0, 0, 0, 0]
ch = [0, 0, 0, 0, 0]
merges = 0
kinds = {"contact": 0, "sector_node": 0}
for b in B:
    e = (out / f"exec_{b}.txt").read_text(encoding="utf-8")
    g = re.search(r"GO orders (\d+) (\{.*\})", e)
    d = eval(g.group(2))
    go += int(g.group(1))
    ref += d.get("refused_before_a_step", 0)
    ex += sum(v for k, v in d.items() if k.startswith("executed:"))
    for t, c, tot in re.findall(r"executed, (\w+): (\d+), closer to the target at the last record (\d+)", e):
        if t == "SEARCH":
            st += int(c)
            sc += int(tot)
        else:
            ht += int(c)
            hc += int(tot)
    v = (out / f"eval_{b}.txt").read_text(encoding="utf-8")
    done += int(re.search(r"GO orders: \d+ completed: (\d+)", v).group(1))
    o = (out / f"org_{b}.txt").read_text(encoding="utf-8")
    w = re.search(r"to the order's target (\d+) elsewhere (\d+)", o)
    walk_same += int(w.group(1))
    walk_other += int(w.group(2))
    merges += int(re.search(r"merges: (\d+)", o).group(1))
    for kk, n in re.findall(r"'(contact|sector_node)': (\d+)", re.search(r"objective kinds: (Counter\(\{.*?\}\))", o).group(1)):
        kinds[kk] += int(n)
    f = (out / f"fair_{b}.txt").read_text(encoding="utf-8")
    r = re.search(r"records (\d+) in the observer's own sees (\d+) only in the side's seen of that turn (\d+) in neither (\d+)", f)
    for i in range(4):
        fair[i] += int(r.group(i + 1))
    c = (out / f"cmd_{b}.txt").read_text(encoding="utf-8")
    r = re.search(r"changes (\d+) (\{.*\})", c)
    d = eval(r.group(2))
    ch[0] += int(r.group(1))
    ch[1] += d.get("new_was_member", 0)
    ch[2] += d.get("old_fell_in_records", 0)
    ch[3] += d.get("same_task_in_orders", 0)
    m = (out / f"modes_{b}.txt").read_text(encoding="utf-8")
    a = eval(re.search(r"^active (\[.*\])", m, re.M).group(1))
    z = eval(re.search(r"^D0 (\[.*\])", m, re.M).group(1))
    share = lambda x: round(100 * sum(n for k, n in x if k.startswith("m0_")) / sum(n for _, n in x))
    modes[b] = (share(a), share(z), dict(a).get("m3_none", 0), dict(z).get("m3_none", 0))
print("GO", go, "refused", ref, f"{100 * ref / go:.0f}%", "executed", ex, f"{100 * ex / go:.0f}%", "completed", done, f"{100 * done / go:.0f}%")
print("SEARCH closer", sc, "of", st, "HOLD closer", hc, "of", ht)
print("patrol walks to the order's target", walk_same, "of", walk_same + walk_other)
print("fair records, own, side, neither", fair)
print("commander changes, new was member, old fell, same task", ch[:4])
print("merges", merges, "objectives", kinds)
print("patrol share of decisions active / D0, m3_none active / D0", modes)
