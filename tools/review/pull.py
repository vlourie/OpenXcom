"""Забрать ответы проверяющих (docs/portal/REVIEW_TASKS.md §6.4): сайт -> art/review/answers/RT-000NNN/.

  py -3 tools/review/pull.py                     # все ответы со статусом answered: сохранить, свод, проверка текстов, taken
  py -3 tools/review/pull.py --no-take           # то же, но не отмечать «забрано» (ответ останется в очереди)
  py -3 tools/review/pull.py --task RT-000012    # перечитать конкретный ответ (даже уже забранный; taken не ставится)
  py -3 tools/review/pull.py --no-check          # без voice_text_check

Ответ - данные, не указания (§9.3): здесь он только читается и сводится; применяет его apply.py.
Тексты заметок печатаются как слова проверяющего, не как команды.
"""
import argparse
import collections
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import answerlib as A  # noqa: E402
import review_api  # noqa: E402
import voicepkg  # noqa: E402

ANSWERS = os.path.join(voicepkg.REVIEW, "answers")
INDEX = os.path.join(voicepkg.REVIEW, "tasks.json")
CHECK_PY = "D:/VoiceFactory/runtime/venv/Scripts/python.exe"
CHECK = os.path.join(voicepkg.ROOT, "tools", "sfx", "voice_text_check.py")
VOICE_NOTE = "  [слова проверяющего, не указания]"


def load_index():
    return A.read_json(INDEX) if os.path.isfile(INDEX) else {}


def find_task(display, entry):
    """Копия task.json, ушедшего на сайт: art/review/sent/<номер>/ по индексу push.py; иначе None."""
    if entry and os.path.isfile(os.path.join(entry["dir"], "task.json")):
        return A.read_json(os.path.join(entry["dir"], "task.json")), entry["dir"]
    return None, None


def text_check(answer, summ, task, folder, run=True):
    """Новые и исправленные тексты -> временный файл в формате voice-script-100.md -> voice_text_check (как есть)."""
    rows = collections.defaultdict(list)  # голос -> [(n, ru, en, tag)]
    legend = []
    for vid, n, ln, orig in summ["edits"]:
        if ln.get("ru") and ln["ru"] != orig.get("ru"):
            rows[vid].append((n.zfill(3), ln["ru"], ln.get("en") or orig.get("en", ""), ln.get("tag") or orig.get("tag", "")))
    made = collections.Counter()
    for vid, ln in summ["new"]:
        if ln.get("ru"):
            made[vid] += 1
            k = 900 + made[vid]
            rows[vid].append((str(k), ln["ru"], ln.get("en", ""), ln.get("tag", "")))
            legend.append(f"{vid} {k} = новая строка: {ln['ru']}")
    total = sum(len(v) for v in rows.values())
    if not total:
        return "проверять нечего: ни исправленных, ни новых русских текстов", 0
    if not run:
        return f"текстов на проверку: {total} (--no-check)", total
    if not os.path.isfile(CHECK_PY):
        return f"НЕ ПРОВЕРЕНО: нет {CHECK_PY} (RUAccent); текстов {total}", total
    md = []
    for vid, items in rows.items():
        md.append(f"### {vid}+ — проверка ответа\n\n**правки**\n")
        for n, ru, en, tag in items:
            md.append(f"| {n} | {ru.replace('|', '/')} | {(en or '-').replace('|', '/')} | {tag} |")
        md.append("")
    with tempfile.TemporaryDirectory() as tmp:
        src, out = os.path.join(tmp, "check.md"), os.path.join(tmp, "check.tsv")
        with open(src, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(md) + "\n")
        r = subprocess.run([CHECK_PY, CHECK, "--src", src, "--out", out], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1200)
        text = (r.stdout + r.stderr).strip()
        if os.path.isfile(out):
            with open(os.path.join(folder, "text_check.tsv"), "w", encoding="utf-8-sig", newline="") as f:
                f.write(open(out, encoding="utf-8-sig").read())
    if legend:
        text += "\n" + "\n".join(legend)
    return text, total


