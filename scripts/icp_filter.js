/**
 * icp_filter.js — canonical Phase 1 lead classifier.
 *
 * classifyLead(raw) takes a normalized prospect (from Apollo, StoreLeads, or a seed row)
 * and returns { icp_tier, is_archived, archive_reason, routing_confidence }.
 *
 * The n8n "Classify & Disqualify" Code node holds a copy of classifyLead(). Keep them in sync.
 * Rules are documented in docs/icp_filters.md.
 *
 * Input shape (normalize upstream before calling):
 *   {
 *     domain: string,
 *     company_name: string,
 *     description: string,
 *     keywords: string[],           // Apollo org keywords + industry, lowercased
 *     employee_count: number|null,
 *     annual_revenue_usd: number|null   // Apollo reports annual; we convert to monthly
 *   }
 */

const DROPSHIP = [/\bdropship(ping)?\b/i, /\baliexpress\b/i, /\bprint on demand\b/i, /\bpod\b/i];
const BRICK = [/\blocal\b/i, /\brestaurant\b/i, /\bsalon\b/i, /\bdentist\b/i, /\bchiropractor\b/i, /\bretail store\b/i];
const ECOM = ["shopify", "woocommerce", "bigcommerce", "magento", "ecommerce", "e-commerce", "dtc"];
const INFO = ["coach", "course", "consultant", "mastermind", "program", "mentor",
              "info product", "online business", "agency"];

const MIN_MONTHLY_REVENUE = 100_000;
const MAX_EMPLOYEES = 500;

function anyMatch(patterns, text) {
  return patterns.some((re) => re.test(text || ""));
}
function anyIncludes(needles, haystackArr) {
  const hay = (haystackArr || []).join(" ").toLowerCase();
  return needles.some((n) => hay.includes(n));
}

function classifyLead(raw) {
  const name = raw.company_name || "";
  const desc = raw.description || "";
  const nameDesc = `${name} ${desc}`;
  const domain = (raw.domain || "").toLowerCase();
  const keywords = raw.keywords || [];
  const monthlyRevenue = raw.annual_revenue_usd != null ? raw.annual_revenue_usd / 12 : null;

  // ---- 1. Hard disqualifiers (any → archive) ----
  if (anyMatch(DROPSHIP, nameDesc)) {
    return archived("dropshipper");
  }
  if (anyMatch(BRICK, desc)) {
    return archived("brick_and_mortar");
  }
  if (raw.employee_count != null && raw.employee_count > MAX_EMPLOYEES) {
    return archived("too_enterprise");
  }
  if (/\.(local|city)$/.test(domain)) {
    return archived("geo_local_domain");
  }

  // Provisional tier decides how strict the revenue gate is.
  const looksEcom = anyIncludes(ECOM, keywords) || anyIncludes(ECOM, [nameDesc]);
  const looksInfo = anyIncludes(INFO, keywords) || anyIncludes(INFO, [nameDesc]);

  // Revenue gate: primary_info requires known >= $100K/mo. Unknown revenue on an
  // info-routed lead is a disqualifier (per icp_filters.md); ecom unknown revenue is
  // allowed through to Phase 4 where list/AOV gating happens.
  if (monthlyRevenue != null && monthlyRevenue < MIN_MONTHLY_REVENUE) {
    return archived("below_revenue_threshold");
  }
  if (monthlyRevenue == null && looksInfo && !looksEcom) {
    return archived("below_revenue_threshold");
  }

  // ---- 2. Tier routing ----
  if (looksEcom) return routed("secondary_ecom", "high");
  if (looksInfo) return routed("primary_info", "high");
  return routed("primary_info", "low"); // ambiguous → keep, flag low confidence, never auto-kill
}

function archived(reason) {
  return { icp_tier: "disqualified", is_archived: true, archive_reason: reason, routing_confidence: "n/a" };
}
function routed(tier, confidence) {
  return { icp_tier: tier, is_archived: false, archive_reason: null, routing_confidence: confidence };
}

// Support both ESM (test harness) and n8n Code node (which uses CommonJS-ish global).
if (typeof module !== "undefined" && module.exports) {
  module.exports = { classifyLead };
}
export { classifyLead };
