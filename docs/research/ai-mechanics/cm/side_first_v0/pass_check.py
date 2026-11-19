"""SIDE-FIRST COMBAT V0.1: the check of the repeated pass, all hostile turns. args: zip:prefix:arm:mission ...
tu_grew_rec: [AIREC] state.tu of one unit in one hostile turn growing; tu_grew_dec: the same by [AIDECIDE] tu.
over: a record that spent more than the unit had at its [AIDECIDE]; compared with [AIREC] state.tu and with [AIEXEC] tu + spent.
same_rep: the same unit, turn, tile, action and aim as its own previous record, where the previous one spent nothing: the engine doing again what did not happen.
rounds: think rounds in a row within a visit (n of the visit's records); a visit with more than 2 think rounds would be free thinking.
jump: the next unit has a lower id than the last; after the last went out, or not. out_turn_share: of hostile turns."""
import gzip
import io
import json
import re
import sys
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KV = re.compile(r"(\w+)=([^ ]*)")


def battle(z, label):
    ls = [s.split("\t")[-1] for s in gzip.open(io.BytesIO(z.read(f"out/{label}/openxcom.log.gz")), "rt", encoding="utf-8", errors="replace").read().splitlines()]
    c = Counter()
    visits = Counter()
    rec_tu = {}
    dec_tu = {}
    prev_rec = {}
    last = None
    turn = None
    out = set()
    cur = None
    rec_state = None
    max_n = Counter()
    ex = []
    for s in ls:
        if s.startswith("[AICASUALTY] "):
            d = dict(KV.findall(s))
            if d.get("side") == "1":
                out.add(d.get("victim"))
        elif s.startswith("[AIDECIDE] "):
            d = dict(KV.findall(s.split(" hu=")[0]))
            cur = d if d.get("side") == "1" else None
            rec_state = None
            if not cur:
                continue
            if d["turn"] != turn:
                turn = d["turn"]
                last = None
                out = set()
                c["turns"] += 1
            k = (turn, d["unit"])
            t = int(d.get("tu") or 0)
            if k in dec_tu and t > dec_tu[k]:
                c["tu_grew_dec"] += 1
            dec_tu[k] = t
            if d["unit"] != last:
                visits[k] += 1
                if last and int(d["unit"]) < int(last):
                    c["jump"] += 1
                    c["jump_after_out" if last in out else "jump_other"] += 1
                last = d["unit"]
            c["n_" + str(min(int(d.get("n") or 0), 3))] += 1
        elif s.startswith("[AIREC] "):
            j = json.loads(s[8:])
            if j.get("side") == 1:
                k = (j["turn"], j["unit"])
                tu = j["state"]["tu"]
                if k in rec_tu and tu > rec_tu[k]:
                    c["tu_grew_rec"] += 1
                rec_tu[k] = tu
                rec_state = tu
        elif s.startswith("[AIEXEC] ") and cur:
            x = json.loads(s[9:])
            d, cur = cur, None
            if str(x.get("unit")) != d["unit"]:
                continue
            c["records"] += 1
            spent = x.get("spent") or 0
            act = d.get("act")
            sig = (d["turn"], d["unit"], d.get("from"), act, d.get("to"))
            if act not in ("0", "1", None):
                if spent == 0:
                    c["acted_spent_0"] += 1
                    if prev_rec.get(d["unit"]) == sig:
                        c["same_rep_0"] += 1
                if spent > 0 and prev_rec.get(d["unit"]) == sig and act == "2":
                    c["walk_same_from_to"] += 1
            prev_rec[d["unit"]] = sig if spent == 0 else None
            have = int(d.get("tu") or 0)
            if spent > have:
                c["over"] += 1
                c["over_rec_eq"] += 1 if rec_state is not None and rec_state == (x.get("tu") or 0) + spent else 0
                c["over_rec_gt"] += 1 if rec_state is not None and rec_state > have else 0
                if len(ex) < 3:
                    ex.append((d["turn"], d["unit"], "act", act, "dec.tu", have, "rec.tu", rec_state, "exec.tu", x.get("tu"), "spent", spent, "walk", x.get("walk")))
    c["unit_turns"] = len(visits)
    c["visits"] = sum(visits.values())
    c["extra_visits"] = sum(v - 1 for v in visits.values())
    return c, max(visits.values()) if visits else 0, ex


for a in sys.argv[1:]:
    zp, prefix, arm, mission = a.rsplit(":", 3)
    z = zipfile.ZipFile(zp)
    tot = Counter()
    mx = 0
    exs = []
    for s_ in (1, 2, 3, 4):
        c, m, ex = battle(z, f"{prefix}_{arm}_{mission}_s{s_}")
        tot.update(c)
        mx = max(mx, m)
        exs += ex
    print(f"{prefix} {arm} {mission}: ходов {tot['turns']}, юнит-ходов {tot['unit_turns']}, заходов {tot['visits']}, доп. заходов {tot['extra_visits']} ({tot['extra_visits'] / max(1, tot['unit_turns']):.2f} на юнит-ход), макс. {mx}; прыжков назад {tot['jump']}: после выбытия {tot['jump_after_out']} ({tot['jump_after_out'] / max(1, tot['turns']):.2f} на ход), иначе {tot['jump_other']}; рост ОВ rec {tot['tu_grew_rec']} dec {tot['tu_grew_dec']}; записей {tot['records']}, без траты ОВ {tot['acted_spent_0']}, из них повтор того же {tot['same_rep_0']}; потрачено больше ОВ решения {tot['over']} (rec.tu == exec.tu+spent {tot['over_rec_eq']})")
    print("   примеры:", exs[:2])
