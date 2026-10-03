#!/usr/bin/env python3
"""Побоища: серия случайных боёв Пираток, где обе стороны ведёт ИИ, и статистика по ним.

Каждое зерно - свой бой: миссия, местность, раса и тьма выбираются игрой по зерну
(NewBattleState::probeRandomize); отряд - самый большой экипаж кампании Vitali (копия сейва, со снаряжением,
сложностью и месяцем кампании), с --recruits - новобранцы быстрого боя в корабле от 8 мест. Обе стороны играет ИИ (OXCE_AI_BOT), итог - строка [AIRESULT].
Одно и то же зерно на той же сборке даёт тот же бой: серию можно повторить после правки ИИ и
сравнить мерило - раненые за бой, потерянное здоровье, доля боёв с ранеными, длина боя
(docs/AI_ROADMAP.md, «Цель»).

Прогоны невидимые и тихие (tools/ai_probe.py): скрытые окна, звук в dummy, приоритет ниже обычного,
по умолчанию 4 боя одновременно. Нужна локальная сборка стенда build-ai (cmake -DOXCE_AI_DEV=ON).

  py -3.13 tools/ai_arena.py --seeds 1-40 [--jobs 4] [--turns 60] [--diff 4] [--label base] [--out итог.txt]
  py -3.13 tools/ai_arena.py --missions @tools/ai_missions.txt --seeds 1-50 --jobs 8 --label maps27 [--resume]

С --missions каждая миссия играется на всех зёрнах (местность, раса и отряд - по зерну), в сводке строка на миссию.
Таблица пишется по строке после каждого боя; --resume продолжает прерванную серию с того же места.
Контракт серии: --strict-flags (флаги стенда явно), --expect exe=.. ai_probe=.. data=.. flags=.. (отпечатки, которые
задание ждёт от машины) - не совпало, ни одного боя; список файлов отпечатка данных - <label>.data_manifest.tsv.

Таблица боёв - <label>.tsv рядом с логами прогона (%TEMP%/oxce_ai_probe/arena), сводка - в stdout и --out.
"""
import argparse, collections, gzip, json, os, queue, re, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_probe

ENC_W = "utf-8-sig"
ENC_R = "utf-8-sig"
# поведение из [AIDECIDE]: p - сторона игрока (бот), h - враг
MOVES = ("decisions", "run", "kneel", "throw", "psi", "melee")
COLS = ("seed", "want", "how", "mission", "kind", "month", "units", "terrain", "race", "craft", "shade", "turn", "player", "pdead", "pout",
        "pwounded", "phplost", "hostile", "hdead", "hout", "hleft", "livesoldiers", "livealiens", "aborted",
        "pattacks", "hattacks", "tac") + tuple(s + m for s in "ph" for m in MOVES) + ("seconds", "note")
DECIDE = re.compile(r"\[AIDECIDE\] turn=\d+ side=(\d) .*? act=(\d+) to=\S+ run=(\d)(?: kneel=(\d))?")


def behaviour(log):
    """Счётчики решений по сторонам из лога боя: сам лог перезапишет следующий бой того же потока."""
    c = collections.Counter()
    try:
        text = Path(log).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    for side, act, run, kneel in DECIDE.findall(text):
        s = {"0": "p", "1": "h"}.get(side)
        if not s:
            continue
        act = int(act)
        c[s + "decisions"] += 1
        c[s + "run"] += act == 2 and run == "1"
        # присед - и отдельным действием, и флагом при выстреле или засаде (AIModule.cpp, action->kneel)
        c[s + "kneel"] += act == 3 or kneel == "1"
        c[s + "throw"] += act in (6, 12)
        c[s + "psi"] += act in (13, 14)
        c[s + "melee"] += act == 10
    return {s + m: c[s + m] for s in "ph" for m in MOVES}


def seeds_of(spec):
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b) + 1)) if b else [int(a)]
    return out


