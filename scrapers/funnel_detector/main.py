"""
funnel_detector — Phase 2. The most important enrichment output: it decides the
audit modality (funnel_type) the Phase 3 worker will use, and detects tech stack in
the same homepage fetch (folded in here to avoid a second HTTP round-trip per lead).

Reads only PUBLIC pages (homepage + sitemap). No login, no account.

Endpoint:
  POST /detect  { "domain": "example.com" }
  -> { funnel_entry_url, funnel_type, form_selector, confidence, tech_stack }

funnel_type is one of the audit_mode_enum values so it can be written straight to
lead_enrichment.funnel_type:
  ecom_cart_abandon | info_optin_abandon | info_application_abandon | null

The detection heuristics live in pure functions (detect_funnel / detect_tech_stack)
so they can be unit-tested offline against saved HTML — see test_funnel_detector.py.
"""
import os
import re
import logging
from typing import Optional
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("funnel_detector")

FETCH_TIMEOUT = float(os.getenv("FUNNEL_FETCH_TIMEOUT", "15"))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

app = FastAPI(title="funnel-detector", version="0.1.0")


class DetectRequest(BaseModel):
    domain: str = Field(..., min_length=3)


class TechStack(BaseModel):
    esp: Optional[str] = None
    cart: Optional[str] = None
    page_builder: Optional[str] = None
    has_fb_pixel: bool = False
    has_ga4: bool = False
    confidence: str = "low"


class DetectResponse(BaseModel):
    domain: str
    funnel_entry_url: Optional[str]
    funnel_type: Optional[str]
    form_selector: Optional[str]
    confidence: str
    tech_stack: TechStack
    reason: Optional[str] = None


# ---- pure detection cores (offline-testable) --------------------------------

ESP_SIGNS = {
    "klaviyo": [r"klaviyo\.com/onsite", r"static\.klaviyo\.com", r"a\.klaviyo\.com"],
    "mailchimp": [r"list-manage\.com", r"chimpstatic\.com"],
    "activecampaign": [r"activecampaign\.com", r"ac-analytics"],
    "convertkit": [r"convertkit\.com", r"ck\.page"],
    "hubspot": [r"js\.hs-scripts\.com", r"hsubspot"],
}
CART_SIGNS = {
    "shopify": [r"cdn\.shopify\.com", r"myshopify\.com", r"shopify-features", r"/cdn/shop/"],
    "woocommerce": [r"wp-content/plugins/woocommerce", r"wc-ajax=", r"woocommerce-page"],
    "bigcommerce": [r"bigcommerce\.com", r"stencil-utils"],
    "magento": [r"Magento_", r"mage-cache-storage", r"/static/version\d+/frontend/", r"magentocdn"],
}
BUILDER_SIGNS = {
    "kajabi": [r"mykajabi\.com", r"kajabi-storefronts", r"kajabi\.com"],
    "teachable": [r"teachable\.com", r"fedora-cdn"],
    "clickfunnels": [r"clickfunnels\.com", r"myclickfunnels"],
    "leadpages": [r"leadpages\.co", r"lpages\.co"],
    "unbounce": [r"unbounce\.com", r"ubembed"],
    "thinkific": [r"thinkific\.com"],
    "podia": [r"podia\.com"],
    "kartra": [r"kartra\.com"],
}
# Course/coaching platforms => an info business, never ecom.
_INFO_PLATFORMS = {"kajabi", "teachable", "thinkific", "podia", "kartra"}


def _first_hit(html: str, table: dict) -> Optional[str]:
    for name, pats in table.items():
        if any(re.search(p, html, re.I) for p in pats):
            return name
    return None


def detect_tech_stack(html: str) -> TechStack:
    esp = _first_hit(html, ESP_SIGNS)
    cart = _first_hit(html, CART_SIGNS)
    builder = _first_hit(html, BUILDER_SIGNS)
    has_pixel = bool(re.search(r"connect\.facebook\.net/.*/fbevents\.js|fbq\(", html, re.I))
    has_ga4 = bool(re.search(r"gtag/js\?id=G-|gtag\(['\"]config['\"],\s*['\"]G-", html, re.I))
    hits = sum(x is not None for x in (esp, cart, builder))
    confidence = "high" if hits >= 2 else ("medium" if hits == 1 else "low")
    return TechStack(esp=esp, cart=cart, page_builder=builder,
                     has_fb_pixel=has_pixel, has_ga4=has_ga4, confidence=confidence)


