-- seed_test_leads.sql — Phase 1 test fixtures.
--
-- Inserts 10 RAW prospects with icp_tier left NULL and is_archived FALSE, as they'd look
-- BEFORE the classifier runs. Two ways to use them:
--
--   A) Offline logic test (no DB, no Apollo credits) — preferred:
--        node scripts/test_icp_filter.mjs        # asserts the classifier routes all 10 correctly
--
--   B) End-to-end DB test — run this file, then apply the classifier via your workflow (or the
--      UPDATE block at the bottom which mirrors classifyLead), then run the verification query.
--
-- Cleanup: DELETE FROM leads WHERE source = 'seed_test';

BEGIN;

INSERT INTO leads (domain, company_name, founder_email, source, source_metadata) VALUES
  -- 3 clean info-business -> should route primary_info, active
  ('scalewithsam.com',  'Scale With Sam',        'sam@scalewithsam.com',  'seed_test', '{"description":"1:1 business coaching and a group mastermind for founders","keywords":["coach","mastermind"],"employee_count":8,"annual_revenue_usd":3000000}'),
  ('coursecraft.io',    'CourseCraft',           'hi@coursecraft.io',     'seed_test', '{"description":"Online course teaching paid ads to consultants","keywords":["course","online business"],"employee_count":4,"annual_revenue_usd":1800000}'),
  ('lena-consults.com', 'Lena Queen Consulting', 'lena@lena-consults.com','seed_test', '{"description":"Marketing consultant and mentor program","keywords":["consultant","mentor","program"],"employee_count":2,"annual_revenue_usd":1400000}'),
  -- 2 clean ecom meeting bar -> should route secondary_ecom, active
  ('glowskin.co',       'GlowSkin',              'team@glowskin.co',      'seed_test', '{"description":"DTC skincare brand","keywords":["shopify","ecommerce","dtc"],"employee_count":25,"annual_revenue_usd":12000000}'),
  ('trailgear.com',     'TrailGear',             'ops@trailgear.com',     'seed_test', '{"description":"Outdoor gear ecommerce","keywords":["woocommerce","ecommerce"],"employee_count":40,"annual_revenue_usd":20000000}'),
  -- 2 dropshippers -> archive: dropshipper
  ('fastdropship.store','Fast Dropship Store',   NULL,                    'seed_test', '{"description":"AliExpress dropshipping made easy","keywords":["dropshipping"],"employee_count":3,"annual_revenue_usd":2000000}'),
  ('teeprint.co',       'TeePrint',              NULL,                    'seed_test', '{"description":"Print on demand t-shirts","keywords":[],"employee_count":5,"annual_revenue_usd":3000000}'),
  -- 2 local businesses -> archive: brick_and_mortar
  ('bellasalon.com',    'Bella Salon',           NULL,                    'seed_test', '{"description":"A local hair salon and spa","keywords":[],"employee_count":12,"annual_revenue_usd":1500000}'),
  ('joespizza.com',     'Joes Pizza',            NULL,                    'seed_test', '{"description":"Family restaurant serving NY slices","keywords":[],"employee_count":30,"annual_revenue_usd":2500000}'),
  -- 1 sub-threshold info -> archive: below_revenue_threshold ($50k/mo)
  ('tinymentor.com',    'Tiny Mentor',           NULL,                    'seed_test', '{"description":"Solo coaching mentor","keywords":["coach","mentor"],"employee_count":1,"annual_revenue_usd":600000}')
ON CONFLICT (LOWER(domain)) DO NOTHING;

COMMIT;

-- ---------------------------------------------------------------------------
-- OPTIONAL: apply classification in-DB (mirrors scripts/icp_filter.js) so the
-- end-to-end path can be verified without running n8n. Order matters: archive first.
-- ---------------------------------------------------------------------------
-- UPDATE leads SET is_archived=TRUE, icp_tier='disqualified', archive_reason='dropshipper'
--   WHERE source='seed_test' AND (company_name ~* 'dropship|aliexpress|print on demand' OR source_metadata->>'description' ~* 'dropship|aliexpress|print on demand');
-- UPDATE leads SET is_archived=TRUE, icp_tier='disqualified', archive_reason='brick_and_mortar'
--   WHERE source='seed_test' AND is_archived=FALSE AND source_metadata->>'description' ~* '\y(local|restaurant|salon|dentist|chiropractor|retail store)\y';
-- UPDATE leads SET is_archived=TRUE, icp_tier='disqualified', archive_reason='below_revenue_threshold'
--   WHERE source='seed_test' AND is_archived=FALSE AND (source_metadata->>'annual_revenue_usd')::numeric/12 < 100000;
-- UPDATE leads SET icp_tier='secondary_ecom'
--   WHERE source='seed_test' AND is_archived=FALSE AND icp_tier IS NULL AND source_metadata->>'keywords' ~* 'shopify|woocommerce|bigcommerce|magento|ecommerce|dtc';
-- UPDATE leads SET icp_tier='primary_info'
--   WHERE source='seed_test' AND is_archived=FALSE AND icp_tier IS NULL;

-- ---------------------------------------------------------------------------
-- VERIFICATION — expected: 3 primary_info active, 2 secondary_ecom active, 5 archived w/ reasons
-- ---------------------------------------------------------------------------
-- SELECT icp_tier, is_archived, archive_reason, COUNT(*)
-- FROM leads WHERE source='seed_test'
-- GROUP BY 1,2,3 ORDER BY 1,2;
