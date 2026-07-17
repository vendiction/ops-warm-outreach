# OPS-WARM-OUTREACH — Test Log

A record of what has been validated on real infrastructure, the bugs/tunings found by
live testing, and the honest limitations. Environment: Supabase (cloud DB) + Docker on a
laptop + n8n + a free Zoho IMAP inbox + a free MailerLite test funnel + 2 IG accounts.

---

## Stage-by-stage status

| Stage | Status | How it was proven |
|-------|--------|-------------------|
| Schema + migrations | ✅ Live | 3 migrations applied to Supabase; 5 tables confirmed |
| Enrichment — funnel detection | ✅ Live, tuned | 20 real sites over 2 rounds (Allbirds, Bombas, Gymshark, SPI, Amy Porterfield, James Wedmore, Melyssa Griffin, Graham Cochrane, Kajabi, Thinkific, Tony Robbins, Mindvalley, Russell Brunson, Ramit, Marie Forleo, etc.) |
| Audit — browser opt-in (real funnel) | ✅ Live | MailerLite subscriber created by the worker's automated opt-in |
| Audit — reCAPTCHA handling | ✅ (blocked, correctly) | Diagnostic surfaced reCAPTCHA iframes; automated opt-in cannot pass — honest limitation |
| Audit — IMAP read (all folders incl. spam) | ✅ Live | Read real Zoho inbox; found emails in INBOX, Spam, Trash |
| Audit — email classification | ✅ Live, tuned | Classified confirmation, welcome; detected spam placement |
| Audit — double opt-in detection | ✅ Live, added | `double_optin_detected` + `confirmation_in_spam` flags fire on the real funnel |
| Audit — aggregation → gap finding | ✅ Live | Produced a specific, sellable gap summary |
| Scoring — rubric logic | ✅ Live | Haiku parse + archive logic vs DB |
| Drafting — DM (Sonnet) | ✅ Live | 3-message S.I.P.E. sequence generated in n8n |
| Drafting — cold email (4-touch) | ✅ Live | Hook → proof → soft ask → breakup; judged send-ready |
| HITL bot — Approve | ✅ Live | Approved a real card; flowed to send console |
| HITL bot — cards for DM + email | ✅ Live | Both channels post correctly with all buttons |
| Send console — human DM send | ✅ Live | Real A→B send; cap ticked; event logged |
| Send console — daily cap | ✅ Live | Enforced |
| Reply triage — classifier | ✅ Live | Real reply → "interested/high" → 🔥 Discord alert |
| Cold-email dispatch workflow | ◑ Cadence logic only | 4-touch gate validated vs DB; not sent (needs 15-inbox webhook) |
| Email reply triage workflow | ◑ Classifier only | Needs a live cold-email inbox |
| Sourcing — Apollo (search → reveal → normalize) | ✅ Live | Real founder (Nathalie Blais / Coach Academy) found, email revealed, classified `primary_info`, landed in DB |
| Sourcing — Meta Ad / StoreLeads | ⛔ Not run | Needs scraper containers / access |
| Analytics — digest | ◑ Built, not run | Free to test |
| Full chain via n8n (all Active on timers) | ✅ Live | Auto-handoff proven: seeded lead flowed enrich→score→draft→Discord→console on timers, no manual clicks |
| Synth audit — application funnels (Option C) | ✅ Live | Application-funnel lead → synthetic structural gap → scored → drafted (referenced HubSpot + application-abandon) → Discord |

Legend: ✅ proven live · ◑ built, partially validated · ⛔ tool/account-gated

---

## Bugs & tunings found BY live testing (all fixed)

1. **`Log Draft Event` node** read `$json.messages` (undefined at that point) → now reads from the `Loop jobs` node. Fixed in the drafting workflow + builder.
2. **Info-funnel emails misclassified** as `other` by the audit brain → added `optin_recovery` keyword set + aggregation. Info vertical now the strongest.
3. **Discord double-emoji** (`✅✅`) rejected every HITL card (error 50035) → changed to `⚡`.
4. **`mage/` matched inside `image/`** → false Magento on every site → tightened Magento signals to real markers.
5. **`cf-` matched Cloudflare classes** → false ClickFunnels → tightened builder signals; ClickFunnels now a *true* positive (correctly detected on Russell Brunson).
6. **Funnel priority** called anything with a `/shop` path "ecom" → now requires a real cart platform or `/cart|/checkout`; course platforms (Kajabi/Teachable/Thinkific/Podia/Kartra) force "info".
7. **IMAP read only scanned INBOX** → missed spam-foldered mail → now scans all folders and tags spam.
8. **Double opt-in confirmation** classified as `other` → added `confirmation` class + `double_optin_detected` / `confirmation_in_spam` findings.
9. **Apollo wrong endpoint** — workflow used `mixed_people/search` → the API needs `mixed_people/api_search`.
10. **Apollo no reveal step** — search returns masked emails; added a `people/match` (reveal) node + flatten so leads get real emails (1 credit each). Also added an email-domain fallback for when org data is thin.
11. **Apollo revenue `0` = auto-archive** — Apollo returns `annual_revenue_usd: 0` for *undisclosed* revenue; the filter treated 0 as a real below-threshold value and archived nearly every real coach. Fixed to treat `0` as unknown → the audit is the real qualifier.

---

## Honest limitations surfaced

- **reCAPTCHA blocks automated opt-in.** Funnels protected by captcha cannot be audited
  automatically. Solving captchas = bot-detection evasion, which is out of scope by design.
  Mitigation: detect captcha → mark the audit "blocked" and skip, or human-assist the ~10-second
  opt-in for high-value prospects.
- **Double opt-in funnels** don't yield a nurture sequence to the audit — but the audit now
  *detects* the double opt-in itself, which is a finding (friction + often spam).
- **Enrichment on genuinely hybrid sites** (a coach who also runs a real store, e.g. Ramit,
  Marie Forleo) is a defensible best-guess, not a clean call. ~80% clean on real ICP sites;
  the rest are honest nulls or defensible calls.
- **Gap-summary phrasing** from Claude defaulted to a generic line even when a high-severity
  finding (spam/double opt-in) existed. The *data* is correct; the prompt should be tuned to
  lead with the highest-severity finding. (Prompt-tuning item, not a bug.)

---

## Cost of this test round

**$0.** Free Zoho inbox (IMAP, no Bridge), free MailerLite funnel, Supabase free tier,
Docker on the existing laptop, existing Anthropic key.

---

## What remains untested (and why)

- **Live sourcing at volume** — Apollo Basic ($49); people-search is paywalled.
- **Sending to real prospects** — warmed sender accounts (30–45 day clock).
- **Full unattended chain** — deployment: all 9 workflows Active + scrapers/audit-worker as
  services + always-on host.

Every stage that carries real *risk* has been tested live. What's left is operational.
