# Test Setup vs. Launch Setup

What was used to **validate** the system (free / local / scale-of-one) versus what must be
**swapped in for launch** (production). Everything in the "Tested with" column was proven to
work; the "Launch needs" column is the production equivalent.

Companion to `SETUP_TEST.md` (how the test rig was built) and `DEPLOYMENT.md` (the launch runbook).

---

## Component-by-component

| Component | Tested with | Launch needs | Why it changes |
|-----------|-------------|--------------|----------------|
| **Database** | Supabase free tier (session pooler, port 5432) | Same Supabase, or a dedicated Postgres | Free tier is fine to launch on; upgrade only if volume demands |
| **Compute / host** | Docker on a Windows laptop | Always-on host (Railway / Render / Fly.io / VPS) | Laptop can't survive the 72h audit or run 24/7. **This is the #1 launch change.** |
| **Sourcing** | Apollo Basic ($49) — real, working | Same Apollo Basic | Already the production tool; no change |
| **Audit inbox** | 1 free Zoho inbox (IMAP, app password) | Catch-all domain + 1 mailbox (Migadu ~$19/yr or Zoho ~$1/mo) → many `audit1@…` addresses | One inbox audits one funnel at a time; a pool enables concurrent audits at volume |
| **`secrets/protonmail_pool.json`** | Placeholder / single Zoho inbox | Real pool file pointing all addresses at the catch-all IMAP | The file name is legacy; it's just the inbox pool |
| **Test funnel** | Free MailerLite page we controlled | N/A — real prospects' funnels | Only needed to prove the audit; gone at launch |
| **Sender accounts (DMs)** | 2 IG accounts (A→B), no warmup | Genuine, **warmed** accounts (30–45 days) | **The real bottleneck.** New accounts sending cold DMs get flagged. Start warming now. |
| **Cold-email sending** | Logic only (not sent) | 15-inbox stack, verified warm + send webhook | Deliverability + warmup can't be tested until live |
| **Drafting / scoring** | Real Anthropic API | Same | No change |
| **Discord HITL + digest** | Real Discord webhooks/bot | Same | No change |
| **Send console** | Local `:8095` | Same, on the host | Runs wherever deployed |
| **Scrapers** | funnel_detector run live; similarweb/social **not running** | Run all of them | Thin enrichment → low scores. Run every scraper so scoring isn't skewed. |
| **`.env`** | Local file, real keys | Same keys set on the **host** | Secrets live where deployed, not on the laptop |
| **Workflows** | Run manually + on 1-min test timers | All 10 imported, sane intervals, **Active** on the host | 1-min timers were for testing; use production intervals |

---

## What was proven with the test rig (so you don't re-test it)

Every stage below was validated on the test setup above and **transfers to launch unchanged**
(same code, environment-independent):

- Sourcing (Apollo search → reveal → real founder in DB)
- Enrichment (real sites, funnel-type detection)
- Audit / moat (real funnel opt-in → IMAP → classify → gap) — for opt-in funnels
- **Option C** — application funnels → synthetic structural gap → belt
- Scoring, drafting (DM + cold email), HITL (all 5 actions), reply triage, analytics digest
- **The automatic belt** — stages hand off on timers with no manual clicks
- Full path: Apollo → Discord → console

## What the test rig could NOT prove (only launch reveals)

- **Durability over days** — the 72h audit surviving, containers staying up. Test rig ran minutes, not days.
- **Volume / concurrency** — tested with 1 lead, not 80/day. Race conditions, rate limits, credit burn only show at scale.
- **Deliverability** — inbox vs spam at real send volume. Completely untestable without warmed accounts sending.

These are not gaps in testing — they are inherently launch-only. The mitigation is a **soft
launch**: start at 5–10 leads/day, watch the digest (audit success rate, reply rates, inbox
health), fix what breaks, then scale.

---

## The launch swap-list (ordered)

1. **Start warming sender accounts** — 30–45 day clock, the only thing money can't accelerate. Do this first.
2. **Set up the catch-all inbox pool** — cheap domain + mailbox → populate `protonmail_pool.json`.
3. **Deploy to an always-on host** — move Docker stack off the laptop; set `.env` on the host.
4. **Run all scrapers** (not just funnel_detector) so scores are accurate.
5. **Import all 10 workflows**, set production intervals, wire credentials, toggle Active.
6. **Verify the 15 cold-email inboxes are warm** → live-test `send_cold_email`.
7. **Soft launch** small; watch the digest; scale when stable.

Everything else (Apollo, DB, Anthropic, Discord, console, drafting logic) is already the
production version — it doesn't change from test to launch.

---

## Cost: test vs. launch

| | Test | Launch (steady state) |
|--|------|----------------------|
| Database | $0 (Supabase free) | $0–25 |
| Host | $0 (laptop) | $5–20/mo |
| Sourcing | $49 (Apollo) | $49/mo |
| Inbox pool | $0 (1 free Zoho) | $2–5/mo |
| Anthropic | existing key | $20–50/mo usage |
| Sender accounts | $0 (2 IG) | time (warmup) + any account costs |
| **Total** | **~$49** | **~$75–125/mo** + operator time |
