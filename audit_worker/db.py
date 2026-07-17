"""DB access for the audit worker: a lazy pooled connection and update_audit()."""
import json
from contextlib import contextmanager
from typing import Iterator

from psycopg_pool import ConnectionPool

from config import get_config

_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(get_config().database_url, min_size=1, max_size=5, open=True)
    return _pool


@contextmanager
def get_conn() -> Iterator:
    """Context manager yielding a pooled connection (commits on clean exit)."""
    with _get_pool().connection() as conn:
        yield conn


# Columns update_audit() is allowed to write. Anything else in **fields is ignored,
# so main.py can splat findings dicts without risking a bad column name.
_ALLOWED = {
    "audit_status", "failure_reason", "completed_at",
    "welcome_email_received", "welcome_has_cta",
    "abandoned_cart_count", "abandoned_application_followup_count",
    "first_recovery_delay_hours", "discount_offered", "discount_amount",
    "total_emails_received_72h", "deliverability_signal", "gap_summary",
    "raw_email_captures",
}
_JSONB = {"raw_email_captures"}


def update_audit(audit_id: int, **fields) -> None:
    """Update a lead_audits row with the provided findings/status. jsonb columns
    are json-encoded; unknown keys are dropped. Always bumps updated_at."""
    set_parts, values = [], []
    for key, val in fields.items():
        if key not in _ALLOWED:
            continue
        if key in _JSONB:
            set_parts.append(f"{key} = %s::jsonb")
            values.append(json.dumps(val, default=str))
        else:
            set_parts.append(f"{key} = %s")
            values.append(val)
    if not set_parts:
        return
    set_parts.append("updated_at = NOW()")
    values.append(audit_id)
    sql = f"UPDATE lead_audits SET {', '.join(set_parts)} WHERE id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, values)
            conn.commit()
