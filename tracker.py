"""Core tracking logic: SQLite storage, geolocation, bot detection, user-agent parsing."""

import json
import os
import re
import sqlite3
import time
import urllib.request
import urllib.error

DB_PATH = os.path.join(os.path.dirname(__file__), "tracker.db")

# ---------------------------------------------------------------- database

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracked (
                id         TEXT PRIMARY KEY,
                recipient  TEXT NOT NULL,
                subject    TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                tracked_id TEXT NOT NULL,
                kind       TEXT NOT NULL,          -- 'open' or 'click'
                ts         INTEGER NOT NULL,
                ip         TEXT,
                city       TEXT,
                region     TEXT,
                country    TEXT,
                lat        REAL,
                lon        REAL,
                isp        TEXT,
                device     TEXT,
                browser    TEXT,
                is_bot     INTEGER DEFAULT 0,
                note       TEXT
            );
            """
        )


def create_tracked(recipient, subject, tid):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO tracked (id, recipient, subject, created_at) VALUES (?, ?, ?, ?)",
            (tid, recipient, subject, int(time.time())),
        )


def get_tracked(tid):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tracked WHERE id = ?", (tid,)).fetchone()
        return dict(row) if row else None


def log_event(tracked_id, kind, ip, ua, note=None):
    geo = geolocate(ip)
    device, browser = parse_ua(ua)
    is_bot = detect_bot(ua, geo.get("isp", ""))
    with _connect() as conn:
        conn.execute(
            """INSERT INTO events
               (tracked_id, kind, ts, ip, city, region, country, lat, lon, isp,
                device, browser, is_bot, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tracked_id, kind, int(time.time()), ip,
                geo.get("city"), geo.get("region"), geo.get("country"),
                geo.get("lat"), geo.get("lon"), geo.get("isp"),
                device, browser, int(is_bot), note,
            ),
        )
    return {"geo": geo, "device": device, "browser": browser, "is_bot": is_bot}


def list_tracked():
    """All tracked emails with their event summary."""
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM tracked ORDER BY created_at DESC")]
        for row in rows:
            events = [
                dict(e)
                for e in conn.execute(
                    "SELECT * FROM events WHERE tracked_id = ? ORDER BY ts DESC", (row["id"],)
                )
            ]
            row["events"] = events
            row["opens"] = sum(1 for e in events if e["kind"] == "open")
            row["clicks"] = sum(1 for e in events if e["kind"] == "click")
            row["human_opens"] = sum(1 for e in events if e["kind"] == "open" and not e["is_bot"])
            row["proxy_opens"] = sum(1 for e in events if e["kind"] == "open" and e["is_bot"])
            row["unique_open"] = any(e["kind"] == "open" for e in events)
        return rows


def recent_sends_to(recipient, seconds=900):
    """How many mails were sent to this recipient in the recent window (anti-spam guard)."""
    cutoff = int(time.time()) - seconds
    with _connect() as conn:
        (n,) = conn.execute(
            "SELECT COUNT(*) FROM tracked WHERE LOWER(recipient) = ? AND created_at > ?",
            (recipient.strip().lower(), cutoff),
        ).fetchone()
        return n


def stats():
    rows = list_tracked()
    total_sent = len(rows)
    opened = sum(1 for r in rows if r["unique_open"])
    total_events = sum(r["opens"] + r["clicks"] for r in rows)
    return {
        "total_sent": total_sent,
        "unique_opened": opened,
        "open_rate": round(100 * opened / total_sent) if total_sent else 0,
        "total_events": total_events,
    }


# ---------------------------------------------------------------- geolocation

_geo_cache = {}

# Free, key-less IP geolocation (ip-api.com). Rate limit: 45 req/min.
# Reserved/private IPs are skipped (localhost, LAN, docker...).
_RESOLVERS = {"127.0.0.1", "::1", "0.0.0.0"}


