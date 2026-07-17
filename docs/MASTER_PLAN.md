# OPS-WARM-OUTREACH — Master Plan

Markdown mirror of `OPS-WARM-OUTREACH_KYLE_HANDOFF.pdf`. Same content, grep-friendly.

---

## System Role & Objective

95% automated multi-channel client acquisition targeting high-net-worth B2B founders (info businesses, coaches, course creators, qualifying ecom brands doing $100K+/mo) to sell $5,000–$7,000/mo Full Stack Email Marketing retainers.

---

## PART 1 — Core Methodology

### 1A. Operational Spine (Agency Model)

**ICP — Strict Dual-Tier**

- **Primary (Info / Coaches / Courses):** $100K+/mo gross revenue, 10K+ engaged list. 60–80%+ margins → can absorb $5–7K retainer easily.
- **Secondary (Ecom, gated tighter):** 80K+ list with $70+ AOV, OR 60K–100K list with $27+ AOV. Ecom margins (20–40%) force higher thresholds.
- **Hard disqualifiers:** dropshippers, brick-and-mortar, unproven-revenue startups. Auto-archive at score <10/25.

**25-Point Qualification Scoring** — 1–5 on Revenue, Profit margin, List size, Growth rate, Decision authority. 20+ = dream, 15–19 = warm queue, 10–14 = cold queue, <10 = archive.

**Core Value Prop — 17-Step Email Profit Formula:** 30 daily broadcasts + 10 automated workflows + deliverability + weekly reporting.

**Hook — Automated Audit:** opt in, abandon high-intent action, map recovery emails 72hr, identify revenue gaps.

**Close:** NEVER in DMs. Push to 20-min screen-share.

### 1B. Communication Supplement (DM Copy Layer)

- 160-char rule on initial DMs
- S.I.P.E.: Short, Incomplete, Personal, Emotional
- Tease-then-deliver
- Ladder of Tiny Yeses to screen-share

### 1C. Contradictions to Avoid

- ❌ No closing in DMs
- ❌ No trailing-off cliffhangers
- ❌ No fake AI personalization (generic compliments)
- ✅ Personalization from actual audit data

---

## PART 2 — Technical Stack

### Have
Hostinger VPS · n8n · Postgres · Supabase · Docker · Anthropic API (Haiku/Sonnet/Opus) · Cold email stack (15 inboxes across `fascinatecopy.site`, `fascinatehq.online`, `usefascinate.space`) · Discord HITL pattern · Playwright experience.

### Build In-House
Audit worker · DM sending layer · Discord HITL bot · Scoring engine (n8n + Haiku) · DM drafting engine (n8n + Sonnet/Opus) · Reply triage classifier · Postgres schema · Small scrapers.

### Buy (Cheapest)
- IPRoyal proxies (~$20–40/mo)
- Dolphin{anty} free tier ($0)
- Apollo free tier → $49/mo when needed
- Apify pay-as-you-go (~$5–15/mo)
- Metabase OSS ($0)
- Cal.com + Google Meet ($0)

### Invest Time
- Warm 3 IG + 2 LinkedIn + 2 FB personas over 30–45 days
- Self-created ProtonMail inbox pool (20+ accounts)

**Starting monthly cost: ~$25–55.**

### Skip
❌ SmartLead/Instantly · ❌ PhantomBuster · ❌ Streamlit · ❌ Clay

---

## PART 3 — Build Order

| Phase | Title | Timeline | Spec |
|-------|-------|----------|------|
| 0 | Foundation & Bottleneck Unblock | Week 1 | `BUILD_SPEC_0_FOUNDATION.md` |
| 1 | Sourcing Pipeline | Week 1–2 | `BUILD_SPEC_1_SOURCING.md` |
| 2 | Enrichment Pipeline | Week 2 | `BUILD_SPEC_2_ENRICHMENT.md` |
| 3 | Python Audit Worker (THE MOAT) | Week 2–4 | `BUILD_SPEC_3_AUDIT_WORKER.md` |
| 4 | Qualification & Scoring | Week 4 | `BUILD_SPEC_4_SCORING.md` |
| 5 | AI Personalization & DM Drafting | Week 4–5 | `BUILD_SPEC_5_DRAFTING.md` |
| 6 | Discord HITL Bot | Week 5 | `BUILD_SPEC_6_HITL.md` |
| 7 | Sending & Reply Triage | Week 5–6 | `BUILD_SPEC_7_SENDING.md` |
| 8 | Analytics Dashboard | Week 6 | `BUILD_SPEC_8_ANALYTICS.md` |

---

## PART 4 — Critical Path Bottlenecks

Run parallel to Phases 0–2 or launch stalls:

1. **Social account warmup** — 30–45 day clock. Start Day 1.
2. **Cold email domain warmup** — verify existing stack healthy.
3. **ProtonMail inbox pool** — must exist before Phase 3 runs live.
4. **Proxy + Dolphin setup** — required before any sending or audit traffic.

---

## PART 5 — Resolved Decisions (locked)

| Decision | Resolution |
|----------|------------|
| ICP scope | Dual-tier. Info primary, ecom gated tighter. |
| Audit modality | Dual mode: cart-abandon (ecom) + application/opt-in abandon (info). Same 72hr IMAP capture. |
| Cold email role | Parallel channel via existing 15-inbox stack. Same audit-driven personalization. |
| DM execution | In-house Playwright + Dolphin + IPRoyal. No PhantomBuster. |
| Assignee | Kyle leads. Rinoah unavailable (OPS-61). Kevin support. |

If any of these conflicts with implementation reality, escalate to Jon. Do not re-litigate silently.