MECH_EXT = (".rul", ".map", ".rmp", ".mcd")  # рулсеты, карты, маршруты, свойства тайлов: картинки, звук и строки не входят
PATH_KEYS = ("OXCE_AI_EXE", "OXCE_AI_GAME", "OXCE_AI_WORK", "OXCE_AI_BUILD")  # где лежит, а не что играет: exe - своим отпечатком


def sha_file(path, h=None):
    import hashlib
    h = h or hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h


def data_fingerprint(a, manifest=None):
    """Данные механики, которые читает бой: файлы MECH_EXT установки (ai_probe.GAME) по пути без регистра, сейв кампании,
    файл миссий. Хэш по файлам кэшируется в arena/.data_hash.json по (размер, время изменения).
    manifest (список) получает строки «путь без регистра, размер, sha256» в порядке хэша - сверить две машины файл в файл."""
    import hashlib
    cache_path = ai_probe.WORK / "arena" / ".data_hash.json"
    try:
        cache = json.loads(cache_path.read_text(encoding=ENC_R))
    except (OSError, ValueError):
        cache = {}
    files = []
    for root, dirs, names in os.walk(ai_probe.GAME):
        dirs[:] = sorted(d for d in dirs if d.lower() != "language")
        files += [Path(root) / n for n in names if n.lower().endswith(MECH_EXT)]
    if not a.recruits:
        files.append(ai_probe.campaign_path(a.campaign))
    if a.missions.startswith("@"):
        files.append(Path(a.missions[1:]).resolve())
    total, fresh = hashlib.sha256(), {}
    for p in sorted(files, key=lambda p: str(p).lower()):
        try:
            st = p.stat()
        except OSError:
            total.update(f"{p}|missing\n".encode())
            if manifest is not None:
                manifest.append(f"{p}\tmissing\t")
            continue
        key = f"{p}|{st.st_size}|{st.st_mtime_ns}"
        fresh[key] = cache.get(key) or sha_file(p).hexdigest()
        rel = os.path.relpath(p, ai_probe.GAME) if str(p).lower().startswith(str(ai_probe.GAME).lower()) else p.name
        total.update(f"{rel.lower()}|{fresh[key]}\n".encode())
        if manifest is not None:
            manifest.append(f"{rel.lower()}\t{st.st_size}\t{fresh[key]}")
    try:
        cache_path.write_text(json.dumps(fresh), encoding=ENC_W)
    except OSError:
        pass
    return total.hexdigest(), len(files)


def effective_flags():
    """Окружение боя OXCE_AI_* после --env и значений по умолчанию ai_probe.bench_defaults, без путей, каноническим текстом."""
    env = ai_probe.bench_defaults({k: v for k, v in os.environ.items() if k.startswith("OXCE_AI_") and k not in PATH_KEYS})
    return ";".join(f"{k}={env[k]}" for k in sorted(env))


FP_KEYS = ("exe", "ai_probe", "data", "flags")


def fingerprints(a, manifest=None):
    """Четыре отпечатка серии (контракт конфигурации 02.10): exe, ai_probe.py, данные механики, флаги. Пары A/B и
    продолжение серии сравнивают их: разные - INVALID_CONFIG."""
    import hashlib
    try:
        exe = sha_file(ai_probe.EXE).hexdigest()
    except OSError:
        exe = "missing"
    data, n = data_fingerprint(a, manifest)
    flags = effective_flags()
    return {"exe": exe, "ai_probe": sha_file(ai_probe.__file__).hexdigest(), "data": data,
            "flags": hashlib.sha256(flags.encode()).hexdigest()}, flags, n


def read_fingerprint(prov):
    """Отпечатки последнего старта из arena/<label>.prov.txt, или None (старые серии их не писали)."""
    try:
        lines = prov.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    last = next((ln for ln in reversed(lines) if ln.startswith("fingerprint: ")), None)
    return dict(kv.split("=", 1) for kv in last[len("fingerprint: "):].split()) if last else None


