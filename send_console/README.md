# Send Console — human-assisted DM sending (compliant Phase 7)

A small web queue for sending IG/FB/LinkedIn DMs by hand. The pipeline drafts and a human
approves in Discord; approved DMs land here. For each one the operator copies the text, sends
it from the real app while genuinely logged in, and marks it sent. No browser automation, no
proxies, no evasion — the sending is done by a person, so there's nothing for a platform to
detect.

## Run

```bash
pip install -r requirements.txt
DATABASE_URL=... ANTHROPIC_API_KEY=... DM_DAILY_CAP=20 \
  DISCORD_HOTLEAD_WEBHOOK=... uvicorn main:app --port 8095
# open http://localhost:8095
```

Docker: build from the **repo root** so `reply_triage/` and `prompts/` are in context, or use
the provided compose service.

## What it does

- `GET /` — the queue UI: approved DMs, hottest first, with Copy / Open profile / Mark sent / Skip.
- Per-channel **daily cap** (`DM_DAILY_CAP`, default 20) shown and enforced on Mark sent.
- `POST /api/sent/{id}` — status → `sent`, stamps `sent_at`, logs a `send` event.
- `POST /api/skip/{id}` — status → `skipped`.
- `POST /api/reply` `{outreach_id, text}` — paste a reply; the triage classifier tags it,
  stores it, and pings the hot-lead Discord webhook if it's `interested`.

## Why human-assisted

This replaces the anti-detect DM bot from the original spec. Same drafts, same prospects, same
audit hook — a person sends instead of a detection-evading automation. Removes the account-ban
risk entirely (a real human on a real device is real activity). Throughput ~30–50 DMs/day/operator,
around the per-account cap the bot approach used anyway. See docs/PHASE_7_DECISION.md.
