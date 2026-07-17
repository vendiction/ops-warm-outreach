# Meta Ad Library Scraper (Phase 1)

Small FastAPI + Playwright service. Given a domain, checks whether the company is
**currently running Meta ads** — a spending signal used during sourcing.

## Run

```bash
docker build -t ops-wo-meta-scraper .
docker run -d --name meta_scraper --network n8n_default \
  -e IPROYAL_PROXY=geo.iproyal.com:12321 \
  -e IPROYAL_PROXY_USER=... -e IPROYAL_PROXY_PASS=... \
  -p 8091:8091 ops-wo-meta-scraper
```

n8n calls it at `http://meta_scraper:8091/scrape`.

## Request / response

```
POST /scrape   { "domain": "glowskin.co", "country": "US" }
->             { "domain": "...", "active_ads_count": 4, "is_advertising": true, "reason": null }
```

`is_advertising` is `null` (not `false`) when the check itself failed — a failed ad check
must never be read as "not advertising", and must never block sourcing.

## ToS / rate-limit note

The Ad Library is Meta's **public ad-transparency surface** — this reads only that public
data for competitive research, no login, no private data. It's still subject to Meta's ToS
and aggressive IP rate-limiting, so:
- Rotate IPRoyal sticky sessions every `META_SCRAPES_PER_SESSION` (default 20) requests — handled automatically.
- On a CAPTCHA/checkpoint the service backs off and returns `null`. **It never solves CAPTCHAs** — solving them is the fast path to a hard block.
- Keep total volume modest; this is a confidence signal, not a gate.

## Fragility

The ad-card CSS selectors are a heuristic and the Ad Library DOM changes often. If
`active_ads_count` looks wrong across many domains, update the selector list in `main.py`
(`scrape()`), re-test against 3–5 domains you can eyeball in a browser, redeploy.
