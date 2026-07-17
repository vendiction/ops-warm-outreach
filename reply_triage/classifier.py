"""Shared reply-triage classifier. Pure text classification — no evasion, no browser.

Used by both the email-reply n8n path and the send console's "log a DM reply" action.
classify_reply(text) -> {classification, reasoning, urgency}. Loads the system prompt
verbatim from prompts/reply_triage_haiku.md. Falls back to 'unclear' on any API failure
so a bad classification never blocks a human from seeing the reply.
"""
import json
import os
import re
from pathlib import Path

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "reply_triage_haiku.md"
_VALID = {"interested", "objection", "not_interested", "unclear", "auto_reply"}
_URGENCY = {"high", "normal", "low"}
_MODEL = os.getenv("CLAUDE_HAIKU_MODEL", "claude-haiku-4-5-20251001")


def _system_prompt() -> str:
    try:
        text = _PROMPT_PATH.read_text(encoding="utf-8")
        return text[text.index("## System"):].strip()
    except Exception:
        return ("You classify prospect replies. Return strict JSON only: "
                '{"classification": one of interested|objection|not_interested|unclear|auto_reply, '
                '"reasoning": "<one sentence>", "urgency": high|normal|low}.')


def _parse(text: str) -> dict:
    """Parse + validate the model's JSON. Raises ValueError on anything malformed."""
    try:
        obj = json.loads(re.sub(r"```json|```", "", text or "").strip())
    except Exception as e:
        raise ValueError(f"malformed_json: {e}")
    c = obj.get("classification")
    if c not in _VALID:
        raise ValueError(f"bad_classification: {c}")
    u = obj.get("urgency")
    if u not in _URGENCY:
        u = "normal"
    return {"classification": c, "reasoning": (obj.get("reasoning") or "")[:300], "urgency": u}


def classify_reply(reply_text: str, api_key: str | None = None) -> dict:
    """Classify one reply. Returns the validated dict; on any failure returns a safe
    'unclear'/normal result so the human still gets pinged to look."""
    key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not (reply_text or "").strip():
        return {"classification": "unclear", "reasoning": "empty reply", "urgency": "normal"}
    if not key:
        return {"classification": "unclear", "reasoning": "no api key configured", "urgency": "normal"}
    try:
        from anthropic import Anthropic  # lazy
        client = Anthropic(api_key=key)
        msg = client.messages.create(
            model=_MODEL, max_tokens=200, temperature=0,
            system=_system_prompt(),
            messages=[{"role": "user", "content": reply_text[:4000]}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        return _parse(text)
    except Exception as e:
        return {"classification": "unclear", "reasoning": f"triage_error: {str(e)[:120]}", "urgency": "normal"}
