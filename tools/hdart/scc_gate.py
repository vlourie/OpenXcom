# Ворота конвейера адресации стен SCC (docs/research/map-addressing-scc-contract-2026-10-06.md, раздел 5, П-12):
# разрешение address.txt набора против MCD. Движок MCD не видит - эти правила держит только конвейер.
#  - слот разрешения совпадает с типом записи, которая рисует кадр (1 - west, 2 - north);
#  - петля анимации записи (Frame[0..7]) разрешается целиком и с одним n;
#  - всё, во что клетка может перейти из записи (die, alt, дальше по цепочке), если разрешено, - с тем же n
#    и тем же слотом; без разрешения - допустимо (рисуется основным кадром).
# Отказ - код 1 и строка на каждую причину.
#   py -3.13 tools/hdart/scc_gate.py URBAN <путь>/address.txt [--mcd <путь к MCD>]
import argparse, os, re, sys

RECORD = 62
F_FRAMES, F_UFO_DOOR, F_DOOR, F_DIE, F_ALT, F_TYPE = 0, 30, 35, 44, 46, 53
SLOT = {"west": 1, "north": 2}
SLOT_NAME = {1: "west", 2: "north"}
MCD_DIRS = [os.path.join("Пиратки", "Dioxine_XPiratez", "user", "mods", "Piratez", "TERRAIN"),
            os.path.join("user", "mods", "XComFiles", "TERRAIN"),
            os.path.join("bin", "UFO", "TERRAIN")]


def read_mcd(path):
    data = open(path, "rb").read()
    recs = []
    for i in range(0, len(data) - RECORD + 1, RECORD):
        b = data[i:i + RECORD]
        frames = []
        for v in b[F_FRAMES:F_FRAMES + 8]:
            if v not in frames:
                frames.append(v)
        recs.append(dict(i=len(recs), frames=frames, type=b[F_TYPE], die=b[F_DIE], alt=b[F_ALT],
                         door=b[F_DOOR], ufo_door=b[F_UFO_DOOR]))
    return recs


def parse_address(text):
    """Та же грамматика, что у движка (HdSprites::registerWalls): (разрешения {кадр: (слот, n)}, ошибки)."""
    errors, addr = [], {}
    version, frames = None, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"(\w+)\s*:\s*(.*)$", line)
        if not m:
            errors.append("строка без ключа: %r" % line)
        elif m.group(1) == "version":
            version = m.group(2).strip()
        elif m.group(1) == "frames":
            frames = m.group(2).split()
    if version != "1":
        return {}, ["version %r: весь файл выключен" % version]
    for tok in frames or []:
        m = re.fullmatch(r"(\d+):(north|west):(\d+)", tok)
        if not m:
            errors.append("%s: синтаксис" % tok)
            continue
        f, slot, n = int(m.group(1)), SLOT[m.group(2)], int(m.group(3))
        if not 4 <= n <= 16:
            errors.append("%s: n вне 4..16" % tok)
        elif (f, slot) in addr:
            errors.append("%s: повтор" % tok)
            del addr[(f, slot)]
        else:
            addr[(f, slot)] = n
    return addr, errors


def reach(recs, start):
    """Записи, в которые клетка может перейти из start: die и alt, по цепочке (0 - нет связи)."""
    seen, todo = set(), [start]
    while todo:
        r = todo.pop()
        if r in seen or r >= len(recs):
            continue
        seen.add(r)
        for nxt in (recs[r]["die"], recs[r]["alt"]):
            if nxt:
                todo.append(nxt)
    return seen


def check(recs, addr):
    """Список причин отказа (пустой - ворота пройдены) и список предупреждений."""
    refuse, warn = [], []
    by_frame = {}
    for r in recs:
        for f in r["frames"]:
            by_frame.setdefault(f, []).append(r)
    for (f, slot), n in sorted(addr.items()):
        tok = "%d:%s:%d" % (f, SLOT_NAME[slot], n)
        users = by_frame.get(f, [])
        if not users:
            warn.append("%s: кадр не рисует ни одна запись MCD" % tok)
            continue
        for r in users:
            if r["type"] != slot:
                refuse.append("%s: запись %d рисует кадр как тип %d, а не %s" % (tok, r["i"], r["type"], SLOT_NAME[slot]))
                continue
            loop = r["frames"]
            if len(loop) > 1:
                miss = [g for g in loop if addr.get((g, slot)) != n]
                if miss:
                    refuse.append("%s: петля анимации записи %d %s разрешена не целиком или с другим n (кадры %s)"
                                  % (tok, r["i"], loop, miss))
            for q in sorted(reach(recs, r["i"]) - {r["i"]}):
                for g in recs[q]["frames"]:
                    for s2 in (1, 2):
                        n2 = addr.get((g, s2))
                        if n2 is not None and (n2 != n or s2 != slot):
                            refuse.append("%s: запись %d переходит в запись %d (кадр %d), а там %s:%d"
                                          % (tok, r["i"], q, g, SLOT_NAME[s2], n2))
    return sorted(set(refuse)), warn


def find_mcd(set_name, root="."):
    for d in MCD_DIRS:
        folder = os.path.join(root, d)
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                b, e = os.path.splitext(name)
                if b.upper() == set_name.upper() and e.upper() == ".MCD":
                    return os.path.join(folder, name)
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("address")
    ap.add_argument("--mcd")
    o = ap.parse_args()
    mcd = o.mcd or find_mcd(o.set)
    if not mcd:
        sys.exit("MCD набора %s не найден" % o.set)
    addr, errors = parse_address(open(o.address, encoding="utf-8-sig").read())
    refuse, warn = check(read_mcd(mcd), addr)
    for w in warn:
        print("предупреждение:", w)
    for e in errors:
        print("ОТКАЗ (файл):", e)
    for r in refuse:
        print("ОТКАЗ:", r)
    ok = not refuse and not errors and addr
    print("%s: %s, разрешений %d (MCD %s)" % (o.set, "ПРОХОДИТ" if ok else "ОТКАЗ", len(addr), mcd))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