def geolocate(ip):
    if not ip or ip in _RESOLVERS or ip.startswith(("10.", "192.168.", "172.16.", "172.17.", "172.18.")):
        return {"city": "Local / unknown", "region": "", "country": "", "lat": None, "lon": None, "isp": ""}
    if ip in _geo_cache:
        return _geo_cache[ip]
    try:
        req = urllib.request.Request(
            f"http://ip-api.com/json/{ip}?fields=city,regionName,country,lat,lon,isp,org,as",
            headers={"User-Agent": "email-tracker-demo/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        geo = {
            "city": data.get("city") or "",
            "region": data.get("regionName") or "",
            "country": data.get("country") or "",
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "isp": data.get("isp") or data.get("org") or data.get("as") or "",
        }
    except (urllib.error.URLError, TimeoutError, ValueError):
        geo = {"city": "Unknown", "region": "", "country": "", "lat": None, "lon": None, "isp": ""}
    _geo_cache[ip] = geo
    return geo


# ---------------------------------------------------------------- bot / proxy detection

_BOT_UA = re.compile(
    r"bot|crawl|spider|scan|curl|wget|python|httpclient|preview|headless|phantom|zgrab|nmap",
    re.IGNORECASE,
)
_PROXY_ISP = re.compile(
    r"google|microsoft|outlook|yahoo|apple|amazonses|amazon|digitalocean|hetzner|ovh|"
    r"linode|vultr|cloud|datacamp|proxy|hosting|server",
    re.IGNORECASE,
)


def detect_bot(ua, isp):
    """Heuristics: scanner user-agents, or opens whose IP belongs to a known
    email-image-proxy / datacenter provider (Gmail & Outlook proxy images
    through their own servers, so 'location' would be theirs, not the reader's)."""
    if ua and _BOT_UA.search(ua):
        return True
    if isp and _PROXY_ISP.search(isp):
        return True
    return False


def parse_ua(ua):
    ua = ua or ""
    ua_l = ua.lower()
    if any(k in ua_l for k in ("iphone", "ipad", "ios")):
        device = "iOS"
    elif "android" in ua_l:
        device = "Android"
    elif "mac" in ua_l:
        device = "macOS"
    elif "windows" in ua_l:
        device = "Windows"
    elif "linux" in ua_l:
        device = "Linux"
    else:
        device = "Unknown"
    if "firefox" in ua_l:
        browser = "Firefox"
    elif "edg/" in ua_l:
        browser = "Edge"
    elif "chrome" in ua_l or "crios" in ua_l:
        browser = "Chrome"
    elif "safari" in ua_l:
        browser = "Safari"
    elif "outlook" in ua_l or "thunderbird" in ua_l:
        browser = "Mail client"
    else:
        browser = "Unknown"
    return device, browser


# ---------------------------------------------------------------- demo data

def seed_demo():
    """Insert realistic demo opens so the dashboard looks alive for portfolio viewers."""
    demo = [
        ("demo-01", "client@startup.io",  "Partnership proposal",  [
            ("open",  "1.2.3.4",   "San Francisco", "California", "United States", 37.77, -122.42, "Comcast Cable",       "Windows", "Chrome",  0),
            ("click", "1.2.3.4",   "San Francisco", "California", "United States", 37.77, -122.42, "Comcast Cable",       "Windows", "Chrome",  0),
            ("open",  "8.8.8.8",   "Mountain View", "California", "United States", 37.40, -122.08, "Google LLC",          "Unknown", "Unknown", 1),
        ]),
        ("demo-02", "hr@bigcorp.com",    "Job application - Security Analyst", [
            ("open",  "20.42.65.92", "Redmond",  "Washington", "United States", 47.67, -122.12, "Microsoft Corporation", "Unknown", "Unknown", 1),
            ("open",  "5.10.10.10",  "London",   "England",    "United Kingdom", 51.51, -0.13, "Vodafone UK",           "Android", "Gmail",   0),
        ]),
        ("demo-03", "founder@ycombinator.com", "Invoice #2041", [
            ("open",  "13.107.246.13", "Redmond", "Washington", "United States", 47.67, -122.12, "Microsoft Corporation", "Unknown", "Outlook", 1),
        ]),
        ("demo-04", "me@personal-mail.com", "Weekly newsletter", [
            ("open",  "102.89.34.100", "Lagos", "Lagos", "Nigeria", 6.52, 3.37, "MTN Nigeria", "Android", "Chrome", 0),
            ("open",  "102.89.34.100", "Lagos", "Lagos", "Nigeria", 6.52, 3.37, "MTN Nigeria", "Android", "Chrome", 0),
            ("click", "102.89.34.100", "Lagos", "Lagos", "Nigeria", 6.52, 3.37, "MTN Nigeria", "Android", "Chrome", 0),
        ]),
    ]
    now = int(time.time())
    with _connect() as conn:
        for tid, recipient, subject, events in demo:
            if conn.execute("SELECT 1 FROM tracked WHERE id = ?", (tid,)).fetchone():
                continue
            conn.execute(
                "INSERT INTO tracked (id, recipient, subject, created_at) VALUES (?, ?, ?, ?)",
                (tid, recipient, subject, now - 86400 * 3),
            )
            for i, (kind, ip, city, region, country, lat, lon, isp, device, browser, is_bot) in enumerate(events):
                conn.execute(
                    """INSERT INTO events
                       (tracked_id, kind, ts, ip, city, region, country, lat, lon, isp,
                        device, browser, is_bot)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tid, kind, now - 3600 * (10 - i * 2), ip, city, region, country,
                     lat, lon, isp, device, browser, is_bot),
                )


if __name__ == "__main__":
    init_db()
    seed_demo()
    print("Database initialized with demo data at", DB_PATH)
