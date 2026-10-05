#!/usr/bin/env python3
"""Профиль поиска пути стенда: разбор строк [AIPF] прогона run_one.py (флаг OXCE_AI_PATHPROF=1, build-ai42).

  py -3.13 tools/ai_speed/path_prof.py pf_st1 pf_ct1 pf_bm1 [--build build-ai42] [--sites 25]

Что считает прибор (AiProbe::pathAsk, docs/research/ai-path-audit-2026-10-01.md): каждый calculate и findReachable
внутри решения ИИ (beforeThink..logDecision) с ключом запроса - вид, юнит, откуда, куда, тип хода, цель ракеты, потолок ОВ,
ОВ и энергия юнита - и временем. Повтор - тот же ключ второй раз в том же решении; межрешенческий повтор (x) - ключ был
в предыдущем решении, а карта и юниты с тех пор не сдвинулись (pathRevision). У повтора сверяется отпечаток ответа
(mis, xmis): любое число кроме 0 значит, что одинаковый запрос дал разный ответ, и кэшировать его нельзя.

Строки: [AIPF] unit= same= tt=<время think, мкс> n= u= r= t= tr= x= tx= mis= xmis= calc= reach= bres= astar= nopath=
на каждое решение; [AIPF] total ... outside_n= outside_t= anchor=0x... в итоге боя; [AIPF] site=0x... kind= n= r= t= tr=
на каждое место вызова. Место вызова - адрес возврата в процессе; имя ему даёт nm по exe сборки: сдвиг от anchor
(адрес AiProbe::active в том же процессе) прибавляется к адресу active из nm, и берётся ближайший символ ниже."""
import argparse
import bisect
import json
import re
import subprocess
import sys

from _common import OUT, ENC_R, ENC_W, build_exe, nm_exe, probe_work

# hex first: "-?\d+" would otherwise take the "0" of "0x..." and every site would land on the anchor
KV = re.compile(r"(\w+)=(0x[0-9a-f]+|-?\d+)")


def parse_line(body):
    return {k: int(v, 16) if v.startswith("0x") else int(v) for k, v in KV.findall(body)}


def read_run(work, name):
    """Строки [AIPF] прогона: решения, итог, места вызова, первые разошедшиеся повторы (mis / xmis)."""
    decisions, total, sites, mis = [], None, [], []
    log = work / ("var_" + name) / "openxcom.log"
    with open(log, encoding=ENC_R, errors="replace") as f:
        for raw in f:
            body = raw.rstrip("\n").split("\t", 2)[-1]
            if not body.startswith("[AIPF] "):
                continue
            rest = body[7:]
            if rest.startswith("total "):
                total = parse_line(rest)
            elif rest.startswith("site="):
                d = parse_line(rest)
                d["kind"] = "calc" if " kind=calc" in rest else "reach"
                sites.append(d)
            elif rest.startswith(("mis ", "xmis ")):
                mis.append(rest)
            else:
                decisions.append(parse_line(rest))
    return decisions, total, sites, mis