def provenance(a):
    """Происхождение серии - перед КАЖДЫМ стартом (и при --resume): хэш exe, сборка, коммит, окружение боя.
    Пишется в stdout (журнал воркера logs/<label>.out) и дописывается в arena/<label>.prov.txt рядом с таблицей.
    Коммит - из BUILD_INFO.txt в каталоге exe (пишется при упаковке сборки), в сам exe он не зашит."""
    import datetime, hashlib
    exe = ai_probe.EXE
    h = hashlib.sha256()
    try:
        with open(exe, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        st = exe.stat()
        sha, size = h.hexdigest(), st.st_size
        mtime = datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
    except OSError as e:
        sha, size, mtime = f"нет ({e})", "", ""
    try:
        info = (exe.parent / "BUILD_INFO.txt").read_text(encoding="utf-8-sig").strip().splitlines()
    except OSError:
        info = []
    commit = next((ln.split("=", 1)[1] for ln in info if ln.startswith("git_commit=")), "unknown")
    keys = ("OXCE_AI_FAST", "OXCE_AI_ENERGY_PATROL_END", "OXCE_AI_FIREPOINT_ENERGY_PATH")
    eff = {k: v for k, v in os.environ.items() if k.startswith("OXCE_AI_") and k not in ("OXCE_AI_EXE", "OXCE_AI_GAME", "OXCE_AI_WORK")}
    lines = [f"=== provenance {datetime.datetime.now().isoformat(timespec='seconds')} label={a.label}",
             f"exe_sha256={sha}", f"exe_size={size}", f"exe_mtime={mtime}", f"exe_path={exe}",
             f"build_label={exe.parent.name}", f"git_commit={commit}",
             # чья машина играла: панель стенда ставит AIWORKER_ID из settings.json, иначе имя компьютера;
             # не OXCE_AI_ - такие движок кладёт в хэш cfg каждой строки записи, и серии разных машин разойдутся
             f"worker_id={os.environ.get('AIWORKER_ID') or os.environ.get('COMPUTERNAME', 'unknown')}",
             "effective_env: " + ", ".join(f"{k}={eff.get(k, '<unset>')}" for k in keys),
             "all_oxce_ai_env: " + " ".join(f"{k}={eff[k]}" for k in sorted(eff)),
             "args: " + " ".join(sys.argv[1:])]
    manifest = []
    fp, flags, n = fingerprints(a, manifest)
    arena = ai_probe.WORK / "arena"
    arena.mkdir(parents=True, exist_ok=True)
    # файлы, из которых сложен отпечаток данных: при расхождении машин сравнить два таких списка (diff), а не гадать
    (arena / f"{a.label}.data_manifest.tsv").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    prov = arena / f"{a.label}.prov.txt"
    before = read_fingerprint(prov)
    errors = []
    # продолжение серии с другой конфигурацией смешало бы две серии в одной таблице
    if a.resume and before and (arena / f"{a.label}.tsv").exists() and before != fp:
        errors.append(f"серия {a.label} продолжается с другими отпечатками: "
                      + " ".join(k for k in fp if before.get(k) != fp[k]))
    # ожидаемые отпечатки из задания (--expect): устаревший exe, ai_probe или game\ станции не играет ни одного боя
    for k, v in getattr(a, "expect", {}).items():
        if fp[k] != v:
            errors.append(f"отпечаток {k}: ожидался {v}, на машине {fp[k]}"
                          + (f" (файлы данных - {arena / (a.label + '.data_manifest.tsv')})" if k == "data" else ""))
    # отклонённый старт пишется под другим именем: read_fingerprint берёт последний ПРИНЯТЫЙ, иначе следующее
    # продолжение с верной конфигурацией сверялось бы с отклонённой
    tag = "rejected_fingerprint: " if errors else "fingerprint: "
    lines += [f"effective_flags={flags}", f"data_files={n}", tag + " ".join(f"{k}={v}" for k, v in fp.items())]
    print("\n".join(lines), flush=True)
    with open(prov, "a", encoding="utf-8") as f:
        f.write("\n".join(lines + [f"INVALID_CONFIG: {e}" for e in errors]) + "\n")
    if errors:
        for e in errors:
            print(f"INVALID_CONFIG: {e}", flush=True)
        sys.exit(3)


SLOTS = queue.Queue()
LABEL = "arena"


def one(seed, turns, diff, timeout, campaign, mission=None, tactics=False, careful=False, squad=0):
    # папка прогона - по потоку, а не по зерну: одно зерно идёт на разных миссиях одновременно;
    # у каждой серии (--label) свои папки - серии идут рядом, в том числе на одной сборке
    slot = SLOTS.get()
    try:
        r = ai_probe.run(None, turns, name=f"arena_{LABEL}_w{slot}", timeout=timeout, bot=True, seed=seed, diff=diff,
                         campaign=campaign, mission=mission, tactics=tactics, careful=careful, squad=squad)
        moves = behaviour(r.log)
    finally:
        SLOTS.put(slot)
    row = {"seed": seed, "want": mission or "", "seconds": f"{r.seconds:.0f}", "note": "",
           "_casualties": r.tagged("[AICASUALTY]"), "_tiles": r.tagged("[AISTATE]"),
           # решения и, по OXCE_AI_TRACE_MELEE, кандидаты ближнего боя ([AIMELEE]), по OXCE_AI_TRACE_PATH -
           # расчёты пути ([AIPATH]) - в порядке лога
           "_decide": [l for l in r.lines if l.startswith(("[AIDECIDE]", "[AIMELEE]", "[AIPATH]"))] if os.environ.get("OXCE_AI_KEEP_DECIDE") else [],
           # по OXCE_AI_RECORD - запись решений (docs/AI_DECISION_RECORD.md): решение, исполнение, итог после хода врага,
           # разбор по OXCE_AI_TRACE_DECISION; списки кандидатов ([AICAND]) - отдельно, они тяжелее всего остального
           "_rec": [l for l in r.lines if l.startswith(("[AIRECHEAD]", "[AIREC]", "[AIEXEC]", "[AIAFTER]", "[AITRACE]"))],
           "_cand": r.tagged("[AICAND]"),
           # по OXCE_AI_RECORD_PATH - путь патруля и что держит первый шаг ([AIPATROL], план V2, L0-B)
           "_path": [l for l in r.lines if l.startswith("[AIPATROL]")],
           # итоги боя со счётчиками приборов стенда (свет, отход, FOV на шаге) - по ним читается шлюз серии; в сверку
           # series_eq.py не входят (в них время); [AIPF] - профиль пути по OXCE_AI_PATHPROF=1 (лог боя станция убирает)
           "_result": [l for l in r.lines if l.startswith(("[AIRESULT]", "[AILIGHT]", "[AIESCRF]", "[AIWALKFOV]", "[AIWALKFOVSKIP]", "[AIAMBMEMO]", "[AIPF]"))]}
    row.update(moves)
    battle = r.tagged("[AIPROBE] battle")
    if battle:
        row.update({k: v for k, v in ai_probe.fields(battle[0]).items() if k in COLS})
    res = r.tagged("[AIRESULT]")
    if res:
        got = ai_probe.fields(res[0])
        # mission в [AIRESULT] - тип боя движка (у любого НЛО STR_UFO_GROUND_ASSAULT), миссия - из строки battle
        row["kind"] = got.pop("mission", "")
        row.update({k: v for k, v in got.items() if k in COLS})
    else:
        stuck = r.tagged("[AIPROBE] stuck")
        row["how"] = "stuck" if stuck else ("nobattle" if not battle else "timeout-real")
        row["note"] = stuck[0].split(": ", 1)[-1] if stuck else str(r.log)
    return row


def outcome(row):
    """win - врагов на ногах не осталось, loss - у игрока, draw - предел ходов, иначе прогон не дошёл."""
    if row.get("want") and row.get("mission") and row["want"] != row["mission"]:
        return "unpinned"  # такой миссии нет в списке быстрого боя, игра взяла случайную
    if "could not be placed" in row.get("note", ""):
        return "nomap"  # корабль не встаёт на карту миссии: генератор падает так же и в игре
    if row.get("how") not in ("over", "abort", "timeout"):
        return row.get("how", "?")
    if row["how"] == "timeout":
        return "draw"
    if row.get("livealiens", "") != "":
        # подсчёт движка: сдавшихся, пленённых пси и оглушённых сверх порога он живыми не считает
        if int(row["livealiens"]) == 0:
            return "win"
        if int(row["livesoldiers"]) == 0:
            return "loss"
        # бот не отступает никогда: прерванный бой - это таймер миссии (turnLimit + chronoTrigger), отряд продержался
        return "held" if row["how"] == "abort" or row.get("aborted") == "1" else "end-other"
    if int(row["hleft"]) == 0:
        return "win"
    if int(row["pdead"]) + int(row["pout"]) >= int(row["player"]):
        return "loss"
    return "abort"


def summary(rows, label):
    lines = [f"серия {label}: боёв {len(rows)}"]
    by = {}
    for r in rows:
        by.setdefault(outcome(r), []).append(r)
    lines.append("исходы: " + ", ".join(f"{k} {len(v)}" for k, v in sorted(by.items())))
    done = [r for r in rows if outcome(r) in ("win", "loss", "draw", "held", "abort", "end-other")]
    if not done:
        return lines
    n = len(done)
    num = lambda r, k: int(r[k])
    wounded = [num(r, "pwounded") for r in done]
    lines += [
        f"сыгранных {n}: раненых за бой {sum(wounded) / n:.2f}, боёв с ранеными {100 * sum(w > 0 for w in wounded) / n:.0f} %,"
        f" погибших за бой {sum(num(r, 'pdead') for r in done) / n:.2f}, без сознания {sum(num(r, 'pout') for r in done) / n:.2f}",
        f"потеряно здоровья за бой {sum(num(r, 'phplost') for r in done) / n:.1f},"
        f" ходов в бою медиана {statistics.median(num(r, 'turn') for r in done):.0f},"
        f" врагов убито/оглушено {sum(num(r, 'hdead') + num(r, 'hout') for r in done)} из {sum(num(r, 'hostile') for r in done)}",
        f"атак за бой: игрок {sum(num(r, 'pattacks') for r in done) / n:.1f}, враг {sum(num(r, 'hattacks') for r in done) / n:.1f};"
        f" время боя медиана {statistics.median(float(r['seconds']) for r in done):.0f} с",
    ]
    moves = {m: sum(int(r.get(m) or 0) for r in done) for m in COLS if m[1:] in MOVES}
    for s, who in (("p", "бот-игрок"), ("h", "враг")):
        d = moves[s + "decisions"] or 1
        lines.append(f"{who}: решений {moves[s + 'decisions']}, бегом {100 * moves[s + 'run'] / d:.1f} %,"
                     f" присел {100 * moves[s + 'kneel'] / d:.1f} %, гранат и ракет {moves[s + 'throw']},"
                     f" пси {moves[s + 'psi']}, вплотную {moves[s + 'melee']}")
    bad = [r for r in rows if r not in done]
    for r in bad:
        lines.append(f"  не доиграно: зерно {r['seed']} {r.get('how')} {r.get('mission', '-')} {r.get('note', '')[:160]}")
    return lines


def by_mission(rows):
    """Строка на миссию: сколько сыграно, исходы, погибших и раненых за бой, длина боя."""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r.get("want") or r.get("mission") or "-"].append(r)
    lines = ["", "по миссиям (сыграно | победа/поражение/предел | погибло, ранено из отряда | ходов медиана | nomap):"]
    for m, rs in sorted(groups.items()):
        done = [r for r in rs if outcome(r) in ("win", "loss", "draw", "held", "abort", "end-other")]
        out = collections.Counter(outcome(r) for r in rs)
        if not done:
            lines.append(f"  {m}: не сыграно ни одного, {dict(out)}")
            continue
        n = len(done)
        mean = lambda k: sum(int(r[k]) for r in done) / n
        lines.append(f"  {m}: {n} | {out['win']}/{out['loss']}/{out['draw']} | {mean('pdead'):.1f}, {mean('pwounded'):.1f}"
                     f" из {mean('player'):.0f} | {statistics.median(int(r['turn']) for r in done):.0f}"
                     f" | {out['nomap']}" + (f" | прочее {n - out['win'] - out['loss'] - out['draw']}"
                                              if n > out['win'] + out['loss'] + out['draw'] else "")
                     + (f" | не доиграно {len(rs) - n - out['nomap']}" if len(rs) - n - out['nomap'] else ""))
    return lines


