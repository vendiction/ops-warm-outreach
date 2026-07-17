"""Disposable-inbox pool with rotation policy.

Weekly usage is DERIVED from lead_audits (no extra table): an inbox that appears as
disposable_inbox on N audits started in the last 7 days has been used N times. Cooldowns
(48h normal, 6h on early failure) are persisted in a small JSON state file so an inbox
isn't reused too soon. pick_inbox() returns the first inbox under both limits.
"""
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import get_config


@dataclass
class Inbox:
    email: str
    imap_host: str
    imap_port: int
    user: str
    password: str


def load_pool() -> list[Inbox]:
    """Read the ProtonMail pool file. Shape: [{address, imap_host, imap_port, user, pass}]."""
    with open(get_config().protonmail_pool_file) as f:
        data = json.load(f)
    return [
        Inbox(
            email=i["address"],
            imap_host=i.get("imap_host", "127.0.0.1"),
            imap_port=int(i.get("imap_port", 1143)),
            user=i.get("user", i["address"]),
            password=i["pass"],
        )
        for i in data
    ]


def creds_for(email: str) -> Optional[Inbox]:
    for inbox in load_pool():
        if inbox.email == email:
            return inbox
    return None


def _load_state() -> dict:
    try:
        with open(get_config().inbox_state_file) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    path = get_config().inbox_state_file
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f)


def _weekly_usage() -> dict:
    """email -> (count_last_7d, last_started_at) from lead_audits."""
    from db import get_conn  # lazy: keeps module import free of a live DB
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT disposable_inbox, COUNT(*), MAX(started_at)
                FROM lead_audits
                WHERE started_at > NOW() - INTERVAL '7 days' AND disposable_inbox IS NOT NULL
                GROUP BY disposable_inbox
                """
            )
            return {r[0]: (r[1], r[2]) for r in cur.fetchall()}


def pick_inbox() -> Optional[Inbox]:
    cfg = get_config()
    pool = load_pool()
    usage = _weekly_usage()
    state = _load_state()
    now = datetime.now(timezone.utc)
    for inbox in pool:
        used, last = usage.get(inbox.email, (0, None))
        if used >= cfg.inbox_max_per_week:
            continue
        cd = state.get(inbox.email, {}).get("cooldown_until")
        if cd and datetime.fromisoformat(cd) > now:
            continue
        if last and (now - last) < timedelta(hours=cfg.inbox_cooldown_hours):
            continue
        return inbox
    return None


def release_inbox(inbox: Inbox, cooldown_hours: Optional[int] = None) -> None:
    cfg = get_config()
    hours = cooldown_hours if cooldown_hours is not None else cfg.inbox_cooldown_hours
    state = _load_state()
    state.setdefault(inbox.email, {})["cooldown_until"] = (
        datetime.now(timezone.utc) + timedelta(hours=hours)
    ).isoformat()
    _save_state(state)


def pool_stats() -> dict:
    try:
        pool = load_pool()
    except Exception as e:
        return {"total": 0, "available_est": 0, "error": f"pool file unreadable: {e}"}
    try:
        usage = _weekly_usage()
    except Exception:
        usage = {}  # DB not reachable during health check — report structural stats only
    cap = get_config().inbox_max_per_week
    available = sum(1 for i in pool if usage.get(i.email, (0, None))[0] < cap)
    return {"total": len(pool), "available_est": available}
