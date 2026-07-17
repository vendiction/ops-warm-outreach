# Scrapers

Small, single-purpose FastAPI + Playwright microservices that n8n calls over HTTP. Each runs
as its own Docker container on the `n8n_default` network so n8n reaches it by container name.

## Conventions (all scrapers follow these)

- **One service, one job.** `meta_ad_library` checks ad activity; Phase 2 adds `similarweb`,
  `social_posts`, `funnel_detector`. Don't merge them.
- **Never raise to n8n on a scrape failure.** Return a result object with the useful field set to
  `null` plus a `reason`. A failed scrape must not crash the workflow or block a lead — n8n reads
  `null` and proceeds. Distinguish `null` ("couldn't check") from `false`/`0` ("checked, none").
- **Proxy through IPRoyal**, rotating sticky sessions on a cadence to dodge IP rate limits.
- **Never solve CAPTCHAs.** On a checkpoint/CAPTCHA, back off, rotate session, return `null`.
  Solving them is the fastest route to a hard block.
- **Secrets from env only.** Proxy creds, tokens — never hardcoded, never logged.
- **A `/health` endpoint** on every service for the container healthcheck.
- **Port convention:** 809x range (`meta_ad_library` = 8091). Keep them distinct.

## Ports

| Service | Port | Phase |
|---------|------|-------|
| meta_ad_library | 8091 | 1 |
| similarweb | 8092 | 2 |
| social_posts | 8093 | 2 |
| funnel_detector | 8094 | 2 |

## Local smoke test (any service)

```bash
cd scrapers/<service>
pip install -r requirements.txt && playwright install chromium
uvicorn main:app --port 809x &
curl -s localhost:809x/health
curl -s -X POST localhost:809x/scrape -H 'content-type: application/json' -d '{"domain":"example.com"}'
```

## DOM fragility

These read third-party HTML whose structure changes without notice. Every service isolates its
selectors in one place and documents in its own README which function to re-check when output
looks wrong. Expect to re-tune selectors periodically — that's normal scraper maintenance, not a bug.
