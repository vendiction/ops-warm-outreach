# OPS-WARM-OUTREACH

95% automated multi-channel client acquisition system for FascinateCopy.
Sells $5K–$7K/mo Full Stack Email Marketing retainers to info businesses, coaches, course creators, and qualifying ecom brands.

**Owner:** Kyle (lead dev)
**Direction:** Jon
**Ops:** Julia
**Pattern reference:** OPS-61, FC IG Lead Discovery

---

## Read First (in this order)

1. `docs/OPS-WARM-OUTREACH_KYLE_HANDOFF.pdf` — master context prompt. Paste into Claude at start of every session.
2. `docs/MASTER_PLAN.md` — same content as PDF, markdown form for grep and edits.
3. `build_specs/BUILD_SPEC_0_FOUNDATION.md` — where you start Day 1.

## Repo Layout

```
ops-warm-outreach/
├── README.md                     # this file
├── .env.example                  # secrets template
├── docs/
│   ├── OPS-WARM-OUTREACH_KYLE_HANDOFF.pdf
│   └── MASTER_PLAN.md
├── build_specs/
│   ├── BUILD_SPEC_0_FOUNDATION.md
│   ├── BUILD_SPEC_1_SOURCING.md
│   ├── BUILD_SPEC_2_ENRICHMENT.md
│   ├── BUILD_SPEC_3_AUDIT_WORKER.md
│   ├── BUILD_SPEC_4_SCORING.md
│   ├── BUILD_SPEC_5_DRAFTING.md
│   ├── BUILD_SPEC_6_HITL.md
│   ├── BUILD_SPEC_7_SENDING.md
│   └── BUILD_SPEC_8_ANALYTICS.md
├── db/
│   └── migrations/
│       └── 001_initial_schema.sql
├── audit_worker/                 # Phase 3 Python service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── modes/
│   │   ├── ecom.py
│   │   └── info_business.py
│   ├── imap_parser.py
│   └── README.md
├── prompts/                      # Claude prompt library
│   ├── scoring_haiku.md
│   ├── drafting_sonnet.md
│   ├── drafting_opus.md
│   ├── reply_triage_haiku.md
│   └── audit_gap_summary_sonnet.md
└── shared/
    └── n8n-templates/            # workflows exported as JSON here
```

## Session Workflow (per phase)

1. Read the `BUILD_SPEC_N.md` for the phase you're building.
2. Open a Claude Code session.
3. Paste the master context PDF as the first message.
4. Paste the build spec as the second message.
5. Build → test → commit → move to next phase.
6. Do NOT one-shot the whole system.

## Conventions

- No secrets in the repo. Use `.env` (gitignored).
- Per-phase README with run instructions.
- Postgres migrations numbered sequentially in `db/migrations/`.
- n8n workflows exported as JSON to `shared/n8n-templates/`.
- Python services isolated with their own `requirements.txt`.
- One Claude Code session per phase.

## Escalation

If a decision is needed that isn't in the master plan or build spec, ping Jon in Discord.
Do not silently expand scope. Do not assume.
