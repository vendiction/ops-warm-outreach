-- 002_hitl_posted_flag.sql
-- Adds the flag the Phase 6 Discord HITL bot uses to avoid re-posting drafts it has
-- already surfaced. (The spec calls this "migration 003"; the repo only had 001, so this
-- is the second migration — numbering is sequential in this repo, not per-spec.)

BEGIN;

ALTER TABLE lead_outreach
  ADD COLUMN IF NOT EXISTS posted_to_hitl BOOLEAN NOT NULL DEFAULT FALSE;

-- The bot's hot-path query: drafts not yet posted, hottest first.
CREATE INDEX IF NOT EXISTS idx_lead_outreach_hitl_queue
  ON lead_outreach (created_at)
  WHERE status = 'draft' AND posted_to_hitl = FALSE;

COMMIT;
