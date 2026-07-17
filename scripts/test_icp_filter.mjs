/**
 * test_icp_filter.mjs — offline test of the Phase 1 classifier.
 * Runs the 10 spec fixtures (3 info, 2 ecom, 5 disqualified) with zero API cost.
 *
 *   node scripts/test_icp_filter.mjs
 */
import { classifyLead } from "./icp_filter.js";

const fixtures = [
  // --- 3 clean info-business → primary_info ---
  { name: "info-1 coach", raw: { domain: "scalewithsam.com", company_name: "Scale With Sam",
      description: "1:1 business coaching and a group mastermind for founders", keywords: ["coach", "mastermind"],
      employee_count: 8, annual_revenue_usd: 3_000_000 }, expect: { icp_tier: "primary_info", is_archived: false } },
  { name: "info-2 course", raw: { domain: "coursecraft.io", company_name: "CourseCraft",
      description: "Online course teaching paid ads to consultants", keywords: ["course", "online business"],
      employee_count: 4, annual_revenue_usd: 1_800_000 }, expect: { icp_tier: "primary_info", is_archived: false } },
  { name: "info-3 consultant", raw: { domain: "lena-consults.com", company_name: "Lena Queen Consulting",
      description: "Marketing consultant and mentor program", keywords: ["consultant", "mentor", "program"],
      employee_count: 2, annual_revenue_usd: 1_400_000 }, expect: { icp_tier: "primary_info", is_archived: false } },

  // --- 2 clean ecom meeting bar → secondary_ecom (final gating in Phase 4) ---
  { name: "ecom-1 shopify", raw: { domain: "glowskin.co", company_name: "GlowSkin",
      description: "DTC skincare brand", keywords: ["shopify", "ecommerce", "dtc"],
      employee_count: 25, annual_revenue_usd: 12_000_000 }, expect: { icp_tier: "secondary_ecom", is_archived: false } },
  { name: "ecom-2 woo", raw: { domain: "trailgear.com", company_name: "TrailGear",
      description: "Outdoor gear ecommerce", keywords: ["woocommerce", "ecommerce"],
      employee_count: 40, annual_revenue_usd: 20_000_000 }, expect: { icp_tier: "secondary_ecom", is_archived: false } },

  // --- 5 disqualified ---
  { name: "dq-1 dropshipper", raw: { domain: "fastdropship.store", company_name: "Fast Dropship Store",
      description: "AliExpress dropshipping made easy", keywords: ["dropshipping"],
      employee_count: 3, annual_revenue_usd: 2_000_000 }, expect: { is_archived: true, archive_reason: "dropshipper" } },
  { name: "dq-2 dropshipper-pod", raw: { domain: "teeprint.co", company_name: "TeePrint",
      description: "Print on demand t-shirts", keywords: [],
      employee_count: 5, annual_revenue_usd: 3_000_000 }, expect: { is_archived: true, archive_reason: "dropshipper" } },
  { name: "dq-3 local salon", raw: { domain: "bellasalon.com", company_name: "Bella Salon",
      description: "A local hair salon and spa", keywords: [],
      employee_count: 12, annual_revenue_usd: 1_500_000 }, expect: { is_archived: true, archive_reason: "brick_and_mortar" } },
  { name: "dq-4 local restaurant", raw: { domain: "joespizza.com", company_name: "Joe's Pizza",
      description: "Family restaurant serving NY slices", keywords: [],
      employee_count: 30, annual_revenue_usd: 2_500_000 }, expect: { is_archived: true, archive_reason: "brick_and_mortar" } },
  { name: "dq-5 sub-threshold info", raw: { domain: "tinymentor.com", company_name: "Tiny Mentor",
      description: "Solo coaching mentor", keywords: ["coach", "mentor"],
      employee_count: 1, annual_revenue_usd: 600_000 }, // $50k/mo < $100k → below_revenue_threshold
      expect: { is_archived: true, archive_reason: "below_revenue_threshold" } },
];

let pass = 0, fail = 0;
for (const f of fixtures) {
  const got = classifyLead(f.raw);
  const okTier = f.expect.icp_tier === undefined || got.icp_tier === f.expect.icp_tier;
  const okArch = f.expect.is_archived === undefined || got.is_archived === f.expect.is_archived;
  const okReason = f.expect.archive_reason === undefined || got.archive_reason === f.expect.archive_reason;
  const ok = okTier && okArch && okReason;
  ok ? pass++ : fail++;
  console.log(`[${ok ? "PASS" : "FAIL"}] ${f.name} → ${JSON.stringify(got)}`);
  if (!ok) console.log(`        expected ${JSON.stringify(f.expect)}`);
}
console.log(`\n${pass}/${pass + fail} passed`);
process.exit(fail === 0 ? 0 : 1);
