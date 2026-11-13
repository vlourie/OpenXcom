"""NATURAL GATE: the report's numbers against the scripts' outputs and the logs, stops on any mismatch. Args: gate dir, zip, report"""
import gzip
import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gate_lib as G

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
D, rep = Path(sys.argv[1]), Path(sys.argv[3]).read_text(encoding="utf-8-sig")
T = {n: (D / f"{n}.txt").read_text(encoding="utf-8", errors="replace") for n in ("judge", "proved", "m10_gate", "use", "final", "value2", "leads")}
checks = []


def has(name, s, *subs):
    for x in subs:
        checks.append((f"{name}: {x}", x in T[s]))


def text(*subs):
    for x in subs:
        checks.append((f"report: {x}", x in rep))


has("funnel", "judge", "battles 48 turns 820 decisions 39508 with a gun and a known target 31146")
for n, pat in ((24996, "0 (turn"), (9124, "lof 0, TU for a shot, one comrade"), (290, "line evidence"), (251, "A has a free cell"), (227, "the step leaves"), (77, "this weapon wounded"), (46, "B has no other"), (16, "own move costs"), (20, "2x refuted")):
    checks.append((f"funnel {n}", re.search(rf"\b{n}\s+{re.escape(pat)}", T["judge"]) is not None))
has("flips", "judge", "'after comrade left': 80, 'next turn': 18, 'same turn': 62")
has("ff", "judge", "'shots': 5385, 'fdmg_all': 12650, 'dmg_all': 30628, 'shots_fdmg': 247, 'shots_fdmg_lane': 195, 'fdmg_lane': 9612")
has("calibration", "judge", "evidence 18 evidence in engine 3")
text("24 996", "9 124", "39 508", "31 146", "12 650", "30 628", "9 612", "5 385")
for n, pat in ((62, "0 same-turn"), (49, "1 a comrade walked"), (34, "2 B still has"), (12, "3 weapon wounded"), (5, "4 B had no other"), (13, "x only by a comrade")):
    checks.append((f"proved {n}", re.search(rf"\b{n}\s+{re.escape(pat)}", T["proved"]) is not None))
has("five", "final", "L9_s2 t 2 B 1000014 [9, 41, 0] tu 86 T 571 [12, 38, 0] d 5 STR_SONIC_PISTOL m 8 25 TU p 89 p_d 89 shots 3",
    "L7_s1 t 11 B 1000019 [46, 30, 0] tu 23 T 471 [20, 22, 1] d 28 STR_LASER_RIFLE_PIR m 8 16 TU p 86 p_d 66 shots 1", "then t 8 u 471 dmg 0 f 0",
    "M10_s1 t 22 B 1000047 [20, 33, 0] tu 42 T 1 [47, 19, 0] d 31 AUX_DOOM_IMP_WEAPON m 8 31 TU p 38 p_d 6", "then t 8 u 1 dmg 0 f 9",
    "M3_s1 t 2 B 1000008 [33, 59, 0] tu 21 T 444 [31, 16, 0] d 44 AUX_SILACOID_WEAPON m 8 17 TU p 54 p_d -4",
    "M3_s2 t 4 B 1000039 [32, 57, 0] tu 65 T 444 [20, 9, 0] d 50 STR_CANISTER_GUN m 8 23 TU p 41 p_d -64")
has("base", "final", "'acts': 5385, 'wounding': 898")
checks.append(("898/5385 is 16.7", round(898 / 5385 * 100, 1) == 16.7))
checks.append(("19/34 is 56", round(19 / 34 * 100) == 56))
checks.append(("5015/9441 is 53", round(5015 / 9441 * 100) == 53))
has("use", "use", "'openings with TU': 34, 'no attack': 15, 'attack any': 19, 'attack T': 6", "'indirect evidence': 467, 'testable': 53, 'stayed closed': 41, 'opened': 12", "'decisions with a shot in hand': 9441, 'no attack': 4426, 'attack': 5015")
has("openings", "leads", "first decision at an opening, any target: {'attacks': 19, 'dmg': 0, 'fdmg': 9, 'wounding': 0}")
text("9 441", "5 015", "16,7 %", "53 %", "56 %")
for n, pat in ((13, "B has another"), (8, "no evidence"), (5, "A not blocked"), (1, "the step costs"), (1, "PASSES")):
    checks.append((f"m10 {n}", re.search(rf"^\s*{n}\s+{re.escape(pat)}", T["m10_gate"], re.M) is not None))
rows = [s for s in T["m10_gate"].splitlines() if "A not blocked" in s and s[0].isdigit()]
checks.append(("m10 false five", [int(s.split()[0]) for s in rows] == [6, 8, 17, 20, 21]))
text("6, 8, 17, 20, 21")
own = T["final"]
for n, pat in ((23, "blocked"), (22, "blocked, own cell"), (12, "  flat: own move costs at least"), (3, "  flat: own move costs no shot"), (7, "  no flat cell")):
    checks.append((f"own {n}", f"{n:3d}  {pat}" in own))
