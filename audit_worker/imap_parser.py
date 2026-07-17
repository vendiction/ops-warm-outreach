"""IMAP fetch + heuristic classification of a funnel's recovery emails.

classify_email(subject, body) is a pure, stdlib-only function (unit-tested offline).
fetch_and_classify() connects to the disposable inbox, reads INBOX (primary) and the
Spam/Junk folder (spam), and returns one dict per message in the shape aggregate()
in main.py expects.
"""
import re
from datetime import datetime, timezone
from typing import Optional

# --- classification keyword sets ---------------------------------------------
_WELCOME = [r"\bwelcome\b", r"thanks? for (signing|subscrib|joining)", r"you'?re in"]
# Double opt-in confirmation — a distinct pattern (and a finding: friction + often spam).
_CONFIRM = [r"confirm your (email|subscription|sign-?up)", r"confirm that .* correct email",
            r"please confirm", r"verify your (email|subscription)", r"confirmation email",
            r"click .*to confirm", r"not be subscribed unless", r"double opt-?in", r"almost there"]
_CART = [r"forgot something", r"left .*in your (cart|bag)", r"still (thinking|interested)",
         r"complete your (order|purchase)", r"your cart", r"come back"]
_APP = [r"application", r"your call", r"book(ing)? your", r"schedule", r"we received your",
        r"next steps", r"strategy (call|session)"]
# Info-funnel nurture / opt-in recovery — softer language than ecom cart recovery.
_OPTIN = [r"did you get a chance", r"haven'?t (watched|started|finished|had a chance|seen)",
          r"still (there|interested|want|time)", r"checking in", r"jump back", r"pick up where",
          r"your (access|spot|seat|link|training)", r"don'?t miss", r"expires?", r"last chance",
          r"\breminder\b", r"finish (the|your|watching)", r"you signed up", r"ready to (start|dive|watch)",
          r"complete your (registration|signup|sign-up|profile)", r"before (it'?s gone|friday|midnight|tonight)"]
_DISCOUNT = [r"\b\d{1,2}%\s*off\b", r"\$\d+\s*off", r"coupon", r"promo code", r"discount", r"save \d"]
_CTA = [r"<a\s", r"shop now", r"complete", r"book now", r"claim", r"get started", r"finish", r"checkout"]


def _any(pats: list, text: str) -> bool:
    return any(re.search(p, text, re.I) for p in pats)


def _discount_amount(text: str) -> Optional[str]:
    m = re.search(r"(\d{1,2}%)\s*off", text, re.I) or re.search(r"(\$\d+)\s*off", text, re.I)
    return m.group(1) if m else None


def classify_email(subject: str, body: str, folder: str = "INBOX") -> dict:
    """Pure classifier. folder drives the deliverability signal (spam folder -> 'spam')."""
    subject = subject or ""
    body = body or ""
    text = f"{subject}\n{body}"
    if _any(_CONFIRM, text):
        classification = "confirmation"
    elif _any(_APP, text):
        classification = "application_followup"
    elif _any(_CART, text):
        classification = "cart_recovery"
    elif _any(_WELCOME, text):
        classification = "welcome"
    elif _any(_OPTIN, text):
        classification = "optin_recovery"
    else:
        classification = "other"
    has_discount = _any(_DISCOUNT, text)
    deliverability = "spam" if folder.lower() in ("spam", "junk") else "primary"
    return {
        "classification": classification,
        "has_cta": _any(_CTA, text),
        "has_discount": has_discount,
        "discount_amount": _discount_amount(text) if has_discount else None,
        "deliverability": deliverability,
        "subject": subject[:300],
    }


def fetch_and_classify(inbox_email: str, since: Optional[datetime] = None) -> list:
    """Connect to the inbox, read INBOX + Spam, classify each message. Lazy imports so
    importing this module needs no imap/db deps."""
    from imap_tools import MailBox, AND  # lazy
    from inbox_pool import creds_for      # lazy

    creds = creds_for(inbox_email)
    if not creds:
        raise RuntimeError(f"no credentials for inbox {inbox_email}")

    trigger = since or datetime.now(timezone.utc)
    results = []
    for folder in ("INBOX", "Spam"):
        try:
            with MailBox(creds.imap_host, port=creds.imap_port).login(
                creds.user, creds.password, initial_folder=folder
            ) as mb:
                criteria = AND(date_gte=trigger.date()) if since else AND(all=True)
                for msg in mb.fetch(criteria, mark_seen=False):
                    body = msg.text or msg.html or ""
                    rec = classify_email(msg.subject, body, folder=folder)
                    hours_after = None
                    if msg.date:
                        md = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=timezone.utc)
                        hours_after = round((md - trigger).total_seconds() / 3600, 2)
                    rec["received_hours_after_trigger"] = hours_after
                    rec["from"] = getattr(msg, "from_", None)
                    rec["date"] = msg.date.isoformat() if msg.date else None
                    results.append(rec)
        except Exception:
            # A missing Spam folder (naming varies) shouldn't fail the whole parse.
            if folder == "INBOX":
                raise
    # earliest first, so aggregate()'s "first recovery" is chronological
    results.sort(key=lambda r: r.get("received_hours_after_trigger") or 0)
    return results
