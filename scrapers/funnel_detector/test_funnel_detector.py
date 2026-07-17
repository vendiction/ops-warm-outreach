"""
Offline test of funnel_detector's pure heuristics (no network).
  python scrapers/funnel_detector/test_funnel_detector.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from main import detect_tech_stack, detect_funnel  # noqa

BASE = "https://example.com"

cases = [
    # (name, html, sitemap_urls, expected_funnel_type, expected_cart_or_none)
    ("ecom shopify",
     '<script src="https://cdn.shopify.com/s/files/x.js"></script><a href="/cart">Cart</a>',
     ["https://example.com/products/widget", "https://example.com/cart"],
     "ecom_cart_abandon", "shopify"),
    ("info application",
     '<html><a href="/apply">Apply to work with me</a> klaviyo.com/onsite</html>',
     ["https://example.com/apply"],
     "info_application_abandon", None),
    ("info optin webinar",
     '<html>Join the free <a href="/masterclass">masterclass</a></html>',
     ["https://example.com/masterclass"],
     "info_optin_abandon", None),
    ("homepage email form only",
     '<form><input type="email" placeholder="you@x.com"></form> subscribe to newsletter',
     [],
     "info_optin_abandon", None),
    ("no funnel",
     '<html><body>About us. Contact.</body></html>',
     [],
     None, None),
]

passed = 0
for name, html, sm, exp_type, exp_cart in cases:
    tech = detect_tech_stack(html)
    url, ftype, sel, conf = detect_funnel(BASE, html, sm, tech)
    ok = (ftype == exp_type) and (tech.cart == exp_cart)
    passed += ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: type={ftype} cart={tech.cart} conf={conf}")
    if not ok:
        print(f"       expected type={exp_type} cart={exp_cart}")

# tech-stack detection spot checks
t = detect_tech_stack('connect.facebook.net/en_US/fbevents.js gtag/js?id=G-ABC123 convertkit.com')
tech_ok = t.has_fb_pixel and t.has_ga4 and t.esp == "convertkit"
print(f"[{'PASS' if tech_ok else 'FAIL'}] tech stack: esp={t.esp} pixel={t.has_fb_pixel} ga4={t.has_ga4}")
passed += tech_ok

total = len(cases) + 1
print(f"\n{passed}/{total} passed")
sys.exit(0 if passed == total else 1)
