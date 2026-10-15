#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""PROD_TWO_PASS_V4 - OTHER_SIDE / ROTATION: один предмет, нарисованный в игре с разных сторон (решение Vitali 07.10).

Класс: подкласс «другой бок, кандидат» переписи остатка (probes/remaining-classes-v1/report.tsv, 654 строки,
899 кадров). V3 baseline (коммит 9c1d10a79, замок v3_baseline) не трогается: здесь отдельная папка и отдельный
отбор, рисование кадра - тем же кодом V3.

Порядок (Vitali 07.10):
    presort          -> pool.json, presort.md: группы связей другого бока (families.json, alternate_view_*),
                        отсев природы, перекрасок, кусков, обломков, разрушенных видов (флаги report.tsv)
    control-propose  -> control/proposal.tsv и лист: 30-40 групп с предложенной истиной (OTHER_VIEW, MIRROR,
                        SAME_FRAMEWORK_DIFFERENT_OBJECT, NOT_OBJECT) - истину подтверждает Vitali, не модель
    cards <set>      -> карточки групп (кадры крупно и место на карте с рентгеном у каждого члена)
    classify-pack <set> / classify <set> [--runs 3] / classify-merge <set>
                     -> разбор группы Codex: три независимых ответа, довод - большинство (R-231)
    control-report   -> ворота: ложный OTHER_VIEW не больше 5 процентов, найдено настоящих OTHER_VIEW от 70
До прохождения ворот видеокарта не трогается; не прошли - только отчёт, где классификатор ошибается.
"""
import csv
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)
ENC = "utf-8-sig"
PROBES = os.path.join("art", "objects", "generation", "probes")
OUT = os.path.join(PROBES, "prod-two-pass-v4")
REPORT = os.path.join(PROBES, "remaining-classes-v1", "report.tsv")
FAMS = os.path.join("art", "objects", "families", "families.json")
SUBCLASS = "другой бок, кандидат"
ALT = ("alternate_view_possible", "alternate_view_weak")
# флаги переписи, с которыми строка не идёт в V4: не тот класс (Vitali 07.10 - природа, перекраска, кусок,
# разрушенный вид не брать). identity_disputed / identity_weak остаются - опознание решает шаг V3
EXCL_FLAGS = {"nature": "природа", "recolor_family": "перекраска", "fragment_suspect": "подозрение на кусок",
              "debris_name": "обломки по названию", "die_target": "разрушенный вид (MCD die)"}
LABELS = ("OTHER_VIEW", "MIRROR", "SAME_FRAMEWORK_DIFFERENT_OBJECT", "NOT_OBJECT", "UNCERTAIN")


def read_tsv(path):
    with open(path, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC) as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=ENC) as f:
        f.write(text)


def alt_edges():
    """Пары другого бока из families.json: каноник семейства - первый ключ записи review."""
    with open(FAMS, encoding=ENC) as f:
        fams = json.load(f)
    edges = {}
    for fm in fams:
        a = fm["canonical"].upper()
        for x in fm.get("review", []):
            if x.get("reason") in ALT:
                b = x["keys"][0].upper()
                if a != b:
                    ev = x.get("evidence") or {}
                    edges[tuple(sorted((a, b)))] = {"kind": x["reason"], "score": ev.get("score"),
                                                    "color": ev.get("color_hist"), "why": ev.get("why", []),
                                                    "family": fm["family_id"]}
    return edges


def components(nodes, edges):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen, out = set(), []
    for k in sorted(nodes):
        if k in seen:
            continue
        st, comp = [k], set()
        while st:
            x = st.pop()
            if x not in comp:
                comp.add(x)
                st.extend(adj[x] - comp)
        seen |= comp
        out.append(sorted(comp))
    return out


def do_presort():
    rows = read_tsv(REPORT)
    by = {r["asset_id"].upper(): r for r in rows}
    sub = {k: r for k, r in by.items() if r["subclass"].startswith(SUBCLASS)}
    if len(sub) != 654:
        print("!! строк подкласса %d, ожидалось 654 - перепись изменилась" % len(sub))
    edges = alt_edges()
    use = {e: v for e, v in edges.items() if e[0] in sub or e[1] in sub}
    groups = components(sub, use)
    pool, out_reason = [], Counter()
    for i, g in enumerate(groups):
        members = []
        why_out = []
        for k in g:
            r = by.get(k)
            fl = set((r or {}).get("flags", "").split())
            m = {"asset_id": k, "in_class": k in sub, "frames": int(r["frames"]) if r else 0,
                 "places": int(r["places"]) if r and r["places"] else 0,
                 "action": r["action"] if r else "", "class": r["class"] if r else "вне переписи",
                 "subclass": r["subclass"] if r else "", "flags": sorted(fl)}
            members.append(m)
            bad = [EXCL_FLAGS[x] for x in fl if x in EXCL_FLAGS]
            if bad:
                why_out.append("%s: %s" % (k, ", ".join(bad)))
            elif r and k not in sub and r["action"] == "EXCLUDE":
                why_out.append("%s: вне класса, %s" % (k, r["reason"]))
        pairs = [dict(v, a=a, b=b) for (a, b), v in use.items() if a in g and b in g]
        gid = "G%03d" % i
        item = {"group_id": gid, "members": members, "pairs": pairs,
                "rows": sum(1 for m in members if m["in_class"]),
                "frames": sum(m["frames"] for m in members if m["in_class"]),
                "places": sum(m["places"] for m in members),
                "min_score": min((p["score"] or 0) for p in pairs) if pairs else 0,
                "excluded": why_out}
        pool.append(item)
        for w in why_out:
            out_reason[w.split(": ", 1)[1]] += 1
    ok = [g for g in pool if not g["excluded"]]
    ok.sort(key=lambda g: (-g["places"], g["group_id"]))
    dump({"profile": "PROD_TWO_PASS_V4", "groups": pool, "pool_order": [g["group_id"] for g in ok]},
         os.path.join(OUT, "pool.json"))
    sz = Counter(len(g["members"]) for g in ok)
    lines = ["# V4 presort", "",
             "Подкласс «%s»: строк %d, кадров %d." % (SUBCLASS, len(sub), sum(int(r["frames"]) for r in sub.values())),
             "Групп связей другого бока: %d (членов вне подкласса %d)." % (
                 len(pool), sum(1 for g in pool for m in g["members"] if not m["in_class"])),
             "", "Отсев (группа уходит целиком, если хоть один член несёт причину):", ""]
    for w, n in out_reason.most_common():
        lines.append("- %s: %d" % (w, n))
    lines += ["", "В пуле V4: групп %d, строк подкласса %d, кадров %d, мест на картах %d." % (
        len(ok), sum(g["rows"] for g in ok), sum(g["frames"] for g in ok), sum(g["places"] for g in ok)),
              "Размеры групп в пуле: " + ", ".join("%d - %d" % kv for kv in sorted(sz.items())),
              "Нижняя оценка alt_view в группе: " + ", ".join(
                  "%s %d" % (lab, sum(1 for g in ok if lo <= g["min_score"] < hi))
                  for lab, lo, hi in (("<0.62", 0, 0.62), ("0.62-0.70", 0.62, 0.70), ("0.70-0.76", 0.70, 0.76),
                                      (">=0.76", 0.76, 9)))]
    write_text(os.path.join(OUT, "presort.md"), "\n".join(lines) + "\n")
    print("\n".join(lines))


# ------------------------------------------------------------------ контроль разбора группы

CTL = os.path.join(OUT, "control")
# Предложенная истина контроля (07.10, по листам кадров): подтверждает Vitali. Человеческой истины по повороту
# в данных нет (decisions.tsv - 5 решений о перекраске и зеркале), поэтому контроль - предложение до его слова.
# MIRROR здесь - только побайтное отражение (проверено: отличных пикселей 0); отражённый силуэт с другим светом
# (C_INT:55|54, XBASEN_BEDS:15|12) - тот же предмет с другой стороны, OTHER_VIEW.
CONTROL = [
    ("OTHER_VIEW", "MANSIONFURNITURE_MAG:3", "MANSIONFURNITURE_MAG:2", "стул спереди и сзади"),
    ("OTHER_VIEW", "COMPUTERS:7", "COMPUTERS:6", "пульт с двух сторон"),
    ("OTHER_VIEW", "AVENGER_G3:52", "AVENGER_G3:53", "кресло спереди и сзади"),
    ("OTHER_VIEW", "URBANWAR:106", "URBANWAR:107", "контейнер с двух сторон"),
    ("OTHER_VIEW", "C_INT:55", "C_INT:54", "кресло, отражён силуэт, свет свой"),
    ("OTHER_VIEW", "XBASEN_BEDS:15", "XBASEN_BEDS:12", "щит на стене, отражён силуэт, свет свой"),
    ("OTHER_VIEW", "DUNGEON_VILLA:34", "DUNGEON_VILLA:35", "стул с двух сторон (пул)"),
    ("OTHER_VIEW", "ASYLUM_WALL:25", "CULTDECOR:47", "скамья (пул)"),
    ("OTHER_VIEW", "XBASEN_BITS:26", "XBASEN_BITS:27", "табурет (пул)"),
    ("OTHER_VIEW", "RUSTSHACKS2:24", "RUSTSHACKS2:25", "стул (пул)"),
    ("OTHER_VIEW", "COMMS:69", "COMMS:71", "офисное кресло (пул)"),
    ("OTHER_VIEW", "SGR_INT03:53", "SGR_INT03:54", "розовая тумба (пул)"),
    ("OTHER_VIEW", "RUSTSHACKS2:20", "RUSTSHACKS2:21", "стойка с бронёй (пул)"),
    ("OTHER_VIEW", "URBANWAR:93", "URBANWAR:94", "тёмный контейнер (пул)"),
    ("MIRROR", "FRNITURE:9", "CITYFRNITURE:8", "побайтное отражение"),
    ("MIRROR", "GOVT:113", "GOVT:112", "побайтное отражение"),
    ("MIRROR", "XB1BR:57", "XB1BR:56", "побайтное отражение"),
    ("MIRROR", "XB1BR:67", "XB1BR:68", "побайтное отражение"),
    ("MIRROR", "FREIGHTER_COMMAND:43", "FREIGHTER_COMMAND:44", "побайтное отражение"),
    ("MIRROR", "SPACESTATION_INT:75", "SPACESTATION_INT:84", "побайтное отражение"),
    ("MIRROR", "A_DECOR:0", "A_DECOR:8", "побайтное отражение"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "TAVERN:16", "TAVERN:18", "разные портреты (пул)"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "TAVERN:15", "TAVERN:17", "разные портреты (пул)"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "COMDECOR:68", "COMDECOR:69", "разные картины (пул)"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "ABUNKER:13", "CRIBDECOR:61", "разные картины (пул)"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "MILURBITSEXT:91", "MILURBITSEXT:92", "разные плакаты (пул)"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "CARGO1:69", "CARGO1:70", "разные вывески (пул)"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "TABLES:0", "TABLES:2", "стол с разными предметами (пул)"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "GOVTDECOR:62", "GOVTDECOR:63", "стол с разными предметами (пул)"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "STATUES_NORD:7", "STATUES_NORD:8", "разные статуи (пул)"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "A_DECOR:83", "DECORLUX:53", "автомат и шкаф (пул)"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "XOPSDESERTRUINS:10", "XOPSDESERTRUINS:9", "урна и бочка"),
    ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "DECORLUX:8", "DECORLUX:7", "столик с пальмой и стол"),
    ("NOT_OBJECT", "ACHURCH:49", "ACHURCH:50", "каменная кладка"),
    ("NOT_OBJECT", "C_EXT_WALL_DBLUE:11", "C_EXT_WALL_DBLUE:12", "обшивка корабля"),
    ("NOT_OBJECT", "SIBERIABASE:4", "SIBERIABASE:5", "стена"),
    ("NOT_OBJECT", "MOUNTSNOW2:45", "MOUNTSNOW2:46", "скала"),
    ("NOT_OBJECT", "CAVEBLACK:0", "CAVEBLACK:2", "стена пещеры"),
    ("NOT_OBJECT", "XOPSUFOEXT:1", "XOPSUFOEXT:2", "стена НЛО"),
]
PAIR_HEAD = ["id", "label", "same_object", "confidence", "reason"]
CLS_BATCH = 6
CLASSIFY = """# Are these two game sprites the same object?

