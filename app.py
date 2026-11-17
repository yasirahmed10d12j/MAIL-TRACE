"""MailTrace - email open & location tracker.

Run:  python app.py
Open: http://127.0.0.1:5000
"""

import os
import secrets
import uuid

from flask import Flask, jsonify, redirect, render_template, request, Response

import tracker
from sender import load_env, send_tracked_mail, to_html

load_env()  # reads .env next to this file, if present

# 1x1 transparent GIF
PIXEL = bytes.fromhex(
    "474946383961010000010080000000000000ffffff21f90401000000002c"
    "00000000010000010000020202004b0103003b"
)

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")

app = Flask(__name__)
tracker.init_db()


@app.get("/")
def index():
    return render_template("index.html", base_url=BASE_URL)


@app.get("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.get("/pixel/<tid>.gif")
def pixel(tid):
    """Invisible 1x1 image: every fetch = one email open."""
    record = tracker.get_tracked(tid)
    if record:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0].strip()
        info = tracker.log_event(tid, "open", ip, request.headers.get("User-Agent", ""))
        app.logger.info(
            "OPEN %s from %s (%s%s) bot=%s",
            tid, ip, info["geo"].get("city", "?"), info["geo"].get("country", ""),
            info["is_bot"],
        )
    return Response(PIXEL, mimetype="image/gif", headers={"Cache-Control": "no-store, no-cache"})


@app.get("/link/<tid>")
def track_link(tid):
    """Tracked redirect: logs a click, then forwards to ?url= or /dashboard."""
    record = tracker.get_tracked(tid)
    if record:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0].strip()
        tracker.log_event(tid, "click", ip, request.headers.get("User-Agent", ""))
    target = request.args.get("url", "/dashboard")
    if not target.startswith(("/", "http://", "https://")):
        target = "/dashboard"
    return redirect(target, code=302)


@app.post("/api/tracked")
def api_create():
    data = request.get_json(silent=True) or {}
    recipient = (data.get("recipient") or "").strip()
    subject = (data.get("subject") or "No subject").strip()
    if not recipient or "@" not in recipient:
        return jsonify({"error": "A valid recipient email is required"}), 400
    tid = uuid.uuid4().hex[:12]
    tracker.create_tracked(recipient, subject, tid)
    return jsonify({
        "id": tid,
        "pixel_url": f"{BASE_URL}/pixel/{tid}.gif",
        "link_url": f"{BASE_URL}/link/{tid}",
        "html_snippet": f'<img src="{BASE_URL}/pixel/{tid}.gif" width="1" height="1" style="display:none" alt="">',
    })


@app.post("/api/send")
def api_send():
    data = request.get_json(silent=True) or {}
    recipient = (data.get("recipient") or "").strip()
    subject = (data.get("subject") or "No subject").strip()
    body = data.get("body") or ""
    if not recipient or "@" not in recipient:
        return jsonify({"error": "A valid recipient email is required"}), 400

    # ---- Anti-spam guard: warn BEFORE sending so mail lands in inbox ----
    warnings = []
    if tracker.recent_sends_to(recipient) >= 1:
        warnings.append(
            f"Aap ne 15 min me {recipient} ko pehle bhi mail bheji hai — "
            "baar-baar bhejne se Gmail spam mark karta hai. Thoda ruk ke bhejo."
        )
    if len(subject) > 3 and subject.isupper():
        warnings.append("Subject ALL CAPS hai — spam filter isko trigger samajhta hai.")
    if body.count("http") > 5:
        warnings.append("Message me 5+ links hain — kam links = inbox chances zyada.")
    for word in ("winner", "lottery", "free money", "click here now", "urgent!!!"):
        if word in body.lower() or word in subject.lower():
            warnings.append(f'"{word}" jaisi spammy words hata do.')
            break

    tid = uuid.uuid4().hex[:12]
    tracker.create_tracked(recipient, subject, tid)
    ok, message = send_tracked_mail(recipient, subject, to_html(body), BASE_URL, tid)
    return jsonify({"id": tid, "sent": ok, "message": message,
                    "warnings": warnings}), (200 if ok else 400)


@app.get("/api/tracked")
def api_list():
    return jsonify({"emails": tracker.list_tracked(), "stats": tracker.stats()})


@app.post("/api/seed")
def api_seed():
    tracker.seed_demo()
    return jsonify({"ok": True})


@app.post("/api/clear")
def api_clear():
    with tracker._connect() as conn:
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM tracked")
    return jsonify({"ok": True})


if __name__ == "__main__":
    if not os.path.exists(tracker.DB_PATH):
        tracker.seed_demo()
    print(f"  MailTrace running -> {BASE_URL}/dashboard")
    app.run(debug=True, port=5000)
