#!/usr/bin/env python3
"""Отчёт по выборкам prof_battle.py: плоский профиль, включающий, дерево от Game::run.

py -3.13 tools/ai_speed/prof_report.py prof_sotl.samples.json [--phase battle] [--tree 0.7] [--top 50]"""
import argparse, bisect, json, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

from _common import ROOT, OUT, ENC_R, ENC_W, build_dir, nm_exe

PREF = 0x140000000


def symbols(build):
    exp = Path(build).is_absolute()  # опытная сборка из блокнота: символы снимать заново после каждой пересборки
    cache = OUT / (("oxce_exp" if exp else build) + ".nm.txt")
    OUT.mkdir(exist_ok=True)
    if exp or not cache.exists():
        r = subprocess.run([nm_exe(), "-n", "--defined-only", "-C", str(build_dir(build) / "bin" / "openxcom.exe")],
                           capture_output=True)
        cache.write_bytes(r.stdout)
    addrs, names = [], []
    for line in cache.read_text(encoding=ENC_R, errors="replace").splitlines():
        p = line.split(" ", 2)
        if len(p) < 3 or p[1] not in "TtWw":
            continue
        n = p[2]
        if n.startswith((".", "__gnu", "_Unwind")) and p[1] in "t":
            pass
        addrs.append(int(p[0], 16))
        names.append(n)
    return addrs, names


def short(name):
    name = name.replace("OpenXcom::", "")
    name = re.sub(r"\(.*", "", name) if not name.startswith("(") else name
    return name[:110]


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--phase", default="battle")
    ap.add_argument("--top", type=int, default=45)
    ap.add_argument("--tree", type=float, default=1.0, help="порог ветки дерева, процентов")
    ap.add_argument("--depth", type=int, default=14)
    ap.add_argument("--root", default="Game::run")
    a = ap.parse_args()
    d = json.loads(Path(a.file).read_text(encoding=ENC_R))
    addrs, names = symbols(d["build"])
    mods = sorted((b, b + s, n) for b, s, n in d["mods"])
    exe = next((m for m in mods if m[2].lower() == "openxcom.exe"), None)
    cache = {}

    def name(addr, leaf):
        key = (addr, leaf)
        if key in cache:
            return cache[key]
        r = "?"
        for b, e, n in mods:
            if b <= addr < e:
                if exe and b == exe[0]:
                    va = addr - b + PREF - (0 if leaf else 1)
                    i = bisect.bisect_right(addrs, va) - 1
                    r = short(names[i]) if i >= 0 else "exe?"
                else:
                    r = "[" + n + "]"
                break
        cache[key] = r
        return r

    samples = [s for ph, s in d["samples"] if ph == a.phase or a.phase == "all"]
    n = len(samples)
    print(f"{d['mission']} зерно {d['seed']} {d['build']} запись={d['record']} {' '.join(d.get('env', []))}")
    print(f"всего {d['wall']:.1f} с, выборок фазы {a.phase}: {n} из {len(d['samples'])}, шаг {d['interval'] * 1000:.0f} мс, "
          f"поток стоял под замером {d['walk_s']:.1f} с")
    for l in d["result"]:
        print("  " + l[:400])
    if d.get("cpu"):
        print("потоки (tid, ЦП ядро+польз, с):", ", ".join(f"{t[0]}: {t[2] + t[3]:.1f}" for t in d["cpu"]))
    if not n:
        return
    flat, incl = Counter(), Counter()
    tree = defaultdict(int)
    noroot = 0
    for st in samples:
        nm = [name(x, i == 0) for i, x in enumerate(st)]
        flat[nm[0]] += 1
        for x in set(nm):
            incl[x] += 1
        path = list(reversed(nm))
        # дерево от корня: сжимаем повторы и чужие модули подряд
        if a.root in " ".join(path):
            i = max(j for j, x in enumerate(path) if a.root in x)
            path = path[i:]
        else:
            noroot += 1
            path = ["(без " + a.root + ")"] + path[-6:]
        comp = []
        for x in path:
            if comp and comp[-1] == x:
                continue
            comp.append(x)
        for j in range(1, min(len(comp), a.depth) + 1):
            tree[tuple(comp[:j])] += 1
    print(f"\n--- свой код функции (лист стека), первые {a.top} ---")
    for k, v in flat.most_common(a.top):
        print(f"{100 * v / n:6.2f} %  {k}")
    print(f"\n--- функция где-либо в стеке (включая вызванное), первые {a.top + 25} ---")
    for k, v in incl.most_common(a.top + 25):
        print(f"{100 * v / n:6.2f} %  {k}")
    print(f"\n--- дерево от {a.root} (ветки от {a.tree} %), без корня {100 * noroot / n:.1f} % ---")
    kids = defaultdict(list)
    for path, v in tree.items():
        kids[path[:-1]].append((v, path))

    def walk(path, ind):
        for v, p in sorted(kids.get(path, []), reverse=True):
            if 100 * v / n < a.tree:
                continue
            print(f"{100 * v / n:6.2f} %  {'  ' * ind}{p[-1]}")
            walk(p, ind + 1)

    walk((), 0)


if __name__ == "__main__":
    main()
