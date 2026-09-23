"""Runs dynu-update.sh against a fake Dynu API. Needs sh + curl (Linux, or Git Bash on Windows).
   python test_dynu.py"""
import hashlib, http.server, os, shutil, subprocess, sys, tempfile, threading, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
SH = shutil.which("sh") or r"C:\Program Files\Git\bin\sh.exe"
calls, cfg = [], {"ip": "203.0.113.7", "answer": "good 203.0.113.7"}

class Fake(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/checkip":
            body = "Current IP Address: " + cfg["ip"]
        else:
            calls.append(dict(urllib.parse.parse_qsl(u.query)))
            body = cfg["answer"]
        self.send_response(200); self.end_headers(); self.wfile.write(body.encode())
    def log_message(self, *a): pass

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
state = os.path.join(tempfile.mkdtemp(), "last-ip")

def run(**env):
    e = dict(os.environ, DYNU_HOSTNAME="x-piratez.mywire.org", DYNU_PASSWORD="secret",
             DYNU_API=base + "/nic/update", DYNU_CHECKIP=base + "/checkip",
             DYNU_STATE=state, DYNU_ONCE="1", DYNU_BUSY_WAIT="0")
    e.update(env)
    p = subprocess.run([SH, os.path.join(HERE, "dynu-update.sh")], env=e, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr

fails = 0
def check(name, ok, out=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name)
    if not ok: fails += 1; print(out)

rc, out = run(); c = calls[-1] if calls else {}
check("first run updates", rc == 0 and len(calls) == 1 and c.get("myip") == cfg["ip"], out)
check("password sent as SHA-256, never in clear", c.get("password") == hashlib.sha256(b"secret").hexdigest())
check("ipv6 left alone", c.get("myipv6") == "no")
rc, out = run(); check("same IP: Dynu not called again", rc == 0 and len(calls) == 1, out)
cfg["ip"] = "203.0.113.8"; cfg["answer"] = "good 203.0.113.8"
rc, out = run(); check("changed IP: updated", rc == 0 and len(calls) == 2 and "IP changed" in out, out)
rc, out = run(DYNU_FORCE_DAYS="0"); check("weekly refresh re-sends unchanged IP", len(calls) == 3, out)
cfg["ip"] = "203.0.113.9"; cfg["answer"] = "badauth"
rc, out = run(); check("badauth is fatal (exit 2)", rc == 2 and "FATAL" in out, out)
cfg["answer"] = "911"
rc, out = run(); check("911 is retried, state not saved", rc == 0 and open(state).read().strip() == "203.0.113.8", out)
cfg["answer"] = "nochg"
rc, out = run(); check("nochg counts as done", rc == 0 and open(state).read().strip() == "203.0.113.9", out)
rc, out = run(DYNU_PASSWORD="", DYNU_PASSWORD_SHA256=""); check("no password: refuses to start", rc == 2, out)
srv.shutdown()
print("all passed" if not fails else f"{fails} failed"); sys.exit(1 if fails else 0)
