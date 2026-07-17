"""Offline tests for the audit worker's pure logic (no network, no DB).
  python audit_worker/test_audit_logic.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from imap_parser import classify_email  # noqa
import main  # aggregate + majority_signal live here  # noqa

passed = total = 0
def check(name, cond):
    global passed, total
    total += 1; passed += bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")

# --- classify_email ---
w = classify_email("Welcome to the club!", "Thanks for signing up. Shop now.")
check("welcome classified", w["classification"] == "welcome")
check("welcome cta detected", w["has_cta"] is True)

c = classify_email("You forgot something in your cart", "Complete your order and save 10% off")
check("cart classified", c["classification"] == "cart_recovery")
check("discount detected", c["has_discount"] and c["discount_amount"] == "10%")

a = classify_email("We received your application", "Next steps for your strategy call")
check("application classified", a["classification"] == "application_followup")

o = classify_email("Company newsletter", "Here is some news.")
check("other classified", o["classification"] == "other")

s = classify_email("Promo", "50% off", folder="Spam")
check("spam folder -> spam deliverability", s["deliverability"] == "spam")
check("inbox folder -> primary deliverability", w["deliverability"] == "primary")

# --- aggregate ---
classified = [
    {"classification": "welcome", "has_cta": True, "has_discount": False, "deliverability": "primary", "received_hours_after_trigger": 0.1},
    {"classification": "cart_recovery", "has_cta": True, "has_discount": True, "discount_amount": "15%", "deliverability": "primary", "received_hours_after_trigger": 3.5},
    {"classification": "cart_recovery", "has_cta": True, "has_discount": False, "deliverability": "spam", "received_hours_after_trigger": 20.0},
]
f = main.aggregate(classified)
check("welcome_email_received", f["welcome_email_received"] is True)
check("welcome_has_cta", f["welcome_has_cta"] is True)
check("abandoned_cart_count=2", f["abandoned_cart_count"] == 2)
check("discount_offered", f["discount_offered"] is True)
check("discount_amount=15%", f["discount_amount"] == "15%")
check("total=3", f["total_emails_received_72h"] == 3)
check("first_recovery_delay from earliest cart", f["first_recovery_delay_hours"] == 3.5)
check("raw captures preserved", len(f["raw_email_captures"]) == 3)

# --- majority_signal ---
check("majority primary", main.majority_signal(classified) == "primary")
check("majority empty -> primary", main.majority_signal([]) == "primary")

print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