has("no19", "m10_gate", "B 1000034 (9, 23, 0) T 115 (33, 9, 0) d 28 STR_HEAVY_CANNON tu 74 shot 24 p 45", "valB 4.992 | own (12, (9, 20, 0)) 3 > 2 | A 1000047 (14, 20, 0) tu 114 step 8 shots 3 > 3 | no attack | PASSES")
has("no19", "value2", "m10 t6 B1000034 T115 d28 STR_HEAVY_CANNON m8 24TU p45 range 15 drop 2 (rul) p_d 19 | T hp 101/107>95/107", "T attacks t..t+2 4 wounding 0 dmg 0 | weapon acts 8 wounding 1 dmg 25")
has("L9", "value2", "L9_s2 t2 B1000014 T571 d5 STR_SONIC_PISTOL m8 25TU p89 range 12 drop 3 (rul) p_d 89 | T hp 75/75>9/75 w4 fell (3, 'dead') | T attacks t..t+2 0 wounding 0 dmg 0 | weapon acts 25 wounding 2 dmg 31")
has("L2", "leads", "T's casualty: turn 2 side 0 victim 1000015 dead STR_SWORD", "T's casualty: turn 2 side 1 victim 1000055 stun STR_SWORD", "T's casualty: turn 2 side 1 victim 1000057 dead STR_SWORD", "('pstart', '3', '88/88'", "line 3079 B (45, 31, 2) kneel 0 tu 102 T ((41, 28, 0), 'lof', 0")
has("L7 t10", "leads", "line 5398 B (36, 20, 0) kneel 0 tu 119", "src firepoint to (31, 25, 0) at None sp 46", "line 5406 B (31, 25, 0) kneel 0 tu 73 T ((17, 19, 1), 'lof', 1")
has("L7 t6", "leads", "src patrol.node to (5, 59, 0) at None sp 34", "line 3917 B (47, 23, 0) kneel 0 tu 33 T ((27, 33, 1), 'lof', 1")
has("L7 t11", "leads", "line 5676 B (46, 30, 0) kneel 0 tu 23 T ((20, 22, 1), 'lof', 0", "line 5768 B (46, 30, 0) kneel 0 tu 23 T ((20, 22, 1), 'lof', 1", "A at (42, 29, 0) tu 298", "T's casualty: turn 12 side 0 victim 1000022 dead", "T's casualty: turn 12 side 0 victim 1000010 dead")
has("M7", "leads", "line 1870 B (42, 31, 0) kneel 0 tu 59 T ((40, 10, 0), 'lof', 1", "line 1876 B (42, 33, 0) kneel 0 tu 51 T ((40, 10, 0), 'lof', 1", "line 1881 B (47, 30, 0) kneel 0 tu 25 T ((40, 10, 0), 'lof', 0")

# the shortlist by distance: 9 from 30 unproved, 2 proved, 5 near
short = T["judge"].split("shortlist (all gates): 16\n")[1].split("\n\n")[0].splitlines()
ds = [(s.split()[0], s.split()[1], s.split(" B")[1].split("(")[0], int(re.search(r" d(\d+) ", s).group(1))) for s in short]
proved = {("L9_s2", "t2"), ("L7_s1", "t11", "1000019"), ("M10_s1", "t22")}
far = [x for x in ds if x[3] >= 30 and (x[0], x[1]) != ("M10_s1", "t22")]
near = [x for x in ds if x[3] < 28]
checks.append(("shortlist 16", len(ds) == 16))
checks.append(("9 far", len(far) == 9))
checks.append(("5 near", len(near) == 5 and {x[0] + x[1] for x in near} == {"L2_s2t2", "L9_s2t2", "M7_s2t3", "L7_s1t6", "L7_s1t10"}))

# the L9 log itself
with zipfile.ZipFile(sys.argv[2]) as z:
    raw = z.read("out/scpa_D_L9_s2/openxcom.log.gz")
L = [s.rstrip("\n").split("\t")[-1] for s in gzip.open(io.BytesIO(raw), "rt", encoding="utf-8", errors="replace")]
b = G.Battle(L)
a = [b.exec.get(d["rec"]) or {} for d in b.by_unit[1000005] if d["turn"] == 2 and d["side"] == 1]
checks.append(("A struck 64", any(e.get("dmg") == 64 for e in a)))
checks.append(("A's last step", any(e.get("pos") == [10, 42, 0] and e.get("spent") == 14 for e in a)))
sh = [d for d in b.dec if d["side"] == 1 and d["turn"] == 2 and d["t"] in G.SHOT and G.attack_target(b, d) == 571]
checks.append(("11 shots at T, no wound", len(sh) == 11 and all(((b.exec.get(d["rec"]) or {}).get("dmg") or 0) == 0 for d in sh)))
bl = [d for d in b.by_unit[1000014] if d["turn"] == 2 and d["side"] == 1 and d["acts"]]
los = [G.shots_by_target(b.acts(d["acts"]))[571]["lof"] for d in bl if d["pos"] == (9, 41, 0) and d["tu"] == 86]
checks.append(("L9 opening", los[:1] == [0] and 1 in los))
checks.append(("L9 no attack", not any(d["t"] in {5, 6, 7, 8, 9, 10, 11, 12} for d in b.by_unit[1000014] if d["turn"] == 2 and d["side"] == 1)))
bad = [n for n, ok in checks if not ok]
print(len(checks), "checks,", "all ok" if not bad else f"FAILED: {bad}")
sys.exit(1 if bad else 0)