def read_table(table):
    """Уже сыгранные строки таблицы - чтобы продолжить прерванную серию (--resume)."""
    if not table.exists():
        return []
    lines = table.read_text(encoding=ENC_W).splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln.strip()]


# архивы боя рядом с таблицей: павшие текстом, остальное gzip членами; ключ строки боя -> суффикс файла
ARCHIVES = (("_casualties", ".casualties.txt"), ("_tiles", ".tiles.gz"), ("_decide", ".decide.gz"),
            ("_rec", ".rec.gz"), ("_cand", ".cand.gz"), ("_path", ".path.gz"), ("_result", ".result.txt"))


def _append(path, data):
    with open(path, "ab") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def pack_battle(row):
    """Куски архивов боя: (суффикс, байты), gzip-член собран в памяти. Зовётся в потоке боя (play), не в главном:
    zlib отпускает GIL, и сжатие идёт параллельно. В главном потоке сервер (44 игры, ядро 2.6 ГГц) упирался в одно
    ядро на gzip.compress cand - игры кончились, а бои дописывались ещё минуты по одному."""
    tag = f"seed={row['seed']} want={row['want']} "
    out = []
    for key, ext in ARCHIVES:
        if row.get(key):
            # концы строк как у прежней записи текстовым режимом (на Windows CRLF и в таблице, и внутри gzip)
            text = "".join(f"{tag}{line}{os.linesep}" for line in row[key]).encode("utf-8")
            # уровень 1, а не 9 по умолчанию: бой станции 387 МБ сжимается 3,8 с вместо 71 с при +22 % размера, хвост
            # серии был сжатием последнего боя; распакованные байты те же, сами .gz - нет
            out.append((ext, text if ext.endswith(".txt") else gzip.compress(text, compresslevel=1)))
    return out


