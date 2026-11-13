"""Страница прослушивания полного набора голосов: art/sfx/voicepack/listen.html (рядом с файлами, ссылки
относительные - открывать обычным браузером). Модели не грузит, можно запускать во время генерации:
готовые голоса видны, остальные помечены «в работе».

    py -3 tools/sfx/voicepack_page.py
"""
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voice_script                              # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "art/sfx/voicepack"
REG = {"Ж": "жен.", "М": "муж.", "Н": "нечел."}

CSS = """
:root{--bg:#14161a;--fg:#e6e6e6;--mut:#8b93a1;--card:#1d2026;--line:#2b2f37;--ok:#4caf7a;--warn:#e0a84a;--bad:#e06a5a}
@media (prefers-color-scheme: light){:root{--bg:#f6f6f4;--fg:#1d1f22;--mut:#5f6670;--card:#fff;--line:#e2e2de}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px}
h1{font-size:22px;margin:0 0 4px} h2{font-size:18px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
.sum{color:var(--mut);margin-bottom:12px} nav{display:flex;flex-wrap:wrap;gap:4px 14px} nav a{color:var(--mut)}
.v{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:10px 0}
.v h3{font-size:15px;margin:0 0 4px} .meta{color:var(--mut);font-size:12.5px;margin:2px 0}
table{border-collapse:collapse;width:100%;margin-top:6px} td{border-top:1px solid var(--line);padding:4px 6px;vertical-align:middle}
td.n{color:var(--mut);width:28px} audio{height:28px;width:220px;max-width:100%}
.b{font-size:11.5px;border-radius:4px;padding:0 4px;margin-left:4px;white-space:nowrap}
.ok{color:var(--ok)} .warn{color:var(--warn)} .bad{color:var(--bad)}
details{margin-top:4px;color:var(--mut)} .wip{color:var(--warn)}
@media (max-width:700px){td{display:block;border-top:none} tr{display:block;border-top:1px solid var(--line);padding:4px 0}}
"""


def badge(it):
    out = []
    if not it.get("band", True):
        out.append(f'<span class="b bad">{it["f0"]:.0f} Гц вне полосы</span>')
    else:
        out.append(f'<span class="b ok">{it.get("f0", 0):.0f} Гц</span>')
    c = it.get("close")
    if c is not None and c < 0.75:
        out.append(f'<span class="b warn" title="{html.escape(it.get("heard", ""))}">слышно {c:.2f}</span>')
    if it.get("dur", 0) > 3.0:
        out.append(f'<span class="b warn">{it["dur"]} с</span>')
    return "".join(out)


def audio(f):
    return f'<audio controls preload="none" src="{html.escape(f)}"></audio>'


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    voices = voice_script.parse(more=voice_script.MORE100, only=voice_script.pinned())
    audit_path = OUT / 'audit.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8-sig')) if audit_path.exists() else None
    approved = {(r['voice'], r['lang'], r['line']): r['file'] for r in audit['selected']} if audit else None
    sections = []
    for v in voices:
        if not sections or sections[-1][0] != v["section"]:
            sections.append((v["section"], []))
        sections[-1][1].append(v)
    done = lines = 0
    body = []
    for si, (sec, vs) in enumerate(sections):
        body.append(f'<h2 id="s{si}">{html.escape(sec)}</h2>')
        for v in vs:
            p = OUT / v["id"] / "voice.json"
            st = json.load(open(p, encoding="utf-8-sig")) if p.exists() else None
            ready = bool(st and st.get("asr_done"))
            done += ready
            head = (f'<h3>{v["id"]} — {html.escape(v["name"])} <span class="meta">[{REG[v["reg"]]}]</span>'
                    + ("" if ready else ' <span class="wip">в работе</span>') + "</h3>")
            meta = (f'<div class="meta"><b>Для кого:</b> {html.escape(v["for"])}</div>'
                    f'<div class="meta"><b>Голосом:</b> {html.escape(v["direction"])}</div>')
            if not ready:
                body.append(f'<div class="v">{head}{meta}</div>')
                continue
            ref = (f'<div class="meta">Образец голоса ({st["ref_f0"]:.0f} Гц'
                   + (f', сдвиг {st["ref_shift"]:+.1f} пт' if st.get("ref_shift") else "")
                   + f'): {audio(st["ref"])}</div>')
            if approved is None:
                chosen = {(it['lang'], it['n']): it for it in st['lines'] if it.get('chosen')}
            else:
                chosen = {(it['lang'], it['n']): it for it in st['lines'] if 'file' in it
                          and approved.get((v['id'], it['lang'], it['n'])) == it['file']}
            rows = []
            for ln in v["lines"]:
                cells = [f'<td class="n">{ln["n"]}</td>']
                for lang in ("ru", "en"):
                    it = chosen.get((lang, ln["n"]))
                    if it:
                        lines += 1
                        alts = [x for x in st["lines"] if x["lang"] == lang and x["n"] == ln["n"]
                                and "file" in x and x['file'] != it['file']]
                        alt = ("<details><summary>другие дубли</summary>"
                               + "".join(f'<div>{audio(x["file"])}{badge(x)}</div>' for x in alts)
                               + "</details>") if alts else ""
                        cells.append(f'<td>{audio(it["file"])}{badge(it)}<div>{html.escape(ln[lang])}</div>{alt}</td>')
                    else:
                        cells.append(f'<td class="bad">не включено после проверки — {html.escape(ln[lang])}</td>')
                rows.append("<tr>" + "".join(cells) + "</tr>")
            body.append(f'<div class="v">{head}{meta}{ref}<table>{"".join(rows)}</table></div>')
    nav = "".join(f'<a href="#s{i}">{html.escape(s)}</a>' for i, (s, _) in enumerate(sections))
    page = (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>Голоса Пираток</title>'
            f'<style>{CSS}</style></head><body><h1>Голоса Пираток — сценарий RU / EN</h1>'
            f'<div class="sum">Готово голосов: {done} из {len(voices)}, реплик: {lines}. Высота — медиана тона; '
            f'«слышно» — сходство распознанного с текстом (наведи — что услышано).</div><nav>{nav}</nav>'
            + "".join(body) + "</body></html>")
    (OUT / "listen.html").write_text(page, encoding="utf-8")
    print(f"страница: {OUT / 'listen.html'} - голосов {done}/{len(voices)}, реплик {lines}")


if __name__ == "__main__":
    main()