# Path signals for funnel typing, in priority order.
APPLICATION_PATHS = [r"/apply", r"/book-a-call", r"/schedule", r"/consultation", r"/strategy-call", r"/call"]
OPTIN_PATHS = [r"/vsl", r"/webinar", r"/masterclass", r"/free-training", r"/training", r"/guide", r"/download", r"/free"]
ECOM_PATHS = [r"/cart", r"/checkout", r"/products/", r"/shop", r"/collections/"]


def detect_funnel(base_url: str, html: str, sitemap_urls: list, tech: TechStack):
    """Return (funnel_entry_url, funnel_type, form_selector, confidence)."""
    haystack = html.lower()
    all_paths = " ".join(sitemap_urls).lower() + " " + haystack

    def find_url(patterns):
        # Prefer a sitemap URL that matches; else construct from the path on base.
        for u in sitemap_urls:
            if any(re.search(p, u, re.I) for p in patterns):
                return u
        for p in patterns:
            if re.search(p, haystack):
                return urljoin(base_url, p.strip("\\").lstrip("/") and p.replace("\\", "").lstrip("/") or "")
        return None

    # 1) Application/booking (info high-ticket) — strongest info signal
    if any(re.search(p, all_paths) for p in APPLICATION_PATHS):
        return find_url(APPLICATION_PATHS) or base_url, "info_application_abandon", "form", "high"

    # A course/coaching platform means info — it can never be ecom.
    if tech.page_builder in _INFO_PLATFORMS:
        if any(re.search(p, all_paths) for p in OPTIN_PATHS):
            return find_url(OPTIN_PATHS) or base_url, "info_optin_abandon", "form.optin-form", "high"
        return base_url, "info_optin_abandon", "form", "medium"

    # 2) Ecom — only on a REAL cart platform or an explicit /cart|/checkout path.
    #    A bare /shop or /products (no cart tech) is NOT enough — it mislabels info stores.
    strong_cart_path = bool(re.search(r"/cart\b|/checkout\b", all_paths))
    if tech.cart or strong_cart_path:
        return (find_url(ECOM_PATHS) or base_url, "ecom_cart_abandon", None,
                "high" if (tech.cart and strong_cart_path) else "medium")

    # 3) Opt-in / lead magnet
    if any(re.search(p, all_paths) for p in OPTIN_PATHS):
        return find_url(OPTIN_PATHS) or base_url, "info_optin_abandon", "form.optin-form", "medium"

    # 4) Homepage has an email opt-in form → treat as opt-in on the homepage
    if re.search(r'<input[^>]+type=["\']?email', haystack) or re.search(r"newsletter|subscribe", haystack):
        return base_url, "info_optin_abandon", "form", "low"

    return None, None, None, "low"


# ---- HTTP fetch + endpoint --------------------------------------------------

async def _fetch(url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=FETCH_TIMEOUT,
                                     headers={"User-Agent": UA}) as c:
            r = await c.get(url)
            if r.status_code < 400:
                return r.text
    except Exception as e:
        log.info("fetch failed %s: %s", url, e)
    return None


async def _sitemap_urls(base_url: str) -> list:
    xml = await _fetch(urljoin(base_url, "/sitemap.xml"))
    if not xml:
        return []
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)[:500]


@app.post("/detect", response_model=DetectResponse)
async def detect(req: DetectRequest) -> DetectResponse:
    base = req.domain if req.domain.startswith("http") else f"https://{req.domain}"
    html = await _fetch(base)
    if html is None:
        return DetectResponse(domain=req.domain, funnel_entry_url=None, funnel_type=None,
                              form_selector=None, confidence="low", tech_stack=TechStack(),
                              reason="homepage_unreachable")
    tech = detect_tech_stack(html)
    sitemap = await _sitemap_urls(base)
    url, ftype, selector, conf = detect_funnel(base, html, sitemap, tech)
    reason = None if ftype else "no discoverable funnel"
    return DetectResponse(domain=req.domain, funnel_entry_url=url, funnel_type=ftype,
                          form_selector=selector, confidence=conf, tech_stack=tech, reason=reason)


@app.get("/health")
async def health():
    return {"status": "ok"}
