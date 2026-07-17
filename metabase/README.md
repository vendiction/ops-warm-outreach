# Metabase Dashboards — Phase 8

Three dashboards over the `v_*` analytics views (from `db/migrations/003_analytics_views.sql`).

Rather than ship brittle, version-specific dashboard JSON, this is the build recipe: create
each card as a Metabase question on the named view, then arrange into the dashboard. Once built,
use Metabase's own export (Settings → Admin → Serialization, or the API) to snapshot the
dashboards into `metabase/dashboards/*.json` for version control.

## One-time setup

1. In Metabase, add the warm_outreach database as a data source using the **read-only** role
   (`METABASE_RO_USER` from `.env`, created in BUILD_SPEC_0). Read-only keeps a dashboard query
   from ever mutating pipeline data.
2. Admin → Table Metadata: confirm the `v_*` views are visible. If not, sync the schema.
3. Build the cards below. Each card = one question on one view.

---

## Julia — Daily Operations

Purpose: run the day in one screen. Refresh every 5 min.

| Card | View | Viz |
|------|------|-----|
| Drafts waiting (by channel) | `v_hitl_queue` | table: channel, drafts_waiting, oldest_wait_hours |
| Oldest draft wait | `v_hitl_queue` | number: MAX(oldest_wait_hours) |
| Today's sends by channel | `v_channel_reply_rates` (filter sent_day = today) | bar |
| Today's replies | `v_channel_reply_rates` | number: SUM(interested) / SUM(replied) |
| Audit success (7d) | `v_audit_success_7d` | gauge: success_pct (green >75, yellow 50–75, red <50) |
| Inbox pool | `v_inbox_health` | number: COUNT available vs COUNT(in_cooldown) |

## Jon — Weekly Strategy

Purpose: "are we on track?" in 30 seconds.

| Card | View | Viz |
|------|------|-----|
| Conversion funnel (7d) | `v_conversion_funnel` | funnel: sourced → enriched → audited → qualified → contacted → interested_replies |
| Interested-reply trend | `v_channel_reply_rates` | line: interested over sent_day |
| Score distribution | `v_score_distribution` | bar histogram, colored by tier |
| Reply rate by channel | `v_channel_reply_rates` | table: channel, replied/sent, interested/sent |
| Top rejection reasons | `v_reject_reasons` | row chart |

> Cost-per-booked-call needs spend inputs (Anthropic + IPRoyal). Add a small manual
> `weekly_costs` table or a Metabase model once real spend exists; it's a Phase 8 follow-up,
> not a blocker.

## Kyle — Technical / Prompt Performance

| Card | View | Viz |
|------|------|-----|
| Audit failures by reason | `v_audit_health` (filter audit_status='failed') | row chart on failure_reason |
| Daily pipeline pulse | `v_daily_pipeline` | stacked area by event_type |
| Draft → reject rate | `v_daily_pipeline` (draft vs draft_failed / rejected) | line |
| Score sub-distribution | `v_score_distribution` | box/hist |

---

## Health thresholds (so a problem is visible, not buried)

- **Audit success (7d) < 60%** → the moat is degrading; check `v_audit_health` failure reasons.
- **HITL oldest wait > 12h** → drafts backing up; Julia needs to review or volume is too high.
- **Interested-reply rate drops week-over-week** → prompt/targeting drift; pull `v_reject_reasons`.

## Daily digest

The `digest/` service posts the same headline numbers to Discord at 08:00 and a weekly PDF
Sunday 21:00 — so the dashboard is for drill-down, the digest is the push. Both read these views.
