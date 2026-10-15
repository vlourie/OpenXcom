"""Установка точного движка стен (wall_exact.py) по планам пачек и решению по фактурному текущему.

Что ставится по картинке (одна картинка - все её кадры, классика у них побайтно одна):
  * план пачки (plan_bNNN.tsv) предлагает B2 или A - точный этого источника (render/b2, render/xbrz);
  * фактурный текущий - точный B2 только если картинка в review/replace.tsv (шов или лесенка на листе,
    слово Vitali 15.10); остальной фактурный, гладкий текущий и OWNED - не трогаются.
Зеркальные близнецы уже лежат в render/b2 и render/xbrz перевёрнутыми (wall_exact: «зеркало <картинка>»).
Картинка из review/hold.tsv (зеркальная пара, стороны которой получили бы разный источник) не ставится
вовсе до решения Vitali: лево и право одной стены - одним рисунком. Картинка из review/flicker.tsv (точный
дал мигание петли анимации, R-341) не ставится: остаётся прежний пак. Картинка из review/reject.tsv
(B2 теряет материал против текущего, R-357; с зеркальной парой) не ставится: остаётся прежний пак.

  wall_exact_install.py --batches 1-11 [--yes]

Без --yes - сухой прогон: число картинок и файлов, кадры без пака в установке. С --yes - манифест
(build_hd_pack.stage), установка в обе копии мода hd (repo - набор целиком, если его там нет или он
неполный, R-257), сверка sha256 и числа файлов набора.
"""
import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

ROOT = Path(HERE).resolve().parents[1]
ENC = "utf-8-sig"
R = ROOT / "census" / "walls" / "exact"
GAME = ROOT / "Пиратки" / "Dioxine_XPiratez" / "user" / "mods" / "hd" / "hd"
REPO = ROOT / "user" / "mods" / "hd" / "hd"
SRC = {"B2": "b2", "A": "xbrz"}


def rows(p):
    with open(p, encoding=ENC, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def batches(s):
    out = set()
    for part in s.split(","):
        a, _, b = part.partition("-")
        out |= set(range(int(a), int(b or a) + 1))
    return sorted(out)


def plan_of(bs, replace, hold=(), flicker=(), reject=()):
    """[(rel, src_png, кадр, картинка, источник, почему)] и сводка."""
    out, cnt, nopack = [], {}, []
    for b in bs:
        for r in rows(R / "render" / ("plan_b%03d.tsv" % b)):
            p, prop, why = r["картинка"], r["предложение"], r["причина"]
            if p in flicker:
                cnt["мигание петли"] = cnt.get("мигание петли", 0) + 1
                continue
            if p in reject:
                cnt["отклонено по материалу"] = cnt.get("отклонено по материалу", 0) + 1
                continue
            if p in hold and (prop in SRC or p in replace):
                cnt["отложено по зеркалу"] = cnt.get("отложено по зеркалу", 0) + 1
                continue
            if prop in SRC:
                kind, note = prop, "план пачки %d: %s" % (b, why)
            elif why.startswith("фактурный") and p in replace:
                kind, note = "B2", "пачка %d: фактурный текущий с %s - точный B2 (Vitali 15.10)" % (b, replace[p])
            else:
                cnt["оставлен текущий"] = cnt.get("оставлен текущий", 0) + 1
                continue
            src = R / "render" / SRC[kind] / (p + ".png")
            if not src.exists():
                raise SystemExit("%s: нет %s" % (p, src))
            cnt[kind] = cnt.get(kind, 0) + 1
            for k in r["кадры"].split():
                s, n = k.split(":")
                rel = "TERRAIN/%s.PCK/%s.png" % (s, n)
                if not (GAME / rel).exists():
                    nopack.append(k)
                    continue
                if list((GAME / "TERRAIN" / ("%s.PCK" % s)).glob("%s.v*.png" % n)):
                    raise SystemExit("%s: в установке есть варианты .vN - точный их не заменяет" % k)
                out.append((rel, str(src), k, p, kind, note))
    return out, cnt, nopack


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", required=True)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    os.chdir(ROOT)
    replace = {r["картинка"]: (r["что видно"] or "швом/лесенкой") for r in rows(R / "review" / "replace.tsv")}
    hp = R / "review" / "hold.tsv"
    hold = {r["картинка"] for r in rows(hp)} if hp.exists() else set()
    fp = R / "review" / "flicker.tsv"
    flicker = {r["картинка"] for r in rows(fp)} if fp.exists() else set()
    jp = R / "review" / "reject.tsv"
    reject = {r["картинка"] for r in rows(jp)} if jp.exists() else set()
    plan, cnt, nopack = plan_of(batches(a.batches), replace, hold, flicker, reject)
    rels = sorted({p[0] for p in plan})
    print("картинок по источнику: %s; файлов %d; кадров без пака в установке %d %s"
          % (cnt, len(rels), len(nopack), nopack[:10]))
    if not a.yes:
        raise SystemExit("сухой прогон; --yes - записать")
    import build_hd_pack as bp
    man = bp.load()
    for rel, src, k, p, kind, note in plan:
        old = man["files"].get(rel, {}).get("sha256")
        bp.stage(man, rel, src, generator="wall_exact_%s" % kind, generator_version="wall_exact.py 15.10",
                 source_path=src, approved=True, approval=note, asset_id=k, source_frame=p, replaced=old)
    bp.save(man, why="wall_exact %s" % a.batches)
    bp.log("save", "", bp.manifest_hash(man)[:16], "wall_exact %s: %d файлов" % (a.batches, len(rels)))
    print("game:", bp.install(man, "game", only=rels))
    repo = []
    for r in rels:
        sd = r.rsplit("/", 1)[0] + "/"
        whole = [k for k in man["files"] if k.startswith(sd)]
        if (REPO / sd).is_dir() and len(os.listdir(REPO / sd)) >= len(whole):
            repo.append(r)
        else:                                   # R-257: набора нет или он неполный - целиком
            repo += whole
    print("repo:", bp.install(man, "repo", only=sorted(set(repo))))
    bad = 0
    for r in rels:
        for root in (GAME, REPO):
            if hashlib.sha256((root / r).read_bytes()).hexdigest() != man["files"][r]["sha256"]:
                print("РАСХОДИТСЯ", root, r)
                bad += 1
    for sd in sorted({r.rsplit("/", 1)[0] + "/" for r in rels}):
        ng, nr = len(os.listdir(GAME / sd)), len(os.listdir(REPO / sd))
        nm = len([k for k in man["files"] if k.startswith(sd)])
        if not ng == nr == nm:
            print("ЧИСЛО ФАЙЛОВ", sd, "game", ng, "repo", nr, "манифест", nm)
            bad += 1
    print("сверка: расхождений", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