class Symbols:
    """Символы exe по nm -C -n: имя по статическому адресу."""

    def __init__(self, exe):
        out = subprocess.run([nm_exe(), "-C", "--defined-only", "-n", str(exe)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace").stdout
        self.addrs, self.names = [], []
        for line in out.splitlines():
            parts = line.split(" ", 2)
            if len(parts) == 3 and parts[1] in "tT":
                self.addrs.append(int(parts[0], 16))
                self.names.append(parts[2])
        self.active = next((a for a, n in zip(self.addrs, self.names) if n == "OpenXcom::AiProbe::active()"), None)

    def name(self, static):
        i = bisect.bisect_right(self.addrs, static) - 1
        if i < 0:
            return "?"
        n = self.names[i]
        n = re.sub(r"\(.*\)( const)?$", "", n).replace("OpenXcom::", "")
        return f"{n}+0x{static - self.addrs[i]:x}"


def pct(a, b):
    return f"{100.0 * a / b:5.1f}%" if b else "    -"


def summary(name, decisions, total, sites, mis, syms, nsites):
    t = total
    print(f"=== {name}")
    if not t:
        print("  нет строки [AIPF] total - бой не дошёл до итога или флаг выключен")
        return
    print(f"  решений {t['decisions']}, из них при неизменной карте и юнитах {t['same']} ({pct(t['same'], t['decisions'])});"
          f" время think {t['tt'] / 1e6:.2f} с")
    print(f"  запросов {t['n']} (calculate {t['calc']}: bresenham {t['bres']}, A* {t['astar']}, без пути {t['nopath']};"
          f" findReachable {t['reach']}); уникальных {t['u']}")
    print(f"  время поиска пути {t['t'] / 1e6:.2f} с = {pct(t['t'], t['tt'])} think")
    print(f"  повторы внутри решения: {t['r']} ({pct(t['r'], t['n'])} запросов), {t['tr'] / 1e6:.2f} с"
          f" ({pct(t['tr'], t['t'])} времени поиска, {pct(t['tr'], t['tt'])} think); ответ разошёлся: {t['mis']}")
    print(f"  повторы предыдущего решения при той же карте: {t['x']} ({pct(t['x'], t['n'])}), {t['tx'] / 1e6:.2f} с"
          f" ({pct(t['tx'], t['t'])} времени поиска); ответ разошёлся: {t['xmis']}")
    print(f"  вне решений (сам ход, проверки игры): {t['outside_n']} запросов"
          f" (calculate {t['outside_calc']}, findReachable {t['outside_reach']}), {t['outside_t'] / 1e6:.2f} с")
    if decisions:
        heavy = sorted(decisions, key=lambda d: -d["t"])[:5]
        print("  самые дорогие решения (юнит: поиск/думал мкс, запросов, повторов):")
        for d in heavy:
            print(f"    {d['unit']:5d}: {d['t']:8d}/{d['tt']:8d}  n={d['n']:4d} r={d['r']:4d} x={d['x']:4d}"
                  f" calc={d['calc']} reach={d['reach']} astar={d['astar']} nopath={d['nopath']}")
        rep = [d for d in decisions if d["r"]]
        print(f"  решений с повторами: {len(rep)} из {len(decisions)}")
    base = syms.active if syms else None

    def where(site):
        return syms.name(base + (site - t["anchor"])) if base else f"0x{site:x}"

    if sites:
        print(f"  места вызова (по времени, первые {nsites}):")
        for s in sorted(sites, key=lambda s: -s["t"])[:nsites]:
            print(f"    {s['kind']:5} n={s['n']:6d} r={s['r']:6d} t={s['t'] / 1e6:7.3f}с tr={s['tr'] / 1e6:7.3f}с  {where(s['site'])}")
    if mis:
        print(f"  разошедшиеся повторы (первые {min(len(mis), 12)} из записанных {len(mis)}; was/now = алгоритм/длина/ОВ,"
              f" us = мкс первого/этого, site0/site = место первого/этого):")
        for m in mis[:12]:
            m = re.sub(r"(site0?)=0x([0-9a-f]+)", lambda x: x.group(1) + "=" + where(int(x.group(2), 16)), m)
            print("    " + m)


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="+", help="имена прогонов run_one.py")
    ap.add_argument("--build", default="build-ai42", help="сборка, чей exe даёт имена местам вызова")
    ap.add_argument("--sites", type=int, default=25)
    ap.add_argument("--json", default="", help="сводку всех прогонов записать в этот файл")
    a = ap.parse_args()
    work = probe_work()
    exe = build_exe(a.build)
    syms = Symbols(exe) if exe.is_file() else None
    if syms and syms.active is None:
        print(f"в {exe} нет символа AiProbe::active - места вызова без имён")
        syms = None
    allsum = {}
    for name in a.names:
        decisions, total, sites, mis = read_run(work, name)
        summary(name, decisions, total, sites, mis, syms, a.sites)
        allsum[name] = {"total": total, "decisions": len(decisions)}
    if a.json:
        with open(a.json, "w", encoding=ENC_W) as f:
            json.dump(allsum, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
