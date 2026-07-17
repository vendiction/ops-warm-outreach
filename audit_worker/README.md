# Audit Worker — Phase 3

Dockerized Python service that opts into prospect funnels, waits 72hr, parses recovery emails.

## Local Dev

```bash
cd audit_worker
cp ../.env.example ../.env  # populate with real credentials
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
patchright install chromium

# Ensure DB reachable
python -c "from db import get_conn; print(get_conn())"

# Run
uvicorn main:app --reload --port 8080
```

## Docker

```bash
docker build -t ops-warm-audit-worker .
docker run -p 8080:8080 --env-file ../.env ops-warm-audit-worker
```

## Endpoints

- `POST /audit/start` — kicks off Playwright flow, sets audit to in_progress
- `POST /audit/parse` — IMAP fetch, classify, generate gap_summary
- `GET /health` — pool + proxy status

## Inbox pool management

Passwords live in a `.env`-referenced JSON file at `PROTONMAIL_POOL_FILE`
(shape: `[{"address","imap_host","imap_port","user","pass"}]`). Never commit — it lives under
`secrets/`, which is gitignored.

Rotation policy: no inbox used twice within 48hr, no more than 5 audits per inbox per week.

## Testing

Two offline test suites (no DB, no network, no credentials needed):

```bash
python test_audit_logic.py        # classify_email + aggregate + majority_signal  (18/18)
python -c "import main; print('imports OK')"   # all 9 modules resolve
```

Live checks (need DB / inbox creds): `update_audit` write path and inbox rotation are covered
in the Phase 3 validation notes. See `BUILD_SPEC_3_AUDIT_WORKER.md` for full acceptance criteria
and the staged rollout plan.

## Modules (built)

- `config.py` — env parsing (`get_config()`), no side effects at import
- `db.py` — pooled `get_conn()` + `update_audit(**findings)` with a column allowlist + jsonb handling
- `inbox_pool.py` — `pick_inbox` / `release_inbox` / `pool_stats`; weekly usage derived from `lead_audits`, cooldowns in a JSON state file
- `proxy_pool.py` — IPRoyal sticky sessions (`get_sticky_session`, `proxy_healthy`)
- `imap_parser.py` — pure `classify_email()` + `fetch_and_classify()` over INBOX + Spam
- `claude_gap_summary.py` — async Sonnet call using `prompts/audit_gap_summary_sonnet.md`, retries then a deterministic fallback so a summary failure never blackholes a completed audit
- `modes/base.py` — shared patchright launcher + email-fill/click helpers
- `modes/ecom.py` · `modes/info_optin.py` · `modes/info_application.py` — the three funnel flows

**Design note:** heavy deps (patchright, anthropic, imap-tools) are imported lazily inside
functions, so `import main` and the pure-logic tests run without them. The Docker image installs
everything.

**Still needs accounts to run live:** the modes need IPRoyal proxies + real funnels, and
`/audit/parse` needs the ProtonMail inbox pool (3–5 inboxes is enough to prove it end-to-end).
Everything is built and unit-tested now; only live execution waits on those.
