# social_posts (Phase 2, port 8093) — ⚠️ ACCOUNT-GATED

Pulls the prospect's 3 most recent IG/LinkedIn posts for real personalization in Phase 5.

**This is the one Phase 2 scraper that needs a warmed persona to run.** Until a dedicated
SCRAPING persona (its own Dolphin profile, separate from the Phase 7 DM personas) is assigned
via `SCRAPE_IG_DOLPHIN_PROFILE` / `SCRAPE_LI_DOLPHIN_PROFILE`, it returns `[]` with
`reason="no_scraping_persona_configured"`. The enrichment workflow treats that as non-fatal —
enrichment still completes, `recent_social_posts` is just empty. So you can ship the whole
pipeline now and this fills in the moment a scraping persona graduates.

**Hard rules (BUILD_SPEC_2):**
- Scraping persona ≠ DM persona. Never reuse.
- Cap 30 profile visits/day/persona.
- On a login-wall/checkpoint: return [], never solve it.

The actual `_scrape_ig` / `_scrape_li` bodies are the integration point — they reuse the
Phase 7 Dolphin+Playwright executor pattern and get wired when a persona exists.
