"""Клиент бот-API заданий проверки (docs/portal/REVIEW_TASKS.md §10, «Этап A - сделано»).

Адрес и ключ - только с этой машины, секрет в репозиторий и в вывод не попадает. Порядок поиска:
  1. XP_REVIEW_URL / XP_REVIEW_BOT_KEY (перекрывают всё; так же гоняется локальный портал);
  2. файл XP_REVIEW_BOT_CONFIG или %USERPROFILE%/.xp-portal/review_bot.json: {"url": "...", "key": "..."}
     (рядом с bot.json тикетов; ключ с областью review заводится отдельно:
      Xp.Portal admin bot create --categories code,graphics,balance,translation,general,review);
  3. адрес (но не ключ) - из bot.json тикетов, если в п. 1-2 его нет.
Ключ тикетов не подходит: без области review сайт отвечает 403 bot_scope_missing.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".xp-portal"
REVIEW_CONFIG = Path(os.environ.get("XP_REVIEW_BOT_CONFIG") or HOME / "review_bot.json")
TICKETS_CONFIG = Path(os.environ.get("XP_BOT_CONFIG") or HOME / "bot.json")


class ApiError(Exception):
    def __init__(self, status, code, detail):
        super().__init__(f"HTTP {status} {code}: {detail}")
        self.status, self.code, self.detail = status, code, detail


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def load_config():
    url = os.environ.get("XP_REVIEW_URL", "")
    key = os.environ.get("XP_REVIEW_BOT_KEY", "")
    if not (url and key):
        cfg = _read(REVIEW_CONFIG)
        url = url or cfg.get("url", "")
        key = key or cfg.get("key", "")
    if not url:
        url = _read(TICKETS_CONFIG).get("url", "")
    if not url or not key:
        die("нет ключа бота для заданий проверки: задай XP_REVIEW_BOT_KEY (и XP_REVIEW_URL) или положи "
            f"{REVIEW_CONFIG} с {{\"url\": ..., \"key\": ...}}. Ключ с областью review заводится на сервере: "
            "Xp.Portal admin bot create --categories code,graphics,balance,translation,general,review")
    return {"url": url.rstrip("/"), "key": key}


class Client:
    def __init__(self, cfg=None):
        self.cfg = cfg or load_config()

    @property
    def host(self):
        return urllib.parse.urlsplit(self.cfg["url"]).netloc

    def request(self, method, path, body=None, raw=None, headers=None, retries=4):
        """JSON-запрос (body) или байты (raw). Повтор на 429/502/503/504 и обрывах сети."""
        url = self.cfg["url"] + "/api/v1/bot/review/tasks" + path
        h = {"X-Bot-Key": self.cfg["key"], "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            h["Content-Type"] = "application/json; charset=utf-8"
        elif raw is not None:
            data = raw
            h["Content-Type"] = "application/octet-stream"
        h.update(headers or {})
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=data, method=method, headers=h)
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    payload = r.read()
                    return r.status, (json.loads(payload.decode("utf-8")) if payload else None)
            except urllib.error.HTTPError as e:
                text = e.read().decode("utf-8", "replace")
                if e.code in (429, 502, 503, 504) and attempt < retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                code, detail = "", text[:300]
                try:
                    p = json.loads(text)
                    code, detail = p.get("code", ""), p.get("detail") or p.get("title") or detail
                except ValueError:
                    pass
                raise ApiError(e.code, code, detail) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt >= retries:
                    raise
                time.sleep(2 * (attempt + 1))

    def create(self, payload, key):
        return self.request("POST", "", body=payload, headers={"Idempotency-Key": key})

    def get(self, number):
        return self.request("GET", "/" + str(number))[1]

    def put_file(self, number, path, data, sha256):
        quoted = urllib.parse.quote(path, safe="/")
        return self.request("PUT", f"/{number}/files/{quoted}", raw=data, headers={"X-Sha256": sha256})

    def send(self, number):
        return self.request("POST", f"/{number}/send")[1]

    def list(self, status="answered", take=200):
        return self.request("GET", f"?status={status}&take={take}")[1]

    def answer(self, number):
        return self.request("GET", f"/{number}/answer")[1]

    def taken(self, number):
        return self.request("POST", f"/{number}/taken")[1]

    def revoke(self, number):
        return self.request("POST", f"/{number}/revoke")[1]
