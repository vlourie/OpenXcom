"""FINAL_SELECT: автоматический выбор лучшего прохода (RESTORE / STRICT / THIRD) на предмет и один финальный лист.

Специалист 05.10 (после провала VITALI_JUDGE на DEV): судьи Codex/Claude - только внутренние эвристики (выбрать
лучший проход, явно плохое - в residual), права окончательного PASS у них нет. Человеку - один лист: оригинал и
выбранный HD, по умолчанию всё идёт в игру, отмечается только брак. Метрика - касания человека на 100 предметов.

Счёт кадра - сумма по судьям прохода (claude, codex): PASS sure +2, PASS unsure +1, UNCERTAIN 0, FAIL unsure -1,
FAIL sure -2. Выбор - наибольший счёт; при равенстве - более поздний проход (он рисовался, чтобы исправить прежний).
Голоса арбитра спора не берутся: калибровка показала, что он бракует годное (R-234). Лист без истории проходов:
на карточке только оригинал и выбранный кадр.

Автоматического residual нет (RESIDUAL = None): на V1 из кадров «оба FAIL sure» (-4) годных 15 из 52, и правило
«лучший проход всё равно -4 - в residual» выкинуло бы 13 предметов из 50, у которых годный проход был. На V1 же
внутри предмета счёт ставит годный выше брака в 19 парах из 32, ниже - в 3, равны - 10 (там решает поздний проход;
на V1 годный всегда позже, поэтому правило равенства V1 не проверяет).

    calib    без модели: правило выбора на V1 (там вердикт Vitali известен на каждом проходе) - сколько касаний
             было бы на V1 и сколько годных ушло бы в residual
    select   без модели: V2 -> prod-two-pass-v2/final_select/select.tsv (выбранный проход, счёт всех проходов)
    page     без модели: лист final_select/index.html (картинки внутри файла) - публикуется как страница
    answers  без модели: --tsv <файл с ответами страницы> -> final_select/verdicts_vitali.tsv и сводка касаний

Запуск: GPUQ_BYPASS=1 PYTHONIOENCODING=utf-8 py -3.13 tools/hdart/final_select.py calib
"""
import argparse
import base64
import io
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import visual_judge as vj  # noqa: E402

ENC = "utf-8-sig"
STAGES = ("RESTORE", "STRICT", "THIRD")
SCORE = {("PASS", "sure"): 2, ("PASS", "unsure"): 1, ("FAIL", "unsure"): -1, ("FAIL", "sure"): -2}
RESIDUAL = None
OUT = os.path.join(vj.V2, "final_select")


def score(rows):
    """Сумма голосов и строка «кто что сказал»; None, если какого-то судьи нет."""
    if not rows or not all(rows.values()):
        return None, ""
    s = sum(SCORE.get((r["verdict"], r["confidence"]), 0) for r in rows.values())
    note = " | ".join("%s %s %s: %s" % (w, r["verdict"], r["confidence"], r.get("reason", ""))
                      for w, r in sorted(rows.items()))
    return s, note


def pick(cands):
    """cands: [(stage, score, ...)] - наибольший счёт, при равенстве более поздний проход."""
    ok = [c for c in cands if c[1] is not None]
    if not ok:
        return None
    return max(ok, key=lambda c: (c[1], STAGES.index(c[0])))


