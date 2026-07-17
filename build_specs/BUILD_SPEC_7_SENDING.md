# BUILD_SPEC_7 — Sending & Reply Triage

**Phase:** 7
**Timeline:** Week 5–6
**Owner:** Kyle
**Depends on:** Phase 6 (approved drafts), Phase 0 (warmed accounts, proxies, Dolphin, cold email stack)
**Blocks:** Phase 8 (metrics need sends + replies)

---

## Objective

Dispatch approved messages within compliance limits, capture replies, classify them, and route hot conversations to a human before they go cold.

If Phase 7 sends without respect for rate limits or fails to surface interested replies within minutes, everything upstream is wasted.

---

## Scope

### In
1. In-house Playwright DM sender for IG / LinkedIn / FB
2. Cold email dispatcher hooking existing 15-inbox n8n stack
3. Per-profile daily quota enforcement (hard cap 10–20 DMs/day/profile)
4. Human-timing jitter, session rotation, soft-block cooldown
5. Reply capture: IMAP for email, Playwright inbox scrape for DMs
6. Claude Haiku reply classifier
7. Discord "hot lead" channel notification with full context
8. Ladder-of-Tiny-Yeses playbook doc for human operator

### Out
- Actually replying to prospects (human does this)
- Booking calls (Cal.com handles this)

---

## Acceptance Criteria

- [ ] Approved DM drafts sent within 60 min of approval (jittered within reasonable business hours per persona timezone)
- [ ] Per-profile daily send cap enforced (10–20 DMs/day, configurable per profile)
- [ ] Cold email sends respect existing 15-inbox stack quotas (20/day/inbox ramping to 50)
- [ ] Soft-block detection: if IG returns "action blocked" or LinkedIn shows warning, set profile to `cooldown` for 2hr, log to `outreach_events` (reuse M5 executor pattern)
- [ ] Reply capture polls every 5 min, writes to `lead_outreach.reply_body` + `reply_received_at`
- [ ] Reply classifier runs within 30s of capture, sets `reply_classification`
- [ ] `interested` replies post to `#hot-leads` Discord channel with full thread context + @mention operator
- [ ] Zero automated responses to prospects — every reply goes through human

---

## Files Touched

```
sender/
├── Dockerfile
├── requirements.txt
├── main.py                        # scheduler + orchestrator
├── channels/
│   ├── __init__.py
│   ├── base.py                    # DM channel ABC
│   ├── instagram.py
│   ├── linkedin.py
│   └── facebook.py
├── quota.py                       # per-profile daily counter
├── dolphin.py                     # Dolphin{anty} local API client
├── proxy.py                       # IPRoyal sticky session mgmt
└── README.md

reply_triage/
├── Dockerfile
├── requirements.txt
├── main.py                        # IMAP + Playwright inbox pollers
├── classifier.py                  # Haiku call
└── README.md

docs/
└── hot_lead_playbook.md           # Ladder of Tiny Yeses for operator
```

---

## Implementation Notes

### Sender orchestration

Runs on n8n cron every 15 min:
1. Query `SELECT * FROM lead_outreach WHERE status = 'approved' AND channel LIKE 'dm_%' ORDER BY approved_at LIMIT N`
2. For each: check profile quota, check cooldown, jitter timing
3. Dispatch to appropriate channel sender
4. On success: UPDATE `status = 'sent'`, `sent_at = NOW()`, `send_metadata`
5. On failure: log to `outreach_events`, do NOT auto-retry (surface for human review)

### Dolphin{anty} integration

Dolphin exposes a local HTTP API for launching + closing browser profiles.

```python
# dolphin.py sketch
async def launch_profile(profile_id: str) -> dict:
    resp = await httpx.post(
        f"{DOLPHIN_API_URL}/v1.0/browser_profiles/{profile_id}/start",
        headers={"Authorization": f"Bearer {DOLPHIN_TOKEN}"}
    )
    return resp.json()  # returns {port, wsEndpoint, ...}

async def close_profile(profile_id: str):
    await httpx.post(
        f"{DOLPHIN_API_URL}/v1.0/browser_profiles/{profile_id}/stop",
        headers={"Authorization": f"Bearer {DOLPHIN_TOKEN}"}
    )
```

