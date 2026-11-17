"""End-to-end self-test for MailTrace. Run while the server is up:
    python selftest.py [base_url]   (default http://127.0.0.1:5000)
"""

import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
PUBLIC_IP = "102.89.34.100"  # any public IP for a real geolocation test

passed = failed = 0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def req(path, method="GET", body=None, headers=None):
    """Does NOT follow redirects — we assert on 302 directly."""
    opener = urllib.request.build_opener(_NoRedirect)
    r = urllib.request.Request(BASE + path, method=method,
                               data=json.dumps(body).encode() if body else None,
                               headers={"Content-Type": "application/json", **(headers or {})})
    try:
        return opener.open(r, timeout=20)
    except urllib.error.HTTPError as err:  # 3xx/4xx returned as response objects
        return err


def check(name, cond, detail=""):
    global passed, failed
    passed, failed = passed + (1 if cond else 0), failed + (0 if cond else 1)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not cond else ""))


print("MailTrace self-test ->", BASE)

# 1. pages
check("landing page", req("/").status == 200)
check("dashboard page", req("/dashboard").status == 200)

# 2. create tracked email
out = json.loads(req("/api/tracked", "POST",
                     {"recipient": "selftest@probe.io", "subject": "Selftest"}).read())
tid = out.get("id", "")
check("create tracked email", bool(tid), str(out))

# 3. pixel fetch = open, with real public IP
img = req(f"/pixel/{tid}.gif", headers={"X-Forwarded-For": PUBLIC_IP, "User-Agent": UA})
check("pixel returns GIF", img.status == 200 and b"GIF8" in img.read(8))

# 4. click tracking
click = req(f"/link/{tid}?url=https://example.com",
            headers={"X-Forwarded-For": PUBLIC_IP, "User-Agent": UA})
check("tracked link redirects", click.status == 302)

# 5. events recorded + geolocated
data = json.loads(req("/api/tracked").read())
mine = next((e for e in data["emails"] if e["id"] == tid), None)
kinds = {ev["kind"] for ev in mine["events"]}
check("open + click logged", {"open", "click"} <= kinds, str(kinds))
geo = mine["events"][0]
check("geolocation enriched", bool(geo["city"] and geo["country"]), str(geo))
check("device parsed", geo["device"] in ("Windows", "macOS", "Linux", "iOS", "Android"), geo["device"])
check("stats computed", data["stats"]["total_events"] >= 2, str(data["stats"]))

# 6. bot detection
bot = req(f"/pixel/{tid}.gif", headers={"X-Forwarded-For": "209.85.220.41", "User-Agent": "curl/8.0"})
data = json.loads(req("/api/tracked").read())
mine = next(e for e in data["emails"] if e["id"] == tid)
check("bot/proxy open flagged", any(ev["is_bot"] for ev in mine["events"]))

# 7. validation
bad = req("/api/tracked", "POST", {"recipient": "not-an-email"})
check("invalid recipient rejected", bad.status == 400)

# 8. SMTP status — only asserts graceful handling when unconfigured
#    (never sends a real test mail through the user's account)
from sender import load_env, smtp_config
load_env()
cfg = smtp_config()
if cfg["host"] and cfg["user"] and cfg["password"]:
    check("SMTP configured", True, cfg["user"])
else:
    send = json.loads(req("/api/send", "POST",
                          {"recipient": "x@y.com", "subject": "s", "body": "<p>hi</p>"}).read())
    check("SMTP error handled gracefully", send.get("sent") is False, str(send))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