def do_calib():
    with open(os.path.join(vj.OUT_CAL, "key.json"), encoding=ENC) as f:
        items = json.load(f)
    judges = {w: vj.load_answers(vj.OUT_CAL, w) for w in ("claude", "codex")}
    by = {}
    for x in items:
        s, _ = score({w: judges[w].get(x["id"]) for w in judges})
        by.setdefault(x["asset_id"], []).append((x["stage"], s, x["truth"]))
    c = Counter()
    resid_good = []
    for a, cands in sorted(by.items()):
        best = pick(cands)
        has_pass = any(t == "PASS" for _, _, t in cands)
        if best is None:
            c["нет голосов"] += 1
            continue
        resid = RESIDUAL is not None and best[1] <= RESIDUAL
        c["предметов"] += 1
        c["есть годный проход"] += has_pass
        if resid:
            c["в residual"] += 1
            if has_pass:
                resid_good.append(a)
            # касание: годный проход есть - его надо вернуть (и он должен быть выбран)
            c["касаний"] += has_pass
        else:
            c["выбран годный"] += best[2] == "PASS"
            c["выбран брак, годный был"] += best[2] == "FAIL" and has_pass
            c["касаний"] += best[2] == "FAIL"
        for _, s, t in cands:
            if s is not None and s <= -4:
                c["кадров -4: годных" if t == "PASS" else "кадров -4: брака"] += 1
    for k in ("предметов", "есть годный проход", "выбран годный", "выбран брак, годный был", "в residual",
              "касаний", "кадров -4: годных", "кадров -4: брака", "нет голосов"):
        print("%-28s %d" % (k, c[k]))
    print("годный ушёл в residual:", resid_good)
    print("касаний на 100 предметов: %.1f" % (100 * c["касаний"] / max(1, c["предметов"])))
    print("для сравнения: прежний путь V1 - вердикт на каждый кадр: %d касаний на %d предметов" % (len(items), c["предметов"]))


def v2_candidates():
    keys = {}
    for st in STAGES:
        d = vj.prod_dir(st)
        if not os.path.exists(os.path.join(d, "key.json")):
            # V3: третий проход бывает не нужен; V2 прошёл все три, там ничего не меняется
            print("проход %s не прогонялся - кандидатов с него нет" % st)
            continue
        with open(os.path.join(d, "key.json"), encoding=ENC) as f:
            items = json.load(f)
        judges = {w: vj.load_answers(d, w) for w in ("claude", "codex")}
        for x in items:
            s, note = score({w: judges[w].get(x["id"]) for w in judges})
            keys.setdefault(x["asset_id"], []).append((st, s, x["piece"].replace("\\", "/"), note))
    return keys


def do_select():
    os.makedirs(OUT, exist_ok=True)
    auto = {r["asset_id"]: r for r in vj.read_tsv(os.path.join(vj.V2, "final_auto.tsv"))}
    rows, c = [], Counter()
    for a, cands in sorted(v2_candidates().items()):
        if a not in auto:
            raise SystemExit("предмета %s нет в final_auto.tsv" % a)
        best = pick(cands)
        if best is None:
            raise SystemExit("у %s нет полного набора голосов ни на одном проходе" % a)
        st, s, piece, note = best
        if not os.path.exists(piece):
            raise SystemExit("нет файла %s" % piece)
        sect = "RESIDUAL" if RESIDUAL is not None and s <= RESIDUAL else "GAME"
        c[(sect, st)] += 1
        rows.append({"asset_id": a, "section": sect, "stage": st, "score": str(s), "piece": piece,
                     "all": " ".join("%s=%s" % (x[0], x[1]) for x in cands), "was_v2": auto[a]["status"],
                     "note": note})
    if len(rows) != len(auto):
        raise SystemExit("в final_auto %d предметов, выбрано %d" % (len(auto), len(rows)))
    head = ["asset_id", "section", "stage", "score", "all", "was_v2", "piece", "note"]
    p = os.path.join(OUT, "select.tsv")
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        f.write("\t".join(head) + "\n")
        for r in rows:
            f.write("\t".join(r[k].replace("\t", " ").replace("\n", " ") for k in head) + "\n")
    os.replace(p + ".tmp", p)
    for k in sorted(c):
        print("%-9s %-8s %d" % (k[0], k[1], c[k]))
    moved = Counter((r["was_v2"], r["section"]) for r in rows)
    for k in sorted(moved):
        print("V2 %-13s -> %-9s %d" % (k[0], k[1], moved[k]))
    print("записано %s: %d предметов" % (p, len(rows)))


