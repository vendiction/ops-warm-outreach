# OPS-WARM-OUTREACH — Launch Readiness

The single source of truth: what the original handoff asked for, what's been proven, and
exactly what's left before going live. Every phase below was tested on **real infrastructure**
(Supabase + Docker + real Apollo + free Zoho IMAP + real MailerLite funnel + real accounts).

---

## Original spec → tested status

| Phase | Spec deliverable | Status | Proof |
|-------|-----------------|--------|-------|
| 0 | Foundation (schema, migrations, .env) | ✅ Tested | 5 tables on Supabase |
| 1 | Sourcing (Apollo/Meta/StoreLeads) | ✅ Tested | Apollo found + revealed a real founder (Nathalie Blais / Coach Academy) end-to-end |
| 2 | Enrichment | ✅ Tested | 20 real sites + the real prospect's funnel detected |
| 3 | Audit worker (the moat) | ✅ Tested | Live browser opt-in + IMAP read + classify + gap finding on a real funnel |
| 4 | Qualification & scoring (Haiku) | ✅ Tested | Scored the real prospect 9/25 with reasoning |
| 5 | AI drafting (Sonnet/Opus) | ✅ Tested | DM + 4-touch cold-email sequences for a real prospect |
| 6 | Discord HITL bot | ✅ Tested | All 5 actions: Approve, Edit, Reject, Skip Lead, bulk; double-action guard |
| 7 | Sending & reply triage | ◑ Partial | Reply triage ✅ live; **sending ⛔ needs warmed accounts** |
| 8 | Analytics (Metabase + digest) | ✅ Tested | Daily digest posted to Discord from real data |
| — | **Full chain** (Apollo → Discord) | ✅ Tested | One real prospect flowed the entire belt to an approval-ready draft |

**Note:** the spec's Phase 7 originally called for Playwright/Dolphin evasion sending. This was
deliberately replaced with a compliant model — automated cold email + human-sent DMs (send
console) — early in the build. See `docs/PHASE_7_DECISION.md`.

---

## What's left before launch (all operational — no untested code on the critical path)

### 🔴 Gating (must happen)
1. **Warm sender accounts** — 30–45 day clock. The only true bottleneck; nothing accelerates it.
   **Start today**, in parallel with everything else.
2. **Verify the 15 cold-email inboxes are warm**, then live-test `send_cold_email` through the stack.
3. **Deploy to an always-on host** (Railway/Render/Fly.io or a VPS) and flip all 9 n8n workflows
   **Active**. Wire scrapers + audit worker as services. See `DEPLOYMENT.md`.
4. **Inbox pool** — replace the single test inbox with a catch-all domain (Migadu/Zoho, ~$2–5/mo)
   giving unlimited `audit1@…` addresses.

### 🟡 Product decisions
5. **Application-funnel audit strategy — DECIDED & BUILT (Option C).** Auto-audit works on
   simple opt-in funnels but can't complete application funnels (multi-field/HubSpot) or
   captcha'd funnels. Resolution: opt-in → auto-audit; application → `synth_audit_application`
   workflow writes a structural "leaking warm applicants" gap so the lead flows through
   scoring→drafting normally; captcha → skip. See `docs/APPLICATION_FUNNEL_ROUTING.md`.
   Remaining action: import + activate that workflow at deploy.

### 🟢 Optional / nice-to-have (free, low-risk)
6. Wire `DISCORD_DIGEST_WEBHOOK` permanently (done in testing).
7. Live-run `triage_email_replies` once a cold-email inbox exists.
8. Test alternate sources (`source_meta_ad_library`, `source_storeleads`) if you want more than Apollo.
9. Run all enrichment scrapers (similarweb/social) so scores aren't skewed low by missing data.

---

## Costs to operate (per month)

| Item | Cost |
|------|------|
| Apollo Basic | $49 |
| Inbox pool (catch-all domain + mailbox) | ~$2–5 |
| Always-on host | ~$5–20 |
| Anthropic API (usage) | ~$20–50 |
| Proxies (IPRoyal) | only if audit gets IP-blocked at volume |
| **Total** | **~$75–125/mo** + operator time |

---

## Bugs found & fixed by live testing (≈11)

Log Draft Event node · info-funnel misclassification · Discord double-emoji · `image/`→Magento ·
`cf-`→ClickFunnels · funnel-priority (shop path) · IMAP INBOX-only (missed spam) · double-opt-in
detection · Apollo wrong endpoint · Apollo missing reveal step · Apollo revenue-0 archive trap ·
enrichment localhost-unreachable-from-n8n.

---

## Honest limitations (know these going in)

- **Auto-audit ≠ universal.** Works on simple opt-in funnels; blocked by reCAPTCHA and
  application/complex forms. Plan to route or human-assist those.
- **Scores depend on enrichment completeness.** Thin enrichment → low scores. Run all scrapers.
- **Apollo revenue data is unreliable** for small info businesses — the audit is the real qualifier.
- **The operator is required daily** (~30–45 min: approve + send DMs + work hot replies).

---

## The one-line status

**Every phase of the system is built and tested live except sending to real prospects, which is
gated only on the 30–45 day account warmup.** The machine works end-to-end. What remains is
operational: warm accounts, deploy, and one product decision on application funnels.

**Highest-leverage next action: start warming accounts today.**
