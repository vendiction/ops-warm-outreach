# SETUP_TEST.md — from extracted files to a running A→B demo

Target: prove the pipeline end-to-end at scale-of-one with **Supabase (DB) + Docker (services) +
2 IG accounts (A sends, B receives) + 1 ProtonMail (audit)**. No VPS, no warmup, no evasion.
A only ever messages B.

Work top to bottom. Each step says what it's for and how to verify it.

---

## 0. Prereqs on your machine

- [ ] Docker Desktop installed and running (`docker --version`)
- [ ] Python 3.11+ (`python3 --version`) — for running the offline tests
- [ ] `psql` client (or you'll use Supabase's SQL editor instead)
- [ ] Node 18+ (only to run the one JS test) — optional

---

## 1. Database — Supabase (replaces "stand up Postgres")

1. [ ] Create a project at supabase.com. Pick a region near you. Save the DB password.
2. [ ] Get the connection string: Project → **Connect** → **Session pooler** (port 5432).
       It looks like `postgres://postgres.<ref>:<pwd>@aws-...pooler.supabase.com:5432/postgres`.
       **Use session mode, not transaction mode (6543)** — the pooled `psycopg` code needs it.
3. [ ] Apply the 3 migrations, in order. Either:
   - **psql:**
     ```bash
     export DATABASE_URL="postgres://postgres.<ref>:<pwd>@...pooler.supabase.com:5432/postgres"
     psql "$DATABASE_URL" -f db/migrations/001_initial_schema.sql
     psql "$DATABASE_URL" -f db/migrations/002_hitl_posted_flag.sql
     psql "$DATABASE_URL" -f db/migrations/003_analytics_views.sql
     ```
   - **or** paste each file into Supabase → SQL Editor → Run, in order.
4. [ ] Verify: `psql "$DATABASE_URL" -c "\dt"` shows 5 tables (leads, lead_enrichment,
       lead_audits, lead_outreach, outreach_events).

---

## 2. `.env` — fill only what the test needs

```bash
cp .env.example .env
```
Fill these (leave the rest blank for now):

- [ ] `DATABASE_URL` = your Supabase session string
- [ ] `ANTHROPIC_API_KEY` = your key (scoring, drafting, triage)
- [ ] `DISCORD_BOT_TOKEN` + `DISCORD_HITL_CHANNEL_ID` = the new bot (step 4)
- [ ] `DISCORD_HOTLEAD_WEBHOOK` = a Discord webhook URL for interested-reply pings (channel →
      Edit → Integrations → Webhooks → New)
- [ ] `PROTONMAIL_POOL_FILE=./secrets/protonmail_pool.json` (step 3)
- [ ] `DM_DAILY_CAP=20`

Confirm `.env` is gitignored: `git status` must NOT list it.

---

## 3. ProtonMail — the one audit inbox

1. [ ] Have your ProtonMail address ready with IMAP access:
   - Free plan → install **ProtonMail Bridge**, which exposes IMAP at `127.0.0.1:1143`.
   - Mail Plus ($4/mo) → direct IMAP, no Bridge.
2. [ ] Create `secrets/protonmail_pool.json` (folder is gitignored):
   ```json
   [{"address":"you@proton.me","imap_host":"127.0.0.1","imap_port":1143,"user":"you@proton.me","pass":"<bridge-or-app-password>"}]
   ```
3. [ ] Smoke-test IMAP:
   ```bash
   cd audit_worker && pip install -r requirements.txt
   python3 -c "from imap_tools import MailBox; MailBox('127.0.0.1',port=1143).login('you@proton.me','<pass>'); print('IMAP OK')"
   ```

---

## 4. Discord bot (new, dedicated)

Follow `hitl_bot/README.md` → "Create a brand-new bot + token": create the app, add the bot,
reset/copy the token, **no privileged intents**, invite with View Channels + Send Messages +
Embed Links + Read History, enable Developer Mode, copy the review channel ID.
- [ ] `DISCORD_BOT_TOKEN` and `DISCORD_HITL_CHANNEL_ID` in `.env`.

---

## 5. Sanity-check the code before running anything (no accounts needed)

These prove the build is intact on your machine:

```bash
node scripts/test_icp_filter.mjs                     # 10/10
python3 scrapers/funnel_detector/test_funnel_detector.py   # 6/6
python3 audit_worker/test_audit_logic.py             # 18/18
python3 reply_triage/test_classifier.py              # 8/8
```

---

## 6. Bring up the services with Docker

For the test you need: the **HITL bot** and the **send console** (and optionally the audit
worker). Supabase is the DB, so ignore the Metabase/n8n bits for now.

```bash
docker compose up -d hitl_bot send_console
docker compose logs -f hitl_bot        # should log "logged in as ..."
```
- [ ] Send console reachable: open http://localhost:8095 (empty queue is fine).
- [ ] Bot shows online in your Discord server.

> n8n (sourcing/enrich/score/draft workflows) is optional for the demo — you can drive those
> steps by hand (step 7). If you want them, run n8n locally (`npx n8n` or its Docker image),
> import the JSON from `shared/n8n-templates/`, and set the Postgres + Anthropic credentials.

---

## 7. Run the A→B demo (hand-driven, minimal)

You can trigger each stage manually so you don't need every workflow wired:

1. [ ] **Seed one lead** = your IG account B, as the "prospect":
   ```sql
   INSERT INTO leads (domain, company_name, founder_ig_handle, source, icp_tier, qualification_score, is_archived)
   VALUES ('bteststore.com','B Test Co','@your_ig_account_B','manual','primary_info',18,false)
   RETURNING id;
   ```
2. [ ] **Audit (optional in test):** point the audit worker at a funnel **you control** (a throwaway
   opt-in page) using the Proton inbox, or skip and hand-write a `lead_audits` row + `gap_summary`.
   For the fast path, insert a completed audit so drafting has a gap to use.
3. [ ] **Draft:** run the drafting step (n8n `draft_outreach.json`, or call the prompt manually) to
   create a `dm_ig` draft for the lead. It lands as `status='draft'`.
4. [ ] **Approve:** the HITL bot posts it to Discord → click **Approve** → `status='approved'`.
5. [ ] **Send (human):** open http://localhost:8095 → the approved DM appears → **Copy** → open IG
   as account **A**, paste, send to account **B** → click **Mark sent**.
6. [ ] **Reply:** from account **B**, reply to the DM. Copy that reply text, and in the send console
   use the paste-a-reply action (or `POST /api/reply {outreach_id, text}`) → it classifies and, if
   interested, pings `DISCORD_HOTLEAD_WEBHOOK`.
7. [ ] **Verify the trail:**
   ```sql
   SELECT event_type, actor, occurred_at FROM outreach_events ORDER BY occurred_at;
   ```
   You should see draft → approve → send → reply.

That's the full loop proven at scale-of-one.

---

## What this test does NOT cover (by design)

- Real prospects (A only messages B), volume, LinkedIn/FB, concurrent audits (1 inbox).
- Those need more genuine accounts + the ~20-inbox pool — not more code.

## If something breaks

- `psycopg ... prepared statement` errors → you used the transaction pooler; switch to **session** (5432).
- Bot online but no drafts posted → nothing is in `status='draft'` yet; do step 3.
- IMAP login fails → Bridge not running, or wrong port (1143 for Bridge).
- Container can't reach Supabase → check `DATABASE_URL` is the pooler host and your network allows it.
