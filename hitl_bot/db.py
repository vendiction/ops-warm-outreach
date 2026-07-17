"""Postgres helpers for the HITL bot. All state transitions are guarded (only act on
rows still in 'draft') and each logs an outreach_event. Pure DB — no Discord imports,
so it's unit-testable against a live database."""
import os
import json
from contextlib import contextmanager
from typing import Optional

from psycopg_pool import ConnectionPool

_pool: Optional[ConnectionPool] = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=5, open=True)
    return _pool


@contextmanager
def _conn():
    with _get_pool().connection() as conn:
        yield conn


def tier_for(score: Optional[int]) -> str:
    if score is None:
        return "unknown"
    if score >= 20:
        return "hot"
    if score >= 15:
        return "warm"
    if score >= 10:
        return "cold"
    return "archive"


def fetch_unposted_drafts(limit: int = 5) -> list[dict]:
    """Drafts not yet posted to Discord, hottest first. Joins the context the embed needs."""
    sql = """
        SELECT lo.id, lo.lead_id, lo.channel::text AS channel, lo.sequence_step,
               lo.draft_body, lo.draft_char_count, lo.draft_model,
               l.company_name, l.qualification_score, a.gap_summary
        FROM lead_outreach lo
        JOIN leads l ON l.id = lo.lead_id
        LEFT JOIN lead_audits a ON a.lead_id = l.id AND a.audit_status = 'complete'
        WHERE lo.status = 'draft' AND lo.posted_to_hitl = FALSE
        ORDER BY l.qualification_score DESC NULLS LAST, lo.created_at ASC
        LIMIT %s
    """
    with _conn() as c, c.cursor() as cur:
        cur.execute(sql, (limit,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        r["tier"] = tier_for(r["qualification_score"])
    return rows


def mark_posted(outreach_ids: list[int]) -> None:
    if not outreach_ids:
        return
    with _conn() as c, c.cursor() as cur:
        cur.execute("UPDATE lead_outreach SET posted_to_hitl = TRUE WHERE id = ANY(%s)", (outreach_ids,))
        c.commit()


def _log_event(cur, lead_id: int, event_type: str, data: dict, actor: str) -> None:
    cur.execute(
        "INSERT INTO outreach_events (lead_id, event_type, event_data, actor) VALUES (%s,%s,%s::jsonb,%s)",
        (lead_id, event_type, json.dumps(data), actor),
    )


def approve(outreach_id: int, user: str, edited_body: Optional[str] = None) -> Optional[int]:
    """Approve one draft. If edited_body given, store it in approved_body (draft_body untouched
    so edit-rate is measurable). Returns lead_id, or None if it wasn't in 'draft'."""
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            UPDATE lead_outreach
            SET status = 'approved',
                approved_body = COALESCE(%s, draft_body),
                approved_by = %s,
                approved_at = NOW(),
                updated_at = NOW()
            WHERE id = %s AND status = 'draft'
            RETURNING lead_id
            """,
            (edited_body, user, outreach_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        lead_id = row[0]
        _log_event(cur, lead_id, "approved", {"outreach_id": outreach_id, "edited": edited_body is not None}, user)
        c.commit()
        return lead_id


def reject(outreach_id: int, user: str, reason: str) -> Optional[int]:
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            UPDATE lead_outreach
            SET status = 'rejected', rejected_reason = %s, approved_by = %s, updated_at = NOW()
            WHERE id = %s AND status = 'draft'
            RETURNING lead_id
            """,
            (reason, user, outreach_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        lead_id = row[0]
        _log_event(cur, lead_id, "rejected", {"outreach_id": outreach_id, "reason": reason}, user)
        c.commit()
        return lead_id


def skip_lead(lead_id: int, user: str) -> int:
    """Skip every remaining draft for a lead. Returns count skipped."""
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE lead_outreach SET status = 'skipped', updated_at = NOW() WHERE lead_id = %s AND status = 'draft'",
            (lead_id,),
        )
        n = cur.rowcount
        _log_event(cur, lead_id, "skipped", {"drafts_skipped": n}, user)
        c.commit()
        return n


def bulk_approve_warm(user: str, limit: int = 10) -> list[str]:
    """Approve the next N warm-queue (score 15-19) drafts. Hot queue (20+) is never
    included — enforced in SQL, not config. Returns approved company names."""
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            WITH picked AS (
                SELECT lo.id, lo.lead_id
                FROM lead_outreach lo
                JOIN leads l ON l.id = lo.lead_id
                WHERE lo.status = 'draft'
                  AND l.qualification_score BETWEEN 15 AND 19
                ORDER BY lo.created_at ASC
                LIMIT %s
            )
            UPDATE lead_outreach lo
            SET status = 'approved',
                approved_body = draft_body,
                approved_by = %s,
                approved_at = NOW(),
                updated_at = NOW()
            FROM picked
            WHERE lo.id = picked.id
            RETURNING lo.lead_id
            """,
            (limit, f"{user} (bulk)"),
        )
        lead_ids = [r[0] for r in cur.fetchall()]
        for lid in set(lead_ids):
            _log_event(cur, lid, "approved", {"bulk": True}, f"{user} (bulk)")
        names = []
        if lead_ids:
            cur.execute("SELECT company_name FROM leads WHERE id = ANY(%s)", (list(set(lead_ids)),))
            names = [r[0] for r in cur.fetchall()]
        c.commit()
        return names