def play(*args):
    """Бой и его архивы в потоке пула. Строки архивов после сжатия из строки боя убраны: rows держится до конца
    серии ради сводки, а сводке нужны только столбцы таблицы."""
    row = one(*args)
    packed = pack_battle(row)
    for key, _ in ARCHIVES:
        row.pop(key, None)
    return row, packed


def commit_battle(table, row, packed=None):
    """Бой в серию целиком или никак (R-162). Порядок: журнал с прежними размерами архивов -> куски архивов
    (gzip-член собран в памяти, одна запись на файл) -> строка таблицы - отметка «бой записан» -> журнал снят.
    Оборвали посреди - recover() при --resume срежет архивы до размеров из журнала, и бой сыграется заново.
    packed - готовые куски из play(); без них сжимается здесь."""
    chunks = [(table.with_suffix(ext), data) for ext, data in (pack_battle(row) if packed is None else packed)]
    journal = table.with_suffix(".journal")
    sizes = {p.name: (p.stat().st_size if p.exists() else 0) for p, _ in chunks}
    tmp = journal.with_suffix(".journal.tmp")
    tmp.write_text("\t".join([str(row["seed"]), str(row.get("want", ""))] + [f"{n}={s}" for n, s in sizes.items()]) + "\n",
                   encoding="utf-8")
    os.replace(tmp, journal)
    for path, data in chunks:
        _append(path, data)
    _append(table, ("\t".join(str(row.get(c, "")).replace("\t", " ") for c in COLS) + "\t" + outcome(row) + os.linesep).encode("utf-8"))
    journal.unlink()