You see pairs of sprites from an isometric pixel-art game (X-COM style, 32x40 pixels per map cell). For each pair
A and B decide what relation they have. The tile set names are hidden on purpose: decide from the pictures only.

For every pair you get two images:
- `<id>_sprites.png`: A and B enlarged x8 on a dark floor, B flipped left-right (only to help comparing), and A and B
  at game size x3 on a light floor;
- `<id>_map.png`: where A (top) and B (bottom) stand on a real game map: the cell is boxed in red; the x-ray panel
  dims the surroundings and draws the frame on top of everything.

Answer with exactly one label per pair:
- OTHER_VIEW: the same physical object (same model, same materials, same details) seen from another side or rotated
  90 degrees: front and back of the same chair, the two faces of the same machine. Sprites drawn as a left-right
  flip of each other but with their OWN shading or slightly different drawing are also OTHER_VIEW.
- MIRROR: B is A flipped left-right pixel for pixel - same details AND the same shading after flipping.
- SAME_FRAMEWORK_DIFFERENT_OBJECT: the same frame, body or layout, but a different object: another picture in the
  same frame, another poster or screen, the same table with different things on it, a different statue on the same
  plinth, a different machine in the same box shape, or simply two different objects of similar size.
- NOT_OBJECT: at least one of the two is not a standalone object: a wall or floor section, a piece of a ship hull or
  building, terrain, rock, cave relief, vegetation.
- UNCERTAIN: you cannot decide from what is visible.

Rules:
- A wrong OTHER_VIEW is the worst mistake: it makes two different things be drawn as one. If any visible detail
  differs in a way a rotation cannot explain (another picture, other items, other colours of the same part, another
  shape), it is NOT OTHER_VIEW. If in doubt between OTHER_VIEW and anything else, answer UNCERTAIN.
- Colour shifts from lighting are not differences; a different colour scheme of the same part is.
- Decide each pair on its own.

