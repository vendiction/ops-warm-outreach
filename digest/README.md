# Digest Service — Phase 8

In-process scheduler (APScheduler) that runs two jobs against the analytics views:

- **Daily 08:00** — builds the digest and posts it to Discord.
- **Sunday 21:00** — builds a weekly PDF (reportlab) and posts it to Discord as an attachment.

No accounts needed — reads the `v_*` views and posts via the Discord webhook.

## Run

```bash
psql "$DATABASE_URL" -f ../db/migrations/003_analytics_views.sql   # views must exist first
pip install -r requirements.txt
DISCORD_DIGEST_WEBHOOK=... DATABASE_URL=... python main.py

# docker (add to docker-compose with restart: unless-stopped)
docker build -t ops-wo-digest . && docker run --env-file ../.env ops-wo-digest
```

## Env

- `DATABASE_URL` — the warm_outreach DB
- `DISCORD_DIGEST_WEBHOOK` — channel webhook for the digest
- `DIGEST_TZ` — schedule timezone (default `Asia/Manila`)

## Test the builders without waiting for the cron

```python
import main
print(main.build_daily_digest())      # returns the digest string
main.build_weekly_pdf("/tmp/r.pdf")   # writes the PDF
```

Numbers read as zero until Phases 1–7 produce real data — expected pre-launch.