def recover(table):
    """Перед --resume: оборванная строка таблицы срезается, архивы незаписанного боя - до размеров из журнала.
    Возвращает, что сделано (для журнала серии); пустая строка - серия остановлена между боями."""
    done = []
    if table.exists():
        raw = table.read_bytes()
        if raw and not raw.endswith(b"\n"):
            with open(table, "r+b") as f:
                f.truncate(raw.rfind(b"\n") + 1)
            done.append("срезана оборванная строка таблицы")
    journal = table.with_suffix(".journal")
    if not journal.exists():
        return "; ".join(done)
    seed, want, *sizes = journal.read_text(encoding="utf-8").rstrip("\n").split("\t")
    if (want, seed) in {(r.get("want", ""), str(r["seed"])) for r in read_table(table)}:
        done.append(f"бой {seed} {want} записан до остановки, журнал снят")
    else:
        for item in sizes:
            name, _, size = item.rpartition("=")
            path = table.parent / name
            if path.exists() and path.stat().st_size > int(size):
                with open(path, "r+b") as f:
                    f.truncate(int(size))
                done.append(f"{name} срезан до {size}")
        done.append(f"бой {seed} {want} не записан - сыграется заново")
    journal.unlink()
    return "; ".join(done)


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # R-001
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", default="1-20", help="зёрна боёв: 1-40 или 3,7,10-12")
    ap.add_argument("--jobs", type=int, default=4, help="боёв одновременно")
    ap.add_argument("--turns", type=int, default=60, help="предел ходов боя")
    ap.add_argument("--diff", type=int, default=None, help="сложность 0-4 (по умолчанию из кампании, иначе 4)")
    ap.add_argument("--campaign", default="NoCodexCatZ.sav", help="сейв кампании: отряд - самый большой экипаж оттуда")
    ap.add_argument("--recruits", action="store_true", help="вместо кампании новобранцы быстрого боя")
    ap.add_argument("--timeout", type=int, default=1200, help="секунд на бой")
    ap.add_argument("--missions", default="", help="миссии через запятую или @файл (строка на миссию): каждая на всех зёрнах")
    ap.add_argument("--resume", action="store_true", help="продолжить серию: уже сыгранные миссия+зерно из таблицы пропустить")
    ap.add_argument("--tactics", action="store_true", help="враг с правилами опыта (OXCE_AI_TACTICS): стреляет или уходит в укрытие")
    ap.add_argument("--careful", action="store_true", help="осторожный бот за игрока (OXCE_AI_CAREFUL): укрытие, отвод раненых, присед и бег по правилам игрока")
    ap.add_argument("--squad", type=int, default=0, help="отряд как у Vitali (OXCE_AI_SQUAD): n самых опытных бойцов самого опытного экипажа, остальные дома")
    ap.add_argument("--label", default="arena")
    ap.add_argument("--out", default="")
    ap.add_argument("--env", action="append", default=[], metavar="K=V",
                    help="переменная окружения боя OXCE_AI_*, повторяемый: --env OXCE_AI_EVAL=1 --env OXCE_AI_EVAL_RISK=0.12")
    ap.add_argument("--strict-flags", action="store_true",
                    help="каждый флаг стенда (ai_probe.BENCH_FLAGS) обязан быть задан через --env, иначе INVALID_CONFIG")
    ap.add_argument("--expect", action="append", default=[], metavar="K=SHA",
                    help="ожидаемый отпечаток (exe, ai_probe, data, flags - как в строке fingerprint prov.txt), повторяемый:"
                         " не совпал хоть один - INVALID_CONFIG (код 3) до первого боя")
    a = ap.parse_args()
    exp = {}
    for kv in a.expect:
        k, _, v = kv.partition("=")
        if k not in FP_KEYS or not v:
            raise SystemExit(f"--expect {kv}: ключ из {', '.join(FP_KEYS)} и значение")
        exp[k] = v.lower()
    a.expect = exp
    global LABEL
    LABEL = a.label
    for kv in a.env:
        k, _, v = kv.partition("=")
        if not k.startswith("OXCE_AI_"):
            raise SystemExit(f"--env {kv}: только OXCE_AI_*")
        os.environ[k] = v  # ai_probe.run копирует окружение в процесс боя
    if a.strict_flags:
        given = {kv.partition("=")[0] for kv in a.env}
        missing = [k for k in ai_probe.BENCH_FLAGS if k not in given]
        if missing:
            print("INVALID_CONFIG: не заданы явно флаги стенда: " + " ".join(missing), flush=True)
            sys.exit(2)

    provenance(a)
    seeds = seeds_of(a.seeds)
    missions = [None]
    if a.missions:
        text = Path(a.missions[1:]).read_text(encoding=ENC_W) if a.missions.startswith("@") else a.missions.replace(",", "\n")
        missions = [m.strip() for m in text.splitlines() if m.strip() and not m.startswith("#")]
    table = ai_probe.WORK / "arena" / f"{a.label}.tsv"
    table.parent.mkdir(parents=True, exist_ok=True)
    if a.resume:
        fixed = recover(table)
        if fixed:
            print(f"восстановление серии: {fixed}", flush=True)
    else:
        table.with_suffix(".journal").unlink(missing_ok=True)
    rows = read_table(table) if a.resume else []
    played = {(r.get("want", ""), str(r["seed"])) for r in rows}
    jobs = [(m, s) for m in missions for s in seeds if (m or "", str(s)) not in played]
    if not rows:
        table.write_text("\t".join(COLS + ("outcome",)) + "\n", encoding=ENC_W)
    for slot in range(a.jobs):
        SLOTS.put(slot)
    campaign = None if a.recruits else a.campaign
    total = len(jobs) + len(rows)
    print(f"правила: враг {'опыт' if a.tactics else 'родной'}, бот {'осторожный' if a.careful else 'родной'}"
          + (f", окружение {' '.join(a.env)}" if a.env else ""), flush=True)
    print(f"боёв {len(jobs)} (уже сыграно {len(rows)}), миссий {len(missions)}, зёрен {len(seeds)}, потоков {a.jobs}", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(a.jobs) as pool:
        # по мере готовности, а не по порядку: бой, чей процесс не закрылся и ждёт таймаута, не держит запись остальных
        futures = [pool.submit(play, s, a.turns, a.diff, a.timeout, campaign, m, a.tactics, a.careful, a.squad) for m, s in jobs]
        for fut in as_completed(futures):
            row, packed = fut.result()
            rows.append(row)
            # бой в таблицу сразу: серия на часы, обрыв не должен стоить уже сыгранного. Рядом архивы: павшие
            # ([AICASUALTY] как есть), снимки юнитов на начало хода (docs/AI_TRAINING.md), решения ИИ
            # (decide - только по OXCE_AI_KEEP_DECIDE=1, сотни МБ на порцию), rec, cand, path
            commit_battle(table, row, packed)
            print(f"[{len(rows)}/{total}] зерно {row['seed']}: {outcome(row)}, {row.get('mission', '-')},"
                  f" ход {row.get('turn', '-')}, раненых {row.get('pwounded', '-')}, {row['seconds']} с", flush=True)
    lines = summary(rows, a.label) + (by_mission(rows) if a.missions else []) + [
        f"таблица: {table}", f"вся серия {time.time() - t0:.0f} с"]
    print("\n".join(lines))
    if a.out:
        Path(a.out).write_text("\n".join(lines) + "\n", encoding=ENC_W)
    return 0


if __name__ == "__main__":
    sys.exit(main())
