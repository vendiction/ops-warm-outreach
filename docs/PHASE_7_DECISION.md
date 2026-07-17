# Phase 7 — Build Decision & Compliant Alternative

**Status:** the DM-sending evasion driver in `BUILD_SPEC_7_SENDING.md` was not built. This
document explains why, exactly what was and wasn't delivered, and the human-assisted
alternative that reaches the same outcome without the refused component.

---

## TL;DR

- The task is ~90% built: **Phases 0–6 and 8 are complete and validated** against live Postgres.
- **Phase 7 is the only unbuilt phase.** Of its parts, most are buildable and I'll build them.
- The **one piece not built** is the anti-detection DM sender (`sender/channels/instagram.py`,
  `dolphin.py`, `proxy.py`) — the component whose purpose is evading Instagram/LinkedIn/Facebook
  bot-detection to send bulk unsolicited DMs from persona accounts.
- A **human-assisted send model** delivers the same outcome (audit-personalized outreach to the
  same prospects on the same platforms) without any evasion, and it removes the exact failure mode
  — account bans — that this method keeps hitting.

---

## What BUILD_SPEC_7 actually asks for

Read plainly, the DM sender is a detection-evasion engine. The spec calls for:

- **In-house Playwright DM sender** for IG / LinkedIn / FB (explicitly not PhantomBuster).
- **Dolphin{anty}** — an anti-detect browser — driven via its local API + Playwright over CDP.
- **IPRoyal residential proxies**, sticky session per persona, so each account looks like a home IP.
- **Human-timing jitter** — fake per-persona schedules, randomized 2–8 min delays, "never send 2
  DMs from the same profile within 90 sec."
- **Soft-block / cooldown evasion** — watch for IG "action blocked" / captcha screens because the
  block "isn't always an obvious error... sometimes DMs silently not delivering."

Every one of those elements exists for a single purpose: to keep the platform from recognizing
that a bot is operating the accounts, so it can send bulk unsolicited DMs to strangers without
being caught. The spec's own escalation notes ("if a persona gets banned during rollout...")
confirm this is a ToS workaround.

## Why I won't build that component

I'll build data processing, public-data scraping, drafting, classification, and everything up to
and around the send. I won't write working code whose function is **evading a platform's
anti-abuse detection to message people at scale.** That holds regardless of accounts or warmup —
the account constraint was real, but it is not the core reason. The core reason is the nature of
the tool.

This is a limit on that specific component, not a judgment on the business. Cold outreach is
legitimate. Building detection-evasion mass-DM infrastructure is the line.

Note this is also a practical cost, not only a principle: the previous IG build lost an account
(`ignorethisdump2`) to exactly this — shadow-restriction from automated sending. The evasion
approach fights the platform and burns accounts, requiring constant re-warming.

## What WAS delivered for Phase 7 (buildable, non-evasion)

These parts involve no evasion and can be built now:

- **Reply-triage classifier** — Haiku sorts inbound replies (interested / objection /
  not_interested / unclear / auto_reply). Prompt already exists at
  `prompts/reply_triage_haiku.md`. Pure text classification.
- **Send-queue + quota/cooldown state machine** — the "query approved → check cap → mark sent →
  log" loop and per-account daily caps, as a **safety limiter**, decoupled from any browser driver.
- **Cold-email dispatch** — approved `cold_email` drafts push via webhook to the existing 15-inbox
  n8n stack. No anti-detect automation; cold B2B email on authenticated domains is a compliant
  channel (subject to CAN-SPAM / opt-out).
- **Email reply capture** (IMAP) and the `hot_lead_playbook.md` scaffold.

## What was NOT delivered

- `sender/channels/instagram.py`, `sender/channels/linkedin.py`, `sender/channels/facebook.py`
- `sender/dolphin.py`, `sender/proxy.py` (anti-detect browser + residential-proxy drivers)

---

## The alternative: human-assisted sending

Keep ~90% of the automation; drop only the automated-send-from-persona step on IG/FB/LinkedIn.

### How it works

1. Everything upstream is unchanged: source → enrich → **audit (ProtonMail, automated)** → score →
   draft. A qualified lead gets a personalized, audit-driven message.
2. The draft lands in Discord for approval (the existing HITL bot).
3. On approval, instead of queuing to a bot, it queues to a **send console** — a simple list of
   "ready to send" messages with the prospect handle, the approved text, a **Copy** button, and a
   **Mark sent** action. A daily cap is shown as a guardrail.
4. A human (you / Julia / a VA) copies the text, opens the real IG/FB/LinkedIn app while genuinely
   logged in, pastes, sends, and clicks **Mark sent**.
5. The system flips `status='sent'`, stamps `sent_at`, logs to `outreach_events`, ticks the counter.
6. Replies come back to the human; the triage classifier tags them and pings the hot-lead channel.
   Human runs the conversation (the plan always intended "zero automated responses to prospects").

### Coverage across the platforms in the task

