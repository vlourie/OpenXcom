"""Капсулы в игре (10.11): копия стрим.sav, бойцам боя - броня капсулы, пол и внешность под нужную картинку
(индекс = look + lookVariant*4, как InventoryState). Пачки по числу бойцов. Аргументы: before|after.
Пишет E:/tmp/doll_ingame/podtest_<k>.sav, pod_run_<режим>_<k>.txt, план pod/pod_plan.json."""
import json
import os
import re
import sys
sys.stdout.reconfigure(encoding="utf-8")
MODE = sys.argv[1]
G = r"E:\OpenXCom\Пиратки\Dioxine_XPiratez"
OUT = r"E:\tmp\doll_ingame"
ARM = {"MAN_570": "STR_SPACE_POD_PEASANT_UC", "MAN_620": "STR_SPACE_POD_HYBRID_UC", "MAN_720": "STR_SPACE_POD_LAMIA_UC",
       "MAN_870": "STR_SPACE_POD_OGRE_UC", "MAN_920": "STR_SPACE_POD_GNOME_UC"}
WANT = [("MAN_570", k) for k in ("F0", "F9", "F40", "F63", "M0", "M20", "M45", "M63")] + \
       [("MAN_620", k) for k in ("F0", "F7", "M4", "M7")] + [("MAN_720", k) for k in ("F2", "F6", "M2", "M7")] + \
       [("MAN_870", k) for k in ("F5", "F13", "M3", "M15")] + [("MAN_920", k) for k in ("F0", "F23", "M12", "M23")]
text0 = open(os.path.join(G, "user", "piratez", "стрим.sav"), encoding="utf-8", errors="surrogateescape", newline="").read()
bg = text0.find("\nbattleGame:")
ids = []
for m in re.finditer(r"(?m)^    - id: (\d+)\r?\n(?:      .*\r?\n){0,6}?      faction: 0", text0[bg:]):
    i = int(m.group(1))
    if i not in ids and re.search(r"(?m)^ +id: %d\r?$" % i, text0[:bg]):
        ids.append(i)
NU = len(ids)
batches = [WANT[k:k + NU] for k in range(0, len(WANT), NU)]
print("бойцов", NU, "картинок", len(WANT), "пачек", len(batches))
plan = []
os.makedirs(os.path.join(OUT, "pod", "ingame"), exist_ok=True)
for k, b in enumerate(batches):
    SET = dict(zip(ids, b))
    text = text0
    done = 0
    for m in reversed(list(re.finditer(r"(?m)^( +)- type: STR_SOLDIER\w*\r?\n", text[:bg]))):
        head = text[m.start():m.start() + 400]
        i = re.search(r"(?m)^ +id: (\d+)", head)
        if not i or int(i.group(1)) not in SET:
            continue
        end = text.find("\n" + m.group(1) + "- type:", m.end())
        end = min(end if end > 0 else bg, bg)
        rec = text[m.start():end]
        s, key = SET[int(i.group(1))]
        n = int(key[1:])
        rec = re.sub(r"(?m)^( +armor: )\S+", r"\g<1>" + ARM[s], rec, count=1)
        rec = re.sub(r"(?m)^( +gender: )\d+", r"\g<1>" + ("0" if key[0] == "M" else "1"), rec, count=1)
        rec = re.sub(r"(?m)^( +look: )\d+", r"\g<1>%d" % (n % 4), rec, count=1)
        rec = re.sub(r"(?m)^( +lookVariant: )\d+", r"\g<1>%d" % (n // 4), rec, count=1)
        text = text[:m.start()] + rec + text[end:]
        done += 1
    assert done == len(SET), (k, done, len(SET))
    with open(os.path.join(OUT, "podtest_%d.sav" % k), "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(text)
    plan.append(["%s%s.SPK" % (s, key) for s, key in b])
    L = ["load E:/tmp/doll_ingame/podtest_%d.sav" % k, "wait 3000"]

    def series(tag):
        L.append("wait 800")
        L.append("key 105")
        L.append("wait 1200")
        for j in range(len(b)):
            L.append("shot E:/tmp/doll_ingame/pod/ingame/%s_%d_i%02d.png" % (tag, k, j))
            L.append("key 9")
            L.append("wait 700")
        L.append("key 27")
        L.append("wait 800")

    if MODE == "before":
        L.append("set oxceHdUi=0 k=1")
        series("before")
    else:
        series("on")
        L.append("set oxceHdUi=0 k=1")
        series("m0")
    open(os.path.join(OUT, "pod_run_%s_%d.txt" % (MODE, k)), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
json.dump({"units": NU, "plan": plan}, open(os.path.join(OUT, "pod", "pod_plan.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
