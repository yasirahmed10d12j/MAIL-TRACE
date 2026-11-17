"""One-shot setup verification: plain-text conversion, tunnel reachability, SMTP login."""

import json
import socket
import smtplib
import urllib.request

from sender import load_env, smtp_config, to_html

print("--- 1. Plain text -> HTML conversion ---")
demo = to_html("Hi!\n\nKya haal hai?\nKal milte hain.\n\nThanks")
assert "<p" in demo and "<br>" in demo and "Kya haal hai" in demo
print("OK: normal text auto-converts to clean HTML")

print("--- 2. Tunnel (public URL) reachable ---")
BASE = None
for line in open(".env", encoding="utf-8"):
    if line.startswith("BASE_URL="):
        BASE = line.split("=", 1)[1].strip()
try:
    with urllib.request.urlopen(BASE + "/dashboard", timeout=25) as r:
        assert r.status == 200
    print("OK:", BASE, "-> HTTP 200 (pixel URL publicly reachable)")
except Exception as exc:
    print("FAIL:", exc)

print("--- 3. Gmail login (no mail is sent) ---")
cfg = smtp_config()
try:
    with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20) as s:
        s.login(cfg["user"], cfg["password"])
    print("OK: Gmail login successful —", cfg["user"])
except smtplib.SMTPAuthenticationError:
    print("FAIL: password wrong — .env me 16-char app password (spaces ke bina) hona chahiye")
except (socket.timeout, OSError) as exc:
    print("FAIL: network error —", exc)
