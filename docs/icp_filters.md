# ICP Filters — Hard Disqualifiers & Tier Routing

**Applied in:** Phase 1 sourcing, inside the n8n Code node, BEFORE any Claude call or paid enrichment.
**Canonical logic:** `scripts/icp_filter.js` (`classifyLead()`). The n8n Code node holds a copy of the
same function — keep them in sync; this file is the human-readable spec both follow.

The rule: nothing is silently dropped. A lead either routes to a tier or is written with
`is_archived = TRUE` and a specific `archive_reason`. We keep archived rows so we can audit the
filter and re-open false negatives.

---

## Order of evaluation

1. **Hard disqualifiers** (any match → archive). Checked first, cheapest, no API cost.
2. **Tier routing** (if not archived). Provisional at Phase 1 from Apollo fields; Phase 2 refines
   with real tech-stack detection.

---

## 1. Hard disqualifiers — archive if ANY are true

| Reason code | Trigger | Matched against |
|-------------|---------|-----------------|
| `dropshipper` | `dropship`, `dropshipping`, `aliexpress`, `print on demand`, `pod` | company name + description |
| `brick_and_mortar` | `local`, `restaurant`, `salon`, `dentist`, `chiropractor`, `retail store` | description |
| `below_revenue_threshold` | Apollo monthly-revenue bucket `< $100K/mo`, or unknown for a lead that would route `primary_info` | revenue bucket |
| `geo_local_domain` | domain ends `.local`/`.city`, or is an obvious city-name site | domain |
| `too_enterprise` | employee count `> 500` (wrong motion for our retainer) | employee count |

Word matches are case-insensitive and word-boundary aware (so "localization" ≠ "local", and a
company literally named "POD" only trips on the standalone token). Revenue is treated as **monthly**
per the ICP; Apollo reports annual, so we divide by 12 before comparing.

## 2. Tier routing — if not archived

Evaluated in order; first match wins.

### → `secondary_ecom`
- Cart/ecom signal in Apollo keywords or industry: `shopify`, `woocommerce`, `bigcommerce`, `magento`, `ecommerce`, `dtc`
- (Phase 2 also confirms via `/products/` or `/shop/` in the sitemap.)

### → `primary_info`
- Info-business keywords in name/description/keywords: `coach`, `course`, `consultant`, `mastermind`, `program`, `mentor`, `info product`, `online business`, `agency`
- (Phase 2 also confirms via tech stack: `kajabi`, `teachable`, `thinkific`, `podia`, `clickfunnels`, `convertkit`, `activecampaign`.)

### → fallback
- No clear signal either way → route `primary_info` but tag `source_metadata.routing_confidence = "low"`
  so Phase 2/Phase 4 can re-check. We do **not** archive on ambiguity — that's a false-negative risk
  the spec says to surface to Jon, not auto-kill.

---

## Secondary-tier gating (the tighter ecom thresholds)

The dual-tier ICP gates ecom harder than info because ecom margins can't absorb a $5K retainer as
easily. Apollo alone can't see list size / AOV, so **full secondary-tier gating happens in Phase 4
scoring**, once enrichment has list and AOV signals. At Phase 1 we only assign the provisional
`secondary_ecom` tier; the 80K-list/$70-AOV vs 60–100K/$27-AOV test is a scoring-phase concern.
Documented here so nobody expects Phase 1 to enforce it.

---

## Borderline cases → escalate, don't guess

Per the spec: if the filter can't confidently place a lead (e.g. a "consultant" who's actually a
local financial advisor), it routes with `routing_confidence = "low"`. If low-confidence exceeds
~30% of a run, batch those to Jon in Discord for a rules tune rather than letting the filter drift.
