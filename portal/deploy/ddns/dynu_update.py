"""Keeps a Dynu hostname pointed at this server's public IPv4. Standard library only.

Two ways to authenticate, the first one set wins:
  DYNU_API_KEY           API v2 (https://api.dynu.com/v2/, header API-Key). The record is read
                         first, so Dynu is written to only when its IPv4 really differs.
  DYNU_PASSWORD_SHA256   IP update protocol (https://api.dynu.com/nic/update) with a hashed
  DYNU_PASSWORD          password; the plain one is hashed here and never sent in clear.

Other environment (see .env.example):
  DYNU_HOSTNAME          x-piratez.mywire.org
  DYNU_INTERVAL          seconds between IP checks, default 300
  DYNU_FORCE_DAYS        re-send an unchanged IP this often (password mode), default 7
  DYNU_API_RECHECK       re-read the live record this often (API mode), seconds, default 3600
  DYNU_ONCE=1            one pass and exit (tests, cron)
  DYNU_API, DYNU_API_V2, DYNU_CHECKIP, DYNU_STATE, DYNU_BUSY_WAIT   overridden only by tests

Exit code 2 = fatal (bad key or password, unknown host, abuse): the container stops instead of
hammering Dynu, which blocks clients that retry bad credentials.
"""
import hashlib, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

E = os.environ.get
HOST = E("DYNU_HOSTNAME", "").strip().lower()
API = E("DYNU_API", "https://api.dynu.com/nic/update")
API_V2 = E("DYNU_API_V2", "https://api.dynu.com/v2").rstrip("/")
CHECKIP = E("DYNU_CHECKIP", "https://checkip.dynu.com/")
STATE = E("DYNU_STATE", "/state/last-ip")
INTERVAL = int(E("DYNU_INTERVAL") or 300)
FORCE = int(E("DYNU_FORCE_DAYS") or 7) * 86400
API_RECHECK = int(E("DYNU_API_RECHECK") or 3600)
BUSY_WAIT = int(E("DYNU_BUSY_WAIT") or 600)
UA = "x-piratez-ddns/1.0"

DONE, RETRY, FATAL = 0, 1, 2
# fields of DNS.domain that the update accepts; readOnly ones (id, token, state, dates) are not sent
WRITABLE = ("name", "group", "ipv4Address", "ipv6Address", "ttl", "ipv4", "ipv6",
            "ipv4WildcardAlias", "ipv6WildcardAlias", "allowZoneTransfer", "dnssec")


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def http(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def public_ip():
    try:
        _, body = http(CHECKIP)
    except OSError as e:
        log(f"cannot learn the public IP: {e}")
        return None
    m = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", body)
    return m.group(1) if m else None


def update_password(ip, pw_hash):
    q = urllib.parse.urlencode({"hostname": HOST, "myip": ip, "myipv6": "no", "password": pw_hash})
    try:
        _, body = http(API + "?" + q)
    except OSError as e:
        log(f"network error: {e}")
        return RETRY
    code = (body.split() or [""])[0]
    if code in ("good", "nochg"):
        log(f"{code} {HOST} -> {ip}")
        return DONE
    if code in ("911", "dnserr", "servererror"):
        log(f"dynu busy ({code}), retry in {BUSY_WAIT}s")
        time.sleep(BUSY_WAIT)
        return RETRY
    if code in ("badauth", "nohost", "notfqdn", "numhost", "abuse", "!donator", "unknown"):
        log(f"FATAL dynu answered '{body.strip()}' - check DYNU_HOSTNAME and the password")
        return FATAL
    log(f"unexpected answer '{body.strip()[:200]}', retry later")
    return RETRY


def update_api(ip, key):
    hdr = {"API-Key": key, "Accept": "application/json"}
    try:
        status, body = http(API_V2 + "/dns", headers=hdr)
        if status == 401:
            log("FATAL dynu API refused the key (401) - check DYNU_API_KEY")
            return FATAL
        if status != 200:
            log(f"dynu API {status} on list, retry later: {body[:200]}")
            return RETRY
        domain = next((d for d in json.loads(body).get("domains", []) if d.get("name", "").lower() == HOST), None)
        if domain is None:
            log(f"FATAL {HOST} is not among the domains of this API key")
            return FATAL
        if domain.get("ipv4Address") == ip:
            log(f"nochg {HOST} -> {ip} (already in DNS)")
            return DONE
        # read-modify-write: POST replaces the record, so every writable field goes back as it was
        body = {k: domain[k] for k in WRITABLE if k in domain}
        body["ipv4Address"] = ip
        body["ipv4"] = True
        status, answer = http(f"{API_V2}/dns/{domain['id']}", data=json.dumps(body).encode(),
                              headers={**hdr, "Content-Type": "application/json"}, method="POST")
    except (OSError, ValueError) as e:
        log(f"network or format error: {e}")
        return RETRY
    if status == 200:
        log(f"good {HOST} -> {ip} (was {domain.get('ipv4Address')})")
        return DONE
    if status == 401:
        log("FATAL dynu API refused the key (401) on update")
        return FATAL
    log(f"dynu API {status} on update, retry later: {answer[:200]}")
    return RETRY


def main():
    if not HOST:
        log("FATAL DYNU_HOSTNAME is not set")
        return FATAL
    key = E("DYNU_API_KEY", "").strip()
    pw_hash = E("DYNU_PASSWORD_SHA256", "").strip().lower()
    if not key and not pw_hash and E("DYNU_PASSWORD"):
        pw_hash = hashlib.sha256(E("DYNU_PASSWORD").encode()).hexdigest()
    if not key and not pw_hash:
        log("FATAL set DYNU_API_KEY, DYNU_PASSWORD_SHA256 or DYNU_PASSWORD")
        return FATAL
    os.makedirs(os.path.dirname(STATE) or ".", exist_ok=True)
    log(f"watching {HOST} every {INTERVAL}s via {'API key' if key else 'IP update password'}")
    while True:
        ip = public_ip()
        if ip:
            last, age = "", FORCE
            if os.path.exists(STATE):
                last = open(STATE).read().strip()
                age = time.time() - os.path.getmtime(STATE)
            # an unchanged IP is re-checked hourly with the API key (it reads the live record and
            # repairs a manual change), weekly with the password (Dynu calls frequent resends abuse)
            if ip != last or age >= (API_RECHECK if key else FORCE):
                if last and ip != last:
                    log(f"IP changed: {last} -> {ip}")
                rc = update_api(ip, key) if key else update_password(ip, pw_hash)
                if rc == DONE:
                    with open(STATE, "w") as f:
                        f.write(ip)
                elif rc == FATAL:
                    return FATAL
        if E("DYNU_ONCE") == "1":
            return DONE
        time.sleep(INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
