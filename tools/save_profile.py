# -*- coding: utf-8 -*-
"""Портрет игрока по сохранению кампании.

Считает по дневникам бойцов и по missionStatistics то, чего нет в логе:
чем и на чьём ходу игрок добивает, как часто берёт живьём, в какой темноте
воюет, в каких боях у него появляются раненые.

Запуск:
    py -3 tools\\save_profile.py                      # сохранение Пираток по умолчанию
    py -3 tools\\save_profile.py путь\\к.sav [каталог рулсетов]

Поле turn в дневнике - это СКВОЗНОЙ счётчик: он растёт на 1 на каждую сторону,
то есть на 3 за круг. Остаток от деления на 3 разделяет ходы. Что остаток 0 -
это ход игрока, видно по двум признакам: на остатке 1 нет ни одного убийства
пси-усилителем (им нельзя ударить на чужом ходу) и только на остатке 1
срабатывают мины.
"""
import io, os, re, sys, collections

SAV_DEFAULT = r"E:\OpenXCom\Пиратки\Dioxine_XPiratez\user\piratez\NoCodexCatZ.sav"
RUL_DEFAULT = r"E:\OpenXCom\Пиратки\Dioxine_XPiratez\user\mods\Piratez\Ruleset"

KILL_RE = re.compile(
    r"\{type: ([^,]*),rank: ([^,]*),race: ([^,]*),weapon: ([^,]*),weaponAmmo: ([^,]*),"
    r"status: (\d+),faction: (\d+),mission: (-?\d+),turn: (-?\d+),side: (-?\d+),"
    r"bodypart: (-?\d+),id: (-?\d+)\}")

KEEP = ("battleType", "maxRange", "power", "clipSize", "autoShots", "blastRadius",
        "accuracyMelee", "twoHanded")


def load_items(root):
    """Таблица предметов из рулсетов.

    Определения СЛИВАЮТСЯ, а не затираются: дробовики описаны в Piratez.rul,
    а переопределены в Shotguns_Rebalance.rul, и перезапись словаря стирала бы
    им battleType.
    """
    items = {}
    for fn in sorted(os.listdir(root)):
        if not fn.endswith(".rul"):
            continue
        cur, insec = None, False
        for ln in io.open(os.path.join(root, fn), encoding="utf-8", errors="replace"):
            s = ln.rstrip("\n")
            if re.match(r"^[a-zA-Z]", s):
                insec = s.startswith("items:")
                cur = None
                continue
            if not insec:
                continue
            m = re.match(r"^  - type: (\S+)", s)
            if m:
                cur = m.group(1)
                items.setdefault(cur, {})
                continue
            if cur is None:
                continue
            m = re.match(r"^    (\w+): (.+)$", s)
            if m and m.group(1) in KEEP:
                items[cur][m.group(1)] = m.group(2).strip()
    return items


def reach(items, weapon):
    """Во что складывается удар: вплотную, выстрел, бросок, пси."""
    it = items.get(weapon) or {}
    b = it.get("battleType", "?")
    if b == "3":
        return "вплотную"
    if b == "1":
        try:
            mr = int(it.get("maxRange"))
        except (TypeError, ValueError):
            return "выстрел"
        # в Пиратках дубина и шокер описаны огнестрелом с дальностью 1-3
        return "вплотную" if mr <= 3 else "выстрел"
    if b == "4":
        return "граната"
    if b == "5":
        return "мина"
    if b == "9":
        return "пси"
    return "прочее"


def read_missions(lines):
    i0 = next(i for i, l in enumerate(lines) if l.startswith("missionStatistics:"))
    i1 = next(i for i, l in enumerate(lines) if i > i0 and re.match(r"^[a-zA-Z]", l))
    ms, cur = [], None
    for l in lines[i0 + 1:i1]:
        if l.startswith("  - id:"):
            cur = {"id": int(l.split(":")[1]), "_inj": []}
            ms.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^    (\w+): (.*)$", l)
        if m:
            cur[m.group(1)] = m.group(2).strip()
            continue
        m = re.match(r"^      (\d+): (\d+)$", l)
        if m:
            cur["_inj"].append(int(m.group(2)))
    return ms