Output exactly one line per pair, tab-separated, no header, no other text:
<id>\t<label>\t<same_object: yes|no|unsure>\t<confidence: low|medium|high>\t<short reason: what you compared>
"""


_CTX = []


def machine_mirror(p):
    """Побайтное зеркало (B - отражение A до пикселя, вместе со светом): решает машина, к Codex не идёт (Vitali 07.10)."""
    import numpy as np
    if not _CTX:
        import relation_probe as rp
        _CTX.append(rp.Ctx())
    A = np.asarray(_CTX[0].rgba(p["a"]))
    B = np.asarray(_CTX[0].rgba(p["b"]))[:, ::-1]
    return A.shape == B.shape and np.array_equal(A, B)


def ctl_pairs():
    return [{"id": "P%02d" % (i + 1), "truth": t, "a": a, "b": b, "note": n} for i, (t, a, b, n) in enumerate(CONTROL)]


def pair_set(name):
    """Набор пар: control - контроль; pool - все пары групп пула V4."""
    if name == "control":
        return ctl_pairs(), CTL
    if name == "pool":
        with open(os.path.join(OUT, "pool.json"), encoding=ENC) as f:
            pool = json.load(f)
        G = {g["group_id"]: g for g in pool["groups"]}
        out = []
        for gid in pool["pool_order"]:
            for p in sorted(G[gid]["pairs"], key=lambda p: (p["a"], p["b"])):
                out.append({"id": "Q%03d" % (len(out) + 1), "group": gid, "a": p["a"], "b": p["b"],
                            "score": p["score"]})
        return [p for p in out if not machine_mirror(p)], os.path.join(OUT, "pool_cls")
    raise SystemExit("набор: control или pool")


def do_control_propose():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    import relation_probe as rp
    pairs = ctl_pairs()
    os.makedirs(CTL, exist_ok=True)
    with open(os.path.join(CTL, "proposal.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writerow(["id", "truth_proposed", "a", "b", "note"])
        for p in pairs:
            w.writerow([p["id"], p["truth"], p["a"], p["b"], p["note"]])
    ctx = rp.Ctx()
    Z, CW, CH = 3, 32 * 3 + 6, 40 * 3 + 30
    cols = 2
    W = CW * 3 + 230
    img = Image.new("RGB", (cols * W, ((len(pairs) + cols - 1) // cols) * CH), (40, 42, 46))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)      # кириллица в подписи
    for i, p in enumerate(pairs):
        x0, y0 = (i % cols) * W, (i // cols) * CH
        for j, (k, fl) in enumerate(((p["a"], False), (p["b"], False), (p["b"], True))):
            arr = np.asarray(ctx.rgba(k), dtype=np.uint8)
            im = Image.fromarray(arr[:, ::-1] if fl else arr, "RGBA").resize((32 * Z, 40 * Z), Image.NEAREST)
            img.paste(im, (x0 + j * CW, y0), im)
        d.text((x0 + 3 * CW + 4, y0 + 4), "%s  %s\n%s\n%s\n%s" % (p["id"], p["truth"].replace(
            "SAME_FRAMEWORK_DIFFERENT_OBJECT", "SAME_FRAMEWORK"), p["a"], p["b"], p["note"]), fill=(230, 230, 120),
               font=font)
    img.save(os.path.join(CTL, "proposal_sheet.png"))
    print("контроль: %d пар, %s; лист %s" % (len(pairs), dict(Counter(p["truth"] for p in pairs)),
                                            os.path.join(CTL, "proposal_sheet.png")))


def do_cards(name):
    import identity_card as ic
    from PIL import Image
    pairs, out = pair_set(name)
    img_dir = os.path.join(out, "blind", "img")
    os.makedirs(img_dir, exist_ok=True)
    C = ic.Cards()
    notes = {}
    for p in pairs:
        f1 = os.path.join(img_dir, p["id"] + "_sprites.png")
        f2 = os.path.join(img_dir, p["id"] + "_map.png")
        if os.path.exists(f1) and os.path.exists(f2):
            continue
        A, B = C.sprite(p["a"]), C.sprite(p["b"])
        Bf = B.transpose(Image.FLIP_LEFT_RIGHT)
        top = ic.row([ic.labelled(ic.big(A, 8, ic.DARK), "A x8"), ic.labelled(ic.big(B, 8, ic.DARK), "B x8"),
                      ic.labelled(ic.big(Bf, 8, ic.DARK), "B flipped left-right x8")])
        bot = ic.row([ic.labelled(ic.big(A, 3, ic.LIGHT), "A x3"), ic.labelled(ic.big(B, 3, ic.LIGHT), "B x3")])
        ic.stack([top, bot]).save(f1)
        maps, nn = [], []
        for lab, k in (("A", p["a"]), ("B", p["b"])):
            places, total = C.places([k])
            got = None
            for t, b, cnt, kk in places:
                pair, note = C.p_place(kk, t, b)
                if pair:
                    got = ic.labelled(ic.fit(pair[0], 1500), "%s on a map" % lab)
                    break
            nn.append("%s: %s" % (lab, "есть место" if got else "НЕТ места на карте"))
            maps.append(got if got is not None else ic.labelled(Image.new("RGB", (400, 60), (20, 20, 24)),
                                                                 "%s: not found on any map" % lab))
        ic.stack(maps).save(f2)
        notes[p["id"]] = nn
        print(p["id"], p["a"], p["b"], "; ".join(nn), flush=True)
    dump(notes, os.path.join(out, "cards_notes.json"))


def do_classify_pack(name):
    pairs, out = pair_set(name)
    blind = os.path.join(out, "blind")
    with open(os.path.join(blind, "CLASSIFY.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(CLASSIFY)
    batches = {}
    for k in range(0, len(pairs), CLS_BATCH):
        bn = "B%02d" % (k // CLS_BATCH + 1)
        part = pairs[k:k + CLS_BATCH]
        batches[bn] = [p["id"] for p in part]
        lines = ["# Batch %s" % bn, "", "Instructions: CLASSIFY.md in this folder.", ""]
        for p in part:
            for s in ("sprites", "map"):
                if not os.path.exists(os.path.join(blind, "img", "%s_%s.png" % (p["id"], s))):
                    raise SystemExit("нет карточки %s_%s - сначала cards" % (p["id"], s))
            lines += ["## %s" % p["id"], "", "images: img/%s_sprites.png, img/%s_map.png" % (p["id"], p["id"]), ""]
        with open(os.path.join(blind, bn + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    dump({"n": len(pairs), "batches": batches}, os.path.join(out, "pack.json"))
    print("пакет %s: %d пар, %d батчей" % (blind, len(pairs), len(batches)))


def parse_pairs(text, want):
    got = {}
    for line in text.splitlines():
        f = [x.strip() for x in line.strip().strip("`").split("\t")]
        if len(f) < 4 or f[0] not in want or f[1].upper() not in LABELS:
            continue
        got[f[0]] = {"id": f[0], "label": f[1].upper(), "same_object": f[2].lower(), "confidence": f[3].lower(),
                     "reason": f[4] if len(f) > 4 else ""}
    return got


def save_pairs(path, ans):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=PAIR_HEAD, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        for k in sorted(ans):
            w.writerow({c: ans[k].get(c, "").replace("\t", " ") for c in PAIR_HEAD})
    os.replace(path + ".tmp", path)


def do_classify(name, runs, effort, max_calls):
    """Codex, runs независимых прогонов (каждый батч - отдельная сессия codex exec), ответы answers/r<N>.tsv."""
    import shutil
    import subprocess
    import time
    pairs, out = pair_set(name)
    with open(os.path.join(out, "pack.json"), encoding=ENC) as f:
        pack = json.load(f)
    blind = os.path.abspath(os.path.join(out, "blind"))
    codex = shutil.which("codex") or "codex"
    logs = os.path.join(out, "answers", "logs")
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(blind, "CLASSIFY.md"), encoding="utf-8") as f:
        rules = f.read()
    # предел вызовов, согласованный с Vitali до запуска (07.10: 41 лишний вызов на контролях)
    todo = 0
    for r in range(1, runs + 1):
        path = os.path.join(out, "answers", "r%d.tsv" % r)
        done = {x["id"] for x in read_tsv(path)} if os.path.exists(path) else set()
        todo += sum(1 for ids in pack["batches"].values() if not all(i in done for i in ids))
    print("вызовов Codex к выполнению: %d (предел %d), effort %s" % (todo, max_calls, effort), flush=True)
    if todo > max_calls:
        raise SystemExit("вызовов %d больше согласованного предела %d - не запускаю" % (todo, max_calls))
    for r in range(1, runs + 1):
        path = os.path.join(out, "answers", "r%d.tsv" % r)
        ans = {x["id"]: x for x in read_tsv(path)} if os.path.exists(path) else {}
        for bn, ids in pack["batches"].items():
            if all(i in ans for i in ids):
                continue
            with open(os.path.join(blind, bn + ".md"), encoding="utf-8") as f:
                batch = f.read()
            imgs = [os.path.join(blind, "img", "%s_%s.png" % (i, s)) for i in ids for s in ("sprites", "map")]
            task = (rules + "\n\n" + batch + "\nThe images are attached in this order: " +
                    ", ".join("image %d = %s" % (k + 1, os.path.basename(q)) for k, q in enumerate(imgs)) +
                    ".\nAnswer now: exactly %d lines, one per pair, as specified.\n" % len(ids))
            last = os.path.abspath(os.path.join(logs, "r%d_%s.last.txt" % (r, bn)))
            t0 = time.time()
            cmd = [codex, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-C", blind, "--color", "never",
                   "-c", "model_reasoning_effort=" + effort, "-o", last] + sum([["-i", q] for q in imgs], []) + ["-"]
            with open(os.path.join(logs, "r%d_%s.log" % (r, bn)), "w", encoding="utf-8") as lf:   # stdin (R-222)
                rc = subprocess.run(cmd, cwd=blind, stdout=lf, stderr=subprocess.STDOUT,
                                    input=task.encode("utf-8"), timeout=40 * 60).returncode
            log = open(os.path.join(logs, "r%d_%s.log" % (r, bn)), encoding="utf-8", errors="replace").read()
            whole = "Answer now: exactly %d lines" % len(ids) in log
            text = open(last, encoding="utf-8", errors="replace").read() if os.path.exists(last) else ""
            got = parse_pairs(text, set(ids))
            ans.update(got)
            save_pairs(path, ans)
            print("r%d %s: код %d, %.0f с, ответов %d из %d, задание дошло целиком: %s" % (
                r, bn, rc, time.time() - t0, len(got), len(ids), "да" if whole else "НЕТ"), flush=True)


def majority(pairs, out):
    """Большинство из трёх прогонов (R-231): ярлык, названный хотя бы двумя; иначе UNCERTAIN."""
    runs = []
    for r in (1, 2, 3):
        p = os.path.join(out, "answers", "r%d.tsv" % r)
        runs.append({x["id"]: x for x in read_tsv(p)} if os.path.exists(p) else {})
    res = {}
    for p in pairs:
        labs = [run[p["id"]]["label"] for run in runs if p["id"] in run]
        c = Counter(labs).most_common(1)
        lab = c[0][0] if c and c[0][1] >= 2 else "UNCERTAIN"
        res[p["id"]] = {"label": lab, "votes": labs}
    return res, sum(1 for run in runs if run)


def do_classify_merge(name):
    pairs, out = pair_set(name)
    res, n = majority(pairs, out)
    with open(os.path.join(out, "classified.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writerow(["id", "a", "b", "label", "votes"] + (["truth"] if name == "control" else ["group"]))
        for p in pairs:
            r = res[p["id"]]
            w.writerow([p["id"], p["a"], p["b"], r["label"], ",".join(r["votes"]),
                        p.get("truth", p.get("group", ""))])
    print("прогонов %d; итог: %s" % (n, dict(Counter(r["label"] for r in res.values()))))
    return res


def do_pool_summary():
    """Один круг Codex по пулу (Vitali 07.10, правило консервативное): OTHER_VIEW с уверенностью high и same_object
    yes - кандидат V4; OTHER_VIEW medium/low, UNCERTAIN и пропуск ответа - residual (второго круга нет);
    MIRROR - вне V4 (и побайтные зеркала, снятые машиной до Codex); SAME_FRAMEWORK - V3 отдельными предметами;
    NOT_OBJECT - исключить. Группа V4 - связная компонента рёбер OTHER_VIEW sure."""
    out = os.path.join(OUT, "pool_cls")
    path = os.path.join(out, "answers", "r1.tsv")
    if not os.path.exists(path):
        raise SystemExit("нет ответов %s" % path)
    ans = {x["id"]: x for x in read_tsv(path)}
    with open(os.path.join(OUT, "pool.json"), encoding=ENC) as f:
        pool = json.load(f)
    G = {g["group_id"]: g for g in pool["groups"]}
    allp = []
    for gid in pool["pool_order"]:
        for p in sorted(G[gid]["pairs"], key=lambda p: (p["a"], p["b"])):
            allp.append({"id": "Q%03d" % (len(allp) + 1), "group": gid, "a": p["a"], "b": p["b"]})
    rows, weak_ov = [], 0
    for p in allp:
        if machine_mirror(p):
            cat, a = "MIRROR", {"label": "MIRROR", "confidence": "machine", "same_object": "", "reason": "побайтное"}
        else:
            a = ans.get(p["id"], {"label": "UNCERTAIN", "confidence": "", "same_object": "", "reason": "нет ответа"})
            cat = a["label"]
            if cat == "OTHER_VIEW" and not (a["confidence"] == "high" and a["same_object"] == "yes"):
                cat, weak_ov = "UNCERTAIN", weak_ov + 1
        rows.append(dict(p, category=cat, label=a["label"], confidence=a["confidence"],
                         same_object=a["same_object"], reason=a.get("reason", "")))
    sure = [r for r in rows if r["category"] == "OTHER_VIEW"]
    comps = components(sorted({k for r in sure for k in (r["a"], r["b"])}), [(r["a"], r["b"]) for r in sure])
    head = ["id", "group", "a", "b", "category", "label", "confidence", "same_object", "reason"]
    with open(os.path.join(out, "classified.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=head, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n",
                           extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: str(r.get(c, "")).replace("\t", " ") for c in head})
    dump([sorted(c) for c in comps], os.path.join(out, "v4_groups.json"))
    c = Counter(r["category"] for r in rows)
    lines = ["# V4 pool: один круг Codex (high), пар %d, ответов %d" % (len(rows), len(ans)), ""]
    lines += ["- OTHER_VIEW sure: %d" % c["OTHER_VIEW"],
              "- MIRROR: %d (из них побайтных, снятых машиной: %d)" % (
                  c["MIRROR"], sum(1 for r in rows if r["confidence"] == "machine")),
              "- SAME_FRAMEWORK_DIFFERENT_OBJECT: %d" % c["SAME_FRAMEWORK_DIFFERENT_OBJECT"],
              "- NOT_OBJECT: %d" % c["NOT_OBJECT"],
              "- UNCERTAIN: %d (из них OTHER_VIEW не high/yes: %d)" % (c["UNCERTAIN"], weak_ov), "",
              "Групп V4 (связные по OTHER_VIEW sure): %d, кадров в них %d." % (len(comps), sum(len(x) for x in comps))]
    write_text(os.path.join(out, "summary.md"), "\n".join(lines) + "\n")
    print("\n".join(lines))


def do_control_report():
    pairs, out = pair_set("control")
    truth_path = os.path.join(CTL, "truth.tsv")
    if not os.path.exists(truth_path):
        raise SystemExit("нет control/truth.tsv: истину контроля подтверждает Vitali (proposal.tsv - предложение)")
    truth = {r["id"]: r["truth"] for r in read_tsv(truth_path)}
    res, n = majority(pairs, out)
    if n < 2:
        raise SystemExit("прогонов %d - ворота не считаются (нужно хотя бы 2: Vitali 07.10 остановил третий круг)" % n)
    # CONTROL_UNCERTAIN (Vitali 07.10: P05, P06, P12, P14 - ярлык не подтверждён) - ни в числителе, ни в знаменателе
    skip = [p for p in pairs if truth[p["id"]] == "CONTROL_UNCERTAIN"]
    pairs = [p for p in pairs if truth[p["id"]] != "CONTROL_UNCERTAIN"]
    ov = [p for p in pairs if truth[p["id"]] == "OTHER_VIEW"]
    neg = [p for p in pairs if truth[p["id"]] != "OTHER_VIEW"]
    neg_nm = [p for p in neg if truth[p["id"]] != "MIRROR"]     # побайтные зеркала в производстве отсекает машина
    fp_nm = [p for p in neg_nm if res[p["id"]]["label"] == "OTHER_VIEW"]
    fp = [p for p in neg if res[p["id"]]["label"] == "OTHER_VIEW"]
    fp_diff = [p for p in fp if truth[p["id"]] in ("SAME_FRAMEWORK_DIFFERENT_OBJECT", "NOT_OBJECT")]
    tp = [p for p in ov if res[p["id"]]["label"] == "OTHER_VIEW"]
    fpr = len(fp) / len(neg) if neg else 0.0
    rec = len(tp) / len(ov) if ov else 0.0
    ok = fpr <= 0.05 and rec >= 0.70
    conf = Counter((truth[p["id"]], res[p["id"]]["label"]) for p in pairs)
    lines = ["# V4 group control: разбор пары", "",
             "Пар %d: OTHER_VIEW %d, прочих %d. Прогонов Codex %d, довод - ярлык хотя бы двух прогонов "
             "(при двух - согласие обоих), иначе UNCERTAIN." % (len(pairs), len(ov), len(neg), n),
             "Вне ворот (CONTROL_UNCERTAIN, решение Vitali 07.10): %s." % (
                 ", ".join("%s %s|%s" % (p["id"], p["a"], p["b"]) for p in skip) or "нет"), "",
             "- ложный OTHER_VIEW без побайтных зеркал (их отсекает машина до Codex): %d из %d" % (
                 len(fp_nm), len(neg_nm)),
             "- ложный OTHER_VIEW: %d из %d = %.1f%% (ворота <= 5%%) %s" % (len(fp), len(neg), 100 * fpr,
                                                                           "PASS" if fpr <= 0.05 else "FAIL"),
             "  из них разные предметы или не предмет: %d" % len(fp_diff),
             "- найдено настоящих OTHER_VIEW: %d из %d = %.1f%% (ворота >= 70%%) %s" % (
                 len(tp), len(ov), 100 * rec, "PASS" if rec >= 0.70 else "FAIL"),
             "", "ИТОГ: %s" % ("PASS" if ok else "FAIL"), "", "## Матрица (истина -> ответ)", ""]
    for (t, l), c in sorted(conf.items()):
        lines.append("- %s -> %s: %d" % (t, l, c))
    lines += ["", "## Ошибки", ""]
    for p in pairs:
        t, r = truth[p["id"]], res[p["id"]]
        if t != r["label"]:
            lines.append("- %s %s | %s: истина %s, ответ %s (голоса %s)" % (
                p["id"], p["a"], p["b"], t, r["label"], ",".join(r["votes"])))
    write_text(os.path.join(CTL, "report.md"), "\n".join(lines) + "\n")
    print("\n".join(lines))


# --- судья согласованности группы: контроль с правдой по построению -------------------------------------------
# Правды «эти HD-кадры - один предмет» в данных нет: стороны прежнего пака рисовались порознь (отражённый B от A
# отличается на 12-60 из 255 даже у пар OTHER_VIEW). Поэтому контроль собирается из HD-кадров пака установки так,
# что ответ известен заранее: годное (тот же кадр отражённым, с другим светом), разные предметы (пары каркаса из
# CONTROL, подмена HD чужим предметом при своём спрайте) и дефекты (цвет, масштаб, пропавшая часть).
CONS = os.path.join(OUT, "control_cons")
PACK_HD = os.path.join(ROOT, "Пиратки", "Dioxine_XPiratez", "user", "mods", "hd", "hd", "TERRAIN")
CONS_KINDS = [  # вид, правда, сколько
    ("POS_MIRROR", "CONSISTENT", 10), ("POS_LIGHT", "CONSISTENT", 10),
    ("DIFF_FRAMEWORK", "INCONSISTENT", 12), ("DIFF_SWAP", "INCONSISTENT", 10),
    ("DEF_COLOR", "INCONSISTENT", 10), ("DEF_SCALE", "INCONSISTENT", 10), ("DEF_PART", "INCONSISTENT", 10)]
CONS_LABELS = ("CONSISTENT", "INCONSISTENT", "UNCERTAIN")
CONS_HEAD = ["id", "label", "problem", "confidence", "reason"]
CONS_BATCH = 6
CONSIST = """# Do these HD frames show one and the same object?

