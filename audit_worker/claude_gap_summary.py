"""Generate the one-line gap_summary from audit findings via Claude.

Loads the system prompt from prompts/audit_gap_summary_sonnet.md. On repeated API
failure it returns a deterministic template sentence so the audit still completes —
a failed summary must never blackhole a completed audit.
"""
import json
from pathlib import Path
from typing import Optional

from config import get_config

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "audit_gap_summary_sonnet.md"


def _system_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return ("You turn structured funnel-audit findings into ONE crisp sentence (under 25 "
                "words) naming the specific gap. Return only the sentence, no preamble.")


def _fallback(audit_mode: str, f: dict) -> str:
    total = f.get("total_emails_received_72h") or 0
    if total == 0:
        return "No follow-up emails arrived in 72 hours — the recovery funnel is silent."
    if audit_mode == "ecom_cart_abandon" and not f.get("abandoned_cart_count"):
        return "Welcome sends but there's zero abandoned-cart recovery — bailed carts leave silently."
    if f.get("first_recovery_delay_hours") and f["first_recovery_delay_hours"] > 12:
        return (f"First recovery email lands {round(f['first_recovery_delay_hours'])}h after drop-off — "
                "most of the window is already lost.")
    if f.get("welcome_email_received") and not f.get("welcome_has_cta"):
        return "Welcome email has no CTA and little follow-up — early engagement is left on the table."
    return "Follow-up sequence exists but has clear timing and coverage gaps leaking revenue."


async def generate_gap_summary(lead_id: int, audit_mode: str, findings: dict) -> str:
    cfg = get_config()
    payload = {
        "audit_mode": audit_mode,
        "findings": {k: v for k, v in findings.items() if k != "raw_email_captures"},
    }
    if not cfg.anthropic_api_key:
        return _fallback(audit_mode, findings)

    try:
        from anthropic import AsyncAnthropic  # lazy
        from tenacity import retry, stop_after_attempt, wait_exponential  # lazy

        client = AsyncAnthropic(api_key=cfg.anthropic_api_key)

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
        async def _call() -> str:
            msg = await client.messages.create(
                model=cfg.gap_summary_model,
                max_tokens=250,
                temperature=0.3,
                system=_system_prompt(),
                messages=[{"role": "user", "content": json.dumps(payload)}],
            )
            return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()

        text = await _call()
        return text or _fallback(audit_mode, findings)
    except Exception:
        return _fallback(audit_mode, findings)