def main():
    sav = sys.argv[1] if len(sys.argv) > 1 else SAV_DEFAULT
    rul = sys.argv[2] if len(sys.argv) > 2 else RUL_DEFAULT
    items = load_items(rul)
    txt = io.open(sav, encoding="utf-8", errors="replace").read()
    lines = txt.split("\n")
    K = [m.groups() for m in KILL_RE.finditer(txt)]
    ms = read_missions(lines)
    n = float(len(K))
    print("сохранение: %s" % sav)
    print("предметов в рулсетах: %d, записей в дневниках: %d, боёв: %d"
          % (len(items), len(K), len(ms)))

    st = collections.Counter(g[5] for g in K)
    fc = collections.Counter(g[6] for g in K)
    print("\n=== чем кончилось для противника ===")
    print("  убит      %6d  %5.1f%%" % (st["6"], 100 * st["6"] / n))
    print("  оглушён   %6d  %5.1f%%" % (st["7"], 100 * st["7"] / n))
    print("  из них мирных жителей %d, своих %d" % (fc["2"], fc["0"]))

    print("\n=== чем добивает ===")
    c = collections.Counter(reach(items, g[3]) for g in K)
    for k, v in c.most_common():
        print("  %-10s %6d  %5.1f%%" % (k, v, 100 * v / n))

    print("\n=== на чьём ходу ===")
    for r, name in ((0, "свой ход"), (1, "ход противника")):
        sub = [g for g in K if int(g[8]) % 3 == r]
        m = float(len(sub)) or 1.0
        mel = sum(1 for g in sub if reach(items, g[3]) == "вплотную")
        stn = sum(1 for g in sub if g[5] == "7")
        psi = sum(1 for g in sub if reach(items, g[3]) == "пси")
        mine = sum(1 for g in sub if reach(items, g[3]) == "мина")
        print("  %-15s %6d (%4.1f%%)  вплотную %4.1f%%  живьём %4.1f%%  пси %d  мины %d"
              % (name, len(sub), 100 * m / n, 100 * mel / m, 100 * stn / m, psi, mine))

    print("\n=== оружие, топ 20 ===")
    ws = collections.Counter(g[3] for g in K)
    for k, v in ws.most_common(20):
        print("  %6d  %5.1f%%  %s" % (v, 100 * v / n, k))
    aux = sum(v for k, v in ws.items() if k.startswith("AUX_"))
    print("  всего встроенным оружием машин (AUX_*): %d = %.1f%%" % (aux, 100 * aux / n))

    names = {"0": "в лоб", "1": "слева", "2": "справа", "3": "в спину", "4": "снизу"}
    print("\n=== с какой стороны попадание ===")
    for k, v in collections.Counter(g[9] for g in K).most_common():
        print("  %-9s %6d  %5.1f%%" % (names.get(k, k), v, 100 * v / n))

    own, per = -1, collections.Counter()
    for l in lines:
        if re.match(r"^\s+killList:", l):
            own += 1
            continue
        if own >= 0 and re.match(r"^\s*- \{type: .*,turn: (-?\d+),side: ", l):
            per[own] += 1
    v = sorted(per.values(), reverse=True)
    s = float(sum(v)) or 1.0
    print("\n=== насколько узок ударный кулак (дневников %d) ===" % len(v))
    for k in (1, 5, 10, 20, 50):
        if k <= len(v):
            print("  верхние %2d бойцов: %4.1f%% всех записей" % (k, 100 * sum(v[:k]) / s))

    bym = collections.defaultdict(list)
    for g in K:
        bym[int(g[7])].append(int(g[8]))
    lens = sorted((max(t) - min(t)) // 3 for t in bym.values() if (max(t) - min(t)) // 3 < 100)
    print("\n=== ходов между первым и последним убийством ===")
    print("  медиана %d, 75%% %d, 90%% %d (боёв %d)"
          % (lens[len(lens) // 2], lens[int(len(lens) * .75)], lens[int(len(lens) * .9)], len(lens)))

    def light(x):
        d = int(x.get("daylight", 0))
        return "тьма" if d == 0 else ("сумерки" if d <= 7 else "день")

    print("\n=== освещённость и цена боя ===")
    agg = collections.defaultdict(lambda: [0, 0, 0, 0])
    for x in ms:
        a = agg[light(x)]
        a[0] += 1
        a[1] += len(x["_inj"])
        a[2] += sum(x["_inj"])
        if x.get("success") != "true":
            a[3] += 1
    for k in ("тьма", "сумерки", "день"):
        a = agg[k]
        if not a[0]:
            continue
        print("  %-8s боёв %4d  раненых/бой %.2f  дней лечения/бой %5.1f  провалов %d (%.1f%%)"
              % (k, a[0], a[1] / float(a[0]), a[2] / float(a[0]), a[3], 100.0 * a[3] / a[0]))

    inj = [len(x["_inj"]) for x in ms]
    ok = sum(1 for x in ms if x.get("success") == "true")
    print("\n  успешных боёв %d из %d (%.1f%%), боёв без единого раненого %d (%.0f%%)"
          % (ok, len(ms), 100.0 * ok / len(ms),
             sum(1 for i in inj if i == 0), 100.0 * sum(1 for i in inj if i == 0) / len(inj)))

    print("\n=== как менялась манера (срез по последним боям) ===")
    mx = max(int(g[7]) for g in K)
    for cut, name in ((mx - 200, "последние 200 боёв"), (mx - 500, "последние 500"), (0, "вся кампания")):
        sub = [g for g in K if int(g[7]) >= cut]
        m = float(len(sub)) or 1.0
        print("  %-20s записей %6d  вплотную %4.1f%%  чужой ход %4.1f%%  живьём %4.1f%%  машины %4.1f%%"
              % (name, len(sub),
                 100 * sum(1 for g in sub if reach(items, g[3]) == "вплотную") / m,
                 100 * sum(1 for g in sub if int(g[8]) % 3 == 1) / m,
                 100 * sum(1 for g in sub if g[5] == "7") / m,
                 100 * sum(1 for g in sub if g[3].startswith("AUX_")) / m))

    print("\n=== где у него появляются раненые (боёв >= 6) ===")
    agg2 = collections.defaultdict(lambda: [0, 0, 0])
    for x in ms:
        a = agg2[x.get("type", "?")]
        a[0] += 1
        a[1] += len(x["_inj"])
        if x.get("success") != "true":
            a[2] += 1
    rows = sorted(((a[1] / float(a[0]), k, a) for k, a in agg2.items() if a[0] >= 6), reverse=True)
    for r, k, a in rows[:12]:
        print("  %5.2f раненых/бой  боёв %3d  провалов %d  %s" % (r, a[0], a[2], k))


if __name__ == "__main__":
    main()
