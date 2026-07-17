-- =====================================================
-- OPS-WARM-OUTREACH — Initial Schema
-- Migration: 001
-- Owner: Kyle
-- =====================================================
-- Run against the Postgres instance on the Hostinger VPS.
-- Assumes database `warm_outreach` already created.

BEGIN;

-- =====================================================
-- ENUMS
-- =====================================================

CREATE TYPE audit_status_enum AS ENUM (
  'pending',
  'in_progress',
  'complete',
  'failed'
);

CREATE TYPE outreach_channel_enum AS ENUM (
  'dm_ig',
  'dm_linkedin',
  'dm_fb',
  'cold_email'
);

CREATE TYPE outreach_status_enum AS ENUM (
  'draft',
  'approved',
  'rejected',
  'skipped',
  'sent',
  'replied',
  'bounced',
  'failed'
);

CREATE TYPE audit_mode_enum AS ENUM (
  'ecom_cart_abandon',
  'info_optin_abandon',
  'info_application_abandon'
);

CREATE TYPE icp_tier_enum AS ENUM (
  'primary_info',
  'secondary_ecom',
  'disqualified'
);

CREATE TYPE reply_classification_enum AS ENUM (
  'interested',
  'objection',
  'not_interested',
  'unclear',
  'auto_reply'
);

-- =====================================================
-- 1. LEADS — raw sourced prospects
-- =====================================================

