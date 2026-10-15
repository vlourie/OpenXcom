"""Расход сессии Claude Code по её журналу: вызовы модели, входные токены, запись и чтение кэша,
сжатия, контекст первого вызова и объём сделанной работы (вызовы инструментов).

Контроль правок 15.10.2026 (аудит кредитов, docs/research/credits-audit-2026-10-15.md): первый вызов
новой сессии и частота сжатий. Журналы Claude Code лежат в
%USERPROFILE%/.claude/projects/<корень с '-' вместо ':' и косых>/<id>.jsonl; в них у записей
"type":"assistant" есть message.usage (input_tokens, cache_creation_input_tokens,
cache_read_input_tokens, output_tokens), у сжатий - "subtype":"compact_boundary".
Контекст вызова = input + cache_creation + cache_read. Изменение лимита плана в журнале не пишется:
его смотреть в карточке использования приложения до и после задачи.

Запуск:
  PYTHONIOENCODING=utf-8 py -3.13 tools/session_usage.py                       # сессии, начатые сегодня
  PYTHONIOENCODING=utf-8 py -3.13 tools/session_usage.py --since "2026-10-15 09:08"
  PYTHONIOENCODING=utf-8 py -3.13 tools/session_usage.py <id или путь .jsonl> [...]
  PYTHONIOENCODING=utf-8 py -3.13 tools/session_usage.py <id> --from "2026-10-15 09:22"   # отрезок одной задачи
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = Path.home() / ".claude" / "projects" / str(ROOT).replace(":", "-").replace("\\", "-").replace("/", "-")


def ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    except Exception:
        return None


def local(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M").astimezone()


def scan(path, start=None):
    calls, seen, compacts, tools = [], set(), 0, 0
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = ts(d.get("timestamp", "") or "")
            if start and t and t < start:
                continue
            if d.get("subtype") == "compact_boundary" or (d.get("type") == "system" and "compact_boundary" in line):
                compacts += 1
                continue
            if d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            for c in m.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    tools += 1
            u = m.get("usage")
            if not u or m.get("id") in seen:
                continue
            seen.add(m.get("id"))
            i, cc, cr = (u.get("input_tokens") or 0, u.get("cache_creation_input_tokens") or 0,
                         u.get("cache_read_input_tokens") or 0)
            calls.append(dict(t=t, ctx=i + cc + cr, inp=i, create=cc, read=cr, out=u.get("output_tokens") or 0))
    return calls, compacts, tools


def report(path, start=None):
    calls, compacts, tools = scan(path, start)
    if not calls:
        return None
    first = calls[0]
    n = len(calls)
    ctxs = [c["ctx"] for c in calls if c["ctx"] > 0]
    r = dict(
        id=path.name[:8], start=first["t"], end=calls[-1]["t"], calls=n, tools=tools, compacts=compacts,
        first_ctx=first["ctx"], first_create=first["create"], first_read=first["read"],
        inp=sum(c["inp"] for c in calls), create=sum(c["create"] for c in calls),
        read=sum(c["read"] for c in calls), out=sum(c["out"] for c in calls),
        ctx_avg=sum(ctxs) // max(len(ctxs), 1), ctx_max=max(ctxs) if ctxs else 0,
    )
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions", nargs="*", help="id (начало имени) или путь .jsonl; пусто - по --since")
    ap.add_argument("--since", help="сессии, начатые не раньше (местное время, 'ГГГГ-ММ-ДД ЧЧ:ММ'); по умолчанию сегодня 00:00")
    ap.add_argument("--from", dest="start", help="считать только вызовы с этого времени (отрезок задачи)")
    a = ap.parse_args()
    start = local(a.start) if a.start else None
    if a.sessions:
        paths = []
        for s in a.sessions:
            p = Path(s)
            paths += [p] if p.suffix == ".jsonl" and p.exists() else sorted(LOGS.glob(f"{s}*.jsonl"))
    else:
        since = local(a.since) if a.since else datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        paths = [p for p in LOGS.glob("*.jsonl") if datetime.fromtimestamp(p.stat().st_mtime).astimezone() >= since]
    rows = []
    for p in sorted(paths):
        r = report(p, start)
        if r and (a.sessions or not a.since or r["start"] >= local(a.since)):
            rows.append(r)
    if not rows:
        print(f"Журналов не найдено в {LOGS}")
        return 1
    rows.sort(key=lambda r: r["start"])
    print(f"Журналы: {LOGS}" + (f"; отрезок с {a.start}" if a.start else ""))
    print("сессия    начало         вызовов инстр сжатий | 1-й вызов: контекст  запись   чтение | сумма: вход      запись     чтение     выход | контекст ср/макс")
    for r in rows:
        print(f"{r['id']}  {r['start']:%d.%m %H:%M:%S}  {r['calls']:>6} {r['tools']:>5} {r['compacts']:>6} | "
              f"{r['first_ctx']:>18,} {r['first_create']:>8,} {r['first_read']:>8,} | "
              f"{r['inp']:>12,} {r['create']:>10,} {r['read']:>10,} {r['out']:>9,} | {r['ctx_avg']:>7,}/{r['ctx_max']:,}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
