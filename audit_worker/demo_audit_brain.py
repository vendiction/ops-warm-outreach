"""
Realistic audit-brain demo (no Bridge, no IMAP, no cost).
Throws a varied, messy set of funnel emails at the classifier, then aggregates them
into a gap finding exactly like a real 72h audit would produce.

    python audit_worker/demo_audit_brain.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from imap_parser import classify_email  # noqa
import main  # aggregate + majority_signal  # noqa

# (subject, body, folder, hours_after_optin) — a realistic INFO opt-in funnel over 72h
INBOX = [
    ("Welcome to the free training!",
     "Thanks for signing up. Here's your access link. Watch the first module now.",
     "INBOX", 0.1),
    ("Did you get a chance to start?",
     "Just checking in — you signed up but haven't watched yet. Jump back in here.",
     "INBOX", 22.0),
    ("Your bonus expires soon",
     "As a thank-you, here's 20% off the full program with code TRAIN20. Grab it before Friday.",
     "INBOX", 47.5),
    ("[Newsletter] 5 tips for better funnels",
     "This week's roundup of marketing tips and a case study.",
     "INBOX", 50.0),
    ("Out of office",
     "I'm away until Monday and will reply when I'm back.",
     "INBOX", 51.0),  # noise — auto-reply-ish
    ("Flash sale: 20% off ends tonight",
     "Last chance. Use code TRAIN20. Enroll now.",
     "Spam", 60.0),   # landed in spam
]

print("=== Per-email classification ===\n")
classified = []
for subject, body, folder, hrs in INBOX:
    rec = classify_email(subject, body, folder=folder)
    rec["received_hours_after_trigger"] = hrs
    classified.append(rec)
    tag = f"[{rec['deliverability']:>7}]"
    disc = f" discount={rec['discount_amount']}" if rec.get("has_discount") else ""
    print(f"{tag} {rec['classification']:<22} cta={str(rec['has_cta']):<5}{disc}")
    print(f"          \"{subject}\"  (+{hrs}h)\n")

print("=== Aggregated audit findings (what scoring/drafting would receive) ===\n")
findings = main.aggregate(classified)
show = {k: v for k, v in findings.items() if k != "raw_email_captures"}
print(json.dumps(show, indent=2))
print(f"\nmajority deliverability signal: {main.majority_signal(classified)}")

# A plain-English gap line (the deterministic fallback the real worker uses if Claude is down)
from claude_gap_summary import _fallback
print("\n=== Example gap_summary (deterministic fallback) ===")
print(_fallback("info_optin_abandon", findings))
