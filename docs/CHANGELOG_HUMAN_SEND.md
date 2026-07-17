# Changelog — Human-Assisted Send (compliant Phase 7)

## What we're trying to achieve

The same outcome as the original plan — **audit-personalized outreach to $100K+/mo founders that
books screen-share calls** — but with the account-burning, ToS-evading DM bot removed. Email sends
fully automatically; IG/FB/LinkedIn DMs are sent by a human from real accounts. Same prospects,
same audit hook, same copy; no detection-evasion anywhere.

## What changed

**Removed / not built**
- The anti-detect DM sender (`sender/channels/*`, `dolphin.py`, `proxy.py`) — the Dolphin +
  residential-proxy + timing-jitter engine whose job was evading platform bot-detection. Not built.
  Rationale in `docs/PHASE_7_DECISION.md`.
- The requirement for 7 warmed persona accounts + 30–45 day warmup, and residential proxies **for
  sending**. Not needed when a human sends from a real account. (ProtonMail + audit worker unchanged.)

**Added (all compliant, all validated)**
- `send_console/` — a small web queue. Approved IG/FB/LinkedIn drafts appear with Copy / Open
  profile / Mark sent / Skip. Per-channel **daily cap** enforced (`DM_DAILY_CAP`, default 20). A
  human copies the text and sends from the real app. UI on `:8095`.
- `reply_triage/classifier.py` — shared Haiku reply classifier (interested / objection /
  not_interested / unclear / auto_reply), using `prompts/reply_triage_haiku.md`. Used by both the
  console (paste a DM reply) and the email-triage workflow.
- `shared/n8n-templates/send_cold_email.json` — automated cold-email dispatch with the 4-touch
  cadence (step1 now; step2 +3d, step3 +2d, step4 +3d), through the existing 15-inbox stack webhook.
- `shared/n8n-templates/triage_email_replies.json` — IMAP-triggered email reply triage: match
  lead, classify, attach to the sent email, ping the hot-lead Discord channel if interested.
- `db/migrations` unchanged; new services added to `docker-compose.yml` (`send_console`).

## The loop now

```
source → enrich → audit (ProtonMail) → score → draft → approve (Discord)
      → cold email: SENT AUTOMATICALLY (15-inbox stack)
      → IG/FB/LinkedIn: HUMAN sends from send console
      → reply triage (Haiku) → interested → hot-lead ping → human books the call
```

## What each channel does now

| Channel | Send | Automated? |
|---------|------|------------|
| Cold email | `send_cold_email.json` → 15-inbox stack | ✅ fully |
| IG / FB / LinkedIn DM | `send_console` (human copy-paste) | ⚙️ human, ~30–45 min/day |
| Reply triage (email) | `triage_email_replies.json` | ✅ fully |
| Reply triage (DM) | send console "paste reply" → same classifier | ⚙️ human pastes, auto-classifies |

## Validation

- Reply classifier parse/validate: 8/8 offline.
- Send console (fresh DB): 10/10 — queue lists approved DMs, uses `approved_body`, resolves
  handles, enforces the daily cap (3rd send blocked at cap), skip, and reply classify+store+log.
- Cold-email cadence gate (live PG): step1 immediate; step2 due only after step1 sent + 3 days;
  not due at 1 day. Pass.
- Both workflows: valid n8n JSON, embedded JS passes syntax check, triage prompt embedded verbatim.

## What still needs accounts (unchanged by this)

- 2 IG accounts + 1 ProtonMail is enough to demo the whole loop (A→B send via console, one audit).
- Real volume still wants the ProtonMail pool (~20) for concurrent audits and more sender accounts
  (now just genuine accounts, not warmed-to-evade personas).
- Cold email needs the 15-inbox stack verified warm before turning on `send_cold_email`.
