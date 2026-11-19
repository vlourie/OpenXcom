"""Данные пилота вкладки «Задания» лаунчера: голоса одной расы, как они сейчас в игре.

Собирает для голосов расы карточку (замысел, «для кого», «по игре», «как играть»), реплики
(номер, событие, подача, RU, EN) и ogg из установленных модов hd_voices_ru / hd_voices_en.
Пишет task.json и audio.js (ogg в base64) в папку пилота. Установку игры только читает.

  py -3 tools/review/pilot_voices.py --voices V019,V020 --race Ламия --out art/review/pilot_lamia
"""
import argparse, base64, glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voicepkg  # общий сборщик пакета (его же берёт push.py)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voices", required=True)
    ap.add_argument("--race", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    want = a.voices.split(",")
    os.makedirs(a.out, exist_ok=True)

    voices, files = voicepkg.build_voices(want)
    audio = {pkg[:-4]: base64.b64encode(open(path, "rb").read()).decode("ascii") for pkg, path in files}

    task = {"schema": 1, "kind": "voice.race", "race": a.race, "voices": voices}
    with open(os.path.join(a.out, "task.json"), "w", encoding="utf-8-sig") as f:
        json.dump(task, f, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "task.js"), "w", encoding="utf-8") as f:
        f.write("window.TASK=" + json.dumps(task, ensure_ascii=False) + ";\n")
    with open(os.path.join(a.out, "audio.js"), "w", encoding="utf-8") as f:
        f.write("window.AUDIO=" + json.dumps(audio) + ";\n")
    n = sum(len(v["lines"]) for v in voices)
    miss = sum(1 for v in voices for r in v["lines"] if not r["has_ru"])
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{a.race}: голосов {len(voices)}, реплик {n}, без ogg RU {miss}, файлов звука {len(audio)}, "
          f"audio.js {os.path.getsize(os.path.join(a.out, 'audio.js')) // 1024} КБ")


if __name__ == "__main__":
    main()
