"""STALE_PATROL_NODE: можно ли проверять сохранённый узел позже, у самого использования (аудит п. 17.24). По записям
[AIREC] (без новой сборки): в каких решениях сбросы STALE и сколько решений реально идут патрулём к сохранённому узлу.
  py -3.13 tools/ai_speed/stale_late_est.py <rec.gz> [...]
Классы сброса: USE - итог решения патруль (mode 0, слот p); GATE - кости дали патруль (odds mode 0), но итог другой
(после сброса без нового узла - засада или отход); CGATE - кости дали бой (2), итог не бой - бой мог упасть в патруль;
OTHER - решение до патруля не доходило."""
import collections, gzip, json, sys

sys.stdout.reconfigure(encoding="utf-8")
for path in sys.argv[1:]:
    cls = collections.Counter()
    side_use = collections.Counter()
    side_kept = collections.Counter()
    side_dec = collections.Counter()
    other = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            i = line.find("[AIREC] ")
            if i < 0:
                continue
            try:
                r = json.loads(line[i + 8:])
            except ValueError:
                continue
            b = r.get("base") or {}
            side = "p" if r.get("side") == 0 else "h"
            side_dec[side] += 1
            reason = b.get("reason") or {}
            trail = reason.get("trail") or []
            odds = reason.get("odds") or []
            use = b.get("mode") == 0 and b.get("slot") == "p"
            if use and b.get("src") == "patrol.node":
                side_use[side] += 1
                if b.get("src_rec") is not None and b["src_rec"] < r["rec"]:
                    side_kept[side] += 1
            st = [t for t in trail if t.startswith("patrol.stale")]
            if not st:
                continue
            om = odds[-1]["mode"] if odds else None
            if use:
                c = "USE"
            elif om == 0:
                c = "GATE"
            elif om == 2 and b.get("mode") != 2:
                c = "CGATE"
            else:
                c = "OTHER"
            cls[(side, c, "new-" if st[0].endswith("new -") else "new")] += 1
            if c != "USE":
                other.append((r.get("seed"), r["rec"], side, c, b.get("mode"), b.get("slot"), b.get("src"), om, st[0]))
    print(f"== {path.rsplit('/', 1)[-1]}")
    print("  решений h/p:", dict(side_dec), " итог патруль к узлу:", dict(side_use), " из них узел из прежнего решения:", dict(side_kept))
    for k in sorted(cls):
        print("  сброс", k, cls[k])
    srcs = collections.Counter((o[2], o[3], o[6], "odds" if o[7] is not None else "без костей") for o in other)
    for k in sorted(srcs):
        print("   не патруль:", k, srcs[k])
