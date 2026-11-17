"""SMTP sending with automatic tracking-pixel injection.

Configure via .env (copy .env.example -> .env):
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=465            # 465 = SSL, 587 = STARTTLS
    SMTP_USER=you@gmail.com
    SMTP_PASS=your-app-password   # Gmail: myaccount.google.com -> Security -> App passwords
    MAIL_FROM="Ahmed <you@gmail.com>"
"""

import os
import re
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

PIXEL_RE = re.compile(r"</body>", re.IGNORECASE)


def load_env(path=None):
    """Tiny .env loader (KEY=VALUE lines). Runs automatically from app.py."""
    path = path or os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def smtp_config():
    return {
        "host": os.environ.get("SMTP_HOST"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER"),
        "password": os.environ.get("SMTP_PASS"),
        "from": os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER"),
    }


def build_tracked_html(html_body, base_url, tid):
    """Inject the tracking pixel just before </body>."""
    pixel = (f'<img src="{base_url}/pixel/{tid}.gif" width="1" height="1" alt="" '
             f'style="display:none">')
    return PIXEL_RE.sub(pixel + "</body>", html_body, count=1)


import html as _html


def to_html(body):
    """Accepts plain text OR HTML. Plain text is auto-converted to clean
    paragraphs: blank line = new paragraph, single line break = <br>."""
    if "<" in body and ">" in body:          # already looks like HTML
        return body
    paras = [p.strip() for p in body.replace("\r\n", "\n").split("\n\n") if p.strip()]
    out = []
    for p in paras:
        p = _html.escape(p).replace("\n", "<br>")
        out.append(f'<p style="margin:0 0 14px">{p}</p>')
    inner = "".join(out) or "<p></p>"
    return (f'<html><body style="font-family:Segoe UI,Arial,sans-serif;'
            f'font-size:15px;line-height:1.6;color:#1a1a1a">{inner}</body></html>')


def send_tracked_mail(recipient, subject, html_body, base_url, tid):
    cfg = smtp_config()
    if not (cfg["host"] and cfg["user"] and cfg["password"]):
        return False, (
            "SMTP is not configured. Copy .env.example to .env and fill in "
            "SMTP_HOST / SMTP_USER / SMTP_PASS (Gmail needs an App Password, not your login password)."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(parse_from(cfg["from"]))
    msg["To"] = recipient
    if os.environ.get("REPLY_TO"):
        msg["Reply-To"] = os.environ["REPLY_TO"]
    # Plain-text alternative helps deliverability (spam filters distrust
    # HTML-only mail from unknown senders).
    plain = re.sub(r"<[^>]+>", " ", html_body)
    plain = re.sub(r"\s+", " ", plain).strip()
    msg.attach(MIMEText(plain or " ", "plain", "utf-8"))
    msg.attach(MIMEText(build_tracked_html(html_body, base_url, tid), "html", "utf-8"))

    try:
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=25) as smtp:
                smtp.login(cfg["user"], cfg["password"])
                smtp.send_message(msg)
        else:  # 587 / STARTTLS
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=25) as smtp:
                smtp.starttls()
                smtp.login(cfg["user"], cfg["password"])
                smtp.send_message(msg)
        return True, f"Sent to {recipient} — tracking pixel is live."
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP login failed — check SMTP_USER / SMTP_PASS (Gmail: use an App Password)."
    except (smtplib.SMTPException, socket.timeout, OSError) as exc:
        return False, f"SMTP error: {exc}"


def parse_from(value):
    """'Ahmed <a@x.com>' or 'a@x.com' -> (name, addr)."""
    if "<" in value and ">" in value:
        name, _, addr = value.partition("<")
        return name.strip().strip('"'), addr.replace(">", "").strip()
    return "", value.strip()
