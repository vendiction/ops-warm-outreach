"""
similarweb — Phase 2. Monthly-traffic estimate for a domain.

No account needed for the default path (scrapes SimilarWeb's PUBLIC website page).
Optional SIMILARWEB_API_KEY enables the free API (100/mo) as a fallback for leads
that will proceed to audit. Reads public data only.

  POST /traffic  {"domain":"example.com"} -> {domain, traffic_estimate, source, reason}

traffic_estimate is monthly visits (int) or null when it can't be read — null must be
treated as "unknown", never 0.
"""
import os, re, logging
from typing import Optional
import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("similarweb")
API_KEY = os.getenv("SIMILARWEB_API_KEY")
IPROYAL_PROXY = os.getenv("IPROYAL_PROXY")
IPROYAL_USER = os.getenv("IPROYAL_PROXY_USER")
IPROYAL_PASS = os.getenv("IPROYAL_PROXY_PASS")

app = FastAPI(title="similarweb-scraper", version="0.1.0")

class TrafficRequest(BaseModel):
    domain: str = Field(..., min_length=3)

class TrafficResponse(BaseModel):
    domain: str
    traffic_estimate: Optional[int]
    source: Optional[str] = None   # 'public_scrape' | 'api' | None
    reason: Optional[str] = None

def _proxy():
    if not IPROYAL_PROXY:
        return None
    cfg = {"server": f"http://{IPROYAL_PROXY}"}
    if IPROYAL_USER: cfg["username"] = IPROYAL_USER
    if IPROYAL_PASS: cfg["password"] = IPROYAL_PASS
    return cfg

def _parse_visits(text: str) -> Optional[int]:
    # e.g. "1.2M", "850K", "12,345" near a 'Total Visits' label
    m = re.search(r"([\d.,]+)\s*([KMB])?\s*(?:total visits|visits)", text, re.I)
    if not m:
        m = re.search(r"total visits[^0-9]{0,40}([\d.,]+)\s*([KMB])?", text, re.I)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get((m.group(2) or "").upper(), 1)
    return int(num * mult)

async def _api(domain: str) -> Optional[int]:
    if not API_KEY:
        return None
    url = (f"https://api.similarweb.com/v1/website/{domain}/total-traffic-and-engagement/visits"
           f"?api_key={API_KEY}&granularity=monthly&main_domain_only=true")
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url)
            if r.status_code == 200:
                visits = r.json().get("visits", [])
                if visits:
                    return int(visits[-1].get("visits", 0))
    except Exception as e:
        log.info("api fallback failed: %s", e)
    return None

@app.post("/traffic", response_model=TrafficResponse)
async def traffic(req: TrafficRequest) -> TrafficResponse:
    # 1) public scrape
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, proxy=_proxy())
            page = await browser.new_page()
            try:
                await page.goto(f"https://www.similarweb.com/website/{req.domain}/",
                                timeout=30000, wait_until="domcontentloaded")
                body = await page.inner_text("body")
                est = _parse_visits(body)
            finally:
                await browser.close()
        if est is not None:
            return TrafficResponse(domain=req.domain, traffic_estimate=est, source="public_scrape")
    except PWTimeout:
        pass
    except Exception as e:
        log.info("public scrape failed: %s", e)
    # 2) API fallback
    est = await _api(req.domain)
    if est is not None:
        return TrafficResponse(domain=req.domain, traffic_estimate=est, source="api")
    return TrafficResponse(domain=req.domain, traffic_estimate=None, reason="traffic_unavailable")

@app.get("/health")
async def health():
    return {"status": "ok", "api_fallback": bool(API_KEY), "proxy": bool(IPROYAL_PROXY)}
