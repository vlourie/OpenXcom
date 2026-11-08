"""Отправить на сайт задание «голоса расы» (voice.race): docs/portal/REVIEW_TASKS.md §3, §6, §10.

  py -3 tools/review/push.py --list                              # расы: голосов, реплик, ogg, МБ, порядок
  py -3 tools/review/push.py --race Ламия --assignee MuRuCoN --dry-run   # собрать пакет в art/review/out/Ламия/
  py -3 tools/review/push.py --race Ламия --assignee MuRuCoN     # создать задание, доложить файлы, send
  py -3 tools/review/push.py --all --assignee MuRuCoN            # все расы по порядку (с паузой)

Ключ и адрес - review_api.py (XP_REVIEW_BOT_KEY / ~/.xp-portal/review_bot.json). Повтор той же команды ничего не
дублирует: Idempotency-Key устойчив от (раса, назначенный, хэш пакета), готовые файлы не шлются (сверка по sha256).
Номера отправленных заданий - art/review/tasks.json (по нему pull.py находит расу), а то, что ушло, лежит
неизменным в art/review/sent/RT-000NNN/ (task.json и files.tsv с sha256 ogg).
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voicepkg  # noqa: E402
import review_api  # noqa: E402

OUT = os.path.join(voicepkg.REVIEW, "out")
INDEX = os.path.join(voicepkg.REVIEW, "tasks.json")


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def load_index():
    if os.path.isfile(INDEX):
        return json.load(open(INDEX, encoding="utf-8-sig"))
    return {}


def race_order():
    """Расы от самых многоголосых к редким (ТЗ §11), при равенстве - по числу реплик, потом по имени."""
    ev = voicepkg.read_events()
    out = []
    for race, vids in voicepkg.races().items():
        out.append((race, vids, sum(len(ev.get(v, [])) for v in vids)))
    out.sort(key=lambda r: (-len(r[1]), -r[2], r[0]))
    return out


def cmd_list():
    print(f"{'№':>3} {'раса':<24} {'голосов':>7} {'реплик':>6} {'ogg':>6} {'МБ':>6}  замечания")
    tot = [0, 0, 0, 0]
    for i, (race, vids, lines) in enumerate(race_order(), 1):
        task, files, _ = voicepkg.build_task(race, vids)
        mb = sum(os.path.getsize(p) for _, p in files) / 1048576
        bad = voicepkg.validate(task, files)
        print(f"{i:>3} {race:<24} {len(vids):>7} {lines:>6} {len(files):>6} {mb:>6.1f}  {'; '.join(bad[:2])}{' ...' if len(bad) > 2 else ''}")
        for k, v in enumerate((len(vids), lines, len(files), mb)):
            tot[k] += v
    print(f"    {'итого':<24} {tot[0]:>7} {tot[1]:>6} {tot[2]:>6} {tot[3]:>6.0f}")


def stable_key(race, assignee, pkg_hash):
    return "rt-" + hashlib.sha256(f"{race}|{assignee.lower()}|{pkg_hash}".encode("utf-8")).hexdigest()[:40]


def pick_vids(a, races_map):
    if a.voices:
        want = [v.strip() for v in a.voices.split(",") if v.strip()]
        known = {v for vs in races_map.values() for v in vs}
        unknown = [v for v in want if v not in known]
        if unknown:
            review_api.die("нет голосов: " + ", ".join(unknown))
        race = a.race or voicepkg.race_of(voicepkg.voice_json(want[0])["name"])
        return race, want
    if a.race not in races_map:
        review_api.die(f"нет расы {a.race!r}; список: push.py --list")
    return a.race, races_map[a.race]


def load_json_arg(path, what):
    try:
        return json.load(open(path, encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        review_api.die(f"{what} {path}: {e}")


def prepare(a, race, vids):
    """Собрать пакет расы и записать его в art/review/out/<раса>/. Возвращает (task, files, hashes, problems, dir)."""
    card_override = load_json_arg(a.card, "--card") if a.card else None
    questions = load_json_arg(a.questions, "--questions") if a.questions else None
    task, files, _ = voicepkg.build_task(race, vids, card_override, questions, a.card_version)
    bad = voicepkg.validate(task, files)
    hashes = {pkg: voicepkg.sha256_file(p) for pkg, p in files}
    folder = os.path.join(OUT, race)
    write_json(os.path.join(folder, "task.json"), task)
    with open(os.path.join(folder, "files.tsv"), "w", encoding="utf-8-sig", newline="\n") as f:
        f.write("path\tsha256\tsize\n")
        for pkg, p in files:
            f.write(f"{pkg}\t{hashes[pkg]}\t{os.path.getsize(p)}\n")
    return task, files, hashes, bad, folder


def summary(race, task, files):
    lines = sum(len(v["lines"]) for v in task["voices"])
    nogame = sum(1 for v in task["voices"] for r in v["lines"] if r.get("in_game") is False)
    mb = sum(os.path.getsize(p) for _, p in files) / 1048576
    return (f"{race}: голосов {len(task['voices'])}, реплик {lines} (не в игре {nogame}), ogg {len(files)} ({mb:.1f} МБ), "
            f"карточка v{task['card_version']}, вопросов {len(task.get('questions', []))}")


def upload(client, number, files, hashes, workers):
    remote = {f["path"]: f["sha256"] for f in client.get(number)["files"]}
    todo = [(pkg, p) for pkg, p in files if remote.get(pkg) != hashes[pkg]]
    print(f"  файлов на сайте {len(remote)}, доложить {len(todo)}")
    if not todo:
        return
    done, step, failed = 0, max(1, len(todo) // 10), []

    def one(item):
        pkg, p = item
        with open(p, "rb") as f:
            client.put_file(number, pkg, f.read(), hashes[pkg])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(one, it): it for it in todo}
        for fut in as_completed(futs):
            try:
                fut.result()
            except review_api.ApiError as e:
                failed.append((futs[fut][0], str(e)))
            done += 1
            if done % step == 0 or done == len(todo):
                print(f"  загружено {done}/{len(todo)}")
    if failed:
        for pkg, err in failed[:5]:
            print(f"  ОШИБКА {pkg}: {err}")
        review_api.die(f"не доложено файлов: {len(failed)}")


def send(client, number, wait, tries):
    for i in range(tries):
        try:
            t = client.send(number)
            return t
        except review_api.ApiError as e:
            if e.status == 409 and e.code == "files_pending" and i + 1 < tries:
                print(f"  проверка файлов не закончилась, повтор через {wait} с ({i + 1}/{tries})")
                time.sleep(wait)
                continue
            raise
    return None


def push_race(a, client, race, vids):
    task, files, hashes, bad, folder = prepare(a, race, vids)
    print(summary(race, task, files))
    if not any(v["lines"] for v in task["voices"]):
        print("  пропуск: у голосов расы нет реплик (проверять нечего)")
        return True
    if bad:
        print(f"  НЕЛЬЗЯ слать, пределы сайта ({len(bad)}):")
        for b in bad[:8]:
            print("   -", b)
        return False
    if a.dry_run:
        pkg_dir = os.path.join(folder, "files")
        if os.path.isdir(pkg_dir):
            shutil.rmtree(pkg_dir)
        for pkg, p in files:
            dst = os.path.join(pkg_dir, *pkg.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(p, dst)
        print(f"  пакет собран: {folder}")
        return True
    pkg_hash = voicepkg.package_hash(task, hashes)
    key = stable_key(race, a.assignee, pkg_hash)
    payload = {"assignee": a.assignee, "title": a.title or race, "adult": bool(a.adult), "task": task}
    if a.due:
        payload["due"] = a.due if "T" in a.due else a.due + "T00:00:00Z"
    status, t = client.create(payload, key)
    number = t["number"]
    print(f"  {t['displayNumber']}: {'создано' if status == 201 else 'уже было'}, статус {t['status']}, назначен {t['assignee']}")
    # неизменная копия того, что ушло: по ней pull/apply сверяют ответ (папка out/<раса> перезаписывается новой сборкой)
    sent = os.path.join(voicepkg.REVIEW, "sent", t["displayNumber"])
    os.makedirs(sent, exist_ok=True)
    for name in ("task.json", "files.tsv"):
        shutil.copyfile(os.path.join(folder, name), os.path.join(sent, name))
    index = load_index()
    index[t["displayNumber"]] = {"number": number, "race": race, "dir": sent, "assignee": a.assignee,
                                 "title": t["title"], "adult": bool(a.adult), "card_version": task["card_version"],
                                 "key": key, "pushed": time.strftime("%Y-%m-%d %H:%M:%S")}
    write_json(INDEX, index)
    if t["status"] != "draft":
        print(f"  уже не черновик ({t['status']}): файлы и send не нужны")
        return t["status"] != "revoked"
    upload(client, number, files, hashes, a.workers)
    t = send(client, number, a.wait, a.tries)
    print(f"  send: статус {t['status']}, файлов на сайте {len(t['files'])}")
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="расы: голоса, реплики, ogg, МБ, порядок отправки")
    ap.add_argument("--race", help="раса: часть имени голоса до двоеточия")
    ap.add_argument("--voices", help="или голоса через запятую: V019,V020 (раса - у первого, если не задана --race)")
    ap.add_argument("--all", action="store_true", help="все расы по порядку --list")
    ap.add_argument("--assignee", help="имя аккаунта назначенного (нужно право review.tasks)")
    ap.add_argument("--adult", action="store_true", help="пометка 18+ (назначенному нужна галка review.adult)")
    ap.add_argument("--title", help="заголовок задания (по умолчанию - раса)")
    ap.add_argument("--due", help="срок: 2026-11-20")
    ap.add_argument("--card", help="JSON с полями карточки расы (mood, accent, palette, taboo) поверх подставленных")
    ap.add_argument("--card-version", type=int, help="версия карточки (по умолчанию - из art/review/cards/<раса>.json или 1)")
    ap.add_argument("--questions", help="JSON: список {id, text}")
    ap.add_argument("--revoke", metavar="RT-000012", help="отозвать задание (из любого статуса, кроме closed) и выйти")
    ap.add_argument("--dry-run", action="store_true", help="только собрать пакет в art/review/out/<раса>/, на сайт не ходить")
    ap.add_argument("--workers", type=int, default=8, help="параллельных загрузок файлов")
    ap.add_argument("--wait", type=int, default=5, help="пауза между повторами send при files_pending, с")
    ap.add_argument("--tries", type=int, default=60, help="сколько раз повторять send при files_pending")
    ap.add_argument("--pause", type=int, default=3, help="пауза между заданиями при --all, с")
    ap.add_argument("--limit", type=int, default=0, help="при --all - первые N рас")
    a = ap.parse_args()

    if a.list:
        return cmd_list()
    if a.revoke:
        t = review_api.Client().revoke(a.revoke)
        print(f"{t['displayNumber']}: статус {t['status']}")
        return
    if not (a.race or a.voices or a.all):
        ap.error("нужно --list, --race, --voices или --all")
    if not a.dry_run and not a.assignee:
        ap.error("нужен --assignee (или --dry-run)")
    client = None
    if not a.dry_run:
        client = review_api.Client()
        print(f"сайт: {client.host}")
    races_map = voicepkg.races()
    if a.all:
        order = [(r, v) for r, v, _ in race_order()]
        if a.limit:
            order = order[: a.limit]
    else:
        order = [pick_vids(a, races_map)]
    ok = fail = 0
    for i, (race, vids) in enumerate(order):
        if i and not a.dry_run:
            time.sleep(a.pause)
        try:
            good = push_race(a, client, race, vids)
        except review_api.ApiError as e:
            print(f"  ОШИБКА {race}: {e}")
            good = False
            if not a.all:
                sys.exit(1)
        ok += bool(good)
        fail += not good
    if a.all:
        print(f"итого: готово {ok}, не отправлено {fail}")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
