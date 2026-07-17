"""
OPS-WARM-OUTREACH — Audit Worker
Phase 3: Dockerized service for opting into prospect funnels, waiting 72hr,
and parsing recovery emails into structured audit findings.

Endpoints:
  POST /audit/start   — kicks off Playwright flow, returns audit_id
  POST /audit/parse   — invoked by n8n after 72hr, parses IMAP + calls Claude
  GET  /health        — status + pool health
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import Config
from db import get_conn, update_audit
from inbox_pool import pick_inbox, release_inbox
from proxy_pool import get_sticky_session
from imap_parser import fetch_and_classify
from claude_gap_summary import generate_gap_summary
from modes.ecom import EcomAbandonMode
from modes.info_optin import InfoOptinMode
from modes.info_application import InfoApplicationMode

app = FastAPI(title="ops-warm-outreach-audit-worker", version="0.1.0")

MODE_ROUTER = {
    "ecom_cart_abandon": EcomAbandonMode,
    "info_optin_abandon": InfoOptinMode,
    "info_application_abandon": InfoApplicationMode,
}


class StartAuditRequest(BaseModel):
    lead_id: int
    funnel_entry_url: str
    funnel_type: str = Field(..., pattern="^(ecom_cart_abandon|info_optin_abandon|info_application_abandon)$")
    form_selector: Optional[str] = None


class StartAuditResponse(BaseModel):
    audit_id: int
    audit_status: str
    audit_completes_at: datetime
    disposable_inbox: str


class ParseAuditRequest(BaseModel):
    audit_id: int


@app.post("/audit/start", response_model=StartAuditResponse, status_code=202)
async def start_audit(req: StartAuditRequest):
    """Trigger the funnel interaction and mark audit as in_progress."""
    ModeClass = MODE_ROUTER.get(req.funnel_type)
    if not ModeClass:
        raise HTTPException(400, f"unknown funnel_type: {req.funnel_type}")

    # Pick pool resources
    inbox = pick_inbox()
    if not inbox:
        raise HTTPException(503, "no inbox available in pool")
    proxy_session = get_sticky_session()

    # Insert audit row
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lead_audits (
                    lead_id, audit_mode, audit_status,
                    disposable_inbox, proxy_session_id,
                    started_at, audit_completes_at
                )
                VALUES (%s, %s, 'in_progress', %s, %s, NOW(), NOW() + INTERVAL '72 hours')
                RETURNING id, audit_completes_at
                """,
                (req.lead_id, req.funnel_type, inbox.email, proxy_session.id),
            )
            audit_id, completes_at = cur.fetchone()
            conn.commit()

    # Run the modality-specific Playwright flow
    mode = ModeClass(
        funnel_url=req.funnel_entry_url,
        inbox_email=inbox.email,
        proxy_url=proxy_session.url,
        form_selector=req.form_selector,
    )
    try:
        await mode.run()
    except Exception as e:
        # Mark audit failed immediately; release inbox for reuse sooner
        update_audit(
            audit_id,
            audit_status="failed",
            failure_reason=f"playwright_failure: {str(e)[:200]}",
        )
        release_inbox(inbox, cooldown_hours=6)  # short cooldown on early failure
        raise HTTPException(502, f"audit interaction failed: {e}")

    return StartAuditResponse(
        audit_id=audit_id,
        audit_status="in_progress",
        audit_completes_at=completes_at,
        disposable_inbox=inbox.email,
    )


@app.post("/audit/parse")
async def parse_audit(req: ParseAuditRequest):
    """IMAP-fetch, classify emails, generate gap_summary, write findings."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lead_id, audit_mode, disposable_inbox, started_at
                FROM lead_audits
                WHERE id = %s AND audit_status = 'in_progress'
                """,
                (req.audit_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "audit not found or not in_progress")
            lead_id, audit_mode, inbox_email, started_at = row

    # Fetch + classify
    try:
        classified = fetch_and_classify(inbox_email, since=started_at - timedelta(minutes=15))
    except Exception as e:
        update_audit(req.audit_id, audit_status="failed", failure_reason=f"imap_error: {str(e)[:200]}")
        raise HTTPException(502, f"IMAP failure: {e}")

    if not classified:
        update_audit(
            req.audit_id,
            audit_status="complete",
            welcome_email_received=False,
            abandoned_cart_count=0,
            abandoned_application_followup_count=0,
            total_emails_received_72h=0,
            gap_summary="No emails received during the 72-hour window — the funnel is not sending any follow-up.",
        )
        return {"ok": True, "audit_id": req.audit_id, "emails": 0}

    # Aggregate findings
    findings = aggregate(classified)

    # Claude gap summary
    findings["gap_summary"] = await generate_gap_summary(
        lead_id=lead_id, audit_mode=audit_mode, findings=findings
    )

    # Persist
    update_audit(
        req.audit_id,
        audit_status="complete",
        completed_at=datetime.now(timezone.utc),
        **findings,
    )
    return {"ok": True, "audit_id": req.audit_id, "emails": len(classified)}


def aggregate(classified: list) -> dict:
    """Turn a list of classified emails into the structured findings dict."""
    welcomes = [m for m in classified if m["classification"] == "welcome"]
    carts = [m for m in classified if m["classification"] == "cart_recovery"]
    apps = [m for m in classified if m["classification"] == "application_followup"]
    optins = [m for m in classified if m["classification"] == "optin_recovery"]

    # Earliest recovery email of ANY type sets the follow-up delay.
    recovery = carts + apps + optins
    first_recovery = None
    if recovery:
        with_hours = [m for m in recovery if m.get("received_hours_after_trigger") is not None]
        if with_hours:
            first_recovery = min(m["received_hours_after_trigger"] for m in with_hours)

    return {
        "welcome_email_received": len(welcomes) > 0,
        "welcome_has_cta": any(m.get("has_cta") for m in welcomes),
        "abandoned_cart_count": len(carts),
        "abandoned_application_followup_count": len(apps),
        # Not a DB column (update_audit ignores it); flows into the gap summary so info
        # funnels register their nurture/recovery volume:
        "optin_followup_count": len(optins),
        "first_recovery_delay_hours": first_recovery,
        "discount_offered": any(m.get("has_discount") for m in classified),
        "discount_amount": next((m.get("discount_amount") for m in classified if m.get("has_discount")), None),
        "total_emails_received_72h": len(classified),
        "deliverability_signal": majority_signal(classified),
        "raw_email_captures": classified,
    }


def majority_signal(classified: list) -> str:
    signals = [m.get("deliverability", "primary") for m in classified]
    return max(set(signals), key=signals.count) if signals else "primary"


@app.get("/health")
async def health():
    from inbox_pool import pool_stats
    from proxy_pool import proxy_healthy
    return {
        "status": "ok",
        "inbox_pool": pool_stats(),
        "proxy_healthy": proxy_healthy(),
    }