An isometric pixel-art game (X-COM style) draws one physical object with several sprites: one per side it can face
(front, back, rotated 90 degrees). Each small game sprite (32x40 pixels) was redrawn as a high-resolution HD frame.
For every group below decide whether the HD frames TOGETHER show ONE object: the same model, materials, colours,
details, wear and size, each HD frame faithful to its own game sprite.

For every group you get one image `<id>_group.png`, one column per frame:
- top row: the game sprite of that frame, enlarged x8 (the truth about shape, colours and size in the cell);
- middle row: the HD frame of that sprite at the same scale, on a dark floor;
- bottom row: the same HD frame on a light floor (to see dark parts and edges).
All panels have the same size and the same cell, so sizes can be compared directly.

Differences that are FINE: the other side shows other parts of the object; light and shading change with the side;
a silhouette that is a left-right flip of the other frame; HD detail that the sprite only hints at.

Differences that are NOT fine:
- DIFFERENT_OBJECT: the frames show different things (another picture, another machine, other items on top);
- COLOR_MATERIAL: the same part has another colour scheme or material than in the other frame or its own sprite;
- SCALE: the object is clearly bigger or smaller in its cell than in its sprite or than in the other frame;
- MISSING_OR_EXTRA_PART: a part visible in the sprite is missing in the HD frame, or the HD frame adds a big part;
- OTHER: anything else that makes the group not one consistent object (say what).

