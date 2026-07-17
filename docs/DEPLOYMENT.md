# OPS-WARM-OUTREACH — Deployment / Launch Runbook

How to go from "tested on a laptop" to "the belt runs itself." Follow top to bottom.
The system is a set of independent workers coordinated through the database — flip each to
Active and it runs on its own schedule. There is no single "run" button.

---

## 0. What you're buying / setting up (the gates)

| Item | Cost | Unlocks |
|------|------|---------|
| Apollo Basic | $49/mo | Automatic sourcing (people-search API) |
| Inbox pool — catch-all domain + 1 IMAP mailbox (Migadu ~$19/yr or Zoho ~$1/mo) | ~$2–5/mo | Concurrent audits (unlimited `audit1@`, `audit2@`… addresses) |
| Always-on host (Railway / Render / Fly.io / VPS) | ~$5–20/mo | Belt keeps running (esp. the 72h audit) |
| Warmed sender accounts (genuine, aged) | time | Sending DMs to real prospects (30–45 day clock) |
| Anthropic API | usage (~$20–50/mo) | Scoring / drafting / triage |

Proxies (IPRoyal): **only if** the audit worker gets IP-blocked at volume. Buy reactively.

Two milestones:
- **A — belt runs to Discord approval:** needs Apollo + inbox pool + host + all workers deployed.
  No sender accounts. ~$53/mo + a day of setup.
- **B — live sending:** A + warmed accounts + the human operator.

---

## 1. Database (already done for testing)

Supabase project, session pooler string (port 5432), 3 migrations applied. For production you
may move to a dedicated Postgres, but Supabase is fine to launch on.

---

## 2. Inbox pool (replace the single test inbox)

1. Point a **catch-all domain** at one IMAP mailbox (Migadu/Zoho/Fastmail).
2. Populate `secrets/protonmail_pool.json` with N addresses, all pointing at the **same** IMAP
   server (that's the only change from the "20 separate accounts" assumption):
   ```json
   [
     {"address":"audit1@yourdomain.com","imap_host":"imap.provider.com","imap_port":993,"user":"pool@yourdomain.com","pass":"APP_PASS"},
     {"address":"audit2@yourdomain.com","imap_host":"imap.provider.com","imap_port":993,"user":"pool@yourdomain.com","pass":"APP_PASS"}
   ]
   ```
   (Start with 3–5; grow toward ~20 as prospect volume grows.)

---

## 3. Deploy the services

The compose file currently runs `hitl_bot`, `send_console`, `digest`, `metabase`. Before launch,
also run the scrapers and the audit worker (wire them into `docker-compose.yml` as services, or
run them as containers):

- `scrapers/funnel_detector` → port 8094
- `scrapers/similarweb` → 8092 (needs `SIMILARWEB_API_KEY`, optional)
- `scrapers/social_posts` → 8093 (needs a scraping persona; returns [] without one)
- `audit_worker` → the browser + IMAP worker (needs Playwright/Chromium in the image)

Note for n8n → scraper calls: n8n can't reach `localhost`; use `host.docker.internal:8094`
(Docker Desktop) or put them on the same Docker network.

Set the compose network to `driver: bridge` (the repo default reverts to `external: true` on
every re-extract — change it after extracting).

---

## 4. Import + wire + activate all 9 workflows in n8n

Import from `shared/n8n-templates/`:
`source_apollo`, `source_meta_ad_library`, `source_storeleads`, `enrich_new_leads`,
`score_qualified_audits`, `draft_outreach`, `send_cold_email`, `triage_email_replies`.

Credentials to create once and select on each node:
- **Postgres** (`Postgres · warm_outreach`): Supabase session pooler; SSL = Require + "Ignore SSL
  Issues" ON (fixes the self-signed-cert error).
- **Anthropic** (Header Auth): Header **Name** = `x-api-key`, Value = your key. (Not the
  credential name — that was a real gotcha.)
- **Cold Email IMAP** (for reply triage) and the **cold-email send webhook** env
  (`COLD_EMAIL_SEND_WEBHOOK`) pointing at the existing 15-inbox stack.

Then **toggle each workflow to Active**. Schedules start immediately. Recommended intervals are
in each workflow's sticky note (source hourly, enrich ~10m, score ~1m, draft ~5m, send ~15m).

---

## 5. Deploy to an always-on host

The 72h audit and the timers require the stack to survive the laptop being off.
- Easiest no-VPS path: **Railway / Render / Fly.io** — connect the repo, set env vars, deploy.
- Or a small **VPS** (Hetzner/DigitalOcean/Contabo) running Docker Compose.
- The audit worker (real browser) is the awkward piece — keep it on a host that can run Chromium.

Set all env vars from `.env.example` on the host (DATABASE_URL, ANTHROPIC_API_KEY, Discord
token + webhooks, APOLLO_API_KEY, PROTONMAIL_POOL_FILE, DM_DAILY_CAP, COLD_EMAIL_SEND_WEBHOOK…).

---

## 6. Warm the sender accounts (start NOW — the real bottleneck)

Even in the human-send model, brand-new accounts sending cold DMs get flagged. Age genuine
accounts for 30–45 days before real sending. This clock runs in parallel with everything above,
so **start it first** — it gates go-live regardless of how fast the rest is done.

---

## 7. Go live in the right order

1. **Email-first** (fastest — no warmup, no sender accounts, auto-dispatch via the 15-inbox
   stack). Verify the inboxes are warm, then activate `send_cold_email`.
2. **DMs** once accounts are aged — the human works the send console daily.
3. Keep a human on: Discord approvals + send console + hot-lead replies (~30–45 min/day).

---

## 8. Day-2 operations

- **Operator (daily):** Discord approve → send console → work 🔥 replies. Never touches n8n or a terminal.
- **Owner (occasional):** re-tune scrapers when sites change (you did this for `image/` and `cf-`),
  swap restricted accounts, tune prompts from reject reasons, watch spend + deliverability.
- **Audit-mode note:** funnels with reCAPTCHA get marked "blocked" (skip or human-assist). Funnels
  with double opt-in are detected as a finding.

---

## Quick "is it running?" checklist

- [ ] All 9 workflows show **Active** in n8n
- [ ] Scrapers + audit worker reachable (health endpoints)
- [ ] `hitl_bot` online in Discord; `send_console` loads
- [ ] Apollo pulling leads (check the `leads` table growing)
- [ ] Audits completing (check `lead_audits`)
- [ ] Drafts posting to Discord
- [ ] Everything on the always-on host, not the laptop
