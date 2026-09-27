"""Таблица боевых эффектов для движка: какое оружие какой вспышкой стреляет, какой патрон
каким попаданием бьёт, каким видом удара машет оружие ближнего боя.

Классы и калибры - tools/hdart/weapon_classes.py, разбор - docs/research/combat-fx.md.
Движок (src/Engine/HdFx.cpp) читает hd/FX/weapons.txt; предмета нет в таблице - берёт
попадание по типу урона, удар - приклад или кулак.

    flash <предмет> <вид>        вспышка у ствола: pistol smg rifle ... laser plasma electric
    hit   <предмет> <семья>      попадание: cal1..cal5 pellet arrow laser ... boom_he boom_fire ...
    swing <предмет> <вид>        удар: fist claw bite blade pierce club whip sting butt
    tracer <предмет> <опции>     трассер: classic | bright;fade=F | head=R,G,B | width=W

Запуск: PYTHONIOENCODING=utf-8 py -3 tools/hdart/fx_map.py --out <мод>/hd [--out <вторая копия>/hd]
"""
import argparse
import os
from collections import Counter

import weapon_classes as wc

# взрыв по типу урона; у энергии цвет движок берёт с классического кадра взрыва
BOOM_DT = {"CONCUSSIVE": "he", "PIERCING": "he", "BURN": "fire", "CHOKING": "gas", "CHEM": "acid", "DAZE": "stun",
           "BIO": "bio", "PLASMA": "plasma", "LASER": "energy", "ELECTRIC": "electric", "EMP": "electric",
           "WARP": "psi", "MIND": "psi", "CHARM": "psi"}


# гаусс и рельса: своё попадание (голубая вспышка, самая крупная кровь) и синий снаряд
GAUSS_WORDS = {"GAUSS", "XGAUSS", "XG", "RAIL"}
# диски CD-оружия: классический снаряд и попадание читаются лучше клипа (летящий диск)
CLASSIC_WORDS = {"CD"}
# плеть и копьё дальнего удара стреляют, но ствола у них нет
NO_MUZZLE_WORDS = {"WHIP", "SPEAR"}
# трассер: у плазмы тёмный хвост читался ракетой - яркий снаряд и почти прозрачный хвост;
# гаусс - синий снаряд, хвост свой; лазер - тоньше
TRACER_OF_HIT = {"plasma": "bright;fade=0.35", "gauss": "head=90,170,255", "laser": "width=0.7", "classic": "classic"}


def rows_of(items):
    flash, hit, swing, tracer = {}, {}, {}, {}
    guns = {t: it for t, it in items.items() if it.get("battleType") == 1 and wc.is_ranged(it)}
    for t, it in sorted(guns.items()):
        r = wc.classify(t, it, items)
        words = set(wc.words_of(t))
        flash[t] = "none" if words & NO_MUZZLE_WORDS else r["flash"]
        for a in wc.ammo_of(it, items):
            h = r["hits"].get(a.get("type"))
            if h and words & CLASSIC_WORDS:
                h = "classic"
            elif h and words & GAUSS_WORDS and h.startswith("cal"):
                h = "gauss"
            if h and a.get("type") not in hit:
                hit[a["type"]] = h
                if h == "boom":
                    hit[a["type"]] = "boom_" + BOOM_DT.get(wc.dtype(a) or wc.dtype(it) or "", "he")
            # снаряд берётся с патрона, а нет его там - с оружия: строка на обоих
            if h in TRACER_OF_HIT:
                for owner in (a.get("type"), t):
                    tracer.setdefault(owner, TRACER_OF_HIT[h])
    # гранаты, мины и всё, что бьёт само, без ствола
    for t, it in sorted(items.items()):
        if t in hit or it.get("battleType") not in (4, 5) or not (it.get("power") or it.get("battleType") == 4):
            continue
        h = wc.hit_of(it, "thrown", 2, it)
        hit[t] = "boom_" + BOOM_DT.get(wc.dtype(it) or "", "he") if h == "boom" else h
    for t, it in sorted(items.items()):
        bt = it.get("battleType", 0)
        if t.startswith("AURA_"):
            continue
        if (bt == 3 and it.get("power")) or "meleeType" in it or it.get("meleePower"):
            swing[t] = wc.melee_kind(t, bt)
    # стиль рисуется на ряд кадров снаряда, а ряд бывает общий (NOVA_PLASMA_GUN летит снарядом гаусса):
    # у всех хозяев ряда один стиль - тот, что у большинства, иначе исход решал бы порядок предметов
    by_row = {}
    for t, style in tracer.items():
        row = items.get(t, {}).get("bulletSprite")
        if isinstance(row, int) and row >= 0:
            by_row.setdefault(row, []).append(t)
    for row, owners in by_row.items():
        top = Counter(tracer[t] for t in owners).most_common(1)[0][0]
        for t in owners:
            tracer[t] = top
    return flash, hit, swing, tracer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", action="append", required=True, help="каталог hd мода (кладём в <out>/FX/weapons.txt)")
    args = ap.parse_args()
    flash, hit, swing, tracer = {}, {}, {}, {}
    # ваниль первой, мод поверх: одинаковые имена у них значат одно и то же
    for mod in ("xcom1", "Piratez"):
        f, h, s, tr = rows_of(wc.load_items(wc.MODS[mod]))
        flash.update(f); hit.update(h); swing.update(s); tracer.update(tr)
        print(f"{mod}: вспышек {len(f)}, попаданий {len(h)}, ударов {len(s)}, трассеров {len(tr)}")
    lines = ["# written by tools/hdart/fx_map.py: flash|hit|swing <item> <kind>, tracer <item> <options>"]
    lines += [f"flash {t} {k}" for t, k in sorted(flash.items())]
    lines += [f"hit {t} {k}" for t, k in sorted(hit.items())]
    lines += [f"swing {t} {k}" for t, k in sorted(swing.items())]
    lines += [f"tracer {t} {k}" for t, k in sorted(tracer.items())]
    for out in args.out:
        d = os.path.join(out, "FX")
        os.makedirs(d, exist_ok=True)
        # читает движок: без спецификации (R-001, исключение для файлов игры)
        with open(os.path.join(d, "weapons.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        print("->", os.path.join(d, "weapons.txt"))
    print("попадания:", dict(Counter(hit.values()).most_common()))
    print("удары:", dict(Counter(swing.values()).most_common()))


if __name__ == "__main__":
    main()
