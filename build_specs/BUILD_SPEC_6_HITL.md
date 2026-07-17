# BUILD_SPEC_6 — Discord HITL Bot

**Phase:** 6
**Timeline:** Week 5
**Owner:** Kyle
**Depends on:** Phase 5 (drafts to review)
**Blocks:** Phase 7 (approved drafts feed sending)

---

## Objective

Give Julia a review surface that lets her approve/edit/reject 50–100 drafts/day in under 30 minutes.

Reuse the pattern from FC IG Lead Discovery M8 (ghost followup) and OPS-61 — do NOT invent a new framework.

---

## Scope

### In
1. Discord bot service (Python, `discord.py`)
2. Poll `lead_outreach` for `status = 'draft'` rows, post to Discord
3. Interactive buttons: Approve / Edit / Reject / Skip Lead
4. Edit modal for inline rewrite
5. State transitions written to Postgres
6. Bulk-approve mode for warm queue (score 15–19) — one click approves next 10
7. Rate-limited posting so Julia isn't overwhelmed (5 drafts posted at a time, next batch after action)

### Out
- Sending logic (Phase 7)
- Hot-lead handoff conversation (Phase 7)

---

## Acceptance Criteria

- [ ] Bot connects to Discord, posts drafts to configured HITL channel
- [ ] Each post shows: lead summary (company, score, gap headline), channel, sequence step, full draft body
- [ ] All 4 buttons functional; state flips in Postgres within 1s of click
- [ ] Edit modal saves rewrite to `lead_outreach.approved_body` (draft_body stays untouched for comparison)
- [ ] `approved_by`, `approved_at`, `rejected_reason` populated appropriately
- [ ] Bulk-approve button for warm queue works; hot queue (score 20+) never bulk-approvable
- [ ] Bot survives Discord reconnects, VPS restarts (systemd unit or Docker restart policy)
- [ ] Julia can process 50 drafts in <30 min in a live test

---

## Files Touched

```
hitl_bot/
├── Dockerfile
├── requirements.txt
├── main.py                        # bot entrypoint
├── views.py                       # button views + modals
├── db.py                          # Postgres helpers
├── formatter.py                   # draft → Discord embed
└── README.md
```

---

## Implementation Notes

### Bot poll pattern

Every 30 seconds:
1. Query `SELECT * FROM lead_outreach WHERE status = 'draft' ORDER BY <priority> LIMIT 5`
2. For each: format as Discord embed, post with buttons, mark as `posted_to_hitl = TRUE` (add column in migration 003)
3. Do not re-post already-posted drafts

Priority ordering: hot queue (score 20+) first, then warm queue by `created_at`.

### Embed format

```
📩 Draft — Sarah Coaching (score 22, hot)
Channel: IG DM · Step 1 · 143 chars

Gap: Zero follow-up after application starts

──────────
Hey Sarah — saw your post on undercharging, felt the sting 😅
I opted into your application yesterday, bailed at Q3, zero follow-up came through. Mind if I share a fix?
──────────

[✅ Approve]  [✏️ Edit]  [❌ Reject]  [⏭ Skip Lead]
```

Include:
- Lead ID (small text, for reference)
- Link to full lead record in Metabase (deep link)
- Score + tier badge (color-code embed by tier — hot = red accent, warm = blue, cold = grey)

### Edit modal

`discord.py` supports modals natively. Prefill with `draft_body`, save on submit to `approved_body`. Keep `draft_body` unchanged so we can measure edit rate.

### Bulk approve

Add a button `[✅✅ Approve Next 10 Warm]` visible only when the current draft is warm-queue. On click:
1. Fetch next 10 warm-queue drafts
2. Mark all as `approved` with `approved_by = '<user> (bulk)'`
3. Post summary "Approved 10 warm-queue drafts: [list of company names]"

Hot queue (score 20+) never bulk-approvable — each must be reviewed individually. This is a rule, not a config.

### Rejection tracking

When Julia clicks Reject, show a dropdown of common reasons:
- Bad hook
- Missed the gap
- Sounds AI
- Wrong channel for this prospect
- Prospect actually not ICP
- Other (opens modal for freeform)

Store selected reason in `lead_outreach.rejected_reason`. Use these for weekly prompt-tuning reviews.

### Resilience

- Wrap all Discord API calls in try/except
- On disconnect, `discord.py` auto-reconnects — just log
- Deploy as Docker container with `restart: unless-stopped`
- Health-check endpoint at `/health` for external monitoring (optional Phase 8)

---

## Test Approach

Seed 20 drafts across tiers. Julia does a live test:
1. Time how long 20 drafts take to process
2. Note any UX friction (button lag, modal weirdness)
3. Try disconnecting internet mid-approval — does bot recover?

Expected: 20 drafts in <10 min on first pass. If it's slower, the embed format is too dense.

---

## LOE Estimate

- Bot scaffold + Discord auth: 3 hr
- Views + buttons + modals: 5 hr
- Postgres integration + poll loop: 4 hr
- Bulk-approve mode: 2 hr
- Testing + Julia feedback: 4 hr

**Total: ~18 hours.**

---

## Escalation

- If Julia's daily volume exceeds review capacity → add a second HITL channel for warm-queue with different reviewer
- If bot crashes on Discord API version bump → update `discord.py`, don't hack around it
- If rejection reasons cluster on one prompt failure → schedule prompt tuning with Jon
