# 17 — Preorder URL audit across all 40 sites

## Question

No site config mentions ennakkotilaus, preorder or tulossa today, so preorder listings are either never fetched or fetched from a normal category with a badge nobody parses. Add the URLs and the provenance plumbing. See [spec](../spec-tracker-refocus.md) → "Preorder URLs".

**Config:** new `preorder_urls` array alongside `source_url` / `source_urls`.

**Plumbing:**
- `paginator.source_urls(config)` returns preorder URLs too, tagged so the caller knows which is which (e.g. a list of `(url, is_preorder)` pairs, with the existing string-list helper kept for the site-identity lookup, which must stay the first normal URL).
- `runner._scrape_source_url` passes `from_preorder_url` into `detect_availability` and into `upsert_listing`.
- A listing seen on both a normal and a preorder URL in one run keeps the last sighting's flag, matching the existing "last occurrence wins" dedupe.

**Audit, per site (40):** find the shop's preorder category or tag URL. Candidate patterns to check: `/ennakkotilaus`, `/ennakkotilaukset`, `/ennakko`, `/tulossa`, `/pre-order`, `/preorder`, `/kommande`, `/kommer-snart`, plus the shop's own tag and filter URLs. Verify the page actually lists products and paginates the same way the site's other URLs do. Where a shop has no separate preorder page, record that and note whether its normal categories carry preorder items with a badge (that case is ticket 18's problem, not this one).

The same pass re-checks normal category coverage: a product that is never fetched can never produce an event. Where a gap is obvious, add the URL.

**Deliverable:** `.scratch/tracker-refocus/preorder-urls.md`, one line per site: site, preorder URL or "none exists", product count seen on it, notes. Same shape as the ticket-06 multi-URL audit.

**Tests:** `tests/test_site_configs.py` checks that every `preorder_urls` entry is an absolute URL on the site's own host. `tests/test_runner.py` covers the `from_preorder_url` flag reaching `listings` (that test belongs to ticket 19's set; either ticket may land it).

**Status: OPEN**

Blocking: nothing
Blocked by: 15
