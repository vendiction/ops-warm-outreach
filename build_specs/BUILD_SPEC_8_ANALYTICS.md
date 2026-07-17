# BUILD_SPEC_8 — Analytics Dashboard

**Phase:** 8
**Timeline:** Week 6
**Owner:** Kyle
**Depends on:** Phases 1–7 producing real data
**Blocks:** Nothing (final phase)

---

## Objective

Give Jon and Julia visibility into whether the system is working, without either of them writing SQL.

Metabase over Postgres. Daily digest to Discord. Weekly deep-dive to Jon.

---

## Scope

### In
1. Postgres views encapsulating common metrics
2. Metabase collections for:
   - Daily operations (Julia's dashboard)
   - Weekly strategy (Jon's dashboard)
   - Prompt performance (Kyle's dashboard)
3. Daily 8am Discord digest
4. Weekly Sunday-night PDF report to Jon

### Out
- Anything predictive (no forecasting models in MVP)
- Attribution beyond channel-level (no per-prompt-version cohorts in MVP)

---

## Acceptance Criteria

- [ ] All Postgres views deploy cleanly via migration script
- [ ] Metabase dashboards render without slow queries (each panel <2s)
- [ ] Daily digest posts to Discord at 8am with core numbers
- [ ] Jon can answer "did we make progress this week?" in <30 seconds from his dashboard
- [ ] Bottlenecks visible: if audit failure rate spikes, if reply rate drops, if a persona is dead — dashboard shows it

---

## Files Touched

```
db/migrations/
  └── 004_analytics_views.sql
metabase/
  ├── dashboards/                  # exported dashboard JSON
  │   ├── julia_daily.json
  │   ├── jon_weekly.json
  │   └── kyle_technical.json
  └── README.md
digest/
├── Dockerfile
├── requirements.txt
├── main.py                        # cron 8am + Sunday 9pm
└── README.md
```

---

## Implementation Notes

### Core Postgres views

```sql
CREATE VIEW v_daily_pipeline AS
SELECT
  DATE(e.occurred_at) AS day,
  e.event_type,
  COUNT(*) AS n
FROM outreach_events e
WHERE e.occurred_at >= NOW() - INTERVAL '30 days'
GROUP BY 1, 2;

CREATE VIEW v_conversion_funnel AS
SELECT
  DATE(l.created_at) AS source_day,
  COUNT(*) FILTER (WHERE NOT l.is_archived) AS sourced,
  COUNT(*) FILTER (WHERE le.enrichment_status = 'complete') AS enriched,
  COUNT(*) FILTER (WHERE la.audit_status = 'complete') AS audited,
  COUNT(*) FILTER (WHERE l.qualification_score >= 15) AS qualified,
  COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM lead_outreach lo WHERE lo.lead_id = l.id AND lo.status = 'sent')) AS contacted,
  COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM lead_outreach lo WHERE lo.lead_id = l.id AND lo.reply_classification = 'interested')) AS interested_replies
FROM leads l
LEFT JOIN lead_enrichment le ON le.lead_id = l.id
LEFT JOIN lead_audits la ON la.lead_id = l.id
GROUP BY 1;

CREATE VIEW v_audit_health AS
SELECT
  DATE(la.completed_at) AS day,
  la.audit_status,
  la.failure_reason,
  COUNT(*) AS n
FROM lead_audits la
WHERE la.completed_at IS NOT NULL
  AND la.completed_at >= NOW() - INTERVAL '30 days'
GROUP BY 1, 2, 3;

CREATE VIEW v_persona_health AS
SELECT
  psl.profile_id,
  psl.send_date,
  psl.sends_count,
  psl.cooldown_until,
  COUNT(lo.id) FILTER (WHERE lo.reply_received_at IS NOT NULL) AS replies_from_this_profile_batch
FROM profile_send_log psl
LEFT JOIN lead_outreach lo ON lo.send_metadata->>'profile_id' = psl.profile_id
  AND DATE(lo.sent_at) = psl.send_date
GROUP BY 1, 2, 3, 4;

CREATE VIEW v_channel_reply_rates AS
SELECT
  channel,
  DATE(sent_at) AS sent_day,
  COUNT(*) FILTER (WHERE status = 'sent') AS sent,
  COUNT(*) FILTER (WHERE reply_received_at IS NOT NULL) AS replied,
  COUNT(*) FILTER (WHERE reply_classification = 'interested') AS interested,
  COUNT(*) FILTER (WHERE reply_classification = 'not_interested') AS not_interested
FROM lead_outreach
WHERE sent_at >= NOW() - INTERVAL '30 days'
GROUP BY 1, 2;
```

### Julia's daily dashboard

- Drafts in HITL queue (with wait time)
- Today's send count by channel
- Today's replies (interested / other)
- Persona health traffic light (green / yellow / red per persona)
- Inbox pool health (# available, # in cooldown)

### Jon's weekly dashboard

- Weekly conversion funnel (sourced → interested)
- Cost per booked call (Anthropic + IPRoyal + Apify / calls booked)
- Score distribution histogram
- Top 10 audit gap themes (from `gap_summary` clustering)
- Prompt version reject rate (which drafts get rejected most)

### Kyle's technical dashboard

- Audit failure breakdown by reason
- Playwright error rate per scraper
- IMAP fetch success rate
- Claude API cost by phase (Haiku vs Sonnet vs Opus)
- n8n workflow run success/failure per hour

### Daily digest

Discord message at 8am each morning:

```
🌅 OPS-WARM-OUTREACH — Daily Digest — 2026-07-15

📥 Sourced yesterday: 187 (up 12%)
🧬 Enriched: 176
⚙️ Audits started: 34 · completed: 28 · failed: 6
📊 Scored ≥15: 19 (61% of audited)
✍️ Drafts created: 47
🎛️ In HITL queue: 12 (avg wait 3h)
📤 Sent: 32 DMs + 45 emails
💬 Replies: 8 · interested: 3 · not interested: 4 · unclear: 1

🚦 Health:
  • Personas: 5 green / 2 yellow / 0 red
  • Inbox pool: 15 available / 5 cooling down
  • Audit success rate (7d): 78% ✅

🔥 Hot leads awaiting operator response: 2
```

### Weekly PDF report

Sunday 9pm cron. Generate PDF (reportlab) summarizing the week and email to Jon. Include:
- Executive summary (4 lines)
- Funnel chart
- Reply-rate trend
- Top wins + top failures
- Next week's projected volume

---

## Test Approach

Once Phase 7 has been running 3+ days with real data:
- Load Julia dashboard, spot-check numbers against raw queries
- Have Jon look at his dashboard: can he answer "are we on track?" in 30s?
- Trigger a fake failure (mark 5 audits as failed) — confirm health lights turn yellow

---

## LOE Estimate

- Views SQL: 4 hr
- Metabase dashboards: 6 hr
- Digest bot: 4 hr
- Weekly PDF report: 4 hr
- Testing: 3 hr

**Total: ~21 hours.**

---

## Escalation

- If Metabase queries slow > 5s → add materialized views, refresh hourly
- If dashboards keep needing tweaks after week 1 → schedule a 30-min review with Jon + Julia to lock the layout
- If digest volume overwhelms Discord → move to daily email instead
