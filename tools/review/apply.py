"""Подготовить работу по ответу проверяющего (docs/portal/REVIEW_TASKS.md §6.4, §9.3). Генерацию НЕ запускает,
voice.json и игру не трогает.

  py -3 tools/review/apply.py RT-000012            # по art/review/answers/RT-000012/answer.json
  py -3 tools/review/apply.py --all                # все ответы, к которым apply ещё не применялся
  py -3 tools/review/apply.py RT-000012 --dry-run  # только показать, что будет записано
  py -3 tools/review/apply.py RT-000012 --force-stale   # применить и устаревшие правки (по умолчанию пропускаются)

Что пишет:
  art/review/excluded.tsv          стёртые проверяющим реплики (voice, n, task, date); читает build_voicepack_mods.py,
                                   ogg в art/sfx/voicepack остаются; вернуть реплику - удалить строку
  art/review/regen/RT-000012.tsv   очередь перегенерации: правки, «перезаписать» и новые строки (voice, n|new, event, ru, en, tag, note)
  art/review/cards/<раса>.json     карточка расы новой версией; следующий push.py возьмёт её сам
  art/review/answers/RT-000012/applied.json   что применено
Заметки проверяющего никуда не применяются: это слова, не команды.
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import answerlib as A  # noqa: E402
import voicepkg  # noqa: E402

REVIEW = voicepkg.REVIEW
ANSWERS = os.path.join(REVIEW, "answers")
EXCLUDED = os.path.join(REVIEW, "excluded.tsv")
REGEN = os.path.join(REVIEW, "regen")


def read_excluded():
    rows = []
    if os.path.isfile(EXCLUDED):
        for line in open(EXCLUDED, encoding="utf-8-sig").read().splitlines()[1:]:
            if line.strip():
                rows.append(line.split("\t"))
    return rows


def cell(s):
    return A.one_line(str(s if s is not None else "")).replace("\t", " ")


def apply_one(display, force_stale, dry):
    folder = os.path.join(ANSWERS, display)
    ap = os.path.join(folder, "answer.json")
    if not os.path.isfile(ap):
        print(f"{display}: нет {ap} (сначала pull.py)")
        return False
    answer = A.read_json(ap)
    tp = os.path.join(folder, "task.json")
    if not os.path.isfile(tp):
        print(f"{display}: нет копии task.json: применять нечего без исходных текстов")
        return False
    task = A.read_json(tp)
    done_p = os.path.join(folder, "applied.json")
    prev = A.read_json(done_p) if os.path.isfile(done_p) else {}
    sent_dir = os.path.join(REVIEW, "sent", display)
    warnings = A.check(answer, task, display)
    stale = A.stale(answer, task, sent_dir)
    summ = A.summarize(answer, task)
    today = datetime.date.today().isoformat()
    print(f"=== {display} ({task.get('race')}): правок {len(summ['edits'])}, стёрто {len(summ['deleted'])}, "
          f"новых {len(summ['new'])}, на перезапись {len(summ['regen'])}, предупреждений {len(warnings)}")
    for x in warnings[:10]:
        print("   ! " + x)

    skipped = []

    def ok(vid, n):
        if (vid, n) in stale and not force_stale:
            skipped.append(f"{vid}/{n}: {stale[(vid, n)]}")
            return False
        return True

    # (а) стёртое -> excluded.tsv
    have = {(r[0], r[1]) for r in read_excluded()}
    add_ex = []
    for vid, n, ln, orig in summ["deleted"]:
        if ok(vid, n) and (vid, n) not in have:
            add_ex.append((vid, n, display, today))
            have.add((vid, n))

    # (б) очередь перегенерации
    regen, seen = [], set()
    deleted = {(vid, n) for vid, n, _, _ in summ["deleted"]}
    for vid, n, ln, orig in summ["edits"] + summ["keeps"]:
        if (vid, n) in deleted or (vid, n) in seen:
            continue
        wants = ln.get("op") == "edit" or ln.get("regen")
        if not wants or not ok(vid, n):
            continue
        seen.add((vid, n))
        why = "; ".join(x for x in (ln.get("verdict"), ln.get("reason")) if x)
        note = " | ".join(x for x in (why, ln.get("note")) if x)
        regen.append((vid, n, ln.get("event") or orig.get("event"), ln.get("ru") or orig.get("ru"),
                      ln.get("en") or orig.get("en"), ln.get("tag") if ln.get("tag") is not None else orig.get("tag"), note))
    for vid, ln in summ["new"]:
        regen.append((vid, "new", ln.get("event"), ln.get("ru"), ln.get("en"), ln.get("tag"), ln.get("note")))

    # (в) карточка расы
    changes = A.card_changes(answer, task)
    card_out = None
    if changes and not prev.get("card_version"):
        race = task.get("race")
        saved = voicepkg.saved_card(race)
        base = (saved or {}).get("card") or task.get("card") or {}
        version = ((saved or {}).get("version") or task.get("card_version") or 1) + 1
        card_out = {"race": race, "version": version, "task": display, "date": today,
                    "card": {**base, **{k: new for k, (_, new) in changes.items()}},
                    "history": ((saved or {}).get("history") or []) + [{"version": version, "task": display, "date": today,
                                                                           "changed": sorted(changes)}]}

    print(f"  excluded.tsv: +{len(add_ex)}   regen: {len(regen)} строк (из них новых {len(summ['new'])})   "
          f"карточка: {('v%d, поля %s' % (card_out['version'], ', '.join(sorted(changes)))) if card_out else 'без изменений'}")
    if skipped:
        print(f"  ПРОПУЩЕНО устаревших правок: {len(skipped)} (--force-stale, если уверены)")
        for s in skipped[:10]:
            print("   - " + s)
    if dry:
        print("  --dry-run: ничего не записано")
        return True

    if add_ex:
        new = not os.path.isfile(EXCLUDED)
        os.makedirs(REVIEW, exist_ok=True)
        with open(EXCLUDED, "w" if new else "a", encoding="utf-8-sig" if new else "utf-8", newline="\n") as f:
            if new:
                f.write("voice\tn\ttask\tdate\n")
            for r in add_ex:
                f.write("\t".join(r) + "\n")
    if regen:
        os.makedirs(REGEN, exist_ok=True)
        with open(os.path.join(REGEN, display + ".tsv"), "w", encoding="utf-8-sig", newline="\n") as f:
            f.write("voice\tn\tevent\tru\ten\ttag\tnote\n")
            for r in regen:
                f.write("\t".join(cell(x) for x in r) + "\n")
    if card_out:
        A.write_json(voicepkg.card_file(card_out["race"]), card_out)
    A.write_json(done_p, {"date": today, "excluded": [list(r[:2]) for r in add_ex], "regen": len(regen),
                          "skipped_stale": skipped, "card_version": card_out["version"] if card_out else prev.get("card_version")})
    print(f"  записано; номера новым репликам выдаёт генерация; voice.json и игру не трогали")
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task", nargs="*", help="номера заданий RT-000012")
    ap.add_argument("--all", action="store_true", help="все ответы без applied.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-stale", action="store_true")
    a = ap.parse_args()
    names = [t.upper() for t in a.task]
    if a.all and os.path.isdir(ANSWERS):
        names += [d for d in sorted(os.listdir(ANSWERS)) if not os.path.isfile(os.path.join(ANSWERS, d, "applied.json"))]
    if not names:
        ap.error("нужен номер задания или --all")
    fine = all([apply_one(n, a.force_stale, a.dry_run) for n in names])
    sys.exit(0 if fine else 1)


if __name__ == "__main__":
    main()
