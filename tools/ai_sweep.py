#!/usr/bin/env python3
"""Уборка рабочих папок прогонов игры (ai_probe, ai_arena, game_hidden): удаляет папки, которые не трогали дольше
--hours, итоги серий (arena/) не трогает. Соединение mods в папке ведёт на моды установки - снимается ссылкой,
внутрь обход не заходит (R-047).

Зачем: 02.10 вторая машина встала с полным диском - 4218 папок боёв, ~400 ГБ, серия упала посреди. На стендах то же
делает панель (aiworker.sweep после серии и раз в час); здесь - для основной машины и ручных прогонов.

  py -3.13 tools/ai_sweep.py              что удалилось бы (ничего не трогает)
  py -3.13 tools/ai_sweep.py --run        удалить
  --hours 12      не трогать папки моложе (по умолчанию 12 ч: идущие и только что доигранные прогоны целы)
  --root DIR      корень (по умолчанию %OXCE_AI_WORK%/oxce_ai_probe или %TEMP%/oxce_ai_probe и %TEMP%/oxce_hidden_user)
"""
import argparse, os, sys, tempfile, time
from pathlib import Path

REPARSE, DIRECTORY, READONLY = 0x400, 0x10, 0x1
KEEP = {"arena"}  # итоги серий ai_arena: таблицы, архивы боёв


def roots():
    base = os.environ.get("OXCE_AI_WORK")
    out = [Path(base) / "oxce_ai_probe"] if base else [Path(tempfile.gettempdir()) / "oxce_ai_probe"]
    out.append(Path(tempfile.gettempdir()) / "oxce_hidden_user")
    return out


def is_work_dir(p):
    """Папка прогона: в ней конфиг, журнал игры или ссылка на моды."""
    return any((p / n).exists() or os.path.lexists(p / n) for n in ("options.cfg", "openxcom.log", "mods"))


def newest(p):
    """Последнее изменение: сама папка и её верхний уровень (журнал игры пишется на каждом ходу)."""
    t = p.stat().st_mtime
    try:
        for e in os.scandir(p):
            t = max(t, e.stat(follow_symlinks=False).st_mtime)
    except OSError:
        pass
    return t


def size(path):
    n = 0
    for e in os.scandir(path):
        st = e.stat(follow_symlinks=False)
        if st.st_file_attributes & REPARSE:
            continue
        n += size(e.path) if e.is_dir(follow_symlinks=False) else st.st_size
    return n


def rmtree(path):
    for e in os.scandir(path):
        st = e.stat(follow_symlinks=False)
        if st.st_file_attributes & REPARSE:  # соединение или ссылка: снимаем саму ссылку
            (os.rmdir if st.st_file_attributes & DIRECTORY else os.unlink)(e.path)
        elif e.is_dir(follow_symlinks=False):
            rmtree(e.path)
        else:
            if st.st_file_attributes & READONLY:
                os.chmod(e.path, 0o666)
            os.unlink(e.path)
    os.rmdir(path)


def candidates(root, hours, sub=False):
    """Папки прогонов в корне. sub: корень сам - одна папка прогона (oxce_hidden_user)."""
    if not root.is_dir():
        return []
    dirs = [root] if sub else [Path(e.path) for e in os.scandir(root)
                               if e.is_dir(follow_symlinks=False) and e.name not in KEEP]
    old = time.time() - hours * 3600
    return [d for d in dirs if is_work_dir(d) and newest(d) < old]


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", action="store_true", help="удалить (без ключа - только показать)")
    ap.add_argument("--hours", type=float, default=12)
    ap.add_argument("--root", action="append", help="корень (можно несколько)")
    a = ap.parse_args()
    total = gone = 0
    for root in ([Path(r) for r in a.root] if a.root else roots()):
        found = candidates(root, a.hours, sub=root.name == "oxce_hidden_user")
        if not found:
            print(f"{root}: нечего убирать")
            continue
        sz = sum(size(d) for d in found)
        total += sz
        print(f"{root}: папок прогонов старше {a.hours:g} ч - {len(found)}, {sz / 2 ** 30:.1f} ГБ")
        if not a.run:
            continue
        for d in found:
            try:
                rmtree(d)
                gone += 1
            except OSError as ex:
                print(f"  не удалилась {d.name}: {ex!r}")
    if a.run:
        print(f"удалено папок {gone}, освобождено ~{total / 2 ** 30:.1f} ГБ")
    elif total:
        print("ничего не удалено: запуск с --run удалит")


if __name__ == "__main__":
    main()
