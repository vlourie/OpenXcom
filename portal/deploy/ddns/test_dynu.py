"""Runs dynu_update.py against a fake Dynu (both the IP update protocol and API v2).
   python test_dynu.py"""
import hashlib, http.server, json, os, subprocess, sys, tempfile, threading, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
calls, posts = [], []
cfg = {"ip": "203.0.113.7", "answer": "good", "key": "k1", "list_status": 200,
       "domains": [{"id": 42, "name": "x-piratez.mywire.org", "token": "t", "state": "Complete",
                    "group": "", "ipv4Address": "198.51.100.1", "ttl": 90, "ipv4": True, "ipv6": False,
                    "ipv4WildcardAlias": True, "createdOn": "2026-01-01T00:00:00Z"}]}

class Fake(http.server.BaseHTTPRequestHandler):
    def reply(self, code, body):
        self.send_response(code); self.end_headers(); self.wfile.write(body.encode())
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/checkip": return self.reply(200, "Current IP Address: " + cfg["ip"])
        if u.path == "/nic/update":
            calls.append(dict(urllib.parse.parse_qsl(u.query))); return self.reply(200, cfg["answer"])
        if u.path == "/v2/dns":
            calls.append({"list": self.headers.get("API-Key")})
            if self.headers.get("API-Key") != cfg["key"]: return self.reply(401, '{"statusCode":401}')
            return self.reply(cfg["list_status"], json.dumps({"statusCode": 200, "domains": cfg["domains"]}))
        self.reply(404, "")
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        posts.append((self.path, body))
        for d in cfg["domains"]:
            if self.path == f"/v2/dns/{d['id']}": d.update(body)
        self.reply(200, '{"statusCode":200}')
    def log_message(self, *a): pass

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"

def run(state, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("DYNU_")}
    e.update(DYNU_HOSTNAME="x-piratez.mywire.org", DYNU_API=base + "/nic/update", DYNU_API_V2=base + "/v2",
             DYNU_CHECKIP=base + "/checkip", DYNU_STATE=state, DYNU_ONCE="1", DYNU_BUSY_WAIT="0")
    e.update(env)
    p = subprocess.run([sys.executable, os.path.join(HERE, "dynu_update.py")], env=e, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr

fails = 0
def check(name, ok, out=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails += 1; print(out)
read = lambda p: open(p).read().strip()

print("-- IP update password")
st = os.path.join(tempfile.mkdtemp(), "last-ip")
rc, out = run(st, DYNU_PASSWORD="secret"); c = calls[-1] if calls else {}
check("first run updates", rc == 0 and len(calls) == 1 and c.get("myip") == cfg["ip"], out)
check("password sent as SHA-256, never in clear", c.get("password") == hashlib.sha256(b"secret").hexdigest())
check("ipv6 left alone", c.get("myipv6") == "no")
rc, out = run(st, DYNU_PASSWORD="secret"); check("same IP: Dynu not called again", rc == 0 and len(calls) == 1, out)
cfg["ip"] = "203.0.113.8"
rc, out = run(st, DYNU_PASSWORD="secret"); check("changed IP: updated", rc == 0 and len(calls) == 2 and "IP changed" in out, out)
rc, out = run(st, DYNU_PASSWORD="secret", DYNU_FORCE_DAYS="0"); check("weekly refresh re-sends unchanged IP", len(calls) == 3, out)
cfg["ip"] = "203.0.113.9"; cfg["answer"] = "badauth"
rc, out = run(st, DYNU_PASSWORD="secret"); check("badauth is fatal (exit 2)", rc == 2 and "FATAL" in out, out)
cfg["answer"] = "911"
rc, out = run(st, DYNU_PASSWORD="secret"); check("911 is retried, state not saved", rc == 0 and read(st) == "203.0.113.8", out)
cfg["answer"] = "nochg"
rc, out = run(st, DYNU_PASSWORD="secret"); check("nochg counts as done", rc == 0 and read(st) == "203.0.113.9", out)
rc, out = run(st); check("no credentials: refuses to start", rc == 2, out)

print("-- API v2 key")
st = os.path.join(tempfile.mkdtemp(), "last-ip"); calls.clear()
rc, out = run(st, DYNU_API_KEY="k1")
path, body = posts[-1] if posts else ("", {})
check("wrong IP in DNS: record updated", rc == 0 and path == "/v2/dns/42" and body.get("ipv4Address") == cfg["ip"], out)
check("other settings sent back unchanged", body.get("ttl") == 90 and body.get("ipv4WildcardAlias") is True and body.get("name") == "x-piratez.mywire.org")
check("read-only fields not sent", not {"id", "token", "state", "createdOn"} & set(body))
check("key sent in API-Key header", calls and calls[0].get("list") == "k1")
n = len(posts)
rc, out = run(st, DYNU_API_KEY="k1", DYNU_API_RECHECK="0"); check("record already right: no write", rc == 0 and len(posts) == n and "nochg" in out, out)
rc, out = run(st, DYNU_API_KEY="k1"); check("same IP within the hour: API not even read", rc == 0 and len(calls) == 2, out)
rc, out = run(st, DYNU_API_KEY="bad", DYNU_API_RECHECK="0"); check("bad key is fatal (exit 2)", rc == 2 and "401" in out, out)
rc, out = run(st, DYNU_API_KEY="k1", DYNU_HOSTNAME="other.mywire.org", DYNU_API_RECHECK="0"); check("unknown host is fatal", rc == 2 and "not among" in out, out)
cfg["list_status"] = 502; cfg["ip"] = "203.0.113.10"
rc, out = run(st, DYNU_API_KEY="k1"); check("server error is retried, state kept", rc == 0 and read(st) == "203.0.113.9", out)
cfg["list_status"] = 200
rc, out = run(st, DYNU_API_KEY="k1", DYNU_PASSWORD="secret"); check("API key wins over password", rc == 0 and posts[-1][1]["ipv4Address"] == "203.0.113.10" and "API key" in out, out)
srv.shutdown()
print("all passed" if not fails else f"{fails} failed"); sys.exit(1 if fails else 0)