Then connect Playwright to Dolphin's port:
```python
browser = await p.chromium.connect_over_cdp(f"ws://localhost:{port}")
```

### Rate limit enforcement (critical)

Per-profile daily quota table (add to migration 003):
```sql
CREATE TABLE profile_send_log (
  profile_id TEXT NOT NULL,
  send_date DATE NOT NULL,
  sends_count SMALLINT NOT NULL DEFAULT 0,
  cooldown_until TIMESTAMPTZ,
  PRIMARY KEY (profile_id, send_date)
);
```

Before every send:
```python
def can_send(profile_id: str) -> bool:
    row = fetch_or_create(profile_id, today())
    if row.cooldown_until and row.cooldown_until > now():
        return False
    if row.sends_count >= DAILY_CAP:
        return False
    return True
```

**Non-obvious:** IG's soft-block signal isn't always an obvious error — sometimes it's a "captcha" screen shown to the persona's account, sometimes it's just DMs silently not delivering. Reply-back monitoring in Phase 7 is the truth signal: if a persona sends 20 DMs and gets zero replies over 3 days, cooldown that profile for a week and investigate.

### Timing jitter

Each persona should have a fake schedule:
- `ig_persona_01`: sends 09:00–11:00 and 14:00–16:00 US Eastern
- `ig_persona_02`: sends 10:00–12:00 and 15:00–17:00 US Central
- etc.

Randomize per-send delay 2–8 min. Never send 2 DMs from same profile within 90 sec.

### Cold email dispatch

Approved drafts with `channel = 'cold_email'` don't go through Playwright — they push to the existing n8n cold email stack via webhook:

```json
POST https://n8n.<internal>/webhook/cold-email-send
{
  "lead_id": 123,
  "outreach_id": 456,
  "to_email": "founder@example.com",
  "subject": "...",
  "body": "...",
  "from_domain_hint": "fascinatecopy.site"
}
```

Existing n8n workflow handles inbox selection, warmup ramp, sending, and bounce tracking. Just make sure `outreach_id` round-trips so we can UPDATE `lead_outreach.status = 'sent'`.

### Reply capture

**For email replies:** IMAP poll on all 15 inboxes every 5 min. Match inbound to `lead_outreach` by `from_email` + subject thread. Existing cold email stack may already do this — reuse if possible.

**For DM replies:** Playwright polls each persona's DM inbox every 15 min. This is expensive (session launch + scroll + parse) — only do it for personas that have sent DMs in the last 7 days.

### Reply classification

Prompt: `prompts/reply_triage_haiku.md`. Returns strict JSON:
```json
{
  "classification": "interested" | "objection" | "not_interested" | "unclear" | "auto_reply",
  "reasoning": "one sentence",
  "urgency": "high" | "normal" | "low"
}
```

`interested` with `urgency: high` triggers immediate Discord @mention.

### Hot lead playbook

`docs/hot_lead_playbook.md` documents the human takeover flow — the Ladder of Tiny Yeses in practice, with example responses. This is the actual sales playbook, not code. Jon should own the content, Kyle just creates the file scaffold.

---

## Test Approach

**Staged rollout:**
- Day 1: 3 DMs/day/profile, manual monitoring of every send
- Day 3: 8 DMs/day if no blocks
- Day 7: 15 DMs/day if reply rate >0
- Day 14: 20 DMs/day if account health stable

**Reply latency test:** Have someone (Kevin or a friend) reply to a test DM. Confirm hot-lead notification hits Discord within 10 min.

---

## LOE Estimate

- Sender scaffold + Dolphin integration: 6 hr
- Per-channel senders (IG + LinkedIn + FB): 15 hr
- Rate limit + cooldown logic: 4 hr
- Cold email webhook integration: 3 hr
- Reply capture (email + DM): 8 hr
- Classifier + Discord notification: 4 hr
- Staged rollout monitoring: 4 hr (spread over 2 weeks)

**Total: ~44 hours.**

---

## Escalation

- If a persona gets banned during rollout → post-mortem in Discord, adjust warmup activity mix, do NOT immediately buy new accounts
- If reply rate is <1% after week 2 at production volume → drafting quality issue, escalate to prompt tuning
- If hot-lead Discord notification latency >15 min → check reply-capture poll interval, likely IMAP throttling
