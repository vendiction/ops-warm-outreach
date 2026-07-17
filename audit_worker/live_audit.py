"""One-shot LIVE audit — the whole moat in a single run, no DB, no 72h wait.

    OPTIN_URL=https://your.page  AUDIT_EMAIL=you@zohomail.com  AUDIT_PASS=app-password \
    IMAP_HOST=imap.zoho.com python live_audit.py [--read-only] [--wait 60]

Steps:
  1. Opens the funnel in a real browser (patchright/chromium) and submits the email  [skip with --read-only]
  2. Waits a bit for the sequence to fire (--wait seconds; default 90)
  3. Reads the inbox over IMAP, classifies every email, aggregates a gap finding
  4. Prints the finding + the Claude gap summary (or the deterministic fallback)

This is the same code path the real audit worker uses — just driven directly.
"""
import argparse
import asyncio
import os
import sys
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

URL = os.getenv("OPTIN_URL", "")
EMAIL = os.getenv("AUDIT_EMAIL", "")
PASS = os.getenv("AUDIT_PASS", "")
HOST = os.getenv("IMAP_HOST", "imap.zoho.com")
PORT = int(os.getenv("IMAP_PORT", "993"))


async def opt_in():
    from modes.info_optin import InfoOptinMode
    print(f"[1/3] Opting in at {URL} as {EMAIL} ...")
    await InfoOptinMode(funnel_url=URL, inbox_email=EMAIL).run()
    print("      submitted (browser closed)")


def _majority_signal(classified: list) -> str:
    signals = [m.get("deliverability", "primary") for m in classified]
    return max(set(signals), key=signals.count) if signals else "primary"


def _aggregate(classified: list) -> dict:
    """Same logic as the worker's aggregate() — inlined so this script doesn't need
    FastAPI/Postgres just to read an inbox."""
    welcomes = [m for m in classified if m["classification"] == "welcome"]
    carts = [m for m in classified if m["classification"] == "cart_recovery"]
    apps = [m for m in classified if m["classification"] == "application_followup"]
    optins = [m for m in classified if m["classification"] == "optin_recovery"]
    confirms = [m for m in classified if m["classification"] == "confirmation"]

    recovery = carts + apps + optins
    first_recovery = None
    if recovery:
        with_hours = [m for m in recovery if m.get("received_hours_after_trigger") is not None]
        if with_hours:
            first_recovery = min(m["received_hours_after_trigger"] for m in with_hours)

    double_optin = len(confirms) > 0
    confirm_in_spam = any(m.get("deliverability") == "spam" for m in confirms)

    return {
        "welcome_email_received": len(welcomes) > 0,
        "welcome_has_cta": any(m.get("has_cta") for m in welcomes),
        "abandoned_cart_count": len(carts),
        "abandoned_application_followup_count": len(apps),
        "optin_followup_count": len(optins),
        "double_optin_detected": double_optin,
        "confirmation_in_spam": confirm_in_spam,
        "first_recovery_delay_hours": first_recovery,
        "discount_offered": any(m.get("has_discount") for m in classified),
        "discount_amount": next((m.get("discount_amount") for m in classified if m.get("has_discount")), None),
        "total_emails_received_72h": len(classified),
        "deliverability_signal": _majority_signal(classified),
        "raw_email_captures": classified,
    }


def _gap_line(f: dict) -> str:
    """Deterministic gap summary for the demo (Claude version used when a key is set)."""
    if f.get("confirmation_in_spam"):
        return ("Double opt-in confirmation email is landing in SPAM — subscribers who never see it "
                "never confirm, so you're silently losing the top of your list. Highest-priority fix.")
    if f.get("double_optin_detected"):
        return ("Funnel uses double opt-in — every unconfirmed signup is a lost lead. Worth testing "
                "single opt-in or a stronger confirmation nudge.")
    if not f.get("welcome_email_received"):
        return "No welcome email fires after opt-in — the first, warmest moment is wasted."
    if f.get("first_recovery_delay_hours") and f["first_recovery_delay_hours"] > 12:
        return (f"First follow-up lands {f['first_recovery_delay_hours']}h after opt-in — most of the "
                "engagement window is already gone.")
    if not f.get("welcome_has_cta"):
        return "Welcome email has no clear CTA — early engagement is left on the table."
    return "Opt-in sequence is thin — few follow-ups, limited recovery of drop-offs."


def read_and_classify(since_ts):
    from imap_tools import MailBox
    from imap_parser import classify_email

    print(f"[3/3] Reading {EMAIL} over IMAP (all folders) ...")
    classified = []
    with MailBox(HOST, port=PORT).login(EMAIL, PASS) as mb:
        # Real audits MUST scan spam too — a recovery/confirmation email in spam is a finding.
        for folder_info in mb.folder.list():
            fname = folder_info.name
            is_spam = any(s in fname.lower() for s in ("spam", "junk", "bulk"))
            try:
                mb.folder.set(fname)
            except Exception:
                continue
            for msg in mb.fetch(mark_seen=False):
                when = msg.date
                if when and when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                if since_ts and when and when < since_ts:
                    continue
                folder = "Spam" if is_spam else "INBOX"
                rec = classify_email(msg.subject or "", (msg.text or msg.html or "")[:5000], folder=folder)
                hrs = ((when - since_ts).total_seconds() / 3600) if (since_ts and when) else 0.0
                rec["received_hours_after_trigger"] = round(max(hrs, 0.0), 2)
                rec["_folder"] = fname
                classified.append(rec)

    if not classified:
        print("\n  No emails found since opt-in. Either the sequence hasn't fired yet"
              "  (try a longer --wait) or the funnel sends nothing — which is itself a finding.")
        return

    print(f"\n=== Emails captured: {len(classified)} ===")
    for r in classified:
        disc = f" discount={r['discount_amount']}" if r.get("has_discount") else ""
        print(f"  [{r['deliverability']:>7}] {r['classification']:<22} +{r['received_hours_after_trigger']}h "
              f"cta={r['has_cta']}{disc}  (folder: {r.get('_folder','?')})\n            \"{r['subject'][:70]}\"")

    findings = _aggregate(classified)
    show = {k: v for k, v in findings.items() if k != "raw_email_captures"}
    print("\n=== Aggregated findings ===")
    print(json.dumps(show, indent=2))

    print("\n=== Gap summary (what drafting would use) ===")
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from claude_gap_summary import generate_gap_summary
            print(asyncio.run(generate_gap_summary(0, "info_optin_abandon", findings)))
        except Exception:
            print(_gap_line(findings))
    else:
        print(_gap_line(findings))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--read-only", action="store_true", help="skip the browser opt-in; just read+classify")
    ap.add_argument("--wait", type=int, default=90, help="seconds to wait for the sequence (default 90)")
    args = ap.parse_args()

    missing = [k for k, v in {"AUDIT_EMAIL": EMAIL, "AUDIT_PASS": PASS}.items() if not v]
    if missing or (not args.read_only and not URL):
        sys.exit(f"Missing env: {', '.join(missing + ([] if (args.read_only or URL) else ['OPTIN_URL']))}")

    since = datetime.now(timezone.utc)
    if not args.read_only:
        asyncio.run(opt_in())
        print(f"[2/3] Waiting {args.wait}s for the sequence to fire ...")
        import time
        time.sleep(args.wait)
    else:
        since = None
        print("[read-only] classifying everything currently in the inbox")

    read_and_classify(since)


if __name__ == "__main__":
    main()
