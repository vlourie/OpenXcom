"""Задания писателям «сотни» (docs/research/voice-direction.md): карточка голоса, его записанные реплики по событиям,
сколько дописать до 55 выбора + 50 движения, с какого номера.

    py -3 tools/sfx/voice_more_batches.py [--per 10]
-> art/sfx/voicepack/more/in_NN.md (национальные пары - в одном задании), сводка.
Готовые блоки пилота (docs/research/voice-script-100.md) в задания не идут.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voice_script                              # noqa: E402
import voicepack_events as E                     # noqa: E402
from voice_text_check import parse100            # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "art/sfx/voicepack/more"
SELECT, MOVE = 55, 50


def card(v):
    ev = {ln["n"]: E.classify(v, ln)[0] for ln in v["lines"]}
    sel = sum(e == "select" for e in ev.values())
    mov = sum(e == "move" for e in ev.values())
    start = max(int(ln["n"]) for ln in v["lines"]) + 1
    need_s, need_m = max(0, SELECT - sel), max(0, MOVE - mov)
    out = [f"## {v['id']} — {v['name']} [{v['reg']}]", "",
           f"Раздел: {v['section']}", f"Для кого: {v.get('for', '')}", f"По игре: {v.get('game', '')}",
           f"Как играть голосом: {v.get('direction', '')}", "",
           f"**Дописать: выбор {need_s} (номера {start:03d}-{start + need_s - 1:03d}), движение {need_m} "
           f"(номера {start + need_s:03d}-{start + need_s + need_m - 1:03d}).**", "",
           "Уже записано (не повторять):", ""]
    for ln in v["lines"]:
        out.append(f"- {ln['n']} [{E.WORD[ev[ln['n']]]}] {ln['ru']} / {ln['en']}")
    return "\n".join(out) + "\n", need_s + need_m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=10)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    done = set(parse100())
    voices = [v for v in voice_script.parse() if v["id"] not in done]
    # национальная пара - одним куском (мужской и женский идут подряд)
    groups, i = [], 0
    while i < len(voices):
        v = voices[i]
        if v["section"].startswith("Национальные") and i + 1 < len(voices) and \
                voices[i + 1]["name"].split(":")[0] == v["name"].split(":")[0]:
            groups.append([v, voices[i + 1]])
            i += 2
        else:
            groups.append([v])
            i += 1
    batches, cur = [], []
    for g in groups:
        if cur and len(cur) + len(g) > a.per:
            batches.append(cur)
            cur = []
        cur += g
    if cur:
        batches.append(cur)
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for k, b in enumerate(batches, 1):
        parts, n = [], 0
        for v in b:
            text, need = card(v)
            parts.append(text)
            n += need
        total += n
        (OUT / f"in_{k:02d}.md").write_text(f"# Задание {k:02d}: {len(b)} голосов, {n} реплик\n\n" + "\n".join(parts),
                                            encoding="utf-8-sig")
        print(f"in_{k:02d}: {len(b)} голосов, {n} реплик ({b[0]['id']}..{b[-1]['id']})")
    print(f"заданий {len(batches)}, голосов {len(voices)}, реплик {total}")


if __name__ == "__main__":
    main()