def png_uri(img):
    b = io.BytesIO()
    img.save(b, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def do_page():
    import numpy as np
    from PIL import Image
    rows = vj.read_tsv(os.path.join(OUT, "select.tsv"))
    desc = {r["asset_id"]: r["description"] for r in vj.read_tsv(os.path.join(vj.V2, "descriptions.tsv"))}
    data = []
    for i, r in enumerate(sorted(rows, key=lambda r: (r["section"] != "GAME", r["asset_id"])), 1):
        o = vj.sprite(r["asset_id"])
        orig = Image.fromarray(np.repeat(np.repeat(o, 4, 0), 4, 1))
        hd = Image.open(r["piece"]).convert("RGBA")
        data.append({"id": "a%02d" % i, "row": i, "asset": r["asset_id"], "sect": r["section"],
                     "what": desc.get(r["asset_id"], ""), "orig": png_uri(orig), "img": png_uri(hd)})
    with open(os.path.join(HERE, "final_select_page.html"), encoding=ENC) as f:
        tpl = f.read()
    n_game = sum(d["sect"] == "GAME" for d in data)
    html = (tpl.replace("__ROWS__", json.dumps(data, ensure_ascii=False))
               .replace("__N__", str(len(data))).replace("__NGAME__", str(n_game))
               .replace("__NRES__", str(len(data) - n_game)))
    p = os.path.join(OUT, "index.html")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print("лист %s: %d предметов (в игру %d, residual %d), %.1f МБ" % (p, len(data), n_game, len(data) - n_game,
                                                                      os.path.getsize(p) / 1e6))


def do_answers(tsv):
    rows = {r["asset_id"]: r for r in vj.read_tsv(os.path.join(OUT, "select.tsv"))}
    marks = {r["asset_id"]: r for r in vj.read_tsv(tsv) if r.get("asset_id") in rows}
    out, touches = [], 0
    for a, r in sorted(rows.items()):
        m = marks.get(a, {})
        flipped = m.get("mark", "") == "1"
        touches += flipped
        game = (r["section"] == "GAME") != flipped
        out.append({"asset_id": a, "verdict": "PASS" if game else "FAIL", "stage": r["stage"],
                    "section": r["section"], "touched": "1" if flipped else "", "note": m.get("note", ""),
                    "piece": r["piece"]})
    head = ["asset_id", "verdict", "stage", "section", "touched", "note", "piece"]
    p = os.path.join(OUT, "verdicts_vitali.tsv")
    with open(p + ".tmp", "w", encoding=ENC, newline="") as f:
        f.write("\t".join(head) + "\n")
        for r in out:
            f.write("\t".join(r[k].replace("\t", " ") for k in head) + "\n")
    os.replace(p + ".tmp", p)
    c = Counter(r["verdict"] for r in out)
    print("в игру %d, брак %d; касаний %d на %d предметов = %.1f на 100" % (
        c["PASS"], c["FAIL"], touches, len(out), 100 * touches / len(out)))
    # разбивка для разбора ошибок выбора (сам выбор не меняет): где брак - по проходу, счёту, прежнему статусу V2
    for name, key in (("проход", lambda a: rows[a]["stage"]), ("счёт", lambda a: rows[a]["score"]),
                      ("статус V2", lambda a: rows[a]["was_v2"])):
        t = Counter((key(r["asset_id"]), r["verdict"]) for r in out)
        print("по %s:" % name)
        for k in sorted({k for k, _ in t}, key=lambda x: (len(x), x)):
            n = t[(k, "PASS")] + t[(k, "FAIL")]
            print("  %-13s в игру %2d  брак %2d  (брак %.0f%%)" % (k, t[(k, "PASS")], t[(k, "FAIL")],
                                                                 100 * t[(k, "FAIL")] / n))
    ty = Counter(x for r in marks.values() if r.get("mark") == "1" for x in r.get("types", "").split(",") if x)
    if ty:
        print("типы брака:", ", ".join("%s %d" % kv for kv in ty.most_common()))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.chdir(vj.ROOT)
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["calib", "select", "page", "answers"])
    ap.add_argument("--tsv")
    ap.add_argument("--batch", default="", help="папка производственной партии (по умолчанию V2)")
    a = ap.parse_args()
    if a.batch:
        global OUT
        vj.V2 = a.batch
        OUT = os.path.join(vj.V2, "final_select")
    if a.cmd == "calib":
        do_calib()
    elif a.cmd == "select":
        do_select()
    elif a.cmd == "page":
        do_page()
    else:
        if not a.tsv:
            raise SystemExit("нужен --tsv")
        do_answers(a.tsv)


if __name__ == "__main__":
    main()