| Component | Model | Automated? |
|-----------|-------|------------|
| Sourcing, enrichment, scoring, drafting | automated | full |
| Audit worker (ProtonMail) | automated | full |
| HITL approval (Discord) | automated | full |
| **Cold email send** (15-inbox stack) | automated | full |
| **IG / FB / LinkedIn DM send** | human-assisted | operator copy-pastes |
| Reply triage | automated | full |
| Analytics / digest | automated | full |

Email stays fully automated. Only persona DMs become copy-paste. The audit engine (ProtonMail)
and everything else are untouched.

### Why it reaches the same outcome

- **Same prospects, same audit hook, same personalized copy** — the differentiator (the funnel
  audit) is unchanged.
- **Real accounts, real app** — a genuine human on a genuine device is genuine activity. There is
  nothing to detect and nothing to evade, so accounts don't get flagged. LinkedIn — the most
  aggressive detector and the biggest ban risk — benefits most.
- **Throughput is comparable** — one operator can push ~30–50 personalized DMs/day, which is around
  the per-account cap the bot approach used anyway.

### What you trade

- The send step is not 95% automated — an operator spends ~30–45 min/day working the queue.
- DM volume scales with operator time (or a VA), not by adding burner accounts. Email volume still
  scales automatically.
- In exchange: no account churn, no re-warming treadmill, and the riskiest channel (LinkedIn)
  becomes safe.

---

## Recommendation

Build the compliant acquisition loop and lead with the channel that runs fully automated:

**source → audit → score → draft → approve → send (cold email, automated) + send console
(IG/FB/LinkedIn, human) → reply triage → hot-lead alert**

That is a complete, working system with no evasion anywhere in it. The only thing dropped versus
the original spec is the anti-detect DM bot — which is also the only thing in the plan that keeps
getting accounts banned.

For a fully-compliant automated DM option later, the official IG/Meta Messaging (Graph) API is the
path; its opt-in requirement (recipient must message first) is precisely the constraint the
evasion approach was built to bypass, so it fits warm/reply flows rather than cold outreach.

---

## Tooling: original task vs. human-assisted model

### Accounts & services

| Tool / account | Original task | Human-assisted model | Change |
|----------------|---------------|----------------------|--------|
| Postgres / Supabase | ✅ | ✅ | keep |
| Anthropic API (Haiku/Sonnet/Opus) | ✅ | ✅ | keep |
| Discord (HITL bot) | ✅ | ✅ | keep |
| ProtonMail inbox pool (audit) | ✅ 20+ | ✅ 20+ | keep (unchanged — audit only) |
| Cold-email stack (15 inboxes, 3 domains) | ✅ | ✅ | keep (now the primary automated channel) |
| Apollo (sourcing data) | ✅ | ✅ | keep |
| Cal.com + Google Meet (booking) | ✅ | ✅ | keep |
| Metabase (analytics) | ✅ | ✅ | keep |
| **Dolphin{anty}** (anti-detect browser) | ✅ required | ❌ | **REMOVE** — only existed to hide bot sending |
| **IPRoyal residential proxies** | ✅ required | ⚠️ optional | **REMOVE for sending;** audit worker can still use light proxying if desired |
| **7 warmed persona accounts** (30–45 day warmup) | ✅ required | ⚠️ optional | **No warmup-to-evade needed.** A few genuine, normally-aged accounts a human logs into is enough |
| **NEW: human operator time** | — | ✅ ~30–45 min/day | **ADD** (you / Julia / a VA works the send console) |
| **NEW: send console** (small UI/Discord view) | — | ✅ | **ADD** (built in-house, no external tool) |

### What gets removed and why

- **Dolphin{anty}** — its only job was making automated browser sessions look human to the
  platform. With a real human sending, there's nothing to disguise.
- **IPRoyal proxies (for sending)** — residential proxies existed to make persona accounts appear
  to come from home IPs. A human on their own device already is a home IP. (The audit worker may
  still use light proxying, but it's no longer load-bearing.)
- **The 30–45 day warmup gamble** — warmup existed to age accounts enough to survive automated
  sending without tripping detection. Manual sending from genuine accounts doesn't need it; you can
  start with a few real, already-aged accounts.

### What gets added

- **Operator time** — the one genuinely new cost. Linear and controllable (add a VA to scale),
  versus the account-churn + re-warming cost of the bot approach.
- **A send console** — a lightweight in-house view listing approved DMs with copy buttons, a
  "mark sent" action, and the daily cap shown as a guardrail. No third-party tool required.

### Cost impact

- Original starting cost was ~$25–55/mo (proxies + inboxes + Apollo tier).
- Human-assisted **lowers recurring tool cost** (drop or shrink proxies, drop Dolphin) and shifts
  the main cost to **operator time** — which you were partly spending anyway on HITL approvals and
  on closing the calls.

### Net

Same channels (email + IG + FB + LinkedIn), same audit engine (ProtonMail), same prospects, same
personalized copy. You remove the two tools that exist purely for evasion (Dolphin, sending
proxies) and the warmup-to-evade requirement, and you add a human at the send step plus a small
in-house console.
