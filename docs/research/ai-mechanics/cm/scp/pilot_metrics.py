"""SIDE_TURN_ACTION_SCHEDULER combat pilot: per battle metrics of an arm (log + arena table) into one TSV.

Per battle: the result ([AIRESULT]: outcome, turns, player losses and damage, hostile losses, battle ms); the hostile side's
decisions, attack decisions (act 6-14), executed attacks (time units spent, no walk), attacks that did damage, damage dealt,
units downed, friendly damage, time units spent; walks (the player's reaction opportunities); reactions of the player in
hostile turns and of the hostile side in player turns; casualties by phase (hostile units down in hostile turns - mostly
reaction fire and own fire - and in player turns); hostile turn 1 alone (the same state in both arms up to the first pick);
the scheduler ([AISCHED], arm B): attack picks out of the engine's order and what the promoted unit then did, its time in us.

  py -3.13 -I pilot_metrics.py <out dir> <arena dir> <prefix> <tsv out>"""
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT, ARENA, PRE, TSV = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
KV = re.compile(r"(\w+)=(\S+)")
ATT = {6, 7, 8, 9, 10, 12, 13, 14}
COLS = ["label", "arm", "scen", "seed", "outcome", "how", "turns", "player", "pdead", "pout", "pinc", "phplost", "hostile", "hdead",
        "hout", "hinc", "ms", "ms_turn", "h_dec", "h_attdec", "h_attexec", "h_atthit", "h_dmg", "h_downed", "h_fdmg", "h_spent",
        "h_walks", "p_react", "p_react_per10", "h_react", "h_down_hturn", "h_down_pturn", "p_down_hturn", "p_down_pturn",
        "t1_h_attexec", "t1_h_atthit", "t1_h_dmg", "t1_p_react", "t1_h_down", "t1_p_down", "t1_h_walks",
        "s_picks", "s_promo", "s_promo_att", "s_promo_exec", "s_promo_hit", "s_promo_dmg", "s_us", "nonpromo_attexec"]


def one(label):
    res = {}
    pend = None
    st = defaultdict(float)
    promoted = set()     # (turn, unit) promoted out of the engine's order by an attack pick
    promo_pend = {}      # unit -> turn, waiting for its first decision after the pick
    for raw in gzip.open(OUT / label / "openxcom.log.gz", "rt", encoding="utf-8", errors="replace"):
        body = raw.rstrip("\n").split("\t", 2)[-1]
        if body.startswith("[AIDECIDE] "):
            d = dict(KV.findall(body.split(" hu=")[0]))
            pend = None
            if d["side"] != "1":
                continue
            t, act = int(d["turn"]), int(d["act"])
            att = act in ATT
            st["h_dec"] += 1
            st["h_attdec"] += att
            first = promo_pend.pop(d["unit"], None) == t
            if first:
                st["s_promo_att"] += att
            pend = (t, d["unit"], att, first)
        elif body.startswith("[AIEXEC] ") and pend:
            x = json.loads(body[9:])
            t, u, att, first = pend
            pend = None
            if str(x["unit"]) != u:
                continue
            spent, walk = x.get("spent") or 0, bool(x.get("walk"))
            dmg = x.get("dmg") or 0
            st["h_spent"] += spent
            st["h_walks"] += walk
            if t == 1:
                st["t1_h_walks"] += walk
            if att and spent > 0 and not walk:
                hit = dmg > 0
                st["h_attexec"] += 1
                st["h_atthit"] += hit
                st["h_dmg"] += dmg
                st["h_downed"] += x.get("downed") or 0
                st["h_fdmg"] += x.get("fdmg") or 0
                if t == 1:
                    st["t1_h_attexec"] += 1
                    st["t1_h_atthit"] += hit
                    st["t1_h_dmg"] += dmg
                if (t, u) in promoted:
                    if first:
                        st["s_promo_exec"] += 1
                        st["s_promo_hit"] += hit
                        st["s_promo_dmg"] += dmg
                else:
                    st["nonpromo_attexec"] += 1
        elif body.startswith("[AISCHED] "):
            d = dict(KV.findall(body.split(" cands=")[0]))
            st["s_picks"] += 1
            st["s_us"] += int(d.get("us", 0))
            if d["why"].startswith("attack") and d["chosen"] != d["order"]:
                st["s_promo"] += 1
                promoted.add((int(d["turn"]), d["chosen"]))
                promo_pend[d["chosen"]] = int(d["turn"])
        elif body.startswith("[AIEVENT] ") and " what=reaction " in body:
            d = dict(KV.findall(body))
            if d["side"] == "1":
                st["p_react"] += 1
                if d["turn"] == "1":
                    st["t1_p_react"] += 1
            else:
                st["h_react"] += 1
        elif body.startswith("[AICASUALTY] "):
            d = dict(KV.findall(body))
            who = "h" if d["vfaction"] == "1" else "p" if d["vfaction"] == "0" else None
            if who:
                st[f"{who}_down_{'hturn' if d['side'] == '1' else 'pturn'}"] += 1
                if d["turn"] == "1" and d["side"] == "1":
                    st[f"t1_{who}_down"] += 1
        elif body.startswith("[AIRESULT] "):
            res = dict(KV.findall(body))
    return res, st


rows = []
for d in sorted(OUT.glob(f"{PRE}_*")):
    label = d.name
    arm, scen, s = label[len(PRE) + 1:].split("_")
    res, st = one(label)
    tsv = ARENA / f"{label}.tsv"
    outcome = "-"
    if tsv.exists():
        ls = tsv.read_text(encoding="utf-8-sig").splitlines()
        outcome = dict(zip(ls[0].split("\t"), ls[-1].split("\t"))).get("outcome", "-")
    g = lambda k: float(res.get(k, 0) or 0)
    turns = g("turn")
    r = {"label": label, "arm": arm, "scen": scen, "seed": s[1:], "outcome": outcome, "how": res.get("how", "-"), "turns": turns,
         "player": g("player"), "pdead": g("pdead"), "pout": g("pout"), "phplost": g("phplost"), "hostile": g("hostile"),
         "hdead": g("hdead"), "hout": g("hout"), "ms": g("ms")}
    r["pinc"] = (r["pdead"] + r["pout"]) / r["player"] if r["player"] else 0
    r["hinc"] = (r["hdead"] + r["hout"]) / r["hostile"] if r["hostile"] else 0
    r["ms_turn"] = r["ms"] / turns if turns else 0
    for k in COLS:
        if k not in r:
            r[k] = st.get(k, 0)
    opp = st["h_walks"] + st["h_attexec"]
    r["p_react_per10"] = 10 * st["p_react"] / opp if opp else 0
    rows.append(r)
with open(TSV, "w", encoding="utf-8-sig") as f:
    f.write("\t".join(COLS) + "\n")
    for r in rows:
        f.write("\t".join(str(round(r[k], 4)) if isinstance(r[k], float) else str(r[k]) for k in COLS) + "\n")
print(f"{PRE}: {len(rows)} battles -> {TSV}")
