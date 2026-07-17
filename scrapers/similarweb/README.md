# similarweb (Phase 2, port 8092)

Monthly-traffic estimate. **No account needed** for the default public scrape.
Set `SIMILARWEB_API_KEY` (free tier, 100/mo) to enable the API fallback for high-value leads.

`POST /traffic {"domain":"example.com"}` -> `{traffic_estimate, source, reason}`.
`traffic_estimate=null` means unknown — never read it as 0. Per spec, if SimilarWeb blocks even
the public scrape, we skip traffic and proceed (it's a soft signal, not a gate).

SimilarWeb blocks headless aggressively — runs through IPRoyal if `IPROYAL_PROXY` is set.
The visits-parsing regex in `_parse_visits` is the thing to re-check if numbers look wrong.
