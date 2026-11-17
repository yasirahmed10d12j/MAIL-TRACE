# 📧 MailTrace — Email Open & Location Tracker

A fully working, self-hosted email tracking system — the same technology behind
Mailtrack, Yesware and sales-engagement platforms. Know **if**, **when**, **where**
and **on what device** your email was opened — and detect when an "open" is
actually a bot or a provider's image proxy.

**Stack:** Python (Flask, stdlib SMTP) · SQLite · Leaflet.js · free ip-api.com geolocation · zero paid APIs

---

## Features

| Feature | How it works |
|---|---|
| 👁 **Open detection** | Invisible 1×1 tracking pixel; every fetch = one open |
| 📍 **Location intel** | Sender IP geolocated (city/region/country + ISP) and pinned on a dark world map |
| 🤖 **Bot & proxy detection** | Scanner user-agents and Google/Microsoft image-proxy IPs flagged so open counts stay honest |
| 🖱 **Click tracking** | Tracked link redirects (`/link/<id>`) log clicks alongside opens |
| 💻 **Device fingerprint** | OS + mail client parsed from the User-Agent |
| ✉️ **Real SMTP sending** | Send directly from the dashboard (Gmail/Outlook/Zoho, SSL + STARTTLS) with the pixel auto-injected |
| 📊 **Live dashboard** | Stats, activity timeline, world map; auto-refreshes every 15 s |

## What I verified while building (real requests, real geolocation)

- Pixel fetch logged an open → geolocated to **Lagos, Nigeria (MTN Nigeria)** with correct lat/lon
- Link click → logged + 302 redirect
- Fetch from a **Google LLC IP** → geolocated to Mountain View and flagged 🤖 (Gmail image-proxy simulation)
- Scanner UA (`curl`) → flagged 🤖
- SMTP without config → graceful, actionable error message

## Quick start

```bash
cd email-tracker
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000/dashboard**

### Send real emails (optional)

```bash
copy .env.example .env   # then edit .env
```

- **Gmail:** enable 2-Step Verification, create an *App Password*
  (myaccount.google.com → Security → App passwords), put it in `SMTP_PASS`
- Set `SMTP_PORT=465` (SSL) or `587` (STARTTLS) — both supported
- Or use Outlook (`smtp.office365.com:587`), Zoho, or any SMTP server

> ⚠️ **Important for real sends:** the tracking pixel URL must be reachable
> from the *recipient's* mail client. `127.0.0.1` only works for local tests —
> for real use, host this on a VPS (or tunnel with `cloudflared` / `ngrok`)
> and set `BASE_URL` in `.env` to the public URL.

### Using the pixel manually (any mail composer)

1. Register the email in the dashboard → copy the **HTML snippet**
2. Paste it into your email's HTML source (before `</body>`)
3. Watch opens appear on the map & timeline

## How the tracking pixel works

```
Recipient opens email
        │
        ▼
Mail client fetches  <img src="https://your-host/pixel/<id>.gif">
        │
        ▼
Flask logs: timestamp · IP · User-Agent
        │
        ▼
IP → ip-api.com geolocation (cached)   UA → device/browser parse
        │
        ▼
IP flagged if ISP ∈ {Google, Microsoft, datacenters} or UA is a scanner
        │
        ▼
1×1 transparent GIF returned (Cache-Control: no-store)
        │
        ▼
Dashboard: timeline + map markers (cyan = open, amber = click, red = bot)
```

## Honest limitations (documented, not hidden)

- **Gmail / Outlook / Yahoo proxy images** through their own servers, so a
  first-open location may show *their* datacenter — MailTrace detects these IPs
  and labels the open as `🤖 BOT / EMAIL PROXY` instead of showing a fake location.
- Some mail clients block remote images by default → no pixel fetch, no open.
- Pixel-based tracking can't detect plaintext opens.
- Requires internet for geolocation lookups (cached per IP after first lookup).

## Ethical use

Track only emails you send yourself, disclose where required, and respect
GDPR/privacy laws in your jurisdiction. Built for education and as a
cybersecurity portfolio project.

---

*Cybersecurity portfolio project by Ahmed.*
