# BUILD_SPEC_5 — AI Personalization & DM Drafting

**Phase:** 5
**Timeline:** Week 4–5
**Owner:** Kyle
**Depends on:** Phase 4 (score ≥15 triggers drafting)
**Blocks:** Phase 6 (HITL reviews these drafts)

---

## Objective

Turn structured audit findings + recent social posts into channel-appropriate outreach that Julia can approve in seconds and Jon can defend to sophisticated founders.

The output must sound like a human copywriter who did the audit personally — not like AI wrote it.

---

## Scope

### In
1. n8n workflow triggered on `leads.qualification_score >= 15`
2. Prompts:
   - `prompts/drafting_sonnet.md` (for scores 15–19)
   - `prompts/drafting_opus.md` (for scores 20+)
3. Message validators (char count, S.I.P.E. compliance heuristics, forbidden phrase list)
4. 3-touch DM sequence per social channel (IG / LinkedIn / FB) — channels selected based on which handles the enrichment found
5. 4-touch cold email sequence for the parallel channel
6. Writes to `lead_outreach` with `status = draft`

### Out
- HITL review (Phase 6)
- Sending (Phase 7)

---

## Acceptance Criteria

- [ ] Every score-≥15 lead gets drafts written to `lead_outreach` within 5 minutes of scoring
- [ ] For each lead: drafts exist for every channel their enrichment supports (e.g., if IG handle + LinkedIn URL both present → both channel drafts created)
- [ ] Message 1 in every DM sequence is ≤160 characters (validator hard-blocks longer, does not silently truncate)
- [ ] Message 1 references BOTH the specific audit gap AND a specific recent social post — not one or the other
- [ ] Forbidden phrase list catches: "Love your recent post", "Just wanted to reach out", "Hope this finds you well", "I noticed you're", "Let me know if" — draft rejected if any hit
- [ ] Cold email variant uses same audit gap but adapts tone for email
- [ ] Manual test: 10 drafts reviewed by Jon, ≥8 pass the "would I send this?" test on first draft

---

## Files Touched

```
shared/n8n-templates/
  └── draft_outreach.json
prompts/
  ├── drafting_sonnet.md              # already scaffolded
  ├── drafting_opus.md                # already scaffolded
  └── forbidden_phrases.md            # list of banned openings
```

---

## Implementation Notes

### Model routing

- Score 15–19: **Claude Sonnet** (`claude-sonnet-4-6`) — good enough for warm queue, ~5× cheaper than Opus
- Score 20+: **Claude Opus** (`claude-opus-4-7`) — hot leads deserve the best draft

Do NOT default everything to Opus "because it's better" — cost adds up fast and Sonnet passes HITL 90%+ of the time on warm-queue leads.

### Payload composition

```json
{
  "channel": "dm_ig",
  "sequence_step": 1,
  "prospect": {
    "first_name": "Sarah",
    "company_name": "Sarah Coaching",
    "recent_social_posts": [
      {"platform": "instagram", "text": "The biggest mistake new coaches make is undercharging..."},
      ...
    ]
  },
  "audit_gap": "Zero abandoned-application follow-up emails after starting the discovery call form",
  "gap_summary": "You're leaking calls at the application step — nothing follows up when someone bails.",
  "tech_stack": {"esp": "kajabi", "cart": null, "page_builder": "kajabi"}
}
```

### Message validator

Runs AFTER Claude returns, BEFORE Postgres write:

```python
def validate_draft(draft: dict, channel: str, step: int) -> tuple[bool, str]:
    body = draft["body"]
    if channel.startswith("dm_") and step == 1:
        if len(body) > 160:
            return False, f"exceeds 160 char limit ({len(body)})"
    forbidden = load_forbidden_phrases()
    for phrase in forbidden:
        if phrase.lower() in body.lower():
            return False, f"contains forbidden phrase: {phrase!r}"
    # Must reference gap: crude check — one of these gap keywords appears
    gap_keywords = extract_keywords(draft.get("_audit_gap"))
    if not any(kw in body.lower() for kw in gap_keywords):
        return False, "does not reference audit gap"
    return True, "ok"
```

On validation failure, retry Claude ONCE with a corrective note ("Your previous draft failed validation for X. Rewrite ensuring…"). If retry also fails, log and skip — do NOT write a bad draft to the DB.

### Sequence templates

**IG / LinkedIn / FB DM sequence:**
- Msg 1 (≤160 chars): S.I.P.E. hook, references audit gap + social post. Ends with a specific question inviting reply.
- Msg 2 (sent only if Msg 1 was replied to and reply is `interested` — routes through Phase 7 human): tease-then-deliver. This msg is drafted, but Phase 7 routes it to human review before sending because it's mid-conversation.
- Msg 3: soft escalation to screen-share via ladder of tiny yeses.

**Cold email sequence:**
- Email 1: subject line + 3-sentence body, audit gap-driven. Plain text.
- Email 2: value-add follow-up 3 days later — deliver a piece of the audit as proof.
- Email 3: soft ask for a call 5 days later.
- Email 4: breakup email 8 days later.

### Prompt library structure

`prompts/drafting_sonnet.md` and `drafting_opus.md` share a common instruction block and differ only in model-specific tuning. Keep them in sync manually — no shared file loading logic in MVP.

Every prompt file starts with a version tag comment (`<!-- v1.0 -->`) so we can track changes when we tune.

---

## Test Approach

**Cold start test:** Feed 5 real audited leads (with Jon's approval) through the drafting engine. Julia reviews all drafts:
- Which pass first time?
- Which fail validation?
- Which pass validation but Julia edits before approving?

Track pass/edit/reject rates. Target for Phase 5 done:
- ≥60% approved without edit
- ≤10% rejected outright

If below thresholds, tune prompts.

**Regression test:** Keep a fixed set of 5 "golden" audit inputs in `tests/golden_audits.json`. After any prompt change, re-run and confirm drafts still pass validation + read well.

---

## LOE Estimate

- Prompt drafts + iteration: 8 hr
- Validator: 3 hr
- n8n workflow: 4 hr
- Testing + prompt tuning: 6 hr

**Total: ~21 hours.**

---

## Escalation

- If forbidden-phrase list needs frequent updates → track additions in Discord, batch weekly
- If validation failure rate >30% → the prompt is fundamentally wrong, don't paper over with retries
- If Julia edits >50% of drafts even after passing validation → prompt tuning session needed with Jon on tone