CREATE TABLE leads (
  id                    BIGSERIAL PRIMARY KEY,
  domain                TEXT NOT NULL,
  company_name          TEXT,
  founder_name          TEXT,
  founder_email         TEXT,
  founder_ig_handle     TEXT,
  founder_linkedin_url  TEXT,
  founder_fb_handle     TEXT,
  source                TEXT NOT NULL,  -- 'apollo', 'meta_ad_library', 'storeleads', 'manual', etc.
  source_metadata       JSONB DEFAULT '{}'::jsonb,
  icp_tier              icp_tier_enum,
  qualification_score   SMALLINT,       -- 0–25, populated in Phase 4
  qualification_subscores JSONB,         -- {revenue: 5, margin: 4, list: 5, growth: 3, authority: 4}
  qualification_reasoning TEXT,
  is_archived           BOOLEAN NOT NULL DEFAULT FALSE,
  archive_reason        TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_leads_domain ON leads (LOWER(domain));
CREATE INDEX idx_leads_score ON leads (qualification_score DESC NULLS LAST);
CREATE INDEX idx_leads_tier_active ON leads (icp_tier) WHERE is_archived = FALSE;
CREATE INDEX idx_leads_created ON leads (created_at DESC);

-- =====================================================
-- 2. LEAD_ENRICHMENT — traffic, tech stack, social posts
-- =====================================================

CREATE TABLE lead_enrichment (
  id                    BIGSERIAL PRIMARY KEY,
  lead_id               BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  traffic_estimate      INTEGER,        -- monthly visitors
  tech_stack            JSONB,          -- {esp: 'klaviyo', cart: 'shopify', ...}
  funnel_entry_url      TEXT,           -- URL for audit worker to hit
  funnel_type           audit_mode_enum,
  recent_social_posts   JSONB,          -- [{platform, url, text, posted_at}, ...]
  enrichment_status     TEXT NOT NULL DEFAULT 'complete',  -- 'complete', 'failed', 'partial'
  enrichment_failure_reason TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_enrichment_lead ON lead_enrichment (lead_id);
CREATE INDEX idx_enrichment_status ON lead_enrichment (enrichment_status);

-- =====================================================
-- 3. LEAD_AUDITS — 72hr funnel audit results
-- =====================================================

CREATE TABLE lead_audits (
  id                    BIGSERIAL PRIMARY KEY,
  lead_id               BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  audit_mode            audit_mode_enum NOT NULL,
  audit_status          audit_status_enum NOT NULL DEFAULT 'pending',
  disposable_inbox      TEXT,           -- which ProtonMail address was used
  proxy_session_id      TEXT,
  started_at            TIMESTAMPTZ,
  audit_completes_at    TIMESTAMPTZ,    -- started_at + 72hr; scheduler polls this
  completed_at          TIMESTAMPTZ,
  failure_reason        TEXT,

  -- Structured findings
  welcome_email_received  BOOLEAN,
  welcome_has_cta         BOOLEAN,
  abandoned_cart_count    SMALLINT,
  abandoned_application_followup_count SMALLINT,
  first_recovery_delay_hours NUMERIC(6, 2),
  discount_offered        BOOLEAN,
  discount_amount         TEXT,
  total_emails_received_72h SMALLINT,
  deliverability_signal   TEXT,        -- 'primary' | 'promotions' | 'spam'
  gap_summary             TEXT,        -- Claude-generated one-liner
  raw_email_captures      JSONB,       -- headers, subjects, bodies (compressed)

  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audits_lead ON lead_audits (lead_id);
CREATE INDEX idx_audits_status ON lead_audits (audit_status);
CREATE INDEX idx_audits_ready_to_parse
  ON lead_audits (audit_completes_at)
  WHERE audit_status = 'in_progress';

-- =====================================================
-- 4. LEAD_OUTREACH — drafted / approved messages
-- =====================================================

CREATE TABLE lead_outreach (
  id                    BIGSERIAL PRIMARY KEY,
  lead_id               BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  channel               outreach_channel_enum NOT NULL,
  sequence_step         SMALLINT NOT NULL,   -- 1, 2, 3 for DMs; 1–4 for cold email
  status                outreach_status_enum NOT NULL DEFAULT 'draft',
  draft_body            TEXT NOT NULL,
  draft_char_count      SMALLINT,
  draft_model           TEXT,               -- 'sonnet', 'opus'
  approved_body         TEXT,               -- if edited in HITL, differs from draft_body
  approved_by           TEXT,               -- Discord user
  approved_at           TIMESTAMPTZ,
  rejected_reason       TEXT,
  sent_at               TIMESTAMPTZ,
  send_metadata         JSONB,              -- {profile_id, proxy_session, inbox_id, ...}
  reply_received_at     TIMESTAMPTZ,
  reply_body            TEXT,
  reply_classification  reply_classification_enum,
  reply_reasoning       TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_outreach_lead ON lead_outreach (lead_id);
CREATE INDEX idx_outreach_status_channel ON lead_outreach (status, channel);
CREATE INDEX idx_outreach_pending_send
  ON lead_outreach (channel, approved_at)
  WHERE status = 'approved';

-- =====================================================
-- 5. OUTREACH_EVENTS — append-only audit log
-- =====================================================

CREATE TABLE outreach_events (
  id                    BIGSERIAL PRIMARY KEY,
  lead_id               BIGINT REFERENCES leads(id) ON DELETE SET NULL,
  outreach_id           BIGINT REFERENCES lead_outreach(id) ON DELETE SET NULL,
  event_type            TEXT NOT NULL,      -- 'source', 'enrich', 'audit_start', 'audit_complete', 'score', 'draft', 'approve', 'send', 'reply', 'error', 'archive'
  event_data            JSONB DEFAULT '{}'::jsonb,
  actor                 TEXT,               -- 'system', 'julia', 'kyle', 'jon', discord user
  occurred_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_lead_time ON outreach_events (lead_id, occurred_at DESC);
CREATE INDEX idx_events_type_time ON outreach_events (event_type, occurred_at DESC);

-- =====================================================
-- Updated-at triggers
-- =====================================================

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_leads_touch
  BEFORE UPDATE ON leads
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TRIGGER trg_enrichment_touch
  BEFORE UPDATE ON lead_enrichment
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TRIGGER trg_audits_touch
  BEFORE UPDATE ON lead_audits
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

CREATE TRIGGER trg_outreach_touch
  BEFORE UPDATE ON lead_outreach
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

COMMIT;

-- =====================================================
-- Sanity checks (run after migration)
-- =====================================================
-- SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
-- Expected: lead_audits, lead_enrichment, lead_outreach, leads, outreach_events
