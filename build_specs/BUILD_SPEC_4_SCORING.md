# BUILD_SPEC_4 — Qualification & Scoring

**Phase:** 4
**Timeline:** Week 4
**Owner:** Kyle
**Depends on:** Phase 3 (audit data)
**Blocks:** Phase 5 (drafting only runs for score ≥15)

---

## Objective

For every lead with a completed audit, apply the 25-point scoring rubric via Claude Haiku, route by score, and log the reasoning to the DB so decisions are auditable later.

---

## Scope

### In
1. n8n workflow triggered on `lead_audits.audit_status = 'complete'`
2. Prompt: `prompts/scoring_haiku.md`
3. Postgres write of score + subscores + reasoning
4. Routing: <10 archive, 10–14 cold queue, 15–19 warm queue, 20+ hot queue
5. `outreach_events` log

### Out
- Drafting (Phase 5)
- Any human review of scores (that's not needed — score is deterministic given the rubric)

---

## Acceptance Criteria

- [ ] Every `lead_audits.audit_status = 'complete'` row triggers scoring within 60 seconds
- [ ] `leads.qualification_score` populated (0–25)
- [ ] `leads.qualification_subscores` JSONB has 5 keys: revenue, margin, list, growth, authority (each 1–5)
- [ ] `leads.qualification_reasoning` populated with Haiku's 2–4 sentence justification
- [ ] Score <10 → `is_archived = TRUE`, `archive_reason = 'score below threshold: X/25'`
- [ ] Manual test: 5 seeded leads with known ideal scores fall within ±2 of expected

---

## Files Touched

```
shared/n8n-templates/
  └── score_qualified_audits.json
prompts/
  └── scoring_haiku.md                # already scaffolded
```

---

## Implementation Notes

### n8n workflow

Simple 6-node flow:
1. **Postgres trigger** — listens on `lead_audits` updates where `audit_status = 'complete'`
2. **Postgres SELECT** — pull `leads`, `lead_enrichment`, `lead_audits` for this lead
3. **Function node** — compose payload for Claude
4. **Anthropic HTTP node** — POST to Haiku
5. **Function node** — parse JSON response, validate schema
6. **Postgres UPDATE** — `leads` with score + subscores + reasoning
7. **IF node** — score <10 → set `is_archived = TRUE`
8. **Postgres INSERT** — `outreach_events` with `event_type = 'score'`

### Payload composition

```json
{
  "company_name": "Example Coaching",
  "domain": "examplecoaching.com",
  "icp_tier": "primary_info",
  "traffic_monthly": 42000,
  "tech_stack": {"esp": "kajabi", "cart": null, "page_builder": "kajabi"},
  "recent_social_posts": [...3 posts...],
  "audit": {
    "welcome_email_received": true,
    "welcome_has_cta": false,
    "abandoned_application_followup_count": 0,
    "first_recovery_delay_hours": null,
    "discount_offered": false,
    "total_emails_received_72h": 2,
    "deliverability_signal": "promotions",
    "gap_summary": "..."
  }
}
```

### Score interpretation

The rubric is documented in `prompts/scoring_haiku.md`. Haiku returns strict JSON — validate with a schema check. If Haiku returns malformed JSON, retry once with `temperature=0`, then fail the score attempt (do NOT force a score with defaults).

### Routing

After UPDATE, the workflow routes on score:
- `<10` → archive branch (no further phases)
- `10–14` → `queue_cold` (Phase 5 may or may not draft, based on quota)
- `15–19` → `queue_warm` (Phase 5 drafts with Sonnet)
- `20+` → `queue_hot` (Phase 5 drafts with Opus, immediate HITL priority in Phase 6)

---

## Test Approach

Seed 5 leads representing the score spectrum:
- Enterprise info-business w/ every gap → expect 22–25
- Solid coach w/ small gaps → expect 17–19
- Mid-size ecom w/ decent funnel → expect 13–15
- Weak signals → expect 8–10
- Clear disqualifier w/ audit that ran anyway → expect <8

Run scoring, verify scores land in expected ranges. If any is >3 points off, tune the prompt (rubric weights).

---

## LOE Estimate

- Prompt tuning: 3 hr
- n8n workflow: 3 hr
- Testing + calibration: 3 hr

**Total: ~9 hours.** Small phase, but the prompt quality determines routing quality for everything downstream — don't rush the calibration.

---

## Escalation

- If Haiku returns wildly inconsistent scores on identical inputs → switch to `temperature=0` (should be default anyway) and add examples to prompt
- If score distribution collapses (95% land at 12–15) → the rubric weights need adjustment, escalate to Jon
