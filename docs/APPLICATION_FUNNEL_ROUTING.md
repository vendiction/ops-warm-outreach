# Application-Funnel Routing (Option C)

## The problem

The automated audit (the moat) opts into a prospect's funnel with a disposable inbox,
waits, and reads the emails that come back. This works on **simple opt-in funnels**
(email field → welcome sequence). It does **not** work on:

- **Application funnels** — multi-field "apply today" forms (often HubSpot). The audit
  worker can't complete a multi-field application, so the opt-in never registers.
- **reCAPTCHA-protected funnels** — solving captchas would be bot-detection evasion (out
  of scope by policy).

Proven live on a real prospect (Coach Academy / `canadacoachacademy.com/training` — a
HubSpot application form): the auto-opt-in filled one email field, but the application
never submitted, so no emails arrived.

Application funnels correlate with **higher-ticket coaches** ($5k–$50k programs, "apply to
work with me"). Those are among the *best* prospects — so simply skipping them throws away
premium leads.

## The decision — Option C

For application funnels, **don't audit — infer the gap from the funnel type.**

Application funnels have a near-universal structural weakness: **no recovery sequence for
people who start the application and don't finish.** Those are the warmest, highest-intent
leads (they pre-qualified themselves by starting), and they leak silently. That gap is
true for almost every application funnel, it's specific, and it's about *their money* — a
strong hook that needs no audit.

This is how a human strategist would assess an application funnel anyway. We never claim to
have opted in; the gap is honestly presented as an inferred structural observation.

## How it's implemented

Enrichment already detects funnel type and writes `lead_enrichment.funnel_type`
(`info_optin_abandon` | `info_application_abandon` | `ecom_cart_abandon`). Routing:

| Funnel type | Path |
|-------------|------|
| `info_optin_abandon` | Real audit worker (opt-in → IMAP → classify) |
| `info_application_abandon` | **Synth Audit workflow** → structural gap → scoring → drafting |
| captcha-detected | Skipped (no funnel_type route) |

The **`synth_audit_application.json`** workflow (n8n) runs every 10 min:
1. Finds application-funnel leads that are enriched but have no audit yet
2. Writes a synthetic `complete` audit row carrying the "leaking warm applicants" gap
3. Logs a `synthetic_application` audit event

Because scoring and drafting both key off a completed audit + its `gap_summary`, these
leads then flow through the rest of the belt **exactly like opt-in leads** — no downstream
special-casing. The resulting draft leads with the application-abandon hook.

## Honest caveat

The application-funnel gap is *inferred* (structural), not *audited* (proven-specific), so
it's slightly less personalized than a real opt-in audit. For funnels where a real audit
is impossible anyway, a strong inferred hook is the right call — and it keeps your
highest-value segment in the pipeline with zero manual work.

## Status: proven live

Tested end-to-end (2026-07-17): seeded an application-funnel lead (App Demo Coaching,
HubSpot), ran the synth-audit workflow → it wrote a `complete` audit with the structural
gap → scoring picked it up → drafting produced a 4-touch cold-email sequence that led with
the application-abandon hook and even referenced the HubSpot stack → posted to Discord.
Also fixed during testing: the log node now references `lead_id` from the Compose node
(the INSERT node doesn't pass it through).

## To activate

Import `shared/n8n-templates/synth_audit_application.json`, wire the Postgres credential on
its 3 DB nodes, and toggle it Active alongside the other workflows.
