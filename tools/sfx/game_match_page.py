"""Страница прослушивания: голоса игры рядом с нашими (Vitali 21.10: «подобрать такие же или максимально похожие»).

    py -3 tools/sfx/game_match_page.py
-> art/sfx/voicepack/game_match/index.html; клипы игры копируются в game_match/game/ (установка - только чтение).
Группы и клипы - из game_voice_match.GROUPS и art/sfx/voicepack/game_clips.tsv.
"""
import csv
import html
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from game_voice_match import CLIPS, GROUPS, speech   # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
VP = ROOT / "art/sfx/voicepack"
SND = ROOT / "Пиратки/Dioxine_XPiratez/user/mods/Piratez/Resources/Sounds"
OUT = VP / "game_match"
OURS_EN = 4                                      # английских реплик нашего голоса на карточке


def audio(src, text, cls=""):
    return (f'<div class="clip {cls}"><audio controls preload="none" src="{html.escape(src)}"></audio>'
            f'<span>{html.escape(text)}</span></div>')


def ours(vid):
    st = json.loads((VP / vid / "voice.json").read_text(encoding="utf-8-sig"))
    out = [f'<h4>{vid} — {html.escape(st["name"])}</h4>']
    if st.get("ref"):
        out.append(audio(f"../{st['ref']}", "опорный: " + st.get("ref_text", ""), "ref"))
    en = [it for it in st["lines"] if it.get("chosen") and it["lang"] == "en"][:OURS_EN]
    out += [audio(f"../{it['file']}", it["text"]) for it in en]
    return "".join(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    clips = {}
    with open(CLIPS, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            clips.setdefault(r["dir"], []).append(r)
    body, n = [], 0
    for title, dirs, vids in GROUPS:
        game = []
        for d in dirs:
            for r in clips.get(d, []):
                dst = OUT / "game" / d / r["file"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    shutil.copy2(SND / d / r["file"], dst)
                rel = "game/" + d + "/" + r["file"]
                game.append(audio(rel, f'{r["heard"]}  ({r["dur"]} с, {r["file"]})',
                                  "" if speech(r["heard"]) else "noise"))
                n += 1
        body.append(f'<section><h2>{html.escape(title)}</h2><div class="cols"><div><h3>В игре</h3>{"".join(game)}</div>'
                    f'<div><h3>Наши голоса</h3>{"".join(ours(v) for v in vids)}</div></div></section>')
    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Голоса игры и наши</title>
<style>
:root {{ --bg:#fff; --fg:#1d1d1f; --mute:#6b6b70; --line:#e2e2e6; --ref:#eef4ff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#17171a; --fg:#ececf0; --mute:#9a9aa3; --line:#2c2c31; --ref:#1d2636; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, sans-serif; margin:0 auto; max-width:1200px; padding:16px; }}
h1 {{ font-size:22px; }} h2 {{ font-size:18px; border-top:1px solid var(--line); padding-top:16px; }}
h3 {{ font-size:14px; color:var(--mute); text-transform:uppercase; letter-spacing:.04em; }} h4 {{ margin:14px 0 4px; }}
.cols {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; }}
@media (max-width:760px) {{ .cols {{ grid-template-columns:1fr; }} }}
.clip {{ display:flex; align-items:center; gap:8px; margin:3px 0; }} .clip audio {{ height:30px; flex:0 0 220px; max-width:55%; }}
.clip span {{ font-size:13px; }} .ref {{ background:var(--ref); border-radius:6px; padding:2px 4px; }}
.noise span {{ color:var(--mute); font-style:italic; }}
</style></head><body>
<h1>Голоса игры и наши голоса</h1>
<p>Слева — английские клипы Пираток для этого типа бойца (паника, берсерк, смерть, отклики), серым — крики и звуки
без слов. Справа — наш опорный клип и английские реплики. Отметьте, где голос надо сделать таким же или похожим.</p>
{"".join(body)}
</body></html>"""
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print("клипов игры", n, "->", OUT / "index.html")


if __name__ == "__main__":
    main()