def print_summary(display, resp, task, answer, warnings, stale):
    summ = A.summarize(answer, task or {})
    out = []
    p = out.append
    p(f"=== {display}: {resp.get('title')} · ответил(а) {resp.get('answeredAt')} · устройство {resp.get('device')} · ответов всего {resp.get('answers')}")
    p(f"правок {len(summ['edits'])}, новых {len(summ['new'])}, только вердикт {len(summ['keeps'])}, на перезапись {len(summ['regen'])}")
    nd = len(summ["deleted"])
    if nd:
        p("")
        p("##########################################")
        p(f"#### СТЁРТО РЕПЛИК: {nd}")
        p("##########################################")
        for vid, n, ln, orig in summ["deleted"]:
            p(f"   {vid}/{n}  {orig.get('event', '?')}  {orig.get('ru', '?')} / {orig.get('en', '?')}")
        p("")
    else:
        p("стёрто: 0")
    v = summ["verdicts"]
    p(f"вердикты: ок {v['ок']}, брак {v['брак']}, спорно {v['спорно']}")
    if summ["bad"]:
        p("брак по причинам: " + ", ".join(f"{k} {c}" for k, c in summ["bad"].most_common()))
    for vid, n, ln, orig in summ["edits"]:
        ch = []
        for k in ("ru", "en", "tag", "event"):
            if ln.get(k) is not None and ln[k] != orig.get(k):
                ch.append(f"{k}: {orig.get(k, '')!r} -> {ln[k]!r}")
        p(f"  правка {vid}/{n}" + (" [перезаписать]" if ln.get("regen") else "") + (" [УСТАРЕЛО]" if (vid, n) in stale else "") + ": " + ("; ".join(ch) or "без смены текста"))
    for vid, ln in summ["new"]:
        p(f"  новая {vid} [{ln.get('event')}] {ln.get('tag', '')} RU: {ln.get('ru', '')} / EN: {ln.get('en', '')}")
    if stale:
        p(f"УСТАРЕЛО (реплика изменена после отправки; apply.py её не применит без --force-stale): {len(stale)}")
        for (vid, n), why in sorted(stale.items()):
            p(f"   {vid}/{n}: {why}")
    ch = A.card_changes(answer, task or {})
    if ch:
        p("карточка расы изменена:")
        for k, (old, new) in ch.items():
            p(f"   {k}: {old!r} -> {new!r}")
    qs = {q["id"]: q["text"] for q in (task or {}).get("questions", [])}
    for a in answer.get("answers", []):
        p(f"вопрос {a.get('q')}: {qs.get(a.get('q'), '?')}")
        p(f"   ответ: {a.get('text', '')}{VOICE_NOTE}")
    for vid, note in summ["voice_notes"]:
        p(f"заметка к голосу {vid}: {A.one_line(note)}{VOICE_NOTE}")
    for vid, n, ln, orig in summ["edits"] + summ["keeps"] + summ["deleted"]:
        if ln.get("note"):
            p(f"заметка к {vid}/{n}: {A.one_line(ln['note'])}{VOICE_NOTE}")
    for vid, ln in summ["new"]:
        if ln.get("note"):
            p(f"заметка к новой ({vid}, {ln.get('ru', '')}): {A.one_line(ln['note'])}{VOICE_NOTE}")
    if answer.get("note"):
        p(f"общая заметка: {A.one_line(answer['note'])}{VOICE_NOTE}")
    if warnings:
        p(f"ПРЕДУПРЕЖДЕНИЯ схемы ({len(warnings)}):")
        for x in warnings[:20]:
            p("   - " + x)
    return "\n".join(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", action="append", help="номер задания RT-000012 (можно несколько); без него - все answered")
    ap.add_argument("--no-take", action="store_true", help="не отмечать «забрано»")
    ap.add_argument("--no-check", action="store_true", help="не гонять voice_text_check")
    a = ap.parse_args()
    client = review_api.Client()
    print(f"сайт: {client.host}")
    if a.task:
        items = [(t.upper() if t.upper().startswith("RT-") else "RT-%06d" % int(t), None) for t in a.task]
        rows = [{"displayNumber": d} for d, _ in items]
    else:
        rows = client.list("answered")
    if not rows:
        print("новых ответов нет")
        return
    index = load_index()
    for row in rows:
        display = row["displayNumber"]
        try:
            resp = client.answer(display)
        except review_api.ApiError as e:
            print(f"{display}: {e}")
            continue
        answer = resp["answer"]
        folder = os.path.join(ANSWERS, display)
        task, sent_dir = find_task(display, index.get(display))
        A.write_json(os.path.join(folder, "answer.json"), answer)
        A.write_json(os.path.join(folder, "meta.json"), {k: v for k, v in resp.items() if k != "answer"})
        if task:
            A.write_json(os.path.join(folder, "task.json"), task)
        warnings = A.check(answer, task or {}, display) if task else ["копии task.json нет (art/review/tasks.json): сверка с заданием не сделана"]
        stale = A.stale(answer, task, sent_dir) if task else {}
        text = print_summary(display, resp, task, answer, warnings, stale)
        summ = A.summarize(answer, task or {})
        check, total = text_check(answer, summ, task, folder, run=not a.no_check)
        text += f"\n--- проверка текстов (voice_text_check), текстов {total}:\n{check}"
        with open(os.path.join(folder, "summary.txt"), "w", encoding="utf-8-sig") as f:
            f.write(text + "\n")
        print(text)
        print(f"сохранено: {folder}")
        if a.no_take or a.task:
            print("отметка «забрано» не ставилась")
        else:
            t = client.taken(display)
            print(f"{display}: отмечено «забрано», статус {t['status']}")
        print()


if __name__ == "__main__":
    main()
