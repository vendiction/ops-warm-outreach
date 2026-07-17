# funnel_detector (Phase 2, port 8094)

Fetches a prospect's public homepage + sitemap and returns:
- `funnel_entry_url` + `funnel_type` (`ecom_cart_abandon` / `info_optin_abandon` / `info_application_abandon`) + `form_selector` — the audit modality for Phase 3
- `tech_stack` (esp / cart / page_builder / has_fb_pixel / has_ga4) — folded in from the same fetch

**No account needed** — reads public pages only, httpx (no browser).

`POST /detect  {"domain":"example.com"}`. Returns `funnel_type=null` + `reason="no discoverable funnel"` when nothing is found (never guesses).

Detection heuristics are pure functions (`detect_funnel`, `detect_tech_stack`) — test offline:
`python test_funnel_detector.py`  (6/6). Re-tune the path/signal lists there when real leads reveal misses.
