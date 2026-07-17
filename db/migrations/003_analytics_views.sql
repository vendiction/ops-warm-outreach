-- 003_analytics_views.sql
-- Phase 8 analytics views. Read-only reporting layer over the operational tables.
-- Metabase points its read-only role at these; the digest service queries them too.
-- (Spec calls this migration 004; repo is at 002, so this is 003 — sequential numbering.)
--
-- Send/reply metrics will read as zero until Phase 7 is live and producing sends —
-- that's expected, not a bug. v_persona_health is deferred: it needs profile_send_log,
-- a Phase 7 table that doesn't exist yet (stub noted at the bottom).

BEGIN;

-- Event counts per day per type (the raw pipeline pulse).
CREATE OR REPLACE VIEW v_daily_pipeline AS
SELECT DATE(occurred_at) AS day, event_type, COUNT(*) AS n
FROM outreach_events
WHERE occurred_at >= NOW() - INTERVAL '30 days'
GROUP BY 1, 2;

-- The funnel: how far each day's sourced leads have progressed.
CREATE OR REPLACE VIEW v_conversion_funnel AS
SELECT
  DATE(l.created_at) AS source_day,
  COUNT(*) FILTER (WHERE NOT l.is_archived) AS sourced,
  COUNT(*) FILTER (WHERE le.enrichment_status = 'complete') AS enriched,
  COUNT(*) FILTER (WHERE la.audit_status = 'complete') AS audited,
  COUNT(*) FILTER (WHERE l.qualification_score >= 15) AS qualified,
  COUNT(*) FILTER (WHERE EXISTS (
      SELECT 1 FROM lead_outreach lo WHERE lo.lead_id = l.id AND lo.status = 'sent')) AS contacted,
  COUNT(*) FILTER (WHERE EXISTS (
      SELECT 1 FROM lead_outreach lo WHERE lo.lead_id = l.id AND lo.reply_classification = 'interested')) AS interested_replies
FROM leads l
LEFT JOIN lead_enrichment le ON le.lead_id = l.id
LEFT JOIN lead_audits la ON la.lead_id = l.id
GROUP BY 1;

-- Audit worker health — completions vs failures, with the failure reason breakdown.
CREATE OR REPLACE VIEW v_audit_health AS
SELECT DATE(completed_at) AS day, audit_status, failure_reason, COUNT(*) AS n
FROM lead_audits
WHERE completed_at IS NOT NULL AND completed_at >= NOW() - INTERVAL '30 days'
GROUP BY 1, 2, 3;

-- Rolling audit success rate (last 7 days) — one number for the digest health line.
CREATE OR REPLACE VIEW v_audit_success_7d AS
SELECT
  COUNT(*) FILTER (WHERE audit_status = 'complete') AS complete,
  COUNT(*) FILTER (WHERE audit_status = 'failed') AS failed,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE audit_status = 'complete')
    / NULLIF(COUNT(*) FILTER (WHERE audit_status IN ('complete', 'failed')), 0), 0
  ) AS success_pct
FROM lead_audits
WHERE completed_at >= NOW() - INTERVAL '7 days';

-- Score distribution (histogram buckets + tier).
CREATE OR REPLACE VIEW v_score_distribution AS
SELECT
  qualification_score AS score,
  CASE
    WHEN qualification_score >= 20 THEN 'hot'
    WHEN qualification_score >= 15 THEN 'warm'
    WHEN qualification_score >= 10 THEN 'cold'
    ELSE 'archive'
  END AS tier,
  COUNT(*) AS n
FROM leads
WHERE qualification_score IS NOT NULL
GROUP BY 1, 2;

-- HITL queue depth + how long drafts have been waiting.
CREATE OR REPLACE VIEW v_hitl_queue AS
SELECT
  lo.channel::text AS channel,
  COUNT(*) AS drafts_waiting,
  ROUND(EXTRACT(EPOCH FROM (NOW() - MIN(lo.created_at))) / 3600.0, 1) AS oldest_wait_hours,
  ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - lo.created_at))) / 3600.0, 1) AS avg_wait_hours
FROM lead_outreach lo
WHERE lo.status = 'draft'
GROUP BY 1;

-- Per-channel send + reply rates (empty until Phase 7 sends).
CREATE OR REPLACE VIEW v_channel_reply_rates AS
SELECT
  channel::text AS channel,
  DATE(sent_at) AS sent_day,
  COUNT(*) FILTER (WHERE status IN ('sent', 'replied')) AS sent,
  COUNT(*) FILTER (WHERE reply_received_at IS NOT NULL) AS replied,
  COUNT(*) FILTER (WHERE reply_classification = 'interested') AS interested,
  COUNT(*) FILTER (WHERE reply_classification = 'not_interested') AS not_interested
FROM lead_outreach
WHERE sent_at >= NOW() - INTERVAL '30 days'
GROUP BY 1, 2;

-- Rejection reasons for weekly prompt tuning (which drafts get killed and why).
CREATE OR REPLACE VIEW v_reject_reasons AS
SELECT rejected_reason, COUNT(*) AS n
FROM lead_outreach
WHERE status = 'rejected' AND rejected_reason IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC;

-- Disposable-inbox pool health, derived from audit usage (last 7 days).
CREATE OR REPLACE VIEW v_inbox_health AS
SELECT
  disposable_inbox,
  COUNT(*) AS audits_last_7d,
  MAX(started_at) AS last_used,
  (MAX(started_at) > NOW() - INTERVAL '48 hours') AS in_cooldown
FROM lead_audits
WHERE disposable_inbox IS NOT NULL AND started_at >= NOW() - INTERVAL '7 days'
GROUP BY 1;

-- v_persona_health: DEFERRED to Phase 7. It needs profile_send_log (per-persona daily
-- send counts + cooldowns), which the sending executor creates. Placeholder so the
-- dashboard card has a stable name to bind to once Phase 7 lands:
--   CREATE VIEW v_persona_health AS SELECT ... FROM profile_send_log ...;

COMMIT;
