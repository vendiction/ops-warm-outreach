# Disposable Inbox Pool & Cold-Email Stack

**Owner:** Julia (creation) / Kyle (IMAP wiring) · **Blocks:** Phase 3 audit worker on real leads

Two separate inbox concerns live here:
1. **ProtonMail disposable pool** — the addresses the audit worker submits into prospect funnels
   to capture their recovery sequences.
2. **Cold-email sending stack** — the existing 15-inbox rig that Phase 5/7 send from.

---

## 1. ProtonMail disposable pool

20+ self-created accounts, IMAP enabled and verified. Credentials live in
`secrets/protonmail_pool.json` (gitignored) — **never in this file.** This doc is the registry
and the rotation policy only.

### Rotation policy (per BUILD_SPEC_0)

- Each inbox handles **max 5 audits/week**.
- **48-hour cooldown** between reuses of the same inbox.
- On an early audit failure (checkout broke, opt-in rejected), the worker returns the inbox with
  a shorter 6h cooldown so it isn't wasted.
- One inbox is only ever tied to one live audit at a time — the worker's inbox picker enforces this.

### IMAP access note

ProtonMail needs Bridge for IMAP on free accounts, which means running Bridge on the VPS.
Cheaper and simpler: put **2–3 accounts on the Mail Plus $4/mo trial** for direct IMAP without
Bridge, and rotate the highest audit volume through those. Document which accounts are Bridge vs
direct below so Kyle knows which host/port each uses.

### Registry

| # | Address | IMAP mode | IMAP verified? | Audits this week | Last used | Cooldown until |
|---|---------|-----------|----------------|------------------|-----------|----------------|
| 01 | ______@proton.me | direct (Plus) | ☐ | 0 | — | — |
| 02 | ______@proton.me | direct (Plus) | ☐ | 0 | — | — |
| 03 | ______@proton.me | bridge | ☐ | 0 | — | — |
| … | | | ☐ | | | |
| 20 | ______@proton.me | bridge | ☐ | 0 | — | — |

### IMAP verification check (run per inbox before marking verified)

```bash
python3 - <<'PY'
from imap_tools import MailBox
# creds pulled from secrets/protonmail_pool.json in real use; inline here only to smoke-test one
HOST, USER, PASS = "127.0.0.1", "user@proton.me", "app-password"  # Bridge: 127.0.0.1:1143
with MailBox(HOST, port=1143).login(USER, PASS, "INBOX") as mb:
    print("OK — INBOX reachable, message count:", len(list(mb.fetch(limit=1))))
PY
```

A pass = login succeeds and INBOX fetch returns without error. Tick the box in the registry.

---

## 2. Cold-email sending stack (existing 15-inbox rig)

Domains: `fascinatecopy.site` · `fascinatehq.online` · `usefascinate.space`

Phase 0 job is **verification only** — confirm the existing warmup is healthy before Phase 5
drafts start hitting it. Do not send campaign mail from here in Phase 0.

### Health check (last 7 days, from n8n warmup workflow logs)

- [ ] Zero hard bounces on outgoing warmup mail
- [ ] Zero spam complaints
- [ ] All 15 inboxes still authenticated (SPF/DKIM/DMARC passing)
- [ ] Per-inbox volume known, with headroom to the 50/day cap

### Inbox health registry

| Inbox | Domain | Auth OK? | Bounces 7d | Spam 7d | Current/day | Healthy? |
|-------|--------|----------|-----------|---------|-------------|----------|
| 01 | fascinatecopy.site | ☐ | | | | ☐ |
| … | | ☐ | | | | ☐ |
| 15 | usefascinate.space | ☐ | | | | ☐ |

**If any inbox is unhealthy:** pause it, note it here, do **not** delete it, and do **not** route
Phase 5 sends through it until it recovers.
