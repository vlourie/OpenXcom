import glob, os, collections
DIRS = [r"E:\OpenXCom\Пиратки\Dioxine_XPiratez\user\mods\Piratez\TERRAIN",
        r"E:\OpenXCom\Пиратки\Dioxine_XPiratez\UFO\TERRAIN"]
REC, F_FOOT, F_TYPE = 62, 52, 53
PART = {0: "floor", 1: "westwall", 2: "northwall", 3: "object"}
by_val = collections.Counter()
by_val_part = collections.defaultdict(collections.Counter)
sets_of = collections.defaultdict(collections.Counter)
for d in DIRS:
    for p in glob.glob(os.path.join(d, "*.MCD")) + glob.glob(os.path.join(d, "*.mcd")):
        name = os.path.splitext(os.path.basename(p))[0].upper()
        b = open(p, "rb").read()
        for i in range(0, len(b) - REC + 1, REC):
            v = b[i + F_FOOT]; t = b[i + F_TYPE]
            by_val[v] += 1
            by_val_part[v][PART.get(t, str(t))] += 1
            sets_of[v][name] += 1
for v, n in sorted(by_val.items()):
    top = ", ".join(f"{s}:{c}" for s, c in sets_of[v].most_common(14))
    print(f"footstep {v}: {n} records, sets {len(sets_of[v])}, parts {dict(by_val_part[v])}")
    print("   ", top)