Answer per group:
- CONSISTENT: one object, every difference is of the fine kind;
- INCONSISTENT: at least one difference of the not-fine kind; name the main problem;
- UNCERTAIN: you cannot decide.
A wrong CONSISTENT is the worst mistake: it lets two different or mismatched pictures into the game as one object. If
in doubt, answer UNCERTAIN, not CONSISTENT.

Output exactly one line per group, tab-separated, no header, no other text:
<id>\t<CONSISTENT|INCONSISTENT|UNCERTAIN>\t<problem: NONE|DIFFERENT_OBJECT|COLOR_MATERIAL|SCALE|MISSING_OR_EXTRA_PART|OTHER>\t<confidence: low|medium|high>\t<short reason: which frames and what you compared>
"""


def pack_hd(key):
    import numpy as np
    from PIL import Image
    s, n = key.split(":")
    p = os.path.join(PACK_HD, s + ".PCK", n + ".png")
    if not os.path.exists(p):
        raise SystemExit("нет HD-кадра %s в паке установки" % key)
    im = Image.open(p).convert("RGBA")
    if im.size != (128, 160):
        im = im.resize((128, 160), Image.LANCZOS)
    return np.asarray(im).copy()


def cons_variant(kind, hd, rng):
    """Порча второго кадра по виду контроля. hd - RGBA 160x128, уже отражённый."""
    import colorsys
    import numpy as np
    out = hd.copy()
    rgb = out[..., :3].astype(np.float32)
    a = out[..., 3] > 0
    if kind == "POS_LIGHT":                      # свет с другой стороны: плавный перепад яркости
        g = np.linspace(1.15, 0.80, out.shape[1])[None, :, None]
        out[..., :3] = np.clip(rgb * g, 0, 255).astype(np.uint8)
    elif kind == "DEF_COLOR":                    # другая цветовая схема: поворот тона и подъём насыщенности
        sh = rng.choice([0.33, 0.5, 0.67])
        f = rgb[a] / 255.0
        hsv = np.array([colorsys.rgb_to_hsv(*c) for c in f])
        hsv[:, 0] = (hsv[:, 0] + sh) % 1.0
        hsv[:, 1] = np.clip(np.maximum(hsv[:, 1], 0.45) * 1.2, 0, 1)
        out[..., :3][a] = (np.array([colorsys.hsv_to_rgb(*c) for c in hsv]) * 255).astype(np.uint8)
    elif kind == "DEF_SCALE":                    # предмет 0.7 от своего, стоит на том же месте клетки
        from PIL import Image
        ys, xs = np.nonzero(a)
        box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        cut = Image.fromarray(hd).crop(box)
        w, h = max(1, int(cut.width * 0.7)), max(1, int(cut.height * 0.7))
        cut = cut.resize((w, h), Image.LANCZOS)
        canvas = Image.new("RGBA", (hd.shape[1], hd.shape[0]), (0, 0, 0, 0))
        cx = (box[0] + box[2]) // 2
        canvas.paste(cut, (cx - w // 2, box[3] - h), cut)
        out = np.asarray(canvas).copy()
    elif kind == "DEF_PART":                     # верхняя треть предмета пропала
        ys = np.nonzero(a)[0]
        cut = ys.min() + int(0.35 * (ys.max() - ys.min() + 1))
        out[:cut, :, 3] = 0
    return out


def cons_items():
    """Группы контроля: id C01..., вид, правда, кадры [(подпись, спрайт key, отражён, источник HD, порча)]."""
    import random
    rng = random.Random(4040)
    ov = [(a, b) for t, a, b, n in CONTROL if t == "OTHER_VIEW"]
    fw = [(a, b) for t, a, b, n in CONTROL if t == "SAME_FRAMEWORK_DIFFERENT_OBJECT"]
    items = []
    for k, (kind, truth, cnt) in enumerate(CONS_KINDS):
        for i in range(cnt):
            if kind == "DIFF_FRAMEWORK":
                a, b = fw[i]
                fr = [(a, False, a, ""), (b, False, b, "")]
            else:
                base = ov[(k * 4 + i) % len(ov)][rng.choice((0, 1))]
                if kind == "DIFF_SWAP":                  # свой спрайт, а HD - чужого предмета (не тот предмет)
                    other = ov[(k * 4 + i + 5) % len(ov)][0]
                    fr = [(base, False, base, ""), (base, True, other, "")]
                else:
                    fr = [(base, False, base, ""), (base, True, base, kind)]
            if rng.random() < 0.5:
                fr = fr[::-1]
            items.append({"kind": kind, "truth": truth, "frames": fr})
    rng.shuffle(items)
    for i, it in enumerate(items):
        it["id"] = "C%02d" % (i + 1)
    return items


def do_cons_build():
    """Карточки контроля судьи согласованности: blind/img/<id>_group.png, правда - truth.tsv вне blind."""
    import random
    import numpy as np
    from PIL import Image, ImageDraw
    import identity_card as ic
    import relation_probe as rp
    ctx = rp.Ctx()
    rng = random.Random(77)
    items = cons_items()
    img_dir = os.path.join(CONS, "blind", "img")
    os.makedirs(img_dir, exist_ok=True)
    W, H, L = 256, 320, 18

    def panel(arr, bg, text):
        im = Image.new("RGB", (W, H + L), (18, 18, 22))
        floor = Image.new("RGB", (W, H), bg)
        pic = Image.fromarray(arr, "RGBA")
        pic = pic.resize((W, H), Image.NEAREST if arr.shape[1] == 32 else Image.BICUBIC)
        floor.paste(pic, (0, 0), pic)
        im.paste(floor, (0, L))
        ImageDraw.Draw(im).text((4, 3), text, fill=(240, 220, 90))
        return im

    for it in items:
        cols = []
        for j, (sk, flip, hk, spoil) in enumerate(it["frames"], 1):
            spr = np.asarray(ctx.rgba(sk), dtype=np.uint8)
            hd = pack_hd(hk)
            if flip:
                spr, hd = spr[:, ::-1].copy(), hd[:, ::-1].copy()
            if spoil:
                hd = cons_variant(spoil, hd, rng)
            cols.append([panel(spr, ic.DARK, "frame %d: game sprite x8" % j),
                         panel(hd, ic.DARK, "frame %d: HD" % j),
                         panel(hd, ic.LIGHT, "frame %d: HD on light floor" % j)])
        sheet = Image.new("RGB", (len(cols) * (W + 8), 3 * (H + L + 6)), (30, 30, 34))
        for c, col in enumerate(cols):
            for r, p in enumerate(col):
                sheet.paste(p, (c * (W + 8), r * (H + L + 6)))
        sheet.save(os.path.join(img_dir, it["id"] + "_group.png"))
    with open(os.path.join(CONS, "truth.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writerow(["id", "kind", "truth", "frames"])
        for it in items:
            w.writerow([it["id"], it["kind"], it["truth"],
                        " ; ".join("%s%s hd=%s %s" % (s, " flip" if fl else "", h, sp) for s, fl, h, sp in it["frames"])])
    blind = os.path.join(CONS, "blind")
    with open(os.path.join(blind, "CONSIST.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(CONSIST)
    batches = {}
    for k in range(0, len(items), CONS_BATCH):
        bn = "B%02d" % (k // CONS_BATCH + 1)
        part = items[k:k + CONS_BATCH]
        batches[bn] = [p["id"] for p in part]
        lines = ["# Batch %s" % bn, "", "Instructions: CONSIST.md in this folder.", ""]
        for p in part:
            lines += ["## %s" % p["id"], "", "image: img/%s_group.png" % p["id"], ""]
        with open(os.path.join(blind, bn + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    dump({"n": len(items), "batches": batches}, os.path.join(CONS, "pack.json"))
    print("контроль согласованности: %d групп, %s; %d батчей; %s" % (
        len(items), dict(Counter(i["kind"] for i in items)), len(batches), blind))


def parse_cons(text, want):
    got = {}
    for line in text.splitlines():
        f = [x.strip() for x in line.strip().strip("`").split("\t")]
        if len(f) < 4 or f[0] not in want or f[1].upper() not in CONS_LABELS:
            continue
        got[f[0]] = {"id": f[0], "label": f[1].upper(), "problem": f[2].upper(), "confidence": f[3].lower(),
                     "reason": f[4] if len(f) > 4 else ""}
    return got


def do_cons_judge(runs, effort):
    """Codex на контроле согласованности: runs независимых прогонов, answers/r<N>.tsv (как do_classify)."""
    import shutil
    import subprocess
    import time
    with open(os.path.join(CONS, "pack.json"), encoding=ENC) as f:
        pack = json.load(f)
    blind = os.path.abspath(os.path.join(CONS, "blind"))
    codex = shutil.which("codex") or "codex"
    logs = os.path.join(CONS, "answers", "logs")
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(blind, "CONSIST.md"), encoding="utf-8") as f:
        rules = f.read()
    for r in range(1, runs + 1):
        path = os.path.join(CONS, "answers", "r%d.tsv" % r)
        ans = {x["id"]: x for x in read_tsv(path)} if os.path.exists(path) else {}
        for bn, ids in pack["batches"].items():
            if all(i in ans for i in ids):
                continue
            with open(os.path.join(blind, bn + ".md"), encoding="utf-8") as f:
                batch = f.read()
            imgs = [os.path.join(blind, "img", "%s_group.png" % i) for i in ids]
            task = (rules + "\n\n" + batch + "\nThe images are attached in this order: " +
                    ", ".join("image %d = %s" % (k + 1, os.path.basename(q)) for k, q in enumerate(imgs)) +
                    ".\nAnswer now: exactly %d lines, one per group, as specified.\n" % len(ids))
            last = os.path.abspath(os.path.join(logs, "r%d_%s.last.txt" % (r, bn)))
            t0 = time.time()
            cmd = [codex, "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-C", blind, "--color", "never",
                   "-c", "model_reasoning_effort=" + effort, "-o", last] + sum([["-i", q] for q in imgs], []) + ["-"]
            with open(os.path.join(logs, "r%d_%s.log" % (r, bn)), "w", encoding="utf-8") as lf:   # stdin (R-222)
                rc = subprocess.run(cmd, cwd=blind, stdout=lf, stderr=subprocess.STDOUT,
                                    input=task.encode("utf-8"), timeout=40 * 60).returncode
            log = open(os.path.join(logs, "r%d_%s.log" % (r, bn)), encoding="utf-8", errors="replace").read()
            whole = "Answer now: exactly %d lines" % len(ids) in log
            text = open(last, encoding="utf-8", errors="replace").read() if os.path.exists(last) else ""
            got = parse_cons(text, set(ids))
            ans.update(got)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "w", encoding=ENC, newline="") as f:
                w = csv.DictWriter(f, fieldnames=CONS_HEAD, delimiter="\t", quoting=csv.QUOTE_NONE,
                                   lineterminator="\n")
                w.writeheader()
                for k in sorted(ans):
                    w.writerow({c: ans[k].get(c, "").replace("\t", " ") for c in CONS_HEAD})
            os.replace(path + ".tmp", path)
            print("r%d %s: код %d, %.0f с, ответов %d из %d, задание дошло целиком: %s" % (
                r, bn, rc, time.time() - t0, len(got), len(ids), "да" if whole else "НЕТ"), flush=True)


def do_cons_report():
    """Ворота судьи согласованности: разные предметы - ложный CONSISTENT 0; дефекты - не больше 5%;
    годные - CONSISTENT не меньше 70% (UNCERTAIN не ошибка, но уходит человеку)."""
    truth = {r["id"]: r for r in read_tsv(os.path.join(CONS, "truth.tsv"))}
    runs = []
    for r in (1, 2, 3):
        p = os.path.join(CONS, "answers", "r%d.tsv" % r)
        runs.append({x["id"]: x for x in read_tsv(p)} if os.path.exists(p) else {})
    n = sum(1 for run in runs if run)
    if n < 3:
        raise SystemExit("прогонов %d из 3 - ворота не считаются" % n)
    res = {}
    for i in truth:
        labs = [run[i]["label"] for run in runs if i in run]
        c = Counter(labs).most_common(1)
        res[i] = (c[0][0] if c and c[0][1] >= 2 else "UNCERTAIN", labs,
                  [run[i]["problem"] for run in runs if i in run])
    diff = [i for i in truth if truth[i]["kind"].startswith("DIFF")]
    defs = [i for i in truth if truth[i]["kind"].startswith("DEF")]
    pos = [i for i in truth if truth[i]["kind"].startswith("POS")]
    fp_diff = [i for i in diff if res[i][0] == "CONSISTENT"]
    fp_def = [i for i in defs if res[i][0] == "CONSISTENT"]
    tp = [i for i in pos if res[i][0] == "CONSISTENT"]
    g1, g2, g3 = not fp_diff, len(fp_def) <= 0.05 * len(defs), len(tp) >= 0.70 * len(pos)
    lines = ["# V4 group control: судья согласованности", "",
             "Групп %d, прогонов Codex %d, довод - большинство из трёх (иначе UNCERTAIN). Правда по построению." % (
                 len(truth), n), "",
             "- разные предметы, ложный CONSISTENT: %d из %d (ворота 0) %s" % (len(fp_diff), len(diff),
                                                                             "PASS" if g1 else "FAIL"),
             "- дефекты цвета, масштаба, части, ложный CONSISTENT: %d из %d (ворота <= 5%%) %s" % (
                 len(fp_def), len(defs), "PASS" if g2 else "FAIL"),
             "- годные, CONSISTENT: %d из %d (ворота >= 70%%) %s" % (len(tp), len(pos), "PASS" if g3 else "FAIL"),
             "", "ИТОГ: %s" % ("PASS" if g1 and g2 and g3 else "FAIL"), "", "## По видам", ""]
    by = Counter((truth[i]["kind"], res[i][0]) for i in truth)
    for (k, l), c in sorted(by.items()):
        lines.append("- %s -> %s: %d" % (k, l, c))
    lines += ["", "## Ошибки и UNCERTAIN", ""]
    for i in sorted(truth):
        if res[i][0] != truth[i]["truth"]:
            lines.append("- %s %s: ответ %s (голоса %s, проблемы %s) | %s" % (
                i, truth[i]["kind"], res[i][0], ",".join(res[i][1]), ",".join(res[i][2]), truth[i]["frames"]))
    write_text(os.path.join(CONS, "report.md"), "\n".join(lines) + "\n")
    print("\n".join(lines))


# ---------------------------------------------------------------- рендер V4 pilot (Vitali 07.10)
# 23 группы OTHER_VIEW sure, 51 кадр. Путь кадра - ровно V3 (restore_batch_v1 + restore_probe_v1: промпт RESTORE,
# негатив, вариант C - эскиз struct_guide и СВОЙ спрайт кадра, подложка с правилом тонкого края, до трёх попыток,
# ворота photo_accept и asset_fidelity). Меняется только текст предмета: одно описание группы на все её кадры
# (идентичность, материал, цвет, детали), и одно зерно на группу. HD другого ракурса на вход не подаётся.
# Связи V7 и блокеры generation.tsv не применяются: состав задан разбором пула V4 (pool_cls/v4_groups.json).

REND = os.path.join(OUT, "render_v4")
GROUPS = os.path.join(OUT, "pool_cls", "v4_groups.json")
V3_BASE = os.path.join(PROBES, "prod-two-pass-v3", "baseline.json")
SEED_V4 = 10100                          # зерно группы = SEED_V4 + номер группы
SAME_AS_V3 = ("prompt", "negative", "variant", "gates", "machine", "thin_rule", "code_sha256")


def use_rb():
    """restore_batch_v1 на папке рендера V4 (как prod_two_pass_v1.use_rb); модули V3 не правятся."""
    import restore_batch_v1 as rb
    out = REND.replace("\\", "/")
    rb.OUT, rb.PROFILE = out, "PROD_TWO_PASS_V4_PILOT"
    rb.rp.OUT, rb.rp.RUN1, rb.rp.PROBE, rb.rp.ONLY = out, out, rb.PROFILE, None
    return rb


def rend_body():
    rb = use_rb()
    import hashlib
    full = rb.baseline_body.__globals__
    import asset_fidelity as AF
    import inspect

    def fsha(p):
        with open(os.path.join(ROOT, p), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    return {"profile": rb.PROFILE,
            "decision": "Vitali 07.10: рендер 23 групп V4 / 51 кадра, OTHER_VIEW sure; V4 pilot, не baseline",
            "prompt": rb.rp.RESTORE, "negative": rb.rp.negative(), "variant": rb.rp.VARIANT,
            "gates": list(AF.CHECKS), "machine": "photo_accept", "seed_v4": SEED_V4,
            "thin_rule": {"name": "THIN_EDGE_NEUTRAL_BACKGROUND", "thin_min": full["THIN_MIN"],
                          "panel": full["THIN_PANEL"],
                          "code": inspect.getsource(rb.thin_ratio) + inspect.getsource(rb.panels_rule)},
            "code_sha256": {p: fsha(p) for p in rb.BASE_CODE},
            "jobs_sha256": fsha(os.path.join(REND, "jobs.json")),
            "descriptions_sha256": fsha(os.path.join(REND, "descriptions.tsv"))}


def do_render_build():
    """jobs.json и descriptions.tsv рендера V4 из v4_groups.json и render_v4/group_descriptions.tsv."""
    with open(GROUPS, encoding=ENC) as f:
        groups = json.load(f)
    gd = read_tsv(os.path.join(REND, "group_descriptions.tsv"))
    if len(gd) != len(groups):
        raise SystemExit("описаний групп %d, групп %d" % (len(gd), len(groups)))
    jobs, desc = [], []
    for i, (g, d) in enumerate(zip(groups, gd), 1):
        if d["group"] != "G%02d" % i or d["members"].split() != g:
            raise SystemExit("описание %s не совпадает с группой %d: %s" % (d["group"], i, " ".join(g)))
        if not d["description"].strip():
            raise SystemExit("пустое описание %s" % d["group"])
        for k in g:
            s, n = k.split(":")
            jobs.append({"name": "pv4_%s_%s" % (s.lower(), n), "job_id": "%s_%s" % (d["group"], n), "map": "",
                         "at": [], "take": ["%s@0" % k], "what": d["description"], "asset_id": k, "src": k,
                         "seed": SEED_V4 + i, "stratum": "prod_two_pass_v4", "group": d["group"],
                         "identity_how": "V4_GROUP", "identity_source": d["source"], "output": ""})
            desc.append({"asset_id": k, "group": d["group"], "description": d["description"], "status": "OK",
                         "note": "описание группы; Vitali 07.10 разрешил рендер"})
    jp = os.path.join(REND, "jobs.json")
    if os.path.exists(jp):
        with open(jp, encoding=ENC) as f:
            if json.load(f) != jobs:
                raise SystemExit("jobs.json уже есть и отличается - состав не переписывается")
    dump(jobs, jp)
    with open(os.path.join(REND, "descriptions.tsv"), "w", encoding=ENC, newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(desc[0]), delimiter="\t", quoting=csv.QUOTE_NONE, lineterminator="\n")
        w.writeheader()
        w.writerows(desc)
    print("групп %d, кадров %d" % (len(groups), len(jobs)))


def do_render_freeze():
    """baseline.json рендера V4; общие с V3 поля обязаны совпасть с prod-two-pass-v3/baseline.json."""
    import hashlib
    body = rend_body()
    with open(V3_BASE, encoding=ENC) as f:
        v3 = json.load(f)["body"]
    diff = [k for k in SAME_AS_V3 if json.loads(json.dumps(body[k])) != v3.get(k)]
    if diff:
        raise SystemExit("путь кадра не тот, что у V3: %s" % ", ".join(diff))
    sha = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    bp = os.path.join(REND, "baseline.json")
    if os.path.exists(bp):
        with open(bp, encoding=ENC) as f:
            if json.load(f)["sha256"] != sha:
                raise SystemExit("baseline.json V4 уже есть и отличается")
        print("baseline.json тот же: %s" % sha[:12])
        return
    dump({"sha256": sha, "body": body}, bp)
    print("baseline.json %s; совпадает с V3 по: %s" % (sha[:12], ", ".join(SAME_AS_V3)))


def check_rend_base():
    with open(os.path.join(REND, "baseline.json"), encoding=ENC) as f:
        old = json.load(f)
    body = json.loads(json.dumps(rend_body(), ensure_ascii=False))
    diff = sorted(k for k in body if body[k] != old["body"].get(k))
    if diff:
        raise SystemExit("baseline V4 изменился: %s" % ", ".join(diff))
    return old


def do_render(max_renders):
    """Модель - только через очередь (render_chunks.py): путь V3 на заданиях V4."""
    rb = use_rb()
    check_rend_base()
    rb.install_rule()
    rb.install_exceptions()
    rb.rp.do_render(max_renders)


def do_render_report():
    """Без модели: машинные ворота V3 по кадру и лист по группам (оригинал x4 | рендер у каждого члена)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    import asset_fidelity as AF
    import map_mockup as mm
    rb = use_rb()
    base = check_rend_base()
    world = mm.World()
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
    jobs = rb.rp.jobs(False)
    res, by_group = [], defaultdict(list)
    for j in jobs:
        mp = os.path.join(REND, "render", "meta", j["name"] + ".json")
        s, n = j["asset_id"].split(":")
        o = np.asarray(world.sprite(s.lower(), int(n), None).convert("RGBA"))
        row = {"group": j["group"], "asset_id": j["asset_id"]}
        if not os.path.exists(mp):
            res.append(dict(row, machine_final="NOT_RENDERED"))
            by_group[j["group"]].append((j, o, None, "NOT_RENDERED", []))
            continue
        with open(mp, encoding=ENC) as f:
            m = json.load(f)
        r = AF.measure(o, Image.open(m["piece"]))
        mc, fv = rb.machine_class(m["outcome"]), AF.verdict(r)
        final = max((mc, fv), key=lambda v: rb.WORST.get(v, 2))
        why = ["photo_accept %s" % m["outcome"]] if mc != "PASS" else []
        why += ["%s %s" % (c, r[c][0]) for c in AF.CHECKS if r[c][0] != "PASS"]
        res.append(dict(row, machine_final=final, photo_accept=m["outcome"], fidelity=fv,
                        attempts=len(m["attempts"]), panel=m["attempts"][-1]["panel"], why="; ".join(why),
                        checks={c: list(r[c]) for c in AF.CHECKS}, piece=m["piece"]))
        by_group[j["group"]].append((j, o, m["piece"], final, why))
    mcnt = Counter(x["machine_final"] for x in res)
    gall = {g: Counter(x[3] for x in v) for g, v in by_group.items()}
    gpass = sum(1 for c in gall.values() if set(c) == {"PASS"})
    done = sum(mcnt[v] for v in ("PASS", "REVIEW", "FAIL"))
    pa = Counter(x.get("photo_accept", "—") for x in res if x["machine_final"] != "NOT_RENDERED")
    gates = Counter(w.split()[0] for x in res for w in x.get("why", "").split("; ") if w)
    md = ["# V4 pilot (OTHER_VIEW sure): машинный итог рендера", "",
          "baseline V4 `%s` (путь кадра = V3); групп %d, кадров %d, отрисовано %d." % (
              base["sha256"][:12], len(by_group), len(res), done), "",
          "Итог кадра - худшее из photo_accept и ворот верности %s (как V3). Визуальная приёмка - человек." % (
              ", ".join(AF.CHECKS)), "",
          "| | PASS | REVIEW | FAIL | не отрисовано |", "|---|---|---|---|---|",
          "| кадров | %d | %d | %d | %d |" % (mcnt["PASS"], mcnt["REVIEW"], mcnt["FAIL"], mcnt["NOT_RENDERED"]), "",
          "Групп, где все кадры машинный PASS: %d из %d." % (gpass, len(by_group)), "",
          "photo_accept: %s" % ", ".join("%s %d" % kv for kv in sorted(pa.items())), "",
          "Сработавшие ворота (кадров): %s" % (", ".join("%s %d" % kv for kv in sorted(gates.items())) or "нет"),
          "", "| группа | кадр | машина | photo_accept | верность | попыток | подложка | почему |",
          "|---|---|---|---|---|---|---|---|"]
    for x in res:
        md.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            x["group"], x["asset_id"], x["machine_final"], x.get("photo_accept", "—"), x.get("fidelity", "—"),
            x.get("attempts", "—"), x.get("panel", "—"), x.get("why", "") or "—"))
    write_text(os.path.join(REND, "report.md"), "\n".join(md) + "\n")
    dump({"baseline_sha256": base["sha256"], "machine": dict(mcnt), "groups_all_pass": gpass, "items": res},
         os.path.join(REND, "report.json"))
    W, H = 128, 160
    rows = []
    for g in sorted(by_group):
        items = by_group[g]
        row = Image.new("RGB", (len(items) * (2 * W + 16) + 8, H + 64), (24, 24, 24))
        d = ImageDraw.Draw(row)
        d.text((6, 4), "%s  %s" % (g, items[0][0]["what"][:150]), fill=(235, 235, 235), font=font)
        for i, (j, o, piece, final, why) in enumerate(items):
            x = 8 + i * (2 * W + 16)
            for k, im in enumerate((np.repeat(np.repeat(o, 4, 0), 4, 1),
                                    np.asarray(Image.open(piece).convert("RGBA")) if piece else None)):
                bg = Image.new("RGBA", (W, H), (60, 58, 56, 255))
                if im is not None and im.shape[:2] == (H, W):
                    bg.alpha_composite(Image.fromarray(im))
                row.paste(bg.convert("RGB"), (x + k * W, 24))
            col = (120, 220, 120) if final == "PASS" else (230, 180, 90) if final == "REVIEW" else (240, 110, 110)
            d.text((x, H + 28), "%s  %s" % (j["asset_id"], final), fill=col, font=font)
            d.text((x, H + 46), "; ".join(why)[:40], fill=(200, 160, 120), font=font)
        rows.append(row)
    sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)), (24, 24, 24))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    sheet.save(os.path.join(REND, "sheet.png"))
    print("\n".join(md[:14]))


FINAL = os.path.join(REND, "final_select")
PAGE_TPL = os.path.join(ROOT, "tools", "hdart", "final_select_page.html")
PAGE_SUBS = [  # шаблон V3 не правится (замок v3_baseline): своё хранилище (R-187), тип брака «стороны», текст
    ("<title>Финальный лист V2</title>", "<title>V4 Pilot Sheet</title>"),
    ('const LS = "final-select-v2";', 'const LS = "final-select-v4-pilot";'),
    ('const COL = "final";', 'const COL = "final_v4";'),
    ('["OTHER", "другое"]', '["OTHER_VIEW", "стороны - не один предмет"], ["OTHER", "другое"]'),
    ("<h1>Финальный лист · __N__ предметов</h1>", "<h1>V4 pilot · финальный лист · __N__ кадров</h1>"),
    ("На каждый предмет автоматика уже выбрала лучший из трёх проходов (RESTORE, STRICT, THIRD) — здесь\nтолько он,",
     "V4 pilot: другой бок предмета, у каждого кадра один проход (RESTORE), кадры одной группы стоят подряд -\n"
     "сверху номер группы. Здесь кадр"),
]


def do_final_page():
    """Без модели: финальный лист V4 как в V3 (оригинал и кадр, по умолчанию всё в игру, отмечается брак).
    Выбирать не из чего: у кадра один проход, судей нет (Codex = 0, решение Vitali 07.10)."""
    import base64
    import io
    import numpy as np
    from PIL import Image
    import map_mockup as mm
    check_rend_base()
    with open(os.path.join(REND, "report.json"), encoding=ENC) as f:
        rep = json.load(f)
    desc = {r["asset_id"]: r["description"] for r in read_tsv(os.path.join(REND, "descriptions.tsv"))}
    items = [x for x in rep["items"] if x.get("piece")]
    if len(items) != len(rep["items"]):
        raise SystemExit("не отрисовано: %d" % (len(rep["items"]) - len(items)))
    items.sort(key=lambda x: (x["group"], x["asset_id"]))
    world = mm.World()

    def uri(im):
        b = io.BytesIO()
        im.save(b, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

    data, sel = [], []
    for i, x in enumerate(items, 1):
        s, n = x["asset_id"].split(":")
        o = np.asarray(world.sprite(s.lower(), int(n), None).convert("RGBA"))
        data.append({"id": "a%02d" % i, "row": i, "asset": x["asset_id"], "sect": "GAME",
                     "what": "%s · %s" % (x["group"], desc[x["asset_id"]]),
                     "orig": uri(Image.fromarray(np.repeat(np.repeat(o, 4, 0), 4, 1))),
                     "img": uri(Image.open(x["piece"]).convert("RGBA"))})
        sel.append({"asset_id": x["asset_id"], "group": x["group"], "section": "GAME", "stage": "RESTORE",
                    "machine": x["machine_final"], "why": x.get("why", ""), "piece": x["piece"]})
    with open(PAGE_TPL, encoding=ENC) as f:
        html = f.read()
    for a, b in PAGE_SUBS:
        if html.count(a) != 1:
            raise SystemExit("шаблон изменился: %r" % a[:60])
        html = html.replace(a, b)
    html = (html.replace("__ROWS__", json.dumps(data, ensure_ascii=False)).replace("__N__", str(len(data)))
                .replace("__NGAME__", str(len(data))).replace("__NRES__", "0"))
    os.makedirs(FINAL, exist_ok=True)
    head = ["asset_id", "group", "section", "stage", "machine", "why", "piece"]
    write_text(os.path.join(FINAL, "select.tsv"),
               "\n".join(["\t".join(head)] + ["\t".join(r[k] for k in head) for r in sel]) + "\n")
    p = os.path.join(FINAL, "index.html")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("лист %s: %d кадров, групп %d, %.1f МБ" % (p, len(data), len({x["group"] for x in items}),
                                                   os.path.getsize(p) / 1e6))


def do_final_answers(tsv):
    """Без модели: ответы листа -> verdicts_vitali.tsv и сводка: правки на 100 кадров, группы, развалившиеся
    по согласованности сторон (тип OTHER_VIEW), брак, не связанный со сторонами (цвет, кайма, прочее)."""
    sel = {r["asset_id"]: r for r in read_tsv(os.path.join(FINAL, "select.tsv"))}
    marks = {r["asset_id"]: r for r in read_tsv(tsv) if r.get("asset_id") in sel}
    out = []
    for a, r in sel.items():
        m = marks.get(a, {})
        bad = m.get("mark", "") == "1"
        out.append({"asset_id": a, "group": r["group"], "verdict": "FAIL" if bad else "PASS",
                    "types": m.get("types", "") if bad else "", "note": m.get("note", "") if bad else "",
                    "machine": r["machine"], "piece": r["piece"]})
    head = ["asset_id", "group", "verdict", "types", "note", "machine", "piece"]
    write_text(os.path.join(FINAL, "verdicts_vitali.tsv"),
               "\n".join(["\t".join(head)] + ["\t".join(r[k].replace("\t", " ") for k in head) for r in out])
               + "\n")
    bad = [r for r in out if r["verdict"] == "FAIL"]
    groups = {r["group"] for r in out}
    cons = sorted({r["group"] for r in bad if "OTHER_VIEW" in r["types"].split(",")})
    other = [r for r in bad if "OTHER_VIEW" not in r["types"].split(",")]
    ty = Counter(t for r in bad for t in (r["types"].split(",") if r["types"] else ["(без типа)"]))
    mx = Counter((r["machine"], r["verdict"]) for r in out)
    md = ["# V4 pilot: финальный лист - ответы Vitali", "",
          "Кадров %d, групп %d. Брак %d, в игру %d; правки человека %.1f на 100 кадров (V3: 3,1)." % (
              len(out), len(groups), len(bad), len(out) - len(bad), 100 * len(bad) / len(out)), "",
          "Групп, развалившихся по согласованности сторон (тип OTHER_VIEW): %d из %d%s." % (
              len(cons), len(groups), (" - " + ", ".join(cons)) if cons else ""),
          "Брак без типа OTHER_VIEW (цвет, материал, кайма и прочее, не про стороны): %d кадров." % len(other), "",
          "Типы брака: %s" % (", ".join("%s %d" % kv for kv in ty.most_common()) or "нет"), "",
          "Машинный итог против человека: %s" % ", ".join(
              "%s -> %s %d" % (m, v, mx[(m, v)]) for m in ("PASS", "REVIEW", "FAIL") for v in ("PASS", "FAIL")
              if mx[(m, v)]), ""]
    if bad:
        md += ["| группа | кадр | типы | машина | заметка |", "|---|---|---|---|---|"]
        md += ["| %s | %s | %s | %s | %s |" % (r["group"], r["asset_id"], r["types"] or "—", r["machine"],
                                             r["note"] or "—") for r in sorted(bad, key=lambda r: r["group"])]
    write_text(os.path.join(FINAL, "summary.md"), "\n".join(md) + "\n")
    print("\n".join(md))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    if cmd in ("render-build", "render-freeze", "render", "render-report", "final-page", "final-answers"):
        os.chdir(ROOT)
        if cmd == "final-page":
            do_final_page()
        elif cmd == "final-answers":
            do_final_answers(arg)
        elif cmd == "render-build":
            do_render_build()
        elif cmd == "render-freeze":
            do_render_freeze()
        elif cmd == "render-report":
            do_render_report()
        else:
            mr = sys.argv[sys.argv.index("--max-renders") + 1] if "--max-renders" in sys.argv else "4"
            do_render(int(mr))
        return
    if cmd == "cons-build":
        do_cons_build()
        return
    if cmd == "cons-judge":
        do_cons_judge(int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 3,
                      sys.argv[sys.argv.index("--effort") + 1] if "--effort" in sys.argv else "high")
        return
    if cmd == "cons-report":
        do_cons_report()
        return
    if cmd == "presort":
        do_presort()
    elif cmd == "control-propose":
        do_control_propose()
    elif cmd == "cards":
        do_cards(arg)
    elif cmd == "classify-pack":
        do_classify_pack(arg)
    elif cmd == "classify":
        runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 3
        effort = sys.argv[sys.argv.index("--effort") + 1] if "--effort" in sys.argv else "high"
        if "--max-calls" not in sys.argv:
            raise SystemExit("нужен --max-calls N: число вызовов Codex, согласованное с Vitali до запуска")
        do_classify(arg, runs, effort, int(sys.argv[sys.argv.index("--max-calls") + 1]))
    elif cmd == "pool-summary":
        do_pool_summary()
    elif cmd == "classify-merge":
        do_classify_merge(arg)
    elif cmd == "control-report":
        do_control_report()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
